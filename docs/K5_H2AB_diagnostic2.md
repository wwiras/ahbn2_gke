# K5 H2 Selector A/B Diagnostic

## 1. Objective

Prepare a diagnostic that changes only which already-eligible peers receive the canonical AHBN fanout. The 30 GKE runs are manual-only and have not been executed by Codex.

## 2. Scientific Hypothesis

At identical seed, repetition, topology, workload, overload, controller, and canonical fanout, peer-selection policy may alter delivery/reach efficiency.

## 3. Scope / No-More-No-Less Guardrail

The frozen matrix is exactly five seeds (42--46), three repetitions, two treatments, factor 2.0, and 1400 ms: 30 runs. No other algorithm, factor, seed, feedback protocol, parameter search, or GKE execution is included.

## 4. Canonical AHBN Immutability

The score, EWMA, observations, thresholds, mode rule, and fanout mapping 2/3/4 are untouched. `app/ahbn_controller.py` is not modified. The diagnostic reads the controller-produced `self.fanout`; it never changes it.

## 5. Current Selector Audit

- Eligible AHBN Gossip peers are built in `PeerState.target_peers` (`app/peer.py`) from `self.neighbors`, excluding the incoming sender, self, and `unavailable_neighbors`.
- Eligible AHBN cluster peers come from `cluster_targets`: heads exclude sender, self, and unavailable peers from members and gateways; non-heads may select only their available cluster head.
- Gossip computes `k = min(self.fanout, len(candidates))`, then the control calls module-global `random.sample(candidates, k)`. The process-global RNG is not explicitly seeded by the topology seed. By contrast, standalone Gossip uses `self.rng = random.Random(topology seed)`; that RNG is not used by AHBN.
- Gossip candidate order is inherited from the topology neighbor list. `app/gen_topology.py` writes physical neighbors sorted by numeric peer ID, so peer IDs and adjacency/configuration list order determine the population order presented to `random.sample`. Python list order is material; no set/dict determines the canonical Gossip order.
- The Kubernetes ConfigMap preserves generated JSON list order. Kubernetes does not reorder the in-memory candidates after parsing.
- AHBN cluster control selection is deterministic and order-dependent: a head takes the first gateway, then members in list order, then remaining gateways, before truncating to fanout. Cluster member lists are generated in numeric node order and gateways in adjacent-cluster order.
- Eligibility is computed before applying the fanout limit. Gossip samples after `k`; cluster control constructs its priority order and truncates to the budget.
- Gossip sampling is without replacement over the list. Generated topology lists are unique, so a forwarding event does not repeat a peer. The later order-preserving deduplication is retained unchanged.
- Across events, Gossip may repeatedly select some peers by chance; cluster control can repeatedly favor the same early peers and omit later peers. The unseeded AHBN process-global RNG and deterministic cluster ordering can plausibly contribute to run/repetition sensitivity, which H2 is designed to diagnose.

## 6. Treatment A

`selector_control` is the existing behavior exactly: module-global `random.sample` for AHBN Gossip and existing deterministic `cluster_targets` ordering for AHBN cluster mode. It remains the default when no H2 metadata is present.

## 7. Treatment B

`seeded_uniform` samples without replacement from the existing eligible peers, capped by the existing canonical fanout. A SHA-256-derived event seed covers experiment seed, forwarding peer, message ID, fanout, and the sorted unique eligible set. An event-local `random.Random` makes the result reproducible without perturbing control RNG state. It adds no weights, feedback, history, metadata exchange, or network protocol.

## 8. Code Changes

- `app/peer.py`: experiment-only treatment metadata, stable seeded-uniform selector, treatment trace fields. The production default remains control.
- `app/gen_topology.py`: copies experiment-only `k5_h2` metadata from a generated H2 config into the topology payload.
- `tests/test_k5_h2_selector_ab.py`: focused T1--T8 tests.
- `scripts/run_k5_h2_selector_ab.sh`: balanced 30-run manual runner using existing K5 orchestration.
- `scripts/k5_h2_selector_ab_analysis.py`: config preparation, run reconciliation, paired analysis, descriptive statistics, and selector diagnostics.

## 9. Tests

Focused tests cover control equivalence and RNG progression, eligible-set preservation, canonical-fanout preservation, no duplicates, same-seed determinism, seed sensitivity, controller invariance, unavailable exclusion, treatment trace identity, and frozen config coordinates. Relevant canonical and semantic suites are run locally.

## 10. Test Results

Pending local execution. Results and exact output are appended below; any failure stops preparation.

## 11. Docker Image Requirement

YES. `app/peer.py` is runtime container code and `app/Dockerfile` copies it into the peer image. A new manually built/pushed image is therefore required. Codex will not build, tag, push, or inspect that image.

## 12. Experiment Matrix

Five seeds x three repetitions x two treatments = 30 runs. Factor 2.0, delay 1400 ms. Treatment order alternates deterministically using seed plus repetition parity and actual order is written to `runner.log`.

## 13. Metrics

Existing K5 delivery ratio, propagation delay, duplicates, and total forwards are retained. The analysis adds send attempts, new reach, new-reach efficiency, peer selection frequency, unique selected peers, eligible-neighbor coverage, max-share concentration, repeated-selection rate, and selector semantic violations from existing local logs only.

