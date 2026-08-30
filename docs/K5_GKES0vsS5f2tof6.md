# K5 Final GKE Confirmation — S0 versus S5 (2/3/4/5/6)

## Scientific question and frozen design

This final gate asks whether the extra S5 actuator authority retains a useful directional delivery benefit in real GKE. Phase 1 supplied the preselected GKE thresholds; Phase 2 found improved delivery across 5/5 deterministic stress seeds; Phase 2A passed formula, normalization, EWMA, and z-occupancy parity. This is a confirmation, not a threshold search.

- Canonical controller: `z = -d_hat + l_hat + u_hat + c_hat`
- Frozen thresholds: `T3 = 0.90`, `T4 = 1.50`
- S0: `z <= -0.25 -> 2`; `-0.25 < z < 0.25 -> 3`; `z >= 0.25 -> 4`
- S5: `z <= -0.25 -> 2`; `-0.25 < z < 0.25 -> 3`; `0.25 <= z < 0.90 -> 4`; `0.90 <= z < 1.50 -> 5`; `z >= 1.50 -> 6`
- Scenario: BA, N=20, m=2, source peer-0, overload factor 2.0 / delay 1400 ms, 20 messages
- Seeds: 42, 43, 44, 45, 46

Thresholds must not be adjusted after the GKE outcome. Only S0 and S5 are in scope.

## Feasibility and isolation

Feasible: **YES**, using a dedicated experiment image and runtime wrapper. The wrapper calls the canonical observation/controller update, then replaces only the forwarding budget before using the same eligible-neighbour and peer-selection paths. The experiment alternates treatment order by seed. Independent GKE runs are paired by coordinate, but exact event-level replay is not claimed because timing and event order may diverge.

The pre-existing final-actuator harness was not reusable unchanged: it encoded the older degree-proportional `S5-C6` policy. It has been corrected to the frozen score-based S5 mapping. No production controller or peer source was changed.

`CANONICAL AHBN MODIFIED: NO`

Canonical SHA-256 values:

```text
dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8  app/ahbn_controller.py
64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a  app/peer.py
```

## Experiment files

- `app/k5_final_actuator_policy.py` — pure frozen S0/S5 mapper
- `app/k5_final_actuator_runtime.py` — experiment-only runtime override
- `app/Dockerfile.k5_final_actuator` — dedicated image recipe
- `scripts/k5_final_actuator_analysis.py` — config, validity checks, paired analysis, occupancy
- `scripts/run_k5_final_actuator_gke.sh` — fail-fast 10-run manual runner
- `tests/test_k5_final_actuator_gke.py` — boundary, isolation, parser, artifact, and runner tests
- `outputs/k5_gke_s0_vs_s5/` — only output root

The analyzer creates `per_run_results.csv`, `paired_results.csv`, `controller_states.csv`, `actuator_occupancy.csv`, `aggregate_results.csv`, `summary.json`, and `README.md`. Raw run artifacts remain below `runs/`.

## Preflight record

Commands run by Codex (offline/static only):

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q \
  tests/test_k5_final_actuator_gke.py \
  tests/test_k5_phase2_actuator_mapping.py \
  tests/test_k5_phase2_determinism.py
```

Output:

```text
..................                                                       [100%]
18 passed, 1 warning in 0.24s
```

The warning states that pytest could not update its cache because this checkout is read-only to the sandbox; it does not affect the tests. Boundary cases for S5 (`0.249999`, `0.25`, `0.899999`, `0.90`, `1.499999`, `1.50`) and S0 (`0.25`, `0.90`, `1.50`) passed.

```text
git diff --check
```

Output: empty (PASS).

```text
git status --short
 M app/k5_final_actuator_policy.py
 M app/k5_final_actuator_runtime.py
 M scripts/k5_final_actuator_analysis.py
 M scripts/run_k5_final_actuator_gke.sh
 M tests/test_k5_final_actuator_gke.py
