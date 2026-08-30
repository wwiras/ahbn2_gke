#!/usr/bin/env python3
"""Manual entry point for the K5 H1/H2 plain-Python screening experiment."""

from pathlib import Path

from k5_h1h2_actuator_sim import run_screen


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    destination = root / "outputs" / "k5_h1h2_actuator_screening"
    run_screen(destination)
    print(f"Screening complete: {destination}")

