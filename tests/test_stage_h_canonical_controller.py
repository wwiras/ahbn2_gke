from __future__ import annotations

import math
import sys
import unittest
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from ahbn_controller import AHBNParams, AHBNState, CanonicalAHBNController

TOL = 1e-12
LEVELS = (0.20, 0.45, 0.70, 0.80, 1.00)


def expected_fanout(score: float) -> int:
    if score < -0.25 or math.isclose(score, -0.25, rel_tol=0.0, abs_tol=TOL):
        return 2
    if score > 0.25 or math.isclose(score, 0.25, rel_tol=0.0, abs_tol=TOL):
        return 4
    return 3


def evaluate(d: float, l: float, u: float, c: float):
    """Exercise production update with an already-settled synthetic EWMA state."""
    state = AHBNState(d_hat=d, l_hat=l, u_hat=u, c_hat=c)
    return CanonicalAHBNController().update(state, d, l, u, c)


def expected(d: float, l: float, u: float, c: float):
    parts = (-d, l, u, c)
    score = sum(parts)
    weight = 1.0 / (1.0 + math.exp(-score))
    mode = "gossip" if weight >= 0.5 else "cluster"
    fanout = expected_fanout(score)
    return parts, score, weight, mode, fanout


class StageHCanonicalControllerTests(unittest.TestCase):
    def assert_case(self, vector):
        decision = evaluate(*vector)
        parts, score, weight, mode, fanout = expected(*vector)
        self.assertAlmostEqual(decision.duplication_score_contribution, parts[0], delta=TOL)
        self.assertAlmostEqual(decision.latency_score_contribution, parts[1], delta=TOL)
        self.assertAlmostEqual(decision.utilization_score_contribution, parts[2], delta=TOL)
        self.assertAlmostEqual(decision.churn_score_contribution, parts[3], delta=TOL)
        self.assertAlmostEqual(decision.score, score, delta=TOL)
        self.assertAlmostEqual(decision.weight, weight, delta=TOL)
        self.assertEqual(decision.mode, mode)
        self.assertEqual(decision.fanout, fanout)
        return decision

    def test_h01_frozen_parameters(self):
        p = AHBNParams()
        self.assertEqual((p.alpha, p.d0, p.l0, p.u0, p.c0), (.30, 0, 0, 0, 0))
        self.assertEqual((p.w_d, p.w_l, p.w_u, p.w_c), (-1, 1, 1, 1))
        self.assertEqual((p.kappa, p.beta, p.mode_threshold), (1, 1, .50))
        self.assertEqual((p.min_fanout, p.max_fanout, p.default_fanout), (2, 4, 3))

    def test_h02_canonical_scenario_matrix(self):
        cases = (
            (0, 0, 0, 0), (.8, 0, 0, 0), (0, .8, 0, 0),
            (0, 0, .8, 0), (0, 0, 0, .8), (.7, 0, .45, 0),
            (.7, 0, .8, 0), (.7, .3, .6, 0), (0, .7, 1, 0),
            (1, 0, 0, 0), (.8, 0, .8, 0), (.8, .3, .3, .2),
            (.5, .5, .5, .5),
        )
        for vector in cases:
            with self.subTest(vector=vector):
                self.assert_case(vector)

    def test_h03_zero_is_neutral_and_half_each_is_not(self):
        neutral = self.assert_case((0, 0, 0, 0))
        self.assertEqual((neutral.score, neutral.weight, neutral.mode, neutral.fanout),
                         (0, .5, "gossip", 3))
        moderate = self.assert_case((.5, .5, .5, .5))
        self.assertAlmostEqual(moderate.score, 1.0, delta=TOL)
        self.assertGreater(moderate.weight, .5)

    def test_h04_stage_f_crossover_anchors(self):
        moderate = self.assert_case((.70, 0, .45, 0))
        severe = self.assert_case((.70, 0, .80, 0))
        self.assertAlmostEqual(moderate.score, -.25, delta=TOL)
        self.assertEqual(moderate.mode, "cluster")
        self.assertEqual(moderate.fanout, 2)
        self.assertAlmostEqual(severe.score, .10, delta=TOL)
        self.assertEqual(severe.mode, "gossip")
        self.assertEqual(severe.fanout, 3)

    def test_h05_single_signal_monotonic_sweeps(self):
        for signal in range(4):
            rows = []
            for value in (i / 10 for i in range(11)):
                vector = [0.0] * 4
                vector[signal] = value
                rows.append(self.assert_case(tuple(vector)))
            scores = [r.score for r in rows]
            weights = [r.weight for r in rows]
            fanouts = [r.fanout for r in rows]
            modes = [r.mode for r in rows]
            if signal == 0:
                self.assertTrue(all(a > b for a, b in zip(scores, scores[1:])))
                self.assertTrue(all(a > b for a, b in zip(weights, weights[1:])))
                self.assertTrue(all(a >= b for a, b in zip(fanouts, fanouts[1:])))
                self.assertNotIn(("cluster", "gossip"), zip(modes, modes[1:]))
            else:
                self.assertTrue(all(a < b for a, b in zip(scores, scores[1:])))
                self.assertTrue(all(a < b for a, b in zip(weights, weights[1:])))
                self.assertTrue(all(a <= b for a, b in zip(fanouts, fanouts[1:])))
                self.assertNotIn(("gossip", "cluster"), zip(modes, modes[1:]))

    def test_h06_utilization_mixed_background_sweeps(self):
        for d, l, c in ((0, 0, 0), (.3, 0, 0), (.7, 0, 0), (.7, .2, .1)):
            rows = [self.assert_case((d, l, i / 10, c)) for i in range(11)]
            self.assertTrue(all(a.score < b.score for a, b in zip(rows, rows[1:])))
            self.assertTrue(all(a.weight < b.weight for a, b in zip(rows, rows[1:])))
            self.assertTrue(all(a.fanout <= b.fanout for a, b in zip(rows, rows[1:])))
            self.assertNotIn(("gossip", "cluster"),
                             zip([r.mode for r in rows], [r.mode for r in rows[1:]]))

    def test_h07_pairwise_conflict_matrix(self):
        for positive_index in (1, 2, 3):
            for d, positive in product(LEVELS, repeat=2):
                vector = [0.0] * 4
                vector[0], vector[positive_index] = d, positive
                got = self.assert_case(tuple(vector))
                self.assertAlmostEqual(got.score, -d + positive, delta=TOL)
                self.assertEqual(got.mode, "cluster" if positive < d else "gossip")

    def test_h08_multisignal_additive_composition(self):
        cases = (((.8, .2, .2, 0), -.4, "cluster"),
                 ((.8, .3, .3, .3), .1, "gossip"),
                 ((.9, .2, .2, .2), -.3, "cluster"),
                 ((.9, .4, .4, .4), .3, "gossip"))
        for vector, score, mode in cases:
            got = self.assert_case(vector)
            self.assertAlmostEqual(got.score, score, delta=TOL)
            self.assertEqual(got.mode, mode)

    def test_h09_decision_boundary_below_at_above_zero(self):
        for vector, mode in (((.51, 0, .50, 0), "cluster"),
                             ((.50, 0, .50, 0), "gossip"),
                             ((.49, 0, .50, 0), "gossip"),
                             ((.61, .20, .40, 0), "cluster"),
                             ((.60, .20, .40, 0), "gossip"),
                             ((.59, .20, .40, 0), "gossip")):
            self.assertEqual(self.assert_case(vector).mode, mode)

    def test_h10_fanout_quantization_boundaries(self):
        below_low = -.25 - 1e-9
        above_low = -.25 + 1e-9
        below_high = .25 - 1e-9
        above_high = .25 + 1e-9
        for score, fanout in ((below_low, 2), (-.25, 2), (above_low, 3),
                              (0, 3), (below_high, 3), (.25, 4), (above_high, 4)):
            vector = (-score, 0, 0, 0) if score < 0 else (0, score, 0, 0)
            got = evaluate(*vector)
            self.assertAlmostEqual(got.score, score, delta=TOL)
            self.assertAlmostEqual(got.weight, 1 / (1 + math.exp(-score)), delta=TOL)
            self.assertEqual(got.fanout, fanout)
        canonical_corners = [self.assert_case(v) for v in product((0.0, 1.0), repeat=4)]
        self.assertEqual(set(r.fanout for r in canonical_corners), {2, 3, 4})

    def test_h11_unit_cube_corners(self):
        for vector in product((0.0, 1.0), repeat=4):
            self.assert_case(vector)
        self.assertAlmostEqual(self.assert_case((1, 1, 1, 1)).score, 2, delta=TOL)

    def test_h12_production_input_clipping(self):
        state = AHBNState()
        got = CanonicalAHBNController().update(state, -1, 2, 3, -4)
        self.assertEqual((got.raw_d, got.raw_l, got.raw_u, got.raw_c), (0, 1, 1, 0))
        self.assertEqual((got.d_hat, got.l_hat, got.u_hat, got.c_hat), (0, .3, .3, 0))

    def test_h13_alpha_regression(self):
        got = CanonicalAHBNController().update(AHBNState(), 1, 1, 1, 1)
        self.assertEqual((got.d_hat, got.l_hat, got.u_hat, got.c_hat), (.3, .3, .3, .3))

    def test_h14_duplicate_lower_values_are_monotonic(self):
        rows = [self.assert_case((d, 0, 0, 0)) for d in (.2, .5, .8)]
        self.assertTrue(rows[0].score > rows[1].score > rows[2].score)
        self.assertTrue(rows[0].weight > rows[1].weight > rows[2].weight)

    def test_h15_mode_fanout_separation_and_reachability(self):
        cases = (((.5, 0, 0, 0), "cluster", 2),
                 ((.1, 0, 0, 0), "cluster", 3),
                 ((0, .1, 0, 0), "gossip", 3),
                 ((0, .5, 0, 0), "gossip", 4))
        for vector, mode, fanout in cases:
            got = self.assert_case(vector)
            self.assertEqual((got.mode, got.fanout), (mode, fanout))
        anchors = (self.assert_case((1, 0, 0, 0)),
                   self.assert_case((0, 0, 0, 0)),
                   self.assert_case((0, 0, 1, 0)))
        self.assertEqual([row.fanout for row in anchors], [2, 3, 4])


if __name__ == "__main__":
    unittest.main()