?? docs/K5_GKES0vsS5f2tof6.md
```

Only experiment-local policy/runtime, scripts, tests, and this document changed.

```text
git diff -- app/ahbn_controller.py app/peer.py
```

Output: empty (PASS).

## Docker and image provenance

The dedicated image was built and pushed manually as required. All ten validated runs used:

```text
tag:    wwiras/ahbn2-peer:k5-s0-vs-s5-f2tof6-20260831
digest: docker.io/wwiras/ahbn2-peer@sha256:87f457236a42c9e0dc8099850e76307f27b7fed16364122a54fa89007621eecc
```

The commands supplied for manual execution were:

Run manually from the repository root:

```bash
docker build --platform linux/amd64 \
  -t wwiras/ahbn2-peer:k5-s0-vs-s5-f2tof6-20260831 \
  -f app/Dockerfile.k5_final_actuator app
docker push wwiras/ahbn2-peer:k5-s0-vs-s5-f2tof6-20260831
docker buildx imagetools inspect wwiras/ahbn2-peer:k5-s0-vs-s5-f2tof6-20260831
```

Image provenance was recorded consistently in every row of `per_run_results.csv`.

## Manual GKE command and execution record

```bash
IMAGE=wwiras/ahbn2-peer:k5-s0-vs-s5-f2tof6-20260831 \
  scripts/run_k5_final_actuator_gke.sh
```

The user ran the command manually. The runner verified the exact Python environment, Kubernetes context, authorization, canonical file hashes, focused tests, treatment/run validity, pod health, workload coordinate, controller semantics, fanout semantics, and post-run canonical hashes.

Result root:

```text
outputs/k5_gke_s0_vs_s5/20260830T201359Z
```

Recorded provenance:

```text
Python: /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python
Python version: Python 3.14.6
git commit: 5eb7a0dbd24e267bd252cfc6508689b7bf0db53a
namespace: ahbn-k5-final-actuator
```

Relevant terminal output:

```text
K5 FINAL ACTUATOR GKE: S0 vs S5 only; seeds 42--46; factor 2.0
.............                                                            [100%]
13 passed in 0.07s
...
=== PASS seed=46 treatment=S0 ===
...
=== PASS seed=46 treatment=S5 ===
FINAL K5 analysis PASS: 10 runs, 5 matched seeds -> outputs/k5_gke_s0_vs_s5/20260830T201359Z
dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8  app/ahbn_controller.py
64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a  app/peer.py
K5 final actuator GKE complete: outputs/k5_gke_s0_vs_s5/20260830T201359Z
```

The complete unabridged command transcript is retained at `outputs/k5_gke_s0_vs_s5/20260830T201359Z/terminal.log`. No run failed validation. To resume only an interrupted result root, the prepared command was:

```bash
IMAGE=wwiras/ahbn2-peer:k5-s0-vs-s5-f2tof6-20260831 \
  scripts/run_k5_final_actuator_gke.sh --resume outputs/k5_gke_s0_vs_s5/<UTC_TIMESTAMP>
