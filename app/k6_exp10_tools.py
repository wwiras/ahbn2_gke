from __future__ import annotations
import argparse, json
from pathlib import Path
import yaml
from gen_topology import assign_clusters, assign_dcsoc_clusters, build_graph

ALGORITHMS=("gossip","structured","dcsoc","ahbn")
STRATEGIES={"gossip":"gossip","structured":"cluster","dcsoc":"dcsoc","ahbn":"ahbn"}
SEEDS=(42,43,44,45,46)

def exp10_metadata(topo):
    meta=topo.get("k6_exp10") or topo.get("k5_exp10")
    if not meta: raise ValueError("missing k6_exp10/k5_exp10 metadata")
    return meta

def choose_exp10_target(topo):
    nodes=topo.get("nodes",{}); strategy=str(topo.get("strategy","")); source=int(topo.get("message_source",-1))
    if strategy=="cluster":
        candidates=[int(k) for k,v in nodes.items() if int(k)!=source and v.get("is_cluster_head")]; role="CH"; basis="highest-degree realized non-source Structured CH"
    elif strategy=="dcsoc":
        candidates=[int(k) for k,v in nodes.items() if int(k)!=source and v.get("dcsoc_role")=="core"]; role="CORE"; basis="highest-degree realized non-source DC-SoC CORE"
    else:
        candidates=[int(k) for k in nodes if int(k)!=source]; role="critical forwarding peer"; basis="highest-degree realized non-source physical peer"
    if not candidates: raise RuntimeError(f"no valid non-source Exp10 critical target for strategy={strategy}, message_source={source}")
    target=max(candidates,key=lambda i:(len(nodes[str(i)].get("neighbors",[])),-i)); node=nodes[str(target)]
    return {"peer_id":target,"role":role,"cluster_id":node.get("cluster_id"),"degree":len(node.get("neighbors",[])),"selection_basis":basis}

def choose_exp10_source(cfg):
    """Choose the lowest-ID peer that is non-critical in both structural overlays."""
    num_nodes=int(cfg.get("numNodes",20)); num_clusters=int(cfg.get("numClusters",4)); topology=cfg.get("topology",{})
    graph=build_graph(num_nodes,topology.get("type","ba"),float(topology.get("edgeProb",0.2)),int(topology.get("baM",2)),int(topology.get("seed",42)))
    structured_heads,_,_=assign_clusters(num_nodes,num_clusters)
    dcsoc=cfg.get("dcsoc",{}); dcsoc_heads,_,_,_,_=assign_dcsoc_clusters(graph,eps=float(dcsoc.get("eps",2.0)),min_samples=int(dcsoc.get("min_samples",3)))
    candidates=sorted(set(graph.nodes())-set(structured_heads)-set(dcsoc_heads))
    if not candidates: raise RuntimeError("no peer is non-critical in both Structured and DC-SoC overlays")
    return candidates[0]

def load_jsonl(path):
    rows=[]; seen=set(); decoder=json.JSONDecoder()
    for number,line in enumerate(path.read_text().splitlines(),1):
        pending=line.strip()
        if not pending.startswith("{"): continue
        try:
            while pending:
                value,end=decoder.raw_decode(pending)
                if not isinstance(value,dict): raise ValueError
                identity=json.dumps(value,sort_keys=True,separators=(",",":"))
                if identity not in seen: rows.append(value); seen.add(identity)
                pending=pending[end:].lstrip()
        except (json.JSONDecodeError,ValueError) as error:
            raise ValueError(f"{path}:{number}: invalid JSON event") from error
    return rows

def write_config(base,out,algorithm,seed):
    if algorithm not in ALGORITHMS or seed not in SEEDS: raise ValueError("invalid Exp10 coordinate")
    cfg=yaml.safe_load(base.read_text()); cfg["experiment"]=f"k6_exp10_{algorithm}_seed{seed}"
    cfg["strategy"]=STRATEGIES[algorithm]; cfg["topology"]["seed"]=seed
    source=choose_exp10_source(cfg); cfg["messageSource"]=source
    cfg.pop("k5_exp10",None)
    cfg["k6_exp10"]={"algorithm":algorithm,"seed":seed,"failure":"pod_delete","recovery_definition":"survivor_full_delivery","source_selection":"lowest_id_not_structured_ch_or_dcsoc_core"}
    if algorithm=="dcsoc": cfg["dcsoc"]={"eps":2.0,"min_samples":3,"preserve_message_source":True,"dynamic_maintenance":True}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(yaml.safe_dump(cfg,sort_keys=False))

