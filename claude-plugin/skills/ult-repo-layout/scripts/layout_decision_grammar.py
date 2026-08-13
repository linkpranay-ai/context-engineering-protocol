#!/usr/bin/env python3
"""layout_decision_grammar.py - shared vocabulary for the layer-path decision
artifact (`context-layout-discovery.md`).

Factored out of discover_layers.py/confirm_layers.py (D24 v5 SS18 Phase 1,
strategic decision S2 / open question Q-d) so a third caller
(ult-cep-wizard's write path) can stage decision lines without reaching
into either module's internals. Before this module existed, the same
`TITLE_TO_BASE_KEY` map was independently re-imported by confirm_layers.py
(`import discover_layers as dl`) and by ult-cep-wizard's
wizard_layout_source.py (its own importlib.import_module reach-in) - two
un-factored copies of the same coupling.

This module owns *data*, not behavior: the section-title <-> config-key map,
the decision-line regex grammar, and the comment-clause/dotted-path parsers
that turn a line's trailing comment into "which verbs are offered here" and
"which dotted context-config.yaml key does a collision CUSTOM edit touch".

It deliberately does NOT own artifact parsing (`parse_artifact`), field
resolution (`Field`/`FieldError`), or the config-write engine (`set_scalar`,
`append_list_item`, `set_list_item`, `apply_field`) - those stay in
confirm_layers.py because they are bound up with `run_confirm`'s own
atomicity/write-ordering contract (resolve every field before writing any),
not reusable vocabulary.

discover_layers.py and confirm_layers.py both import from here instead of
defining their own copies; neither module's CLI surface or behavior changes
because of this refactor - their own pre-existing test suites pass
unmodified against it.
"""
import re

# ---------------------------------------------------------------------------
# Section titles (verbatim `## <title>` headers rendered by
# discover_layers.py's LayerSection.render) and the map from each primary
# layer section's title to its dotted context-config.yaml base key.
# ---------------------------------------------------------------------------
WHAT_L2_TITLE = "What-L2 - project's own requirements/spec docs"
HOW_L2_TITLE = "How-L2 - this project's own compiled conventions"
WHAT_L1_TITLE = "What-L1 - external reference material (standards/specs this project didn't author)"
HOW_L1_TITLE = "How-L1 - org-wide process standards"
COLLISION_TITLE = "Cross-layer path collisions (S30)"

TITLE_TO_BASE_KEY = {
    WHAT_L2_TITLE: "layers.what_l2",
    HOW_L2_TITLE: "how_dimension.how_l2",
    WHAT_L1_TITLE: "layers.what_l1",
    HOW_L1_TITLE: "how_dimension.how_l1",
}

# ---------------------------------------------------------------------------
# Decision-line grammar
# ---------------------------------------------------------------------------
FIELD_LINE_RE = re.compile(
    r"^(decision|enable|include_roots_decision|exclude_decision|collision_decision):\s*(.*)$"
)
# Matched against a Field's already-`#`-stripped .comment text, not the raw
# line - parse_artifact() splits off everything after the first `#` before
# a comment ever reaches here.
CONFIRMED_STAMP_RE = re.compile(r"^CONFIRMED\s+(\S+)\s*$")
PLACEHOLDER_RE = re.compile(r"<[^<>]*>")
DOTTED_INDEX_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]$")


def parse_comment_clauses(comment):
    """Parse a field's trailing comment into {VERB: default_arg_or_None}.

    Each `|`-separated clause is either a bare verb or `VERB: <arg>` (the
    trailing colon's argument is the verb's default/placeholder argument,
    not part of the verb itself - e.g. a SKIP clause's own parenthetical
    note in a discover_layers.py-rendered line is explanatory only and is
    discarded here, never mistaken for part of an argument).
    """
    clauses = [c.strip() for c in comment.split("|") if c.strip()]
    allowed = {}
    for clause in clauses:
        m = re.match(r"^([A-Za-z][A-Za-z_]*)\s*:\s*(.+)$", clause)
        if m:
            verb, arg = m.group(1), m.group(2).strip()
        else:
            verb = clause.split()[0]
            arg = None
        allowed.setdefault(verb, arg)
    return allowed


def parse_dotted_path(path_str):
    """`"layers.what_l2.include_roots[0]"` -> (["layers","what_l2","include_roots"], 0);
    `"how_dimension.how_l1.path"` -> (["how_dimension","how_l1","path"], None).
    """
    parts = path_str.strip().split(".")
    m = DOTTED_INDEX_RE.match(parts[-1])
    if m:
        parts[-1] = m.group(1)
        return parts, int(m.group(2))
    return parts, None
