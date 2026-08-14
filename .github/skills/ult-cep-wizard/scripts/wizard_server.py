#!/usr/bin/env python3
"""wizard_server.py - entry point for ult-cep-wizard (D24 §18.2/§18.2b).

Stdlib-only, deliberately: `http.server.ThreadingHTTPServer` and nothing else for
transport - no third-party import anywhere in this file or anything it imports. This
is where the project's stdlib-only stance (D24 exit criterion 5) is enforced
structurally, not just by policy.

Startup sequence, in order, matching wizard_preflight.py's own contract:
  1. Run `wizard_preflight.run_preflight()` against the target repo root. Any failure
     raises `PreflightError` before anything network-facing happens - no socket is
     opened, no bootstrap token is generated.
  2. Bind 127.0.0.1 on an OS-assigned port (port 0) - never a fixed port, so this
     server can never collide with something else already listening, and never
     accidentally binds a non-loopback interface. Bound exactly once (see
     `build_server` - constructing a throwaway socket just to learn the OS-assigned
     port, then closing it and rebinding on "the same" port, would leave a real race
     window for another process to grab that port in between).
  3. Mint the bootstrap token and print the one-time exchange URL to stdout.
  4. Serve forever (Ctrl+C / SIGINT to stop) via ThreadingHTTPServer.

Build-order step 2 wired up exactly one gated route (`GET /`, session required) plus
the auth exchange (`GET /exchange`), to prove the auth pipeline works end-to-end. The
next step (build-order step 4) added the real frontend and its three read-only JSON
routes: `GET /api/status` (the four-box view model, `wizard_boxes.build_boxes`),
`GET /api/picker` (directory browsing, `wizard_picker.list_directory`), and
`GET /api/decisions` (parsed decision-line state, `LayoutSource.read_decisions`) - all
session-gated exactly like `/`, and all GET-only. `/` serves the real static frontend
(`static/index.html` plus `static/wizard.css`/`static/wizard.js`, also session-gated).

D24 Phase 1 (this step) adds the write path's two mutating routes via `do_POST`:
`POST /api/stage` (stages a resolved verb into one PENDING decision line,
`wizard_decision_staging.stage_decision`) and `POST /api/apply` (the real commit,
`wizard_apply.apply_confirmed`). Every mutating request passes three gates in order,
mirroring `do_GET`'s own `_origin_host_ok()` check plus the two `wizard_auth.py`
mechanisms that existed since build-order step 2 but had nothing to gate until now:
Host/Origin validation (`_origin_host_ok`, now exercising its mutating-method branch
for the first time), session cookie (`_require_session`), and the CSRF nonce header
(`ctx.session_store.check_csrf` against `wizard_auth.CSRF_HEADER_NAME` - never a
cookie or query string). A request failing any gate never reaches `stage_decision`/
`apply_confirmed` at all.

D24 Phase 2 (guided brownfield onboarding, §18.14) retired `wizard_preflight.py`'s old
checks 2/3 - a broken or never-`discover`-ed repo is no longer a startup-fatal
`SystemExit`, since the server must always bind and render *something*. Consequences
here: `ctx.layout_source` is no longer constructed once in `build_server()` - a
`LayoutSourceError` (e.g. a `layout_broken` repo) would have made the whole process
un-startable, which is exactly what Phase 2 exists to stop. Every handler that needs
one now calls the new `_try_layout_source()` helper to build one fresh per request,
mirroring `_require_session()`'s own non-distinguishing-failure contract (`None` after
already sending a response - a 503 here, since a broken layout is legitimately
unavailable rather than unauthenticated/malformed). Two new routes:
`GET /api/state` (session-gated, `wizard_onboarding_state.compute_state` - the
four-state router `wizard.js` calls before deciding what to render, deliberately not
folded into `/api/status` since that route assumes a constructible `LayoutSource`) and
`POST /api/discover` (the same 3-gate mutating dispatch as `/api/stage`/`/api/apply`,
`wizard_discover.run_discover` - the real, in-process (re-)generation of
`context-layout-discovery.md`).

UI design pass adds two more read-only, session-gated routes for the top-bar
docs viewer: `GET /api/docs` (the closed set of CEP's own docs available to
render, `wizard_docs.list_docs`) and `GET /api/docs/<id>` (one doc rendered to
HTML on request, `wizard_docs.find_doc` + `wizard_markdown.render`) - both
resolve against `wizard_docs.install_root()`, not `ctx.repo_root`, since these
docs describe the CEP protocol itself, not whatever repo is being onboarded.
`_handle_api_status` also now wires in
`wizard_stub_content`'s previously-orphaned preview cards alongside the existing box
view model.
"""

