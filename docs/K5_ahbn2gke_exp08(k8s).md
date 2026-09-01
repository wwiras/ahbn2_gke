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

The user manually built and pushed `wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-amd64`. Verified platform: `linux/amd64`. Registry digest observed after pull: `sha256:eb6281a87417e97a8e1dfa78c3ac7197be08c6c8ed2b44ede8e5408351e8ddfa`. That image resolved the architecture failure but omitted the final-actuator modules/runtime; a new immutable trace-fix image is therefore required.

## Docker Architecture Failure

The previous smoke stopped before scientific execution with `exec /usr/local/bin/python: exec format error`. This is classified as an infrastructure/container architecture issue—not an AHBN controller, actuator, Gossip, Structured, DC-SoC, or Exp08 scientific failure.

## Corrective Action

The corrected image is `wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-amd64`, verified as `linux/amd64`, with observed registry digest `sha256:eb6281a87417e97a8e1dfa78c3ac7197be08c6c8ed2b44ede8e5408351e8ddfa`.

## Missing Final-Actuator Trace Integration Event

Smoke `20260902_015208` passed Kubernetes rollout/readiness and completed both Gossip runs, both Structured runs, and both DC-SoC runs. At `k5_ahbn_seed42_factor1.0`, collection contained 454 `ahbn_controller_trace` rows and 264 canonical `ahbn_forwarding_decision` rows but zero `k5_final_actuator_decision` rows. The image had been built from `app/Dockerfile`, which omitted both final-actuator modules and started `peer.py`; S5 was therefore not packaged or invoked. This is an integration/packaging failure, not an AHBN scientific failure.

Smoke diagnostics included Structured factor 3.0 delivery ratio 1.0, propagation delay approximately 1.94685 s, zero duplicates, and 380 total forwards; DC-SoC factor 1.0 delivery ratio 1.0, propagation delay approximately 0.85422 s, and maintenance count 0; DC-SoC factor 3.0 delivery ratio 1.0, propagation delay approximately 2.16760 s, and maintenance count 0. These are smoke diagnostics only and are not formal scientific results.

Smoke result: **FAIL — integration/trace gate**. The minimal correction packages `k5_final_actuator_policy.py` and `k5_final_actuator_runtime.py` in `app/Dockerfile` and starts the accepted wrapper. Canonical controller and S5 policy logic are unchanged. The next immutable image is `wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64`.

## Local Validation

Focused: 28 passed. Complete relevant K5/actuator set: 93 passed plus 16 subtests. Generated comparator contract: PASS; expected formal runs: 80. Commands and summaries are reported in the preparation handoff.

## Smoke Command

`IMAGE=wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64 scripts/run_k5_exp08_smoke.sh`

## Smoke Terminal Output

[pending manual execution]

## Smoke Result

[pending]

## Formal Command

Only enabled after smoke PASS: `IMAGE=wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64 scripts/run_k5_exp08_formal.sh --smoke-report outputs/k5_exp08_smoke-<timestamp>/terminal.log`

## Formal Terminal Output

[pending manual execution]

## Formal Results

[pending]

## Statistical Validation

[pending]

## Scientific Interpretation

[pending]

## Final K5 Gate

[pending]

Historical Exp08 material remains separately labeled in `docs/K5_exp08(k8s).md`; no historical numerical result is copied into this restart notebook.
