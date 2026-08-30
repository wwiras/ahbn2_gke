#!/usr/bin/env python3
"""K5 Phase 2: deterministic plain-Python S0 versus S5 screening.

Production AHBN is imported read-only to create the canonical controller trace.
The candidate actuator and the dissemination laboratory live entirely here.
"""

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
from typing import Callable, Iterable

import networkx as nx

# Direct execution places ``scripts/`` rather than the repository root on
# sys.path. Add only that root so the canonical controller can be read safely.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.ahbn_controller import AHBNState, CanonicalAHBNController


SEEDS = (42, 43, 44, 45, 46)
TREATMENTS = ("S0", "S5")
MESSAGE_COUNT = 120
SOURCE = 0
N = 20
M = 2


def actuator_s0(z: float) -> int:
    """Exact experimental mirror of canonical 2/3/4 quantization."""
    if z <= -0.25 or math.isclose(z, -0.25, rel_tol=0.0, abs_tol=1e-12):
        return 2
    if z >= 0.25 or math.isclose(z, 0.25, rel_tol=0.0, abs_tol=1e-12):
        return 4
    return 3


def actuator_s5(z: float) -> int:
    if z <= -0.25:
        return 2
    if z < 0.25:
        return 3
    if z < 0.90:
        return 4
    if z < 1.50:
        return 5
    return 6


def controller_score(d_hat: float, l_hat: float, u_hat: float, c_hat: float) -> float:
    """Frozen canonical equation, exposed so its invariance is directly tested."""
    return -d_hat + l_hat + u_hat + c_hat


def stable_unit(*parts: object) -> float:
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") / 2**64


def stable_key(*parts: object) -> int:
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:16], "big")


def observation(seed: int, message: int) -> tuple[float, float, float, float]:
    """Fixed exogenous load schedule; identical for paired treatments.

    Four 30-message blocks create baseline, elevated, severe, and recovery
    pressure. Small deterministic jitter prevents an artificial constant trace.
    No observation depends on treatment or dissemination results.
    """
    block = message // 30
    centres = (
        (0.55, 0.25, 0.30, 0.15),
        (0.20, 0.75, 0.80, 0.55),
        (0.05, 0.95, 0.95, 0.85),
        (0.35, 0.40, 0.45, 0.25),
    )[block]
    values = []
    for index, centre in enumerate(centres):
        jitter = (stable_unit(seed, message, index, "observation") - 0.5) * 0.10
        values.append(max(0.0, min(1.0, centre + jitter)))
    return tuple(values)  # type: ignore[return-value]


def canonical_trace(seed: int, count: int = MESSAGE_COUNT) -> list[dict[str, float | int]]:
    controller, state = CanonicalAHBNController(), AHBNState()
    rows = []
    for message in range(count):
        decision = controller.update(state, *observation(seed, message))
        mirrored = controller_score(decision.d_hat, decision.l_hat, decision.u_hat, decision.c_hat)
        if not math.isclose(decision.score, mirrored, rel_tol=0.0, abs_tol=1e-12):
            raise AssertionError("canonical controller equation changed")
        rows.append({
            "seed": seed, "message": message,
            "d_hat": decision.d_hat, "l_hat": decision.l_hat,
            "u_hat": decision.u_hat, "c_hat": decision.c_hat,
            "z": decision.score,
        })
    return rows


@dataclass(frozen=True)
class MessageResult:
    treatment: str
    seed: int
    message: int
    z: float
    requested_fanout: int
    delivery_ratio: float
    forwarding_attempts: int
    total_forwards: int
    duplicates: int
    new_reaches: int
    new_reach_efficiency: float
    propagation_delay: int


def simulate_message(
    graph: nx.Graph, seed: int, message: int, z: float, treatment: str
) -> MessageResult:
    """Disseminate once with canonical unweighted sample-without-replacement semantics."""
    actuator: Callable[[float], int] = actuator_s0 if treatment == "S0" else actuator_s5
    requested = actuator(z)
    seen = {SOURCE}
    queue = deque([(SOURCE, None, 0)])
    attempts = duplicates = new_reaches = max_delay = 0
    while queue:
        sender, incoming, depth = queue.popleft()
        eligible = sorted(peer for peer in graph.neighbors(sender) if peer != incoming)
        selected = sorted(
            eligible,
            key=lambda peer: stable_key(seed, message, sender, depth, peer, "peer-order"),
        )[: min(requested, len(eligible))]
        for peer in selected:
            attempts += 1
            if peer in seen:
                duplicates += 1
            else:
                seen.add(peer)
                new_reaches += 1
                max_delay = max(max_delay, depth + 1)
                queue.append((peer, sender, depth + 1))
    return MessageResult(
        treatment, seed, message, z, requested, (len(seen) - 1) / (len(graph) - 1),
        attempts, attempts, duplicates, new_reaches,
        new_reaches / attempts if attempts else 0.0, max_delay,
    )


def paired_seed(seed: int, count: int = MESSAGE_COUNT) -> tuple[list[MessageResult], list[dict[str, float | int]]]:
    graph = nx.freeze(nx.barabasi_albert_graph(N, M, seed=seed))
    trace = canonical_trace(seed, count)
    rows = [
        simulate_message(graph, seed, int(state["message"]), float(state["z"]), treatment)
        for state in trace for treatment in TREATMENTS
    ]
    return rows, trace


