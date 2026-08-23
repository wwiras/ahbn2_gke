"""K3.5 event-driven DC-SoC dynamic-maintenance reconciliation tests."""

from __future__ import annotations

import copy
import importlib.util
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import networkx as nx

from tests.test_k2 import PEER


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
from dcsoc_maintenance import DCSOCMaintenance  # noqa: E402

GEN_SPEC = importlib.util.spec_from_file_location("k35_gen", APP / "gen_topology.py")
GEN = importlib.util.module_from_spec(GEN_SPEC)
GEN_SPEC.loader.exec_module(GEN)


def topology() -> dict:
    graph = nx.Graph()
    graph.add_edges_from([
        (0, 1), (0, 2), (1, 2),
        (3, 4), (3, 5), (4, 5), (3, 6),
    ])
    heads, clusters, members, roles, edges = GEN.assign_dcsoc_clusters(
        graph, eps=1.0, min_samples=3
    )
    nodes = {}
    for node_id in graph:
        cluster_id = clusters[node_id]
        nodes[str(node_id)] = {
            "neighbors": sorted(graph.neighbors(node_id)),
            "cluster_id": cluster_id,
            "is_cluster_head": node_id in heads,
            "cluster_head_id": heads[cluster_id],
            "cluster_members": [n for n in members[cluster_id] if n != node_id],
            "gateway_neighbors": [],
            **roles[node_id],
        }
    return {
        "strategy": "dcsoc", "nodes": nodes,
        "dcsoc": {"eps": 1.0, "min_samples": 3, "structural_edges": edges},
    }


class AvailabilityAndLocalRepairTests(unittest.TestCase):
    def test_m01_to_m04_transition_idempotence(self):
        state = DCSOCMaintenance(topology())
        self.assertTrue(state.set_availability(1, False, reason="failure"))
        self.assertFalse(state.set_availability(1, False, reason="duplicate"))
        self.assertTrue(state.set_availability(1, True, reason="return"))
        self.assertFalse(state.set_availability(1, True, reason="duplicate"))
        self.assertEqual([e["maintenance_action"] for e in state.events], ["leave", "rejoin"])

    def test_m05_to_m07_tail_detach_no_election_and_rejoin(self):
        state = DCSOCMaintenance(topology())
        before = state.core_replacement_count
        state.set_availability(1, False, reason="leave")
        self.assertNotIn((0, 1), state.structural_edges)
        self.assertNotIn(1, state.nodes[0]["dcsoc_children"])
        self.assertEqual(state.core_replacement_count, before)
        state.set_availability(1, True, reason="return")
        self.assertEqual(state.nodes[1]["dcsoc_parent"], 0)
        self.assertEqual(state.nodes[1]["cluster_id"], 0)

    def test_m08_to_m16_core_local_repair_rule_and_isolation(self):
        state = DCSOCMaintenance(topology())
        unaffected = copy.deepcopy({n: state.nodes[n] for n in (4, 5, 6)})
        state.set_availability(0, False, reason="core_failure")
        self.assertEqual(state.events[-1]["replacement_core"], 1)
        self.assertEqual(state.nodes[1]["dcsoc_role"], "core")
        self.assertNotIn(0, {node for edge in state.structural_edges for node in edge})
        self.assertEqual(state.nodes[2]["dcsoc_parent"], 1)
        self.assertEqual(state.nodes[3]["dcsoc_parent"], 1)
        self.assertEqual({n: state.nodes[n] for n in (4, 5, 6)}, unaffected)
        self.assertEqual(state.core_replacement_count, 1)
        self.assertEqual(state.recluster_count, 0)

    def test_m10_m11_candidate_cluster_and_inactive_exclusion(self):
        state = DCSOCMaintenance(topology())
        state.set_availability(1, False)
        state.set_availability(0, False)
        self.assertEqual(state.events[-1]["replacement_core"], 2)
        self.assertNotEqual(state.events[-1]["replacement_core"], 3)

    def test_m12_m13_highest_degree_and_lowest_id_tie(self):
        state = DCSOCMaintenance(topology())
        state.set_availability(3, False)
        self.assertEqual(state.events[-1]["replacement_core"], 4)

    def test_m14_no_candidate_safe(self):
        state = DCSOCMaintenance(topology())
        state.set_availability(1, False)
        state.set_availability(2, False)
        state.set_availability(0, False)
        self.assertIsNone(state.events[-1]["replacement_core"])
        self.assertEqual(state.core_replacement_count, 0)

    def test_m17_m18_former_core_returns_as_leaf(self):
        state = DCSOCMaintenance(topology())
        state.set_availability(0, False)
        state.set_availability(0, True)
        self.assertEqual(state.nodes[0]["dcsoc_role"], "leaf")
        self.assertEqual(state.nodes[0]["dcsoc_parent"], 1)
        self.assertEqual(state.nodes[0]["cluster_id"], 0)


