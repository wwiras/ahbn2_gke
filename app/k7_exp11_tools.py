"""K7 Exp11 configuration, topology contract, and run validation helpers."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import yaml
from gen_topology import assign_clusters, assign_dcsoc_clusters, build_graph

ALGORITHMS = ("gossip", "structured", "dcsoc", "ahbn")
STRATEGIES = {"gossip":"gossip", "structured":"cluster", "dcsoc":"dcsoc", "ahbn":"ahbn"}
SEEDS = (42,43,44,45,46)
PLANNED_LEAVE_OFFSETS_S = (1.0, 8.0, 15.0, 22.0)
FEASIBILITY_LEAVE_OFFSETS_S = (1.0, 26.0, 51.0, 76.0)
FEASIBILITY_MESSAGE_COUNT = 240

def planned_wait_seconds(experiment_start: float, planned_offset: float,
                         current_time: float, previous_cycle_complete: bool) -> float:
    """Return time until a frozen event, or fail rather than shift its time."""
    if not previous_cycle_complete:
        raise RuntimeError("preceding churn cycle unresolved at planned leave time")
    remaining = float(experiment_start) + float(planned_offset) - float(current_time)
    if remaining < 0:
        raise RuntimeError("planned churn deadline missed; run is invalid")
    return remaining

def choose_exp10_target(topo):
    """Compatibility symbol required by the shared controller; unused by K7."""
    event=topo["k7_exp11"]["planned_churn_schedule"][0]
    return {"peer_id":event["target_peer"],"role":event["target_role"],"cluster_id":topo["nodes"][str(event["target_peer"])].get("cluster_id"),"degree":len(topo["nodes"][str(event["target_peer"])]["neighbors"])}

def design(base: dict, seed: int) -> tuple[int,list[int]]:
    n=int(base["numNodes"]); nc=int(base["numClusters"]); tc=base["topology"]
    graph=build_graph(n,tc["type"],float(tc.get("edgeProb",.2)),int(tc["baM"]),seed)
    sh,_,_=assign_clusters(n,nc); dc=base.get("dcsoc",{})
    dh,_,_,_,_=assign_dcsoc_clusters(graph,float(dc.get("eps",2)),int(dc.get("min_samples",3)))
    source_candidates=sorted(set(graph)-set(sh)-set(dh))
    if not source_candidates: raise RuntimeError("no common non-structural source")
    source=source_candidates[0]
    ranked=lambda xs: sorted((x for x in xs if x!=source),key=lambda x:(-graph.degree(x),x))
    targets=[]
    for pool in (ranked(dh),ranked(sh),ranked(graph.nodes)):
        for peer in pool:
            if peer not in targets: targets.append(peer)
            if len(targets)==4: return source,targets
    raise RuntimeError("fewer than four distinct non-source churn targets")

def write_config(base_path: Path,out: Path,algorithm: str,seed: int,
                 feasibility_dcsoc: bool = False) -> None:
    if algorithm not in ALGORITHMS or seed not in SEEDS: raise ValueError("invalid K7 coordinate")
    if feasibility_dcsoc and (algorithm != "dcsoc" or seed != 42):
        raise ValueError("feasibility gate is DC-SoC seed42 only")
    cfg=yaml.safe_load(base_path.read_text()); source,targets=design(cfg,seed)
    cfg["experiment"]=f"k7_exp11_{algorithm}_seed{seed}"; cfg["strategy"]=STRATEGIES[algorithm]
    cfg["topology"]["seed"]=seed; cfg["messageSource"]=source; cfg["k5_h2"]["seed"]=seed
    cfg["k7_exp11"].update({"algorithm":algorithm,"seed":seed,"source_peer":source,"target_peers":targets})
    if feasibility_dcsoc:
        cfg["experiment"]="k7_dcsoc_feas25_seed42"
        cfg["workload"]["messageCount"]=FEASIBILITY_MESSAGE_COUNT
        cfg["k7_exp11"].update({"feasibility_gate":"dcsoc_25s_seed42","scientific_use":"FEASIBILITY-ONLY / NOT EXP11 RESULT","plannedLeaveOffsetsSec":list(FEASIBILITY_LEAVE_OFFSETS_S)})
    cfg["dcsoc"]={"eps":2.0,"min_samples":3,"preserve_message_source":True,"dynamic_maintenance":algorithm=="dcsoc"}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(yaml.safe_dump(cfg,sort_keys=False))

def enrich_topology(path: Path, config_path: Path) -> None:
    topo=json.loads(path.read_text()); cfg=yaml.safe_load(config_path.read_text()); meta=cfg["k7_exp11"]
    targets=[int(x) for x in meta["target_peers"]]
    events=[]
    offsets=tuple(float(x) for x in meta["plannedLeaveOffsetsSec"])
    expected_offsets=FEASIBILITY_LEAVE_OFFSETS_S if meta.get("feasibility_gate") else PLANNED_LEAVE_OFFSETS_S
    if offsets != expected_offsets:
        raise ValueError("K7 planned leave offsets differ from frozen schedule")
    for i,(target,offset) in enumerate(zip(targets,offsets),1):
        node=topo["nodes"][str(target)]
        role=(node.get("dcsoc_role","TAIL").upper() if meta["algorithm"]=="dcsoc" else "CH" if meta["algorithm"]=="structured" and node["is_cluster_head"] else "PEER")
        events.append({"event_index":i,"target_peer":target,"target_role":role,"planned_leave_offset_s":offset,"recovery_action":"statefulset_recreate_and_ready_alive"})
    topo["k7_exp11"]={**meta,"planned_churn_schedule":events,"num_events":4,"schedule_semantics":"fixed_offsets_fail_closed","maintenance_interval":"after_each_completed_cycle" if meta["algorithm"]=="dcsoc" else None}
    path.write_text(json.dumps(topo,indent=2)+"\n")

def validate_feasibility_topology(path: Path) -> None:
    t=json.loads(path.read_text()); m=t.get("k7_exp11",{}); schedule=m.get("planned_churn_schedule",[])
    targets=[int(e["target_peer"]) for e in schedule]
    checks={"identity":t.get("experiment")=="k7_dcsoc_feas25_seed42","coordinate":t.get("strategy")=="dcsoc" and m.get("algorithm")=="dcsoc" and m.get("seed")==42,"workload":t.get("workload")=={"message_count":FEASIBILITY_MESSAGE_COUNT,"message_interval":.4},"schedule":tuple(float(e["planned_leave_offset_s"]) for e in schedule)==FEASIBILITY_LEAVE_OFFSETS_S,"targets":targets==[0,5,10,15] and len(set(targets))==4,"source_safe":int(t["message_source"]) not in targets,"label":m.get("scientific_use")=="FEASIBILITY-ONLY / NOT EXP11 RESULT"}
    bad=[name for name,ok in checks.items() if not ok]
    if bad: raise ValueError(f"{path}: feasibility contract failed: {bad}")

def validate_topologies(paths: list[Path], expected=ALGORITHMS) -> None:
    seen=[]; reference=None; physical=None
    for path in paths:
        t=json.loads(path.read_text()); m=t.get("k7_exp11",{}); a=m.get("algorithm"); seen.append(a)
        schedule=m.get("planned_churn_schedule",[]); targets=[e.get("target_peer") for e in schedule]; offsets=tuple(e.get("planned_leave_offset_s") for e in schedule)
        checks={"identity":t.get("experiment")==f"k7_exp11_{a}_seed{m.get('seed')}","strategy":t.get("strategy")==STRATEGIES.get(a),"scale":(t.get("num_nodes"),t.get("topology_type"),t.get("ba_m"))==(20,"ba",2),"workload":t.get("workload")=={"message_count":80,"message_interval":.4},"timing":t.get("settle_time")==18 and t["failure"]=={"mode":"churn","trigger_time":1.0,"overload_delay_ms":200,"num_events":4,"interval_sec":1.2,"target_type":"mixed"},"schedule":len(schedule)==4 and len(set(targets))==4 and offsets==PLANNED_LEAVE_OFFSETS_S and m.get("schedule_semantics")=="fixed_offsets_fail_closed","source_safe":t.get("message_source") not in targets,"S5":t.get("k5_h2",{}).get("actuator_treatment")=="S5","isolation":bool(t["dcsoc"]["dynamic_maintenance"])==(a=="dcsoc")}
        bad=[k for k,v in checks.items() if not v]
        if bad: raise ValueError(f"{path}: K7 contract failed: {bad}")
        match=(t["message_source"],targets,offsets,t["workload"],t["failure"],t["settle_time"])
        graph={k:v["neighbors"] for k,v in t["nodes"].items()}
        if reference is not None and match!=reference: raise ValueError("matched K7 inputs differ")
        if physical is not None and graph!=physical: raise ValueError("matched physical topology differs")
        reference,physical=match,graph
    if tuple(seen)!=tuple(expected): raise ValueError(f"treatment order mismatch: {seen}")

def load_jsonl(path: Path) -> list[dict]:
    rows=[]; seen=set(); decoder=json.JSONDecoder()
    for no,line in enumerate(path.read_text().splitlines(),1):
        pending=line.strip()
        if not pending.startswith("{"): continue
        try:
            while pending:
                row,end=decoder.raw_decode(pending)
                identity=json.dumps(row,sort_keys=True,separators=(",",":"))
                if identity not in seen: rows.append(row); seen.add(identity)
                pending=pending[end:].lstrip()
        except json.JSONDecodeError as e: raise ValueError(f"{path}:{no}: invalid JSON") from e
    return rows

def _elapsed(row: dict, workload_origin: float) -> float:
    """Use an explicit common domain when supplied; preserve raw timestamps."""
    if "workload_elapsed_s" in row:
        return float(row["workload_elapsed_s"])
    return float(row["ts"]) - workload_origin

def validate_churn_timeline(topo: dict, rows: list[dict]) -> dict:
    """Independently validate workload pacing and all frozen churn cycles."""
    meta=topo["k7_exp11"]; schedule=meta.get("planned_churn_schedule",[])
    expected_offsets=PLANNED_LEAVE_OFFSETS_S
    observed_offsets=tuple(float(e.get("planned_leave_offset_s",-1)) for e in schedule)
    if len(schedule)!=4 or observed_offsets!=expected_offsets:
        raise ValueError(f"planned churn schedule invalid: expected={expected_offsets} observed={observed_offsets}")
    injected=[r for r in rows if r.get("event")=="message_injected"]
    if len(injected)!=80:
        raise ValueError(f"injected_count invalid: expected=80 observed={len(injected)}")
    message_ids=[r.get("message_id") for r in injected]
    if len(set(message_ids))!=80:
        raise ValueError(f"unique injected messages invalid: expected=80 observed={len(set(message_ids))}")
    injected=sorted(injected,key=lambda r:float(r.get("workload_elapsed_s",r["ts"])))
    origin=float(injected[0]["ts"]); injection_elapsed=[_elapsed(r,origin) for r in injected]
    if injection_elapsed[-1] < 79*.4:
        raise ValueError(f"workload pacing invalid: duration={injection_elapsed[-1]:.3f}s expected_at_least={79*.4:.3f}s")
    leaves=[r for r in rows if r.get("event")=="churn_leave_scheduled"]
    downs=[r for r in rows if r.get("event")=="pod_unavailability_observed"]
    joins=[r for r in rows if r.get("event")=="churn_rejoined"]
    if (len(leaves),len(downs),len(joins))!=(4,4,4):
        raise ValueError(f"churn event counts invalid: leaves={len(leaves)} unavailable={len(downs)} rejoined={len(joins)}")
    leaves.sort(key=lambda r:int(r["event_index"])); downs.sort(key=lambda r:int(r["event_index"])); joins.sort(key=lambda r:int(r["event_index"]))
    planned_epochs=[float(r["planned_leave_time"]) for r in leaves]
    planned_gaps=tuple(round(t-planned_epochs[0],6) for t in planned_epochs)
    expected_gaps=tuple(t-expected_offsets[0] for t in expected_offsets)
    if planned_gaps!=expected_gaps:
        raise ValueError(f"dynamic rescheduling detected: expected gaps={expected_gaps} observed={planned_gaps}")
    delete_elapsed=[]; timing_errors=[]
    for index,(planned,leave,down,join) in enumerate(zip(schedule,leaves,downs,joins),1):
        if any(int(r["event_index"])!=index for r in (leave,down,join)):
            raise ValueError(f"churn event ordering invalid at event {index}")
        target=int(planned["target_peer"])
        if target==int(topo["message_source"]): raise ValueError(f"source churned at event {index}")
        if any(int(r["target_peer"])!=target for r in (leave,down,join)):
            raise ValueError(f"churn target mismatch at event {index}")
        required=("planned_leave_time","actual_delete_time","unavailable_time","recovery_ready_time","grpc_alive_time","replacement_pod_uid")
        missing=[name for name in required if name not in join]
        if missing: raise ValueError(f"event {index} timing/recovery telemetry missing: {missing}")
        if join["replacement_pod_uid"]==down.get("original_pod_uid"):
            raise ValueError(f"event {index} replacement UID did not change")
        times=[float(join[n]) for n in required[:5]]
        if not (times[0]<=times[1]<times[2]<=times[3]<=times[4]):
            raise ValueError(f"event {index} timing ordering invalid: {times}")
        if index>1 and float(joins[index-2]["grpc_alive_time"])>=times[0]:
            raise ValueError(f"event {index} overlaps unresolved preceding cycle")
        elapsed=float(join.get("actual_delete_workload_elapsed_s",times[1]-origin)); delete_elapsed.append(elapsed)
        if elapsed < float(planned["planned_leave_offset_s"]) or elapsed-float(planned["planned_leave_offset_s"])>0.5:
            timing_errors.append(f"event {index} delete timing outside tolerance: planned={planned['planned_leave_offset_s']:.2f}s actual={elapsed:.2f}s")
    if delete_elapsed[-1]>=injection_elapsed[-1]:
        raise ValueError(f"last churn workload_elapsed={delete_elapsed[-1]:.2f} s, last injection workload_elapsed={injection_elapsed[-1]:.2f} s")
    if timing_errors: raise ValueError(timing_errors[0])
    return {"injected_count":80,"first_injected_ts":float(injected[0]["ts"]),"last_injected_ts":float(injected[-1]["ts"]),"workload_duration_s":injection_elapsed[-1],"delete_elapsed_s":delete_elapsed}

def active_at(peer: int, ts: float, events: list[dict]) -> bool:
    active=True
    for e in sorted(events,key=lambda x:float(x["ts"])):
        if float(e["ts"])>ts: break
        if int(e["target_peer"])==peer: active=e["event"]=="churn_rejoined"
    return active

def validate_run(run_dir: Path) -> dict:
    missing=[n for n in ("topology.json","logs.jsonl","controller.log","pods.json") if not (run_dir/n).is_file()]
    if missing: raise ValueError(f"missing mandatory artifacts: {missing}")
    topo=json.loads((run_dir/"topology.json").read_text()); rows=load_jsonl(run_dir/"logs.jsonl"); meta=topo["k7_exp11"]; algorithm=meta["algorithm"]
    timeline=validate_churn_timeline(topo,rows)
    leaves=[r for r in rows if r.get("event")=="churn_leave_scheduled"]; downs=[r for r in rows if r.get("event")=="pod_unavailability_observed"]; joins=[r for r in rows if r.get("event")=="churn_rejoined"]
    for i,(leave,down,join) in enumerate(zip(leaves,downs,joins),1):
        if {int(leave["event_index"]),int(down["event_index"]),int(join["event_index"])}!={i} or not(float(leave["ts"])<float(down["ts"])<float(join["ts"])): raise ValueError("churn ordering invalid")
        if int(join["target_peer"])==int(topo["message_source"]): raise ValueError("source churned")
        required=("planned_leave_time","actual_delete_time","unavailable_time","recovery_ready_time","grpc_alive_time")
        if any(name not in join for name in required): raise ValueError("incomplete K7 timing telemetry")
        if i>1 and not float(joins[i-2]["grpc_alive_time"]) < float(join["planned_leave_time"]): raise ValueError("overlapping churn cycles")
        if not (float(join["planned_leave_time"]) <= float(join["actual_delete_time"]) < float(join["unavailable_time"]) <= float(join["recovery_ready_time"]) <= float(join["grpc_alive_time"])): raise ValueError("K7 timing telemetry ordering invalid")
    maintenance=[r for r in rows if r.get("event")=="dcsoc_maintenance"]
    if algorithm=="dcsoc" and not maintenance: raise ValueError("DC-SoC maintenance missing")
    if algorithm!="dcsoc" and maintenance: raise ValueError("maintenance leaked")
    traces=[r for r in rows if r.get("event")=="ahbn_controller_trace"]; decisions=[r for r in rows if r.get("event")=="k5_final_actuator_decision"]
    if (algorithm=="ahbn") != bool(traces and decisions): raise ValueError("AHBN trace isolation failed")
    injected=[r for r in rows if r.get("event")=="message_injected"]
    received=[r for r in rows if r.get("event")=="received_new"]; dup=[r for r in rows if r.get("event")=="received_duplicate"]; fwd=[r for r in rows if r.get("event")=="forward"]
    churn_state=[{"event":"churn_rejoined","target_peer":r["target_peer"],"ts":r["ts"]} for r in joins]+[{"event":"churn_down","target_peer":r["peer_id"],"ts":r["ts"]} for r in downs]
    opportunities=[]
    for inj in injected:
        ts=float(inj["ts"]); active={p for p in range(topo["num_nodes"]) if active_at(p,ts,churn_state)}; got={int(r["peer_id"]) for r in received if r.get("message_id")==inj["message_id"]}
        relevant=[float(r["ts"]) for r in received if r.get("message_id")==inj["message_id"] and int(r["peer_id"]) in active]
        opportunities.append({"message_id":inj["message_id"],"injected_ts":ts,"active_peers":sorted(active),"expected_count":len(active),"delivered_count":len(active&got),"full_delivery":active<=got,"completion_ts":max(relevant) if active<=got and relevant else None})
    recoveries=[]
    for join in joins:
        candidates=[o for o in opportunities if o["injected_ts"]>=float(join["ts"]) and o["full_delivery"]]
        first=candidates[0] if candidates else None
        recoveries.append({"event_index":join["event_index"],"recovered":first is not None,"recovery_time_s":first["completion_ts"]-float(join["ts"]) if first else None,"recovery_message_id":first["message_id"] if first else None,"censored":first is None,"censored_at_s":topo["settle_time"] if first is None else None})
    expected=sum(o["expected_count"] for o in opportunities); delivered=sum(o["delivered_count"] for o in opportunities)
    result={"run_id":topo["run_id"],"algorithm":algorithm,"seed":meta["seed"],"delivery_ratio":delivered/expected,"propagation_delay":None,"duplicates":len(dup),"total_forwards":len(fwd),"churn_events":4,"recovered_events":sum(r["recovered"] for r in recoveries),"recovery_events":recoveries,"core_replacement_count":max((int(r.get("core_replacement_count",0)) for r in maintenance),default=0),"rejoin_assignment_count":max((int(r.get("rejoin_assignment_count",0)) for r in maintenance),default=0),"recluster_count":max((int(r.get("recluster_count",0)) for r in maintenance),default=0),"maintenance_duration":sum(float(r.get("maintenance_duration",0)) for r in maintenance)}
    delays=[]
    for inj in injected:
        arrivals=[float(r["ts"]) for r in received if r.get("message_id")==inj["message_id"]]
        if arrivals: delays.append(max(arrivals)-float(inj["ts"]))
    result["propagation_delay"]=sum(delays)/len(delays) if delays else None
    (run_dir/"metrics.json").write_text(json.dumps(result,indent=2)+"\n"); (run_dir/"churn_events.json").write_text(json.dumps({"planned":meta["planned_churn_schedule"],"observed":{"leaves":leaves,"unavailable":downs,"rejoined":joins},"recovery":recoveries,"delivery_opportunities":opportunities},indent=2)+"\n")
    return result

def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd",required=True)
    c=s.add_parser("config"); c.add_argument("--base",type=Path,required=True); c.add_argument("--out",type=Path,required=True); c.add_argument("--algorithm",choices=ALGORITHMS,required=True); c.add_argument("--seed",type=int,required=True); c.add_argument("--feasibility-dcsoc",action="store_true")
    e=s.add_parser("enrich"); e.add_argument("--topology",type=Path,required=True); e.add_argument("--config",type=Path,required=True)
    v=s.add_parser("contract"); v.add_argument("paths",nargs="+",type=Path)
    r=s.add_parser("run"); r.add_argument("--run-dir",type=Path,required=True)
    f=s.add_parser("feasibility-contract"); f.add_argument("path",type=Path)
    a=p.parse_args()
    if a.cmd=="config": write_config(a.base,a.out,a.algorithm,a.seed,a.feasibility_dcsoc)
    elif a.cmd=="enrich": enrich_topology(a.topology,a.config)
    elif a.cmd=="contract": validate_topologies(a.paths)
    elif a.cmd=="feasibility-contract": validate_feasibility_topology(a.path)
    else: print(json.dumps(validate_run(a.run_dir),sort_keys=True))
if __name__=="__main__": main()
