# K5 H3 Mode-Transition Diagnostic

## Scientific question and hypothesis

Does a local Cluster↔Gossip switch cause an already-active message to acquire a second,
overlapping dissemination branch? H3 requires direct per-message evidence, not temporal
correlation between controller transitions and duplicates.

## Repository inspection and instrumentation decision

`PeerState.process_envelope` records a message in `seen_messages` before selecting targets.
Only the first receipt calls `target_peers`; a duplicate calls `adaptive_update`, logs
`received_duplicate`, and returns before target selection. `target_peers` performs one
controller update and emits `ahbn_forwarding_decision` with message, forwarding peer,
mode, score, weight, fanout, eligible peers, and selected peers. Existing `forward`,
`forward_duplicate_ack`, `received_new`, and `received_duplicate` events provide outcomes.

Therefore existing instrumented K5 logs are sufficient. Canonical source is unchanged and
no Docker image is required. Completion events can display a later current mode, but the
recipient was selected earlier; such a label is not evidence of a Mode-B branch.

## Operational definitions

- **Active transition:** two chronologically ordered recipient-selection decisions for the
  same `(run_id, message_id, forwarding_peer)` with different modes. This is stricter and
  more causally valid than a controller update between selection and RPC completion.
- **Overlap:** a recipient selected after that transition also appears in the same peer's
  pre-transition selections for the message.
- **Restarted branch:** a second Mode-B selection exists and substantially repeats the
  Mode-A recipient set. The analyzer reports the primitive overlap; this label requires
  conservative trace review.
- **Transition-linked duplicate:** an overlapping recipient subsequently returns a duplicate
  ACK to that same forwarding peer. An unrelated duplicate is not attributed to H3.
- **Group T/N:** messages with/without at least one qualifying active transition.
- **New-reach efficiency:** unique `(message_id, peer_id)` `received_new` events divided by
  send attempts (`forward`, duplicate ACK, failed, or rejected).

Under current semantics, at most one decision is expected per message and forwarding peer.
That invariant directly tests whether the hypothesized restarted local branch exists.

## Files and outputs

- `scripts/analyze_h3_mode_transitions.py`
- `tests/test_h3_mode_transitions.py`
- `output/k5_h3_mode_transition/h3_transition_events.csv`
- `output/k5_h3_mode_transition/h3_message_summary.csv`
- `output/k5_h3_mode_transition/h3_representative_traces.txt`
- `output/k5_h3_mode_transition/h3_summary.json`

## Validation

COMMAND TO RUN:

```bash
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m unittest tests.test_h3_mode_transitions -v
```

PASS requires all six deterministic cases to pass. The cases cover no transition, clean
transition, both overlap directions, unrelated duplicate, and post-completion transition.

## Offline analysis

COMMAND TO RUN (known problematic overload traces, no GKE execution):

```bash
cd /Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python scripts/analyze_h3_mode_transitions.py \
  outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed42_factor2.0/logs.jsonl \
  outputs/k5_stage3b_instrumented_smoke/runs/k5_ahbn_seed43_factor2.0/logs.jsonl \
  --output output/k5_h3_mode_transition
```

ACTUAL TERMINAL OUTPUT (2026-08-30): six unit tests passed. Offline analysis processed
40 messages, 589 forwarding decisions, and 940 send attempts. It found 0 repeated
`(run,message,peer)` decisions, 0 active transitions in either direction, 0 overlapping
post-transition recipients, and 0 transition-linked duplicates. Score/weight, mode,
fanout, unavailable-selection, and duplicate-recipient-selection violations were all 0.

All 40 messages are Group N; Group T is empty. Consequently the transition/non-transition
rate comparison is unavailable rather than evidence of equal rates. No GKE runner is needed
because the saved traces contain all causal fields and canonical control flow makes the
qualifying second selection observable if it occurs.

## PASS/FAIL checks

PASS requires parseable logs; decision uniqueness accounting; zero score/weight, mode,
fanout, unavailable-selection, and within-decision duplicate-recipient violations. Any
nonzero repeated `(run,message,peer)` decision must be inspected as an H3 candidate.

## Verdict criteria

- **H3 SUPPORTED:** Mode-B selection directly overlaps Mode-A selection and produces linked duplicates.
- **H3 PARTIALLY SUPPORTED:** direct selection overlap exists but duplicate linkage is limited.
- **H3 NOT SUPPORTED:** no second mode-specific selection exists, or transitions remain clean.
- **H3 INCONCLUSIVE:** traces lack decisions/outcomes or contain too few messages to evaluate.

No H3 correction or AHBN optimization is authorized by this diagnostic.

## Current verdict

**H3 NOT SUPPORTED** for the analyzed factor-2.0 seeds 42 and 43 traces. The canonical
receive path prevents duplicate receipts from selecting another branch, and the runtime
data contains no second per-message selection at any forwarding peer. This is a bounded
diagnostic verdict, not a claim about unobserved implementations or conditions.
