# Stage B — Complete Controller Causal Chain
## B0 Preflight

The authoritative preflight completed from `/Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61`. Git status was empty; HEAD was `d58f2a0510926afc95fff1b33931cdd86dc5ab17`. The required interpreter reported Python 3.14.6 and resolved to `/Users/wwiras/Documents/src/AHBNProj/venv0.6/bin/python`. The preserved K5 smoke directory exists.

```console
$ pwd
/Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61
$ git status --short
$ git rev-parse HEAD
d58f2a0510926afc95fff1b33931cdd86dc5ab17
$ /Users/wwiras/Documents/src/AHBNProj/venv0.6/bin/python --version
Python 3.14.6
$ /Users/wwiras/Documents/src/AHBNProj/venv0.6/bin/python -c 'import sys; print(sys.executable)'
/Users/wwiras/Documents/src/AHBNProj/venv0.6/bin/python
$ test -d /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08-20260824_113523
# exit 0
```
## B1 Trace discovery

Trace file: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08-20260824_113523/runs/k5_ahbn_seed42_factor1.0/logs.jsonl`

Row count: **322** AHBN controller trace events (from 1,161 JSONL records).

Available logged fields: `c_hat`, `churn_join_count`, `churn_leave_count`, `churn_score_contribution`, `d_hat`, `duplicate_window_duplicates`, `duplicate_window_received`, `duplication_score_contribution`, `event`, `experiment`, `fanout`, `fanout_changed`, `l_hat`, `latency_normalized`, `latency_raw`, `latency_score_contribution`, `latency_window_count`, `mode`, `mode_changed`, `neighbor_count`, `overload_active`, `overload_ms`, `peer_id`, `raw_c`, `raw_d`, `raw_l`, `raw_u`, `run_id`, `score`, `ts`, `u_hat`, `utilization_score_contribution`, `utilization_source`, `weight`.

Raw observations (`raw_d`, `raw_l`, `raw_u`, `raw_c`) and all four EWMAs are logged. Message identifiers are not present on controller rows; peer and timestamp are present. The overload target is not a per-row field; `overload_active`, `overload_ms`, and utilization source are present.

```console
$ wc -l .../runs/k5_ahbn_seed42_factor1.0/logs.jsonl
1161 .../runs/k5_ahbn_seed42_factor1.0/logs.jsonl
$ rg -c '"event": "ahbn_controller_trace"' .../logs.jsonl
322
```

The JSONL collector occasionally concatenated multiple valid JSON objects on one physical line. The diagnostic reader therefore used `json.JSONDecoder.raw_decode` repeatedly per line, preserving every object and original object order.
## B2 Canonical equation verification

The canonical source `ahbn/control.py` and preserved run config agree: alpha=0.30; d0=l0=u0=c0=0.50; w_d=-1, w_l=+1, w_u=-1, w_c=+1; kappa=1; beta=1; mode_threshold=0.50; min/max/default fanout=2/4/3 (default fanout is run configuration/initial state, not an `AHBNParams` member). Runtime score is `Cd+Cl+Cu+Cc`; weight is `sigmoid(kappa*score)`; mode is gossip iff weight >= 0.50; fanout is `round(clamp(2 + weight*2, 2, 4))`.

Commands used read-only:

```console
$ sed -n '1,340p' ahbn/control.py
$ sed -n '1,120p' .../configs/k5_ahbn_seed42_factor1.0.yaml
```

Relevant exact source expressions:

```python
return (
    p.w_d * (state.d_hat - p.d0)
    + p.w_l * (state.l_hat - p.l0)
    + p.w_u * (state.u_hat - p.u0)
    + p.w_c * (state.c_hat - p.c0)
)
state.weight = self.sigmoid(p.kappa * state.score)
if state.weight >= p.mode_threshold:
    state.mode = "gossip"
else:
    state.mode = "cluster"
