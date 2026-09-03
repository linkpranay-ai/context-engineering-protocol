#!/usr/bin/env python3
"""wizard_retrofit_draft.py - reference-resolution and template-drafting for
Journey 3 (consumer/retrofit) Phase B (D24, ult-cep-wizard).

No LLM in the loop (Journey 3 plan's own scope decision 1): every drafted
sentence is a fixed, contract-specific template with the resolved reference
substituted in - never generated text. The frontend always presents the
result in an editable textarea (see wizard_retrofit_state.set_draft_override)
so a human supplies final wording; this module's output is a starting point,
never treated as final.

Contract order and reference resolution follow ult-cep-retrofit/SKILL.md Step
5/6 exactly:
  - Step 6.4: multiple confirmed contracts for one skill are combined into
    ONE block at ONE insertion point, in the fixed order CONTRACT_ORDER
    below - never separate passes that could compute different insertion
    points and scatter pointers through the file.
  - Step 5: exactly two v1-supported reference shapes, ask-don't-assume:
    same-repo (a relative path, computed here) or plugin-qualified (a
    human-supplied `/<plugin>:<skill>` reference, validated but never
    auto-detected). Anything else - CEP vendored at a subpath, or living in
    an entirely separate unvendored location - is out of v1 scope per
    SKILL.md's own "When something doesn't fit flow" section; the calling
    UI is expected to skip the affected unit rather than this module
    inventing a resolution.

`build_draft()` is the one orchestration entry point wizard_server.py calls:
idempotency check first (cep_retrofit.check_pointer, by contract identity),
then - only for whatever remains - insertion-point detection plus this
module's own resolve_reference/draft_insertion_text. Everything else here is
a pure function (resolve_reference, draft_insertion_text,
detect_contract_locations) with no side effects beyond the bounded
filesystem walk detect_contract_locations does to compute a default.
"""
from __future__ import annotations

import importlib
import os
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wizard_containment as wc  # noqa: E402
import wizard_content_hash as wch  # noqa: E402


class RetrofitDraftError(Exception):
    """Raised for any refusal in this module - already-user-facing message."""


CONTRACT_ORDER = (
    "CONSUMING-CONTEXT-PACKAGE.md",
    "CONSUMING-COMPILED-GUIDELINES.md",
    "CONSUMING-CODE-GRAPH.md",
)

_TEMPLATE_SENTENCES = {
    # the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting: the retrofit-inserted pointer
    # used to only say "if a package exists, see `{ref}`" - silent on what
    # happens when one *doesn't* exist, which is exactly the gap the finding
    # flagged (a task skill quietly proceeding ungrounded with only an
    # end-of-work disclosure). The extra sentence below makes the selected
    # context_availability policy visible in the retrofitted skill file
    # itself, not just in this module's own default - see
    # CONSUMING-CONTEXT-PACKAGE.md's "Context-availability policy" callout
    # for what each policy value means and CONTEXT_AVAILABILITY_POLICIES
    # below for the enforced set of valid values.
    "CONSUMING-CONTEXT-PACKAGE.md": (
        "If a CEP context package exists for this work, see `{ref}` for how "
        "to detect, load, and apply it before proceeding. "
        "**Context-availability policy: `{context_availability}`** — if no "
        "approved matching package is found, follow `{ref}`'s "
        "\"Context-availability policy\" callout for the `{context_availability}` "
        "branch before proceeding with the work."
    ),
    "CONSUMING-COMPILED-GUIDELINES.md": (
        "If compiled project guidelines exist for this codebase, see `{ref}` "
        "for how to load and apply them before making changes."
    ),
    "CONSUMING-CODE-GRAPH.md": (
        "If a code graph is available for this repo, see `{ref}` for how to "
        "query it for structural and dependency context before making "
        "changes."
    ),
}

# the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting: the three context-availability
# policies CONSUMING-CONTEXT-PACKAGE.md's step 1 "Not found" branch now
# recognizes. "ask" is the recommended default for implementation, design,
# planning, review, and debugging skills - matches this module's own
# DEFAULT_CONTEXT_AVAILABILITY below, so a retrofit that never sets the
# field explicitly still gets the safer, non-silent behavior rather than
# reverting to the old always-proceed-silently gap.
CONTEXT_AVAILABILITY_POLICIES = ("ask", "required", "optional")
DEFAULT_CONTEXT_AVAILABILITY = "ask"