## 14. Runner

`scripts/run_k5_h2_selector_ab.sh` generates only the frozen coordinates, refuses to overwrite a completed run, reuses `scripts/run_experiment.sh` and `app/k5_exp08_tools.py`, validates each run, restores the Helm topology file, and runs aggregation only after all 30 runs pass.

## 15. Analysis Script

`scripts/k5_h2_selector_ab_analysis.py` preserves matching by seed and repetition and writes `per_run_metrics.csv`, `paired_deltas.csv`, `aggregate_summary.csv`, `per_seed_summary.csv`, and `comparison.md`. It reports descriptive statistics only and makes no significance claim.

## 16. Manual Execution Command

Pending final verification. The final command requires `IMAGE` to reference the user-built H2 image.

## 17. Terminal Commands and Output

Commands executed during audit (read-only unless noted):

```text
sed -n '1,240p' <attached task>; sed -n '241,520p' <attached task>; sed -n '521,900p' <attached task>; sed -n '901,1100p' <attached task>
pwd; rg --files -g AGENTS.md ...; git status --short; rg -n fanout/eligible/neighbor/peer/random/sample/shuffle/selector ...
git status --short; rg -n selector references ...; sed app/peer.py; inspect prior H2 documentation and files
sed relevant app/peer.py, runner, analysis, K5 runner, and test files
sed app/k5_exp08_tools.py, scripts/run_experiment.sh, K5 config, generator, Helm template; rg metrics
sed remainder of app/gen_topology.py; inspect Dockerfile and Docker-command documentation
git diff -- app/peer.py; inspect tests/test_k2.py fixtures
```

Audit outputs established the selector behavior documented in section 5. One exploratory command requested nonexistent guessed paths `app/generate_topology.py` and root `Dockerfile`; repository discovery immediately located the actual files at `app/gen_topology.py` and `app/Dockerfile`. This was not a preparation test failure and changed no state.

Write authorization check:

```text
touch docs/.codex_h2_write_check && rm docs/.codex_h2_write_check
exit 0; no output
```

Edits were applied with patch operations; no Docker, Kubernetes, Helm, or experiment command was executed.

## 18. Current Status

**FAIL / STOPPED during focused local test import.** No regression suite, Docker command, Kubernetes command, or experiment run was attempted after the failure.

### Preparation failure record

Exact command:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k5_h2_selector_ab
```

Failing test/module: `tests.test_k5_h2_selector_ab` failed during module import; zero test methods ran.

Expected behavior: the focused T1--T8 test module imports and runs its nine local test methods.

Observed behavior:

```text
ImportError: Failed to import test module: test_k5_h2_selector_ab
ModuleNotFoundError: No module named 'ahbn_controller'
Ran 1 test in 0.000s
FAILED (errors=1)
```

The output-capture wrapper then also emitted `zsh:3: read-only variable: status` because `status` is reserved by zsh. This secondary logging-wrapper error occurred after the unittest failure and did not cause the test import failure.

Likely cause: `tests/test_k5_h2_selector_ab.py` imports `ahbn_controller` before importing `tests.test_k2`; the existing fixture module is what inserts `app/` into `sys.path`. The production/runtime module is present, but it is not yet on the test process import path at that line.

Minimal proposed correction (not applied): import `tests.test_k2`/its `PEER` fixture before importing `ahbn_controller`, or reuse the controller classes already imported by `tests.test_k2`. In the logging wrapper, rename the shell variable from reserved `status` to `test_exit`. Then rerun only the focused test command. Per the task policy, this correction awaits manual approval/decision.

The continuation task subsequently authorized this exact correction. The preserved text above describes the state at the original stop point; the correction and successful reruns follow below.

## Runtime Change Audit

### `app/peer.py`

Required because the runtime peer must choose between the faithful control and H2 seeded-uniform selector and emit treatment/seed/repetition evidence. It reads the already-computed eligible peers and existing `self.fanout`. It does not alter score, EWMA, observations, thresholds, mode, fanout, or eligibility exclusions. With absent H2 metadata it defaults to `selector_control`; focused and existing instrumentation tests prove the original RNG output and RNG progression are unchanged.

### `app/gen_topology.py`

Required only to copy the experiment-only `k5_h2` seed/repetition/treatment metadata into the topology JSON read by each peer. Graph construction, adjacency ordering, clusters, source, failure, overload, workload, and AHBN metadata are untouched. Locally generated matched A/B topologies had identical `nodes`, topology type, BA parameter, seed, source, failure, bottleneck, workload, and AHBN fields; only treatment/run metadata differed.

Runtime audit answers:

- Canonical AHBN semantics changed: NO
- Topology construction semantics changed: NO
- Fanout changed: NO
- Eligibility changed: NO
- Experiment/selector wiring only: YES
- Baseline algorithms changed: NO
- New network protocol or ACK feedback: NO

## Runner Validation

`bash -n scripts/run_k5_h2_selector_ab.sh`: PASS. The runner contains exactly seeds 42--46, repetitions 1--3, two treatments, factor 2.0, and 1400 ms. Treatment order alternates deterministically. The image is supplied through `IMAGE`; no nonexistent digest is hard-coded. Codex did not execute the runner.

## Analysis Validation

The analysis script passed compilation and two temporary synthetic 30-run/15-pair reconciliations. It matches by seed plus repetition and reports B-A and relative deltas for delivery ratio, propagation delay, duplicates, send attempts, total forwards, new reach, and new-reach efficiency. Per-run output includes mean eligible/selected counts, peer frequencies, unique selected peers, coverage, max-share concentration, repeated-selection rate, and semantic violations. The per-seed table explicitly includes seed 42. No significance claim is made.

## Docker Requirement

New image required: YES. `app/peer.py` is copied by `app/Dockerfile` into the peer runtime image. `app/gen_topology.py` is also copied, although its H2 change is metadata-only. Codex did not build, tag, inspect, or push an image.

## Final Git Diff Audit

Commands:

```text
git status --short
git diff --stat
git diff
git diff --check
```

Result: `git diff --check` PASS. Modified tracked files are `app/peer.py` and `app/gen_topology.py`. New files are this document, `scripts/k5_h2_selector_ab_analysis.py`, `scripts/run_k5_h2_selector_ab.sh`, and `tests/test_k5_h2_selector_ab.py`. No unrelated file is changed. `app/ahbn_controller.py` and `app/observations.py` have empty diffs.

## Final Preparation Status

PASS.

- Focused H2 suite: 9/9 PASS
- Authoritative K2 canonical regression: 21/21 PASS
- Existing H2 instrumentation and K5 semantic regression: 10/10 PASS
- Total recorded local tests: 40/40 PASS
- Controller semantic changes: 0
- Formal GKE runs executed by Codex: 0

## Manual Docker Commands

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
docker build --platform linux/amd64 -t wwiras/ahbn2-peer:k5-h2ab-20260829 -f app/Dockerfile app
docker push wwiras/ahbn2-peer:k5-h2ab-20260829
```

