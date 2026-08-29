# K5 H2 temporary peer-selection diagnostic

## STAGE A — CODEX DEVELOPMENT

### Purpose

This instrumentation-only diagnostic asks whether canonical AHBN's limited forwarding slots are used without observed redundancy (a fanout-pressure signal consistent with H1), or whether selected destinations return duplicate acknowledgements while eligible alternatives were omitted (a selection-opportunity signal consistent with H2).

The earlier external-only design was rejected because canonical logs did not contain the selection-time eligible, selected, and omitted peer sets. Those values cannot be reconstructed reliably from `forward`, `forward_duplicate_ack`, `received_new`, and controller traces alone.

This is a two-run instrumentation validation and directional diagnosis, not statistical inference.

### Canonical freeze

The controller remains:

```text
z = -d_hat + l_hat + u_hat + c_hat

LOW:      z <= -0.25        fanout 2
MODERATE: -0.25 < z < 0.25  fanout 3
HIGH:     z >= 0.25         fanout 4
```

Coefficients, EWMA, zero centres, score thresholds, mode rule, eligibility, selection, RNG, ordering, cache/seen state, duplicate suppression, forwarding, overload, and source semantics are unchanged.

### Runtime instrumentation

`app/peer.py` adds one event type, `ahbn_forwarding_decision`, after canonical targets have been selected. The event records copied observational values:

```text
run_id, experiment, message_id, sender, incoming_sender
mode, score, weight, controller_fanout, fanout_requested
topology_neighbors, active_neighbors, unavailable_neighbors
eligible_neighbors, selected_peers, selected_peer_count
omitted_eligible_peers
```

No RNG key is logged because the canonical runtime has no existing reusable selection key. No RNG call was added. The selected list passed to forwarding is not replaced or mutated by logging.

For AHBN Gossip, the trace receives the candidate list already used by `random.sample`. For AHBN cluster mode, the full candidate list is reconstructed by the same deterministic `cluster_targets` method using an oversized diagnostic-only budget. This makes no state change and consumes no RNG. The original bounded call still determines forwarding targets.

Lightweight fixtures may lack runtime identity metadata. Only the trace uses optional access, producing JSON `null`; canonical `PeerState` requirements were not changed.

### Exact runtime diff

The runtime diff is confined to `app/peer.py`:

1. An optional `message_id` is passed into `target_peers` for trace correlation.
2. A deterministic, non-mutating cluster eligibility observation helper is added outside the canonical Gossip source region.
3. The trace helper copies collections and emits one `ahbn_forwarding_decision` after target selection.
4. `process_envelope` supplies the existing envelope message ID.

Intended runtime semantic difference:

```text
ONE observational ahbn_forwarding_decision log event only
```

There are no intended protocol-semantic changes.

### External analysis

`scripts/k5_h2_peer_selection_analysis.py` correlates decisions and outcomes with:

```text
run_id + message_id + forwarding peer + destination peer + timestamp
```

`forward` or a matching `received_new` is an observed nonduplicate outcome. `forward_duplicate_ack` is an observed duplicate outcome. Events earlier than the decision are ignored. Missing or conflicting outcomes remain unknown.

The conservative classifications are:

- `SELECTION_OPPORTUNITY_SIGNAL`: selected duplicate observed while eligible peers were omitted; incomplete other selected outcomes are allowed because the duplicate opportunity itself is directly observed.
- `FANOUT_PRESSURE_SIGNAL`: saturated fanout, omitted eligible peers, and every selected outcome observed nonduplicate.
- `MIXED`: saturated fanout with omitted peers and fully observed selected outcomes containing both duplicate and nonduplicate results.
- `NO_OMISSION`: every eligible peer was selected.
- `INSUFFICIENT_EVIDENCE`: correlation or selected-outcome evidence is incomplete for any stronger class.

The analyzer creates `per_decision.csv`, `per_seed_summary.csv`, `h1_h2_summary.csv`, `comparison.md`, and per-seed `run_summary.json` while preserving raw logs.

### Scientific limitations

An eligible peer is not necessarily unseen. A later duplicate ACK does not prove the selection was predictably bad when made; distributed races remain possible. Results must be described as observed duplicate outcomes, selection-opportunity signals, and fanout-pressure signals—not causal proof.

### Files changed or added

```text
app/peer.py
scripts/k5_h2_peer_selection_analysis.py
scripts/run_k5_h2_peer_selection_diagnostic.sh
tests/test_k5_h2_instrumentation.py
tests/test_k5_h2_peer_selection.py
docs/K5_H2peertest.md
```

### Original failed regression

Command:

```bash
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest discover -v -s tests
```

Relevant exact terminal result:

```text
Ran 127 tests in 0.056s

FAILED (failures=1, errors=9)
```

The nine errors were:

```text
AttributeError: 'PeerState' object has no attribute 'run_id'
```

The static failure was:

```text
FAIL: test_no_legacy_controller_bypasses_or_gossip_structural_append
AssertionError: 'gateway_neighbors' unexpectedly found in gossip_branch
```

Causes and corrections:

