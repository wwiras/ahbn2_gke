"""K5 Stage 2 forwarding-semantics regression tests."""

from __future__ import annotations

import contextlib
import math
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.test_k2 import PEER, peer_fixture
from ahbn_controller import AHBNParams, AHBNState, CanonicalAHBNController


def forwarding_peer():
    peer = peer_fixture(mode="gossip", fanout=3)
    peer.failed = False
    peer.forward_count = 0
    peer.run_id = peer.experiment = "k5-stage2"
    peer.overload_ms = 0
    peer.bottleneck_active = False
    peer.bottleneck_delay_ms = 0
    peer.observations = mock.Mock()
    peer.trigger_failure_reaction = mock.Mock()
    peer.peer_dns = mock.Mock(return_value="peer-1:50051")
    return peer


def envelope():
    return SimpleNamespace(sender_id=0, message_id="m")


class ForwardResultSemanticsTests(unittest.TestCase):
    def test_duplicate_ack_keeps_healthy_peer_available(self):
        peer = forwarding_peer()
        stub = mock.Mock()
        stub.Forward.return_value = SimpleNamespace(ok=False, message="duplicate")
        with mock.patch.object(PEER.grpc, "insecure_channel", return_value=contextlib.nullcontext()), \
             mock.patch.object(PEER.peer_pb2_grpc, "PeerServiceStub", return_value=stub), \
             mock.patch.object(PEER, "log_event"):
            peer.forward_to_peer(1, envelope())
        self.assertNotIn(1, peer.unavailable_neighbors)
        peer.observations.record_leave.assert_not_called()
        peer.trigger_failure_reaction.assert_not_called()

    def test_transport_failure_marks_peer_unavailable(self):
        peer = forwarding_peer()
        stub = mock.Mock()
        stub.Forward.side_effect = RuntimeError("unreachable")
        with mock.patch.object(PEER.grpc, "insecure_channel", return_value=contextlib.nullcontext()), \
             mock.patch.object(PEER.peer_pb2_grpc, "PeerServiceStub", return_value=stub), \
             mock.patch.object(PEER, "log_event"):
            peer.forward_to_peer(1, envelope())
        self.assertIn(1, peer.unavailable_neighbors)
        peer.observations.record_leave.assert_called_once_with()
        peer.trigger_failure_reaction.assert_called_once_with(reason="forward_failed")


class EligibilitySemanticsTests(unittest.TestCase):
    def test_ahbn_gossip_filters_unavailable_before_selection(self):
        peer = peer_fixture(mode="gossip", fanout=3)
        peer.neighbors = [1, 2, 3, 4, 5]
        peer.unavailable_neighbors = {2, 4}
        with mock.patch.object(PEER.random, "sample", wraps=PEER.random.sample) as sample:
            targets = peer.target_peers(sender_id=99)
        self.assertEqual(set(targets), {1, 3, 5})
        self.assertEqual(sample.call_args.args[0], [1, 3, 5])

    def test_standalone_gossip_filter_remains_unchanged(self):
        peer = peer_fixture(mode="gossip", fanout=3)
        peer.strategy = "gossip"
        peer.default_fanout = 3
        peer.rng = __import__("random").Random(42)
        peer.neighbors = [1, 2, 3, 4, 5]
        peer.unavailable_neighbors = {2, 4}
        self.assertEqual(set(peer.target_peers(sender_id=99)), {1, 3, 5})


class FrozenControllerTests(unittest.TestCase):
    def test_fanout_mapping_and_controller_equation_are_canonical(self):
        params = AHBNParams()
        self.assertEqual((params.min_fanout, params.default_fanout, params.max_fanout), (2, 3, 4))
        for vector, expected_fanout in (((1, 0, 0, 0), 2), ((0, 0, 0, 0), 3), ((0, 0, 1, 0), 4)):
            state = AHBNState(d_hat=vector[0], l_hat=vector[1], u_hat=vector[2], c_hat=vector[3])
            got = CanonicalAHBNController().update(state, *vector)
            score = -vector[0] + vector[1] + vector[2] + vector[3]
            self.assertAlmostEqual(got.score, score)
            self.assertEqual(got.mode, "gossip" if got.weight >= 0.5 else "cluster")
            self.assertEqual(got.fanout, expected_fanout)
            self.assertAlmostEqual(got.weight, 1 / (1 + math.exp(-score)))


if __name__ == "__main__":
    unittest.main()
