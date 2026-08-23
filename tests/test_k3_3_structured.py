"""K3.3 deterministic standalone-Structured semantic validation."""

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
from ahbn.strategies.cluster import ClusterStrategy


def structured_peer(*, head: bool = False):
    peer = PEER.PeerState.__new__(PEER.PeerState)
    peer.strategy = "cluster"
    peer.peer_id = 0
    peer.neighbors = [20, 21, 22]
    peer.is_cluster_head = head
    peer.cluster_members = [0, 1, 2, 2, 3, 4, 5]
    peer.cluster_head_id = 9
    peer.gateway_neighbors = [0, 6, 6]
    peer.unavailable_neighbors = set()
    peer.mode = "cluster"
    peer.fanout = 3
    peer.default_fanout = 3
    return peer


class StructuredSelectionTests(unittest.TestCase):
    def test_s01_s02_s03_member_head_sender_and_self(self):
        peer = structured_peer()
        self.assertEqual(peer.target_peers(sender_id=8), [9])
        self.assertEqual(peer.target_peers(sender_id=9), [])
        peer.cluster_head_id = 0
        self.assertEqual(peer.target_peers(sender_id=8), [])

    def test_s04_s05_s06_s07_head_members_gateway_sender_self(self):
        peer = structured_peer(head=True)
        self.assertEqual(peer.target_peers(sender_id=1), [2, 3, 4, 5, 6])
        self.assertNotIn(0, peer.target_peers(sender_id=99))
        peer.gateway_neighbors.append(99)
        self.assertNotIn(99, peer.target_peers(sender_id=99))

    def test_s08_s09_more_than_four_and_ahbn_fanout_independent(self):
        expected = [1, 2, 3, 4, 5, 6]
        for fanout in (2, 3, 4):
            peer = structured_peer(head=True)
            peer.fanout = fanout
            peer.default_fanout = fanout
            self.assertEqual(peer.target_peers(sender_id=99), expected)

    def test_s10_s11_deterministic_and_no_gossip_sampling(self):
        results = []
        with mock.patch.object(PEER.random, "sample", side_effect=AssertionError("sampling")):
            for seed in (42, 43, 99):
                random.seed(seed)
                results.append(structured_peer(head=True).target_peers(sender_id=99))
        self.assertEqual(results, [[1, 2, 3, 4, 5, 6]] * 3)

    def test_s12_s13_unavailable_targets_no_hidden_repair(self):
        head = structured_peer(head=True)
        head.unavailable_neighbors = {3, 6}
        self.assertEqual(head.target_peers(sender_id=99), [1, 2, 4, 5])
        member = structured_peer()
        member.unavailable_neighbors = {9}
        member.neighbors = [7, 8, 10]
        self.assertEqual(member.target_peers(sender_id=8), [])

    def test_s14_standalone_initialization_has_no_ahbn_controller(self):
        topology = {
            "run_id": "k3.3", "strategy": "cluster", "num_nodes": 2,
            "message_source": 1, "seed": 13, "fanout": 2,
            "nodes": {
                "0": {"neighbors": [1], "is_cluster_head": True,
                      "cluster_head_id": 0, "cluster_members": [1],
                      "gateway_neighbors": []},
                "1": {"neighbors": [0], "is_cluster_head": False,
                      "cluster_head_id": 0, "cluster_members": [0],
                      "gateway_neighbors": []},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "topology.json"
            path.write_text(json.dumps(topology), encoding="utf-8")
            with mock.patch.dict("os.environ", {"TOPOLOGY_PATH": str(path)}), \
                 mock.patch.object(PEER.socket, "gethostname", return_value="peer-0"), \
                 mock.patch.object(PEER, "log_event"):
                peer = PEER.PeerState()
        self.assertIsNone(peer.ahbn_params)
        self.assertIsNone(peer.ahbn_controller)
        self.assertIsNone(peer.ahbn_state)
        self.assertIsInstance(peer.observations, PEER.StandaloneObservationSink)
        peer.adaptive_update()

    def test_s15_duplicate_receipt_does_not_refanout(self):
        peer = structured_peer()
        peer.failed = False
        peer.lock = threading.Lock()
        peer.recv_count = 0
        peer.duplicate_count = 0
        peer.seen_messages = {"m"}
        peer.observations = SimpleNamespace(record_receive=lambda **kwargs: None)
        peer.ahbn_controller = mock.Mock()
        peer.adaptive_update = PEER.PeerState.adaptive_update.__get__(peer)
        peer.target_peers = mock.Mock(side_effect=AssertionError("refanout"))
        peer.run_id = peer.experiment = "k3.3"
        peer.overload_ms = 0
        peer.bottleneck_active = False
        peer.bottleneck_delay_ms = 0
        envelope = SimpleNamespace(message_id="m", sent_at=1.0, created_at=1.0,
                                   sender_id=9, hop=1)
        with mock.patch.object(PEER, "log_event"), \
             mock.patch.object(PEER, "now", return_value=2.0):
            self.assertEqual(peer.process_envelope(envelope), (False, "duplicate"))
        peer.target_peers.assert_not_called()
        peer.ahbn_controller.update.assert_not_called()

    def test_s16_s17_no_dcsoc_influence_and_source_follows_role(self):
        baseline = structured_peer()
        influenced = structured_peer()
        influenced.dcsoc_role = "core"
        influenced.dcsoc_parent = 77
        influenced.dcsoc_children = [78]
        influenced.dcsoc_core_neighbors = [79]
        self.assertEqual(baseline.target_peers(99), influenced.target_peers(99))
        self.assertEqual(influenced.target_peers(99), [9])

    def test_direct_controlsim_parity_member_head_and_availability(self):
        nodes = {
            node_id: SimpleNamespace(is_active=node_id not in {3, 8})
            for node_id in range(10)
        }
        manager = SimpleNamespace(
            get_cluster_members=lambda cluster_id, exclude=None: [0, 1, 2, 3, 4, 5],
            get_cluster_head=lambda cluster_id: 9,
        )
        simulator = SimpleNamespace(nodes=nodes, cluster_manager=manager)

        ref_head = SimpleNamespace(node_id=0, cluster_id=0, is_cluster_head=True,
                                   gateway_neighbors=[6, 8])
        reference_head = ClusterStrategy().select_targets(
            ref_head, None, simulator, exclude_target_id=1
        )
        kube_head = structured_peer(head=True)
        kube_head.gateway_neighbors = [6, 8]
        kube_head.unavailable_neighbors = {3, 8}
        self.assertEqual(reference_head, kube_head.target_peers(1))

        ref_member = SimpleNamespace(node_id=7, cluster_id=0, is_cluster_head=False,
                                     gateway_neighbors=[])
        reference_member = ClusterStrategy().select_targets(
            ref_member, None, simulator, exclude_target_id=8
        )
        kube_member = structured_peer()
        kube_member.peer_id = 7
        self.assertEqual(reference_member, kube_member.target_peers(8))


if __name__ == "__main__":
    unittest.main()
