# K5 Exp08(K8s) — Final Actuator Restart

## Source Snapshot

31-Aug-2026 frozen AHBN (`ahbn2_gke_31Aug2026(1).zip` lineage), audited at git commit `7927e647101c22f991b24cfd8a8fe2af10818417` before restart edits.

## Authoritative Actuator Files

The accepted production treatment is S5 from `app/k5_final_actuator_policy.py`, invoked only through `app/k5_final_actuator_runtime.py`. Its frozen requested fanout is: z <= -0.25 -> 2; -0.25 < z < 0.25 -> 3; 0.25 <= z < 0.90 -> 4; 0.90 <= z < 1.50 -> 5; z >= 1.50 -> 6. `tests/test_k5_final_actuator_gke.py`, `scripts/run_k5_final_actuator_gke.sh`, `scripts/k5_final_actuator_analysis.py`, and `docs/K5_GKES0vsS5f2tof6.md` retain the acceptance evidence.

## Canonical Integrity

The controller remains `z = -d_hat + l_hat + u_hat + c_hat`, with alpha 0.3, sigmoid weight, mode `gossip` at weight >= 0.5 and `cluster` otherwise. `app/ahbn_controller.py` and `app/peer.py` were not edited by this restart; pre-edit SHA-256 values were respectively `dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8` and `64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a`.

## Resolved Experiment Matrix

The repository represents repetition through five deterministic seeds, not a separate repetition loop: four algorithms x four delays (700, 1050, 1400, 2100 ms) x seeds 42--46 = **80 formal executions**. Topology is BA(N=20,m=2), source peer-0, comparator order Gossip, Structured, DC-SoC, AHBN. Smoke is eight executions: all four algorithms x seed 42 x 700/2100 ms.

## Docker Image

A rebuild is required because peer-container source and its entrypoint contract changed. Manual command: `scripts/build_push_k5_exp08_final_actuator_image.sh`. Default new tag: `wwiras/ahbn2-peer:k5-exp08-final-s5-20260901`. Codex does not execute this script.

## Local Validation

Pending command capture from the mandated interpreter. No GKE execution is part of local validation.

## Smoke Command

`IMAGE=wwiras/ahbn2-peer:k5-exp08-final-s5-20260901 scripts/run_k5_exp08_smoke.sh`

## Smoke Terminal Output

[pending manual execution]

## Smoke Result

[pending]

## Formal Command

Only after smoke PASS: `IMAGE=wwiras/ahbn2-peer:k5-exp08-final-s5-20260901 scripts/run_k5_exp08_formal.sh --smoke-report outputs/k5_exp08_smoke-<timestamp>/terminal.log`

## Formal Terminal Output

[pending manual execution]

## Formal Results

[pending]

## Statistical Validation

[pending]

## Scientific Interpretation

[pending]

## Final K5 Gate

[pending]

---

# Historical Exp08 record (pre-restart)

# K5 — Exp08(K8s): CH Overload

## Execution metadata

- Execution date/time: 2026-08-23 (Asia/Kuala_Lumpur)
- Project root: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke`
- Python interpreter: `/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python`
- Git commit: `4afeb7e452614061165d4d7c8eafab1e32a081fb`
- Git repository state: clean (`git status --short` returned no output)
- Kubernetes context: `gke_stoked-cosine-415611_us-central1-a_bcgossip-cluster`

## Experiment objective

Observe Gossip, Structured, DC-SoC, and AHBN, in that strict sequential order, while an important forwarding peer remains alive and reachable but receives progressively increasing forwarding/processing delay.

## Frozen scientific semantics

`SLOW != FAILED`. Overload must not remove, restart, replace, disconnect, or trigger failure recovery for the target. Primary metrics are delivery ratio, propagation delay, duplicates, total forwards, and AHBN adaptive traces. The canonical AHBN controller must remain unchanged.

## Commands executed and terminal output

### Repository and source inspection

```text
$ pwd
/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke

$ git status --short

$ git rev-parse HEAD
4afeb7e452614061165d4d7c8eafab1e32a081fb

