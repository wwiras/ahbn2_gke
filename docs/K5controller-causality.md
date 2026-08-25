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

# Stage C — Observation Semantics Audit

Stage C audited the preserved 322-state K5 Exp08 trace at commit `e3b8ed46849bc5eb7eb05a3ecf3d167735669f61`; it did not rerun K5 or access GKE. Complete evidence tables and reconstruction data are under `outputs/k5_controller_observation_stageC/`.

## Result

The raw observation formula and peer-local EWMA were independently reconstructed for all four signals and every controller row. Maximum error was exactly zero and mismatch count was zero for `raw_d`, `raw_l`, `raw_u`, `raw_c`, `d_hat`, `l_hat`, `u_hat`, and `c_hat`. Each peer begins with four zero EWMAs and applies `hat = 0.3 raw + 0.7 previous_hat`; no resets or stale cross-peer state were found.

| Signal | Actual meaning | Exp08 behaviour | Verdict |
| --- | --- | --- | --- |
| Duplicate | Local interval `duplicates / receives`; seen `message_id` defines duplicate | Target receive stream is duplicate-heavy | EXPECTED |
| Latency | Mean local one-hop `now - sent_at` in seconds, capped against 1 second | Includes target sleep for new messages but not early-return duplicates | SUSPICIOUS |
| Utilization | Binary local `overload_ms > 0` emulation state, not CPU/queue telemetry | Target raw_u=1 throughout active rows; EWMA approaches 1 | EXPECTED |
| Churn | Local `(joins+leaves)/neighbor_count`, capped at 1 | No active-period joins/leaves; EWMA decays toward zero | EXPECTED |

The K5 harness waits 0.5 seconds, then selects the highest-degree eligible non-source forwarding peer. In the AHBN seed-42 factor-1.0 trace it selects peer 4 and injects 700 ms. Peer 4 is not a topology cluster head; the preserved experiment therefore overloads a high-connectivity forwarding peer despite the broad “CH overload” description. All 73 `overload_active=true` controller rows and all 72 `cluster + fanout 2` rows belong to peer 4. None of the other 19 peers produces fanout 2.

The low cluster+2 latency mean is explained by path semantics rather than a unit error. Of the 72 rows, 17 are new-message samples above 0.6 seconds and 55 are duplicate samples below 0.1 seconds. New messages sleep for 700 ms before latency is recorded; duplicates are classified, observed, and returned before that sleep. The 1-second normalization and alpha-0.3 EWMA yield mean `l_hat=0.161186`. This pipeline is internally correct but is a path-dependent measure of overload delay, hence the conservative SUSPICIOUS verdict.

The high utilization value is intentionally synthetic. `InjectOverload` sets local `overload_ms=700`; the adapter maps any positive value to `raw_u=1`; repeated active updates make `u_hat` converge to 1, producing cluster+2 mean `u_hat=0.967593`. It cannot distinguish overload magnitudes and provides no evidence about measured CPU, queue depth, or busy ratio. Such resource claims require instrumentation.

The duplicate mean is supported directly: 55/72 cluster+2 windows contain one duplicate out of one receive, so the peer-local EWMA remains high (`d_hat=0.769544`). Churn is accurately near zero: active rows contain no join/leave observations, raw_c remains zero, and residual state decays (`c_hat=0.000972`).

No concrete observation-generation defect, normalization error, unit mismatch, scope leak, or EWMA defect was established. The remaining primary question is controller interpretation: correctly high utilization favors cluster through `w_u=-1`, while correctly absent churn favors cluster through `w_c=+1`. Those sign/weight questions are explicitly deferred to Stage D.

STAGE C PASS — OBSERVATIONS SOUND; CONTROLLER INTERPRETATION REQUIRES AUDIT


# Stage D — Controller Interpretation Audit

Stage D used the preserved 322 controller states only; it did not rerun K5, access GKE, or modify controller semantics. Preflight ran from the authoritative GKE repository at HEAD `012f653434e1459be45e9679d2cb9762fef58a75` with an initially clean status and the mandated Python 3.14.6 interpreter.

## Intended interpretation and directionality

