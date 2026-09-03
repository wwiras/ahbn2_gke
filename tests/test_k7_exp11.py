from __future__ import annotations
import ast,hashlib,json,subprocess,sys
from pathlib import Path
import pytest,yaml
ROOT=Path(__file__).parents[1]; APP=ROOT/"app"; sys.path.insert(0,str(APP))
from ahbn_controller import AHBNState,CanonicalAHBNController
from dcsoc_maintenance import DCSOCMaintenance
from k6_final_actuator_policy import requested_fanout as k6_fanout
from k7_final_actuator_policy import requested_fanout as k7_fanout
from k7_exp11_tools import ALGORITHMS,PLANNED_LEAVE_OFFSETS_S,SEEDS,active_at,load_jsonl,planned_wait_seconds,validate_churn_timeline,validate_topologies,write_config

K5={"ahbn_controller.py":"dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8","peer.py":"64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a","k5_final_actuator_policy.py":"8c7a0658cd226d0349e3ed3c64c943887196fdee57d9ef06874fd8525b683cff","k5_final_actuator_runtime.py":"1d95271079064b6c159fcb9d7b553c03cc8b6cb42893f1b8e92bf8f4b6e95a25"}
K6={"app/k6_controller.py":"e9f60e6b796977dad43fbee7319b0bc901b95f962d5c5337a355c39a68f29289","app/k6_final_actuator_policy.py":"b39078e45774bb0535fce267dccad43b17e64721726ecb8c340b85eb30d33bf6","app/k6_final_actuator_runtime.py":"9a81f6d14aa80ebd1250c2b85d9e3635625c24cf35194e39da1965cbc227d5d9","app/k6_exp10_tools.py":"c136284615f35df9853904a462b2a5523f1f6a424cb07316f1a576852aa6c85e","scripts/run_k6_exp10.sh":"8d985588ee5e7e72820d355c6625cb634ae1ec48a610357038b113a951464b7b","scripts/k6_exp10_analysis.py":"411a8225d626222e672075b129221b2afd7954382953be8dc3e8d53f493691f0","experiments/k6_exp10.yaml":"1f7460c6242c98065e021120128d4d37ec5d5f75de4c367ce0bdb5f064868d82","tests/test_k6_exp10.py":"f9fd1db863692c401ce1233284d521a3c28c61f095bbdd166b78386a178d0575","app/Dockerfile.k6_exp10":"dbf091f5e4d1af3b1b7875cddae8749fdcdc4ef2524ecd6760283da93bcefaff","scripts/build_k6_exp10_image.sh":"cc7536dafb19009115b3680e8dd43b5e6f1ed9ff7d6f31bac56e2a2391c08bd4"}

def test_frozen_hashes():
    for f,h in K5.items(): assert hashlib.sha256((APP/f).read_bytes()).hexdigest()==h
    for f,h in K6.items(): assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h

@pytest.mark.parametrize("z",[-1,-.25,-.249999,0,.249999,.25,.899999,.9,1.499999,1.5,2])
@pytest.mark.parametrize("treatment",["S0","S5"])
def test_policy_parity(z,treatment): assert k7_fanout(treatment,z)==k6_fanout(treatment,z)

def normalized(path,stage):
    tree=ast.parse(path.read_text());
    if tree.body and isinstance(tree.body[0],ast.Expr): tree.body.pop(0)
    class N(ast.NodeTransformer):
        def visit_ImportFrom(self,node):
            if node.module==f"{stage}_final_actuator_policy": node.module="policy"
            return node
    return ast.dump(N().visit(tree),include_attributes=False)

def test_runtime_semantic_parity():
    k6=(APP/"k6_final_actuator_runtime.py").read_text(); k7=(APP/"k7_final_actuator_runtime.py").read_text()
    for token in ("self.adaptive_update()","self.ahbn_state.score","self.cluster_targets", "self.rng.sample", "requested_fanout(TREATMENT, score)", 'event="k5_final_actuator_decision"', "self.log_ahbn_forwarding_decision"):
        assert token in k6 and token in k7

