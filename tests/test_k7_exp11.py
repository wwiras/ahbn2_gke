from __future__ import annotations
import ast,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
from types import ModuleType,SimpleNamespace
from unittest import mock
import pytest,yaml
ROOT=Path(__file__).parents[1]; APP=ROOT/"app"; sys.path.insert(0,str(APP))
from ahbn_controller import AHBNState,CanonicalAHBNController
from dcsoc_maintenance import DCSOCMaintenance
from k6_final_actuator_policy import requested_fanout as k6_fanout
from k7_final_actuator_policy import requested_fanout as k7_fanout
from k7_rpc_trace import apply_with_trace
from k7_exp11_tools import ALGORITHMS,FEASIBILITY_LEAVE_OFFSETS_S,FEASIBILITY_MESSAGE_COUNT,PLANNED_LEAVE_OFFSETS_S,SEEDS,active_at,load_jsonl,planned_wait_seconds,validate_churn_timeline,validate_feasibility_topology,validate_topologies,write_config

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
    assert "k7_rpc_trace.py" in docker and "k7_rpc_trace.install(peer)" in (APP/"k7_final_actuator_runtime.py").read_text()

def feasibility_topology(tmp_path):
    cfg=tmp_path/"gate.yaml"; topo=tmp_path/"topology.json"
    write_config(ROOT/"experiments/k7_exp11.yaml",cfg,"dcsoc",42,True)
    subprocess.run([sys.executable,str(APP/"k7_gen_topology.py"),"--config",str(cfg),"--out",str(topo)],check=True)
    return topo

def test_feasibility_contract_is_dcsoc_seed42_only_and_does_not_mutate_formal(tmp_path):
    topo=feasibility_topology(tmp_path); validate_feasibility_topology(topo); t=json.loads(topo.read_text())
    assert t["workload"]=={"message_count":FEASIBILITY_MESSAGE_COUNT,"message_interval":.4}
    assert tuple(e["planned_leave_offset_s"] for e in t["k7_exp11"]["planned_churn_schedule"])==FEASIBILITY_LEAVE_OFFSETS_S
    assert [e["target_peer"] for e in t["k7_exp11"]["planned_churn_schedule"]]==[0,5,10,15]
    assert t["message_source"] not in {0,5,10,15}
    for algorithm in ("gossip","structured","ahbn"):
        with pytest.raises(ValueError,match="DC-SoC seed42 only"): write_config(ROOT/"experiments/k7_exp11.yaml",tmp_path/f"{algorithm}.yaml",algorithm,42,True)
    normal=tmp_path/"normal.yaml"; write_config(ROOT/"experiments/k7_exp11.yaml",normal,"dcsoc",42)
    assert yaml.safe_load(normal.read_text())["workload"]["messageCount"]==80
    assert tuple(yaml.safe_load(normal.read_text())["k7_exp11"]["plannedLeaveOffsetsSec"])==PLANNED_LEAVE_OFFSETS_S

def test_feasibility_runner_is_isolated_and_fixed_deadline_fail_closed():
    runner=(ROOT/"scripts/run_k7_exp11.sh").read_text(); controller=(APP/"k7_controller.py").read_text()
    assert "algorithms=(dcsoc)" in runner and "outputs/k7_dcsoc_feas25-" in runner
    assert "FEASIBILITY-ONLY / NOT EXP11 RESULT" in (APP/"k7_exp11_tools.py").read_text()
    assert "planned_wait_seconds" in controller and "recovery completed" not in controller
    assert all(token in controller for token in ("replacement_uid_observed_time","recovery_ready_time","grpc_alive_time","leave_maintenance_start","rejoin_maintenance_start","explicit_du_start","expected_acknowledgement_count","FAIL_TIMEOUT","FAIL_DEADLINE","FAIL_INFRA","FAIL_MAINTENANCE"))
    assert "bind_replacement_ip=feasibility" in controller and "elif topo[\"strategy\"]==\"dcsoc\"" in controller

