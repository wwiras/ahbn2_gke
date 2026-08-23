# K2 — AHBN Regression and Semantic Validation

## A. Verdict

```text
K2 FINAL STATUS: PASS
```

K2 was regression/semantic validation only. No scientific campaign, Kubernetes
cluster mutation, parameter tuning, comparator work, or production workload was
performed.

## B. Scope and method

The Kubernetes implementation was exercised in process against the untouched
ControlSim v0.61 sources at
`/Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61`. The K2 harness uses fixed
vectors, stateful sequences, a fixed-seed 800-update trajectory, adversarial
dispatch fixtures, and independent trace recomputation. ControlSim was read only.

The executable harness is `tests/test_k2.py` and is explicitly labelled
`K2 REGRESSION HARNESS — NOT A SCIENTIFIC EXPERIMENT`.

## C. Controller trajectory parity

All-zero, all-one, neutral, isolated-pressure, combined-pressure, monotonic,
oscillating, threshold-adjacent, and fixed-seed trajectories matched ControlSim
at every update for `d_hat`, `l_hat`, `u_hat`, `c_hat`, score, weight, mode, and
fanout (strict comparison to 14 decimal places). The 800-update sequence was run
twice and produced identical output. No NaN, infinity, bound violation, invalid
mode, or invalid fanout occurred.

The exact boundary is preserved: `weight >= 0.50` selects Gossip and
`weight < 0.50` selects Structured. Dense fanout validation over 1,001 weights,
including rounding boundaries, produced only 2, 3, or 4 and matched the canonical
mapping. Independent controller states remained peer-local.

## D. Observation validation

- Duplication: interval ratios 0, 0.5, and 1 were reproduced; a high window
  followed by reset and a zero-duplicate window yielded uncontaminated results.
- Latency: measured elapsed-time inputs 0, 100, 500, 1000, and 1500 ms normalized
  monotonically to 0, 0.1, 0.5, 1, and 1. The sensor uses elapsed time and exposes
  raw latency/count provenance.
- Utilization: `overload_ms` is an actuator; zero maps to `raw_u=0` and every
  positive tested magnitude maps to `raw_u=1`.
- Churn: no event yields zero; one join or leave with four neighbors yields 0.25;
  one join plus one leave yields 0.50; the zero-neighbor denominator is safe.
- Window integrity: raw counters reset atomically under the adapter lock while
  controller EWMA state persists. Separate adapter/controller instances do not
  share state.

Runtime availability uses `unavailable_neighbors` as a transition set: the first
failed communication records one leave, repeated failure does not; the first
later success removes the unavailable mark and records one join, while repeated
success does not.

## E. Utilization validation

The validated path is:

```text
overload_ms actuator -> controlled delay -> binary raw_u -> EWMA u_hat
-> canonical score -> canonical decision
```

Values 0, 1, 250, 700, and 5000 ms mapped to 0, 1, 1, 1, and 1. Rise and decay
sequences followed the canonical EWMA. `overload_ms` is absent from the controller
API and score; setting the actuator alone did not change mode or fanout. No
`overload_ms / overload_max` path exists.

## F. Dispatch parity

Gossip mode was compared directly with frozen v0.61 `AHBNStrategy` using the same
topology, sender, fanout, and RNG seed. Only physical eligible neighbors were
sampled; sender and self were excluded; structural head/gateway targets were not
appended; fanout was honored; targets were unique; roles did not alter Gossip.

Structured mode was likewise compared directly. A member forwards only to its
head (unless that head is sender/self). A head with a bounded AHBN fanout preserves
one gateway when available, fills remaining budget with members, then uses any
remaining budget for additional gateways. Thus canonical AHBN fanout bounds the
Structured target list while preserving the gateway obligation. Standalone
Structured behavior was not modified.

## G. Event and bypass validation

