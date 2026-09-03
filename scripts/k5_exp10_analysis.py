#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, math, statistics, sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "app"))
from k5_exp10_tools import ALGORITHMS, SEEDS

METRICS = ("delivery_ratio", "propagation_delay", "duplicates", "total_forwards", "recovery_time_s")

def interval(values):
    mean = statistics.fmean(values)
    if len(values) < 2: return mean, mean, mean
    critical = 2.7764451051977987 if len(values) == 5 else 1.96
    margin = critical * statistics.stdev(values) / math.sqrt(len(values))
    return mean, mean - margin, mean + margin

def analyze(root: Path, mode: str):
    rows = [json.loads(p.read_text()) for p in sorted(root.glob("runs/*/*/metrics.json"))]
    seeds = (42,) if mode == "smoke" else SEEDS
    expected = {(a, s) for s in seeds for a in ALGORITHMS}
    actual = [(r["algorithm"], int(r["seed"])) for r in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError(f"matrix mismatch: expected={sorted(expected)} actual={sorted(actual)}")
    out = root / "results"; out.mkdir(exist_ok=True)
    with (out / "per_run.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary = []
    for algorithm in ALGORITHMS:
        group = [r for r in rows if r["algorithm"] == algorithm]
        for metric in METRICS:
            values = [float(r[metric]) for r in group if r.get(metric) is not None]
            mean, low, high = interval(values) if values else (None, None, None)
            summary.append({"algorithm": algorithm, "metric": metric, "n": len(values),
                            "mean": mean, "ci95_low": low, "ci95_high": high,
                            "unrecovered_runs": sum(not r["recovered"] for r in group) if metric == "recovery_time_s" else ""})
    with (out / "aggregate.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0])); writer.writeheader(); writer.writerows(summary)
    paired = []
    for algorithm in ALGORITHMS[1:]:
        for seed in seeds:
            base = next(r for r in rows if r["algorithm"] == "gossip" and r["seed"] == seed)
            other = next(r for r in rows if r["algorithm"] == algorithm and r["seed"] == seed)
            for metric in METRICS:
                delta = None if base.get(metric) is None or other.get(metric) is None else float(other[metric]) - float(base[metric])
                paired.append({"algorithm": algorithm, "reference": "gossip", "seed": seed, "metric": metric, "delta": delta})
    with (out / "paired_vs_gossip.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(paired[0])); writer.writeheader(); writer.writerows(paired)
    (out / "dataset_completeness.json").write_text(json.dumps({"mode": mode, "expected_runs": len(expected),
        "actual_runs": len(rows), "coordinates": sorted(actual), "unrecovered_runs": sum(not r["recovered"] for r in rows)}, indent=2) + "\n")
    print(f"Exp10 analysis PASS: {len(rows)} matched runs -> {out}")

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--mode",choices=("smoke","formal"),required=True)
    a=p.parse_args(); analyze(a.root,a.mode)
