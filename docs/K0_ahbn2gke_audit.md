# K0 — Read-only Kubernetes implementation audit

Audit date: 2026-08-23 (Asia/Kuala_Lumpur)  
Scope: previous `ahbn_gke.zip` versus frozen control-simulator `v0.61.zip`  
Filesystem changes: this report only. No production code, configuration, manifest, experiment, plot, or output was modified. No final experiment was run.

## A. Executive verdict

```text
K0 FINAL STATUS: PASS
```

The old Kubernetes implementation is **not** canonical v0.61 AHBN. K0 passes because the implementation was traced end-to-end and the required later changes are identified. The most serious findings are: the four-input EWMA/centred-score/sigmoid controller is absent; failure and overload bypass it; AHBN Gossip mode mixes Gossip with structural targets; bounds/defaults can be noncanonical; Exp12 does not implement the declared resource fractions; no genuine DC-SoC comparator exists; and the designated checkout contains none of the archived implementation files.

## B. Repository provenance

| Source | Root examined | Git/identity | Status |
|---|---|---|---|
| Designated project | `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke` | branch `main`, HEAD `3621d700d1abb07113eca8e8a6f6bf9fb4aa703d` | Clean, but HEAD contains only `.gitignore`, `LICENSE`, and `README.md`; no audit implementation |
| Previous Kubernetes source | `/Users/wwiras/Desktop/ahbn_gke.zip` (`ahbn_gke/`) | embedded branch `main`, HEAD `bad792042f18919bdf5e9e7b7e777d6f704e0595`; embedded `origin/main` is stale at `e949c376…` | Authoritative old-code audit input; not extracted or changed |
| Frozen simulator | `/Users/wwiras/Desktop/v0.61.zip` (`v0.61/`) | no Git metadata found in ZIP | Frozen semantic reference |

Runtime/build evidence: requested interpreter is Python 3.14.6; the K8s image is `python:3.11-slim`; `app/requirements.txt` pins grpcio 1.80.0, Kubernetes 35.0.0, NetworkX 3.6.1, PyYAML 6.0.3, pandas 3.0.2 and related plotting packages. The simulator requirements are unpinned lower bounds for PyYAML, NetworkX, pandas, matplotlib, and scikit-learn. Kubernetes uses a Helm chart (`helm/ahbn`) containing a ConfigMap, StatefulSet, controller Job, service/RBAC, and generated `topology.json`; launch entry points are `scripts/run_exp8.sh`, `run_exp10.sh`, `run_exp11.sh`, `run_exp12.sh`, and `run_experiment.sh`.

The K8s topology generator seeds NetworkX (`seed`, default 42), and churn selection uses `Random(seed + 99)`. Runtime Gossip/AHBN target selection uses module-global `random.sample` without an explicit seed, so targets are not reproducible. The scripts create timestamped runs but do not record image digest, Kubernetes/Helm versions, or dependency/runtime snapshots.

## C. Canonical AHBN discrepancy matrix

