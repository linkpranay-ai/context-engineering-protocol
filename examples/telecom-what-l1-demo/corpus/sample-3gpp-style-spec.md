<!--
SYNTHETIC / FICTIONAL DOCUMENT — NOT A REAL 3GPP SPECIFICATION.

This file is a hand-authored demo fixture. It imitates 3GPP/ETSI clause-numbering
and cross-reference conventions (e.g. "7.2.9.2", "Annex A.3", "(see clause 7.5)")
so it can exercise the What-L1 external-reference indexer with realistic
structure — but the procedure it describes ("Enhanced Synchronized Beacon
Procedure", ESBP) is invented for this demo and does not correspond to any real
3GPP technical specification, release, or working-group document. Do not cite
this file as a source of real telecom standards content. See
`examples/telecom-what-l1-demo/WALKTHROUGH.md` for how to point this same
mechanism at your own real, properly-licensed spec corpus instead.
-->

# TS XX.999: Synthetic Demo Specification for Enhanced Synchronized Beacon Procedure (ESBP)

## 1 Scope

This synthetic document specifies a fictional radio access procedure, the
Enhanced Synchronized Beacon Procedure (ESBP), used only to demonstrate the
What-L1 external-reference indexing mechanism in the Context Engineering
Protocol. It is not a real specification.

## 2 References

The following documents are referenced by this synthetic specification. As
with the rest of this file, these references are invented for demo purposes.

- [1] TS XX.001: "Synthetic Demo Vocabulary and Abbreviations"
- [2] TS XX.201: "Synthetic Demo Physical Layer Procedures"

## 3 Definitions, symbols and abbreviations

### 3.1 Definitions

**Beacon anchor**: a reference timing signal transmitted by the network that
UEs use to align their local ESBP timing window (see clause 7.2).

**Synchronization drift**: the accumulated timing offset between a UE's local
clock and the beacon anchor, measured in the drift-correction procedure of
clause 7.5.

### 3.2 Abbreviations

- ESBP: Enhanced Synchronized Beacon Procedure
- SDW: Synchronization Drift Window

## 4 General description

ESBP is a fictional procedure that allows a UE to maintain beacon-relative
timing alignment across a mobility event without a full re-synchronization.
The high-level flow is summarized in clause 4.1 and detailed procedure-by-
procedure in clause 7.

### 4.1 Overview of the ESBP flow

At a high level, ESBP consists of four phases: initial beacon acquisition
(clause 7.2), periodic drift monitoring (clause 7.3), conditional
re-acquisition triggering (clause 7.4), and drift correction (see clause 7.5).
Annex A.3 gives an informative example of a full ESBP cycle end to end.

## 5 UE procedures

### 5.1 UE capability signalling

A UE indicating support for ESBP shall set the `esbp-Supported` capability
field as defined in TS XX.201 [2], clause 5.3.4a.

### 5.2 UE state model

The UE's ESBP state machine has three states: IDLE, ACQUIRED, and DRIFTING.
Transitions between these states are governed by the procedures in clause 7.

## 6 Network procedures

### 6.1 Beacon anchor transmission

The network transmits the beacon anchor at a periodicity configured by the
`beaconAnchorPeriodicity` parameter. See clause 7.2 for how a UE uses this
signal during initial acquisition.

### 6.2 Network-triggered re-acquisition

The network may trigger UE re-acquisition per the conditions in clause 7.4
when uplink timing measurements indicate excessive synchronization drift.

## 7 Detailed procedures

### 7.1 General

This clause specifies the detailed ESBP procedures referenced from clauses 4
through 6 above.

### 7.2 Initial beacon acquisition

#### 7.2.1 General

Upon entering ESBP mode, a UE shall search for a beacon anchor as described
in clauses 7.2.2 through 7.2.9.

#### 7.2.9 Beacon anchor detection window

##### 7.2.9.1 Window configuration

The UE shall open a detection window of `beaconDetectionWindowLength`
subframes, aligned to the timing reference in TS XX.201 [2].

##### 7.2.9.2 Window search procedure

Within the detection window opened per clause 7.2.9.1, the UE shall correlate
incoming symbols against the known beacon anchor sequence. On successful
detection, the UE shall transition to the ACQUIRED state (see clause 5.2) and
begin periodic drift monitoring per clause 7.3.

If no beacon anchor is detected before the window in clause 7.2.9.1 closes,
the UE shall retry acquisition up to `maxAcquisitionRetries` times before
declaring acquisition failure.

### 7.3 Periodic drift monitoring

While in the ACQUIRED state, the UE shall periodically measure synchronization
drift relative to the most recently detected beacon anchor. The measurement
interval is `driftMonitoringInterval`, and the accumulated drift value feeds
the re-acquisition trigger in clause 7.4.

### 7.4 Conditional re-acquisition triggering

If the measured synchronization drift from clause 7.3 exceeds
`driftReacquisitionThreshold`, the UE shall transition to the DRIFTING state
(clause 5.2) and re-run initial beacon acquisition (clause 7.2).

### 7.5 Drift correction

#### 7.5.1 General

When synchronization drift is within tolerance but nonzero, the UE applies a
drift correction rather than a full re-acquisition. This subclause specifies
the correction procedure.

#### 7.5.2 Correction algorithm

The UE shall apply a timing offset correction bounded by
`maxDriftCorrectionStep` per correction cycle, recomputing the correction on
every drift measurement from clause 7.3 until the measured drift falls below
`driftReacquisitionThreshold` (clause 7.4).

## Annex A (informative): Worked ESBP examples

### A.1 Example deployment parameters

This subclause gives example values for the configurable parameters
introduced in clause 7: `beaconAnchorPeriodicity`, `beaconDetectionWindowLength`,
`driftMonitoringInterval`, `driftReacquisitionThreshold`, and
`maxDriftCorrectionStep`.

### A.2 Example UE state transitions

This subclause walks through the UE state model of clause 5.2 for a single
mobility event, from IDLE through ACQUIRED, DRIFTING, and back to ACQUIRED.

### A.3 Full ESBP cycle example

This subclause traces one complete ESBP cycle end to end: initial beacon
acquisition (clause 7.2.9.2), periodic drift monitoring (clause 7.3), a
re-acquisition trigger (clause 7.4), and drift correction (clause 7.5.2),
matching the overview given in clause 4.1.

## Annex B (informative): Change history

This synthetic document has no real change history — it was authored once, for
demo purposes, as part of the Context Engineering Protocol's What-L1 example.
