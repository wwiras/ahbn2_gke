# K5 H4 Seen/Cache Semantics Diagnostic

## Scientific question

Do incorrect seen-cache semantics explain K5 Exp08 duplicate/redundant dissemination?
The diagnostic tests false-new receipts, false-duplicate receipts, duplicate refanout,
concurrency races, ACK/receipt consistency, and cache lifetime/key scope. It does not change
duplicate suppression or forwarding behavior.

## Repository finding and operational model

`PeerState.seen_messages` is an exact process-local `set[str]`. `process_envelope` holds one
lock across membership testing and insertion. A new message is inserted before overload delay
and target selection. A cached message records a duplicate, updates observations, logs it, and
returns before target selection. There is no TTL, capacity eviction, probabilistic membership,
or run-ID component in the key.

The K5 runners call `helm uninstall` before every run, so their fresh pods provide run isolation
for reused IDs `m1` through `m20`. Reusing an ID in a second run within the same peer process
would be classified as a duplicate; the deterministic test documents this boundary. It is not
evidence of an observed K5 fault unless pod recreation failed, which existing health/restart
checks would expose.

## Diagnostic invariants

- At most one `received_new` exists per `(run_id, message_id, peer_id)`.
- Every `received_duplicate` has an earlier local `received_new`.
- Every AHBN forwarding decision belongs to a local first receipt and occurs once.
- Duplicate receipt and sender-side duplicate ACK counts match by directed edge where complete
  logs are available; unmatched counts are reported separately because collection loss is not
  automatically a cache error.
- Concurrent identical receipts produce exactly one first-receipt winner.
- Cache state is process-scoped and exact; pod recreation supplies run scoping.

## Files and output

- `scripts/analyze_h4_seen_cache.py`
- `tests/test_h4_seen_cache.py`
- `outputs/k5_h4_seen_cache/h4_summary.json`
- `outputs/k5_h4_seen_cache/h4_summary.txt`
- `outputs/k5_h4_seen_cache/h4_cache_violations.csv`

## Commands

COMMAND TO RUN — local deterministic validation:

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
PYTHONPYCACHEPREFIX=/tmp/k5_h4_pycache \
  /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
  -m pytest tests/test_h4_seen_cache.py -v
```

COMMAND TO RUN — offline K5 overload analysis:

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
  scripts/analyze_h4_seen_cache.py \
  outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed42_factor2.0/logs.jsonl \
  outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed43_factor2.0/logs.jsonl \
  --output outputs/k5_h4_seen_cache
```

No GKE run or Docker image is required because saved logs contain the necessary causal events.

## PASS/FAIL and verdict

PASS requires zero first-receipt uniqueness, duplicate-causality, and decision-causality
violations. ACK mismatches are reported but require trace-completeness review before attribution.

- **H4 SUPPORTED:** direct evidence of false new/duplicate classification, a race, eviction,
  cross-run contamination in an unrestarted process, or duplicate-triggered refanout.
- **H4 PARTIALLY SUPPORTED:** a semantic anomaly exists but its contribution to K5 is limited.
- **H4 NOT SUPPORTED:** exact-cache invariants hold and pod lifecycle isolates reused IDs.
- **H4 INCONCLUSIVE:** logs are incomplete or cannot establish receipt order/lifecycle.

## Environment Failure

The first validation attempt failed before semantic testing:

```text
ModuleNotFoundError: No module named 'grpc'
Ran 1 test in 0.000s
FAILED (errors=1)
```

## Root Cause and Corrective Action

`tests/test_h4_seen_cache.py` imported `PeerState` from `app.peer` only for two runtime-oriented
tests. That pulled in `grpc`, generated gRPC modules, and Kubernetes/runtime dependencies even
though the H4 offline analyzer needs none of them. The test now exercises synthetic event traces
through `diagnose` directly. No dependency was installed or stubbed, and production code was not
changed. Runtime lock atomicity is reported as not observable from saved logs; source inspection
shows the membership check and insertion share one lock.

The repaired test no longer imports `app.peer`, so the original `grpc` import failure is resolved.
The required pytest invocation then encountered a separate environment failure:

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest tests/test_h4_seen_cache.py -v
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python: No module named pytest
```

This is not an H4 result. The smallest proposed correction is to use the repository's established
standard-library runner, without installing packages:

```bash
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
  -m unittest tests.test_h4_seen_cache -v
```

Per the diagnostic failure rule, that fallback and the offline analysis have not yet been run.

## Unit Test Command and Result

The authorized standard-library runner resolved the test-runner boundary. After aligning the
synthetic decision field with the real `selected_peers` schema and adding same-sender coverage:

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest tests.test_h4_seen_cache -v
Ran 10 tests in 0.001s
OK
```

