import inspect, json, sys
from pathlib import Path
import networkx as nx
import pytest

ROOT=Path(__file__).parents[1]; APP=ROOT/"app"; sys.path.insert(0,str(APP))
from dcsoc_maintenance import DCSOCMaintenance
from gen_topology import assign_dcsoc_clusters
from k5_exp10_tools import ALGORITHMS, choose_exp10_source, choose_exp10_target, validate_run, validate_topologies, write_config

def topology(strategy="cluster"):
    nodes={str(i):{"neighbors":n,"cluster_id":c,"is_cluster_head":h,"cluster_head_id":head,"cluster_members":members,"gateway_neighbors":[]}
      for i,(n,c,h,head,members) in enumerate([([1,2],0,True,0,[1,2]),([0,2],0,False,0,[0,2]),([0,1,3],0,False,0,[0,1]),([2],1,True,3,[])])}
    return {"strategy":strategy,"message_source":0,"nodes":nodes}

def test_target_is_highest_degree_native_structural_peer():
    selected=choose_exp10_target(topology())
    assert selected=={"peer_id":3,"role":"CH","cluster_id":1,"degree":1,"selection_basis":"highest-degree realized non-source Structured CH"}
    assert selected["peer_id"]!=topology()["message_source"]

def test_unstructured_target_uses_degree_then_lowest_id():
    selected=choose_exp10_target(topology("gossip"))
    assert selected["peer_id"]==2
    assert selected["peer_id"]!=topology("gossip")["message_source"]

def test_non_source_degree_tie_uses_lowest_node_id():
    topo=topology("ahbn"); topo["nodes"]["1"]["neighbors"]=[0,2,3]
    assert choose_exp10_target(topo)["peer_id"]==1

def test_dcsoc_stops_when_source_is_only_core():
    topo=topology("dcsoc")
    for node in topo["nodes"].values(): node["dcsoc_role"]="leaf"
    topo["nodes"]["0"]["dcsoc_role"]="core"
    with pytest.raises(RuntimeError,match="no valid non-source Exp10 critical target"):
        choose_exp10_target(topo)

def dcsoc_fixture():
    graph=nx.Graph([(0,1),(0,2),(1,2),(2,3),(2,4),(3,4)])
    heads,clusters,members,roles,edges=assign_dcsoc_clusters(graph,eps=1,min_samples=2)
    nodes={str(i):{"neighbors":sorted(graph.neighbors(i)),"cluster_id":clusters[i],"is_cluster_head":i in heads,"cluster_head_id":heads[clusters[i]],"cluster_members":[x for x in members[clusters[i]] if x!=i],"gateway_neighbors":[],**roles[i]} for i in graph}
    return {"strategy":"dcsoc","nodes":nodes,"dcsoc":{"eps":1,"min_samples":2,"structural_edges":edges}}

def test_dcsoc_replacement_contract_and_derived_timing():
    topo=dcsoc_fixture(); maintenance=DCSOCMaintenance(topo)
    failed=next(int(k) for k,v in topo["nodes"].items() if v["dcsoc_role"]=="core")
    maintenance.set_availability(failed,False,reason="test"); event=maintenance.events[-1]
    assert failed not in event["surviving_candidate_set"]
    candidates=event["surviving_candidate_set"]
    expected=max(candidates,key=lambda i:(len(topo["nodes"][str(i)]["neighbors"]),-i))
    assert event["replacement_core"]==expected
    assert event["replacement_degree"]==len(topo["nodes"][str(expected)]["neighbors"])
    assert event["maintenance_end"]>=event["maintenance_start"] and event["maintenance_duration"]>=0
    snap=maintenance.snapshot(); assert snap["nodes"][expected]["dcsoc_role"]=="core"
    assert all(failed not in edge for edge in snap["structural_edges"])

def test_comparators_do_not_receive_repair_or_hardwired_ahbn():
    source=(APP/"controller.py").read_text().split("def run_exp10_failure",1)[1].split("\ndef ",1)[0]
    assert 'topo.get("strategy") == "dcsoc"' in source
    assert "mode =" not in source and "fanout =" not in source and "FailStop" not in source