raw_fanout = p.min_fanout + p.beta * state.weight * fanout_span
state.fanout = int(round(self.clamp(raw_fanout, p.min_fanout, p.max_fanout)))
```
## B3 322-state extraction

All 322 events preserve their appearance order in the trace; `sequence` is the resulting 1-based diagnostic row number. Timestamps are retained as logged. No original trace was altered. The complete augmented extraction is `outputs/k5_controller_causality_stageB/stageB_all_states.csv`.
## B4 Equation reconstruction

Maximum `|z_reconstructed-z_logged|`: **0**. Maximum `|weight_reconstructed-weight_logged|`: **1.1102230246251565e-16**. Mismatches at tolerance 1e-12: **0**. Gate: **PASS**.
## B5 Mode/fanout reconciliation

| Mode | Fanout | Count |
|---|---:|---:|
| cluster | 2 | 72 |
| cluster | 3 | 127 |
| gossip | 3 | 123 |
| gossip | 4 | 0 |

Ordering used for reconciliation: preserved trace record `sequence`. Adjacent-row mode transitions: **23**; adjacent-row fanout transitions: **2**. Gate: **PASS** against the reported 23/2. For scientific clarity, because rows from different peers are interleaved, true per-peer transitions (ascending `ts` within each `peer_id`) are 16/2, matching logged `mode_changed=true`/`fanout_changed=true` counts of 16/2. The reported 23 is therefore a trace-adjacency statistic, while 16 is the actual sum of per-controller mode changes.
## B6 Group diagnostic statistics

| Mode | Fanout | n | d_hat mean | l_hat mean | u_hat mean | c_hat mean | Cd mean | Cl mean | Cu mean | Cc mean | z mean | Weight min | Weight mean | Weight max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cluster | 2 | 72 | 0.769544 | 0.161186 | 0.967593 | 0.000972 | -0.269544 | -0.338814 | -0.467593 | -0.499028 | -1.574979 | 0.132126 | 0.173082 | 0.246664 |
| cluster | 3 | 127 | 0.494230 | 0.009069 | 0.007874 | 0.021192 | 0.005770 | -0.490931 | 0.492126 | -0.478808 | -0.471843 | 0.265743 | 0.385903 | 0.499959 |
| gossip | 3 | 123 | 0.003654 | 0.005347 | 0.000000 | 0.062550 | 0.496346 | -0.494653 | 0.500000 | -0.437450 | 0.064244 | 0.500006 | 0.516027 | 0.575479 |

Full min/mean/max statistics for every requested signal, contribution, score, and weight are in `stageB_group_summary.csv`.

Fanout-only weight reconciliation:

| Fanout | n | Weight min | Weight mean | Weight max |
|---:|---:|---:|---:|---:|
| 2 | 72 | 0.132125913650299 | 0.173082362005122 | 0.246663717219434 |
| 3 | 250 | 0.265743179626533 | 0.449923973760987 | 0.575479379979082 |

With min=2, max=4, beta=1, raw fanout is `2+2w`; Python rounding produces fanout 2 below 2.5 (w<0.25), fanout 3 throughout this trace for w>=0.25 (no state reaches the fanout-4 boundary w>=0.75). Thus all 72 weights 0.1321–0.2467 quantize to 2, while every remaining weight starts at 0.2657 and quantizes to 3.
## B7 Lowest-weight states

```text
STATE 1
trace row / sequence = 215
peer = 4
timestamp = 1787542890.29645

d_hat = 0.93364788255134
l_hat = 0.0513565616294282
u_hat = 0.999999963296632
c_hat = 1.10110104651882e-09

duplicate:
-1.0 * (0.93364788255134 - 0.50) = -0.43364788255134

latency:
+1.0 * (0.0513565616294282 - 0.50) = -0.448643438370572

utilization:
-1.0 * (0.999999963296632 - 0.50) = -0.499999963296632

churn:
+1.0 * (1.10110104651882e-09 - 0.50) = -0.499999998898899

--------------------------------
z reconstructed      = -1.88229128311744
z logged             = -1.88229128311744
weight reconstructed = 0.132125913650299
weight logged        = 0.132125913650299
mode                  = cluster
fanout                = 2
STATE 2
trace row / sequence = 220
peer = 4
timestamp = 1787542890.7252

d_hat = 0.916818199620404
l_hat = 0.0665836283269282
u_hat = 0.999999993831265
c_hat = 1.85062052888418e-10

duplicate:
-1.0 * (0.916818199620404 - 0.50) = -0.416818199620404

