# K5 final actuator GKE — S0 versus S5-C6

## 1. Scientific question and boundary

Under the unchanged canonical controller `z = -d_hat + l_hat + u_hat + c_hat`, does bounded topology-aware S5-C6 improve the GKE delivery/traffic trade-off over canonical S0? The only treatments are S0 and S5-C6. No S1, S2, S3, S4, C5, C7, cap search, controller change, or further actuator exploration is permitted.

The plain-Python screening selected S5-C6 as the only candidate to take to this final GKE comparison.

## 2. Frozen mappings

- S0: LOW/MODERATE/HIGH = `min(2, Ne) / min(3, Ne) / min(4, Ne)`.
- S5-C6: LOW = `min(ceil(Ne/3), 6, Ne)`; MODERATE = `min(ceil(2Ne/3), 6, Ne)`; HIGH = `min(Ne, 6)`.
- `Ne` is the actual eligible-neighbour count at the forwarding decision. There is no `Ne=9` cap.

The controller, score coefficients/signs, EWMA, score and mode thresholds, eligibility, and canonical selector are identical. The experiment changes only requested fanout after the canonical state update.

## 3. Immutable canonical files

Pre-preparation and post-preparation SHA-256 values are identical:

```text
dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8  app/ahbn_controller.py
64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a  app/peer.py
```

Neither file has a Git diff. The manual runner checks these exact hashes before the first run and after aggregation and stops on mismatch.

## 4. Established K5 scenario and comparability

The preparation reuses `experiments/k5_exp08_ahbn.yaml`, `scripts/run_experiment.sh`, `app/k5_exp08_tools.py`, Helm infrastructure, logging, and validation. Frozen coordinates are BA(m=2), N=20, source peer-0, seeds 42--46, overload factor 2.0 / 1400 ms, trigger 0.5, workload 20 messages at 0.4 seconds, and settle time 18 seconds.

The repository has no approved exact event replay for this actuator comparison. The strongest existing valid mechanism is repeated matched seeds under identical topology, workload, image, namespace, overload, controller, eligibility, selector, logging, and parser. Treatment order alternates by seed to reduce systematic run-order bias. Exact causal replay equivalence is not claimed.

## 5. Implementation mechanism

- `app/k5_final_actuator_policy.py`: pure S0 and S5-C6 mapping using actual `Ne`.
- `app/k5_final_actuator_runtime.py`: experiment-only wrapper around the canonical peer. It invokes the canonical adaptive update, derives the existing LOW/MODERATE/HIGH state from the unchanged score boundaries, computes only the requested budget, and uses the existing cluster/Gossip eligible sets and selection behavior.
- `app/Dockerfile.k5_final_actuator`: dedicated noncanonical image recipe; canonical Dockerfile is untouched.
- `scripts/k5_final_actuator_analysis.py`: frozen config creation, trace validation, per-run metrics, matched-seed deltas, aggregate CSV, and Markdown summary.
- `scripts/run_k5_final_actuator_gke.sh`: manual-only, fail-fast 10-run runner.
- `tests/test_k5_final_actuator_gke.py`: mapping, actual-Ne, isolation, hidden-cap, and parser regression.

Each forwarding decision logs treatment, score, weight, mode, LOW/MODERATE/HIGH state, actual eligible count, canonical controller fanout, requested fanout, and actual fanout. The runtime introduces no peer history, ranking, ACK, Bloom filter, novelty score, or protocol field.

## 6. Treatment isolation and actual-Ne validation

Focused tests apply identical `(d,l,u,c)` observations to independent canonical controllers and prove identical score, weight, and mode. At `Ne=9`, HIGH maps to S0=4 and S5-C6=6 while upstream output remains identical.

S5-C6 expected rows pass for `Ne = 0,1,2,3,4,5,6,7,9,12`:

```text
0: 0/0/0   1: 1/1/1   2: 1/2/2   3: 1/2/3   4: 2/3/4
5: 2/4/5   6: 2/4/6   7: 3/5/6   9: 3/6/6   12: 4/6/6
```

