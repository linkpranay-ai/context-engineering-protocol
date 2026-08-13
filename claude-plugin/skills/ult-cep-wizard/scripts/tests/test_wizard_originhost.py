"""Regression suite for wizard_originhost.py (D24 §18.2b, locked). Stdlib unittest
only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_originhost as woh  # noqa: E402

PORT = 54321
ALLOWLIST = woh.build_host_allowlist(PORT)


class TestBuildHostAllowlist(unittest.TestCase):
    def test_allowlist_contains_all_three_loopback_forms(self):
        allowlist = woh.build_host_allowlist(PORT)
        self.assertIn(f"127.0.0.1:{PORT}", allowlist)
        self.assertIn(f"localhost:{PORT}", allowlist)
        self.assertIn(f"[::1]:{PORT}", allowlist)

    def test_allowlist_does_not_contain_a_different_port(self):
        allowlist = woh.build_host_allowlist(PORT)
        self.assertNotIn(f"127.0.0.1:{PORT + 1}", allowlist)


class TestHostIsAllowed(unittest.TestCase):
    def test_exact_match_allowed(self):
        self.assertTrue(woh.host_is_allowed(f"127.0.0.1:{PORT}", ALLOWLIST))

    def test_case_insensitive_match_allowed(self):
        self.assertTrue(woh.host_is_allowed(f"LOCALHOST:{PORT}", ALLOWLIST))

    def test_missing_host_header_rejected(self):
        self.assertFalse(woh.host_is_allowed(None, ALLOWLIST))
        self.assertFalse(woh.host_is_allowed("", ALLOWLIST))

    def test_wrong_port_rejected(self):
        self.assertFalse(woh.host_is_allowed(f"127.0.0.1:{PORT + 1}", ALLOWLIST))

    def test_dns_rebinding_style_hostname_rejected(self):
        """A hostname that isn't in the allowlist but still resolves to 127.0.0.1 via
        attacker-controlled DNS must be rejected on the Host string itself - this
        function never does its own DNS resolution, so an unfamiliar hostname is
        rejected regardless of what it would resolve to."""
        self.assertFalse(woh.host_is_allowed(f"evil.example.com:{PORT}", ALLOWLIST))

    def test_bare_ip_without_port_rejected(self):
        self.assertFalse(woh.host_is_allowed("127.0.0.1", ALLOWLIST))


class TestRequestIsAllowedNonMutating(unittest.TestCase):
    def test_get_with_good_host_and_no_origin_referer_allowed(self):
        self.assertTrue(
            woh.request_is_allowed(
                method="GET",
                host_header=f"127.0.0.1:{PORT}",
                origin_header=None,
                referer_header=None,
                allowlist=ALLOWLIST,
            )
        )

    def test_get_with_bad_host_rejected(self):
        self.assertFalse(
            woh.request_is_allowed(
                method="GET",
                host_header="evil.example.com",
                origin_header=None,
                referer_header=None,
                allowlist=ALLOWLIST,
            )
        )

    def test_head_treated_same_as_get(self):
        self.assertTrue(
            woh.request_is_allowed(
                method="HEAD",
                host_header=f"localhost:{PORT}",
                origin_header=None,
                referer_header=None,
                allowlist=ALLOWLIST,
            )
        )


class TestRequestIsAllowedMutating(unittest.TestCase):
    def test_post_with_good_host_but_no_origin_or_referer_rejected(self):
        self.assertFalse(
            woh.request_is_allowed(
                method="POST",
                host_header=f"127.0.0.1:{PORT}",
                origin_header=None,
                referer_header=None,
                allowlist=ALLOWLIST,
            )
        )

    def test_post_with_matching_origin_allowed(self):
        self.assertTrue(
            woh.request_is_allowed(
                method="POST",
                host_header=f"127.0.0.1:{PORT}",
                origin_header=f"http://127.0.0.1:{PORT}",
                referer_header=None,
                allowlist=ALLOWLIST,
            )
        )

    def test_post_with_matching_referer_allowed(self):
        self.assertTrue(
            woh.request_is_allowed(
                method="POST",
                host_header=f"127.0.0.1:{PORT}",
                origin_header=None,
                referer_header=f"http://127.0.0.1:{PORT}/",
                allowlist=ALLOWLIST,
            )
        )

    def test_post_with_cross_origin_origin_header_rejected(self):
        self.assertFalse(
            woh.request_is_allowed(
                method="POST",
                host_header=f"127.0.0.1:{PORT}",
                origin_header="http://evil.example.com",
                referer_header=None,
                allowlist=ALLOWLIST,
            )
        )

    def test_post_with_unparseable_origin_rejected_not_skipped(self):
        """A malformed Origin header must fail closed, not be treated as absent."""
        self.assertFalse(
            woh.request_is_allowed(
                method="POST",
                host_header=f"127.0.0.1:{PORT}",
                origin_header="null",
                referer_header=None,
                allowlist=ALLOWLIST,
            )
        )

    def test_post_with_matching_origin_but_bad_host_still_rejected(self):
        """Host allowlist check applies even when Origin looks fine."""
        self.assertFalse(
            woh.request_is_allowed(
                method="POST",
                host_header="evil.example.com",
                origin_header=f"http://127.0.0.1:{PORT}",
                referer_header=None,
                allowlist=ALLOWLIST,
            )
        )

    def test_put_and_delete_and_patch_are_all_treated_as_mutating(self):
        for method in ("PUT", "DELETE", "PATCH"):
            with self.subTest(method=method):
                self.assertFalse(
                    woh.request_is_allowed(
                        method=method,
                        host_header=f"127.0.0.1:{PORT}",
                        origin_header=None,
                        referer_header=None,
                        allowlist=ALLOWLIST,
                    )
                )


if __name__ == "__main__":
    unittest.main()
