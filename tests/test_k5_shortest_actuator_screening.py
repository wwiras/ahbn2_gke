import importlib.util
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "k5_shortest_actuator_screening.py"
SPEC = importlib.util.spec_from_file_location("k5_shortest", MODULE)
sim = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = sim
SPEC.loader.exec_module(sim)


def test_required_mapping_and_bounds():
    expected_at_9 = {"S0": (2, 3, 4), "S2": (3, 6, 9), "S5-C5": (3, 5, 5), "S5-C6": (3, 6, 6), "S5-C7": (3, 6, 7)}
    for ne in sim.NE_CASES:
        for policy in sim.POLICIES:
            values = tuple(sim.fanout(policy, mode, ne) for mode in sim.MODES)
            assert all(0 <= value <= ne for value in values)
            if ne == 9:
                assert values == expected_at_9[policy]


def test_only_fanout_changes_and_replay_is_deterministic():
    scenario = sim.build_scenario("multipath", 42)
    edges = sorted(scenario.graph.edges())
    treatments = [sim.simulate(scenario, "HIGH", policy) for policy in sim.POLICIES]
    first = treatments[3]
    second = sim.simulate(scenario, "HIGH", "S5-C6")
    assert first == second
    assert sorted(scenario.graph.edges()) == edges
    assert {result.mode for result in treatments} == {"HIGH"}
    assert {result.scenario for result in treatments} == {"multipath"}
    assert {result.seed for result in treatments} == {42}


def test_categorical_fields_are_excluded_from_arithmetic_aggregation():
    rows = [
        {"policy": "S0", "seed": 42, "scenario": "clean", "mode": "HIGH",
         **{metric: 0 for metric in sim.NUMERIC_METRICS}},
        {"policy": "S0", "seed": 42, "scenario": "multipath", "mode": "LOW",
         **{metric: 2 for metric in sim.NUMERIC_METRICS}},
    ]
    aggregate = sim.average(rows, ("policy", "seed"))
    assert aggregate["delivery_ratio"] == 1
    assert aggregate["send_attempts"] == 1
    assert "scenario" not in aggregate
    assert "mode" not in aggregate


def test_complete_result_files_are_deterministic(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    sim.run(first)
    sim.run(second)
    names = {path.name for path in first.iterdir()}
    assert names == {path.name for path in second.iterdir()}
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