class ExplicitDUAndBoundaryTests(unittest.TestCase):
    def test_m19_to_m23_explicit_du_active_only_frozen_and_deterministic(self):
        original = topology()
        state = DCSOCMaintenance(original)
        state.set_availability(6, False)
        state.explicit_du()
        first = state.snapshot()
        self.assertEqual(state.recluster_count, 1)
        self.assertNotIn(6, state.events[-1]["active_peers"])
        self.assertEqual(state.structural_generation, 1)
        state.explicit_du()
        second = state.snapshot()
        self.assertEqual(first["nodes"], second["nodes"])
        self.assertEqual(first["structural_edges"], second["structural_edges"])
        self.assertEqual(state.recluster_count, 2)

    def test_m24_m25_local_repairs_never_recluster(self):
        state = DCSOCMaintenance(topology())
        state.set_availability(1, False)
        state.set_availability(0, False)
        self.assertEqual(state.recluster_count, 0)

    def test_m26_m27_slow_and_asymmetric_delay_are_observational(self):
        topo = topology()
        state = DCSOCMaintenance(topo)
        before = state.snapshot()
        state.nodes[0]["overload_ms"] = 500
        state.nodes[0]["latency_ms"] = 900
        state.nodes[1]["latency_ms"] = 2
        after = state.snapshot()
        for snapshot in (before, after):
            for config in snapshot["nodes"].values():
                config.pop("overload_ms", None)
                config.pop("latency_ms", None)
        self.assertEqual(before, after)
        self.assertEqual(state.events, [])

    def test_m28_to_m32_instrumentation_and_real_timing(self):
        ticks = iter([10.0, 10.25])
        walls = iter([100.0, 100.3])
        state = DCSOCMaintenance(topology(), timer=lambda: next(ticks), clock=lambda: next(walls))
        state.set_availability(0, False, reason="fixture")
        event = state.events[-1]
        self.assertEqual(event["maintenance_start"], 100.0)
        self.assertEqual(event["maintenance_end"], 100.3)
        self.assertEqual(event["maintenance_duration"], 0.25)
        self.assertEqual(event["maintenance_reason"], "fixture")
        self.assertEqual(state.core_replacement_count, 1)
        self.assertEqual(state.recluster_count, 0)
        self.assertEqual(state.rejoin_assignment_count, 0)


class IsolationAndForwardingTests(unittest.TestCase):
    def test_runtime_rpc_applies_transition_and_explicit_du(self):
        runtime = SimpleNamespace(
            dcsoc_maintenance=DCSOCMaintenance(topology()),
            peer_id=1, lock=threading.Lock(), run_id="k3.5", experiment="k3.5",
        )
        service = PEER.PeerService(runtime)
        with mock.patch.object(PEER, "log_event"):
            reply = service.ApplyDCSOCMaintenance(
                SimpleNamespace(node_id=0, available=False, explicit_du=False,
                                reason="core_failure"), None,
            )
            self.assertTrue(reply.ok)
            self.assertEqual(runtime.dcsoc_role, "core")
            reply = service.ApplyDCSOCMaintenance(
                SimpleNamespace(node_id=0, available=False, explicit_du=True,
                                reason="explicit_du"), None,
            )
            self.assertTrue(reply.ok)
        self.assertEqual(runtime.dcsoc_maintenance.recluster_count, 1)

    def test_m33_m34_no_ahbn_state_or_controller(self):
        state = DCSOCMaintenance(topology())
        self.assertFalse(any("ahbn" in name.lower() for name in vars(state)))
        with mock.patch.object(PEER.PeerState, "adaptive_update", side_effect=AssertionError("AHBN")):
            state.set_availability(0, False)

    def test_m35_m36_reject_non_dcsoc_and_no_dispatch_changes(self):
        for strategy in ("gossip", "cluster"):
            other = topology()
            other["strategy"] = strategy
            with self.assertRaises(ValueError):
                DCSOCMaintenance(other)

    def test_m37_m38_forwarding_and_sender_self_after_repair(self):
        state = DCSOCMaintenance(topology())
        state.set_availability(0, False)
        peer = PEER.PeerState.__new__(PEER.PeerState)
        peer.peer_id = 1
        peer.lock = threading.Lock()
        peer.strategy = "dcsoc"
        peer.mode = "gossip"
        peer.fanout = None
        peer.unavailable_neighbors = {0}
        state.sync_peer(peer)
        self.assertEqual(peer.target_peers(2), [3])
        self.assertNotIn(peer.peer_id, peer.target_peers(99))

    def test_m39_duplicate_no_refanout_after_repair(self):
        state = DCSOCMaintenance(topology())
        state.set_availability(0, False)
        peer = PEER.PeerState.__new__(PEER.PeerState)
        peer.peer_id = 1
        peer.lock = threading.Lock()
        state.sync_peer(peer)
        peer.strategy = "dcsoc"
        peer.mode = "gossip"
        peer.fanout = None
        peer.failed = False
        peer.recv_count = peer.duplicate_count = 0
        peer.seen_messages = {"m"}
        peer.observations = SimpleNamespace(record_receive=lambda **kwargs: None)
        peer.adaptive_update = mock.Mock()
        peer.target_peers = mock.Mock(side_effect=AssertionError("refanout"))
        peer.run_id = peer.experiment = "k3.5"
        peer.overload_ms = 0
        peer.bottleneck_active = False
        peer.bottleneck_delay_ms = 0
        envelope = SimpleNamespace(message_id="m", sent_at=1.0, created_at=1.0,
                                   sender_id=2, hop=1)
        with mock.patch.object(PEER, "log_event"), mock.patch.object(PEER, "now", return_value=2.0):
            self.assertEqual(peer.process_envelope(envelope), (False, "duplicate"))
        peer.target_peers.assert_not_called()

    def test_m40_m41_deterministic_replays(self):
        def replay():
            state = DCSOCMaintenance(topology())
            state.set_availability(3, False)
            state.set_availability(3, True)
            return state.snapshot()
        self.assertEqual(replay(), replay())


if __name__ == "__main__":
    unittest.main()