def validate_topologies(paths,expected_algorithms):
    observed=[]; physical=None; matched=None
    for path in paths:
        topo=json.loads(path.read_text()); meta=exp10_metadata(topo); algorithm=meta["algorithm"]; observed.append(algorithm)
        checks={"strategy":topo["strategy"]==STRATEGIES[algorithm],"BA/N":topo["topology_type"]=="ba" and topo["ba_m"]==2 and topo["num_nodes"]==20,
          "workload":topo["workload"]=={"message_count":20,"message_interval":0.4},"failure":topo["failure"]["mode"]=="exp10_pod_delete" and topo["failure"]["trigger_time"]==0.5,
          "settle":topo["settle_time"]==18.0,"S5":topo["k5_h2"]["actuator_treatment"]=="S5","maintenance isolation":bool(topo["dcsoc"]["dynamic_maintenance"])==(algorithm=="dcsoc")}
        failed=[name for name,ok in checks.items() if not ok]
        if failed: raise ValueError(f"{path}: contract failed: {failed}")
        target=choose_exp10_target(topo)
        if int(target["peer_id"])==int(topo["message_source"]): raise ValueError(f"{path}: failure target equals message source")
        scenario=(topo["message_source"],topo["workload"],topo["failure"]["trigger_time"],topo["num_nodes"],topo["topology_type"],topo["ba_m"],topo["settle_time"])
        if matched is not None and scenario!=matched: raise ValueError("matched Exp10 scenario inputs differ")
        matched=scenario
        current={k:v["neighbors"] for k,v in topo["nodes"].items()}
        if physical is not None and current!=physical: raise ValueError("matched physical topology differs")
        physical=current
    if tuple(observed)!=tuple(expected_algorithms): raise ValueError(f"treatment order mismatch: {observed}")

