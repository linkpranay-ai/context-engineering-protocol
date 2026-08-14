"""Regression suite for wizard_server.py (D24 §18.2/§18.2b). Stdlib unittest only. Run
with:

    python -m unittest discover -s scripts/tests -v

Unlike the other test_wizard_*.py files, this one drives a *real* bound socket end to
end (127.0.0.1, OS-assigned port) rather than calling functions directly - the thing
worth proving here is that wizard_auth/wizard_originhost/wizard_preflight are actually
wired together correctly inside the HTTP handler, which unit-testing each module in
isolation can't show.

Fixture-building helpers are duplicated from test_wizard_preflight.py rather than
imported from it - no existing test file in this repo imports from a sibling test
file, and keeping each test file able to run standalone (`python
test_wizard_server.py`) matters more here than the few lines saved.
"""

import json
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_auth  # noqa: E402
import wizard_preflight  # noqa: E402
import wizard_server as ws  # noqa: E402


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
REAL_SKILL_MD = REAL_REPO_ROOT / ".github" / "skills" / "ult-repo-layout" / "SKILL.md"
REAL_VALIDATE_LAYOUT = (
    REAL_REPO_ROOT
    / ".github"
    / "skills"
    / "ult-repo-layout"
    / "scripts"
    / "validate_layout.py"
)
REAL_DISCOVER_LAYERS = (
    REAL_REPO_ROOT
    / ".github"
    / "skills"
    / "ult-repo-layout"
    / "scripts"
    / "discover_layers.py"
)
REAL_LAYOUT_DECISION_GRAMMAR = (
    REAL_REPO_ROOT
    / ".github"
    / "skills"
    / "ult-repo-layout"
    / "scripts"
    / "layout_decision_grammar.py"
)
REAL_CONFIRM_LAYERS = (
    REAL_REPO_ROOT
    / ".github"
    / "skills"
    / "ult-repo-layout"
    / "scripts"
    / "confirm_layers.py"
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_valid_target_repo(root: Path) -> None:
    """A repo that passes wizard_preflight's one remaining check (ult-repo-layout
    installed) and also validates clean / has real discovery state on disk - i.e. a
    steady_state-shaped repo, not just a preflight-passing one. Same shape as
    test_wizard_preflight.py's positive fixture. Also includes discover_layers.py (not
    needed by preflight itself, but wizard_layout_source.LayoutSource - now
    constructed fresh per-request via _try_layout_source(), not once at startup, see
    wizard-onboarding-state-machine.md §5 - imports it at construction time for every
    test in this file that reaches a handler needing one, not just the /api/status
    ones)."""
    skill_dir = root / ".github" / "skills" / "ult-repo-layout"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SKILL_MD, skill_dir / "SKILL.md")
    shutil.copy(REAL_VALIDATE_LAYOUT, scripts_dir / "validate_layout.py")
    shutil.copy(REAL_DISCOVER_LAYERS, scripts_dir / "discover_layers.py")
    # D24 Phase 1: LayoutSource's module import now also requires
    # layout_decision_grammar.py and confirm_layers.py alongside
    # discover_layers.py - see the matching note in test_wizard_layout_source.py.
    shutil.copy(
        REAL_LAYOUT_DECISION_GRAMMAR, scripts_dir / "layout_decision_grammar.py"
    )
    shutil.copy(REAL_CONFIRM_LAYERS, scripts_dir / "confirm_layers.py")
    (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
    _write(
        root / "contexts" / ".layout-slots.yaml",
        "slots:\n  - slot: context_packages\n    kind: directory\n"
        "    schema_version: 1\n",
    )


def _install_skill(root: Path, skill_name: str, script_names) -> None:
    """Same generalized fixture-copy helper as test_wizard_boxes.py's own
    _install_skill - duplicated rather than imported, per this file's own module
    docstring on why fixture helpers aren't shared across test files."""
    real_skill_dir = REAL_REPO_ROOT / ".github" / "skills" / skill_name
    skill_dir = root / ".github" / "skills" / skill_name
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_skill_dir / "SKILL.md", skill_dir / "SKILL.md")
    for script_name in script_names:
        shutil.copy(real_skill_dir / "scripts" / script_name, scripts_dir / script_name)