| Requirement | Canonical v0.61 behaviour | Previous K8s behaviour | Classification | Evidence | Required later action |
|---|---|---|---|---|---|
| Duplicate observation | Normalized `d`, EWMA to `d_hat` | Lifetime `duplicate_count / recv_count`; no EWMA | MISMATCH | K8s `peer.py:281-284`; canonical `control.py:139-152` | K1 define raw observation and feed canonical update |
| Latency observation | Normalized local latency pressure, EWMA `l_hat` | End-to-end `latency_ms` logged only | MISSING | `peer.py:769-793`; canonical `control.py:153-158` | K1 add legitimate normalized K8s mapping |
| Utilization observation | Normalized processing/utilization pressure, EWMA `u_hat` | Binary overload flags/delay; no measured input | MISSING | `peer.py:288-298` | K1 map an available runtime signal |
| Churn observation | Normalized instability pressure, EWMA `c_hat` | No churn state/input; only indirect failed sends | MISSING | no `c_hat` in `peer.py`; canonical `simulator.py:571-634` | K1 add runtime churn signal |
| Normalization | Every raw input clamped/normalized `[0,1]` | Ratio un-clamped; other inputs binary or absent | MISMATCH | canonical `control.py:105-121`; K8s `peer.py:281-298` | K1 centralize canonical contract |
| EWMA | `alpha=0.30` for d/l/u/c | None | MISSING | canonical `control.py:109-170` | K1 port unchanged equation |
| Centred score | Four centred terms, centres 0.50 | Threshold cascade; no score | MISSING | canonical `control.py:177-204`; K8s `peer.py:305-356` | K1 port unchanged equation |
| Coefficients | `-1,+1,-1,+1` | Absent | MISSING | canonical `control.py:50-69` | K1 port frozen values |
| Sigmoid | `W=sigmoid(kappa*S)`, kappa 1 | None | MISSING | canonical `control.py:123-133,210-232` | K1 port stable sigmoid |
| Mode threshold | `W >= .50` Gossip | duplicate threshold; emergency flags force Gossip; Exp8 overrides `.7` | MISMATCH | `peer.py:309-356`; `exp8_ahbn.yaml:30-33` | K1 remove alternate rule/override |
| Fanout equation | `round(clamp(2 + weight*2,2,4))`, beta 1 | default ±1 only | MISMATCH | canonical `control.py:303-318`; K8s `peer.py:330-356` | K1 port canonical calculation |
| Fanout bounds | `[2,4]` | generated defaults `[1,6]`; Exp8 AHBN `[1,4]` | MISMATCH | `gen_topology.py:440-446`; Exp8 YAML | K1 freeze `[2,4]` |
| Default fanout | 3 | default 3, but active Exp8 AHBN/10/11/12 use 2 | MISMATCH | `gen_topology.py:114-116`; experiment YAML | K1 preserve 3 |
| Exact mode execution | Gossip only Gossip; cluster only Structured | cluster pure; Gossip appends head/gateways | MISMATCH (`AHBN-MODE-MIXING`) | `peer.py:580-628`; canonical `strategies/ahbn.py:115-145` | K1 remove structural append |
| Sender/self/dedup | Exclude sender/self; deduplicate | Sender excluded; AHBN list deduped/self-filtered | EQUIVALENT | `peer.py:519-539,549-565,589-628` | K2 regression-test |
| Mode transitions | Solely canonical controller | failure and experiment flags mutate mode/fanout | MISMATCH | `peer.py:309-356,431-492` | K1 remove bypass paths |
| Failure reaction | Evidence changes observations, then controller | failed/rejected send directly sets Gossip/default+1 | MISMATCH | `peer.py:431-492,681-710` | K1 feed legitimate observation |
| Overload/bottleneck | Environment changes observations only | binary flag directly forces decision | MISMATCH | `peer.py:288-333` | K1 remove shortcut |
| Configuration | Frozen values across experiments | partial hard-coded block; YAML overrides | MISMATCH | `gen_topology.py:437-446`; Exp8 YAML | K1 freeze values |

End-to-end old path: gRPC receipt updates lifetime counters and duplicate state → overload delay → end-to-end latency log → `target_peers()` calls `adaptive_update()` for AHBN → threshold/shortcut cascade sets mode/default±1 fanout → cluster targets or sampled physical neighbours plus structural targets → asynchronous gRPC sends → success/failure logs and direct failure reaction.

The environmental injections (delay, fail-stop, pod delete) are valid. Their direct use to force an AHBN decision is invalid experiment/event-specific controller logic.

## D. Forwarding-semantics matrix

| Algorithm | Target eligibility | Sender/self exclusion | Fanout | Structural obligations | Duplicates | Controller |
|---|---|---|---|---|---|---|
| Gossip | Physical neighbours | Sender excluded; self implicitly absent | Always samples configured default; unlike normal frozen Exp08+ Gossip | None | logged then stopped | None; isolated |
| Structured | Member→head; head→members + adjacent heads | Sender excluded; deduped | No arbitrary cap | Retained | logged then stopped | None; isolated |
| DC-SoC | No implementation | N/A | N/A | Density/MASTER/CORE/TAIL absent | N/A | N/A |
| AHBN | Cluster mode Structured; Gossip samples neighbours **plus** head/gateways | Sender/self excluded; deduped | Noncanonical ±1 and configurable `[1,6]` | Gossip wrongly preserves backbone | logged then stopped | Noncanonical shortcuts |

Static clusters are contiguous ID blocks with heads at block starts; head gateways form a chain independent of graph density. Failed structural destinations remain in lists; no repair occurs. Pod recreation reloads the original ConfigMap and loses all in-memory seen/controller state.

## E. Experiment matrix

| Experiment | Current implementation | Frozen intended semantics | Difference | Later stage |
|---|---|---|---|---|
| Exp08(K8s) | BA 20/m=2/source 0; CH delay 250 ms in `exp8.yaml`, comparison files use 700 ms/20 messages; AHBN alone fanout 2/threshold .7 | CH overload; matched algorithms; canonical AHBN; simulator reference BA 100/m=3/factors `[1,1.5,2,3]` | Multiple definitions; AHBN-only settings break fairness; overload shortcut | K1/K3/K5 |
| Exp10 | BA 20/m=2/source 4; only CH failure at .03; `target_peer` ignored | Peer/CH failure; reference ER 100/p=.08/source 0, node/CH/overload modes | Default one-message workload may finish first; first eligible CH chosen; no repair | K1/K4/K5 |
| Exp11 | BA 20/m=2/source 4; four sequential pod deletes and waits | Pod churn; reference ER 100, cycles, 10%, 2 s downtime | immediate StatefulSet recreation; no downtime/fraction; state lost; no `c` | K1/K4/K5 |
| Exp12 | BA 20/m=2/source 4; first six non-CH peers get identical 350 ms delay | asymmetric delays/resource heterogeneity profiles | resource fractions/classes unused; no per-peer resources or utilization input | K1/K5 |