def gate_analyzer():
    spec=importlib.util.spec_from_file_location("gate_analysis",ROOT/"scripts/k7_dcsoc_feasibility_analysis.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def gate_controller():
    name="gate_controller_test"
    if name in sys.modules and hasattr(sys.modules[name],"controller"): return sys.modules[name]
    sys.modules.pop(name,None)
    class RpcError(Exception): pass
    class Code:
        def __init__(self,name): self.name=name
    grpc=SimpleNamespace(RpcError=RpcError,StatusCode=SimpleNamespace(DEADLINE_EXCEEDED=Code("DEADLINE_EXCEEDED"),UNAVAILABLE=Code("UNAVAILABLE")),insecure_channel=None)
    shared_controller=SimpleNamespace(grpc=grpc,peer_addr=lambda peer,svc,ns,port:f"peer-{peer}.{svc}.{ns}.svc.cluster.local:{port}",peer_pb2=SimpleNamespace(Empty=lambda:object(),DCSOCMaintenanceRequest=lambda **kwargs:kwargs),peer_pb2_grpc=SimpleNamespace(PeerServiceStub=None),now=lambda:0.0,log_event=lambda **kwargs:None,run_churn=None,main=lambda:None)
    sys.modules["controller_shared"]=shared_controller
    kubernetes=ModuleType("kubernetes"); kubernetes.client=SimpleNamespace(); kubernetes.config=SimpleNamespace()
    client_module=ModuleType("kubernetes.client"); rest_module=ModuleType("kubernetes.client.rest"); rest_module.ApiException=type("ApiException",(Exception,),{})
    sys.modules["kubernetes"]=kubernetes; sys.modules["kubernetes.client"]=client_module; sys.modules["kubernetes.client.rest"]=rest_module
    spec=importlib.util.spec_from_file_location(name,APP/"k7_controller.py"); module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module); return module

def test_replacement_target_address_is_ip_bound_and_survivors_keep_dns():
    module=gate_controller()
    assert module._peer_destination(0,0,"10.16.3.7","ahbn-peer","ns",50051)=="10.16.3.7:50051"
    assert module._peer_destination(1,0,"10.16.3.7","ahbn-peer","ns",50051)=="peer-1.ahbn-peer.ns.svc.cluster.local:50051"

def test_changed_replacement_uid_resolves_to_its_pod_ip():
    module=gate_controller(); replacement=SimpleNamespace(metadata=SimpleNamespace(uid="new-uid"),status=SimpleNamespace(pod_ip="10.16.3.7"))
    assert module._replacement_identity(replacement,"old-uid")==("new-uid","10.16.3.7")
    assert module._replacement_identity(replacement,"new-uid") is None

def test_direct_replacement_readiness_uses_pod_ip():
    module=gate_controller(); addresses=[]
    class Channel:
        def __init__(self,address): addresses.append(address)
        def __enter__(self): return self
        def __exit__(self,*args): pass
    stub=SimpleNamespace(GetStatus=lambda request,timeout:SimpleNamespace(ready=True))
    with mock.patch.object(module.controller.grpc,"insecure_channel",side_effect=Channel),mock.patch.object(module.controller.peer_pb2_grpc,"PeerServiceStub",return_value=stub):
        assert module._direct_replacement_status("10.16.3.7",50051).ready
    assert addresses==["10.16.3.7:50051"]

@pytest.mark.parametrize("phase,rpc_fields",[("leave",{"node_id":0,"available":False}),("rejoin",{"node_id":0,"available":True}),("explicit_du",{"explicit_du":True})])
def test_all_twenty_acks_required_with_ip_bound_target_for_every_phase(phase,rpc_fields):
    module=gate_controller(); addresses=[]
    class Channel:
        def __init__(self,address): self.address=address; addresses.append(address)
        def __enter__(self): return self
        def __exit__(self,*args): pass
    class Stub:
        def __init__(self,channel): self.channel=channel
        def ApplyDCSOCMaintenance(self,request,timeout,metadata=None): return SimpleNamespace(ok=True,message="maintenance applied")
    topo={"nodes":{str(i):{} for i in range(20)}}
    with mock.patch.object(module.controller.grpc,"insecure_channel",side_effect=Channel),mock.patch.object(module.controller.peer_pb2_grpc,"PeerServiceStub",side_effect=Stub),mock.patch.object(module.controller,"log_event"):
        result=module._maintenance_phase(topo,0,1,phase,"ahbn-peer","ns",50051,"10.16.3.7",**rpc_fields)
    assert result["acknowledgement_count"]==result["expected_acknowledgement_count"]==20
    assert addresses[0]=="10.16.3.7:50051" and addresses[1]=="peer-1.ahbn-peer.ns.svc.cluster.local:50051"

