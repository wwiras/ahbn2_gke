#!/usr/bin/env python3
"""Offline K5 H4 diagnostic for exact seen-message cache semantics."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def load_events(paths: Iterable[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                offset = 0
                object_index = 0
                while offset < len(line):
                    while offset < len(line) and line[offset].isspace():
                        offset += 1
                    if offset == len(line):
                        break
                    row, offset = decoder.raw_decode(line, offset)
                    if not isinstance(row, dict):
                        raise ValueError(f"{path}:{line_no}: JSON event is not an object")
                    object_index += 1
                    row["_input"] = str(path)
                    row["_line"] = line_no
                    row["_object"] = object_index
                    events.append(row)
    return sorted(events, key=lambda row: (float(row.get("ts", 0)), row["_input"], row["_line"]))


def diagnose(events: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    first: dict[tuple[str, str, int], dict[str, Any]] = {}
    receives: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    decisions: Counter[tuple[str, str, int]] = Counter()
    duplicate_acks: Counter[tuple[str, str, int, int]] = Counter()
    duplicate_receipts: Counter[tuple[str, str, int, int]] = Counter()
    repeated_destinations = Counter()
    last_receive_kind: dict[tuple[str, str, int], str] = {}
    multipath_duplicates = 0
    same_sender_duplicates = 0
    violations: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    all_new: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        if row.get("event") == "received_new" and {"run_id", "message_id", "peer_id"} <= row.keys():
            all_new[(str(row["run_id"]), str(row["message_id"]), int(row["peer_id"]))].append(row)

    for row in events:
        event = row.get("event")
        if event not in {"received_new", "received_duplicate", "ahbn_forwarding_decision",
                         "forward_duplicate_ack"}:
            continue
        required = {"run_id", "message_id"}
        required.add("sender" if event == "ahbn_forwarding_decision" else "peer_id")
        if event == "forward_duplicate_ack":
            required.add("dst_peer")
        if not required <= row.keys():
            violations.append({"kind": "MISSING_IDENTITY",
                               "detail": f"missing={sorted(required - row.keys())} event={row}"})
            continue
        run, message = str(row["run_id"]), str(row["message_id"])
        peer = int(row["sender"] if event == "ahbn_forwarding_decision" else row["peer_id"])
        key = (run, message, peer)
        if event == "received_new":
            receives[key].append(row)
            if key in first:
                violations.append({"kind": "MULTIPLE_FIRST_RECEIPTS", "run_id": run,
                                   "message_id": message, "peer_id": peer})
            else:
                first[key] = row
            last_receive_kind[key] = "new"
        elif event == "received_duplicate":
            receives[key].append(row)
            if key not in first:
                later_new = all_new.get(key, [])
                if later_new:
                    new_row = later_new[0]
                    cases.append({"run_id": run, "message_id": message, "receiver_peer": peer,
                                  "sender_peer": int(row.get("src_peer", -1)),
                                  "duplicate_ts": row.get("ts"), "prior_new_found": False,
                                  "new_ts": new_row.get("ts"),
                                  "delta_new_minus_duplicate_s":
                                      float(new_row.get("ts", 0)) - float(row.get("ts", 0)),
                                  "classification": "PARSER_OR_ORDERING",
                                  "explanation": "cache insertion precedes overload sleep and NEW log"})
                else:
                    violations.append({"kind": "DUPLICATE_WITHOUT_PRIOR_NEW", "run_id": run,
                                       "message_id": message, "peer_id": peer})
            duplicate_receipts[(run, message, int(row.get("src_peer", -1)), peer)] += 1
            reference_new = first.get(key) or (all_new.get(key) or [None])[0]
            if reference_new:
                if int(row.get("src_peer", -1)) != int(reference_new.get("src_peer", -1)):
                    multipath_duplicates += 1
                else:
                    same_sender_duplicates += 1
            last_receive_kind[key] = "duplicate"
        elif event == "ahbn_forwarding_decision":
            decision_key = (run, message, int(row.get("sender", peer)))
            if decisions[decision_key] > 0 and last_receive_kind.get(decision_key) == "duplicate":
                violations.append({"kind": "DUPLICATE_TRIGGERED_REFANOUT", "run_id": run,
                                   "message_id": message, "peer_id": decision_key[2]})
            decisions[decision_key] += 1
            for destination in row.get("selected_peers", []):
                repeated_destinations[(run, message, decision_key[2], int(destination))] += 1
        else:
            duplicate_acks[(run, message, peer, int(row.get("dst_peer", -1)))] += 1

    for key, count in decisions.items():
        if key not in first:
            violations.append({"kind": "DECISION_WITHOUT_NEW_RECEIPT", "run_id": key[0],
                               "message_id": key[1], "peer_id": key[2]})
        if count != 1:
            violations.append({"kind": "DECISION_COUNT_NOT_ONE", "run_id": key[0],
                               "message_id": key[1], "peer_id": key[2], "count": count})

    unmatched_ack = sum((duplicate_acks - duplicate_receipts).values())
    unmatched_receipt = sum((duplicate_receipts - duplicate_acks).values())
    run_messages = defaultdict(set)
    run_peers = defaultdict(set)
    for run, message, peer in first:
        run_messages[run].add(message); run_peers[run].add(peer)
    summary = {
        "runs": len(run_messages),
        "messages": sum(len(values) for values in run_messages.values()),
        "total_receive_events": sum(len(values) for values in receives.values()),
        "peer_message_first_receipts": len(first),
        "unique_message_receiver_pairs": len(first),
        "duplicate_receipts": sum(duplicate_receipts.values()),
        "multipath_duplicate_receipts": multipath_duplicates,
        "same_sender_duplicate_receipts": same_sender_duplicates,
        "duplicate_acks": sum(duplicate_acks.values()),
        "unmatched_duplicate_acks": unmatched_ack,
        "unmatched_duplicate_receipts": unmatched_receipt,
        "forwarding_decisions": sum(decisions.values()),
        "repeated_message_sender_destination_decisions":
            sum(count - 1 for count in repeated_destinations.values() if count > 1),
        "duplicate_without_prior_new":
            sum(row["kind"] == "DUPLICATE_WITHOUT_PRIOR_NEW" for row in violations),
        "duplicate_before_delayed_new_log": len(cases),
        "duplicate_triggered_refanout":
            sum(row["kind"] == "DUPLICATE_TRIGGERED_REFANOUT" for row in violations),
        "same_message_repeated_receiver_observations": sum(duplicate_receipts.values()),
        "distinct_repeated_message_receiver_pairs":
            len({(run, message, receiver) for run, message, _sender, receiver in duplicate_receipts}),
        "seen_cache_atomicity": "NOT OBSERVABLE FROM CURRENT LOGS",
        "cache_lifetime_reset": "No within-run loss observable; cross-process state is not logged",
        "unexplained_duplicate_events":
            sum(duplicate_receipts.values()) - multipath_duplicates - same_sender_duplicates,
        "violations": len(violations),
        "cache_key_observed": "message_id (process-local); run isolation supplied by pod recreation",
        "verdict": "H4 NOT SUPPORTED" if not violations else "H4 INCONCLUSIVE",
    }
    return summary, violations, cases


def write_outputs(out: Path, summary: dict[str, Any], violations: list[dict[str, Any]],
                  cases: list[dict[str, Any]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "h4_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    fields = sorted({key for row in violations for key in row}) or ["kind"]
    with (out / "h4_cache_violations.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(violations)
    case_fields = sorted({key for row in cases for key in row}) or ["classification"]
    with (out / "h4_ordering_cases.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=case_fields); writer.writeheader(); writer.writerows(cases)
    lines = ["K5 H4 seen/cache diagnostic", "", *(f"{key}: {value}" for key, value in summary.items())]
    (out / "h4_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary, violations, cases = diagnose(load_events(args.logs))
    write_outputs(args.output, summary, violations, cases)
    print(json.dumps(summary, indent=2))
    if violations:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
