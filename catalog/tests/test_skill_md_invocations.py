"""Repo-level test for Round-2 adversarial-review finding 2.2 (2026-08-31): the
`python scripts/check_graphify_output.py .` invocation documented in
ult-codegraph/SKILL.md's "How to run" section wasn't actually runnable as written
-- it's a path relative to the skill's own `scripts/` directory, but every other
documented invocation in this repo (and the CI workflow itself) runs from repo
root, where that relative path doesn't resolve. Stdlib unittest only. Run with:

python -m unittest discover -s catalog/tests -v
"""
import re
import unittest
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_MD = LIBRARY_ROOT / ".github" / "skills" / "ult-codegraph" / "SKILL.md"

# Matches a `python <path>.py` invocation (skipping `-m`/other flag-led
# invocations like `python -m unittest ...`, which name a module, not a repo file).
PYTHON_SCRIPT_INVOCATION_RE = re.compile(r"^\s*python3?\s+(?!-)(\S+\.py)\b", re.MULTILINE)

BASH_FENCE_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def _bash_blocks(markdown_text):
    return BASH_FENCE_RE.findall(markdown_text)


def _python_script_invocations(bash_block_text):
    return PYTHON_SCRIPT_INVOCATION_RE.findall(bash_block_text)


class TestSkillMdInvocationsResolveFromRepoRoot(unittest.TestCase):
    def test_ult_codegraph_skill_md_has_at_least_one_bash_block(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertTrue(_bash_blocks(text), "expected at least one ```bash block in ult-codegraph/SKILL.md")

    def test_every_python_script_invocation_resolves_from_repo_root(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        invocations = []
        for block in _bash_blocks(text):
            invocations.extend(_python_script_invocations(block))

        self.assertTrue(
            invocations,
            "expected at least one `python <script>.py` invocation in ult-codegraph/SKILL.md",
        )

        unresolved = [
            rel_path for rel_path in invocations
            if not (LIBRARY_ROOT / rel_path).is_file()
        ]
        self.assertEqual(
            unresolved,
            [],
            f"these documented invocations in ult-codegraph/SKILL.md do not resolve "
            f"to an existing file from repo root (the cwd every other documented "
            f"invocation and the CI workflow itself assumes): {unresolved}",
        )

    def test_check_graphify_output_invocation_specifically_is_repo_root_relative(self):
        # The exact regression this finding reported: pin down that the fixed
        # invocation is the repo-root-relative form, not just "some path that
        # happens to resolve" (e.g. if a future edit relies on a different cwd).
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn(
            "python .github/skills/ult-codegraph/scripts/check_graphify_output.py",
            text,
        )


if __name__ == "__main__":
    unittest.main()