## Canonical Regression

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
    -m unittest tests.test_k1 tests.test_k2 tests.test_stage_h_canonical_controller -v
Ran 46 tests in 0.026s
OK
```

Production/canonical files modified: **NO**. Working-tree additions remain diagnostic tests,
scripts, documentation, and generated H3 evidence only.

## Offline Analysis Failure

Command:

```bash
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
  scripts/analyze_h4_seen_cache.py \
  outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed42_factor2.0/logs.jsonl \
  outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed43_factor2.0/logs.jsonl \
  --output outputs/k5_h4_seen_cache
```

Relevant terminal output:

```text
Traceback (most recent call last):
  File "scripts/analyze_h4_seen_cache.py", line 150, in <module>
    main()
  File "scripts/analyze_h4_seen_cache.py", line 142, in main
    summary, violations = diagnose(load_events(args.logs))
  File "scripts/analyze_h4_seen_cache.py", line 21, in load_events
    row = json.loads(line)
json.decoder.JSONDecodeError: Extra data: line 1 column 345 (char 344)
```

Likely cause: at least one saved log physical line contains additional content after a complete
JSON object, consistent with concatenated concurrent log records. The loader currently requires
exactly one JSON object per line. The smallest proposed correction is confined to the H4 loader:
use `json.JSONDecoder.raw_decode` repeatedly across each physical line, reject any non-whitespace
residue, and retain source line/object indices for auditability. No event fields or scientific
interpretation would change. Per the failure rule, this correction has not yet been applied and
no H4 scientific verdict has been issued.

## Concatenated-Record Repair and Filesystem Stop

The H4-only loader was updated to repeatedly apply `JSONDecoder.raw_decode`, retain physical line
and object indices, and reject non-object events. A synthetic concatenated-record case was added.

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
    -m unittest tests.test_h4_seen_cache -v
Ran 11 tests in 0.002s
OK
```

The analyzer then parsed and diagnosed the input but could not create the required output directory
because the current Codex filesystem sandbox does not grant writes to the project repository:

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
    scripts/analyze_h4_seen_cache.py \
    outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed42_factor2.0/logs.jsonl \
    outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed43_factor2.0/logs.jsonl \
    --output outputs/k5_h4_seen_cache
PermissionError: [Errno 1] Operation not permitted: 'outputs/k5_h4_seen_cache'
```

This is not an H4 scientific result. The smallest proposed correction is to rerun the same analyzer
command with explicit permission to write only the required project output directory. Per the
failure rule, no retry or verdict was performed in this turn.

## Permission Resolution and New Validation Stop

Filesystem inspection:

```text
$ pwd
/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
$ ls -ld .
drwxr-xr-x@ ... .
$ ls -ld outputs
drwxr-xr-x@ ... outputs
$ test -w outputs
outputs not shell-writable
```

The analyzer was rerun with narrow explicit sandbox permission for its existing command and output
directory. The permission issue is **RESOLVED**, and it wrote the H4 output files. The analyzer then
exited 1 because its scientific violation gate found:

```json
{
  "runs": 2,
  "messages": 40,
  "total_receive_events": 980,
  "peer_message_first_receipts": 589,
  "duplicate_receipts": 391,
  "multipath_duplicate_receipts": 381,
  "same_sender_duplicate_receipts": 0,
  "duplicate_acks": 391,
  "unmatched_duplicate_acks": 0,
  "unmatched_duplicate_receipts": 0,
  "forwarding_decisions": 0,
  "repeated_message_sender_destination_decisions": 0,
  "duplicate_without_prior_new": 10,
  "duplicate_triggered_refanout": 0,
  "unexplained_duplicate_events": 10,
  "violations": 599,
  "verdict": "H4 INCONCLUSIVE"
}
```

The immediate schema cause is known: real `ahbn_forwarding_decision` events identify their peer with
`sender`, not `peer_id`, but the analyzer's shared identity precheck currently requires `peer_id`
before its event-specific branch. This explains the impossible combination of 589 known H3
decisions and zero H4 decisions, and likely accounts for 589 of 599 violations. The smallest
correction is H4-only: validate event-specific identity (`sender` for decision events, `peer_id` for
receive/ACK events), add a real-schema synthetic test, and rerun validation. The remaining ten
duplicate-order anomalies must then be inspected rather than assumed to be cache faults. Per the
failure rule, no correction or scientific verdict was made in this turn.

## Output Path Correction

All new H4 references were corrected from `output/` to the project-standard `outputs/`.

## Event-Specific Schema Fix and Final Validation

Actual log schemas use `sender` for `ahbn_forwarding_decision`, `peer_id` plus `src_peer` for
`received_new`/`received_duplicate`, and `peer_id` plus `dst_peer` for `forward` and
`forward_duplicate_ack`. The analyzer now validates identity per event. A real-schema test proves
that a decision with `sender` and no `peer_id` is accepted and counted.

```text
$ /Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python \
    -m unittest tests.test_h4_seen_cache -v
