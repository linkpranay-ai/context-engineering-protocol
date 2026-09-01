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
import wizard_docs  # noqa: E402
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
        # docs/requirements/ resolves but has never been created on disk in this
        # fixture (see the stub-card comment below) - the file-listing fields ride
        # along on the same BoxPath and must reflect that: resolved, zero files.
        what_l2 = payload["what"]["paths"][0]
        self.assertEqual(what_l2["files"], [])
        self.assertEqual(what_l2["total_file_count"], 0)
        self.assertFalse(what_l2["truncated"])

        self.assertFalse(payload["guidelines"]["available"])
        self.assertFalse(payload["tripwire"]["available"])

        # Phase 2 (§18.14 Section C): docs/requirements/ resolves but is empty in
        # this fixture, and Guidelines isn't installed at all here (available=False,
        # so guidelines_card's own initialized=False path never even applies) - the
        # What box's stub card is the one that should surface. Trip-wire is also
        # unavailable here (owning skill not installed), so tripwire_card's own
        # available=False branch must suppress its card the same way.
        stub_titles = [c["box_title"] for c in payload["stub_cards"]]
        self.assertIn("What", stub_titles)
        self.assertNotIn("Trip-wire", stub_titles)


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

        # Regression test for the report finding this fixes (Trip-wire onboarding
        # dead end): available + uninitialized + 0 entries must surface a stub
        # card naming ult-institutional-memory-distill, same as Guidelines'
        # uninitialized case does for compiling-project-guidelines.
        stub_titles = [c["box_title"] for c in payload["stub_cards"]]
        self.assertIn("Trip-wire", stub_titles)
        tripwire_stub = next(
            c for c in payload["stub_cards"] if c["box_title"] == "Trip-wire"
        )
        self.assertIn("ult-institutional-memory-distill", tripwire_stub["prompt_text"])


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


class TestApiDocAsset(WizardServerTestCase):
    """Regression tests proving _handle_api_doc_asset is gated on the exact
    same wizard_docs.docs_root() trust check list_docs()/_handle_api_docs
    already require - not a second, independently-maintained check that could
    silently drift looser than the first and let this route serve a file out
    of a root the docs list itself would have refused to trust. docs_root()
    is about this *skill's own* install location, not the target repo under
    test, so these monkeypatch wizard_docs._docs_dir/_self_test_root exactly
    the way TestDocsRoot in test_wizard_docs.py already does for the function
    directly - here the same fixture is driven through the real HTTP route."""

    def setUp(self):
        super().setUp()
        self._orig_docs_dir = wizard_docs._docs_dir
        self._orig_self_test_root = wizard_docs._self_test_root

    def tearDown(self):
        wizard_docs._docs_dir = self._orig_docs_dir
        wizard_docs._self_test_root = self._orig_self_test_root
        super().tearDown()

    def test_no_cookie_is_401(self):
        resp = self._get("/api/docs-assets/hero.png")
        self.assertEqual(resp.status, 401)

    def test_asset_refused_when_docs_root_unverified(self):
        # Neither location verifies: the bundled docs/ sibling doesn't exist
        # and the fallback root has no CONCEPT.md+PROTOCOL.md pair - the same
        # "not this skill's own CEP bundle" case TestBundleVerification in
        # test_wizard_docs.py covers for list_docs() directly. A real file
        # sits right where the route would look, to prove the 404 comes from
        # the trust gate and not merely from the file being absent.
        with tempfile.TemporaryDirectory() as tmp:
            missing_bundle = Path(tmp) / "docs"
            unrelated = Path(tmp) / "unrelated"
            unrelated.mkdir()
            (unrelated / "hero.png").write_bytes(b"not actually verified")
            wizard_docs._docs_dir = lambda: missing_bundle
            wizard_docs._self_test_root = lambda: unrelated
            cookie = self._authenticated_cookie()
            resp = self._get("/api/docs-assets/hero.png", cookie=cookie)
            self.assertEqual(resp.status, 404)

    def test_asset_served_when_docs_root_verified(self):
        # The permit path: once docs_root() verifies (a bundled docs/ sibling
        # is trusted outright, same as list_docs()'s own resolution order), a
        # real asset under it is served - proving the gate above is a real
        # trust check, not an always-404 regression hiding behind it.
        with tempfile.TemporaryDirectory() as tmp:
            bundled = Path(tmp) / "docs"
            bundled.mkdir()
            (bundled / "hero.png").write_bytes(b"fake-png-bytes")
            wizard_docs._docs_dir = lambda: bundled
            cookie = self._authenticated_cookie()
            resp = self._get("/api/docs-assets/hero.png", cookie=cookie)
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.read(), b"fake-png-bytes")


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


