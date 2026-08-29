"""Synthetic parser/classifier tests for the external H2 analysis."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.k5_h2_peer_selection_analysis import analyze_decisions, classify, load_jsonl


def decision(*, eligible=None, selected=None, omitted=None, timestamp=10.0):
    eligible = [0, 3, 9, 10, 12, 13, 14] if eligible is None else eligible
    selected = [0, 14, 3, 13] if selected is None else selected
    omitted = [peer for peer in eligible if peer not in selected] if omitted is None else omitted
    return {
        "event": "ahbn_forwarding_decision", "ts": timestamp,
        "run_id": "run", "message_id": "m", "sender": 2, "incoming_sender": 1,
        "mode": "gossip", "score": 0.4, "fanout_requested": 4,
        "eligible_neighbors": eligible, "selected_peers": selected,
        "omitted_eligible_peers": omitted,
    }


def outcome(destination, kind="forward", timestamp=11.0):
    return {"event": kind, "ts": timestamp, "run_id": "run", "message_id": "m",
            "peer_id": 2, "dst_peer": destination}


class H2ClassifierTests(unittest.TestCase):
    def test_case_1_selection_opportunity(self):
        rows = [decision(), outcome(0, "forward_duplicate_ack")]
        result = analyze_decisions(rows, 42)[0]
        self.assertTrue(result["duplicate_with_omitted_eligible"])
        self.assertEqual(result["classification"], "SELECTION_OPPORTUNITY_SIGNAL")
        self.assertIn("not assumed unseen", result["classification_evidence"])

    def test_case_2_fanout_pressure(self):
        rows = [decision()] + [outcome(peer) for peer in (0, 14, 3, 13)]
        self.assertEqual(analyze_decisions(rows, 42)[0]["classification"],
                         "FANOUT_PRESSURE_SIGNAL")

    def test_case_3_mixed(self):
        rows = [decision(), outcome(0, "forward_duplicate_ack"),
                outcome(14), outcome(3), outcome(13)]
        self.assertEqual(analyze_decisions(rows, 42)[0]["classification"], "MIXED")

    def test_case_4_no_omission(self):
        rows = [decision(eligible=[0, 3], selected=[0, 3], omitted=[])]
        self.assertEqual(analyze_decisions(rows, 42)[0]["classification"], "NO_OMISSION")

    def test_case_5_missing_outcomes(self):
        self.assertEqual(analyze_decisions([decision()], 42)[0]["classification"],
                         "INSUFFICIENT_EVIDENCE")

    def test_duplicate_trace_lines_are_deduplicated(self):
        d = decision()
        events = [d, dict(d)] + [outcome(peer) for peer in (0, 14, 3, 13)]
        self.assertEqual(len(analyze_decisions(events, 42)), 1)

    def test_conflicting_duplicate_and_malformed_records_fail(self):
        other = decision(); other["score"] = 0.5
        with self.assertRaises(ValueError):
            analyze_decisions([decision(), other], 42)
        with self.assertRaises(ValueError):
            analyze_decisions([decision(omitted=[9])], 42)

    def test_race_sensitive_timestamp_ignores_predecision_outcome(self):
        events = [decision(), outcome(0, "forward_duplicate_ack", timestamp=9.99)]
        got = analyze_decisions(events, 42)[0]
        self.assertEqual(got["selected_duplicate_count"], 0)
        self.assertEqual(got["classification"], "INSUFFICIENT_EVIDENCE")

    def test_empty_sets_zero_counts_and_division_guard_inputs(self):
        got = analyze_decisions([decision(eligible=[], selected=[], omitted=[])], 42)[0]
        self.assertEqual(got["classification"], "NO_OMISSION")
        self.assertEqual(classify(omitted=1, selected=0, duplicates=0,
                                  nonduplicates=0, unknown=0, saturated=False)[0],
                         "INSUFFICIENT_EVIDENCE")

    def test_concatenated_json_and_malformed_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logs.jsonl"
            path.write_text('{"event":"a"}{"event":"b"}\n', encoding="utf-8")
            self.assertEqual([row["event"] for row in load_jsonl(path)], ["a", "b"])
            path.write_text('{"event":\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_jsonl(path)


if __name__ == "__main__":
    unittest.main()