## Manual Experiment Command

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
source /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/activate
IMAGE=wwiras/ahbn2-peer:k5-h2ab-20260829 ./scripts/run_k5_h2_selector_ab.sh
```

Output destination: `output/k5_h2_selector_ab-<UTC timestamp>/`.

```text
chmod +x scripts/run_k5_h2_selector_ab.sh scripts/k5_h2_selector_ab_analysis.py
bash -n scripts/run_k5_h2_selector_ab.sh
python -m py_compile scripts/k5_h2_selector_ab_analysis.py tests/test_k5_h2_selector_ab.py app/peer.py app/gen_topology.py
syntax checks: PASS
```

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k5_h2_selector_ab
test_k5_h2_selector_ab (unittest.loader._FailedTest.test_k5_h2_selector_ab) ... ERROR

======================================================================
ERROR: test_k5_h2_selector_ab (unittest.loader._FailedTest.test_k5_h2_selector_ab)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_k5_h2_selector_ab
Traceback (most recent call last):
  File "/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/lib/python3.14/unittest/loader.py", line 137, in loadTestsFromName
    module = __import__(module_name)
  File "/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/tests/test_k5_h2_selector_ab.py", line 12, in <module>
    from ahbn_controller import AHBNParams, AHBNState, CanonicalAHBNController
ModuleNotFoundError: No module named 'ahbn_controller'


----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (errors=1)

## Import Failure Correction

### Previous Failure

See the preserved preparation failure record above.

### Minimal Correction

Reordered imports in `tests/test_k5_h2_selector_ab.py` so `tests.test_k2` establishes `app/` and reference paths before `ahbn_controller` is imported. Production code was not changed for this correction.

### Focused Test Rerun

```text
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k5_h2_selector_ab
test_frozen_matrix_config_contains_only_requested_coordinate (tests.test_k5_h2_selector_ab.SelectorABTests.test_frozen_matrix_config_contains_only_requested_coordinate) ... ok
test_t1_control_reproduces_existing_selector_and_rng_progression (tests.test_k5_h2_selector_ab.SelectorABTests.test_t1_control_reproduces_existing_selector_and_rng_progression) ... ok
test_t2_t3_t4_eligible_fanout_and_no_duplicate_invariants (tests.test_k5_h2_selector_ab.SelectorABTests.test_t2_t3_t4_eligible_fanout_and_no_duplicate_invariants) ... ok
test_t5_same_seed_set_fanout_and_event_is_order_independent (tests.test_k5_h2_selector_ab.SelectorABTests.test_t5_same_seed_set_fanout_and_event_is_order_independent) ... ok
test_t6_different_seeds_can_change_selection (tests.test_k5_h2_selector_ab.SelectorABTests.test_t6_different_seeds_can_change_selection) ... ok
test_t7_controller_result_is_selector_invariant (tests.test_k5_h2_selector_ab.SelectorABTests.test_t7_controller_result_is_selector_invariant) ... ok
test_t8_unavailable_excluded_and_trace_identifies_treatment (tests.test_k5_h2_selector_ab.SelectorABTests.test_t8_unavailable_excluded_and_trace_identifies_treatment) ... ok

