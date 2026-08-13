#!/usr/bin/env python3
"""Real, runnable Playwright evidence for the ult-cep-wizard UI walkthrough
used in case-studies/robotframework-wizard-ui/CASE-STUDY.md.

This is not a mock of the wizard's HTTP API: it drives the actual rendered
page in a real Chromium instance, clicking the same buttons a human would
click, exactly as case-studies/TEMPLATE.md and the approved case-study plan
require ("use playwrite to properly test the UI (wizard) if it works fine").

Usage:
    python wizard_playwright_walkthrough.py <exchange_url> <output_dir> [--prefix before|after]

<exchange_url> is the one-time /exchange?token=... URL printed by
wizard_server.py at launch. <output_dir> is where screenshots are written.
--prefix lets the same script be re-run twice against two separate server
launches (once before ult-autoscaffold-content has written any content,
once after) so the case study can show a genuine before/after pair.

Every stage prints a single JSON line to stdout describing what happened
(state observed, buttons clicked, any error text surfaced by the page)
so a human (or this session) can build an honest pass/fail table afterward
without re-reading screenshots by eye.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

REPORT = []


def log(stage, **kw):
    entry = {"stage": stage, **kw}
    REPORT.append(entry)
    print(json.dumps(entry), flush=True)


def wait_for_state(page, predicate, timeout_s=20, poll_s=0.25):
    """Poll the page's #status-json debug element or DOM markers until
    predicate(page) is true, or raise TimeoutError."""
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            if predicate(page):
                return True
        except Exception as e:  # noqa: BLE001 - diagnostic only
            last_err = e
        time.sleep(poll_s)
    raise TimeoutError(f"condition not met within {timeout_s}s (last_err={last_err})")


def fetch_state(page):
    """Hit the wizard's own /api/state endpoint from inside the page context
    (reuses the session cookie) — the authoritative state string, rather than
    inferring it from which DOM nodes happen to exist. Mirrors exactly what
    wizard.js's own loadState() does."""
    return page.evaluate(
        "() => fetch('/api/state').then(r => r.json())"
    )


