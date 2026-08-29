#!/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python
"""External post-processing for the temporary K5 H2 diagnostic."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


CLASSES = (
    "SELECTION_OPPORTUNITY_SIGNAL",
    "FANOUT_PRESSURE_SIGNAL",
    "MIXED",
    "NO_OMISSION",
    "INSUFFICIENT_EVIDENCE",
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"missing trace file: {path}")
    decoder = json.JSONDecoder()
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        pending = raw.strip()
        if not pending:
            continue
        while pending:
            try:
                row, end = decoder.raw_decode(pending)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: malformed JSON record") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: record is not an object")
            rows.append(row)
            pending = pending[end:].lstrip()
    return rows


def peer_list(value: Any, field: str) -> list[int]:
    if not isinstance(value, list) or any(isinstance(x, bool) or not isinstance(x, int) for x in value):
        raise ValueError(f"{field} must be a list of integer peer IDs")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} contains duplicate peer IDs")
    return value


def classify(*, omitted: int, selected: int, duplicates: int,
             nonduplicates: int, unknown: int, saturated: bool) -> tuple[str, str]:
    if min(omitted, selected, duplicates, nonduplicates, unknown) < 0:
        raise ValueError("negative classification count")
    if duplicates + nonduplicates + unknown != selected:
        raise ValueError("selected outcome counts are inconsistent")
    if omitted == 0:
        return "NO_OMISSION", "all eligible peers were selected"
    if duplicates:
        if saturated and nonduplicates and unknown == 0:
            return "MIXED", (
                f"fanout saturated with {omitted} omitted eligible peers; "
                f"observed outcomes include {duplicates} duplicate and {nonduplicates} nonduplicate"
            )
        return "SELECTION_OPPORTUNITY_SIGNAL", (
            f"{duplicates} selected peer(s) returned duplicate ACK while "
            f"{omitted} eligible peer(s) were omitted; omitted peers are not assumed unseen"
        )
    if unknown:
        return "INSUFFICIENT_EVIDENCE", (
            f"{unknown}/{selected} selected-peer outcome(s) could not be correlated"
        )
    if saturated and nonduplicates == selected:
        return "FANOUT_PRESSURE_SIGNAL", (
            f"fanout saturated; all {selected} selected outcomes were observed nonduplicate; "
            f"{omitted} eligible peer(s) remained omitted"
        )
    return "INSUFFICIENT_EVIDENCE", "available events do not establish an observational class"


def analyze_decisions(events: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    decisions = [e for e in events if e.get("event") == "ahbn_forwarding_decision"]
    outcomes: dict[tuple[str, str, int, int], list[tuple[float, str]]] = {}
    for event in events:
        kind = event.get("event")
        if kind not in {"forward", "forward_duplicate_ack", "received_new"}:
            continue
        try:
            run_id = str(event["run_id"])
            message_id = str(event["message_id"])
            timestamp = float(event["ts"])
            if kind == "received_new":
                sender, destination = int(event["src_peer"]), int(event["peer_id"])
                outcome = "nonduplicate"
            else:
                sender, destination = int(event["peer_id"]), int(event["dst_peer"])
                outcome = "duplicate" if kind == "forward_duplicate_ack" else "nonduplicate"
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed {kind} event") from exc
        key = (run_id, message_id, sender, destination)
        item = (timestamp, outcome)
        if item not in outcomes.setdefault(key, []):
            outcomes[key].append(item)

    analyzed: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, int], dict[str, Any]] = {}
    for event in sorted(decisions, key=lambda row: float(row.get("ts", 0))):
        required = {"run_id", "message_id", "sender", "incoming_sender", "mode", "score",
                    "fanout_requested", "eligible_neighbors", "selected_peers",
                    "omitted_eligible_peers", "ts"}
        missing = sorted(required.difference(event))
        if missing:
            raise ValueError(f"forwarding decision missing fields: {missing}")
        try:
            run_id, message_id = str(event["run_id"]), str(event["message_id"])
            sender, decision_ts = int(event["sender"]), float(event["ts"])
            requested = int(event["fanout_requested"])
        except (TypeError, ValueError) as exc:
            raise ValueError("malformed forwarding decision scalar") from exc
        decision_key = (run_id, message_id, sender)
        if decision_key in seen:
            if event != seen[decision_key]:
                raise ValueError(f"conflicting duplicate decision: {decision_key}")
            continue
        seen[decision_key] = event
        eligible = peer_list(event["eligible_neighbors"], "eligible_neighbors")
        selected = peer_list(event["selected_peers"], "selected_peers")
        omitted = peer_list(event["omitted_eligible_peers"], "omitted_eligible_peers")
        if not set(selected).issubset(eligible):
            raise ValueError(f"{decision_key}: selected peer is not eligible")
        expected_omitted = [peer for peer in eligible if peer not in set(selected)]
        if omitted != expected_omitted:
            raise ValueError(f"{decision_key}: omitted peer list is inconsistent")
        if requested not in (2, 3, 4):
            raise ValueError(f"{decision_key}: noncanonical fanout {requested}")

        duplicate_count = nonduplicate_count = unknown_count = 0
        for destination in selected:
            observed = {outcome for timestamp, outcome in outcomes.get(
                (run_id, message_id, sender, destination), []
            ) if timestamp >= decision_ts}
            if observed == {"duplicate"}:
                duplicate_count += 1
            elif observed == {"nonduplicate"}:
                nonduplicate_count += 1
            else:
                unknown_count += 1
        saturated = len(selected) == min(requested, len(eligible))
        classification, evidence = classify(
            omitted=len(omitted), selected=len(selected), duplicates=duplicate_count,
            nonduplicates=nonduplicate_count, unknown=unknown_count, saturated=saturated,
        )
        analyzed.append({
            "seed": seed,
            "run_id": run_id,
            "decision_ts": decision_ts,
            "message_id": message_id,
            "forwarding_peer": sender,
            "incoming_sender": int(event["incoming_sender"]),
            "mode": event["mode"],
            "score": event["score"],
            "fanout_requested": requested,
            "eligible_count": len(eligible),
            "eligible_peers": compact(eligible),
            "selected_count": len(selected),
            "selected_peers": compact(selected),
            "omitted_eligible_count": len(omitted),
            "omitted_eligible_peers": compact(omitted),
            "selected_duplicate_count": duplicate_count,
            "selected_nonduplicate_observed_count": nonduplicate_count,
            "selected_unknown_count": unknown_count,
            "fanout_saturated": saturated,
            "duplicate_with_omitted_eligible": bool(duplicate_count and omitted),
            "classification": classification,
            "classification_evidence": evidence,
        })
    return analyzed


def compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def summarize(seed: int, decisions: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["classification"] for row in decisions)
    messages = {str(e["message_id"]) for e in events if e.get("event") == "message_injected"}
    reached = {(str(e["message_id"]), int(e["peer_id"])) for e in events
               if e.get("event") == "received_new" and "message_id" in e and "peer_id" in e}
    expected = len(messages) * 20
    summary: dict[str, Any] = {
        "seed": seed,
        "forwarding_decisions": len(decisions),
        "LOW_decisions": sum(row["fanout_requested"] == 2 for row in decisions),
        "MODERATE_decisions": sum(row["fanout_requested"] == 3 for row in decisions),
        "HIGH_decisions": sum(row["fanout_requested"] == 4 for row in decisions),
        "HIGH_forwarding_decisions": sum(row["fanout_requested"] == 4 for row in decisions),
        "mean_eligible_count": mean(row["eligible_count"] for row in decisions),
        "mean_selected_count": mean(row["selected_count"] for row in decisions),
        "mean_omitted_eligible_count": mean(row["omitted_eligible_count"] for row in decisions),
        "selected_duplicate_outcomes": sum(row["selected_duplicate_count"] for row in decisions),
        "delivery": ratio(len(reached), expected),
        "duplicates": sum(e.get("event") == "received_duplicate" for e in events),
        "send_attempts": sum(e.get("event") in {
            "forward", "forward_duplicate_ack", "forward_failed", "forward_rejected"
        } for e in events),
        "never_reached": expected - len(reached),
    }
    for name in CLASSES:
        summary[f"{name}_count"] = counts[name]
        summary[f"{name}_pct"] = ratio(100 * counts[name], len(decisions))
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Iterable[str] | None = None) -> None:
    names = list(fields or (rows[0].keys() if rows else []))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def analyze_root(root: Path) -> None:
    all_decisions: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for seed in (42, 44):
        seed_dir = root / f"seed{seed}"
        events = load_jsonl(seed_dir / "raw" / "logs.jsonl")
        decisions = analyze_decisions(events, seed)
        if not decisions:
            raise ValueError(f"seed {seed}: no ahbn_forwarding_decision events")
        summary = summarize(seed, decisions, events)
        (seed_dir / "run_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        all_decisions.extend(decisions)
        summaries.append(summary)
    write_csv(root / "per_decision.csv", all_decisions)
    write_csv(root / "per_seed_summary.csv", summaries)
    aggregate = []
    for scope, rows in (("ALL", all_decisions),
                        ("HIGH", [r for r in all_decisions if r["fanout_requested"] == 4])):
        counts = Counter(row["classification"] for row in rows)
        aggregate.append({"scope": scope, "decisions": len(rows), **{
            f"{name}_count": counts[name] for name in CLASSES
        }})
    write_csv(root / "h1_h2_summary.csv", aggregate)
    write_comparison(root / "comparison.md", aggregate)
    print(f"H2 analysis complete: {root}")


def write_comparison(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# K5 H2 observational comparison", "",
        "This two-seed diagnostic validates instrumentation and provides directional signals only.",
        "Eligible does not mean definitely unseen; duplicate outcomes do not prove predictably bad selection.", "",
        "| Scope | Decisions | Opportunity | Pressure | Mixed | No omission | Insufficient |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['scope']} | {row['decisions']} | "
            f"{row['SELECTION_OPPORTUNITY_SIGNAL_count']} | {row['FANOUT_PRESSURE_SIGNAL_count']} | "
            f"{row['MIXED_count']} | {row['NO_OMISSION_count']} | "
            f"{row['INSUFFICIENT_EVIDENCE_count']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    try:
        analyze_root(args.root)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
