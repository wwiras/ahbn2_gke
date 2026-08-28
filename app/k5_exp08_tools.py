from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import yaml


ALGORITHMS = ("gossip", "structured", "dcsoc", "ahbn")
STRATEGIES = {"gossip": "gossip", "structured": "cluster", "dcsoc": "dcsoc", "ahbn": "ahbn"}
SEEDS = (42, 43, 44, 45, 46)
FACTORS = (1.0, 1.5, 2.0, 3.0)
DELAYS = {1.0: 700, 1.5: 1050, 2.0: 1400, 3.0: 2100}
T_CRIT_DF4 = 2.7764451051977987


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    decoder = json.JSONDecoder()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.startswith("{"):
            continue
        pending = line
        decoded = []
        try:
            while pending.strip():
                value, end = decoder.raw_decode(pending.lstrip())
                if not isinstance(value, dict):
                    raise ValueError("expected JSON object")
                decoded.append(value)
                pending = pending.lstrip()[end:]
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL record") from exc
        rows.extend(decoded)
    return rows


def write_config(base: Path, out: Path, algorithm: str, seed: int, factor: float) -> None:
    if algorithm not in ALGORITHMS or seed not in SEEDS or factor not in FACTORS:
        raise SystemExit("invalid frozen K5 coordinate")
    cfg = yaml.safe_load(base.read_text(encoding="utf-8"))
    delay = DELAYS[factor]
    run_id = f"k5_{algorithm}_seed{seed}_factor{factor:.1f}"
    cfg["experiment"] = run_id
    cfg["topology"]["seed"] = seed
    cfg["failure"]["overloadDelayMs"] = delay
    cfg["bottleneck"]["delayMs"] = delay
    cfg["k5"] = {"algorithm": algorithm, "seed": seed,
                 "overload_factor": factor, "overload_delay_ms": delay}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    print(run_id)


