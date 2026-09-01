"""Regression suite for discover_layers.py (§17.2-17.4).

Stdlib unittest only, same posture as test_validate_layout.py. Run with:

    python -m unittest discover -s scripts/tests -v

Test classes are grouped by §17.9 stress-scenario intent rather than by
function, since discovery's externally-observable unit is "what shows up in
the artifact for this repo layout" - matching how the design doc itself
frames the stress scenarios (S23-S27, S29-S40; S28 is out of scope for this
module, untouched).
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import confirm_layers as cl  # noqa: E402
import discover_layers as dl  # noqa: E402
import validate_layout as vl  # noqa: E402


def write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TempRepoTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, text=""):
        if text:
            write(self.repo_root / "context-config.yaml", text)
            return vl.load_yaml_file(self.repo_root / "context-config.yaml") or {}
        return {}


# ---------------------------------------------------------------------------
# S23-ish: step 1 precedence - hand-configured, non-default, populated path
# always wins, no scoring, no decision field (shape 2b NOTICE).
# ---------------------------------------------------------------------------

class TestPrecedenceCheck(TempRepoTestCase):
    def test_what_l2_hand_configured_path_wins_no_decision(self):
        write(self.repo_root / "my-specs" / "a.md", "# spec")
        config = self.config("layers:\n  what_l2:\n    path: my-specs/\n")
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertEqual(path, "my-specs/")
        self.assertIn("hand-configured", section.render())
        self.assertFalse(section.decision_lines)

    def test_how_l2_hand_configured_path_wins_no_decision(self):
        write(self.repo_root / "team-conventions" / "style.md", "# style")
        config = self.config("how_dimension:\n  how_l2:\n    path: team-conventions/\n")
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertEqual(path, "team-conventions/")
        self.assertFalse(section.decision_lines)
        self.assertIn("hand-configured", section.render())

    def test_what_l1_hand_configured_path_wins_regardless_of_enabled(self):
        write(self.repo_root / "specs" / "external" / "rfc.md", "# rfc")
        config = self.config(
            "layers:\n  what_l1:\n    enabled: false\n    path: specs/external/\n"
        )
        section, path = dl.discover_what_l1(self.repo_root, config)
        self.assertEqual(path, "specs/external/")
        self.assertFalse(section.decision_lines)


# ---------------------------------------------------------------------------
# Step 2: CEP default path check (What-L2/How-L2 only).
# ---------------------------------------------------------------------------

class TestDefaultPathCheck(TempRepoTestCase):
    def test_what_l2_pre_d21_default_populated_is_notice_only(self):
        write(self.repo_root / "docs" / "requirements" / "a.md", "# reqs")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertFalse(section.decision_lines)
        self.assertIn("NOTICE", section.render())

    def test_how_l2_default_org_populated_is_notice_only(self):
        write(self.repo_root / "org" / "a.md", "# org conventions")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertEqual(path, "org/")
        self.assertFalse(section.decision_lines)


# ---------------------------------------------------------------------------
# Step 3: scan-and-score, Requirements category found -> CONFIRM/CUSTOM/SKIP.
# ---------------------------------------------------------------------------

class TestWhatL2ScanAndScore(TempRepoTestCase):
    def test_requirements_named_dir_with_many_docs_is_high_confidence(self):
        for i in range(12):
            write(self.repo_root / "specification" / f"{i}.md", "# x")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("decision: PENDING", rendered)
        self.assertIn("CONFIRM: specification/", rendered)
        self.assertIn("High", rendered)

    def test_unnamed_dir_with_few_docs_is_low_confidence_but_still_a_candidate(self):
        # At MIN_DOC_COUNT_FOR_UNNAMED_MATCH (2) but below
        # MEDIUM_CONFIDENCE_FILE_FLOOR (3), no name match -> still a
        # candidate, just Low confidence.
        write(self.repo_root / "misc" / "0.md", "# x")
        write(self.repo_root / "misc" / "1.md", "# y")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("misc/", rendered)
        self.assertIn("Low", rendered)

    def test_single_stray_file_unnamed_dir_is_not_a_candidate(self):
        # Below MIN_DOC_COUNT_FOR_UNNAMED_MATCH (2) and no name match ->
        # not evidence of an authored corpus, excluded entirely.
        write(self.repo_root / "misc" / "0.md", "# x")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertNotIn("misc/", rendered)

    def test_dot_prefixed_directory_excluded_from_candidates(self):
        # Simulates .pytest_cache/README.md - a tool-generated stray file
        # inside a hidden cache directory must never surface as a candidate,
        # regardless of file count or name match.
        write(self.repo_root / ".pytest_cache" / "README.md", "# pytest cache")
        write(self.repo_root / ".pytest_cache" / "v" / "cache" / "requirements.md", "# x")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertNotIn("pytest_cache", rendered)
        self.assertIsNone(path)

    def test_no_requirements_match_never_auto_assigns_path_to_other_category(self):
        # H-2: a Design-only match (diagram file, no .md/.rst/.adoc so it
        # never also trips the Requirements doc-count signal) must not
        # silently become what_l2.path.
        write(self.repo_root / "architecture" / "0001-decision.drawio", "<diagram/>")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertIsNone(path)
        rendered = section.render()
        self.assertIn("H-2", rendered)
        self.assertIn("architecture/", rendered)

    def test_design_and_api_matches_become_include_roots_when_requirements_found(self):
        for i in range(12):
            write(self.repo_root / "requirements" / f"{i}.md", "# req")
        write(self.repo_root / "architecture" / "0001-decision.md", "# adr")
        write(self.repo_root / "api-spec" / "openapi.yaml", "openapi: 3.0.0")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("include_roots_decision: PENDING   # ADD: architecture/", rendered)
        self.assertIn("include_roots_decision: PENDING   # ADD: api-spec/", rendered)

    def test_multi_category_dir_gets_exactly_one_include_roots_line(self):
        # M-2 dedup: a single directory matching Design AND API/spec must not
        # produce two competing include_roots_decision lines for one path.
        for i in range(12):
            write(self.repo_root / "requirements" / f"{i}.md", "# req")
        write(self.repo_root / "api-schema" / "0001-decision.md", "# adr-named, also api-named dir")
        write(self.repo_root / "api-schema" / "openapi.yaml", "openapi: 3.0.0")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertEqual(rendered.count("include_roots_decision: PENDING   # ADD: api-schema/"), 1)

    def test_nothing_found_anywhere_escalates_to_custom_or_acknowledge(self):
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE", rendered)
        self.assertIsNone(path)

    def test_cep_bucket_dirs_excluded_from_scan(self):
        for i in range(12):
            write(self.repo_root / "contexts" / f"{i}.md", "# should never count")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertNotIn("contexts/", rendered)

    def test_examples_dir_with_per_example_readmes_is_not_a_requirements_candidate(self):
        # the 2026-08-31 Round-2 evaluation's finding on repo-layout discovery proposing unsuitable candidate directories after installation: a directory of runnable
        # sample code with one README.md per example crosses
        # MIN_DOC_COUNT_FOR_UNNAMED_MATCH (2) despite holding no requirements
        # prose at all - CODE_SAMPLE_DIR_NAMES excludes the un-named
        # fallback route for this exact directory-name convention.
        write(self.repo_root / "examples" / "hello-world" / "README.md", "# Hello World example")
        write(self.repo_root / "examples" / "hello-world" / "main.py", "print('hi')")
        write(self.repo_root / "examples" / "advanced" / "README.md", "# Advanced example")
        write(self.repo_root / "examples" / "advanced" / "main.py", "print('hi')")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertNotIn("examples/", rendered)
        self.assertIsNone(path)

    def test_code_dominant_unnamed_dir_is_not_a_requirements_candidate_regardless_of_name(self):
        # Generalizes the examples/ fix beyond the named fast path: any
        # directory whose code files outnumber its doc files by
        # CODE_DOMINANCE_RATIO is read as "predominantly code, incidentally
        # documented", whatever it happens to be named.
        write(self.repo_root / "cookbook" / "recipe-one" / "README.md", "# Recipe one")
        for i in range(8):
            write(self.repo_root / "cookbook" / "recipe-one" / f"step{i}.py", "pass")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertNotIn("cookbook/", rendered)

    def test_examples_dir_with_genuine_name_match_still_qualifies(self):
        # A name match (REQUIREMENTS_NAME_RE) is untouched by
        # CODE_SAMPLE_DIR_NAMES/CODE_EXTENSIONS - only the un-named generic
        # fallback route is narrowed.
        for i in range(12):
            write(self.repo_root / "specs" / f"{i}.md", "# req")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CONFIRM: specs/", rendered)


class TestWhatL2WorkspaceRootSet(TempRepoTestCase):
    def test_populated_workspace_root_after_exclude_is_notice_only(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        config = self.config(
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n"
        )
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertEqual(path, "docs/")
        self.assertFalse(any(d.startswith("decision:") for d in section.decision_lines))

    def test_sibling_composite_scan_runs_outside_workspace_root(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        write(self.repo_root / "openapi" / "openapi.yaml", "openapi: 3.0.0")
        config = self.config(
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n"
        )
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertIn("openapi/", roots)
        self.assertIn("include_roots_decision: PENDING   # ADD: openapi/", section.render())

    def test_vendor_looking_subdir_inside_workspace_root_proposed_for_exclude(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        for i in range(6):
            write(self.repo_root / "docs" / "vendor-snapshots" / f"file{i}.bin", "binary-ish, not a doc")
        config = self.config(
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n"
        )
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("exclude_decision: PENDING   # ADD: docs/vendor-snapshots/", rendered)

    def test_m3_caution_note_when_excluded_candidate_equals_another_layers_path(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        for i in range(6):
            write(self.repo_root / "docs" / "legacy-conventions" / f"file{i}.bin", "not a doc")
        config = self.config(
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n"
            "how_dimension:\n  how_l2:\n    path: docs/legacy-conventions/\n"
        )
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CAUTION", rendered)
        self.assertIn("how_dimension.how_l2.path", rendered)


# ---------------------------------------------------------------------------
# How-L2: fixed candidate list, then root-signal fallback (H-3).
# ---------------------------------------------------------------------------

class TestHowL2CandidateScan(TempRepoTestCase):
    def test_docs_style_guide_candidate_found(self):
        write(self.repo_root / "docs" / "style-guide" / "a.md", "# style")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertIn("decision: PENDING   # CONFIRM: docs/style-guide/", section.render())

    def test_github_dir_is_a_candidate(self):
        write(self.repo_root / ".github" / "CODEOWNERS", "* @team")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertIn("CONFIRM: .github/", section.render())

    def test_cep_own_installed_skills_and_prompts_do_not_inflate_github_candidacy(self):
        # Regression test: a repo with CEP itself installed has
        # .github/skills/<name>/SKILL.md per installed skill and
        # .github/prompts/*.prompt.md - CEP's own shipped content, not this
        # project's own authored conventions. Previously these alone made
        # .github/ outscore (or even exist as) a genuine How-L2 candidate,
        # proposing CEP's own install directory as the project's conventions
        # dir. Neither subtree should count towards .github/'s candidacy at
        # all here - no real project content exists under .github/ in this
        # fixture, so it must not appear as a candidate.
        write(self.repo_root / ".github" / "skills" / "some-skill" / "SKILL.md", "# Some Skill")
        write(self.repo_root / ".github" / "prompts" / "do-thing.prompt.md", "# Do Thing")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertNotIn(".github/", section.render())

    def test_genuine_github_content_still_wins_alongside_cep_install(self):
        # Same install footprint as above, but this project also keeps real
        # conventions docs directly under .github/ - .github/ must still
        # surface as a candidate on the strength of that real content, with
        # the CEP-install noise simply not counted.
        write(self.repo_root / ".github" / "skills" / "some-skill" / "SKILL.md", "# Some Skill")
        write(self.repo_root / ".github" / "prompts" / "do-thing.prompt.md", "# Do Thing")
        write(self.repo_root / ".github" / "CONTRIBUTING.md", "# Contributing")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertIn("CONFIRM: .github/", section.render())

    def test_ci_workflow_file_alone_does_not_inflate_github_candidacy(self):
        # the 2026-08-31 Round-2 evaluation's finding on repo-layout discovery proposing unsuitable candidate directories after installation: skills/prompts exclusion
        # alone isn't enough - a bare CI workflow YAML (automation, not an
        # authored convention) is neither a doc nor a recognized
        # HOW_L2_GITHUB_SIGNAL_NAMES/_DIRS entry, and previously the "any
        # file at all" fallback let it single-handedly qualify .github/ once
        # skills/prompts were excluded. Nearly every real repo has a CI
        # workflow regardless of whether it has any authored conventions.
        write(self.repo_root / ".github" / "skills" / "some-skill" / "SKILL.md", "# Some Skill")
        write(self.repo_root / ".github" / "prompts" / "do-thing.prompt.md", "# Do Thing")
        write(self.repo_root / ".github" / "workflows" / "ci.yml", "name: CI\non: [push]\n")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertNotIn(".github/", section.render())

    def test_github_issue_template_dir_still_counts_as_a_signal(self):
        write(self.repo_root / ".github" / "ISSUE_TEMPLATE" / "bug.md", "# Bug report")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertIn("CONFIRM: .github/", section.render())

    def test_github_candidate_carries_caution_about_nested_cep_tooling(self):
        # Even when .github/ legitimately ranks on real content, a human
        # confirming it needs to know CEP's own skills/prompts stay nested
        # inside that same path - discovery-time exclusion never carries
        # forward into what "confirmed how_l2.path=.github/" means
        # downstream.
        write(self.repo_root / ".github" / "skills" / "some-skill" / "SKILL.md", "# Some Skill")
        write(self.repo_root / ".github" / "CODEOWNERS", "* @team")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CONFIRM: .github/", rendered)
        self.assertIn("WARNING", rendered)
        self.assertIn(".github/skills/", rendered)

    def test_no_caution_when_github_is_not_a_candidate_at_all(self):
        write(self.repo_root / "docs" / "style-guide" / "a.md", "# style")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertNotIn("WARNING", section.render())

    def test_manifest_present_still_excludes_the_common_skills_and_prompts_pair(self):
        # Same fixture as test_cep_own_installed_skills_and_prompts_do_not_
        # inflate_github_candidacy above, but with a .cep-install.json
        # manifest present too - the manifest-driven path
        # (_manifest_extra_ignored) must reach the same answer as the
        # hardcoded HOW_L2_GITHUB_CANDIDATE_EXCLUDE fallback for the common
        # full-install shape.
        write(self.repo_root / ".github" / "skills" / "some-skill" / "SKILL.md", "# Some Skill")
        write(self.repo_root / ".github" / "prompts" / "do-thing.prompt.md", "# Do Thing")
        write(
            self.repo_root / ".cep-install.json",
            json.dumps({
                "schema_version": 1,
                "runtime": ["claude", "copilot"],
                "mode": "full",
                "only_skills": None,
                "owned_paths": [".github/skills", ".github/prompts", ".cursor/rules"],
                "installed_at": "2026-01-01T00:00:00Z",
            }),
        )
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertNotIn(".github/", section.render())

    def test_manifest_generalizes_beyond_the_hardcoded_skills_and_prompts_pair(self):
        # The hardcoded HOW_L2_GITHUB_CANDIDATE_EXCLUDE fallback only ever
        # knows about {"skills", "prompts"} - a manifest-owned .github/
        # subtree under any other name would NOT be excluded by the
        # fallback, and .github/ would wrongly surface as a candidate on
        # the strength of CEP's own content. With a manifest naming that
        # subtree explicitly, it's excluded correctly instead.
        write(self.repo_root / ".github" / "agents" / "a.md", "# a")
        write(self.repo_root / ".github" / "agents" / "b.md", "# b")
        write(self.repo_root / ".github" / "agents" / "c.md", "# c")
        write(
            self.repo_root / ".cep-install.json",
            json.dumps({
                "schema_version": 1,
                "runtime": ["claude", "copilot"],
                "mode": "only",
                "only_skills": ["some-skill"],
                "owned_paths": [".github/agents"],
                "installed_at": "2026-01-01T00:00:00Z",
            }),
        )
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertNotIn(".github/", section.render())

    def test_only_install_manifest_naming_a_nested_skill_dir_still_excludes(self):
        # Regression test: a --only install of a single skill writes a
        # manifest naming the skill-dir itself (.github/skills/<name>),
        # never the container (.github/skills). _manifest_extra_ignored
        # must still resolve this to the immediate-child name "skills" via
        # a descendant match, not just a direct-child (owned.parent ==
        # cand_dir) match - and the result must be unioned with the
        # hardcoded {"skills", "prompts"} fallback, not replace it, so a
        # narrower --only manifest that says nothing about .github/prompts
        # still excludes it exactly as the no-manifest case would. Before
        # the fix, this exact fixture surfaced .github/ as a CONFIRM
        # candidate - worse than having no manifest at all.
        write(self.repo_root / ".github" / "skills" / "some-skill" / "SKILL.md", "# Some Skill")
        write(self.repo_root / ".github" / "prompts" / "do-thing.prompt.md", "# Do Thing")
        write(
            self.repo_root / ".cep-install.json",
            json.dumps({
                "schema_version": 1,
                "runtime": ["claude"],
                "mode": "only",
                "only_skills": ["some-skill"],
                "owned_paths": [".github/skills/some-skill"],
                "installed_at": "2026-01-01T00:00:00Z",
            }),
        )
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertNotIn(".github/", section.render())

    def test_manifest_absent_falls_back_to_hardcoded_pair_unchanged(self):
        # No .cep-install.json in this fixture (this repo's own tempdir
        # fixtures never write one unless a test does so explicitly) -
        # _read_cep_manifest returns None and discover_how_l2 must fall
        # back to exactly today's HOW_L2_GITHUB_CANDIDATE_EXCLUDE behavior,
        # not treat "no manifest" as "nothing excluded".
        self.assertIsNone(dl._read_cep_manifest(self.repo_root))
        write(self.repo_root / ".github" / "skills" / "some-skill" / "SKILL.md", "# Some Skill")
        write(self.repo_root / ".github" / "prompts" / "do-thing.prompt.md", "# Do Thing")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertNotIn(".github/", section.render())

    def test_root_signals_only_is_not_silent_default_to_dot(self):
        write(self.repo_root / "CONTRIBUTING.md", "# contributing")
        write(self.repo_root / ".editorconfig", "root = true")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CUSTOM: <path> | ACKNOWLEDGE", rendered)
        self.assertIn("CONTRIBUTING.md", rendered)
        self.assertIsNone(path)

    def test_nothing_at_all_escalates(self):
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertIn("CUSTOM: <path> | ACKNOWLEDGE", section.render())


# ---------------------------------------------------------------------------
# What-L1 / How-L1: opt-in 4-case enabled/found matrix.
# ---------------------------------------------------------------------------

class TestOptInLayerMatrix(TempRepoTestCase):
    def test_disabled_and_found_gets_decision_and_enable_fields(self):
        write(self.repo_root / "standards" / "a.md", "# standard")
        config = self.config("layers:\n  what_l1:\n    enabled: false\n")
        section, path = dl.discover_what_l1(self.repo_root, config)
        rendered = section.render()
        self.assertIn("decision: PENDING   # CONFIRM: standards/", rendered)
        self.assertIn("enable: PENDING", rendered)

    def test_disabled_and_not_found_proposes_nothing(self):
        config = self.config("layers:\n  what_l1:\n    enabled: false\n")
        section, path = dl.discover_what_l1(self.repo_root, config)
        self.assertFalse(section.decision_lines)
        self.assertIn("Nothing proposed", section.render())

    def test_enabled_and_found_gets_decision_only_no_enable_field(self):
        write(self.repo_root / "vendor" / "docs" / "a.md", "# vendor doc")
        config = self.config("layers:\n  what_l1:\n    enabled: true\n")
        section, path = dl.discover_what_l1(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CONFIRM: vendor/docs/", rendered)
        self.assertNotIn("enable: PENDING", rendered)

    def test_enabled_and_not_found_escalates_never_shape_3(self):
        config = self.config("layers:\n  what_l1:\n    enabled: true\n")
        section, path = dl.discover_what_l1(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CUSTOM: <path> | DISABLE", rendered)

    def test_how_l1_uses_its_own_candidate_list(self):
        write(self.repo_root / "process" / "a.md", "# process doc")
        config = self.config("how_dimension:\n  how_l1:\n    enabled: false\n")
        section, path = dl.discover_how_l1(self.repo_root, config)
        self.assertIn("CONFIRM: process/", section.render())


# ---------------------------------------------------------------------------
# Cross-layer collision/nesting check (S30) - new to this package.
# ---------------------------------------------------------------------------

class TestCrossLayerCollisionCheck(TempRepoTestCase):
    def test_equal_paths_collide(self):
        collisions = dl.check_cross_layer_collisions(
            {}, what_l2_path="docs/", how_l2_path="docs/",
        )
        self.assertEqual(len(collisions), 1)
        self.assertEqual({collisions[0][0], collisions[0][1]}, {"layers.what_l2.path", "how_dimension.how_l2.path"})

    def test_nested_paths_collide(self):
        collisions = dl.check_cross_layer_collisions(
            {}, what_l2_path="docs/", how_l1_path="docs/standards/",
        )
        self.assertEqual(len(collisions), 1)

    def test_sibling_paths_do_not_collide(self):
        collisions = dl.check_cross_layer_collisions(
            {}, what_l2_path="docs/requirements/", how_l2_path="docs/conventions/",
        )
        self.assertEqual(collisions, [])

    def test_include_root_candidate_participates_in_collision_check(self):
        collisions = dl.check_cross_layer_collisions(
            {}, what_l2_path="docs/", what_l2_roots=["standards/"], how_l1_path="standards/policy/",
        )
        self.assertEqual(len(collisions), 1)
        labels = {collisions[0][0], collisions[0][1]}
        self.assertIn("how_dimension.how_l1.path", labels)

    def test_render_collision_section_uses_pending_decision_field(self):
        collisions = [("layers.what_l2.path", "how_dimension.how_l2.path", "docs", "docs")]
        section = dl.render_collision_section(collisions)
        rendered = section.render()
        self.assertIn("collision_decision: PENDING", rendered)
        self.assertIn("ACKNOWLEDGE", rendered)
        self.assertIn("CUSTOM", rendered)

    def test_no_collisions_renders_no_section(self):
        self.assertIsNone(dl.render_collision_section([]))

    def test_end_to_end_discover_layers_surfaces_collision_section(self):
        write(self.repo_root / "org" / "a.md", "# org")  # resolves how_l2 to org/ by default
        config = self.config(
            "layers:\n  what_l1:\n    enabled: true\n    path: org/\n"
        )
        sections, cfg = dl.discover_layers(self.repo_root)
        titles = [s.title for s in sections]
        self.assertIn("Cross-layer path collisions (S30)", titles)


# ---------------------------------------------------------------------------
# Regression: dogfood-style already-correctly-configured project sees zero
# new decision fields anywhere (Success Criteria's true-negative case).
# ---------------------------------------------------------------------------

class TestAllFourLayersAlreadyCorrect(TempRepoTestCase):
    def test_zero_decisions_when_everything_hand_set_and_populated(self):
        write(self.repo_root / "reqs" / "a.md", "# req")
        write(self.repo_root / "conv" / "a.md", "# conv")
        write(self.repo_root / "ext" / "a.md", "# ext")
        write(self.repo_root / "proc" / "a.md", "# proc")
        config = self.config(
            "layers:\n"
            "  what_l2:\n    path: reqs/\n"
            "  what_l1:\n    enabled: true\n    path: ext/\n"
            "how_dimension:\n"
            "  how_l2:\n    path: conv/\n"
            "  how_l1:\n    enabled: true\n    path: proc/\n"
        )
        sections, cfg = dl.discover_layers(self.repo_root)
        for section in sections:
            self.assertFalse(section.decision_lines, msg=f"{section.title} had unexpected decisions:\n{section.render()}")


# ---------------------------------------------------------------------------
# Artifact rendering smoke test (§17.3's "how to confirm" tail).
# ---------------------------------------------------------------------------

class TestArtifactRendering(TempRepoTestCase):
    def test_render_discovery_artifact_includes_how_to_confirm(self):
        sections, cfg = dl.discover_layers(self.repo_root)
        artifact = dl.render_discovery_artifact("my-repo", sections)
        self.assertIn("How to confirm", artifact)
        self.assertIn("confirm-layers", artifact)

    def test_run_discovery_writes_file_at_repo_root_when_no_workspace_root(self):
        out_path, artifact = dl.run_discovery(self.repo_root)
        self.assertEqual(out_path, self.repo_root / "context-layout-discovery.md")
        self.assertTrue(out_path.is_file())

    def test_run_discovery_writes_file_under_workspace_root_when_set(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        write(
            self.repo_root / "context-config.yaml",
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n",
        )
        out_path, artifact = dl.run_discovery(self.repo_root)
        self.assertEqual(out_path, self.repo_root / "docs" / "context-layout-discovery.md")
        self.assertTrue(out_path.is_file())


class TestDriftTracking(TempRepoTestCase):
    """§17.6: a second `discover` run must not re-litigate a section that
    was fully confirmed last time, unless a confirmed path genuinely
    disappeared."""

    def _make_what_l2_candidate(self):
        for i in range(12):
            write(self.repo_root / "specification" / f"doc-{i}.md", "# spec")

    def _resolve_what_l2_pending(self, artifact, verb):
        # This fixture never gives How-L2 a candidate, so its own decision
        # is always the no-candidate-found shape (`CUSTOM: <path> |
        # ACKNOWLEDGE`) - resolve it too (as ACKNOWLEDGE) so confirm-layers
        # sees zero remaining PENDING fields, same as a real human editing
        # every field on the artifact before confirming.
        text = artifact.replace(
            "decision: PENDING   # CONFIRM: specification/ | CUSTOM: <path> | SKIP",
            f"decision: {verb}   # CONFIRM: specification/ | CUSTOM: <path> | SKIP",
            1,
        )
        return text.replace(
            "decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE",
            "decision: ACKNOWLEDGE   # CUSTOM: <path> | ACKNOWLEDGE",
            1,
        )

    def _run_discover_then_confirm(self, verb):
        _out_path, artifact = dl.run_discovery(self.repo_root)
        artifact_path = self.repo_root / "context-layout-discovery.md"
        artifact_path.write_text(self._resolve_what_l2_pending(artifact, verb), encoding="utf-8")
        return cl.run_confirm(self.repo_root)

    def test_confirmed_path_removed_appends_redisc_section_original_untouched(self):
        self._make_what_l2_candidate()
        code, msgs = self._run_discover_then_confirm("CONFIRM")
        self.assertEqual(code, 0, msgs)
        config_before = (self.repo_root / "context-config.yaml").read_text(encoding="utf-8")
        self.assertIn("path: specification/", config_before)

        shutil.rmtree(self.repo_root / "specification")
        _out_path, artifact = dl.run_discovery(self.repo_root)

        self.assertIn("already confirmed - carried forward unchanged", artifact)
        self.assertIn("decision: CONFIRM: specification/", artifact)
        self.assertIn(f"Re-discovery - {dl.WHAT_L2_TITLE}", artifact)
        self.assertIn("no longer exist or are empty: specification/", artifact)

    def test_drift_detected_even_after_confirmed_section_notice_collapses(self):
        """A confirmed CONFIRM/CUSTOM decision may render as a plain NOTICE
        (not a decision line) on the very next `discover` run, once config
        already holds the confirmed path with content - PR1's own
        precedence check does that collapse, independent of §17.6. Drift
        tracking must still detect the path disappearing on a LATER run,
        not just the one immediately after `confirm-layers` - it must not
        silently lose the confirmed record the moment PR1 stops rendering
        a decision line for it."""
        self._make_what_l2_candidate()
        code, msgs = self._run_discover_then_confirm("CONFIRM")
        self.assertEqual(code, 0, msgs)

        _out_path, notice_artifact = dl.run_discovery(self.repo_root)
        self.assertNotIn("Re-discovery", notice_artifact)

        shutil.rmtree(self.repo_root / "specification")
        _out_path, artifact = dl.run_discovery(self.repo_root)

        self.assertIn("already confirmed - carried forward unchanged", artifact)
        self.assertIn("decision: CONFIRM: specification/", artifact)
        self.assertIn(f"Re-discovery - {dl.WHAT_L2_TITLE}", artifact)
        self.assertIn("no longer exist or are empty: specification/", artifact)

    def test_confirmed_path_still_valid_produces_no_redisc_section(self):
        self._make_what_l2_candidate()
        code, msgs = self._run_discover_then_confirm("CONFIRM")
        self.assertEqual(code, 0, msgs)

        _out_path, artifact = dl.run_discovery(self.repo_root)

        self.assertNotIn("Re-discovery", artifact)

    def test_settled_via_skip_is_not_relitigated_on_rerun(self):
        # SKIP writes nothing to context-config.yaml (by design - §17.5),
        # so unlike CONFIRM/CUSTOM, nothing in config lets a fresh scan
        # short-circuit on its own; discover_layers.py's own drift-tracking
        # carry-forward logic is what must suppress the repeat prompt here.
        self._make_what_l2_candidate()
        code, msgs = self._run_discover_then_confirm("SKIP")
        self.assertEqual(code, 0, msgs)
        self.assertFalse((self.repo_root / "context-config.yaml").exists())

        _out_path, artifact2 = dl.run_discovery(self.repo_root)

        self.assertNotIn(": PENDING", artifact2)
        self.assertIn("already confirmed - carried forward unchanged", artifact2)
        self.assertIn("decision: SKIP", artifact2)

    def test_notice_only_section_is_stable_across_repeated_runs(self):
        write(self.repo_root / "specification" / "a.md", "# spec")
        write(self.repo_root / "conventions" / "a.md", "# conv")
        write(
            self.repo_root / "context-config.yaml",
            "layers:\n"
            "  what_l2:\n    path: specification/\n"
            "  what_l1:\n    enabled: false\n"
            "how_dimension:\n"
            "  how_l2:\n    path: conventions/\n"
            "  how_l1:\n    enabled: false\n",
        )
        _out_path, first = dl.run_discovery(self.repo_root)
        self.assertNotIn(": PENDING", first)

        _out_path, second = dl.run_discovery(self.repo_root)

        self.assertEqual(first, second)
        self.assertNotIn("Re-discovery", second)


class TestPerCandidateDriftTracking(TempRepoTestCase):
    """S40 (§17.6 per-candidate extension, PR 3): a confirmed
    include_roots/exclude candidate that's since disappeared gets its own
    narrowly-scoped, dated Re-discovery section naming only that candidate -
    not a re-review of every other already-confirmed candidate in the
    layer, and not a full section re-review when the primary path is still
    fine."""

    def _make_fixture(self):
        for i in range(12):
            write(self.repo_root / "specification" / f"doc-{i}.md", "# spec")
        write(self.repo_root / "architecture" / "decisions.md", "# adr")
        write(self.repo_root / "api-spec" / "openapi.yaml", "openapi: 3.0.0\n")

    def _resolve_pending(self, artifact):
        text = artifact.replace(
            "decision: PENDING   # CONFIRM: specification/ | CUSTOM: <path> | SKIP",
            "decision: CONFIRM   # CONFIRM: specification/ | CUSTOM: <path> | SKIP",
            1,
        )
        text = text.replace(
            "include_roots_decision: PENDING   # ADD: architecture/ | SKIP",
            "include_roots_decision: ADD   # ADD: architecture/ | SKIP",
            1,
        )
        text = text.replace(
            "include_roots_decision: PENDING   # ADD: api-spec/ | SKIP",
            "include_roots_decision: ADD   # ADD: api-spec/ | SKIP",
            1,
        )
        return text.replace(
            "decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE",
            "decision: ACKNOWLEDGE   # CUSTOM: <path> | ACKNOWLEDGE",
            1,
        )

    def _run_discover_then_confirm(self):
        _out_path, artifact = dl.run_discovery(self.repo_root)
        artifact_path = self.repo_root / "context-layout-discovery.md"
        artifact_path.write_text(self._resolve_pending(artifact), encoding="utf-8")
        return cl.run_confirm(self.repo_root)

    def test_single_drifted_candidate_gets_its_own_narrow_section(self):
        self._make_fixture()
        code, msgs = self._run_discover_then_confirm()
        self.assertEqual(code, 0, msgs)
        config = vl.load_yaml_file(self.repo_root / "context-config.yaml") or {}
        self.assertIn("architecture/", config["layers"]["what_l2"]["include_roots"])
        self.assertIn("api-spec/", config["layers"]["what_l2"]["include_roots"])

        _out_path, stable = dl.run_discovery(self.repo_root)
        self.assertNotIn("Re-discovery", stable)

        shutil.rmtree(self.repo_root / "architecture")
        _out_path, artifact = dl.run_discovery(self.repo_root)

        self.assertIn("already confirmed - carried forward unchanged", artifact)
        self.assertIn("include_roots_decision: ADD: architecture/   # CONFIRMED", artifact)
        self.assertIn("include_roots_decision: ADD: api-spec/   # CONFIRMED", artifact)
        self.assertIn(f"Re-discovery - {dl.WHAT_L2_TITLE} - candidates -", artifact)
        self.assertNotIn(f"Re-discovery - {dl.WHAT_L2_TITLE} - 20", artifact)
        self.assertEqual(artifact.count("Re-discovery"), 1)
        self.assertIn("architecture/", artifact.split("Re-discovery")[1])
        self.assertNotIn("api-spec/", artifact.split("Re-discovery")[1])
        self.assertIn(
            "include_roots_decision: PENDING   # ADD: architecture/ | SKIP", artifact
        )

    def test_primary_path_drift_takes_precedence_over_candidate_drift(self):
        self._make_fixture()
        code, msgs = self._run_discover_then_confirm()
        self.assertEqual(code, 0, msgs)

        shutil.rmtree(self.repo_root / "specification")
        shutil.rmtree(self.repo_root / "architecture")
        _out_path, artifact = dl.run_discovery(self.repo_root)

        self.assertEqual(artifact.count("Re-discovery"), 1)
        self.assertNotIn(f"Re-discovery - {dl.WHAT_L2_TITLE} - candidates -", artifact)
        self.assertIn("previously confirmed path(s) no longer exist or are empty", artifact)

    def test_no_drifted_candidates_produces_no_new_sections(self):
        self._make_fixture()
        code, msgs = self._run_discover_then_confirm()
        self.assertEqual(code, 0, msgs)

        _out_path, first = dl.run_discovery(self.repo_root)
        _out_path, second = dl.run_discovery(self.repo_root)

        self.assertNotIn("Re-discovery", first)
        self.assertEqual(first, second)


class TestScanIgnoredDirNamesParity(unittest.TestCase):
    """discover_layers.SCAN_IGNORED_DIR_NAMES and ult-autoscaffold-content's
    scaffold_state.SCAN_IGNORED_DIR_NAMES are deliberately kept as two small
    local duplicates rather than a shared import (house convention - see
    either module's own comment on the pair). A cross-suite equality check
    is the only thing that catches the two silently drifting apart again,
    since neither skill's own suite can see the other's module on its own.
    test_scaffold_state.py carries the mirror of this check, so an edit made
    from either side fails in that side's own suite.
    """

    def test_scan_ignored_dir_names_match_ult_autoscaffold_content(self):
        autoscaffold_scripts = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "ult-autoscaffold-content"
            / "scripts"
        )
        if not autoscaffold_scripts.is_dir():
            # A partial checkout / install without the sibling skill has
            # nothing to compare against. That is not this test's own
            # failure to report - skip rather than fail.
            self.skipTest(
                f"sibling skill scripts dir not present at {autoscaffold_scripts}"
            )
        sys.path.insert(0, str(autoscaffold_scripts))
        try:
            import scaffold_state as ss  # noqa: E402
        finally:
            sys.path.remove(str(autoscaffold_scripts))

        self.assertEqual(
            dl.SCAN_IGNORED_DIR_NAMES,
            ss.SCAN_IGNORED_DIR_NAMES,
            "discover_layers.SCAN_IGNORED_DIR_NAMES and "
            "scaffold_state.SCAN_IGNORED_DIR_NAMES have drifted apart - "
            "keep the two sets content-identical (see either module's "
            "comment on this pair).",
        )


if __name__ == "__main__":
    unittest.main()