Higher score/weight selects Gossip and can increase fanout; lower score/weight selects Cluster and can decrease fanout. This source-level meaning is decisive when combined with `docs/exp8.md`, which explicitly expects bottleneck pressure to increase Gossip orientation, alternative dissemination aggressiveness, and fanout. The tested target is precisely a **high-connectivity forwarding peer**, peer 4, not a topology cluster head.

| Signal | Sign | High signal pushes | Scientific verdict |
|---|---:|---|---|
| duplicates | -1 | Cluster | SUPPORTED qualitatively; magnitude/reference unproven |
| latency | +1 | Gossip | SUPPORTED independently of Stage C measurement incompleteness |
| local overload | -1 | Cluster | CONTRADICTED by explicit Exp8/Exp12 design intent |
| churn | +1 | Gossip | SUPPORTED qualitatively; baseline/influence unproven |

The utilization result is not based on a generic assumption that Gossip is always preferable. Local load shedding could scientifically motivate Cluster/lower fanout, but that is not the behaviour declared by this project's bottleneck experiments. Project evidence resolves the competing objectives in favour of Gossip/path diversity and increased aggressiveness for Exp8/Exp12.

## Reference, influence, and interactions

The four observations are unipolar intensities. A shared reference of 0.5 converts absence into a strong opposite vote: no overload contributes +0.5 toward Gossip and no churn contributes -0.5 toward Cluster. Therefore `c_hat≈0` means no churn evidence, not inherently maximum Cluster evidence, and `u_hat≈0` means no overload evidence, not Gossip evidence. No explicit scientific justification was found for common 0.5 references or equal coefficient magnitudes.

Additivity creates problematic overload interactions: low churn, high duplicates, and path-incomplete low latency all reinforce Cluster during the preserved overload condition. The same scalar also couples mode selection to fanout, so overload currently selects Cluster and reduces fanout despite the documented Exp8 expectation of Gossip and fanout escalation. Findings separate Class A direction, Class B baseline/reference, and Class C interaction/coupling issues.

## Preserved-state counterfactuals

For the original 72 cluster+2 states: CF0 stays 72 cluster+2; CF1 (remove utilization) becomes 40 cluster+2 and 32 cluster+3; CF2 (reverse utilization) becomes 5 cluster+2 and 67 cluster+3; CF3 (remove churn) becomes 36 cluster+2 and 36 cluster+3; CF4 (remove latency) becomes 66 cluster+2 and 6 cluster+3; CF5 (reverse utilization and remove churn) becomes 54 cluster+3 and 18 gossip+3. These are offline diagnostics, not replacement-controller proposals. Complete per-state and all-state counts are in `outputs/k5_controller_interpretation_stageD/`.

## Stage E design requirement

A valid Stage E correction must preserve defensible duplicate/churn directionality; make genuine local bottleneck evidence produce the explicitly intended bottleneck response; avoid treating absence of unrelated unipolar pressures as dominant opposite evidence without justification; resolve condition dominance coherently; and make mode and fanout responses scientifically separable or demonstrably aligned. Stage D does not prescribe final weights.

STAGE D PASS — MULTIPLE CONTROLLER INTERPRETATION ISSUES IDENTIFIED


# Stage E — Minimal Controller Correction and Offline Validation

## Result

**STAGE E PASS — STRUCTURAL FORM IDENTIFIED; COEFFICIENT CALIBRATION REQUIRED**

## E0 preflight

