#!/usr/bin/env python3
"""Audit the single K7 DC-SoC 25-second calibration gate; never compare treatments."""
from __future__ import annotations
import argparse,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).parents[1]; sys.path.insert(0,str(ROOT/"app"))
from k7_exp11_tools import FEASIBILITY_LEAVE_OFFSETS_S,load_jsonl,validate_feasibility_topology

LABEL="FEASIBILITY-ONLY / NOT EXP11 RESULT"

def diagnostic_failures(rows: list[dict]) -> list[dict]:
    server_events={}
    for row in rows:
        request_id=row.get("request_id")
        if request_id and str(row.get("event","")).startswith("k7_dcsoc_rpc_"):
            server_events.setdefault(request_id,{})[row["event"]]=row
    failures=[]
    for client in rows:
        if client.get("event")!="k7_feasibility_maintenance_rpc" or client.get("final_status")=="ACK": continue
        trace=server_events.get(client.get("request_id"),{})
        entry=trace.get("k7_dcsoc_rpc_handler_entry"); before=trace.get("k7_dcsoc_rpc_before_set_availability"); after=trace.get("k7_dcsoc_rpc_after_set_availability"); sync_before=trace.get("k7_dcsoc_rpc_before_sync_peer"); sync_after=trace.get("k7_dcsoc_rpc_after_sync_peer"); exit_row=trace.get("k7_dcsoc_rpc_handler_exit")
        duration=lambda left,left_key,right,right_key: float(right[right_key])-float(left[left_key]) if left and right else None
        failures.append({"request_id":client.get("request_id"),"event_index":client.get("event_index"),"phase":client.get("phase"),"destination_peer":client.get("destination_peer"),"client_status":client.get("final_status"),"client_rpc_code":client.get("rpc_code"),"client_start_time":client.get("rpc_start_time"),"client_end_time":client.get("rpc_end_time"),"server_entry_present":entry is not None,"server_entry_time":entry.get("handler_entry_time") if entry else None,"entry_to_operation_s":duration(entry,"handler_entry_time",before,"before_set_availability_time"),"set_availability_s":duration(before,"before_set_availability_time",after,"after_set_availability_time"),"sync_peer_s":duration(sync_before,"before_sync_peer_time",sync_after,"after_sync_peer_time"),"handler_exit_present":exit_row is not None,"server_exit_time":exit_row.get("handler_exit_time") if exit_row else None,"handler_success":exit_row.get("success") if exit_row else None})
    return failures

