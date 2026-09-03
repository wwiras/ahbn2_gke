"""Event-driven DC-SoC maintenance over a frozen K3.4 topology.

There is deliberately no background timer.  Local repair is driven by genuine
availability transitions; a full network update requires an explicit ``du``.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Callable

import networkx as nx

from gen_topology import DCSOC_EPS, DCSOC_MIN_SAMPLES, assign_dcsoc_clusters


class DCSOCMaintenance:
    """Own the single active/inactive and structural state for DC-SoC."""

    def __init__(
        self,
        topology: dict,
        *,
        clock: Callable[[], float] = time.time,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        if topology.get("strategy") != "dcsoc":
            raise ValueError("DC-SoC maintenance requires strategy=dcsoc")
        self.nodes = {
            int(node_id): copy.deepcopy(config)
            for node_id, config in topology["nodes"].items()
        }
        self.eps = float(topology.get("dcsoc", {}).get("eps", DCSOC_EPS))
        self.min_samples = int(
            topology.get("dcsoc", {}).get("min_samples", DCSOC_MIN_SAMPLES)
        )
        self.active = {node_id: True for node_id in self.nodes}
        self.previous_cluster = {
            node_id: config.get("cluster_id") for node_id, config in self.nodes.items()
        }
        self.structural_edges = [
            tuple(edge)
            for edge in topology.get("dcsoc", {}).get("structural_edges", [])
        ]
        self.clock = clock
        self.timer = timer
        self.events: list[dict] = []
        self.core_replacement_count = 0
        self.recluster_count = 0
        self.rejoin_assignment_count = 0
        self.structural_generation = 0
        self.lock = threading.RLock()

    def set_availability(
        self, node_id: int, available: bool, *, reason: str = "availability"
    ) -> bool:
        """Apply exactly one action for each real availability transition."""
        with self.lock:
            if node_id not in self.nodes:
                raise KeyError(node_id)
            available = bool(available)
            if self.active[node_id] == available:
                return False
            if available:
                self._maintain("rejoin", self._rejoin, node_id=node_id, reason=reason)
            else:
                self._maintain("leave", self._leave, node_id=node_id, reason=reason)
            return True

    def explicit_du(self, *, reason: str = "explicit_du") -> None:
        """Run the frozen K3.4 constructor on active peers only."""
        with self.lock:
            self._maintain("recluster", self._recluster, reason=reason)

    def sync_peer(self, peer: object) -> None:
        """Publish one node's repaired fields atomically to its peer object."""
        config = self.nodes[int(peer.peer_id)]
        fields = {
            "is_cluster_head": bool(config.get("is_cluster_head", False)),
            "cluster_head_id": config.get("cluster_head_id"),
            "cluster_members": list(config.get("cluster_members", [])),
            "gateway_neighbors": list(config.get("gateway_neighbors", [])),
            "dcsoc_role": config.get("dcsoc_role", "leaf"),
            "dcsoc_parent": config.get("dcsoc_parent"),
            "dcsoc_children": list(config.get("dcsoc_children", [])),
            "dcsoc_core_neighbors": list(config.get("dcsoc_core_neighbors", [])),
        }
        lock = getattr(peer, "lock", None)
        if lock is None:
            for name, value in fields.items():
                setattr(peer, name, value)
            return
        with lock:
            for name, value in fields.items():
                setattr(peer, name, value)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "active": copy.deepcopy(self.active),
                "nodes": copy.deepcopy(self.nodes),
                "structural_edges": list(self.structural_edges),
                "core_replacement_count": self.core_replacement_count,
                "recluster_count": self.recluster_count,
                "rejoin_assignment_count": self.rejoin_assignment_count,
                "structural_generation": self.structural_generation,
            }

    def _maintain(self, action: str, operation: Callable[..., dict], **kwargs) -> None:
        started_at = self.clock()
        started = self.timer()
        detail = operation(**kwargs)
        ended = self.timer()
        ended_at = self.clock()
        self.events.append({
            "maintenance_start": started_at,
            "maintenance_end": ended_at,
            "maintenance_duration": max(0.0, ended - started),
            "maintenance_reason": kwargs.get("reason", action),
            "maintenance_action": action,
            **detail,
        })

    def _leave(self, *, node_id: int, reason: str) -> dict:
        node = self.nodes[node_id]
        failed_role = node.get("dcsoc_role", "leaf")
        cluster_id = node.get("cluster_id")
        parent = node.get("dcsoc_parent")
        children = list(node.get("dcsoc_children", []))
        self.previous_cluster[node_id] = cluster_id
        self.active[node_id] = False

        self.structural_edges = [
            edge for edge in self.structural_edges if node_id not in edge
        ]
        if parent in self.nodes:
            self.nodes[parent]["dcsoc_children"] = [
                child
                for child in self.nodes[parent].get("dcsoc_children", [])
                if child != node_id
            ]
        node["dcsoc_parent"] = None
        node["dcsoc_children"] = []
        node["is_cluster_head"] = False
        replacement = None
        surviving_candidate_set = []
        replacement_degree = None

        if failed_role == "core":
            candidates = [
                candidate
                for candidate, config in self.nodes.items()
                if candidate != node_id
                and self.active[candidate]
                and config.get("cluster_id") == cluster_id
            ]
            surviving_candidate_set = sorted(candidates)
            if candidates:
                replacement = max(
                    candidates,
                    key=lambda candidate: (
                        len(self.nodes[candidate].get("neighbors", [])), -candidate
                    ),
                )
                repl = self.nodes[replacement]
                replacement_degree = len(repl.get("neighbors", []))
                repl["dcsoc_role"] = "core"
                repl["is_cluster_head"] = True
                repl["cluster_head_id"] = replacement
                repl["dcsoc_parent"] = (
                    parent if parent != replacement and self.active.get(parent, False) else None
                )
                inherited = [
                    child
                    for child in children
                    if child != replacement and self.active.get(child, False)
                ]
                repl["dcsoc_children"] = list(dict.fromkeys(
                    repl.get("dcsoc_children", []) + inherited
                ))
                if repl["dcsoc_parent"] is not None:
                    upstream = self.nodes[repl["dcsoc_parent"]]
                    upstream["dcsoc_children"] = list(dict.fromkeys(
                        [replacement if child == node_id else child
                         for child in upstream.get("dcsoc_children", [])]
                        + [replacement]
                    ))
                    self.structural_edges.append((repl["dcsoc_parent"], replacement))
                for child in inherited:
                    self.nodes[child]["dcsoc_parent"] = replacement
                    self.structural_edges.append((replacement, child))
                for candidate, config in self.nodes.items():
                    if config.get("cluster_id") == cluster_id:
                        config["cluster_head_id"] = replacement
                self.core_replacement_count += 1
            else:
                for child in children:
                    if child in self.nodes and self.active.get(child, False):
                        self.nodes[child]["dcsoc_parent"] = None
            node["dcsoc_role"] = "leaf"

        self.structural_edges = list(dict.fromkeys(self.structural_edges))
        return {
            "failed_node": node_id,
            "failed_role": failed_role,
            "affected_cluster": cluster_id,
            "former_parent": parent,
            "replacement_core": replacement,
            "surviving_candidate_set": surviving_candidate_set,
            "replacement_degree": replacement_degree,
        }

    def _rejoin(self, *, node_id: int, reason: str) -> dict:
        node = self.nodes[node_id]
        previous = self.previous_cluster.get(node_id)
        self.active[node_id] = True
        node["dcsoc_role"] = "leaf"
        node["is_cluster_head"] = False
        node["dcsoc_parent"] = None
        node["dcsoc_children"] = []

        cores = sorted(
            candidate
            for candidate, config in self.nodes.items()
            if self.active[candidate]
            and config.get("cluster_id") == previous
            and config.get("dcsoc_role") == "core"
        )
        assigned = previous if cores else None
        if cores:
            core = cores[0]
            node["cluster_id"] = previous
            node["cluster_head_id"] = core
            node["dcsoc_parent"] = core if core != node_id else None
            if core != node_id:
                self.nodes[core]["dcsoc_children"] = list(dict.fromkeys(
                    self.nodes[core].get("dcsoc_children", []) + [node_id]
                ))
                self.structural_edges.append((core, node_id))
            self.rejoin_assignment_count += 1
        self.structural_edges = list(dict.fromkeys(self.structural_edges))
        return {
            "rejoined_node": node_id,
            "previous_cluster": previous,
            "new_cluster": assigned,
        }

    def _recluster(self, *, reason: str) -> dict:
        graph = nx.Graph()
        active_ids = sorted(node_id for node_id, active in self.active.items() if active)
        graph.add_nodes_from(active_ids)
        for node_id in active_ids:
            for neighbor in self.nodes[node_id].get("neighbors", []):
                if neighbor in self.active and self.active[neighbor]:
                    graph.add_edge(node_id, neighbor)
        if active_ids:
            heads, clusters, members, roles, edges = assign_dcsoc_clusters(
                graph, eps=self.eps, min_samples=self.min_samples
            )
            for node_id in active_ids:
                config = self.nodes[node_id]
                cluster_id = clusters[node_id]
                config["cluster_id"] = cluster_id
                config["is_cluster_head"] = node_id in heads
                config["cluster_head_id"] = heads[cluster_id]
                config["cluster_members"] = [
                    member for member in members[cluster_id] if member != node_id
                ]
                config["gateway_neighbors"] = []
                config.update(copy.deepcopy(roles[node_id]))
                self.previous_cluster[node_id] = cluster_id
            self.structural_edges = [tuple(edge) for edge in edges]
            master = heads[0]
        else:
            self.structural_edges = []
            master = None
        self.recluster_count += 1
        self.structural_generation += 1
        return {
            "active_peers": active_ids,
            "master_id": master,
            "structural_generation": self.structural_generation,
        }
