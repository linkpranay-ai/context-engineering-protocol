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
        var group = el("li", { class: "box-path-group" });
        group.appendChild(el("span", { class: "box-path-header", text: p.path }));

        var files = el("ul", { class: "box-path-files" });
        if (p.files.length === 0) {
          // Distinct from the "On, nothing resolved yet." case above: this path
          // *did* resolve, it just has no files under it yet - the exact
          // "resolved but empty" state a first-time user needs to be able to
          // tell apart from "nothing is wired up here at all."
          files.appendChild(el("li", { class: "box-path-empty", text: "(empty)" }));
        } else {
          p.files.forEach(function (f) {
            files.appendChild(el("li", { text: f }));
          });
          if (p.truncated) {
            var remaining = p.total_file_count - p.files.length;
            files.appendChild(
              el("li", { class: "box-path-truncated", text: "+" + remaining + " more files" })
            );
          }
        }
        group.appendChild(files);
        list.appendChild(group);
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
  // (wizard_stub_content.what_how_card/guidelines_card/tripwire_card, D24 §18.14
  // section C) - /api/status now appends a "stub_cards" list alongside the four
  // boxes; this is the only place that ever reads it. Each of the four box
  // articles carries an empty `.stub-card` slot in index.html - hidden whenever
  // there's no card for that box_title this time (e.g. once the box is actually
  // populated, or - Trip-wire only - once it has real ledger entries).
  var STUB_CARD_BOX_IDS = {
    What: "box-what",
    How: "box-how",
    Guidelines: "box-guidelines",
    "Trip-wire": "box-tripwire",
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
      ["nav-doc-concept", !!byId.concept],
      ["nav-doc-protocol", !!byId.protocol],
      ["nav-doc-readme", !!byId.readme],
      // "Case Studies" now navigates straight to case-studies/README.md's
      // rendered content (see nav-doc-case-studies's click handler below),
      // not an auto-generated list - so its availability tracks that one
      // doc, the same way the other two nav buttons track theirs.
      ["nav-doc-case-studies", !!byId["case-studies-readme"]],
      ["nav-doc-faq", !!byId.faq],
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
      if (docsCurrentView.id === "concept") {
        activeId = "nav-doc-concept";
      } else if (docsCurrentView.id === "protocol") {
        activeId = "nav-doc-protocol";
      } else if (docsCurrentView.id === "readme") {
        activeId = "nav-doc-readme";
      } else if (docsCurrentView.id === "faq") {
        activeId = "nav-doc-faq";
      } else {
        // Every other doc id (case-studies-readme, case-studies-synthesis,
        // case-studies-template, case-study-*) lives under the Case
        // Studies section - there's no separate nav button for any of them.
        activeId = "nav-doc-case-studies";
      }
    } else if (retrofitOverlayIsOpen()) {
      activeId = "nav-retrofit";
    }
    ["nav-wizard", "nav-doc-concept", "nav-doc-protocol", "nav-doc-readme", "nav-doc-case-studies", "nav-doc-faq", "nav-retrofit"].forEach(
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
      // #docs-overlay is a normal in-flow block (replaces #main-content, not
      // a fixed-position/own-scroll panel - see wizard.css's comment on
      // .docs-overlay), so the *window* is what's scrolled while reading a
      // long doc like case-studies/README.md. Without resetting that here,
      // navigating to a new doc (e.g. clicking a case study from partway
      // down the index) left the window at its old scrollY, landing the
      // freshly-rendered doc's content mid-page instead of at its top.
      // Default to the top of the overlay; a link's own fragment (see
      // below) then overrides that to a heading further down *within* the
      // doc that was just rendered.
      document.getElementById("docs-overlay").scrollIntoView({ block: "start" });
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
    if (retrofitOverlayIsOpen()) {
      closeRetrofitOverlay();
    }
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

  // ------------------------------------------------------------------------
  // Journey 3 (consumer/retrofit) Phase A+B - inventory view (Phase A,
  // read-only, over GET /api/retrofit/inventory) plus selection/draft
  // (Phase B, over POST /api/retrofit/select, POST /api/retrofit/draft,
  // POST /api/retrofit/draft-override, GET /api/retrofit/state, GET
  // /api/retrofit/contract-locations). Orthogonal to loadState()'s four-
  // screen router (see index.html's comment on #retrofit-overlay): opening/
  // closing this overlay never touches showStateSections. Independent
  // picker state (retrofitCurrentPath) so browsing here never disturbs the
  // layout-decisions picker's own currentPath/currentTarget above.
  //
  // Contract pre-check rule mirrors ult-cep-retrofit/SKILL.md Step 4 exactly:
  // code_related -> CONSUMING-COMPILED-GUIDELINES.md + CONSUMING-CODE-GRAPH.md;
  // task_related -> CONSUMING-CONTEXT-PACKAGE.md; neither -> no default. A unit
  // that's both gets all three pre-checked. A prior staged selection (from
  // RETROFIT-STATE.json, rehydrated via GET /api/retrofit/state on every
  // inventory load) always wins over this recommend()-based default when one
  // exists - a human decision, once made, is never silently overridden by a
  // re-render.
  //
  // No LLM in the loop (Journey 3 plan's own scope decision): every drafted
  // sentence (wizard_retrofit_draft.py) is a fixed template with the
  // resolved reference substituted in, always shown in an editable textarea
  // (change events POST to /api/retrofit/draft-override) - never treated as
  // final without a human looking at it.
  // ------------------------------------------------------------------------

  var CONTRACT_CODE = ["CONSUMING-COMPILED-GUIDELINES.md", "CONSUMING-CODE-GRAPH.md"];
  var CONTRACT_TASK = ["CONSUMING-CONTEXT-PACKAGE.md"];
  var ALL_CONTRACTS = CONTRACT_TASK.concat(CONTRACT_CODE);

  var retrofitCurrentPath = ".";
  // Last GET /api/retrofit/state response - the durable source of truth for
  // what's staged, refreshed at the top of every loadRetrofitInventory() and
  // updated in place after every select/draft/draft-override so a re-render
  // (e.g. re-expanding a <details> row) always reflects the latest save.
  var retrofitState = { schema_version: 1, units: {} };
  // Per-card "drop from batch at the last second" state for the batch diff
  // preview (Journey 3 plan's Phase B UI requirement). Deliberately
  // client-side/in-memory only, keyed by unit_id, never persisted to
  // RETROFIT-STATE.json: it's a preview-only nicety over an Apply button
  // that's disabled by design until Phase C wires up an actual write, so
  // there's nothing here worth surviving a refresh.
  var retrofitBatchExcludedUnitIds = {};
  // Best-effort default same-repo contract locations (GET
  // /api/retrofit/contract-locations) - fetched once and cached; a per-unit
  // reference-path input only ever uses this to prefill an *empty* field,
  // never to overwrite something a human already typed or a prior save
  // already recorded.
  var retrofitContractLocations = null;
  var retrofitContractLocationsPromise = null;
  var retrofitGroupCounter = 0;
  // unit_id -> the {panel, renderResult} handle renderRetrofitDraftPanel
  // returned for that row's currently-rendered <details> element. Rebuilt
  // fresh on every renderRetrofitInventory() call (old rows are gone from
  // the DOM at that point anyway); used after a batch apply (Phase C) to
  // refresh a still-open row's "Insertion method…"/"Already retrofitted…"
  // line in place, without forcing a full inventory re-scan that would
  // collapse every <details> the human had open.
  var retrofitDraftPanelsByUnitId = {};
  // Review gate (see renderRetrofitUnitRow / applyRetrofitReviewGate):
  // whether the human has ticked "I have reviewed this inventory" for the
  // *current* inventory load. Reset to false at the top of every
  // loadRetrofitInventory() call, same lifecycle as retrofitDraftPanelsByUnitId
  // above - a fresh scan of a (possibly different) target needs its own
  // fresh review, a prior target's review does not carry over.
  var retrofitInventoryReviewed = false;
  // Every row's "select" (includeCheckbox) and "draft" (draftButton) control,
  // collected as renderRetrofitUnitRow builds each row, so
  // applyRetrofitReviewGate() can toggle all of them at once - mirrors
  // setDocsNavAvailability()'s button.disabled pattern above, applied here to
  // a dynamically-rebuilt list instead of a fixed one. Rebuilt fresh on every
  // renderRetrofitInventory() call, same as retrofitDraftPanelsByUnitId.
  var retrofitSelectDraftControls = [];

  function applyRetrofitReviewGate() {
    retrofitSelectDraftControls.forEach(function (control) {
      control.disabled = !retrofitInventoryReviewed;
    });
  }

  function retrofitOverlayIsOpen() {
    return document.getElementById("retrofit-overlay").style.display !== "none";
  }

  function showRetrofitOverlay() {
    if (docsOverlayIsOpen()) {
      closeDocsOverlay();
    }
    document.getElementById("retrofit-overlay").style.display = "";
    document.getElementById("main-content").style.display = "none";
    updateActiveNav();
  }

  function closeRetrofitOverlay() {
    document.getElementById("retrofit-overlay").style.display = "none";
    document.getElementById("main-content").style.display = "";
    updateActiveNav();
  }

  function loadRetrofitPicker(relPath) {
    fetchJson("/api/picker?path=" + encodeURIComponent(relPath)).then(function (result) {
      var pathLabel = document.getElementById("retrofit-picker-current-path");
      var upButton = document.getElementById("retrofit-picker-up");
      var list = document.getElementById("retrofit-picker-entries");
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
      retrofitCurrentPath = data.rel_path;
      pathLabel.textContent = data.rel_path;
      upButton.disabled = data.parent_rel_path === null;
      upButton.onclick = function () {
        if (data.parent_rel_path !== null) {
          loadRetrofitPicker(data.parent_rel_path);
        }
      };

      data.entries.forEach(function (entry) {
        var button = el("button", { type: "button", text: entry.name });
        button.addEventListener("click", function () {
          loadRetrofitPicker(entry.rel_path);
        });
        list.appendChild(el("li", null, [button]));
      });
    });
  }

  function loadRetrofitContractLocations() {
    if (!retrofitContractLocationsPromise) {
      retrofitContractLocationsPromise = fetchJson("/api/retrofit/contract-locations").then(
        function (result) {
          retrofitContractLocations = (result.ok && result.body.contract_locations) || {};
          return retrofitContractLocations;
        }
      );
    }
    return retrofitContractLocationsPromise;
  }

  function loadRetrofitState() {
    return fetchJson("/api/retrofit/state").then(function (result) {
      if (result.ok) {
        retrofitState = result.body;
      }
      return retrofitState;
    });
  }

  // Renders the draft-result area for one unit: an info line (insertion
  // method/line, or which contracts were already-present-and-skipped) plus
  // an editable textarea that only appears once a draft_text exists. A
  // `change` on the textarea persists the edit via
  // POST /api/retrofit/draft-override (SKILL.md Step 6.3 - "always
  // editable"), never auto-saved on every keystroke.
  function renderRetrofitDraftPanel(unit, priorEntry) {
    var panel = el("div", { class: "retrofit-draft-panel" });
    var info = el("p", { class: "retrofit-draft-info" });
    var textarea = el("textarea", { class: "retrofit-draft-textarea", rows: "4" });
    textarea.style.display = "none";
    // Confirmation shown only when this draft actually landed in the batch
    // (draft_text non-empty - the all-satisfied/idempotent case never gets
    // added, see renderRetrofitBatchPreview's own filter). Answers "what
    // now?" right where the human is looking, instead of relying on them to
    // notice step 3 appeared somewhere below a possibly long unit list.
    var jumpNote = el("p", { class: "retrofit-draft-jump" });
    jumpNote.style.display = "none";

    function renderResult(entry) {
      info.textContent = "";
      textarea.style.display = "none";
      jumpNote.style.display = "none";
      jumpNote.textContent = "";
      if (!entry) {
        return;
      }
      var included = entry.contracts_included || [];
      var skipped = entry.contracts_skipped_idempotent || [];
      if (included.length === 0 && skipped.length > 0) {
        info.textContent = "Already retrofitted: " + skipped.join(", ") + ".";
        return;
      }
      var pieces = [];
      if (entry.insertion_point) {
        pieces.push(
          "Insertion method: " + entry.insertion_point.method + " (line " + entry.insertion_point.line + ")"
        );
      }
      if (skipped.length > 0) {
        pieces.push("Already present, skipped: " + skipped.join(", "));
      }
      info.textContent = pieces.join(" — ");
      if (typeof entry.draft_text === "string" && entry.draft_text) {
        textarea.value = entry.draft_text;
        textarea.style.display = "";

        jumpNote.textContent = "";
        jumpNote.appendChild(document.createTextNode("✓ Added to the batch. "));
        var jumpLink = el("a", { href: "#retrofit-batch-preview", text: "Review it in step 3 ↓" });
        jumpLink.addEventListener("click", function (event) {
          event.preventDefault();
          var section = document.getElementById("retrofit-batch-preview");
          if (section) {
            section.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        });
        jumpNote.appendChild(jumpLink);
        jumpNote.style.display = "";
      }
    }

    if (priorEntry) {
      renderResult(priorEntry);
    }

    textarea.addEventListener("change", function () {
      postJson("/api/retrofit/draft-override", {
        unit_id: unit.unit_id,
        draft_text: textarea.value,
      }).then(function (result) {
        if (result.ok) {
          retrofitState.units[unit.unit_id] = result.body.selection;
        }
      });
    });

    panel.appendChild(info);
    panel.appendChild(textarea);
    panel.appendChild(jumpNote);
    return { panel: panel, renderResult: renderResult };
  }

  function renderRetrofitUnitRow(unit) {
    var priorEntry = retrofitState.units[unit.unit_id];

    var details = el("details", { class: "retrofit-unit-row" });
    var summary = el("summary");
    summary.appendChild(el("span", { class: "retrofit-unit-name", text: unit.name || unit.unit_id }));
    summary.appendChild(el("span", { class: "retrofit-unit-type-badge", text: unit.type }));
    summary.appendChild(el("span", { class: "retrofit-unit-path", text: unit.path }));
    // Surface cep_retrofit's/the wizard's own tier judgment directly on
    // the row, rather than leaving "canonical" vs. "supplementary" (and why)
    // implicit in server-side data the human never sees. tier/note come
    // from build_inventory()'s inventory step, independent of describe() -
    // still set even when describe_error is non-empty below.
    if (unit.tier) {
      summary.appendChild(
        el("span", { class: "retrofit-tier-badge tier-" + unit.tier, text: unit.tier })
      );
    }
    if (unit.code_related) {
      summary.appendChild(el("span", { class: "retrofit-relate-badge code", text: "code" }));
    }
    if (unit.task_related) {
      summary.appendChild(el("span", { class: "retrofit-relate-badge task", text: "task" }));
    }
    if (unit.via_symlink) {
      summary.appendChild(el("span", { class: "retrofit-relate-badge symlink", text: "via symlink" }));
    }
    if (priorEntry && priorEntry.include) {
      summary.appendChild(el("span", { class: "retrofit-relate-badge staged", text: "staged" }));
    }
    details.appendChild(summary);

    var body = el("div", { class: "retrofit-unit-detail" });
    // cep_retrofit/wizard_retrofit_inventory only ever set a note on a
    // "supplementary" unit (a weaker-signal tier, or a stem match with an
    // existing canonical unit elsewhere in the inventory - see
    // _flag_stray_duplicate_flat_files) - never on a "canonical" one, so no
    // separate tier check is needed here beyond "is there a note at all".
    // Rendered ahead of the describe_error early return below, since
    // tier/note come from the inventory step, not describe() - still
    // meaningful for a unit describe() couldn't read.
    if (unit.note) {
      body.appendChild(el("p", { class: "retrofit-unit-note", text: "Note: " + unit.note }));
    }
    if (unit.describe_error) {
      body.appendChild(
        el("p", { class: "retrofit-unit-error", text: "Could not read this unit: " + unit.describe_error })
      );
      details.appendChild(body);
      return details;
    }

    if (unit.description) {
      body.appendChild(el("p", { class: "retrofit-unit-desc", text: unit.description }));
    }
    var terms = (unit.matched_code_terms || []).concat(unit.matched_task_terms || []);
    if (terms.length) {
      body.appendChild(el("p", { class: "retrofit-unit-terms", text: "Matched terms: " + terms.join(", ") }));
    }

    var includeLabel = el("label", { class: "retrofit-include-label" });
    var includeCheckbox = el("input", { type: "checkbox" });
    includeCheckbox.checked = priorEntry
      ? Boolean(priorEntry.include)
      : Boolean(unit.code_related || unit.task_related);
    includeLabel.appendChild(includeCheckbox);
    includeLabel.appendChild(document.createTextNode(" Include this unit in the retrofit"));
    body.appendChild(includeLabel);
    // Review gate: this row's "select" control starts disabled until the
    // human ticks "I have reviewed this inventory" (see
    // applyRetrofitReviewGate) - registered here, the draft button below
    // registers itself the same way once it exists.
    includeCheckbox.disabled = !retrofitInventoryReviewed;
    retrofitSelectDraftControls.push(includeCheckbox);

    // Step 5's exactly-two-shapes reference resolution: same-repo (this
    // wizard computes a relative-path default, always editable) or
    // plugin-qualified (a manual /<plugin>:<skill> override, never
    // auto-detected). `groupName` keeps each row's radio pair from
    // interfering with every other row's on the same page.
    var groupName = "retrofit-ref-mode-" + retrofitGroupCounter++;
    var modeWrap = el("div", { class: "retrofit-reference-mode" });
    var sameRepoLabel = el("label");
    var sameRepoRadio = el("input", { type: "radio", name: groupName, value: "same-repo" });
    sameRepoLabel.appendChild(sameRepoRadio);
    sameRepoLabel.appendChild(document.createTextNode(" Same repo (relative path)"));
    var pluginLabel = el("label");
    var pluginRadio = el("input", { type: "radio", name: groupName, value: "plugin" });
    pluginLabel.appendChild(pluginRadio);
    pluginLabel.appendChild(document.createTextNode(" Installed plugin (/<plugin>:<skill>)"));
    if (priorEntry && priorEntry.reference_mode === "plugin") {
      pluginRadio.checked = true;
    } else {
      sameRepoRadio.checked = true;
    }
    modeWrap.appendChild(sameRepoLabel);
    modeWrap.appendChild(pluginLabel);
    body.appendChild(modeWrap);

    var preChecked = {};
    if (priorEntry) {
      (priorEntry.contracts || []).forEach(function (c) {
        preChecked[c] = true;
      });
    } else {
      if (unit.code_related) {
        CONTRACT_CODE.forEach(function (c) {
          preChecked[c] = true;
        });
      }
      if (unit.task_related) {
        CONTRACT_TASK.forEach(function (c) {
          preChecked[c] = true;
        });
      }
    }
    var priorRefs = (priorEntry && priorEntry.reference_args) || {};

    var contractsWrap = el("div", { class: "retrofit-unit-contracts" });
    var contractRows = {};
    ALL_CONTRACTS.forEach(function (contract) {
      var row = el("div", { class: "retrofit-contract-row" });
      var label = el("label", { class: "retrofit-contract-label" });
      var checkbox = el("input", { type: "checkbox" });
      checkbox.checked = Boolean(preChecked[contract]);
      label.appendChild(checkbox);
      label.appendChild(document.createTextNode(" " + contract));
      row.appendChild(label);

      var refInput = el("input", {
        type: "text",
        class: "retrofit-contract-ref-input",
        placeholder: "reference for " + contract,
      });
      if (priorRefs[contract]) {
        refInput.value = priorRefs[contract];
      }
      row.appendChild(refInput);
      contractsWrap.appendChild(row);
      contractRows[contract] = { checkbox: checkbox, refInput: refInput };
    });
    body.appendChild(contractsWrap);

    // Prefills empty same-repo reference fields with the detected default -
    // never overwrites a field a human already typed or a prior save
    // already recorded (the `!row.refInput.value` guard).
    function applyDefaultRefs() {
      if (sameRepoRadio.checked && retrofitContractLocations) {
        ALL_CONTRACTS.forEach(function (contract) {
          var row = contractRows[contract];
          if (!row.refInput.value && retrofitContractLocations[contract]) {
            row.refInput.value = retrofitContractLocations[contract];
          }
        });
      }
    }
    loadRetrofitContractLocations().then(applyDefaultRefs);
    sameRepoRadio.addEventListener("change", applyDefaultRefs);

    var draftPanel = renderRetrofitDraftPanel(unit, priorEntry);
    var draftMessage = el("p", { class: "retrofit-draft-message" });

    var draftButton = el("button", { type: "button", text: "Save selection & draft" });
    draftButton.addEventListener("click", function () {
      var contracts = ALL_CONTRACTS.filter(function (contract) {
        return contractRows[contract].checkbox.checked;
      });
      var referenceArgs = {};
      contracts.forEach(function (contract) {
        referenceArgs[contract] = contractRows[contract].refInput.value;
      });
      var referenceMode = pluginRadio.checked ? "plugin" : "same-repo";

      draftMessage.textContent = "Saving…";
      postJson("/api/retrofit/select", {
        unit_id: unit.unit_id,
        primary_file: unit.primary_file,
        include: includeCheckbox.checked,
        contracts: contracts,
        reference_mode: referenceMode,
        reference_args: referenceArgs,
      }).then(function (selectResult) {
        if (!selectResult.ok) {
          draftMessage.textContent =
            (selectResult.body && selectResult.body.error) || "Could not save selection.";
          return;
        }
        retrofitState.units[unit.unit_id] = selectResult.body.selection;
        if (!includeCheckbox.checked || contracts.length === 0) {
          draftMessage.textContent = includeCheckbox.checked
            ? "Selection saved. Choose at least one contract to draft."
            : "Selection saved (excluded).";
          draftPanel.renderResult(null);
          return;
        }
        draftMessage.textContent = "Drafting…";
        postJson("/api/retrofit/draft", { unit_id: unit.unit_id }).then(function (draftResult) {
          if (!draftResult.ok) {
            draftMessage.textContent =
              (draftResult.body && draftResult.body.error) || "Could not draft this unit.";
            return;
          }
          retrofitState.units[unit.unit_id] = draftResult.body.selection;
          draftMessage.textContent = "";
          draftPanel.renderResult(draftResult.body.selection);
          renderRetrofitBatchPreview();
        });
      });
    });

    // Review gate: this row's "draft" control, same starting-disabled
    // treatment as includeCheckbox above.
    draftButton.disabled = !retrofitInventoryReviewed;
    retrofitSelectDraftControls.push(draftButton);

    body.appendChild(draftButton);
    body.appendChild(draftMessage);
    body.appendChild(draftPanel.panel);

    details.appendChild(body);
    retrofitDraftPanelsByUnitId[unit.unit_id] = draftPanel;
    return details;
  }

  // Renders one text blob as a sequence of text nodes, one per source line,
  // each prefixed (e.g. "+ " for the inserted block, "" for plain context) -
  // a DocumentFragment of textContent-only nodes, never innerHTML, matching
  // this file's house rule. No diff algorithm needed anywhere in this
  // section: cep_retrofit.find_insertion_point only ever describes a pure
  // insertion at one splice point, never a replacement, so "before" and
  // "after" are just the target file's own lines sliced around that point.
  function renderRetrofitDiffLines(text, prefix) {
    prefix = prefix || "";
    var frag = document.createDocumentFragment();
    if (!text) {
      return frag;
    }
    text.split("\n").forEach(function (line) {
      frag.appendChild(document.createTextNode(prefix + line + "\n"));
    });
    return frag;
  }

  function renderRetrofitBatchCard(unitId, entry) {
    var checkbox = el("input", { type: "checkbox" });
    checkbox.checked = !retrofitBatchExcludedUnitIds[unitId];
    checkbox.addEventListener("change", function () {
      retrofitBatchExcludedUnitIds[unitId] = !checkbox.checked;
      updateRetrofitBatchFooter();
    });

    var summary = el("summary", {}, [
      checkbox,
      el("span", { class: "retrofit-batch-card-file", text: " " + entry.primary_file }),
    ]);

    var insertionPoint = entry.insertion_point || {};
    var methodText = insertionPoint.method
      ? "Insert via " + insertionPoint.method +
        (insertionPoint.heading ? " (“" + insertionPoint.heading + "”)" : "")
      : "";

    var beforePre = el("pre", { class: "retrofit-diff-context" });
    beforePre.appendChild(renderRetrofitDiffLines(entry.context_before || ""));

    var insertedPre = el("pre", { class: "retrofit-diff-inserted" });
    insertedPre.appendChild(renderRetrofitDiffLines(entry.draft_text || "", "+ "));

    var afterPre = el("pre", { class: "retrofit-diff-context" });
    afterPre.appendChild(renderRetrofitDiffLines(entry.context_after || ""));

    return el("details", { class: "retrofit-batch-card", open: "" }, [
      summary,
      el("p", { class: "retrofit-diff-method", text: methodText }),
      beforePre,
      insertedPre,
      afterPre,
    ]);
  }

  // Same "staged, drafted, not excluded from this batch" filter the diff-
  // preview cards themselves are built from (renderRetrofitBatchPreview) -
  // shared here so the footer's count, the Apply button's enabled state,
  // and the actual POST /api/retrofit/apply body can never drift apart.
  function retrofitBatchUnitIds() {
    return Object.keys(retrofitState.units || {}).filter(function (unitId) {
      var entry = retrofitState.units[unitId];
      return entry && entry.include && entry.draft_text && !retrofitBatchExcludedUnitIds[unitId];
    });
  }

  function updateRetrofitBatchFooter() {
    var countEl = document.getElementById("retrofit-batch-apply-count");
    var applyButton = document.getElementById("retrofit-batch-apply-button");
    if (!countEl) {
      return;
    }
    var total = retrofitBatchUnitIds().length;
    countEl.textContent = total + (total === 1 ? " change" : " changes");
    if (applyButton) {
      applyButton.disabled = total === 0;
    }
  }

  // Aggregates every staged unit that has a non-empty draft into the batch
  // diff-preview view (Journey 3 plan's Phase B requirement) - called after
  // both a fresh inventory load and any individual unit's draft succeeding,
  // so the batch always reflects the latest RETROFIT-STATE.json. A unit with
  // an empty draft_text (all its contracts were already-satisfied, i.e.
  // all_satisfied=True) has nothing to preview and is left out entirely, not
  // shown as a zero-line card.
  function renderRetrofitBatchPreview() {
    var section = document.getElementById("retrofit-batch-preview");
    var cardsContainer = document.getElementById("retrofit-batch-cards");
    if (!section || !cardsContainer) {
      return;
    }
    cardsContainer.innerHTML = "";
    var unitIds = Object.keys(retrofitState.units || {}).filter(function (unitId) {
      var entry = retrofitState.units[unitId];
      return entry && entry.include && entry.draft_text;
    });
    if (unitIds.length === 0) {
      section.style.display = "none";
      updateRetrofitBatchFooter();
      return;
    }
    section.style.display = "";
    unitIds.forEach(function (unitId) {
      cardsContainer.appendChild(renderRetrofitBatchCard(unitId, retrofitState.units[unitId]));
    });
    updateRetrofitBatchFooter();
  }

  function setRetrofitApplySummary(text, isError) {
    var summary = document.getElementById("retrofit-apply-summary");
    if (!summary) {
      return;
    }
    summary.textContent = text || "";
    summary.classList.toggle("error", Boolean(isError));
  }

  var RETROFIT_APPLY_STATUS_LABEL = {
    applied: "Retrofitted",
    skipped_idempotent: "Skipped (already present)",
    failed: "Failed",
  };

  // Renders POST /api/retrofit/apply's per-unit results list (SKILL.md Step
  // 8's own contract: a write failure on one file is reported for that file,
  // never rolled into a single pass/fail verdict for the whole batch) plus
  // the "N retrofitted, M skipped, K failed" roll-up the plan's Phase C UI
  // requirement names explicitly.
  function renderRetrofitApplyResults(results) {
    var report = document.getElementById("retrofit-apply-report");
    var list = document.getElementById("retrofit-apply-results");
    if (!report || !list) {
      return;
    }
    list.innerHTML = "";
    var counts = { applied: 0, skipped_idempotent: 0, failed: 0 };
    results.forEach(function (result) {
      counts[result.status] = (counts[result.status] || 0) + 1;
      var item = el("li", { class: "retrofit-apply-result-item status-" + result.status });
      item.appendChild(
        el("span", {
          class: "retrofit-apply-result-status",
          text: RETROFIT_APPLY_STATUS_LABEL[result.status] || result.status,
        })
      );
      item.appendChild(el("span", { class: "retrofit-apply-result-unit", text: " " + result.unit_id }));
      if (result.reason) {
        item.appendChild(el("span", { class: "retrofit-apply-result-reason", text: " — " + result.reason }));
      }
      list.appendChild(item);
    });
    setRetrofitApplySummary(
      counts.applied + " retrofitted, " + counts.skipped_idempotent + " skipped, " +
        counts.failed + " failed.",
      counts.failed > 0
    );
    report.style.display = "";
  }

  // Applies every currently-staged, non-excluded batch unit (same set
  // retrofitBatchUnitIds() computes for the footer/button state) via one
  // POST /api/retrofit/apply call, then refreshes everything that could have
  // changed as a result: the durable state (draft_text/contracts cleared for
  // whatever actually got written), any still-open unit row's draft panel
  // (so "Insertion method…" flips to "Already retrofitted…" in place instead
  // of looking untouched), and the batch preview itself (applied units drop
  // out once their draft_text is empty - see renderRetrofitBatchPreview's own
  // filter).
  function applyRetrofitBatch() {
    var unitIds = retrofitBatchUnitIds();
    if (unitIds.length === 0) {
      return;
    }
    var applyButton = document.getElementById("retrofit-batch-apply-button");
    if (applyButton) {
      applyButton.disabled = true;
    }
    setRetrofitApplySummary("Applying…", false);
    postJson("/api/retrofit/apply", { unit_ids: unitIds }).then(function (result) {
      if (!result.ok) {
        setRetrofitApplySummary((result.body && result.body.error) || "Apply failed.", true);
        if (applyButton) {
          applyButton.disabled = false;
        }
        return;
      }
      renderRetrofitApplyResults(result.body.results || []);
      loadRetrofitState().then(function () {
        unitIds.forEach(function (unitId) {
          var panel = retrofitDraftPanelsByUnitId[unitId];
          if (panel) {
            panel.renderResult(retrofitState.units[unitId]);
          }
        });
        renderRetrofitBatchPreview();
      });
    });
  }

  function renderRetrofitInventory(result) {
    document.getElementById("retrofit-inventory-target").textContent =
      "Target: " + result.target_rel_path;

    // tier_counts header line, sourced straight from the server's own
    // recount (see wizard_retrofit_inventory.py's tier_counts comment) so it
    // never drifts from what the rows below actually show.
    var counts = result.tier_counts || {};
    document.getElementById("retrofit-tier-summary").textContent =
      (counts.canonical || 0) + " canonical · " + (counts.supplementary || 0) + " supplementary";

    var unclaimedList = document.getElementById("retrofit-unclaimed-dirs");
    unclaimedList.innerHTML = "";
    (result.unclaimed_dirs || []).forEach(function (dir) {
      unclaimedList.appendChild(
        el("li", { class: "retrofit-unclaimed-item", text: "Unclaimed: " + dir })
      );
    });

    // Same shape as the unclaimed list above, for the other half of what the
    // scan didn't turn into rows: paths the target's own .cep-install.json
    // manifest claims, which cep_retrofit.inventory() prunes. Listing them
    // keeps the exclusion reviewable instead of invisible.
    var excludedList = document.getElementById("retrofit-excluded-owned-paths");
    excludedList.innerHTML = "";
    (result.excluded_owned_paths || []).forEach(function (path) {
      excludedList.appendChild(
        el("li", { class: "retrofit-unclaimed-item", text: "Excluded (CEP-owned): " + path })
      );
    });

    var unitsList = document.getElementById("retrofit-units-list");
    unitsList.innerHTML = "";
    // Every existing row is about to be discarded - drop the stale handles
    // along with them so a leftover entry can never be mistaken for a still-
    // live row later (see the variable's own comment).
    retrofitDraftPanelsByUnitId = {};
    // Same reasoning for the review-gate control list - see
    // applyRetrofitReviewGate/loadRetrofitInventory for the reset of
    // retrofitInventoryReviewed itself.
    retrofitSelectDraftControls = [];
    if (result.units.length === 0) {
      unitsList.appendChild(
        el("li", { class: "retrofit-units-empty", text: "No candidate skill units found here." })
      );
      return;
    }
    result.units.forEach(function (unit) {
      unitsList.appendChild(renderRetrofitUnitRow(unit));
    });
  }

  function setRetrofitInventoryMessage(text, isError) {
    var message = document.getElementById("retrofit-inventory-message");
    message.textContent = text || "";
    message.classList.toggle("error", Boolean(isError));
  }

  function loadRetrofitInventory(targetRelPath) {
    document.getElementById("retrofit-inventory").style.display = "";
    setRetrofitInventoryMessage("Scanning…");
    // A fresh scan of a (possibly different) target starts a fresh batch -
    // an apply report left over from a previous target would otherwise sit
    // there looking like it still describes what's on screen now.
    document.getElementById("retrofit-apply-report").style.display = "none";
    retrofitBatchExcludedUnitIds = {};
    // Review gate: a fresh scan of a (possibly different) target starts
    // unreviewed again, same "no carry-over" reasoning as
    // retrofitBatchExcludedUnitIds above.
    retrofitInventoryReviewed = false;
    document.getElementById("retrofit-inventory-reviewed").checked = false;
    loadRetrofitState().then(function () {
      fetchJson("/api/retrofit/inventory?target=" + encodeURIComponent(targetRelPath)).then(
        function (result) {
          if (!result.ok) {
            setRetrofitInventoryMessage(
              (result.body && result.body.error) || "Could not inventory this directory.",
              true
            );
            return;
          }
          setRetrofitInventoryMessage("");
          renderRetrofitInventory(result.body);
          renderRetrofitBatchPreview();
        }
      );
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadState();
    loadDocsNav();
    updateActiveNav();

    document.getElementById("nav-doc-concept").addEventListener("click", function () {
      navigateDocs({ kind: "doc", id: "concept" });
    });
    document.getElementById("nav-doc-protocol").addEventListener("click", function () {
      navigateDocs({ kind: "doc", id: "protocol" });
    });
    document.getElementById("nav-doc-readme").addEventListener("click", function () {
      navigateDocs({ kind: "doc", id: "readme" });
    });
    document.getElementById("nav-doc-case-studies").addEventListener("click", function () {
      navigateDocs({ kind: "doc", id: "case-studies-readme" });
    });
    document.getElementById("nav-doc-faq").addEventListener("click", function () {
      navigateDocs({ kind: "doc", id: "faq" });
    });
    document.getElementById("nav-wizard").addEventListener("click", function () {
      if (retrofitOverlayIsOpen()) {
        closeRetrofitOverlay();
      }
      closeDocsOverlay();
    });
    document.getElementById("nav-retrofit").addEventListener("click", function () {
      showRetrofitOverlay();
      loadRetrofitPicker(retrofitCurrentPath);
    });
    document.getElementById("retrofit-overlay-close").addEventListener("click", function () {
      closeRetrofitOverlay();
    });
    document.getElementById("retrofit-picker-use-dir").addEventListener("click", function () {
      loadRetrofitInventory(retrofitCurrentPath);
    });
    document.getElementById("retrofit-inventory-reviewed").addEventListener("change", function (event) {
      retrofitInventoryReviewed = event.target.checked;
      applyRetrofitReviewGate();
    });
    document.getElementById("retrofit-batch-apply-button").addEventListener("click", function () {
      applyRetrofitBatch();
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
