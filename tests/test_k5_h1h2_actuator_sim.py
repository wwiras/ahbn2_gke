import importlib.util
import math
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "k5_h1h2_actuator_sim.py"
SPEC = importlib.util.spec_from_file_location("k5_h1h2_actuator_sim", MODULE_PATH)
sim = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = sim
SPEC.loader.exec_module(sim)


def test_frozen_threshold_boundaries_and_canonical_mapping():
    assert sim.mode_for_z(-0.50) == "LOW"
    assert sim.mode_for_z(-0.25) == "LOW"
    assert sim.mode_for_z(math.nextafter(-0.25, math.inf)) == "MODERATE"
    assert sim.mode_for_z(math.nextafter(0.25, -math.inf)) == "MODERATE"
    assert sim.mode_for_z(0.25) == "HIGH"
    assert [sim.fanout("S0", mode, 99) for mode in sim.MODES] == [2, 3, 4]


def test_s2_formula_examples_are_exact():
    expected = {3: (2, 3, 3), 4: (2, 3, 4), 6: (2, 4, 6), 9: (3, 6, 9), 12: (4, 8, 12)}
    for ne, values in expected.items():
        assert tuple(sim.fanout("S2", mode, ne) for mode in sim.MODES) == values


def test_replay_is_deterministic_and_shared_scenario_is_unchanged():
    scenario = sim.build_scenario("multipath_convergence", 42)
    before = sorted(scenario.graph.edges())
    first = sim.simulate(scenario, "moderate", 0.0, "S3")
    second = sim.simulate(scenario, "moderate", 0.0, "S3")
    assert first == second
    assert sorted(scenario.graph.edges()) == before


def test_s1_preserves_canonical_budget_and_metrics_are_bounded():
    scenario = sim.build_scenario("limited_unavailability", 43)
    for mode, z in (("LOW", -0.5), ("MODERATE", 0.0), ("HIGH", 0.5)):
        for ne in range(13):
            assert sim.fanout("S1", mode, ne) == sim.fanout("S0", mode, ne)
        result = sim.simulate(scenario, mode.lower(), z, "S1")
        assert 0 <= result.delivery_ratio <= 1
        assert 0 <= result.eta_new <= 1
        assert 0 <= result.h2_overlap <= 1
        assert result.successful_transmissions == result.new_reaches + result.duplicate_receives


def test_s4_caps_are_respected():
    for strategy, cfg in sim.S4_CONFIGS.items():
        for mode in sim.MODES:
            assert sim.fanout(strategy, mode, 100) <= cfg["cap"][mode]