@dataclass
class _Resp:
    """Snapshot of an HTTP response read eagerly and the connection closed - avoids
    ResourceWarnings from responses left open past their `with` block while still
    letting callers use `.status`/`.headers`/`.read()` the way an open response
    would."""

    status: int
    headers: object
    _body: bytes

    def read(self) -> bytes:
        return self._body


class WizardServerTestCase(unittest.TestCase):
    """Base class: builds a valid target repo, starts a real wizard_server in a
    background thread against it, tears both down after each test.

    Subclasses may set EXTRA_SKILLS to a tuple of (skill_name, script_names) pairs to
    additionally install into the fixture repo before the server starts - used by the
    /api/status tests that need compiling-project-guidelines/
    ult-institutional-memory-distill present to exercise the available=True branches
    of the Guidelines/Trip-wire boxes."""

    EXTRA_SKILLS: tuple = ()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        _make_valid_target_repo(self.repo_root)
        for skill_name, script_names in self.EXTRA_SKILLS:
            _install_skill(self.repo_root, skill_name, script_names)

        self.server, self.session_store = ws.build_server(str(self.repo_root))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path: str, cookie=None) -> "_Resp":
        req = urllib.request.Request(self._url(path), method="GET")
        if cookie:
            req.add_header("Cookie", f"{wizard_auth.SESSION_COOKIE_NAME}={cookie}")
        try:
            with urllib.request.urlopen(req) as resp:
                return _Resp(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as exc:
            with exc:
                return _Resp(exc.code, exc.headers, exc.read())

    def _authenticated_cookie(self) -> str:
        """Runs the real /exchange flow against the running server and returns the
        resulting session id - the same path a real browser takes, so tests for
        session-gated routes below don't need to reach into SessionStore internals."""
        opener = urllib.request.build_opener(_NoRedirect())
        token = self.session_store.bootstrap_token
        req = urllib.request.Request(self._url(f"/exchange?token={token}"), method="GET")
        with opener.open(req) as resp:
            set_cookie = resp.headers.get("Set-Cookie")
        return set_cookie.split(";")[0].split("=", 1)[1]

    def _authenticated_session(self) -> "tuple[str, str]":
        """Same real /exchange path as _authenticated_cookie, plus the CSRF nonce
        scraped from the served index page's own meta tag - the same value a real
        browser's JS would read via `document.querySelector('meta[name="wizard-csrf-
        token"]')`, not reached for directly off the Session object, so this exercises
        the same embed-in-HTML path _handle_index actually uses (D24 Phase 1's first
        real caller of the CSRF plumbing)."""
        cookie = self._authenticated_cookie()
        resp = self._get("/", cookie=cookie)
        body = resp.read().decode("utf-8")
        match = re.search(r'name="wizard-csrf-token" content="([^"]+)"', body)
        assert match is not None, "index page did not embed a CSRF nonce"
        return cookie, match.group(1)

    def _post_json(self, path: str, payload: dict, cookie=None, csrf=None) -> "_Resp":
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._url(path), data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        # POST is a mutating method (wizard_originhost.MUTATING_METHODS) -
        # request_is_allowed refuses any mutating request missing both Origin
        # and Referer outright, before this ever reaches session/CSRF checks.
        # A real browser sends this automatically; urllib does not, so it has
        # to be set explicitly here to reach the routes under test at all.
        req.add_header("Origin", self._url(""))
        if cookie:
            req.add_header("Cookie", f"{wizard_auth.SESSION_COOKIE_NAME}={cookie}")
        if csrf:
            req.add_header(wizard_auth.CSRF_HEADER_NAME, csrf)
        try:
            with urllib.request.urlopen(req) as resp:
                return _Resp(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as exc:
            with exc:
                return _Resp(exc.code, exc.headers, exc.read())


class TestPreflightGate(unittest.TestCase):
    def test_build_server_raises_on_a_repo_missing_ult_repo_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(wizard_preflight.PreflightError):
                ws.build_server(tmp)


class TestIndexRequiresSession(WizardServerTestCase):
    def test_index_without_cookie_is_401(self):
        resp = self._get("/")
        self.assertEqual(resp.status, 401)

    def test_index_with_bogus_cookie_is_401(self):
        resp = self._get("/", cookie="not-a-real-session")
        self.assertEqual(resp.status, 401)


class TestExchangeFlow(WizardServerTestCase):
    def test_exchange_with_wrong_token_is_401(self):
        resp = self._get("/exchange?token=wrong")
        self.assertEqual(resp.status, 401)

    def _exchange(self, token: str) -> _Resp:
        """Same eager-read-then-close pattern as _get, but through a no-redirect
        opener so the 302 itself (status + Set-Cookie) is observable."""
        opener = urllib.request.build_opener(_NoRedirect())
        req = urllib.request.Request(self._url(f"/exchange?token={token}"), method="GET")
        with opener.open(req) as resp:
            return _Resp(resp.status, resp.headers, resp.read())

    def test_exchange_with_correct_token_redirects_and_sets_cookie(self):
        token = self.session_store.bootstrap_token
        resp = self._exchange(token)
        self.assertEqual(resp.status, 302)
        set_cookie = resp.headers.get("Set-Cookie")
        self.assertIsNotNone(set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)

    def test_replaying_the_same_token_is_rejected(self):
        token = self.session_store.bootstrap_token
        first = self._exchange(token)
        self.assertEqual(first.status, 302)

        resp = self._get(f"/exchange?token={token}")
        self.assertEqual(resp.status, 401)

    def test_session_cookie_from_exchange_authenticates_index(self):
        token = self.session_store.bootstrap_token
        exchange_resp = self._exchange(token)
        set_cookie = exchange_resp.headers.get("Set-Cookie")
        session_id = set_cookie.split(";")[0].split("=", 1)[1]

        resp = self._get("/", cookie=session_id)
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn("wizard-csrf-token", body)


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """Stops urllib from auto-following the 302 from /exchange, so the test can
    inspect the redirect response itself (status + Set-Cookie) rather than whatever
    it redirects to."""

    def http_response(self, request, response):
        return response

    https_response = http_response


class TestUnknownRoute(WizardServerTestCase):
    def test_unknown_path_is_404(self):
        resp = self._get("/does-not-exist")
        self.assertEqual(resp.status, 404)


class TestApiStatusRequiresSession(WizardServerTestCase):
    def test_no_cookie_is_401(self):
        resp = self._get("/api/status")
        self.assertEqual(resp.status, 401)


class TestApiStatusMinimalRepo(WizardServerTestCase):
    """Neither compiling-project-guidelines nor ult-institutional-memory-distill is
    installed (the base _make_valid_target_repo fixture) - Guidelines and Trip-wire
    must both report available=False over real HTTP, matching
    test_wizard_boxes.py's in-process assertions of the same thing."""

    def test_status_shape_and_unavailable_boxes(self):
        cookie = self._authenticated_cookie()
        resp = self._get("/api/status", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(
            set(payload.keys()),
            {"what", "how", "guidelines", "tripwire", "stub_cards"},
        )
        self.assertEqual(payload["what"]["title"], "What")
        self.assertTrue(payload["what"]["l2_enabled"])
        self.assertFalse(payload["what"]["l1_enabled"])
        self.assertEqual(
            [p["path"] for p in payload["what"]["paths"]], ["docs/requirements/"]
        )

        self.assertFalse(payload["guidelines"]["available"])
        self.assertFalse(payload["tripwire"]["available"])

        # Phase 2 (§18.14 Section C): docs/requirements/ resolves but is empty in
        # this fixture, and Guidelines isn't installed at all here (available=False,
        # so guidelines_card's own initialized=False path never even applies) - the
        # What box's stub card is the one that should surface.
        stub_titles = [c["box_title"] for c in payload["stub_cards"]]
        self.assertIn("What", stub_titles)


class TestApiStatusWithOptionalSkillsInstalled(WizardServerTestCase):
    """Both owning skills installed - Guidelines and Trip-wire must both report
    available=True, uninitialized (no decisions/guidelines compiled yet), matching
    test_wizard_boxes.py's/test_wizard_tripwire.py's own in-process fixtures."""

    EXTRA_SKILLS = (
        ("compiling-project-guidelines", ()),
        ("ult-institutional-memory-distill", ("decision_ledger.py",)),
    )

    def test_guidelines_and_tripwire_report_available(self):
        cookie = self._authenticated_cookie()
        resp = self._get("/api/status", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))

        self.assertTrue(payload["guidelines"]["available"])
        self.assertFalse(payload["guidelines"]["initialized"])
        self.assertEqual(
            payload["guidelines"]["default_path"],
            "starter_kit/project_guidelines/COMPILED-GUIDELINES.md",
        )

        self.assertTrue(payload["tripwire"]["available"])
        self.assertFalse(payload["tripwire"]["initialized"])
        self.assertEqual(payload["tripwire"]["entries"], 0)


class TestApiPicker(WizardServerTestCase):
    def test_no_cookie_is_401(self):
        resp = self._get("/api/picker")
        self.assertEqual(resp.status, 401)

    def test_root_listing_over_http(self):
        cookie = self._authenticated_cookie()
        resp = self._get("/api/picker?path=.", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["rel_path"], ".")
        self.assertIsNone(payload["parent_rel_path"])
        names = {e["name"] for e in payload["entries"]}
        self.assertIn("contexts", names)

    def test_containment_violation_is_400(self):
        cookie = self._authenticated_cookie()
        resp = self._get("/api/picker?path=../escaped", cookie=cookie)
        self.assertEqual(resp.status, 400)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn("error", payload)


class TestStaticAssets(WizardServerTestCase):
    """Static assets are deliberately not session-gated (see wizard_server.py's own
    _handle_static docstring) - no cookie is passed in any of these."""

    def test_wizard_css_is_served(self):
        resp = self._get("/static/wizard.css")
        self.assertEqual(resp.status, 200)
        self.assertIn("text/css", resp.headers.get("Content-Type"))

    def test_wizard_js_is_served(self):
        resp = self._get("/static/wizard.js")
        self.assertEqual(resp.status, 200)
        self.assertIn("javascript", resp.headers.get("Content-Type"))

    def test_unknown_static_asset_is_404(self):
        resp = self._get("/static/does-not-exist.txt")
        self.assertEqual(resp.status, 404)


# --------------------------------------------------------------------------
# D24 Phase 1 write path: GET /api/decisions, POST /api/stage, POST /api/apply
# --------------------------------------------------------------------------

WHAT_L2_TITLE = "What-L2 - project's own requirements/spec docs"
HOW_L2_TITLE = "How-L2 - this project's own compiled conventions"

# A single PENDING decision line - the base fixture every write-path test
# starts from. repo_root/context-layout-discovery.md, matching
# LayoutSource.discovery_artifact_path's own placement for a repo with no
# workspace_root set (the base _make_valid_target_repo fixture has none).
SINGLE_DECISION_ARTIFACT = f"""# Context Layout Discovery - test-repo

## {WHAT_L2_TITLE}
**Status:** enabled by default.

    decision: PENDING   # CONFIRM: docs/reqs/ | CUSTOM: <path> | SKIP

## {HOW_L2_TITLE}
**Status:** enabled by default.

    decision: PENDING   # CONFIRM: org/ | CUSTOM: <path> | SKIP
"""


def _write_discovery_artifact(root: Path, content: str = SINGLE_DECISION_ARTIFACT) -> Path:
    path = root / "context-layout-discovery.md"
    path.write_text(content, encoding="utf-8")
    return path


class TestApiDecisions(WizardServerTestCase):
    def test_no_cookie_is_401(self):
        resp = self._get("/api/decisions")
        self.assertEqual(resp.status, 401)

    def test_no_artifact_yet_returns_empty_fields(self):
        cookie = self._authenticated_cookie()
        resp = self._get("/api/decisions", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIsNone(payload["artifact_hash"])
        self.assertEqual(payload["fields"], [])

    def test_reports_pending_fields_with_allowed_verbs(self):
        _write_discovery_artifact(self.repo_root)
        cookie = self._authenticated_cookie()
        resp = self._get("/api/decisions", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIsNotNone(payload["artifact_hash"])
        self.assertEqual(len(payload["fields"]), 2)
        what_field = next(f for f in payload["fields"] if f["section_title"] == WHAT_L2_TITLE)
        self.assertEqual(what_field["state"], "pending")
        self.assertEqual(what_field["field_key"], "decision")
        self.assertEqual(set(what_field["allowed_verbs"]), {"CONFIRM", "CUSTOM", "SKIP"})


class TestStageRoute(WizardServerTestCase):
    def test_no_cookie_is_401(self):
        resp = self._post_json("/api/stage", {})
        self.assertEqual(resp.status, 401)

    def test_missing_csrf_header_is_403(self):
        _write_discovery_artifact(self.repo_root)
        cookie = self._authenticated_cookie()
        resp = self._post_json(
            "/api/stage",
            {"section_title": WHAT_L2_TITLE, "field_key": "decision", "verb": "CONFIRM"},
            cookie=cookie,
        )
        self.assertEqual(resp.status, 403)

    def test_wrong_csrf_header_is_403(self):
        _write_discovery_artifact(self.repo_root)
        cookie, _real_csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/stage",
            {"section_title": WHAT_L2_TITLE, "field_key": "decision", "verb": "CONFIRM"},
            cookie=cookie,
            csrf="not-the-real-nonce",
        )
        self.assertEqual(resp.status, 403)

    def test_missing_required_field_is_400(self):
        _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()
        resp = self._post_json("/api/stage", {"section_title": WHAT_L2_TITLE}, cookie=cookie, csrf=csrf)
        self.assertEqual(resp.status, 400)

    def test_custom_arg_escaping_root_is_400_and_does_not_write(self):
        artifact_path = _write_discovery_artifact(self.repo_root)
        before = artifact_path.read_text(encoding="utf-8")
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/stage",
            {
                "section_title": WHAT_L2_TITLE,
                "field_key": "decision",
                "verb": "CUSTOM",
                "arg": "../escape/",
            },
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 400)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn("error", payload)
        self.assertEqual(artifact_path.read_text(encoding="utf-8"), before)

    def test_successful_stage_persists_and_is_visible_via_decisions(self):
        _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/stage",
            {"section_title": WHAT_L2_TITLE, "field_key": "decision", "verb": "CONFIRM"},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(payload["staged"])
        self.assertIsNotNone(payload["artifact_hash"])

        decisions = json.loads(self._get("/api/decisions", cookie=cookie).read().decode("utf-8"))
        what_field = next(f for f in decisions["fields"] if f["section_title"] == WHAT_L2_TITLE)
        self.assertEqual(what_field["state"], "staged")
        self.assertEqual(what_field["raw_value"].strip(), "CONFIRM: docs/reqs/")
        self.assertEqual(decisions["artifact_hash"], payload["artifact_hash"])


class TestApplyRoute(WizardServerTestCase):
    def test_no_cookie_is_401(self):
        resp = self._post_json("/api/apply", {})
        self.assertEqual(resp.status, 401)

    def test_missing_csrf_header_is_403(self):
        _write_discovery_artifact(self.repo_root)
        cookie = self._authenticated_cookie()
        resp = self._post_json("/api/apply", {}, cookie=cookie)
        self.assertEqual(resp.status, 403)

    def test_stale_artifact_hash_is_409(self):
        _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()
        self._post_json(
            "/api/stage",
            {"section_title": WHAT_L2_TITLE, "field_key": "decision", "verb": "SKIP"},
            cookie=cookie, csrf=csrf,
        )
        resp = self._post_json(
            "/api/apply", {"loaded_artifact_hash": "not-the-real-hash"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 409)
        self.assertFalse((self.repo_root / "context-config.yaml").exists())

    def test_still_pending_field_is_400(self):
        _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()
        decisions = json.loads(self._get("/api/decisions", cookie=cookie).read().decode("utf-8"))
        resp = self._post_json(
            "/api/apply",
            {"loaded_artifact_hash": decisions["artifact_hash"]},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 400)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn("messages", payload)
        self.assertFalse((self.repo_root / "context-config.yaml").exists())

    def test_full_stage_then_apply_round_trip_writes_config(self):
        _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()

        for section_title, field_key, verb in (
            (WHAT_L2_TITLE, "decision", "CONFIRM"),
            (HOW_L2_TITLE, "decision", "SKIP"),
        ):
            stage_resp = self._post_json(
                "/api/stage",
                {"section_title": section_title, "field_key": field_key, "verb": verb},
                cookie=cookie, csrf=csrf,
            )
            self.assertEqual(stage_resp.status, 200)

        decisions = json.loads(self._get("/api/decisions", cookie=cookie).read().decode("utf-8"))
        apply_resp = self._post_json(
            "/api/apply",
            {"loaded_artifact_hash": decisions["artifact_hash"]},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(apply_resp.status, 200)
        result = json.loads(apply_resp.read().decode("utf-8"))
        self.assertTrue(result["config_changed"])
        self.assertFalse(result["idempotent"])

        config_text = (self.repo_root / "context-config.yaml").read_text(encoding="utf-8")
        self.assertIn("docs/reqs/", config_text)

        # Re-fetching /api/decisions must now show the committed field as
        # confirmed, and /api/status must reflect the newly-written path -
        # the write path's whole point is that these two read routes pick up
        # the change on the very next read, not a stale snapshot.
        after = json.loads(self._get("/api/decisions", cookie=cookie).read().decode("utf-8"))
        what_field = next(f for f in after["fields"] if f["section_title"] == WHAT_L2_TITLE)
        self.assertEqual(what_field["state"], "confirmed")

        status = json.loads(self._get("/api/status", cookie=cookie).read().decode("utf-8"))
        self.assertEqual([p["path"] for p in status["what"]["paths"]], ["docs/reqs/"])

    def test_double_apply_after_commit_is_idempotent_not_error(self):
        _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()
        for section_title, field_key, verb in (
            (WHAT_L2_TITLE, "decision", "CONFIRM"),
            (HOW_L2_TITLE, "decision", "SKIP"),
        ):
            self._post_json(
                "/api/stage",
                {"section_title": section_title, "field_key": field_key, "verb": verb},
                cookie=cookie, csrf=csrf,
            )
        decisions = json.loads(self._get("/api/decisions", cookie=cookie).read().decode("utf-8"))
        first = self._post_json(
            "/api/apply", {"loaded_artifact_hash": decisions["artifact_hash"]}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(first.status, 200)
        first_result = json.loads(first.read().decode("utf-8"))

        second = self._post_json(
            "/api/apply",
            {"loaded_artifact_hash": first_result["artifact_hash_after"]},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(second.status, 200)
        second_result = json.loads(second.read().decode("utf-8"))
        self.assertFalse(second_result["config_changed"])
        self.assertTrue(second_result["idempotent"])


# --------------------------------------------------------------------------
# D24 Phase 2 (§18.14): GET /api/state, POST /api/discover
# --------------------------------------------------------------------------


class TestApiState(WizardServerTestCase):
    """GET /api/state - the four-state onboarding router (Section A). One fixture per
    state, each built on top of the same base repo WizardServerTestCase already sets
    up (ult-repo-layout installed, validates clean, no discovery artifact yet - see
    _make_valid_target_repo)."""

    def test_no_cookie_is_401(self):
        resp = self._get("/api/state")
        self.assertEqual(resp.status, 401)

    def test_needs_discover_when_no_artifact_yet(self):
        cookie = self._authenticated_cookie()
        resp = self._get("/api/state", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["state"], "needs_discover")
        self.assertTrue(payload["validate_ok"])
        self.assertFalse(payload["discovery_artifact_exists"])
        # The base fixture's own single marker (contexts/.layout-slots.yaml, see
        # _make_valid_target_repo) is a real D20 marker for context_packages -
        # d20_initialized must be True here even while D23 state is needs_discover,
        # proving the two axes are independent (same proof as
        # test_wizard_onboarding_state.py's own d20_initialized tests, now over real
        # HTTP).
        self.assertTrue(payload["d20_initialized"])

    def test_layout_broken_when_markers_collide(self):
        # A second .layout-slots.yaml marker for the same slot at a different
        # location - validate_layout.validate's own bijectivity check (S15) FAILs on
        # this, independent of anything D23-related (same trigger as
        # test_wizard_onboarding_state.py's _make_broken_repo).
        _write(
            self.repo_root / "contexts2" / ".layout-slots.yaml",
            "slots:\n  - slot: context_packages\n    kind: directory\n"
            "    schema_version: 1\n",
        )
        cookie = self._authenticated_cookie()
        resp = self._get("/api/state", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["state"], "layout_broken")
        self.assertFalse(payload["validate_ok"])
        self.assertTrue(any(f.startswith("FAIL") for f in payload["validate_failures"]))

    def test_decisions_pending_when_artifact_has_pending_field(self):
        _write_discovery_artifact(self.repo_root)
        cookie = self._authenticated_cookie()
        resp = self._get("/api/state", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["state"], "decisions_pending")
        self.assertTrue(payload["discovery_artifact_exists"])
        self.assertEqual(payload["decision_counts"]["pending"], 2)

    def test_steady_state_when_all_fields_confirmed(self):
        _write_discovery_artifact(
            self.repo_root,
            content=(
                f"# Context Layout Discovery - test-repo\n\n"
                f"## {WHAT_L2_TITLE}\n**Status:** enabled by default.\n\n"
                "    decision: CONFIRM: docs/reqs/   # CONFIRMED 2026-01-01\n"
            ),
        )
        cookie = self._authenticated_cookie()
        resp = self._get("/api/state", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["state"], "steady_state")
        self.assertEqual(payload["decision_counts"]["confirmed"], 1)


class TestDiscoverRoute(WizardServerTestCase):
    """POST /api/discover - UI-driven (re-)discover (Section B). Same 3-gate mutating
    dispatch as /api/stage//api/apply, mirroring TestStageRoute's/TestApplyRoute's own
    401/403/409/200 coverage."""

    def test_no_cookie_is_401(self):
        resp = self._post_json("/api/discover", {})
        self.assertEqual(resp.status, 401)

    def test_missing_csrf_header_is_403(self):
        cookie = self._authenticated_cookie()
        resp = self._post_json("/api/discover", {}, cookie=cookie)
        self.assertEqual(resp.status, 403)

    def test_first_run_with_no_prior_artifact_succeeds(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/discover", {"loaded_artifact_hash": None}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIsNotNone(payload["artifact_hash_after"])
        self.assertEqual(payload["discarded_staged_sections"], [])
        self.assertTrue((self.repo_root / "context-layout-discovery.md").exists())

    def test_stale_artifact_hash_is_409(self):
        _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/discover",
            {"loaded_artifact_hash": "not-the-real-hash"},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 409)

    def test_staged_field_blocks_without_force(self):
        artifact_path = _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()
        stage_resp = self._post_json(
            "/api/stage",
            {"section_title": WHAT_L2_TITLE, "field_key": "decision", "verb": "CONFIRM"},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(stage_resp.status, 200)
        staged_hash = json.loads(stage_resp.read().decode("utf-8"))["artifact_hash"]

        resp = self._post_json(
            "/api/discover",
            {"loaded_artifact_hash": staged_hash},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 409)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn(WHAT_L2_TITLE, payload["at_risk_sections"])
        # Refused before touching the artifact - the staged CONFIRM survives intact.
        self.assertIn("CONFIRM: docs/reqs/", artifact_path.read_text(encoding="utf-8"))

    def test_force_true_proceeds_and_reports_discarded_sections(self):
        _write_discovery_artifact(self.repo_root)
        cookie, csrf = self._authenticated_session()
        stage_resp = self._post_json(
            "/api/stage",
            {"section_title": WHAT_L2_TITLE, "field_key": "decision", "verb": "CONFIRM"},
            cookie=cookie, csrf=csrf,
        )
        staged_hash = json.loads(stage_resp.read().decode("utf-8"))["artifact_hash"]

        resp = self._post_json(
            "/api/discover",
            {"loaded_artifact_hash": staged_hash, "force": True},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn(WHAT_L2_TITLE, payload["discarded_staged_sections"])
        self.assertIsNotNone(payload["artifact_hash_after"])


# --------------------------------------------------------------------------
# Journey 3 Phase A: GET /api/retrofit/inventory
# --------------------------------------------------------------------------

RETROFIT_FIXTURE_SKILL_MD = """---
name: widget-reviewer
description: Use this skill to review code changes and write tests before merging.
---

# Widget Reviewer

Reviews code changes.
"""


class TestApiRetrofitInventory(WizardServerTestCase):
    """Route-wiring only (session-gate + happy path + error mapping) - the
    describe()/recommend() field-level behavior itself is covered directly
    against wizard_retrofit_inventory.build_inventory() in
    test_wizard_retrofit_inventory.py, per this file's own module docstring on
    only needing the real socket for wiring, not per-module logic."""

    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def test_no_cookie_is_401(self):
        resp = self._get("/api/retrofit/inventory")
        self.assertEqual(resp.status, 401)

    def test_default_target_inventories_the_repo_root(self):
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md", RETROFIT_FIXTURE_SKILL_MD
        )
        cookie = self._authenticated_cookie()
        resp = self._get("/api/retrofit/inventory", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["target_rel_path"], ".")
        unit_ids = {u["unit_id"] for u in payload["units"]}
        self.assertIn("widget-reviewer", unit_ids)
        widget = next(u for u in payload["units"] if u["unit_id"] == "widget-reviewer")
        self.assertTrue(widget["code_related"])
        self.assertTrue(widget["task_related"])

    def test_explicit_target_query_param(self):
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md", RETROFIT_FIXTURE_SKILL_MD
        )
        cookie = self._authenticated_cookie()
        resp = self._get(
            "/api/retrofit/inventory?target=widget-reviewer", cookie=cookie
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["target_rel_path"], "widget-reviewer")
        # With "widget-reviewer" itself as the walk root, its own SKILL.md falls
        # through to the flat-file heuristic (skill-dir only fires below the
        # root) - see test_wizard_retrofit_inventory.py for the direct-call
        # coverage of this same cep_retrofit.py behavior.
        self.assertEqual(len(payload["units"]), 1)
        self.assertEqual(payload["units"][0]["unit_id"], "SKILL.md")

    def test_containment_violation_is_400(self):
        cookie = self._authenticated_cookie()
        resp = self._get(
            "/api/retrofit/inventory?target=../escaped", cookie=cookie
        )
        self.assertEqual(resp.status, 400)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
