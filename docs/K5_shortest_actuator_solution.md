# K5 shortest actuator solution — bounded fanout screening

## 1. Objective

Screen only S0, S2, S5-C5, S5-C6, and S5-C7 in a deterministic plain-Python laboratory. The sole treatment variable is the requested LOW/MODERATE/HIGH fanout. No GKE work is part of this task.

## 2. Immutable canonical files

- `app/ahbn_controller.py`: EWMA, `z = -d_hat + l_hat + u_hat + c_hat`, thresholds, mode, and canonical 2/3/4. SHA-256: `dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8`.
- `app/peer.py`: eligibility filtering and peer selection. SHA-256: `64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a`.

The runner checks both hashes before and after the experiment and stops on any difference.

## 3. Policy formulas

S0 is `min((2,3,4), Ne)`. S2 is `(ceil(Ne/3), ceil(2Ne/3), Ne)`. Each S5-Cx applies `min(base, x, Ne)` to the S2 base. The simulator uses the frozen LOW/MODERATE/HIGH decisions and changes only fanout.

## 4. Files created

- `scripts/k5_shortest_actuator_screening.py`: isolated deterministic simulator and analysis.
- `tests/test_k5_shortest_actuator_screening.py`: mapping, bounds, isolation, and determinism tests.
- `scripts/run_k5_shortest_actuator_screening.sh`: manual runner and terminal logger.

Peer selection is a stable-hash ordering, the experiment-local deterministic equivalent of canonical unweighted sampling without replacement. It is identical across all policies and uses no per-neighbour history.

## 5. Tests performed

The focused tests validate every policy at Ne = 0, 1, 2, 3, 4, 5, 6, 7, and 9; the required Ne=9 examples; `0 <= f <= Ne`; graph immutability; and identical repeated results. S1, S3, and S4 are absent.

## 6. Deterministic regression status

Implementation-time focused test command:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q tests/test_k5_shortest_actuator_screening.py
```

Expected: `4 passed`. The manual runner repeats this check before simulation.

## Pre-run correction audit — 2026-08-30

The first determinism-file regression correctly stopped before any main experiment. Its focused pytest result was `1 failed, 2 passed`; the traceback ended with `ValueError: could not convert string to float: 'clean'`. Root cause: `average()` attempted `float(...)` conversion for every field not used as a grouping key, which incorrectly included categorical `scenario` and `mode` values.

The smallest correction was made only in `scripts/k5_shortest_actuator_screening.py`: arithmetic aggregation now iterates the explicit `NUMERIC_METRICS` schema. Group identifiers (`policy` and, for per-seed output, `seed`) remain in aggregate rows; raw output retains `policy`, `seed`, `scenario`, and `mode`; existing LOW/MODERATE/HIGH numeric usage counts remain unchanged. No formula, scenario, seed, topology, selection, metric definition, or controller behavior changed.

`tests/test_k5_shortest_actuator_screening.py` now includes a direct regression fixture containing `scenario="clean"` and `mode="HIGH"`. It verifies numeric delivery/send means and verifies that scenario/mode are absent from arithmetic aggregate rows. The existing result-file determinism test generates two independent output directories and byte-compares all six scientifically relevant files: `fanout_mapping.csv`, `per_run.csv`, `per_seed.csv`, `aggregate_summary.csv`, `results.md`, and `manifest.json`. These files contain the complete simulated metrics, forwarding aggregates, mappings, and selection result; no timestamps or output paths are embedded.

Focused command and complete output:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q -p no:cacheprovider tests/test_k5_shortest_actuator_screening.py
....                                                                     [100%]
4 passed in 0.44s
```

Determinism gate:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q -p no:cacheprovider tests/test_k5_shortest_actuator_screening.py -k complete_result_files_are_deterministic
.                                                                        [100%]
1 passed, 3 deselected in 0.40s
```

Treatment-isolation gate: PASS (`1 passed, 3 deselected in 0.12s`). For a single frozen scenario and controller mode, every policy retains the same scenario, seed, graph, and HIGH classification; only the experiment-local fanout mapping can differ. The simulator accepts the already-decided mode and neither imports nor invokes production controller state.

Actuator-mapping gate: PASS (`1 passed, 3 deselected in 0.10s`). All required Ne cases (0, 1, 2, 3, 4, 5, 6, 7, 9) satisfy `0 <= f <= Ne`. At Ne=9 the exact LOW/MODERATE/HIGH rows are S0 `2/3/4`, S2 `3/6/9`, S5-C5 `3/5/5`, S5-C6 `3/6/6`, and S5-C7 `3/6/7`.

Canonical pre-fix and post-validation hashes are identical:

```text
dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8  app/ahbn_controller.py
64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a  app/peer.py
```

Readiness: **PASS — ready for the manual Python screening**. The main experiment and GKE were not run during pre-run validation. The manual run writes only beneath `outputs/k5_shortest_actuator_solution/<UTC timestamp>/`.

## 7. Exact manual command

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
./scripts/run_k5_shortest_actuator_screening.sh
```

## 8. Expected terminal output

The log begins with the runner name and interpreter, reports `3 passed`, prints the fanout mapping, prints exactly one selection outcome A/B/C/D, then reports `Canonical hash verification: PASS` and the timestamped output path. Any test, hash, or analysis error stops the runner with a nonzero exit.

## 9. Output directory

`outputs/k5_shortest_actuator_solution/<UTC timestamp>/terminal.log` contains the complete terminal transcript. `results/` contains `fanout_mapping.csv`, `per_run.csv`, `per_seed.csv`, `aggregate_summary.csv`, `results.md`, and `manifest.json`.

## 10. Interpretation and selection rules

Delivery recovery, send cost, and duplicate cost use S0 as zero and S2 as one when the denominator exists. A bounded policy qualifies only if it recovers at least 50% of S2's aggregate delivery gain, its send and duplicate cost do not exceed its delivery recovery, and it does not reduce delivery versus S0 in at least four of five seeds. The smallest qualifying cap is selected. Otherwise the exact outcome is `D. NO CLEAR BOUNDED WINNER`, and S0 is retained. Per-seed output must be inspected for pathological seeds; no highest-delivery-only selection is permitted.

Propagation delay is maximum deterministic hop depth. New-reach efficiency is new reaches divided by sends. Unavailable peers are excluded before selection. H2 is observed only through new versus duplicate outcomes; no history-aware ranking exists.

## 11. GKE decision gate

Do not run GKE here. If and only if A, B, or C is produced, the next proposed comparison is canonical S0 versus that one selected S5 policy. For outcome D, retain S0. Any future Docker build/push remains manual.
