import math

from app.ahbn_controller import AHBNParams
from scripts.run_k5_phase2_actuator_screening import actuator_s0, actuator_s5, controller_score


def test_s0_boundary_and_representative_mapping_matches_canonical():
    cases = (-1.0, -0.25, -0.249999, 0.0, 0.249999, 0.25, 0.50, 0.90, 1.50, 3.0)
    expected = (2, 2, 3, 3, 3, 4, 4, 4, 4, 4)
    assert tuple(actuator_s0(z) for z in cases) == expected

    params = AHBNParams()
    for z, wanted in zip(cases, expected):
        # Compare to the exact boundary predicates and frozen fanout parameters
        # used by CanonicalAHBNController.update.
        at_low = math.isclose(z, -0.25, rel_tol=0.0, abs_tol=1e-12)
        at_high = math.isclose(z, 0.25, rel_tol=0.0, abs_tol=1e-12)
        canonical = params.min_fanout if z < -0.25 or at_low else (params.max_fanout if z > 0.25 or at_high else params.default_fanout)
        assert actuator_s0(z) == canonical == wanted


def test_s5_boundary_and_representative_mapping():
    cases = (-1.0, -0.25, -0.249999, 0.0, 0.249999, 0.25, 0.50, 0.899999, 0.90, 1.499999, 1.50, 3.0)
    assert tuple(actuator_s5(z) for z in cases) == (2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6)


def test_controller_equation_is_unchanged():
    assert controller_score(0.2, 0.4, 0.6, 0.8) == -0.2 + 0.4 + 0.6 + 0.8