def test_target_unavailable_remains_a_required_ack_failure():
    module=gate_controller()
    class Unavailable(module.controller.grpc.RpcError):
        def code(self): return module.controller.grpc.StatusCode.UNAVAILABLE
    class Channel:
        def __init__(self,address): self.address=address
        def __enter__(self): return self
        def __exit__(self,*args): pass
    class Stub:
        def __init__(self,channel): self.channel=channel
        def ApplyDCSOCMaintenance(self,request,timeout,metadata=None):
            if self.channel.address=="10.16.3.7:50051": raise Unavailable()
            return SimpleNamespace(ok=True,message="maintenance applied")
    topo={"nodes":{str(i):{} for i in range(20)}}
    with mock.patch.object(module.controller.grpc,"insecure_channel",side_effect=Channel),mock.patch.object(module.controller.peer_pb2_grpc,"PeerServiceStub",side_effect=Stub),mock.patch.object(module.controller,"log_event"):
        result=module._maintenance_phase(topo,0,1,"leave","ahbn-peer","ns",50051,"10.16.3.7",node_id=0,available=False)
    assert result["expected_acknowledgement_count"]==20 and result["acknowledgement_count"]==19
    assert result["failed_peer_ids"]==[0] and result["rpc_unavailable_count"]==1

def test_every_feasibility_rpc_has_unique_correlation_and_complete_client_trace():
    module=gate_controller(); calls=[]; logs=[]; ticks=iter(float(i) for i in range(100))
    class Channel:
        def __init__(self,address): self.address=address
        def __enter__(self): return self
        def __exit__(self,*args): pass
    class Stub:
        def __init__(self,channel): self.channel=channel
        def ApplyDCSOCMaintenance(self,request,timeout,metadata=None):
            calls.append((self.channel.address,timeout,metadata)); return SimpleNamespace(ok=True,message="ok")
    topo={"nodes":{str(i):{} for i in range(3)}}
    with mock.patch.object(module.controller.grpc,"insecure_channel",side_effect=Channel),mock.patch.object(module.controller.peer_pb2_grpc,"PeerServiceStub",side_effect=Stub),mock.patch.object(module.controller,"now",side_effect=lambda:next(ticks)),mock.patch.object(module.controller,"log_event",side_effect=lambda **row:logs.append(row)):
        module._maintenance_phase(topo,1,2,"leave","ahbn-peer","ns",50051,"10.0.0.2",node_id=1,available=False)
    rpc_logs=[row for row in logs if row["event"]=="k7_feasibility_maintenance_rpc"]
    ids=[row["request_id"] for row in rpc_logs]
    assert ids==["k7-feas-event2-leave-peer0","k7-feas-event2-leave-peer1","k7-feas-event2-leave-peer2"]
    assert len(set(ids))==3 and [call[2][0][1] for call in calls]==ids
    assert all(call[1]==3 for call in calls)
    required={"rpc_start_time","rpc_end_time","rpc_elapsed_s","destination_endpoint","addressing_type","rpc_deadline_s","final_status","rpc_code","affected_peer","destination_peer","destination_is_target"}
    assert all(required<=row.keys() and row["final_status"]=="ACK" for row in rpc_logs)
    assert rpc_logs[1]["addressing_type"]=="replacement_pod_ip"
    assert rpc_logs[0]["addressing_type"]==rpc_logs[2]["addressing_type"]=="statefulset_dns"

