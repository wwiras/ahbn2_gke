"""K3.2 deterministic standalone-Gossip semantic validation."""

from __future__ import annotations

import json
import random
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.test_k2 import PEER
from ahbn.strategies.gossip import GossipStrategy


def gossip_peer(*, fanout=2, seed=91):
    peer = PEER.PeerState.__new__(PEER.PeerState)
    peer.strategy = "gossip"
    peer.peer_id = 0
    peer.neighbors = [0, 1, 2, 2, 3, 4, 5, 99]
    peer.default_fanout = fanout
    peer.rng = random.Random(seed)
    peer.unavailable_neighbors = {99}
    peer.is_cluster_head = True
    peer.cluster_members = [6, 7]
    peer.gateway_neighbors = [8]
    peer.cluster_head_id = 9
    peer.mode = "gossip"
    peer.fanout = fanout
    return peer


class GossipSelectionTests(unittest.TestCase):
    def test_g01_g02_g03_g04_physical_self_sender_before_fanout(self):
        peer = gossip_peer(fanout=2)
        targets = peer.target_peers(sender_id=1)
        self.assertEqual(len(targets), 2)
        self.assertTrue(set(targets) <= {2, 3, 4, 5})
        self.assertNotIn(0, targets)
        self.assertNotIn(1, targets)

    def test_g05_g06_g07_no_replacement_static_and_shortfall(self):
        targets = gossip_peer(fanout=2).target_peers(sender_id=1)
        self.assertEqual(len(targets), len(set(targets)))
        self.assertEqual(len(targets), 2)
        shortfall = gossip_peer(fanout=5).target_peers(sender_id=1)
        self.assertEqual(len(shortfall), 4)
        self.assertEqual(set(shortfall), {2, 3, 4, 5})

    def test_g08_g09_none_all_eligible_and_availability(self):
        targets = gossip_peer(fanout=None).target_peers(sender_id=1)
        self.assertEqual(targets, [2, 3, 4, 5])
        self.assertNotIn(99, targets)

    def test_g10_deterministic_bounded_sampling(self):
        first = gossip_peer(fanout=3, seed=17).target_peers(sender_id=1)
        second = gossip_peer(fanout=3, seed=17).target_peers(sender_id=1)
        self.assertEqual(first, second)
        self.assertNotEqual(
            first,
            gossip_peer(fanout=3, seed=18).target_peers(sender_id=1),
        )

    def test_controlsim_bounded_and_unbounded_parity_fixture(self):
        nodes = {
            node_id: SimpleNamespace(is_active=node_id != 99)
            for node_id in (0, 1, 2, 3, 4, 5, 99)
        }
        node = SimpleNamespace(node_id=0, neighbors=[0, 1, 2, 3, 4, 5, 99])
        bounded_sim = SimpleNamespace(nodes=nodes, rng=random.Random(91))
        reference = GossipStrategy(2).select_targets(
            node, None, bounded_sim, exclude_target_id=1
        )
        self.assertEqual(reference, gossip_peer(fanout=2, seed=91).target_peers(1))
        all_sim = SimpleNamespace(nodes=nodes, rng=random.Random(91))
        reference_all = GossipStrategy(None).select_targets(
            node, None, all_sim, exclude_target_id=1
        )
        self.assertEqual(reference_all, gossip_peer(fanout=None).target_peers(1))

    def test_g11_g12_g15_no_structural_or_ahbn_like_state_effect(self):
        first = gossip_peer(fanout=2, seed=7)
        second = gossip_peer(fanout=2, seed=7)
        second.mode = "cluster"
        second.fanout = 999
        second.weight = 1.0
        second.score = 999.0
        second.cluster_members = [42]
        second.gateway_neighbors = [43]
        second.overload_ms = 9000
        self.assertEqual(first.target_peers(1), second.target_peers(1))

    def test_g13_standalone_initialization_has_no_ahbn_controller(self):
        topology = {
            "run_id": "k3.2", "strategy": "gossip", "num_nodes": 2,
            "message_source": 0, "seed": 13,
            "nodes": {
                "0": {"neighbors": [1], "is_cluster_head": False},
                "1": {"neighbors": [0], "is_cluster_head": False},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "topology.json"
            path.write_text(json.dumps(topology), encoding="utf-8")
            with mock.patch.dict("os.environ", {"TOPOLOGY_PATH": str(path)}), \
                 mock.patch.object(PEER.socket, "gethostname", return_value="peer-0"), \
                 mock.patch.object(PEER, "log_event"):
                peer = PEER.PeerState()
        self.assertIsNone(peer.default_fanout)
        self.assertIsNone(peer.ahbn_params)
        self.assertIsNone(peer.ahbn_controller)
        self.assertIsNone(peer.ahbn_state)

    def test_g14_duplicate_receipt_does_not_refanout(self):
        peer = gossip_peer()
        peer.failed = False
        peer.lock = threading.Lock()
        peer.recv_count = 0
        peer.duplicate_count = 0
        peer.seen_messages = {"m"}
        peer.observations = SimpleNamespace(record_receive=lambda **kwargs: None)
        peer.ahbn_controller = mock.Mock()
        peer.adaptive_update = PEER.PeerState.adaptive_update.__get__(peer)
        peer.target_peers = mock.Mock(side_effect=AssertionError("refanout"))
        peer.run_id = "k3.2"
        peer.experiment = "k3.2"
        peer.overload_ms = 0
        peer.bottleneck_active = False
        peer.bottleneck_delay_ms = 0
        envelope = SimpleNamespace(
            message_id="m", sent_at=1.0, created_at=1.0,
            sender_id=1, hop=1,
        )
        with mock.patch.object(PEER, "log_event"), mock.patch.object(PEER, "now", return_value=2.0):
            self.assertEqual(peer.process_envelope(envelope), (False, "duplicate"))
        peer.target_peers.assert_not_called()
        peer.ahbn_controller.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
