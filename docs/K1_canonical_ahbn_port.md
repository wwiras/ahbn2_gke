# K1 — Canonical AHBN port to Kubernetes

## A. Verdict

```text
K1 FINAL STATUS: PASS
```

No Kubernetes deployment or scientific experiment was run. ControlSim v0.61
was read as the authority and was not modified.

## B. Modified files

- `app/ahbn_controller.py` — isolated, environment-independent canonical controller.
- `app/observations.py` — interval-local Kubernetes observation acquisition.
- `app/peer.py` — sensor integration, trace emission, pure-mode dispatch, and churn signals.
- `app/peer.proto` — per-hop send timestamp used by the latency sensor.
- `app/Dockerfile` — includes the two new runtime modules.
- `tests/test_k1.py` — deterministic controller, sensor, equivalence, and bypass tests.
- `docs/K1_canonical_ahbn_port.md` — K1 design and evidence.

## C. Controller equivalence

The authority is `AHBNProj/ahbn/v0.61/ahbn/control.py`. Its Kubernetes port is
`app/ahbn_controller.py:CanonicalAHBNController`.

| Component | Frozen v0.61 | Kubernetes location |
|---|---|---|
| inputs | normalized `d,l,u,c` | `CanonicalAHBNController.update` arguments |
| EWMA | `alpha*x + (1-alpha)*old` | `ewma` |
| centres | `d0=l0=u0=c0=0.5` | `AHBNParams` |
| coefficients | `(-1,+1,-1,+1)` | `AHBNParams` |
| score | centred weighted sum | `update` |
| sigmoid | stable logistic, `kappa=1` | `sigmoid` |
| mode | weight `>=0.5` Gossip, else cluster | `update` |
| fanout | `round(clamp(2 + weight*2,2,4))` | `update` |
| default/bounds | `3`, `[2,4]` | `AHBNParams` |
| emergency path | none in frozen controller | none added |

Legacy topology `ahbn` overrides and AHBN top-level fanout values are ignored.
There is no Kubernetes-specific `u0`, utilization coefficient, or controller
parameter. Same inputs deterministically produce the same outputs.

## D. Observation architecture

`KubernetesObservationAdapter` is separate from the controller. A window ends
at each AHBN evaluation (a local receive). Counters reset atomically afterward;
an empty window produces zero. All outputs are clamped or naturally bounded to
`[0,1]`.

| Input | Meaning and Kubernetes measurement | Normalization / limitation |
|---|---|---|
| `d` | duplicate receipts / all receipts in the closed window | zero receipts gives `0`; interval, not lifetime |
| `l` | mean local time from the previous hop's `sent_at` through local controlled processing | `min(1, mean_seconds/1.0 second)`; fixed K1 reference, not outcome-tuned |
| `u` | normalized local dissemination processing pressure | overload inactive `0`, active `1`; controller EWMA supplies smoothing |
| `c` | newly unavailable + newly returned neighbors | `(joins+leaves)/max(neighbor_count,1)`, saturated at one |

Failed/rejected sends record one leave transition. A later successful send to
that neighbor records one join transition. They do not mutate mode or fanout.

## E. Utilization

- Term: **Utilization (`u_t`)**.
- Semantic meaning: normalized local processing pressure experienced by the
  dissemination service.
- ControlSim sensor: queueing-based `lambda * mean_service_time / m` design.
- GKE experimental actuator: `overload_ms` imposes real processing delay.
- GKE observation: binary controlled processing-pressure state.
- Mapping: inactive `=0.0`; active `=1.0`.
- `250 ms -> u=1.0` and `700 ms -> u=1.0`.
- Overload magnitude is not the utilization metric and never enters the score.
- After acquisition, `raw_u` follows the common EWMA, score, sigmoid, mode, and
  fanout path with no special branch.

## F. Removed legacy logic

- Failed sends no longer force Gossip or increment fanout.
- Overload and bottleneck state no longer force Gossip or alter fanout.
- The cumulative duplicate-threshold decision cascade was removed.
- Experiment/configuration controller overrides no longer affect AHBN.
- AHBN Gossip no longer appends gateways or the cluster head.
- The frozen controller has no direct emergency path, so none was invented.

## G. Dispatch validation

Gossip samples only eligible physical neighbors using runtime fanout. Structured
mode uses only structural targets. Both exclude sender and self and deduplicate.
For an AHBN cluster head, the bounded structured selection preserves one gateway
path where available, then members, then remaining gateways, matching v0.61.
Standalone comparator semantics were not otherwise reconciled (B09 remains).

## H. Trace schema

