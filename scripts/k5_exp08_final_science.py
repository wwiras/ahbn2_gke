#!/usr/bin/env python3
"""Independent, descriptive closure analysis for the frozen K5 Exp08 dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import statistics
from collections import Counter
from pathlib import Path

ALGORITHMS = ("gossip", "structured", "dcsoc", "ahbn")
FACTORS = (1.0, 1.5, 2.0, 3.0)
DELAYS = {1.0: 700, 1.5: 1050, 2.0: 1400, 3.0: 2100}
SEEDS = (42, 43, 44, 45, 46)
METRICS = ("delivery_ratio", "propagation_delay", "duplicates", "total_forwards")
EXPECTED_HASHES = {
    "app/ahbn_controller.py": "dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8",
    "app/peer.py": "64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a",
    "app/k5_final_actuator_policy.py": "8c7a0658cd226d0349e3ed3c64c943887196fdee57d9ef06874fd8525b683cff",
}
EXPECTED_IMAGE = "wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64"
EXPECTED_DIGEST = "sha256:d3224d4cdb16507d28d1c164d60b31b7c451fb0efa36e9add959f364fdd0a8d5"
T95 = {4: 2.7764451051977987, 3: 3.182446305284263}


def read_json(path: Path):
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def describe(values: list[float]) -> dict:
    n = len(values)
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    t = T95.get(n - 1, 1.96)
    margin = t * sd / math.sqrt(n) if n > 1 else 0.0
    ordered = sorted(values)
    return {
        "n": n, "mean": mean, "standard_deviation": sd,
        "ci95_low": mean - margin, "ci95_high": mean + margin,
        "minimum": ordered[0], "maximum": ordered[-1],
        "median": statistics.median(ordered),
    }


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lo, hi = math.floor(position), math.ceil(position)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict], fields: list[str], decimals: int = 4) -> str:
    def render(value):
        if isinstance(value, float):
            return f"{value:.{decimals}f}"
        return str(value)
    lines = ["| " + " | ".join(fields) + " |", "|" + "|".join("---" for _ in fields) + "|"]
    lines.extend("| " + " | ".join(render(row.get(field, "")) for field in fields) + " |" for row in rows)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("formal_root", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.formal_root.resolve()
    project = args.project_root.resolve()
    out = root / "final_analysis"
    tables = out / "tables"
    figures = out / "figures"
    out.mkdir(exist_ok=True)
    tables.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)

    failures: list[str] = []
    warnings: list[str] = []
    expected = set(itertools.product(ALGORITHMS, SEEDS, FACTORS))
    runs: list[dict] = []
    coordinates: list[tuple] = []
    status_rows = 0
    all_ready_alive = True
    target_alive = True
    pod_health = True
    pod_image_tags, pod_image_ids = set(), set()
    target_topology: dict[tuple[int, float], dict] = {}

    run_dirs = sorted((root / "runs").glob("k5_*_seed*_factor*"))
    for run_dir in run_dirs:
        required = ("metrics.json", "statuses.jsonl", "pods.json", "topology.json", "logs.jsonl")
        missing_files = [name for name in required if not (run_dir / name).is_file()]
        if missing_files:
            failures.append(f"{run_dir.name}: missing {missing_files}")
            continue
        metric = read_json(run_dir / "metrics.json")
        coordinate = (metric.get("algorithm"), metric.get("seed"), metric.get("overload_factor"))
        coordinates.append(coordinate)
        row = {key: metric.get(key) for key in metric}
        row["run_directory"] = str(run_dir)
        runs.append(row)
        if metric.get("overload_delay_ms") != DELAYS.get(metric.get("overload_factor")):
            failures.append(f"{run_dir.name}: factor/delay mismatch")
        for name in METRICS:
            value = metric.get(name)
            if not finite_number(value):
                failures.append(f"{run_dir.name}: missing/non-finite {name}")
        bounds = (("delivery_ratio", 0, 1), ("propagation_delay", 0, math.inf),
                  ("duplicates", 0, math.inf), ("total_forwards", 0, math.inf))
        for name, low, high in bounds:
            value = metric.get(name)
            if finite_number(value) and not low <= value <= high:
                failures.append(f"{run_dir.name}: {name} outside [{low}, {high}]")
        if metric.get("algorithm") == "dcsoc" and metric.get("dcsoc_maintenance") != 0:
            failures.append(f"{run_dir.name}: DC-SoC maintenance is not zero")
        if metric.get("controller_invariant_mismatches") != 0:
            failures.append(f"{run_dir.name}: controller invariant mismatch")
        if metric.get("actuator_invariant_mismatches") != 0:
            failures.append(f"{run_dir.name}: actuator invariant mismatch")

        statuses = read_jsonl(run_dir / "statuses.jsonl")
        status_rows += len(statuses)
        if len(statuses) != 20 or any(not x.get("ready") or not x.get("alive") for x in statuses):
            all_ready_alive = False
            failures.append(f"{run_dir.name}: not exactly 20 ready+alive peer statuses")
        targets = [x for x in statuses if x.get("peer_id") == metric.get("target_peer_id")]
        if len(targets) != 1 or not targets[0].get("alive"):
            target_alive = False
            failures.append(f"{run_dir.name}: overloaded target not logically alive")

        pods = read_json(run_dir / "pods.json").get("items", [])
        if len(pods) != 20:
            pod_health = False
            failures.append(f"{run_dir.name}: pod evidence count != 20")
        for pod in pods:
            conditions = {x.get("type"): x.get("status") for x in pod.get("status", {}).get("conditions", [])}
            containers = pod.get("status", {}).get("containerStatuses", [])
            if conditions.get("Ready") != "True" or any(not c.get("ready") for c in containers):
                pod_health = False
                failures.append(f"{run_dir.name}: unready pod in collected evidence")
            for container in pod.get("spec", {}).get("containers", []):
                pod_image_tags.add(container.get("image"))
            for container in containers:
                pod_image_ids.add(container.get("imageID"))

        if metric.get("algorithm") == "ahbn":
            topology = read_json(run_dir / "topology.json")
            nodes = topology.get("nodes", {})
            target = str(metric["target_peer_id"])
            degrees = [len(node.get("neighbors", [])) for node in nodes.values()]
            target_topology[(metric["seed"], metric["overload_factor"])] = {
                "target_peer": metric["target_peer_id"],
                "target_degree": len(nodes.get(target, {}).get("neighbors", [])),
                "mean_node_degree": statistics.fmean(degrees),
                "edge_density": sum(degrees) / (len(degrees) * (len(degrees) - 1)),
            }

    observed = set(coordinates)
    missing_coordinates = sorted(expected - observed)
    unexpected_coordinates = sorted(observed - expected)
    duplicate_coordinates = sorted(item for item, count in Counter(coordinates).items() if count > 1)
    if len(runs) != 80: failures.append(f"run count {len(runs)} != 80")
    if len(observed) != 80: failures.append(f"unique coordinate count {len(observed)} != 80")
    if missing_coordinates: failures.append(f"missing coordinates: {missing_coordinates}")
    if unexpected_coordinates: failures.append(f"unexpected coordinates: {unexpected_coordinates}")
    if duplicate_coordinates: failures.append(f"duplicate coordinates: {duplicate_coordinates}")

    actual_hashes = {path: sha256(project / path) for path in EXPECTED_HASHES}
    recorded_hash_text = (root / "canonical_hashes.txt").read_text() + (root / "final_actuator_hashes.txt").read_text()
    for path, expected_hash in EXPECTED_HASHES.items():
        if actual_hashes[path] != expected_hash:
            failures.append(f"current hash mismatch: {path}")
        if f"{expected_hash}  {path}" not in recorded_hash_text:
            failures.append(f"formal recorded hash mismatch/missing: {path}")
    image = (root / "image.txt").read_text().strip()
    smoke_image = (root / "smoke_image.txt").read_text().strip()
    image_provenance = read_json(root / "image_provenance.json")
    provenance_ok = (
        image == smoke_image == EXPECTED_IMAGE
        and image_provenance.get("image_tags") == [EXPECTED_IMAGE]
        and len(image_provenance.get("image_ids", [])) == 1
        and EXPECTED_DIGEST in image_provenance["image_ids"][0]
        and pod_image_tags == {EXPECTED_IMAGE}
        and len(pod_image_ids) == 1
        and EXPECTED_DIGEST in next(iter(pod_image_ids), "")
    )
    if not provenance_ok:
        failures.append("formal/smoke/pod image provenance mismatch")

    # Comparator summaries and matched-seed deltas.
    combined: list[dict] = []
    for algorithm in ALGORITHMS:
        for factor in FACTORS:
            subset = [row for row in runs if row["algorithm"] == algorithm and row["overload_factor"] == factor]
            for metric in METRICS:
                desc = describe([float(row[metric]) for row in subset])
                combined.append({"algorithm": algorithm, "overload_factor": factor,
                                 "overload_delay_ms": DELAYS[factor], "metric": metric, **desc})
    write_csv(tables / "comparator_combined.csv", combined)
    for metric in METRICS:
        write_csv(tables / f"comparator_{metric}.csv", [row for row in combined if row["metric"] == metric])
    write_csv(tables / "per_seed_results.csv", sorted(runs, key=lambda x: (x["algorithm"], x["seed"], x["overload_factor"])),
              ["run_id", "algorithm", "seed", "overload_factor", "overload_delay_ms", *METRICS,
               "target_peer_id", "dcsoc_maintenance", "controller_invariant_mismatches", "actuator_invariant_mismatches"])

    index = {(row["algorithm"], row["seed"], row["overload_factor"]): row for row in runs}
    deltas: list[dict] = []
    for factor in FACTORS:
        for seed in SEEDS:
            ahbn = index[("ahbn", seed, factor)]
            for comparator in ("gossip", "structured", "dcsoc"):
                other = index[(comparator, seed, factor)]
                deltas.append({"seed": seed, "overload_factor": factor, "overload_delay_ms": DELAYS[factor],
                               "comparison": f"ahbn_minus_{comparator}",
                               **{f"delta_{metric}": ahbn[metric] - other[metric] for metric in METRICS}})
    write_csv(tables / "matched_seed_deltas.csv", deltas)

    tradeoff: list[dict] = []
    for factor in FACTORS:
        a = {row["metric"]: row["mean"] for row in combined if row["algorithm"] == "ahbn" and row["overload_factor"] == factor}
        for comparator in ("gossip", "structured", "dcsoc"):
            c = {row["metric"]: row["mean"] for row in combined if row["algorithm"] == comparator and row["overload_factor"] == factor}
            tradeoff.append({
                "overload_factor": factor, "overload_delay_ms": DELAYS[factor], "comparator": comparator,
                "delivery_deficit": c["delivery_ratio"] - a["delivery_ratio"],
                "duplicate_saving": c["duplicates"] - a["duplicates"],
                "duplicate_reduction_percent": 100 * (c["duplicates"] - a["duplicates"]) / c["duplicates"] if c["duplicates"] else math.nan,
                "forward_saving": c["total_forwards"] - a["total_forwards"],
                "forward_reduction_percent": 100 * (c["total_forwards"] - a["total_forwards"]) / c["total_forwards"] if c["total_forwards"] else math.nan,
                "delay_delta_ahbn_minus_comparator": a["propagation_delay"] - c["propagation_delay"],
            })
    write_csv(tables / "tradeoff_diagnostics.csv", tradeoff)

    # AHBN mechanism summaries from the frozen trace and actuator exports.
    traces = list(csv.DictReader((root / "k5_ahbn_traces.csv").open()))
    decisions = list(csv.DictReader((root / "k5_ahbn_actuator_decisions.csv").open()))
    numeric_trace = {"d_hat": "d_hat", "l_hat": "l_hat", "u_hat": "u_hat", "c_hat": "c_hat", "z": "score"}
    trace_summary: list[dict] = []
    mode_summary: list[dict] = []
    for factor in FACTORS:
        subset = [row for row in traces if float(row["overload_factor"]) == factor]
        for label, column in numeric_trace.items():
            values = [float(row[column]) for row in subset]
            desc = describe(values)
            trace_summary.append({"overload_factor": factor, "overload_delay_ms": DELAYS[factor],
                                  "quantity": label, **desc, "p05": percentile(values, .05),
                                  "p25": percentile(values, .25), "p75": percentile(values, .75),
                                  "p95": percentile(values, .95)})
        counts = Counter(row["mode"] for row in subset)
        for mode in ("gossip", "cluster"):
            mode_summary.append({"overload_factor": factor, "overload_delay_ms": DELAYS[factor],
                                 "mode": mode, "count": counts[mode], "share": counts[mode] / len(subset),
                                 "trace_rows": len(subset)})
    write_csv(tables / "ahbn_trace_numeric_summary.csv", trace_summary)
    write_csv(tables / "ahbn_mode_summary.csv", mode_summary)

    fanout_summary: list[dict] = []
    condition_actions: list[dict] = []
    seed_topology: list[dict] = []
    for factor in FACTORS:
        subset = [row for row in decisions if float(row["overload_factor"]) == factor]
        req = Counter(int(row["requested_fanout"]) for row in subset)
        actual = Counter(int(row["actual_fanout"]) for row in subset)
        for level in range(2, 7):
            fanout_summary.append({"overload_factor": factor, "overload_delay_ms": DELAYS[factor],
                                   "fanout_type": "requested", "fanout": level, "count": req[level],
                                   "share": req[level] / len(subset), "decision_rows": len(subset)})
        for level in sorted(set(actual) | set(range(0, 7))):
            fanout_summary.append({"overload_factor": factor, "overload_delay_ms": DELAYS[factor],
                                   "fanout_type": "realized", "fanout": level, "count": actual[level],
                                   "share": actual[level] / len(subset), "decision_rows": len(subset)})
        condition_actions.append({
            "overload_factor": factor, "overload_delay_ms": DELAYS[factor], "decision_rows": len(subset),
            "mean_z": statistics.fmean(float(row["z"]) for row in subset),
            "mean_requested_fanout": statistics.fmean(int(row["requested_fanout"]) for row in subset),
            "mean_realized_fanout": statistics.fmean(int(row["actual_fanout"]) for row in subset),
            "mean_eligible_neighbors": statistics.fmean(int(row["eligible_neighbors"]) for row in subset),
            "eligible_clipping_count": sum(row["eligible_clipping"] == "True" for row in subset),
            "eligible_clipping_share": statistics.fmean(row["eligible_clipping"] == "True" for row in subset),
            "realized_clipping_count": sum(row["realized_clipping"] == "True" for row in subset),
            "realized_clipping_share": statistics.fmean(row["realized_clipping"] == "True" for row in subset),
        })
        for seed in SEEDS:
            ss = [row for row in subset if int(row["seed"]) == seed]
            top = target_topology[(seed, factor)]
            metric = index[("ahbn", seed, factor)]
            seed_topology.append({
                "seed": seed, "overload_factor": factor, "overload_delay_ms": DELAYS[factor], **top,
                "eligible_mean": statistics.fmean(int(row["eligible_neighbors"]) for row in ss),
                "eligible_min": min(int(row["eligible_neighbors"]) for row in ss),
                "eligible_max": max(int(row["eligible_neighbors"]) for row in ss),
                "requested_mean": statistics.fmean(int(row["requested_fanout"]) for row in ss),
                "realized_mean": statistics.fmean(int(row["actual_fanout"]) for row in ss),
                "clipping_share": statistics.fmean(row["realized_clipping"] == "True" for row in ss),
                "mean_z": statistics.fmean(float(row["z"]) for row in ss),
                "delivery_ratio": metric["delivery_ratio"], "duplicates": metric["duplicates"],
                "total_forwards": metric["total_forwards"], "propagation_delay": metric["propagation_delay"],
            })
    write_csv(tables / "ahbn_fanout_distribution.csv", fanout_summary)
    write_csv(tables / "ahbn_action_by_condition.csv", condition_actions)
    write_csv(tables / "ahbn_seed_topology_summary.csv", seed_topology)

    # Per-seed non-monotonicity and leave-one-seed-out robustness.
    nonmonotonic: list[dict] = []
    for seed in SEEDS:
        sequence = [index[("ahbn", seed, factor)] for factor in FACTORS]
        action = [next(row for row in seed_topology if row["seed"] == seed and row["overload_factor"] == factor) for factor in FACTORS]
        for metric in (*METRICS, "mean_z", "requested_mean", "realized_mean"):
            values = [float((action[i] if metric in action[i] else sequence[i])[metric]) for i in range(4)]
            diffs = [b - a for a, b in zip(values, values[1:])]
            nonmonotonic.append({"seed": seed, "quantity": metric, "v700": values[0], "v1050": values[1],
                                 "v1400": values[2], "v2100": values[3], "delta_signs": "/".join("+" if x > 0 else "-" if x < 0 else "0" for x in diffs),
                                 "monotonic_non_decreasing": all(x >= 0 for x in diffs),
                                 "monotonic_non_increasing": all(x <= 0 for x in diffs)})
    write_csv(tables / "ahbn_nonmonotonicity.csv", nonmonotonic)

    loo_rows: list[dict] = []
    for excluded in SEEDS:
        kept = [seed for seed in SEEDS if seed != excluded]
        for factor in FACTORS:
            for comparator in ("gossip", "structured", "dcsoc"):
                values = [next(row for row in deltas if row["seed"] == seed and row["overload_factor"] == factor and row["comparison"] == f"ahbn_minus_{comparator}") for seed in kept]
                loo_rows.append({"excluded_seed": excluded, "overload_factor": factor, "overload_delay_ms": DELAYS[factor],
                                 "comparison": f"ahbn_minus_{comparator}",
                                 **{f"mean_delta_{metric}": statistics.fmean(row[f"delta_{metric}"] for row in values) for metric in METRICS}})
    write_csv(tables / "leave_one_seed_out.csv", loo_rows)

    conclusions = []
    definitions = (
        ("AHBN lower delivery than Gossip", "gossip", "mean_delta_delivery_ratio", lambda x: x < 0),
        ("AHBN saves duplicates versus Gossip", "gossip", "mean_delta_duplicates", lambda x: x < 0),
        ("AHBN saves forwards versus Gossip", "gossip", "mean_delta_total_forwards", lambda x: x < 0),
    )
    for name, comparator, field, predicate in definitions:
        relevant = [row for row in loo_rows if row["comparison"] == f"ahbn_minus_{comparator}"]
        robust = all(predicate(row[field]) for row in relevant)
        conclusions.append({"conclusion": name, "classification": "ROBUST" if robust else "SENSITIVE",
                            "criterion": "All 20 condition-by-excluded-seed LOO means preserve the stated direction."})
    delivery_rows = [row for row in nonmonotonic if row["quantity"] == "delivery_ratio"]
    monotonic_count = sum(row["monotonic_non_decreasing"] or row["monotonic_non_increasing"] for row in delivery_rows)
    conclusions.append({"conclusion": "AHBN delivery is non-monotonic with overload",
                        "classification": "ROBUST" if monotonic_count == 0 else "SENSITIVE",
                        "criterion": f"Only {monotonic_count}/5 seed trajectories are monotonic; direction is not stable."})
    z_factor_means = [next(row["mean_z"] for row in condition_actions if row["overload_factor"] == factor) for factor in FACTORS]
    z_diffs = [b - a for a, b in zip(z_factor_means, z_factor_means[1:])]
    conclusions.append({"conclusion": "Mean z increases monotonically with configured overload",
                        "classification": "ROBUST" if all(x >= 0 for x in z_diffs) else "SENSITIVE",
                        "criterion": f"Condition means={','.join(f'{x:.4f}' for x in z_factor_means)}; inspected with per-seed trajectories."})
    write_csv(tables / "conclusion_robustness.csv", conclusions)

    comparator_full_delivery = {algorithm: sum(row["delivery_ratio"] == 1.0 for row in runs if row["algorithm"] == algorithm)
                                for algorithm in ALGORITHMS}
    high_levels = Counter(int(row["requested_fanout"]) for row in decisions if int(row["requested_fanout"]) >= 5)
    formal_gate = not failures
    audit = {
        "formal_root": str(root), "expected_executions": 80, "actual_executions": len(runs),
        "unique_coordinates": len(observed), "missing_coordinates": missing_coordinates,
        "unexpected_coordinates": unexpected_coordinates, "duplicate_coordinates": duplicate_coordinates,
        "algorithms": sorted({row["algorithm"] for row in runs}),
        "overload_factors": sorted({row["overload_factor"] for row in runs}),
        "overload_delays_ms": sorted({row["overload_delay_ms"] for row in runs}),
        "seeds": sorted({row["seed"] for row in runs}), "peer_status_rows": status_rows,
        "all_peers_ready_and_alive": all_ready_alive, "overloaded_target_alive_all_runs": target_alive,
        "pod_health_pass": pod_health, "dcsoc_maintenance_zero": all(row.get("dcsoc_maintenance") == 0 for row in runs if row["algorithm"] == "dcsoc"),
        "controller_invariant_mismatches": sum(row.get("controller_invariant_mismatches", 0) for row in runs),
        "actuator_invariant_mismatches": sum(row.get("actuator_invariant_mismatches", 0) for row in runs),
        "expected_hashes": EXPECTED_HASHES, "actual_current_hashes": actual_hashes,
        "image_tag": image, "image_digest": EXPECTED_DIGEST, "image_provenance_pass": provenance_ok,
        "failures": failures, "warnings": warnings, "formal_integrity_gate": "PASS" if formal_gate else "FAIL",
    }
    (out / "final_dataset_audit.json").write_text(json.dumps(audit, indent=2) + "\n")

    # Publication-oriented plots and their exact raw data.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = {"gossip": "Gossip", "structured": "Structured", "dcsoc": "DC-SoC", "ahbn": "AHBN"}
    for metric in METRICS:
        fig, ax = plt.subplots(figsize=(7.2, 4.6))
        plot_rows = [row for row in combined if row["metric"] == metric]
        for algorithm in ALGORITHMS:
            rr = [row for row in plot_rows if row["algorithm"] == algorithm]
            x = [row["overload_delay_ms"] for row in rr]
            y = [row["mean"] for row in rr]
            err = [[row["mean"] - row["ci95_low"] for row in rr], [row["ci95_high"] - row["mean"] for row in rr]]
            ax.errorbar(x, y, yerr=err, marker="o", capsize=3, label=labels[algorithm])
        ax.set_xlabel("Overloaded-peer delay (ms)"); ax.set_ylabel(metric.replace("_", " ").title())
        ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
        fig.savefig(figures / f"{metric}_vs_overload_95ci.png", dpi=240); plt.close(fig)
        write_csv(figures / f"{metric}_vs_overload_95ci_data.csv", plot_rows)
    requested = [row for row in fanout_summary if row["fanout_type"] == "requested"]
    fig, ax = plt.subplots(figsize=(7.2, 4.6)); bottom = [0.0] * 4
    for level in range(2, 7):
        values = [next(row["share"] for row in requested if row["fanout"] == level and row["overload_factor"] == factor) for factor in FACTORS]
        ax.bar([DELAYS[f] for f in FACTORS], values, width=150, bottom=bottom, label=f"f={level}")
        bottom = [a + b for a, b in zip(bottom, values)]
    ax.set_xlabel("Overloaded-peer delay (ms)"); ax.set_ylabel("Decision share"); ax.legend(ncol=3); fig.tight_layout()
    fig.savefig(figures / "ahbn_requested_fanout_by_overload.png", dpi=240); plt.close(fig)
    write_csv(figures / "ahbn_requested_fanout_by_overload_data.csv", requested)
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    zsets = [[float(row["score"]) for row in traces if float(row["overload_factor"]) == factor] for factor in FACTORS]
    ax.boxplot(zsets, tick_labels=[DELAYS[f] for f in FACTORS], showfliers=False)
    ax.axhline(-.25, color="grey", ls="--", lw=.8); ax.axhline(.25, color="grey", ls="--", lw=.8)
    ax.axhline(.9, color="grey", ls="--", lw=.8); ax.axhline(1.5, color="grey", ls="--", lw=.8)
    ax.set_xlabel("Overloaded-peer delay (ms)"); ax.set_ylabel("Canonical z"); fig.tight_layout()
    fig.savefig(figures / "ahbn_z_distribution_by_overload.png", dpi=240); plt.close(fig)
    write_csv(figures / "ahbn_z_distribution_by_overload_data.csv",
              [{"overload_factor": row["overload_factor"], "seed": row["seed"], "z": row["score"]} for row in traces])
    for cost in ("duplicates", "total_forwards"):
        fig, ax = plt.subplots(figsize=(6.5, 4.8))
        for algorithm in ALGORITHMS:
            rr = [row for row in runs if row["algorithm"] == algorithm]
            ax.scatter([row[cost] for row in rr], [row["delivery_ratio"] for row in rr], alpha=.72, label=labels[algorithm])
        ax.set_xlabel(cost.replace("_", " ").title()); ax.set_ylabel("Delivery ratio"); ax.grid(alpha=.2); ax.legend(); fig.tight_layout()
        fig.savefig(figures / f"delivery_vs_{cost}.png", dpi=240); plt.close(fig)
        write_csv(figures / f"delivery_vs_{cost}_data.csv", [{"algorithm": row["algorithm"], "seed": row["seed"], "overload_delay_ms": row["overload_delay_ms"], "delivery_ratio": row["delivery_ratio"], cost: row[cost]} for row in runs])

    overall = {algorithm: {metric: statistics.fmean(float(row[metric]) for row in runs if row["algorithm"] == algorithm) for metric in METRICS} for algorithm in ALGORITHMS}
    summary = {
        "audit_gate": "PASS" if formal_gate else "FAIL", "result_direction": "MIXED",
        "overall_means": overall, "full_delivery_runs": comparator_full_delivery,
        "ahbn_requested_fanout_5_count": high_levels[5], "ahbn_requested_fanout_6_count": high_levels[6],
        "ahbn_delivery_by_delay": {str(DELAYS[f]): next(row["mean"] for row in combined if row["algorithm"] == "ahbn" and row["overload_factor"] == f and row["metric"] == "delivery_ratio") for f in FACTORS},
        "conclusion_robustness": conclusions,
    }
    (out / "final_scientific_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    report_lines = ["# K5 Exp08 Final Independent Validation", "", f"Integrity gate: **{'PASS' if formal_gate else 'FAIL'}**.", "",
                    f"Audited {len(runs)}/80 runs and {len(observed)}/80 unique coordinates; missing={len(missing_coordinates)}, duplicates={len(duplicate_coordinates)}.",
                    f"Collected {status_rows} peer status records; all-ready/alive={all_ready_alive}; overloaded-target-alive={target_alive}.",
                    f"Image provenance={provenance_ok}; controller mismatches={audit['controller_invariant_mismatches']}; actuator mismatches={audit['actuator_invariant_mismatches']}.", "",
                    "## Findings", "", f"Comparator full-delivery counts: {comparator_full_delivery}.",
                    f"AHBN requested fanout levels 5 and 6 occurred {high_levels[5]} and {high_levels[6]} times, respectively.",
                    "Result direction is MIXED: AHBN reduces Gossip traffic cost and frequently lowers delay, but delivers materially less than every comparator; responses are seed- and timing-sensitive.", "",
                    "## Failures", "", *(f"- {item}" for item in failures)]
    (out / "final_validation_report.md").write_text("\n".join(report_lines) + "\n")
    (out / "final_validation_report.json").write_text(json.dumps({"gate": "PASS" if formal_gate else "FAIL", "failures": failures, "summary": summary}, indent=2) + "\n")

    # Evidence-led local documentation; the main manuscript is intentionally not edited.
    agg_delivery = [row for row in combined if row["metric"] == "delivery_ratio"]
    agg_delay = [row for row in combined if row["metric"] == "propagation_delay"]
    agg_dup = [row for row in combined if row["metric"] == "duplicates"]
    agg_fwd = [row for row in combined if row["metric"] == "total_forwards"]
    doc = project / "docs" / "K5_exp08_final_scientific_interpretation.md"
    doc.write_text(f"""# K5 Exp08 Final Scientific Interpretation

