#!/usr/bin/env python3
"""Independent K4.7 reconstruction from raw JSONL runtime events."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


CONTROL_EVENTS = {
    "failure_triggered", "leave", "rejoin", "controller_update",
    "ahbn_controller_trace", "maintenance_start", "maintenance_end",
    "dcsoc_maintenance", "role_assignment", "recluster",
    "overload_applied", "overload_cleared",
}


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"FAIL malformed JSONL line {number}: {exc}") from exc
        if not isinstance(value, dict):
            raise SystemExit(f"FAIL non-object JSONL line {number}")
        rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--message-id", required=True)
    parser.add_argument("--expected-nodes", type=int, required=True)
    parser.add_argument("--delay-tolerance", type=float, default=1e-12)
    args = parser.parse_args()

    rows = load_jsonl(args.log)
    selected = [r for r in rows if r.get("message_id") == args.message_id]
    foreign = [r for r in selected if r.get("message_id") != args.message_id]
    injected = [r for r in selected if r.get("event") == "message_injected"]
    received = [r for r in selected if r.get("event") == "received_new"]
    duplicates = [r for r in selected if r.get("event") == "received_duplicate"]
    forwards = [r for r in selected if r.get("event") == "forward"]
    rejected = [r for r in selected if r.get("event") in {"forward_rejected", "forward_failed"}]

    if len(injected) != 1 or not received:
        raise SystemExit("FAIL expected exactly one injection and at least one received_new")
    if foreign:
        raise SystemExit("FAIL unstable message identity")

    unique_peers = sorted({int(r["peer_id"]) for r in received})
    if len(unique_peers) != len(received):
        raise SystemExit("FAIL received_new is not unique per peer")
    self_forwards = [r for r in forwards if r.get("peer_id") == r.get("dst_peer")]
    if self_forwards:
        raise SystemExit("FAIL self-forward observed")

    inject_ts = float(injected[0]["ts"])
    last_delivery_ts = max(float(r["ts"]) for r in received)
    first_delivery = min(received, key=lambda r: float(r["ts"]))
    reconstructed = {
        "delivery_ratio": len(unique_peers) / args.expected_nodes,
        "propagation_delay": last_delivery_ts - inject_ts,
        "duplicates": len(duplicates),
        "total_forwards": len(forwards),
    }

    with args.summary.open(newline="", encoding="utf-8") as handle:
        reported_row = next(csv.DictReader(handle))
    reported = {
        "delivery_ratio": float(reported_row["delivery_ratio"]),
        "propagation_delay": float(reported_row["propagation_delay"]),
        "duplicates": int(reported_row["duplicates"]),
        "total_forwards": int(reported_row["total_forwards"]),
    }

    controls = [r for r in rows if r.get("event") in CONTROL_EVENTS]
    results = {
        "delivery_ratio": math.isclose(reconstructed["delivery_ratio"], reported["delivery_ratio"], abs_tol=0.0),
        "propagation_delay": math.isclose(reconstructed["propagation_delay"], reported["propagation_delay"], rel_tol=0.0, abs_tol=args.delay_tolerance),
        "duplicates": reconstructed["duplicates"] == reported["duplicates"],
        "total_forwards": reconstructed["total_forwards"] == reported["total_forwards"],
    }

    print(f"message_id={args.message_id}")
    print(f"eligible_receivers={args.expected_nodes}")
    print(f"unique_delivered_peers={unique_peers}")
    print(f"first_delivery_peer={first_delivery['peer_id']}")
    print(f"first_delivery_ts={first_delivery['ts']}")
    print(f"injection_ts={inject_ts}")
    print(f"last_delivery_ts={last_delivery_ts}")
    print(f"duplicate_events={len(duplicates)}")
    print(f"successful_forward_events={len(forwards)}")
    print(f"rejected_forward_events={len(rejected)}")
    print(f"control_events_in_input={len(controls)}")
    for metric in ("delivery_ratio", "propagation_delay", "duplicates", "total_forwards"):
        print(f"{metric}: reconstructed={reconstructed[metric]} reported={reported[metric]} result={'PASS' if results[metric] else 'FAIL'}")
    print("FINAL PASS" if all(results.values()) else "FINAL FAIL")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
