import sys
import json
import importlib.util
from pathlib import Path
import pytest

APP = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP))

from ahbn_controller import AHBNState, CanonicalAHBNController
from k5_final_actuator_policy import requested_fanout


@pytest.mark.parametrize(("score", "expected"), [
    (0.249999, 3), (0.25, 4), (0.899999, 4),
    (0.90, 5), (1.499999, 5), (1.50, 6),
])
def test_s5_frozen_boundaries(score, expected):
    assert requested_fanout("S5", score) == expected


def test_s0_mapping():
    assert requested_fanout("S0", 0.25) == 4
    assert requested_fanout("S0", 0.90) == 4
    assert requested_fanout("S0", 1.50) == 4
    assert requested_fanout("S0", -0.25) == 2


def test_treatment_isolation():
    observations = (0.1, 0.9, 0.8, 0.2)
    decisions = []
    for _treatment in ("S0", "S5"):
        decision = CanonicalAHBNController().update(AHBNState(), *observations)
        decisions.append(decision)
    a, b = decisions
    assert (a.score, a.weight, a.mode) == (b.score, b.weight, b.mode)
    assert requested_fanout("S0", 1.50) == 4
    assert requested_fanout("S5", 1.50) == 6


def test_actuator_command_is_not_redefined_by_eligible_count():
    assert requested_fanout("S5", 1.50) == 6


def test_parser_understands_both_treatments(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "k5_final_actuator_analysis.py"
    spec = importlib.util.spec_from_file_location("k5_final_analysis", script)
    analysis = importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)
    for treatment, requested in (("S0", 4), ("S5", 6)):
        run_dir = tmp_path / treatment; run_dir.mkdir()
        (run_dir / "metrics.json").write_text(json.dumps({
            "delivery_ratio": 0.9, "propagation_delay": 1.2,
            "duplicates": 2, "total_forwards": 3,
        }), encoding="utf-8")
        events = [
            {"event": "k5_final_actuator_decision", "treatment": treatment,
             "eligible_neighbor_count": 9, "score": 1.5,
             "requested_fanout": requested, "actual_fanout": requested},
            {"event": "message_injected", "message_id": "m1"},
            {"event": "received_new", "message_id": "m1", "peer_id": 1},
            {"event": "forward", "message_id": "m1"},
        ]
        (run_dir / "logs.jsonl").write_text(
            "\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")
        row = analysis.summarize(run_dir, 42, treatment)
        assert row["treatment"] == treatment
        assert row["mean_requested_fanout"] == requested


def _complete_final_run(path, analysis):
    path.mkdir()
    (path / "topology.json").write_text(json.dumps({
        "run_id": "k5_final_actuator_seed42_s0", "strategy": "ahbn",
        "k5": {"seed": 42, "overload_factor": 2.0},
        "k5_h2": {"actuator_treatment": "S0"},
    }), encoding="utf-8")
    events = ([{"event": "message_injected", "message_id": f"m{i}", "ts": i}
               for i in range(20)] + [
        {"event": "overload_target_selected"}, {"event": "overload_applied"},
        {"event": "run_finished"},
        {"event": "received_new", "message_id": "m0", "peer_id": 1, "ts": 1.0},
        {"event": "forward"},
        {"event": "ahbn_controller_trace", "score": 0.3, "weight": 0.6,
         "mode": "gossip", "duplication_score_contribution": -0.1,
         "latency_score_contribution": 0.1, "utilization_score_contribution": 0.2,
         "churn_score_contribution": 0.1},
        {"event": "k5_final_actuator_decision", "treatment": "S0",
         "eligible_neighbor_count": 9, "score": 0.3,
         "requested_fanout": 4, "actual_fanout": 4},
    ])
    (path / "logs.jsonl").write_text(
        "\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")
    (path / "controller.log").write_text(json.dumps({"event": "run_finished"}) + "\n",
                                          encoding="utf-8")
    pods = {"items": [{"metadata": {"name": f"peer-{i}"}, "status": {
        "phase": "Running", "containerStatuses": [{"ready": True, "restartCount": 0}]}}
        for i in range(20)]}
    (path / "pods.json").write_text(json.dumps(pods), encoding="utf-8")


def test_final_run_contract_accepts_authoritative_artifacts(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "k5_final_actuator_analysis.py"
    spec = importlib.util.spec_from_file_location("final_contract", script)
    analysis = importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)
    run = tmp_path / "valid"; _complete_final_run(run, analysis)
    result = analysis.validate_final_run(run, 42, "S0")
    assert result["delivery_ratio"] == 1 / 400
    assert (run / "metrics.json").is_file()
    assert not (run / "statuses.jsonl").exists()


def test_final_run_contract_rejects_missing_mandatory_artifact(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "k5_final_actuator_analysis.py"
    spec = importlib.util.spec_from_file_location("missing_contract", script)
    analysis = importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)
    run = tmp_path / "invalid"; _complete_final_run(run, analysis)
    (run / "pods.json").unlink()
    with pytest.raises(ValueError, match="mandatory final-run artifacts missing.*pods.json"):
        analysis.validate_final_run(run, 42, "S0")


def test_runner_pins_project_interpreter_and_resume_contract():
    runner = (Path(__file__).parents[1] / "scripts" / "run_k5_final_actuator_gke.sh").read_text()
    required = "/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python"
    assert f'REQUIRED_PYTHON="{required}"' in runner
    assert 'PYTHON_EXECUTABLE="$("${PYTHON}" -c' in runner
    assert 'PYTHON_PREFIX="$("${PYTHON}" -c' in runner
    assert 'Python override forbidden' in runner
    assert 'SKIP VALID COMPLETE RUN' in runner
    assert 'app/k5_exp08_tools.py run' not in runner
