"""Regression suite for wizard_init.py (the 2026-08-31 Round-2 evaluation's finding on first-run workspace-root namespacing during init).
Stdlib unittest only. Run with:

    python -m unittest discover -s scripts/tests -v

validate_layout.py is copied fresh from the real ult-repo-layout/scripts/ at test
time (not hand-transcribed), same convention as test_wizard_discover.py - so
preview_init/run_init are exercised against the real validate_layout.run_init, not a
paraphrase that could silently drift from it.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_init as wi  # noqa: E402


def _find_real_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        marker = (
            candidate
            / ".github"
            / "skills"
            / "ult-repo-layout"
            / "scripts"
            / "validate_layout.py"
        )
        if marker.exists():
            return candidate
    raise RuntimeError(
        "could not locate the context-engineering-oss repo root from this test "
        "file's location"
    )


REAL_REPO_ROOT = _find_real_repo_root()
REAL_SCRIPTS_DIR = REAL_REPO_ROOT / ".github" / "skills" / "ult-repo-layout" / "scripts"


def _install_ult_repo_layout(repo_root: Path) -> None:
    scripts_dir = repo_root / ".github" / "skills" / "ult-repo-layout" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SCRIPTS_DIR / "validate_layout.py", scripts_dir / "validate_layout.py")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install_owning_skill(repo_root: Path, name: str = "ult-context-generate") -> None:
    (repo_root / ".github" / "skills" / name).mkdir(parents=True, exist_ok=True)


class TestPreviewInit(unittest.TestCase):
    def test_preview_writes_nothing_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            result = wi.preview_init(root, workspace_root=".cep/")

            self.assertTrue(any("Would" in m for m in result.messages))
            self.assertFalse((root / ".cep").exists())
            self.assertFalse((root / "contexts").exists())
            config_text = (root / "context-config.yaml").read_text(encoding="utf-8")
            self.assertNotIn("workspace_root", config_text)

    def test_preview_with_no_workspace_root_previews_pre_d21_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            result = wi.preview_init(root)

            self.assertTrue(any("contexts/" in m for m in result.messages))
            self.assertFalse((root / "contexts").exists())

    def test_blank_workspace_root_is_treated_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            result = wi.preview_init(root, workspace_root="   ")

            self.assertFalse(any("workspace_root" in m for m in result.messages))


class TestPreviewInitRefusals(unittest.TestCase):
    def test_repo_root_as_workspace_root_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            with self.assertRaises(wi.InitError):
                wi.preview_init(root, workspace_root=".")

    def test_already_d20_initialized_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            token = wi.preview_init(root).init_preview_token
            wi.run_init(root, init_preview_token=token)  # real init - now D20-initialized

            with self.assertRaises(wi.InitError):
                wi.preview_init(root, workspace_root="docs/")

    def test_no_installed_owning_skill_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            with self.assertRaises(wi.InitError):
                wi.preview_init(root)

    def test_missing_validate_layout_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(wi.InitError):
                wi.preview_init(root)


class TestRunInit(unittest.TestCase):
    def test_run_init_actually_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            token = wi.preview_init(root, workspace_root=".cep/").init_preview_token

            result = wi.run_init(root, workspace_root=".cep/", init_preview_token=token)

            self.assertTrue(any("Scaffolded" in m or "Registered" in m for m in result.messages))
            self.assertTrue((root / ".cep" / "contexts").is_dir())
            config_text = (root / "context-config.yaml").read_text(encoding="utf-8")
            self.assertIn("workspace_root: .cep", config_text)

    def test_run_init_second_call_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            token = wi.preview_init(root, workspace_root=".cep/").init_preview_token
            wi.run_init(root, workspace_root=".cep/", init_preview_token=token)

            # Already initialized - preview_init itself now refuses before a
            # legitimate token for this second call could ever be minted
            # (test_already_d20_initialized_is_refused covers this refusal
            # directly; asserted again here as the setup for the next line).
            with self.assertRaises(wi.InitError):
                wi.preview_init(root, workspace_root="docs/")
            # run_init refuses too, even handed the first call's own
            # (necessarily stale, for a different workspace_root) token.
            with self.assertRaises(wi.InitError):
                wi.run_init(root, workspace_root="docs/", init_preview_token=token)


class TestInitPreviewTokenGate(unittest.TestCase):
    """the 2026-08-31 Round-2 evaluation's finding on POST /api/init committing without a
    prior preview - unit coverage at the wizard_init.py layer; end-to-end HTTP
    coverage lives in test_wizard_server.py's TestApiInitRoutes."""

    def test_run_init_without_any_token_is_refused_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            with self.assertRaises(wi.InitError):
                wi.run_init(root, workspace_root=".cep/")

            self.assertFalse((root / ".cep").exists())
            config_text = (root / "context-config.yaml").read_text(encoding="utf-8")
            self.assertNotIn("workspace_root", config_text)

    def test_run_init_with_token_for_a_different_workspace_root_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            stale_token = wi.preview_init(root, workspace_root=".cep/").init_preview_token

            with self.assertRaises(wi.InitError):
                wi.run_init(root, workspace_root="docs/", init_preview_token=stale_token)

            self.assertFalse((root / ".cep").exists())
            self.assertFalse((root / "docs" / ".layout-slots.yaml").exists())

    def test_run_init_with_garbage_token_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            with self.assertRaises(wi.InitError):
                wi.run_init(root, workspace_root=".cep/", init_preview_token="not-a-real-token")

            self.assertFalse((root / ".cep").exists())


class TestPreviewMatchesRealRun(unittest.TestCase):
    def test_preview_message_count_matches_real_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            _install_owning_skill(root)
            _write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            preview = wi.preview_init(root, workspace_root="docs/")
            real = wi.run_init(
                root, workspace_root="docs/", init_preview_token=preview.init_preview_token
            )

            self.assertEqual(len(preview.messages), len(real.messages))


if __name__ == "__main__":
    unittest.main()
