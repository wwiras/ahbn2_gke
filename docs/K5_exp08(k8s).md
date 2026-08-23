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
