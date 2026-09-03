# Legacy K5-Prefixed Exp10 Preparation History

This document preserves the pre-migration implementation history. The scientific stage is **K6 — Exp10: Peer / CH Failures** and canonical subsequent execution is documented in `docs/K6_ahbn2gke_exp10.md`. The valid pre-formal smoke at `outputs/k5_exp10_smoke-20260903T022035Z` was produced under the legacy `k5_exp10` implementation prefix and remains immutable.

# K5 Exp10 GKE — Peer / CH Failures

## Objective and scope

Exp10 measures robustness, disruption, continued dissemination, and recovery after genuine Kubernetes pod unavailability during active dissemination. It has exactly four treatments: Gossip, Structured, DC-SoC-inspired, and AHBN. It is not an AHBN tuning experiment and adds no hypotheses, treatments, penalties, security mechanisms, or controller variants.

The authoritative AHBN lineage is the frozen K5 Exp08 implementation in `app/ahbn_controller.py`, `app/peer.py`, `app/k5_final_actuator_policy.py`, and `app/k5_final_actuator_runtime.py`. Exp10 verifies the canonical hashes before and after execution. The observation equation, EWMA, score, coefficients, mode threshold, S5 actuator mapping, topology-aware eligibility, and local-controller semantics are unchanged.

## Matched design

Every seed uses the same BA physical graph (`N=20`, `m=2`), 20-message workload at 0.4 s intervals, failure trigger 0.5 s after injection starts, and 18 s settle/timeout convention. Formal seeds are 42–46. Smoke uses seed 42. Treatment order is Gossip, Structured, DC-SoC, AHBN.

The source is derived once per seed from the realized physical graph and both frozen structural overlays. Eligible sources are peers that are neither a Structured CH nor a DC-SoC CORE; the lowest numeric eligible peer is selected. The selected source is written identically into all four treatment configurations. This changes no physical edge, cluster, role, workload, or comparator behavior.

Target selection is deterministic over each realized overlay after excluding `message_source`: Structured selects the highest-degree remaining CH; DC-SoC selects the highest-degree remaining CORE; Gossip and AHBN select the highest-degree remaining physical peer. Ties use lowest numeric peer ID. The source can never be selected. If no non-source CH or CORE exists, preflight stops the run as invalid without falling back to the source. A common identity is used whenever these native candidate sets yield one, but native structural criticality takes precedence where they do not overlap. The target record contains peer ID, role, cluster, physical degree, selection basis, trigger time, deletion-request time, original pod UID, observed-unavailability time, and observation evidence.

### Source-deletion anomaly and five-seed audit

The first seed-42 smoke (`outputs/k5_exp10_smoke-20260902T181432Z`) selected peer 0 for all treatments while peer 0 was also `message_source`; those results are invalid execution evidence and formal remained stopped. Source exclusion then correctly exposed that seed 42's only DC-SoC CORE was peer 0. Offline audit showed the same incompatibility in formal seeds 44 and 46, so changing only the smoke seed would not repair the formal design.

| Seed | Original source | Structured CHs | Non-source CH | DC-SoC COREs | Non-source CORE | Final source |
|---:|---:|---|---|---|---|---:|
| 42 | 0 | 0, 5, 10, 15 | yes | 0 | no | 1 |
| 43 | 0 | 0, 5, 10, 15 | yes | 3 | yes | 1 |
| 44 | 0 | 0, 5, 10, 15 | yes | 0 | no | 1 |
| 45 | 0 | 0, 5, 10, 15 | yes | 1 | yes | 2 |
| 46 | 0 | 0, 5, 10, 15 | yes | 0 | no | 1 |

After deterministic source selection, every seed has a non-source Structured CH and non-source DC-SoC CORE, and all four treatment topologies pass the matched scenario contract. The frozen AHBN controller, peer semantics, and S5 actuator hashes remain unchanged.

## Failure and treatment-native behavior

The controller injects workload and failure concurrently. At the trigger it calls the Kubernetes pod-delete API with zero grace period and does not accept the request alone as evidence: it polls until the original pod UID is absent, replaced, or observed NotReady. StatefulSet recreation is infrastructure behavior, not a fabricated protocol recovery.

