#!/usr/bin/env python3
"""usage_report.py - context-package usage aggregation report (ROADMAP item 7).

`CONSUMING-CONTEXT-PACKAGE.md` step 9 has every consuming skill append a
`kind: reference` addendum to a package's sibling
`contexts/<package-id>_<date>.addenda.yaml` file, naming exactly which
`context_items` (`cites.ctx_ids`) it actually used. That write side already
ships; nothing previously read it back. This script aggregates it: for every
`contexts/<id>.yaml` package it finds, it unions `cites.ctx_ids` across that
package's addenda files and reports which context_items were never cited by
any downstream consumer - the signal that a package's assembly is
over-including.

Python 3 stdlib only (re, sys, pathlib) - vendorable alongside content_hash.py
and md_index.py. No YAML library: the package/addenda files follow a small,
fixed, documented shape (`references/context-package-schema.md`,
`CONSUMING-CONTEXT-PACKAGE.md` step 9), so this uses a targeted line-scanner
rather than a general parser.

CLI:
    python usage_report.py [--dir contexts/]

Writes `<dir>/USAGE_REPORT.md`. Exits 0 even if zero packages are found (a
repo that hasn't run ult-context-generate yet is a normal state, not an
error).
"""

import re
import sys
from pathlib import Path

_PACKAGE_ID_RE = re.compile(r"^  id:\s*(.+?)\s*$")
_GENERATED_AT_RE = re.compile(r"^  generated_at:\s*(.+?)\s*$")
_ITEM_START_RE = re.compile(r"^    - id:\s*(\S+)\s*$")
_ITEM_FIELD_RE = re.compile(r"^      (\w+):\s*(.+?)\s*$")
_TOP_LEVEL_KEY_RE = re.compile(r"^  \w+:")

_ADDENDUM_START_RE = re.compile(r"^  - id:\s*(\S+)\s*$")
_ADDENDUM_FIELD_RE = re.compile(r"^    (\w+):\s*(.+?)\s*$")
_CITES_CTX_IDS_RE = re.compile(r"ctx_ids:\s*\[([^\]]*)\]")

LAYERS = ["what-l3", "what-l2", "what-l1", "constraints", "how-l1", "llm-generated"]


def parse_package(path):
    """Return {"id", "generated_at", "items": [{"id","layer",...}]} for a
    contexts/<id>.yaml file, or None if it has no context_package.id."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    package_id = None
    generated_at = None
    items = []
    current_item = None
    in_context_items = False

    for line in lines:
        if not in_context_items:
            m = _PACKAGE_ID_RE.match(line)
            if m and package_id is None:
                package_id = m.group(1)
                continue
            m = _GENERATED_AT_RE.match(line)
            if m:
                generated_at = m.group(1)
                continue
            if line.rstrip() == "  context_items:":
                in_context_items = True
            continue

        item_start = _ITEM_START_RE.match(line)
        if item_start:
            if current_item is not None:
                items.append(current_item)
            current_item = {"id": item_start.group(1)}
            continue

        field = _ITEM_FIELD_RE.match(line)
        if field and current_item is not None:
            current_item[field.group(1)] = field.group(2)
            continue

        if _TOP_LEVEL_KEY_RE.match(line):
            # Dedent back to a `  key:` line - context_items block is over.
            if current_item is not None:
                items.append(current_item)
                current_item = None
            in_context_items = False

    if current_item is not None:
        items.append(current_item)

    if package_id is None:
        return None
    return {"id": package_id, "generated_at": generated_at, "items": items}


def parse_addenda(path):
    """Return a list of {"kind", "ctx_ids": [...], "tokens_used": int|None}
    for each addendum entry in a contexts/<id>_<date>.addenda.yaml file."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    entries = []
    current = None

    for line in lines:
        start = _ADDENDUM_START_RE.match(line)
        if start:
            if current is not None:
                entries.append(current)
            current = {"kind": None, "ctx_ids": [], "tokens_used": None}
            continue

        if current is None:
            continue

        cites_m = _CITES_CTX_IDS_RE.search(line)
        if cites_m and line.lstrip().startswith("cites:"):
            raw = cites_m.group(1)
            current["ctx_ids"] = [
                token.strip().strip("'\"")
                for token in raw.split(",")
                if token.strip()
            ]
            continue

        field = _ADDENDUM_FIELD_RE.match(line)
        if field:
            key, value = field.group(1), field.group(2)
            if key == "kind":
                current["kind"] = value
            elif key == "tokens_used":
                try:
                    current["tokens_used"] = int(value)
                except ValueError:
                    pass

    if current is not None:
        entries.append(current)

    return [e for e in entries if e["kind"] == "reference"]