def test_server_trace_records_operation_boundaries_and_missing_id_is_backward_compatible():
    events=[]; calls=[]; ticks=iter(float(i) for i in range(20))
    class Maintenance:
        events=[]; core_replacement_count=0; recluster_count=0; rejoin_assignment_count=0
        def set_availability(self,node_id,available,reason): calls.append(("set",node_id,available,reason)); return True
        def sync_peer(self,state): calls.append(("sync",state.peer_id))
    state=SimpleNamespace(dcsoc_maintenance=Maintenance(),peer_id=7,run_id="run",experiment="k7",_k7_peer_pb2=SimpleNamespace(Ack=lambda **kwargs:SimpleNamespace(**kwargs)))
    service=SimpleNamespace(state=state)
    request=SimpleNamespace(node_id=5,available=False,explicit_du=False,reason="k7_event_2_leave")
    metadata=[SimpleNamespace(key="x-k7-request-id",value="k7-feas-event2-leave-peer7")]
    context=SimpleNamespace(invocation_metadata=lambda:metadata)
    original=mock.Mock(return_value=SimpleNamespace(ok=False))
    reply=apply_with_trace(service,request,context,original,log_event=lambda **row:events.append(row),now=lambda:next(ticks))
    assert reply.ok and calls==[("set",5,False,"k7_event_2_leave"),("sync",7)] and not original.called
    assert [row["event"] for row in events]==["k7_dcsoc_rpc_handler_entry","k7_dcsoc_rpc_before_set_availability","k7_dcsoc_rpc_after_set_availability","k7_dcsoc_rpc_before_sync_peer","k7_dcsoc_rpc_after_sync_peer","k7_dcsoc_rpc_handler_exit"]
    assert all(row["request_id"]=="k7-feas-event2-leave-peer7" and row["affected_peer"]==5 and row["receiving_peer"]==7 for row in events)
    no_metadata=SimpleNamespace(invocation_metadata=lambda:[])
    apply_with_trace(service,request,no_metadata,original,log_event=lambda **row:None,now=lambda:0)
    original.assert_called_once_with(request,no_metadata)

def test_server_trace_explicit_du_preserves_action_and_sync_semantics():
    calls=[]; events=[]
    maintenance=SimpleNamespace(events=[],core_replacement_count=0,recluster_count=0,rejoin_assignment_count=0,explicit_du=lambda reason:calls.append(("du",reason)),sync_peer=lambda state:calls.append(("sync",state.peer_id)))
    state=SimpleNamespace(dcsoc_maintenance=maintenance,peer_id=3,run_id="run",experiment="k7",_k7_peer_pb2=SimpleNamespace(Ack=lambda **kwargs:SimpleNamespace(**kwargs)))
    request=SimpleNamespace(node_id=0,available=False,explicit_du=True,reason="periodic_du")
    context=SimpleNamespace(invocation_metadata=lambda:[SimpleNamespace(key="x-k7-request-id",value="du-id")])
    reply=apply_with_trace(SimpleNamespace(state=state),request,context,mock.Mock(),log_event=lambda **row:events.append(row),now=lambda:1.0)
    assert reply.ok and calls==[("du","periodic_du"),("sync",3)]
    assert all(row["phase"]=="explicit_du" for row in events)

def test_deadline_exceeded_remains_strict_failure_and_is_traced():
    module=gate_controller(); logs=[]
    class Deadline(module.controller.grpc.RpcError):
        def code(self): return module.controller.grpc.StatusCode.DEADLINE_EXCEEDED
        def details(self): return "deadline diagnostic"
    class Channel:
        def __init__(self,address): self.address=address
        def __enter__(self): return self
        def __exit__(self,*args): pass
    class Stub:
        def __init__(self,channel): pass
        def ApplyDCSOCMaintenance(self,request,timeout,metadata=None): raise Deadline()
    topo={"nodes":{"0":{}}}
    with mock.patch.object(module.controller.grpc,"insecure_channel",side_effect=Channel),mock.patch.object(module.controller.peer_pb2_grpc,"PeerServiceStub",side_effect=Stub),mock.patch.object(module.controller,"log_event",side_effect=lambda **row:logs.append(row)):
        result=module._maintenance_phase(topo,0,2,"leave","ahbn-peer","ns",50051,"10.0.0.1",node_id=0,available=False)
    trace=next(row for row in logs if row["event"]=="k7_feasibility_maintenance_rpc")
    assert result["acknowledgement_count"]==0 and result["failed_peer_ids"]==[0] and result["rpc_timeout_count"]==1
    assert trace["final_status"]==trace["rpc_code"]=="DEADLINE_EXCEEDED" and trace["rpc_details"]=="deadline diagnostic"