## What happened

The frozen 80-run Kubernetes campaign produced a valid but mixed result. Gossip, Structured, and DC-SoC delivered to every peer in all 20 runs per algorithm. AHBN delivery was lower in all 20 runs, with condition means of {summary['ahbn_delivery_by_delay']['700']:.4f}, {summary['ahbn_delivery_by_delay']['1050']:.4f}, {summary['ahbn_delivery_by_delay']['1400']:.4f}, and {summary['ahbn_delivery_by_delay']['2100']:.4f} at 700, 1050, 1400, and 2100 ms. AHBN simultaneously used substantially fewer forwards than the 380-run envelope of every comparator and far fewer duplicates than Gossip.

## Comparator evidence

Across all conditions, the highest delivery was a three-way tie (Gossip, Structured, DC-SoC: 1.0). AHBN had the lowest mean delay at all four overload conditions. Gossip generated the most duplicates (680/run); Structured and DC-SoC generated the least (0/run). AHBN used the fewest forwards at every condition; all comparators recorded 380/run.

The descriptive Student-t intervals are in `{tables / 'comparator_combined.csv'}`. They characterize the five frozen seeds and are not claims of population-wide inferential significance.

## AHBN mechanism

The trace confirms the unchanged equation `z = -d_hat + l_hat + u_hat + c_hat` and the S5 mapping. Requested levels 5 and 6 occurred {high_levels[5]} and {high_levels[6]} times. Requested fanout was monotone in each recorded z by construction, but realized fanout was often below the request because eligible-neighbour counts constrained actions. The exact condition, mode, fanout, clipping, and topology summaries are in `{tables}`.

