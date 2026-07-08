#!/usr/bin/env python3
"""
Simple keyword-overlap trigger-accuracy check for skill eval cases (GAP-03).

No LLM call — this is a cheap, deterministic proxy for "would an agent skimming
SKILL.md frontmatter descriptions plausibly route this input to the right skill."
It is not a substitute for real model-based eval, but it catches the most common
trigger failures (a skill's description sharing zero vocabulary with the inputs
it's supposed to handle, or sharing too much vocabulary with inputs it should NOT
handle) for free, in CI, on every run.

Reads every evals/*.eval.json (skipping template.json), looks up each case's
skill by its SKILL.md frontmatter `name:` field (not the directory name — they
differ, e.g. sec-threat-model's name: is `threat-model`), and checks:
  - positive cases: input shares at least MIN_OVERLAP significant words with the
    expected skill's description + tags.
  - negative cases: input shares FEWER than MIN_OVERLAP significant words with the
    not-expected skill's description + tags (i.e. it doesn't superficially look
    like a trigger).

Exits 1 if any case fails. See CONTRIBUTING.md for the 3-eval-minimum requirement.
"""
import json
import re
import sys
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = LIBRARY_ROOT / ".github" / "skills"
EVALS_DIR = LIBRARY_ROOT / "evals"
FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---", re.DOTALL)

MIN_OVERLAP = 2

STOPWORDS = {
    "a", "an", "the", "this", "that", "these", "those", "is", "are", "was",
    "were", "be", "been", "being", "to", "of", "in", "on", "for", "with",
    "before", "any", "and", "or", "but", "not", "no", "do", "does", "did",
    "i", "we", "you", "it", "its", "our", "your", "their", "can", "could",
    "should", "would", "will", "just", "now", "here", "there", "what",
    "when", "where", "how", "into", "from", "at", "by", "as", "if", "then",
    "all", "some", "one", "out", "up", "so", "need", "needs", "want",
    "wants", "let", "lets", "me", "us", "please", "quick", "question",
    "actually", "exactly", "explicitly", "ll", "re",
}

WORD_RE = re.compile(r"[a-z0-9]+")


def significant_words(text):
    words = WORD_RE.findall(text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def load_skill_index():
    """name: field (frontmatter) -> {description, tags-as-text}."""
    index = {}
    for path in SKILLS_DIR.rglob("SKILL.md"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        fm_text = m.group(1)
        name_m = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
        desc_m = re.search(r"^description:\s*(.+)$", fm_text, re.MULTILINE)
        tags_m = re.search(r"^tags:\s*\[(.+)\]$", fm_text, re.MULTILINE)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        desc = desc_m.group(1).strip() if desc_m else ""
        tags = tags_m.group(1).strip() if tags_m else ""
        index[name] = {"description": desc, "tags": tags, "path": path}
    return index


def main():
    skill_index = load_skill_index()
    failures = []
    total_cases = 0

    eval_files = sorted(EVALS_DIR.glob("*.eval.json"))
    if not eval_files:
        print("No evals/*.eval.json files found.")
        return 0

    for eval_file in eval_files:
        data = json.loads(eval_file.read_text(encoding="utf-8"))
        for case in data.get("cases", []):
            total_cases += 1
            case_id = case.get("id", "<no id>")
            input_words = significant_words(case.get("input", ""))

            if case.get("type") == "positive":
                target = case.get("expected_skill", "")
                info = skill_index.get(target)
                if info is None:
                    failures.append(f"{case_id}: expected_skill '{target}' not found in any SKILL.md")
                    continue
                target_words = significant_words(info["description"] + " " + info["tags"])
                overlap = input_words & target_words
                if len(overlap) < MIN_OVERLAP:
                    failures.append(
                        f"{case_id}: only {len(overlap)} word(s) overlap with '{target}' "
                        f"description (need >= {MIN_OVERLAP}); overlap={sorted(overlap)}"
                    )

            elif case.get("type") == "negative":
                target = case.get("not_expected_skill", "")
                info = skill_index.get(target)
                if info is None:
                    failures.append(f"{case_id}: not_expected_skill '{target}' not found in any SKILL.md")
                    continue
                target_words = significant_words(info["description"] + " " + info["tags"])
                overlap = input_words & target_words
                if len(overlap) >= MIN_OVERLAP:
                    failures.append(
                        f"{case_id}: {len(overlap)} word(s) overlap with '{target}' description "
                        f"(should be < {MIN_OVERLAP} — input looks too similar to a real trigger); "
                        f"overlap={sorted(overlap)}"
                    )
            else:
                failures.append(f"{case_id}: unknown case type '{case.get('type')}' (expected positive/negative)")

    print(f"Checked {total_cases} eval case(s) across {len(eval_files)} file(s).")
    if failures:
        print(f"\n{len(failures)} trigger-accuracy failure(s):\n")
        for f in failures:
            print(f"  {f}")
        return 1
    print("All eval cases pass keyword-overlap trigger check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