# The 2026-08-31 Round-2 evaluation's finding on policy drift going undetected on
# already-retrofitted units: `cep_retrofit.check_pointer` treats a contract as
# "already present" on a bare substring match of the contract filename (see its own
# docstring, "matched by identity not literal path") - it has no idea what
# context_availability value was actually baked into that pointer when it was
# drafted. A unit retrofitted under the old "ask" default, later re-run after the
# project reconfigures to "required", would be reported all_satisfied=True with no
# signal at all that the file's own text still promises the stale policy. This regex
# locates that already-embedded policy line so build_draft can compare it against
# the currently-requested value and flag the drift instead of silently skipping it -
# see _current_policy_in_file and the policy_drifted check below.
POLICY_LINE_RE = re.compile(
    r"^.*\*\*Context-availability policy: `(ask|required|optional)`\*\*.*$",
    re.MULTILINE,
)

# Purpose-scoped ignore list for detect_contract_locations()'s walk only,
# following this repo's convention of each filesystem-scanning helper
# keeping its own local set rather than importing one. Deliberately its own
# list: it bounds a narrower walk (finding three fixed contract filenames)
# than module/layer discovery does, so it carries entries that walk needs
# and omits vendored-tree names that one needs. Not asserted identical to
# the discover_layers.py/scaffold_state.py pair, which do check parity
# against each other - no cross-file parity check covers this set.
_SCAN_IGNORED_DIR_NAMES = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "target",
    ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    "site-packages", ".idea", ".vscode",
}

_PLUGIN_QUALIFIER_RE = re.compile(r"^/[A-Za-z0-9][A-Za-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9_-]*$")


def _prune_ignored(dirnames: List[str]) -> None:
    dirnames[:] = [d for d in dirnames if d not in _SCAN_IGNORED_DIR_NAMES]


def detect_contract_locations(repo_root) -> Dict[str, Optional[str]]:
    """Best-effort default: {contract_filename: repo-relative path or None},
    the first match found for each of CONTRACT_ORDER's three fixed filenames
    anywhere under repo_root (deterministic directory-then-name sort order,
    ignored-dir-pruned walk, same shape cep_retrofit.inventory()'s own walk
    uses). This is a *default* only - the same-repo reference-resolution UI
    always shows it as an editable field, never as a silent final answer
    (SKILL.md Step 5: "ask, don't assume")."""
    root = Path(repo_root)
    found: Dict[str, Optional[str]] = {c: None for c in CONTRACT_ORDER}
    remaining = set(CONTRACT_ORDER)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        _prune_ignored(dirnames)
        for name in sorted(filenames):
            if name in remaining:
                full = Path(dirpath) / name
                found[name] = full.relative_to(root).as_posix()
                remaining.discard(name)
        if not remaining:
            break
    return found


def _is_external_root(repo_root, containment_root) -> bool:
    """True only when `containment_root` names a root genuinely different
    from `repo_root` (the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment). None or an
    equal/unresolvable-to-equal root is treated as "in-repo" - the ordinary,
    unchanged case every existing caller and test already exercises."""
    if not containment_root:
        return False
    try:
        return Path(containment_root).resolve() != Path(repo_root).resolve()
    except OSError:
        return True