The `Ne=12, LOW -> 4` regression specifically rejects a hidden cap at nine. The parser independently reconstructs the expected mapping from logged actual `Ne` and stops on any mismatch.

## 7. Local validation audit

Initial focused collection failed before executing a test because the test imported the runtime peer module and the local venv does not contain `grpc`. Output ended with `ModuleNotFoundError: No module named 'grpc'`. No Docker or GKE command ran. The minimal correction separated the pure mapper into `app/k5_final_actuator_policy.py`; runtime behavior and scientific design did not change.

Successful command:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q \
  tests/test_k5_final_actuator_gke.py tests/test_k2.py \
  tests/test_k5_stage2_semantics.py tests/test_k5_h2_instrumentation.py
```

Recorded result before the parser regression was added: `35 passed in 0.17s`. After adding the parser regression, the final focused result was `36 passed in 0.21s`. `bash -n`, Python compilation, and `git diff --check` also pass.

An unscoped repository-root `pytest -q` audit then collected four historical test copies under `outputs/**/diagnostic/` and stopped at collection because those archived peer copies import unavailable local `grpc`. The four errors were outside `tests/` and did not execute new experiment code. The authoritative repository suite was therefore rerun explicitly against `tests/`; its output is recorded in the final preparation response. No archived output was modified or deleted.

Authoritative final result: `173 passed, 16 subtests passed in 0.58s` for `python -m pytest -q tests`.

## 8. Docker requirement — manual only

`NEW DOCKER IMAGE REQUIRED: YES`. The current peer image starts canonical `peer.py` and cannot select S5-C6. The dedicated Dockerfile adds the experiment wrapper while retaining immutable canonical modules.

Recommended immutable tag: `wwiras/ahbn2-peer:k5-final-actuator-20260831`.

Manual commands (Codex has not run them):

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
docker build --platform linux/amd64 \
  -t wwiras/ahbn2-peer:k5-final-actuator-20260831 \
  -f app/Dockerfile.k5_final_actuator app
docker push wwiras/ahbn2-peer:k5-final-actuator-20260831
docker buildx imagetools inspect wwiras/ahbn2-peer:k5-final-actuator-20260831
```

Stop after this preparation report. Do not run GKE until the image exists and the user confirms it.

## 9. Manual GKE execution after image confirmation

The runner validates Python, kubectl, Helm, context, authorization, image input, canonical hashes, and focused tests. It creates `outputs/k5_shortest_actuator_solution_gke/<UTC timestamp>/`, alternates treatment order, runs only 10 frozen coordinates, validates every completed run, aggregates only after all runs pass, restores the Helm topology payload, and verifies post-run hashes.

After the image is confirmed, the single command is:

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
IMAGE=wwiras/ahbn2-peer:k5-final-actuator-20260831 \
  ./scripts/run_k5_final_actuator_gke.sh
```

Expected high-level terminal output is the preflight/hash/test PASS, one START/PASS pair for each of 10 coordinates, `FINAL K5 analysis PASS: 10 runs, 5 matched seeds`, matching post-hashes, and the generated result directory. Any readiness, authentication, namespace, image, ConfigMap, controller, actuator, parser, log, or hash failure terminates immediately; `run_experiment.sh` captures pod, StatefulSet, controller, and log diagnostics in the current run directory.

Output topology:

```text
outputs/k5_shortest_actuator_solution_gke/<timestamp>/
  terminal.log  canonical_hashes_before.txt  canonical_hashes_after.txt
  configs/  raw/  logs/  runs/seed{42..46}/{S0,S5-C6}/
  results/per_run.csv  results/per_seed_paired.csv  results/aggregate.csv
  summary/comparison.md
