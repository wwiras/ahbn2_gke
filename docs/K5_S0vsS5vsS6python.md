# K5 Final S0 vs S5 vs S6 Plain-Python Screening

## 1. Objective

Determine whether topology-normalized S6 provides a meaningful delivery/reach gain at a defensible traffic and duplicate cost versus canonical S0 and fixed S5 fanouts. This is a matched, plain-Python-only final screening gate.

## 2. S0 definition

The validated baseline is unchanged: `z <= -0.25 -> 2`, `-0.25 < z < 0.25 -> 3`, and `z >= 0.25 -> 4`, bounded by the eligible-neighbour count at selection time.

## 3. S5 definitions

`S5-f2`, `S5-f3`, `S5-f4`, `S5-f5`, and `S5-f6` request fixed absolute fanouts 2 through 6 respectively, each bounded by `Ne`. No S5 semantics were redesigned.

## 4. S6 mathematical definition

The frozen five S5 score bins are relabelled from fanout `2..6` to robustness levels `k=1..5`. This preserves their ordering and thresholds while separating requested level from actual fanout. For S6 only:

```python
if Ne <= 0:
    actual_fanout = 0
else:
    actual_fanout = min(Ne, max(1, math.ceil(k * Ne / 5)))
```

S6 uses only the canonical score-derived level `k` and the current already-known `Ne`.

## 5. Canonical AHBN immutability

The controller remains `z = -d_hat + l_hat + u_hat + c_hat`. Production controller, observations, EWMA, modes, eligibility, selection, duplicate handling, and peer implementation are immutable. S6 exists only in the simulation harness.

## 6. Files created/modified

Created:

- `scripts/k5_s0_vs_s5_vs_s6_python.py`
- `scripts/run_k5_s0_vs_s5_vs_s6_python.sh`
- `tests/test_k5_s0_vs_s5_vs_s6_python.py`
- `docs/K5_S0vsS5vsS6python.md`

Canonical files modified: none.

## 7. Tests performed and Codex terminal record

Inspection command:

```text
rg --files -g 'AGENTS.md' -g '*K5*' -g '*k5*' -g '*actuator*' -g 'tests/**' -g 'scripts/**' -g 'docs/**' -g 'outputs/**'
```

Result: located the validated Phase 2 simulator, shortest-actuator simulator, frozen final S0/S5 policy, their tests, and prior K5 evidence. No `AGENTS.md` was found.

Semantic inspection command:

```text
sed -n '1,360p' scripts/run_k5_phase2_actuator_screening.py
sed -n '1,180p' app/k5_final_actuator_policy.py
sed -n '1,180p' docs/K5_GKES0vsS5f2tof6.md
```

Result: confirmed canonical equation, seeds 42--46, BA `N=20,m=2`, 120-message workload, S0 thresholds, five-bin S5 thresholds, matched stable peer ordering, and existing metrics.

Focused S6 test command:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q -p no:cacheprovider tests/test_k5_s0_vs_s5_vs_s6_python.py
```

Output:

```text
....                                                                     [100%]
4 passed in 0.19s
```

Existing S0/S5 regression command:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q -p no:cacheprovider tests/test_k5_phase2_actuator_mapping.py tests/test_k5_phase2_determinism.py
```

Output:

```text
.....                                                                    [100%]
5 passed in 0.11s
```

Canonical hash command and output:

```text
shasum -a 256 app/ahbn_controller.py app/peer.py
dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8  app/ahbn_controller.py
64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a  app/peer.py
```

Final static verification:

```text
bash -n scripts/run_k5_s0_vs_s5_vs_s6_python.sh
git diff --check
git diff -- app/ahbn_controller.py app/peer.py
git status --short
```

Output (the first three commands were empty, therefore PASS):

```text
?? docs/K5_S0vsS5vsS6python.md
?? scripts/k5_s0_vs_s5_vs_s6_python.py
?? scripts/run_k5_s0_vs_s5_vs_s6_python.sh
?? tests/test_k5_s0_vs_s5_vs_s6_python.py
```

## 8. Exact manual experiment command

```bash
/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/scripts/run_k5_s0_vs_s5_vs_s6_python.sh
```

## 9. Output directory

Completed result root:

`/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_s0_vs_s5_vs_s6_python/20260831T054106Z/`

The `results/` child contains per-message, per-seed, aggregate, controller-state, actuator-diagnostic, eligible-neighbour-distribution, actual-fanout-distribution, and summary artifacts. `terminal.log` captures the complete manual run.

## 10. Terminal output/results after user execution

The user executed the supplied command manually. Complete terminal output:

```text
K5 plain-Python S0 vs S5-f2..f6 vs S6
Python: /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python
....                                                                     [100%]
4 passed in 0.17s
Selected fixed comparator: S5-f6
Decision: B — S6 NOT SUFFICIENTLY BETTER; RETAIN S5/S0
Reason: S6 did not clear the predeclared delivery/consistency/efficiency gate against both comparators.
Results: /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_s0_vs_s5_vs_s6_python/20260831T054106Z/results
Canonical hash verification: PASS
Complete: /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_s0_vs_s5_vs_s6_python/20260831T054106Z
```

All focused tests passed during the run and the post-experiment canonical hashes matched their pre-experiment values.

### Per-seed matched comparison

The strongest fixed treatment by the predeclared selection rule was `S5-f6`. Delivery deltas are percentage points; forwarding and duplicate deltas use native counts. Positive deltas indicate S6 is higher than the named comparator.

| Seed | S0 delivery | S5-f6 delivery | S6 delivery | S6-S0 delivery (pp) | S6-S5-f6 delivery (pp) | S0 forwards | S5-f6 forwards | S6 forwards | S6-S0 forwards | S6-S5-f6 forwards | S0 duplicates | S5-f6 duplicates | S6 duplicates | S6-S0 duplicates | S6-S5-f6 duplicates |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | 0.7943 | 0.9504 | 0.9311 | +13.68 | -1.93 | 3,639 | 4,914 | 5,238 | +1,599 | +324 | 1,828 | 2,747 | 3,115 | +1,287 | +368 |
| 43 | 0.9732 | 1.0000 | 0.9596 | -1.36 | -4.04 | 5,308 | 6,360 | 5,274 | -34 | -1,086 | 3,089 | 4,080 | 3,086 | -3 | -994 |
| 44 | 0.9004 | 0.9868 | 0.9338 | +3.33 | -5.31 | 4,297 | 5,490 | 5,220 | +923 | -270 | 2,244 | 3,240 | 3,091 | +847 | -149 |
| 45 | 0.9320 | 0.9961 | 0.9395 | +0.75 | -5.66 | 4,566 | 5,631 | 5,259 | +693 | -372 | 2,441 | 3,360 | 3,117 | +676 | -243 |
| 46 | 0.9763 | 0.9952 | 0.9404 | -3.60 | -5.48 | 4,862 | 5,509 | 5,250 | +388 | -259 | 2,636 | 3,240 | 3,106 | +470 | -134 |

S6 exceeded S0 delivery in 3/5 seeds and was below S5-f6 delivery in 5/5 seeds.

### Aggregate comparison

| Treatment | Delivery | Delay | Forwards | Duplicates | New-reach efficiency | Δ delivery vs S0 (pp) | Δ forwards vs S0 | Δ duplicates vs S0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| S0 | 0.9153 | 4.2917 | 4,534.4 | 2,447.6 | 0.4633 | 0.00 | 0.0 | 0.0 |
| S5-f2 | 0.6750 | 5.5817 | 2,633.8 | 1,094.8 | 0.5876 | -24.03 | -1,900.6 | -1,352.8 |
| S5-f3 | 0.8606 | 4.8400 | 3,967.0 | 2,004.8 | 0.4982 | -5.46 | -567.4 | -442.8 |
| S5-f4 | 0.9323 | 4.0967 | 4,719.8 | 2,594.2 | 0.4534 | +1.70 | +185.4 | +146.6 |
| S5-f5 | 0.9671 | 3.6400 | 5,198.2 | 2,993.2 | 0.4268 | +5.18 | +663.8 | +545.6 |
| S5-f6 | 0.9857 | 3.3283 | 5,580.8 | 3,333.4 | 0.4049 | +7.04 | +1,046.4 | +885.8 |
| S6 | 0.9409 | 3.2950 | 5,248.2 | 3,103.0 | 0.4087 | +2.56 | +713.8 | +655.4 |

Relative to S5-f6, S6 had 4.48 percentage points lower delivery, 332.6 fewer forwards, 230.4 fewer duplicates, 0.0333 lower delay, and 0.0038 higher new-reach efficiency. The small traffic and efficiency savings did not compensate for the consistent delivery loss.

Relative to S0, S6 gained 2.56 delivery points and reduced delay by 0.9967, but cost 713.8 additional forwards and 655.4 additional duplicates per seed. Its new-reach efficiency fell by 0.0546, slightly exceeding the predeclared maximum efficiency cost of 0.05.

## 11. Final decision

**B — S6 NOT SUFFICIENTLY BETTER; RETAIN S5/S0**

S6 did not clear the predeclared delivery, consistency, and efficiency gate against both comparators. It provided a mean delivery improvement over S0, but the benefit was inconsistent across seeds and required materially more forwarding and duplicates. More importantly, S6 delivered less than S5-f6 in every matched seed and by 4.48 percentage points on average. Therefore the topology-aware mapping does not justify final GKE validation.

Retain S5/S0. Do not create S7 or another actuator variant.
