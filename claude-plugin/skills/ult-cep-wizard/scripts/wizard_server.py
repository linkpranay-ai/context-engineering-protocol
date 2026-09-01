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
resolve against `wizard_docs.docs_root()`, not `ctx.repo_root`, since these
docs describe the CEP protocol itself, not whatever repo is being onboarded.
`_handle_api_status` also now wires in
`wizard_stub_content`'s previously-orphaned preview cards alongside the existing box
view model.

the 2026-08-31 Round-2 evaluation's finding on first-run workspace-root namespacing during init adds the first-run `layout.workspace_root`
namespacing offer's write path: `POST /api/init/preview` (dry-run, zero disk writes,
`wizard_init.preview_init`) and `POST /api/init` (the real commit,
`wizard_init.run_init`) - same 3-gate mutating dispatch and `_try_layout_source()`
defensive-backstop convention as `/api/discover`. `GET /api/state`'s response also
gained `workspace_root_current`/`workspace_root_offer_eligible`
(`wizard_onboarding_state`) so the frontend knows whether to show the offer at all
before ever calling either new route.
"""

from __future__ import annotations

import html
import json
import mimetypes
import posixpath
import sys
from dataclasses import asdict
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
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
import wizard_init  # noqa: E402
import wizard_markdown  # noqa: E402
import wizard_layout_source  # noqa: E402
import wizard_onboarding_state  # noqa: E402
import wizard_originhost  # noqa: E402
import wizard_picker  # noqa: E402
import wizard_preflight  # noqa: E402
import wizard_retrofit_apply  # noqa: E402
import wizard_retrofit_draft  # noqa: E402
import wizard_retrofit_inventory  # noqa: E402
import wizard_retrofit_state  # noqa: E402
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

# Sentinel returned by _resolve_external_root_or_none() to distinguish "an
# external_root was given and failed validation (a 400 is already sent)" from
# the legitimate "no external_root was given at all" None case - see that
# method's docstring (the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment).
_EXTERNAL_ROOT_INVALID = object()


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
            if path == "/api/retrofit/state":
                self._handle_api_retrofit_state()
                return
            if path == "/api/retrofit/contract-locations":
                self._handle_api_retrofit_contract_locations()
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
            if path == "/api/init/preview":
                self._handle_api_init_preview(session)
                return
            if path == "/api/init":
                self._handle_api_init(session)
                return
            if path == "/api/retrofit/select":
                self._handle_api_retrofit_select()
                return
            if path == "/api/retrofit/draft":
                self._handle_api_retrofit_draft()
                return
            if path == "/api/retrofit/draft-override":
                self._handle_api_retrofit_draft_override()
                return
            if path == "/api/retrofit/apply":
                self._handle_api_retrofit_apply()
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

        def _resolve_external_root_or_none(self, raw: Optional[str]):
            """Journey 3 (the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment): validates
            an optional external retrofit-target root string via
            wizard_containment.resolve_external_target, shared by every
            picker/inventory/select/draft/apply route that can be pointed at
            one. Three-way, not two-way, because a blank/omitted `raw` is a
            legitimate "use ctx.repo_root" request, not a failure:

              - `raw` blank/None -> returns None (no external root requested).
              - `raw` given and valid -> returns the resolved absolute path
                string.
              - `raw` given and invalid -> already sent a 400 with the
                ContainmentError's message; returns _EXTERNAL_ROOT_INVALID so
                the caller can `return` without a second error path, mirroring
                _require_session()/_read_json_body()'s own
                already-responded-so-just-return contract.

            Re-validates every time rather than trusting a previously-
            persisted RETROFIT-STATE.json `target_root` value, on the same
            fail-closed, defense-in-depth footing every other containment
            check in this file already takes for `primary_file` - state on
            disk is this wizard's own, but never assumed untamperable."""
            if not raw or not str(raw).strip():
                return None
            try:
                resolved = wizard_containment.resolve_external_target(ctx.repo_root, raw)
            except wizard_containment.ContainmentError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return _EXTERNAL_ROOT_INVALID
            return str(resolved)

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
            #
            # A card must not point a user at scaffolding content while its own
            # What/How decision is still awaiting Apply - see
            # wizard_stub_content.what_how_card's layer_decisions_pending
            # docstring. Reading decisions here (rather than only from
            # /api/decisions) costs one extra read_decisions() call on this
            # route, same source object, no extra containment/validate work.
            # read_decisions() itself already returns [] when no discovery
            # artifact exists yet, so no explicit no-artifact branch is needed
            # here (matches _handle_api_decisions's own un-wrapped call below).
            #
            # `f.layer` (from layout_decision_grammar.resolve_section_layer(),
            # via wizard_layout_source.read_decisions()) replaces a prior
            # `f.section_title.startswith("What"/"How")` check that missed two
            # real cases: a re-issued "Re-discovery - <title> - <date>"
            # section (starts with "Re-discovery", not "What"/"How"), and
            # COLLISION_TITLE ("Cross-layer path collisions (S30)", which
            # starts with neither and can affect either layer).
            what_pending = how_pending = False
            for f in source.read_decisions():
                if f.state == "confirmed":
                    continue
                if "what" in f.layer:
                    what_pending = True
                if "how" in f.layer:
                    how_pending = True
            what_card = wizard_stub_content.what_how_card(
                "What",
                ctx.repo_root,
                [p.path for p in view.what.paths],
                layer_decisions_pending=what_pending,
            )
            how_card = wizard_stub_content.what_how_card(
                "How",
                ctx.repo_root,
                [p.path for p in view.how.paths],
                layer_decisions_pending=how_pending,
            )
            guidelines_card = wizard_stub_content.guidelines_card(
                ctx.repo_root,
                view.guidelines.initialized,
                view.guidelines.default_path,
                layer_decisions_pending=what_pending or how_pending,
            )
            tripwire_card = wizard_stub_content.tripwire_card(
                ctx.repo_root,
                available=view.tripwire.available,
                initialized=view.tripwire.initialized,
                entries=view.tripwire.entries,
                ledger_path=view.tripwire.ledger_path,
                layer_decisions_pending=what_pending or how_pending,
            )
            payload["stub_cards"] = [
                asdict(card)
                for card in (what_card, how_card, guidelines_card, tripwire_card)
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
            """`external_root` (the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment,
            optional) browses subdirectories of an already-confirmed external
            retrofit target instead of ctx.repo_root - every other caller of
            this route (the onboarding/decision-staging pickers) never sends
            it, so this stays a no-op for them."""
            if self._require_session() is None:
                return
            query = urlsplit(self.path).query
            params = parse_qs(query)
            rel_path = params.get("path", ["."])[0]
            external_root = self._resolve_external_root_or_none(
                params.get("external_root", [None])[0]
            )
            if external_root is _EXTERNAL_ROOT_INVALID:
                return
            try:
                result = wizard_picker.list_directory(external_root or ctx.repo_root, rel_path)
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
                    "target_root": external_root,
                },
            )

        def _handle_api_retrofit_inventory(self) -> None:
            """Journey 3 Phase A - read-only, same session-gate-only posture as
            `_handle_api_picker` (no CSRF/mutating gate: nothing is written).
            `target` defaults to "." (the repo root itself) so a first load with
            no query string still returns something rather than erroring.

            `external_root` (the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment, optional):
            when given, `target` is scanned relative to this already-validated
            external root instead of ctx.repo_root - see
            `_resolve_external_root_or_none` and
            `wizard_retrofit_inventory.build_inventory`'s own docstring. The
            resulting `target_root` in the response is what the frontend must
            echo back on every subsequent select/draft/apply call for units
            discovered from this scan."""
            if self._require_session() is None:
                return
            query = urlsplit(self.path).query
            params = parse_qs(query)
            target_rel_path = params.get("target", ["."])[0]
            external_root = self._resolve_external_root_or_none(
                params.get("external_root", [None])[0]
            )
            if external_root is _EXTERNAL_ROOT_INVALID:
                return
            try:
                result = wizard_retrofit_inventory.build_inventory(
                    ctx.repo_root, target_rel_path, external_root=external_root
                )
            except wizard_retrofit_inventory.RetrofitInventoryError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(
                HTTPStatus.OK, wizard_retrofit_inventory.to_json_dict(result)
            )

        def _handle_api_retrofit_state(self) -> None:
            """Journey 3 Phase B - rehydrate every staged selection/draft on
            page load (e.g. after a browser refresh). Read-only, same
            session-gate-only posture as `_handle_api_retrofit_inventory`."""
            if self._require_session() is None:
                return
            state = wizard_retrofit_state.load_state(ctx.repo_root)
            self._send_json(HTTPStatus.OK, wizard_retrofit_state.to_json_dict(state))

        def _handle_api_retrofit_contract_locations(self) -> None:
            """Journey 3 Phase B - best-effort default same-repo contract
            locations (wizard_retrofit_draft.detect_contract_locations).
            Read-only; the frontend always shows this as an editable default,
            never a silent final answer (SKILL.md Step 5: ask, don't
            assume)."""
            if self._require_session() is None:
                return
            locations = wizard_retrofit_draft.detect_contract_locations(ctx.repo_root)
            self._send_json(HTTPStatus.OK, {"contract_locations": locations})

        def _handle_api_retrofit_select(self) -> None:
            """Journey 3 Phase B - stage (or replace) one unit's inclusion,
            contract selection, and reference-resolution config. Does not
            compute a draft itself - a changed selection is expected to be
            followed by a POST /api/retrofit/draft call, kept as two steps so
            the frontend can let a human review contracts/reference mode
            before spending a draft computation on them."""
            body = self._read_json_body()
            if body is None:
                return
            unit_id = body.get("unit_id")
            primary_file = body.get("primary_file")
            if not unit_id or not primary_file:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "unit_id and primary_file are required"},
                )
                return
            contracts = body.get("contracts") or []
            if not isinstance(contracts, list) or not all(
                isinstance(c, str) for c in contracts
            ):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "contracts must be a list of strings"},
                )
                return
            unknown = [c for c in contracts if c not in wizard_retrofit_draft.CONTRACT_ORDER]
            if unknown:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": f"unknown contract(s): {', '.join(unknown)}"},
                )
                return
            # the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting: per-unit
            # context-availability policy - validated here, at the same
            # point contracts are validated, rather than deferred to
            # draft() time, so a bad value is rejected before it's ever
            # persisted into RETROFIT-STATE.json.
            context_availability = body.get(
                "context_availability", wizard_retrofit_draft.DEFAULT_CONTEXT_AVAILABILITY
            )
            if context_availability not in wizard_retrofit_draft.CONTEXT_AVAILABILITY_POLICIES:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "error": (
                            f"unknown context_availability {context_availability!r} "
                            f"(expected one of "
                            f"{', '.join(wizard_retrofit_draft.CONTEXT_AVAILABILITY_POLICIES)})"
                        )
                    },
                )
                return
            # the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment: re-validated on every
            # request, per _resolve_external_root_or_none's own docstring -
            # never trusted merely because the client echoed back a value the
            # inventory response once returned.
            target_root = self._resolve_external_root_or_none(body.get("target_root"))
            if target_root is _EXTERNAL_ROOT_INVALID:
                return
            try:
                wizard_containment.check_containment(target_root or ctx.repo_root, primary_file)
            except wizard_containment.ContainmentError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            # Directory the drafted reference is written relative to: a flat
            # file's own containing directory, or a skill-dir/manifest-dir
            # unit's own directory (primary_file already points inside it) -
            # this dirname math is correct for every unit type without this
            # handler needing to know the unit's "type" at all.
            unit_dir_rel_path = posixpath.dirname(primary_file) or "."

            state = wizard_retrofit_state.load_state(ctx.repo_root)
            entry = wizard_retrofit_state.upsert_selection(
                state,
                unit_id,
                primary_file=primary_file,
                unit_dir_rel_path=unit_dir_rel_path,
                include=bool(body.get("include", True)),
                contracts=contracts,
                reference_mode=body.get("reference_mode", "same-repo"),
                reference_args=body.get("reference_args") or {},
                context_availability=context_availability,
                target_root=target_root,
            )
            wizard_retrofit_state.save_state(ctx.repo_root, state)
            self._send_json(HTTPStatus.OK, {"unit_id": unit_id, "selection": entry})

        def _handle_api_retrofit_draft(self) -> None:
            """Journey 3 Phase B - computes (or recomputes) one unit's draft:
            idempotency check, insertion point, and template text, via
            wizard_retrofit_draft.build_draft(). Persists the result into
            RETROFIT-STATE.json so it survives a refresh; a prior manual
            override (draft-override) is intentionally discarded by a
            re-draft, since the underlying contracts/reference config changed
            and the override text no longer necessarily applies."""
            body = self._read_json_body()
            if body is None:
                return
            unit_id = body.get("unit_id")
            if not unit_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "unit_id is required"})
                return

            state = wizard_retrofit_state.load_state(ctx.repo_root)
            try:
                entry = wizard_retrofit_state.find_unit(state, unit_id)
            except wizard_retrofit_state.RetrofitStateError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if not entry.get("include", False):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": f"unit {unit_id!r} is not included - select it first"},
                )
                return
            contracts = entry.get("contracts") or []
            if not contracts:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": f"unit {unit_id!r} has no contracts selected"},
                )
                return

            # the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment: re-validated from the
            # persisted entry, same defense-in-depth footing as the select
            # handler - never trusted merely because it was written by our
            # own earlier request.
            target_root = self._resolve_external_root_or_none(entry.get("target_root"))
            if target_root is _EXTERNAL_ROOT_INVALID:
                return
            try:
                result = wizard_retrofit_draft.build_draft(
                    ctx.repo_root,
                    entry["primary_file"],
                    entry.get("unit_dir_rel_path", "."),
                    contracts,
                    entry.get("reference_mode", "same-repo"),
                    entry.get("reference_args") or {},
                    context_availability=entry.get(
                        "context_availability",
                        wizard_retrofit_draft.DEFAULT_CONTEXT_AVAILABILITY,
                    ),
                    containment_root=target_root,
                )
            except wizard_retrofit_draft.RetrofitDraftError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            entry = wizard_retrofit_state.set_draft(
                state,
                unit_id,
                draft_text=result.draft_text,
                insertion_point=result.insertion_point,
                contracts_included=result.contracts_included,
                contracts_skipped_idempotent=result.contracts_skipped_idempotent,
                target_file_hash=result.target_file_hash,
                context_before=result.context_before,
                context_after=result.context_after,
                policy_drifted=result.policy_drifted,
            )
            wizard_retrofit_state.save_state(ctx.repo_root, state)
            self._send_json(
                HTTPStatus.OK,
                {
                    "unit_id": unit_id,
                    "selection": entry,
                    "all_satisfied": result.all_satisfied,
                },
            )

        def _handle_api_retrofit_draft_override(self) -> None:
            """Journey 3 Phase B - persists a human's textarea edit over a
            previously-computed draft (SKILL.md Step 6.3's "always editable"
            requirement). Requires draft() to have run first for this unit -
            there is nothing to override otherwise."""
            body = self._read_json_body()
            if body is None:
                return
            unit_id = body.get("unit_id")
            draft_text = body.get("draft_text")
            if not unit_id or draft_text is None:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "unit_id and draft_text are required"},
                )
                return
            state = wizard_retrofit_state.load_state(ctx.repo_root)
            try:
                entry = wizard_retrofit_state.set_draft_override(state, unit_id, draft_text)
            except wizard_retrofit_state.RetrofitStateError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            wizard_retrofit_state.save_state(ctx.repo_root, state)
            self._send_json(HTTPStatus.OK, {"unit_id": unit_id, "selection": entry})

        def _handle_api_retrofit_apply(self) -> None:
            """Journey 3 Phase C - writes every requested unit's already-
            drafted insertion to disk, one file at a time
            (wizard_retrofit_apply.apply_batch). A per-unit failure is a
            normal, expected outcome here, not a request-level error - this
            always answers HTTP 200 with a per-unit results list; only a
            structurally malformed request (missing/non-list unit_ids) gets
            its own 400, matching SKILL.md Step 8's own stated contract that
            a write failure on one file never aborts the rest of the batch.

            For every unit that actually gets written, the corresponding
            RETROFIT-STATE.json entry is reset to the same "nothing left to
            insert here" shape build_draft() itself uses when everything is
            already satisfied (draft_text="", insertion_point=None,
            contracts_included=[]) - see wizard_retrofit_apply's module
            docstring for why this is what makes a resubmitted batch safe by
            construction. State is persisted after each successful write
            (not once at the end) so a mid-batch crash never leaves
            RETROFIT-STATE.json out of sync with files actually written to
            disk."""
            body = self._read_json_body()
            if body is None:
                return
            unit_ids = body.get("unit_ids")
            if (
                not isinstance(unit_ids, list)
                or not unit_ids
                or not all(isinstance(u, str) for u in unit_ids)
            ):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "unit_ids must be a non-empty list of strings"},
                )
                return

            state = wizard_retrofit_state.load_state(ctx.repo_root)
            results_by_id: Dict[str, Dict[str, Any]] = {}
            inputs: List[wizard_retrofit_apply.ApplyUnitInput] = []
            for unit_id in unit_ids:
                try:
                    entry = wizard_retrofit_state.find_unit(state, unit_id)
                except wizard_retrofit_state.RetrofitStateError as exc:
                    results_by_id[unit_id] = {
                        "unit_id": unit_id,
                        "status": "failed",
                        "reason": str(exc),
                        "contracts_applied": [],
                        "contracts_skipped_idempotent": [],
                    }
                    continue
                if not entry.get("include", False):
                    results_by_id[unit_id] = {
                        "unit_id": unit_id,
                        "status": "failed",
                        "reason": "not included in the selection",
                        "contracts_applied": [],
                        "contracts_skipped_idempotent": [],
                    }
                    continue
                # the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment: re-validated per
                # unit, not once for the whole request - each unit already
                # carries its own independent target_root (see
                # wizard_retrofit_state.upsert_selection's docstring), and a
                # revalidation failure for one unit (e.g. its external root
                # vanished between draft and apply) must fail only that unit,
                # matching this same handler's own "one failure never aborts
                # the batch" contract for every other per-unit problem above.
                raw_target_root = entry.get("target_root")
                target_root = None
                if raw_target_root:
                    try:
                        target_root = str(
                            wizard_containment.resolve_external_target(
                                ctx.repo_root, raw_target_root
                            )
                        )
                    except wizard_containment.ContainmentError as exc:
                        results_by_id[unit_id] = {
                            "unit_id": unit_id,
                            "status": "failed",
                            "reason": str(exc),
                            "contracts_applied": [],
                            "contracts_skipped_idempotent": [],
                        }
                        continue
                inputs.append(
                    wizard_retrofit_apply.ApplyUnitInput(
                        unit_id=unit_id,
                        primary_file=entry.get("primary_file"),
                        insertion_point=entry.get("insertion_point"),
                        draft_text=entry.get("draft_text") or "",
                        contracts_included=list(entry.get("contracts_included") or []),
                        target_file_hash=entry.get("target_file_hash"),
                        containment_root=target_root,
                    )
                )

            for result in wizard_retrofit_apply.apply_batch(ctx.repo_root, inputs):
                if result.status == "applied":
                    applied_entry = wizard_retrofit_state.find_unit(state, result.unit_id)
                    skipped = list(
                        applied_entry.get("contracts_skipped_idempotent") or []
                    ) + list(result.contracts_applied)
                    wizard_retrofit_state.set_draft(
                        state,
                        result.unit_id,
                        draft_text="",
                        insertion_point=None,
                        contracts_included=[],
                        contracts_skipped_idempotent=skipped,
                        target_file_hash=result.target_file_hash_after,
                        context_before="",
                        context_after="",
                    )
                    wizard_retrofit_state.save_state(ctx.repo_root, state)
                results_by_id[result.unit_id] = {
                    "unit_id": result.unit_id,
                    "status": result.status,
                    "reason": result.reason,
                    "contracts_applied": result.contracts_applied,
                    "contracts_skipped_idempotent": result.contracts_skipped_idempotent,
                }

            self._send_json(
                HTTPStatus.OK,
                {"results": [results_by_id[unit_id] for unit_id in unit_ids]},
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
            against wizard_docs.docs_root() - this skill's own docs
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
            # entry.path lives under docs_root() (see wizard_docs.py); its
            # own directory, relative to that root, is where any relative
            # image src in the doc's own Markdown/HTML is meant to resolve
            # against - "." (the root itself, for PROTOCOL.md/README.md)
            # collapses to the bare prefix rather than a literal "./". Not
            # None here: entry came from find_doc(), which only ever returns
            # a hit by scanning list_docs(), which itself already required a
            # verified docs_root() to produce anything at all.
            doc_dir_rel = entry.path.parent.relative_to(wizard_docs.docs_root()).as_posix()
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
                d.path.relative_to(wizard_docs.docs_root()).as_posix(): d.doc_id
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
            two doc-serving routes need different trust models. Gated on
            wizard_docs.docs_root() being non-None first - the same trust
            `_handle_api_docs`/`list_docs()` require - so this route can never
            serve a file out of an unverified root that `/api/docs` itself
            would have refused to enumerate."""
            if self._require_session() is None:
                return
            docs_root = wizard_docs.docs_root()
            if docs_root is None:
                self._reject(HTTPStatus.NOT_FOUND, "Not found.")
                return
            decoded = unquote(rel_path)
            try:
                target = wizard_containment.check_containment(docs_root, decoded)
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

        def _handle_api_init_preview(self, session: wizard_auth.Session) -> None:
            """the 2026-08-31 Round-2 evaluation's finding on first-run workspace-root namespacing during init: dry-run preview of the
            first-run `layout.workspace_root` namespacing offer - the tree/messages
            shown before the human commits to a value. Defensive backstop
            `_try_layout_source()` gate matches every other mutating-adjacent route
            here (frontend is expected to have already routed past `layout_broken`
            via `/api/state`); this route itself never mutates anything regardless,
            since `wizard_init.preview_init` always calls `dry_run=True`.

            the 2026-08-31 Round-2 evaluation's finding on POST /api/init committing without a
            prior preview: a successful preview stamps this session's
            `init_preview_token` - the only value `_handle_api_init` will ever
            accept as proof a preview happened for the workspace_root it's about
            to commit."""
            body = self._read_json_body()
            if body is None:
                return
            workspace_root = body.get("workspace_root")
            if workspace_root:
                # Belt-and-suspenders (2026-09-01): validate_layout.run_init
                # already rejects an absolute/UNC workspace_root as
                # not-well-formed, but this route is the only write-adjacent
                # one in the wizard that skipped the containment check every
                # other client-supplied path gets at the HTTP boundary - add
                # it here too, rather than relying solely on a check several
                # calls away that a future refactor could bypass.
                try:
                    wizard_containment.check_containment(ctx.repo_root, workspace_root)
                except wizard_containment.ContainmentError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

            if self._try_layout_source() is None:
                return
            try:
                result = wizard_init.preview_init(ctx.repo_root, workspace_root=workspace_root)
            except wizard_init.InitError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            session.init_preview_token = result.init_preview_token
            self._send_json(HTTPStatus.OK, {"messages": result.messages})

        def _handle_api_init(self, session: wizard_auth.Session) -> None:
            """The real, committing call - identical body shape to
            `/api/init/preview`. The frontend is expected to have already shown the
            human the matching preview output for the same `workspace_root` value
            before calling this (see wizard_init.run_init's own docstring).

            the 2026-08-31 Round-2 evaluation's finding on POST /api/init committing without a
            prior preview: `init_preview_token` is sourced only from this
            session's own state (set by a prior successful `/api/init/preview`
            call), never from the request body - a client cannot supply or
            forge its way past this by sending its own value. No preview this
            session, or a preview for a different `workspace_root`, both fail
            `wizard_init.run_init`'s internal match check before anything is
            written."""
            body = self._read_json_body()
            if body is None:
                return
            workspace_root = body.get("workspace_root")
            if workspace_root:
                # See the matching guard in _handle_api_init_preview - this is
                # the real, committing route, so the guard matters even more here.
                try:
                    wizard_containment.check_containment(ctx.repo_root, workspace_root)
                except wizard_containment.ContainmentError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

            if self._try_layout_source() is None:
                return
            try:
                result = wizard_init.run_init(
                    ctx.repo_root,
                    workspace_root=workspace_root,
                    init_preview_token=session.init_preview_token,
                )
            except wizard_init.InitError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            # One-shot: a completed commit consumes the preview it was based
            # on, same posture as the bootstrap token's single-use exchange -
            # a stale token from this commit must not authorize another one.
            session.init_preview_token = None
            self._send_json(HTTPStatus.OK, {"messages": result.messages})

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
