"""K3.6 cross-baseline isolation and final-regression fixtures."""

from __future__ import annotations

import copy
import random
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.test_k2 import PEER
from tests.test_k3_5_dcsoc_dynamic import DCSOCMaintenance, topology


def bare_peer(strategy: str, peer_id: int = 1):
    peer = PEER.PeerState.__new__(PEER.PeerState)
    peer.strategy = strategy
    peer.peer_id = peer_id
    peer.neighbors = [0, 2, 3, 4, 5, 6, 7, 8]
    peer.unavailable_neighbors = set()
    peer.fanout = 2 if strategy == "ahbn" else (5 if strategy == "gossip" else 2)
    peer.default_fanout = peer.fanout
    peer.mode = "gossip"
    peer.rng = random.Random(8675309)
    peer.is_cluster_head = True
    peer.cluster_head_id = 1
    peer.cluster_members = [0, 2, 3, 4, 5, 6]
    peer.gateway_neighbors = [7]
    peer.dcsoc_role = "core"
    peer.dcsoc_parent = None
    peer.dcsoc_children = [0, 2, 3, 4, 5, 6, 7]
    peer.dcsoc_core_neighbors = []
    if strategy == "ahbn":
        peer.adaptive_update = lambda: None
    return peer


class CrossBaselineStaticIsolationTests(unittest.TestCase):
    def test_x01_x02_four_independent_instances_and_common_topology(self):
        peers = {name: bare_peer(name) for name in ("ahbn", "gossip", "cluster", "dcsoc")}
        before = {name: list(peer.neighbors) for name, peer in peers.items()}
        peers["ahbn"].neighbors.append(99)
        self.assertEqual(peers["gossip"].neighbors, before["gossip"])
        self.assertEqual(peers["cluster"].neighbors, before["cluster"])
        self.assertEqual(peers["dcsoc"].neighbors, before["dcsoc"])

    def test_x03_to_x11_baseline_native_target_selection(self):
        gossip = bare_peer("gossip")
        structured = bare_peer("cluster")
        dcsoc = bare_peer("dcsoc")
        with mock.patch.object(PEER.PeerState, "adaptive_update", side_effect=AssertionError("AHBN")):
            gossip_targets = gossip.target_peers(0)
            structured_targets = structured.target_peers(0)
            dcsoc_targets = dcsoc.target_peers(0)
        self.assertEqual(len(gossip_targets), 5)
        self.assertTrue(set(gossip_targets) <= {2, 3, 4, 5, 6, 7, 8})
        self.assertEqual(structured_targets, [2, 3, 4, 5, 6, 7])
        self.assertEqual(dcsoc_targets, [2, 3, 4, 5, 6, 7])

    def test_x12_to_x14_ahbn_canonical_path_and_no_dcsoc_influence(self):
        peer = bare_peer("ahbn")
        peer.dcsoc_children = list(range(20, 40))
        peer.dcsoc_maintenance = SimpleNamespace(recluster_count=999)
        peer.rng = random.Random(7)
        self.assertEqual(len(peer.target_peers(0)), 2)
        peer.fanout = 4
        self.assertEqual(len(peer.target_peers(0)), 4)

    def test_x15_x16_sender_and_self_exclusion_all_algorithms(self):
        for strategy in ("ahbn", "gossip", "cluster", "dcsoc"):
            peer = bare_peer(strategy)
            targets = peer.target_peers(0)
            self.assertNotIn(0, targets, strategy)
            self.assertNotIn(peer.peer_id, targets, strategy)

    def test_x17_duplicate_no_refanout_all_algorithms(self):
        envelope = SimpleNamespace(
            message_id="same-message", sent_at=1.0, created_at=1.0,
            sender_id=0, hop=1,
        )
        for strategy in ("ahbn", "gossip", "cluster", "dcsoc"):
            peer = bare_peer(strategy)
            peer.failed = False
            peer.lock = threading.Lock()
            peer.recv_count = peer.duplicate_count = 0
            peer.seen_messages = {"same-message"}
            peer.observations = SimpleNamespace(record_receive=lambda **kwargs: None)
            peer.target_peers = mock.Mock(side_effect=AssertionError("refanout"))
            peer.run_id = peer.experiment = "k3.6"
            peer.overload_ms = 0
            peer.bottleneck_active = False
            peer.bottleneck_delay_ms = 0
            with mock.patch.object(PEER, "log_event"), mock.patch.object(PEER, "now", return_value=2.0):
                self.assertEqual(peer.process_envelope(envelope), (False, "duplicate"))
            peer.target_peers.assert_not_called()

    def test_x18_x19_fanout_and_controller_isolation_matrix(self):
        peers = {name: bare_peer(name) for name in ("ahbn", "gossip", "cluster", "dcsoc")}
        first = {name: peer.target_peers(0) for name, peer in peers.items()}
        peers["ahbn"].fanout = 4
        second = {name: peer.target_peers(0) for name, peer in peers.items() if name != "ahbn"}
        self.assertEqual(len(first["ahbn"]), 2)
        self.assertEqual(len(first["gossip"]), 5)
        self.assertEqual(len(first["cluster"]), 6)
        self.assertEqual(len(first["dcsoc"]), 6)
        for name in second:
            if name != "gossip":
                self.assertEqual(second[name], first[name])
        for name in ("gossip", "cluster", "dcsoc"):
            self.assertIsNone(getattr(peers[name], "ahbn_controller", None))


