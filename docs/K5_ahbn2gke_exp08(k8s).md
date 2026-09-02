# K5 Exp08(K8s) — Final Actuator Restart

## Source Snapshot

31-Aug-2026 frozen AHBN (`ahbn2_gke_31Aug2026(1).zip` lineage).

## Authoritative Actuator Files

The accepted actuator is frozen S5 in `app/k5_final_actuator_policy.py` and is invoked by `app/k5_final_actuator_runtime.py`. Acceptance history and regression evidence remain in `tests/test_k5_final_actuator_gke.py`, `scripts/run_k5_final_actuator_gke.sh`, `scripts/k5_final_actuator_analysis.py`, and `docs/K5_GKES0vsS5f2tof6.md`.

## Canonical Integrity

The unchanged controller is `z = -d_hat + l_hat + u_hat + c_hat`, using the canonical EWMA pipeline. Pre-edit SHA-256: `app/ahbn_controller.py` = `dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8`; `app/peer.py` = `64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a`.

## Resolved Experiment Matrix

Formal: Gossip, Structured, DC-SoC, AHBN x delays 700/1050/1400/2100 ms x seeds 42--46 = 80 executions. The five seeds are the repository's five repetitions; there is no second repetition loop. Smoke: the four algorithms x seed 42 x delays 700/2100 ms = 8 executions.

## Docker Image

The successful smoke used `wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64`. Collected pod provenance records `docker.io/wwiras/ahbn2-peer@sha256:d3224d4cdb16507d28d1c164d60b31b7c451fb0efa36e9add959f364fdd0a8d5`. This tracefix image is the smoke-validated image required for formal execution.

## Docker Architecture Failure

The previous smoke stopped before scientific execution with `exec /usr/local/bin/python: exec format error`. This is classified as an infrastructure/container architecture issue—not an AHBN controller, actuator, Gossip, Structured, DC-SoC, or Exp08 scientific failure.

## Corrective Action

The corrected image is `wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-amd64`, verified as `linux/amd64`, with observed registry digest `sha256:eb6281a87417e97a8e1dfa78c3ac7197be08c6c8ed2b44ede8e5408351e8ddfa`.

## Missing Final-Actuator Trace Integration Event

Smoke `20260902_015208` passed Kubernetes rollout/readiness and completed both Gossip runs, both Structured runs, and both DC-SoC runs. At `k5_ahbn_seed42_factor1.0`, collection contained 454 `ahbn_controller_trace` rows and 264 canonical `ahbn_forwarding_decision` rows but zero `k5_final_actuator_decision` rows. The image had been built from `app/Dockerfile`, which omitted both final-actuator modules and started `peer.py`; S5 was therefore not packaged or invoked. This is an integration/packaging failure, not an AHBN scientific failure.

Smoke diagnostics included Structured factor 3.0 delivery ratio 1.0, propagation delay approximately 1.94685 s, zero duplicates, and 380 total forwards; DC-SoC factor 1.0 delivery ratio 1.0, propagation delay approximately 0.85422 s, and maintenance count 0; DC-SoC factor 3.0 delivery ratio 1.0, propagation delay approximately 2.16760 s, and maintenance count 0. These are smoke diagnostics only and are not formal scientific results.

Smoke result: **FAIL — integration/trace gate**. The minimal correction packages `k5_final_actuator_policy.py` and `k5_final_actuator_runtime.py` in `app/Dockerfile` and starts the accepted wrapper. Canonical controller and S5 policy logic are unchanged. The next immutable image is `wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64`.

## Local Validation

Focused and complete local validation commands and results are reported in the preparation handoff. Generated comparator contract: PASS; expected formal runs: 80.

## Smoke Command

`IMAGE=wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64 scripts/run_k5_exp08_smoke.sh`

## Smoke Terminal Output

Complete transcript: `outputs/k5_exp08_smoke-20260902_082442/terminal.log`.

## Smoke Result

**PASS.** Eight of eight executions are present: Gossip 2/2, Structured 2/2, DC-SoC 2/2, AHBN 2/2. The recorded gate is:

```text
K5 EXP08 SMOKE GATE: PASS
IMPLEMENTATION INTEGRITY: PASS
DATASET COMPLETE: YES
DC-SOC SLOW!=FAILED: PASS
CANONICAL AHBN UNCHANGED: PASS
FINAL ACTUATOR: PASS
RESULT DIRECTION: MIXED
```

AHBN at 700 ms recorded 357 controller traces, 240 S5 decisions, and zero controller/actuator mismatches. AHBN at 2100 ms recorded 525 controller traces, 293 S5 decisions, and zero controller/actuator mismatches. These smoke measurements validate implementation only and are not formal scientific results.

## Formal Command

`IMAGE=wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64 scripts/run_k5_exp08_formal.sh --smoke-report outputs/k5_exp08_smoke-20260902_082442/terminal.log`

## Formal Terminal Output

Complete transcript: `outputs/k5_exp08_formal-20260902_092321/terminal.log`. The terminal gate records 80/80 executions, zero missing/duplicate coordinates, zero controller/actuator mismatches, DC-SoC maintenance zero, and `K5 EXP08 FORMAL GATE: PASS`.

## Formal Results

All values below are condition means across five matched seeds.