def wait_for_onboarding_state(page, expected_states, timeout_s=25, poll_s=0.4):
    """Poll /api/state until state.state is one of expected_states. Returns
    the final state dict. Raises TimeoutError with the last-seen state on
    failure so callers can log it rather than silently mis-detect."""
    deadline = time.time() + timeout_s
    last_state = None
    while time.time() < deadline:
        last_state = fetch_state(page)
        if last_state.get("state") in expected_states:
            return last_state
        time.sleep(poll_s)
    raise TimeoutError(f"state never reached {expected_states}, last seen: {last_state}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exchange_url")
    ap.add_argument("output_dir")
    ap.add_argument("--prefix", default="run")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def shot(name):
        path = out_dir / f"{args.prefix}-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        log("screenshot", file=str(path.name))

    with sync_playwright() as p:
        # NOTE: this environment has the full Chromium build (chromium-1234)
        # installed but not the separate chrome-headless-shell binary
        # (its download is blocked by a corporate TLS-inspection proxy that
        # `playwright install` doesn't trust by default). channel="chromium"
        # forces Playwright to drive the full browser headlessly instead of
        # the headless-shell variant it would otherwise prefer.
        browser = p.chromium.launch(headless=True, channel="chromium")
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page_errors = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Capture every /api/* response's real status code + body so decision
        # staging / apply failures are visible even when the UI swallows or
        # overwrites the error text before a screenshot catches it.
        api_calls = []

        def on_response(resp):
            if "/api/" not in resp.url:
                return
            try:
                body = resp.text()
            except Exception:
                body = None
            entry = {"url": resp.url, "status": resp.status, "body": (body or "")[:500]}
            api_calls.append(entry)
            if resp.status >= 400:
                log("api_error_response", **entry)

        page.on("response", on_response)

        # --- Stage 0: open the one-time exchange URL ---------------------
        page.goto(args.exchange_url, wait_until="networkidle")
        log("opened_exchange_url", url=args.exchange_url)

        # After exchange, the server redirects to the app root with a
        # session cookie set. Give the initial /api/status fetch a moment.
        page.wait_for_timeout(500)
        title = page.title()
        log("page_loaded", title=title)

        # Detect which onboarding state we actually landed on by asking the
        # server's own /api/state endpoint (authoritative — matches exactly
        # what wizard.js's loadState() branches on), not DOM heuristics.
        initial = fetch_state(page)
        log("initial_state_detected", state=initial.get("state"), d20_initialized=initial.get("d20_initialized"))
        shot("01-initial-state")

        # --- Stage 1: needs_discover -> Run Discover ----------------------
        if initial.get("state") == "needs_discover":
            page.click("#discover-button")
            log("clicked_run_discover")
            try:
                final = wait_for_onboarding_state(
                    page, ["decisions_pending", "steady_state", "layout_broken"], timeout_s=30
                )
                log("discover_completed", state=final.get("state"))
                # Give the client-side loadState() poll a moment to re-render
                # the DOM sections for the new state before screenshotting.
                page.wait_for_timeout(700)
            except TimeoutError as e:
                log("discover_timeout", error=str(e))
            shot("02-after-discover")
        else:
            log("skipped_discover", reason=f"initial state was {initial.get('state')!r}, not needs_discover")

        # --- Stage 2: decisions_pending -> resolve every PENDING field ----
        # Deliberately routed through CUSTOM + the directory picker for
        # What-L2/How-L2 (rather than blindly clicking CONFIRM on whatever
        # discover proposed) so this run lands on genuinely EMPTY target
        # directories. discover's own CONFIRM candidates for this repo
        # (doc/, .github/) are both real, already-populated directories -
        # confirming those would never render ult-autoscaffold-content's
        # empty-case stub cards, which is the exact Phase D wiring this
        # case study exists to exercise. This also gives real UI coverage
        # of the picker flow itself, which a straight-CONFIRM run never
        # touches. See CASE-STUDY.md's "before/after redo" note.
        CUSTOM_TARGETS = {
            "What-L2": "docs/requirements",
            "How-L2": "org",
        }

        def use_picker(row, rel_path):
            """Click a row's 'Pick directory...' button, drive the picker to
            rel_path one path segment at a time via real clicks on the
            entries it renders, then click 'Use this directory'."""
            pick_btn = row.locator("button", has_text="Pick directory")
            pick_btn.click()
            page.wait_for_timeout(300)
            # The picker's browsed-to directory is a single module-level JS
            # variable shared across every field - it does NOT reset to the
            # repo root when a different field's "Pick directory..." is
            # clicked. Walk back up to root first so each call starts from
            # a known location, same as a human would via the Up button.
            up_button = page.locator("#picker-up")
            for _ in range(20):
                if up_button.get_attribute("disabled") is not None:
                    break
                up_button.click()
                page.wait_for_timeout(200)
            for segment in rel_path.split("/"):
                entry_btn = page.locator("#picker-entries button", has_text=segment)
                entry_btn.first.click()
                page.wait_for_timeout(300)
            current = page.locator("#picker-current-path").inner_text().strip()
            use_btn = page.locator("#picker-use-dir")
            use_btn.click()
            page.wait_for_timeout(300)
            return current

        rows = page.locator(".decision-row")
        n_rows = rows.count()
        resolved = []
        preferred_order = ["CONFIRM", "ACKNOWLEDGE", "SKIP", "DISABLE", "true", "false"]
        for i in range(n_rows):
            row = rows.nth(i)
            title_text = row.locator(".decision-title").inner_text() if row.locator(".decision-title").count() else f"row-{i}"
            custom_key = next((k for k in CUSTOM_TARGETS if title_text.startswith(k)), None)
            buttons = row.locator("button")
            btn_count = buttons.count()
            btn_texts = [buttons.nth(j).inner_text().strip() for j in range(btn_count)]
            if custom_key is not None and any(b.startswith("Pick directory") for b in btn_texts):
                target = CUSTOM_TARGETS[custom_key]
                landed_on = use_picker(row, target)
                resolved.append({"field": title_text, "verb": "CUSTOM", "target": target, "picker_landed_on": landed_on})
                page.wait_for_timeout(500)
                continue
            chosen = None
            for pref in preferred_order:
                if pref in btn_texts:
                    chosen = pref
                    break
            if chosen is None and btn_texts:
                if btn_texts[0].startswith("Pick directory"):
                    resolved.append({"field": title_text, "verb": None, "note": "CUSTOM-only field, left pending intentionally"})
                    continue
                chosen = btn_texts[0]
            if chosen is not None:
                idx = btn_texts.index(chosen)
                buttons.nth(idx).click()
                resolved.append({"field": title_text, "verb": chosen})
                page.wait_for_timeout(200)

        log("decisions_resolved", count=len(resolved), detail=resolved)
        shot("03-decisions-resolved")

        apply_btn = page.locator("#apply-button")
        if apply_btn.count():
            # The Apply button's disabled state is driven by an async
            # /api/decisions re-fetch triggered after each stage() call
            # (updateApplyButton runs once that promise resolves) - poll
            # rather than reading the attribute immediately, so a slow
            # final re-render isn't mistaken for "still has pending fields".
            try:
                wait_for_state(
                    page,
                    lambda pg: pg.locator("#apply-button").get_attribute("disabled") is None,
                    timeout_s=10,
                )
            except TimeoutError:
                pass
            disabled = apply_btn.get_attribute("disabled")
            log("apply_button_state", disabled=disabled is not None)
            if disabled is None:
                apply_btn.click()
                log("clicked_apply")
                try:
                    wait_for_state(
                        page,
                        lambda pg: bool((pg.locator("#apply-message").inner_text() or "").strip())
                        if pg.locator("#apply-message").count()
                        else False,
                        timeout_s=10,
                    )
                    log("apply_confirmed", message=page.locator("#apply-message").inner_text())
                except TimeoutError as e:
                    msg = page.locator("#apply-message").inner_text() if page.locator("#apply-message").count() else ""
                    log("apply_timeout", error=str(e), apply_message=msg)
            page.wait_for_timeout(500)
        else:
            log("no_apply_button_present")

        shot("04-steady-state")
        post_apply_state = fetch_state(page)
        log("post_apply_state", state=post_apply_state.get("state"))

        # --- Stage 3: steady_state boxes + What/How stub cards ------------
        stub_cards = page.locator(".stub-card")
        n_stub = stub_cards.count()
        stub_info = []
        for i in range(n_stub):
            card = stub_cards.nth(i)
            desc = card.locator(".stub-card-desc").inner_text() if card.locator(".stub-card-desc").count() else ""
            expected_path = card.locator(".stub-card-path").inner_text() if card.locator(".stub-card-path").count() else ""
            has_prompt = card.locator(".stub-card-prompt").count() > 0
            stub_info.append({"desc": desc, "expected_path": expected_path, "has_prompt_text": has_prompt})
        log("stub_cards_observed", count=n_stub, detail=stub_info)
        shot("05-boxes-and-stub-cards")

        # --- Stage 4: docs viewer nav --------------------------------------
        for nav_id, nav_name in [
            ("#nav-doc-protocol", "protocol"),
            ("#nav-doc-readme", "readme"),
            ("#nav-doc-case-studies", "case-studies"),
        ]:
            try:
                page.click(nav_id)
                page.wait_for_selector("#docs-overlay", state="visible", timeout=5000)
                page.wait_for_timeout(400)
                body_text_len = len(page.locator("#docs-overlay-body").inner_text())
                log("docs_nav_opened", doc=nav_name, body_chars=body_text_len)
                shot(f"06-docs-{nav_name}")
                page.click("#docs-overlay-close")
                page.wait_for_timeout(200)
            except PWTimeoutError as e:
                log("docs_nav_failed", doc=nav_name, error=str(e))

        log("page_errors", errors=page_errors)
        log("console_errors", errors=console_errors[:20])

        browser.close()

    report_path = out_dir / f"{args.prefix}-report.json"
    report_path.write_text(json.dumps(REPORT, indent=2), encoding="utf-8")
    print(f"\nWrote {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