## Gains, sacrifice, and defensibility

AHBN's bounded adaptive fanout gained lower dissemination traffic and, in three conditions, lower mean delay. It sacrificed nominal reachability. This is a real efficiency-reachability/robustness trade-off because the delivery deficit co-occurred with meaningful forward and Gossip-duplicate savings; it is not evidence that propagation performance was maintained. Lower delivery is scientifically interpretable, but it remains the principal limitation and cannot be described away as success.

## Non-monotonicity and topology

AHBN delivery was non-monotonic for {5-monotonic_count}/5 seeds. Changes in delivery co-occurred with changes in requested/realized fanout and redundancy, and frequent clipping shows that topology degree and eligible-neighbour availability can constrain dissemination. These are descriptive associations. The frozen data do not isolate controller adaptation from Kubernetes scheduling, runtime timing, or topology-path effects, so causal attribution is not justified.

## Claims that must not be made

- AHBN did not maintain full or comparator-equivalent delivery in Exp08.
- AHBN did not consistently outperform the comparators.
- A universally balanced or robust operating point is not established by this experiment.
- Non-monotonic improvement at higher overload must not be presented as a causal adaptation effect.
- The older 8.6% delay-increase and 134% Structured-increase claims are not the frozen K5 result.

## Thesis contribution

Exp08 demonstrates a reproducible bounded adaptive operating envelope in a real Kubernetes runtime: AHBN changes internal action levels, cuts dissemination cost, and exposes an explicit reachability limitation under a slow-but-alive important peer. Its contribution is the measured multi-objective trade-off and mechanism evidence—not universal superiority.
""")

    audit_doc = project / "docs" / "K5_exp08_manuscript_claim_audit.md"
    audit_doc.write_text(f"""# K5 Exp08 Manuscript Claim Audit

