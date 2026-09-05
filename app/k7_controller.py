"""K7-only churn controller layered over the frozen shared controller."""
from __future__ import annotations
import sys, time
import k7_exp11_tools
sys.modules["k5_exp10_tools"] = k7_exp11_tools
import controller_shared as controller
from kubernetes import client, config
from kubernetes.client.rest import ApiException

def _peer_destination(peer_id, target, replacement_ip, svc, namespace, port):
    """Bind only the churn target to its observed replacement incarnation."""
    return f"{replacement_ip}:{port}" if peer_id==target else controller.peer_addr(peer_id,svc,namespace,port)

def _direct_replacement_status(replacement_ip, port):
    address=f"{replacement_ip}:{port}"
    with controller.grpc.insecure_channel(address) as channel:
        return controller.peer_pb2_grpc.PeerServiceStub(channel).GetStatus(controller.peer_pb2.Empty(),timeout=2)

def _replacement_identity(pod, old_uid):
    if pod.metadata.uid==old_uid: return None
    return pod.metadata.uid,pod.status.pod_ip

def _maintenance_request_id(event_index, phase, peer_id):
    return f"k7-feas-event{event_index}-{phase}-peer{peer_id}"

def _maintenance_phase(topo, target, event_index, phase, svc, namespace, port, replacement_ip, **request):
    """Run the frozen peer-local operation and make every acknowledgement auditable."""
    start=controller.now(); failed=[]; timeouts=0; unavailable=0; acknowledged=0
    for raw_peer_id in sorted(topo["nodes"],key=int):
        peer_id=int(raw_peer_id)
        destination=_peer_destination(peer_id,target,replacement_ip,svc,namespace,port)
        addressing_type="replacement_pod_ip" if peer_id==target else "statefulset_dns"
        request_id=_maintenance_request_id(event_index,phase,peer_id)
        rpc_start=controller.now(); final_status="OTHER_GRPC_ERROR"; rpc_code=None; rpc_details=None; error_text=None; ack_message=None
        try:
            with controller.grpc.insecure_channel(destination) as channel:
                ack=controller.peer_pb2_grpc.PeerServiceStub(channel).ApplyDCSOCMaintenance(
                    controller.peer_pb2.DCSOCMaintenanceRequest(reason=f"k7_event_{event_index}_{phase}",**request),
                    timeout=3,metadata=(("x-k7-request-id",request_id),))
            if ack.ok: acknowledged+=1
            else: failed.append(peer_id)
            final_status="ACK" if ack.ok else "NACK"; rpc_code="OK"; ack_message=ack.message
        except controller.grpc.RpcError as error:
            failed.append(peer_id); code=error.code()
            timeouts+=int(code==controller.grpc.StatusCode.DEADLINE_EXCEEDED)
            unavailable+=int(code==controller.grpc.StatusCode.UNAVAILABLE)
            rpc_code=code.name; rpc_details=error.details() if hasattr(error,"details") else None; error_text=str(error)
            final_status=code.name if code in (controller.grpc.StatusCode.DEADLINE_EXCEEDED,controller.grpc.StatusCode.UNAVAILABLE) else "OTHER_GRPC_ERROR"
        finally:
            rpc_end=controller.now()
            controller.log_event(event="k7_feasibility_maintenance_rpc",request_id=request_id,event_index=event_index,event_number=event_index,phase=phase,target_peer=target,affected_peer=target,destination_peer=peer_id,destination_is_target=peer_id==target,destination_endpoint=destination,addressing_type=addressing_type,rpc_start_time=rpc_start,rpc_end_time=rpc_end,rpc_elapsed_s=rpc_end-rpc_start,rpc_deadline_s=3,final_status=final_status,rpc_code=rpc_code,rpc_details=rpc_details,error=error_text,ack_message=ack_message)
    end=controller.now()
    result={"phase":phase,"start_time":start,"end_time":end,"duration_s":end-start,"acknowledgement_count":acknowledged,"expected_acknowledgement_count":len(topo["nodes"]),"rpc_timeout_count":timeouts,"rpc_unavailable_count":unavailable,"failed_peer_ids":failed}
    controller.log_event(event="k7_dcsoc_phase",event_index=event_index,target_peer=target,**result)
    return result