All active YAMLs use topology seed 42. Exp8 comparison topology/workload matches except for AHBN’s fanout/controller override. No unified comparator campaign exists for Exp10/11/12. Commented alternatives in Exp10, Exp11, Helm values, and the controller Job are stale and non-authoritative.

## F. Runtime-observation and metrics map

| Input | Available K8s signal | Limitation |
|---|---|---|
| `d` | counts and `received_duplicate` | current lifetime ratio is noncanonical; mapping deferred |
| `l` | `received_new.latency_ms`, timeout/failure, injected delay | end-to-end latency; not fed to controller |
| `u` | `overload_ms`, pod requests/limits | no measured CPU/queue/processing utilization or resource class |
| `c` | pod delete/recovered logs; failed sends | peers receive no membership/recovery event or churn window/rate |

Delivery ratio, receipt delay, duplicates, and successful forwards are derivable. Exp10 recovery time is last receipt minus failure timestamp, which is not robust when no post-failure recovery occurs. Failed attempts are excluded from `total_forwards`, and concatenated pod logs are not globally sorted.

Canonical decisions cannot be independently audited: logs omit raw canonical d/l/u/c, all EWMAs, score, weight, coefficients, and normalization provenance. Existing logs do include old duplicate/fail/overload pressures, mode/fanout, transitions, and triggers.

## G. DC-SoC gap analysis

### Static structure

Generic ID-block Structured clustering exists, but there is no `dcsoc` strategy, density clustering, MASTER/CORE/TAIL roles, MASTER→CORE→TAIL forwarding, or DC-SoC structural obligations. All are **MISSING**.

### Dynamic maintenance

Inactive removal, deterministic CORE replacement, relationship repair, join/rejoin assignment, periodic reclustering, and recovery-state transfer are **MISSING**. No maintenance diagnostic events exist. JSON logging could support them later. Overload is operationally distinct from fail-stop/pod deletion, which is correct and must remain so.

## H. Blockers

| ID | Priority | Issue |
|---|---|---|
| B01 | P0 | Canonical four-observation EWMA/score/sigmoid controller absent |
| B02 | P0 | AHBN-MODE-MIXING in Gossip mode |
| B03 | P0 | Failure/bottleneck/overload directly override decisions |
| B04 | P0 | Fanout equation/bounds/default and threshold noncanonical |
| B05 | P0 | Exp12 resource heterogeneity declarations not implemented |
| B06 | P0 | No genuine DC-SoC or maintenance |
| B07 | P1 | Exp10 target ignored; timing/workload may make failure ineffective |
| B08 | P1 | Exp11 recreation loses state and lacks intended downtime/cycles |
| B09 | P1 | Standalone Gossip always fanout-limited |
| B10 | P1 | Designated checkout lacks archived implementation |
| B11 | P2 | Runtime sampling unseeded; image digest/tool versions unrecorded |
| B12 | P2 | Canonical trace missing; recovery metric weak |
| B13 | P3 | Stale commented alternatives and unreachable controller block |

Critical semantic blockers: 6 (`B01`–`B06`).

## I. Mandatory K0 checks