def test_analyzer_correlates_client_and_server_diagnostics_without_root_cause_inference():
    rows=[
        {"event":"k7_feasibility_maintenance_rpc","request_id":"id","event_index":2,"phase":"leave","destination_peer":0,"final_status":"DEADLINE_EXCEEDED","rpc_code":"DEADLINE_EXCEEDED"},
        {"event":"k7_dcsoc_rpc_handler_entry","request_id":"id","handler_entry_time":10.0},
        {"event":"k7_dcsoc_rpc_before_set_availability","request_id":"id","before_set_availability_time":10.1},
        {"event":"k7_dcsoc_rpc_after_set_availability","request_id":"id","after_set_availability_time":10.2},
        {"event":"k7_dcsoc_rpc_before_sync_peer","request_id":"id","before_sync_peer_time":10.3},
    ]
    failure=gate_analyzer().diagnostic_failures(rows)[0]
    assert failure["server_entry_present"] and failure["entry_to_operation_s"]==pytest.approx(.1)
    assert failure["set_availability_s"]==pytest.approx(.1)
    assert failure["sync_peer_s"] is None and not failure["handler_exit_present"]

def write_gate_fixture(tmp_path,cycle_count=4):
    root=tmp_path/"out"; run=root/"runs/seed42/dcsoc"; run.mkdir(parents=True); topo=feasibility_topology(tmp_path); (run/"topology.json").write_text(topo.read_text())
    rows=[{"event":"message_injected","message_id":f"m{i}","ts":1000+i*.4} for i in range(240)]
    for i,(target,offset) in enumerate(zip((0,5,10,15),FEASIBILITY_LEAVE_OFFSETS_S),1):
        if i>cycle_count: break
        completion=1000+offset+2
        rows.append({"event":"k7_dcsoc_feasibility_cycle","event_index":i,"target_peer":target,"cycle_status":"PASS","planned_leave_time":1000+offset,"actual_delete_time":1000+offset+.1,"unavailable_time":1000+offset+.2,"replacement_uid_observed_time":1000+offset+.5,"replacement_pod_ip":f"10.0.0.{target+1}","recovery_ready_time":1000+offset+1,"grpc_alive_time":1000+offset+1.1,"leave_maintenance_start":1000+offset+1.1,"leave_maintenance_end":1000+offset+1.3,"rejoin_maintenance_start":1000+offset+1.3,"rejoin_maintenance_end":1000+offset+1.5,"explicit_du_start":1000+offset+1.5,"explicit_du_end":completion,"structural_cycle_completion_time":completion,"structural_cycle_completion_elapsed_s":offset+2,"infrastructure_recovery_s":.9,"total_cycle_s":2,"slack_before_next_event_s":23 if i<4 else None,"dissemination_time_remaining_after_cycle_s":17.6 if i==4 else None,"rpc_timeout_count":0,"failed_peer_ids":[],"maintenance_acknowledgement_count":60,"expected_acknowledgement_count":60,"original_pod_uid":f"old{i}","replacement_pod_uid":f"new{i}"})
    (run/"logs.jsonl").write_text("\n".join(json.dumps(r) for r in rows)+"\n")
    pods=[{"status":{"conditions":[{"type":"Ready","status":"True"}]}} for _ in range(20)]; (run/"pods.json").write_text(json.dumps({"items":pods}))
    return root

def test_feasibility_analyzer_requires_four_of_four_valid_cycles(tmp_path):
    report=gate_analyzer().analyze(write_gate_fixture(tmp_path)); assert report["feasibility"]=="PASS" and report["scientific_use"]=="FEASIBILITY-ONLY / NOT EXP11 RESULT"

def test_feasibility_analyzer_fails_any_missing_cycle(tmp_path):
    report=gate_analyzer().analyze(write_gate_fixture(tmp_path,3)); assert report["feasibility"]=="FAIL"
