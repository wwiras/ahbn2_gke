"""Zero-semantic-change tests for the temporary H2 trace."""

from __future__ import annotations

import random
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.test_k2 import PEER, peer_fixture


class H2InstrumentationSemanticsTests(unittest.TestCase):
    def prepare(self, *, mode="gossip", fanout=4, head=False):
        peer = peer_fixture(mode=mode, fanout=fanout, head=head)
        peer.run_id = peer.experiment = "h2-local"
        peer.ahbn_state = SimpleNamespace(score=0.4, weight=0.6)
        return peer

    def test_gossip_targets_order_and_rng_progression_are_unchanged(self):
        candidates = [1, 2, 3, 4, 5]
        random.seed(6102)
        expected = random.sample(candidates, 4)
        expected_next = random.random()

        peer = self.prepare()
        peer.neighbors = list(candidates)
        random.seed(6102)
        with mock.patch.object(PEER, "log_event") as logged:
            actual = peer.target_peers(sender_id=99, message_id="m1")
            actual_next = random.random()

        self.assertEqual(actual, expected)
        self.assertEqual(actual_next, expected_next)
        self.assertEqual(logged.call_count, 1)
        trace = logged.call_args.kwargs
        self.assertEqual(trace["event"], "ahbn_forwarding_decision")
        self.assertEqual(trace["eligible_neighbors"], candidates)
        self.assertEqual(trace["selected_peers"], expected)
        self.assertEqual(trace["omitted_eligible_peers"], [x for x in candidates if x not in expected])

    def test_lightweight_fixture_without_runtime_metadata_is_supported(self):
        peer = peer_fixture(mode="gossip", fanout=2)
        self.assertFalse(hasattr(peer, "run_id"))
        self.assertFalse(hasattr(peer, "experiment"))
        random.seed(11)
        with mock.patch.object(PEER, "log_event") as logged:
            targets = peer.target_peers(sender_id=99, message_id="minimal")
        self.assertEqual(len(targets), 2)
        self.assertIsNone(logged.call_args.kwargs["run_id"])
        self.assertIsNone(logged.call_args.kwargs["experiment"])

    def test_trace_occurs_after_random_selection(self):
        peer = self.prepare()
        peer.neighbors = [1, 2, 3, 4, 5]
        order = []
        original_sample = random.sample

        def sampled(population, k):
            result = original_sample(population, k)
            order.append(("selected", list(result)))
            return result

        def logged(**fields):
            order.append(("logged", list(fields["selected_peers"])))

        random.seed(42)
        with mock.patch.object(PEER.random, "sample", side_effect=sampled), \
             mock.patch.object(PEER, "log_event", side_effect=logged):
            targets = peer.target_peers(sender_id=99, message_id="m2")
        self.assertEqual([step for step, _ in order], ["selected", "logged"])
        self.assertEqual(order[0][1], targets)
        self.assertEqual(order[1][1], targets)

    def test_cluster_targets_and_order_are_unchanged(self):
        peer = self.prepare(mode="cluster", fanout=3, head=True)
        peer.cluster_members = [0, 1, 2, 3, 4]
        peer.gateway_neighbors = [7, 8]
        with mock.patch.object(PEER, "log_event") as logged:
            targets = peer.target_peers(sender_id=99, message_id="m3")
        self.assertEqual(targets, [7, 1, 2])
        trace = logged.call_args.kwargs
        self.assertEqual(trace["eligible_neighbors"], [7, 1, 2, 3, 4, 8])
        self.assertEqual(trace["selected_peers"], targets)

    def test_logged_copies_cannot_mutate_forward_targets(self):
        peer = self.prepare(fanout=2)
        peer.neighbors = [1, 2, 3]

        def mutate_trace(**fields):
            fields["selected_peers"].clear()
            fields["eligible_neighbors"].clear()

        random.seed(7)
        with mock.patch.object(PEER, "log_event", side_effect=mutate_trace):
            targets = peer.target_peers(sender_id=99, message_id="m4")
        self.assertEqual(len(targets), 2)


if __name__ == "__main__":
    unittest.main()