def _delete_and_recover(topo, target, event_index, svc, namespace, port, bind_replacement_ip=False):
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
    ready_deadline=time.monotonic()+180; replacement_uid=None; replacement_ip=None; replacement_uid_at=None; ready_at=None; grpc_alive_at=None
    while time.monotonic()<ready_deadline:
        try:
            pod=api.read_namespaced_pod(name,namespace)
            identity=_replacement_identity(pod,old_uid)
            if identity is not None and replacement_uid_at is None:
                replacement_uid,replacement_ip=identity; replacement_uid_at=controller.now()
                controller.log_event(event="replacement_uid_observed",event_index=event_index,target_peer=target,replacement_pod_uid=replacement_uid,replacement_pod_ip=replacement_ip,replacement_uid_observed_time=replacement_uid_at)
            is_ready=pod.metadata.uid!=old_uid and any(c.type=="Ready" and c.status=="True" for c in (pod.status.conditions or []))
            if is_ready and (pod.status.pod_ip or not bind_replacement_ip):
                replacement_uid=pod.metadata.uid; replacement_ip=pod.status.pod_ip; ready_at=controller.now(); check_start=controller.now()
                try:
                    if bind_replacement_ip:
                        controller.log_event(event="replacement_pod_ip_bound",event_index=event_index,target_peer=target,replacement_pod_uid=replacement_uid,replacement_pod_ip=replacement_ip,destination=f"{replacement_ip}:{port}",kubernetes_ready_time=ready_at)
                        status=_direct_replacement_status(replacement_ip,port); check_end=controller.now()
                        controller.log_event(event="replacement_ip_get_status",event_index=event_index,target_peer=target,replacement_pod_uid=replacement_uid,replacement_pod_ip=replacement_ip,destination=f"{replacement_ip}:{port}",get_status_start=check_start,get_status_end=check_end,get_status_result="ready" if status.ready else "not_ready")
                    else:
                        controller.wait_for_peer_ready(target,svc,namespace,port,timeout=5); status=type("Status",(),{"ready":True})(); check_end=controller.now()
                    if status.ready: grpc_alive_at=check_end; break
                    ready_at=None
                except controller.grpc.RpcError as error:
                    check_end=controller.now(); ready_at=None
                    controller.log_event(event="replacement_ip_get_status",event_index=event_index,target_peer=target,replacement_pod_uid=replacement_uid,replacement_pod_ip=replacement_ip,destination=f"{replacement_ip}:{port}",get_status_start=check_start,get_status_end=check_end,get_status_result="rpc_error",rpc_code=error.code().name,error=str(error))
                except RuntimeError:
                    ready_at=None
        except ApiException as error:
            if error.status!=404: raise
        time.sleep(.25)
    if ready_at is None or grpc_alive_at is None: raise RuntimeError(f"event {event_index}: replacement never became Ready/alive")
    if replacement_uid_at is None: raise RuntimeError(f"event {event_index}: changed replacement UID not observed")
    return actual_delete,down,replacement_uid_at,ready_at,grpc_alive_at,old_uid,replacement_uid,replacement_ip

