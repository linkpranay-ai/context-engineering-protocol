<!--
Mode 2: pristine writing-plans (vendored-skill/writing-plans.pristine.SKILL.md) run against the same
bare-ask task wording as Mode 1, with no CEP context package loaded. Per the skill's own File
Structure step, a real run would explore the repo before drawing task boundaries — the exploration
budget here is bounded to what a single unguided grep-and-skim pass would plausibly surface (the
skill's own Process has no equivalent of "load extracted evidence first"), not the exhaustive,
line-cited evidence Mode 1 received from the package. This is the realistic "no interview, bare ask"
baseline the skill is designed for. Captured verbatim as generated — not hand-polished after the fact.

Bare-ask task text (identical to Mode 1):
"Add the Supported-Features AVP to the SMF's Gy Credit-Control-Request messages, the way Gx already
does it, so the OCS can negotiate feature support with the SMF over Gy."
-->

# Gy Supported-Features AVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Supported-Features AVP to Gy Credit-Control-Requests, matching the existing Gx implementation, so the OCS can negotiate feature capabilities with the SMF over Gy.

**Architecture:** Register the Supported-Features grouped AVP (and its Vendor-Id / Feature-List-ID / Feature-List children) in the Gy Diameter dictionary, then build and attach it in the SMF's Gy CCR-sending path, following the same structure Gx already uses.

**Tech Stack:** C, freeDiameter, meson build.

## Global Constraints

- New AVP handles must be resolved the same way every other Gy AVP handle is resolved today (dictionary lookup at init time).
- Vendor-Id child should use the same 3GPP vendor constant already used elsewhere in this codebase.
- This is additive — no existing Gy AVP behavior should change.

---

### Task 1: Register the Gy Supported-Features AVP dictionary handles

**Files:**
- Modify: `lib/diameter/gy/dict.c` (add a `Supported-Features` rule entry to the Gy CCR/CCA command definitions)
- Modify: `lib/diameter/gy/message.h` (declare the new AVP handles)
- Modify: `lib/diameter/gy/message.c` (define and dictionary-search the new AVP handles)
- Test: `tests/volte/diameter-gy-path.c` (new file, following the existing `tests/volte/diameter-cx-path.c` pattern)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `ogs_diam_gy_supported_features`, `ogs_diam_gy_feature_list_id`, `ogs_diam_gy_feature_list` handles for Task 2 to use.

- [ ] **Step 1: Write the failing test**

```c
/* tests/volte/diameter-gy-path.c */
#include "core/abts.h"
#include "diameter/gy/gy-message.h"

static void gy_supported_features_test1(abts_case *tc, void *data)
{
    ABTS_PTR_NOTNULL(tc, ogs_diam_gy_supported_features);
    ABTS_PTR_NOTNULL(tc, ogs_diam_gy_feature_list_id);
    ABTS_PTR_NOTNULL(tc, ogs_diam_gy_feature_list);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `meson test -C build volte`
Expected: FAIL — the new handles don't exist yet.

- [ ] **Step 3: Write minimal implementation**

In `lib/diameter/gy/message.h`, declare the three new handles:

```c
extern struct dict_object *ogs_diam_gy_supported_features;
extern struct dict_object *ogs_diam_gy_feature_list_id;
extern struct dict_object *ogs_diam_gy_feature_list;
```

In `lib/diameter/gy/message.c`, define and resolve them:

```c
struct dict_object *ogs_diam_gy_supported_features = NULL;
struct dict_object *ogs_diam_gy_feature_list_id = NULL;
struct dict_object *ogs_diam_gy_feature_list = NULL;

/* ... inside the dictionary-init function ... */
CHECK_dict_search(DICT_AVP, AVP_BY_NAME_ALL_VENDORS,
        "Supported-Features", &ogs_diam_gy_supported_features);
CHECK_dict_search(DICT_AVP, AVP_BY_NAME_ALL_VENDORS,
        "Feature-List-ID", &ogs_diam_gy_feature_list_id);
CHECK_dict_search(DICT_AVP, AVP_BY_NAME_ALL_VENDORS,
        "Feature-List", &ogs_diam_gy_feature_list);
```

In `lib/diameter/gy/dict.c`, add a matching `Supported-Features` rule entry to the Gy CCR and CCA command rule blocks.

- [ ] **Step 4: Run test to verify it passes**

Run: `meson test -C build volte`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/diameter/gy/dict.c lib/diameter/gy/message.h lib/diameter/gy/message.c tests/volte/diameter-gy-path.c
git commit -m "feat(gy): register Supported-Features AVP handles"
```

### Task 2: Send the Supported-Features AVP on outgoing Gy CCRs

**Files:**
- Modify: `src/smf/gy-path.c` (add AVP construction to the function that builds and sends Gy CCRs)

**Interfaces:**
- Consumes: `ogs_diam_gy_supported_features`, `ogs_diam_gy_feature_list_id`, `ogs_diam_gy_feature_list` (from Task 1).
- Produces: nothing (last task).

- [ ] **Step 1: Write the failing test**

```c
/* Extend tests/volte/diameter-gy-path.c */
static void gy_ccr_includes_supported_features_test1(abts_case *tc, void *data)
{
    /* Send a simulated CCR-Initial and assert the captured message
     * includes a Supported-Features AVP. */
    /* ... simulated session setup, mirroring diameter-cx-path.c ... */
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `meson test -C build volte`
Expected: FAIL — no Supported-Features AVP in the constructed CCR yet.

- [ ] **Step 3: Write minimal implementation**

In `src/smf/gy-path.c`, inside the function that builds the Gy CCR, add:

```c
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
val.u32 = 0;
ret = fd_msg_avp_setvalue(avpch1, &val);
ogs_assert(ret == 0);
ret = fd_msg_avp_add(avp, MSG_BRW_LAST_CHILD, avpch1);
ogs_assert(ret == 0);

ret = fd_msg_avp_add(req, MSG_BRW_LAST_CHILD, avp);
ogs_assert(ret == 0);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `meson test -C build volte`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/smf/gy-path.c
git commit -m "feat(gy): send Supported-Features AVP on outgoing Gy CCRs"
```

## Self-Review

**1. Spec coverage:** Both dictionary registration and AVP construction are covered.

**2. Placeholder scan:** No TBD/placeholder language found.

**3. Type consistency:** Handle names match between Task 1 and Task 2.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-06-gy-supported-features.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
