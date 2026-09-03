# K6 — Exp10: Peer / CH Failures

## Stage and immutable provenance

K5 is the completed actuator-validation stage. Its `app/k5_final_actuator_policy.py` and `app/k5_final_actuator_runtime.py` are immutable. K6 inherits the frozen S5 behavior through stage-specific copies, `app/k6_final_actuator_policy.py` and `app/k6_final_actuator_runtime.py`. Policy boundary tests and normalized runtime-AST comparison prove behavioral parity; the shared canonical controller, observations, peer protocol, and forwarding implementation are not duplicated or changed for stage naming.

Frozen K5 hashes are:

- policy: `8c7a0658cd226d0349e3ed3c64c943887196fdee57d9ef06874fd8525b683cff`
- runtime: `1d95271079064b6c159fcb9d7b553c03cc8b6cb42893f1b8e92bf8f4b6e95a25`
- controller: `dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8`
- peer: `64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a`

K6 preserves the observation inputs, EWMA, `z = -d_hat + l_hat + u_hat + c_hat`, mode threshold, S5 mapping, eligible-neighbor constraints, and peer-selection semantics. No failure-specific AHBN override exists.

## Historical smoke and migration reason

`outputs/k5_exp10_smoke-20260903T022035Z` is valid, immutable pre-formal evidence created before stage naming was corrected. It contains four matched seed-42 runs with source peer 1 and failed peer 0, actual pod-unavailability evidence, valid comparator roles, one logical DC-SoC CORE replacement, natural maintenance timing, post-failure AHBN traces, auditable `survivor_full_delivery` recovery, explicit AHBN censoring, and a complete four-run analysis. Poor AHBN performance is data, not an execution anomaly.

An earlier smoke at `outputs/k5_exp10_smoke-20260902T181432Z` was invalid because source peer 0 was deleted. Source exclusion then revealed that source 0 was the only DC-SoC CORE in seeds 42, 44, and 46. The Exp10-only matched-source rule selects the lowest-ID peer that is neither a Structured CH nor a DC-SoC CORE, identically for all treatments. Failure targets always exclude that source and fail closed if no native target exists.

The canonical migration changes naming and wiring only: `k6_exp10` metadata and run IDs, `scripts/run_k6_exp10.sh`, `scripts/k6_exp10_analysis.py`, namespace `ahbn-k6-exp10`, K6 output prefixes, and K6 container entrypoints. Historical K5-prefixed artifacts remain readable by the K6 parser.

## Frozen experiment contract

The experiment remains BA `N=20`, `m=2`, seeds 42–46, 20 messages at 0.4 seconds, failure trigger 0.5 seconds, and settle/timeout 18 seconds. Treatment order is Gossip, Structured, DC-SoC-inspired, AHBN. For each seed, physical topology, source, workload, trigger, size, BA parameters, and timeout are matched.

Targets are highest physical degree excluding source for Gossip/AHBN, highest-degree non-source CH for Structured, and highest-degree non-source CORE for DC-SoC; ties use lowest numeric ID. Gossip and Structured receive no structural repair. DC-SoC performs deterministic local CORE replacement and relationship repair without synthetic delay. Recovery remains the first post-unavailability message delivered to every surviving peer; absence is explicitly censored.

Offline contract status is PASS for seeds 42, 43, 44, 45, and 46.

## Second migration-integrity smoke

The second smoke validates only the K5→K6 stage boundary, K6 imports/packaging/naming, and unchanged end-to-end execution plumbing. No performance threshold applies and it must not be rerun merely because AHBN performs poorly.

Build and push manually:

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
IMAGE=wwiras/ahbn2-peer:k6-exp10-frozen-s5-20260903-amd64 ./scripts/build_k6_exp10_image.sh
```

Run exactly one second smoke manually:

```bash
IMAGE=wwiras/ahbn2-peer:k6-exp10-frozen-s5-20260903-amd64 ./scripts/run_k6_exp10.sh smoke
```

Expected output is `outputs/k6_exp10_smoke-<UTC>/` using namespace `ahbn-k6-exp10` and run IDs `k6_exp10_<treatment>_seed42`.

Pass requires four matched treatments; a surviving common source distinct from every target; actual deletion/unavailability evidence; CH and CORE target validity; no Gossip/Structured repair; one logical DC-SoC replacement with natural timing; post-failure AHBN/S5 traces without override; all five primary metrics or explicit recovery censoring; and completed K6 analysis. The user performs all Docker and GKE operations manually.

DO NOT RUN FORMAL YET. Return the second K6 migration-integrity smoke for review first.
