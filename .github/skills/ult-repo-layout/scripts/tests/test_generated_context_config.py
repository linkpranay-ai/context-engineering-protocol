"""Regression suite for the generated `context-config.yaml` baseline (D21
§16.6, Phase 3d).

`install.ps1 -InitProject` / `install.sh --init-project` generate this file by
copying `starter_kits/context_engineering/context-config.yaml.template` and
applying a 7-row mechanical substitution table (documented in
`ult-repo-layout/SKILL.md` "Generated context-config.yaml"); 5 rows are
substituted with their `e.g.` defaults, and `project_name`/`description` are
the only two fields deliberately left as `<placeholder>` for the human (or
`/ult-repo-layout init`) to fill in.

This suite pins that substitution table against the live template so the two
can't silently drift apart, and confirms the resulting file still composes
cleanly with validate_layout.py's "not initialized" pass (init's S7 guard) -
exactly what a brand-new project sees before running `/ult-repo-layout init`.

Stdlib unittest only, same convention as test_validate_layout.py. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_layout as vl  # noqa: E402

# .github/skills/ult-repo-layout/scripts/tests/ -> radisys-ai-power-lib/
REPO_ROOT = Path(__file__).resolve().parents[5]
TEMPLATE_PATH = REPO_ROOT / "starter_kits" / "context_engineering" / "context-config.yaml.template"

# The 5 mechanical substitutions (ult-repo-layout/SKILL.md "Generated
# context-config.yaml"). project_name/description are deliberately NOT here -
# they're the only two fields left as <placeholder> for the human.
SUBSTITUTIONS = {
    "<source code root, e.g. app/ or src/>": ".",
    "<requirements docs root, e.g. docs/requirements/>": "docs/requirements/",
    "<external reference root, e.g. specs/external/>": "specs/external/",
    "<org conventions/templates root, e.g. org/>": "org/",
    "<process standards root, e.g. org/process-standards/>": "org/process-standards/",
}

REMAINING_PLACEHOLDERS = {
    "<your-project-name>",
    "<one-line description of what this product/service does>",
}


def _collect_placeholder_values(node):
    """Recursively collect every string value of the form '<...>' from a
    parsed config tree."""
    found = []
    if isinstance(node, dict):
        for value in node.values():
            found.extend(_collect_placeholder_values(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_placeholder_values(item))
    elif isinstance(node, str) and node.startswith("<") and node.endswith(">"):
        found.append(node)
    return found


def generated_config_text():
    """Apply the Phase 3d substitution table to the live template, exactly as
    install.ps1/install.sh do."""
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    for placeholder, value in SUBSTITUTIONS.items():
        if placeholder not in text:
            raise AssertionError(
                f"context-config.yaml.template no longer contains "
                f"{placeholder!r} - the Phase 3d substitution table in "
                f"ult-repo-layout/SKILL.md and the install scripts are now "
                f"out of sync with the template."
            )
        text = text.replace(placeholder, value)
    return text


class TestSubstitutionTable(unittest.TestCase):
    def test_template_exists(self):
        self.assertTrue(TEMPLATE_PATH.is_file(), TEMPLATE_PATH)

    def test_only_project_name_and_description_placeholders_remain(self):
        config = vl.load_yaml_lite(generated_config_text())
        placeholders = set(_collect_placeholder_values(config))
        self.assertEqual(placeholders, REMAINING_PLACEHOLDERS)

    def test_cache_product_context_path_untouched(self):
        # cache.product_context_path is the context_packages slot's pre-D21
        # default/fallback (Phase 0) - not part of the substitution table, so
        # it must survive byte-for-byte.
        config = vl.load_yaml_lite(generated_config_text())
        self.assertEqual(config["cache"]["product_context_path"], "contexts/")

    def test_no_project_layout_section(self):
        # §16.6 item 2 / SKILL.md: the generated baseline has no
        # project_layout section, so it composes cleanly with init's S7
        # "refuse if already initialized" guard.
        config = vl.load_yaml_lite(generated_config_text())
        self.assertNotIn("project_layout", config)


class TestGeneratedConfigValidation(unittest.TestCase):
    def test_validates_as_not_initialized_with_no_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "context-config.yaml").write_text(
                generated_config_text(), encoding="utf-8"
            )
            ok, report = vl.validate(root)
            self.assertTrue(ok, "\n".join(report))
            self.assertFalse(any(line.startswith("FAIL") for line in report))
            self.assertTrue(any("not initialized" in line for line in report))

    def test_context_packages_defaults_to_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "context-config.yaml").write_text(
                generated_config_text(), encoding="utf-8"
            )
            ok, report = vl.validate(root)
            self.assertTrue(
                any(
                    "context_packages" in line and "using default 'contexts/'" in line
                    for line in report
                ),
                "\n".join(report),
            )


if __name__ == "__main__":
    unittest.main()
