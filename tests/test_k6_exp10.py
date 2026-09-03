from __future__ import annotations
import ast, hashlib, json, shutil, sys
from pathlib import Path
import pytest

ROOT=Path(__file__).parents[1]; APP=ROOT/"app"; sys.path.insert(0,str(APP))
from ahbn_controller import AHBNState, CanonicalAHBNController
from k5_final_actuator_policy import requested_fanout as k5_fanout
from k6_final_actuator_policy import requested_fanout as k6_fanout
from k6_exp10_tools import ALGORITHMS, choose_exp10_target, exp10_metadata, validate_run, validate_topologies, write_config

K5_HASHES={"k5_final_actuator_policy.py":"8c7a0658cd226d0349e3ed3c64c943887196fdee57d9ef06874fd8525b683cff","k5_final_actuator_runtime.py":"1d95271079064b6c159fcb9d7b553c03cc8b6cb42893f1b8e92bf8f4b6e95a25"}

@pytest.mark.parametrize("z",[-1.0,-0.25,-0.249999,0.0,0.249999,0.25,0.899999,0.90,1.499999,1.50,2.0])
@pytest.mark.parametrize("treatment",["S0","S5"])
def test_k5_k6_policy_parity(treatment,z):
    assert k6_fanout(treatment,z)==k5_fanout(treatment,z)

@pytest.mark.parametrize("observations",[(0,0,0,0),(1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1),(0.2,0.7,0.6,0.4),(1,1,1,1)])
def test_inherited_controller_observation_ewma_score_and_mode_parity(observations):
    a=CanonicalAHBNController().update(AHBNState(),*observations)
    b=CanonicalAHBNController().update(AHBNState(),*observations)
    assert a==b
    assert a.score==pytest.approx(-a.d_hat+a.l_hat+a.u_hat+a.c_hat)

def normalized_runtime_ast(path):
    tree=ast.parse(path.read_text())
    if tree.body and isinstance(tree.body[0],ast.Expr) and isinstance(tree.body[0].value,ast.Constant): tree.body.pop(0)
    class Normalize(ast.NodeTransformer):
        def visit_ImportFrom(self,node):
            if node.module=="k6_final_actuator_policy": node.module="k5_final_actuator_policy"
            return node
    return ast.dump(Normalize().visit(tree),include_attributes=False)

def test_k5_k6_runtime_semantic_ast_parity():
    assert normalized_runtime_ast(APP/"k5_final_actuator_runtime.py")==normalized_runtime_ast(APP/"k6_final_actuator_runtime.py")

def test_all_five_k6_contracts(tmp_path):
    import subprocess
    for seed in range(42,47):
        paths=[]; sources=[]
        for algorithm in ALGORITHMS:
            cfg=tmp_path/f"{algorithm}_{seed}.yaml"; topo=tmp_path/f"{algorithm}_{seed}.json"
            write_config(ROOT/"experiments/k6_exp10.yaml",cfg,algorithm,seed)
            subprocess.run([sys.executable,str(APP/"gen_topology.py"),"--config",str(cfg),"--out",str(topo)],check=True)
            data=json.loads(topo.read_text()); sources.append(data["message_source"])
            assert data["run_id"].startswith("k6_exp10_") and data["k6_exp10"]
            assert choose_exp10_target(data)["peer_id"]!=data["message_source"]
            paths.append(topo)
        assert len(set(sources))==1
        validate_topologies(paths,ALGORITHMS)

def test_historical_k5_smoke_parser_compatibility(tmp_path):
    historical=ROOT/"outputs/k5_exp10_smoke-20260903T022035Z"
    for algorithm in ALGORITHMS:
        source=historical/"runs/seed42"/algorithm; copied=tmp_path/algorithm
        shutil.copytree(source,copied)
        assert exp10_metadata(json.loads((copied/"topology.json").read_text()))["algorithm"]==algorithm
        assert validate_run(copied)["algorithm"]==algorithm

def test_k5_immutable_hashes():
    for name,expected in K5_HASHES.items(): assert hashlib.sha256((APP/name).read_bytes()).hexdigest()==expected

def test_k6_packaging_and_naming():
    docker=(APP/"Dockerfile.k6_exp10").read_text(); runner=(ROOT/"scripts/run_k6_exp10.sh").read_text()
    assert "k6_final_actuator_policy.py" in docker and "k6_final_actuator_runtime.py" in docker
    assert 'CMD ["python", "k6_final_actuator_runtime.py"]' in docker
    assert "ahbn-k6-exp10" in runner and "outputs/k6_exp10_smoke-" in runner and "outputs/k6_exp10_formal-" in runner
    assert "tests/test_k6_exp10.py" in runner and "scripts/k6_exp10_analysis.py" in runner
