#!/usr/bin/env python3
"""Manual Playwright verification for the What/How box file-listing UI added
in this pass (BoxPath.files/total_file_count/truncated -> wizard.js's
renderWhatHowBox nested <ul class="box-path-files">).

This is not a mock: it starts the real wizard_server.py in a background
thread against a synthetic fixture repo built specifically to exercise every
rendering case in one run - a populated multi-file path, a nested
subdirectory, a >40-file path (truncation), and a resolved-but-empty path -
then drives the *actual rendered page* in a real headless Chromium the same
way case-studies/robotframework-wizard-ui/wizard_playwright_walkthrough.py
already proved out for this project, clicking through discover/decisions to
steady_state and asserting DOM content against the fixture's known file
lists, not against the API response - the point is to confirm what a human
would actually see.

Usage (no arguments - fixture, server, and browser are all self-contained):
    python manual_playwright_box_files.py [output_dir]

Prints one JSON line per stage (mirrors wizard_playwright_walkthrough.py's
own log format) and writes screenshots + a final report.json to output_dir
(default: a manual_playwright_box_files-output/ directory next to this
script). Exits non-zero if any assertion fails.

Not part of the wizard-e2e CI job - see this pass's plan for why (a new
Playwright dependency in CI is a separate, bigger call left for later).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
import wizard_server as ws  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REPORT = []


def log(stage, **kw):
    entry = {"stage": stage, **kw}
    REPORT.append(entry)
    print(json.dumps(entry), flush=True)


# ---------------------------------------------------------------------------
# Fixture repo - same _make_valid_target_repo shape test_wizard_boxes.py uses
# (ult-repo-layout installed, a context_packages slot marker so the repo
# passes validate_layout.py's --validate), plus real files seeded under the
# What-L2/How-L2 default paths and the What-L1/How-L1 paths enabled via
# context-config.yaml - deliberately not routed through the decision
# picker, since the defaults already point at where we seeded content.
# ---------------------------------------------------------------------------

def find_real_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        marker = (
            candidate / ".github" / "skills" / "ult-repo-layout" / "scripts" / "validate_layout.py"
        )
        if marker.exists():
            return candidate
    raise RuntimeError("could not locate the context-engineering-oss repo root")


def install_skill(root: Path, skill_name: str, script_names) -> None:
    real_root = find_real_repo_root()
    real_skill_dir = real_root / ".github" / "skills" / skill_name
    skill_dir = root / ".github" / "skills" / skill_name
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_skill_dir / "SKILL.md", skill_dir / "SKILL.md")
    for script_name in script_names:
        shutil.copy(real_skill_dir / "scripts" / script_name, scripts_dir / script_name)


def write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_fixture_repo(root: Path) -> dict:
    """Builds the synthetic repo and returns the expected file lists keyed by
    box/layer, so the Playwright assertions below have a single source of
    truth to check the rendered DOM against."""
    install_skill(
        root,
        "ult-repo-layout",
        ["validate_layout.py", "discover_layers.py", "layout_decision_grammar.py", "confirm_layers.py"],
    )
    (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
    write(
        root / "contexts" / ".layout-slots.yaml",
        "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
    )
    # Enable What-L1/How-L1 alongside the always-on L2 defaults so both
    # boxes render a two-group (L2 + L1) listing, not just one.
    write(
        root / "context-config.yaml",
        "layers:\n  what_l1:\n    enabled: true\n    path: external/specs/\n"
        "how_dimension:\n  how_l1:\n    enabled: true\n    path: external/conventions/\n",
    )

    # What-L2 (docs/requirements/): a flat file + a nested subdirectory file.
    write(root / "docs" / "requirements" / "overview.md", "# overview\n")
    write(root / "docs" / "requirements" / "nested" / "detail.md", "# detail\n")
    what_l2_files = sorted(["overview.md", "nested/detail.md"], key=str.casefold)

    # What-L1 (external/specs/): a single file - the plain non-truncated,
    # non-nested case, for contrast with the other three.
    write(root / "external" / "specs" / "api-spec.md", "# api spec\n")
    what_l1_files = ["api-spec.md"]

    # How-L2 (org/): 45 files - exercises the >40 truncation path with a
    # real "+N more files" line, not just a unit-test mock.
    how_l2_files = []
    for i in range(45):
        name = f"convention-{i:02d}.md"
        write(root / "org" / name, "x")
        how_l2_files.append(name)
    how_l2_files.sort(key=str.casefold)

    # How-L1 (external/conventions/): resolved (directory exists) but
    # deliberately empty - the "(empty)" rendering case.
    (root / "external" / "conventions").mkdir(parents=True)

    return {
        "what_l2_path": "docs/requirements/",
        "what_l2_files": what_l2_files,
        "what_l1_path": "external/specs/",
        "what_l1_files": what_l1_files,
        "how_l2_path": "org/",
        "how_l2_files": how_l2_files,
        # No trailing slash here, unlike the L2/config-default paths above:
        # this one is resolved via the decision picker's CUSTOM verb (see
        # resolve_all_decisions/use_picker below), which stores the raw
        # picked path without appending one.
        "how_l1_path": "external/conventions",
        "how_l1_files": [],
    }


# ---------------------------------------------------------------------------
# Wizard driving helpers (same shape as wizard_playwright_walkthrough.py)
# ---------------------------------------------------------------------------


def fetch_state(page):
    return page.evaluate("() => fetch('/api/state').then(r => r.json())")


def wait_for_onboarding_state(page, expected_states, timeout_s=25, poll_s=0.4):
    deadline = time.time() + timeout_s
    last_state = None
    while time.time() < deadline:
        last_state = fetch_state(page)
        if last_state.get("state") in expected_states:
            return last_state
        time.sleep(poll_s)
    raise TimeoutError(f"state never reached {expected_states}, last seen: {last_state}")


# Opt-in L1 layer decision rows only ever offer `CUSTOM: <path> | DISABLE`
# (discover_layers.py's own grammar comment) - there is no plain "confirm the
# already-configured path" button, even though context-config.yaml above
# already points these at real seeded content. A title-prefix match routes
# these two rows through the directory picker instead of letting the generic
# preferred-verb resolver fall through to DISABLE, which would silently turn
# the layer back off and defeat the point of this fixture.
CUSTOM_TARGETS = {
    "What-L1": "external/specs",
    "How-L1": "external/conventions",
}


def use_picker(page, row, rel_path):
    """Click a row's 'Pick directory...' button, walk the picker to rel_path
    one segment at a time via real clicks, then confirm - same approach
    wizard_playwright_walkthrough.py already proved out for this UI."""
    row.locator("button", has_text="Pick directory").click()
    page.wait_for_timeout(300)
    up_button = page.locator("#picker-up")
    for _ in range(20):
        if up_button.get_attribute("disabled") is not None:
            break
        up_button.click()
        page.wait_for_timeout(200)
    for segment in rel_path.split("/"):
        page.locator("#picker-entries button", has_text=segment).first.click()
        page.wait_for_timeout(300)
    page.locator("#picker-use-dir").click()
    page.wait_for_timeout(300)


def resolve_all_decisions(page):
    """Generic verb resolution (same preference order
    wizard_playwright_walkthrough.py uses) for every row, except the two L1
    rows this fixture cares about staying enabled, which are routed through
    the picker at their known-good fixture path instead."""
    rows = page.locator(".decision-row")
    n_rows = rows.count()
    preferred_order = ["CONFIRM", "ACKNOWLEDGE", "SKIP", "DISABLE", "true", "false"]
    resolved = []
    for i in range(n_rows):
        row = rows.nth(i)
        title_text = (
            row.locator(".decision-title").inner_text()
            if row.locator(".decision-title").count()
            else f"row-{i}"
        )
        custom_key = next((k for k in CUSTOM_TARGETS if title_text.startswith(k)), None)
        buttons = row.locator("button")
        btn_texts = [buttons.nth(j).inner_text().strip() for j in range(buttons.count())]
        if custom_key is not None and any(b.startswith("Pick directory") for b in btn_texts):
            target = CUSTOM_TARGETS[custom_key]
            use_picker(page, row, target)
            resolved.append({"field": title_text, "verb": "CUSTOM", "target": target})
            page.wait_for_timeout(400)
            continue
        chosen = next((p for p in preferred_order if p in btn_texts), None)
        if chosen is None and btn_texts and not btn_texts[0].startswith("Pick directory"):
            chosen = btn_texts[0]
        if chosen is not None:
            buttons.nth(btn_texts.index(chosen)).click()
            resolved.append({"field": title_text, "verb": chosen})
            page.wait_for_timeout(200)
    return resolved


def extract_box_path_groups(page, box_id, layer):
    """Reads the rendered .box-path-group entries for one box/layer out of
    the live DOM - path header, file list, and whether a truncation line is
    present - as plain Python data, so assertions read like the fixture
    comparisons above rather than a wall of Playwright locator calls."""
    list_locator = page.locator(f'#{box_id} .box-paths[data-layer="{layer}"]')
    groups = list_locator.locator(".box-path-group")
    result = []
    for i in range(groups.count()):
        group = groups.nth(i)
        header = group.locator(".box-path-header").inner_text().strip()
        file_items = group.locator(".box-path-files > li")
        files = []
        truncated_note = None
        empty_note = None
        for j in range(file_items.count()):
            item = file_items.nth(j)
            cls = item.get_attribute("class") or ""
            text = item.inner_text().strip()
            if "box-path-truncated" in cls:
                truncated_note = text
            elif "box-path-empty" in cls:
                empty_note = text
            else:
                files.append(text)
        result.append(
            {"path": header, "files": files, "truncated_note": truncated_note, "empty_note": empty_note}
        )
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (Path(__file__).resolve().parent / "manual_playwright_box_files-output")
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="cep_wizard_box_files_fixture_")
    root = Path(tmp)
    expected = build_fixture_repo(root)
    log("fixture_built", root=str(root), expected_summary={
        k: (v if not isinstance(v, list) else f"{len(v)} files") for k, v in expected.items()
    })

    failures = []

    def check(name, condition, detail=None):
        entry = {"name": name, "passed": bool(condition)}
        if detail is not None:
            entry["detail"] = detail
        log("assertion", **entry)
        if not condition:
            failures.append(entry)

    server, session_store = ws.build_server(str(root))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    token = session_store.bootstrap_token
    exchange_url = f"http://127.0.0.1:{port}/exchange?token={token}"
    log("server_started", port=port)

    try:
        with sync_playwright() as p:
            # Same channel="chromium" workaround wizard_playwright_walkthrough.py
            # documents - this environment's proxy blocks the separate
            # chrome-headless-shell download, so drive the full browser headlessly.
            browser = p.chromium.launch(headless=True, channel="chromium")
            context = browser.new_context(viewport={"width": 1440, "height": 1200})
            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            def shot(name):
                path = out_dir / f"{name}.png"
                page.screenshot(path=str(path), full_page=True)
                log("screenshot", file=str(path.name))

            page.goto(exchange_url, wait_until="networkidle")
            page.wait_for_timeout(500)
            initial = fetch_state(page)
            log("initial_state_detected", state=initial.get("state"))
            shot("01-initial-state")

            if initial.get("state") == "needs_discover":
                page.click("#discover-button")
                log("clicked_run_discover")
                state = wait_for_onboarding_state(page, ["decisions_pending", "steady_state", "layout_broken"], timeout_s=30)
                log("discover_completed", state=state.get("state"))
                page.wait_for_timeout(700)
            else:
                state = initial
            shot("02-after-discover")

            if state.get("state") == "decisions_pending":
                resolved = resolve_all_decisions(page)
                log("decisions_resolved", count=len(resolved), detail=resolved)
                page.wait_for_timeout(300)
                apply_btn = page.locator("#apply-button")
                if apply_btn.count() and apply_btn.get_attribute("disabled") is None:
                    apply_btn.click()
                    log("clicked_apply")
                page.wait_for_timeout(700)

            final_state = fetch_state(page)
            log("final_state", state=final_state.get("state"))
            check("reached_steady_state", final_state.get("state") == "steady_state", final_state.get("state"))
            shot("03-steady-state-boxes")

            # --- What box -----------------------------------------------------
            what_groups = extract_box_path_groups(page, "box-what", "L2")
            what_l2 = next((g for g in what_groups if g["path"] == expected["what_l2_path"]), None)
            check("what_l2_group_present", what_l2 is not None)
            if what_l2:
                check(
                    "what_l2_files_match",
                    sorted(what_l2["files"], key=str.casefold) == expected["what_l2_files"],
                    {"got": what_l2["files"], "want": expected["what_l2_files"]},
                )
                check("what_l2_not_truncated", what_l2["truncated_note"] is None)

            what_l1_groups = extract_box_path_groups(page, "box-what", "L1")
            what_l1 = next((g for g in what_l1_groups if g["path"] == expected["what_l1_path"]), None)
            check("what_l1_group_present", what_l1 is not None)
            if what_l1:
                check("what_l1_files_match", what_l1["files"] == expected["what_l1_files"], what_l1["files"])

            # --- How box (truncation + resolved-but-empty) --------------------
            how_l2_groups = extract_box_path_groups(page, "box-how", "L2")
            how_l2 = next((g for g in how_l2_groups if g["path"] == expected["how_l2_path"]), None)
            check("how_l2_group_present", how_l2 is not None)
            if how_l2:
                check("how_l2_shows_40_files", len(how_l2["files"]) == 40, len(how_l2["files"]))
                check(
                    "how_l2_files_are_first_40_alphabetically",
                    how_l2["files"] == expected["how_l2_files"][:40],
                )
                check(
                    "how_l2_truncation_note_shows_real_remainder",
                    how_l2["truncated_note"] == "+5 more files",
                    how_l2["truncated_note"],
                )

            how_l1_groups = extract_box_path_groups(page, "box-how", "L1")
            how_l1 = next((g for g in how_l1_groups if g["path"] == expected["how_l1_path"]), None)
            check("how_l1_group_present", how_l1 is not None)
            if how_l1:
                check("how_l1_renders_empty_note", how_l1["empty_note"] == "(empty)", how_l1["empty_note"])
                check("how_l1_has_no_files", how_l1["files"] == [])

            log("page_errors", errors=page_errors)
            check("no_page_errors", page_errors == [], page_errors)

            browser.close()
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(REPORT, indent=2), encoding="utf-8")
    print(f"\nWrote {report_path}", file=sys.stderr)

    if failures:
        print(f"\n{len(failures)} assertion(s) FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f['name']}: {f.get('detail')}", file=sys.stderr)
        sys.exit(1)
    print(f"\nAll {sum(1 for e in REPORT if e['stage'] == 'assertion')} assertions passed.", file=sys.stderr)


if __name__ == "__main__":
    main()