$ rg --files -g 'AGENTS.md' /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
(no output; no repository AGENTS.md found)
```

Inspection covered `experiments/exp8*.yaml`, `scripts/run_exp8*.sh`, `scripts/run_experiment.sh`, `app/gen_topology.py`, `app/ahbn_controller.py`, prior K3/K4 records, and relevant tests. Existing mechanisms include topology generation, Helm release-local reset, controller execution, pod/controller log collection, plot generation, overload RPC injection, and AHBN controller traces. No K5 master runner, frozen four-level K8s overload sweep, or K5 repetition policy exists.

### Python gate

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python --version
Python 3.14.6

$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -c 'import sys; print(sys.executable)'
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python
```

PASS: the mandated interpreter exists and resolves to itself. No system-Python fallback was used for Python validation or topology generation.

### Kubernetes/GKE prerequisite validation

The first sandboxed API attempt was denied locally, before reaching GKE:

```text
$ kubectl config current-context; kubectl get nodes -o wide; kubectl get pods -A
gke_stoked-cosine-415611_us-central1-a_bcgossip-cluster
Unable to connect to the server: dial tcp 35.255.43.164:443: connect: operation not permitted
Unable to connect to the server: dial tcp 35.255.43.164:443: connect: operation not permitted
```

The identical read-only probe was repeated with network permission:

```text
$ kubectl config current-context
gke_stoked-cosine-415611_us-central1-a_bcgossip-cluster

$ kubectl get nodes -o wide
NAME                                              STATUS   ROLES    AGE     VERSION
gke-bcgossip-cluster-default-pool-958388ec-1mnf   Ready    <none>   3h14m   v1.35.6-gke.1641000
gke-bcgossip-cluster-default-pool-958388ec-5d12   Ready    <none>   3h14m   v1.35.6-gke.1641000
gke-bcgossip-cluster-default-pool-958388ec-807z   Ready    <none>   3h14m   v1.35.6-gke.1641000
gke-bcgossip-cluster-default-pool-958388ec-dr4s   Ready    <none>   3h14m   v1.35.6-gke.1641000
gke-bcgossip-cluster-default-pool-958388ec-g5c6   Ready    <none>   3h14m   v1.35.6-gke.1641000
gke-bcgossip-cluster-default-pool-958388ec-n9mx   Ready    <none>   3h14m   v1.35.6-gke.1641000
gke-bcgossip-cluster-default-pool-958388ec-s29g   Ready    <none>   3h14m   v1.35.6-gke.1641000

$ kubectl get pods -A
NAMESPACE   NAME     READY   STATUS    RESTARTS
ahbn-k4     peer-0   1/1     Running   0
ahbn-k4     peer-1   1/1     Running   0
ahbn-k4     peer-2   1/1     Running   0
ahbn-k4     peer-3   1/1     Running   0
ahbn-k4     peer-4   1/1     Running   0
ahbn-k4     peer-5   1/1     Running   0
ahbn-k4     peer-6   1/1     Running   0
ahbn-k4     peer-7   1/1     Running   0
(all observed GKE system pods were Running; full command output was displayed in the execution terminal)
```

GKE prerequisite: PASS. The cluster was not created, recreated, or torn down.

### Canonical AHBN configuration

`app/ahbn_controller.py` defines immutable defaults:

```text
alpha=0.3; d0=l0=u0=c0=0.5
w_d=-1.0; w_l=1.0; w_u=-1.0; w_c=1.0
kappa=1.0; beta=1.0; min_fanout=2; max_fanout=4
default_fanout=3; mode_threshold=0.5
```

This matches the frozen canonical controller. However, generated topology still exposes legacy/noncanonical AHBN metadata (`min_fanout=1`, `max_fanout=6`) and `exp8_ahbn.yaml` requests `fanout: 2`, `min_fanout: 1`, and `mode_threshold: 0.7`. Prior K4 evidence says these topology fields are ignored by the canonical AHBN runtime, but their presence makes the intended K5 configuration ambiguous and requires explicit reconciliation in a targeted follow-up rather than silent overwrite here.

### Generated Exp08 comparator contracts