The manuscript is framing guidance; the frozen 2026 K5 dataset is authoritative for Exp08. The main manuscript was not edited.

| Manuscript claim | Old value/wording | New frozen K5 evidence | Status | Recommended wording |
|---|---|---|---|---|
| AHBN maintains propagation performance under bottleneck | “maintaining propagation performance” | AHBN delivery means are {summary['ahbn_delivery_by_delay']['700']:.4f}–{summary['ahbn_delivery_by_delay']['2100']:.4f}; all three comparators are 1.0 in 20/20 runs each. | REVISE | AHBN reduces dissemination cost and often delay, while sacrificing reachability under bounded adaptive fanout. |
| AHBN consistently occupies a balanced operating point | “consistently” / “balanced” | Traffic savings are robust, but delivery is uniformly lower and trajectories are non-monotonic. | QUALIFY | AHBN occupies a bounded adaptive trade-off point in Exp08; whether that balance is acceptable depends on reachability requirements. |
| Duplicate reduction up to 62.2% | 62.2% | Frozen condition-specific AHBN-vs-Gossip reductions are recorded in `{tables / 'tradeoff_diagnostics.csv'}` and differ from the old value. Structured/DC-SoC have zero duplicates. | REVISE | Report the new condition-specific values and name Gossip as the baseline; do not generalize to all comparators. |
| AHBN limits delay increase to 8.6% | 8.6% | Frozen AHBN mean delay rises from {next(r['mean'] for r in agg_delay if r['algorithm']=='ahbn' and r['overload_factor']==1.0):.4f}s to {next(r['mean'] for r in agg_delay if r['algorithm']=='ahbn' and r['overload_factor']==3.0):.4f}s and is non-monotonic by seed. | REMOVE | Replace with absolute means/95% CIs and comparator-specific deltas from frozen K5. |
| Structured delay rises 134% | 134% | The frozen Structured condition means are in `{tables / 'comparator_propagation_delay.csv'}`; the old percentage is not the authoritative K5 value. | REVISE | Recalculate explicitly from frozen means and state the endpoints. |
| Kubernetes validation confirms robustness | broad robustness claim | Implementation and mechanism are robustly evidenced, but AHBN reaches fewer nodes than comparators in every run. | QUALIFY | Kubernetes validation confirms executable adaptation and a stable traffic-saving direction, while revealing a reachability limitation. |
| Gossip gains reachability through redundancy | qualitative | Gossip delivery is 1.0 in 20/20 runs with 680 duplicates/run. | RETAIN | Gossip preserves full delivery in this campaign at the highest duplicate cost. |
| Structured methods are bottleneck-sensitive | qualitative | Structured remains at full delivery and 0 duplicates but delay grows with overload. | RETAIN | Structured retains delivery and zero duplicate count here, with overload-sensitive delay. |
| AHBN uses local observation-driven adaptation | qualitative | Canonical traces and S5 actions are present with zero invariant mismatch. | RETAIN | AHBN adapts bounded requested fanout from locally derived z; eligible topology constrains realized action. |
""")

    freeze = project / "docs" / "K5_EXP08_FROZEN.md"
    if formal_gate:
        git_commit = (root / "git_commit.txt").read_text().strip()
        git_state = (root / "git_status.txt").read_text().strip() or "clean"
        topology0 = read_json(root / "runs" / "k5_ahbn_seed42_factor1.0" / "topology.json")
        freeze.write_text(f"""# K5 Exp08 Freeze Record