def analyze(root: Path) -> dict:
    run=root/"runs"/"seed42"/"dcsoc"; validate_feasibility_topology(run/"topology.json")
    rows=load_jsonl(run/"logs.jsonl")
    cycles=sorted((r for r in rows if r.get("event")=="k7_dcsoc_feasibility_cycle"),key=lambda r:int(r["event_index"]))
    injected=sorted((r for r in rows if r.get("event")=="message_injected"),key=lambda r:float(r["ts"]))
    pods=json.loads((run/"pods.json").read_text()).get("items",[]) if (run/"pods.json").is_file() else []
    final_healthy=len(pods)==20 and all(any(c.get("type")=="Ready" and c.get("status")=="True" for c in p.get("status",{}).get("conditions",[])) for p in pods)
    complete=len(cycles)==4 and [int(c["event_index"]) for c in cycles]==[1,2,3,4]
    required=("planned_leave_time","actual_delete_time","unavailable_time","replacement_uid_observed_time","replacement_pod_ip","recovery_ready_time","grpc_alive_time","leave_maintenance_start","leave_maintenance_end","rejoin_maintenance_start","rejoin_maintenance_end","explicit_du_start","explicit_du_end","structural_cycle_completion_time")
    valid=[]
    for c in cycles:
        ordered=all(k in c for k in required) and float(c["planned_leave_time"])<=float(c["actual_delete_time"])<float(c["unavailable_time"])<=float(c["replacement_uid_observed_time"])<=float(c["recovery_ready_time"])<=float(c["grpc_alive_time"])<=float(c["leave_maintenance_start"])<=float(c["leave_maintenance_end"])<=float(c["rejoin_maintenance_start"])<=float(c["rejoin_maintenance_end"])<=float(c["explicit_du_start"])<=float(c["explicit_du_end"])<=float(c["structural_cycle_completion_time"])
        valid.append(ordered and bool(c.get("replacement_pod_ip")) and c.get("cycle_status")=="PASS" and c.get("original_pod_uid")!=c.get("replacement_pod_uid") and int(c.get("maintenance_acknowledgement_count",-1))==int(c.get("expected_acknowledgement_count",-2)) and not c.get("failed_peer_ids"))
    last_injection=float(injected[-1]["ts"]) if len(injected)==240 else None
    event4_before_end=complete and last_injection is not None and float(cycles[-1].get("structural_cycle_completion_time",float("inf")))<last_injection
    spacing_ok=complete and all(float(cycles[i]["structural_cycle_completion_elapsed_s"])<FEASIBILITY_LEAVE_OFFSETS_S[i+1] for i in range(3))
    passed=complete and all(valid) and len(injected)==240 and spacing_ok and event4_before_end and final_healthy
    totals=[float(c["total_cycle_s"]) for c,v in zip(cycles,valid) if v]
    slacks=[float(c["slack_before_next_event_s"]) for c in cycles[:3] if c.get("slack_before_next_event_s") is not None]
    failures=diagnostic_failures(rows)
    report={"title":"K7 DC-SoC 25s FEASIBILITY GATE","scientific_use":LABEL,"feasibility":"PASS" if passed else "FAIL","events":cycles,"rpc_diagnostic_failures":failures,"criteria":{"four_cycles":complete,"240_injections":len(injected)==240,"all_cycle_requirements":complete and all(valid),"fixed_25s_slots_respected":spacing_ok,"event4_completed_before_last_injection":event4_before_end,"final_runtime_health":final_healthy},"maximum_total_cycle_s":max(totals) if totals else None,"mean_total_cycle_s":statistics.fmean(totals) if totals else None,"minimum_slack_before_next_event_s":min(slacks) if slacks else None,"events_with_rpc_timeout":sum(int(c.get("rpc_timeout_count",0))>0 for c in cycles),"event4_completion_relative_to_end_of_injection_s":float(cycles[-1]["structural_cycle_completion_time"])-last_injection if complete and last_injection is not None else None,"decision":"Candidate 25-second spacing supported by this feasibility gate. Final K7 contract may now be reviewed for freezing." if passed else "Candidate 25-second spacing NOT supported. Do not freeze or run formal K7. Review timing evidence before selecting another contract."}
    out=root/"results"; out.mkdir(parents=True,exist_ok=True); (out/"dcsoc_feas25_report.json").write_text(json.dumps(report,indent=2)+"\n")
    lines=[report["title"],LABEL]
    for c in cycles: lines += [f"Event {c['event_index']}: target={c.get('target_peer')} infrastructure={c.get('infrastructure_recovery_s')} total={c.get('total_cycle_s')} slack={c.get('slack_before_next_event_s',c.get('dissemination_time_remaining_after_cycle_s'))} timeouts={c.get('rpc_timeout_count',0)} status={c.get('cycle_status')}"]
    for failure in failures: lines += [f"Event {failure['event_index']} {failure['phase']} peer {failure['destination_peer']}: client={failure['client_status']}/{failure['client_rpc_code']} server_entry={failure['server_entry_present']} entry_to_operation_s={failure['entry_to_operation_s']} set_availability_s={failure['set_availability_s']} sync_peer_s={failure['sync_peer_s']} handler_exit={failure['handler_exit_present']} success={failure['handler_success']}"]
    lines += [f"Overall: FEASIBILITY {report['feasibility']}",report["decision"]]
    (out/"dcsoc_feas25_report.txt").write_text("\n".join(lines)+"\n"); print("\n".join(lines))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); a=p.parse_args(); raise SystemExit(0 if analyze(a.root)["feasibility"]=="PASS" else 1)
