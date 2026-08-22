# K0.5 Repository Reconciliation

## Source

- Archive: `/Users/wwiras/Desktop/ahbn_gke.zip`
- Archived branch: `main`
- Archived HEAD: `bad792042f18919bdf5e9e7b7e777d6f704e0595`
- Archived `origin/main` recorded by the K0 handoff: `e949c376f5140e0171f1d2d9b901c5d7d906aa64`
- Archived `origin/main` resolved from the Git metadata in the supplied archive during K0.5: `bad792042f18919bdf5e9e7b7e777d6f704e0595`

The difference between the K0 handoff's recorded `origin/main` and the ref currently embedded in the supplied archive is documented as a provenance discrepancy. No archived Git metadata was copied to the destination.

## Destination

- Repository root: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke`
- Branch: `main`
- HEAD before restoration: `f9824ca88f6d69f656188623a3a1cb8f5140e0a5`
- Remote: `origin https://github.com/wwiras/ahbn2_gke.git` (fetch and push)
- Initial status: `## main...origin/main` (clean)
- Initial tracked tree: `.gitignore`, `LICENSE`, `README.md`, and `docs/K0_ahbn2gke_audit.md`

## Restored files

Restored 45 files from the archive under `app/`, `configs/`, `docs/`, `experiments/`, `helm/`, `k8s/`, and `scripts/`. Archive packaging artifacts (`.DS_Store` and `__MACOSX`) and the archive's `.git/` directory were excluded. The executable mode was preserved on all six shell scripts.

The existing destination files `.gitignore`, `LICENSE`, `README.md`, and `docs/K0_ahbn2gke_audit.md` were retained.

## Equivalence

Deterministic `cmp` comparison reported `MATCH` for all 45 restored files. There were no restored files reported as `DIFFERENT` or `MISSING`. The existing destination-only file `docs/K0_ahbn2gke_audit.md` was reported as `EXTRA`, as expected.

Critical equivalence: **PASS**. This includes:

- `app/peer.py`, `app/controller.py`, `app/gen_topology.py`, and `app/peer.proto`
- all `experiments/exp8*.yaml` files and `experiments/exp10.yaml`, `exp11.yaml`, and `exp12.yaml`
- `scripts/run_exp8.sh`, `run_exp10.sh`, `run_exp11.sh`, `run_exp12.sh`, and `run_experiment.sh`
- all archived Helm and Kubernetes project files

## Existing root-file differences

| File | Result | Destination SHA-256 | Archive SHA-256 | Action |
| --- | --- | --- | --- | --- |
| `.gitignore` | DIFFERENT | `fe07aeae2cfd1ff2ce4c0c5911dfbb550a3f1065e213175039abadfc3a5a15bb` | `a5f7ed7949900125ee2b95e4fab5f8458cd22ed998d78ddd704173137b92be76` | Retained destination version |
| `LICENSE` | MATCH | identical | identical | Retained destination version |
| `README.md` | DIFFERENT | `f14634dbd1453820b1a489a57573780194ee32c7da2b99291227ed608db3bd0e` | `d018e85fec45c4897d6c2d80f889f35d790934629be7b15c4f3ff9808acafba0` | Retained destination version |

Root-file difference count: 2.

## Validation

- Python: `PYTHONPYCACHEPREFIX=/tmp/ahbn-k05-pycache python3 -m compileall -q app` — **PASS**
- Static YAML: Ruby/Psych `YAML.load_stream` over `configs/*.yaml`, `experiments/*.yaml`, `k8s/base/*.yaml`, `helm/ahbn/Chart.yaml`, and `helm/ahbn/values.yaml` — **PASS** (14 files)
- Helm: `helm template ahbn helm/ahbn` — **PASS**
- Shell: `bash -n` over every `scripts/*.sh` file — **PASS**
- Archive equivalence: deterministic `cmp` for all restored project files — **PASS**
- Git whitespace: `git diff --check` — **PASS**
- Git inspection: `git status --short --branch`, `git diff --stat`, and `git diff --check` were run. Restored files remain untracked for review; no commit or push was performed.

## Scope

No algorithm or experiment semantics were modified during K0.5.

No Kubernetes deployment, experiment, simulation, workload, image build, push, commit, or Git history rewrite was performed. K1 was not started.