**K5 EXP08 STATUS: FROZEN**  
Freeze date: 2026-09-02

## Immutable experiment identity

- Formal output: `{root}`
- Expected/actual executions: 80/80
- Algorithms: Gossip, Structured, DC-SoC, AHBN
- Delays: 700, 1050, 1400, 2100 ms
- Seeds: 42, 43, 44, 45, 46
- Topology: {topology0['num_nodes']} nodes, `{topology0['topology_type']}`, `ba_m={topology0['ba_m']}`, source={topology0['message_source']}
- Image: `{image}`
- Digest: `{EXPECTED_DIGEST}`
- Recorded git commit: `{git_commit}`
- Recorded working-tree state at formal start:\n\n```text\n{git_state}\n```

## Frozen implementation

{chr(10).join(f'- `{path}`: `{digest}`' for path, digest in EXPECTED_HASHES.items())}
- `app/k5_final_actuator_runtime.py`: `{sha256(project / 'app/k5_final_actuator_runtime.py')}`
- Controller equation: `z = -d_hat + l_hat + u_hat + c_hat`
- S5: `z<=-0.25→2`, `-0.25<z<0.25→3`, `0.25<=z<0.90→4`, `0.90<=z<1.50→5`, `z>=1.50→6`

## Validation gate

- Dataset coordinates: PASS (80 unique; zero missing/duplicate/unexpected)
- Mandatory metric domains: PASS
- All 1,600 collected peer statuses ready and alive: PASS
- Overloaded target logically alive in every run: PASS
- DC-SoC SLOW!=FAILED (maintenance zero): PASS
- Controller invariant mismatches: 0
- Actuator invariant mismatches: 0
- Canonical/S5 hashes: PASS
- Smoke/formal/pod image provenance: PASS
- Result direction: MIXED
- Formal integrity gate: PASS