from __future__ import annotations

import html
import json
import mimetypes
import sys
from dataclasses import asdict
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wizard_apply  # noqa: E402
import wizard_auth  # noqa: E402
import wizard_boxes  # noqa: E402
import wizard_containment  # noqa: E402
import wizard_content_hash  # noqa: E402
import wizard_decision_staging  # noqa: E402
import wizard_discover  # noqa: E402
import wizard_docs  # noqa: E402
import wizard_markdown  # noqa: E402
import wizard_layout_source  # noqa: E402
import wizard_onboarding_state  # noqa: E402
import wizard_originhost  # noqa: E402
import wizard_picker  # noqa: E402
import wizard_preflight  # noqa: E402
import wizard_retrofit_inventory  # noqa: E402
import wizard_stub_content  # noqa: E402

BIND_HOST = "127.0.0.1"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# path (relative to STATIC_DIR) -> Content-Type, for the small fixed set of static
# assets this server ever serves. Not a general static-file server (no directory
# listing, no arbitrary path under STATIC_DIR) - deliberately a closed set, so adding
# a new static asset means adding a line here, not widening what's servable.
STATIC_ASSETS = {
    "wizard.css": "text/css; charset=utf-8",
    "wizard.js": "application/javascript; charset=utf-8",
}


class _ServerContext:
    """Mutable holder populated right after bind (once the real OS-assigned port is
    known) but before serve_forever starts accepting connections. Each per-request
    handler instance reads from this at request time - BaseHTTPRequestHandler
    subclasses aren't instantiated until a request actually arrives, so this is safe
    without any lock: by the time the first handler instance exists, all fields are
    already set and never mutated again.

    No `layout_source` field (Phase 2, D24 §18.14) - constructing it once here would
    make a `LayoutSourceError` (e.g. a `layout_broken` repo) fatal at startup, which is
    exactly what the onboarding state machine exists to avoid. Each handler that needs
    one builds it fresh per request via `_try_layout_source()` instead."""

    def __init__(self) -> None:
        self.session_store: Optional[wizard_auth.SessionStore] = None
        self.allowlist: Optional[frozenset] = None
        self.repo_root: Optional[Path] = None


