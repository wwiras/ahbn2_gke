"""K7 runtime inheriting the frozen K6/K5 S5 actuator behavior."""
from __future__ import annotations
import json, os
import peer
from k7_final_actuator_policy import TREATMENTS, requested_fanout

def _configured_treatment() -> str:
    with open(os.environ.get("TOPOLOGY_PATH", "/config/topology.json"), encoding="utf-8") as handle:
        treatment = json.load(handle).get("k5_h2", {}).get("actuator_treatment")
    if treatment not in TREATMENTS:
        raise RuntimeError(f"missing/invalid k5_h2.actuator_treatment: {treatment!r}")
    return treatment

TREATMENT = _configured_treatment()

def target_peers(self, sender_id: int, message_id: str | None = None) -> list[int]:
    if self.strategy != "ahbn":
        return peer._K5_CANONICAL_TARGET_PEERS(self, sender_id, message_id)
    self.adaptive_update(); score = self.ahbn_state.score
    if self.mode == "cluster":
        eligible = self.diagnostic_cluster_eligible_peers(sender_id)
        budget = requested_fanout(TREATMENT, score)
        targets = self.cluster_targets(sender_id, fanout=budget)
        if getattr(self, "h2_selector_treatment", "selector_control") == "seeded_uniform":
            targets = self.h2_seeded_uniform_selection(eligible, budget, message_id)
    else:
        eligible = [n for n in self.neighbors if n not in (sender_id, self.peer_id) and n not in self.unavailable_neighbors]
        budget = requested_fanout(TREATMENT, score); k = min(budget, len(eligible))
        if k > 0:
            targets = self.h2_seeded_uniform_selection(eligible, budget, message_id) if getattr(self, "h2_selector_treatment", "selector_control") == "seeded_uniform" else self.rng.sample(eligible, k)
        else: targets = []
        targets = list(dict.fromkeys(targets))
    canonical_fanout = self.fanout; self.fanout = budget
    peer.log_event(event="k5_final_actuator_decision", run_id=self.run_id, experiment=self.experiment, peer_id=self.peer_id, treatment=TREATMENT, message_id=message_id, sender=self.peer_id, incoming_sender=sender_id, score=score, weight=self.ahbn_state.weight, mode=self.mode, eligible_neighbor_count=len(set(eligible)), canonical_fanout=canonical_fanout, requested_fanout=budget, actual_fanout=len(targets))
    self.log_ahbn_forwarding_decision(sender_id, message_id, eligible, targets)
    return targets

peer._K5_CANONICAL_TARGET_PEERS = peer.PeerState.target_peers
peer.PeerState.target_peers = target_peers
if __name__ == "__main__": peer.serve()
