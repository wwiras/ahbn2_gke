from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

APP = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP))

from ahbn_controller import AHBNState, CanonicalAHBNController
from k5_exp08_tools import ALGORITHMS, FACTORS, SEEDS, write_config
from k5_final_actuator_policy import requested_fanout


def load_runtime(tmp_path: Path, monkeypatch):
    topology = tmp_path / "topology.json"
    topology.write_text(json.dumps({"k5_h2": {"actuator_treatment": "S5"}}))
    monkeypatch.setenv("TOPOLOGY_PATH", str(topology))
    sys.modules.pop("k5_final_actuator_runtime", None)
    fake_peer = types.ModuleType("peer")
    class PeerState:
        def target_peers(self, sender_id, message_id=None):
            return ["canonical"]
    fake_peer.PeerState = PeerState
    fake_peer.log_event = lambda **kwargs: None
    fake_peer.serve = lambda: None
    monkeypatch.setitem(sys.modules, "peer", fake_peer)
    return importlib.import_module("k5_final_actuator_runtime")


def test_canonical_equation_is_frozen():
    state = AHBNState()
    decision = CanonicalAHBNController().update(state, 0.8, 0.6, 0.4, 0.2)
    assert decision.score == pytest.approx(-state.d_hat + state.l_hat + state.u_hat + state.c_hat)


@pytest.mark.parametrize("eligible_count", range(0, 8))
def test_exp08_s5_never_exceeds_eligible_neighbors(tmp_path, monkeypatch, eligible_count):
    runtime = load_runtime(tmp_path, monkeypatch)
    eligible = list(range(1, eligible_count + 1))
    fake = SimpleNamespace(
        strategy="ahbn", mode="gossip", ahbn_state=SimpleNamespace(score=1.5, weight=0.8),
        neighbors=eligible, unavailable_neighbors=set(), peer_id=0, fanout=4,
        run_id="test", experiment="test", h2_selector_treatment="selector_control",
        rng=__import__("random").Random(42), adaptive_update=lambda: None,
        log_ahbn_forwarding_decision=lambda *args: None,
    )
    with mock.patch.object(runtime.peer, "log_event"):
        targets = runtime.target_peers(fake, sender_id=99, message_id="m1")
    assert len(targets) == min(requested_fanout("S5", 1.5), eligible_count)
    assert set(targets).issubset(eligible)


@pytest.mark.parametrize("strategy", ("gossip", "cluster", "dcsoc"))
def test_non_ahbn_comparators_delegate_unchanged(tmp_path, monkeypatch, strategy):
    runtime = load_runtime(tmp_path, monkeypatch)
    fake = SimpleNamespace(strategy=strategy)
    sentinel = [7, 8]
    with mock.patch.object(runtime.peer, "_K5_CANONICAL_TARGET_PEERS", return_value=sentinel) as delegated:
        assert runtime.target_peers(fake, 1, "m") == sentinel
    delegated.assert_called_once_with(fake, 1, "m")


def test_frozen_formal_matrix_and_s5_config(tmp_path):
    base = Path(__file__).parents[1] / "experiments" / "k5_exp08_ahbn.yaml"
    out = tmp_path / "config.yaml"
    write_config(base, out, "ahbn", 42, 1.0)
    text = out.read_text()
    assert len(ALGORITHMS) * len(FACTORS) * len(SEEDS) == 80
    assert "actuator_treatment: S5" in text
    assert "seed: 42" in text


def test_exp08_runner_uses_final_actuator_image_contract():
    root = Path(__file__).parents[1]
    dockerfile = (root / "app" / "Dockerfile").read_text()
    build = (root / "scripts" / "build_push_k5_exp08_final_actuator_image.sh").read_text()
    assert "k5_final_actuator_policy.py" in dockerfile
    assert "k5_final_actuator_runtime.py" in dockerfile
    assert 'CMD ["python", "k5_final_actuator_runtime.py"]' in dockerfile
    assert "docker buildx build" in build
    assert "--platform linux/amd64" in build
    assert "-f app/Dockerfile" in build
    assert "--push" in build
    assert "k5-exp08-final-s5-20260902-tracefix-amd64" in build


def test_formal_guard_matrix_and_gate_contract():
    root = Path(__file__).parents[1]
    formal = (root / "scripts" / "run_k5_exp08_formal.sh").read_text()
    runner = (root / "scripts" / "run_k5_exp08.sh").read_text()
    analysis = (root / "app" / "k5_exp08_tools.py").read_text()
    assert 'grep -Fxq "K5 EXP08 SMOKE GATE: PASS"' in formal
    assert "formal IMAGE differs from smoke-validated image" in formal
    assert "algorithms=(gossip structured dcsoc ahbn)" in runner
    assert "seeds=(42 43 44 45 46)" in runner
    assert "factors=(1.0 1.5 2.0 3.0)" in runner
    assert "K5 EXP08 FORMAL GATE: PASS" in analysis
    assert "EXPECTED FORMAL EXECUTIONS:" in analysis
    assert "CONTROLLER INVARIANT MISMATCHES:" in analysis
    assert "formal output directory already exists" in formal
    assert "EXPECTED_CONTROLLER_HASH" in runner
    assert "EXPECTED_POLICY_HASH" in runner
    assert "image_provenance.json" in analysis


def test_latency_overload_has_no_failure_or_maintenance_action():
    root = Path(__file__).parents[1]
    for algorithm in ALGORITHMS:
        config = (root / "experiments" / f"k5_exp08_{algorithm}.yaml").read_text()
        assert "mode: bottleneck" in config
    runner = (root / "scripts" / "run_k5_exp08.sh").read_text()
    assert "dcsoc_maintenance" not in runner
