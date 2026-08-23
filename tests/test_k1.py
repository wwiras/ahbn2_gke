from __future__ import annotations

import importlib.util
import math
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from ahbn_controller import AHBNParams, AHBNState, CanonicalAHBNController
from observations import KubernetesObservationAdapter


class ControllerTests(unittest.TestCase):
    def test_frozen_parameters_and_signs(self):
        p = AHBNParams()
        self.assertEqual(
            (p.alpha, p.d0, p.l0, p.u0, p.c0),
            (0.3, 0.5, 0.5, 0.5, 0.5),
        )
        self.assertEqual((p.w_d, p.w_l, p.w_u, p.w_c), (-1, 1, -1, 1))
        self.assertEqual(
            (p.kappa, p.beta, p.min_fanout, p.max_fanout, p.default_fanout),
            (1, 1, 2, 4, 3),
        )

    def test_bounds_exact_ewma_score_sigmoid_mode_and_fanout(self):
        ctl = CanonicalAHBNController()
        state = AHBNState()
        first = ctl.update(state, -4, 2, 1, 0)
        self.assertEqual((first.raw_d, first.raw_l, first.raw_u, first.raw_c), (0, 1, 1, 0))
        self.assertEqual((state.d_hat, state.l_hat, state.u_hat, state.c_hat), (0, .3, .3, 0))
        expected_score = -(0-.5) + (.3-.5) - (.3-.5) + (0-.5)
        self.assertAlmostEqual(state.score, expected_score)
        self.assertAlmostEqual(state.weight, 1 / (1 + math.exp(-expected_score)))
        self.assertEqual(state.mode, "gossip" if state.weight >= .5 else "cluster")
        self.assertLessEqual(2, state.fanout)
        self.assertLessEqual(state.fanout, 4)
        second = ctl.update(state, 1, 1, 0, 1)
        self.assertAlmostEqual(second.d_hat, .3)
        self.assertTrue(all(0 <= x <= 1 for x in (
            second.d_hat, second.l_hat, second.u_hat, second.c_hat, second.weight
        )))

    def test_reference_vectors_match_frozen_controlsim(self):
        reference_path = Path(os.environ.get(
            "AHBN_CONTROLSIM_CONTROL",
            "/Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61/ahbn/control.py",
        ))
        spec = importlib.util.spec_from_file_location("frozen_control", reference_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        ref_ctl = module.AHBNController(module.AHBNParams())
        ref_state = module.NodeControlState()
        ctl, state = CanonicalAHBNController(), AHBNState()
        vectors = [
            (.5, .5, .5, .5), (1, .2, .2, .1), (.1, 1, .2, .1),
            (.1, .2, 1, .1), (.1, .2, .2, 1), (1, 1, 1, 1),
            (0, 0, 0, 0), (.9, .1, .9, .1), (.1, .9, .1, .9),
        ]
        for vector in vectors:
            got = ctl.update(state, *vector)
            ref_ctl.update_metrics(ref_state, *vector)
            ref_ctl.decide_mode_and_fanout(ref_state)
            self.assertEqual(got.mode, ref_state.mode)
            self.assertEqual(got.fanout, ref_state.fanout)
            for name in ("d_hat", "l_hat", "u_hat", "c_hat", "score", "weight"):
                self.assertAlmostEqual(getattr(got, name), getattr(ref_state, name), places=14)


class ObservationTests(unittest.TestCase):
    def test_duplication_latency_and_interval_reset(self):
        obs = KubernetesObservationAdapter(latency_max_seconds=1)
        obs.record_receive(duplicate=False, latency_seconds=0)
        zero = obs.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        self.assertEqual((zero.d, zero.l), (0, 0))
        obs.record_receive(duplicate=False, latency_seconds=.1)
        obs.record_receive(duplicate=True, latency_seconds=.3)
        first = obs.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        self.assertEqual(first.d, .5)
        self.assertAlmostEqual(first.l, .2)
        second = obs.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        self.assertEqual((second.d, second.l), (0, 0))
        obs.record_receive(duplicate=True, latency_seconds=2)
        saturated = obs.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        self.assertEqual((saturated.d, saturated.l), (1, 1))

    def test_latency_normalization_is_monotonic(self):
        values = []
        for latency in (0, .1, .5, 1, 2):
            obs = KubernetesObservationAdapter(latency_max_seconds=1)
            obs.record_receive(duplicate=False, latency_seconds=latency)
            values.append(obs.snapshot_and_reset(overload_ms=0, neighbor_count=1).l)
        self.assertEqual(values, sorted(values))
        self.assertEqual((values[0], values[-1]), (0, 1))

    def test_utilization_binary_mapping_and_canonical_ewma(self):
        self.assertEqual(KubernetesObservationAdapter.utilization(0), 0)
        self.assertEqual(KubernetesObservationAdapter.utilization(250), 1)
        self.assertEqual(KubernetesObservationAdapter.utilization(700), 1)
        ctl, state = CanonicalAHBNController(), AHBNState()
        a = ctl.update(state, 0, 0, 1, 0)
        b = ctl.update(state, 0, 0, 1, 0)
        self.assertAlmostEqual(a.u_hat, .3)
        self.assertAlmostEqual(b.u_hat, .51)
        self.assertTrue(0 <= b.u_hat <= 1)

    def test_churn_observation_and_zero_neighbor_safety(self):
        obs = KubernetesObservationAdapter()
        self.assertEqual(obs.snapshot_and_reset(overload_ms=0, neighbor_count=0).c, 0)
        obs.record_join()
        obs.record_leave()
        self.assertEqual(obs.snapshot_and_reset(overload_ms=0, neighbor_count=0).c, 1)
        obs.record_leave()
        self.assertEqual(obs.snapshot_and_reset(overload_ms=0, neighbor_count=4).c, .25)

    def test_sensor_has_no_experiment_input(self):
        names = KubernetesObservationAdapter.snapshot_and_reset.__code__.co_varnames
        self.assertNotIn("experiment", names)


class StaticBypassTests(unittest.TestCase):
    def test_no_legacy_controller_bypasses_or_gossip_structural_append(self):
        source = (ROOT / "app" / "peer.py").read_text()
        adaptive = source[source.index("    def adaptive_update"):source.index("    def trigger_failure_reaction")]
        self.assertNotIn("bottleneck_pressure", adaptive)
        self.assertNotIn("fail_pressure", adaptive)
        self.assertNotIn("duplicate_ratio_high", adaptive)
        trigger = source[source.index("    def trigger_failure_reaction"):source.index("    def apply_bottleneck_delay")]
        self.assertNotIn('self.mode =', trigger)
        self.assertNotIn('self.fanout =', trigger)
        target = source[source.index("    def target_peers"):source.index("    def forward_to_peer")]
        gossip_branch = target[target.index('if self.mode == "cluster"'):]
        self.assertNotIn("gateway_neighbors", gossip_branch)
        self.assertNotIn("cluster_head_id", gossip_branch)


if __name__ == "__main__":
    unittest.main()
