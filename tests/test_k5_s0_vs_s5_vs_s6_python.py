import importlib.util
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "k5_s0_vs_s5_vs_s6_python.py"
SPEC = importlib.util.spec_from_file_location("k5_s6", MODULE)
sim = importlib.util.module_from_spec(SPEC); assert SPEC.loader
sys.modules[SPEC.name] = sim; SPEC.loader.exec_module(sim)


def test_required_s6_examples_bounds_and_monotonicity():
    expected = {5: [1, 2, 3, 4, 5], 10: [2, 4, 6, 8, 10]}
    for ne in (0, 1, 2, 3, 5, 6, 7, 10, 13):
        values = [sim.topology_fanout(k, ne) for k in range(1, 6)]
        assert values == sorted(values)
        assert all(0 <= value <= ne for value in values)
        if ne > 0:
            assert min(values) >= 1
            assert values[-1] == ne
        else:
            assert values == [0] * 5
        if ne in expected:
            assert values == expected[ne]


def test_s0_and_fixed_s5_semantics():
    assert [sim.s0_requested_fanout(z) for z in (-.25, 0, .25, 2)] == [2, 3, 4, 4]
    for fanout in range(2, 7):
        assert sim.actual_fanout(f"S5-f{fanout}", 99, 13) == (fanout, fanout)
        assert sim.actual_fanout(f"S5-f{fanout}", 99, 1) == (fanout, 1)


def test_s6_uses_only_k_and_ne_and_records_selected_count():
    assert [sim.robustness_level(z) for z in (-.25, 0, .25, .90, 1.50)] == [1, 2, 3, 4, 5]
    for z in (-1, 0, .5, 1, 2):
        k, actual = sim.actual_fanout("S6", z, 7)
        assert actual == sim.topology_fanout(k, 7)
    graph = sim.nx.freeze(sim.nx.barabasi_albert_graph(sim.N, sim.M, seed=42))
    _, rows = sim.simulate_message(graph, 42, 0, 2.0, "S6")
    assert all(row["calculated_actual_fanout"] == row["actual_selected_peer_count"] for row in rows)


def test_matched_seed_replay_is_deterministic():
    graph = sim.nx.freeze(sim.nx.barabasi_albert_graph(sim.N, sim.M, seed=42))
    first = sim.simulate_message(graph, 42, 0, .5, "S6")
    second = sim.simulate_message(graph, 42, 0, .5, "S6")
    assert first == second
    assert sim.SEEDS == (42, 43, 44, 45, 46)
