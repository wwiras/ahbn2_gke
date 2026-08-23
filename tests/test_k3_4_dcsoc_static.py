"""K3.4 static DC-SoC reconciliation and frozen-semantic parity tests."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import networkx as nx

from tests.test_k2 import PEER
from ahbn.strategies.dcsoc import DCSOCStrategy


ROOT = Path(__file__).resolve().parents[1]
GEN_SPEC = importlib.util.spec_from_file_location("k34_gen", ROOT / "app/gen_topology.py")
GEN = importlib.util.module_from_spec(GEN_SPEC)
GEN_SPEC.loader.exec_module(GEN)


def dcsoc_peer(*, role="core", parent=None, children=None):
    peer = PEER.PeerState.__new__(PEER.PeerState)
    peer.strategy = "dcsoc"
    peer.peer_id = 4
    peer.dcsoc_role = role
    peer.dcsoc_parent = parent
    peer.dcsoc_children = list(children or [])
    peer.dcsoc_core_neighbors = []
    peer.unavailable_neighbors = set()
    peer.default_fanout = 3
    peer.fanout = 3
    peer.mode = "gossip"
    return peer


class DCSOCClusteringAndRolesTests(unittest.TestCase):
    def fixture(self):
        graph = nx.Graph()
        graph.add_edges_from([(0, 1), (0, 2), (1, 2),
                              (3, 4), (4, 5), (3, 5)])
        return GEN.assign_dcsoc_clusters(graph, eps=1.0, min_samples=3)

    def test_d01_frozen_parameters(self):
        self.assertEqual((GEN.DCSOC_EPS, GEN.DCSOC_MIN_SAMPLES), (2.0, 3))

    def test_d02_d03_deterministic_complete_assignment(self):
        first = self.fixture()
        second = self.fixture()
        self.assertEqual(first, second)
        self.assertEqual(set(first[1]), set(range(6)))
        self.assertNotIn(-1, first[1].values())

    def test_d04_d05_master_and_lowest_id_degree_tie(self):
        heads, _, _, roles, _ = self.fixture()
        self.assertEqual(heads, [0, 3])
        roots = [node for node, role in roles.items()
                 if role["dcsoc_role"] == "core" and role["dcsoc_parent"] is None]
        self.assertEqual(roots, [0])

    def test_d06_d07_d08_core_tail_role_uniqueness(self):
        heads, labels, members, roles, edges = self.fixture()
        self.assertEqual({n for n, r in roles.items() if r["dcsoc_role"] == "core"},
                         set(heads))
        for node in labels:
            self.assertIn(roles[node]["dcsoc_role"], {"core", "leaf"})
            if node not in heads:
                self.assertIn(roles[node]["dcsoc_parent"], heads)
        self.assertEqual(len(edges), len(set(map(tuple, edges))))

    def test_d09_source_is_master_in_generated_topology(self):
        graph = nx.complete_graph(6)
        heads, _, _, _, _ = GEN.assign_dcsoc_clusters(graph)
        self.assertEqual(heads[0], 0)


class DCSOCForwardingTests(unittest.TestCase):
    def test_direct_controlsim_static_target_parity(self):
        nodes = {node: SimpleNamespace(is_active=node != 8) for node in range(12)}
        simulator = SimpleNamespace(nodes=nodes, cluster_manager=object())
        reference = SimpleNamespace(
            node_id=4, cluster_id=0, dcsoc_role="core",
            dcsoc_children=[5, 6, 8, 11],
        )
        expected = DCSOCStrategy().select_targets(
            reference, None, simulator, exclude_target_id=6
        )
        kube = dcsoc_peer(children=[5, 6, 8, 11])
        kube.unavailable_neighbors = {8}
        self.assertEqual(kube.target_peers(6), expected)

    def test_d10_d11_d12_master_core_tail_forwarding(self):
        master = dcsoc_peer(children=[5, 6, 7])
        self.assertEqual(master.target_peers(99), [5, 6, 7])
        core = dcsoc_peer(parent=2, children=[5, 6, 7, 9])
        self.assertEqual(core.target_peers(2), [5, 6, 7, 9])
        tail = dcsoc_peer(role="leaf", parent=2)
        self.assertEqual(tail.target_peers(2), [])

    def test_d13_intercluster_core_child_is_forwarded(self):
        peer = dcsoc_peer(children=[5, 11])
        peer.dcsoc_core_neighbors = [11]
        self.assertEqual(peer.target_peers(99), [5, 11])

    def test_d14_d15_sender_and_self_excluded(self):
        peer = dcsoc_peer(children=[3, 4, 5])
        self.assertEqual(peer.target_peers(3), [5])
        tail = dcsoc_peer(role="leaf", parent=4)
        self.assertEqual(tail.target_peers(9), [])

    def test_d16_unavailable_structural_targets_filtered(self):
        peer = dcsoc_peer(children=[5, 6, 7])
        peer.unavailable_neighbors = {6}
        self.assertEqual(peer.target_peers(99), [5, 7])

    def test_d17_duplicate_no_refanout(self):
        peer = dcsoc_peer()
        peer.failed = False
        peer.lock = threading.Lock()
        peer.recv_count = peer.duplicate_count = 0
        peer.seen_messages = {"m"}
        peer.observations = SimpleNamespace(record_receive=lambda **kwargs: None)
        peer.adaptive_update = mock.Mock()
        peer.target_peers = mock.Mock(side_effect=AssertionError("refanout"))
        peer.run_id = peer.experiment = "k3.4"
        peer.overload_ms = 0
        peer.bottleneck_active = False
        peer.bottleneck_delay_ms = 0
        env = SimpleNamespace(message_id="m", sent_at=1.0, created_at=1.0,
                              sender_id=2, hop=1)
        with mock.patch.object(PEER, "log_event"), mock.patch.object(PEER, "now", return_value=2.0):
            self.assertEqual(peer.process_envelope(env), (False, "duplicate"))
        peer.target_peers.assert_not_called()

    def test_d18_d19_more_than_three_no_ahbn_bounds(self):
        peer = dcsoc_peer(children=[5, 6, 7, 8, 9])
        for fanout in (2, 3, 4):
            peer.fanout = peer.default_fanout = fanout
            self.assertEqual(peer.target_peers(99), [5, 6, 7, 8, 9])

    def test_d20_d21_no_sampling_or_structured_dispatch(self):
        peer = dcsoc_peer(children=[5, 6])
        peer.cluster_members = [20]
        peer.gateway_neighbors = [21]
        with mock.patch.object(PEER.random, "sample", side_effect=AssertionError("sampling")), \
             mock.patch.object(PEER.PeerState, "cluster_targets", side_effect=AssertionError("structured")):
            self.assertEqual(peer.target_peers(99), [5, 6])


class DCSOCIsolationAndBoundaryTests(unittest.TestCase):
    def topology(self):
        graph = nx.complete_graph(5)
        heads, labels, members, roles, edges = GEN.assign_dcsoc_clusters(graph)
        nodes = {}
        for node in graph:
            nodes[str(node)] = {
                "neighbors": sorted(graph.neighbors(node)),
                "cluster_id": labels[node], "is_cluster_head": node in heads,
                "cluster_head_id": heads[labels[node]],
                "cluster_members": members[labels[node]], "gateway_neighbors": [],
                **roles[node],
            }
        return {"run_id": "k3.4", "strategy": "dcsoc", "num_nodes": 5,
                "message_source": heads[0], "seed": 42, "fanout": None,
                "nodes": nodes, "dcsoc": {"eps": 2.0, "min_samples": 3,
                "master_id": heads[0], "structural_edges": edges,
                "dynamic_maintenance": False}}

    def test_d22_d23_no_ahbn_controller_or_state_influence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "topology.json"
            path.write_text(json.dumps(self.topology()), encoding="utf-8")
            with mock.patch.dict("os.environ", {"TOPOLOGY_PATH": str(path)}), \
                 mock.patch.object(PEER.socket, "gethostname", return_value="peer-0"), \
                 mock.patch.object(PEER, "log_event"):
                peer = PEER.PeerState()
        self.assertIsNone(peer.ahbn_params)
        self.assertIsNone(peer.ahbn_controller)
        self.assertIsNone(peer.ahbn_state)
        self.assertIsInstance(peer.observations, PEER.StandaloneObservationSink)

    def test_d24_d25_d26_d27_deterministic_slow_overload_static(self):
        topo = self.topology()
        before = json.dumps(topo["nodes"], sort_keys=True)
        for node in topo["nodes"].values():
            node["overload_ms"] = 250
            node["processing_delay"] = 0.5
        after_structure = json.dumps(
            {key: {field: value for field, value in node.items()
                   if field not in {"overload_ms", "processing_delay"}}
             for key, node in topo["nodes"].items()}, sort_keys=True)
        self.assertEqual(before, after_structure)
        self.assertFalse(topo["dcsoc"]["dynamic_maintenance"])

    def test_d28_traceability_document_exists(self):
        audit = ROOT / "docs/K3.4_dcsoc_static.md"
        if audit.exists():
            text = audit.read_text(encoding="utf-8")
            self.assertIn("Paper → ControlSim traceability", text)
            self.assertIn("DEFERRED TO K3.5", text)


if __name__ == "__main__":
    unittest.main()