Every AHBN evaluation emits `ahbn_controller_trace` with timestamp (the common
logger's `ts`), peer/run/experiment context, `raw_d/raw_l/raw_u/raw_c`, all four
EWMA states, four named score contributions, total `score`, `weight`, `mode`,
`fanout`, `mode_changed`, and `fanout_changed`. Diagnostics include
`utilization_source`, `overload_active`, `overload_ms`, duplicate counts,
latency count/raw/normalized values, churn join/leave counts, and neighbor count.

## I. Test evidence

Evidence is `python3 -m unittest discover -s tests -v` plus static inspection.

| ID | Result | Evidence |
|---|---|---|
| K1-T01 | PASS | raw-input clamp assertions |
| K1-T02 | PASS | EWMA bound assertions |
| K1-T03 | PASS | `.3`, then `.51` exact sequence |
| K1-T04 | PASS | explicit centred-score assertion |
| K1-T05 | PASS | frozen parameter/sign tuple |
| K1-T06 | PASS | explicit logistic comparison |
| K1-T07 | PASS | weight bounds |
| K1-T08 | PASS | v0.61 reference sequence |
| K1-T09 | PASS | v0.61 reference fanout sequence |
| K1-T10 | PASS | `[2,4]` assertions |
| K1-T11 | PASS | neutral reference vector |
| K1-T12 | PASS | eight additional reference vectors |
| K1-T13 | PASS | zero-duplicate window |
| K1-T14 | PASS | all-duplicate window |
| K1-T15 | PASS | snapshot reset test |
| K1-T16 | PASS | empty/minimum latency is zero |
| K1-T17 | PASS | `.1`, `.3`, and saturation cases |
| K1-T18 | PASS | overload inactive maps to zero |
| K1-T19 | PASS | active maps to one |
| K1-T20 | PASS | `.3`, `.51` canonical EWMA test |
| K1-T21 | PASS | no events yields zero churn |
| K1-T22 | PASS | join/leave tests |
| K1-T23 | PASS | zero-neighbor denominator test |
| K1-T24 | PASS | adapter API has no experiment input |
| K1-T25 | PASS | Gossip branch static verification |
| K1-T26 | PASS | no structural fields in Gossip branch |
| K1-T27 | PASS | bounded structural selection implementation |
| K1-T28 | PASS | sender filters in both modes |
| K1-T29 | PASS | self filters in both modes |
| K1-T30 | PASS | order-preserving/set deduplication |
| K1-T31 | PASS | failure handler has no decision assignment |
| K1-T32 | PASS | overload RPC has no decision assignment |
| K1-T33 | PASS | bottleneck absent from controller transition |
| K1-T34 | PASS | controller API and adapter ignore experiment ID |

| ID | Result | Evidence |
|---|---|---|
| K1-U01 | PASS | `utilization(0)==0` |
| K1-U02 | PASS | `utilization(250)==1` |
| K1-U03 | PASS | `250` and `700` both equal one |
| K1-U04 | PASS | controller receives `snapshot.u`, never milliseconds |
| K1-U05 | PASS | canonical `update` applies utilization EWMA |
| K1-U06 | PASS | `0 -> .3 -> .51` |
| K1-U07 | PASS | bound assertion |
| K1-U08 | PASS | overload handler does not set mode |
| K1-U09 | PASS | overload handler does not set fanout |
| K1-U10 | PASS | sole `u0` is frozen `AHBNParams.u0` |
| K1-U11 | PASS | sole `w_u` is frozen `AHBNParams.w_u` |
| K1-U12 | PASS | experiment identifier never enters controller |
| K1-U13 | PASS | direct nine-vector v0.61 comparison |

## J. Cross-environment reference vectors

The test loads the untouched v0.61 `control.py` and feeds both controllers the
same sequence: neutral, high duplication, high latency, high utilization, high
churn, all-high, all-low, structured-preference, and Gossip-preference vectors.
At every step, `d_hat/l_hat/u_hat/c_hat`, score, weight, mode, and fanout agree
to 14 decimal places (mode and fanout exactly).

## K. Remaining blockers

- B05 Exp12 final experimental implementation
- B06 DC-SoC static and dynamic implementation
- B07 Exp10 targeting/timing
- B08 Exp11 churn orchestration/state handling
- B09 standalone Gossip reconciliation
- B11 distributed runtime seeding/reproducibility
- B12 final metrics/recovery validation

The scientific interpretation is: AHBN employs a single adaptive controller
across environments. Sensors may be environment-specific, but after normalized
`d,l,u,c` enter the controller, EWMA, score, sigmoid, mode, and fanout are the
same. Correctness is mathematical equivalence, not a desired experimental
transition or performance advantage.
