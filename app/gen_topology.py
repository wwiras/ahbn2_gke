from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx
import yaml


DCSOC_EPS = 2.0
DCSOC_MIN_SAMPLES = 3


def build_graph(
    num_nodes: int,
    topology_type: str,
    edge_prob: float,
    ba_m: int,
    seed: int,
    max_tries: int = 100,
):
    if topology_type == "er":
        for attempt in range(max_tries):
            attempt_seed = seed + attempt
            g = nx.erdos_renyi_graph(
                num_nodes,
                edge_prob,
                seed=attempt_seed,
            )

            if nx.is_connected(g):
                return g

        raise RuntimeError(
            f"Failed to generate a connected ER graph with "
            f"num_nodes={num_nodes}, edge_prob={edge_prob} "
            f"after {max_tries} attempts. "
            f"Increase edgeProb or use topology.type=ba."
        )

    elif topology_type == "ba":
        g = nx.barabasi_albert_graph(
            num_nodes,
            ba_m,
            seed=seed,
        )
        return g

    else:
        raise ValueError("topology.type must be er or ba")


def assign_clusters(
    num_nodes: int,
    num_clusters: int,
):
    cluster_size = max(1, num_nodes // num_clusters)

    cluster_heads = []
    cluster_of = {}

    members = {
        i: [] for i in range(num_clusters)
    }

    for cid in range(num_clusters):
        head = cid * cluster_size

        if head < num_nodes:
            cluster_heads.append(head)

    for node_id in range(num_nodes):
        cid = min(
            node_id // cluster_size,
            num_clusters - 1,
        )

        cluster_of[node_id] = cid
        members[cid].append(node_id)

    return cluster_heads, cluster_of, members


def assign_dcsoc_clusters(
    graph: nx.Graph,
    eps: float = DCSOC_EPS,
    min_samples: int = DCSOC_MIN_SAMPLES,
):
    """Reproduce the frozen ControlSim static DC-SoC overlay.

    Density clustering uses the precomputed all-pairs physical hop distance.
    Noise is attached to its nearest established cluster; if none is formed,
    all nodes form one cluster.  This is DBSCAN-based, not full DBSCAN++.
    """
    if eps <= 0 or min_samples <= 0:
        raise ValueError("DC-SoC eps and min_samples must be > 0")
    node_ids = sorted(graph.nodes())
    if not node_ids:
        return [], {}, {}, {}, []
    unreachable = float(len(node_ids) + 1)
    distances = {
        source: {
            target: float(distance)
            for target, distance in nx.single_source_shortest_path_length(
                graph, source
            ).items()
        }
        for source in node_ids
    }
    neighborhoods = {
        node: [
            candidate for candidate in node_ids
            if distances[node].get(candidate, unreachable) <= eps
        ]
        for node in node_ids
    }
    labels = {node: None for node in node_ids}
    cluster_id = 0
    for node in node_ids:
        if labels[node] is not None:
            continue
        if len(neighborhoods[node]) < min_samples:
            labels[node] = -1
            continue
        labels[node] = cluster_id
        queue = list(neighborhoods[node])
        queued = set(queue)
        index = 0
        while index < len(queue):
            candidate = queue[index]
            index += 1
            if labels[candidate] == -1:
                labels[candidate] = cluster_id
            if labels[candidate] is not None:
                continue
            labels[candidate] = cluster_id
            if len(neighborhoods[candidate]) >= min_samples:
                for neighbor in neighborhoods[candidate]:
                    if neighbor not in queued:
                        queue.append(neighbor)
                        queued.add(neighbor)
        cluster_id += 1
    established = sorted({label for label in labels.values() if label >= 0})
    if not established:
        labels = {node: 0 for node in node_ids}
    else:
        label_members = {
            label: [node for node in node_ids if labels[node] == label]
            for label in established
        }
        for node in node_ids:
            if labels[node] != -1:
                continue
            labels[node] = min(
                established,
                key=lambda label: (
                    min(distances[node].get(member, unreachable)
                        for member in label_members[label]),
                    label,
                ),
            )
            label_members[labels[node]].append(node)
        remap = {old: new for new, old in enumerate(sorted(set(labels.values())))}
        labels = {node: remap[label] for node, label in labels.items()}
    members = {}
    for node in node_ids:
        members.setdefault(labels[node], []).append(node)
    heads = [
        max(members[cid], key=lambda node: (graph.degree(node), -node))
        for cid in sorted(members)
    ]
    roles = {
        node: {
            "dcsoc_role": "leaf",
            "dcsoc_parent": None,
            "dcsoc_children": [],
            "dcsoc_core_neighbors": [],
        }
        for node in node_ids
    }
    structural_edges = []
    for index, cid in enumerate(sorted(members)):
        core = heads[index]
        roles[core]["dcsoc_role"] = "core"
        for member in sorted(members[cid]):
            if member == core:
                continue
            roles[member]["dcsoc_parent"] = core
            roles[core]["dcsoc_children"].append(member)
            structural_edges.append([core, member])
        if index:
            parent_core = heads[index - 1]
            roles[core]["dcsoc_parent"] = parent_core
            roles[parent_core]["dcsoc_children"].append(core)
            roles[parent_core]["dcsoc_core_neighbors"].append(core)
            roles[core]["dcsoc_core_neighbors"].append(parent_core)
            structural_edges.append([parent_core, core])
    return heads, labels, members, roles, structural_edges


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--config",
        required=True,
    )

    ap.add_argument(
        "--out",
        required=True,
    )

    args = ap.parse_args()

    cfg = yaml.safe_load(
        Path(args.config).read_text()
    )

    experiment = cfg.get(
        "experiment",
        "exp10",
    )

    strategy = cfg.get(
        "strategy",
        "ahbn",
    )

    num_nodes = int(
        cfg.get("numNodes", 20)
    )

    configured_fanout = cfg.get("fanout")
    fanout = (
        None
        if strategy in {"cluster", "dcsoc"}
        or (strategy == "gossip" and configured_fanout is None)
        else int(configured_fanout if configured_fanout is not None else 3)
    )

    num_clusters = int(
        cfg.get("numClusters", 4)
    )

    message_source = int(
        cfg.get("messageSource", 0)
    )

    settle_time = float(
        cfg.get("settleTime", 15.0)
    )

    # ---------------------------------------------------
    # Topology configuration
    # ---------------------------------------------------

    topo_cfg = cfg.get("topology", {})

    topology_type = topo_cfg.get(
        "type",
        "er",
    )

    edge_prob = float(
        topo_cfg.get("edgeProb", 0.2)
    )

    ba_m = int(
        topo_cfg.get("baM", 2)
    )

    seed = int(
        topo_cfg.get("seed", 42)
    )

    # ---------------------------------------------------
    # Failure / overload configuration
    # ---------------------------------------------------

    failure_cfg = cfg.get("failure", {})

    failure_mode = failure_cfg.get(
        "mode",
        "node_failure",
    )

    trigger_time = float(
        failure_cfg.get(
            "triggerTime",
            failure_cfg.get(
                "trigger_time",
                1.0,
            ),
        )
    )

    overload_delay_ms = int(
        failure_cfg.get(
            "overloadDelayMs",
            failure_cfg.get(
                "overload_delay_ms",
                200,
            ),
        )
    )

    num_events = int(
        failure_cfg.get(
            "numEvents",
            failure_cfg.get(
                "num_events",
                3,
            ),
        )
    )

    interval_sec = float(
        failure_cfg.get(
            "intervalSec",
            failure_cfg.get(
                "interval_sec",
                1.0,
            ),
        )
    )

    target_type = str(
        failure_cfg.get(
            "targetType",
            failure_cfg.get(
                "target_type",
                "mixed",
            ),
        )
    )

    # ---------------------------------------------------
    # Workload configuration
    # ---------------------------------------------------

    workload_cfg = cfg.get("workload", {})
    
    bottleneck_cfg = cfg.get("bottleneck", {})

    bottleneck_enabled = bool(
        bottleneck_cfg.get("enabled", False)
    )

    bottleneck_target = str(
        bottleneck_cfg.get("target", "ch_only")
    )

    bottleneck_delay_ms = int(
        bottleneck_cfg.get(
            "delayMs",
            bottleneck_cfg.get(
                "delay_ms",
                250,
            ),
        )
    )

    message_count = int(
        workload_cfg.get(
            "messageCount",
            workload_cfg.get(
                "message_count",
                1,
            ),
        )
    )

    message_interval = float(
        workload_cfg.get(
            "messageInterval",
            workload_cfg.get(
                "message_interval",
                0.0,
            ),
        )
    )

    # ---------------------------------------------------
    # Exp8 bottleneck configuration
    # ---------------------------------------------------

    bottleneck_cfg = cfg.get(
        "bottleneck",
        {},
    )

    bottleneck_enabled = bool(
        bottleneck_cfg.get(
            "enabled",
            False,
        )
    )

    bottleneck_target = str(
        bottleneck_cfg.get(
            "target",
            "ch_only",
        )
    )

    bottleneck_delay_ms = int(
        bottleneck_cfg.get(
            "delayMs",
            bottleneck_cfg.get(
                "delay_ms",
                250,
            ),
        )
    )

    # ---------------------------------------------------
    # Build topology graph
    # ---------------------------------------------------

    g = build_graph(
        num_nodes,
        topology_type,
        edge_prob,
        ba_m,
        seed,
    )

    actual_nodes = g.number_of_nodes()

    dcsoc_cfg = cfg.get("dcsoc", {})
    dcsoc_eps = float(dcsoc_cfg.get("eps", DCSOC_EPS))
    dcsoc_min_samples = int(
        dcsoc_cfg.get("min_samples", DCSOC_MIN_SAMPLES)
    )
    dcsoc_roles = {}
    structural_edges = []
    if strategy == "dcsoc":
        (cluster_heads, cluster_of, members, dcsoc_roles,
         structural_edges) = assign_dcsoc_clusters(
            g, eps=dcsoc_eps, min_samples=dcsoc_min_samples
        )
        message_source = cluster_heads[0]
    else:
        cluster_heads, cluster_of, members = assign_clusters(
            actual_nodes,
            num_clusters,
        )

    # ---------------------------------------------------
    # Build node metadata
    # ---------------------------------------------------

    nodes = {}

    for node_id in range(actual_nodes):
        cid = cluster_of[node_id]

        head = cluster_heads[cid]

        gateways = []

        if node_id in cluster_heads:
            idx = cluster_heads.index(node_id)

            if idx > 0:
                gateways.append(
                    cluster_heads[idx - 1]
                )

            if idx < len(cluster_heads) - 1:
                gateways.append(
                    cluster_heads[idx + 1]
                )

        nodes[str(node_id)] = {
            "neighbors": sorted(
                list(g.neighbors(node_id))
            ),

            "cluster_id": cid,

            "is_cluster_head":
                node_id in cluster_heads,

            "cluster_head_id": head,

            "cluster_members": [
                n
                for n in members[cid]
                if n != node_id
            ],

            "gateway_neighbors": gateways,
            **dcsoc_roles.get(node_id, {}),
        }

    # ---------------------------------------------------
    # Final topology payload
    # ---------------------------------------------------

    topo = {
        "run_id": experiment,

        "experiment": experiment,

        "mode": (
            "bottleneck"
            if bottleneck_enabled
            else failure_mode
        ),

        "seed": seed,

        "strategy": strategy,

        "num_nodes": actual_nodes,

        "topology_type": topology_type,

        "edge_prob": edge_prob,

        "ba_m": ba_m,

        "message_source": message_source,

        "fanout": fanout,

        "num_clusters": num_clusters,

        "dcsoc": {
            "eps": dcsoc_eps,
            "min_samples": dcsoc_min_samples,
            "master_id": cluster_heads[0] if strategy == "dcsoc" else None,
            "structural_edges": structural_edges,
            "dynamic_maintenance": False,
        },

        "settle_time": settle_time,

        # -----------------------------------------------
        # Failure configuration
        # -----------------------------------------------

        "failure": {
            "mode": failure_mode,

            "trigger_time": trigger_time,

            "overload_delay_ms":
                overload_delay_ms,

            "num_events": num_events,

            "interval_sec": interval_sec,

            "target_type": target_type,
        },

        # -----------------------------------------------
        # Exp8 bottleneck configuration
        # -----------------------------------------------

        "bottleneck": {
            "enabled": bottleneck_enabled,

            "target": bottleneck_target,

            "delay_ms": bottleneck_delay_ms,
        },

        # -----------------------------------------------
        # Workload configuration
        # -----------------------------------------------

        "workload": {
            "message_count": message_count,

            "message_interval":
                message_interval,
        },

        # -----------------------------------------------
        # AHBN parameters
        # -----------------------------------------------

        "ahbn": {
            "mode_threshold": 0.5,

            "min_fanout": 1,

            "max_fanout": 6,
        },

        # -----------------------------------------------
        # Node metadata
        # -----------------------------------------------

        "nodes": nodes,
    }

    out = Path(args.out)

    out.write_text(
        json.dumps(topo, indent=2),
        encoding="utf-8",
    )

    print(f"wrote {out}")


if __name__ == "__main__":
    main()
