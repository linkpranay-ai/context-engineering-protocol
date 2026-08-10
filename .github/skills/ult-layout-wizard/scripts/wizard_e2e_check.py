#!/usr/bin/env python3
"""wizard_e2e_check.py - CI-only driver for the `wizard-e2e` job (D24 §18.10 exit
criterion 3, build-order step 6).

**Not part of the shipped skill.** Nothing under `.github/skills/ult-layout-wizard/`
imports this module and it is not listed in SKILL.md - it exists solely so
`ci.yml`'s `wizard-e2e` job has one real script to invoke per target repo, instead of
inlining Python in YAML. Uses stdlib `urllib.request` only, matching this project's
general no-Selenium/no-Playwright stance for a Phase-0 read-only server (see the
implementation plan's own §3 point 3 reasoning) - "headless-CI" here just means "drive
the real HTTP API directly," no browser involved.

**Why every target repo still gets `--stamp-minimal-install` (updated for Phase 2,
§18.14 - the original reason below no longer applies but the stamp itself is still
worth doing):** originally, `wizard_preflight.py`'s old check 2 (`_check_initialized`,
retired in Phase 2 - see `wizard_preflight.py`'s own module docstring for why it tested
the wrong axis) refused to start the server at all against a repo with zero
`.layout-slots.yaml` markers - including this repo itself, which never ran
`ult-repo-layout init` on itself. Preflight no longer gates on that (a repo with only
`ult-repo-layout` *installed* now binds and serves a real `needs_discover`/
`layout_broken` screen instead of refusing to start), so the stamp is no longer load-
bearing for the server to come up at all. It is kept anyway because it is still the
cheapest way to give the two external target repos *some* real, resolvable
`what`/`how`/`context_packages` content to report through `/api/status` and
`/api/picker` - without it, "run the wizard against 3 real repos" would mostly be
exercising the `needs_discover` screen, not the boxes/picker this job actually checks.
The two external repos' `docs/requirements/`/`org/` paths still won't exist (they were
never written with CEP in mind), so `what`/`how` correctly report empty, exactly as R6
in the implementation plan anticipated - it's the *reason* they're empty (foreign repo,
no matching directories) that this script confirms, not an assumption.

Usage:
    python wizard_e2e_check.py <repo_root> --label <name> [--stamp-minimal-install]

Exits 0 with a per-box summary on success; exits 1 with a specific failure reason
otherwise. Never touches anything outside `<repo_root>` and never commits/persists the
stamp - the CI runner's clone is thrown away at the end of the job either way.
"""

from __future__ import annotations

import argparse
import http.client
import json
import shutil
import sys
import threading
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

THIS_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
SELF_REPO_LAYOUT_SKILL = THIS_REPO_ROOT / ".github" / "skills" / "ult-repo-layout"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wizard_server  # noqa: E402


def _copy_if_distinct(src: Path, dst: Path) -> None:
    """For the "self" e2e case, `repo_root` IS the checkout this script lives in -
    `SELF_REPO_LAYOUT_SKILL` and the stamp target resolve to the exact same file, and
    `ult-repo-layout` is already genuinely installed there (this repo ships it), so
    there is nothing to stamp. `shutil.copy` raises `SameFileError` rather than
    treating that as a no-op, so it's checked explicitly instead of letting the whole
    job fail on the one case where "already present" is the correct, expected state."""
    if src.resolve() == dst.resolve():
        return
    shutil.copy(src, dst)


def stamp_minimal_install(repo_root: Path) -> None:
    """Same recipe as test_wizard_server.py's `_make_valid_target_repo` fixture,
    applied to a real (possibly foreign) repo checkout instead of a throwaway tempdir.
    Only ever adds files under `.github/skills/` and `contexts/` - never touches or
    overwrites anything the target repo already has, and this process's checkout is
    discarded at the end of the CI job regardless."""
    skill_dir = repo_root / ".github" / "skills" / "ult-repo-layout"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    _copy_if_distinct(SELF_REPO_LAYOUT_SKILL / "SKILL.md", skill_dir / "SKILL.md")
    _copy_if_distinct(
        SELF_REPO_LAYOUT_SKILL / "scripts" / "validate_layout.py",
        scripts_dir / "validate_layout.py",
    )
    _copy_if_distinct(
        SELF_REPO_LAYOUT_SKILL / "scripts" / "discover_layers.py",
        scripts_dir / "discover_layers.py",
    )
    # discover_layers.py imports this (extracted alongside confirm_layers.py's shared
    # vocabulary, D24 v5 SS18 Phase 1 prep) - without it, discover_layers fails to
    # import on any *external* target repo (it never fails on this repo itself, since
    # here the two files already sit side by side), which crashes the request handler
    # mid-response and surfaces client-side as http.client.RemoteDisconnected, not as
    # any obvious import error. Keep this copy in lockstep with
    # test_wizard_server.py's _make_valid_target_repo fixture, which this function's
    # own docstring already promises to mirror.
    _copy_if_distinct(
        SELF_REPO_LAYOUT_SKILL / "scripts" / "layout_decision_grammar.py",
        scripts_dir / "layout_decision_grammar.py",
    )
    # wizard_layout_source.LayoutSource's module import also reaches for
    # confirm_layers.py directly (not just discover_layers.py) - same failure mode as
    # the layout_decision_grammar.py gap above if it's missing on the target repo.
    _copy_if_distinct(
        SELF_REPO_LAYOUT_SKILL / "scripts" / "confirm_layers.py",
        scripts_dir / "confirm_layers.py",
    )
    (repo_root / ".github" / "skills" / "ult-context-generate").mkdir(
        parents=True, exist_ok=True
    )
    slots_dir = repo_root / "contexts"
    slots_dir.mkdir(parents=True, exist_ok=True)
    (slots_dir / ".layout-slots.yaml").write_text(
        "slots:\n  - slot: context_packages\n    kind: directory\n"
        "    schema_version: 1\n",
        encoding="utf-8",
    )


