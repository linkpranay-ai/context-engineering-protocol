<!--
Mode 3: retrofitted writing-plans (vendored-skill/writing-plans.retrofitted.SKILL.md) loading the same
real context package as Mode 1, plus the institutional_memory_hits[] spliced in per
CONSUMING-CONTEXT-PACKAGE.md's institutional-memory-hits paragraph (Part 1's fix — this is the first
case study able to exercise it end-to-end). The three hits are the real, unedited output of
`decision_ledger.py query` (decision-ledger-fixture/query-result.json) against a small,
disclosed-as-fabricated 3-entry ledger (decision-ledger-fixture/ledger.json) seeded for this case study
— none of the three entries are real historical decisions by the open5gs or obra/superpowers
maintainers. Package used: context-package/gy-supported-features_feature-add_20260806.mode3-with-ledger.yaml
(content_hash unchanged at 9ce47746 — the institutional-memory layer is a distinct annotation on top of
the base package, not a re-derivation of its evidence). Diff from Mode 1 is confined to exactly the
spots the three hits touch: the Feature-List bitmask value (ihm_001, tier: revise — Mode 1 left this as
an explicit unresolved placeholder; Mode 3 resolves it) and two corroborating citations added to
decisions already correct in Mode 1 (ihm_002, ihm_003, both tier: proceed — no code change, just an
institutional-memory citation added alongside). Captured verbatim as generated — not hand-polished
after the fact.

Task given to the skill (identical wording to Modes 1 and 2): "Add the Supported-Features AVP to the
SMF's Gy Credit-Control-Request messages, the way Gx already does it, so the OCS can negotiate feature
support with the SMF over Gy."
-->

# Gy Supported-Features AVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Supported-Features grouped AVP to outgoing Gy Credit-Control-Requests, mirroring the Gx interface's existing implementation, so the OCS can negotiate Gy feature support with the SMF.

**Architecture:** Three additive layers, each mirroring an existing Gx counterpart one-for-one: (1) dictionary registration — a new CCR/CCA rule entry in `lib/diameter/gy/dict.c` plus a new AVP handle declared/resolved in `lib/diameter/gy/message.h`/`message.c`; (2) message construction — a new guarded AVP-building block in `src/smf/gy-path.c`'s `smf_gy_send_ccr`, placed alongside its existing sequence of `fd_msg_avp_new`/`fd_msg_avp_add` calls; (3) a minimal dictionary-registration self-test, since no existing Diameter-level test harness in this repo covers Gy at all (confirmed: zero Gy/Gx references anywhere under `tests/`).

**Tech Stack:** C, freeDiameter (`libfdcore`/`libfdproto`), meson build, abts test framework (`tests/unit`).

## Global Constraints