latency:
+1.0 * (0.0665836283269282 - 0.50) = -0.433416371673072

utilization:
-1.0 * (0.999999993831265 - 0.50) = -0.499999993831265

churn:
+1.0 * (1.85062052888418e-10 - 0.50) = -0.499999999814938

--------------------------------
z reconstructed      = -1.85023456493968
z logged             = -1.85023456493968
weight reconstructed = 0.135845358750944
weight logged        = 0.135845358750944
mode                  = cluster
fanout                = 2
STATE 3
trace row / sequence = 173
peer = 4
timestamp = 1787542886.193

d_hat = 0.974052630699
l_hat = 0.00485740995022887
u_hat = 0.882351
c_hat = 0.00352947

duplicate:
-1.0 * (0.974052630699 - 0.50) = -0.474052630699

latency:
+1.0 * (0.00485740995022887 - 0.50) = -0.495142590049771

utilization:
-1.0 * (0.882351 - 0.50) = -0.382351

churn:
+1.0 * (0.00352947 - 0.50) = -0.49647053

--------------------------------
z reconstructed      = -1.84801675074877
z logged             = -1.84801675074877
weight reconstructed = 0.136105921388375
weight logged        = 0.136105921388375
mode                  = cluster
fanout                = 2
STATE 4
trace row / sequence = 214
peer = 4
timestamp = 1787542890.29553

d_hat = 0.905211260787629
l_hat = 0.0709820583440771
u_hat = 0.999999947566617
c_hat = 1.57300149502689e-09

duplicate:
-1.0 * (0.905211260787629 - 0.50) = -0.405211260787629

latency:
+1.0 * (0.0709820583440771 - 0.50) = -0.429017941655923

utilization:
-1.0 * (0.999999947566617 - 0.50) = -0.499999947566617

churn:
+1.0 * (1.57300149502689e-09 - 0.50) = -0.499999998426998

--------------------------------
z reconstructed      = -1.83422914843717
z logged             = -1.83422914843717
weight reconstructed = 0.137735231636826
weight logged        = 0.137735231636826
mode                  = cluster
fanout                = 2
STATE 5
trace row / sequence = 219
peer = 4
timestamp = 1787542890.72207

d_hat = 0.881168856600577
l_hat = 0.0934862336520292
u_hat = 0.999999991187521
c_hat = 2.64374361269169e-10

duplicate:
-1.0 * (0.881168856600577 - 0.50) = -0.381168856600577

latency:
+1.0 * (0.0934862336520292 - 0.50) = -0.406513766347971

utilization:
-1.0 * (0.999999991187521 - 0.50) = -0.499999991187521

churn:
+1.0 * (2.64374361269169e-10 - 0.50) = -0.499999999735626

