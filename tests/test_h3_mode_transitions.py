import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_h3_mode_transitions import classify  # noqa: E402


def decision(ts, message, peer, mode, selected):
    return {"ts": ts, "event": "ahbn_forwarding_decision", "run_id": "r",
            "message_id": message, "sender": peer, "mode": mode,
            "selected_peers": selected}


class H3ClassificationTests(unittest.TestCase):
    def transitions(self, events):
        return classify(events)[0]

    def test_no_transition(self):
        self.assertEqual([], self.transitions([decision(1, "m", 2, "cluster", [3]),
                                               decision(2, "m", 2, "cluster", [4])]))

    def test_transition_without_overlap(self):
        got = self.transitions([decision(1, "m", 2, "cluster", [3, 4]),
                                decision(2, "m", 2, "gossip", [5, 6])])
        self.assertEqual("CLEAN_TRANSITION", got[0]["classification"])

    def test_cluster_to_gossip_overlap(self):
        got = self.transitions([decision(1, "m", 2, "cluster", [3, 4]),
                                decision(2, "m", 2, "gossip", [3, 5])])
        self.assertEqual([3], __import__("json").loads(got[0]["overlapping_recipients"]))

    def test_gossip_to_cluster_overlap(self):
        got = self.transitions([decision(1, "m", 2, "gossip", [3, 4]),
                                decision(2, "m", 2, "cluster", [4, 5])])
        self.assertEqual("Gossip→Cluster", got[0]["direction"])

    def test_unrelated_duplicate_is_not_attributed(self):
        events = [decision(1, "m", 2, "cluster", [3]),
                  decision(2, "m", 2, "gossip", [3]),
                  {"ts": 3, "event": "forward_duplicate_ack", "run_id": "r",
                   "message_id": "m", "peer_id": 9, "dst_peer": 3}]
        self.assertEqual("OVERLAPPING_RECIPIENT", self.transitions(events)[0]["classification"])

    def test_transition_after_completion_is_not_active(self):
        events = [decision(1, "m", 2, "cluster", [3]),
                  {"ts": 2, "event": "ahbn_controller_trace", "run_id": "r",
                   "peer_id": 2, "mode": "gossip"}]
        self.assertEqual([], self.transitions(events))


if __name__ == "__main__":
    unittest.main()
