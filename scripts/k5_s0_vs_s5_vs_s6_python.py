#!/usr/bin/env python3
"""Matched K5 S0/S5/S6 plain-Python actuator screen."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ahbn_controller import AHBNState, CanonicalAHBNController

SEEDS = (42, 43, 44, 45, 46)
TREATMENTS = ("S0", "S5-f2", "S5-f3", "S5-f4", "S5-f5", "S5-f6", "S6")
MESSAGE_COUNT, SOURCE, N, M = 120, 0, 20, 2
METRICS = ("delivery_ratio", "propagation_delay", "total_forwards", "duplicates", "new_reach_efficiency")


def s0_requested_fanout(z: float) -> int:
    """Exact validated Phase-2 S0 mapping."""
    if z <= -0.25 or math.isclose(z, -0.25, rel_tol=0.0, abs_tol=1e-12):
        return 2
    if z >= 0.25 or math.isclose(z, 0.25, rel_tol=0.0, abs_tol=1e-12):
        return 4
    return 3


def robustness_level(z: float) -> int:
    """Frozen five-bin S5 mapping relabelled from fanout 2..6 to level 1..5."""
    if z <= -0.25:
        return 1
    if z < 0.25:
        return 2
    if z < 0.90:
        return 3
    if z < 1.50:
        return 4
    return 5


def topology_fanout(k: int, ne: int) -> int:
    if k not in range(1, 6) or ne < 0:
        raise ValueError(f"invalid S6 request: {k=}, {ne=}")
    return 0 if ne <= 0 else min(ne, max(1, math.ceil(k * ne / 5)))


def actual_fanout(treatment: str, z: float, ne: int) -> tuple[int, int]:
    """Return (requested robustness level/budget, actual selected-peer count)."""
    if treatment == "S0":
        requested = s0_requested_fanout(z)
        return requested, min(requested, ne)
    if treatment.startswith("S5-f"):
        requested = int(treatment.removeprefix("S5-f"))
        if treatment not in TREATMENTS:
            raise ValueError(f"unsupported treatment: {treatment}")
        return requested, min(requested, ne)
    if treatment == "S6":
        k = robustness_level(z)
        return k, topology_fanout(k, ne)
    raise ValueError(f"unsupported treatment: {treatment}")


def stable_unit(*parts: object) -> float:
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") / 2**64


def stable_key(*parts: object) -> int:
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:16], "big")


def observation(seed: int, message: int) -> tuple[float, float, float, float]:
    centres = ((.55, .25, .30, .15), (.20, .75, .80, .55),
               (.05, .95, .95, .85), (.35, .40, .45, .25))[message // 30]
    values = [max(0.0, min(1.0, centre + (stable_unit(seed, message, i, "observation") - .5) * .10))
              for i, centre in enumerate(centres)]
    return tuple(values)  # type: ignore[return-value]


def canonical_trace(seed: int) -> list[dict[str, float | int]]:
    controller, state, rows = CanonicalAHBNController(), AHBNState(), []
    for message in range(MESSAGE_COUNT):
        decision = controller.update(state, *observation(seed, message))
        expected = -decision.d_hat + decision.l_hat + decision.u_hat + decision.c_hat
        if not math.isclose(decision.score, expected, rel_tol=0.0, abs_tol=1e-12):
            raise AssertionError("canonical controller equation changed")
        rows.append({"seed": seed, "message": message, "z": decision.score,
                     "d_hat": decision.d_hat, "l_hat": decision.l_hat,
                     "u_hat": decision.u_hat, "c_hat": decision.c_hat,
                     "robustness_level_k": robustness_level(decision.score)})
    return rows


@dataclass(frozen=True)
class MessageResult:
    treatment: str
    seed: int
    message: int
    z: float
    delivery_ratio: float
    propagation_delay: int
    total_forwards: int
    duplicates: int
    new_reaches: int
    new_reach_efficiency: float


def simulate_message(graph: nx.Graph, seed: int, message: int, z: float, treatment: str):
    seen, queue = {SOURCE}, deque([(SOURCE, None, 0)])
    forwards = duplicates = reaches = max_delay = 0
    diagnostics = []
    while queue:
        sender, incoming, depth = queue.popleft()
        eligible = sorted(peer for peer in graph.neighbors(sender) if peer != incoming)
        requested, actual = actual_fanout(treatment, z, len(eligible))
        selected = sorted(eligible, key=lambda peer: stable_key(seed, message, sender, depth, peer, "peer-order"))[:actual]
        diagnostics.append({"treatment": treatment, "seed": seed, "message": message,
                            "sender": sender, "depth": depth, "z": z,
                            "robustness_level_k": robustness_level(z) if treatment == "S6" else "",
                            "eligible_neighbors_Ne": len(eligible), "requested_level_or_budget": requested,
                            "calculated_actual_fanout": actual, "actual_selected_peer_count": len(selected)})
        for peer in selected:
            forwards += 1
            if peer in seen:
                duplicates += 1
            else:
                seen.add(peer); reaches += 1; max_delay = max(max_delay, depth + 1)
                queue.append((peer, sender, depth + 1))
    result = MessageResult(treatment, seed, message, z, (len(seen) - 1) / (len(graph) - 1),
                           max_delay, forwards, duplicates, reaches, reaches / forwards if forwards else 0.0)
    return result, diagnostics


def raw_results():
    messages, diagnostics, traces = [], [], []
    for seed in SEEDS:
        graph = nx.freeze(nx.barabasi_albert_graph(N, M, seed=seed))
        trace = canonical_trace(seed); traces.extend(trace)
        for state in trace:
            for treatment in TREATMENTS:
                result, events = simulate_message(graph, seed, int(state["message"]), float(state["z"]), treatment)
                messages.append(result); diagnostics.extend(events)
    return messages, diagnostics, traces


def summarize(messages: list[MessageResult]) -> list[dict[str, object]]:
    groups = defaultdict(list)
    for row in messages:
        groups[row.seed, row.treatment].append(row)
    output = []
    for (seed, treatment), rows in sorted(groups.items()):
        forwards = sum(row.total_forwards for row in rows)
        reaches = sum(row.new_reaches for row in rows)
        output.append({"seed": seed, "treatment": treatment,
                       "delivery_ratio": statistics.mean(row.delivery_ratio for row in rows),
                       "propagation_delay": statistics.mean(row.propagation_delay for row in rows),
                       "total_forwards": forwards, "send_attempts": forwards,
                       "duplicates": sum(row.duplicates for row in rows), "new_reaches": reaches,
                       "new_reach_efficiency": reaches / forwards if forwards else 0.0})
    return output


def aggregate(per_seed: list[dict[str, object]]) -> list[dict[str, object]]:
    by_treatment = defaultdict(list)
    for row in per_seed: by_treatment[str(row["treatment"])].append(row)
    base = by_treatment["S0"]
    output = []
    for treatment in TREATMENTS:
        rows = by_treatment[treatment]
        item = {"treatment": treatment}
        for metric in METRICS:
            item[metric] = statistics.mean(float(row[metric]) for row in rows)
        item["delta_delivery_vs_S0_pp"] = 100 * (float(item["delivery_ratio"]) - statistics.mean(float(r["delivery_ratio"]) for r in base))
        item["delta_forwards_vs_S0"] = float(item["total_forwards"]) - statistics.mean(float(r["total_forwards"]) for r in base)
        item["delta_duplicates_vs_S0"] = float(item["duplicates"]) - statistics.mean(float(r["duplicates"]) for r in base)
        output.append(item)
    return output


def select_fixed(summary: list[dict[str, object]]) -> str:
    fixed = [row for row in summary if str(row["treatment"]).startswith("S5-f")]
    return str(max(fixed, key=lambda r: (float(r["delivery_ratio"]), -float(r["total_forwards"])))["treatment"])


def decision(per_seed: list[dict[str, object]], summary: list[dict[str, object]]) -> tuple[str, str, str]:
    selected = select_fixed(summary)
    index = {(int(r["seed"]), str(r["treatment"])): r for r in per_seed}
    s6 = next(r for r in summary if r["treatment"] == "S6")
    fixed = next(r for r in summary if r["treatment"] == selected)
    s0 = next(r for r in summary if r["treatment"] == "S0")
    gain_s0 = 100 * (float(s6["delivery_ratio"]) - float(s0["delivery_ratio"]))
    gain_fixed = 100 * (float(s6["delivery_ratio"]) - float(fixed["delivery_ratio"]))
    consistent_s0 = sum(float(index[seed, "S6"]["delivery_ratio"]) >= float(index[seed, "S0"]["delivery_ratio"]) for seed in SEEDS)
    consistent_fixed = sum(float(index[seed, "S6"]["delivery_ratio"]) >= float(index[seed, selected]["delivery_ratio"]) for seed in SEEDS)
    efficiency_cost = float(s6["new_reach_efficiency"]) - max(float(s0["new_reach_efficiency"]), float(fixed["new_reach_efficiency"]))
    if gain_s0 >= .5 and gain_fixed >= .5 and consistent_s0 >= 4 and consistent_fixed >= 4 and efficiency_cost >= -.05:
        return "A — S6 PROMISING FOR FINAL GKE VALIDATION", selected, "Meaningful, consistent delivery gain with bounded efficiency cost."
    return "B — S6 NOT SUFFICIENTLY BETTER; RETAIN S5/S0", selected, "S6 did not clear the predeclared delivery/consistency/efficiency gate against both comparators."


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def run(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    messages, diagnostics, traces = raw_results()
    per_seed = summarize(messages); summary = aggregate(per_seed)
    outcome, selected, reason = decision(per_seed, summary)
    write_csv(output / "per_message_results.csv", [asdict(row) for row in messages])
    write_csv(output / "per_seed_results.csv", per_seed)
    write_csv(output / "aggregate_results.csv", summary)
    write_csv(output / "actuator_diagnostics.csv", diagnostics)
    write_csv(output / "controller_states.csv", traces)
    ne = Counter(int(row["eligible_neighbors_Ne"]) for row in diagnostics)
    fanouts = Counter((str(row["treatment"]), int(row["calculated_actual_fanout"])) for row in diagnostics)
    write_csv(output / "eligible_neighbor_distribution.csv", [{"Ne": k, "count": ne[k]} for k in sorted(ne)])
    write_csv(output / "actual_fanout_distribution.csv", [{"treatment": t, "actual_fanout": f, "count": c} for (t, f), c in sorted(fanouts.items())])
    manifest = {"experiment": "K5 S0 vs S5-f2..f6 vs S6", "seeds": SEEDS, "treatments": TREATMENTS,
                "messages_per_seed": MESSAGE_COUNT, "selected_S5": selected, "decision": outcome, "reason": reason,
                "s6_formula": "0 if Ne <= 0 else min(Ne, max(1, ceil(k * Ne / 5)))"}
    (output / "summary.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Selected fixed comparator: {selected}")
    print(f"Decision: {outcome}")
    print(f"Reason: {reason}")
    print(f"Results: {output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", required=True, type=Path)
    run(parser.parse_args().output)


if __name__ == "__main__":
    main()
