from scripts.run_k5_phase2_actuator_screening import canonical_trace, paired_seed


def test_trace_replay_is_deterministic():
    assert canonical_trace(42, 8) == canonical_trace(42, 8)


def test_paired_replay_is_deterministic_and_pre_treatment_state_is_shared():
    first_rows, first_trace = paired_seed(42, 8)
    second_rows, second_trace = paired_seed(42, 8)
    assert first_rows == second_rows
    assert first_trace == second_trace
    for index in range(0, len(first_rows), 2):
        s0, s5 = first_rows[index:index + 2]
        assert (s0.seed, s0.message, s0.z) == (s5.seed, s5.message, s5.z)
