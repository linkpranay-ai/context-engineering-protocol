"""Regression suite for wizard_auth.py (D24 §18.2b, locked). Stdlib unittest only. Run
with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_auth as wa  # noqa: E402


class TestTokenExchange(unittest.TestCase):
    def test_correct_token_mints_a_session(self):
        store = wa.SessionStore(bootstrap_token="test-token-123")
        session = store.exchange_token("test-token-123")
        self.assertIsNotNone(session)
        self.assertTrue(session.session_id)
        self.assertTrue(session.csrf_nonce)
        # Session id and CSRF nonce must never be the same value - they protect
        # different things and a shared value would let a CSRF check accidentally
        # pass using a leaked cookie.
        self.assertNotEqual(session.session_id, session.csrf_nonce)

    def test_wrong_token_is_rejected(self):
        store = wa.SessionStore(bootstrap_token="test-token-123")
        self.assertIsNone(store.exchange_token("wrong-token"))

    def test_empty_token_is_rejected(self):
        store = wa.SessionStore(bootstrap_token="test-token-123")
        self.assertIsNone(store.exchange_token(""))

    def test_token_is_single_use_replay_rejected(self):
        store = wa.SessionStore(bootstrap_token="test-token-123")
        first = store.exchange_token("test-token-123")
        self.assertIsNotNone(first)
        second = store.exchange_token("test-token-123")
        self.assertIsNone(second, "replaying the same valid token must be rejected")

    def test_wrong_guess_after_consumption_also_rejected_same_as_replay(self):
        """A caller must not be able to distinguish 'already consumed' from 'wrong
        token' from the return value alone - both are None."""
        store = wa.SessionStore(bootstrap_token="test-token-123")
        store.exchange_token("test-token-123")
        self.assertIsNone(store.exchange_token("test-token-123"))
        self.assertIsNone(store.exchange_token("something-else"))


class TestAuthenticateRequest(unittest.TestCase):
    def _store_with_session(self):
        store = wa.SessionStore(bootstrap_token="tok")
        session = store.exchange_token("tok")
        return store, session

    def test_valid_session_id_authenticates(self):
        store, session = self._store_with_session()
        result = store.authenticate_request(session.session_id)
        self.assertIsNotNone(result)
        self.assertEqual(result.session_id, session.session_id)

    def test_no_cookie_fails(self):
        store, _session = self._store_with_session()
        self.assertIsNone(store.authenticate_request(None))
        self.assertIsNone(store.authenticate_request(""))

    def test_unknown_session_id_fails(self):
        store, _session = self._store_with_session()
        self.assertIsNone(store.authenticate_request("not-a-real-session-id"))

    def test_idle_timeout_invalidates_session(self):
        store, session = self._store_with_session()
        # Directly age the session past the idle timeout rather than mocking
        # time.monotonic - this exercises the real comparison in
        # authenticate_request() against a real (if backdated) timestamp.
        session.last_seen_at -= wa.IDLE_TIMEOUT_SECONDS + 1
        self.assertIsNone(store.authenticate_request(session.session_id))

    def test_authenticate_request_bumps_last_seen_at(self):
        store, session = self._store_with_session()
        original = session.last_seen_at
        session.last_seen_at -= 60  # simulate a minute of prior idle time
        store.authenticate_request(session.session_id)
        self.assertGreater(session.last_seen_at, original - 60)

    def test_expired_session_cannot_be_revived_by_a_second_call(self):
        store, session = self._store_with_session()
        session.last_seen_at -= wa.IDLE_TIMEOUT_SECONDS + 1
        self.assertIsNone(store.authenticate_request(session.session_id))
        # The expired session must actually be gone, not just reported invalid once.
        self.assertIsNone(store.authenticate_request(session.session_id))


class TestCsrf(unittest.TestCase):
    def test_correct_nonce_passes(self):
        store = wa.SessionStore(bootstrap_token="tok")
        session = store.exchange_token("tok")
        self.assertTrue(store.check_csrf(session, session.csrf_nonce))

    def test_wrong_nonce_fails(self):
        store = wa.SessionStore(bootstrap_token="tok")
        session = store.exchange_token("tok")
        self.assertFalse(store.check_csrf(session, "wrong-nonce"))

    def test_missing_nonce_fails(self):
        store = wa.SessionStore(bootstrap_token="tok")
        session = store.exchange_token("tok")
        self.assertFalse(store.check_csrf(session, None))
        self.assertFalse(store.check_csrf(session, ""))

    def test_check_csrf_only_reads_its_explicit_argument(self):
        """check_csrf must never itself reach into a cookie or query string - the
        caller is responsible for extracting the header value. Proven here by calling
        it with a value that does NOT match the session's cookie-carried session_id,
        confirming session_id is never silently accepted as a stand-in nonce."""
        store = wa.SessionStore(bootstrap_token="tok")
        session = store.exchange_token("tok")
        self.assertFalse(store.check_csrf(session, session.session_id))


class TestSessionCookieHeader(unittest.TestCase):
    def test_cookie_header_has_required_flags(self):
        store = wa.SessionStore(bootstrap_token="tok")
        session = store.exchange_token("tok")
        header = store.session_cookie_header(session)
        self.assertIn(f"{wa.SESSION_COOKIE_NAME}={session.session_id}", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Strict", header)
        self.assertIn("Path=/", header)

    def test_cookie_header_never_carries_the_csrf_nonce(self):
        store = wa.SessionStore(bootstrap_token="tok")
        session = store.exchange_token("tok")
        header = store.session_cookie_header(session)
        self.assertNotIn(session.csrf_nonce, header)


if __name__ == "__main__":
    unittest.main()