```

## Decision rule

- **A — CONFIRMED:** delivery improves in most seeds, mean delivery delta is clearly positive, k=5/k=6 activate, added traffic is proportionate, and parity remains valid.
- **B — NOT CONFIRMED:** delivery benefit is absent/negligible/inconsistent, or added traffic lacks useful reach. Keep S0; do not tune thresholds.
- **C — INCONCLUSIVE:** a technical validity problem prevents comparison, including insufficient S5 activation. Correct only that technical problem.

## Per-seed paired results

Delivery deltas are S5 minus S0 and are shown in percentage points. Delay and traffic deltas use the native metric units.

| Seed | S0 delivery | S5 delivery | Delivery delta (pp) | S0 delay | S5 delay | Delay delta | S0 forwards | S5 forwards | Forward delta | S0 duplicates | S5 duplicates | Duplicate delta | S0 efficiency | S5 efficiency | Efficiency delta | S5 k=5 | S5 k=6 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | 0.4725 | 0.7075 | +23.50 | 0.589826 | 1.314551 | +0.724725 | 169 | 263 | +94 | 129 | 253 | +124 | 0.634228 | 0.548450 | -0.085779 | 7 | 9 |
| 43 | 0.4600 | 0.7425 | +28.25 | 0.101112 | 0.534289 | +0.433177 | 164 | 277 | +113 | 91 | 208 | +117 | 0.721569 | 0.612371 | -0.109197 | 2 | 3 |
| 44 | 0.5900 | 0.4850 | -10.50 | 0.814072 | 0.314517 | -0.499554 | 216 | 174 | -42 | 153 | 115 | -38 | 0.639566 | 0.671280 | +0.031714 | 2 | 0 |
| 45 | 0.6475 | 0.6975 | +5.00 | 1.287481 | 1.286082 | -0.001399 | 239 | 259 | +20 | 199 | 191 | -8 | 0.591324 | 0.620000 | +0.028676 | 3 | 13 |
| 46 | 0.5900 | 0.5250 | -6.50 | 0.177657 | 0.593045 | +0.415388 | 216 | 190 | -26 | 203 | 168 | -35 | 0.563246 | 0.586592 | +0.023346 | 2 | 4 |

S5 improved delivery in 3/5 seeds. It lost delivery in seeds 44 and 46; this variability is retained in the conclusion and is not hidden by the mean.

## Aggregate results

| Metric | S0 mean | S5 mean | Delta S5-S0 | S0 median | S5 median | S0 min–max | S5 min–max | S0 SD | S5 SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Delivery ratio | 0.5520 | 0.6315 | +0.0795 (+7.95 pp) | 0.5900 | 0.6975 | 0.4600–0.6475 | 0.4850–0.7425 | 0.081842 | 0.117535 |
| Propagation delay | 0.594029 | 0.808497 | +0.214467 | 0.589826 | 0.593045 | 0.101112–1.287481 | 0.314517–1.314551 | 0.486221 | 0.460924 |
| Duplicates | 155.0 | 187.0 | +32.0 | 153.0 | 191.0 | 91–203 | 115–253 | 47.4763 | 50.8871 |
| Forwarding attempts | 355.8 | 419.6 | +63.8 | 369.0 | 450.0 | 255–438 | 289–516 | 78.1454 | 94.0016 |
| Total forwards | 200.8 | 232.6 | +31.8 | 216.0 | 259.0 | 164–239 | 174–277 | 32.7368 | 47.0138 |
| New reaches | 220.8 | 252.6 | +31.8 | 236.0 | 279.0 | 184–259 | 194–297 | 32.7368 | 47.0138 |
| New-reach efficiency | 0.629987 | 0.607739 | -0.022248 | 0.634228 | 0.612371 | 0.563246–0.721569 | 0.548450–0.671280 | 0.060096 | 0.045199 |

Mean delivery increased by 7.95 percentage points. Mean forwarding attempts increased by 63.8 (17.9%), total forwards and new reaches each increased by 31.8, and duplicates increased by 32.0. Mean new-reach efficiency declined by 0.02225, or 2.225 percentage points. Mean delay increased by 0.21447, although median delay changed only from 0.58983 to 0.59305.

## Actuator and z occupancy

Across the five S5 runs there were 1,263 actuator decisions:

| S5 gear/region | Count | Percent |
|---|---:|---:|
| k=2 | 346 | 27.40% |
| k=3 | 863 | 68.33% |
| k=4 | 9 | 0.71% |
| k=5 | 16 | 1.27% |
| k=6 | 29 | 2.30% |
| z >= 0.90 | 45 | 3.56% |
| z >= 1.50 | 29 | 2.30% |

The extra gears therefore activated in real GKE: k=5 appeared in every S5 seed and k=6 appeared in four of five seeds. Seed 44 had two k=5 activations but no k=6 activation. For S0, the corresponding score-region counts were 32/1,104 (2.90%) for `z >= 0.90` and 10/1,104 (0.91%) for `z >= 1.50`; its actuator remained capped at k=4 as required.

## Final classification

**A — CONFIRMED.**

The frozen rule is satisfied:

1. Delivery improved in most seeds (3/5).
2. Mean delivery improvement was clearly positive (+7.95 percentage points).
3. The additional k=5 and k=6 gears activated in GKE (45 combined activations).
4. Additional traffic was accompanied by useful reach: mean new reaches increased by 31.8. The cost was real—attempts +63.8, duplicates +32.0, efficiency -2.225 percentage points, and mean delay +0.21447—but it was proportionate to the observed reach benefit rather than traffic without reach.
5. All ten runs passed semantic/artifact validation, and canonical controller and peer hashes were identical before and after the experiment.

Scientific conclusion:

> S5 is empirically supported by the existing GKE-derived thresholds, deterministic Python stress screening, parity diagnostics, and this independent five-seed GKE confirmation. S5 may be frozen as the final canonical actuator.

No thresholds were tuned, no alternative actuator was tested, and no canonical production source was modified during this confirmation. Promotion into canonical source is a separate implementation decision and was not performed here.