----------------------------------------------------------------------
Ran 7 tests in 0.006s

OK
exit_status=0
```

The first corrected-import rerun executed 7/7 existing methods successfully. To meet the explicit nine-property/9-test contract, the combined T2--T4 method was split into three test methods and the existing frozen-matrix check was extended to verify T9 default-control behavior. No production code changed.

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k5_h2_selector_ab
test_t1_control_reproduces_existing_selector_and_rng_progression (tests.test_k5_h2_selector_ab.SelectorABTests.test_t1_control_reproduces_existing_selector_and_rng_progression) ... ok
test_t2_candidate_selects_only_from_existing_eligible_set (tests.test_k5_h2_selector_ab.SelectorABTests.test_t2_candidate_selects_only_from_existing_eligible_set) ... ok
test_t3_candidate_preserves_canonical_fanout_or_eligible_count (tests.test_k5_h2_selector_ab.SelectorABTests.test_t3_candidate_preserves_canonical_fanout_or_eligible_count) ... ok
test_t4_candidate_has_no_duplicate_recipient (tests.test_k5_h2_selector_ab.SelectorABTests.test_t4_candidate_has_no_duplicate_recipient) ... ok
test_t5_same_seed_set_fanout_and_event_is_order_independent (tests.test_k5_h2_selector_ab.SelectorABTests.test_t5_same_seed_set_fanout_and_event_is_order_independent) ... ok
test_t6_different_seeds_can_change_selection (tests.test_k5_h2_selector_ab.SelectorABTests.test_t6_different_seeds_can_change_selection) ... ok
test_t7_controller_result_is_selector_invariant (tests.test_k5_h2_selector_ab.SelectorABTests.test_t7_controller_result_is_selector_invariant) ... ok
test_t8_unavailable_excluded_and_trace_identifies_treatment (tests.test_k5_h2_selector_ab.SelectorABTests.test_t8_unavailable_excluded_and_trace_identifies_treatment) ... ok
test_t9_default_is_control_and_config_is_frozen (tests.test_k5_h2_selector_ab.SelectorABTests.test_t9_default_is_control_and_config_is_frozen) ... ok

----------------------------------------------------------------------
Ran 9 tests in 0.007s

OK
exit_status=0
```

