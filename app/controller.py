from __future__ import annotations

import json
import os
import random
import threading
import time

import grpc
from kubernetes import client, config
from kubernetes.client.rest import ApiException

import peer_pb2
import peer_pb2_grpc
from k5_exp10_tools import choose_exp10_target


def now() -> float:
    return time.time()


def log_event(**kwargs):
    print(json.dumps({"ts": now(), **kwargs}, sort_keys=True), flush=True)


def load_topology(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def peer_addr(peer_id: int, svc: str, ns: str, port: int) -> str:
    return f"peer-{peer_id}.{svc}.{ns}.svc.cluster.local:{port}"


def wait_for_peers(num_nodes: int, svc: str, ns: str, port: int, timeout: int = 300) -> None:
    start = time.time()

    for peer_id in range(num_nodes):
        ok = False

        while time.time() - start < timeout:
            try:
                with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
                    stub = peer_pb2_grpc.PeerServiceStub(channel)
                    status = stub.GetStatus(peer_pb2.Empty(), timeout=2)

                    if status.ready:
                        ok = True
                        break

            except Exception:
                pass

            time.sleep(1.0)

        if not ok:
            raise RuntimeError(f"peer-{peer_id} did not become ready")


def wait_for_peer_ready(peer_id: int, svc: str, ns: str, port: int, timeout: int = 180) -> None:
    start = time.time()

    while time.time() - start < timeout:
        try:
            with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
                stub = peer_pb2_grpc.PeerServiceStub(channel)
                status = stub.GetStatus(peer_pb2.Empty(), timeout=2)

                if status.ready:
                    return

        except Exception:
            pass

        time.sleep(1.0)

    raise RuntimeError(f"peer-{peer_id} did not recover within {timeout}s")


    peers_raw = topo.get("peers", [])

    # Support both formats:
    # 1) peers: [{...}, {...}]
    # 2) peers: {"peer-0": {...}, "peer-1": {...}}
    if isinstance(peers_raw, dict):
        peers = []
        for peer_id, peer_data in peers_raw.items():
            if isinstance(peer_data, dict):
                p = dict(peer_data)
                p.setdefault("id", peer_id)
                p.setdefault("peer_id", peer_id)
                peers.append(p)
    elif isinstance(peers_raw, list):
        peers = peers_raw
    else:
        peers = []

    if not peers:
        raise RuntimeError("No peers found in topology.json")

    # Exp12: target low-resource peers when available
    if mode == "resource" or mode == "exp12":
        candidates = [
            p for p in peers
            if isinstance(p, dict)
            and p.get("resource_group") == "low"
            and not p.get("failed", False)
        ]

        if candidates:
            return candidates[0].get("id") or candidates[0].get("peer_id") or candidates[0].get("name")

    # Fallback: choose any non-failed peer
    candidates = [
        p for p in peers
        if isinstance(p, dict)
        and not p.get("failed", False)
    ]

    if not candidates:
        raise RuntimeError("No valid target peers found")

    target = candidates[0]
    return target.get("id") or target.get("peer_id") or target.get("name")


def choose_target(topo, mode):
    nodes = topo.get("nodes", {})
    source = int(topo.get("message_source", -1))
    failure = topo.get("failure", {})
    target_type = failure.get("target_type", "mixed")

    if not nodes:
        raise RuntimeError("No nodes found in topology.json")

    candidates = []

    for k, v in nodes.items():
        peer_id = int(k)

        if peer_id == source:
            continue

        is_ch = bool(v.get("is_cluster_head", False))

        if mode == "ch_failure" and not is_ch:
            continue

        if target_type == "cluster_head" and not is_ch:
            continue

        if target_type == "non_ch" and is_ch:
            continue

        candidates.append(peer_id)

    if not candidates:
        raise RuntimeError(f"No valid target nodes found for mode={mode}, target_type={target_type}")

    return candidates[0]


def choose_churn_targets(topo: dict, count: int, target_type: str) -> list[int]:
    rng = random.Random(topo.get("seed", 42) + 99)
    source = topo["message_source"]
    nodes = topo["nodes"]

    candidates: list[int] = []

    for k, v in nodes.items():
        peer_id = int(k)

        if peer_id == source:
            continue

        is_ch = bool(v["is_cluster_head"])

        if target_type == "cluster_head" and not is_ch:
            continue

        if target_type == "non_ch" and is_ch:
            continue

        candidates.append(peer_id)

    if not candidates:
        raise RuntimeError(f"No eligible churn targets for target_type={target_type}")

    rng.shuffle(candidates)

    if count <= len(candidates):
        return candidates[:count]

    out: list[int] = []
    while len(out) < count:
        out.extend(candidates)

    return out[:count]


def fail_stop_peer(peer_id: int, svc: str, ns: str, port: int) -> None:
    for attempt in range(3):
        try:
            with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
                stub = peer_pb2_grpc.PeerServiceStub(channel)
                stub.FailStop(peer_pb2.Empty(), timeout=3)

            log_event(
                event="fail_stop_requested",
                peer_id=peer_id,
                attempt=attempt + 1,
            )
            return

        except Exception as e:
            log_event(
                event="fail_stop_retry",
                peer_id=peer_id,
                attempt=attempt + 1,
                error=str(e),
            )
            time.sleep(1)

    raise RuntimeError(f"Failed to fail-stop peer {peer_id}")


def apply_overload(peer_id: int, svc: str, ns: str, port: int, delay_ms: int) -> None:
    with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
        stub = peer_pb2_grpc.PeerServiceStub(channel)
        stub.InjectOverload(peer_pb2.OverloadRequest(delay_ms=delay_ms), timeout=3)

    log_event(event="overload_requested", peer_id=peer_id, overload_ms=delay_ms)


def broadcast_dcsoc_maintenance(
    topo: dict, svc: str, ns: str, port: int, *, node_id: int = 0,
    available: bool = True, explicit_du: bool = False,
    include_affected: bool = False, reason: str,
) -> None:
    """Apply one authoritative event to every reachable DC-SoC peer."""
    if topo.get("strategy") != "dcsoc":
        return
    for raw_peer_id in sorted(topo["nodes"], key=int):
        peer_id = int(raw_peer_id)
        if (not available and not explicit_du and peer_id == node_id
                and not include_affected):
            continue
        try:
            with grpc.insecure_channel(peer_addr(peer_id, svc, ns, port)) as channel:
                stub = peer_pb2_grpc.PeerServiceStub(channel)
                stub.ApplyDCSOCMaintenance(
                    peer_pb2.DCSOCMaintenanceRequest(
                        node_id=node_id, available=available,
                        explicit_du=explicit_du, reason=reason,
                    ),
                    timeout=3,
                )
        except Exception as error:
            log_event(event="dcsoc_maintenance_broadcast_failed", peer_id=peer_id,
                      affected_node=node_id, reason=reason, error=str(error))


def delete_peer_pod(peer_id: int, ns: str) -> None:
    config.load_incluster_config()
    v1 = client.CoreV1Api()
    pod_name = f"peer-{peer_id}"

    try:
        v1.delete_namespaced_pod(
            name=pod_name,
            namespace=ns,
            grace_period_seconds=0,
        )

        log_event(
            event="pod_delete_requested",
            peer_id=peer_id,
            pod_name=pod_name,
        )

    except ApiException as e:
        if e.status == 404:
            log_event(
                event="pod_delete_missing",
                peer_id=peer_id,
                pod_name=pod_name,
            )
            return

        raise


def delete_peer_pod_observed(peer_id: int, ns: str, timeout: float = 30.0) -> dict:
    """Delete a pod and prove that the original pod instance became unavailable."""
    config.load_incluster_config()
    v1 = client.CoreV1Api()
    pod_name = f"peer-{peer_id}"
    original = v1.read_namespaced_pod(name=pod_name, namespace=ns)
    original_uid = original.metadata.uid
    requested_at = now()
    v1.delete_namespaced_pod(name=pod_name, namespace=ns, grace_period_seconds=0)
    log_event(event="pod_delete_requested", peer_id=peer_id, pod_name=pod_name,
              original_pod_uid=original_uid, deletion_requested_at=requested_at)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            current = v1.read_namespaced_pod(name=pod_name, namespace=ns)
            current_uid = current.metadata.uid
            ready = any(
                condition.type == "Ready" and condition.status == "True"
                for condition in (current.status.conditions or [])
            )
            if current_uid != original_uid or not ready:
                observed_at = now()
                evidence = "replacement_uid" if current_uid != original_uid else "not_ready"
                log_event(event="pod_unavailability_observed", peer_id=peer_id,
                          pod_name=pod_name, original_pod_uid=original_uid,
                          observed_pod_uid=current_uid, observed_ready=ready,
                          evidence=evidence, unavailability_observed_at=observed_at)
                return {"requested_at": requested_at, "observed_at": observed_at,
                        "original_uid": original_uid, "observed_uid": current_uid,
                        "evidence": evidence}
        except ApiException as error:
            if error.status == 404:
                observed_at = now()
                log_event(event="pod_unavailability_observed", peer_id=peer_id,
                          pod_name=pod_name, original_pod_uid=original_uid,
                          observed_pod_uid=None, observed_ready=False,
                          evidence="not_found", unavailability_observed_at=observed_at)
                return {"requested_at": requested_at, "observed_at": observed_at,
                        "original_uid": original_uid, "observed_uid": None,
                        "evidence": "not_found"}
            raise
        time.sleep(0.05)
    raise RuntimeError(f"pod deletion was not observed for {pod_name} within {timeout}s")


def run_exp10_failure(topo: dict, peer_svc: str, namespace: str, grpc_port: int) -> None:
    failure = topo["failure"]
    time.sleep(float(failure.get("trigger_time", 0.5)))
    target = choose_exp10_target(topo)
    log_event(event="failure_target_selected", run_id=topo["run_id"],
              strategy=topo["strategy"], **target)
    triggered_at = now()
    log_event(event="failure_triggered", run_id=topo["run_id"],
              strategy=topo["strategy"], failure_mode="pod_delete",
              target_peer=target["peer_id"], target_role=target["role"],
              target_cluster=target["cluster_id"], target_degree=target["degree"],
              failure_triggered_at=triggered_at)
    evidence = delete_peer_pod_observed(target["peer_id"], namespace)
    if topo.get("strategy") == "dcsoc":
        broadcast_dcsoc_maintenance(
            topo, peer_svc, namespace, grpc_port, node_id=target["peer_id"],
            available=False, reason="exp10_pod_delete",
        )
    log_event(event="failure_injection_complete", run_id=topo["run_id"],
              target_peer=target["peer_id"], **evidence)


def inject_messages(
    run_id: str,
    source_id: int,
    peer_svc: str,
    namespace: str,
    grpc_port: int,
    message_count: int,
    message_interval: float,
    retry_unavailable_source: bool = False,
) -> None:
    for idx in range(message_count):
        message_id = f"m{idx + 1}"

        deadline = time.monotonic() + 180.0
        while True:
            try:
                with grpc.insecure_channel(peer_addr(source_id, peer_svc, namespace, grpc_port)) as channel:
                    stub = peer_pb2_grpc.PeerServiceStub(channel)
                    stub.StartRun(peer_pb2.StartRequest(run_id=run_id, message_id=message_id), timeout=3)
                break
            except Exception as error:
                if not retry_unavailable_source or time.monotonic() >= deadline:
                    raise
                log_event(event="source_temporarily_unavailable", run_id=run_id,
                          peer_id=source_id, message_id=message_id, error=str(error))
                time.sleep(0.25)

        log_event(
            event="source_triggered",
            run_id=run_id,
            peer_id=source_id,
            message_id=message_id,
        )

        if idx < message_count - 1 and message_interval > 0:
            time.sleep(message_interval)


def run_churn(topo: dict, peer_svc: str, namespace: str, grpc_port: int) -> None:
    failure = topo["failure"]

    trigger_time = float(failure.get("trigger_time", 1.0))
    num_events = int(failure.get("num_events", 3))
    interval_sec = float(failure.get("interval_sec", 1.0))
    target_type = str(failure.get("target_type", "mixed"))

    time.sleep(trigger_time)

    targets = choose_churn_targets(topo, num_events, target_type)

    for idx, target in enumerate(targets, start=1):
        is_ch = topo["nodes"][str(target)]["is_cluster_head"]

        log_event(
            event="churn_triggered",
            run_id=topo["run_id"],
            churn_index=idx,
            target_peer=target,
            is_cluster_head=is_ch,
            target_type=target_type,
        )

        delete_peer_pod(target, namespace)
        broadcast_dcsoc_maintenance(
            topo, peer_svc, namespace, grpc_port, node_id=target,
            available=False, reason="churn_leave",
        )
        wait_for_peer_ready(target, peer_svc, namespace, grpc_port)
        # The recreated pod starts from the static topology and did not receive
        # the leave broadcast while it was absent. Replay that transition;
        # surviving peers treat it idempotently, while the returning peer then
        # rejoins as a leaf rather than reclaiming a former CORE role.
        broadcast_dcsoc_maintenance(
            topo, peer_svc, namespace, grpc_port, node_id=target,
            available=False, include_affected=True, reason="churn_leave_replay",
        )
        broadcast_dcsoc_maintenance(
            topo, peer_svc, namespace, grpc_port, node_id=target,
            available=True, reason="churn_rejoin",
        )

        log_event(
            event="churn_recovered",
            run_id=topo["run_id"],
            churn_index=idx,
            target_peer=target,
            is_cluster_head=is_ch,
        )

        if idx < len(targets) and interval_sec > 0:
            time.sleep(interval_sec)

def run_mixed_resources(topo: dict, peer_svc: str, namespace: str, grpc_port: int) -> None:
    failure = topo["failure"]

    trigger_time = float(failure.get("trigger_time", 1.0))
    num_events = int(failure.get("num_events", 3))
    overload_ms = int(failure.get("overload_delay_ms", 350))

    source = int(topo.get("message_source", -1))
    nodes = topo.get("nodes", {})

    candidates = [
        int(k) for k, v in nodes.items()
        if int(k) != source and not bool(v.get("is_cluster_head", False))
    ]

    if not candidates:
        raise RuntimeError("No eligible mixed-resource targets found")

    targets = candidates[:num_events]

    time.sleep(trigger_time)

    for target in targets:
        apply_overload(target, peer_svc, namespace, grpc_port, overload_ms)

        log_event(
            event="mixed_resource_applied",
            run_id=topo["run_id"],
            peer_id=target,
            overload_ms=overload_ms,
        )

def run_bottleneck(
    topo: dict,
    peer_svc: str,
    namespace: str,
    grpc_port: int,
) -> None:
    bottleneck = topo.get("bottleneck", {})

    enabled = bool(
        bottleneck.get("enabled", False)
    )

    if not enabled:
        return

    trigger_time = float(
        topo.get("failure", {}).get(
            "trigger_time",
            1.0,
        )
    )

    delay_ms = int(
        bottleneck.get("delay_ms", 250)
    )

    target_type = str(
        bottleneck.get("target", "ch_only")
    )

    time.sleep(trigger_time)

    nodes = topo.get("nodes", {})

    targets = []

    for k, v in nodes.items():
        peer_id = int(k)

        is_ch = bool(
            v.get("is_cluster_head", False)
        )

        if target_type == "important_peer":
            # Deterministic experiment-harness selection.  The algorithm is
            # not told why this peer was selected.  Select natively important
            # forwarding state for each strategy; a native CH/CORE may also be
            # the paired source and remains a meaningful processing target.
            continue

        if target_type == "ch_only":
            if is_ch:
                targets.append(peer_id)

        elif target_type == "non_ch":
            if not is_ch:
                targets.append(peer_id)

        elif target_type == "all":
            targets.append(peer_id)

    if target_type == "important_peer":
        strategy = str(topo.get("strategy", ""))
        source = int(topo.get("message_source", -1))
        eligible = [int(k) for k in nodes if int(k) != source]
        if strategy == "dcsoc":
            cores = [
                int(k) for k, node in nodes.items()
                if node.get("dcsoc_role") == "core"
            ]
            eligible = cores or eligible
            role = "MASTER/CORE"
            basis = "highest-degree DC-SoC CORE"
        elif strategy == "cluster":
            heads = [
                int(k) for k, node in nodes.items()
                if bool(node.get("is_cluster_head", False))
            ]
            eligible = heads or eligible
            role = "CH"
            basis = "highest-degree Structured CH"
        else:
            role = "high-connectivity forwarding peer"
            basis = "highest-degree non-source BA peer"
        if eligible:
            targets = [max(
                eligible,
                key=lambda peer_id: (
                    len(nodes[str(peer_id)].get("neighbors", [])),
                    -peer_id,
                ),
            )]
            log_event(
                event="overload_target_selected",
                run_id=topo["run_id"],
                strategy=strategy,
                peer_id=targets[0],
                role=role,
                selection_basis=basis,
                seed=topo.get("seed"),
            )

    if not targets:
        raise RuntimeError(
            f"No bottleneck targets found "
            f"for target_type={target_type}"
        )

    log_event(
        event="bottleneck_started",
        run_id=topo["run_id"],
        target_type=target_type,
        delay_ms=delay_ms,
        targets=targets,
    )

    for peer_id in targets:
        apply_overload(
            peer_id,
            peer_svc,
            namespace,
            grpc_port,
            delay_ms,
        )

        log_event(
            event="bottleneck_applied",
            run_id=topo["run_id"],
            peer_id=peer_id,
            delay_ms=delay_ms,
            is_cluster_head=nodes[str(peer_id)][
                "is_cluster_head"
            ],
        )


def main() -> None:
    topo_path = os.environ.get("TOPOLOGY_PATH", "/config/topology.json")
    peer_svc = os.environ.get("PEER_SERVICE_NAME", "ahbn-peer")
    namespace = os.environ.get("POD_NAMESPACE", "default")
    grpc_port = int(os.environ.get("GRPC_PORT", "50051"))

    topo = load_topology(topo_path)

    run_id = topo["run_id"]
    num_nodes = topo["num_nodes"]
    source_id = topo["message_source"]

    failure = topo["failure"]
    mode = failure["mode"]
    overload_ms = int(failure.get("overload_delay_ms", 200))

    workload = topo.get("workload", {})
    message_count = int(workload.get("message_count", 1))
    message_interval = float(workload.get("message_interval", 0.0))

    log_event(
        event="controller_started",
        run_id=run_id,
        failure_mode=mode,
        message_count=message_count,
        message_interval=message_interval,
        retry_unavailable_source=(mode == "exp10_pod_delete"),
    )

    wait_for_peers(num_nodes, peer_svc, namespace, grpc_port)

    log_event(event="all_peers_ready", run_id=run_id)

    stress_thread = None

    if mode == "exp10_pod_delete":
        stress_thread = threading.Thread(
            target=run_exp10_failure,
            args=(topo, peer_svc, namespace, grpc_port),
            daemon=True,
        )
        stress_thread.start()

    elif mode == "churn":
        stress_thread = threading.Thread(
            target=run_churn,
            args=(topo, peer_svc, namespace, grpc_port),
            daemon=True,
        )
        stress_thread.start()

    elif mode == "mixed_resources":
        stress_thread = threading.Thread(
            target=run_mixed_resources,
            args=(topo, peer_svc, namespace, grpc_port),
            daemon=True,
        )
        stress_thread.start()
        
    elif mode == "bottleneck":
        stress_thread = threading.Thread(
            target=run_bottleneck,
            args=(
                topo,
                peer_svc,
                namespace,
                grpc_port,
            ),
            daemon=True,
        )

        stress_thread.start()
    
    inject_messages(
        run_id=run_id,
        source_id=source_id,
        peer_svc=peer_svc,
        namespace=namespace,
        grpc_port=grpc_port,
        message_count=message_count,
        message_interval=message_interval,
        retry_unavailable_source=(mode == "exp10_pod_delete"),
    )

    if mode in (
        "churn",
        "mixed_resources",
        "bottleneck",
        "exp10_pod_delete",
    ):
        if stress_thread is not None:
            stress_thread.join()

    elif mode != "none":
        time.sleep(float(failure["trigger_time"]))

        target = choose_target(topo, mode)

        if target is None:
            log_event(
                event="failure_skipped",
                run_id=run_id,
                failure_mode=mode,
            )
        else:
            is_ch = topo["nodes"][str(target)]["is_cluster_head"]

            log_event(
                event="failure_triggered",
                run_id=run_id,
                failure_mode=mode,
                target_peer=target,
                is_cluster_head=is_ch,
            )

            if mode in ("node_failure", "ch_failure"):
                fail_stop_peer(target, peer_svc, namespace, grpc_port)
                broadcast_dcsoc_maintenance(
                    topo, peer_svc, namespace, grpc_port, node_id=target,
                    available=False, reason=mode,
                )

            elif mode == "overload":
                apply_overload(target, peer_svc, namespace, grpc_port, overload_ms)

            else:
                raise ValueError(mode)

    else:
        log_event(
            event="failure_skipped",
            run_id=run_id,
            failure_mode="none",
        )

    time.sleep(float(topo.get("settle_time", 15.0)))

    log_event(event="run_finished", run_id=run_id)


if __name__ == "__main__":
    main()