- Authoritative working directory: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke`
- Starting commit: `304add5d72e417beff2c3f226781a57746ad7f6d`
- Starting `git status --short`: clean
- Interpreter version: `Python 3.14.6`
- Interpreter executable: `/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python`
- Stage B, C, and D output directories and `docs/K5controller-causality.md`: present

The selected minimum structural correction is zero-reference pressure semantics with overload direction corrected: `z=-a_d d+a_l l+a_u u+a_c c`, positive magnitudes, and no evidence-based intercept. The equal-one instance is a diagnostic baseline, not frozen production calibration. No production controller or experiment YAML was changed; K5 and GKE were not run.

## Offline evidence

The exact 322 Stage B rows were evaluated for E-A and E-B. For E-B, the 72 original Cluster+2 rows produce 0 Cluster+2, 6 Cluster+3, 66 Gossip+3, and 0 Gossip+4, with weights [0.373674342691, 0.692862728262]. This distribution is descriptive, not the acceptance criterion. The paired overload test passes 72/72: every original `u` raises score and weight relative to the identical `u=0` state. Mode movements are {'Cluster->Cluster': 6, 'Cluster->Gossip': 66} and fanout deltas are {0: 72}.

For `a_d=a_l=a_c=1`, each overload row requires `a_u >= (d-l-c)/u` (clipped at zero when the right side is negative). Bounds: minimum 0.186462888886, median 0.664096607433, maximum 2.721619261820. Equal diagnostic `a_u=1` satisfies 66/72. The six misses are early-EWMA states where active overload has not accumulated enough `u_hat` to overcome active duplicate pressure. Equality therefore does not guarantee `z>=0` everywhere and remains scientifically uncalibrated.

All 88 monotonic sweep steps pass for E-B across zero and representative mixed backgrounds. Synthetic tests preserve the intended directions. Duplicate-only pressure selects Cluster, so the correction retains redundancy control and does not structurally collapse to always-Gossip. Churn and latency independently raise orientation; overload does not require high latency.

## Direct answers

1. **Q1:** I1–I7 in `stageE_design_invariants.md`: correct monotonic directions, zero-as-no-contribution, visible overload, and bounded/simple/local deterministic operation.
2. **Q2:** No. Reversing `w_u` alone leaves false opposite evidence caused by 0.5 references.
3. **Q3:** Yes, for these unipolar pressures the common 0.5 references must be removed or equivalently reinterpreted as zero-reference contributions.
4. **Q4:** Zero pressure means zero contribution.
5. **Q5:** No evidenced intercept is required. `b=0` is score-neutral; default mode intent is not explicit, and the inherited threshold tie selects Gossip.
6. **Q6:** Yes. Signs `(-,+,+,+)` preserve duplicate, latency, overload, and churn directionality.
7. **Q7:** With the other diagnostic magnitudes one, required `a_u` ranges from 0.186462888886 to 2.721619261820, median 0.664096607433; row-level bounds are in the CSV.
8. **Q8:** No for universal `z>=0`: `a_u=1` satisfies 66/72 constraints and misses six, with maximum required bound 2.721619261820. It does pass monotonic overload response in all 72 pairs.
9. **Q9:** If policy requires Gossip for every state above a defined severe-overload threshold, a calibrated asymmetric constraint on `a_u` is necessary. No guard or priority branch is yet justified because neither that threshold nor universal-Gossip policy is established.
10. **Q10:** Yes. Corrected overload raises the scalar and naturally raises or preserves both mode orientation and fanout; no contradiction demonstrates a need to decouple.
11. **Q11:** E-B, the zero-reference signed pressure family.
12. **Q12:** Yes; all required synthetic cases have semantically consistent contributions and decisions.
13. **Q13:** Yes; all intended monotonic checks pass.
14. **Q14:** Yes; overload strictly raises score/weight for all 72 paired states because `u>0` and `a_u>0`.
15. **Q15:** Yes structurally and in the duplicate-only test; the full-state counts are reported in `stageE_candidate_summary.csv`.
16. **Q16:** Yes; no-disturbance, single-pressure, and mixed cases retain interpretable behavior independent of Exp08.
17. **Q17:** Structural signs/reference are justified; magnitudes are not scientifically frozen and require later controlled calibration/sensitivity analysis.
18. **Q18:** The formulation is ready for the next calibration stage, but not for production implementation until magnitudes are frozen.

## Gate

All Stage E offline-analysis gates pass. E-C and E-D were explicitly evaluated as conditional escalations and were not activated because no additional structural contradiction was demonstrated. Production `app/ahbn_controller.py`, YAML, cluster state, and experiment execution remained untouched.

# Stage F — Policy-Led Coefficient Calibration

## Scope and preflight

Stage F used only preserved Stage B–E evidence and synthetic pressure states. It did not rerun K5, access GKE, modify controller/YAML, change alpha/kappa/beta/threshold/fanout bounds, or optimize end-to-end outcomes. Preflight ran in `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke` at starting HEAD `00440e90b1894c3b2b923ddbf5ef65e95897549c`; starting `git status --short` was clean. Python was 3.14.6 at the mandated executable. All required prior outputs, the preserved K5 trace, and this document were present.

## Policy and mathematical result

The established family remains `z=-a_d d+a_l l+a_u u+a_c c`, positive coefficients and `b=0`. Set `a_d=1` to remove relative-scale non-identifiability and express latency, overload, and churn as ratios to duplicate cost. Diagnostic bands are LOW `[0,.25]`, MODERATE `(.25,.50]`, HIGH `(.50,.75]`, and SEVERE `(.75,1]`; they are not runtime thresholds.

The exact bottleneck invariant is: with `d,l,c` fixed, increasing `u` must strictly increase score and weight, never decrease fanout, make low-fanout Cluster no more likely, and progressively increase Gossip/alternative-path orientation. It does not require every overload state to be Gossip or fanout 4. Zero pressure is score-neutral (`z=0`, `weight=.5`), and the inherited tie-selected label is not a substantive preference. Duplicate-dominant states are Cluster-oriented; latency-, overload-, and churn-dominant states are Gossip-oriented. Latency supports but is not required for overload response, and small churn remains a small contribution.

The declared conflict policy uses representative high duplicates `.70`: a moderate competitor `.45` does not win, but a severe competitor `.80` does. For any standalone competing signal `x`, this yields `.70/.80 < a_x/a_d < .70/.45`, or `0.875 < ratio < 1.555...`. The exact crossover is always `d/x`. Thus the same policy-derived admissible interval applies initially to `a_l/a_d`, `a_u/a_d`, and `a_c/a_d`. This interval is identified; a unique point within it is not.

## Candidate and preserved-state evidence

F-A `(1,1,1,1)`, F-B `(1,1,1.25,1)`, and F-C `(1,1,1,1.25)` satisfy all policy anchors. F-D `(1,.75,1.25,1)` is rejected because severe latency `.80` does not overcome high duplicates `.70`. No candidate becomes always-Gossip or always-Cluster across 322 states. At scale 1, no preserved weight is below `.10` or above `.90`; F-A spans `.290270–.727836`, while F-B spans `.290270–.774461`. Scale 2 changes confidence/fanout and gives F-B one weight above `.90`, demonstrating why absolute scale is a separate unresolved choice.

All candidate overload comparisons pass 72/72 strict score/weight increases. Every `u=0.0…1.0` sweep across four backgrounds has nondecreasing fanout and strictly increasing score/weight. Existing mode/fanout coupling therefore remains acceptable. Local perturbations preserve sign monotonicity and duplicate-only Cluster behaviour; strict synthetic crossover anchors can change when a ratio is perturbed across their boundary, which correctly exposes that the admissible region—not any point—is robustly established.

The six equal-one negative overload rows are sequences 168–173, the first six overload-EWMA states (`u_hat=.30,.51,.657,.7599,.83193,.882351`) within 0.411 seconds of activation, while duplicate EWMA is `.845616–.974053`. They are scientifically acceptable evidence accumulation, not directional policy violations: every paired state moves upward versus `u=0`, and the brief explicitly rejects universal immediate Gossip. If immediate reaction is later required, that is a new policy/observation-latency requirement rather than evidence for fitting away all six.

## Direct answers

1. **Q1:** The fixed-background strict score/weight increase and nondecreasing-fanout bottleneck invariant stated above.
2. **Q2:** No; neither every `u>0` nor every preserved overload row must be Gossip.
3. **Q3:** Score-neutral: `z=0`, `weight=.5`; the threshold tie label is not a strong policy.
4. **Q4:** Duplicate-dominant conditions must remain Cluster-oriented.
5. **Q5:** Latency-dominant conditions are Gossip-oriented, but latency is supportive rather than a prerequisite for overload adaptation.
6. **Q6:** Overload-dominant conditions are Gossip-oriented and stronger overload must never move orientation backward.
7. **Q7:** Churn-dominant conditions are Gossip-oriented; zero and small churn have zero and small positive contributions.
8. **Q8:** Under the declared diagnostic policy, severe overload `.80` overcomes high duplicates `.70`, while moderate overload `.45` does not.
9. **Q9:** `0.875 < a_u/a_d < 1.555...`; the lower crossover is exactly `.70/.80=.875`.
10. **Q10:** Severe churn `.80` overcomes high duplicates `.70`; moderate churn `.45` does not.
11. **Q11:** `0.875 < a_c/a_d < 1.555...`.
12. **Q12:** Severe latency `.80` overcomes high duplicates `.70`; moderate latency `.45` does not.
13. **Q13:** `0.875 < a_l/a_d < 1.555...`.
14. **Q14:** Acceptable early evidence accumulation, not policy violations, under the stated non-immediate-switch policy.
15. **Q15:** F-A, F-B, and F-C; F-D fails one latency-conflict anchor.
16. **Q16:** No candidate collapses to one mode across all 322 states.
17. **Q17:** No scale-1 candidate excessively saturates. Scale 2 begins to produce a small high-tail for F-B/F-D and materially changes fanout.
18. **Q18:** Yes; all overload sweeps preserve nondecreasing fanout, so no decoupling evidence appears.
19. **Q19:** The feasible ratio region and monotonic directions are robust; individual point candidates can cross deliberately strict policy boundaries under ±20%, so a unique point is not robustly identified.
20. **Q20:** No. Multiple simple sets implement the same approved qualitative policy and preserved evidence cannot distinguish them without fitting Exp08 consequences.
21. **Q21:** Not applicable; no coefficients are scientifically frozen. F-A is the parsimonious leading point only.
22. **Q22:** An independently approved crossover severity and desired score/weight/fanout margin for each conflict, plus evidence establishing the desired absolute sigmoid confidence scale.
23. **Q23:** Structurally yes, but not yet ready for coefficient implementation; the next stage must wait for the missing policy-strength evidence.

## Gate and verdict

All offline Stage F gates pass: repository/evidence verified; no K5/GKE/production changes; structure and zero semantics preserved; policies, inequalities, bands, crossovers, early rows, candidate matrices, 322/72-state consequences, monotonicity, saturation, scale separation, sensitivity, coupling, and ranking documented. The required coefficients-freeze alternative is satisfied by explicitly identifying the evidence gap.

**STAGE F PASS — POLICY CONSTRAINTS ESTABLISHED; UNIQUE CALIBRATION NOT IDENTIFIED**

# Stage F2 — Calibration Decision Gate

Stage F2 used the authoritative repository at initial HEAD `e3ea9be834aba76912b6d559985e3546f2662478` with a clean initial status and Python 3.14.6 from the mandated environment. All Stage B–F and preserved K5 evidence existed. It did not rerun K5, access GKE, change controller/YAML, or optimize an end-to-end outcome.

The asymmetry search found explicit directional requirements—overload must increase Gossip/path-diversity orientation, churn must cause adaptive reaction, and duplicate-dominant conditions remain Cluster-oriented—but no independent claim or cost model establishes that latency, overload, or churn deserves a larger coefficient magnitude. In particular, nothing distinguishes F-B's `a_u=1.25` or F-C's `a_c=1.25` from `1.10` or `1.40`. All hats share the bounded numeric domain `[0,1]`, but they do not share physical units or information content; equal coefficients are therefore not an empirical claim of equal real-world costs.

F-A/F-B/F-C satisfy every declared Stage F anchor with the same required qualitative outcome. All retain overload monotonicity, duplicate-only Cluster behaviour, single-pressure Gossip behaviour, and no scale-1 saturation. Local perturbations expose the established interval boundaries similarly; no candidate has a clear non-performance robustness advantage. Across the preserved 322 states, F-A/F-B differ in only 3 modes and 1 fanout, F-A/F-C in 2 modes and 0 fanouts, and F-B/F-C in 5 modes and 1 fanout. These descriptive differences are not selection criteria.

The formal convention is: among policy-valid coefficient sets, minimize `J=(a_l-1)^2+(a_u-1)^2+(a_c-1)^2` unless independent evidence justifies asymmetry. On the Stage F box, the unique minimizer is F-A `(1,1,1,1)`. This is a minimum-assumption symmetry/parsimony rule, not performance fitting or statistical maximum entropy. Equal-one is conventionally selected, not uniquely estimated.

Global scale is likewise unidentified and mathematically confounded with `kappa` as sigmoid gain. No evidence requires a non-unit scale; scale 1 adds no gain parameter, preserves useful dynamic range, and avoids the stronger saturation/fanout effects seen at scale 2. Therefore scale 1 is frozen by parsimony while `kappa=1` remains unchanged.

The canonical F2 freeze is `a_d=a_l=a_u=a_c=1`, `b=0`, global scale `1`, giving `z=-d+l+u+c`. Alpha, observations, normalization, sigmoid, kappa, threshold/rule, beta, fanout mapping, and fanout bounds remain unchanged. Further coefficient work would be informative only with an independent cost model, crossover severity, or confidence-margin requirement; otherwise it would merely benchmark-fit the controller.

Exact supporting artifacts are under `outputs/k5_controller_calibration_stageF2/`. Stage G implementation is scientifically ready but was not performed.

**STAGE F2 PASS — CANONICAL EQUAL-WEIGHT CALIBRATION FROZEN BY PARSIMONY**
# Stage G — Minimal Scientifically Justified Controller Correction

Stage G began from clean commit `f766d00eb6f36be91ab73812735cc576a07b874e`. The authoritative Stage E, F, and F2 conclusions were read before production editing. F2 freezes the equal-one calibration by parsimony, not empirical optimization.

The old production equation was `z=-(d_hat-0.5)+(l_hat-0.5)-(u_hat-0.5)+(c_hat-0.5)`. Because all four observations are unipolar pressures, absence of pressure must contribute zero rather than opposite evidence. The corrected equation is `z=-d_hat+l_hat+u_hat+c_hat`: duplicate pressure points toward Cluster, while latency, utilization, and churn pressures point toward Gossip. Utilization's sign therefore changes from negative to positive. Coefficient magnitudes remain equal to one because no independent evidence supports asymmetry; the intercept remains zero and global scale remains one. This is a semantic correction, not performance optimization.

Changed implementation/configuration files are `app/ahbn_controller.py` and `experiments/k5_exp08_ahbn.yaml`. The only test expectation changes are in `tests/test_k1.py` and `tests/test_k2.py`, where obsolete pre-G equation/ControlSim comparisons were replaced by direct assertions of the frozen Stage G equation. The additive score architecture, observation and EWMA pipeline, sigmoid, mode rule, and fanout mapping remain intact.

All seven deterministic anchors pass: zero pressure gives `z=0`, weight `0.5`; duplicate-only gives `z=-1`; latency-, utilization-, and churn-only each give `z=+1`; `(d,u)=(0.70,0.45)` gives `z=-0.25`; and `(d,u)=(0.70,0.80)` gives `z=+0.10`. Across four representative backgrounds and `u=0.0..1.0`, score and weight strictly increase and fanout never decreases. Independent direction checks confirm increasing d lowers score and increasing l/u/c raises it.

All 322 untouched Stage B states reconstruct to `z=-d_hat+l_hat+u_hat+c_hat` and `weight=sigmoid(z)` within floating-point tolerance, with unchanged mode/fanout rules. Descriptively, 132 reconstruct as Cluster/fanout-3 and 190 as Gossip/fanout-3; score min/mean/max is `-0.894072335338/-0.0748051356591/0.983671493326`, and weight min/mean/max is `0.290270155821/0.482241347218/0.727836113112`. Of the original 72 Cluster+fanout-2 overload states, 66 reconstruct as Gossip/fanout-3 and 6 as Cluster/fanout-3. These counts are verification only and were not acceptance targets.

All 93 repository unit/regression tests pass. Frozen values remain alpha `0.30`, kappa `1`, beta `1`, mode threshold `0.50`, fanout bounds `[2,4]`, and default fanout `3`. No observation generation, baseline algorithm, DC-SoC behavior, experiment topology, workload, overload semantics, coefficient tuning, threshold tuning, performance-fitting branch, or max-fanout increase occurred.

The smallest established K5 smoke could not run because this environment has no configured Kubernetes current context; `kubectl` fell back to unavailable `localhost:8080`. Consequently no corrected runtime trace exists and runtime equality (`Cu=+u_hat`, `Cc=+c_hat`) is not claimed. Offline implementation and regression gates pass, but the full Stage G acceptance gate remains blocked solely on K5 smoke/runtime verification.

**Stage G verdict: IMPLEMENTATION/OFFLINE VERIFICATION PASS — FULL ACCEPTANCE BLOCKED AT K5 RUNTIME SMOKE.**

## Stage G runtime closure

The previous Stage G block was solely the absence of a Kubernetes context. On 2026-08-25 the active context was `gke_stoked-cosine-415611_us-central1-a_bcgossip-cluster`; `bcgossip-cluster` was RUNNING in `us-central1-a` on GKE `1.35.6-gke.1641000`, and all seven nodes were Ready. The local regression gate remained 93/93 PASS and `git diff --check` passed.

The corrected `app/` source was built by Cloud Build as `gcr.io/stoked-cosine-415611/ahbn2-peer:stageg-20260825` (digest `sha256:6ef9bb70c95ba8e755df31a9c5e52e00544965b6e2609e5fa76a5e11b13c7c36`). Every deployed peer used that digest. Direct inspection inside `peer-0` confirmed references `(0,0,0,0)`, coefficients `(-1,+1,+1,+1)`, alpha `0.3`, kappa `1`, beta `1`, threshold `0.5`, and min/max/default fanout `2/4/3`.

The smallest existing per-run K5 path was selected rather than the comparator matrix: `scripts/run_experiment.sh` with `experiments/k5_exp08_ahbn.yaml`, seed 42, factor 1.0, run ID `k5_ahbn_seed42_factor1.0`. The exact command is preserved in `outputs/k5_controller_correction_stageG/stageG_runtime_smoke_command.txt`. The isolated `ahbn-stageg` deployment reached 20/20 Ready peers, completed its controller job normally, and collected a new trace at `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_stageg_runtime-20260825_1024/runs/k5_ahbn_seed42_factor1.0/logs.jsonl`.

The trace contained 1,886 physical lines, 1,886 parsed JSON objects, and 529 controller rows. For every controller row, independent reconstruction found exact contribution errors of zero, maximum score error `2.220446049250313e-16`, maximum weight error `1.1102230246251565e-16`, and zero mismatches at tolerance `1e-12`. Runtime `Cu=+u_hat` was CONFIRMED on all 41 positive-utilization/active-overload rows. Runtime `Cc=+c_hat`, including approximately zero rather than `-0.5` on all 140 approximately-zero-churn rows, was CONFIRMED.

Logged mode and fanout reconstruction was CONFIRMED with zero mismatches. Counts were Cluster/fanout-3: 348, Gossip/fanout-3: 177, and Gossip/fanout-4: 4. Trace-adjacency transitions were 28 mode and 2 fanout, while actual per-peer transitions were 19 mode and 1 fanout, matching the logged transition flags. Harness metrics—delivery `0.745`, propagation delay `0.6468360066 s`, duplicates `231`, forwards `255`—are descriptive only and were not used for acceptance or tuning.

Runtime score, weight, utilization direction, churn zero-reference semantics, mode mapping, fanout mapping, and parameter freeze are now CONFIRMED. No baseline, observation, topology-generation, workload, overload, failure, churn, or heterogeneity code changed; no tuning, max-fanout increase, or experiment-specific controller logic was introduced.

**STAGE G PASS — MINIMAL SCIENTIFIC CONTROLLER CORRECTION IMPLEMENTED AND VERIFIED IN GKE**

The canonical corrected AHBN controller is frozen and ready for separately authorized formal post-correction evaluation.
