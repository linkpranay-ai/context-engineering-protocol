// wizard.js - vanilla JS for ult-cep-wizard's frontend. No bundler, no npm, no
// framework (D24 exit criterion 5's stdlib-only stance extends to the frontend as
// "no build step", even though JS itself isn't Python stdlib).
//
// Read-only endpoints, all session-cookie-gated server-side (this script never
// handles auth itself - a 401 here just means the session expired, see
// handleUnauthorized below):
//   GET /api/status    - the four-box view model (wizard_boxes.to_json_dict shape)
//   GET /api/picker?path=<rel> - directory listing (wizard_picker shape)
//   GET /api/decisions - every decision-bearing line's current state + artifact hash
//
// Phase 1 (D24 §18) write path, both session-cookie *and* CSRF-header gated
// (wizard_auth.CSRF_HEADER_NAME, read from the <meta name="wizard-csrf-token"> tag
// _handle_index embeds - never a cookie or query string, see postJson below):
//   POST /api/stage - stage a resolved verb (CONFIRM/CUSTOM/SKIP/DISABLE/
//                      ACKNOWLEDGE) onto one still-PENDING decision line
//   POST /api/apply - commit every currently-staged decision into
//                      context-config.yaml via confirm_layers.run_confirm; refuses
//                      (409) if the artifact changed since it was loaded
//
// The picker itself stays purely browse-only (clicking an entry navigates, nothing
// else) - selecting a directory *for* a decision is a separate, explicit action
// (see setTarget/"Use this directory" below), triggered from the decisions list, so
// browsing around never has a side effect on its own.
//
// Phase 2 (D24 §18.14) guided brownfield onboarding adds:
//   GET  /api/state   - the four-state onboarding router (wizard_onboarding_state
//                        shape). loadState() calls this first, on every page load,
//                        before anything else - it decides which of the state
//                        screens below is even shown. Never cached client-side,
//                        matching the server's own "everything read fresh" stance.
//   POST /api/discover - (re-)run ult-repo-layout's discover step in place
//                        (wizard_discover.run_discover). Refuses (409) if the
//                        artifact changed since it was loaded, or - the real reason
//                        this needs a confirm step - if any section has a staged-but
//                        -not-yet-Applied decision that a bare re-run would silently
//                        discard (409 with at_risk_sections; force:true proceeds and
//                        discards them, only after the user explicitly confirms).
//
// loadState()'s four screens: layout_broken (validation failed - minimal FAIL-lines
// screen, nothing else attempted), needs_discover (guide-only intro + a real Run
// Discover button), decisions_pending/steady_state (today's existing
// boxes/decisions/picker experience, unchanged - just reachable now). A
// d20_initialized=false flag is carried on every state but never picks the screen -
// on needs_discover it only swaps which of two guide-copy variants intros the
// (always-shared) Run Discover button (renderNeedsDiscover, greenfield vs.
// brownfield copy - see references/wizard-onboarding-state-machine.md), and on
// decisions_pending/steady_state it only toggles the small dismissible banner.
//
// UI design pass adds the top-bar docs viewer, wired once at startup rather than
// inside loadState() - these are CEP's own project docs, not part of the onboarding
// flow, so they're available regardless of which of the four states above is showing:
//   GET /api/docs      - the closed set of docs this install actually has bundled
//   GET /api/docs/<id> - one doc rendered to HTML (wizard_markdown.render server-side)
// Opening a doc replaces #main-content with #docs-overlay client-side only (never a
// real navigation - the wizard's /exchange URLs are single-use, so there's no second
// page to send a browser to). Docs this install doesn't have (e.g. a copy of this
// skill installed standalone, without PROTOCOL.md/case-studies/ alongside it) simply
// disable their nav button rather than erroring - see setDocsNavAvailability.
//
// Revised: the top bar itself now carries CEP's shared project identity (logo, full
// name, tagline), not this tool's own title - "Wizard" is just another nav button
// next to Protocol/README/Case Studies, and this tool's title+guide copy moved down
// into #main-content's own .page-header (see index.html). navigateDocs()/
// renderDocView()/docsBack() replace the old openDoc()/openCaseStudiesIndex() pair,
// adding a small in-overlay view history (docsBackStack) so a Back button can step
// back out of any doc to whatever was open before it - standing in for real browser
// history, which a single-use /exchange URL can't use either.
//
// "Case Studies" in the top bar navigates straight to case-studies/README.md's own
// rendered content now, not a client-built list (the old {kind: "case-studies-index"}
// view is gone) - and every relative Markdown link inside a rendered doc (to another
// case study, to SYNTHESIS.md/TEMPLATE.md, or to a heading anchor in PROTOCOL.md/
// README.md) becomes a real in-app navigation too, via wizard_markdown.py's
// link_resolver marking it with data-doc-id/-fragment instead of a real href - see
// the delegated click listener on #docs-overlay-body below. A link that doesn't
// resolve to a doc this install has (e.g. references/reproducibility-guide.md) is left
// as a real GitHub link that opens in a new tab instead, so it never dead-ends the SPA.

