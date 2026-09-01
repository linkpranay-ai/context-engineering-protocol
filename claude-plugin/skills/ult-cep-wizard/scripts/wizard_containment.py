#!/usr/bin/env python3
"""wizard_containment.py - symlink/junction/reparse-tag containment for
ult-cep-wizard (D24 §18.2b, locked).

Ensures every path the wizard resolves relative to the affirmed project root is
actually *inside* that root on the real filesystem - not just string-prefix-matching
inside it. A path can nominally sit under the root string-wise while a symlink or
junction partway down actually points somewhere else entirely; `Path.resolve()` alone
hides this (it silently follows the link and hands back wherever it really points),
so this module also walks every intermediate path component explicitly and rejects
any that is a reparse point we don't specifically recognize as safe.

Windows specifics (this workspace runs on Windows, and D24 exit criterion 4 requires
Windows-specific UNC/case-fold/reparse-tag containment tests - build-order step 3 /
risk R1 is the corresponding CI leg):

  - Both symlinks (`IO_REPARSE_TAG_SYMLINK`) and directory junctions
    (`IO_REPARSE_TAG_MOUNT_POINT`) are real containment violations and rejected.
  - OneDrive Files-On-Demand cloud placeholders (`IO_REPARSE_TAG_CLOUD` and its
    per-provider `IO_REPARSE_TAG_CLOUD_1`..`_F` family, per winnt.h) are NOT a
    containment violation - a placeholder is still a real file inside the root, just
    not yet hydrated locally. This workspace lives under OneDrive, so getting this
    distinction wrong would make the wizard unusable here. Fail-closed still applies
    the other direction: any reparse tag that ISN'T a recognized cloud-placeholder tag
    is treated as a violation, even if it doesn't match the specific SYMLINK/
    MOUNT_POINT tags named above - an unrecognized reparse point is exactly the kind
    of ambiguity this module exists to reject, not default-allow (R3: full end-to-end
    validation of the OneDrive case needs one manual run on a real synced machine -
    unit tests here mock the reparse-tag value rather than depending on live sync
    state).
  - UNC paths (`\\\\server\\share\\...`) and drive-letter paths are both handled;
    containment comparisons fold case (NTFS is case-insensitive-but-preserving) and
    strip the `\\\\?\\` extended-length prefix `Path.resolve()` sometimes adds, so the
    same real location compares equal regardless of which spelling either side used.

On POSIX (this module also runs under CI's ubuntu-latest leg for the
platform-independent majority of its logic), reparse tags don't exist -
`os.path.islink()` is the whole per-component check, and any symlink anywhere in the
resolved chain is rejected the same way a Windows symlink/junction is.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


class ContainmentError(Exception):
    """Raised with an already-user-facing message naming the offending path."""


# --- Windows reparse tag constants (winnt.h) --------------------------------
# Duplicated here rather than imported from a Windows-only stdlib module, so this
# file still imports cleanly on POSIX (the platform-independent tests need to run
# under CI's ubuntu-latest leg too).
IO_REPARSE_TAG_SYMLINK = 0xA000000C
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
# Reference only (not used directly in the gating logic below - see
# _is_cloud_placeholder_tag's mask comment for why these are documented, not
# enumerated one by one).
KNOWN_REJECTED_REPARSE_TAGS = frozenset({IO_REPARSE_TAG_SYMLINK, IO_REPARSE_TAG_MOUNT_POINT})

# IO_REPARSE_TAG_CLOUD family: winnt.h defines IO_REPARSE_TAG_CLOUD (0x9000001A) plus
# twelve per-provider variants IO_REPARSE_TAG_CLOUD_1..IO_REPARSE_TAG_CLOUD_F, which
# only differ from the base tag in one nibble (bits 12-15, the "family" nibble) - e.g.
# IO_REPARSE_TAG_CLOUD_1 = 0x9000101A. Masking that nibble out and comparing to the
# base tag recognizes the whole family in one check, rather than enumerating all
# thirteen values by hand (and risking a future provider variant falling through the
# gap as an unrecognized/rejected tag).
_CLOUD_TAG_BASE = 0x9000001A
_CLOUD_TAG_FAMILY_MASK = 0x0000F000
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_cloud_placeholder_tag(tag: int) -> bool:
    return (tag & ~_CLOUD_TAG_FAMILY_MASK) == _CLOUD_TAG_BASE


def _reparse_tag_for(path: Path) -> Optional[int]:
    """Windows only: the raw reparse tag for this exact path component (never
    resolved/followed - `follow_symlinks=False` is the whole point here). None if the
    component isn't a reparse point at all, doesn't exist, or this isn't Windows."""
    if sys.platform != "win32":
        return None
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    attrs = getattr(st, "st_file_attributes", 0)
    if not (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
        return None
    return getattr(st, "st_reparse_tag", None)


def component_is_containment_violation(path: Path) -> bool:
    """True if this exact path component (not resolved) is a reparse point that
    breaks containment. Fail-closed: on Windows, any reparse point that isn't a
    recognized cloud-placeholder tag is a violation - not just the named SYMLINK/
    MOUNT_POINT tags. On POSIX, any symlink is a violation."""
    if sys.platform == "win32":
        tag = _reparse_tag_for(path)
        if tag is None:
            return False
        return not _is_cloud_placeholder_tag(tag)
    return os.path.islink(path)


def _strip_extended_prefix(s: str) -> str:
    """Strips the `\\\\?\\` extended-length prefix Path.resolve() sometimes adds on
    Windows for long paths, so `\\\\?\\C:\\foo` and `C:\\foo` compare equal."""
    if s.startswith("\\\\?\\UNC\\"):
        return "\\\\" + s[len("\\\\?\\UNC\\"):]
    if s.startswith("\\\\?\\"):
        return s[len("\\\\?\\"):]
    return s


def _normalized_for_comparison(path: Path) -> str:
    s = _strip_extended_prefix(str(path))
    return s.rstrip("\\/").casefold()


def is_contained(affirmed_root, candidate_path) -> bool:
    """Non-raising convenience wrapper around check_containment - callers that just
    need a boolean (e.g. filtering a directory listing) don't need a try/except."""
    try:
        check_containment(affirmed_root, candidate_path)
        return True
    except ContainmentError:
        return False


def check_containment(affirmed_root, candidate_path) -> Path:
    """Resolves `candidate_path` relative to `affirmed_root` and verifies real
    containment. Returns the resolved Path on success; raises ContainmentError
    otherwise. Two independent checks, both must pass:

      1. The fully-resolved candidate must be the root itself or a descendant of it
         (case-insensitive, UNC/extended-prefix-normalized comparison).
      2. No path component between the root and the target (walked WITHOUT following
         symlinks) may be a reparse point we don't recognize as safe. This catches the
         case .resolve() alone would hide: a symlink pointing at another location that
         still happens to resolve to somewhere under root - link-based indirection
         inside the root is exactly the kind of ambiguity this module exists to
         reject, not just an outside-root escape.
    """
    root = Path(affirmed_root).resolve()
    unresolved_target = Path(affirmed_root, candidate_path)
    try:
        rel_parts = unresolved_target.relative_to(Path(affirmed_root)).parts
    except ValueError:
        raise ContainmentError(
            f"'{candidate_path}' is not relative to the affirmed project root "
            f"'{affirmed_root}'."
        )

    resolved_target = unresolved_target.resolve()
    root_str = _normalized_for_comparison(root)
    target_str = _normalized_for_comparison(resolved_target)
    if target_str != root_str and not target_str.startswith(root_str + os.sep.casefold()):
        raise ContainmentError(
            f"'{candidate_path}' resolves outside the affirmed project root "
            f"'{root}'."
        )

    current = Path(affirmed_root)
    for part in rel_parts:
        current = current / part
        if component_is_containment_violation(current):
            raise ContainmentError(
                f"'{current}' is a symlink/junction/reparse point - not allowed "
                "inside the affirmed project root (OneDrive cloud placeholders are "
                "exempt from this check; this path is not one)."
            )

    return resolved_target


def resolve_external_target(repo_root, candidate_path) -> Path:
    """Validates a user-supplied absolute external retrofit-target root
    (the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment - "Retrofit wizard cannot operate
    on sibling or standalone skill library"). Unlike check_containment, this
    function's whole job is to validate a root that is deliberately OUTSIDE
    repo_root, so it cannot reuse check_containment's "must be inside" test -
    only its containment-violation machinery (component_is_containment_violation)
    for the candidate root itself.

    Requirements, all fail-closed:

      1. candidate_path must be non-empty and, once turned into a Path, absolute -
         a relative external root is meaningless (relative to what?) and is
         rejected rather than silently resolved against cwd or repo_root.
      2. candidate_path must NOT already be inside repo_root - if it is, this is
         just an ordinary in-repo target and callers should route it through the
         existing picker/containment_root=None path instead of this one.
         is_contained() already proves this correctly without any new logic:
         pathlib's join semantics mean `Path(repo_root, absolute_candidate)`
         evaluates to `absolute_candidate` itself, so this reuses
         check_containment's existing resolved-and-normalized comparison rather
         than re-implementing it.
      3. candidate_path itself, AND every one of its ancestor directories
         (component_is_containment_violation, walked over candidate.parents),
         must not be a symlink/junction/reparse point - the external root
         becomes the new write boundary for every unit selected under it, so
         both it and the path leading to it must be real and unambiguous,
         exactly like every intermediate component check_containment already
         requires for in-repo paths. OneDrive cloud placeholders are exempt
         (component_is_containment_violation's own distinction), so an
         ancestor sitting under Files-On-Demand sync is still accepted.
      4. candidate_path must exist and be a real directory - nothing is created
         on the caller's behalf; per that finding's own repro steps,
         the user has already cloned/checked out the library before pointing
         the wizard at it.

    Returns the resolved Path. Every downstream containment/write check for
    this unit or session passes this Path as `containment_root` in place of
    repo_root - the write boundary moves, but never widens: check_containment
    still runs the exact same two checks against whichever root it's given.
    Raises ContainmentError on any failure, the same exception type (and the
    same "reason" surfacing convention) callers already handle for an in-repo
    containment failure."""
    if not candidate_path or not str(candidate_path).strip():
        raise ContainmentError("An external retrofit target path is required.")

    candidate = Path(candidate_path)
    if not candidate.is_absolute():
        raise ContainmentError(
            f"'{candidate_path}' is not an absolute path - an external retrofit "
            "target must be given as a full path (e.g. the root of an "
            "already-cloned skill library)."
        )

    if is_contained(repo_root, candidate):
        raise ContainmentError(
            f"'{candidate_path}' is already inside the project root '{repo_root}' - "
            "use the ordinary in-repo target picker instead of the external-target flow."
        )

    # The 2026-08-31 Round-2 evaluation's finding on external (out-of-repo)
    # retrofit-target containment: the check below this comment only ever
    # looked at `candidate` itself - a reparse point one level higher (e.g.
    # `candidate`'s parent is a junction, but `candidate` on disk is an
    # ordinary directory once you're through it) walked straight past
    # unnoticed, and the resolved Path returned from this function silently
    # became a different real location than the literal path the user typed.
    # That's exactly the "link-based indirection" ambiguity
    # check_containment's own docstring already refuses for in-repo paths
    # (see its component-by-component walk above) - an external root
    # deserves the same guarantee along its own ancestor chain, checked
    # before the candidate-itself check below so either one on its own is
    # sufficient to reject.
    for ancestor in candidate.parents:
        if component_is_containment_violation(ancestor):
            raise ContainmentError(
                f"'{ancestor}' is a symlink/junction/reparse point in the path to "
                f"'{candidate}' - not allowed as an ancestor of an external retrofit "
                "target root (OneDrive cloud placeholders are exempt from this "
                "check; this ancestor is not one)."
            )

    if component_is_containment_violation(candidate):
        raise ContainmentError(
            f"'{candidate}' is a symlink/junction/reparse point - not allowed as an "
            "external retrofit target root (OneDrive cloud placeholders are exempt "
            "from this check; this path is not one)."
        )

    if not candidate.is_dir():
        raise ContainmentError(
            f"'{candidate}' does not exist or is not a directory - clone/checkout "
            "the external skill library first, then point the wizard at its root."
        )

    return candidate.resolve()