class TestApiStatusWithPendingDecisions(WizardServerTestCase):
    """Regression test: a What/How stub card must not tell the user to
    scaffold content at a resolved path that a not-yet-Applied decision
    might be about to move out from under them. Same base fixture as
    TestApiStatusMinimalRepo
    (docs/requirements/ resolves but is empty on disk, so absent the gate
    the What card would surface exactly as it does there) - the only
    difference is a discovery artifact with a still-PENDING What-L2 field."""

    def test_what_card_suppressed_while_its_decision_is_pending(self):
        _write_discovery_artifact(self.repo_root, content=SINGLE_DECISION_ARTIFACT)
        cookie = self._authenticated_cookie()
        resp = self._get("/api/status", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))

        stub_titles = [c["box_title"] for c in payload["stub_cards"]]
        self.assertNotIn("What", stub_titles)

    def test_gate_is_per_box_not_whole_artifact(self):
        # What-L2 confirmed, How-L2 still PENDING - proves the gate is
        # per-box, not an all-or-nothing artifact-exists check: What's card
        # may return once its own decision lands even while How's stays
        # suppressed.
        _write_discovery_artifact(
            self.repo_root,
            content=(
                f"# Context Layout Discovery - test-repo\n\n"
                f"## {WHAT_L2_TITLE}\n**Status:** enabled by default.\n\n"
                "    decision: CONFIRM: docs/reqs/   # CONFIRMED 2026-01-01\n\n"
                f"## {HOW_L2_TITLE}\n**Status:** enabled by default.\n\n"
                "    decision: PENDING   # CONFIRM: org/ | CUSTOM: <path> | SKIP\n"
            ),
        )
        cookie = self._authenticated_cookie()
        resp = self._get("/api/status", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))

        stub_titles = [c["box_title"] for c in payload["stub_cards"]]
        self.assertIn("What", stub_titles)
        self.assertNotIn("How", stub_titles)

    def test_rediscovery_section_title_still_marks_its_layer_pending(self):
        # Regression test: the old `section_title.startswith("What"/"How")`
        # check missed a re-issued section, since discover_layers.py titles
        # those "Re-discovery - <canonical title> - <date>", which starts
        # with "Re-discovery", not "What"/"How". resolve_section_layer()
        # must still resolve this to the "what" layer so the What card stays
        # suppressed while the re-discovered decision is unresolved.
        _write_discovery_artifact(
            self.repo_root,
            content=(
                f"# Context Layout Discovery - test-repo\n\n"
                f"## Re-discovery - {WHAT_L2_TITLE} - 2026-01-01\n"
                "**Status:** enabled by default.\n\n"
                "    decision: PENDING   # CONFIRM: docs/reqs/ | CUSTOM: <path> | SKIP\n\n"
                f"## {HOW_L2_TITLE}\n**Status:** enabled by default.\n\n"
                "    decision: CONFIRM: org/   # CONFIRMED 2026-01-01\n"
            ),
        )
        cookie = self._authenticated_cookie()
        resp = self._get("/api/status", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))

        stub_titles = [c["box_title"] for c in payload["stub_cards"]]
        self.assertNotIn("What", stub_titles)
        self.assertIn("How", stub_titles)

    def test_collision_section_title_marks_both_layers_pending(self):
        # Regression test: COLLISION_TITLE ("Cross-layer path collisions
        # (S30)") starts with neither "What" nor "How", so the old check
        # treated a still-unresolved collision as pending for *neither*
        # layer - a false-negative gap the review found by reasoning.
        # resolve_section_layer() maps it to both layers, so a pending
        # collision decision suppresses both the What and How cards.
        _write_discovery_artifact(
            self.repo_root,
            content=(
                f"# Context Layout Discovery - test-repo\n\n"
                f"## {WHAT_L2_TITLE}\n**Status:** enabled by default.\n\n"
                "    decision: CONFIRM: docs/reqs/   # CONFIRMED 2026-01-01\n\n"
                f"## {HOW_L2_TITLE}\n**Status:** enabled by default.\n\n"
                "    decision: CONFIRM: org/   # CONFIRMED 2026-01-01\n\n"
                "## Cross-layer path collisions (S30)\n\n"
                "    collision_decision: PENDING   # ACKNOWLEDGE | CUSTOM: <layer> -> <new path>\n"
            ),
        )
        cookie = self._authenticated_cookie()
        resp = self._get("/api/status", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))

        stub_titles = [c["box_title"] for c in payload["stub_cards"]]
        self.assertNotIn("What", stub_titles)
        self.assertNotIn("How", stub_titles)


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