def validate_contract(paths: list[Path]) -> None:
    observed = []
    for path in paths:
        topo = json.loads(path.read_text(encoding="utf-8"))
        k5 = topo["k5"]
        algorithm = k5["algorithm"]
        checks = {
            "strategy": topo["strategy"] == STRATEGIES[algorithm],
            "BA(m=2)": topo["topology_type"] == "ba" and topo["ba_m"] == 2,
            "N=20": topo["num_nodes"] == 20,
            "source=0": topo["message_source"] == 0,
            "trigger=0.5": topo["failure"]["trigger_time"] == 0.5,
            "workload=20x0.4": topo["workload"] == {"message_count": 20, "message_interval": 0.4},
            "settle=18": topo["settle_time"] == 18.0,
            "one-important-peer": topo["bottleneck"]["target"] == "important_peer",
            "SLOW-not-failure": topo["failure"]["mode"] == "bottleneck",
            "canonical-AHBN-metadata": topo["ahbn"] == {
                "mode_threshold": 0.5, "min_fanout": 2,
                "max_fanout": 4, "default_fanout": 3},
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise SystemExit(f"{path}: contract FAIL: {failed}")
        if algorithm == "dcsoc" and not topo["dcsoc"]["structural_edges"]:
            raise SystemExit(f"{path}: DC-SoC structure absent")
        observed.append(algorithm)
        print(f"{algorithm}: K5 shared contract PASS")
    if observed != list(ALGORITHMS):
        raise SystemExit(f"comparator order mismatch: {observed}")
    print(f"algorithms={','.join(ALGORITHMS)}")
    print(f"seeds={','.join(map(str, SEEDS))}")
    print("factors=" + ",".join(f"{x:.1f}" for x in FACTORS))
    print("delays=" + ",".join(str(DELAYS[x]) for x in FACTORS))
    print("expected_runs=80")


def validate_run(run_dir: Path) -> dict:
    topo = json.loads((run_dir / "topology.json").read_text(encoding="utf-8"))
    rows = load_jsonl(run_dir / "logs.jsonl")
    k5 = topo["k5"]
    run_id = topo["run_id"]
    events = [row.get("event") for row in rows]
    injected = [row for row in rows if row.get("event") == "message_injected"]
    received = [row for row in rows if row.get("event") == "received_new"]
    duplicates = [row for row in rows if row.get("event") == "received_duplicate"]
    forwards = [row for row in rows if row.get("event") == "forward"]
    targets = [row for row in rows if row.get("event") == "overload_target_selected"]
    applied = [row for row in rows if row.get("event") == "overload_applied"]
    statuses = load_jsonl(run_dir / "statuses.jsonl")
    pods = json.loads((run_dir / "pods.json").read_text(encoding="utf-8")).get("items", [])
    bad_events = {"peer_failed", "failure_triggered", "churn_triggered", "pod_delete_requested"}
    if len(injected) != 20 or len(targets) != 1 or len(applied) != 1:
        raise SystemExit(f"{run_id}: injection/target/overload count FAIL: {len(injected)}/{len(targets)}/{len(applied)}")
    if applied[0].get("peer_id") != targets[0].get("peer_id") or applied[0].get("overload_ms") != k5["overload_delay_ms"]:
        raise SystemExit(f"{run_id}: overload target/value mismatch")
    if bad_events.intersection(events):
        raise SystemExit(f"{run_id}: failure/churn event present: {bad_events.intersection(events)}")
    if len(statuses) != 20 or any(not x.get("ready") or not x.get("alive") for x in statuses):
        raise SystemExit(f"{run_id}: peer liveness FAIL")
    if len(pods) != 20:
        raise SystemExit(f"{run_id}: peer pod count={len(pods)}, expected 20")
    for pod in pods:
        states = pod.get("status", {}).get("containerStatuses", [])
        if (pod.get("status", {}).get("phase") != "Running" or len(states) != 1
                or not states[0].get("ready") or states[0].get("restartCount", 0) != 0):
            raise SystemExit(f"{run_id}: unhealthy/restarted pod: {pod['metadata']['name']}")
    maintenance = [row for row in rows if row.get("event") == "dcsoc_maintenance"]
    if k5["algorithm"] == "dcsoc" and maintenance:
        raise SystemExit(f"{run_id}: overload-triggered DC-SoC maintenance={len(maintenance)}")
    message_ids = {row["message_id"] for row in injected}
    delivered = {(row.get("message_id"), int(row["peer_id"])) for row in received if row.get("message_id") in message_ids}
    per_message = []
    for mid in sorted(message_ids):
        t0 = min(row["ts"] for row in injected if row["message_id"] == mid)
        rec = [row["ts"] for row in received if row.get("message_id") == mid]
        if rec:
            per_message.append(max(rec) - t0)
    result = {
        "run_id": run_id, "algorithm": k5["algorithm"], "strategy": topo["strategy"],
        "seed": k5["seed"], "overload_factor": k5["overload_factor"],
        "overload_delay_ms": k5["overload_delay_ms"],
        "target_peer_id": targets[0]["peer_id"], "target_role": targets[0]["role"],
        "selection_basis": targets[0]["selection_basis"],
        "delivery_ratio": len(delivered) / (20 * 20),
        "propagation_delay": sum(per_message) / len(per_message) if per_message else math.nan,
        "duplicates": len(duplicates), "total_forwards": len(forwards),
        "dcsoc_maintenance": len(maintenance),
        "ahbn_trace_rows": sum(row.get("event") == "ahbn_controller_trace" for row in rows),
    }
    if not (0 <= result["delivery_ratio"] <= 1) or not math.isfinite(result["propagation_delay"]):
        raise SystemExit(f"{run_id}: metric sanity FAIL: {result}")
    out = run_dir / "metrics.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return result


def aggregate(root: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    metrics = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("runs/*/metrics.json"))]
    if len(metrics) != 80 or len({x["run_id"] for x in metrics}) != 80:
        raise SystemExit(f"formal run reconciliation FAIL: rows={len(metrics)}, unique={len({x['run_id'] for x in metrics})}")
    raw = pd.DataFrame(metrics).sort_values(["algorithm", "seed", "overload_factor"])
    expected = {(a, s, f) for a in ALGORITHMS for s in SEEDS for f in FACTORS}
    actual = {(r.algorithm, int(r.seed), float(r.overload_factor)) for r in raw.itertuples()}
    if actual != expected:
        raise SystemExit("formal coordinate set mismatch")
    raw.to_csv(root / "k5_raw_results.csv", index=False)
    summary = []
    for (algorithm, factor), group in raw.groupby(["algorithm", "overload_factor"], sort=False):
        for metric in ("delivery_ratio", "propagation_delay", "duplicates", "total_forwards"):
            values = group[metric].astype(float)
            mean = values.mean(); se = values.std(ddof=1) / math.sqrt(len(values))
            summary.append({"algorithm": algorithm, "overload_factor": factor,
                            "overload_delay_ms": DELAYS[float(factor)], "metric": metric,
                            "n": len(values), "mean": mean,
                            "ci95_low": mean - T_CRIT_DF4 * se,
                            "ci95_high": mean + T_CRIT_DF4 * se})
    agg = pd.DataFrame(summary)
    agg.to_csv(root / "k5_aggregate_results.csv", index=False)
    if len(agg.groupby(["algorithm", "overload_factor"])) != 16 or set(agg["n"]) != {5}:
        raise SystemExit("aggregate group integrity FAIL")
    plot_dir = root / "plots"; plot_dir.mkdir(exist_ok=True)
    labels = {"gossip": "Gossip", "structured": "Structured", "dcsoc": "DC-SoC", "ahbn": "AHBN"}
    for metric in ("delivery_ratio", "propagation_delay", "duplicates", "total_forwards"):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for algorithm in ALGORITHMS:
            data = agg[(agg.algorithm == algorithm) & (agg.metric == metric)].sort_values("overload_factor")
            yerr = [data["mean"] - data["ci95_low"], data["ci95_high"] - data["mean"]]
            ax.errorbar(data["overload_factor"], data["mean"], yerr=yerr, marker="o", capsize=3, label=labels[algorithm])
        ax.set_xlabel("Overload factor"); ax.set_ylabel(metric.replace("_", " ").title()); ax.legend(); fig.tight_layout()
        fig.savefig(plot_dir / f"{metric}_vs_overload.png", dpi=200); plt.close(fig)
    traces = []
    for run in sorted(root.glob("runs/k5_ahbn_*")):
        for row in load_jsonl(run / "logs.jsonl"):
            if row.get("event") == "ahbn_controller_trace":
                traces.append({**{k: json.loads((run / "topology.json").read_text())["k5"][k] for k in ("seed", "overload_factor")}, **row})
    pd.DataFrame(traces).to_csv(root / "k5_ahbn_traces.csv", index=False)
    if traces:
        td = pd.DataFrame(traces)
        fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        for factor, data in td[td.seed == 42].groupby("overload_factor"):
            data = data.sort_values("ts"); x = range(len(data))
            axes[0].plot(x, data["weight"], label=f"factor {factor}")
            axes[1].plot(x, data["fanout"], label=f"factor {factor}")
        axes[0].set_ylabel("Controller weight"); axes[1].set_ylabel("Fanout"); axes[1].set_xlabel("Trace event index"); axes[0].legend(); fig.tight_layout()
        fig.savefig(plot_dir / "ahbn_adaptive_trace_seed42.png", dpi=200); plt.close(fig)
    print(f"raw_rows={len(raw)} unique_runs={raw.run_id.nunique()} aggregate_groups=16 n=5")


def main() -> None:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("config"); p.add_argument("--base", type=Path, required=True); p.add_argument("--out", type=Path, required=True); p.add_argument("--algorithm", required=True); p.add_argument("--seed", type=int, required=True); p.add_argument("--factor", type=float, required=True)
    p = sub.add_parser("contract"); p.add_argument("topologies", nargs="+", type=Path)
    p = sub.add_parser("run"); p.add_argument("run_dir", type=Path)
    p = sub.add_parser("aggregate"); p.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.cmd == "config": write_config(args.base, args.out, args.algorithm, args.seed, args.factor)
    elif args.cmd == "contract": validate_contract(args.topologies)
    elif args.cmd == "run": validate_run(args.run_dir)
    else: aggregate(args.root)


if __name__ == "__main__":
    main()