- The first safe-metadata patch had matched `peer_started` instead of the new trace helper. `peer_started` was restored exactly, and only the observational helper now uses `getattr(..., None)`.
- Cluster diagnostic reconstruction mentioned `gateway_neighbors` inside the static canonical Gossip source slice. It was moved into a diagnostic helper before `target_peers`; canonical selection and the existing regression were not changed.

### Focused corrective tests

Command:

```bash
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest -v tests.test_k5_h2_instrumentation tests.test_k5_h2_peer_selection tests.test_k1.StaticBypassTests.test_no_legacy_controller_bypasses_or_gossip_structural_append tests.test_k2.DispatchTests tests.test_k3_6_cross_baseline tests.test_k5_stage2_semantics.EligibilitySemanticsTests
```

Exact summary:

```text
----------------------------------------------------------------------
Ran 34 tests in 0.014s

OK
```

This covers lightweight fixture compatibility, selection/order invariance, subsequent RNG progression, log-after-selection order, copied trace collections, cluster/Gateway ordering, parser validation, classifications, duplicate records, missing records, malformed records, empty sets, and timestamp-sensitive correlation.

### Full local regression

Command:

```bash
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest discover -v -s tests
```

Exact summary:

```text
----------------------------------------------------------------------
Ran 128 tests in 0.054s

OK
```

Final status:

```text
controller equation unchanged: PASS
controller thresholds unchanged: PASS
fanout 2/3/4 unchanged: PASS
mode rule unchanged: PASS
eligibility unchanged: PASS
selection algorithm unchanged: PASS
selected-peer ordering unchanged: PASS
RNG progression unchanged: PASS
forward targets unchanged: PASS
gateway semantics unchanged: PASS
duplicate suppression unchanged: PASS
```

### Static validation

Commands:

```bash
bash -n scripts/run_k5_h2_peer_selection_diagnostic.sh

/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python - <<'PY'
import ast
from pathlib import Path
for name in ('scripts/k5_h2_peer_selection_analysis.py', 'tests/test_k5_h2_instrumentation.py', 'tests/test_k5_h2_peer_selection.py'):
    ast.parse(Path(name).read_text(encoding='utf-8'), filename=name)
    print(f'{name}: syntax PASS')
PY

git diff --check
```

Exact output:

```text
runner shell syntax: PASS
scripts/k5_h2_peer_selection_analysis.py: syntax PASS
tests/test_k5_h2_instrumentation.py: syntax PASS
tests/test_k5_h2_peer_selection.py: syntax PASS
git diff --check: PASS
```

One earlier `py_compile` attempt could not write a temporary file into an existing protected `scripts/__pycache__`; this was a filesystem artifact, not a source failure. Read-only AST parsing above passed for every new Python source.

Stage A completion:

```text
Canonical semantic changes: 0
Observational trace additions: 1
Docker images built by Codex: 0
Docker images pushed by Codex: 0
GKE diagnostic runs executed by Codex: 0
```

## STAGE B — USER MANUAL DOCKER BUILD

The repository Dockerfile is `app/Dockerfile`, its required build context is `app`, and existing GKE builds target `linux/amd64`. Use the dedicated noncanonical diagnostic tag below.

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke

docker build \
  --platform linux/amd64 \
  -t wwiras/ahbn2-peer:k5-h2diag-20260829 \
  -f app/Dockerfile \
  app

docker push wwiras/ahbn2-peer:k5-h2diag-20260829

docker buildx imagetools inspect wwiras/ahbn2-peer:k5-h2diag-20260829
```

Record the pushed digest printed by the final two commands.

**STOP HERE IF ANY COMMAND FAILS.**

Return the complete terminal output for correction. Do not proceed to GKE.

Codex did not execute any command in this stage.

## STAGE C — USER MANUAL GKE RUN

Proceed only after Stage B build, push, and remote image inspection all succeed.

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke

./scripts/run_k5_h2_peer_selection_diagnostic.sh \
  --image wwiras/ahbn2-peer:k5-h2diag-20260829
```

The runner verifies the expected context `gke_stoked-cosine-415611_us-central1-a_bcgossip-cluster`, uses namespace `ahbn-k5-h2`, and fails rather than falling back to a canonical image.

This performs exactly two diagnostic runs:

```text
seed 42 × 1
seed 44 × 1
```

It does not run formal K5 and does not rerun a failed seed automatically.

Expected output root:

```text
outputs/k5_h2_peer_selection-<UTC timestamp>/
```

Expected contents include:

```text
metadata.json
seed42/raw/
seed42/run_summary.json
seed44/raw/
seed44/run_summary.json
per_decision.csv
per_seed_summary.csv
h1_h2_summary.csv
comparison.md
logs/runner.log
```

Inspect results with:

```bash
find outputs/k5_h2_peer_selection-* -maxdepth 3 -type f | sort

tail -n +1 outputs/k5_h2_peer_selection-*/comparison.md

/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python - <<'PY'
from pathlib import Path
roots = sorted(Path("outputs").glob("k5_h2_peer_selection-*"))
if not roots:
    raise SystemExit("no H2 output found")
root = roots[-1]
print(root)
print((root / "comparison.md").read_text())
PY
```

If either seed fails, stop. Preserve the output directory and complete terminal output; do not rerun automatically.

```text
Docker images built by Codex: 0
Docker images pushed by Codex: 0
GKE diagnostic runs executed by Codex: 0
```