def resolve_reference(
    repo_root,
    unit_dir_rel_path: str,
    contract_filename: str,
    mode: str,
    *,
    same_repo_contract_rel_path: Optional[str] = None,
    plugin_qualifier: Optional[str] = None,
    containment_root: Optional[str] = None,
) -> str:
    """Resolves what string to substitute into the drafted sentence for one
    contract - see module docstring for the two supported modes.
    `unit_dir_rel_path` is the directory the reference is written *relative
    to*: the unit's own directory for a skill-dir/manifest-dir, or the
    containing directory of the file itself for a flat-file unit (callers
    compute this once from the unit's `path`, not this function - it has no
    opinion on unit "type"). Raises RetrofitDraftError on any missing or
    malformed argument for the selected mode; never silently falls back to
    the other mode.

    `containment_root` (the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment) is the root
    `unit_dir_rel_path` is actually relative to when it differs from
    `repo_root` - i.e. an external retrofit target
    (`wizard_containment.resolve_external_target`). same-repo mode is refused
    outright whenever `containment_root` is genuinely external: the contract
    doc it points at always lives under `repo_root`, while the unit's own
    directory lives under an unrelated root, so a relative path between them
    is either meaningless (different drives) or would require exactly the
    kind of cross-boundary `..`-escape containment exists to prevent. Only
    plugin-qualified mode - purely lexical, no filesystem-root dependency -
    is offered for an external unit, both here and mirrored in the frontend
    (the same-repo radio is disabled client-side when a unit's target is
    external)."""
    if contract_filename not in CONTRACT_ORDER:
        raise RetrofitDraftError(f"unknown contract {contract_filename!r}")

    if mode == "same-repo":
        if _is_external_root(repo_root, containment_root):
            raise RetrofitDraftError(
                "same-repo reference mode isn't available for an external "
                "retrofit target - the contract doc lives in this project's "
                "repo, but this unit lives under a different root. Use "
                "plugin-qualified reference mode instead."
            )
        if not same_repo_contract_rel_path or not same_repo_contract_rel_path.strip():
            raise RetrofitDraftError(
                "same-repo mode requires same_repo_contract_rel_path"
            )
        contract_rel = same_repo_contract_rel_path.strip()
        try:
            wc.check_containment(repo_root, contract_rel)
            wc.check_containment(repo_root, unit_dir_rel_path)
        except wc.ContainmentError as exc:
            raise RetrofitDraftError(str(exc)) from exc
        # posixpath, not os.path - both inputs are already forward-slash,
        # repo-relative strings, and the result is written into a Markdown
        # file, which should read forward-slash on every host OS (matches
        # wizard_decision_staging.py's own forward-slash-only convention),
        # not whatever os.sep the wizard happens to be running under.
        start_dir = unit_dir_rel_path if unit_dir_rel_path not in ("", ".") else "."
        return posixpath.relpath(contract_rel, start_dir)

    if mode == "plugin":
        if not plugin_qualifier or not plugin_qualifier.strip():
            raise RetrofitDraftError("plugin mode requires plugin_qualifier")
        qualifier = plugin_qualifier.strip()
        if not _PLUGIN_QUALIFIER_RE.match(qualifier):
            raise RetrofitDraftError(
                f"{qualifier!r} does not look like a plugin-qualified reference "
                f"(expected '/<plugin>:<skill>')"
            )
        return f"{qualifier}'s {contract_filename}"

    raise RetrofitDraftError(
        f"unknown reference mode {mode!r} (expected 'same-repo' or 'plugin')"
    )


def draft_insertion_text(
    contracts: List[str],
    references: Dict[str, str],
    *,
    context_availability: str = DEFAULT_CONTEXT_AVAILABILITY,
) -> str:
    """Combined block for every contract in `contracts` (any input order),
    rendered in CONTRACT_ORDER's fixed stable order per SKILL.md Step 6.4,
    one template sentence per contract with its resolved reference
    substituted. Raises RetrofitDraftError if a contract isn't a known
    CONTRACT_ORDER member, has no entry in `references`, or
    `context_availability` isn't one of CONTEXT_AVAILABILITY_POLICIES.

    `context_availability` is passed to every template's `.format()` call
    uniformly (the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting) - `str.format()`
    silently ignores unused named kwargs, so this is safe even though only
    the CONSUMING-CONTEXT-PACKAGE.md template currently references
    `{context_availability}`.
    """
    unknown = [c for c in contracts if c not in CONTRACT_ORDER]
    if unknown:
        raise RetrofitDraftError(f"unknown contract(s): {', '.join(unknown)}")
    missing_ref = [c for c in contracts if c not in references]
    if missing_ref:
        raise RetrofitDraftError(f"no resolved reference for: {', '.join(missing_ref)}")
    if context_availability not in CONTEXT_AVAILABILITY_POLICIES:
        raise RetrofitDraftError(
            f"unknown context_availability {context_availability!r} "
            f"(expected one of {', '.join(CONTEXT_AVAILABILITY_POLICIES)})"
        )

    ordered = [c for c in CONTRACT_ORDER if c in contracts]
    sentences = [
        _TEMPLATE_SENTENCES[c].format(
            ref=references[c], context_availability=context_availability
        )
        for c in ordered
    ]
    return "\n\n".join(sentences)


def _find_cep_retrofit_scripts_dir(repo_root) -> Path:
    """Same lookup wizard_retrofit_inventory.py's own (private) version does
    - duplicated for the same reason wizard_decision_staging.py/
    wizard_apply.py each duplicate their own confirm_layers.py importer
    rather than importing one another's: this module must be independently
    usable, and independently unit-testable, without either of those having
    already run in the same process."""
    scripts_dir = Path(repo_root) / ".github" / "skills" / "ult-cep-retrofit" / "scripts"
    if not (scripts_dir / "cep_retrofit.py").exists():
        raise RetrofitDraftError(
            f"ult-cep-retrofit's cep_retrofit.py was not found under {scripts_dir} - "
            f"is ult-cep-retrofit installed in this repo?"
        )
    return scripts_dir