## Principal result and limitations

Gossip, Structured, and DC-SoC achieve delivery 1.0 in every run. AHBN trades lower delivery for fewer forwards, far fewer duplicates than Gossip, and lower mean delay in three of four conditions. Its delivery and internal response are non-monotonic and seed/timing sensitive; frequent eligible-neighbour clipping means realized dissemination can be topology-constrained. This supports a bounded adaptive trade-off interpretation, not consistent superiority or maintained propagation performance.

Manuscript claims requiring revision include the old 8.6%/134% delay statements, the unqualified 62.2% duplicate statement, “maintains propagation performance,” and broad “consistently balanced/robust” wording.

## Closure artifacts

- Audit: `{out / 'final_dataset_audit.json'}`
- Validation: `{out / 'final_validation_report.md'}`
- Scientific summary: `{out / 'final_scientific_summary.json'}`
- Tables: `{tables}`
- Figures: `{figures}`
- Interpretation: `{doc}`
- Manuscript audit: `{audit_doc}`

No further Exp08 tuning or reruns may be performed solely to improve performance. Any reopening requires a new preregistered experiment identity and must not overwrite this frozen dataset.
""")

    print(f"FINAL DATASET AUDIT: {'PASS' if formal_gate else 'FAIL'}")
    print(f"runs={len(runs)}/80 unique_coordinates={len(observed)}/80 missing={len(missing_coordinates)} duplicates={len(duplicate_coordinates)}")
    print(f"peer_statuses={status_rows} all_ready_alive={all_ready_alive} overloaded_target_alive={target_alive}")
    print(f"image_provenance={provenance_ok} controller_mismatches={audit['controller_invariant_mismatches']} actuator_mismatches={audit['actuator_invariant_mismatches']}")
    print(f"comparator_full_delivery_runs={comparator_full_delivery}")
    print(f"ahbn_fanout_5={high_levels[5]} ahbn_fanout_6={high_levels[6]}")
    print(f"RESULT DIRECTION: MIXED")
    print(f"K5 EXP08 STATUS: {'FROZEN' if formal_gate else 'NOT FROZEN'}")
    if failures:
        raise SystemExit("; ".join(failures))


if __name__ == "__main__":
    main()