### Canonical Regression

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k2
test_k2_c01_c02_c03_multistep_trajectories (tests.test_k2.ControllerParityTests.test_k2_c01_c02_c03_multistep_trajectories) ... ok
test_k2_c04_c05_ewma_rise_decay_and_bounds (tests.test_k2.ControllerParityTests.test_k2_c04_c05_ewma_rise_decay_and_bounds) ... ok
test_k2_c06_c07_threshold_and_transitions (tests.test_k2.ControllerParityTests.test_k2_c06_c07_threshold_and_transitions) ... ok
test_k2_c08_dense_fanout_mapping (tests.test_k2.ControllerParityTests.test_k2_c08_dense_fanout_mapping) ... ok
test_k2_c09_long_fixed_seed_stability (tests.test_k2.ControllerParityTests.test_k2_c09_long_fixed_seed_stability) ... ok
test_k2_c10_controller_state_isolation (tests.test_k2.ControllerParityTests.test_k2_c10_controller_state_isolation) ... ok
test_k2_d01_to_d05_gossip_roles_no_mixing_and_fanout (tests.test_k2.DispatchTests.test_k2_d01_to_d05_gossip_roles_no_mixing_and_fanout) ... {"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 2, "eligible_neighbors": [2, 2, 3, 4, 5], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 2, "incoming_sender": 1, "message_id": null, "mode": "gossip", "omitted_eligible_peers": [3, 4, 5], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 1, "selected_peers": [2], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.7624052, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 3, "eligible_neighbors": [2, 2, 3, 4, 5], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 3, "incoming_sender": 1, "message_id": null, "mode": "gossip", "omitted_eligible_peers": [4, 5], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 2, "selected_peers": [2, 3], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.7625768, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 4, "eligible_neighbors": [2, 2, 3, 4, 5], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 4, "incoming_sender": 1, "message_id": null, "mode": "gossip", "omitted_eligible_peers": [4], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 3, "selected_peers": [2, 3, 5], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.762769, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 2, "eligible_neighbors": [2, 2, 3, 4, 5], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 2, "incoming_sender": 1, "message_id": null, "mode": "gossip", "omitted_eligible_peers": [3, 4, 5], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 1, "selected_peers": [2], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.7629561, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 3, "eligible_neighbors": [2, 2, 3, 4, 5], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 3, "incoming_sender": 1, "message_id": null, "mode": "gossip", "omitted_eligible_peers": [4, 5], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 2, "selected_peers": [2, 3], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.7630699, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 4, "eligible_neighbors": [2, 2, 3, 4, 5], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 4, "incoming_sender": 1, "message_id": null, "mode": "gossip", "omitted_eligible_peers": [4], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 3, "selected_peers": [2, 3, 5], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.7631948, "unavailable_neighbors": [], "weight": null}
ok
test_k2_d06_to_d09_structured_member_head_gateway_budget (tests.test_k2.DispatchTests.test_k2_d06_to_d09_structured_member_head_gateway_budget) ... {"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 3, "eligible_neighbors": [9], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 3, "incoming_sender": 1, "message_id": null, "mode": "cluster", "omitted_eligible_peers": [], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 1, "selected_peers": [9], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.763327, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 3, "eligible_neighbors": [], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 3, "incoming_sender": 9, "message_id": null, "mode": "cluster", "omitted_eligible_peers": [], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 0, "selected_peers": [], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.763406, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 3, "eligible_neighbors": [7, 1, 2, 3, 4, 8], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 3, "incoming_sender": 99, "message_id": null, "mode": "cluster", "omitted_eligible_peers": [3, 4, 8], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 3, "selected_peers": [7, 1, 2], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.763495, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 3, "eligible_neighbors": [7, 1, 2, 3, 4, 8], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 3, "incoming_sender": 99, "message_id": null, "mode": "cluster", "omitted_eligible_peers": [3, 4, 8], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 3, "selected_peers": [7, 1, 2], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.763572, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 4, "eligible_neighbors": [7, 2, 3, 4, 8], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 4, "incoming_sender": 1, "message_id": null, "mode": "cluster", "omitted_eligible_peers": [8], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 4, "selected_peers": [7, 2, 3, 4], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.763631, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 4, "eligible_neighbors": [7, 2, 3, 4, 8], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 4, "incoming_sender": 1, "message_id": null, "mode": "cluster", "omitted_eligible_peers": [8], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 4, "selected_peers": [7, 2, 3, 4], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.763724, "unavailable_neighbors": [], "weight": null}
ok
test_k2_d10_d11_sender_self_and_dedup_adversarial (tests.test_k2.DispatchTests.test_k2_d10_d11_sender_self_and_dedup_adversarial) ... {"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 4, "eligible_neighbors": [1, 3, 4, 5], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 4, "incoming_sender": 2, "message_id": null, "mode": "gossip", "omitted_eligible_peers": [], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 4, "selected_peers": [3, 5, 1, 4], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.763894, "unavailable_neighbors": [], "weight": null}
{"active_neighbors": [0, 1, 2, 3, 4, 5], "controller_fanout": 4, "eligible_neighbors": [7, 1, 3, 4, 8], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 4, "incoming_sender": 2, "message_id": null, "mode": "cluster", "omitted_eligible_peers": [8], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 4, "selected_peers": [7, 1, 3, 4], "sender": 0, "topology_neighbors": [0, 1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012733.764, "unavailable_neighbors": [], "weight": null}
ok
test_k2_d12_duplicate_receipt_returns_before_forwarding (tests.test_k2.DispatchTests.test_k2_d12_duplicate_receipt_returns_before_forwarding) ... ok
test_k2_o01_o02_duplicate_windows (tests.test_k2.ObservationTests.test_k2_o01_o02_duplicate_windows) ... ok
test_k2_o03_o04_latency_normalization (tests.test_k2.ObservationTests.test_k2_o03_o04_latency_normalization) ... ok
test_k2_o05_o06_o07_o08_churn_accounting (tests.test_k2.ObservationTests.test_k2_o05_o06_o07_o08_churn_accounting) ... ok
test_k2_o09_o10_peer_local_window_and_ewma_persistence (tests.test_k2.ObservationTests.test_k2_o09_o10_peer_local_window_and_ewma_persistence) ... ok
test_k2_r01_to_r04_failure_and_overload_no_direct_bypass (tests.test_k2.RegressionAndTraceTests.test_k2_r01_to_r04_failure_and_overload_no_direct_bypass) ... ok
test_k2_r05_to_r07_legacy_values_cannot_reach_controller (tests.test_k2.RegressionAndTraceTests.test_k2_r05_to_r07_legacy_values_cannot_reach_controller) ... ok
test_k2_r08_to_r10_experiment_identity_cannot_change_controller (tests.test_k2.RegressionAndTraceTests.test_k2_r08_to_r10_experiment_identity_cannot_change_controller) ... ok
test_k2_t01_to_t10_trace_recomputation_and_provenance (tests.test_k2.RegressionAndTraceTests.test_k2_t01_to_t10_trace_recomputation_and_provenance) ... ok
test_k2_u01_to_u06_binary_magnitude_invariance (tests.test_k2.UtilizationTests.test_k2_u01_to_u06_binary_magnitude_invariance) ... ok
test_k2_u07_u08_ewma_rise_decay (tests.test_k2.UtilizationTests.test_k2_u07_u08_ewma_rise_decay) ... ok
test_k2_u09_u10_actuator_not_decision_input (tests.test_k2.UtilizationTests.test_k2_u09_u10_actuator_not_decision_input) ... ok

----------------------------------------------------------------------
Ran 21 tests in 0.021s

OK
exit_status=0
```

Relevant existing selector instrumentation and forwarding/eligibility semantics:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k5_h2_instrumentation tests.test_k5_stage2_semantics
test_cluster_targets_and_order_are_unchanged (tests.test_k5_h2_instrumentation.H2InstrumentationSemanticsTests.test_cluster_targets_and_order_are_unchanged) ... ok
test_gossip_targets_order_and_rng_progression_are_unchanged (tests.test_k5_h2_instrumentation.H2InstrumentationSemanticsTests.test_gossip_targets_order_and_rng_progression_are_unchanged) ... ok
test_lightweight_fixture_without_runtime_metadata_is_supported (tests.test_k5_h2_instrumentation.H2InstrumentationSemanticsTests.test_lightweight_fixture_without_runtime_metadata_is_supported) ... ok
test_logged_copies_cannot_mutate_forward_targets (tests.test_k5_h2_instrumentation.H2InstrumentationSemanticsTests.test_logged_copies_cannot_mutate_forward_targets) ... ok
test_trace_occurs_after_random_selection (tests.test_k5_h2_instrumentation.H2InstrumentationSemanticsTests.test_trace_occurs_after_random_selection) ... ok
test_ahbn_gossip_filters_unavailable_before_selection (tests.test_k5_stage2_semantics.EligibilitySemanticsTests.test_ahbn_gossip_filters_unavailable_before_selection) ... {"active_neighbors": [1, 3, 5], "controller_fanout": 3, "eligible_neighbors": [1, 3, 5], "event": "ahbn_forwarding_decision", "experiment": null, "fanout_requested": 3, "incoming_sender": 99, "message_id": null, "mode": "gossip", "omitted_eligible_peers": [], "repetition": null, "run_id": null, "score": null, "seed": null, "selected_peer_count": 3, "selected_peers": [1, 5, 3], "sender": 0, "topology_neighbors": [1, 2, 3, 4, 5], "treatment": "selector_control", "ts": 1788012744.940866, "unavailable_neighbors": [2, 4], "weight": null}
ok
test_standalone_gossip_filter_remains_unchanged (tests.test_k5_stage2_semantics.EligibilitySemanticsTests.test_standalone_gossip_filter_remains_unchanged) ... ok
test_duplicate_ack_keeps_healthy_peer_available (tests.test_k5_stage2_semantics.ForwardResultSemanticsTests.test_duplicate_ack_keeps_healthy_peer_available) ... ok
test_transport_failure_marks_peer_unavailable (tests.test_k5_stage2_semantics.ForwardResultSemanticsTests.test_transport_failure_marks_peer_unavailable) ... ok
test_fanout_mapping_and_controller_equation_are_canonical (tests.test_k5_stage2_semantics.FrozenControllerTests.test_fanout_mapping_and_controller_equation_are_canonical) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.004s

OK
exit_status=0
```

### Runner Validation

```text
bash -n scripts/run_k5_h2_selector_ab.sh
runner shell syntax: PASS
```

### Analysis Validation

```text
Local matched-topology and synthetic 30-run analysis validation (temporary directory only)
wrote /var/folders/33/0lf2wn0j4t319z0ps_v666zc0000gn/T/tmp.aGy7rDkHAl/a.json
wrote /var/folders/33/0lf2wn0j4t319z0ps_v666zc0000gn/T/tmp.aGy7rDkHAl/b.json
matched A/B topology and conditions: IDENTICAL; treatment metadata only differs
synthetic matrix fixtures: 30
H2 A/B analysis PASS: 30 runs, 15 matched pairs -> /var/folders/33/0lf2wn0j4t319z0ps_v666zc0000gn/T/tmp.aGy7rDkHAl/analysis
analysis_exit=0
```

Completeness tightening: T7 now compares d_hat/l_hat/u_hat/c_hat explicitly; per-run analysis now records mean eligible and selected counts.

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k5_h2_selector_ab
test_t1_control_reproduces_existing_selector_and_rng_progression (tests.test_k5_h2_selector_ab.SelectorABTests.test_t1_control_reproduces_existing_selector_and_rng_progression) ... ok
test_t2_candidate_selects_only_from_existing_eligible_set (tests.test_k5_h2_selector_ab.SelectorABTests.test_t2_candidate_selects_only_from_existing_eligible_set) ... ok
test_t3_candidate_preserves_canonical_fanout_or_eligible_count (tests.test_k5_h2_selector_ab.SelectorABTests.test_t3_candidate_preserves_canonical_fanout_or_eligible_count) ... ok
test_t4_candidate_has_no_duplicate_recipient (tests.test_k5_h2_selector_ab.SelectorABTests.test_t4_candidate_has_no_duplicate_recipient) ... ok
test_t5_same_seed_set_fanout_and_event_is_order_independent (tests.test_k5_h2_selector_ab.SelectorABTests.test_t5_same_seed_set_fanout_and_event_is_order_independent) ... ok
test_t6_different_seeds_can_change_selection (tests.test_k5_h2_selector_ab.SelectorABTests.test_t6_different_seeds_can_change_selection) ... ok
test_t7_controller_result_is_selector_invariant (tests.test_k5_h2_selector_ab.SelectorABTests.test_t7_controller_result_is_selector_invariant) ... ok
test_t8_unavailable_excluded_and_trace_identifies_treatment (tests.test_k5_h2_selector_ab.SelectorABTests.test_t8_unavailable_excluded_and_trace_identifies_treatment) ... ok
test_t9_default_is_control_and_config_is_frozen (tests.test_k5_h2_selector_ab.SelectorABTests.test_t9_default_is_control_and_config_is_frozen) ... ok

----------------------------------------------------------------------
Ran 9 tests in 0.012s

OK
exit_status=0
```

```text
python -m py_compile scripts/k5_h2_selector_ab_analysis.py
synthetic 30-run paired analysis rerun
H2 A/B analysis PASS: 30 runs, 15 matched pairs -> /var/folders/33/0lf2wn0j4t319z0ps_v666zc0000gn/T/tmp.5JBy1LjrHJ
analysis_exit=0
```

Final verification command:

```text
git status --short
git diff --check
ls -l scripts/run_k5_h2_selector_ab.sh scripts/k5_h2_selector_ab_analysis.py
 M app/gen_topology.py
 M app/peer.py
?? docs/K5_H2AB_diagnostic2.md
?? scripts/k5_h2_selector_ab_analysis.py
?? scripts/run_k5_h2_selector_ab.sh
?? tests/test_k5_h2_selector_ab.py
-rwxr-xr-x@ 1 wwiras  staff  10722 Aug 29 22:13 scripts/k5_h2_selector_ab_analysis.py
-rwxr-xr-x@ 1 wwiras  staff   3624 Aug 29 22:02 scripts/run_k5_h2_selector_ab.sh
final diff and executable checks: PASS
```

## Post-Run Analysis Failure

### Experiment Execution Status

The existing authoritative output was inspected before any edit. All 30 metrics files exist: 15 selector_control and 15 seeded_uniform. Every seed 42--46 has repetitions 1--3 for both treatments.

| Seed | Rep | selector_control | seeded_uniform |
|---:|---:|---|---|
| 42 | 1 | PASS | PASS |
| 42 | 2 | PASS | PASS |
| 42 | 3 | PASS | PASS |
| 43 | 1 | PASS | PASS |
| 43 | 2 | PASS | PASS |
| 43 | 3 | PASS | PASS |
| 44 | 1 | PASS | PASS |
| 44 | 2 | PASS | PASS |
| 44 | 3 | PASS | PASS |
| 45 | 1 | PASS | PASS |
| 45 | 2 | PASS | PASS |
| 45 | 3 | PASS | PASS |
| 46 | 1 | PASS | PASS |
| 46 | 2 | PASS | PASS |
| 46 | 3 | PASS | PASS |

EXPERIMENT EXECUTION STATUS = COMPLETE. No GKE experiment was rerun.

### Failure

The completed runner reached local post-run aggregation and failed with:

```text
KeyError: 'canonical_fanout'
scripts/k5_h2_selector_ab_analysis.py, summarize_run
```

### Actual Persisted Selector Schema

Representative rows were read from both treatments and seeds 42, 44, and 46. All sampled forwarding-decision rows have the same key set:

```text
active_neighbors, controller_fanout, eligible_neighbors, event, experiment,
fanout_requested, incoming_sender, message_id, mode, omitted_eligible_peers,
repetition, run_id, score, seed, selected_peer_count, selected_peers, sender,
topology_neighbors, treatment, ts, unavailable_neighbors, weight
```

Sanitized representative control row:

```json
{"event":"ahbn_forwarding_decision","seed":42,"repetition":1,"treatment":"selector_control","message_id":"m1","sender":5,"mode":"gossip","score":0.022480130195617676,"weight":0.5056197958843149,"controller_fanout":3,"fanout_requested":3,"eligible_neighbors":[0,11,12],"selected_peers":[11,0,12],"selected_peer_count":3,"unavailable_neighbors":[]}
```

Sanitized representative candidate row:

```json
{"event":"ahbn_forwarding_decision","seed":46,"repetition":3,"treatment":"seeded_uniform","message_id":"m1","sender":15,"mode":"gossip","score":0.0032953977584838866,"weight":0.5008238486940624,"controller_fanout":3,"fanout_requested":3,"eligible_neighbors":[9],"selected_peers":[9],"selected_peer_count":1,"unavailable_neighbors":[]}
```

The runtime logger in app/peer.py explicitly emits controller_fanout=self.fanout and fanout_requested=self.fanout. No persisted selector row contains canonical_fanout.

### Root Cause

Case A: the same information exists under another field. The analysis script expected the nonexistent name canonical_fanout, while the persisted runtime canonical AHBN fanout is controller_fanout. fanout_requested is an equivalent compatibility field in these rows. This is an analysis schema mismatch, not a controller, fanout, logging, or experiment-execution failure.

### Minimal Correction

Only scripts/k5_h2_selector_ab_analysis.py and its focused test were changed. A helper now reads controller_fanout first and fanout_requested as a compatible fallback. If neither fanout nor eligibility is available, it returns None, records the diagnostic as unavailable, and leaves primary scientific aggregation intact. It never substitutes an invented numeric value. The 6,965 actual selection rows had zero unavailable fanout diagnostics.

Runtime AHBN code changes for this recovery: NONE. Canonical controller changes: NONE. Fanout mapping changes: NONE. Docker rebuild required: NO.

### Focused Analysis Regression Test

Command:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k5_h2_selector_ab
```

Relevant output:

```text
test_analysis_accepts_actual_persisted_selector_schema ... ok
test_analysis_marks_missing_optional_fanout_unavailable ... ok
test_summarize_run_handles_actual_and_optional_missing_schema ... ok
...
Ran 12 tests in 0.009s
OK
focused_exit=0
```

The end-to-end summarize_run regression covers selector_control, seeded_uniform, expected_selected=min(controller_fanout, unique eligible count), and a missing optional fanout producing None rather than a crash. Full local source suite: 140/140 PASS.

### Existing-Output Analysis Rerun

Command (local aggregation only):

```text
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
PYTHONPYCACHEPREFIX=/private/tmp/h2_pycache /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python scripts/k5_h2_selector_ab_analysis.py analyze --root output/k5_h2_selector_ab-20260830T004109Z
```

Output:

```text
H2 A/B analysis PASS: 30 runs, 15 matched pairs -> output/k5_h2_selector_ab-20260830T004109Z
```

Generated analysis artifacts:

```text
per_run_metrics.csv
paired_deltas.csv
aggregate_summary.csv
per_seed_summary.csv
comparison.md
```

### Matched-Pair Completeness

15/15 seed+repetition pairs and 30/30 runs were analyzed. Persisted topology/config audit found all 15 matched pairs scientifically identical in node count, BA topology and adjacency, source, workload, failure/bottleneck settings, overload factor 2.0, overload delay 1400 ms, and AHBN parameters. Pair metadata differs only in the intended selector treatment/run identity.

### Canonical Invariant Check

Existing H2 logs contain 11,487 controller traces and 6,965 forwarding decisions:

```text
score violations                         0
mode violations                          0
fanout violations                        0
fanout diagnostic unavailable rows       0
unavailable peer selected                0
duplicate ACK -> unavailable violations  0
duplicate ACK outcomes                   4,522
```

These checks use persisted data only. No GKE access or rerun was used.

### Seed-42 Inspection

| Rep | Treatment | Delivery | Delay s | Duplicates | Forwards | Attempts | New-reach efficiency | Coverage | Max share |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | control | 0.6450 | 1.2916 | 198 | 238 | 436 | 0.5917 | 1.000 | 0.2569 |
| 1 | seeded | 0.5450 | 1.0065 | 168 | 198 | 366 | 0.5956 | 1.000 | 0.2295 |
| 2 | control | 0.5175 | 0.8014 | 140 | 187 | 327 | 0.6330 | 1.000 | 0.1407 |
| 2 | seeded | 0.5625 | 1.0098 | 166 | 205 | 371 | 0.6065 | 1.000 | 0.2264 |
| 3 | control | 0.7225 | 1.2902 | 229 | 269 | 498 | 0.5803 | 1.000 | 0.2209 |
| 3 | seeded | 0.5625 | 1.0082 | 166 | 205 | 371 | 0.6065 | 1.000 | 0.2264 |

Seed 42 is mixed across repetitions: candidate delivery is lower in reps 1 and 3 and higher in rep 2. This observation was not used to tune anything.

### Scientific H2 A/B Summary

Across 15 matched pairs, candidate B versus control A changed mean delivery 0.624667 -> 0.536167 (-0.0885, -14.17%), delay 0.7700 -> 0.8015 s (+4.09%), duplicates 170.8 -> 130.667 (-23.50%), attempts 400.667 -> 325.133 (-18.85%), forwards 229.867 -> 194.467 (-15.40%), and new-reach efficiency 0.630296 -> 0.667869 (+5.96%). This is descriptive; paired deltas are variable and no significance claim is made.

Both treatments selected all 20 peers per run on average for control and 19.93 for candidate; mean eligible-neighbor coverage was 1.0000 and 0.9967, max selection share 0.1695 and 0.1579, and repeated-selection rate 0.9481 and 0.9362. These diagnostics are outcome-dependent aggregates over different dissemination trajectories, not proof that selector concentration alone caused the delivery change.

### Final H2 Status

H2 post-run recovery: PASS. Experiment execution is complete, local aggregation is complete, all matched pairs reconcile, canonical/runtime code was not changed, no experiment was rerun, and no Docker rebuild is required. Stop after this analysis; no H3 experiment or new solution is implemented.

### Git Diff Guardrail

```text
$ git status --short
 M app/gen_topology.py
 M app/peer.py
?? docs/K5_H2AB_diagnostic2.md
?? output/
?? scripts/k5_h2_selector_ab_analysis.py
?? scripts/run_k5_h2_selector_ab.sh
?? tests/test_k5_h2_selector_ab.py

$ git diff --stat
 app/gen_topology.py |  3 +++
 app/peer.py         | 55 +++++++++++++++++++++++++++++++++++++++++++++++------
 2 files changed, 52 insertions(+), 6 deletions(-)

$ git diff --check
(no output; PASS)
```

The repository had no commits on these untracked H2 files and already had the shown app/gen_topology.py and app/peer.py H2 runtime modifications before this recovery began. This recovery did not edit either runtime file. Its source changes are confined to the untracked analysis script, focused test, and appended documentation; local aggregation created only analysis artifacts inside the preserved output root.