def summarize_run(rows: Iterable[MessageResult]) -> list[dict[str, float | int | str]]:
    groups: dict[tuple[int, str], list[MessageResult]] = defaultdict(list)
    for row in rows:
        groups[row.seed, row.treatment].append(row)
    answer = []
    for (seed, treatment), group in sorted(groups.items()):
        attempts = sum(row.forwarding_attempts for row in group)
        new = sum(row.new_reaches for row in group)
        answer.append({
            "seed": seed, "treatment": treatment,
            "delivery_ratio": statistics.mean(row.delivery_ratio for row in group),
            "total_forwards": sum(row.total_forwards for row in group),
            "forwarding_attempts": attempts,
            "duplicates": sum(row.duplicates for row in group),
            "new_reaches": new,
            "new_reach_efficiency": new / attempts if attempts else 0.0,
            "propagation_delay": statistics.mean(row.propagation_delay for row in group),
        })
    return answer


def paired_table(per_run: list[dict[str, float | int | str]]) -> list[dict[str, float | int]]:
    indexed = {(int(row["seed"]), str(row["treatment"])): row for row in per_run}
    metrics = ("delivery_ratio", "total_forwards", "duplicates", "new_reach_efficiency", "propagation_delay")
    output = []
    for seed in SEEDS:
        item: dict[str, float | int] = {"seed": seed}
        for metric in metrics:
            s0 = float(indexed[seed, "S0"][metric])
            s5 = float(indexed[seed, "S5"][metric])
            item[f"S0_{metric}"] = s0
            item[f"S5_{metric}"] = s5
            item[f"delta_{metric}"] = (100.0 * (s5 - s0) if metric == "delivery_ratio" else s5 - s0)
        output.append(item)
    return output


def descriptive(per_run: list[dict[str, float | int | str]]) -> dict[str, object]:
    result: dict[str, object] = {}
    metrics = ("delivery_ratio", "total_forwards", "duplicates", "new_reach_efficiency", "propagation_delay")
    for treatment in TREATMENTS:
        selected = [row for row in per_run if row["treatment"] == treatment]
        result[treatment] = {}
        for metric in metrics:
            values = [float(row[metric]) for row in selected]
            result[treatment][metric] = {  # type: ignore[index]
                "mean": statistics.mean(values), "median": statistics.median(values),
                "min": min(values), "max": max(values), "stdev": statistics.stdev(values),
            }
    return result


def classify(paired: list[dict[str, float | int]], occupancy: Counter[int]) -> tuple[str, str]:
    if occupancy[5] + occupancy[6] == 0:
        return "D — ambiguous", "S5 never activated k=5 or k=6."
    delivery = [float(row["delta_delivery_ratio"]) for row in paired]
    forwards = [float(row["delta_total_forwards"]) for row in paired]
    duplicates = [float(row["delta_duplicates"]) for row in paired]
    efficiency = [float(row["delta_new_reach_efficiency"]) for row in paired]
    if min(delivery) < -0.1:
        return "C — worse", "Delivery decreased by more than 0.1 percentage points for at least one seed."
    improved = sum(delta > 0.1 for delta in delivery)
    mean_delivery = statistics.mean(delivery)
    mean_forward_cost = statistics.mean(forwards)
    mean_duplicate_cost = statistics.mean(duplicates)
    if improved >= 4 and mean_delivery >= 0.5 and statistics.mean(efficiency) >= -0.05:
        return "A — promising", "Delivery improved across most seeds with defensible mean efficiency."
    if max(delivery) <= 0.1 and (mean_forward_cost > 0 or mean_duplicate_cost > 0):
        return "B — no meaningful benefit", "Delivery was effectively unchanged while traffic increased."
    return "D — ambiguous", "The screen showed inconsistent or marginal seed-level trade-offs; do not add designs automatically."


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    messages: list[MessageResult] = []
    traces: list[dict[str, float | int]] = []
    for seed in SEEDS:
        seed_rows, seed_trace = paired_seed(seed)
        messages.extend(seed_rows)
        traces.extend(seed_trace)
    per_run = summarize_run(messages)
    paired = paired_table(per_run)
    occupancy = Counter(actuator_s5(float(row["z"])) for row in traces)
    occupancy_rows = [{"fanout": k, "count": occupancy[k], "percentage": 100.0 * occupancy[k] / len(traces)} for k in range(2, 7)]
    outcome, reason = classify(paired, occupancy)
    summary = {
        "experiment": "K5 Phase 2 S0 versus S5", "seeds": list(SEEDS),
        "n": N, "ba_m": M, "source": SOURCE, "messages_per_seed": MESSAGE_COUNT,
        "thresholds": {"T3": 0.90, "T4": 1.50},
        "states_z_ge_0_90": sum(float(row["z"]) >= 0.90 for row in traces),
        "states_z_ge_1_50": sum(float(row["z"]) >= 1.50 for row in traces),
        "descriptive_statistics": descriptive(per_run), "outcome": outcome, "reason": reason,
    }
    write_csv(output_dir / "per_run_results.csv", per_run)  # type: ignore[arg-type]
    write_csv(output_dir / "paired_results.csv", paired)  # type: ignore[arg-type]
    write_csv(output_dir / "actuator_occupancy.csv", occupancy_rows)  # type: ignore[arg-type]
    write_csv(output_dir / "z_states.csv", traces)  # type: ignore[arg-type]
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output_dir / "README.md").write_text(
        "# K5 Phase 2 actuator screening\n\n"
        f"Outcome: **{outcome}**\n\n{reason}\n\n"
        "Delivery deltas in `paired_results.csv` are percentage points. "
        "All other deltas are S5 minus S0 in native units.\n",
        encoding="utf-8",
    )
    print(f"{outcome}: {reason}")
    print(f"Results: {output_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=Path("outputs/k5_phase2_actuator_screening"),
    )
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