```text
$ for f in experiments/exp8_gossip.yaml experiments/exp8_cluster.yaml experiments/exp8_dcsoc.yaml experiments/exp8_ahbn.yaml; do /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python app/gen_topology.py --config "$f" --out <tmp>/<name>.json; done
wrote <tmp>/exp8_gossip.json
wrote <tmp>/exp8_cluster.json
wrote <tmp>/exp8_dcsoc.json
wrote <tmp>/exp8_ahbn.json
```

Relevant generated values:

```text
Gossip:    strategy=gossip, topology=BA(m=2), nodes=20, source=0,
           delay=700 ms, trigger=0.5 s, workload=20 x 0.4 s, settle=18 s
Structured:strategy=cluster, topology=BA(m=2), nodes=20, source=0,
           delay=700 ms, trigger=0.5 s, workload=20 x 0.4 s, settle=18 s
DC-SoC:   strategy=dcsoc, topology=ER(p=0.2), nodes=20, source/master=3,
           delay=250 ms, trigger=20 s, workload=1 x 0 s, settle=15 s
AHBN:     strategy=ahbn, topology=BA(m=2), nodes=20, source=0, fanout field=2,
           delay=700 ms, trigger=0.5 s, workload=20 x 0.4 s, settle=18 s
```

The required control plus progressive overload conditions are not defined. Historical factors `[1.0, 1.5, 2.0, 3.0]` are mentioned in documentation, but no K8s base-delay interpretation or matching four-comparator configuration exists. No repetition count or seed list is defined.

The existing `scripts/run_exp8_compare.sh` runs only:

```text
AHBN -> Structured -> Gossip
```

It omits DC-SoC, uses the wrong mandatory order, and runs one condition once. Therefore it cannot be used as the K5 master experiment without defining new scientific configuration.

### Semantic regression tests

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest tests.test_k1 tests.test_k2 tests.test_k3_2_gossip tests.test_k3_3_structured tests.test_k3_4_dcsoc_static tests.test_k3_5_dcsoc_dynamic
................................................................................
----------------------------------------------------------------------
Ran 80 tests in 0.044s

OK
```

The implementation-level canonical controller and SLOW-not-failure/DC-SoC static semantics pass their existing regression tests. This does not cure the missing/inconsistent K5 campaign definition.

## PASS/FAIL gates

### K5 prerequisite/preflight

**FAIL**. Environment and GKE health pass, but the frozen K5 scientific execution contract is absent/internally inconsistent:

1. No defined K8s overload progression/control mapping.
2. No defined K5 repetition count or seed policy.
3. DC-SoC uses a different topology, source, workload, delay, trigger, and settle time from the other comparators.
4. The existing comparison runner omits DC-SoC and violates the required comparator order.
5. Legacy/noncanonical AHBN fields remain in the Exp08 input/generated topology, even though the canonical runtime currently ignores them.

Continuing would require inventing experiment dimensions or silently choosing among conflicting configurations, which is explicitly forbidden. No comparator was launched.

## Comparator execution

### Gossip execution

NOT RUN — stopped at K5 preflight gate.

### Structured execution

NOT RUN — stopped at K5 preflight gate.

### DC-SoC execution

NOT RUN — stopped at K5 preflight gate.

### AHBN execution

NOT RUN — stopped at K5 preflight gate.

## Cross-comparator validation

NOT RUN.

## Result locations

No K5 result directories were created. Read-only topology generation used a temporary directory. Existing cluster resources were not changed.

## Source/configuration changes

No source, algorithm, experiment configuration, or Kubernetes resource was changed. Only this mandatory execution record was added.

## K5 Final Gate

```text
Environment prerequisite: FAIL (scientific configuration gate; GKE health PASS)
Gossip: NOT RUN
Structured: NOT RUN
DC-SoC: NOT RUN
AHBN: NOT RUN
Cross-comparator integrity: NOT RUN
Aggregation: NOT RUN

Critical semantic gate:
SLOW != FAILED: NOT RUN (implementation regression evidence PASS)

DC-SoC maintenance triggered by overload:
NOT RUN

Canonical AHBN unchanged:
PASS

