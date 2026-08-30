#!/usr/bin/env python3
"""Deterministic, plain-Python K5 H1/H2 actuator screening laboratory.

This module mirrors the frozen controller thresholds but never imports or mutates
production AHBN state.  Strategies differ only in fanout and/or peer ranking.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import networkx as nx


MODES = ("LOW", "MODERATE", "HIGH")
CANONICAL_FANOUT = {"LOW": 2, "MODERATE": 3, "HIGH": 4}
Z_CASES = (
    ("low", -0.50),
    ("low_boundary", -0.25),
    ("just_above_low", math.nextafter(-0.25, math.inf)),
    ("moderate", 0.0),
    ("just_below_high", math.nextafter(0.25, -math.inf)),
    ("high_boundary", 0.25),
    ("high", 0.50),
)
S4_CONFIGS = {
    "S4_cap5": {"rho": {"LOW": 1 / 3, "MODERATE": 0.60, "HIGH": 0.80}, "cap": {"LOW": 3, "MODERATE": 4, "HIGH": 5}},
    "S4_cap6": {"rho": {"LOW": 1 / 3, "MODERATE": 0.60, "HIGH": 0.80}, "cap": {"LOW": 3, "MODERATE": 5, "HIGH": 6}},
    "S4_cap7": {"rho": {"LOW": 1 / 3, "MODERATE": 0.60, "HIGH": 0.80}, "cap": {"LOW": 4, "MODERATE": 6, "HIGH": 7}},
    "S4_cap8": {"rho": {"LOW": 1 / 3, "MODERATE": 0.60, "HIGH": 0.80}, "cap": {"LOW": 4, "MODERATE": 7, "HIGH": 8}},
}
STRATEGIES = ("S0", "S1", "S2", "S3", *S4_CONFIGS)


def mode_for_z(z: float) -> str:
    """Frozen thresholds: both exact boundaries belong to the outer regions."""
    if z <= -0.25:
        return "LOW"
    if z >= 0.25:
        return "HIGH"
    return "MODERATE"


def stable_key(*parts: object) -> int:
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:16], "big")


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    graph: nx.Graph
    source: int
    unavailable: frozenset[int]


@dataclass
class Metrics:
    scenario: str
    seed: int
    z_case: str
    z: float
    mode: str
    strategy: str
    delivery_ratio: float
    send_attempts: int
    successful_transmissions: int
    new_reaches: int
    duplicate_receives: int
    eta_new: float
    duplicates_per_delivered_node: float
    sends_per_delivered_node: float
    mean_h1_gap: float
    median_h1_gap: float
    p95_h1_gap: float
    h2_overlap: float
    overlap_cost: float


def build_scenario(name: str, seed: int, n: int = 20, m: int = 2) -> Scenario:
    """Generate one immutable BA scenario; callers replay it across strategies."""
    if name == "multipath_convergence":
        m = 3  # One bounded denser condition to expose converging paths.
    graph = nx.freeze(nx.barabasi_albert_graph(n, m, seed=seed))
    ranked = sorted(graph, key=lambda node: (-graph.degree[node], node))
    source = ranked[0] if name == "capacity_opportunity" else seed % n
    unavailable: frozenset[int] = frozenset()
    if name == "limited_unavailability":
        unavailable = frozenset([node for node in ranked if node != source][:2])
    if name not in {"clean_propagation", "multipath_convergence", "capacity_opportunity", "limited_unavailability"}:
        raise ValueError(f"unknown scenario: {name}")
    return Scenario(name, seed, graph, source, unavailable)


def fanout(strategy: str, mode: str, ne: int) -> int:
    floor = CANONICAL_FANOUT[mode]
    if strategy in {"S0", "S1"}:
        return min(ne, floor)
    if strategy in {"S2", "S3"}:
        raw = {"LOW": max(2, math.ceil(ne / 3)), "MODERATE": max(3, math.ceil(2 * ne / 3)), "HIGH": ne}[mode]
        return min(ne, raw)
    cfg = S4_CONFIGS[strategy]
    return min(ne, cfg["cap"][mode], max(floor, math.ceil(cfg["rho"][mode] * ne)))


def percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def simulate(scenario: Scenario, z_case: str, z: float, strategy: str) -> Metrics:
    """Replay one message with FIFO forwarding and message-scoped local history."""
    mode = mode_for_z(z)
    source = scenario.source
    available = set(scenario.graph) - set(scenario.unavailable)
    if source not in available:
        raise ValueError("source cannot be unavailable")
    reachable = nx.node_connected_component(scenario.graph.subgraph(available), source) - {source}
    seen = {source}
    queue = deque([(source, None, 0)])
    selected_count: dict[tuple[int, int], int] = defaultdict(int)
    duplicate_history: dict[tuple[int, int], int] = defaultdict(int)
    new_history: dict[tuple[int, int], int] = defaultdict(int)
    attempts = successful = new_reaches = duplicates = 0
    h1_gaps: list[float] = []
    smart = strategy in {"S1", "S3", *S4_CONFIGS}

    # A small immutable prehistory represents locally retained ACK/use counters
    # from earlier traffic. It is identical for every strategy and contains no
    # current-message possession or future-state information.
    for sender in scenario.graph:
        for peer in scenario.graph.neighbors(sender):
            duplicate_history[sender, peer] = stable_key(scenario.seed, "prior-dup", sender, peer) % 3
            new_history[sender, peer] = stable_key(scenario.seed, "prior-new", sender, peer) % 3
            selected_count[sender, peer] = stable_key(scenario.seed, "prior-use", sender, peer) % 2

    while queue:
        sender, incoming, round_no = queue.popleft()
        eligible = sorted(
            node for node in scenario.graph.neighbors(sender)
            if node != incoming and node in available
        )
        ne = len(eligible)
        if not ne:
            continue
        k = fanout(strategy, mode, ne)
        h1_gaps.append(max(0.0, 1.0 - k / ne))
        if smart:
            # All terms are sender-local: returned NEW/DUP result and recent use.
            def rank(peer: int) -> tuple[float, int]:
                score = (-2.0 * duplicate_history[sender, peer]
                         -1.0 * selected_count[sender, peer]
                         +1.0 * new_history[sender, peer])
                return (-score, stable_key(scenario.seed, "msg-0", sender, round_no, peer))
            selected = sorted(eligible, key=rank)[:k]
        else:
            # Deterministic equivalent of canonical unweighted random sampling.
            selected = sorted(eligible, key=lambda peer: stable_key(scenario.seed, "msg-0", sender, round_no, peer))[:k]

        for peer in selected:
            attempts += 1
            successful += 1
            selected_count[sender, peer] += 1
            if peer in seen:
                duplicates += 1
                duplicate_history[sender, peer] += 1
            else:
                seen.add(peer)
                new_reaches += 1
                new_history[sender, peer] += 1
                queue.append((peer, sender, round_no + 1))

    delivered = len(seen - {source})
    receives = new_reaches + duplicates
    delivery_ratio = delivered / len(reachable) if reachable else 1.0
    return Metrics(
        scenario.name, scenario.seed, z_case, z, mode, strategy,
        delivery_ratio, attempts, successful, new_reaches, duplicates,
        new_reaches / attempts if attempts else 0.0,
        duplicates / delivered if delivered else 0.0,
        attempts / delivered if delivered else 0.0,
        statistics.mean(h1_gaps) if h1_gaps else 0.0,
        statistics.median(h1_gaps) if h1_gaps else 0.0,
        percentile95(h1_gaps),
        duplicates / receives if receives else 0.0,
        1.0 - new_reaches / successful if successful else 0.0,
    )


def aggregate(rows: Iterable[Metrics]) -> list[dict[str, object]]:
    groups: dict[str, list[Metrics]] = defaultdict(list)
    for row in rows:
        groups[row.strategy].append(row)
    result = []
    metric_names = [key for key in asdict(next(iter(groups.values()))[0]) if key not in {"scenario", "seed", "z_case", "z", "mode", "strategy"}]
    for strategy in STRATEGIES:
        item: dict[str, object] = {"strategy": strategy, "runs": len(groups[strategy])}
        for name in metric_names:
            item[name] = statistics.mean(float(getattr(row, name)) for row in groups[strategy])
        result.append(item)
    return result


def deltas(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    anchor = next(row for row in summary if row["strategy"] == "S0")
    metrics = ("delivery_ratio", "send_attempts", "duplicate_receives", "eta_new", "mean_h1_gap", "h2_overlap")
    output = []
    for row in summary:
        item: dict[str, object] = {"strategy": row["strategy"]}
        for name in metrics:
            base, value = float(anchor[name]), float(row[name])
            item[f"delta_{name}"] = value - base
            item[f"pct_{name}"] = ((value - base) / base * 100.0) if base else None
        item["delivery_percentage_point_delta"] = 100.0 * (float(row["delivery_ratio"]) - float(anchor["delivery_ratio"]))
        output.append(item)
    return output


def pareto(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    objectives = {"delivery_ratio": 1, "eta_new": 1, "send_attempts": -1, "duplicate_receives": -1, "mean_h1_gap": -1, "h2_overlap": -1}
    answer = []
    for candidate in summary:
        dominators = []
        for other in summary:
            if other is candidate:
                continue
            comparisons = [objectives[k] * float(other[k]) >= objectives[k] * float(candidate[k]) - 1e-12 for k in objectives]
            strict = [objectives[k] * float(other[k]) > objectives[k] * float(candidate[k]) + 1e-12 for k in objectives]
            if all(comparisons) and any(strict):
                dominators.append(str(other["strategy"]))
        answer.append({"strategy": candidate["strategy"], "pareto_frontier": not dominators, "dominated_by": ";".join(dominators)})
    return answer


def choose_s4(summary: list[dict[str, object]], frontier: list[dict[str, object]]) -> tuple[dict[str, object], str]:
    """Apply explicit gates, then use efficiency/cost/simplicity tie-breaks."""
    anchor = next(row for row in summary if row["strategy"] == "S0")
    on_frontier = {row["strategy"] for row in frontier if row["pareto_frontier"]}
    candidates = []
    for row in summary:
        if not str(row["strategy"]).startswith("S4_"):
            continue
        delivery_gate = float(row["delivery_ratio"]) >= float(anchor["delivery_ratio"]) - 0.01
        h1_gate = float(row["mean_h1_gap"]) < float(anchor["mean_h1_gap"]) - 1e-12
        h2_gate = float(row["h2_overlap"]) <= float(anchor["h2_overlap"]) + 0.02
        if delivery_gate and h1_gate and h2_gate:
            candidates.append(row)
    pool = candidates or [row for row in summary if str(row["strategy"]).startswith("S4_")]
    # Pareto membership, efficiency, cost, then the lower cap encode Gates 4/5.
    best = max(pool, key=lambda row: (
        row["strategy"] in on_frontier,
        float(row["eta_new"]),
        float(row["delivery_ratio"]),
        -float(row["send_attempts"]),
        -float(row["duplicate_receives"]),
        -int(str(row["strategy"]).removeprefix("S4_cap")),
    ))
    reason = "passed delivery (-1 pp tolerance), H1, and H2 (+0.02 tolerance) gates" if candidates else "no S4 passed every gate; selected least-cost fallback"
    return best, reason


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_screen(output_dir: Path, seeds: Iterable[int] = range(42, 47)) -> None:
    scenarios = ("clean_propagation", "multipath_convergence", "capacity_opportunity", "limited_unavailability")
    rows: list[Metrics] = []
    for seed in seeds:
        generated = {name: build_scenario(name, seed) for name in scenarios}
        for scenario in generated.values():
            for z_case, z in Z_CASES:
                for strategy in STRATEGIES:
                    rows.append(simulate(scenario, z_case, z, strategy))
    summary = aggregate(rows)
    delta_rows = deltas(summary)
    frontier = pareto(summary)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "per_run.csv", [asdict(row) for row in rows])
    write_csv(output_dir / "aggregate_summary.csv", summary)
    write_csv(output_dir / "deltas_vs_s0.csv", delta_rows)
    write_csv(output_dir / "pareto_summary.csv", frontier)
    best_s4, best_reason = choose_s4(summary, frontier)
    manifest = {"seeds": list(seeds), "scenarios": list(scenarios), "z_cases": list(Z_CASES), "strategies": list(STRATEGIES), "s4_grid": S4_CONFIGS, "best_s4_by_gated_tiebreak": best_s4["strategy"], "best_s4_reason": best_reason}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    lines = ["# K5 H1/H2 actuator screening results", "", "Source excluded from delivery numerator and reachable-population denominator.", "", f"Best S4 parameterization: **{best_s4['strategy']}** ({best_reason}).", "", "See `aggregate_summary.csv`, `deltas_vs_s0.csv`, and `pareto_summary.csv` for the decision evidence."]
    (output_dir / "screening_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
