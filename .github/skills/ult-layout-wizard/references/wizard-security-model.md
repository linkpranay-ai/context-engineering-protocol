# Wizard security model

Self-contained restatement of `ult-layout-wizard`'s bind/auth/session/CSRF/Origin-Host/
containment design (D24 §18.2b). Read this alongside the four modules it describes —
`wizard_auth.py`, `wizard_originhost.py`, `wizard_containment.py`,
`wizard_preflight.py` — each of which carries the same reasoning in its own docstring;
this file exists to give a reviewer one place to read the whole model without opening
four files.

**Scope note:** this describes the real, current attack surface of a
localhost-only development tool, not a hardened multi-tenant or internet-facing
deployment. See `SECURITY.md`'s `## Scope` section for the top-level disclosure.

## 1. Fail-fast dependency gate (`wizard_preflight.py`) + per-request onboarding state

**Narrowed in Phase 2 (D24 §18.14).** Before any socket opens or any token is minted,
one check runs, sufficient on its own to refuse startup:

1. `ult-repo-layout` is installed at all (`SKILL.md` + `scripts/validate_layout.py`
   present).

The two checks this module used to run at startup — "has `ult-repo-layout` actually
been run here" (D20 slot-registry markers) and "does `validate_layout.py --validate`
currently pass" — are **retired from preflight, not softened**. The first tested the
wrong axis entirely: it looked for D20 init state, but the wizard's Decisions UI
operates on the separate D23 discover/confirm-layers system, so a repo that only ever
ran `discover`+`confirm-layers` (the real brownfield path) could never pass it, no
matter how complete its setup was. The second — requiring `validate()` to already
pass — meant the wizard could never help fix a broken layout, only refuse to look at
one. Both are now handled by **`wizard_onboarding_state.py`**, computed fresh on every
`GET /api/state` request instead of once at startup:

| State | Entry condition |
|---|---|
| `layout_broken` | `validate_layout.validate()` fails — minimal FAIL-lines screen, no boxes/decisions/picker attempted |
| `needs_discover` | Validates clean, no discovery artifact yet — guide-only intro + `POST /api/discover` |
| `decisions_pending` | Artifact exists, some field still pending/staged |
| `steady_state` | Artifact exists, everything confirmed |

D20 initialization status is still computed (relocated, not deleted, to
`wizard_onboarding_state._is_d20_initialized`) but only as a non-gating informational
`d20_initialized` boolean carried on every state — never a reason to refuse to start or
to pick a different screen. See `wizard-onboarding-state-machine.md` for the full
state table and the reasoning above in more detail.

Consequently, `wizard_server.build_server()` no longer constructs a `LayoutSource` at
startup either — a broken layout must still let the process bind and serve the
`layout_broken` screen, not `SystemExit` before opening a socket. Each handler that
needs a `LayoutSource` builds one fresh per request via `_try_layout_source()`, which
returns a 503 (not a startup crash) if `validate()` fails between requests.

Any preflight failure still prints one specific, actionable message and exits nonzero.
The `wizard-e2e` CI job's minimal-install stamp is kept, but is no longer load-bearing
for the server to start at all — see `wizard_e2e_check.py`'s own docstring for why it's
still worth doing.

## 2. Bind and process lifetime

- Binds `127.0.0.1` only, on an OS-assigned port (`port 0`) — bound exactly once, no
  throwaway-socket-then-rebind race window.
- `<repo_root>` is a required, explicit CLI argument, never inferred from the current
  working directory — printed back to the console before anything else happens, so a
  wrong invocation is visibly wrong before any read (let alone a future write)
  happens.
- No persistence anywhere: `SessionStore` is in-process memory only. The server exits
  on Ctrl+C or process termination, and nothing survives a restart — there is no
  session-renewal mechanism by design (a fresh bootstrap token is minted every launch).
  This "dies on process exit" property is architecturally true by construction, not
  something provable by a test running inside that same process (Risk R4) — it's
  verifiable by code review (no `atexit`/daemonization/persistence anywhere in
  `wizard_server.py`), not by a unit test asserting it.

## 3. Auth: single-use bootstrap token → session cookie (`wizard_auth.py`)

Adapted from the Jupyter/`mkdocs serve` precedent, narrowed to single-use:

1. Startup mints one `secrets.token_urlsafe(32)` bootstrap token and prints
   `/exchange?token=<token>` to stdout — the only place that token ever appears.
2. `GET /exchange` verifies it via `secrets.compare_digest` (never `==`, avoiding a
   timing side-channel) and marks it consumed immediately — a second visit to the same
   URL is rejected as replay, even within the token's own lifetime. Both "wrong token"
   and "already consumed" fail identically, so a prober can't distinguish the two.
3. On success, the server responds with `Set-Cookie: wizard_session=...; HttpOnly;
   SameSite=Strict; Path=/` (no `Secure` flag — this is plain HTTP on 127.0.0.1, not a
   downgrade of a real HTTPS deployment) and embeds a CSRF nonce directly in the served
   HTML — never in a cookie, since the entire point of a CSRF nonce is that a hostile
   page can't read it while a cookie is sent automatically regardless of origin.
4. Every subsequent request must present the session cookie; `authenticate_request()`
   also enforces a 30-minute idle timeout — anything older is invalidated outright,
   with no silent extension by an unauthenticated probe.
5. Any state-changing request must additionally present the session's CSRF nonce in a
   request **header** (`X-Wizard-CSRF-Token`) — `check_csrf()` never reads a cookie or
   query string itself, so a caller can't accidentally wire it to the wrong source.
   This is now exercised by real traffic: `POST /api/stage` and `POST /api/apply`
   (Phase 1's write endpoints) both gate on it — see §7.

## 4. Origin/Referer/Host validation (`wizard_originhost.py`)

Two independent, fail-closed checks (reject on any ambiguity, never default-allow):

- **Host allowlist**, checked on *every* request regardless of method: the `Host`
  header must match `127.0.0.1:<port>`, `localhost:<port>`, or `[::1]:<port>` at the
  server's actual bound port, built fresh at startup — never a hardcoded default. This
  closes a DNS-rebinding gap: a hostname that resolves to 127.0.0.1 but isn't one of
  these three literal strings is rejected on the `Host` header alone.
- **Origin/Referer presence**, checked only for mutating-shaped methods (POST/PUT/
  PATCH/DELETE): a request missing both headers is rejected outright, and any header
  that *is* present must resolve to the same host allowlist. GET/HEAD are exempt (they
  shouldn't be mutating, and requiring these headers on a plain GET would break a user
  simply pasting the wizard URL into a browser). This now exercises the accept path too,
  not only reject: every `POST /api/stage`/`POST /api/apply` request the wizard's own
  frontend sends carries an `Origin` header that resolves to the bound host, and
  `do_POST` checks this before session or CSRF at all (§7).

## 5. Path containment (`wizard_containment.py`)

Every path resolved relative to the affirmed root — by the picker, by the box view
model, by anything — is checked for genuine containment, not just string-prefix
matching:

- The fully-resolved candidate must be the root itself or a real descendant of it
  (case-insensitive, NTFS-case-fold-normalized comparison, with the `\\?\` extended-
  length prefix `Path.resolve()` sometimes adds stripped before comparing).
- **Every intermediate path component** between the root and the target is walked
  *without* following symlinks and checked individually — this catches what
  `Path.resolve()` alone would hide: a symlink pointing elsewhere that still happens to
  resolve to somewhere back under the root.
- On Windows: both symlinks (`IO_REPARSE_TAG_SYMLINK`) and directory junctions
  (`IO_REPARSE_TAG_MOUNT_POINT`) are real violations. **OneDrive Files-On-Demand cloud
  placeholders are explicitly not** — a placeholder is still a real file inside the
  root, just not yet hydrated locally, recognized by masking the family nibble of the
  `IO_REPARSE_TAG_CLOUD` tag range rather than enumerating all thirteen per-provider
  variants by hand. Any *other*, unrecognized reparse tag is still rejected — fail-
  closed, not "everything except the two named tags is fine."
- On POSIX: any symlink anywhere in the resolved chain is a violation, full stop —
  there's no cloud-placeholder concept to special-case.
- UNC paths and drive-letter paths are both handled and normalized to the same
  comparison form.

**Risk R3 — OneDrive placeholder validation is partly manual.** A cloud placeholder is
live sync state, not a packageable CI fixture. Unit tests mock the reparse-tag value
directly (`_is_cloud_placeholder_tag`'s logic is fully unit-testable in isolation);
full end-to-end confirmation that a *real* Files-On-Demand placeholder on a *real*
synced machine is not rejected needs a manual run — disclosed here as mocked-not-fully-
automated, not claimed equivalent to full CI coverage.

**Manual validation record:** this repo was developed inside an OneDrive-synced local
checkout, so a real end-to-end run against it exercises this exact path. Local
smoke-testing done during implementation ran the server against that OneDrive-synced
checkout without any containment false-positive on a real cloud-placeholder file —
confirming the placeholder-vs-violation distinction holds against genuine OneDrive
sync state, not only the mocked unit-test case. If you validate this on your own
OneDrive- or similar cloud-sync-backed checkout, it's worth a one-line addition here
recording the platform and outcome.

## 6. What this tool deliberately does not add

- No rate limiting, no multi-tenant isolation, no TLS — none of these matter for a
  single-operator, localhost-only, single-sitting tool, and adding them would
  misrepresent the actual threat model this tool operates under.
- No dependency beyond the Python standard library, anywhere in `wizard_server.py` or
  anything it imports — this is where the project's stdlib-only stance is enforced
  structurally, not just by policy. This still holds with the write path in place:
  `wizard_apply.py` calls `confirm_layers.run_confirm()` in-process, no subprocess, no
  new dependency.
- Still no RBAC and still no distinction between "can view" and "can write" — the
  single bootstrap-token session that can see `/api/status` is the same session that
  can call `/api/apply`. This was already true in spirit (§18.13 flag #2, single-
  operator posture) and the write path doesn't change it — there was never a second,
  lower-privilege session type to preserve.

## 7. Write-path security (Phase 1 + Phase 2)

`POST /api/stage` and `POST /api/apply` are the wizard's first two mutating routes.
Neither writes anything directly — see `wizard-write-path.md` for what they actually
do (`wizard-proposes, CLI-commits`, §18.3). This section is about what gates a request
*before* it reaches either handler, and the one validation layer that's new to the
write path specifically.

**Gate order in `do_POST`** — each gate can reject on its own, checked in this order
so the cheapest, most information-hiding check runs first:

1. `_origin_host_ok()` — the same Host-allowlist + Origin/Referer check as `do_GET`
   (§4), now actually exercising its mutating-method branch. A request that fails here
   never gets far enough to reveal whether a session even exists.
2. `_require_session()` — the same session-cookie + idle-timeout check every other
   route uses (§3.4). A missing or expired session is rejected here, same 401 either
   way, before CSRF is even checked.
3. `check_csrf()` against the `X-Wizard-CSRF-Token` header (§3.5) — a valid session
   with a missing or wrong CSRF header is rejected with 403, not 401, so a caller can
   tell "your session is fine, but this specific request wasn't authorized" apart from
   "you're not logged in at all."

Only a request that clears all three reaches `_handle_api_stage`/`_handle_api_apply`
and, from there, `wizard_decision_staging.stage_decision`/`wizard_apply.apply_confirmed`.

**`POST /api/discover` (Phase 2, D24 §18.14) is a fourth mutating route through this
exact same gate order** — `_origin_host_ok()` → `_require_session()` → `check_csrf()`,
no new or relaxed mechanism. It hands off to `wizard_discover.run_discover`, which adds
its own two request-shaped guards on top (not HTTP-layer concerns, so not part of this
list): a `StaleArtifactError` (409) if the loaded artifact hash is stale — the same H6
staleness pattern Apply already uses, checked first, even when the caller passes
`force` — and an `AtRiskDecisionsError` (409, with `at_risk_sections`) if any field is
`staged`-but-not-yet-Applied and the caller didn't pass `force: true`, so a bare re-run
can never silently clobber in-progress staged work. See `wizard-write-path.md`'s
`/api/discover` section for the full request/response shape.

**CUSTOM-argument validation (round-3 H1)** — the one fail-closed layer that's new to
this path, not a reuse of an existing one. A `CUSTOM` verb's `arg` is a user-typed (or
picker-supplied) relative path, and `confirm_layers.py` itself performs no validation
on it at all — the discovery artifact is hand-editable by design, so nothing upstream
can be assumed to have already checked it. `wizard_decision_staging.validate_custom_arg`
rejects: any literal backslash (never silently converted to a forward slash — a
Windows-shaped path is refused, not "fixed"), any `..` component, any drive letter, any
`#` (a comment-truncation hazard in `confirm_layers.set_scalar`'s YAML rewrite), and
finally re-runs the request through `wizard_containment.check_containment` — the same
genuine-containment check the picker itself uses (§5) — so a syntactically clean but
symlink-escaping path is still caught.

**The two content-hash checks close round-3 C2 and H6** — both live in
`wizard_apply.apply_confirmed`, not in the HTTP layer, so they apply the same way
whether Apply is driven by the browser or by a future non-browser caller:

- **H6 (staleness):** the artifact's current content hash must match the hash the
  caller loaded it under. A mismatch — e.g. a concurrent `discover` re-run, or another
  browser tab staging something — is a 409, never a silent overwrite of state the
  caller never saw.
- **C2 (silent no-op):** `confirm_layers.run_confirm()` returning exit code 0 is not by
  itself proof anything was committed. `context-config.yaml`'s content hash is diffed
  before and after the call and classified into three outcomes — real commit (hash
  changed), legitimate idempotent no-op (hash unchanged, message starts with "Nothing
  to confirm"), or the failure mode (hash unchanged, no such message) — and only the
  third is ever raised back to the caller as an error (`UnexpectedNoOpError`, 500).
  Never reported as success.

None of this expands the trust boundary described in §18.13 flag #2 (single-operator,
no RBAC) or flag #9 (residual same-OS-user exposure) — the write routes exercise that
same boundary for the first time, they don't widen it. Anyone who could already read
`/api/status` inside this session could already read `context-config.yaml` directly off
disk; the write path lets that same person write it through a validated, atomic,
hash-checked path instead of hand-editing YAML, nothing more.

## 8. Docs viewer read routes (D24 UI design pass)

Three new `GET` routes serve CEP's own project docs (`PROTOCOL.md`, `README.md`,
`case-studies/*/CASE-STUDY.md`) into the in-app docs overlay — all still session-gated
(`_require_session()`), all still read-only, but the last one has a materially
different trust model from the other two:

- **`GET /api/docs`, `GET /api/docs/<id>`** — closed-set by construction, the same
  posture `STATIC_ASSETS` already uses for `wizard.css`/`wizard.js` (§5 is about paths
  resolved from client input; these routes have none). `<id>` is never a path — it's a
  dict-lookup key against a list `wizard_docs.list_docs()` builds itself by scanning
  `wizard_docs.install_root()`. Any `<id>` not already in that scan is a plain 404, not
  a filesystem lookup gone wrong. No `wizard_containment` call is needed or made here,
  same reasoning `wizard_docs.py`'s own module docstring gives for why it's unlike
  `wizard_picker.py`.
- **`GET /api/docs-assets/<rel_path>`** — the one exception. A rendered doc can
  reference its own relative images (`README.md`'s hero SVG, resolved by
  `wizard_markdown.render(..., asset_prefix=...)` into a URL under this route — see that
  module's docstring), and the browser then requests whatever `src` the renderer
  emitted — so `<rel_path>` genuinely is client-supplied, shaped exactly like
  `wizard_picker.py`'s `rel_path`. It gets the same treatment: `unquote()`'d, then
  `wizard_containment.check_containment(wizard_docs.install_root(), decoded)` — full
  symlink/junction/reparse-tag walking, not string-prefix matching, identical machinery
  to §5. **The affirmed root is `wizard_docs.install_root()` (where this skill is
  installed), not `<repo_root>`** (the project being onboarded) — a different root than
  every other containment check in this file, because these are CEP's own docs, not the
  target repo's. A `ContainmentError` and a missing file both 404 identically, matching
  this file's running theme of non-distinguishing failure (§3.2, §5).

Trust model note: the Markdown/HTML *content* itself is never sanitized against
injection (see `wizard_markdown.py`'s module docstring) — it's rendered on the
assumption that `PROTOCOL.md`/`README.md`/case-study files are repo-controlled, the
same level `STATIC_ASSETS` already assumes for `wizard.css`/`wizard.js`. That
assumption does not extend to `/api/docs-assets`'s `<rel_path>`, which is why it alone
gets the full containment check above rather than inheriting the closed-set posture of
its two sibling routes.
