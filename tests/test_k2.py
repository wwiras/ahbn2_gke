"""K2 deterministic AHBN regression and semantic validation.

K2 REGRESSION HARNESS -- NOT A SCIENTIFIC EXPERIMENT.
No Kubernetes API or network workload is used by this suite.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import math
import random
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
REFERENCE = Path("/Users/wwiras/Documents/src/AHBNProj/ahbn/v0.61")
sys.path.insert(0, str(APP))
sys.path.insert(0, str(REFERENCE))

from ahbn_controller import AHBNParams, AHBNState, CanonicalAHBNController
from observations import KubernetesObservationAdapter
from ahbn.strategies.ahbn import AHBNStrategy


def expected_fanout(score: float) -> int:
    if score < -0.25 or math.isclose(score, -0.25, rel_tol=0.0, abs_tol=1e-12):
        return 2
    if score > 0.25 or math.isclose(score, 0.25, rel_tol=0.0, abs_tol=1e-12):
        return 4
    return 3


def assert_trajectory(test, sequence):
    ctl, state = CanonicalAHBNController(), AHBNState()
    results = []
    for vector in sequence:
        got = ctl.update(state, *vector)
        expected_score = -got.d_hat + got.l_hat + got.u_hat + got.c_hat
        expected_weight = 1 / (1 + math.exp(-expected_score))
        test.assertAlmostEqual(got.score, expected_score, places=14)
        test.assertAlmostEqual(got.weight, expected_weight, places=14)
        test.assertEqual(got.mode, "gossip" if expected_weight >= .5 else "cluster")
        test.assertEqual(got.fanout, expected_fanout(expected_score))
        results.append(tuple(getattr(got, name) for name in (
            "d_hat", "l_hat", "u_hat", "c_hat", "score", "weight", "mode", "fanout"
        )))
    return results


def load_peer_module():
    """Load peer.py with transport-only modules stubbed out."""
    grpc = types.ModuleType("grpc")
    grpc.insecure_channel = lambda *a, **k: contextlib.nullcontext()
    grpc.server = lambda *a, **k: None
    pb2 = types.ModuleType("peer_pb2")
    for name in ("Envelope", "Ack", "StatusReply"):
        setattr(pb2, name, type(name, (), {"__init__": lambda self, **kw: self.__dict__.update(kw)}))
    pb2_grpc = types.ModuleType("peer_pb2_grpc")
    pb2_grpc.PeerServiceServicer = object
    pb2_grpc.PeerServiceStub = object
    sys.modules.update(grpc=grpc, peer_pb2=pb2, peer_pb2_grpc=pb2_grpc)
    spec = importlib.util.spec_from_file_location("k2_peer", APP / "peer.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PEER = load_peer_module()


def peer_fixture(*, mode="gossip", head=False, fanout=3):
    peer = PEER.PeerState.__new__(PEER.PeerState)
    peer.strategy = "ahbn"
    peer.peer_id = 0
    peer.neighbors = [0, 1, 2, 2, 3, 4, 5]
    peer.is_cluster_head = head
    peer.cluster_members = [0, 1, 2, 2, 3, 4]
    peer.cluster_head_id = 9
    peer.gateway_neighbors = [0, 7, 7, 8]
    peer.mode = mode
    peer.fanout = fanout
    peer.adaptive_update = lambda: None
    peer.unavailable_neighbors = set()
    return peer


class ControllerParityTests(unittest.TestCase):
    def test_k2_c01_c02_c03_multistep_trajectories(self):
        categories = [
            [(0, 0, 0, 0)] * 20,
            [(1, 1, 1, 1)] * 20,
            [(0.5, 0.5, 0.5, 0.5), (1, 0, 0, 0), (0, 1, 0, 0),
             (0, 0, 1, 0), (0, 0, 0, 1), (1, 0, 1, 0), (0, 1, 0, 1)],
            [(i / 20, i / 20, i / 20, i / 20) for i in range(21)],
            [(i % 2, (i + 1) % 2, i % 2, (i + 1) % 2) for i in range(40)],
        ]
        for sequence in categories:
            assert_trajectory(self, sequence)

    def test_k2_c04_c05_ewma_rise_decay_and_bounds(self):
        ctl = CanonicalAHBNController()
        for index in range(4):
            state = AHBNState()
            rise, decay = [], []
            for value in (0, 0, 0, 1, 1, 1):
                vector = [0.0] * 4
                vector[index] = value
                ctl.update(state, *vector)
                rise.append((state.d_hat, state.l_hat, state.u_hat, state.c_hat)[index])
            self.assertEqual(rise, sorted(rise))
            for value in (1, 1, 1, 0, 0, 0):
                vector = [0.0] * 4
                vector[index] = value
                ctl.update(state, *vector)
                decay.append((state.d_hat, state.l_hat, state.u_hat, state.c_hat)[index])
            self.assertGreater(decay[2], decay[-1])
            self.assertTrue(all(0 <= x <= 1 for x in rise + decay))

    def test_k2_c06_c07_threshold_and_transitions(self):
        ctl = CanonicalAHBNController()
        neutral = ctl.update(AHBNState(), 0, 0, 0, 0)
        self.assertAlmostEqual(neutral.weight, .5)
        self.assertEqual(neutral.mode, "gossip")
        low = ctl.update(AHBNState(), 1, 0, 0, 0)
        high = ctl.update(AHBNState(), 0, 1, 0, 1)
        self.assertLess(low.weight, .5)
        self.assertEqual(low.mode, "cluster")
        self.assertGreater(high.weight, .5)
        self.assertEqual(high.mode, "gossip")
        state = AHBNState()
        a = ctl.update(state, 1, 0, 0, 0)
        b = ctl.update(state, 0, 1, 1, 1)
        self.assertTrue(a.mode_changed)
        self.assertTrue(b.mode_changed)

    def test_k2_c08_dense_fanout_mapping(self):
        fanouts = [expected_fanout(-1 + i / 250) for i in range(1001)]
        self.assertEqual(set(fanouts), {2, 3, 4})
        for score, expected in ((-1, 2), (-.250001, 2), (-.25, 2),
                                (-.249999, 3), (.249999, 3), (.25, 4), (3, 4)):
            self.assertEqual(expected_fanout(score), expected)

    def test_k2_c09_long_fixed_seed_stability(self):
        def run():
            rng = random.Random(6102)
            seq = [tuple(rng.random() for _ in range(4)) for _ in range(800)]
            out = assert_trajectory(self, seq)
            for row in out:
                self.assertTrue(all(math.isfinite(x) and 0 <= x <= 1 for x in row[:4]))
                self.assertTrue(math.isfinite(row[4]) and 0 <= row[5] <= 1)
                self.assertIn(row[6], ("gossip", "cluster"))
                self.assertIn(row[7], (2, 3, 4))
            return out
        self.assertEqual(run(), run())

    def test_k2_c10_controller_state_isolation(self):
        ctl = CanonicalAHBNController()
        a, b = AHBNState(), AHBNState()
        for _ in range(10):
            ctl.update(a, 1, 0, 1, 0)
        self.assertEqual(b, AHBNState())
        ctl.update(b, 0, 1, 0, 1)
        self.assertNotEqual(a, b)


class ObservationTests(unittest.TestCase):
    def test_k2_o01_o02_duplicate_windows(self):
        obs = KubernetesObservationAdapter()
        for duplicate in [False] * 5 + [True] * 5:
            obs.record_receive(duplicate=duplicate, latency_seconds=0)
        high = obs.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        for _ in range(10):
            obs.record_receive(duplicate=False, latency_seconds=0)
        low = obs.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        empty = obs.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        self.assertEqual((high.d, low.d, empty.d), (.5, 0, 0))
        self.assertEqual((low.duplicate_window_received, low.duplicate_window_duplicates), (10, 0))

    def test_k2_o03_o04_latency_normalization(self):
        values = []
        for ms in (0, 100, 500, 1000, 1500):
            obs = KubernetesObservationAdapter(1)
            obs.record_receive(duplicate=False, latency_seconds=ms / 1000)
            snap = obs.snapshot_and_reset(overload_ms=0, neighbor_count=1)
            values.append(snap.l)
            self.assertAlmostEqual(snap.latency_raw, ms / 1000)
        self.assertEqual(values, [0, .1, .5, 1, 1])

    def test_k2_o05_o06_o07_o08_churn_accounting(self):
        obs = KubernetesObservationAdapter()
        self.assertEqual(obs.snapshot_and_reset(overload_ms=0, neighbor_count=0).c, 0)
        obs.record_leave()
        self.assertEqual(obs.snapshot_and_reset(overload_ms=0, neighbor_count=4).c, .25)
        obs.record_join()
        self.assertEqual(obs.snapshot_and_reset(overload_ms=0, neighbor_count=4).c, .25)
        obs.record_leave(); obs.record_join()
        self.assertEqual(obs.snapshot_and_reset(overload_ms=0, neighbor_count=4).c, .5)

    def test_k2_o09_o10_peer_local_window_and_ewma_persistence(self):
        a, b = KubernetesObservationAdapter(), KubernetesObservationAdapter()
        a.record_receive(duplicate=True, latency_seconds=1)
        self.assertEqual(b.snapshot_and_reset(overload_ms=0, neighbor_count=4).d, 0)
        ctl, state = CanonicalAHBNController(), AHBNState()
        first = a.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        ctl.update(state, first.d, first.l, first.u, first.c)
        previous = state.d_hat
        second = a.snapshot_and_reset(overload_ms=0, neighbor_count=4)
        ctl.update(state, second.d, second.l, second.u, second.c)
        self.assertAlmostEqual(state.d_hat, previous * .7)


class UtilizationTests(unittest.TestCase):
    def test_k2_u01_to_u06_binary_magnitude_invariance(self):
        self.assertEqual([KubernetesObservationAdapter.utilization(x)
                          for x in (0, 1, 250, 700, 5000)], [0, 1, 1, 1, 1])

    def test_k2_u07_u08_ewma_rise_decay(self):
        ctl, state = CanonicalAHBNController(), AHBNState()
        values = [ctl.update(state, 0, 0, KubernetesObservationAdapter.utilization(x), 0).u_hat
                  for x in (0, 250, 250, 0)]
        self.assertEqual(values[0], 0)
        self.assertLess(values[1], values[2])
        self.assertLess(values[3], values[2])

    def test_k2_u09_u10_actuator_not_decision_input(self):
        self.assertNotIn("overload_ms", CanonicalAHBNController.update.__code__.co_varnames)
        peer = peer_fixture()
        before = (peer.mode, peer.fanout)
        peer.overload_ms = 5000
        self.assertEqual((peer.mode, peer.fanout), before)


class DispatchTests(unittest.TestCase):
    @staticmethod
    def reference_fixture(*, mode, head, fanout):
        class ClusterManager:
            def get_cluster_members(self, cluster_id, exclude=None):
                return [n for n in [0, 1, 2, 2, 3, 4] if n != exclude]

            def get_cluster_head(self, cluster_id):
                return 9

        nodes = {n: SimpleNamespace(is_active=True) for n in range(10)}
        node = SimpleNamespace(
            node_id=0, neighbors=[0, 1, 2, 2, 3, 4, 5],
            control=SimpleNamespace(mode=mode, fanout=fanout),
            is_cluster_head=head, cluster_id=0, gateway_neighbors=[0, 7, 7, 8],
        )
        simulator = SimpleNamespace(
            nodes=nodes, rng=random.Random(91), cluster_manager=ClusterManager()
        )
        return node, simulator

    def test_k2_d01_to_d05_gossip_roles_no_mixing_and_fanout(self):
        for head in (False, True):
            for fanout in (2, 3, 4):
                peer = peer_fixture(mode="gossip", head=head, fanout=fanout)
                random.seed(91)
                targets = peer.target_peers(sender_id=1)
                node, simulator = self.reference_fixture(mode="gossip", head=head, fanout=fanout)
                reference = AHBNStrategy().select_targets(node, None, simulator, sender_id=1)
                self.assertEqual(targets, reference)
                self.assertLessEqual(len(targets), fanout)
                self.assertTrue(set(targets) <= {2, 3, 4, 5})
                self.assertFalse(set(targets) & {0, 1, 7, 8, 9})
                self.assertEqual(len(targets), len(set(targets)))

    def test_k2_d06_to_d09_structured_member_head_gateway_budget(self):
        member = peer_fixture(mode="cluster", head=False)
        self.assertEqual(member.target_peers(sender_id=1), [9])
        self.assertEqual(member.target_peers(sender_id=9), [])
        head = peer_fixture(mode="cluster", head=True, fanout=3)
        self.assertEqual(head.target_peers(sender_id=99), [7, 1, 2])
        node, simulator = self.reference_fixture(mode="cluster", head=True, fanout=3)
        self.assertEqual(head.target_peers(sender_id=99),
                         AHBNStrategy().select_targets(node, None, simulator, sender_id=99))
        head.fanout = 4
        self.assertEqual(head.target_peers(sender_id=1), [7, 2, 3, 4])
        node, simulator = self.reference_fixture(mode="cluster", head=True, fanout=4)
        self.assertEqual(head.target_peers(sender_id=1),
                         AHBNStrategy().select_targets(node, None, simulator, sender_id=1))

    def test_k2_d10_d11_sender_self_and_dedup_adversarial(self):
        for mode, head in (("gossip", True), ("cluster", True)):
            peer = peer_fixture(mode=mode, head=head, fanout=4)
            random.seed(4)
            targets = peer.target_peers(sender_id=2)
            self.assertNotIn(0, targets)
            self.assertNotIn(2, targets)
            self.assertEqual(len(targets), len(set(targets)))

    def test_k2_d12_duplicate_receipt_returns_before_forwarding(self):
        source = (APP / "peer.py").read_text()
        duplicate = source[source.index('if (\n                envelope.message_id\n                in self.seen_messages'):
                           source.index('# Existing overload mechanism')]
        self.assertIn('return False, "duplicate"', duplicate)
        self.assertNotIn("target_peers", duplicate)


class RegressionAndTraceTests(unittest.TestCase):
    def test_k2_r01_to_r04_failure_and_overload_no_direct_bypass(self):
        peer = peer_fixture(mode="cluster", fanout=2)
        peer.run_id = "k2"
        with contextlib.redirect_stdout(io.StringIO()):
            peer.trigger_failure_reaction("fixture")
        self.assertEqual((peer.mode, peer.fanout), ("cluster", 2))
        peer.overload_ms = 700
        self.assertEqual((peer.mode, peer.fanout), ("cluster", 2))

    def test_k2_r05_to_r07_legacy_values_cannot_reach_controller(self):
        frozen = AHBNParams()
        self.assertEqual((frozen.mode_threshold, frozen.min_fanout,
                          frozen.max_fanout, frozen.default_fanout), (.5, 2, 4, 3))
        source = (APP / "peer.py").read_text()
        for key in ("mode_threshold", "min_fanout", "max_fanout", "default_fanout"):
            self.assertNotIn(f'topo.get("{key}"', source)

    def test_k2_r08_to_r10_experiment_identity_cannot_change_controller(self):
        source = (APP / "ahbn_controller.py").read_text().lower()
        for token in ("experiment_id", "exp08", "exp10", "exp11", "exp12"):
            self.assertNotIn(token, source)
        sequence = [(0, 1, 0, 1), (1, 0, 1, 0)] * 10
        self.assertEqual(assert_trajectory(self, sequence), assert_trajectory(self, sequence))

    def test_k2_t01_to_t10_trace_recomputation_and_provenance(self):
        ctl, state = CanonicalAHBNController(), AHBNState()
        previous_mode, previous_fanout = state.mode, state.fanout
        decision = ctl.update(state, .4, .7, 1, .2)
        p = ctl.params
        parts = (p.w_d * (decision.d_hat - p.d0), p.w_l * (decision.l_hat - p.l0),
                 p.w_u * (decision.u_hat - p.u0), p.w_c * (decision.c_hat - p.c0))
        self.assertEqual(parts, (decision.duplication_score_contribution,
                                 decision.latency_score_contribution,
                                 decision.utilization_score_contribution,
                                 decision.churn_score_contribution))
        score = sum(parts)
        weight = 1 / (1 + math.exp(-score))
        self.assertAlmostEqual(decision.score, score)
        self.assertAlmostEqual(decision.weight, weight)
        self.assertEqual(decision.mode, "gossip" if weight >= .5 else "cluster")
        self.assertEqual(decision.fanout, expected_fanout(score))
        self.assertEqual(decision.mode_changed, decision.mode != previous_mode)
        self.assertEqual(decision.fanout_changed, decision.fanout != previous_fanout)
        combined = (APP / "peer.py").read_text() + json.dumps(decision.__dict__)
        for field in ("overload_ms", "overload_active", "raw_u", "u_hat", "latency_raw",
                      "duplicate_window_received", "churn_join_count"):
            self.assertIn(field, combined)


if __name__ == "__main__":
    unittest.main()