class CrossBaselineDynamicIsolationTests(unittest.TestCase):
    def test_x20_x21_x22_failure_churn_and_mutable_state_isolation(self):
        first = DCSOCMaintenance(topology())
        second = DCSOCMaintenance(topology())
        second_before = second.snapshot()
        first.set_availability(0, False, reason="shared_failure")
        self.assertEqual(first.core_replacement_count, 1)
        self.assertEqual(second.snapshot(), second_before)
        first.set_availability(0, True, reason="shared_rejoin")
        self.assertEqual(first.rejoin_assignment_count, 1)

    def test_x23_x24_slow_is_not_failed_or_maintenance(self):
        state = DCSOCMaintenance(topology())
        before = state.snapshot()
        state.nodes[0]["overload_ms"] = 500
        self.assertEqual(state.events, [])
        self.assertEqual(state.core_replacement_count, 0)
        self.assertEqual(state.recluster_count, 0)
        after = state.snapshot()
        before["nodes"][0]["overload_ms"] = 500
        self.assertEqual(after, before)

    def test_x25_explicit_du_affects_dcsoc_only(self):
        others = {name: bare_peer(name) for name in ("ahbn", "gossip", "cluster")}
        snapshots = {
            name: copy.deepcopy({key: value for key, value in vars(peer).items() if key != "rng"})
            for name, peer in others.items()
        }
        rng_states = {name: peer.rng.getstate() for name, peer in others.items()}
        state = DCSOCMaintenance(topology())
        state.explicit_du()
        self.assertEqual(state.recluster_count, 1)
        for name, peer in others.items():
            self.assertEqual(
                {key: value for key, value in vars(peer).items() if key != "rng"},
                snapshots[name],
            )
            self.assertEqual(peer.rng.getstate(), rng_states[name])

    def test_x26_metrics_are_observational(self):
        peer = bare_peer("gossip")
        before = peer.target_peers(0)
        peer.recv_count = 1000
        peer.duplicate_count = 999
        peer.latencies = [999.0]
        peer.rng = random.Random(8675309)
        self.assertEqual(peer.target_peers(0), before)


class CrossBaselineDeterminismTests(unittest.TestCase):
    def results(self, order):
        result = {}
        for strategy in order:
            peer = bare_peer(strategy)
            if strategy == "ahbn":
                random.seed(91)
            result[strategy] = peer.target_peers(0)
        return result

    def test_x27_experiment_identity_is_not_target_input(self):
        for strategy in ("ahbn", "gossip", "cluster", "dcsoc"):
            left, right = bare_peer(strategy), bare_peer(strategy)
            left.experiment, right.experiment = "Exp08", "Exp12"
            random.seed(91)
            left_targets = left.target_peers(0)
            random.seed(91)
            self.assertEqual(left_targets, right.target_peers(0))

    def test_x28_x29_x30_order_rng_and_replay_isolation(self):
        forward = ("ahbn", "gossip", "cluster", "dcsoc")
        reverse = tuple(reversed(forward))
        self.assertEqual(self.results(forward), self.results(reverse))
        self.assertEqual(self.results(forward), self.results(forward))
        alone = bare_peer("gossip").target_peers(0)
        bare_peer("cluster").target_peers(0)
        bare_peer("dcsoc").target_peers(0)
        self.assertEqual(bare_peer("gossip").target_peers(0), alone)


if __name__ == "__main__":
    unittest.main()
