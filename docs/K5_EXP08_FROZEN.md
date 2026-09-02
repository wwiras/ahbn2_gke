# K5 Exp08 Freeze Record

**K5 EXP08 STATUS: FROZEN**  
Freeze date: 2026-09-02

## Immutable experiment identity

- Formal output: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08_formal-20260902_092321`
- Expected/actual executions: 80/80
- Algorithms: Gossip, Structured, DC-SoC, AHBN
- Delays: 700, 1050, 1400, 2100 ms
- Seeds: 42, 43, 44, 45, 46
- Topology: 20 nodes, `ba`, `ba_m=2`, source=0
- Image: `wwiras/ahbn2-peer:k5-exp08-final-s5-20260902-tracefix-amd64`
- Digest: `sha256:d3224d4cdb16507d28d1c164d60b31b7c451fb0efa36e9add959f364fdd0a8d5`
- Recorded git commit: `c04e673c78a52b96e1534992305fb2b49762785c`
- Recorded working-tree state at formal start:

```text
M app/k5_exp08_tools.py
 M docs/K5_ahbn2gke_exp08(k8s).md
 M helm/ahbn/topology.json
 M scripts/run_k5_exp08.sh
 M scripts/run_k5_exp08_formal.sh
 M tests/test_k5_exp08_final_actuator.py
?? docs/K6_ahbn2gke_exp10(k8s).md
```

## Frozen implementation

- `app/ahbn_controller.py`: `dee8cb8e81494bc1448793076803a330602d613e9654ac7fa572d8203f6cc7c8`
- `app/peer.py`: `64c529f9c32f732c8d4f2c5959c75c0bbed20252328b81b018eb35c6cef10b5a`
- `app/k5_final_actuator_policy.py`: `8c7a0658cd226d0349e3ed3c64c943887196fdee57d9ef06874fd8525b683cff`
- `app/k5_final_actuator_runtime.py`: `1d95271079064b6c159fcb9d7b553c03cc8b6cb42893f1b8e92bf8f4b6e95a25`
- Controller equation: `z = -d_hat + l_hat + u_hat + c_hat`
- S5: `z<=-0.25→2`, `-0.25<z<0.25→3`, `0.25<=z<0.90→4`, `0.90<=z<1.50→5`, `z>=1.50→6`

## Validation gate

- Dataset coordinates: PASS (80 unique; zero missing/duplicate/unexpected)
- Mandatory metric domains: PASS
- All 1,600 collected peer statuses ready and alive: PASS
- Overloaded target logically alive in every run: PASS
- DC-SoC SLOW!=FAILED (maintenance zero): PASS
- Controller invariant mismatches: 0
- Actuator invariant mismatches: 0
- Canonical/S5 hashes: PASS
- Smoke/formal/pod image provenance: PASS
- Result direction: MIXED
- Formal integrity gate: PASS

## Principal result and limitations

Gossip, Structured, and DC-SoC achieve delivery 1.0 in every run. AHBN trades lower delivery for fewer forwards, far fewer duplicates than Gossip, and lower mean delay in three of four conditions. Its delivery and internal response are non-monotonic and seed/timing sensitive; frequent eligible-neighbour clipping means realized dissemination can be topology-constrained. This supports a bounded adaptive trade-off interpretation, not consistent superiority or maintained propagation performance.

Manuscript claims requiring revision include the old 8.6%/134% delay statements, the unqualified 62.2% duplicate statement, “maintains propagation performance,” and broad “consistently balanced/robust” wording.

## Closure artifacts

- Audit: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08_formal-20260902_092321/final_analysis/final_dataset_audit.json`
- Validation: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08_formal-20260902_092321/final_analysis/final_validation_report.md`
- Scientific summary: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08_formal-20260902_092321/final_analysis/final_scientific_summary.json`
- Tables: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08_formal-20260902_092321/final_analysis/tables`
- Figures: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/outputs/k5_exp08_formal-20260902_092321/final_analysis/figures`
- Interpretation: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/docs/K5_exp08_final_scientific_interpretation.md`
- Manuscript audit: `/Users/wwiras/Documents/src/AHBN_GKEProj/ahbn2_gke/docs/K5_exp08_manuscript_claim_audit.md`

No further Exp08 tuning or reruns may be performed solely to improve performance. Any reopening requires a new preregistered experiment identity and must not overwrite this frozen dataset.