def test_all_formal_seed_contracts_are_matched_and_have_valid_targets(tmp_path):
    import subprocess
    for seed in range(42,47):
        paths=[]; sources=[]
        for algorithm in ALGORITHMS:
            config=tmp_path/f"{algorithm}_{seed}.yaml"; generated=tmp_path/f"{algorithm}_{seed}.json"
            write_config(ROOT/"experiments/exp10.yaml",config,algorithm,seed)
            subprocess.run([sys.executable,str(APP/"gen_topology.py"),"--config",str(config),"--out",str(generated)],check=True)
            topo=json.loads(generated.read_text()); sources.append(topo["message_source"])
            assert choose_exp10_target(topo)["peer_id"]!=topo["message_source"]
            if algorithm=="structured": assert any(int(k)!=topo["message_source"] and v["is_cluster_head"] for k,v in topo["nodes"].items())
            if algorithm=="dcsoc": assert any(int(k)!=topo["message_source"] and v["dcsoc_role"]=="core" for k,v in topo["nodes"].items())
            paths.append(generated)
        assert len(set(sources))==1
        validate_topologies(paths,ALGORITHMS)

def test_source_selection_is_deterministic_and_noncritical():
    cfg=__import__("yaml").safe_load((ROOT/"experiments/exp10.yaml").read_text()); cfg["topology"]["seed"]=42
    assert choose_exp10_source(cfg)==choose_exp10_source(cfg)==1

def test_no_synthetic_reconstruction_penalty():
    source=(APP/"dcsoc_maintenance.py").read_text()
    assert "reconstruction_penalty" not in source and "result_delay" not in source

def test_recovery_is_first_full_survivor_delivery_and_can_be_censored(tmp_path):
    run=tmp_path/"run"; run.mkdir()
    topo={"run_id":"x","num_nodes":3,"message_source":0,"settle_time":18.0,"strategy":"gossip",
      "k5_exp10":{"algorithm":"gossip","seed":42},"nodes":{
       "0":{"neighbors":[1,2],"cluster_id":0,"is_cluster_head":True},
       "1":{"neighbors":[0],"cluster_id":0,"is_cluster_head":False},
       "2":{"neighbors":[0],"cluster_id":0,"is_cluster_head":False}}}
    (run/"topology.json").write_text(json.dumps(topo)); (run/"controller.log").write_text("{}"); (run/"pods.json").write_text('{"items":[]}')
    events=[{"event":"failure_target_selected","peer_id":1,"role":"critical forwarding peer","cluster_id":0,"degree":1,"ts":1.0},
      {"event":"failure_triggered","target_peer":1,"ts":1.1},{"event":"pod_unavailability_observed","peer_id":1,"ts":1.2}]
    events += [{"event":"message_injected","message_id":f"m{i}","ts":0.5+i} for i in range(1,21)]
    events += [{"event":"received_new","message_id":"m2","peer_id":0,"ts":2.2},{"event":"received_new","message_id":"m2","peer_id":2,"ts":2.5}]
    (run/"logs.jsonl").write_text("\n".join(json.dumps(e) for e in events)+"\n")
    result=validate_run(run)
    assert result["recovered"] and result["recovery_message_id"]=="m2"
    assert result["recovery_time_s"]==pytest.approx(1.3)
    (run/"logs.jsonl").write_text("\n".join(json.dumps(e) for e in events[:-1])+"\n")
    result=validate_run(run)
    assert not result["recovered"] and result["recovery_time_s"] is None

def test_canonical_files_are_unchanged():
    import hashlib
    hashes={"ahbn_controller.py":"dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8","peer.py":"64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a"}
    for name,expected in hashes.items(): assert hashlib.sha256((APP/name).read_bytes()).hexdigest()==expected

def test_runner_fails_closed_and_does_not_execute_by_itself():
    runner=(ROOT/"scripts/run_k5_exp10.sh").read_text()
    assert "set -Eeuo pipefail" in runner and "tests/test_k5_exp10.py" in runner
    assert "CAPTURE_STREAM=1" in runner and "kubectl config current-context" in runner