def run_k7_churn(topo, svc, namespace, port):
    meta=topo["k7_exp11"]; experiment_start=controller.now(); previous_complete=True
    for event in meta["planned_churn_schedule"]:
        i=int(event["event_index"]); target=int(event["target_peer"]); planned=experiment_start+float(event["planned_leave_offset_s"])
        wait=k7_exp11_tools.planned_wait_seconds(experiment_start,event["planned_leave_offset_s"],controller.now(),previous_complete)
        time.sleep(wait)
        controller.log_event(event="churn_leave_scheduled",run_id=topo["run_id"],event_index=i,planned_leave_time=planned,target_peer=target,target_role=event["target_role"])
        previous_complete=False
        feasibility=bool(meta.get("feasibility_gate"))
        try:
            actual_delete,down,replacement_uid_at,ready,grpc_alive,original_uid,replacement_uid,replacement_ip=_delete_and_recover(topo,target,i,svc,namespace,port,bind_replacement_ip=feasibility)
        except Exception as error:
            if meta.get("feasibility_gate"):
                controller.log_event(event="k7_dcsoc_feasibility_cycle",event_index=i,target_peer=target,target_role=event["target_role"],planned_leave_time=planned,planned_leave_elapsed_s=float(event["planned_leave_offset_s"]),cycle_status="FAIL_INFRA",error=str(error))
            raise
        phases=[]
        if topo["strategy"]=="dcsoc" and feasibility:
            phases.append(_maintenance_phase(topo,target,i,"leave",svc,namespace,port,replacement_ip,node_id=target,available=False))
            phases.append(_maintenance_phase(topo,target,i,"rejoin",svc,namespace,port,replacement_ip,node_id=target,available=True))
            phases.append(_maintenance_phase(topo,target,i,"explicit_du",svc,namespace,port,replacement_ip,explicit_du=True))
        elif topo["strategy"]=="dcsoc":
            controller.broadcast_dcsoc_maintenance(topo,svc,namespace,port,node_id=target,available=False,include_affected=True,reason=f"k7_event_{i}_leave")
            controller.broadcast_dcsoc_maintenance(topo,svc,namespace,port,node_id=target,available=True,reason=f"k7_event_{i}_rejoin")
            controller.broadcast_dcsoc_maintenance(topo,svc,namespace,port,explicit_du=True,reason=f"k7_event_{i}_periodic_du")
        rejoined=controller.now(); previous_complete=True
        if not feasibility:
            controller.log_event(event="churn_rejoined",run_id=topo["run_id"],event_index=i,target_peer=target,target_role=event["target_role"],planned_leave_time=planned,actual_delete_time=actual_delete,unavailable_time=down,replacement_uid_observed_time=replacement_uid_at,recovery_ready_time=ready,grpc_alive_time=grpc_alive,rejoin_availability_time=rejoined,replacement_pod_uid=replacement_uid,downtime_duration=rejoined-down)
            continue
        failed=sorted({peer for phase in phases for peer in phase["failed_peer_ids"]}); timeouts=sum(p["rpc_timeout_count"] for p in phases); unavailable=sum(p["rpc_unavailable_count"] for p in phases); acknowledged=sum(p["acknowledgement_count"] for p in phases); expected=sum(p["expected_acknowledgement_count"] for p in phases)
        next_offset=meta["planned_churn_schedule"][i]["planned_leave_offset_s"] if i<len(meta["planned_churn_schedule"]) else None
        slack=experiment_start+float(next_offset)-rejoined if next_offset is not None else None
        remaining=experiment_start+(int(topo["workload"]["message_count"])-1)*float(topo["workload"]["message_interval"])-rejoined if next_offset is None else None
        status="PASS" if not failed and (slack is None or slack>0) and (remaining is None or remaining>0) else "FAIL_TIMEOUT" if timeouts else "FAIL_MAINTENANCE" if failed else "FAIL_DEADLINE"
        controller.log_event(event="k7_dcsoc_feasibility_cycle",run_id=topo["run_id"],event_index=i,target_peer=target,target_role=event["target_role"],planned_leave_time=planned,planned_leave_elapsed_s=float(event["planned_leave_offset_s"]),actual_delete_time=actual_delete,actual_delete_elapsed_s=actual_delete-experiment_start,unavailable_time=down,unavailable_elapsed_s=down-experiment_start,replacement_uid_observed_time=replacement_uid_at,replacement_uid_observed_elapsed_s=replacement_uid_at-experiment_start,replacement_pod_ip=replacement_ip,recovery_ready_time=ready,recovery_ready_elapsed_s=ready-experiment_start,grpc_alive_time=grpc_alive,grpc_alive_elapsed_s=grpc_alive-experiment_start,leave_maintenance_start=phases[0]["start_time"],leave_maintenance_start_elapsed_s=phases[0]["start_time"]-experiment_start,leave_maintenance_end=phases[0]["end_time"],leave_maintenance_end_elapsed_s=phases[0]["end_time"]-experiment_start,rejoin_maintenance_start=phases[1]["start_time"],rejoin_maintenance_start_elapsed_s=phases[1]["start_time"]-experiment_start,rejoin_maintenance_end=phases[1]["end_time"],rejoin_maintenance_end_elapsed_s=phases[1]["end_time"]-experiment_start,explicit_du_start=phases[2]["start_time"],explicit_du_start_elapsed_s=phases[2]["start_time"]-experiment_start,explicit_du_end=phases[2]["end_time"],explicit_du_end_elapsed_s=phases[2]["end_time"]-experiment_start,structural_cycle_completion_time=rejoined,structural_cycle_completion_elapsed_s=rejoined-experiment_start,infrastructure_recovery_s=grpc_alive-down,leave_maintenance_s=phases[0]["duration_s"],rejoin_maintenance_s=phases[1]["duration_s"],explicit_du_s=phases[2]["duration_s"],total_cycle_s=rejoined-planned,slack_before_next_event_s=slack,dissemination_time_remaining_after_cycle_s=remaining,rpc_timeout_count=timeouts,rpc_unavailable_count=unavailable,failed_peer_ids=failed,maintenance_acknowledgement_count=acknowledged,expected_acknowledgement_count=expected,cycle_status=status,original_pod_uid=original_uid,replacement_pod_uid=replacement_uid)
        if status!="PASS": raise RuntimeError(f"event {i}: feasibility cycle {status}; failed peers={failed}")
        controller.log_event(event="churn_rejoined",run_id=topo["run_id"],event_index=i,target_peer=target,target_role=event["target_role"],planned_leave_time=planned,actual_delete_time=actual_delete,unavailable_time=down,replacement_uid_observed_time=replacement_uid_at,recovery_ready_time=ready,grpc_alive_time=grpc_alive,rejoin_availability_time=rejoined,replacement_pod_uid=replacement_uid,downtime_duration=rejoined-down)

controller.run_churn = run_k7_churn
if __name__ == "__main__": controller.main()
