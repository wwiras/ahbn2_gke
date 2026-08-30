#!/usr/bin/env python3
"""Diagnose whether one peer selects recipients for one message in both AHBN modes."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

DECISION = "ahbn_forwarding_decision"
SEND_EVENTS = {"forward", "forward_duplicate_ack", "forward_failed", "forward_rejected"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        pending = raw.strip()
        if not pending or not pending.startswith("{"):
            continue
        while pending:
            try:
                row, end = decoder.raw_decode(pending)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: malformed JSON") from exc
            rows.append(row)
            pending = pending[end:].lstrip()
    return sorted(rows, key=lambda row: float(row.get("ts", 0.0)))


def canonical_violations(events: list[dict[str, Any]]) -> dict[str, int]:
    result = {"score_violations": 0, "mode_violations": 0, "fanout_violations": 0,
              "unavailable_peer_selected_violations": 0,
              "duplicate_recipient_selection_violations": 0}
    for row in events:
        if row.get("event") != DECISION:
            continue
        score, weight, mode = row.get("score"), row.get("weight"), row.get("mode")
        fanout = row.get("controller_fanout", row.get("fanout_requested"))
        if score is not None and weight is not None:
            # The runtime controller uses sigmoid(score).
            import math
            expected_weight = 1.0 / (1.0 + math.exp(-float(score)))
            result["score_violations"] += abs(float(weight) - expected_weight) > 1e-12
        if weight is not None and mode is not None:
            result["mode_violations"] += mode != ("gossip" if float(weight) >= .5 else "cluster")
        if score is not None and fanout is not None:
            z = float(score)
            expected = 2 if z <= -.25 else 4 if z >= .25 else 3
            result["fanout_violations"] += int(fanout) != expected
        selected = list(row.get("selected_peers", []))
        result["unavailable_peer_selected_violations"] += bool(
            set(selected) & set(row.get("unavailable_neighbors", [])))
        result["duplicate_recipient_selection_violations"] += len(selected) != len(set(selected))
    return result


def classify(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return active transition rows and per-message summaries.

    Operational definition: an active transition requires two recipient-selection
    decisions for the same (run, message, peer), with different modes.  This is the
    earliest point at which Mode B can create a new branch; completion-time mode
    labels cannot qualify because recipients were already selected under Mode A.
    """
    decisions: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    message_events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        run = str(row.get("run_id", "")); message = row.get("message_id")
        if message is None:
            continue
        message = str(message)
        message_events[(run, message)].append(row)
        if row.get("event") == DECISION:
            decisions[(run, message, int(row["sender"]))].append(row)

    transitions: list[dict[str, Any]] = []
    transition_messages: set[tuple[str, str]] = set()
    for (run, message, peer), rows in decisions.items():
        rows.sort(key=lambda row: float(row.get("ts", 0.0)))
        reached: set[int] = set()
        for previous, current in zip(rows, rows[1:]):
            reached.update(map(int, previous.get("selected_peers", [])))
            if previous.get("mode") == current.get("mode"):
                continue
            selected = set(map(int, current.get("selected_peers", [])))
            overlap = sorted(selected & reached)
            direction = f"{str(previous.get('mode')).title()}→{str(current.get('mode')).title()}"
            duplicate_dests = {int(e["dst_peer"]) for e in message_events[(run, message)]
                               if e.get("event") == "forward_duplicate_ack"
                               and int(e.get("peer_id", -1)) == peer
                               and float(e.get("ts", 0)) >= float(current.get("ts", 0))}
            linked = sorted(set(overlap) & duplicate_dests)
            transitions.append({"run_id": run, "message_id": message, "peer_id": peer,
                "transition_ts": current.get("ts"), "direction": direction,
                "pre_mode": previous.get("mode"), "post_mode": current.get("mode"),
                "post_transition_recipients": json.dumps(sorted(selected)),
                "overlapping_recipients": json.dumps(overlap),
                "overlap_count": len(overlap), "linked_duplicate_recipients": json.dumps(linked),
                "linked_duplicate_count": len(linked),
                "classification": "TRANSITION_WITH_DUPLICATE" if linked else
                    "OVERLAPPING_RECIPIENT" if overlap else "CLEAN_TRANSITION"})
            transition_messages.add((run, message))

    summaries = []
    for key, rows in sorted(message_events.items()):
        attempts = [e for e in rows if e.get("event") in SEND_EVENTS]
        unique = {(str(e.get("message_id")), int(e["peer_id"])) for e in rows
                  if e.get("event") == "received_new" and "peer_id" in e}
        duplicates = sum(e.get("event") == "received_duplicate" for e in rows)
        summaries.append({"run_id": key[0], "message_id": key[1],
            "group": "T" if key in transition_messages else "N",
            "duplicate_count": duplicates, "send_attempts": len(attempts),
            "unique_peers_reached": len(unique),
            "new_reach_efficiency": len(unique) / len(attempts) if attempts else None})
    return transitions, summaries


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def analyze(inputs: list[Path], output: Path) -> dict[str, Any]:
    events = []
    for path in inputs:
        events.extend(load_jsonl(path))
    transitions, messages = classify(events)
    output.mkdir(parents=True, exist_ok=True)
    transition_fields = ["run_id", "message_id", "peer_id", "transition_ts", "direction",
        "pre_mode", "post_mode", "post_transition_recipients", "overlapping_recipients",
        "overlap_count", "linked_duplicate_recipients", "linked_duplicate_count", "classification"]
    message_fields = ["run_id", "message_id", "group", "duplicate_count", "send_attempts",
                      "unique_peers_reached", "new_reach_efficiency"]
    write_csv(output / "h3_transition_events.csv", transitions, transition_fields)
    write_csv(output / "h3_message_summary.csv", messages, message_fields)
    invariants = canonical_violations(events)
    decision_keys = [(str(e.get("run_id", "")), str(e.get("message_id")), int(e["sender"]))
                     for e in events if e.get("event") == DECISION]
    groups = {}
    for group in ("T", "N"):
        selected = [row for row in messages if row["group"] == group]
        attempts = sum(int(row["send_attempts"]) for row in selected)
        reaches = sum(int(row["unique_peers_reached"]) for row in selected)
        groups[group] = {"message_count": len(selected),
            "duplicate_count": sum(int(row["duplicate_count"]) for row in selected),
            "duplicate_rate_per_message":
                sum(int(row["duplicate_count"]) for row in selected) / len(selected)
                if selected else None,
            "forward_attempts": attempts,
            "forward_attempts_per_message": attempts / len(selected) if selected else None,
            "unique_peers_reached": reaches,
            "unique_peers_reached_per_message": reaches / len(selected) if selected else None,
            "new_reach_efficiency": reaches / attempts if attempts else None}
    summary = {"input_files": [str(p) for p in inputs],
        "messages": len(messages), "forwarding_decisions": len(decision_keys),
        "send_attempts": sum(e.get("event") in SEND_EVENTS for e in events),
        "active_transitions": len(transitions),
        "cluster_to_gossip": sum(t["direction"] == "Cluster→Gossip" for t in transitions),
        "gossip_to_cluster": sum(t["direction"] == "Gossip→Cluster" for t in transitions),
        "overlapping_recipient_events": sum(t["overlap_count"] for t in transitions),
        "transition_linked_duplicates": sum(t["linked_duplicate_count"] for t in transitions),
        "repeated_message_peer_decisions": len(decision_keys) - len(set(decision_keys)),
        "groups": groups,
        "invariants": invariants,
        "h3_verdict": "H3 NOT SUPPORTED" if not transitions else "H3 PARTIALLY SUPPORTED"}
    (output / "h3_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    traces = [json.dumps(row, sort_keys=True) for row in transitions[:10]]
    (output / "h3_representative_traces.txt").write_text(
        "No qualifying active-message transitions.\n" if not traces else "\n".join(traces) + "\n",
        encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    missing = [path for path in args.inputs if not path.is_file()]
    if missing:
        parser.error(f"missing input(s): {missing}")
    summary = analyze(args.inputs, args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
