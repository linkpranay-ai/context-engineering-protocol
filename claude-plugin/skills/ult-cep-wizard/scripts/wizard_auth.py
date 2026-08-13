"""wizard_auth.py - bootstrap token issuance, single-use exchange, session cookie
management, and CSRF nonce handling for ult-cep-wizard (D24 §18.2b, locked).

Auth model (Jupyter/mkdocs-serve precedent, adapted for single-use tokens):

  1. On startup, wizard_server.py mints one bootstrap token via
     `secrets.token_urlsafe(32)` and prints a one-time URL (`/exchange?token=<token>`)
     to stdout. Nothing else is printed to stdout by this module - the token is the
     whole trust boundary, so it only ever appears in that one printed line.
  2. The browser visits that URL once. `SessionStore.exchange_token()` verifies the
     token via `secrets.compare_digest` (never `==`, to avoid timing side-channels),
     marks it consumed (a second visit to the same URL - replay - is rejected even
     within the token's own lifetime), and mints a new session: a session id, a CSRF
     nonce, and `created_at`/`last_seen_at` timestamps.
  3. The server responds with a `Set-Cookie` for the session id
     (`HttpOnly; SameSite=Strict; Path=/` - no `Secure` flag, since this is plain http
     on 127.0.0.1, not a downgrade of a real HTTPS deployment) and embeds the CSRF
     nonce directly in the HTML it serves (never in a cookie - the whole point of a
     CSRF nonce is that a hostile page can't read it, and cookies are sent
     automatically regardless of origin).
  4. Every request after that must present the session cookie via
     `SessionStore.authenticate_request()`, which also enforces the 30-minute idle
     timeout - a `last_seen_at` older than that invalidates the session outright (no
     silent extension by an unauthenticated probe).
  5. Any state-changing request must additionally present the session's CSRF nonce in
     a request *header* (never read from a cookie or query string) via
     `SessionStore.check_csrf()`. Phase 0 registers zero mutating routes, but the
     plumbing exists end-to-end now so Phase 1's first write endpoint has nothing new
     to design here.

There is deliberately no session renewal/refresh-token mechanism: idle timeout or
process exit (whichever first) ends the session, full stop - restart the server for a
fresh bootstrap token. This is a single-operator, single-sitting local tool, not a
multi-session service (R4: this is architecturally true, not test-provable from within
the same process - see wizard-security-model.md, added in a later build step).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Optional

IDLE_TIMEOUT_SECONDS = 30 * 60
SESSION_COOKIE_NAME = "wizard_session"
CSRF_HEADER_NAME = "X-Wizard-CSRF-Token"


@dataclass
class Session:
    session_id: str
    csrf_nonce: str
    created_at: float
    last_seen_at: float


class SessionStore:
    """All state is in-process memory only - nothing is written to disk, and nothing
    survives process restart."""

    def __init__(self, bootstrap_token: Optional[str] = None):
        self._bootstrap_token = bootstrap_token or secrets.token_urlsafe(32)
        self._token_consumed = False
        self._sessions: dict[str, Session] = {}

    @property
    def bootstrap_token(self) -> str:
        return self._bootstrap_token

    def exchange_token(self, presented_token: str) -> Optional[Session]:
        """Single-use exchange: a valid, not-yet-consumed token mints a new session
        and is immediately marked consumed. Returns None on any failure (wrong token,
        already consumed) - callers must not distinguish the two in their response, so
        an attacker probing can't tell "wrong guess" from "already used"."""
        if self._token_consumed:
            return None
        if not presented_token or not secrets.compare_digest(
            presented_token, self._bootstrap_token
        ):
            return None
        self._token_consumed = True
        return self._create_session()

    def _create_session(self) -> Session:
        now = time.monotonic()
        session = Session(
            session_id=secrets.token_urlsafe(32),
            csrf_nonce=secrets.token_urlsafe(32),
            created_at=now,
            last_seen_at=now,
        )
        self._sessions[session.session_id] = session
        return session

    def authenticate_request(
        self, presented_session_id: Optional[str]
    ) -> Optional[Session]:
        """Validates a session cookie value and enforces the idle timeout. Returns the
        live Session on success (and bumps last_seen_at), else None - callers must
        treat None as "respond 401", not distinguish "no cookie" from "expired" from
        "unknown session id" (same non-distinguishing rationale as exchange_token)."""
        if not presented_session_id:
            return None
        session = self._sessions.get(presented_session_id)
        if session is None:
            return None
        now = time.monotonic()
        if now - session.last_seen_at > IDLE_TIMEOUT_SECONDS:
            del self._sessions[presented_session_id]
            return None
        session.last_seen_at = now
        return session

    def check_csrf(self, session: Session, presented_nonce: Optional[str]) -> bool:
        """For mutating routes only. Compares only against the header value the caller
        passes in - this function never itself reads cookies or query strings, so a
        caller can't accidentally wire it to the wrong source."""
        if not presented_nonce:
            return False
        return secrets.compare_digest(presented_nonce, session.csrf_nonce)

    def session_cookie_header(self, session: Session) -> str:
        return (
            f"{SESSION_COOKIE_NAME}={session.session_id}; "
            "HttpOnly; SameSite=Strict; Path=/"
        )