- Gossip receives no structural repair; surviving redundant paths continue naturally.
- Structured receives no election, repair, or Gossip fallback. A recreated ordinal may resume from the same static configuration, but Exp10 adds no structural reconstruction.
- DC-SoC-inspired marks the deleted CORE inactive at surviving peers, excludes it, elects the highest-degree survivor in the affected cluster (lowest ID on ties), repairs parent/child edges, and resumes its structured forwarding.
- AHBN reacts only when genuine failed sends update its existing local leave/churn observations. Exp10 does not force mode or fanout.

The DC-SoC comparator is DC-SoC-inspired and does not reproduce the complete social/trust/economic mechanism of Dong et al. No artificial reconstruction penalty is injected. Maintenance start/end use wall-clock event timestamps, while duration is measured from the actual in-process operation with a monotonic timer.

## Recovery definition and metrics

The prior legacy definition, last receipt minus failure time, is rejected. `recovery_time_s` is measured from `pod_unavailability_observed.ts` to the completion timestamp of the first message injected at or after that observation that is received by every surviving peer (`all N-1 peers other than the deleted target`). The qualifying message ID and raw receipts remain auditable. A run with no qualifying message is `recovered=false`, `recovery_time_s=null`, and is counted as censored/unrecovered; it is never assigned zero and is not silently excluded.

Primary outcomes are exactly delivery ratio, propagation delay, duplicates, total forwards, and recovery time. DC-SoC maintenance and AHBN traces are diagnostic. Low delivery, high traffic/delay, branch disruption, and unrecovered outcomes are valid data. Deployment/image/topology mismatches, an unobserved deletion, missing artifacts, or controller invariant violations invalidate execution.

## Outputs and validation

Smoke writes `outputs/k5_exp10_smoke-<UTC>/`; formal writes `outputs/k5_exp10-<UTC>/`. The root contains `terminal.log`, generated configurations/topologies, image and Git provenance, canonical hashes, per-run raw logs and pod evidence, role mapping, `failure_events.json`, maintenance/AHBN traces, `metrics.json`, and aggregate, paired, completeness summaries under `results/`.

Preflight validates the interpreter, tools, context, pod-delete authorization, frozen hashes, unit tests, matched topology/workload, S5 metadata, and treatment isolation. Per-run validation requires one target/trigger/observed-unavailability chain, 20 injections, a native structural target, DC-SoC-only repair, deterministic replacement, monotonic measured maintenance, AHBN-only traces, and computable metrics. The runner stops with its current stage/seed/treatment and preserves logs on failure.

## Manual procedure

A new image is required because `controller.py`, `dcsoc_maintenance.py`, and topology metadata changed. Do not overwrite the frozen Exp08 tag. Build and push manually:

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
IMAGE=wwiras/ahbn2-peer:k5-exp10-frozen-s5-matchedsource-20260903-amd64 ./scripts/build_k5_exp10_image.sh
```

Equivalent exact commands:

```bash
docker buildx build --platform linux/amd64 --load -f app/Dockerfile.k5_final_actuator -t wwiras/ahbn2-peer:k5-exp10-frozen-s5-matchedsource-20260903-amd64 app
docker push wwiras/ahbn2-peer:k5-exp10-frozen-s5-matchedsource-20260903-amd64
```

Smoke (implementation evidence only):

```bash
IMAGE=wwiras/ahbn2-peer:k5-exp10-frozen-s5-matchedsource-20260903-amd64 ./scripts/run_k5_exp10.sh smoke
```

After smoke passes, formal:

```bash
IMAGE=wwiras/ahbn2-peer:k5-exp10-frozen-s5-matchedsource-20260903-amd64 ./scripts/run_k5_exp10.sh formal
```

No GKE run, pod deletion, image build, or image push was performed during preparation.

## Exclusions — no more, no less

No Q-AHBN, actuator comparison, controller retuning, direct failure bonus, forced mode/fanout, full DC-SoC trust/economic system, reconstruction sleep, simulated failure, security experiment, or automatic rerun of poor protocol outcomes is included. Historical `docs/exp10*.md` and the old manuscript remain reference history only.
