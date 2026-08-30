"""Focused local tests for the K5 H2 selector-only A/B diagnostic."""

from __future__ import annotations

import random
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

from tests.test_k2 import PEER, peer_fixture
from ahbn_controller import AHBNParams, AHBNState, CanonicalAHBNController
from scripts.k5_h2_selector_ab_analysis import (
    expected_selected_count, prepare_config, summarize_run,
)


def h2_peer(*, treatment="selector_control", seed=42, mode="gossip", fanout=3):
    peer = peer_fixture(mode=mode, fanout=fanout, head=True)
    peer.h2_selector_treatment = treatment
    peer.h2_seed = seed
    peer.h2_repetition = 1
    peer.run_id = peer.experiment = "h2-test"
    peer.ahbn_state = SimpleNamespace(score=0.0, weight=0.5)
    return peer


class SelectorABTests(unittest.TestCase):
    def test_analysis_accepts_actual_persisted_selector_schema(self):
        for treatment in ("selector_control", "seeded_uniform"):
            row = {
                "event": "ahbn_forwarding_decision",
                "treatment": treatment,
                "controller_fanout": 4,
                "fanout_requested": 4,
                "eligible_neighbors": [1, 2, 3, 4, 5, 6],
                "selected_peers": [1, 2, 3, 4],
            }
            self.assertEqual(expected_selected_count(row), 4)

    def test_analysis_marks_missing_optional_fanout_unavailable(self):
        row = {
            "event": "ahbn_forwarding_decision",
            "treatment": "selector_control",
            "eligible_neighbors": [1, 2, 3],
            "selected_peers": [1, 2, 3],
        }
        self.assertIsNone(expected_selected_count(row))

    def test_summarize_run_handles_actual_and_optional_missing_schema(self):
        for treatment, include_fanout in (
            ("selector_control", True), ("seeded_uniform", True),
            ("selector_control", False),
        ):
            with self.subTest(treatment=treatment, include_fanout=include_fanout), \
                 tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                (run_dir / "metrics.json").write_text(
                    '{"delivery_ratio": 0.5, "propagation_delay": 0.1, '
                    '"duplicates": 1, "total_forwards": 2}', encoding="utf-8"
                )
                decision = {
                    "event": "ahbn_forwarding_decision", "treatment": treatment,
                    "seed": 42, "eligible_neighbors": [1, 2, 3, 4, 5],
                    "selected_peers": [1, 2, 3, 4], "unavailable_neighbors": [],
                }
                if include_fanout:
                    decision.update(controller_fanout=4, fanout_requested=4)
                (run_dir / "logs.jsonl").write_text(
                    "\n".join(json.dumps(row) for row in (
                        decision,
                        {"event": "message_injected", "message_id": "m1"},
                        {"event": "received_new", "message_id": "m1", "peer_id": 0},
                    )) + "\n", encoding="utf-8"
                )
                result = summarize_run(run_dir, 42, 1, treatment)
                self.assertEqual(result["fanout_diagnostic_unavailable_rows"],
                                 0 if include_fanout else 1)
                self.assertEqual(result["fanout_violations"],
                                 0 if include_fanout else None)

    def test_t9_default_is_control_and_config_is_frozen(self):
        peer = peer_fixture(mode="gossip", fanout=2)
        self.assertFalse(hasattr(peer, "h2_selector_treatment"))
        peer.neighbors = [1, 2, 3]
        random.seed(27)
        expected = random.sample(peer.neighbors, 2)
        random.seed(27)
        with mock.patch.object(PEER, "log_event"):
            self.assertEqual(peer.target_peers(99, "default"), expected)
        base = Path(__file__).resolve().parents[1] / "experiments" / "k5_exp08_ahbn.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run.yaml"
            prepare_config(base, out, 42, 1, "seeded_uniform")
            text = out.read_text(encoding="utf-8")
        self.assertIn("overloadDelayMs: 1400", text)
        self.assertIn("overload_factor: 2.0", text)
        self.assertIn("repetition: 1", text)
        self.assertIn("treatment: seeded_uniform", text)

    def test_t1_control_reproduces_existing_selector_and_rng_progression(self):
        eligible = [1, 2, 3, 4, 5]
        random.seed(913)
        expected = random.sample(eligible, 3)
        expected_next = random.random()
        peer = h2_peer()
        peer.neighbors = eligible
        random.seed(913)
        with mock.patch.object(PEER, "log_event"):
            selected = peer.target_peers(99, "event-1")
        self.assertEqual(selected, expected)
        self.assertEqual(random.random(), expected_next)

    def test_t2_candidate_selects_only_from_existing_eligible_set(self):
        peer = h2_peer(treatment="seeded_uniform", fanout=4)
        eligible = [9, 3, 9, 7, 5, 3, 1]
        selected = peer.h2_seeded_uniform_selection(eligible, 4, "event-2")
        self.assertTrue(set(selected).issubset(set(eligible)))

    def test_t3_candidate_preserves_canonical_fanout_or_eligible_count(self):
        peer = h2_peer(treatment="seeded_uniform", fanout=4)
        eligible = [9, 3, 9, 7, 5, 3, 1]
        selected = peer.h2_seeded_uniform_selection(eligible, 4, "event-3")
        self.assertEqual(len(selected), 4)
        self.assertEqual(
            len(peer.h2_seeded_uniform_selection([3, 3, 8], 4, "short")), 2
        )

    def test_t4_candidate_has_no_duplicate_recipient(self):
        peer = h2_peer(treatment="seeded_uniform", fanout=4)
        selected = peer.h2_seeded_uniform_selection([9, 3, 9, 7, 5, 3, 1], 4, "event-4")
        self.assertEqual(len(selected), len(set(selected)))

    def test_t5_same_seed_set_fanout_and_event_is_order_independent(self):
        a = h2_peer(treatment="seeded_uniform", seed=42)
        b = h2_peer(treatment="seeded_uniform", seed=42)
        first = a.h2_seeded_uniform_selection([8, 2, 7, 1, 5], 3, "message-x")
        second = b.h2_seeded_uniform_selection([5, 1, 8, 7, 2], 3, "message-x")
        self.assertEqual(first, second)

    def test_t6_different_seeds_can_change_selection(self):
        selections = {
            tuple(h2_peer(treatment="seeded_uniform", seed=seed)
                  .h2_seeded_uniform_selection(list(range(12)), 4, "event"))
            for seed in range(42, 47)
        }
        self.assertGreater(len(selections), 1)

    def test_t7_controller_result_is_selector_invariant(self):
        observations = (0.2, 0.7, 0.4, 0.1)
        results = []
        for treatment in ("selector_control", "seeded_uniform"):
            state = AHBNState()
            got = CanonicalAHBNController(AHBNParams()).update(state, *observations)
            results.append((got.d_hat, got.l_hat, got.u_hat, got.c_hat,
                            got.score, got.weight, got.mode, got.fanout))
            self.assertIn(treatment, {"selector_control", "seeded_uniform"})
        self.assertEqual(results[0], results[1])

    def test_t8_unavailable_excluded_and_trace_identifies_treatment(self):
        peer = h2_peer(treatment="seeded_uniform", fanout=3)
        peer.neighbors = [1, 2, 3, 4, 5]
        peer.unavailable_neighbors = {2, 4}
        with mock.patch.object(PEER, "log_event") as logged:
            selected = peer.target_peers(99, "event-8")
        self.assertEqual(set(selected), {1, 3, 5})
        self.assertTrue(set(selected).isdisjoint(peer.unavailable_neighbors))
        self.assertEqual(logged.call_args.kwargs["treatment"], "seeded_uniform")
        self.assertEqual(logged.call_args.kwargs["seed"], 42)


if __name__ == "__main__":
    unittest.main()