def validate_run(run_dir):
    required=("topology.json","logs.jsonl","controller.log","pods.json")
    missing=[n for n in required if not (run_dir/n).is_file()]
    if missing: raise ValueError(f"missing mandatory artifacts: {missing}")
    topo=json.loads((run_dir/"topology.json").read_text()); rows=load_jsonl(run_dir/"logs.jsonl"); meta=exp10_metadata(topo); algorithm=meta["algorithm"]
    selected=[r for r in rows if r.get("event")=="failure_target_selected"]; triggered=[r for r in rows if r.get("event")=="failure_triggered"]; unavailable=[r for r in rows if r.get("event")=="pod_unavailability_observed"]
    injected=[r for r in rows if r.get("event")=="message_injected"]
    if not(len(selected)==len(triggered)==len(unavailable)==1 and len(injected)==20): raise ValueError("failure/injection event count mismatch")
    target=int(selected[0]["peer_id"]); node=topo["nodes"][str(target)]
    if target==int(topo["message_source"]): raise ValueError("failure target equals message source")
    if target!=int(triggered[0]["target_peer"]) or target!=int(unavailable[0]["peer_id"]): raise ValueError("failure target mismatch")
    failure_ts=float(unavailable[0]["ts"])
    if float(triggered[0]["ts"])>=failure_ts: raise ValueError("unavailability timestamp ordering invalid")
    if int(selected[0]["degree"])!=len(node["neighbors"]): raise ValueError("target degree mismatch")
    if algorithm=="structured" and not node["is_cluster_head"]: raise ValueError("Structured target is not CH")
    if algorithm=="dcsoc" and node.get("dcsoc_role")!="core": raise ValueError("DC-SoC target is not CORE")
    maintenance=[r for r in rows if r.get("event")=="dcsoc_maintenance"]
    if algorithm=="dcsoc":
        if not maintenance: raise ValueError("DC-SoC maintenance missing")
        event=maintenance[0]
        if int(event["failed_node"])!=target or event["failed_role"]!="core" or target in event["surviving_candidate_set"]: raise ValueError("DC-SoC replacement contract failed")
        candidates=[int(x) for x in event["surviving_candidate_set"]]; expected=max(candidates,key=lambda x:(len(topo["nodes"][str(x)]["neighbors"]),-x)) if candidates else None
        if event.get("replacement_core")!=expected: raise ValueError("DC-SoC replacement selection failed")
        if float(event["maintenance_end"])<float(event["maintenance_start"]) or float(event["maintenance_duration"])<0: raise ValueError("maintenance time invalid")
    elif maintenance: raise ValueError(f"repair leaked into {algorithm}")
    traces=[r for r in rows if r.get("event")=="ahbn_controller_trace"]; decisions=[r for r in rows if r.get("event")=="k5_final_actuator_decision"]
    if algorithm=="ahbn" and(not traces or not decisions): raise ValueError("AHBN trace continuity missing")
    if algorithm!="ahbn" and(traces or decisions): raise ValueError("AHBN trace leaked")
    mids={r["message_id"] for r in injected}; received=[r for r in rows if r.get("event")=="received_new" and r.get("message_id") in mids]
    duplicates=[r for r in rows if r.get("event")=="received_duplicate" and r.get("message_id") in mids]; forwards=[r for r in rows if r.get("event")=="forward" and r.get("message_id") in mids]
    delivered={(r["message_id"],int(r["peer_id"])) for r in received}; delays=[]
    for mid in mids:
        starts=[float(r["ts"]) for r in injected if r["message_id"]==mid]; ends=[float(r["ts"]) for r in received if r["message_id"]==mid]
        if starts and ends: delays.append(max(ends)-min(starts))
    survivors=set(range(topo["num_nodes"]))-{target}; recovery=None
    for injection in sorted(injected,key=lambda r:float(r["ts"])):
        if float(injection["ts"])<failure_ts: continue
        rec=[r for r in received if r["message_id"]==injection["message_id"] and int(r["peer_id"]) in survivors]
        if {int(r["peer_id"]) for r in rec}==survivors:
            recovery={"message_id":injection["message_id"],"completion_ts":max(float(r["ts"]) for r in rec)}; break
    result={"run_id":topo["run_id"],"algorithm":algorithm,"seed":meta["seed"],"target_peer_id":target,"target_role":selected[0]["role"],"target_cluster":selected[0].get("cluster_id"),"target_degree":selected[0]["degree"],
      "failure_trigger_ts":float(triggered[0]["ts"]),"unavailability_ts":failure_ts,"delivery_ratio":len(delivered)/(topo["num_nodes"]*len(mids)),"propagation_delay":sum(delays)/len(delays) if delays else None,"duplicates":len(duplicates),"total_forwards":len(forwards),
      "recovered":recovery is not None,"recovery_time_s":recovery["completion_ts"]-failure_ts if recovery else None,"recovery_message_id":recovery["message_id"] if recovery else None,"unrecovered_censored_at_s":topo["settle_time"] if recovery is None else None,"core_replacement_count":max((int(r.get("core_replacement_count",0)) for r in maintenance),default=0)}
    (run_dir/"metrics.json").write_text(json.dumps(result,indent=2)+"\n"); (run_dir/"failure_events.json").write_text(json.dumps({"target":selected[0],"trigger":triggered[0],"unavailability":unavailable[0],"recovery":recovery},indent=2)+"\n")
    return result

def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="command",required=True)
    c=s.add_parser("config"); c.add_argument("--base",type=Path,required=True); c.add_argument("--out",type=Path,required=True); c.add_argument("--algorithm",choices=ALGORITHMS,required=True); c.add_argument("--seed",type=int,required=True)
    v=s.add_parser("contract"); v.add_argument("paths",nargs="+",type=Path)
    r=s.add_parser("run"); r.add_argument("--run-dir",type=Path,required=True)
    a=p.parse_args()
    if a.command=="config": write_config(a.base,a.out,a.algorithm,a.seed)
    elif a.command=="contract": validate_topologies(a.paths,ALGORITHMS)
    else: print(json.dumps(validate_run(a.run_dir),sort_keys=True))
if __name__=="__main__": main()
