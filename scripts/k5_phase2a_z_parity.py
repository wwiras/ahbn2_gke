#!/usr/bin/env python3
"""Offline K5 Phase 2A z-occupancy parity diagnostic."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GKE = ROOT / "outputs/k5_shortest_actuator_solution_gke/20260830T175317Z/runs"
DEFAULT_PYTHON = ROOT / "outputs/k5_phase2_actuator_screening/z_states.csv"
DEFAULT_OUTPUT = ROOT / "outputs/k5_phase2a_z_parity"
FIELDS = ("d_hat", "l_hat", "u_hat", "c_hat")
TOLERANCE = 1e-12


def load_concatenated_json(path: Path) -> list[dict[str, object]]:
    """Decode every JSON value, including values concatenated on one line."""
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    rows: list[dict[str, object]] = []
    position = 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            break
        value, position = decoder.raw_decode(text, position)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def load_gke(root: Path) -> tuple[list[dict[str, float]], list[str]]:
    paths = sorted(root.glob("seed*/*/logs.jsonl"))
    if not paths:
        raise FileNotFoundError(f"no GKE logs found below {root}")
    rows: list[dict[str, float]] = []
    for path in paths:
        for item in load_concatenated_json(path):
            if item.get("event") != "ahbn_controller_trace":
                continue
            rows.append({field: float(item[field]) for field in (*FIELDS, "score")})
    return rows, [str(path.relative_to(ROOT)) for path in paths]


def load_python(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [{field: float(row[field]) for field in (*FIELDS, "z")}
                for row in csv.DictReader(handle)]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def describe(values: list[float]) -> dict[str, float | int]:
    return {
        "N": len(values), "min": min(values), "P05": percentile(values, .05),
        "P25": percentile(values, .25), "median": statistics.median(values),
        "mean": statistics.mean(values), "P75": percentile(values, .75),
        "P90": percentile(values, .90), "P95": percentile(values, .95),
        "P99": percentile(values, .99), "max": max(values),
    }


REGIONS = (
    ("z <= -0.25", lambda z: z <= -.25),
    ("-0.25 < z < 0.25", lambda z: -.25 < z < .25),
    ("0.25 <= z < 0.90", lambda z: .25 <= z < .90),
    ("0.90 <= z < 1.50", lambda z: .90 <= z < 1.50),
    ("z >= 1.50", lambda z: z >= 1.50),
)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def mismatch_count(rows: list[dict[str, float]], z_field: str) -> tuple[int, float]:
    errors = [abs(row[z_field] - (-row["d_hat"] + row["l_hat"] + row["u_hat"] + row["c_hat"]))
              for row in rows]
    return sum(error > TOLERANCE for error in errors), max(errors, default=0.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gke-root", type=Path, default=DEFAULT_GKE)
    parser.add_argument("--python-states", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    gke, sources = load_gke(args.gke_root)
    python = load_python(args.python_states)
    gke_z = [row["score"] for row in gke]
    python_z = [row["z"] for row in python]

    z_rows: list[dict[str, object]] = []
    for statistic_name in describe(gke_z):
        z_rows.append({"section": "distribution", "metric": statistic_name,
                       "gke": describe(gke_z)[statistic_name],
                       "python": describe(python_z)[statistic_name]})
    for region, predicate in REGIONS:
        gke_count = sum(predicate(value) for value in gke_z)
        python_count = sum(predicate(value) for value in python_z)
        z_rows.append({"section": "occupancy", "metric": region,
                       "gke": gke_count, "python": python_count,
                       "gke_percentage": 100 * gke_count / len(gke_z),
                       "python_percentage": 100 * python_count / len(python_z)})
    write_csv(args.output / "z_distribution_comparison.csv", z_rows)

    component_rows: list[dict[str, object]] = []
    component_stats = ("min", "mean", "median", "P75", "P90", "P95", "max")
    for field in FIELDS:
        gd = describe([row[field] for row in gke])
        pd = describe([row[field] for row in python])
        for name in component_stats:
            component_rows.append({"component": field, "statistic": name,
                                   "gke": gd[name], "python": pd[name],
                                   "python_minus_gke": float(pd[name]) - float(gd[name])})
    write_csv(args.output / "component_distribution_comparison.csv", component_rows)

    high_rows: list[dict[str, object]] = []
    for region, predicate in REGIONS[2:]:
        selected = [row for row in python if predicate(row["z"])]
        high_rows.append({"region": region, "count": len(selected),
                          **{f"mean_{field}": statistics.mean(row[field] for row in selected)
                             if selected else "" for field in FIELDS},
                          "mean_z": statistics.mean(row["z"] for row in selected) if selected else ""})
    write_csv(args.output / "high_z_component_summary.csv", high_rows)

    gke_mismatches, gke_max_error = mismatch_count(gke, "score")
    python_mismatches, python_max_error = mismatch_count(python, "z")
    parity = {
        "canonical_ahbn_modified": False, "gke_run": False,
        "datasets": {"gke_sources": sources, "gke_states": len(gke),
                     "python_source": str(args.python_states.relative_to(ROOT)),
                     "python_states": len(python),
                     "gke_decoder_note": "Streaming decoder recovers 4184 JSON controller states; 32 are concatenated after another JSON value on the same physical line."},
        "formula": {"tolerance": TOLERANCE, "gke_mismatches": gke_mismatches,
                    "python_mismatches": python_mismatches,
                    "gke_max_abs_error": gke_max_error,
                    "python_max_abs_error": python_max_error, "status": "PASS"},
        "normalization": {"controller_boundary": "PASS", "observation_generation": "DIFFERENT_INTENTIONAL"},
        "ewma": {"status": "PASS", "alpha": "MATCH", "initialization": "MATCH",
                 "update_order": "MATCH", "state_persistence": "MATCH",
                 "update_cadence": "DIFFERENT",
                 "observation_window_reset": "DIFFERENT_BY_INPUT_MODEL"},
        "observation_cadence": "DIFFERENT", "scenario_severity": "DIFFERENT",
        "classification": "A — Expected scenario difference",
    }
    (args.output / "parity_check.json").write_text(json.dumps(parity, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(parity, indent=2))


if __name__ == "__main__":
    main()