--------------------------------
z reconstructed      = -1.78768261387169
z logged             = -1.78768261387169
weight reconstructed = 0.14335707685682
weight logged        = 0.14335707685682
mode                  = cluster
fanout                = 2
```
## B8 Boundary-state analysis

| Representative | Seq | Peer | d_hat | l_hat | u_hat | c_hat | Cd | Cl | Cu | Cc | z | weight | mode | fanout |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| typical_cluster_fanout2 | 233 | 4 | 0.804272716137435 | 0.142209904243991 | 0.999999999940232 | 1.79304791682467e-12 | -0.304272716137435 | -0.357790095756009 | -0.499999999940232 | -0.499999999998207 | -1.66206281183188 | 0.159485283308818 | cluster | 2 |
| typical_cluster_fanout3 | 70 | 0 | 0.51 | 0.00660369443893432 | 0 | 0 | -0.01 | -0.493396305561066 | 0.5 | -0.5 | -0.503396305561066 | 0.376742856967779 | cluster | 3 |
| cluster_closest_below_0.50 | 22 | 3 | 0.21 | 0.00983445310592651 | 0 | 0.2 | 0.29 | -0.490165546894073 | 0.5 | -0.3 | -0.000165546894073498 | 0.499958613276576 | cluster | 3 |
| gossip_closest_at_or_above_0.50 | 68 | 0 | 0 | 2.47478485107422e-05 | 0 | 0 | 0.5 | -0.499975252151489 | 0.5 | -0.5 | 2.47478485106978e-05 | 0.500006186962127 | gossip | 3 |
| highest_weight | 138 | 13 | 0 | 0.0042428183555603 | 0 | 0.3 | 0.5 | -0.49575718164444 | 0.5 | -0.2 | 0.30424281835556 | 0.575479379979082 | gossip | 3 |

The decision boundary is z=0/weight=0.5. The closest cluster and gossip rows straddle it because their signed contributions sum just below and just above zero, respectively.
## B9 Dominant contribution analysis

Dominant most-negative contribution among cluster+2 states (all exact-minimum terms counted; ties reported separately):

- duplicate: 0 / 72
- latency: 4 / 72
- utilization: 0 / 72
- churn: 68 / 72

Tied rows: 0.

cluster+2: mean Cd=-0.269544, mean Cl=-0.338814, mean Cu=-0.467593, mean Cc=-0.499028.

cluster+3: mean Cd=0.005770, mean Cl=-0.490931, mean Cu=0.492126, mean Cc=-0.478808.

gossip+3: mean Cd=0.496346, mean Cl=-0.494653, mean Cu=0.500000, mean Cc=-0.437450.

Churn is the most-negative term in 68/72 cluster+2 states and has the largest negative magnitude on average. Latency is most-negative in the other 4 states. There are no positive terms on average in cluster+2: high utilization, high duplicates, low latency, and low churn all contribute negatively, so the outcome is decisively multi-signal, with churn the largest mean downward term and utilization close behind. Cluster+3 differs sharply: low utilization produces a positive Cu that nearly cancels negative latency and churn, while Cd is near neutral. Gossip+3 crosses z>=0 because low duplicates and low utilization contribute almost +0.5 each, overcoming negative latency and churn.
## B10 Causal conclusion

Observed condition: 72 states have weight <0.25, remain below the 0.50 mode threshold, and map to cluster/fanout 2.

Signal behaviour (cluster+2 means): d_hat=0.769544, l_hat=0.161186, u_hat=0.967593, c_hat=0.000972.

Controller contributions: Cd=-0.269544, Cl=-0.338814, Cu=-0.467593, Cc=-0.499028.

Dominant downward driver: churn contribution Cc (most-negative in 68/72 and largest negative magnitude on average), closely followed on average by utilization Cu.

Counteracting upward drivers: none on average; all four mean contributions are negative. Individual rows may have less-negative terms, but no positive term dominates this group.

Net result: mean z=-1.574979; mean weight=0.173082; weight range=[0.132125913650299, 0.246663717219434]; mode=cluster; fanout=2.

The cluster+fanout2 states are caused by a four-signal combination, dominated by near-zero churn and near-one utilization. Mean c_hat is 0.001 and w_c=+1, contributing Cc approximately -0.499; mean u_hat is 0.968 and w_u=-1, contributing Cu approximately -0.468. High duplicate pressure and low latency add Cd approximately -0.270 and Cl approximately -0.339. Together they push z to a mean of -1.575, giving weights in [0.1321, 0.2467]. Those weights remain below the mode threshold and below the w=0.25 fanout-3 quantization boundary, so they yield cluster mode and fanout 2.
## B11 Final Stage B gate

- [x] Correct preserved 322-state trace identified
- [x] Canonical controller equation verified
- [x] All 322 states reconstructed
- [x] Reconstructed z/weight agree with runtime trace
- [x] Mode × fanout counts reconciled
- [x] cluster+2 = 72 explained
- [x] Five lowest-weight states calculated individually
- [x] Boundary states inspected
- [x] Dominant negative contribution identified; multi-signal combination quantified
- [x] No AHBN/controller/experiment semantics modified
- [x] No K5 rerun
- [x] No GKE access required
- [x] Documentation updated
- [x] Repository left clean except intended diagnostic documentation/output

**STAGE B PASS — CAUSAL DRIVER IDENTIFIED**

### Final repository status

```console
$ git status --short
?? docs/K5controller-causality.md
```

No tracked source, configuration, controller, comparator, or experiment file changed. The new diagnostic output directory is ignored by the repository and exists on disk.

## Stage B output-location correction provenance

The original Stage B diagnostic execution mistakenly used the
`/Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61`
tree as the documentation/output destination.

The authoritative K5 project is
`/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke`.

The completed Stage B diagnostic artifacts were therefore copied without recalculation or scientific modification into the authoritative K5 project tree.

Authoritative output location:

`/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_controller_causality_stageB`

The old v0.61 paths appearing earlier in this document describe historical execution provenance only; they are not the authoritative Stage B result location.

### Correction command transcript

```console
$ cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
$ pwd
/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
$ git status --short
$ git rev-parse HEAD
2b2754e95b7e596389aeede5ddf21764aeefbd27
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python --version
Python 3.14.6
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -c 'import sys; print(sys.executable)'
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python
$ ls -la /Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61/docs/K5controller-causality.md
-rw-r--r--@ 1 wwiras staff 14553 Aug 25 06:10 /Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61/docs/K5controller-causality.md
$ ls -la /Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61/outputs/k5_controller_causality_stageB
total 280
-rw-r--r--@ stageB_all_states.csv
-rw-r--r--@ stageB_boundary_states.csv
-rw-r--r--@ stageB_causal_summary.txt
-rw-r--r--@ stageB_group_summary.csv
-rw-r--r--@ stageB_lowest5_states.csv
```

The source document verification found the unchanged PASS marker, 72/127/123/0 mode-fanout counts, zero reconstruction mismatches, maximum weight error `1.1102230246251565e-16`, 23 trace-adjacency mode transitions, 16 actual per-peer mode transitions, and the unchanged contribution/score/weight findings.

Destination inspection before copying reported:

```text
DESTINATION OUTPUT DIRECTORY DOES NOT EXIST
AUTHORITATIVE DOCUMENTATION FILE DOES NOT EXIST
```

Thus no existing or conflicting Stage B evidence was overwritten.

### SHA-256 copy verification

| File | Source and destination SHA-256 | Match |
|---|---|---|
| `stageB_all_states.csv` | `19295dfd1c93cd5f095630ae9711ea9e9d68e85db29bcfd19aceee29725a26a0` | yes |
| `stageB_group_summary.csv` | `f54bc3e3232beff256398c705e1fdbcb8827614003be53b9385fb3e483567b78` | yes |
| `stageB_lowest5_states.csv` | `aa1d8ace9b32c3afe58916f870d05bee4206a7d2a335483330ab7bb6a27f73c2` | yes |
| `stageB_boundary_states.csv` | `7d30f2f021bf7e2c98bc7b00f68467fd61befa1ec64fdd494e1f2606c38e7a67` | yes |
| `stageB_causal_summary.txt` | `e3f2ec01f0a775e744c5498a5cd822d13658b30f988cff74275bd3c1a7a29c1b` | yes |

No analysis was regenerated. No scientific value changed. No K5/GKE execution occurred. No controller source or experiment semantics were modified. Historical evidence remains in the old project tree.

### Final location-correction verification

```console
$ cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
$ git status --short
?? docs/K5controller-causality.md
$ ls -la docs/K5controller-causality.md
-rw-r--r--@ 1 wwiras staff 17653 Aug 25 06:21 docs/K5controller-causality.md
$ find outputs/k5_controller_causality_stageB -maxdepth 1 -type f -print | sort
outputs/k5_controller_causality_stageB/stageB_all_states.csv
outputs/k5_controller_causality_stageB/stageB_boundary_states.csv
outputs/k5_controller_causality_stageB/stageB_causal_summary.txt
outputs/k5_controller_causality_stageB/stageB_group_summary.csv
outputs/k5_controller_causality_stageB/stageB_lowest5_states.csv
$ cmp source destination # repeated for all five files
all_copied_files_byte_identical=YES
$ test -f old-document && test -d old-output-directory
old_evidence_still_exists=YES
```

- [x] Stage B documentation exists in the authoritative GKE project
- [x] Stage B diagnostic outputs exist in the authoritative GKE project
- [x] Copied diagnostic files hash-match the original completed evidence
- [x] Scientific values are unchanged
- [x] No controller source was modified
- [x] No experiment semantics were modified
- [x] No GKE/K5 execution occurred
- [x] Old evidence was not deleted
- [x] Correct project paths are now recorded

**STAGE B OUTPUT LOCATION CORRECTION — PASS**