(function () {
  "use strict";

  function handleUnauthorized() {
    document.body.innerHTML =
      '<p style="padding:2rem;font-family:system-ui,sans-serif;">' +
      "Session expired or invalid. Restart the wizard and open the fresh " +
      "one-time link it prints.</p>";
  }

  function fetchJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (resp) {
      if (resp.status === 401) {
        handleUnauthorized();
        throw new Error("unauthorized");
      }
      return resp.json().then(function (body) {
        return { ok: resp.ok, status: resp.status, body: body };
      });
    });
  }

  // The nonce _handle_index embedded for *this* session - read once at load, same
  // value a fresh page load would hand a real browser. Never sent as a cookie or
  // query string, only this header (wizard_auth.CSRF_HEADER_NAME server-side).
  var CSRF_HEADER_NAME = "X-Wizard-CSRF-Token";
  var csrfMeta = document.querySelector('meta[name="wizard-csrf-token"]');
  var CSRF_TOKEN = csrfMeta ? csrfMeta.getAttribute("content") : "";

  function postJson(url, payload) {
    var headers = { "Content-Type": "application/json" };
    headers[CSRF_HEADER_NAME] = CSRF_TOKEN;
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: headers,
      body: JSON.stringify(payload || {}),
    }).then(function (resp) {
      if (resp.status === 401) {
        handleUnauthorized();
        throw new Error("unauthorized");
      }
      return resp.json().then(function (body) {
        return { ok: resp.ok, status: resp.status, body: body };
      });
    });
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (key === "text") {
          node.textContent = attrs[key];
        } else {
          node.setAttribute(key, attrs[key]);
        }
      });
    }
    (children || []).forEach(function (child) {
      node.appendChild(child);
    });
    return node;
  }

  // Where to point someone who asks "how do I turn L1 on" (observation: Phase 0 is
  // read-only by design - D24 §18.10 defers the write endpoint to Phase 1 - so the
  // only honest answer today is "edit context-config.yaml yourself", surfaced right
  // next to the L1 subsection it applies to instead of making them go find it.
  var L1_ENABLE_HINT = {
    "box-what": "Enable: set layers.what_l1.enabled: true in context-config.yaml.",
    "box-how": "Enable: set how_dimension.how_l1.enabled: true in context-config.yaml.",
  };

  function renderWhatHowBox(boxId, box) {
    var article = document.getElementById(boxId);
    var meta = article.querySelector(".box-meta");
    meta.textContent =
      "L2 " + (box.l2_enabled ? "on" : "off") +
      " · L1 " + (box.l1_enabled ? "on" : "off");

    ["L2", "L1"].forEach(function (layer) {
      var enabled = layer === "L2" ? box.l2_enabled : box.l1_enabled;
      var list = article.querySelector('.box-paths[data-layer="' + layer + '"]');
      var hint = article.querySelector('.layer-hint[data-layer="' + layer + '"]');
      var layerPaths = box.paths.filter(function (p) {
        return p.source === layer;
      });

      list.innerHTML = "";
      if (hint) {
        hint.textContent = !enabled && layer === "L1" ? L1_ENABLE_HINT[boxId] || "" : "";
      }

      if (!enabled) {
        list.appendChild(el("li", { class: "layer-empty", text: "Off." }));
        return;
      }
      if (layerPaths.length === 0) {
        list.appendChild(el("li", { class: "layer-empty", text: "On, nothing resolved yet." }));
        return;
      }
      layerPaths.forEach(function (p) {
        list.appendChild(el("li", { text: p.path }));
      });
    });
  }

  function renderAvailabilityBox(boxId, box, describe) {
    var article = document.getElementById(boxId);
    var meta = article.querySelector(".box-meta");
    article.classList.toggle("unavailable", !box.available);
    if (!box.available) {
      meta.textContent = box.unavailable_reason || "Not available.";
      return;
    }
    meta.textContent = describe(box);
  }

  function describeGuidelines(box) {
    if (box.initialized) {
      return "Resolved: " + box.resolved_paths.join(", ");
    }
    return "Not yet initialized. Default: " + box.default_path;
  }

  function describeTripwire(box) {
    var article = document.getElementById("box-tripwire");
    article.classList.toggle(
      "has-problems",
      Boolean(box.validation_problems && box.validation_problems.length)
    );
    var bits = [
      box.initialized ? "initialized" : "not yet initialized",
      box.entries + " entries",
      box.cursors + " cursors",
      box.rejected_sources + " rejected sources",
      box.hit_dispositions + " dispositions",
    ];
    if (box.validation_problems && box.validation_problems.length) {
      bits.push(box.validation_problems.length + " validation problem(s)");
    }
    return bits.join(", ");
  }

  // Guide-only "copy this prompt for your coding agent" cards
  // (wizard_stub_content.what_how_card/guidelines_card, D24 §18.14 section C) -
  // /api/status now appends a "stub_cards" list alongside the four boxes; this is
  // the only place that ever reads it. Each box article that can host one carries
  // an empty `.stub-card` slot in index.html - hidden whenever there's no card for
  // that box_title this time (e.g. once the box is actually populated).
  var STUB_CARD_BOX_IDS = {
    What: "box-what",
    How: "box-how",
    Guidelines: "box-guidelines",
  };

  function renderStubCards(stubCards) {
    var byTitle = {};
    (stubCards || []).forEach(function (card) {
      byTitle[card.box_title] = card;
    });
    Object.keys(STUB_CARD_BOX_IDS).forEach(function (title) {
      var article = document.getElementById(STUB_CARD_BOX_IDS[title]);
      if (!article) {
        return;
      }
      var slot = article.querySelector(".stub-card");
      if (!slot) {
        return;
      }
      var card = byTitle[title];
      slot.innerHTML = "";
      if (!card) {
        slot.style.display = "none";
        return;
      }
      slot.style.display = "";
      slot.appendChild(el("p", { class: "stub-card-desc", text: card.expect_description }));
      slot.appendChild(el("p", { class: "stub-card-path", text: "Expected: " + card.expected_path }));
      var pre = document.createElement("pre");
      pre.className = "stub-card-prompt";
      pre.textContent = card.prompt_text;
      slot.appendChild(pre);
      var copyButton = el("button", { type: "button", class: "secondary", text: "Copy prompt" });
      copyButton.addEventListener("click", function () {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(card.prompt_text);
        }
      });
      slot.appendChild(copyButton);
    });
  }

  function loadStatus() {
    fetchJson("/api/status").then(function (result) {
      if (!result.ok) {
        return;
      }
      var view = result.body;
      renderWhatHowBox("box-what", view.what);
      renderWhatHowBox("box-how", view.how);
      renderAvailabilityBox("box-guidelines", view.guidelines, describeGuidelines);
      renderAvailabilityBox("box-tripwire", view.tripwire, describeTripwire);
      renderStubCards(view.stub_cards);
    });
  }

  // ------------------------------------------------------------------------
  // Decisions (D24 Phase 1 write path)
  // ------------------------------------------------------------------------

  var latestArtifactHash = null;
  // The decision currently being pointed at a directory via the picker's "Use
  // this directory" button - null when no CUSTOM pick is in progress. Cleared
  // on every successful stage and on Apply, so a stale target never survives
  // past the decision it was set for.
  var currentTarget = null;

  function setApplyMessage(text, isError) {
    var message = document.getElementById("apply-message");
    message.textContent = text || "";
    message.classList.toggle("error", Boolean(isError));
  }

  function setTarget(field) {
    currentTarget = field;
    var info = document.getElementById("picker-target-info");
    var useButton = document.getElementById("picker-use-dir");
    info.textContent =
      'Picking a directory for "' + field.section_title + '" - navigate below, ' +
      'then click "Use this directory".';
    useButton.style.display = "";
  }

  function clearTarget() {
    currentTarget = null;
    document.getElementById("picker-target-info").textContent = "";
    document.getElementById("picker-use-dir").style.display = "none";
  }

  function stage(field, verb, arg) {
    var payload = {
      section_title: field.section_title,
      field_key: field.field_key,
      verb: verb,
      line_no: field.line_no,
    };
    if (arg !== null && arg !== undefined) {
      payload.arg = arg;
    }
    setApplyMessage("");
    postJson("/api/stage", payload).then(function (result) {
      if (!result.ok) {
        setApplyMessage((result.body && result.body.error) || "Could not stage that decision.", true);
        return;
      }
      clearTarget();
      loadDecisions();
    });
  }

  function renderDecisionRow(field) {
    var row = el("li", { class: "decision-row state-" + field.state });
    row.appendChild(el("p", { class: "decision-title", text: field.section_title }));
    row.appendChild(el("span", { class: "decision-state-badge", text: field.state }));
    if (field.raw_value && field.raw_value.trim()) {
      row.appendChild(el("p", { class: "decision-value", text: field.raw_value.trim() }));
    }
    if (field.comment) {
      row.appendChild(el("p", { class: "decision-comment", text: field.comment }));
    }

    if (field.state !== "confirmed" && field.allowed_verbs.length) {
      var actions = el("div", { class: "decision-actions" });
      field.allowed_verbs.forEach(function (verb) {
        if (verb === "CUSTOM") {
          var pickButton = el("button", { type: "button", text: "Pick directory…" });
          pickButton.addEventListener("click", function () {
            setTarget(field);
          });
          actions.appendChild(pickButton);
          return;
        }
        var button = el("button", { type: "button", text: verb });
        button.addEventListener("click", function () {
          stage(field, verb, null);
        });
        actions.appendChild(button);
      });
      row.appendChild(actions);
    }

    return row;
  }

  function updateApplyButton(fields) {
    var button = document.getElementById("apply-button");
    var hasFields = fields.length > 0;
    var allResolved = hasFields && fields.every(function (f) {
      return f.state !== "pending";
    });
    button.disabled = !allResolved;
  }

  function renderDecisions(fields) {
    var list = document.getElementById("decision-list");
    list.innerHTML = "";
    if (fields.length === 0) {
      list.appendChild(
        el("li", {
          class: "decision-empty",
          text: "No layout decisions yet - run ult-repo-layout's discover step first.",
        })
      );
    } else {
      fields.forEach(function (field) {
        list.appendChild(renderDecisionRow(field));
      });
    }
    updateApplyButton(fields);
  }

  function loadDecisions() {
    return fetchJson("/api/decisions").then(function (result) {
      if (!result.ok) {
        return;
      }
      latestArtifactHash = result.body.artifact_hash;
      renderDecisions(result.body.fields);
    });
  }

  function applyDecisions() {
    setApplyMessage("");
    postJson("/api/apply", { loaded_artifact_hash: latestArtifactHash }).then(function (result) {
      if (result.status === 409) {
        setApplyMessage(
          "The layout changed since this page loaded - reloading the latest state.",
          true
        );
        loadDecisions();
        return;
      }
      if (!result.ok) {
        var messages =
          (result.body && result.body.messages) ||
          [(result.body && result.body.error) || "Apply failed."];
        setApplyMessage(messages.join(" "), true);
        return;
      }
      setApplyMessage((result.body.messages || []).join(" ") || "Applied.", false);
      loadStatus();
      loadDecisions();
    });
  }

  var currentPath = ".";

  function loadPicker(relPath) {
    fetchJson("/api/picker?path=" + encodeURIComponent(relPath)).then(function (result) {
      var pathLabel = document.getElementById("picker-current-path");
      var upButton = document.getElementById("picker-up");
      var list = document.getElementById("picker-entries");
      list.innerHTML = "";

      if (!result.ok) {
        pathLabel.textContent = relPath;
        upButton.disabled = true;
        list.appendChild(
          el("li", { text: (result.body && result.body.error) || "Could not list this directory." })
        );
        return;
      }

      var data = result.body;
      currentPath = data.rel_path;
      pathLabel.textContent = data.rel_path;
      upButton.disabled = data.parent_rel_path === null;
      upButton.onclick = function () {
        if (data.parent_rel_path !== null) {
          loadPicker(data.parent_rel_path);
        }
      };

      data.entries.forEach(function (entry) {
        var button = el("button", { type: "button", text: entry.name });
        button.addEventListener("click", function () {
          loadPicker(entry.rel_path);
        });
        list.appendChild(el("li", null, [button]));
      });
    });
  }

  // ------------------------------------------------------------------------
  // Onboarding state router (D24 §18.14 section A) - the very first thing the
  // page does. Everything above this point (boxes/decisions/picker) is the
  // pre-existing Phase 0/1 experience, reachable only once GET /api/state
  // says the repo is actually ready for it.
  // ------------------------------------------------------------------------

  // Every top-level section any state might show. loadState() hides all of
  // these, then unhides only the ones the current state calls for - so a
  // stale section from a previous state (or the pre-JS default) never lingers.
  var ALL_STATE_SECTION_IDS = ["state-layout-broken", "state-needs-discover", "boxes", "decisions", "picker"];

  var SECTIONS_FOR_STATE = {
    layout_broken: ["state-layout-broken"],
    needs_discover: ["state-needs-discover"],
    decisions_pending: ["boxes", "decisions", "picker"],
    steady_state: ["boxes", "decisions", "picker"],
  };

  function showStateSections(ids) {
    ALL_STATE_SECTION_IDS.forEach(function (id) {
      var section = document.getElementById(id);
      if (!section) {
        return;
      }
      section.style.display = ids.indexOf(id) === -1 ? "none" : "";
    });
  }

  function renderLayoutBroken(state) {
    var list = document.getElementById("layout-broken-failures");
    list.innerHTML = "";
    (state.validate_failures || []).forEach(function (line) {
      list.appendChild(el("li", { text: line }));
    });
  }

  // Picks which of needs-discover-greenfield / needs-discover-brownfield intros
  // this repo. Purely which paragraph explains *why* Discover hasn't run yet -
  // the Run Discover button underneath is shared and unaffected either way.
  function renderNeedsDiscover(state) {
    var greenfield = document.getElementById("needs-discover-greenfield");
    var brownfield = document.getElementById("needs-discover-brownfield");
    if (!greenfield || !brownfield) {
      return;
    }
    var isGreenfield = !state.d20_initialized;
    greenfield.style.display = isGreenfield ? "" : "none";
    brownfield.style.display = isGreenfield ? "none" : "";
  }

  // Dismissed for the life of this page load only - reloading the page (or a
  // fresh session) shows the banner again until d20_initialized actually
  // becomes true. That's intentional: dismissing is "not now", not "never".
  var d20BannerDismissed = false;

  function updateD20Banner(state) {
    var banner = document.getElementById("d20-banner");
    if (!banner) {
      return;
    }
    var show =
      !d20BannerDismissed &&
      !state.d20_initialized &&
      (state.state === "decisions_pending" || state.state === "steady_state");
    banner.style.display = show ? "" : "none";
  }

  function loadState() {
    return fetchJson("/api/state").then(function (result) {
      if (!result.ok) {
        return;
      }
      var state = result.body;
      showStateSections(SECTIONS_FOR_STATE[state.state] || []);

      if (state.state === "layout_broken") {
        renderLayoutBroken(state);
        return;
      }
      document.getElementById("d20-banner").style.display = "none";
      if (state.state === "needs_discover") {
        renderNeedsDiscover(state);
        return;
      }
      // decisions_pending / steady_state: today's existing full experience,
      // byte-for-byte unchanged, just gated behind this router now.
      updateD20Banner(state);
      loadStatus();
      loadPicker(currentPath);
      loadDecisions();
    });
  }

  // ------------------------------------------------------------------------
  // UI-driven discover (D24 §18.14 section B) - POST /api/discover, same
  // freshness-hash + at-risk-sections guard wizard_discover.run_discover
  // enforces server-side. Two entry points share it: the needs_discover
  // screen's first-ever run (loaded_artifact_hash: null, nothing staged to
  // lose yet) and a "Re-run Discover…" affordance from the Decisions screen
  // itself, which is the case the at-risk guard actually exists for.
  // ------------------------------------------------------------------------

  function runDiscover(loadedHash, force) {
    return postJson("/api/discover", {
      loaded_artifact_hash: loadedHash,
      force: Boolean(force),
    });
  }

  function setDiscoverMessage(text, isError) {
    var message = document.getElementById("discover-message");
    if (!message) {
      return;
    }
    message.textContent = text || "";
    message.classList.toggle("error", Boolean(isError));
  }

  function setRerunDiscoverMessage(text, isError) {
    var message = document.getElementById("rerun-discover-message");
    if (!message) {
      return;
    }
    message.textContent = text || "";
    message.classList.toggle("error", Boolean(isError));
  }

  // ------------------------------------------------------------------------
  // Docs viewer (UI design pass) - see the module docstring above. Wired once
  // at startup, independent of loadState()'s four-screen router: these are
  // CEP's own project docs, not part of the onboarding flow.
  // ------------------------------------------------------------------------

  var docsList = [];

  // One entry per view the overlay can show: {kind: "doc", id, fragment}.
  // `fragment`, when present, is a heading id to scroll to once the doc's
  // HTML is in the DOM (set when navigating via an in-app link that pointed
  // at an anchor - see the data-doc-id click handler below). docsCurrentView
  // is whatever's on screen right now (null when the overlay is closed);
  // docsBackStack holds every view navigated away from this overlay session,
  // in visiting order, so Back can step through them one at a time - a small
  // in-page history, standing in for the real browser history a single-use
  // /exchange URL can't use (see the module docstring).
  var docsCurrentView = null;
  var docsBackStack = [];

  function setDocsNavAvailability() {
    var byId = {};
    docsList.forEach(function (d) {
      byId[d.id] = d;
    });

    [
      ["nav-doc-protocol", !!byId.protocol],
      ["nav-doc-readme", !!byId.readme],
      // "Case Studies" now navigates straight to case-studies/README.md's
      // rendered content (see nav-doc-case-studies's click handler below),
      // not an auto-generated list - so its availability tracks that one
      // doc, the same way the other two nav buttons track theirs.
      ["nav-doc-case-studies", !!byId["case-studies-readme"]],
    ].forEach(function (pair) {
      var button = document.getElementById(pair[0]);
      button.disabled = !pair[1];
      button.title = pair[1] ? "" : "Not available in this install.";
    });
  }

  function loadDocsNav() {
    fetchJson("/api/docs").then(function (result) {
      if (!result.ok) {
        return;
      }
      docsList = result.body.docs || [];
      setDocsNavAvailability();
    });
  }

  // Highlights whichever top-bar nav button matches what's on screen right
  // now: Wizard when the overlay is closed, the matching doc button when a
  // top-level doc is open, Case Studies for both the index and any case
  // study opened from it (there's no separate per-case-study nav button to
  // light up instead).
  function updateActiveNav() {
    var activeId = "nav-wizard";
    if (docsCurrentView && docsCurrentView.kind === "doc") {
      if (docsCurrentView.id === "protocol") {
        activeId = "nav-doc-protocol";
      } else if (docsCurrentView.id === "readme") {
        activeId = "nav-doc-readme";
      } else {
        // Every other doc id (case-studies-readme, case-studies-synthesis,
        // case-studies-template, case-study-*) lives under the Case
        // Studies section - there's no separate nav button for any of them.
        activeId = "nav-doc-case-studies";
      }
    }
    ["nav-wizard", "nav-doc-protocol", "nav-doc-readme", "nav-doc-case-studies"].forEach(
      function (id) {
        document
          .getElementById(id)
          .classList.toggle("topbar-nav-link-active", id === activeId);
      }
    );
  }

  function docsOverlayIsOpen() {
    return document.getElementById("docs-overlay").style.display !== "none";
  }

  function updateDocsBackButton() {
    document.getElementById("docs-overlay-back").style.display =
      docsBackStack.length > 0 ? "" : "none";
  }

  function showDocsOverlay(title) {
    document.getElementById("docs-overlay-title").textContent = title;
    document.getElementById("docs-overlay").style.display = "";
    document.getElementById("main-content").style.display = "none";
  }

  function closeDocsOverlay() {
    document.getElementById("docs-overlay").style.display = "none";
    document.getElementById("main-content").style.display = "";
    docsCurrentView = null;
    docsBackStack = [];
    updateActiveNav();
  }

  // Renders `view` into the overlay without touching docsBackStack - the
  // single place that actually draws a view, used both for forward
  // navigation (after navigateDocs pushes the old view) and for Back (which
  // pops instead of pushing). `view.kind` is always "doc" now - the
  // Case Studies section's landing content is case-studies/README.md's own
  // rendered HTML (doc id "case-studies-readme"), not a client-built list;
  // see wizard_docs.py for how that doc, its supporting SYNTHESIS.md/
  // TEMPLATE.md, and every individual case study all end up in the same
  // fetchable doc corpus.
  function renderDocView(view) {
    docsCurrentView = view;
    updateDocsBackButton();
    updateActiveNav();
    fetchJson("/api/docs/" + encodeURIComponent(view.id)).then(function (result) {
      if (!result.ok) {
        return;
      }
      showDocsOverlay(result.body.title);
      document.getElementById("docs-overlay-body").innerHTML = result.body.html;
      // A link rendered by wizard_markdown.py's link_resolver (e.g.
      // case-studies/README.md's own "../README.md#measured-impact" link)
      // may carry a fragment identifying a heading inside *this* doc -
      // scroll it into view once the HTML above is actually in the DOM.
      if (view.fragment) {
        var target = document.getElementById(view.fragment);
        if (target) {
          target.scrollIntoView();
        }
      }
    });
  }

  // Forward navigation: if the overlay is already open, the view it's
  // currently showing goes onto the back stack first, so Back can return to
  // it - whether this navigation came from the top bar (e.g. clicking
  // README while a case study is open) or from inside the overlay itself
  // (e.g. clicking a case study from the index).
  function navigateDocs(view) {
    if (docsOverlayIsOpen() && docsCurrentView) {
      docsBackStack.push(docsCurrentView);
    }
    renderDocView(view);
  }

  function docsBack() {
    if (docsBackStack.length === 0) {
      closeDocsOverlay();
      return;
    }
    renderDocView(docsBackStack.pop());
    updateDocsBackButton();
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadState();
    loadDocsNav();
    updateActiveNav();

    document.getElementById("nav-doc-protocol").addEventListener("click", function () {
      navigateDocs({ kind: "doc", id: "protocol" });
    });
    document.getElementById("nav-doc-readme").addEventListener("click", function () {
      navigateDocs({ kind: "doc", id: "readme" });
    });
    document.getElementById("nav-doc-case-studies").addEventListener("click", function () {
      navigateDocs({ kind: "doc", id: "case-studies-readme" });
    });
    document.getElementById("nav-wizard").addEventListener("click", function () {
      closeDocsOverlay();
    });
    document.getElementById("docs-overlay-back").addEventListener("click", function () {
      docsBack();
    });
    document.getElementById("docs-overlay-close").addEventListener("click", function () {
      closeDocsOverlay();
    });
    // Delegated (not per-link) since the overlay body's content is replaced
    // wholesale on every navigation - wizard_markdown.py's link_resolver
    // marks an in-app-navigable link with data-doc-id/-fragment instead of
    // a real href (see its docstring: single-use exchange-token URLs can't
    // support real page navigation), so clicking one routes through
    // navigateDocs exactly like the old case-study list buttons did.
    document.getElementById("docs-overlay-body").addEventListener("click", function (event) {
      var link = event.target.closest("[data-doc-id]");
      if (!link) {
        return;
      }
      event.preventDefault();
      navigateDocs({
        kind: "doc",
        id: link.dataset.docId,
        fragment: link.dataset.docFragment || null,
      });
    });

    document.getElementById("discover-button").addEventListener("click", function () {
      setDiscoverMessage("Running discover…");
      runDiscover(null, false).then(function (result) {
        if (!result.ok) {
          setDiscoverMessage((result.body && result.body.error) || "Discover failed.", true);
          return;
        }
        setDiscoverMessage("");
        loadState();
      });
    });

    document.getElementById("rerun-discover-button").addEventListener("click", function () {
      setRerunDiscoverMessage("");
      runDiscover(latestArtifactHash, false).then(function (result) {
        if (result.status === 409 && result.body && result.body.at_risk_sections) {
          var sections = result.body.at_risk_sections.join(", ");
          var confirmed = window.confirm(
            "Re-running discover would discard staged (not yet Applied) decisions " +
              "in: " + sections + ". Discard and re-run anyway?"
          );
          if (!confirmed) {
            setRerunDiscoverMessage("Re-run cancelled - staged decisions kept.", false);
            return;
          }
          runDiscover(latestArtifactHash, true).then(function (forced) {
            if (!forced.ok) {
              setRerunDiscoverMessage((forced.body && forced.body.error) || "Discover failed.", true);
              return;
            }
            setRerunDiscoverMessage("Discover re-run - decisions refreshed.", false);
            loadStatus();
            loadDecisions();
          });
          return;
        }
        if (result.status === 409) {
          setRerunDiscoverMessage(
            "The layout changed since this page loaded - reloading the latest state.",
            true
          );
          loadDecisions();
          return;
        }
        if (!result.ok) {
          setRerunDiscoverMessage((result.body && result.body.error) || "Discover failed.", true);
          return;
        }
        setRerunDiscoverMessage("Discover re-run - decisions refreshed.", false);
        loadStatus();
        loadDecisions();
      });
    });

    document.getElementById("d20-banner-done").addEventListener("click", function () {
      loadState();
    });

    document.getElementById("d20-banner-dismiss").addEventListener("click", function () {
      d20BannerDismissed = true;
      document.getElementById("d20-banner").style.display = "none";
    });

    document.getElementById("picker-use-dir").addEventListener("click", function () {
      if (!currentTarget) {
        return;
      }
      stage(currentTarget, "CUSTOM", currentPath);
    });

    document.getElementById("apply-button").addEventListener("click", function () {
      applyDecisions();
    });
  });
})();