Final status:
K5 STOPPED — PRECHECK gate failed
```

Smallest supported next step: a targeted correction prompt must establish one authoritative matched K5 configuration, including the K8s interpretation of the four overload levels and the frozen repetition/seed policy, then minimally correct the master sequential runner. Cluster setup/teardown is not required.

## K5 Targeted Preflight Correction

Previous status: `K5 STOPPED — PRECHECK`.

Reason: the K5 campaign definition was incomplete/inconsistent. This remains preserved above as historical evidence and was not an algorithm implementation failure.

The follow-up prompt authoritatively froze:

```text
Shared environment: BA(m=2), N=20, source=0
trigger=0.5 s, workload=20 x 0.4 s, settle=18 s
overload factors=[1.0,1.5,2.0,3.0]
delay mapping=[700,1050,1400,2100] ms
repetitions=5; paired seeds=[42,43,44,45,46]
order=Gossip -> Structured -> DC-SoC -> AHBN
expected formal runs=80
```

Minimal local corrections made:

- Added four K5-only base configurations under `experiments/k5_exp08_*.yaml`.
- Added `scripts/run_k5_exp08.sh`, which is strictly sequential and stops on the first failed run/stage.
- Added `app/k5_exp08_tools.py` for frozen coordinate generation, per-run validation, exact reconciliation, Student-t 95% CI aggregation, and K5 plots.
- Added a K5-only `dcsoc.preserve_message_source` topology option. Legacy DC-SoC experiments retain source=MASTER; K5 retains paired source peer-0. The frozen leaf-to-parent/core forwarding implementation proves source=MASTER is not a fundamental requirement.
- Added deterministic, harness-only `important_peer` overload selection. Exactly one native important peer is selected and logged; the dissemination algorithm receives no privileged selection information.
- Reconciled generated AHBN metadata to canonical values 2/4/3/0.5. `app/ahbn_controller.py` was not changed.
- Allowed the existing runner to accept the mandated Python interpreter, a caller-owned output directory, and caller-owned plotting so the K5 runner can prevent overwrites and validate before aggregation.

No Gossip, Structured, DC-SoC forwarding, AHBN controller, EWMA, threshold, weight, or fanout equation was changed.

## K5.0 — Preflight + Experiment Readiness

### Configuration matrix validation

Command (temporary paths abbreviated):

```text
$ for algorithm in gossip structured dcsoc ahbn; do
    for seed in 42 43 44 45 46; do
      for factor in 1.0 1.5 2.0 3.0; do
        <venv-python> app/k5_exp08_tools.py config ...
        <venv-python> app/gen_topology.py ...
      done
    done
  done
$ <venv-python> <80-coordinate contract assertions>
generated_topologies=80 unique_coordinates=80
algorithms=Gossip -> Structured -> DC-SoC -> AHBN
seeds=42,43,44,45,46
factors=1.0,1.5,2.0,3.0
delays_ms=700,1050,1400,2100
shared_environment=PASS native_dcsoc_structure=PASS canonical_ahbn_metadata=PASS

$ <venv-python> app/k5_exp08_tools.py contract <four seed-42 topologies>
gossip: K5 shared contract PASS
structured: K5 shared contract PASS
dcsoc: K5 shared contract PASS
ahbn: K5 shared contract PASS
algorithms=gossip,structured,dcsoc,ahbn
seeds=42,43,44,45,46
factors=1.0,1.5,2.0,3.0
delays=700,1050,1400,2100
expected_runs=80
```

PASS: all 80 campaign coordinates are unique and match the authoritative contract. DC-SoC establishes native structural edges on every paired BA topology while retaining source peer-0. K5 AHBN topology metadata is canonical-equivalent.

### Semantic regression

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest tests.test_k1 tests.test_k2 tests.test_k3_2_gossip tests.test_k3_3_structured tests.test_k3_4_dcsoc_static tests.test_k3_5_dcsoc_dynamic
................................................................................
----------------------------------------------------------------------
Ran 80 tests in 0.043s

OK
```

PASS: 80/80 existing semantic tests. Canonical AHBN remains unchanged and existing SLOW-not-failure/DC-SoC maintenance isolation tests pass.

### Runtime image publication gate