def _make_handler(ctx: _ServerContext):
    class WizardRequestHandler(BaseHTTPRequestHandler):
        server_version = "ult-cep-wizard/0.1"

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            # Quiet by default - only the startup banner and explicit error bodies
            # matter for a local single-operator tool. Overridden (not left default)
            # so a later step can add opt-in verbose logging without redesigning this.
            pass

        def _reject(self, status: HTTPStatus, message: str) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: HTTPStatus, payload: dict) -> None:
            self._send_bytes(
                status,
                json.dumps(payload).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _require_session(self) -> Optional[wizard_auth.Session]:
            """Shared gate for every route below `/exchange` - returns the live
            Session on success, or None after already sending a 401 (mirrors
            `authenticate_request`'s own non-distinguishing-failure contract, so
            callers don't need a second branch)."""
            session = ctx.session_store.authenticate_request(self._session_cookie())
            if session is None:
                self._reject(
                    HTTPStatus.UNAUTHORIZED,
                    "No valid session. Use the one-time link printed at startup.",
                )
            return session

        def _try_layout_source(self) -> Optional[wizard_layout_source.LayoutSource]:
            """Per-request `LayoutSource` construction (Phase 2) - `validate()`
            failure is no longer a startup-fatal gate, so `build_server()` no longer
            constructs this eagerly. Returns None after already sending a 503 on
            `LayoutSourceError` (mirrors `_require_session()`'s/`_read_json_body()`'s
            own non-distinguishing-failure contract - callers don't need a second
            branch). Callers reaching this are expected to have already routed past
            `layout_broken` via `/api/state` in the normal frontend flow; this is the
            defensive backstop, not the primary router."""
            try:
                return wizard_layout_source.LayoutSource(ctx.repo_root)
            except wizard_layout_source.LayoutSourceError as exc:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
                return None

        def _origin_host_ok(self) -> bool:
            return wizard_originhost.request_is_allowed(
                method=self.command,
                host_header=self.headers.get("Host"),
                origin_header=self.headers.get("Origin"),
                referer_header=self.headers.get("Referer"),
                allowlist=ctx.allowlist,
            )

        def _session_cookie(self) -> Optional[str]:
            raw = self.headers.get("Cookie")
            if not raw:
                return None
            cookie: SimpleCookie = SimpleCookie()
            cookie.load(raw)
            morsel = cookie.get(wizard_auth.SESSION_COOKIE_NAME)
            return morsel.value if morsel else None

        def do_GET(self):  # noqa: N802 - stdlib method name
            if not self._origin_host_ok():
                self._reject(HTTPStatus.FORBIDDEN, "Host/Origin validation failed.")
                return

            path = urlsplit(self.path).path

            if path == "/exchange":
                self._handle_exchange()
                return
            if path == "/":
                self._handle_index()
                return
            if path == "/api/status":
                self._handle_api_status()
                return
            if path == "/api/state":
                self._handle_api_state()
                return
            if path == "/api/picker":
                self._handle_api_picker()
                return
            if path == "/api/decisions":
                self._handle_api_decisions()
                return
            if path == "/api/retrofit/inventory":
                self._handle_api_retrofit_inventory()
                return
            if path == "/api/docs":
                self._handle_api_docs()
                return
            if path.startswith("/api/docs/"):
                self._handle_api_doc_detail(path[len("/api/docs/"):])
                return
            if path.startswith("/api/docs-assets/"):
                self._handle_api_doc_asset(path[len("/api/docs-assets/"):])
                return
            if path.startswith("/static/"):
                self._handle_static(path[len("/static/"):])
                return

            self._reject(HTTPStatus.NOT_FOUND, "Not found.")

        def do_POST(self):  # noqa: N802 - stdlib method name
            # Same Host/Origin gate as do_GET, now actually exercising its
            # mutating-method branch (wizard_originhost.MUTATING_METHODS
            # includes POST) rather than only the exempt GET/HEAD path.
            if not self._origin_host_ok():
                self._reject(HTTPStatus.FORBIDDEN, "Host/Origin validation failed.")
                return
            session = self._require_session()
            if session is None:
                return
            csrf_header = self.headers.get(wizard_auth.CSRF_HEADER_NAME)
            if not ctx.session_store.check_csrf(session, csrf_header):
                self._reject(HTTPStatus.FORBIDDEN, "CSRF check failed.")
                return

            path = urlsplit(self.path).path

            if path == "/api/stage":
                self._handle_api_stage()
                return
            if path == "/api/apply":
                self._handle_api_apply()
                return
            if path == "/api/discover":
                self._handle_api_discover()
                return

            self._reject(HTTPStatus.NOT_FOUND, "Not found.")

        def _read_json_body(self) -> Optional[dict]:
            """Returns the parsed JSON body, or None after already sending a
            400 (mirrors _require_session's own non-distinguishing-failure
            contract - callers don't need a second branch). No body at all is
            treated as `{}`, not an error - callers validate whatever keys
            they actually need themselves, same as a missing query param."""
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "malformed JSON body"})
                return None
            if not isinstance(body, dict):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "JSON body must be an object"})
                return None
            return body

        def _handle_exchange(self) -> None:
            query = urlsplit(self.path).query
            token = parse_qs(query).get("token", [""])[0]
            session = ctx.session_store.exchange_token(token)
            if session is None:
                self._reject(
                    HTTPStatus.UNAUTHORIZED,
                    "Invalid or already-used token. Restart the wizard for a fresh "
                    "one-time link.",
                )
                return

            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/")
            self.send_header(
                "Set-Cookie", ctx.session_store.session_cookie_header(session)
            )
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _handle_index(self) -> None:
            session = self._require_session()
            if session is None:
                return

            nonce = html.escape(session.csrf_nonce)
            template = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            # The CSRF nonce is embedded in the served HTML, never in a cookie (see
            # wizard_auth.py's module docstring) - injected here, not baked into the
            # static file on disk, since it's per-session, not a static asset.
            body = template.replace("{{WIZARD_CSRF_TOKEN}}", nonce).encode("utf-8")
            self._send_bytes(HTTPStatus.OK, body, "text/html; charset=utf-8")

        def _handle_static(self, asset_name: str) -> None:
            # No session gate here deliberately relaxed vs. every other route below -
            # CSS/JS carry no secrets and the index page that references them is
            # itself already session-gated, so an unauthenticated request for
            # wizard.css alone reveals nothing. STATIC_ASSETS is a closed set (not a
            # directory server) - anything not in it is 404, not a filesystem lookup.
            content_type = STATIC_ASSETS.get(asset_name)
            if content_type is None:
                self._reject(HTTPStatus.NOT_FOUND, "Not found.")
                return
            body = (STATIC_DIR / asset_name).read_bytes()
            self._send_bytes(HTTPStatus.OK, body, content_type)

        def _handle_api_status(self) -> None:
            if self._require_session() is None:
                return
            source = self._try_layout_source()
            if source is None:
                return
            view = wizard_boxes.build_boxes(source)
            payload = wizard_boxes.to_json_dict(view)

            # Phase 2 (§18.14 Section C): wire the previously-orphaned
            # wizard_stub_content preview cards in alongside the existing box view
            # model, rather than a new route - its inputs are exactly what
            # build_boxes already computed above.
            what_card = wizard_stub_content.what_how_card(
                "What", ctx.repo_root, [p.path for p in view.what.paths]
            )
            how_card = wizard_stub_content.what_how_card(
                "How", ctx.repo_root, [p.path for p in view.how.paths]
            )
            guidelines_card = wizard_stub_content.guidelines_card(
                ctx.repo_root, view.guidelines.initialized, view.guidelines.default_path
            )
            payload["stub_cards"] = [
                asdict(card)
                for card in (what_card, how_card, guidelines_card)
                if card is not None
            ]
            self._send_json(HTTPStatus.OK, payload)

        def _handle_api_state(self) -> None:
            """Phase 2 (§18.14 Section A): the four-state onboarding router
            `wizard.js` calls before deciding what to render. Deliberately separate
            from `/api/status` - that route assumes a constructible `LayoutSource`
            and would conflate two different failure surfaces with this one's
            `layout_broken` case, which is exactly the state this route exists to
            report rather than 503 on."""
            if self._require_session() is None:
                return
            state = wizard_onboarding_state.compute_state(ctx.repo_root)
            self._send_json(HTTPStatus.OK, wizard_onboarding_state.to_json_dict(state))

        def _handle_api_picker(self) -> None:
            if self._require_session() is None:
                return
            query = urlsplit(self.path).query
            rel_path = parse_qs(query).get("path", ["."])[0]
            try:
                result = wizard_picker.list_directory(ctx.repo_root, rel_path)
            except wizard_picker.PickerError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "rel_path": result.rel_path,
                    "parent_rel_path": result.parent_rel_path,
                    "entries": [
                        {"name": e.name, "rel_path": e.rel_path} for e in result.entries
                    ],
                },
            )

        def _handle_api_retrofit_inventory(self) -> None:
            """Journey 3 Phase A - read-only, same session-gate-only posture as
            `_handle_api_picker` (no CSRF/mutating gate: nothing is written).
            `target` defaults to "." (the repo root itself) so a first load with
            no query string still returns something rather than erroring."""
            if self._require_session() is None:
                return
            query = urlsplit(self.path).query
            target_rel_path = parse_qs(query).get("target", ["."])[0]
            try:
                result = wizard_retrofit_inventory.build_inventory(
                    ctx.repo_root, target_rel_path
                )
            except wizard_retrofit_inventory.RetrofitInventoryError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(
                HTTPStatus.OK, wizard_retrofit_inventory.to_json_dict(result)
            )

        def _handle_api_decisions(self) -> None:
            if self._require_session() is None:
                return
            source = self._try_layout_source()
            if source is None:
                return
            artifact_path = source.discovery_artifact_path
            fields = source.read_decisions()
            self._send_json(
                HTTPStatus.OK,
                {
                    "artifact_hash": wizard_content_hash.hash_artifact(artifact_path),
                    "fields": [
                        {
                            "section_title": f.section_title,
                            "field_key": f.field_key,
                            "line_no": f.line_no,
                            "raw_value": f.raw_value,
                            "comment": f.comment,
                            "state": f.state,
                            "allowed_verbs": f.allowed_verbs,
                        }
                        for f in fields
                    ],
                },
            )

        def _handle_api_docs(self) -> None:
            """UI design pass: the closed set of CEP's own docs available to the
            in-app viewer (PROTOCOL.md, README.md, every case study). Resolved
            against wizard_docs.install_root() - this skill's own install
            location - never ctx.repo_root, since these describe the CEP
            protocol itself, not whatever repo the wizard happens to be
            onboarding right now (see wizard_docs.py's module docstring)."""
            if self._require_session() is None:
                return
            self._send_json(
                HTTPStatus.OK, wizard_docs.to_json_dict(wizard_docs.list_docs())
            )

        def _handle_api_doc_detail(self, doc_id: str) -> None:
            """Renders one doc to HTML on request, rather than eagerly with
            /api/docs - most sessions never open every doc, and Markdown
            rendering is pure CPU work with no reason to pay it upfront. doc_id
            is looked up against the same closed set /api/docs enumerates, so
            an unrecognized id is a plain 404 dict-lookup miss - never a
            filesystem path built from client input (see wizard_docs.py)."""
            if self._require_session() is None:
                return
            entry = wizard_docs.find_doc(doc_id)
            if entry is None:
                self._reject(HTTPStatus.NOT_FOUND, "Unknown doc id.")
                return
            try:
                markdown_text = entry.path.read_text(encoding="utf-8")
            except OSError as exc:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)}
                )
                return
            # entry.path lives under install_root() (see wizard_docs.py); its
            # own directory, relative to that root, is where any relative
            # image src in the doc's own Markdown/HTML is meant to resolve
            # against - "." (the root itself, for PROTOCOL.md/README.md)
            # collapses to the bare prefix rather than a literal "./".
            doc_dir_rel = entry.path.parent.relative_to(wizard_docs.install_root()).as_posix()
            asset_prefix = (
                "/api/docs-assets/"
                if doc_dir_rel == "."
                else f"/api/docs-assets/{doc_dir_rel}/"
            )
            # Maps every other doc's own install-root-relative path back to
            # its doc_id, so a relative Markdown link inside *this* doc (e.g.
            # case-studies/README.md linking to "textual/CASE-STUDY.md") can
            # become an in-app navigation instead of a dead href - see
            # wizard_markdown.render()'s link_resolver parameter. Built fresh
            # per request from the same closed-set scan /api/docs already
            # returns; a path with no matching doc_id (e.g.
            # "references/reproducibility-guide.md", deliberately outside
            # this corpus) falls through to wizard_markdown's GitHub-link
            # fallback instead - never a filesystem lookup on client input.
            link_resolver_map = {
                d.path.relative_to(wizard_docs.install_root()).as_posix(): d.doc_id
                for d in wizard_docs.list_docs()
            }
            self._send_json(
                HTTPStatus.OK,
                {
                    "title": entry.title,
                    "html": wizard_markdown.render(
                        markdown_text,
                        asset_prefix=asset_prefix,
                        doc_dir=doc_dir_rel,
                        link_resolver=link_resolver_map.get,
                    ),
                },
            )

        def _handle_api_doc_asset(self, rel_path: str) -> None:
            """Serves a static file *referenced by* a rendered doc (e.g.
            README.md's own hero image) - unlike doc_id above, this route DOES
            take an arbitrary path from the client, because the browser is
            just requesting whatever <img src> wizard_markdown.render() emitted
            for it. wizard_containment.check_containment is therefore the real
            boundary here (same posture as wizard_picker.py's rel_path), not a
            closed-set dict lookup - see that module's docstring for why the
            two doc-serving routes need different trust models."""
            if self._require_session() is None:
                return
            decoded = unquote(rel_path)
            try:
                target = wizard_containment.check_containment(
                    wizard_docs.install_root(), decoded
                )
            except wizard_containment.ContainmentError:
                self._reject(HTTPStatus.NOT_FOUND, "Not found.")
                return
            if not target.is_file():
                self._reject(HTTPStatus.NOT_FOUND, "Not found.")
                return
            content_type, _ = mimetypes.guess_type(str(target))
            self._send_bytes(
                HTTPStatus.OK, target.read_bytes(), content_type or "application/octet-stream"
            )

        def _handle_api_stage(self) -> None:
            body = self._read_json_body()
            if body is None:
                return
            section_title = body.get("section_title")
            field_key = body.get("field_key")
            verb = body.get("verb")
            arg = body.get("arg")
            line_no = body.get("line_no")
            if not section_title or not field_key or not verb:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "section_title, field_key, and verb are required"},
                )
                return
            if line_no is not None and not isinstance(line_no, int):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "line_no must be an integer"})
                return

            source = self._try_layout_source()
            if source is None:
                return
            artifact_path = source.discovery_artifact_path
            try:
                wizard_decision_staging.stage_decision(
                    ctx.repo_root, artifact_path, section_title, field_key, verb,
                    arg=arg, line_no=line_no,
                )
            except wizard_decision_staging.DecisionStagingError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(
                HTTPStatus.OK,
                {"staged": True, "artifact_hash": wizard_content_hash.hash_artifact(artifact_path)},
            )

        def _handle_api_apply(self) -> None:
            body = self._read_json_body()
            if body is None:
                return
            # A missing/omitted loaded_artifact_hash is deliberately not its
            # own 400 - apply_confirmed's freshness check already fails
            # closed on any mismatch (None only matches a genuinely-missing
            # artifact), so an absent key naturally refuses via the same
            # StaleArtifactError path as a stale one, rather than needing a
            # second explicit check here.
            loaded_artifact_hash = body.get("loaded_artifact_hash")

            source = self._try_layout_source()
            if source is None:
                return
            artifact_path = source.discovery_artifact_path
            try:
                result = wizard_apply.apply_confirmed(
                    ctx.repo_root, artifact_path, loaded_artifact_hash
                )
            except wizard_apply.StaleArtifactError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            except wizard_apply.ValidationError as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST, {"error": str(exc), "messages": exc.messages}
                )
                return
            except wizard_apply.UnexpectedNoOpError as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            self._send_json(
                HTTPStatus.OK,
                {
                    "config_changed": result.config_changed,
                    "idempotent": result.idempotent,
                    "messages": result.messages,
                    "config_hash_after": result.config_hash_after,
                    "artifact_hash_after": result.artifact_hash_after,
                },
            )

        def _handle_api_discover(self) -> None:
            """Phase 2 (§18.14 Section B): UI-driven `discover`/re-discover. Mirrors
            `_handle_api_apply`'s freshness-check-then-real-call shape exactly, but
            adds the staged-decision guard `wizard_discover.run_discover` owns (see
            its own module docstring for why re-running `discover` is unsafe by
            default when a section has a staged-but-not-yet-Applied decision)."""
            body = self._read_json_body()
            if body is None:
                return
            loaded_artifact_hash = body.get("loaded_artifact_hash")
            force = bool(body.get("force", False))

            source = self._try_layout_source()
            if source is None:
                return
            artifact_path = source.discovery_artifact_path
            try:
                result = wizard_discover.run_discover(
                    ctx.repo_root, artifact_path, loaded_artifact_hash, force=force
                )
            except wizard_discover.StaleArtifactError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            except wizard_discover.AtRiskDecisionsError as exc:
                self._send_json(
                    HTTPStatus.CONFLICT,
                    {"error": str(exc), "at_risk_sections": exc.at_risk_sections},
                )
                return
            except wizard_discover.DiscoverError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(
                HTTPStatus.OK,
                {
                    "artifact_hash_after": result.artifact_hash_after,
                    "discarded_staged_sections": result.discarded_staged_sections,
                },
            )

    return WizardRequestHandler