| Delay (ms) | Algorithm | Delivery | Delay (s) | Duplicates | Forwards |
|---:|---|---:|---:|---:|---:|
| 700 | Gossip | 1.0000 | 0.6569 | 680.0 | 380.0 |
| 700 | Structured | 1.0000 | 0.6686 | 0.0 | 380.0 |
| 700 | DC-SoC | 1.0000 | 0.8760 | 0.0 | 380.0 |
| 700 | AHBN | 0.6435 | 0.4037 | 173.6 | 237.4 |
| 1050 | Gossip | 1.0000 | 0.9586 | 680.0 | 380.0 |
| 1050 | Structured | 1.0000 | 0.9850 | 0.0 | 380.0 |
| 1050 | DC-SoC | 1.0000 | 1.1185 | 0.0 | 380.0 |
| 1050 | AHBN | 0.6730 | 0.6325 | 179.0 | 249.2 |
| 1400 | Gossip | 1.0000 | 1.2773 | 680.0 | 380.0 |
| 1400 | Structured | 1.0000 | 1.3006 | 0.0 | 380.0 |
| 1400 | DC-SoC | 1.0000 | 1.4245 | 0.0 | 380.0 |
| 1400 | AHBN | 0.6250 | 0.7166 | 180.0 | 230.0 |
| 2100 | Gossip | 1.0000 | 1.9051 | 680.0 | 380.0 |
| 2100 | Structured | 1.0000 | 1.9254 | 0.0 | 380.0 |
| 2100 | DC-SoC | 1.0000 | 2.0628 | 0.0 | 380.0 |
| 2100 | AHBN | 0.6815 | 1.3385 | 202.4 | 252.6 |

## Statistical Validation

Every algorithm-by-condition cell has `n=5`. The final tables report mean, sample SD, descriptive 95% Student-t CI, minimum, maximum, and median for all four metrics: `outputs/k5_exp08_formal-20260902_092321/final_analysis/tables/comparator_combined.csv`. Matched-seed deltas, per-seed results, and leave-one-seed-out checks are in the same directory. These are descriptive intervals over the five frozen seeds; no post-hoc significance claim is made.

AHBN delivery mean ± SD (95% CI) is 0.6435 ± 0.0835 (0.5398–0.7472), 0.6730 ± 0.0752 (0.5796–0.7664), 0.6250 ± 0.0711 (0.5367–0.7133), and 0.6815 ± 0.0805 (0.5816–0.7814). All three comparators delivered 1.0 in all 60 comparator runs.

## AHBN Mechanism

The 8,921 controller trace rows preserve `z = -d_hat + l_hat + u_hat + c_hat`; `c_hat` is zero throughout because Exp08 has no churn. Across 5,246 S5 decisions, requested fanouts 2/3/4/5/6 occurred 1,464/3,562/40/62/118 times. Thus levels 5 and 6 were reached at every overload level, but were rare. Mean decision z by 700/1050/1400/2100 ms was -0.0922/-0.0846/-0.1054/-0.0848; it did not rise monotonically with configured overload. Cluster-mode share was 69.1%–73.8%. Realized clipping occurred in 62.9%–68.1% of decisions; mean realized fanout was 1.59–1.67 despite mean requested fanout 2.78–2.84, demonstrating eligible-neighbour/topology constraints.

## Delivery-Ratio Analysis

AHBN delivered less than every comparator in all 20 matched runs. Its condition deficits versus Gossip were 0.3565, 0.3270, 0.3750, and 0.3185. This was not driven by one seed: all five leave-one-seed-out subsets preserved the direction. AHBN delivery was non-monotonic for every seed, so the larger 2100-ms mean must not be presented as a systematic overload improvement.

The lower delivery coincided with meaningful cost reduction. Relative to Gossip, AHBN reduced duplicates by 70.2%–74.5%, reduced forwards by 33.5%–39.5%, and had 0.253–0.567 s lower mean delay. It also used fewer forwards than Structured and DC-SoC, but those algorithms achieved full delivery with zero recorded duplicates. The defensible interpretation is therefore an efficiency–reachability trade-off produced by **bounded adaptive fanout**, not maintained propagation performance.

## Scientific Interpretation

Result direction is **MIXED**. Expected evidence includes valid local-observation traces, monotone S5 action mapping from z, use of higher S5 levels, lower dissemination traffic than Gossip, and DC-SoC maintenance remaining zero for a slow-but-alive peer. Mixed/unexpected evidence includes uniformly lower AHBN delivery, non-monotonic delivery and z condition means, comparator-specific advantages, and frequent eligible-neighbour clipping. These are valid scientific findings, not implementation failures. See `docs/K5_exp08_final_scientific_interpretation.md`.

## Final K5 Gate

**PASS.** Independent recursive audit: 80/80 unique coordinates, zero missing/duplicate/unexpected coordinates, valid headline metric domains, 1,600/1,600 collected peer statuses ready and alive, overloaded target alive in every run, matching frozen hashes and image digest, DC-SoC maintenance zero, and zero controller/actuator invariant mismatches. Report: `outputs/k5_exp08_formal-20260902_092321/final_analysis/final_validation_report.md`.

## Freeze Status

**K5 EXP08 STATUS: FROZEN.** Freeze record: `docs/K5_EXP08_FROZEN.md`. Manuscript claim audit: `docs/K5_exp08_manuscript_claim_audit.md`. No further Exp08 tuning or reruns may be performed solely to improve performance.

## K5 Freeze Procedure

Completed on 2026-09-02. The immutable formal identity, recorded commit/working-tree state, image/digest, hashes, topology, coordinate reconciliation, aggregate and per-seed evidence, mechanism summaries, invariant totals, limitations, manuscript revisions, and artifact paths are recorded in `docs/K5_EXP08_FROZEN.md`.

Historical Exp08 material remains separately labeled in `docs/K5_exp08(k8s).md`; no historical numerical result is copied into this restart notebook.