The corrected controller/target-selection plumbing must be present in the image used by GKE. A dedicated tag was chosen so the K4 image would remain untouched.

Exact command:

```text
$ docker build -t wwiras/ahbn2-peer:k5-20260823 -f app/Dockerfile app && docker push wwiras/ahbn2-peer:k5-20260823
```

Terminal/tool result:

```text
REJECTED — This action was rejected due to unacceptable risk.
Reason: Building is routine, but pushing the project-derived container image to the external Docker Hub repository is sensitive egress and the user did not explicitly authorize that payload and destination. The agent must not attempt to achieve the same outcome via workaround, indirect execution, or policy circumvention. Proceed only with a materially safer alternative, or if the user explicitly approves the action after being informed of the risk. Otherwise, stop and request user input.
```

**K5.0 FAIL / STOP**: runtime readiness cannot be established until the user explicitly authorizes publishing this project-derived image to `docker.io/wwiras/ahbn2-peer:k5-20260823`. No image build/push completed, no smoke run started, and Kubernetes resources were not changed.

## K5.1 — Gossip

NOT RUN — stopped at K5.0 runtime image publication gate.

## K5.2 — Structured

NOT RUN.

## K5.3 — DC-SoC

NOT RUN.

## K5.4 — AHBN

NOT RUN.

## K5.5 — Cross-Comparator Reconciliation

NOT RUN.

## K5.6 — Statistical Aggregation

NOT RUN.

## K5.7 — Plotting

NOT RUN.

## K5.8 — Scientific Analysis

NOT RUN.

## K5.9 — Final Regression + Documentation

NOT RUN. Local pre-runtime semantic regression passed as recorded above.

## K5 Continuation Gate Summary

```text
K5.0 local configuration: PASS
K5.0 semantic regression: 80/80 PASS
K5.0 runtime image publication: FAIL — explicit user authorization required
K5.1 Gossip: NOT RUN
K5.2 Structured: NOT RUN
K5.3 DC-SoC: NOT RUN
K5.4 AHBN: NOT RUN
K5.5 Reconciliation: NOT RUN
K5.6 Statistics: NOT RUN
K5.7 Plotting: NOT RUN
K5.8 Analysis: NOT RUN
K5.9 Final regression: NOT RUN

SLOW != FAILED: runtime NOT RUN; semantic regression PASS
DC-SoC overload-triggered maintenance: runtime NOT RUN
Canonical AHBN unchanged: PASS
GKE preserved: PASS

Final status:
K5 STOPPED — K5.0 runtime image publication authorization required
```

---

# K5 Continuation Update — 2026-08-24

This section supersedes the previous continuation gate summary for the current K5 status while preserving the earlier stopped-gate record above as execution history.

## Updated source and runtime image

Before rebuilding the K5 runtime image, the repository was checked:

```text
$ git status --short
(no output)

$ git rev-parse HEAD
425bf10589c88bb05a45922561e5c0a8032b0605
```

PASS: the repository was clean and the K5-corrected source was built from commit:

```text
425bf10589c88bb05a45922561e5c0a8032b0605
```

The runtime image was intentionally published under:

```text
wwiras/ahbn2-peer:v3
```

Docker Hub push result:

```text
v3: digest: sha256:c083aace8ff051573c741c9a7618087f899f6bd830297df424ef7418dd3712c6 size: 2408
```

Published image verification:

```text
Name:      docker.io/wwiras/ahbn2-peer:v3
MediaType: application/vnd.docker.distribution.manifest.v2+json
Digest:    sha256:c083aace8ff051573c741c9a7618087f899f6bd830297df424ef7418dd3712c6
```

### Updated runtime image gate

```text
K5.0 runtime image publication: PASS
Image: wwiras/ahbn2-peer:v3
Digest: sha256:c083aace8ff051573c741c9a7618087f899f6bd830297df424ef7418dd3712c6
Source commit: 425bf10589c88bb05a45922561e5c0a8032b0605
```

The previous image-publication authorization blocker is therefore RESOLVED.

## GKE restart / readiness

The GKE cluster was created using:

```text
scripts/setup_gke.sh
```

Observed cluster:

```text
NAME              LOCATION       MASTER_VERSION       MACHINE_TYPE  NUM_NODES  STATUS
bcgossip-cluster  us-central1-a  1.35.6-gke.1641000  e2-medium     7          RUNNING
```

All seven nodes reached `Ready`.

Gate:

```text
GKE reachable: PASS
7/7 nodes Ready: PASS
```

## K5 smoke execution

Smoke command:

```text
IMAGE=wwiras/ahbn2-peer:v3 \
./scripts/run_k5_exp08.sh smoke
```

Smoke output root:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08-20260824_113523
```

The smoke run executed exactly one condition for each comparator, in the required order:

```text
Gossip -> Structured -> DC-SoC -> AHBN
seed=42
overload_factor=1.0
overload_delay_ms=700
```

### Smoke results

| Algorithm | Delivery ratio | Propagation delay (s) | Duplicates | Total forwards | AHBN trace rows | DC-SoC maintenance |
|---|---:|---:|---:|---:|---:|---:|
| Gossip | 1.0000 | 0.658093 | 32 | 302 | 0 | 0 |
| Structured | 1.0000 | 0.669261 | 0 | 295 | 0 | 0 |
| DC-SoC | 1.0000 | 0.813742 | 0 | 224 | 0 | 0 |
| AHBN | 0.4875 | 0.644628 | 127 | 165 | 322 | 0 |

Per-stage harness result:

```text
Gossip:     1/1 PASS
Structured: 1/1 PASS
DC-SoC:     1/1 PASS
AHBN:       1/1 PASS
```

Important interpretation: the harness PASS confirms runtime/contract validity. It does not by itself establish that the AHBN delivery result is scientifically acceptable.

## Critical semantic smoke gates

### SLOW != FAILED

PASS.

For the AHBN smoke run, all 20 peers reported:

```text
ready=true
alive=true
```

The overloaded AHBN target was peer 4:

```text
target_peer_id=4
target_role=high-connectivity forwarding peer
seen_count=20
ready=true
alive=true
```

Therefore the overloaded peer remained alive and reachable. The observed AHBN delivery reduction was not caused by pod death or failure semantics.

### DC-SoC overload must not trigger maintenance

PASS.

Observed:

```text
dcsoc_maintenance=0
```

The overload-only condition did not trigger DC-SoC failure recovery / structural maintenance.

### AHBN controller activity

PASS.

Observed:

```text
ahbn_trace_rows=322
```

The AHBN controller was active during the smoke run.

## AHBN smoke anomaly / scientific hold

Although the AHBN run completed mechanically, its delivery ratio was:

```text
0.4875
```

The final AHBN peer statuses showed strongly uneven dissemination:

```text
peer-0   seen=20
peer-1   seen=20
peer-2   seen=19
peer-3   seen=3
peer-4   seen=20
peer-5   seen=20
peer-6   seen=3
peer-7   seen=6
peer-8   seen=7
peer-9   seen=3
peer-10  seen=7
peer-11  seen=19
peer-12  seen=19
peer-13  seen=4
peer-14  seen=2
peer-15  seen=1
peer-16  seen=19
peer-17  seen=1
peer-18  seen=1
peer-19  seen=1
```

Total observed deliveries:

```text
195 / (20 peers x 20 messages) = 195 / 400 = 0.4875
```

All peers were alive and Ready. This therefore indicates real dissemination reachability loss rather than a Kubernetes/pod-health failure or an aggregation error.

## Canonical AHBN fanout concern

The K5 smoke result exposed a broader issue already observed in the control simulator.

Canonical AHBN parameters remain:

```text
min_fanout=2
max_fanout=4
default_fanout=3
beta=1.0
```

The canonical fanout calculation is effectively:

```text
span = max_fanout - min_fanout
raw_fanout = min_fanout + beta * weight * span
fanout = round(raw_fanout)
```

With the frozen `[2,4]` range:

```text
raw_fanout = 2 + 2 * weight
```

A broad central weight range therefore quantizes to fanout 3.

Historical control-simulator evidence must now be treated as part of the gate:

```text
Exp07: runtime AHBN fanout observed at 3
Exp08: mode transitions occurred, but fanout remained 3 / no fanout transitions
Exp09: historical logs to be audited
K5 Exp08 smoke: final peer statuses again report fanout=3
```

This raises two related scientific questions:

1. Is the canonical weight-to-fanout mapping operationally capable of producing fanout changes under the observation ranges actually encountered?
2. When AHBN is in Structured/cluster mode, does applying the bounded AHBN fanout truncate structural forwarding sufficiently to reduce coverage?

These are canonical-design questions and must be resolved from existing control-simulator/K1-K3 evidence before any AHBN code or parameter is changed.

## Required next step — Canonical AHBN Fanout Activation Audit

The formal K5 campaign is now deliberately placed on HOLD.

The next step is a read-only/local audit using preserved traces. No GKE cluster is required.

Audit scope:

```text
Exp07 control simulator
    -> weight min/max
    -> fanout min/max
    -> fanout transitions