def aggregate(contexts_dir):
    """Scan contexts_dir for packages + their addenda and return the report
    data structure consumed by render_markdown()."""
    contexts_dir = Path(contexts_dir)
    packages = []
    tokens_used_samples = []

    if not contexts_dir.is_dir():
        return {"packages": packages, "tokens_used_samples": tokens_used_samples}

    for yaml_path in sorted(contexts_dir.glob("*.yaml")):
        if yaml_path.name.endswith(".addenda.yaml"):
            continue
        package = parse_package(yaml_path)
        if package is None:
            continue

        cited_ctx_ids = set()
        addenda_paths = sorted(contexts_dir.glob(f"{package['id']}_*.addenda.yaml"))
        for addenda_path in addenda_paths:
            for entry in parse_addenda(addenda_path):
                cited_ctx_ids.update(entry["ctx_ids"])
                if entry["tokens_used"] is not None:
                    tokens_used_samples.append(entry["tokens_used"])

        for item in package["items"]:
            item["cited"] = item["id"] in cited_ctx_ids

        packages.append(package)

    return {"packages": packages, "tokens_used_samples": tokens_used_samples}


def render_markdown(report):
    packages = report["packages"]
    all_items = [item for pkg in packages for item in pkg["items"]]
    total = len(all_items)
    cited = sum(1 for item in all_items if item["cited"])
    never_cited = total - cited

    lines = ["# Context-package usage report", ""]

    if not packages:
        lines.append("No context packages found.")
        lines.append("")
        lines.append(
            "Run `ult-context-generate` and let downstream skills consume the "
            "resulting package(s) (see `CONSUMING-CONTEXT-PACKAGE.md` step 9) "
            "before running this report."
        )
        lines.append("")
        return "\n".join(lines)

    pct = (never_cited / total * 100) if total else 0.0
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- Total context items: {total}")
    lines.append(f"- Cited by at least one downstream artifact: {cited}")
    lines.append(f"- Never cited: {never_cited} ({pct:.0f}%)")
    lines.append("")

    lines.append("## By layer")
    lines.append("")
    lines.append("| Layer | Items | Never cited | Never-cited % |")
    lines.append("|---|---|---|---|")
    for layer in LAYERS:
        layer_items = [item for item in all_items if item.get("layer") == layer]
        if not layer_items:
            continue
        layer_never = sum(1 for item in layer_items if not item["cited"])
        layer_pct = layer_never / len(layer_items) * 100
        lines.append(f"| {layer} | {len(layer_items)} | {layer_never} | {layer_pct:.0f}% |")
    lines.append("")

    fallback_items = [
        item
        for item in all_items
        if item.get("what_l1_fallback") == "true" or item.get("how_l1_fallback") == "true"
    ]
    lines.append("## Fallback items specifically")
    lines.append("")
    if fallback_items:
        fb_never = sum(1 for item in fallback_items if not item["cited"])
        lines.append(
            f"- What-L1 / How-L1 fallback items: {len(fallback_items)} total, "
            f"{fb_never} never cited"
        )
        lines.append(
            "- These are the lower-confidence, human-reviewed items where "
            "\"generated but then ignored\" is the most actionable finding."
        )
    else:
        lines.append("No What-L1 or How-L1 fallback items found across scanned packages.")
    lines.append("")

    lines.append("## Per-package")
    lines.append("")
    lines.append("| Package | Items | Cited | Generated |")
    lines.append("|---|---|---|---|")
    for pkg in packages:
        pkg_cited = sum(1 for item in pkg["items"] if item["cited"])
        lines.append(
            f"| {pkg['id']} | {len(pkg['items'])} | {pkg_cited} | "
            f"{pkg['generated_at'] or 'unknown'} |"
        )
    lines.append("")

    lines.append("## Token data")
    lines.append("")
    samples = report["tokens_used_samples"]
    if samples:
        lines.append(
            f"- Based on {len(samples)} measured run(s) - not an estimate: "
            f"min {min(samples)}, max {max(samples)}, avg {sum(samples) / len(samples):.0f}"
        )
    else:
        lines.append(
            "No measured runs yet - see `tokens_used` in "
            "`CONSUMING-CONTEXT-PACKAGE.md` step 9."
        )
    lines.append("")

    return "\n".join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    contexts_dir = "contexts/"
    i = 0
    while i < len(argv):
        if argv[i] == "--dir" and i + 1 < len(argv):
            contexts_dir = argv[i + 1]
            i += 2
        else:
            print("usage: usage_report.py [--dir contexts/]", file=sys.stderr)
            return 2

    report = aggregate(contexts_dir)
    markdown = render_markdown(report)

    out_path = Path(contexts_dir) / "USAGE_REPORT.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote {out_path} ({len(report['packages'])} package(s) found)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