def test_controller_equation_and_no_override():
    d=CanonicalAHBNController().update(AHBNState(),.2,.7,.6,.4); assert d.score==pytest.approx(-d.d_hat+d.l_hat+d.u_hat+d.c_hat)
    text=(APP/"k7_controller.py").read_text(); assert "requested_fanout" not in text and "fanout" not in text

def test_all_seed_contracts(tmp_path):
    assert ALGORITHMS==("gossip","structured","dcsoc","ahbn")
    for seed in SEEDS:
        paths=[]; schedules=[]
        for a in ALGORITHMS:
            cfg=tmp_path/f"{a}{seed}.yaml"; topo=tmp_path/f"{a}{seed}.json"; write_config(ROOT/"experiments/k7_exp11.yaml",cfg,a,seed)
            subprocess.run([sys.executable,str(APP/"k7_gen_topology.py"),"--config",str(cfg),"--out",str(topo)],check=True); paths.append(topo)
            t=json.loads(topo.read_text()); schedule=t["k7_exp11"]["planned_churn_schedule"]
            assert len(schedule)==4 and len({x["target_peer"] for x in schedule})==4 and t["message_source"] not in {x["target_peer"] for x in schedule}
            assert tuple(x["planned_leave_offset_s"] for x in schedule)==PLANNED_LEAVE_OFFSETS_S
            assert all(x["recovery_action"] for x in schedule)
            schedules.append([(x["target_peer"],x["planned_leave_offset_s"]) for x in schedule])
        assert all(schedule==schedules[0] for schedule in schedules)
        validate_topologies(paths)

def test_schedule_is_fixed_and_recovery_independent():
    assert PLANNED_LEAVE_OFFSETS_S==(1.0,8.0,15.0,22.0)
    assert planned_wait_seconds(100.0,8.0,103.0,True)==5.0
    assert planned_wait_seconds(100.0,8.0,107.5,True)==.5

def test_unresolved_or_missed_cycle_fails_closed():
    with pytest.raises(RuntimeError,match="unresolved"):
        planned_wait_seconds(100.0,8.0,103.0,False)
    with pytest.raises(RuntimeError,match="deadline missed"):
        planned_wait_seconds(100.0,8.0,108.001,True)
    controller=(APP/"k7_controller.py").read_text()
    assert 'time.sleep(float(topo["failure"]["interval_sec"]))' not in controller
    for field in ("planned_leave_time","actual_delete_time","unavailable_time","recovery_ready_time","grpc_alive_time"):
        assert field in controller

def timeline_fixture(*, injected_count=80, final_delete_elapsed=22.1, missing_event=False):
    schedule=[{"event_index":i,"target_peer":target,"planned_leave_offset_s":offset}
              for i,(target,offset) in enumerate(zip((0,5,10,15),PLANNED_LEAVE_OFFSETS_S),1)]
    topo={"message_source":1,"k7_exp11":{"planned_churn_schedule":schedule}}
    rows=[{"event":"message_injected","message_id":f"m{i+1}","ts":10000+i*.4,
           "workload_elapsed_s":i*.4} for i in range(injected_count)]
    count=3 if missing_event else 4
    for i,(target,offset) in enumerate(zip((0,5,10,15),PLANNED_LEAVE_OFFSETS_S),1):
        if i>count: break
        planned=100+offset; actual=(final_delete_elapsed if i==4 else offset+.1)
        rows.extend([
            {"event":"churn_leave_scheduled","event_index":i,"target_peer":target,"planned_leave_time":planned,"ts":planned},
            {"event":"pod_unavailability_observed","event_index":i,"target_peer":target,"original_pod_uid":f"old-{i}","ts":planned+.2},
            {"event":"churn_rejoined","event_index":i,"target_peer":target,"planned_leave_time":planned,
             "actual_delete_time":planned+.1,"actual_delete_workload_elapsed_s":actual,
             "unavailable_time":planned+.2,"recovery_ready_time":planned+.8,"grpc_alive_time":planned+.9,
             "replacement_pod_uid":f"new-{i}","ts":planned+.9},
        ])
    return topo,rows