Exp08 control simulator
    -> weight min/max
    -> fanout min/max
    -> fanout transitions
    -> mode transitions

Exp09 control simulator
    -> weight min/max
    -> fanout min/max
    -> fanout transitions

K5 Exp08 smoke
    -> weight min/max
    -> fanout distribution
    -> fanout transitions
    -> mode distribution
```

Primary decision:

```text
Does the frozen canonical AHBN fanout mechanism actually activate
outside fanout=3 under the tested observation ranges?
```

No AHBN tuning, max-fanout increase, weight change, beta change, threshold change, or forwarding change is authorized at this stage.

## GKE usage during audit

The fanout audit uses already-collected local logs/results, so GKE does not need to remain running.

The cluster may be torn down during this investigation to avoid unnecessary cloud cost. Cluster teardown completion should be recorded separately when performed.

## Updated K5 stage status

```text
K5.0 configuration matrix: PASS
K5.0 semantic regression: 80/80 PASS
K5.0 runtime image publication: PASS
Runtime image: wwiras/ahbn2-peer:v3
Runtime digest: sha256:c083aace8ff051573c741c9a7618087f899f6bd830297df424ef7418dd3712c6
Source commit: 425bf10589c88bb05a45922561e5c0a8032b0605

GKE smoke prerequisite: PASS
7/7 nodes Ready: PASS

K5 smoke — Gossip: PASS
K5 smoke — Structured: PASS
K5 smoke — DC-SoC: PASS
K5 smoke — AHBN runtime/contract: PASS

SLOW != FAILED: PASS
DC-SoC overload-triggered maintenance: PASS (0 events)
AHBN controller active: PASS (322 trace rows)
Canonical AHBN unchanged: PASS

AHBN smoke delivery sanity: HOLD / INVESTIGATE
Observed AHBN delivery ratio: 0.4875
All 20 AHBN peers alive/Ready: PASS
Observed AHBN final fanout: 3
Historical fanout activation concern: OPEN

K5.1 Gossip formal campaign: NOT RUN
K5.2 Structured formal campaign: NOT RUN
K5.3 DC-SoC formal campaign: NOT RUN
K5.4 AHBN formal campaign: NOT RUN
K5.5 Cross-comparator reconciliation: NOT RUN
K5.6 Statistical aggregation: NOT RUN
K5.7 Plotting: NOT RUN
K5.8 Scientific analysis: IN PROGRESS — fanout activation audit required first
K5.9 Final regression/documentation: NOT RUN

Current final status:
K5 HOLD — SMOKE RUNTIME PASSED; CANONICAL AHBN FANOUT ACTIVATION AUDIT REQUIRED BEFORE FORMAL 80-RUN EXECUTION
```

## Current continuation rule

Do not launch:

```text
IMAGE=wwiras/ahbn2-peer:v3 ./scripts/run_k5_exp08.sh formal
```

until the canonical fanout activation audit is complete and the existing frozen semantics are classified as either:

```text
A. intended canonical behavior -> preserve implementation and continue with scientifically justified interpretation

or

B. canonical design / implementation mismatch -> correct before formal K5, run regression, rebuild image, and repeat smoke
```

The investigation must first use existing evidence. It must not tune AHBN simply to improve the observed K5 delivery result.
