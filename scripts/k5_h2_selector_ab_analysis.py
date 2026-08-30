#!/usr/bin/env python3
"""Prepare H2 configs and aggregate the matched selector A/B diagnostic."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

SEEDS = (42, 43, 44, 45, 46)
REPETITIONS = (1, 2, 3)
TREATMENTS = ("selector_control", "seeded_uniform")
METRICS = ("delivery_ratio", "propagation_delay", "duplicates", "send_attempts",
           "total_forwards", "new_reach", "new_reach_efficiency")


def expected_selected_count(row: dict[str, Any]) -> int | None:
    """Return the persisted runtime selection budget, if it was logged.

    H2 runtime rows call the canonical controller output ``controller_fanout``.
    ``fanout_requested`` is retained as a compatible equivalent for older
    instrumented rows. Missing fanout is an unavailable diagnostic, not a
    reason to abort aggregation of the primary scientific metrics.
    """
    fanout = row.get("controller_fanout", row.get("fanout_requested"))
    eligible = row.get("eligible_neighbors")
    if fanout is None or eligible is None:
        return None
    return min(int(fanout), len(set(eligible)))


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
    return rows


def prepare_config(base: Path, out: Path, seed: int, repetition: int,
                   treatment: str) -> None:
    if seed not in SEEDS or repetition not in REPETITIONS or treatment not in TREATMENTS:
        raise ValueError("coordinate outside frozen H2 matrix")
    cfg = yaml.safe_load(base.read_text(encoding="utf-8"))
    run_id = f"k5_h2_seed{seed}_rep{repetition}_{treatment}"
    cfg["experiment"] = run_id
    cfg["topology"]["seed"] = seed
    cfg["failure"]["overloadDelayMs"] = 1400
    cfg["bottleneck"]["delayMs"] = 1400
    cfg["k5"] = {"algorithm": "ahbn", "seed": seed, "overload_factor": 2.0,
                 "overload_delay_ms": 1400}
    cfg["k5_h2"] = {"seed": seed, "repetition": repetition, "treatment": treatment}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def summarize_run(run_dir: Path, seed: int, repetition: int, treatment: str) -> dict[str, Any]:
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    events = load_jsonl(run_dir / "logs.jsonl")
    decisions = [e for e in events if e.get("event") == "ahbn_forwarding_decision"]
    if not decisions:
        raise ValueError(f"{run_dir}: no selector decisions")
    for row in decisions:
        if row.get("treatment") != treatment or int(row.get("seed")) != seed:
            raise ValueError(f"{run_dir}: treatment/seed trace mismatch")
    send_attempt_events = {"forward", "forward_duplicate_ack", "forward_failed", "forward_rejected"}
    send_attempts = sum(e.get("event") in send_attempt_events for e in events)
    injected = {str(e["message_id"]) for e in events if e.get("event") == "message_injected"}
    reached = {(str(e["message_id"]), int(e["peer_id"])) for e in events
               if e.get("event") == "received_new" and str(e.get("message_id")) in injected}
    frequencies = Counter(int(peer) for row in decisions for peer in row["selected_peers"])
    all_eligible = {int(peer) for row in decisions for peer in row["eligible_neighbors"]}
    total_selected = sum(frequencies.values())
    eligible_counts = [len(set(row["eligible_neighbors"])) for row in decisions]
    selected_counts = [len(row["selected_peers"]) for row in decisions]
    fanout_violations = 0
    fanout_unavailable_rows = 0
    unavailable_violations = 0
    duplicate_selection_violations = 0
    for row in decisions:
        eligible, selected = row["eligible_neighbors"], row["selected_peers"]
        expected = expected_selected_count(row)
        if expected is None:
            fanout_unavailable_rows += 1
        else:
            fanout_violations += len(selected) != expected
        unavailable_violations += bool(set(selected) & set(row["unavailable_neighbors"]))
        duplicate_selection_violations += len(selected) != len(set(selected))
    unique_selected = len(frequencies)
    return {
        "seed": seed, "repetition": repetition, "treatment": treatment,
        "delivery_ratio": metrics["delivery_ratio"],
        "propagation_delay": metrics["propagation_delay"],
        "duplicates": metrics["duplicates"], "send_attempts": send_attempts,
        "total_forwards": metrics["total_forwards"], "new_reach": len(reached),
        "new_reach_efficiency": len(reached) / send_attempts if send_attempts else math.nan,
        "selector_events": len(decisions), "unique_selected_peers": unique_selected,
        "mean_eligible_count": statistics.mean(eligible_counts),
        "mean_selected_count": statistics.mean(selected_counts),
        "eligible_neighbor_coverage": unique_selected / len(all_eligible) if all_eligible else 1.0,
        "selection_max_share": max(frequencies.values()) / total_selected if frequencies else 0.0,
        "repeated_selection_rate": 1 - unique_selected / total_selected if total_selected else 0.0,
        "selection_frequency_json": json.dumps(dict(sorted(frequencies.items()))),
        "fanout_violations": (fanout_violations
                              if fanout_unavailable_rows < len(decisions) else None),
        "fanout_diagnostic_unavailable_rows": fanout_unavailable_rows,
        "unavailable_selection_violations": unavailable_violations,
        "duplicate_selection_violations": duplicate_selection_violations,
    }


def stats(values: list[float]) -> dict[str, float]:
    return {"mean": statistics.mean(values),
            "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
            "median": statistics.median(values), "min": min(values), "max": max(values)}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def analyze(root: Path) -> None:
    rows = []
    for seed in SEEDS:
        for repetition in REPETITIONS:
            for treatment in TREATMENTS:
                run_dir = root / "runs" / f"seed{seed}" / f"rep{repetition}" / treatment
                rows.append(summarize_run(run_dir, seed, repetition, treatment))
    if len(rows) != 30:
        raise ValueError(f"expected 30 runs, found {len(rows)}")
    write_csv(root / "per_run_metrics.csv", rows)
    pairs = []
    for seed in SEEDS:
        for repetition in REPETITIONS:
            a = next(r for r in rows if (r["seed"], r["repetition"], r["treatment"]) ==
                     (seed, repetition, "selector_control"))
            b = next(r for r in rows if (r["seed"], r["repetition"], r["treatment"]) ==
                     (seed, repetition, "seeded_uniform"))
            pair = {"seed": seed, "repetition": repetition}
            for metric in METRICS:
                av, bv = float(a[metric]), float(b[metric])
                pair.update({f"a_{metric}": av, f"b_{metric}": bv,
                             f"delta_{metric}": bv - av,
                             f"relative_delta_pct_{metric}":
                                 (100 * (bv - av) / av) if av else math.nan})
            pairs.append(pair)
    write_csv(root / "paired_deltas.csv", pairs)
    summary = []
    for metric in METRICS:
        item: dict[str, Any] = {"metric": metric}
        for treatment, prefix in (("selector_control", "a"), ("seeded_uniform", "b")):
            values = [float(r[metric]) for r in rows if r["treatment"] == treatment]
            item.update({f"{prefix}_{key}": value for key, value in stats(values).items()})
        deltas = [float(p[f"delta_{metric}"]) for p in pairs]
        item.update({f"delta_{key}": value for key, value in stats(deltas).items()})
        item["relative_delta_pct"] = (
            100 * (item["b_mean"] - item["a_mean"]) / item["a_mean"]
            if item["a_mean"] else math.nan)
        summary.append(item)
    write_csv(root / "aggregate_summary.csv", summary)
    per_seed = []
    for seed in SEEDS:
        selected = [r for r in rows if r["seed"] == seed]
        per_seed.append({"seed": seed,
            "a_delivery": statistics.mean(r["delivery_ratio"] for r in selected if r["treatment"] == "selector_control"),
            "b_delivery": statistics.mean(r["delivery_ratio"] for r in selected if r["treatment"] == "seeded_uniform"),
            "a_efficiency": statistics.mean(r["new_reach_efficiency"] for r in selected if r["treatment"] == "selector_control"),
            "b_efficiency": statistics.mean(r["new_reach_efficiency"] for r in selected if r["treatment"] == "seeded_uniform")})
        per_seed[-1]["delivery_delta"] = per_seed[-1]["b_delivery"] - per_seed[-1]["a_delivery"]
    write_csv(root / "per_seed_summary.csv", per_seed)
    violations = sum((r["fanout_violations"] or 0) +
                     r["unavailable_selection_violations"] +
                     r["duplicate_selection_violations"] for r in rows)
    unavailable_fanout_rows = sum(r["fanout_diagnostic_unavailable_rows"] for r in rows)
    report = ["# K5 H2 Selector A/B Results", "",
              "Matched unit: seed + repetition. Descriptive diagnostic; no significance claim.", "",
              "| Metric | Control A | Candidate B | Delta B-A | Relative Delta |",
              "|---|---:|---:|---:|---:|"]
    for item in summary:
        report.append(f"| {item['metric']} | {item['a_mean']:.6g} | {item['b_mean']:.6g} | "
                      f"{item['delta_mean']:.6g} | {item['relative_delta_pct']:.3f}% |")
    report += ["", "| Seed | A Delivery | B Delivery | Delta | A Efficiency | B Efficiency |",
               "|---:|---:|---:|---:|---:|---:|"]
    for item in per_seed:
        report.append(f"| {item['seed']} | {item['a_delivery']:.6g} | {item['b_delivery']:.6g} | "
                      f"{item['delivery_delta']:.6g} | {item['a_efficiency']:.6g} | {item['b_efficiency']:.6g} |")
    report += ["", f"Selector semantic violations: {violations}",
               f"Fanout-diagnostic unavailable rows: {unavailable_fanout_rows}",
               "", "See per_run_metrics.csv for selection frequency, concentration, coverage, and repetition diagnostics."]
    (root / "comparison.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"H2 A/B analysis PASS: 30 runs, 15 matched pairs -> {root}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("config"); p.add_argument("--base", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True); p.add_argument("--seed", type=int, required=True)
    p.add_argument("--repetition", type=int, required=True); p.add_argument("--treatment", required=True)
    p = sub.add_parser("analyze"); p.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "config":
        prepare_config(args.base, args.out, args.seed, args.repetition, args.treatment)
    else:
        analyze(args.root)


if __name__ == "__main__":
    main()
