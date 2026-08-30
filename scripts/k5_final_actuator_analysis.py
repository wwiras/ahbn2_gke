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
TREATMENTS = ("S0", "S5")
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
    pods_path = run_dir / "pods.json"
    pods = (json.loads(pods_path.read_text(encoding="utf-8")).get("items", [])
            if pods_path.is_file() else [])
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
        ne = int(row["eligible_neighbor_count"]); z = float(row["score"])
        if z <= -0.25:
            expected = 2
        elif z < 0.25:
            expected = 3
        elif treatment == "S0" or z < 0.90:
            expected = 4
        elif z < 1.50:
            expected = 5
        else:
            expected = 6
        fanout_violations += int(row["requested_fanout"] != expected)
        fanout_violations += int(row["actual_fanout"] > min(row["requested_fanout"], ne))
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
    fanout_counts = Counter()
    z_region_counts = Counter()
    eligible_counts = Counter()
    for row in decisions:
        ne = int(row["eligible_neighbor_count"]); z = float(row["score"])
        if z <= -0.25:
            base = 2
        elif z < 0.25:
            base = 3
        elif treatment == "S0" or z < 0.90:
            base = 4
        elif z < 1.50:
            base = 5
        else:
            base = 6
        expected = base
        violations += int(row["requested_fanout"] != expected)
        violations += int(row["actual_fanout"] > min(row["requested_fanout"], ne))
        fanout_counts[int(row["requested_fanout"])] += 1
        z_region_counts[">=0.90"] += int(z >= 0.90)
        z_region_counts[">=1.50"] += int(z >= 1.50)
        eligible_counts[ne] += 1
    if violations:
        raise ValueError(f"{run_dir}: fanout semantic violations={violations}")
    send_events = {"forward", "forward_duplicate_ack", "forward_failed", "forward_rejected"}
    sends = sum(r.get("event") in send_events for r in rows)
    injected = {str(r["message_id"]) for r in rows if r.get("event") == "message_injected"}
    reached = {(str(r["message_id"]), int(r["peer_id"])) for r in rows
               if r.get("event") == "received_new" and str(r.get("message_id")) in injected}
    timestamps = [float(r["ts"]) for r in rows if r.get("ts") is not None]
    pods_path = run_dir / "pods.json"
    pods = (json.loads(pods_path.read_text(encoding="utf-8")).get("items", [])
            if pods_path.is_file() else [])
    image_ids = sorted({state.get("imageID") for pod in pods
                        for state in pod.get("status", {}).get("containerStatuses", [])
                        if state.get("imageID")})
    return {"seed": seed, "treatment": treatment,
            "run_repetition": 1, "scenario_severity": "factor=2.0;delay_ms=1400",
            "controller_version": "canonical-sha256:dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8",
            "image_digest": ";".join(image_ids), "config_override": f"actuator_treatment={treatment}",
            "start_timestamp": min(timestamps) if timestamps else None,
            "end_timestamp": max(timestamps) if timestamps else None,
            "delivery_ratio": metrics["delivery_ratio"],
            "propagation_delay": metrics["propagation_delay"],
            "duplicates": metrics["duplicates"], "send_attempts": sends,
            "total_forwards": metrics["total_forwards"], "new_reach": len(reached),
            "new_reach_efficiency": len(reached) / sends if sends else math.nan,
            **{f"k{k}_count": fanout_counts[k] for k in range(2, 7)},
            **{f"k{k}_pct": 100 * fanout_counts[k] / len(decisions) for k in range(2, 7)},
            "z_ge_0_90_count": z_region_counts[">=0.90"],
            "z_ge_0_90_pct": 100 * z_region_counts[">=0.90"] / len(decisions),
            "z_ge_1_50_count": z_region_counts[">=1.50"],
            "z_ge_1_50_pct": 100 * z_region_counts[">=1.50"] / len(decisions),
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
    write_csv(root / "per_run_results.csv", rows)
    occupancy = [{key: row[key] for key in (
        "seed", "treatment", "k2_count", "k2_pct", "k3_count", "k3_pct",
        "k4_count", "k4_pct", "k5_count", "k5_pct", "k6_count", "k6_pct",
        "z_ge_0_90_count", "z_ge_0_90_pct", "z_ge_1_50_count", "z_ge_1_50_pct")}
        for row in rows]
    write_csv(root / "actuator_occupancy.csv", occupancy)
    controller_states = []
    for seed in SEEDS:
        for treatment in TREATMENTS:
            run_dir = root / "runs" / f"seed{seed}" / treatment
            latest_trace = {}
            for event in load_jsonl(run_dir / "logs.jsonl"):
                if event.get("event") == "ahbn_controller_trace":
                    latest_trace[event.get("peer_id")] = event
                elif event.get("event") == "k5_final_actuator_decision":
                    trace = latest_trace.get(event.get("peer_id"), {})
                    controller_states.append({
                        "seed": seed, "treatment": treatment, "timestamp": event.get("ts"),
                        "peer_id": event.get("peer_id"), "message_id": event.get("message_id"),
                        "z": event.get("score"), "fanout": event.get("requested_fanout"),
                        "actual_fanout": event.get("actual_fanout"), "mode": event.get("mode"),
                        "d_hat": trace.get("d_hat"), "l_hat": trace.get("l_hat"),
                        "u_hat": trace.get("u_hat"), "c_hat": trace.get("c_hat"),
                    })
    if not controller_states:
        raise ValueError("no controller states available for controller_states.csv")
    write_csv(root / "controller_states.csv", controller_states)
    pairs = []
    for seed in SEEDS:
        a = next(r for r in rows if r["seed"] == seed and r["treatment"] == "S0")
        b = next(r for r in rows if r["seed"] == seed and r["treatment"] == "S5")
        pair = {"seed": seed}
        for metric in METRICS:
            pair[f"s0_{metric}"] = a[metric]; pair[f"s5_{metric}"] = b[metric]
            pair[f"delta_{metric}"] = float(b[metric]) - float(a[metric])
        pair["s5_k5_activations"] = b["k5_count"]
        pair["s5_k6_activations"] = b["k6_count"]
        pairs.append(pair)
    write_csv(root / "paired_results.csv", pairs)
    aggregate = []
    for metric in METRICS:
        av = [float(r[metric]) for r in rows if r["treatment"] == "S0"]
        bv = [float(r[metric]) for r in rows if r["treatment"] == "S5"]
        aggregate.append({"metric": metric,
                          "s0_mean": statistics.mean(av), "s5_mean": statistics.mean(bv),
                          "delta_s5_minus_s0": statistics.mean(bv) - statistics.mean(av),
                          "s0_median": statistics.median(av), "s5_median": statistics.median(bv),
                          "s0_min": min(av), "s5_min": min(bv),
                          "s0_max": max(av), "s5_max": max(bv),
                          "s0_stddev": statistics.stdev(av), "s5_stddev": statistics.stdev(bv)})
    write_csv(root / "aggregate_results.csv", aggregate)
    (root / "summary.json").write_text(json.dumps({
        "treatments": list(TREATMENTS), "seeds": list(SEEDS),
        "scenario": {"topology": "BA", "n": 20, "m": 2, "source": "peer-0",
                     "overload_factor": 2.0, "overload_delay_ms": 1400},
        "aggregate": aggregate,
        "classification": "PENDING_HUMAN_GATE_REVIEW",
    }, indent=2) + "\n", encoding="utf-8")
    report = ["# K5 Final Actuator GKE Result", "",
              "Matched seeds 42--46; same frozen K5 factor 2.0 scenario. No exact event replay is claimed.", "",
              "| Metric | S0 | S5 | Delta S5-S0 |", "|---|---:|---:|---:|"]
    for row in aggregate:
        report.append(f"| {row['metric']} | {row['s0_mean']:.6g} | {row['s5_mean']:.6g} | {row['delta_s5_minus_s0']:.6g} |")
    report += ["", "| Seed | S0 Delivery | S5 Delivery | Delta |",
               "|---:|---:|---:|---:|"]
    for row in pairs:
        report.append(f"| {row['seed']} | {row['s0_delivery_ratio']:.6g} | {row['s5_delivery_ratio']:.6g} | {row['delta_delivery_ratio']:.6g} |")
    report += ["", "Final classification must use the frozen gate: `A — CONFIRMED`, "
               "`B — NOT CONFIRMED`, or `C — INCONCLUSIVE`."]
    summary = root / "README.md"
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
