# K5 actuator investigation log

## Phase 2A — offline z-occupancy parity diagnostic (2026-08-31)

No GKE, Kubernetes or canonical-code action was performed. The offline command
was:

```bash
PYTHONPYCACHEPREFIX=/tmp/k5_phase2a_pycache \
  /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
  scripts/k5_phase2a_z_parity.py
```

It recovered all 4,184 controller JSON values from the ten existing Phase 1
GKE logs (including 32 values concatenated onto shared physical lines), loaded
the 600 Phase 2 Python states, and produced the required artifacts under
`outputs/k5_phase2a_z_parity/`.

Formula parity passed exactly: GKE mismatches 0, Python mismatches 0, maximum
absolute error 0 at tolerance `1e-12`. Exact-region occupancy was GKE/Python:
`z<=-.25` 55.449%/0%; moderate 41.969%/25%; `.25<=z<.90`
.860%/20.500%; `.90<=z<1.50` .789%/6.167%; and `z>=1.50`
.932%/48.333%. The prior 108/4,184 (2.58%) is the full `z>=.25` region,
not the `z>=1.50` region.

Python's high-z rows average `d_hat=.127`, `l_hat=.840`, `u_hat=.864`,
`c_hat=.693`, and `z=2.270`. Overall Python-minus-GKE component means are
`-.090`, `+.555`, `+.582`, and `+.445` respectively. Utilization is the
largest upward mean contributor, latency is a close second, and the Python
schedule's sustained churn—versus exactly zero GKE churn—is also material.

Controller-boundary normalization, clipping, alpha `.3`, zero initialization,
update order, score, signs and thresholds match. Observation generation and
cadence intentionally differ: GKE rows are peer-local event-driven updates
from duplicate ratios, one-hop latency, binary selected-peer overload and
observed churn; Python rows are one global scheduled normalized vector per
message index, including a sustained severe block. Consequently raw occupancy
percentages are descriptive but not workload-parity estimates.

Classification: **A — Expected scenario difference**. The k=6 occupancy is a
stress-laboratory workload/model characteristic, not a canonical-controller or
threshold error. Phase 2 remains usable as stress screening. Next: small GKE
S0 vs S5 confirmation; this diagnostic did not start it. Full tables, semantic
comparison, scenario matrix, data-integrity note and conclusion are in
`outputs/k5_phase2a_z_parity/README.md`.

## Phase 2 — plain-Python S0 versus S5 screening (2026-08-31)

### Scientific question

Does allowing canonical AHBN pressure to request two additional fanout levels,
`k=5` and `k=6`, improve delivery enough to justify the additional forwarding
cost? The sole primary comparison is canonical `S0 = 2/3/4` versus candidate
`S5 = 2/3/4/5/6`.

Phase 1 supplied the screening thresholds `T3 = 0.90` and `T4 = 1.50`.
They are not canonical parameters.

### Canonical immutability

No production AHBN file was modified. The canonical equation remains
`z = -d_hat + l_hat + u_hat + c_hat`; EWMA, observations, coefficients, zero
centres, mode logic, peer selection, duplicate handling, and seen/cache
semantics are unchanged. The candidate mapping exists only in the experimental
runner. No GKE, Kubernetes, Docker, or deployment action is part of this phase.

### Experimental design and deterministic pairing

The runner uses `N=20`, a Barabási–Albert topology with `m=2`, source node 0,
and seeds 42–46. Each seed receives 120 fixed exogenous observation vectors.
The production canonical controller is imported read-only and evaluated once to
create the shared `z` trace. Each `(seed, message, z)` state is then replayed
through both actuator mappings on the same frozen topology.

Peer selection is an unweighted sample-without-replacement abstraction: every
eligible list is sorted with a stable SHA-256 key formed from seed, message,
sender, depth, and peer. The key deliberately omits treatment and fanout. Thus
both arms have the same topology, source, messages, observations, event keys,
eligible ordering, and peer-selection method. Natural post-treatment divergence
in seen state is permitted. No per-neighbour novelty, duplicate feedback,
ranking, `D_j`, `N_j`, or `R_j` is used.

### Files created

- `scripts/run_k5_phase2_actuator_screening.py`
- `tests/test_k5_phase2_actuator_mapping.py`
- `tests/test_k5_phase2_determinism.py`
- `docs/K5_6actuatorsTest.md`

The manual run will create only:

- `outputs/k5_phase2_actuator_screening/per_run_results.csv`
- `outputs/k5_phase2_actuator_screening/paired_results.csv`
- `outputs/k5_phase2_actuator_screening/actuator_occupancy.csv`
- `outputs/k5_phase2_actuator_screening/z_states.csv`
- `outputs/k5_phase2_actuator_screening/summary.json`
- `outputs/k5_phase2_actuator_screening/README.md`

### Commands and terminal output

Repository inspection used `rg` and `sed` to examine prior K5 actuator
laboratories, controller tests, and `app/ahbn_controller.py`. The useful prior
FIFO/BA structure was retained, while older H1/H2 per-neighbour history and
additional treatment designs were excluded.

Initial bytecode command:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m py_compile scripts/run_k5_phase2_actuator_screening.py tests/test_k5_phase2_actuator_mapping.py tests/test_k5_phase2_determinism.py
[Errno 1] Operation not permitted: 'scripts/__pycache__/run_k5_phase2_actuator_screening...pyc'
```

This was a sandbox write-location restriction, not a syntax failure. It was
rerun with a temporary bytecode cache:

```text
PYTHONPYCACHEPREFIX=/tmp/k5_phase2_pycache /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m py_compile scripts/run_k5_phase2_actuator_screening.py tests/test_k5_phase2_actuator_mapping.py tests/test_k5_phase2_determinism.py
exit 0
```

An initial direct `--help` invocation then exposed that Python places `scripts/`
rather than the repository root on `sys.path` when a script is executed by
filename. It failed before argument parsing with `ModuleNotFoundError: app`.
The runner now inserts its resolved repository root solely for the read-only
canonical-controller import. The exact invocation was rechecked below.

Mapping parity and determinism tests:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q tests/test_k5_phase2_actuator_mapping.py tests/test_k5_phase2_determinism.py
..... [100%]
5 passed, 1 warning in 0.19s
```

The warning stated that pytest could not write its cache under `.pytest_cache`;
it did not affect test execution.

Final validation disabled pytest's cache provider and checked the exact runner
entry point without executing the screen:

```text
PYTHONPYCACHEPREFIX=/tmp/k5_phase2_pycache .../bin/python -m py_compile scripts/run_k5_phase2_actuator_screening.py tests/test_k5_phase2_actuator_mapping.py tests/test_k5_phase2_determinism.py
exit 0

.../bin/python -m pytest -q -p no:cacheprovider tests/test_k5_phase2_actuator_mapping.py tests/test_k5_phase2_determinism.py
..... [100%]
5 passed in 0.21s

.../bin/python scripts/run_k5_phase2_actuator_screening.py --help
usage: run_k5_phase2_actuator_screening.py [-h] [--output OUTPUT]
exit 0
```

Lightweight occupancy preflight (controller trace only; not the screening):

```text
42 {3: 30, 4: 25, 5: 7, 6: 58} >=.9 65 >=1.5 58
43 {3: 30, 4: 25, 5: 7, 6: 58} >=.9 65 >=1.5 58
44 {3: 30, 4: 24, 5: 8, 6: 58} >=.9 66 >=1.5 58
45 {3: 30, 4: 24, 5: 8, 6: 58} >=.9 66 >=1.5 58
46 {3: 30, 4: 25, 5: 7, 6: 58} >=.9 65 >=1.5 58
```

This confirms meaningful `k=5` and `k=6` exposure. Zero-count fanouts remain
explicitly present in the final occupancy CSV.

`git diff --check` also exited 0.

### Decision criteria

- **A — promising:** delivery improves across most seeds, extra traffic is not
  disproportionate, and new-reach efficiency remains defensible. S5 then earns
  at most one small GKE confirmation; it does not become canonical.
- **B — no meaningful benefit:** delivery is effectively unchanged or tiny and
  inconsistent while traffic increases. Reject S5 and retain S0.
- **C — worse:** delivery decreases, or traffic/duplicates rise severely without
  adequate reach. Reject S5 and retain S0.
- **D — ambiguous:** seed dependence, insufficient actuator occupancy, or an
  unstable trade-off prevents a safe interpretation. Stop without adding new
  designs.

Delivery differences in the paired CSV are percentage points. Other deltas are
`S5 - S0` in native units. Per-seed rows and mean/median/min/max/sample standard
deviation are included.

### Manual run command

The final screening has deliberately not been run by Codex. From the repository
root, the user should run exactly:

```bash
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python scripts/run_k5_phase2_actuator_screening.py
```