- Every new AVP handle must be resolved via `CHECK_dict_search(DICT_AVP, AVP_BY_NAME_ALL_VENDORS, "<Name>", &handle)` at init time — the existing pattern in every `lib/diameter/*/message.c` init function, no exceptions.
- The Supported-Features block must be skipped when `cc_request_type == OGS_DIAM_GY_CC_REQUEST_TYPE_TERMINATION_REQUEST` — exact same guard Gx uses (`src/smf/gx-path.c:322`), since a Termination-Request needs no feature renegotiation. `[trip-wire: ihm_002, tier: proceed, accepted — institutional memory independently corroborates this guard as a repo-wide convention for new AVP-construction blocks, not just a Gx-local choice.]`
- Vendor-Id child must be `OGS_3GPP_VENDOR_ID` (matches every other 3GPP-vendor grouped AVP in this codebase, including Gx's own Supported-Features).
- This is a send-only, additive change: no existing AVP already present in a Gy CCR may change position, value, or presence for any call that doesn't hit the new code path.
- **Resolved, not a placeholder:** the Feature-List bitmask value is `0x00000001` (baseline/Rel-8 support bit), not `0`. `[trip-wire: ihm_001, tier: revise, accepted — institutional memory holds that a new interface advertising Supported-Features/Feature-List for the first time, with no interface-specific bit mapping yet, must default to 0x00000001 rather than 0, since 0 signals "no features supported at all" — a materially different and likely-wrong signal to send during initial feature negotiation. Required evidence before relying on this: confirm 0x00000001 is genuinely what Gx's own Feature-List-ID 1 value represents before reusing it as Gy's default, rather than assuming the numeric value alone implies the same meaning across interfaces — not independently re-verified against 3GPP TS 32.299 in this pass, carried forward as the institutional-memory-sourced decision it is.]`

---

### Task 1: Register the Gy Supported-Features AVP dictionary handle

**Files:**
- Modify: `lib/diameter/gy/dict.c:159` (Gy CCR command rule block, right after the section comment `/* Credit-Control-Request (CCR) Command - Extension for Gy ... */`) — add a `Supported-Features` rule entry; find and modify the parallel CCA rule block the same way.
- Modify: `lib/diameter/gy/message.h:118` (immediately after the existing `extern struct dict_object *ogs_diam_gy_feature_list;` line) — **new handle only**; do not redeclare `ogs_diam_gy_feature_list_id` or `ogs_diam_gy_feature_list`, both already declared here. `[trip-wire: ihm_003, tier: proceed, accepted — institutional memory independently corroborates ctx_005's finding that these two leaf handles already exist in Gy; redeclaring an AVP dictionary handle already declared for another interface is a known anti-pattern.]`
- Modify: `lib/diameter/gy/message.c:64` (immediately after the existing `struct dict_object *ogs_diam_gy_feature_list = NULL;` line) and `lib/diameter/gy/message.c:131` (immediately after the existing `Feature-List` `CHECK_dict_search` line)
- Test: `tests/unit/diameter-gy-message-test.c` (new file, following the existing `tests/unit/*-message-test.c` + abts pattern — see `tests/unit/nas-message-test.c` for the sibling structure)

**Interfaces:**
- Consumes: nothing from an earlier task (this is the first task).
- Produces: `struct dict_object *ogs_diam_gy_supported_features` (global handle, declared `extern` in `message.h`, defined in `message.c`) — Task 2 uses this exact symbol name to build the AVP.

- [ ] **Step 1: Write the failing test**

```c
/* tests/unit/diameter-gy-message-test.c */
#include "core/abts.h"
#include "diameter/gy/gy-message.h"

static void gy_supported_features_dict_test1(abts_case *tc, void *data)
{
    /* Confirm the Gy dictionary now resolves a Supported-Features handle,
     * the same way it already resolves Feature-List-ID and Feature-List. */
    ABTS_PTR_NOTNULL(tc, ogs_diam_gy_supported_features);
}

abts_suite *test_diameter_gy_message(abts_suite *suite)
{
    suite = ADD_SUITE(suite)
    abts_run_test(suite, gy_supported_features_dict_test1, NULL);
    return suite;
}
```

Also register the new suite in `tests/unit/abts-main.c` (follow the existing `ADD_SUITE`-registration line for any sibling `*-message-test.c` file) and add `diameter-gy-message-test.c` to `testunit_unit_sources` in `tests/unit/meson.build`, alongside the existing `nas-message-test.c` / `gtp-message-test.c` entries.

- [ ] **Step 2: Build and run test to verify it fails**

Run: `meson compile -C build && ./build/tests/unit/unit`
Expected: FAIL — `ogs_diam_gy_supported_features` does not exist, build error (undeclared identifier), not a runtime assertion failure. This is expected: the symbol doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

In `lib/diameter/gy/message.h`, immediately after line 118 (`extern struct dict_object *ogs_diam_gy_feature_list;`):

```c
extern struct dict_object *ogs_diam_gy_supported_features;
```

In `lib/diameter/gy/message.c`, immediately after line 64 (`struct dict_object *ogs_diam_gy_feature_list = NULL;`):

```c
struct dict_object *ogs_diam_gy_supported_features = NULL;
```

And immediately after line 131 (the existing `CHECK_dict_search(..., "Feature-List", &ogs_diam_gy_feature_list);` line):

```c
CHECK_dict_search(DICT_AVP, AVP_BY_NAME_ALL_VENDORS,
        "Supported-Features", &ogs_diam_gy_supported_features);
```

In `lib/diameter/gy/dict.c`, add a `Supported-Features` rule entry to both the CCR rule block (starting at line 159) and the parallel CCA rule block, following the exact same shape as the Gx precedent (`lib/diameter/gx/dict.c:206,257`):

```c
{  { .avp_vendor = 10415, .avp_name = "Supported-Features" }, RULE_OPTIONAL, -1, -1 },
```

- [ ] **Step 4: Build and run test to verify it passes**

Run: `meson compile -C build && ./build/tests/unit/unit`
Expected: PASS — `ogs_diam_gy_supported_features` resolves to a non-NULL handle once the Gy dictionary is loaded at process init.

- [ ] **Step 5: Commit**

```bash
git add lib/diameter/gy/dict.c lib/diameter/gy/message.h lib/diameter/gy/message.c tests/unit/diameter-gy-message-test.c tests/unit/abts-main.c tests/unit/meson.build
git commit -m "feat(gy): register Supported-Features AVP dictionary handle"
```

### Task 2: Construct and send the Supported-Features AVP on outgoing Gy CCRs

**Files:**
- Modify: `src/smf/gy-path.c` inside `smf_gy_send_ccr` (starts at `gy-path.c:635`) — insert the new AVP-construction block immediately after the existing Session-Id/new-session handling block, before the sequence of other `fd_msg_avp_new` calls already building the request.

**Interfaces:**
- Consumes: `ogs_diam_gy_supported_features` (from Task 1), plus the already-existing `ogs_diam_gy_feature_list_id` / `ogs_diam_gy_feature_list` handles (already declared today at `message.h:117-118`) and the already-existing `ogs_diam_vendor_id` handle (used identically by the Gx precedent at `gx-path.c:322-345`).
- Produces: nothing consumed by a later task — this is the last functional task.

- [ ] **Step 1: Write the failing test**

There is no existing Gy-level integration test harness in this repo to extend — confirmed by grep: `tests/volte` (the only Diameter-level abts test suite that exercises a simulated peer exchange) covers Cx and Rx only (`tests/volte/diameter-cx-path.c`, `cx-test.c`, `rx-test.c`); there is no `diameter-gy-path.c` or equivalent anywhere under `tests/`. Building a full simulated Gy CCR/CCA exchange harness (spinning up a fake OCS peer, matching `tests/volte`'s pattern) is a separate, larger effort than this plan's task-sized scope — flagging this as a real, disclosed gap rather than inventing a test that doesn't match any existing pattern in this codebase.

The verifiable unit here is narrower: confirm the new code path doesn't corrupt message construction by asserting the resulting `req` message still validates against the Gy dictionary rules from Task 1 (the `RULE_OPTIONAL` entry added there is what the freeDiameter stack itself checks at `fd_msg_send`/`fd_msg_parse_dict` time — an invalid grouped AVP or a rule violation would be caught by freeDiameter's own dictionary validation, not by a custom assertion). This plan does not add a bespoke test for Step 1-4 of this task; instead, Step 4 below is a manual verification step against a running SMF, disclosed as such rather than dressed up as an automated test.

- [ ] **Step 2: (no separate failing-test step — see Step 1's note)**

- [ ] **Step 3: Write minimal implementation**

In `src/smf/gy-path.c`, inside `smf_gy_send_ccr`, immediately after the existing Session-Id/new-session handling block (the `if (sess->gy_sid) { ... } else { ... }` block that follows the `fd_msg_new`/`fd_msg_hdr` setup), insert:

```c
    if (cc_request_type != OGS_DIAM_GY_CC_REQUEST_TYPE_TERMINATION_REQUEST) {
        /* Set Supported-Features */
        ret = fd_msg_avp_new(ogs_diam_gy_supported_features, 0, &avp);
        ogs_assert(ret == 0);

        ret = fd_msg_avp_new(ogs_diam_vendor_id, 0, &avpch1);
        ogs_assert(ret == 0);
        val.i32 = OGS_3GPP_VENDOR_ID;
        ret = fd_msg_avp_setvalue(avpch1, &val);
        ogs_assert(ret == 0);
        ret = fd_msg_avp_add(avp, MSG_BRW_LAST_CHILD, avpch1);
        ogs_assert(ret == 0);

        ret = fd_msg_avp_new(ogs_diam_gy_feature_list_id, 0, &avpch1);
        ogs_assert(ret == 0);
        val.i32 = 1;
        ret = fd_msg_avp_setvalue(avpch1, &val);
        ogs_assert(ret == 0);
        ret = fd_msg_avp_add(avp, MSG_BRW_LAST_CHILD, avpch1);
        ogs_assert(ret == 0);

        ret = fd_msg_avp_new(ogs_diam_gy_feature_list, 0, &avpch1);
        ogs_assert(ret == 0);
        /* Feature-List bitmask: 0x00000001 (baseline/Rel-8 support bit),
         * per institutional-memory decision dl_when-a-new-interface-adv_3a5b76
         * (trip-wire hit ihm_001) — a new interface advertising this AVP for
         * the first time defaults to the baseline bit rather than 0, since 0
         * signals "no features supported at all". Not independently
         * re-verified against 3GPP TS 32.299 in this pass; carried forward
         * as the institutional-memory-sourced decision it is. */
        val.u32 = 0x00000001;
        ret = fd_msg_avp_setvalue(avpch1, &val);
        ogs_assert(ret == 0);
        ret = fd_msg_avp_add(avp, MSG_BRW_LAST_CHILD, avpch1);
        ogs_assert(ret == 0);

        ret = fd_msg_avp_add(req, MSG_BRW_LAST_CHILD, avp);
        ogs_assert(ret == 0);
    }
```

This mirrors `src/smf/gx-path.c:322-345` field-for-field (same guard, same Vendor-Id/Feature-List-ID/Feature-List child sequence), substituting the Gy handles registered in Task 1 for the Gx ones, with the Feature-List value resolved per `[trip-wire: ihm_001, tier: revise, accepted]` above instead of left as a placeholder.

- [ ] **Step 4: Manual verification (no automated test exists for this seam)**

Run: `meson compile -C build`
Expected: builds cleanly with no new warnings.

Then, against a running SMF connected to a Diameter capture point (e.g. `tshark -i any -f "port 3868"` or the SMF's own Diameter debug logging), trigger a PDU session establishment and confirm the outgoing Gy CCR-Initial now includes a Supported-Features grouped AVP with Vendor-Id `10415`, Feature-List-ID `1`, and Feature-List `0x00000001`, and that every other AVP already present in that CCR (Session-Id, Subscription-Id, Multiple-Services-Credit-Control, etc.) is byte-identical to a capture taken before this change.

- [ ] **Step 5: Commit**

```bash
git add src/smf/gy-path.c
git commit -m "feat(gy): send Supported-Features AVP on outgoing Gy CCRs"
```

## Self-Review

**1. Spec coverage:** Both context-package aspects are covered — dictionary registration (Task 1, `ctx_002`/`ctx_003`/`ctx_005`) and message construction (Task 2, `ctx_004`/`ctx_006`). The package's one open question (Feature-List bitmask value) is no longer open in this mode — trip-wire hit `ihm_001` resolved it, and Task 2's code carries the resolved value with its institutional-memory citation rather than a disclosed placeholder. The package's disclosed constraint gap (no performance baseline) isn't addressed by this plan — out of scope for a send-only additive AVP change, consistent with the package's own framing.

**2. Placeholder scan:** No "TBD"/"implement later"/"add appropriate error handling" language anywhere in the two tasks above. Unlike Mode 1, there is no remaining placeholder value in this plan — the one value Mode 1 disclosed as a guess (`Feature-List = 0`) is now a cited, resolved decision (`Feature-List = 0x00000001`, `ihm_001`).

**3. Type consistency:** `ogs_diam_gy_supported_features` is declared once (Task 1, `message.h`), defined once (Task 1, `message.c`), and consumed by exactly that name in Task 2 — no renaming across tasks.

## Trip-wire coverage note

Three institutional-memory hits were surfaced for this aspect (`decision-ledger-fixture/query-result.json`), all pre-dispositioned `accepted` by a human reviewer per the Mode 3 fixture package:

| Hit | Ledger decision | Tier | Effect on this plan |
|---|---|---|---|
| `ihm_001` | Feature-List should default to `0x00000001`, not `0`, for a first-time advertisement | **revise** | Changed: Task 2 Step 3's placeholder bitmask is now a resolved, cited value; Global Constraints' bitmask bullet no longer reads as an open question. |
| `ihm_002` | New AVP-construction blocks must skip on Termination-Request, mirroring Gx | proceed | No change: corroborates the guard Mode 1 already derived independently from `ctx_006`/`decisions_log`; cited as added confidence. |
| `ihm_003` | AVP dictionary handles already declared for one interface must not be redeclared per-interface | proceed | No change: corroborates Task 1's approach (Mode 1 already only added the missing `Supported-Features` handle); cited as added confidence. |

Net effect: two of three hits corroborate what the context package alone already got right (Mode 1 vs. Mode 2's real defect on this exact point — see `mode-2-without-cep-output.md` Task 1, which redeclares both existing leaf handles). The third (`ihm_001`) is the one hit that actually changes generated code — it converts a disclosed, honestly-labeled placeholder into a resolved, cited decision, which is precisely the incremental value the trip-wire/decision-ledger layer is designed to add on top of a context package alone: closing gaps the package's own `gaps_detected`/`open_questions` correctly flagged as unresolvable from source, without ever silently guessing.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-06-gy-supported-features.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

---
`[Context: gy-supported-features_feature-add_20260806, content_hash: 9ce47746, institutional_memory_hit_count: 3, human_approved: true]`