```

## 10. Metrics and final decision rule

Existing definitions remain unchanged for delivery ratio, propagation delay, duplicates, and total forwards. Existing logs supply send attempts, new reach, new-reach efficiency, mode/state counts, eligible counts, requested fanout, and actual fanout. Reports include every seed plus aggregate delta `S5-C6 - S0`; seed divergence is not hidden.

Classify exactly `A. CLEAR S5-C6 WIN` only for a sufficiently consistent delivery/reach gain with acceptable bounded send, duplicate, delay, and efficiency cost. Otherwise classify exactly `B. NO CLEAR S5-C6 WIN`, retain S0, document topology-aware/history-aware selection only as limitation/future work, and stop experimenting. No composite objective or automatic winner is generated.

## 11. Final result

Pending the user-built image and manual GKE run. Codex executed zero Docker builds/pushes and zero GKE experiments.

## 12. Manual image and cluster confirmation — 2026-08-31

The user manually completed the authorized image build, push, and remote inspection. BuildKit reported 13/13 steps finished and local image ID `sha256:c5863e17dbf12ae2d52a2fb893e7c24272ab2ffd612afb6d4f6ad002d327c9f7`. Docker Hub reported manifest-v2 digest:

```text
docker.io/wwiras/ahbn2-peer:k5-final-actuator-20260831
sha256:712beb3f911fd1c405004d7c4e6ec4923f1fe09da573095e4294590b61b180a0
```

The user also manually ran `scripts/setup_gke.sh`. GKE created/reconnected `bcgossip-cluster` in `us-central1-a`; the control plane was healthy and all seven `e2-medium` nodes were `Ready`. The setup script ended with `PASS: GKE cluster bcgossip-cluster is reachable and all nodes are Ready.`

Image gate: PASS. Cluster gate: PASS. Final GKE comparison remains unexecuted by Codex and is ready for the single manual runner command in section 9.

## 13. First manual run fail-fast and diagnosis — 2026-08-31

The user manually invoked:

```bash
IMAGE=wwiras/ahbn2-peer:k5-final-actuator-20260831 \
  ./scripts/run_k5_final_actuator_gke.sh
```

The seed42/S0 workload completed: 20 peers became Ready, the controller job completed, and diagnostics/logs were collected under `outputs/k5_shortest_actuator_solution_gke/20260830T175317Z/runs/seed42/S0`. Post-run validation then stopped at `app/k5_exp08_tools.py:107` with:

```text
FileNotFoundError: .../runs/seed42/S0/statuses.jsonl
```

Inspection found `controller.log`, `logs.jsonl`, `pods.json`, `pods.txt`, `pods_final.txt`, `statefulset.txt`, `statefulset_describe.txt`, and `topology.json`. No equivalent renamed status file existed.

### Output-contract diagnosis

`statuses.jsonl` is produced only by the legacy `collect_statuses()` function inside `scripts/run_k5_exp08.sh`, after `run_experiment.sh` returns. The final-actuator runner never invoked that function. Shared `app/k5_exp08_tools.py validate_run()` nevertheless assumes the legacy file exists because it was written for the original Exp08 80-run matrix. The final runner's actual collection path is `run_experiment.sh -> collect_debug()`, which writes final `pods.json`, pod/StatefulSet diagnostics, `controller.log`, and combined `logs.jsonl` after the controller job completes.

The raw artifacts are authoritative and sufficient: `pods.json` records 20/20 Running, Ready, zero-restart peers; `controller.log` contains exactly one `run_finished`; combined logs contain 20 injections, one overload selection/application, 450 controller traces, 255 S0 actuator decisions, and no treatment/fanout violations. Therefore seed42/S0 is scientifically valid and preserved. No fake `statuses.jsonl` was created.

### Smallest validation fix

Shared Exp08 tooling was not changed. `scripts/k5_final_actuator_analysis.py` now provides an experiment-local `validate-run` command. Mandatory artifacts are `topology.json`, `logs.jsonl`, `pods.json`, and `controller.log`. It fails clearly if any is absent and validates:

- frozen seed/treatment/factor/run identity;
- 20 injections and one overload selection/application;
- exactly one controller completion in combined logs and controller log;
- 20 healthy, Ready, zero-restart pods;
- absence of failure/churn events;
- canonical score contribution arithmetic and mode threshold semantics;
- treatment identity, actual-Ne requested fanout, and actual fanout bound;
- delivery, delay, duplicate, and forward metric reconstruction.

The final runner now calls this validator after each run.

### Interpreter diagnosis and gate

The traceback's `/opt/homebrew/Cellar/python@3.14/3.14.6/.../pathlib` path was the venv's standard-library origin, not evidence that the validator was launched with system Python. Direct inspection proved:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -> python3.14
sys.executable = /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python
Python 3.14.6
```

