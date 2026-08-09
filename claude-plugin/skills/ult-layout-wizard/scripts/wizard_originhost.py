"""wizard_originhost.py - Origin/Referer/Host fail-closed validation for
ult-layout-wizard (D24 §18.2b, locked).

Two independent checks, both fail-closed (reject on any ambiguity, never
default-allow):

  1. **Host allowlist** - every request's `Host` header must match one of the
     addresses this server actually bound to, at the actual bound port. Built fresh at
     startup from the real bound port (never a hardcoded default), so a
     DNS-rebinding attack that points some other hostname at 127.0.0.1 is rejected by
     hostname mismatch even though the IP resolves correctly.
  2. **Origin/Referer presence** - any *mutating-shaped* request (state-changing
     method) missing both an `Origin` and a `Referer` header is rejected outright, and
     any header that *is* present must resolve to the same Host allowlist. Phase 0
     registers zero mutating routes, so this only exercises the reject path for now
     (there's nothing yet these headers are allowed to match) - the plumbing exists
     end-to-end so Phase 1's first write endpoint has nothing new to design here.

GET/HEAD requests are exempt from the Origin/Referer presence check (they shouldn't be
mutating in the first place; requiring these headers on every GET would also break a
user simply typing/pasting the wizard URL directly). Host validation applies to
*every* request, mutating or not - it's cheap and closes the DNS-rebinding gap
regardless of method.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def build_host_allowlist(port: int) -> frozenset:
    return frozenset(
        {
            f"127.0.0.1:{port}",
            f"localhost:{port}",
            f"[::1]:{port}",
        }
    )


def _matches_allowlist(netloc: Optional[str], allowlist: frozenset) -> bool:
    if not netloc:
        return False
    lowered = {h.lower() for h in allowlist}
    return netloc.strip().lower() in lowered


def host_is_allowed(host_header: Optional[str], allowlist: frozenset) -> bool:
    return _matches_allowlist(host_header, allowlist)


def _origin_or_referer_netloc(value: str) -> Optional[str]:
    """Extract the host:port portion of an Origin or Referer header value, or None if
    it doesn't parse as an absolute URL at all (fail closed - an unparseable value is
    treated the same as a mismatch, never skipped/ignored)."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return parsed.netloc or None


def request_is_allowed(
    method: str,
    host_header: Optional[str],
    origin_header: Optional[str],
    referer_header: Optional[str],
    allowlist: frozenset,
) -> bool:
    """The single entry point wizard_server.py calls per request. Fail-closed at every
    branch: any ambiguous or missing case returns False, never True."""
    if not host_is_allowed(host_header, allowlist):
        return False

    if method.upper() not in MUTATING_METHODS:
        return True

    if not origin_header and not referer_header:
        return False

    for header_value in (origin_header, referer_header):
        if not header_value:
            continue
        netloc = _origin_or_referer_netloc(header_value)
        if not _matches_allowlist(netloc, allowlist):
            return False

    return True