def _fetch(url: str, cookie: str | None = None) -> tuple[int, bytes, http.client.HTTPMessage]:
    req = urllib.request.Request(url)
    if cookie:
        req.add_header("Cookie", f"wizard_session={cookie}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), resp.headers
    except HTTPError as exc:
        return exc.code, exc.read(), exc.headers


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """Same fix as test_wizard_server.py's own `_NoRedirect` - stops urllib from
    auto-following (or raising on) the 302 from /exchange, so this script can read the
    redirect response itself (status + Set-Cookie) rather than whatever it redirects
    to."""

    def http_response(self, request, response):
        return response


def run_case(repo_root: Path, label: str, stamp: bool) -> bool:
    print(f"\n=== {label} ({repo_root}) ===")
    if stamp:
        stamp_minimal_install(repo_root)
        print("  stamped minimal ult-repo-layout install (CI-scratch only, not committed)")

    try:
        server, session_store = wizard_server.build_server(str(repo_root))
    except Exception as exc:  # noqa: BLE001 - report any preflight/startup failure plainly
        print(f"  FAIL: server did not start: {exc}")
        return False

    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"

        opener = urllib.request.build_opener(_NoRedirect())
        token = session_store.bootstrap_token
        req = urllib.request.Request(f"{base}/exchange?token={token}")
        with opener.open(req) as resp:
            set_cookie = resp.headers.get("Set-Cookie")
        if not set_cookie:
            print("  FAIL: /exchange did not set a session cookie")
            return False
        cookie = set_cookie.split(";")[0].split("=", 1)[1]

        status_code, body, _ = _fetch(f"{base}/api/status", cookie=cookie)
        if status_code != 200:
            print(f"  FAIL: /api/status returned {status_code}")
            return False
        payload = json.loads(body.decode("utf-8"))
        # Phase 2 (D24 §18.14) added "stub_cards" to this payload (wizard_stub_content
        # cards, computed from the same what/how/guidelines the other four keys
        # already cover) - included here so this check stays exact rather than
        # silently accepting whatever extra keys show up.
        expected_keys = {"what", "how", "guidelines", "tripwire", "stub_cards"}
        if set(payload.keys()) != expected_keys:
            print(f"  FAIL: /api/status keys {set(payload.keys())} != {expected_keys}")
            return False
        what_paths = [p["path"] for p in payload["what"].get("paths", [])]
        how_paths = [p["path"] for p in payload["how"].get("paths", [])]
        print(
            f"  /api/status OK - what.paths={what_paths}, how.paths={how_paths}, "
            f"guidelines.available={payload['guidelines']['available']}, "
            f"tripwire.available={payload['tripwire']['available']}"
        )

        picker_code, picker_body, _ = _fetch(f"{base}/api/picker?path=.", cookie=cookie)
        if picker_code != 200:
            print(f"  FAIL: /api/picker returned {picker_code}")
            return False
        picker_payload = json.loads(picker_body.decode("utf-8"))
        if "entries" not in picker_payload:
            print("  FAIL: /api/picker response missing 'entries'")
            return False
        print(f"  /api/picker OK - {len(picker_payload['entries'])} top-level entries")

        print(f"  PASS: {label}")
        return True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root")
    parser.add_argument("--label", required=True)
    parser.add_argument("--stamp-minimal-install", action="store_true")
    args = parser.parse_args(argv)

    ok = run_case(Path(args.repo_root).resolve(), args.label, args.stamp_minimal_install)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