def test_validator_accepts_fixed_churn_during_80_message_workload_with_different_raw_origins():
    topo,rows=timeline_fixture()
    result=validate_churn_timeline(topo,rows)
    assert result["injected_count"]==80
    assert result["delete_elapsed_s"]==pytest.approx([1.1,8.1,15.1,22.1])
    assert result["workload_duration_s"]==pytest.approx(31.6)

def test_validator_rejects_genuine_churn_after_dissemination():
    topo,rows=timeline_fixture(final_delete_elapsed=32.0)
    with pytest.raises(ValueError,match=r"last churn workload_elapsed=32.00 s, last injection workload_elapsed=31.60 s"):
        validate_churn_timeline(topo,rows)

def test_validator_rejects_fewer_than_80_injections():
    topo,rows=timeline_fixture(injected_count=79)
    with pytest.raises(ValueError,match="injected_count invalid: expected=80 observed=79"):
        validate_churn_timeline(topo,rows)

def test_validator_rejects_missing_churn_event():
    topo,rows=timeline_fixture(missing_event=True)
    with pytest.raises(ValueError,match="leaves=3 unavailable=3 rejoined=3"):
        validate_churn_timeline(topo,rows)

def test_combined_stream_and_snapshot_events_are_deduplicated(tmp_path):
    event={"event":"message_injected","message_id":"m1","ts":123.0}
    path=tmp_path/"logs.jsonl"; path.write_text(json.dumps(event)+"\n"+json.dumps(event)+"\n")
    assert load_jsonl(path)==[event]

def test_dcsoc_leave_rejoin_and_periodic_du(tmp_path):
    cfg=tmp_path/"d.yaml"; topo=tmp_path/"d.json"; write_config(ROOT/"experiments/k7_exp11.yaml",cfg,"dcsoc",42); subprocess.run([sys.executable,str(APP/"k7_gen_topology.py"),"--config",str(cfg),"--out",str(topo)],check=True)
    t=json.loads(topo.read_text()); m=DCSOCMaintenance(t); core=next(x["target_peer"] for x in t["k7_exp11"]["planned_churn_schedule"] if x["target_role"]=="CORE")
    before=m.core_replacement_count; assert m.set_availability(core,False); assert m.core_replacement_count==before+1; assert m.set_availability(core,True); assert m.rejoin_assignment_count==1; m.explicit_du(reason="k7_fixed_schedule"); assert m.recluster_count==1 and all(e["maintenance_duration"]>=0 for e in m.events)
    tail=next(i for i,n in m.nodes.items() if n["dcsoc_role"]=="leaf" and m.active[i]); before=m.core_replacement_count; m.set_availability(tail,False); assert m.core_replacement_count==before

def test_active_denominator_and_censor_contract():
    events=[{"event":"churn_down","target_peer":3,"ts":2},{"event":"churn_rejoined","target_peer":3,"ts":5}]
    assert active_at(3,1,events) and not active_at(3,3,events) and active_at(3,6,events)
    assert "censored_at_s" in (APP/"k7_exp11_tools.py").read_text()

def test_stage_packaging_and_runner():
    docker=(APP/"Dockerfile.k7_exp11").read_text(); runner=(ROOT/"scripts/run_k7_exp11.sh").read_text()
    assert 'CMD ["python", "k7_final_actuator_runtime.py"]' in docker and "k7_controller.py" in docker
    assert "ahbn-k7-exp11" in runner and "outputs/k7_exp11_smoke-" in runner and "immutable_hashes_before" in runner
    assert "--resume RESULT_ROOT" in runner and "existing Gossip image provenance invalid" in runner
    assert "existing run topology differs from regenerated frozen contract" in runner
    assert "SKIP VALID COMPLETE RUN" in runner and "app/k7_exp11_tools.py run --run-dir" in runner
