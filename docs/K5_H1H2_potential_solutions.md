# K5 H1/H2 potential actuator solutions

## Scope and protected canonical files

This is a deterministic design-screening harness, not a replacement for GKE. The frozen implementation was inspected and remains unchanged:

- `app/ahbn_controller.py` — canonical equation, EWMA state, thresholds, and fanout 2/3/4.
- `app/peer.py` — production actuator, eligibility filtering, and peer selection.

These files are protected and were treated as read-only. The experiment mirrors `z = -d_hat + l_hat + u_hat + c_hat`, boundary ownership (`z <= -0.25` LOW and `z >= 0.25` HIGH), and canonical fanout in a separate module under `scripts/`.

## Canonical selection observed

In AHBN gossip mode, `Peer.target_peers` excludes self, the incoming sender, and unavailable neighbours. It then selects `min(fanout, eligible_count)` peers using unweighted `random.sample`; the result is order-preserving deduplicated. Cluster mode uses a deterministic gateway/member ordering. Because the K5 harness is a narrow graph-forwarding screen, S0 represents the gossip actuator. It uses an unweighted, strategy-independent stable-hash ordering, which is the replayable equivalent of sampling without replacement. S2 uses exactly the same ordering.

## Strategies and local-information boundary

- S0: canonical 2/3/4 fanout and unweighted selection.
- S1: canonical fanout with deterministic ranking based on a sender's returned NEW/DUP outcome and recent peer use.
- S2: the specified topology-scaled formulas with S0 selection.
- S3: S2 fanout with S1 ranking.
- S4: S1 ranking with four predeclared bounded configurations (`HIGH` caps 5, 6, 7, and 8).

The simulator may evaluate true possession state, but S1/S3/S4 never rank using it. They update history only after a selected neighbour returns a NEW or DUPLICATE result. This is locally derivable from the existing synchronous forwarding response/status semantics and adds no messages. Exact downstream-reach knowledge is excluded because it is not locally observable.

## Replay, scenarios, and semantics

For each scenario and seed, one frozen NetworkX BA graph is generated and replayed independently into every strategy. The primary condition is `N=20`, `m=2`; the multipath scenario uses the one bounded denser condition `m=3` to expose convergence. Seeds are 42–46. Scenarios are clean propagation, multipath convergence, high-degree capacity opportunity, and deterministic limited unavailability. All representative and boundary `z` cases are exercised. A small deterministic prehistory of per-neighbour NEW/DUP ACK and recent-use counters is part of the shared immutable initial state. It represents prior traffic, is identical across strategies, and contains no current-message or future possession information.

Each available selected edge is one send attempt and successful transmission. A node's first receipt is NEW; later receipts are DUPLICATE. Unavailable nodes are excluded before selection, so they are neither failed sends nor duplicates. Delivery excludes the source in both numerator and reachable-population denominator. This differs from older aggregate K5 reports that count all `received_new` peers including the source, and is intentional for actuator reach measurement.

H1 is recorded at each nonempty forwarding opportunity as `max(0, 1-k/Ne)`. H2 overlap is `duplicates / (NEW + duplicates)`. `overlap_cost` is `1 - NEW/successful_transmissions`, and `eta_new` is `NEW/send_attempts`. Zero denominators produce 0, except delivery is 1 when there is no non-source reachable population.

Lower H1 alone is not a win: flooding can trivially minimize it. The generated Pareto table jointly treats delivery and `eta_new` as higher-is-better and sends, duplicates, mean H1, and H2 overlap as lower-is-better. S4 must preserve S0 delivery within one percentage point, strictly reduce mean H1, and avoid worsening H2 by more than 0.02. Among passing configurations, Pareto membership, `eta_new`, delivery, sends, duplicates, and finally the lower cap (simplicity) are transparent ordered tie-breaks. If none pass, the report labels its choice a fallback. No weighted score is used.

## Validation and manual execution

Unit/regression tests may be run without starting the comparison:

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q tests/test_k5_h1h2_actuator_sim.py
```

The actual comparison is deliberately not run automatically. Start it manually with:

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python scripts/run_k5_h1h2_actuator_sim.py
```

All generated files are written under `outputs/k5_h1h2_actuator_screening/`: per-run metrics, aggregate metrics, deltas against S0, Pareto status, a manifest, and a short screening report.