Every reachable project Python invocation was already passed through `${PYTHON}`; `run_experiment.sh` received it explicitly. To eliminate ambiguity and prevent a future override leak, the runner now pins the exact required executable, verifies `sys.executable` and `sys.prefix`, rejects any other `PYTHON`, and prints Python path, version, and prefix at startup.

### Resume behavior

`run_k5_final_actuator_gke.sh --resume RESULT_ROOT` now requires an existing result root and matching original `image.txt`. For every existing treatment directory it runs full local validation. A valid run emits `SKIP VALID COMPLETE RUN`; a partial or invalid directory stops the runner and is never silently skipped or overwritten. Missing treatment directories run normally. Thus the preserved seed42/S0 is validated/skipped and the first new workload is seed42/S5-C6.

Files modified for this correction:

- `scripts/k5_final_actuator_analysis.py`
- `scripts/run_k5_final_actuator_gke.sh`
- `tests/test_k5_final_actuator_gke.py`
- this audit document

Canonical files remained unchanged at the expected SHA-256 hashes.

Focused verification:

```text
bash -n scripts/run_k5_final_actuator_gke.sh
<required-python> -m py_compile scripts/k5_final_actuator_analysis.py tests/test_k5_final_actuator_gke.py
<required-python> -m pytest -q tests/test_k5_final_actuator_gke.py
........ [100%]
8 passed in 0.06s
```

Authoritative final repository test result after the correction: `176 passed, 16 subtests passed in 1.25s` for `<required-python> -m pytest -q tests`.

Local-only existing-run validation output:

```text
validation=PASS
seed=42 treatment=S0 delivery_ratio=0.6375
propagation_delay=1.2928804397583007 duplicates=195 total_forwards=235
ahbn_trace_rows=450
```

This wrote only the derived `metrics.json` into the existing S0 run directory. No Docker action and no Kubernetes/GKE action was performed by Codex.

New Docker image required: NO. Container runtime code and the manually published image are unchanged.

Exact manual resume command:

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
IMAGE=wwiras/ahbn2-peer:k5-final-actuator-20260831 \
  ./scripts/run_k5_final_actuator_gke.sh --resume \
  outputs/k5_shortest_actuator_solution_gke/20260830T175317Z