def _import_cep_retrofit(repo_root):
    scripts_dir_str = str(_find_cep_retrofit_scripts_dir(repo_root))
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module("cep_retrofit")


_CONTEXT_WINDOW_LINES = 3


def _extract_context(target: Path, insertion_point: Dict[str, Any]) -> "tuple[str, str]":
    """Best-effort context_before/context_after for the batch diff-preview
    view's three-`<pre>`-zone cards (Journey 3 plan's Phase B UI
    requirement) - up to `_CONTEXT_WINDOW_LINES` lines of the target file's
    own text immediately surrounding `insertion_point["line"]`, a 0-indexed
    splice index into `target.read_text().splitlines()` per
    cep_retrofit.find_insertion_point's own contract. No diff algorithm
    needed: every change here is a pure insertion, never a replacement, so
    "before" and "after" is just string-slicing around one splice point.
    Read failures are swallowed (empty/empty) rather than raised - this is a
    presentation nicety for the preview card, never load-bearing for the
    draft itself, which already has everything it needs without it."""
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return "", ""
    line = insertion_point.get("line")
    if not isinstance(line, int):
        return "", ""
    line = max(0, min(line, len(lines)))
    before = lines[max(0, line - _CONTEXT_WINDOW_LINES):line]
    after = lines[line:line + _CONTEXT_WINDOW_LINES]
    return "\n".join(before), "\n".join(after)


@dataclass
class DraftResult:
    all_satisfied: bool
    contracts_included: List[str]
    contracts_skipped_idempotent: List[str]
    insertion_point: Optional[Dict[str, Any]]
    draft_text: str
    target_file_hash: Optional[str]
    context_before: str
    context_after: str
    # the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting: echoed back so callers/tests
    # can confirm which policy actually got baked into draft_text, without
    # re-deriving it from the request.
    context_availability: str = DEFAULT_CONTEXT_AVAILABILITY
    # True when a contract already reported as idempotent-skipped
    # (cr.check_pointer said "present") turns out to carry a stale
    # context_availability value in its own embedded policy line - see
    # _current_policy_in_file and POLICY_LINE_RE above. When this is True and
    # all_satisfied is False with an otherwise-empty contracts_included,
    # draft_text carries the policy-line replacement only (no contract
    # insertion needed) - wizard.js renders this case with a
    # "policy change only" label rather than the normal insertion diff.
    policy_drifted: bool = False


def _current_policy_in_file(target: Path):
    """Returns (existing_policy_value, existing_full_line) for the
    CONSUMING-CONTEXT-PACKAGE.md context-availability-policy line already
    embedded in `target`, or (None, None) if no such line is present - either
    the unit was never retrofitted with that contract at all, or it was
    retrofitted before this policy sentence existed (an older, unmigrated
    pointer is not "drifted", it's simply out of scope for this check, same
    as it always was). Read failures also return (None, None): a target this
    module already opened once via cr.check_pointer's own read is not
    expected to become unreadable in between, and drift detection is a
    best-effort signal, not a correctness gate - not being able to read it
    again is not itself the drift.
    """
    try:
        text = target.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None, None
    m = POLICY_LINE_RE.search(text)
    if not m:
        return None, None
    return m.group(1), m.group(0)


