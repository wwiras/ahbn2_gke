#!/usr/bin/env python3
"""Deterministic K5 bounded-fanout screen; production AHBN is never imported."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path

import networkx as nx

MODES = ("LOW", "MODERATE", "HIGH")
POLICIES = ("S0", "S2", "S5-C5", "S5-C6", "S5-C7")
NE_CASES = (0, 1, 2, 3, 4, 5, 6, 7, 9)
SEEDS = (42, 43, 44, 45, 46)
Z_CASES = (("LOW", -0.5), ("MODERATE", 0.0), ("HIGH", 0.5))
SCENARIOS = ("clean", "multipath", "capacity", "unavailability")
NUMERIC_METRICS = (
    "delivery_ratio", "propagation_delay", "send_attempts", "duplicates",
    "new_reach_count", "new_reach_efficiency", "forwarding_decisions",
    "opportunities_ne_gt_requested", "fraction_ne_gt_requested",
    "mean_eligible_neighbors", "mean_requested_fanout", "mean_actual_fanout",
    "mean_unused_eligible_capacity", "low_usage", "moderate_usage", "high_usage",
)


def fanout(policy: str, mode: str, ne: int) -> int:
    if policy not in POLICIES or mode not in MODES or ne < 0:
        raise ValueError(f"invalid fanout request: {policy=}, {mode=}, {ne=}")
    if policy == "S0":
        return min({"LOW": 2, "MODERATE": 3, "HIGH": 4}[mode], ne)
    base = {"LOW": math.ceil(ne / 3), "MODERATE": math.ceil(2 * ne / 3), "HIGH": ne}[mode]
    if policy == "S2":
        return min(base, ne)
    return min(base, int(policy.removeprefix("S5-C")), ne)


def stable_key(*parts: object) -> int:
    value = json.dumps(parts, separators=(",", ":"), sort_keys=True).encode()
    return int.from_bytes(hashlib.sha256(value).digest()[:16], "big")


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    graph: nx.Graph
    source: int
    unavailable: frozenset[int]


@dataclass(frozen=True)
class Result:
    policy: str
    seed: int
    scenario: str
    mode: str
    delivery_ratio: float
    propagation_delay: int
    send_attempts: int
    duplicates: int
    new_reach_count: int
    new_reach_efficiency: float
    forwarding_decisions: int
    opportunities_ne_gt_requested: int
    fraction_ne_gt_requested: float
    mean_eligible_neighbors: float
    mean_requested_fanout: float
    mean_actual_fanout: float
    mean_unused_eligible_capacity: float
    low_usage: int
    moderate_usage: int
    high_usage: int


def build_scenario(name: str, seed: int) -> Scenario:
    m = 3 if name == "multipath" else 2
    graph = nx.freeze(nx.barabasi_albert_graph(20, m, seed=seed))
    ranked = sorted(graph, key=lambda node: (-graph.degree[node], node))
    source = ranked[0] if name == "capacity" else seed % len(graph)
    unavailable = frozenset(ranked[:2]) - {source} if name == "unavailability" else frozenset()
    return Scenario(name, seed, graph, source, unavailable)


def simulate(scenario: Scenario, mode: str, policy: str) -> Result:
    available = set(scenario.graph) - set(scenario.unavailable)
    reachable = nx.node_connected_component(scenario.graph.subgraph(available), scenario.source) - {scenario.source}
    seen = {scenario.source}
    queue = deque([(scenario.source, None, 0)])
    sends = duplicates = new_reach = max_delay = 0
    events: list[tuple[int, int, int]] = []
    while queue:
        sender, incoming, depth = queue.popleft()
        eligible = sorted(n for n in scenario.graph.neighbors(sender) if n != incoming and n in available)
        requested = fanout(policy, mode, len(eligible))
        actual = min(requested, len(eligible))
        events.append((len(eligible), requested, actual))
        # Stable-hash ordering is the deterministic abstraction of the canonical
        # unweighted sample-without-replacement selector, identical for policies.
        selected = sorted(eligible, key=lambda peer: stable_key(scenario.seed, sender, depth, peer))[:actual]
        for peer in selected:
            sends += 1
            if peer in seen:
                duplicates += 1
            else:
                seen.add(peer)
                new_reach += 1
                max_delay = max(max_delay, depth + 1)
                queue.append((peer, sender, depth + 1))
    decisions = len(events)
    over = sum(ne > requested for ne, requested, _ in events)
    mean = lambda values: statistics.mean(values) if values else 0.0
    usage = {candidate: decisions if mode == candidate else 0 for candidate in MODES}
    return Result(
        policy, scenario.seed, scenario.name, mode,
        len(seen - {scenario.source}) / len(reachable) if reachable else 1.0,
        max_delay, sends, duplicates, new_reach,
        new_reach / sends if sends else 0.0, decisions, over,
        over / decisions if decisions else 0.0,
        mean([x[0] for x in events]), mean([x[1] for x in events]),
        mean([x[2] for x in events]), mean([x[0] - x[2] for x in events]),
        usage["LOW"], usage["MODERATE"], usage["HIGH"],
    )


def raw_results() -> list[Result]:
    return [simulate(build_scenario(scenario, seed), mode, policy)
            for seed in SEEDS for scenario in SCENARIOS
            for mode, _z in Z_CASES for policy in POLICIES]


def average(rows: list[dict[str, object]], keys: tuple[str, ...]) -> dict[str, object]:
    item = {key: rows[0][key] for key in keys}
    for metric in NUMERIC_METRICS:
        item[metric] = statistics.mean(float(row[metric]) for row in rows)
    return item


def grouped(rows: list[dict[str, object]], keys: tuple[str, ...]) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return [average(groups[key], keys) for key in sorted(groups)]


def ratio(value: float, base: float, upper: float) -> float | None:
    denominator = upper - base
    return (value - base) / denominator if abs(denominator) > 1e-12 else None


def decorate(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    by_policy = {str(row["policy"]): row for row in summary}
    s0, s2 = by_policy["S0"], by_policy["S2"]
    for row in summary:
        row["delta_delivery"] = float(row["delivery_ratio"]) - float(s0["delivery_ratio"])
        row["delta_sends"] = float(row["send_attempts"]) - float(s0["send_attempts"])
        row["delta_duplicates"] = float(row["duplicates"]) - float(s0["duplicates"])
        row["delivery_recovery"] = ratio(float(row["delivery_ratio"]), float(s0["delivery_ratio"]), float(s2["delivery_ratio"]))
        row["send_cost"] = ratio(float(row["send_attempts"]), float(s0["send_attempts"]), float(s2["send_attempts"]))
        row["duplicate_cost"] = ratio(float(row["duplicates"]), float(s0["duplicates"]), float(s2["duplicates"]))
    return summary


def select(summary: list[dict[str, object]], per_seed: list[dict[str, object]]) -> tuple[str, str | None]:
    by_policy = {str(row["policy"]): row for row in summary}
    seeds = {(str(row["policy"]), int(row["seed"])): row for row in per_seed}
    eligible = []
    for policy in ("S5-C5", "S5-C6", "S5-C7"):
        row = by_policy[policy]
        recovery, send_cost, duplicate_cost = row["delivery_recovery"], row["send_cost"], row["duplicate_cost"]
        consistent = sum(float(seeds[policy, seed]["delivery_ratio"]) >= float(seeds["S0", seed]["delivery_ratio"]) - 1e-12 for seed in SEEDS) >= 4
        if (recovery is not None and recovery >= 0.5 and send_cost is not None
                and send_cost <= recovery and (duplicate_cost is None or duplicate_cost <= recovery)
                and consistent):
            eligible.append(policy)
    if not eligible:
        return "D. NO CLEAR BOUNDED WINNER", None
    winner = eligible[0]  # smallest cap satisfying all predeclared gates
    return {"S5-C5": "A. S5-C5 selected", "S5-C6": "B. S5-C6 selected", "S5-C7": "C. S5-C7 selected"}[winner], winner


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def markdown_table(rows: list[dict[str, object]]) -> str:
    columns = ("policy", "delivery_ratio", "propagation_delay", "send_attempts", "duplicates", "new_reach_efficiency", "delta_delivery", "delta_sends")
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(f"{row[c]:.6f}" if isinstance(row[c], float) else str(row[c]) for c in columns) + " |")
    return "\n".join(lines)


def mapping_rows() -> list[dict[str, object]]:
    return [{"Ne": ne, **{policy: "/".join(str(fanout(policy, mode, ne)) for mode in MODES) for policy in POLICIES}} for ne in NE_CASES]


def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    raw = [asdict(result) for result in raw_results()]
    per_seed = grouped(raw, ("policy", "seed"))
    summary = decorate(grouped(raw, ("policy",)))
    outcome, winner = select(summary, per_seed)
    write_csv(output_dir / "fanout_mapping.csv", mapping_rows())
    write_csv(output_dir / "per_run.csv", raw)
    write_csv(output_dir / "per_seed.csv", per_seed)
    write_csv(output_dir / "aggregate_summary.csv", summary)
    report = "# K5 shortest actuator screening\n\n" + markdown_table(summary) + f"\n\nSelection outcome: **{outcome}**\n"
    if winner:
        report += f"\nProposed GKE comparison: `S0 vs {winner}`\n"
    else:
        report += "\nRetain S0; no GKE comparison is proposed.\n"
    (output_dir / "results.md").write_text(report, encoding="utf-8")
    manifest = {"seeds": SEEDS, "scenarios": SCENARIOS, "modes": MODES, "policies": POLICIES, "selection_outcome": outcome, "selected_candidate": winner}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Fanout mapping (LOW/MODERATE/HIGH):")
    for row in mapping_rows(): print(row)
    print(f"Selection outcome: {outcome}")
    print(f"Results: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