class TestApiInitRoutes(WizardServerTestCase):
    """POST /api/init/preview, POST /api/init - the first-run
    `layout.workspace_root` namespacing offer (the 2026-08-31 Round-2 evaluation's finding on first-run workspace-root namespacing during init). The base fixture (_make_valid_target_repo) ships a real D20
    marker, which is not the shape this offer targets - setUp removes it to get a
    genuinely un-initialized repo, matching
    test_wizard_onboarding_state.py's own eligible-vs-not split."""

    def setUp(self):
        super().setUp()
        (self.repo_root / "contexts" / ".layout-slots.yaml").unlink()
        # run_init requires context-config.yaml to already exist (it only ever
        # writes the project_layout section into it, never the rest of the
        # file) - the base fixture doesn't create one, since neither
        # validate() nor discover_layers.py needs it to exist.
        _write(
            self.repo_root / "context-config.yaml",
            "cache:\n  product_context_path: contexts/\n",
        )

    def test_no_cookie_is_401_preview(self):
        resp = self._post_json("/api/init/preview", {})
        self.assertEqual(resp.status, 401)

    def test_no_cookie_is_401_init(self):
        resp = self._post_json("/api/init", {})
        self.assertEqual(resp.status, 401)

    def test_missing_csrf_header_is_403(self):
        cookie = self._authenticated_cookie()
        resp = self._post_json("/api/init/preview", {}, cookie=cookie)
        self.assertEqual(resp.status, 403)

    def test_preview_with_workspace_root_writes_nothing(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/init/preview", {"workspace_root": ".cep/"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(any("Would" in m for m in payload["messages"]))
        self.assertFalse((self.repo_root / ".cep").exists())

    def test_preview_invalid_workspace_root_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/init/preview", {"workspace_root": "."}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_init_actually_writes_and_state_reflects_it(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/init", {"workspace_root": ".cep/"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(
            any("Scaffolded" in m or "Registered" in m for m in payload["messages"])
        )
        self.assertTrue((self.repo_root / ".cep" / "contexts").is_dir())

        state_resp = self._get("/api/state", cookie=cookie)
        state_payload = json.loads(state_resp.read().decode("utf-8"))
        self.assertEqual(state_payload["workspace_root_current"], ".cep")
        self.assertFalse(state_payload["workspace_root_offer_eligible"])

    def test_second_init_call_is_400(self):
        cookie, csrf = self._authenticated_session()
        self._post_json(
            "/api/init", {"workspace_root": ".cep/"}, cookie=cookie, csrf=csrf
        )
        resp = self._post_json(
            "/api/init", {"workspace_root": "docs/"}, cookie=cookie, csrf=csrf
        )
        self.assertEqual(resp.status, 400)

    def test_preview_absolute_workspace_root_is_400_writes_nothing_outside_repo(self):
        # An absolute workspace_root must be refused by the containment guard
        # before it ever reaches wizard_init/validate_layout - regression
        # coverage for the gap where such a value could reach this
        # HTTP-exposed route unchecked.
        cookie, csrf = self._authenticated_session()
        with tempfile.TemporaryDirectory() as outside:
            outside_marker = str(Path(outside) / "definitely-not-created")
            resp = self._post_json(
                "/api/init/preview",
                {"workspace_root": outside_marker},
                cookie=cookie,
                csrf=csrf,
            )
            self.assertEqual(resp.status, 400)
            self.assertFalse(Path(outside_marker).exists())

    def test_init_absolute_workspace_root_is_400_writes_nothing_outside_repo(self):
        config_path = self.repo_root / "context-config.yaml"
        before = config_path.read_text(encoding="utf-8") if config_path.exists() else None
        cookie, csrf = self._authenticated_session()
        with tempfile.TemporaryDirectory() as outside:
            outside_marker = str(Path(outside) / "definitely-not-created")
            resp = self._post_json(
                "/api/init",
                {"workspace_root": outside_marker},
                cookie=cookie,
                csrf=csrf,
            )
            self.assertEqual(resp.status, 400)
            self.assertFalse(Path(outside_marker).exists())
            # Nothing should have been scaffolded inside the repo either - the
            # guard must fire before any write, not just before this
            # particular outside path - so the config is byte-for-byte
            # unchanged (or still absent, if it was absent before).
            after = config_path.read_text(encoding="utf-8") if config_path.exists() else None
            self.assertEqual(before, after)


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

    def test_tier_counts_are_present_and_non_empty_for_a_mixed_target(self):
        # tier_counts must actually reach the frontend non-empty for a
        # target that has both a canonical and a supplementary unit - the
        # data the wizard.js header line / per-unit badges read from. The
        # base fixture (_make_valid_target_repo plus this class's own
        # EXTRA_SKILLS) already contributes its own canonical units, so this
        # only asserts on what widget-reviewer/widget-reviewer.md add, not
        # on the repo-root inventory's total.
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md", RETROFIT_FIXTURE_SKILL_MD
        )
        _write(self.repo_root / "widget-reviewer.md", "Stray duplicate doc.")
        cookie = self._authenticated_cookie()
        resp = self._get("/api/retrofit/inventory", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        tier_counts = payload["tier_counts"]
        self.assertGreaterEqual(tier_counts.get("canonical", 0), 1)
        self.assertEqual(tier_counts.get("supplementary", 0), 1)
        flat = next(u for u in payload["units"] if u["unit_id"] == "widget-reviewer.md")
        self.assertEqual(flat["tier"], "supplementary")
        self.assertIn("duplicates widget-reviewer", flat["note"])

    def test_manifest_owned_paths_reach_the_frontend_as_excluded_not_silence(self):
        # A target carrying its own .cep-install.json has those owned paths
        # pruned from the walk. The pruned paths must still reach the
        # frontend, so the human reviewing the inventory can tell "CEP
        # already owns this" apart from "the scan found nothing there".
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md", RETROFIT_FIXTURE_SKILL_MD
        )
        _write(
            self.repo_root / ".cep-install.json",
            json.dumps({
                "schema_version": 1,
                "runtime": ["claude", "copilot"],
                "mode": "full",
                "only_skills": None,
                "owned_paths": [".github/skills"],
                "merged_paths": [],
                "installed_at": "2026-01-01T00:00:00Z",
            }),
        )
        cookie = self._authenticated_cookie()
        resp = self._get("/api/retrofit/inventory", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn(".github/skills", payload["excluded_owned_paths"])
        unit_ids = {u["unit_id"] for u in payload["units"]}
        self.assertIn("widget-reviewer", unit_ids)
        self.assertFalse(any(u.startswith(".github/skills") for u in unit_ids))


class TestRetrofitInventoryReviewGateMarkup(WizardServerTestCase):
    """A lightweight static-source presence check, not a full DOM
    render - this wizard's retrofit-inventory rendering is entirely
    client-side JS (see renderRetrofitUnitRow/renderRetrofitInventory in
    wizard.js), so there is no server-rendered markup a Python test could
    inspect directly. What this can and does check: the retrofit-inventory
    affordances this wizard promises - the tier badge, the review-gate
    checkbox, the excluded-paths list - are actually present in the static
    sources the browser receives, not just described in a commit message."""

    def test_index_html_has_the_review_gate_checkbox(self):
        # index.html is only ever served templated through the session-gated
        # "/" route (_handle_index), never under /static/ - STATIC_ASSETS is
        # a closed set that deliberately excludes it (see wizard_server.py's
        # own comment on that dict).
        cookie = self._authenticated_cookie()
        resp = self._get("/", cookie=cookie)
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn('id="retrofit-inventory-reviewed"', body)
        self.assertIn('id="retrofit-tier-summary"', body)

    def test_wizard_js_renders_the_tier_badge_and_enforces_the_review_gate(self):
        resp = self._get("/static/wizard.js")
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn("retrofit-tier-badge", body)
        self.assertIn("retrofit-inventory-reviewed", body)
        self.assertIn("applyRetrofitReviewGate", body)

    def test_excluded_owned_paths_have_a_list_element_and_a_renderer(self):
        # The endpoint-level coverage above proves excluded_owned_paths
        # reaches the browser; this proves something in the browser reads it.
        cookie = self._authenticated_cookie()
        index = self._get("/", cookie=cookie).read().decode("utf-8")
        self.assertIn('id="retrofit-excluded-owned-paths"', index)
        js = self._get("/static/wizard.js").read().decode("utf-8")
        self.assertIn("retrofit-excluded-owned-paths", js)
        self.assertIn("excluded_owned_paths", js)

    def test_retrofit_search_filter_and_directory_summary_affordances_are_present(self):
        # the 2026-08-31 Round-2 evaluation's finding on retrofit-inventory grouping and filtering by source directory: same lightweight
        # static-source presence check as the other tests in this class -
        # confirms the search/filter/grouping markup and its JS wiring
        # actually reach the browser, not just backend field additions to
        # wizard_retrofit_inventory.py (covered separately in
        # test_wizard_retrofit_inventory.py).
        cookie = self._authenticated_cookie()
        index = self._get("/", cookie=cookie).read().decode("utf-8")
        self.assertIn('id="retrofit-directory-summary"', index)
        self.assertIn('id="retrofit-filter-search"', index)
        self.assertIn('id="retrofit-filter-canonical-only"', index)
        self.assertIn('id="retrofit-filter-code"', index)
        self.assertIn('id="retrofit-filter-task"', index)
        self.assertIn('id="retrofit-review-gate-text"', index)

        js = self._get("/static/wizard.js").read().decode("utf-8")
        self.assertIn("retrofitFilters", js)
        self.assertIn("applyRetrofitFilters", js)
        self.assertIn("renderRetrofitDirectorySummary", js)
        self.assertIn("directory_counts", js)
        # The review gate must be re-derivable from source_directory too,
        # not just tier/code/task - otherwise the directory chips would be
        # decorative rather than an actual filter.
        self.assertIn("source_directory", js)

    def test_retrofit_context_availability_control_is_wired_up(self):
        # the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting: the per-unit
        # context-availability <select> is built dynamically inside
        # renderRetrofitUnitRow (not static index.html markup), so this
        # checks the JS source for the control and its payload wiring
        # rather than the served index page.
        js = self._get("/static/wizard.js").read().decode("utf-8")
        self.assertIn("retrofit-context-availability", js)
        self.assertIn("CONTEXT_AVAILABILITY_POLICIES", js)
        self.assertIn("context_availability: availabilitySelect.value", js)


class TestApiRetrofitState(WizardServerTestCase):
    """Route-wiring only for GET /api/retrofit/state - the state file's own
    load/save/mutation behavior is covered directly in
    test_wizard_retrofit_state.py."""

    def test_no_cookie_is_401(self):
        resp = self._get("/api/retrofit/state")
        self.assertEqual(resp.status, 401)

    def test_no_staged_units_returns_an_empty_skeleton(self):
        cookie = self._authenticated_cookie()
        resp = self._get("/api/retrofit/state", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["units"], {})


class TestApiRetrofitContractLocations(WizardServerTestCase):
    def test_no_cookie_is_401(self):
        resp = self._get("/api/retrofit/contract-locations")
        self.assertEqual(resp.status, 401)

    def test_finds_a_contract_present_in_the_repo(self):
        _write(
            self.repo_root / "context-engineering" / "CONSUMING-CONTEXT-PACKAGE.md",
            "content\n",
        )
        cookie = self._authenticated_cookie()
        resp = self._get("/api/retrofit/contract-locations", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(
            payload["contract_locations"]["CONSUMING-CONTEXT-PACKAGE.md"],
            "context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
        )
        self.assertIsNone(payload["contract_locations"]["CONSUMING-CODE-GRAPH.md"])


class TestApiRetrofitSelect(WizardServerTestCase):
    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def test_no_cookie_is_401(self):
        resp = self._post_json("/api/retrofit/select", {})
        self.assertEqual(resp.status, 401)

    def test_missing_csrf_header_is_403(self):
        cookie = self._authenticated_cookie()
        resp = self._post_json(
            "/api/retrofit/select",
            {"unit_id": "widget-reviewer", "primary_file": "widget-reviewer/SKILL.md"},
            cookie=cookie,
        )
        self.assertEqual(resp.status, 403)

    def test_missing_required_field_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select", {"unit_id": "widget-reviewer"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_unknown_contract_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select",
            {
                "unit_id": "widget-reviewer",
                "primary_file": "widget-reviewer/SKILL.md",
                "contracts": ["NOT-A-REAL-CONTRACT.md"],
            },
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_containment_violation_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select",
            {"unit_id": "widget-reviewer", "primary_file": "../escaped/SKILL.md"},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_successful_select_persists_and_is_visible_via_state(self):
        _write(self.repo_root / "widget-reviewer" / "SKILL.md", RETROFIT_FIXTURE_SKILL_MD)
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select",
            {
                "unit_id": "widget-reviewer",
                "primary_file": "widget-reviewer/SKILL.md",
                "contracts": ["CONSUMING-CONTEXT-PACKAGE.md"],
                "reference_mode": "same-repo",
                "reference_args": {"CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"},
            },
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(payload["selection"]["include"])
        # the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting: not supplied -> default "ask".
        self.assertEqual(payload["selection"]["context_availability"], "ask")

        state = json.loads(self._get("/api/retrofit/state", cookie=cookie).read().decode("utf-8"))
        self.assertIn("widget-reviewer", state["units"])

    def test_unknown_context_availability_is_400(self):
        """the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting."""
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select",
            {
                "unit_id": "widget-reviewer",
                "primary_file": "widget-reviewer/SKILL.md",
                "context_availability": "sometimes",
            },
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_explicit_context_availability_is_persisted(self):
        """the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting."""
        _write(self.repo_root / "widget-reviewer" / "SKILL.md", RETROFIT_FIXTURE_SKILL_MD)
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select",
            {
                "unit_id": "widget-reviewer",
                "primary_file": "widget-reviewer/SKILL.md",
                "contracts": ["CONSUMING-CONTEXT-PACKAGE.md"],
                "reference_mode": "same-repo",
                "reference_args": {"CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"},
                "context_availability": "required",
            },
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["selection"]["context_availability"], "required")

        state = json.loads(self._get("/api/retrofit/state", cookie=cookie).read().decode("utf-8"))
        self.assertEqual(state["units"]["widget-reviewer"]["context_availability"], "required")


class TestApiRetrofitDraft(WizardServerTestCase):
    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def _select(self, cookie, csrf, **overrides):
        payload = {
            "unit_id": "widget-reviewer",
            "primary_file": "widget-reviewer/SKILL.md",
            "contracts": ["CONSUMING-CONTEXT-PACKAGE.md"],
            "reference_mode": "same-repo",
            "reference_args": {
                "CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"
            },
        }
        payload.update(overrides)
        resp = self._post_json("/api/retrofit/select", payload, cookie=cookie, csrf=csrf)
        self.assertEqual(resp.status, 200)

    def test_no_cookie_is_401(self):
        resp = self._post_json("/api/retrofit/draft", {})
        self.assertEqual(resp.status, 401)

    def test_missing_csrf_header_is_403(self):
        cookie = self._authenticated_cookie()
        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": "widget-reviewer"}, cookie=cookie,
        )
        self.assertEqual(resp.status, 403)

    def test_draft_without_a_prior_select_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": "never-selected"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_successful_draft_persists_context_and_is_visible_via_state(self):
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD + "\n## See Also\n\nOther docs.\n",
        )
        cookie, csrf = self._authenticated_session()
        self._select(cookie, csrf)

        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": "widget-reviewer"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertFalse(payload["all_satisfied"])
        self.assertIn("context-engineering/CONSUMING-CONTEXT-PACKAGE.md", payload["selection"]["draft_text"])
        self.assertEqual(payload["selection"]["insertion_point"]["method"], "see-also")

        state = json.loads(self._get("/api/retrofit/state", cookie=cookie).read().decode("utf-8"))
        entry = state["units"]["widget-reviewer"]
        self.assertIn("Other docs.", entry["context_after"] + entry["context_before"])

    def test_selected_context_availability_policy_is_rendered_into_draft_text(self):
        """the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting: the policy chosen at
        select-time must survive through to the drafted skill text, not just
        RETROFIT-STATE.json."""
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD + "\n## See Also\n\nOther docs.\n",
        )
        cookie, csrf = self._authenticated_session()
        self._select(cookie, csrf, context_availability="required")

        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": "widget-reviewer"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn(
            "Context-availability policy: `required`", payload["selection"]["draft_text"]
        )

    def test_drifted_policy_on_an_already_retrofitted_unit_is_flagged(self):
        """the 2026-08-31 Round-2 evaluation's finding on policy drift going
        undetected on already-retrofitted units: a unit whose file already
        carries a pointer drafted under the old "ask" policy, re-drafted
        after the project moves to "required", must come back flagged so
        wizard.js can render a "policy change only" label instead of
        silently reporting all_satisfied."""
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD + "\n\n"
            "If a CEP context package exists for this work, see "
            "`context-engineering/CONSUMING-CONTEXT-PACKAGE.md` for how "
            "to detect, load, and apply it before proceeding. "
            "**Context-availability policy: `ask`** — if no "
            "approved matching package is found, follow "
            "`context-engineering/CONSUMING-CONTEXT-PACKAGE.md`'s "
            "\"Context-availability policy\" callout for the `ask` "
            "branch before proceeding with the work.\n",
        )
        cookie, csrf = self._authenticated_session()
        self._select(cookie, csrf, context_availability="required")

        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": "widget-reviewer"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertFalse(payload["all_satisfied"])
        self.assertTrue(payload["selection"]["policy_drifted"])
        self.assertIn("Context-availability policy: `required`", payload["selection"]["draft_text"])
        self.assertNotIn("`ask`", payload["selection"]["draft_text"])

        state = json.loads(self._get("/api/retrofit/state", cookie=cookie).read().decode("utf-8"))
        self.assertTrue(state["units"]["widget-reviewer"]["policy_drifted"])


