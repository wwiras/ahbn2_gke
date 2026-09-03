"""K7-only churn controller layered over the frozen shared controller."""
from __future__ import annotations
import sys, time
import k7_exp11_tools
sys.modules["k5_exp10_tools"] = k7_exp11_tools
import controller_shared as controller
from kubernetes import client, config
from kubernetes.client.rest import ApiException

def _delete_and_recover(topo, target, event_index, svc, namespace, port):
    config.load_incluster_config(); api=client.CoreV1Api(); name=f"peer-{target}"
    old=api.read_namespaced_pod(name,namespace); old_uid=old.metadata.uid
    api.delete_namespaced_pod(name,namespace,grace_period_seconds=0)
    actual_delete=controller.now()
    controller.log_event(event="pod_delete_requested",event_index=event_index,target_peer=target,pod_name=name,original_pod_uid=old_uid,actual_delete_time=actual_delete)
    deadline=time.monotonic()+60; down=None
    while time.monotonic()<deadline:
        try:
            pod=api.read_namespaced_pod(name,namespace); ready=any(c.type=="Ready" and c.status=="True" for c in (pod.status.conditions or []))
            if pod.metadata.uid!=old_uid or not ready:
                down=controller.now(); evidence="replacement_uid" if pod.metadata.uid!=old_uid else "not_ready"; observed_uid=pod.metadata.uid; break
        except ApiException as error:
            if error.status==404: down=controller.now(); evidence="not_found"; observed_uid=None; break
            raise
        time.sleep(.05)
    if down is None: raise RuntimeError(f"event {event_index}: unavailability not observed")
    controller.log_event(event="pod_unavailability_observed",event_index=event_index,peer_id=target,target_peer=target,ts=down,unavailable_time=down,evidence=evidence,original_pod_uid=old_uid,observed_pod_uid=observed_uid)
    ready_deadline=time.monotonic()+180; replacement_uid=None; ready_at=None; grpc_alive_at=None
    while time.monotonic()<ready_deadline:
        try:
            pod=api.read_namespaced_pod(name,namespace); is_ready=pod.metadata.uid!=old_uid and any(c.type=="Ready" and c.status=="True" for c in (pod.status.conditions or []))
            if is_ready:
                replacement_uid=pod.metadata.uid; ready_at=controller.now()
                try:
                    controller.wait_for_peer_ready(target,svc,namespace,port,timeout=5); grpc_alive_at=controller.now(); break
                except RuntimeError: ready_at=None
        except ApiException as error:
            if error.status!=404: raise
        time.sleep(.25)
    if ready_at is None or grpc_alive_at is None: raise RuntimeError(f"event {event_index}: replacement never became Ready/alive")
    return actual_delete,down,ready_at,grpc_alive_at,replacement_uid

def run_k7_churn(topo, svc, namespace, port):
    meta=topo["k7_exp11"]; experiment_start=controller.now(); previous_complete=True
    for event in meta["planned_churn_schedule"]:
        i=int(event["event_index"]); target=int(event["target_peer"]); planned=experiment_start+float(event["planned_leave_offset_s"])
        wait=k7_exp11_tools.planned_wait_seconds(experiment_start,event["planned_leave_offset_s"],controller.now(),previous_complete)
        time.sleep(wait)
        controller.log_event(event="churn_leave_scheduled",run_id=topo["run_id"],event_index=i,planned_leave_time=planned,target_peer=target,target_role=event["target_role"])
        previous_complete=False
        actual_delete,down,ready,grpc_alive,replacement_uid=_delete_and_recover(topo,target,i,svc,namespace,port)
        if topo["strategy"]=="dcsoc":
            controller.broadcast_dcsoc_maintenance(topo,svc,namespace,port,node_id=target,available=False,include_affected=True,reason=f"k7_event_{i}_leave")
            controller.broadcast_dcsoc_maintenance(topo,svc,namespace,port,node_id=target,available=True,reason=f"k7_event_{i}_rejoin")
            controller.broadcast_dcsoc_maintenance(topo,svc,namespace,port,explicit_du=True,reason=f"k7_event_{i}_periodic_du")
        rejoined=controller.now(); previous_complete=True
        controller.log_event(event="churn_rejoined",run_id=topo["run_id"],event_index=i,target_peer=target,target_role=event["target_role"],planned_leave_time=planned,actual_delete_time=actual_delete,unavailable_time=down,recovery_ready_time=ready,grpc_alive_time=grpc_alive,rejoin_availability_time=rejoined,replacement_pod_uid=replacement_uid,downtime_duration=rejoined-down)

controller.run_churn = run_k7_churn
if __name__ == "__main__": controller.main()