| Check | Result | Evidence |
|---|---|---|
| K0-01 canonical controller | MISMATCH | `peer.py:274-381` vs `control.py:96-344` |
| K0-02 d/l/u/c represented | MISSING | only duplicate ratio plus binary shortcuts |
| K0-03 EWMA | MISSING | absent |
| K0-04 centred score | MISSING | absent |
| K0-05 sigmoid | MISSING | absent |
| K0-06 coefficients | MISSING | absent |
| K0-07 threshold .50 | MISMATCH | Exp8 `.7`; wrong variable semantics |
| K0-08 bounds [2,4] | MISMATCH | `[1,6]` default; `[1,4]` Exp8 |
| K0-09 default 3 | MISMATCH | active configs use 2 |
| K0-10 AHBN Gossip pure | MISMATCH | structural append at `peer.py:605-620` |
| K0-11 AHBN Structured pure | MATCH | delegates to cluster targets |
| K0-12 mixing absent | MISMATCH | AHBN-MODE-MIXING |
| K0-13 sender exclusion | MATCH | all forwarding paths filter sender |
| K0-14 no experiment shortcuts | MISMATCH | event flags force decision |
| K0-15 failure through observations | MISMATCH | direct mutation |
| K0-16 churn through observations | MISSING | no churn input |
| K0-17 Gossip isolated | MATCH | early strategy branch |
| K0-18 Structured isolated | MATCH | early strategy branch |
| K0-19 obligations untruncated | MATCH | full cluster list returned |
| K0-20 genuine DC-SoC | MISSING | no source/selector |
| K0-21 density roles | MISSING | ID-block cluster only |
| K0-22 DC-SoC no truncation | NOT APPLICABLE/MISSING | comparator absent |
| K0-23 DC-SoC no AHBN | NOT APPLICABLE/MISSING | comparator absent |
| K0-24 failure/core replacement | MISSING | absent |
| K0-25 leave/rejoin maintenance | MISSING | absent |
| K0-26 periodic reclustering | MISSING | absent |
| K0-27 overload != failure | MATCH | distinct RPC/action paths |
| K0-28 definitions frozen-consistent | MISMATCH | experiment matrix |
| K0-29 metrics observable | EQUIVALENT (partial) | headline events exist; recovery weak |
| K0-30 decisions auditable | MISSING | no EWMAs/score/weight |
| K0-31 matched comparisons | MISMATCH | AHBN-only Exp8 settings; other campaigns absent |
| K0-32 reproducible seeds | MISMATCH | target sampling unseeded |

## J. Later-stage boundary (not implemented)

- **K1:** canonical AHBN port and evidence-based K8s observation acquisition.
- **K2:** deterministic regression tests for equations, bounds, exact dispatch, exclusions, and deduplication.
- **K3:** Gossip/Structured semantic reconciliation.
- **K4:** scoped DC-SoC static structure plus Exp10/11 maintenance.
- **K5:** reconcile code into the checkout, seed distributed choices, validate manifests/config contracts, and run sanity validation—not the final campaign.

## K. Commands and terminal evidence

No experiments, Kubernetes mutations, builds, installs, or source execution occurred. Commands were read-only except creation of this report:

```text
sed -n '<ranges>' <attached pasted-text.txt>
unzip -Z1 /Users/wwiras/Desktop/{ahbn_gke,v0.61}.zip
find <project-root> -maxdepth 2 -type f
git status --short --branch
git rev-parse --show-toplevel; git rev-parse HEAD; git branch --show-current
git ls-tree -r --name-only HEAD
unzip -p <zip> <relevant-file> | nl -ba
<expected-python> --version
unzip -p ahbn_gke.zip <python-file> | <expected-python> -c 'compile(...)'
rg -n '<metrics/controller patterns>' over streamed archived files
```

Key terminal output:

```text
## main...origin/main
/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
3621d700d1abb07113eca8e8a6f6bf9fb4aa703d
main
.gitignore
LICENSE
README.md

Python 3.14.6
compile app/controller.py: OK
compile app/peer.py: OK
compile app/gen_topology.py: OK

archived HEAD: ref: refs/heads/main
archived main: bad792042f18919bdf5e9e7b7e777d6f704e0595
archived origin/main: e949c376f5140e0171f1d2d9b901c5d7d906aa64
```

Unexpected result: the project root is a clean skeletal checkout, so the audit streamed the supplied ZIP and did not populate the checkout. `controller.py:79-123` is unreachable after `wait_for_peer_ready` returns/raises; it compiles but is dead code.

## Final terminal summary

```text
K0 FINAL STATUS: PASS

Canonical AHBN:
- matching checks: exact Structured dispatch and exclusion mechanics only
- mismatching checks: controller, mode mixing, fanout, thresholds, bypasses
- missing checks: l/u/c, EWMA, score, sigmoid, coefficients, canonical trace

Critical semantic blockers:
- count: 6
- identifiers: B01, B02, B03, B04, B05, B06

Gossip:
- status: ISOLATED BUT SEMANTIC MISMATCH
Structured:
- status: ISOLATED; STATIC OBLIGATIONS MATCH; NO FAILURE REPAIR
DC-SoC:
- static structure status: MISSING
- dynamic maintenance status: MISSING
Exp08(K8s):
- audit status: COMPLETE — gaps identified
Exp10:
- audit status: COMPLETE — gaps identified
Exp11:
- audit status: COMPLETE — gaps identified
Exp12:
- audit status: COMPLETE — gaps identified

Production code modified: NO
Experiment configs modified: NO
Final experiments executed: NO

Audit report:
docs/K0_ahbn2gke_audit.md
```