Failure handling only changes availability/churn observation state and contains
no direct mode/fanout assignment. Overload changes actuator/delay/sensor state,
not a decision directly. Frozen controller construction ignores legacy threshold
0.7, fanout [1,6], and default fanout 2 values. Experiment/run/scenario identity
does not enter the controller or observation equations; searches for Exp08,
Exp10, Exp11, Exp12, and experiment identifiers found no canonical decision branch.

Duplicate receipt increments its interval metric and returns before target
selection, so it is not re-forwarded. It can influence only a future `d_t`.

## H. State isolation and initialization

Two controllers and two observation adapters were driven with different inputs.
EWMA, duplicate, latency, churn, overload, mode, and fanout state remained local.
New controller state is `d_hat=l_hat=u_hat=c_hat=0`, score 0, weight 0.5,
mode Gossip, fanout 3. New observation counters are zero. No persistent restart
recovery was added; that remains B08.

## I. Trace integrity

For deterministic decisions, the four centred score terms, total score, sigmoid
weight, threshold mode, rounded fanout, `mode_changed`, and `fanout_changed` were
independently recomputed and matched. Production trace fields include raw d/l/u/c,
all EWMAs, all four contributions, total score, weight, mode, fanout, overload
milliseconds/active flag, duplicate counts, latency raw/count/normalized values,
and churn counts/denominator. The trace is sufficient to audit utilization and
sensor provenance without adding production metrics.

## J. K2 test matrix

All 62 catalog checks passed:

| Group | Checks | Result | Evidence |
|---|---:|---|---|
| Controller | K2-C01..K2-C10 | 10/10 PASS | trajectory, EWMA, boundary, 800-step and isolation tests |
| Observations | K2-O01..K2-O10 | 10/10 PASS | interval, latency, churn, reset and locality tests |
| Utilization | K2-U01..K2-U10 | 10/10 PASS | binary mapping, rise/decay and bypass tests |
| Dispatch | K2-D01..K2-D12 | 12/12 PASS | direct v0.61 parity and adversarial fixtures |
| Regression | K2-R01..K2-R10 | 10/10 PASS | event, legacy and experiment-independence checks |
| Trace | K2-T01..K2-T10 | 10/10 PASS | independent mathematical recomputation |

The 62 catalog items are grouped into 21 deterministic unittest methods. Together
with the nine K1 methods, the combined run executed 30 methods successfully.

## K. K1 and static regression

The complete K1 suite was rerun after the repair. Its documented logical matrix
remains `K1-T01..T34: 34/34 PASS` and `K1-U01..U13: 13/13 PASS`.

| Validation | Result |
|---|---|
| Python compilation | PASS (`PYTHONPYCACHEPREFIX=/tmp/k2_pycache`) |
| Combined K1 + K2 unittest run | PASS (30 methods) |
| Source YAML parsing | PASS (14 files) |
| Helm lint | PASS |
| Helm rendering | PASS (6 rendered objects) |
| Rendered YAML parsing | PASS (6 objects) |
| Shell syntax (`scripts/*.sh`) | PASS |
| `git diff --check` | PASS |

## L. Defects repaired

One K1 semantic defect was found and minimally repaired in `app/peer.py`.

Before repair, AHBN Gossip admitted self into the random sampling pool and removed
self only afterward, allowing self to consume controller fanout. It also converted
the sample through `sorted(set(...))`, changing frozen v0.61 sampled order.

The repair excludes self before sampling and uses order-preserving deduplication,
matching v0.61. No controller, sensor, threshold, coefficient, or fanout parameter
was changed. The full K1 and K2 suites passed after repair.

## M. Remaining blockers

- B05 Exp12 final experimental implementation
- B06 DC-SoC static/dynamic implementation
- B07 Exp10 targeting/timing
- B08 Exp11 churn orchestration/state handling
- B09 standalone Gossip reconciliation
- B11 distributed runtime seeding/reproducibility
- B12 final metric/recovery validation

K2 does not close these blockers. K3 was not started.
