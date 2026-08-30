import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.analyze_h4_seen_cache import diagnose, load_events


def event(kind, ts, peer=1, src=0):
    return {"event": kind, "ts": ts, "run_id": "r", "message_id": "m",
            "peer_id": peer, "src_peer": src}


class SeenCacheAnalysisTests(unittest.TestCase):
    def test_real_decision_schema_uses_sender_without_peer_id(self):
        rows = [event("received_new", 1),
                {"event": "ahbn_forwarding_decision", "ts": 2, "run_id": "r",
                 "message_id": "m", "sender": 1, "selected_peers": [2, 3]}]
        summary, violations, _ = diagnose(rows)
        self.assertEqual(summary["forwarding_decisions"], 1)
        self.assertNotIn("MISSING_IDENTITY", {row["kind"] for row in violations})

    def test_concatenated_json_records_are_loaded(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "logs.jsonl"
            path.write_text('{"event":"received_new","ts":1}{"event":"received_duplicate","ts":2}\n')
            rows = load_events([path])
        self.assertEqual([row["event"] for row in rows], ["received_new", "received_duplicate"])
        self.assertEqual([row["_object"] for row in rows], [1, 2])

    def test_first_receipt_only(self):
        summary, violations, _ = diagnose([event("received_new", 1)])
        self.assertEqual(violations, [])
        self.assertEqual(summary["peer_message_first_receipts"], 1)
        self.assertEqual(summary["duplicate_receipts"], 0)

    def test_valid_new_then_duplicate(self):
        summary, violations, _ = diagnose([event("received_new", 1), event("received_duplicate", 2)])
        self.assertEqual(violations, [])
        self.assertEqual(summary["duplicate_receipts"], 1)

    def test_duplicate_without_prior_new_is_rejected(self):
        _, violations, _ = diagnose([event("received_duplicate", 1)])
        self.assertEqual(violations[0]["kind"], "DUPLICATE_WITHOUT_PRIOR_NEW")

    def test_multiple_first_receipts_are_rejected(self):
        _, violations, _ = diagnose([event("received_new", 1), event("received_new", 2)])
        self.assertEqual(violations[0]["kind"], "MULTIPLE_FIRST_RECEIPTS")

    def test_duplicate_does_not_create_second_decision(self):
        rows = [event("received_new", 1),
                {**event("ahbn_forwarding_decision", 2), "sender": 1},
                event("received_duplicate", 3)]
        _, violations, _ = diagnose(rows)
        self.assertEqual(violations, [])

    def test_multipath_duplicate_is_classified(self):
        rows = [event("received_new", 1, src=2), event("received_duplicate", 2, src=3)]
        summary, violations, _ = diagnose(rows)
        self.assertEqual(violations, [])
        self.assertEqual(summary["multipath_duplicate_receipts"], 1)

    def test_same_sender_duplicate_is_classified(self):
        rows = [event("received_new", 1, src=2), event("received_duplicate", 2, src=2)]
        summary, violations, _ = diagnose(rows)
        self.assertEqual(violations, [])
        self.assertEqual(summary["same_sender_duplicate_receipts"], 1)

    def test_duplicate_triggered_refanout_is_rejected(self):
        rows = [event("received_new", 1),
                {**event("ahbn_forwarding_decision", 2), "sender": 1, "selected_peers": [4]},
                event("received_duplicate", 3),
                {**event("ahbn_forwarding_decision", 4), "sender": 1, "selected_peers": [5]}]
        _, violations, _ = diagnose(rows)
        self.assertIn("DUPLICATE_TRIGGERED_REFANOUT", {row["kind"] for row in violations})

    def test_duplicate_receipt_and_ack_reconcile(self):
        rows = [event("received_new", 1), event("received_duplicate", 2),
                {"event": "forward_duplicate_ack", "ts": 3, "run_id": "r",
                 "message_id": "m", "peer_id": 0, "dst_peer": 1}]
        summary, _, _ = diagnose(rows)
        self.assertEqual(summary["unmatched_duplicate_acks"], 0)
        self.assertEqual(summary["unmatched_duplicate_receipts"], 0)

    def test_runs_are_independent_analysis_scopes(self):
        rows = [event("received_new", 1), {**event("received_new", 2), "run_id": "r2"}]
        summary, violations, _ = diagnose(rows)
        self.assertEqual(violations, [])
        self.assertEqual(summary["runs"], 2)

    def test_duplicate_before_delayed_new_log_is_ordering_not_cache_loss(self):
        rows = [event("received_duplicate", 1, src=2), event("received_new", 2, src=3)]
        summary, violations, cases = diagnose(rows)
        self.assertEqual(violations, [])
        self.assertEqual(summary["duplicate_before_delayed_new_log"], 1)
        self.assertEqual(cases[0]["classification"], "PARSER_OR_ORDERING")


if __name__ == "__main__":
    unittest.main()