def build_server(repo_root: str = ".") -> "tuple[ThreadingHTTPServer, wizard_auth.SessionStore]":
    """Runs preflight, binds once, and returns the constructed (not-yet-serving)
    server plus its SessionStore. Split out from `run()` so tests (and any future
    embedder) can drive the server directly - start it in a background thread, read
    `session_store.bootstrap_token`, hit real HTTP endpoints, shut it down - without
    scraping the bootstrap token back out of stdout.

    Raises `wizard_preflight.PreflightError` on any failed dependency check; no socket
    is opened in that case. Preflight (Phase 2, D24 §18.14) now only checks that
    `ult-repo-layout` is installed at all - it deliberately does *not* run
    `validate_layout.py`'s `validate()` any more, since a `layout_broken` repo must
    still bind and render a screen, not `SystemExit` before opening a socket. This
    function correspondingly no longer constructs a `LayoutSource` at all - each
    request builds its own fresh via `_try_layout_source()`, so a broken layout is a
    per-request 503 (or the `layout_broken` state from `/api/state`), never a reason
    the whole process can't start."""
    wizard_preflight.run_preflight(repo_root)

    ctx = _ServerContext()
    ctx.repo_root = Path(repo_root).resolve()
    handler_cls = _make_handler(ctx)
    server = ThreadingHTTPServer((BIND_HOST, 0), handler_cls)
    port = server.server_address[1]

    ctx.session_store = wizard_auth.SessionStore()
    ctx.allowlist = wizard_originhost.build_host_allowlist(port)
    return server, ctx.session_store


def run(repo_root: str = ".") -> None:
    try:
        server, session_store = build_server(repo_root)
    except wizard_preflight.PreflightError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

    port = server.server_address[1]
    print("ult-cep-wizard is running.")
    print("Open this link in your browser (valid once, expires after 30 minutes idle):")
    print(f"  http://{BIND_HOST}:{port}/exchange?token={session_store.bootstrap_token}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else ".")