class TestApiRetrofitDraftOverride(WizardServerTestCase):
    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def test_no_cookie_is_401(self):
        resp = self._post_json("/api/retrofit/draft-override", {})
        self.assertEqual(resp.status, 401)

    def test_missing_csrf_header_is_403(self):
        cookie = self._authenticated_cookie()
        resp = self._post_json(
            "/api/retrofit/draft-override",
            {"unit_id": "widget-reviewer", "draft_text": "x"},
            cookie=cookie,
        )
        self.assertEqual(resp.status, 403)

    def test_override_without_a_prior_draft_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select",
            {"unit_id": "widget-reviewer", "primary_file": "widget-reviewer/SKILL.md"},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        resp = self._post_json(
            "/api/retrofit/draft-override",
            {"unit_id": "widget-reviewer", "draft_text": "human text"},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_successful_override_persists_and_is_visible_via_state(self):
        _write(self.repo_root / "widget-reviewer" / "SKILL.md", RETROFIT_FIXTURE_SKILL_MD)
        cookie, csrf = self._authenticated_session()
        self._post_json(
            "/api/retrofit/select",
            {
                "unit_id": "widget-reviewer",
                "primary_file": "widget-reviewer/SKILL.md",
                "contracts": ["CONSUMING-CONTEXT-PACKAGE.md"],
                "reference_mode": "same-repo",
                "reference_args": {
                    "CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"
                },
            },
            cookie=cookie,
            csrf=csrf,
        )
        self._post_json(
            "/api/retrofit/draft", {"unit_id": "widget-reviewer"}, cookie=cookie, csrf=csrf,
        )

        resp = self._post_json(
            "/api/retrofit/draft-override",
            {"unit_id": "widget-reviewer", "draft_text": "human-edited pointer text"},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(payload["selection"]["draft_text"], "human-edited pointer text")
        self.assertTrue(payload["selection"]["draft_overridden"])

        state = json.loads(self._get("/api/retrofit/state", cookie=cookie).read().decode("utf-8"))
        self.assertEqual(
            state["units"]["widget-reviewer"]["draft_text"], "human-edited pointer text"
        )


class TestApiRetrofitApply(WizardServerTestCase):
    """Route-wiring for POST /api/retrofit/apply - the per-unit write mechanics
    themselves are covered directly against wizard_retrofit_apply.apply_batch()
    in test_wizard_retrofit_apply.py, per this file's own module docstring on
    only needing the real socket for wiring, not per-module logic. Includes
    the plan's own explicitly-called-out full happy-path walk (inventory ->
    select -> draft -> apply) as its own test."""

    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def _walk_to_draft(self, cookie, csrf, unit_id="widget-reviewer"):
        """Runs select + draft for one unit against RETROFIT_FIXTURE_SKILL_MD
        (with a "## See Also" heading so the insertion point is deterministic),
        mirroring TestApiRetrofitDraft's own _select/draft sequence."""
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD + "\n## See Also\n\nOther docs.\n",
        )
        resp = self._post_json(
            "/api/retrofit/select",
            {
                "unit_id": unit_id,
                "primary_file": "widget-reviewer/SKILL.md",
                "contracts": ["CONSUMING-CONTEXT-PACKAGE.md"],
                "reference_mode": "same-repo",
                "reference_args": {
                    "CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"
                },
            },
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": unit_id}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)

    def test_no_cookie_is_401(self):
        resp = self._post_json("/api/retrofit/apply", {"unit_ids": ["widget-reviewer"]})
        self.assertEqual(resp.status, 401)

    def test_missing_csrf_header_is_403(self):
        cookie = self._authenticated_cookie()
        resp = self._post_json(
            "/api/retrofit/apply", {"unit_ids": ["widget-reviewer"]}, cookie=cookie,
        )
        self.assertEqual(resp.status, 403)

    def test_missing_unit_ids_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json("/api/retrofit/apply", {}, cookie=cookie, csrf=csrf)
        self.assertEqual(resp.status, 400)

    def test_empty_unit_ids_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/apply", {"unit_ids": []}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_non_list_unit_ids_is_400(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/apply", {"unit_ids": "widget-reviewer"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 400)

    def test_unknown_unit_id_is_reported_failed_not_aborting_the_batch(self):
        cookie, csrf = self._authenticated_session()
        self._walk_to_draft(cookie, csrf)
        resp = self._post_json(
            "/api/retrofit/apply",
            {"unit_ids": ["widget-reviewer", "never-selected"]},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        by_id = {r["unit_id"]: r for r in payload["results"]}
        self.assertEqual(by_id["widget-reviewer"]["status"], "applied")
        self.assertEqual(by_id["never-selected"]["status"], "failed")

    def test_full_happy_path_walk_inventory_select_draft_apply(self):
        """The plan's own explicitly-named Phase C test: inventory -> select ->
        draft -> apply against a fabricated-name fixture library, verifying the
        target file on disk actually contains the inserted contract text."""
        cookie, csrf = self._authenticated_session()

        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD + "\n## See Also\n\nOther docs.\n",
        )
        resp = self._get("/api/retrofit/inventory", cookie=cookie)
        self.assertEqual(resp.status, 200)
        inventory = json.loads(resp.read().decode("utf-8"))
        unit_ids = {u["unit_id"] for u in inventory["units"]}
        self.assertIn("widget-reviewer", unit_ids)

        self._walk_to_draft(cookie, csrf)

        resp = self._post_json(
            "/api/retrofit/apply",
            {"unit_ids": ["widget-reviewer"]},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        result = payload["results"][0]
        self.assertEqual(result["status"], "applied")
        self.assertIn("CONSUMING-CONTEXT-PACKAGE.md", result["contracts_applied"][0])

        on_disk = (self.repo_root / "widget-reviewer" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("context-engineering/CONSUMING-CONTEXT-PACKAGE.md", on_disk)

        state = json.loads(self._get("/api/retrofit/state", cookie=cookie).read().decode("utf-8"))
        entry = state["units"]["widget-reviewer"]
        self.assertEqual(entry["draft_text"], "")
        self.assertIn("CONSUMING-CONTEXT-PACKAGE.md", entry["contracts_skipped_idempotent"])

    def test_reapplying_the_same_unit_after_success_is_skipped_idempotent(self):
        cookie, csrf = self._authenticated_session()
        self._walk_to_draft(cookie, csrf)

        first = self._post_json(
            "/api/retrofit/apply", {"unit_ids": ["widget-reviewer"]}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(json.loads(first.read().decode("utf-8"))["results"][0]["status"], "applied")
        on_disk_after_first = (self.repo_root / "widget-reviewer" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        second = self._post_json(
            "/api/retrofit/apply", {"unit_ids": ["widget-reviewer"]}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(second.status, 200)
        result = json.loads(second.read().decode("utf-8"))["results"][0]
        self.assertEqual(result["status"], "skipped_idempotent")

        on_disk_after_second = (self.repo_root / "widget-reviewer" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(on_disk_after_first, on_disk_after_second)


# --------------------------------------------------------------------------
# the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment: external retrofit-target routes.
# Route-wiring only - resolve_external_target()'s own validation-failure
# modes are covered directly in test_wizard_containment.py, and
# build_inventory()/build_draft()/apply_unit()'s external-root behavior in
# their own test_wizard_retrofit_*.py files. What only a real bound socket
# can prove: the /api/picker, /api/retrofit/inventory,
# /api/retrofit/select, /api/retrofit/draft, and /api/retrofit/apply
# handlers actually thread `external_root`/`target_root` through to those
# functions, re-validate rather than trust a persisted value, and isolate a
# per-unit apply-time revalidation failure from the rest of the batch.
# --------------------------------------------------------------------------


class TestApiPickerExternalRoot(WizardServerTestCase):
    def setUp(self):
        super().setUp()
        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)
        (self.external_root / "widget-reviewer").mkdir()

    def tearDown(self):
        self._ext_tmp.cleanup()
        super().tearDown()

    def test_external_root_browses_outside_repo_root(self):
        cookie = self._authenticated_cookie()
        resp = self._get(
            f"/api/picker?path=.&external_root={self.external_root}", cookie=cookie
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        names = {e["name"] for e in payload["entries"]}
        self.assertIn("widget-reviewer", names)
        # Proves this really browsed external_root, not repo_root: the base
        # fixture's own "contexts" directory (see TestApiPicker's own
        # root-listing assertion) must not appear here.
        self.assertNotIn("contexts", names)
        self.assertEqual(payload["target_root"], str(self.external_root.resolve()))

    def test_invalid_external_root_is_400_and_does_not_leak_a_listing(self):
        cookie = self._authenticated_cookie()
        resp = self._get(
            f"/api/picker?path=.&external_root={self.external_root / 'does-not-exist'}",
            cookie=cookie,
        )
        self.assertEqual(resp.status, 400)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn("error", payload)

    def test_omitted_external_root_still_browses_repo_root(self):
        """Every non-retrofit caller of this route (onboarding/decision
        pickers) never sends external_root - confirms it stays a true no-op
        for them, not just for the retrofit picker itself."""
        cookie = self._authenticated_cookie()
        resp = self._get("/api/picker?path=.", cookie=cookie)
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIsNone(payload["target_root"])


class TestApiRetrofitInventoryExternalRoot(WizardServerTestCase):
    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def setUp(self):
        super().setUp()
        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)

    def tearDown(self):
        self._ext_tmp.cleanup()
        super().tearDown()

    def test_external_root_inventories_outside_repo_root(self):
        # Deliberately NOT written under self.repo_root - if the engine
        # import strayed from ctx.repo_root this would 400 instead of
        # finding the unit (see wizard_retrofit_inventory.py's own
        # cep_retrofit-always-from-repo_root invariant).
        _write(
            self.external_root / "widget-reviewer" / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD,
        )
        cookie = self._authenticated_cookie()
        resp = self._get(
            f"/api/retrofit/inventory?external_root={self.external_root}",
            cookie=cookie,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        unit_ids = {u["unit_id"] for u in payload["units"]}
        self.assertIn("widget-reviewer", unit_ids)
        self.assertEqual(payload["target_root"], str(self.external_root.resolve()))

    def test_invalid_external_root_is_400(self):
        cookie = self._authenticated_cookie()
        resp = self._get(
            f"/api/retrofit/inventory?external_root={self.external_root / 'nope'}",
            cookie=cookie,
        )
        self.assertEqual(resp.status, 400)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn("error", payload)


class TestApiRetrofitSelectExternalRoot(WizardServerTestCase):
    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def setUp(self):
        super().setUp()
        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)
        _write(
            self.external_root / "widget-reviewer" / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD,
        )

    def tearDown(self):
        self._ext_tmp.cleanup()
        super().tearDown()

    def test_valid_target_root_is_persisted(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select",
            {
                "unit_id": "widget-reviewer",
                "primary_file": "widget-reviewer/SKILL.md",
                "target_root": str(self.external_root),
            },
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        state = json.loads(
            self._get("/api/retrofit/state", cookie=cookie).read().decode("utf-8")
        )
        self.assertEqual(
            state["units"]["widget-reviewer"]["target_root"],
            str(self.external_root.resolve()),
        )

    def test_invalid_target_root_is_400_and_not_persisted(self):
        cookie, csrf = self._authenticated_session()
        resp = self._post_json(
            "/api/retrofit/select",
            {
                "unit_id": "widget-reviewer",
                "primary_file": "widget-reviewer/SKILL.md",
                "target_root": str(self.external_root / "does-not-exist"),
            },
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 400)
        state = json.loads(
            self._get("/api/retrofit/state", cookie=cookie).read().decode("utf-8")
        )
        self.assertNotIn("widget-reviewer", state["units"])

    def test_primary_file_is_checked_against_target_root_not_repo_root(self):
        """A primary_file that only exists under repo_root, not under the
        given external target_root, must be a containment/not-found
        failure - proves the select handler's containment check really
        switched roots rather than merely recording the string."""
        _write(
            self.repo_root / "widget-reviewer" / "SKILL.md", RETROFIT_FIXTURE_SKILL_MD
        )
        empty_external = Path(tempfile.mkdtemp())
        try:
            cookie, csrf = self._authenticated_session()
            resp = self._post_json(
                "/api/retrofit/select",
                {
                    "unit_id": "widget-reviewer",
                    "primary_file": "../escaped-attempt/SKILL.md",
                    "target_root": str(empty_external),
                },
                cookie=cookie,
                csrf=csrf,
            )
            self.assertEqual(resp.status, 400)
        finally:
            shutil.rmtree(empty_external, ignore_errors=True)


class TestApiRetrofitDraftExternalRoot(WizardServerTestCase):
    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def setUp(self):
        super().setUp()
        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)
        _write(
            self.external_root / "widget-reviewer" / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD + "\n## See Also\n\nOther docs.\n",
        )

    def tearDown(self):
        self._ext_tmp.cleanup()
        super().tearDown()

    def _select(self, cookie, csrf, **overrides):
        payload = {
            "unit_id": "widget-reviewer",
            "primary_file": "widget-reviewer/SKILL.md",
            "contracts": ["CONSUMING-CONTEXT-PACKAGE.md"],
            # same-repo mode is refused for a genuinely external target - see
            # wizard_retrofit_draft.resolve_reference's own docstring.
            "reference_mode": "plugin",
            "reference_args": {
                "CONSUMING-CONTEXT-PACKAGE.md": "/context-engineering-oss:ult-cep-wizard"
            },
            "target_root": str(self.external_root),
        }
        payload.update(overrides)
        resp = self._post_json("/api/retrofit/select", payload, cookie=cookie, csrf=csrf)
        self.assertEqual(resp.status, 200)

    def test_draft_reads_the_persisted_target_root_from_select(self):
        cookie, csrf = self._authenticated_session()
        self._select(cookie, csrf)

        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": "widget-reviewer"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn(
            "/context-engineering-oss:ult-cep-wizard",
            payload["selection"]["draft_text"],
        )

    def test_same_repo_mode_against_an_external_target_is_400(self):
        """resolve_reference refuses same-repo mode outright for a genuinely
        external containment_root - confirms build_draft's refusal reaches
        the HTTP layer as a 400, not an unhandled exception."""
        cookie, csrf = self._authenticated_session()
        self._select(
            cookie, csrf,
            reference_mode="same-repo",
            reference_args={
                "CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"
            },
        )
        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": "widget-reviewer"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 400)
        payload = json.loads(resp.read().decode("utf-8"))
        self.assertIn("external", payload["error"])


class TestApiRetrofitApplyExternalRoot(WizardServerTestCase):
    """Includes the plan's own explicitly-named external-target happy-path
    walk (inventory -> select -> draft -> apply against a target outside
    repo_root), plus the per-unit apply-time revalidation-failure isolation
    case that is unique to the apply route (select/draft re-validate once
    against the whole request; apply re-validates once per unit, per
    wizard_server.py's own _handle_api_retrofit_apply docstring)."""

    EXTRA_SKILLS = (("ult-cep-retrofit", ("cep_retrofit.py",)),)

    def setUp(self):
        super().setUp()
        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)

    def tearDown(self):
        self._ext_tmp.cleanup()
        super().tearDown()

    def _walk_to_draft(self, cookie, csrf, unit_id, target_root):
        write_root = Path(target_root) if target_root is not None else self.repo_root
        _write(
            write_root / unit_id / "SKILL.md",
            RETROFIT_FIXTURE_SKILL_MD.replace("widget-reviewer", unit_id)
            + "\n## See Also\n\nOther docs.\n",
        )
        payload = {
            "unit_id": unit_id,
            "primary_file": f"{unit_id}/SKILL.md",
            "contracts": ["CONSUMING-CONTEXT-PACKAGE.md"],
            "reference_mode": "plugin",
            "reference_args": {
                "CONSUMING-CONTEXT-PACKAGE.md": "/context-engineering-oss:ult-cep-wizard"
            },
        }
        if target_root is not None:
            payload["target_root"] = str(target_root)
        resp = self._post_json("/api/retrofit/select", payload, cookie=cookie, csrf=csrf)
        self.assertEqual(resp.status, 200)
        resp = self._post_json(
            "/api/retrofit/draft", {"unit_id": unit_id}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(resp.status, 200)

    def test_full_external_target_walk_writes_under_external_root_not_repo_root(self):
        cookie, csrf = self._authenticated_session()

        resp = self._get(
            f"/api/retrofit/inventory?external_root={self.external_root}", cookie=cookie
        )
        self.assertEqual(resp.status, 200)

        self._walk_to_draft(cookie, csrf, "widget-reviewer", self.external_root)

        resp = self._post_json(
            "/api/retrofit/apply",
            {"unit_ids": ["widget-reviewer"]},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        result = json.loads(resp.read().decode("utf-8"))["results"][0]
        self.assertEqual(result["status"], "applied")

        on_disk = (self.external_root / "widget-reviewer" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("/context-engineering-oss:ult-cep-wizard", on_disk)
        self.assertFalse((self.repo_root / "widget-reviewer" / "SKILL.md").exists())

    def test_one_units_vanished_external_root_fails_only_that_unit(self):
        """The rest of the batch (an ordinary in-repo unit) must still
        apply, matching this handler's existing per-unit-failure-never-
        aborts-the-batch contract for every other kind of per-unit
        problem."""
        cookie, csrf = self._authenticated_session()

        self._walk_to_draft(cookie, csrf, "widget-reviewer", self.external_root)
        self._walk_to_draft(cookie, csrf, "second-widget", None)

        # The external root vanishes between draft and apply (e.g. an
        # unmounted drive, a deleted clone) - resolve_external_target now
        # fails where it previously succeeded at select/draft time.
        shutil.rmtree(self.external_root)

        resp = self._post_json(
            "/api/retrofit/apply",
            {"unit_ids": ["widget-reviewer", "second-widget"]},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(resp.status, 200)
        by_id = {r["unit_id"]: r for r in json.loads(resp.read().decode("utf-8"))["results"]}
        self.assertEqual(by_id["widget-reviewer"]["status"], "failed")
        self.assertEqual(by_id["second-widget"]["status"], "applied")
        on_disk = (self.repo_root / "second-widget" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("/context-engineering-oss:ult-cep-wizard", on_disk)


if __name__ == "__main__":
    unittest.main()