def build_draft(
    repo_root,
    primary_file_rel_path: str,
    unit_dir_rel_path: str,
    contracts: List[str],
    reference_mode: str,
    reference_args: Dict[str, str],
    *,
    context_availability: str = DEFAULT_CONTEXT_AVAILABILITY,
    containment_root: Optional[str] = None,
) -> DraftResult:
    """Orchestrates the full Phase B draft computation for one unit:

    1. Containment-checks `primary_file_rel_path` and confirms it's a file.
    2. Idempotency check first, by contract identity (SKILL.md Step 6.1):
       `cep_retrofit.check_pointer`. A contract already present is dropped
       into `contracts_skipped_idempotent`, never re-drafted.
    3. If everything was already present, returns immediately
       (`all_satisfied=True`) without ever calling `find_insertion_point` -
       there is nothing left to insert.
    4. Otherwise: `find_insertion_point` once, then this module's own
       `resolve_reference`/`draft_insertion_text` for whatever remains,
       combined into one block per Step 6.4.

    Raises RetrofitDraftError uniformly on any refusal - missing
    ult-cep-retrofit install, containment violation, non-file target, or a
    resolve_reference/draft_insertion_text failure - so callers need only
    one except clause.

    `containment_root` (the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment): the root
    `primary_file_rel_path`/`unit_dir_rel_path` are actually relative to,
    when it differs from `repo_root` - i.e. an external retrofit target. None
    (the default) keeps the original in-repo behavior byte-for-byte. Threaded
    straight through to `resolve_reference` unchanged; see that function's
    docstring for why same-repo mode is refused when this is genuinely
    external. `repo_root` itself is still used regardless, for locating
    ult-cep-retrofit's own engine (see wizard_retrofit_inventory.py's module
    docstring for the same invariant on the inventory side).
    """
    try:
        target = wc.check_containment(containment_root or repo_root, primary_file_rel_path)
    except wc.ContainmentError as exc:
        raise RetrofitDraftError(str(exc)) from exc
    if not target.is_file():
        raise RetrofitDraftError(f"{primary_file_rel_path} is not a file")

    cr = _import_cep_retrofit(repo_root)
    try:
        already_present = cr.check_pointer(str(target), contracts)
        target_file_hash = wch.hash_file(target)
    except OSError as exc:
        raise RetrofitDraftError(str(exc)) from exc

    remaining = [c for c in contracts if not already_present.get(c)]
    skipped_idempotent = [c for c in contracts if already_present.get(c)]

    if context_availability not in CONTEXT_AVAILABILITY_POLICIES:
        raise RetrofitDraftError(
            f"unknown context_availability {context_availability!r} "
            f"(expected one of {', '.join(CONTEXT_AVAILABILITY_POLICIES)})"
        )

    # the 2026-08-31 Round-2 evaluation's finding on policy drift going undetected
    # on already-retrofitted units: check every skipped-idempotent contract's own
    # embedded policy line against the currently-requested value, not just whether
    # a pointer is present. Only CONSUMING-CONTEXT-PACKAGE.md ever carries this
    # sentence, so this is a no-op for every other contract.
    policy_drifted = False
    policy_replacement_text = ""
    if "CONSUMING-CONTEXT-PACKAGE.md" in skipped_idempotent:
        existing_policy, existing_line = _current_policy_in_file(target)
        if existing_policy is not None and existing_policy != context_availability:
            policy_drifted = True
            policy_replacement_text = existing_line.replace(
                f"`{existing_policy}`", f"`{context_availability}`"
            )

    if not remaining:
        if policy_drifted:
            return DraftResult(
                all_satisfied=False,
                contracts_included=[],
                contracts_skipped_idempotent=skipped_idempotent,
                insertion_point=None,
                draft_text=policy_replacement_text,
                target_file_hash=target_file_hash,
                context_before="",
                context_after="",
                context_availability=context_availability,
                policy_drifted=True,
            )
        return DraftResult(
            all_satisfied=True,
            contracts_included=[],
            contracts_skipped_idempotent=skipped_idempotent,
            insertion_point=None,
            draft_text="",
            target_file_hash=target_file_hash,
            context_before="",
            context_after="",
            context_availability=context_availability,
        )

    try:
        insertion_point = cr.find_insertion_point(str(target))
    except OSError as exc:
        raise RetrofitDraftError(str(exc)) from exc

    references: Dict[str, str] = {}
    for contract in remaining:
        ref_value = (reference_args or {}).get(contract)
        if reference_mode == "same-repo":
            references[contract] = resolve_reference(
                repo_root, unit_dir_rel_path, contract, "same-repo",
                same_repo_contract_rel_path=ref_value,
                containment_root=containment_root,
            )
        elif reference_mode == "plugin":
            references[contract] = resolve_reference(
                repo_root, unit_dir_rel_path, contract, "plugin",
                plugin_qualifier=ref_value,
                containment_root=containment_root,
            )
        else:
            raise RetrofitDraftError(
                f"unknown reference_mode {reference_mode!r} "
                f"(expected 'same-repo' or 'plugin')"
            )

    draft_text = draft_insertion_text(
        remaining, references, context_availability=context_availability
    )
    context_before, context_after = _extract_context(target, insertion_point)

    return DraftResult(
        all_satisfied=False,
        contracts_included=remaining,
        contracts_skipped_idempotent=skipped_idempotent,
        insertion_point=insertion_point,
        draft_text=draft_text,
        target_file_hash=target_file_hash,
        context_before=context_before,
        context_after=context_after,
        context_availability=context_availability,
        # Surfaced here too (not just the not-remaining branch above): a unit can
        # simultaneously still need a different contract inserted (CONSUMING-CODE-
        # GRAPH.md, say) while its already-present CONSUMING-CONTEXT-PACKAGE.md
        # pointer has drifted - wizard.js can flag both, even though draft_text
        # here is still the normal insertion text for `remaining` only.
        policy_drifted=policy_drifted,
    )
