#!/usr/bin/env python3
"""Config preparation, run validation, and matched analysis for final K5 A/B."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import yaml

SEEDS = (42, 43, 44, 45, 46)
TREATMENTS = ("S0", "S5-C6")
METRICS = ("delivery_ratio", "propagation_delay", "duplicates", "send_attempts",
           "total_forwards", "new_reach", "new_reach_efficiency")
MANDATORY_RUN_FILES = ("topology.json", "logs.jsonl", "pods.json", "controller.log")


def load_jsonl(path: Path) -> list[dict]:
    decoder = json.JSONDecoder(); rows = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        pending = raw.strip()
        if not pending or not pending.startswith("{"):
            continue
        while pending:
            try:
                row, end = decoder.raw_decode(pending)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: malformed JSON") from exc
            rows.append(row); pending = pending[end:].lstrip()
    return rows


def prepare(base: Path, out: Path, seed: int, treatment: str) -> None:
    if seed not in SEEDS or treatment not in TREATMENTS:
        raise ValueError("coordinate outside frozen final K5 matrix")
    cfg = yaml.safe_load(base.read_text(encoding="utf-8"))
    run_id = f"k5_final_actuator_seed{seed}_{treatment.lower().replace('-', '')}"
    cfg["experiment"] = run_id
    cfg["topology"]["seed"] = seed
    cfg["failure"]["overloadDelayMs"] = 1400
    cfg["bottleneck"]["delayMs"] = 1400
    cfg["k5"] = {"algorithm": "ahbn", "seed": seed, "overload_factor": 2.0,
                 "overload_delay_ms": 1400}
    cfg["k5_h2"] = {"seed": seed, "treatment": "selector_control",
                     "actuator_treatment": treatment}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def validate_final_run(run_dir: Path, seed: int, treatment: str,
                       write_metrics: bool = True) -> dict:
    """Validate the authoritative final-actuator artifact contract.

    Final pod health is recorded by ``run_experiment.sh`` in ``pods.json``.
    The legacy Exp08-only ``statuses.jsonl`` RPC snapshot is not part of this
    runner's collection path and is intentionally not synthesized.
    """
    missing = [name for name in MANDATORY_RUN_FILES if not (run_dir / name).is_file()]
    if missing:
        raise ValueError(f"{run_dir}: mandatory final-run artifacts missing: {missing}")
    topo = json.loads((run_dir / "topology.json").read_text(encoding="utf-8"))
    expected_run_id = f"k5_final_actuator_seed{seed}_{treatment.lower().replace('-', '')}"
    if (topo.get("run_id") != expected_run_id or topo.get("strategy") != "ahbn"
            or topo.get("k5", {}).get("seed") != seed
            or topo.get("k5", {}).get("overload_factor") != 2.0
            or topo.get("k5_h2", {}).get("actuator_treatment") != treatment):
        raise ValueError(f"{run_dir}: frozen coordinate/topology contract mismatch")
    rows = load_jsonl(run_dir / "logs.jsonl")
    events = Counter(row.get("event") for row in rows)
    if events["message_injected"] != 20 or events["overload_target_selected"] != 1 or events["overload_applied"] != 1:
        raise ValueError(f"{run_dir}: workload/overload event counts invalid: {dict(events)}")
    if events["run_finished"] != 1:
        raise ValueError(f"{run_dir}: controller completion evidence invalid: run_finished={events['run_finished']}")
    controller_rows = load_jsonl(run_dir / "controller.log")
    if sum(row.get("event") == "run_finished" for row in controller_rows) != 1:
        raise ValueError(f"{run_dir}: controller.log lacks exactly one run_finished")
    bad = {"peer_failed", "failure_triggered", "churn_triggered", "pod_delete_requested"}
    observed_bad = bad.intersection(events)
    if observed_bad:
        raise ValueError(f"{run_dir}: forbidden failure/churn events: {sorted(observed_bad)}")
    pods = json.loads((run_dir / "pods.json").read_text(encoding="utf-8")).get("items", [])
    unhealthy = []
    for pod in pods:
        states = pod.get("status", {}).get("containerStatuses", [])
        if (pod.get("status", {}).get("phase") != "Running" or len(states) != 1
                or not states[0].get("ready") or states[0].get("restartCount", 0) != 0):
            unhealthy.append(pod.get("metadata", {}).get("name", "<unknown>"))
    if len(pods) != 20 or unhealthy:
        raise ValueError(f"{run_dir}: final pod health invalid: count={len(pods)} unhealthy={unhealthy}")
    traces = [row for row in rows if row.get("event") == "ahbn_controller_trace"]
    decisions = [row for row in rows if row.get("event") == "k5_final_actuator_decision"]
    if not traces or not decisions:
        raise ValueError(f"{run_dir}: missing controller/actuator traces")
    trace_violations = 0
    for row in traces:
        parts = sum(float(row[name]) for name in (
            "duplication_score_contribution", "latency_score_contribution",
            "utilization_score_contribution", "churn_score_contribution"))
        trace_violations += not math.isclose(float(row["score"]), parts, abs_tol=1e-12)
        trace_violations += row["mode"] != ("gossip" if float(row["weight"]) >= 0.5 else "cluster")
    fanout_violations = 0
    for row in decisions:
        if row.get("treatment") != treatment:
            fanout_violations += 1; continue
        ne = int(row["eligible_neighbor_count"]); state = row["actuator_state"]
        if treatment == "S0":
            expected = min({"LOW": 2, "MODERATE": 3, "HIGH": 4}[state], ne)
        else:
            expected = min({"LOW": (ne + 2) // 3,
                            "MODERATE": (2 * ne + 2) // 3, "HIGH": ne}[state], 6, ne)
        fanout_violations += int(row["requested_fanout"] != expected)
        fanout_violations += int(row["actual_fanout"] > row["requested_fanout"])
    if trace_violations or fanout_violations:
        raise ValueError(f"{run_dir}: semantic violations: controller={trace_violations} fanout={fanout_violations}")
    injected = [row for row in rows if row.get("event") == "message_injected"]
    received = [row for row in rows if row.get("event") == "received_new"]
    duplicates = [row for row in rows if row.get("event") == "received_duplicate"]
    forwards = [row for row in rows if row.get("event") == "forward"]
    message_ids = {row["message_id"] for row in injected}
    delivered = {(row.get("message_id"), int(row["peer_id"])) for row in received
                 if row.get("message_id") in message_ids}
    delays = []
    for message_id in sorted(message_ids):
        t0 = min(row["ts"] for row in injected if row["message_id"] == message_id)
        arrivals = [row["ts"] for row in received if row.get("message_id") == message_id]
        if arrivals:
            delays.append(max(arrivals) - t0)
    metrics = {"run_id": expected_run_id, "algorithm": "ahbn", "strategy": "ahbn",
               "seed": seed, "overload_factor": 2.0, "overload_delay_ms": 1400,
               "delivery_ratio": len(delivered) / 400,
               "propagation_delay": statistics.mean(delays),
               "duplicates": len(duplicates), "total_forwards": len(forwards),
               "dcsoc_maintenance": 0, "ahbn_trace_rows": len(traces)}
    if write_metrics:
        (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**metrics, "validation": "PASS", "treatment": treatment}, sort_keys=True))
    return metrics


def summarize(run_dir: Path, seed: int, treatment: str) -> dict:
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    rows = load_jsonl(run_dir / "logs.jsonl")
    decisions = [r for r in rows if r.get("event") == "k5_final_actuator_decision"]
    if not decisions:
        raise ValueError(f"{run_dir}: missing actuator decisions")
    if any(r.get("treatment") != treatment for r in decisions):
        raise ValueError(f"{run_dir}: unexpected treatment trace")
    violations = 0
    state_counts = Counter()
    eligible_counts = Counter()
    for row in decisions:
        ne = int(row["eligible_neighbor_count"]); state = row["actuator_state"]
        if treatment == "S0":
            expected = min({"LOW": 2, "MODERATE": 3, "HIGH": 4}[state], ne)
        else:
            base = {"LOW": (ne + 2) // 3, "MODERATE": (2 * ne + 2) // 3,
                    "HIGH": ne}[state]
            expected = min(base, 6, ne)
        violations += int(row["requested_fanout"] != expected)
        violations += int(row["actual_fanout"] > row["requested_fanout"])
        state_counts[state] += 1; eligible_counts[ne] += 1
    if violations:
        raise ValueError(f"{run_dir}: fanout semantic violations={violations}")
    send_events = {"forward", "forward_duplicate_ack", "forward_failed", "forward_rejected"}
    sends = sum(r.get("event") in send_events for r in rows)
    injected = {str(r["message_id"]) for r in rows if r.get("event") == "message_injected"}
    reached = {(str(r["message_id"]), int(r["peer_id"])) for r in rows
               if r.get("event") == "received_new" and str(r.get("message_id")) in injected}
    return {"seed": seed, "treatment": treatment,
            "delivery_ratio": metrics["delivery_ratio"],
            "propagation_delay": metrics["propagation_delay"],
            "duplicates": metrics["duplicates"], "send_attempts": sends,
            "total_forwards": metrics["total_forwards"], "new_reach": len(reached),
            "new_reach_efficiency": len(reached) / sends if sends else math.nan,
            "low_count": state_counts["LOW"], "moderate_count": state_counts["MODERATE"],
            "high_count": state_counts["HIGH"],
            "eligible_counts_json": json.dumps(dict(sorted(eligible_counts.items()))),
            "mean_requested_fanout": statistics.mean(r["requested_fanout"] for r in decisions),
            "mean_actual_fanout": statistics.mean(r["actual_fanout"] for r in decisions)}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def analyze(root: Path) -> None:
    rows = [summarize(root / "runs" / f"seed{seed}" / treatment, seed, treatment)
            for seed in SEEDS for treatment in TREATMENTS]
    write_csv(root / "results" / "per_run.csv", rows)
    pairs = []
    for seed in SEEDS:
        a = next(r for r in rows if r["seed"] == seed and r["treatment"] == "S0")
        b = next(r for r in rows if r["seed"] == seed and r["treatment"] == "S5-C6")
        pair = {"seed": seed}
        for metric in METRICS:
            pair[f"s0_{metric}"] = a[metric]; pair[f"s5_c6_{metric}"] = b[metric]
            pair[f"delta_{metric}"] = float(b[metric]) - float(a[metric])
        pairs.append(pair)
    write_csv(root / "results" / "per_seed_paired.csv", pairs)
    aggregate = []
    for metric in METRICS:
        av = [float(r[metric]) for r in rows if r["treatment"] == "S0"]
        bv = [float(r[metric]) for r in rows if r["treatment"] == "S5-C6"]
        aggregate.append({"metric": metric, "s0_mean": statistics.mean(av),
                          "s5_c6_mean": statistics.mean(bv),
                          "delta_s5_c6_minus_s0": statistics.mean(bv) - statistics.mean(av)})
    write_csv(root / "results" / "aggregate.csv", aggregate)
    report = ["# K5 Final Actuator GKE Result", "",
              "Matched seeds 42--46; same frozen K5 factor 2.0 scenario. No exact event replay is claimed.", "",
              "| Metric | S0 | S5-C6 | Delta C6-S0 |", "|---|---:|---:|---:|"]
    for row in aggregate:
        report.append(f"| {row['metric']} | {row['s0_mean']:.6g} | {row['s5_c6_mean']:.6g} | {row['delta_s5_c6_minus_s0']:.6g} |")
    report += ["", "| Seed | S0 Delivery | C6 Delivery | Delta |",
               "|---:|---:|---:|---:|"]
    for row in pairs:
        report.append(f"| {row['seed']} | {row['s0_delivery_ratio']:.6g} | {row['s5_c6_delivery_ratio']:.6g} | {row['delta_delivery_ratio']:.6g} |")
    report += ["", "Final classification pending conservative human interpretation:",
               "`A. CLEAR S5-C6 WIN` or `B. NO CLEAR S5-C6 WIN`."]
    summary = root / "summary" / "comparison.md"; summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"FINAL K5 analysis PASS: 10 runs, 5 matched seeds -> {root}")


def main() -> None:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("config"); p.add_argument("--base", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True); p.add_argument("--seed", type=int, required=True)
    p.add_argument("--treatment", required=True)
    p = sub.add_parser("analyze"); p.add_argument("--root", type=Path, required=True)
    p = sub.add_parser("validate-run"); p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True); p.add_argument("--treatment", required=True)
    args = parser.parse_args()
    if args.command == "config":
        prepare(args.base, args.out, args.seed, args.treatment)
    elif args.command == "validate-run":
        validate_final_run(args.run_dir, args.seed, args.treatment)
    else:
        analyze(args.root)


if __name__ == "__main__":
    main()