```

Expected first messages include the pinned Python identity, `VALIDATE EXISTING seed=42 treatment=S0`, `SKIP VALID COMPLETE RUN seed=42 treatment=S0`, then `START seed=42 treatment=S5-C6`.

## FINAL GKE ACTUATOR DECISION

### Completeness and integrity

The final dataset is complete: 10/10 locally validated GKE runs, comprising S0 and S5-C6 for matched seeds 42–46. Terminal reconciliation reported `FINAL K5 analysis PASS: 10 runs, 5 matched seeds`. Independent read-only revalidation of every raw run also passed.

Canonical hashes before and after are identical:

```text
dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8  app/ahbn_controller.py
64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a  app/peer.py
```

Treatment integrity passed with zero observed fanout violations. S0 used fixed `min(2/3/4, Ne)`. S5-C6 used `min(ceil(Ne/3),6,Ne)`, `min(ceil(2Ne/3),6,Ne)`, and `min(Ne,6)`. Observed actual eligible counts spanned 0–13 and included 11, 12, and 13, proving that runtime `Ne` was neither fixed nor capped at nine.

### Five matched seeds

| Seed | S0 delivery | C6 delivery | Delta | S0 forwards | C6 forwards | Delta | S0 duplicates | C6 duplicates | Delta |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | 0.6375 | 0.5750 | -0.0625 | 235 | 210 | -25 | 195 | 191 | -4 |
| 43 | 0.6550 | 0.7350 | +0.0800 | 242 | 274 | +32 | 188 | 159 | -29 |
| 44 | 0.6425 | 0.5050 | -0.1375 | 237 | 182 | -55 | 144 | 113 | -31 |
| 45 | 0.7300 | 0.7550 | +0.0250 | 272 | 282 | +10 | 213 | 214 | +1 |
| 46 | 0.7025 | 0.3925 | -0.3100 | 261 | 137 | -124 | 147 | 88 | -59 |

Per-treatment run details, including propagation delay and AHBN trace counts:

| Seed | Treatment | Delivery | Delay (s) | Forwards | Duplicates | Trace rows |
|---:|---|---:|---:|---:|---:|---:|
| 42 | S0 | 0.6375 | 1.292880 | 235 | 195 | 450 |
| 42 | S5-C6 | 0.5750 | 0.590336 | 210 | 191 | 421 |
| 43 | S0 | 0.6550 | 0.317230 | 242 | 188 | 450 |
| 43 | S5-C6 | 0.7350 | 0.663742 | 274 | 159 | 453 |
| 44 | S0 | 0.6425 | 0.096888 | 237 | 144 | 401 |
| 44 | S5-C6 | 0.5050 | 0.312410 | 182 | 113 | 315 |
| 45 | S0 | 0.7300 | 1.284132 | 272 | 213 | 505 |
| 45 | S5-C6 | 0.7550 | 1.287221 | 282 | 214 | 516 |
| 46 | S0 | 0.7025 | 0.457525 | 261 | 147 | 428 |
| 46 | S5-C6 | 0.3925 | 0.100446 | 137 | 88 | 245 |

### Aggregate and matched differences

Values below are mean ± sample SD. Confidence intervals use the paired/two-sided t interval with four degrees of freedom and are descriptive given only five pairs.

| Metric | S0 mean ± SD | C6 mean ± SD | Mean delta C6-S0 | 95% CI for delta |
|---|---:|---:|---:|---:|
| Delivery ratio | 0.6735 ± 0.0407 | 0.5925 ± 0.1538 | -0.0810 | [-0.2705, 0.1085] |
| Propagation delay (s) | 0.6897 ± 0.5615 | 0.5908 ± 0.4495 | -0.0989 | [-0.6325, 0.4347] |
| Total forwards | 249.4 ± 16.3 | 217.0 ± 61.5 | -32.4 | [-108.2, 43.4] |
| Duplicates | 177.4 ± 30.5 | 153.0 ± 52.5 | -24.4 | [-54.3, 5.5] |

C6 lost delivery in three seeds (42, 44, 46) and improved it in two (43, 45). Both delivery gains required more forwards. In each large traffic-saving case, delivery also fell. Mean new-reach efficiency increased only 0.0153, with a matched 95% interval spanning zero; this ratio cannot compensate for materially lower absolute dissemination.

Seed 46 is the most severe example but is not isolated. Its 31-percentage-point delivery collapse accompanies 124 fewer forwards and 59 fewer duplicates, while seeds 42 and 44 show the same under-delivery direction. The traffic reduction therefore cannot be interpreted as a robust efficiency improvement.

### Classification and freeze

**B. NO CLEAR S5-C6 WIN**

The canonical controller remains `z = -d_hat + l_hat + u_hat + c_hat`; the result does not show that this controller is wrong. It shows that the tested S5-C6 downstream actuator did not provide a sufficiently robust delivery/traffic trade-off improvement to replace S0 in GKE.

**FINAL ACTUATOR: S0 = 2/3/4 — FROZEN.**

H1 remains a limitation finding: fixed fanout may leave eligible topology capacity unused, but the tested topology-scaled C6 mapping was not reliable enough to replace it. H2 was not solved: no `D_j`, `N_j`, `R_j`, or equivalent neighbour-specific information was introduced. Richer topology-aware or history-aware peer selection remains future work, not part of this experiment.

Reusable final outputs:

- `results/final_matched_seed_comparison.csv`
- `results/final_aggregate_comparison.csv`
- `results/final_decision.md`

**FURTHER K5 ACTUATOR EXPERIMENTS: NONE.** Proceed to Scientific Reports and the remaining thesis. STOP actuator experimentation.