Ran 13 tests in 0.002s
OK
```

Canonical production files modified: **NO**. Canonical regression remains **46/46 PASS**.

## Remaining Ten Duplicate-Before-NEW Cases

All ten are `PARSER_OR_ORDERING` runtime log-order observations, not cache loss. They occur at
overloaded peer 4 in seed 42. The runtime inserts the ID into `seen_messages` under the lock,
releases the lock, sleeps for the 1.4-second overload, and only then logs `received_new`. A second
path can therefore correctly observe SEEN and log a duplicate before the delayed NEW log.

| messages | duplicate sender(s) | receiver | NEW-log delay after DUP | classification |
|---|---|---:|---:|---|
| m3–m7 | 12 | 4 | 1.394–1.395 s | `PARSER_OR_ORDERING` |
| m12 | 13 | 4 | 1.378 s | `PARSER_OR_ORDERING` |
| m13–m16 | 18 | 4 | 1.380–1.386 s | `PARSER_OR_ORDERING` |

The complete table is `outputs/k5_h4_seen_cache/h4_ordering_cases.csv`.

Two initially apparent post-duplicate decisions were also concurrency ordering: the original NEW
handler emitted its first and only decision after a duplicate handler logged. A duplicate-triggered
refanout now conservatively requires an additional decision after an established first decision.
Neither case qualifies.

## Corrected Offline Analysis

Inputs:

- `outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed42_factor2.0/logs.jsonl`
- `outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed43_factor2.0/logs.jsonl`

Outputs:

- `outputs/k5_h4_seen_cache/h4_summary.json`
- `outputs/k5_h4_seen_cache/h4_summary.txt`
- `outputs/k5_h4_seen_cache/h4_cache_violations.csv`
- `outputs/k5_h4_seen_cache/h4_ordering_cases.csv`

| measure | result |
|---|---:|
| runs / messages | 2 / 40 |
| total receive events | 980 |
| first/new receives | 589 |
| duplicate receives | 391 |
| unique first-receipt `(run,message,receiver)` pairs | 589 |
| distinct repeated `(run,message,receiver)` pairs | 177 |
| different-sender/multipath duplicate arrivals | 391 |
| same-sender duplicate arrivals | 0 |
| duplicate ACKs | 391 |
| unmatched ACKs / unmatched duplicate receipts | 0 / 0 |
| forwarding decisions | 589 |
| repeated `(run,message,sender,destination)` decisions | 0 |
| duplicate without any NEW in the run | 0 |
| duplicate before delayed NEW log | 10, all explained |
| duplicate-triggered refanout | 0 |
| unexplained duplicates / analyzer violations | 0 / 0 |

True simultaneous-execution atomicity is **NOT OBSERVABLE FROM CURRENT LOGS**; source inspection
shows lookup and insertion share one lock, and logs contain zero multiple first receipts. No
within-run cache-lifetime loss is observable; cross-process state is not logged. K5 run isolation
is supplied by pod recreation.

## Visualization

```text
                 message M
                    |
          +---------+---------+
          |                   |
       sender A            sender B
          |                   |
          +---------+---------+
                    |
                    v
                receiver C
                    |
          first path: cache M + NEW
                    |
          second path: M is SEEN
                    |
                    v
              DUP + ACK, no refanout
```

## Relation to `z = -d+l+u+c`

```text
 d_hat   l_hat   u_hat   c_hat
    \       |       |       /
             v
       z = -d+l+u+c
             |
             v
       mode + fanout
             |
             v
      forwarding graph
             |
             v
       paths converge
             |
             v
       receiver seen/cache
          /          \
        NEW          DUP -> ACK, no refanout
```

H4 is the receiver-side bottom layer. A correctly suppressed duplicate does not imply an incorrect
score, mode, threshold, or fanout mapping.

## H4 Verdict

**H4 NOT SUPPORTED.** All 391 duplicates have a valid same-run cache insertion, all are
different-sender multipath arrivals, all reconcile to duplicate ACKs, and none trigger refanout.
The ten superficially out-of-order records reflect cache insertion before overload delay and NEW
logging, not seen-state loss.

## Next

H4 is complete for these factor-2.0 traces. The metric reconciles exactly to runtime duplicate
receipts and ACKs, so this evidence does not justify starting H5 as a metric-artefact investigation.
No Docker image or GKE rerun is required.
