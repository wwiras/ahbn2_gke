# K6 Exp10(K8s) — Pre-Reconciliation Audit

## Status

Audit only. Do not execute Exp10 before K5 formal review and freeze.

## Scientific Question

Compare recovery of Gossip, Structured, DC-SoC, and AHBN when a critical forwarding peer is genuinely unavailable. Unlike Exp08, DC-SoC availability-driven maintenance is legitimate here.

## Current Implementation

The only runner is `scripts/run_exp10.sh`, which invokes `scripts/run_experiment.sh experiments/exp10.yaml`. The active configuration contains one AHBN run: BA(N=20,m=2), seed 42, source peer-4, `ch_failure`, target peer metadata 5, trigger 0.03 s, settle 8 s. There is no four-comparator smoke/formal matrix, repetition policy, K6-specific runner, or K9 campaign analysis. Current implemented matrix size: one execution.

Failure injection is selected by `app/controller.py::choose_target` and applied by `FailStop`; pod deletion/churn paths are separate. DC-SoC maintenance is implemented by `app/dcsoc_maintenance.py`, broadcast by `app/controller.py`, and logged by `PeerService.ApplyDCSOCMaintenance` with natural maintenance start/end/duration and replacement counts. `app/plot_exp10.py` produces only a single-run summary and plots.

## Reconciliation Gaps

- No authoritative four-comparator K6 configurations or matched matrix.
- No resolved failure conditions/seeds/repetition count, so no scientific K6 campaign run count exists yet.
- Active `experiments/exp10.yaml` has no `k5_h2.actuator_treatment: S5`; the final-actuator image would reject this configuration at peer startup.
- Legacy docs reference obsolete images and historical single-run output.
- No K6 smoke/formal gate, completeness validation, comparator isolation validation, or aggregate statistics.
- `failure.target_peer` is present in YAML but generated target selection is driven by generated topology and `target_type`; this requires explicit reconciliation before K6.

## Docker and Execution

No K6 image decision is made by this audit. Do not build, push, or execute. The existing tracefix image contains the accepted AHBN runtime, but K6 configuration/runtime compatibility has not yet been validated.

## Pending

Prepare the K6 matrix and manual runners only after K5 is formally reviewed and frozen. Do not copy Exp08 overload dimensions into Exp10.
