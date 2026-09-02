# K5 Exp08 Final Scientific Interpretation

## What happened

The frozen 80-run Kubernetes campaign produced a valid but mixed result. Gossip, Structured, and DC-SoC delivered to every peer in all 20 runs per algorithm. AHBN delivery was lower in all 20 runs, with condition means of 0.6435, 0.6730, 0.6250, and 0.6815 at 700, 1050, 1400, and 2100 ms. AHBN simultaneously used substantially fewer forwards than the 380-run envelope of every comparator and far fewer duplicates than Gossip.

## Comparator evidence

Across all conditions, the highest delivery was a three-way tie (Gossip, Structured, DC-SoC: 1.0). AHBN had the lowest mean delay at all four overload conditions. Gossip generated the most duplicates (680/run); Structured and DC-SoC generated the least (0/run). AHBN used the fewest forwards at every condition; all comparators recorded 380/run.

The descriptive Student-t intervals are in `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08_formal-20260902_092321/final_analysis/tables/comparator_combined.csv`. They characterize the five frozen seeds and are not claims of population-wide inferential significance.

## AHBN mechanism

The trace confirms the unchanged equation `z = -d_hat + l_hat + u_hat + c_hat` and the S5 mapping. Requested levels 5 and 6 occurred 62 and 118 times. Requested fanout was monotone in each recorded z by construction, but realized fanout was often below the request because eligible-neighbour counts constrained actions. The exact condition, mode, fanout, clipping, and topology summaries are in `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08_formal-20260902_092321/final_analysis/tables`.

## Gains, sacrifice, and defensibility

AHBN's bounded adaptive fanout gained lower dissemination traffic and, in three conditions, lower mean delay. It sacrificed nominal reachability. This is a real efficiency-reachability/robustness trade-off because the delivery deficit co-occurred with meaningful forward and Gossip-duplicate savings; it is not evidence that propagation performance was maintained. Lower delivery is scientifically interpretable, but it remains the principal limitation and cannot be described away as success.

## Non-monotonicity and topology

AHBN delivery was non-monotonic for 5/5 seeds. Changes in delivery co-occurred with changes in requested/realized fanout and redundancy, and frequent clipping shows that topology degree and eligible-neighbour availability can constrain dissemination. These are descriptive associations. The frozen data do not isolate controller adaptation from Kubernetes scheduling, runtime timing, or topology-path effects, so causal attribution is not justified.

## Claims that must not be made

- AHBN did not maintain full or comparator-equivalent delivery in Exp08.
- AHBN did not consistently outperform the comparators.
- A universally balanced or robust operating point is not established by this experiment.
- Non-monotonic improvement at higher overload must not be presented as a causal adaptation effect.
- The older 8.6% delay-increase and 134% Structured-increase claims are not the frozen K5 result.

## Thesis contribution

Exp08 demonstrates a reproducible bounded adaptive operating envelope in a real Kubernetes runtime: AHBN changes internal action levels, cuts dissemination cost, and exposes an explicit reachability limitation under a slow-but-alive important peer. Its contribution is the measured multi-objective trade-off and mechanism evidence—not universal superiority.
