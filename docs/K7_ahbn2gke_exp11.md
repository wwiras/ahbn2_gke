# K7 — Exp11 pod churn on GKE

## Scientific question and stage boundary

K7 asks how Gossip, Structured, the repository's DC-SoC-inspired baseline, and AHBN maintain dissemination while peers repeatedly leave and return. K7 does not change K5 or K6. It inherits canonical AHBN (`z=-d_hat+l_hat+u_hat+c_hat`, EWMA, frozen mode threshold) and frozen S5 fanout 2/3/4/5/6 through K7-named packaging. There is no churn boost, forced mode, fallback, or topology-global oracle in AHBN.

K5 and K6 files are hash-gated before local/GKE execution and compared again afterward. `docs/K5_EXP08_FROZEN.md` remains authoritative. The peer SHA-256 in that repository record ends in `...10b5a`; the longer value in the task prose is not a valid 64-hex SHA-256.

## Frozen experiment contract

- Identity: `k7_exp11`; treatments in order Gossip, Structured, DC-SoC, AHBN; seeds 42–46 (smoke: 42 only), with unique `k7_exp11_<treatment>_seed<seed>` run IDs.
- Topology: matched BA graph, N=20, m=2, identical topology seed and physical adjacency within a seed.
- Workload: 80 messages at 0.4 s, settle 18 s. The 32-second message train is a mechanical timing extension: completed K6 evidence showed pod recreation taking 2.3–5.0 s, so the canonical 7.6-second train could not contain four sequential recovery cycles. No AHBN parameter was tuned.
- Churn: four fixed leave offsets from K7 workload start: **1.0, 8.0, 15.0, and 22.0 seconds**. These treatment-independent times are stored in every generated topology before execution. Seven-second slots exceed the maximum observed K6 pod-recreation time (5.034 s) with approximately 1.966 s margin and place all leaves inside the unchanged 31.6-second message train. Every event remains delete, observed unavailability, replacement UID, Kubernetes Ready, gRPC alive, then rejoin. The historical `intervalSec=1.2` field remains only for generic-config compatibility and does not schedule K7 events.
- Fail-closed overlap rule: before each fixed deadline, the preceding cycle must be complete. If it remains unresolved, or completes only after the next planned deadline, the controller raises a contract error and invalidates the run; it never shifts an event to `recovery + 1.2 s`.
- DC-SoC: availability-driven leave/rejoin uses `DCSOCMaintenance`; one explicit DU occurs after each completed churn cycle. Gossip and Structured get no maintenance; AHBN gets no explicit repair.

## Source and target selection

K7 uses **role-aware structural churn**, not random churn. For each seed, the common source is the lowest-ID peer that is neither a Structured CH nor a DC-SoC CORE; generation fails closed if none exists. The four common, distinct, non-source target identities are chosen before execution with this priority: DC-SoC CORE, Structured CH, then high-degree non-source physical peers, deduplicated with lowest ID as tie-breaker. This intentionally disrupts structurally important membership while preserving treatment matching. The same selected peer IDs, fixed leave offsets, and event ordering are applied to Gossip, Structured, DC-SoC, and AHBN; each generated topology also records the treatment-native role.

## Metrics, denominator, and stabilization

Headline metrics are delivery ratio, propagation delay, duplicate receptions, total forward transmissions, and recovery/stabilization. For every injection, expected receivers are exactly peers active at injection time: a peer exits the denominator when unavailability is observed and re-enters only after the replacement pod is Ready and gRPC-alive.

For churn event *i*, recovery is the first message injected at or after that event's verified rejoin for which every peer active/Ready at that opportunity has a `received_new` observation. Recovery time is measured from verified rejoin to the last required reception that completes that opportunity. If none occurs, `recovered=false`, `recovery_time_s=null`, and censoring is explicit. Run-level stabilization reports recovered-event count out of four and preserves all event-level values.

Each run retains generated config, topology, role mapping, logs, controller log, pod/readiness evidence, planned/observed churn trace, metrics, AHBN trace, and DC-SoC maintenance trace. Formal analysis creates the dataset audit, validation report (JSON/Markdown), scientific summary, per-seed and per-event tables, descriptive uncertainty, and the five headline figures; individual seeds remain visible.

## Smoke acceptance and execution record

Smoke is integrity-only. It passes on four matched seed-42 treatments, four genuine complete leave/rejoin cycles per run during active dissemination, valid denominator/censoring, isolated DC-SoC maintenance, frozen AHBN/S5 traces, complete telemetry, parser success, and unchanged K5/K6 hashes. Performance never gates PASS.

The runner writes UTC start, git commit, image/tag (and digest when available), exact terminal output, artifacts, analysis, and PASS/FAIL context beneath `outputs/k7_exp11_smoke-<UTC>/`. On failure it stops; it does not redesign or rerun.

Local validation on 2026-09-03 uses:

```text
/Users/wwiras/Documents/src/AHBN_GKEProj/venv_ahbn2/bin/python -m pytest -q tests/test_k7_exp11.py tests/test_k6_exp10.py tests/test_k5_final_actuator_gke.py

78 passed in 9.01s
```

Docker build/push and all GKE execution are manual. No K7 image or GKE run was performed during implementation.

## Smoke attempt 20260903T071218Z — validator failure

The seed-42 Gossip execution in `outputs/k7_exp11_smoke-20260903T071218Z` completed on image `wwiras/ahbn2-peer:k7-exp11-frozen-s5-20260903-amd64` (pushed digest `sha256:5b7f83e25429abb83925779d65a01f3041dbe2291073a944b61ada706b70fea0`). Post-run validation failed with `ValueError: churn was not active during dissemination` at the combined condition `len(injected) != 80 or max(leaves.ts) >= max(injected.ts)`.

Root cause classification is **E: another concrete implementation defect**, specifically duplicate host-side log ingestion. `peer_stream.jsonl` contains 80 unique `message_injected` records and `final_snapshot.jsonl` contains the same 80 records. `logs.jsonl` concatenates both sources, so the validator saw 160 records even though the timestamp ordering itself passed. This was not a timestamp-domain mismatch and not a runtime pacing failure.

All peer and controller `ts` fields here are Unix wall-clock epoch timestamps generated independently with `time.time()` in their respective pods. Planned/delete/unavailable/Ready/gRPC timestamps are controller-local epoch values; injection timestamps are source-peer-local epoch values. Kubernetes Events use API-server relative display ages and are corroborating evidence, not arithmetic inputs. Generated `planned_leave_offset_s` values are workload-relative logical times. Validation preserves raw fields and uses explicit `workload_elapsed_s` when present, otherwise it derives elapsed time from the first injection within the shared epoch domain.

|Event|Target|Planned epoch (elapsed)|Delete epoch (elapsed)|Unavailable epoch|Ready epoch|gRPC-alive epoch|
|---:|---:|---:|---:|---:|---:|---:|
|1|0|1788419626.564494 (0.997570 s)|1788419626.680500 (1.113576 s)|1788419626.713208|1788419628.611001|1788419628.649009|
|2|5|1788419633.564494 (7.997570 s)|1788419633.656836 (8.089912 s)|1788419633.697822|1788419635.639562|1788419635.646542|
|3|10|1788419640.564494 (14.997570 s)|1788419640.645351 (15.078427 s)|1788419640.667119|1788419641.765025|1788419641.773271|
|4|15|1788419647.564494 (21.997570 s)|1788419647.659284 (22.092360 s)|1788419647.690613|1788419649.623415|1788419649.633615|

The 80 unique injections span epoch 1788419625.566924 through 1788419658.256379 (32.689455 s), with median spacing 0.412135 s. Thus the final actual deletion occurred at workload elapsed 22.092360 s, before injection completion at 32.689455 s. Every target has a distinct replacement UID, verified Ready/gRPC recovery, and matching final pod UID; all 20 final pods are Ready. The execution is **scientifically valid and reusable**.

The minimal correction deduplicates identical JSON events during host-side loading and replaces the former compound check with independent diagnostics for injection count/pacing, frozen schedule, event counts/order, target/source safety, fixed planned gaps, replacement UID, Ready/gRPC evidence, non-overlap, timing tolerance, and final churn versus final injection. Runtime scheduling and the frozen experiment design are unchanged. Docker rebuild is not required because the changed behavior is host-side validation only; the copy of this helper inside the existing image is not used on the controller execution path being corrected.

Offline revalidation of the existing Gossip directory passed and produced `metrics.json` plus `churn_events.json`. Resume mode rechecks the original image tag and digest across all 20 pods, immutable K5/K6 hashes, regenerated topology contract, and complete validator output before marking Gossip reusable. It then continues Structured, DC-SoC, and AHBN and runs analysis only after the four-run matrix is complete.

Post-correction regression command result: `83 passed in 12.15s`.

Next manual command:

```text
IMAGE=wwiras/ahbn2-peer:k7-exp11-frozen-s5-20260903-amd64 ./scripts/run_k7_exp11.sh smoke --resume outputs/k7_exp11_smoke-20260903T071218Z
```

## DC-SoC Smoke Timing Diagnosis

Diagnostic scope: `outputs/k7_exp11_smoke-20260903T071218Z/runs/seed42/dcsoc`. The run stopped after two cycles and failed validation with `churn event counts invalid: leaves=2 unavailable=2 rejoined=2`. No DC-SoC, scheduling, workload, AHBN, S5, K5, or K6 code was changed during this diagnosis.

The source-peer `message_injected` epoch for `m1`, 1788434018.532271, is the workload-relative origin.

|Event 1 milestone (target 0, CORE)|Raw epoch|Elapsed (s)|
|---|---:|---:|
|Planned leave|1788434019.528079|0.995808|
|Delete / unavailable|1788434019.646004 / 1788434019.675113|1.113733 / 1.142842|
|Ready / gRPC alive|1788434021.322755 / 1788434021.327380|2.790484 / 2.795109|
|Leave maintenance first start / last end|1788434021.331392 / 1788434021.425698|2.799121 / 2.893428|
|Rejoin maintenance first start / last end|1788434021.430049 / 1788434021.666224|2.897779 / 3.133954|
|DU peer-0 UNAVAILABLE / last successful end|1788434021.669325 / 1788434021.909289|3.137054 / 3.377019|
|Cycle marked complete / next deadline|1788434021.910173 / 1788434026.528079|3.377902 / 7.995808|

Leave and rejoin were acknowledged by all 20 peers. DU was acknowledged by peers 1–19; peer 0 returned immediate `UNAVAILABLE`/connection refused, without retry. The controller nevertheless marked the cycle complete.

|Event 2 milestone (target 5, LEAF)|Raw epoch|Elapsed (s)|
|---|---:|---:|
|Planned leave|1788434026.528079|7.995808|
|Delete / unavailable|1788434026.627296 / 1788434026.653204|8.095025 / 8.120934|
|Ready / gRPC alive|1788434028.541481 / 1788434028.547640|10.009210 / 10.015369|
|Leave peer-0 / peer-5 deadline exceeded|1788434031.551918 / 1788434034.574559|13.019648 / 16.042288|
|Leave last successful end|1788434034.658343|16.126072|
|Rejoin peer-0 / peer-5 deadline exceeded|1788434037.661874 / 1788434040.687532|19.129603 / 22.155262|
|Rejoin last successful end|1788434040.774292|22.242021|
|DU peer-0 / peer-5 deadline exceeded|1788434043.778858 / 1788434046.809878|25.246588 / 28.277607|
|DU last successful end / cycle marked complete|1788434046.909704 / 1788434046.910547|28.377434 / 28.378277|
|Event-3 fixed deadline|1788434033.528079|14.995808|

All six event-2 failures were sequential `ApplyDCSOCMaintenance` calls with a 3-second timeout and no retry: peer 0 then peer 5 for leave, rejoin, and explicit DU. They contributed approximately 18 seconds. Successful `_leave`/`_rejoin` calls took about 0.03–0.13 ms per peer; successful `_recluster` calls took about 0.68–1.76 ms.

The real blocking path is fixed deadline → delete → observe unavailable → replacement UID/Ready → gRPC alive → broadcast leave to all peers → broadcast rejoin to all peers → broadcast explicit DU to all peers → mark complete → check the next deadline. Replacement, changed UID, Ready, and gRPC alive are required infrastructure recovery. Each peer owns independent maintenance and forwarding fields, so its transition plus `sync_peer` is required local structural recovery. K7 froze DU after each cycle, so DU must also complete on every active peer. These acknowledgements are not auxiliary telemetry; only logging/trace serialization is telemetry-only.

Primary classification: **GENUINE SCHEDULE INFEASIBILITY**. Required distributed maintenance did not finish before +15 seconds. Detaching it from scheduler gating would declare recovery with stale peer structures and change semantics. Error swallowing is an audit weakness, but failing earlier would not make the schedule feasible.

Each of three sequential phases can consume up to `20 peers × 3 s = 60 s`, or 180 s per cycle plus infrastructure recovery. Event 2 consumed at least 20.382 seconds from planned leave through attempted DU and still lacked six acknowledgements. Four cycles at that observed duration exceed 81 seconds; therefore no defensible four-cycle fixed schedule fits the existing ~32-second workload under current semantics.

Gossip and Structured `recovered_events=0` are **expected** under the frozen metric. Their eight full-delivery messages all preceded the first rejoin; no post-rejoin opportunity reached all active peers, so censoring is correct.

Conclusion: no code change, no Docker rebuild, and no resume command. The scientific contract needs explicit revision before another GKE action.

## Scientific Contract Redesign Feasibility Study

This is an offline design study only. Exp11 remains a controlled comparison of Gossip, frozen Structured, repository DC-SoC maintenance, and frozen AHBN under identical temporary peer departures and returns. The churn schedule is the stimulus; pod UID/Ready/gRPC observations measure infrastructure recovery; delivery, delay, duplicates, forwards, and full-delivery opportunities measure dissemination; DC-SoC structural maintenance and AHBN's frozen observation/controller path are treatment-specific responses.

Observed seed-42 timing is not treated as a population estimate. Event 1 took 1.652 s from confirmed unavailability to gRPC recovery, approximately 0.094 s for the leave broadcast, 0.236 s for rejoin, 0.240 s for attempted DU, and 2.382 s from planned leave to controller completion; it had one immediate DU `UNAVAILABLE`. Event 2 took 1.894 s from unavailability to gRPC recovery, approximately 6.107 s for attempted leave, 6.116 s for attempted rejoin, and 6.135 s for attempted DU, totaling 20.382 s from planned leave to controller completion; it had six full 3-second timeouts. Successful peer-local algorithms remained sub-millisecond to a few milliseconds.

The current theoretical maintenance bound is three sequential broadcasts × 20 peers × 3 seconds = 180 seconds per cycle. Controller infrastructure loops additionally allow up to 60 seconds to observe unavailability and 180 seconds for replacement Ready/gRPC recovery, giving a loose code-path bound near 420 seconds plus API overhead. This bound is useful for identifying the impossibility of a hard guarantee, not as a sensible workload target.

Option A, four events plus a longer workload, best preserves the repeated-churn question. Candidate workload-only durations are 47.6 s for 120 messages, 63.6 s for 160, and 79.6 s for 200 (using first-to-last injection duration); none provides comfortable support for four 20.382-second cycles. A provisional 25-second spacing policy gives offsets 1, 26, 51, and 76 seconds. A 240-message workload at 0.4 seconds spans 95.6 seconds, leaving 19.6 seconds of post-final-churn dissemination plus the unchanged settle period. This is a candidate, not a frozen contract: its 4.618-second inter-cycle margin over the one observed long cycle is not validated.

Option B loses the defining repeated-churn richness. Under the observed long-cycle requirement, the current workload can accommodate at most one conservatively separated complete cycle with useful post-recovery dissemination. Two cycles at the current +1/+8 pattern were attempted, but the second was structurally incomplete; three or four are indefensible. One event becomes close to Exp10-style failure/recovery, while two events provide limited repetition and role coverage.

Option C is rejected: **WOULD CHANGE DC-SOC SEMANTICS**. Each active peer owns independent structural state used by forwarding, and K7 froze leave, rejoin, synchronization, and explicit DU. Treating those required updates as post-cycle auxiliary work would permit stale structures. Logging alone is auxiliary.

Sequential-recovery churn remains the recommendation. Fixed overlapping churn could be a valid separate stress experiment, but it asks how algorithms behave under accumulated unresolved pressure. It would not answer K7's current per-cycle recovery question and would systematically expose DC-SoC to queued structural work while stateless comparators have no analogous backlog.

Fairness requires the same fixed offsets and target IDs for all treatments, source exclusion, preregistration, and fail-closed unresolved-cycle handling. A longer common schedule does not grant DC-SoC a treatment-specific grace period; it merely makes the shared contract possible. Extending the workload also increases post-rejoin opportunities for the unchanged recovery metric, improving observability without redefining recovery.

Relative workload/runtime impacts versus the current 80-message workload are: 120 messages 1.5× workload (about 1.32× including 18-second settle), 160 messages 2× (about 1.64× including settle), 200 messages 2.5× (about 1.96×), and provisional 240 messages 3× (about 2.28×). These factors apply to both the four-run smoke and the 20-run formal matrix, excluding mostly fixed deployment overhead.

Preferred provisional contract, contingent on feasibility evidence: four distinct role-aware targets; 240 messages at 0.4 seconds; nominal 96-second workload; offsets 1/26/51/76 seconds; identical schedule across treatments/seeds; unchanged source and target rules; fail closed on unresolved prior cycles; unchanged post-rejoin full-delivery recovery metric; and successful leave/rejoin/sync/DU completion on every active DC-SoC peer before cycle completion. Fewer events are rejected for reduced scientific coverage, overlapping churn for changing the question, and relaxed completion for changing DC-SoC semantics.

Decision: **ONE SMALL FEASIBILITY GATE REQUIRED**. Existing evidence contains only two cycles and required acknowledgement failures, so it cannot establish a defensible upper-enough spacing. The minimal proposed gate is DC-SoC only, seed 42 only, no AHBN or comparator performance analysis, one candidate spacing only: 240 messages at 0.4 seconds with four fixed role-aware targets at +1/+26/+51/+76 seconds. It passes only if all four cycles complete every infrastructure, leave, rejoin, synchronization, and explicit-DU acknowledgement before the next deadline, with the fourth completing while sufficient dissemination opportunities remain. This is not a parameter sweep. It must not be implemented or run without approval.

## DC-SoC 25-second Timing Feasibility Gate

This independent calibration gate answers only whether the current frozen DC-SoC implementation can finish four legitimate churn/recovery cycles in fixed 25-second slots under K7 GKE conditions. It is not an algorithm comparison, AHBN evaluation, parameter sweep, or source of thesis performance results. Its artifacts and dissemination metrics are labeled **FEASIBILITY-ONLY / NOT EXP11 RESULT**. A gate PASS permits review of a candidate contract; it does not freeze K7 automatically.

The gate is DC-SoC only and seed 42 only. It preserves N=20, BA m=2, the common source-selection and source-exclusion rules, and the established deterministic role-aware structural targets 0, 5, 10, and 15. It injects 240 messages at 0.4 seconds and schedules fixed workload-relative leaves at +1, +26, +51, and +76 seconds. These deadlines are generated before execution and never depend on recovery. If a cycle is unresolved at the next deadline, the gate fails closed without postponing the event. The original smoke/formal YAML remains 80 messages with +1/+8/+15/+22; it is not modified by this mode.

Each cycle requires observed deletion/unavailability, a changed StatefulSet replacement UID, Kubernetes Ready, gRPC alive, frozen leave maintenance plus peer-local `sync_peer`, frozen rejoin maintenance and synchronization, explicit DU and structural generation update, and a successful acknowledgement from every active peer for every phase. Machine-readable records retain raw and experiment-relative milestone timestamps; phase durations; infrastructure recovery; total cycle time; next-deadline slack (or event-4 dissemination time remaining); timeout/unavailable counts; failed peer IDs; actual and expected acknowledgements; and `PASS`, `FAIL_TIMEOUT`, `FAIL_DEADLINE`, `FAIL_INFRA`, or `FAIL_MAINTENANCE` status.

Overall PASS requires exactly four attempted and confirmed unavailability/replacement/Ready/gRPC cycles, all three DC-SoC phases and all acknowledgements for every cycle, cycles 1–3 complete before +26/+51/+76 respectively, cycle 4 complete before the final injection so post-rejoin dissemination opportunities remain, 240 injections spanning the churn sequence, and final topology/runtime health. Any missing cycle or criterion is FAIL. The analyzer reports per-event infrastructure time, total cycle, slack, RPC failures, aggregate maximum/mean cycle time, minimum slack, timeout-bearing event count, event-4 completion relative to injection end, and one of the two preregistered decision statements. It computes no comparative ranking.

Provisional candidate freeze, requiring a gate PASS and a separate explicit review: all four treatments and formal seeds 42–46; 240 messages at 0.4 seconds; +1/+26/+51/+76 fixed leaves; matched topology, source, target IDs, and schedule; unchanged recovery metric and fail-closed semantics; unchanged DC-SoC, AHBN, and S5 semantics.

Execution is manual only. The dedicated mode writes `outputs/k7_dcsoc_feas25-<UTC>/` and does not resume, overwrite, or reinterpret `outputs/k7_exp11_smoke-20260903T071218Z`. Because K7 controller telemetry and gate-only acknowledgement enforcement are image-resident, use a new immutable image tag. No Docker build, push, GKE run, or feasibility gate was performed while implementing this mode.

Local implementation validation on 2026-09-03: the prescribed K7/K6/K5 pytest command completed with **87 passed in 8.96s**. Python compilation of all modified Python files, Bash syntax checking of the modified runner and shared K7 execution script, and `git diff --check` all passed.

The first manual gate attempt (`outputs/k7_dcsoc_feas25-20260903T130124Z`) exposed an orchestration race rather than a spacing failure: DNS-based `GetStatus` succeeded, but the target immediately returned `UNAVAILABLE` for all three required maintenance phases. The gate now binds the changed replacement UID to its Kubernetes `podIP`, validates `GetStatus` directly at that IP, and uses the same verified IP only for the target's leave replay, rejoin, and explicit-DU RPCs. Unaffected peers retain StatefulSet DNS addressing. All three phases still require 20/20 acknowledgements; no target exclusion, retry, sleep, schedule, workload, or DC-SoC semantic change was introduced.

Local validation after the replacement-IP binding correction: **94 passed in 9.46s** for the prescribed K7/K6/K5 regression suite; modified-Python compilation, Bash syntax validation, and `git diff --check` passed.

The second manual gate attempt (`outputs/k7_dcsoc_feas25-20260903T162956Z`) confirmed the replacement-IP correction: event 1 passed all three 20/20 phases with approximately 21.723 seconds of slot slack. Event 2 recovered target peer 5 and reached it at its verified replacement IP, but the leave replay to unaffected peer 0 at its normal StatefulSet DNS endpoint returned `DEADLINE_EXCEEDED` after the unchanged 3-second deadline. Rejoin and explicit DU subsequently achieved 20/20. The cycle still had approximately 18.541 seconds of slot slack, so this trace does not establish 25-second schedule infeasibility. The available evidence cannot distinguish client/transport dispatch, server handler scheduling, `set_availability`, `sync_peer`, or response-path delay; its classification remains **INSUFFICIENT EVIDENCE**.

K7 feasibility-only RPC diagnostics now assign every event/phase/destination call a deterministic correlation ID and carry it in dedicated gRPC invocation metadata (`x-k7-request-id`). This does not alter the protobuf or overload a scientific request field. The controller records the affected and destination peers, target/unaffected status, actual endpoint, replacement-IP versus StatefulSet-DNS addressing, RPC start/end/elapsed time, the unchanged 3-second deadline, ACK/NACK or gRPC outcome, status code/details, and error text for all 20 recipients.

Server tracing is installed only by `k7_final_actuator_runtime.py`; frozen `peer.py` remains byte-identical. Calls without K7 correlation metadata invoke the original handler directly. Correlated calls emit handler entry, before/after the existing availability or explicit-DU operation, before/after the existing `sync_peer`, and handler exit with success/failure, phase, affected peer, and receiving peer. The operation order, arguments, acknowledgement semantics, and state transitions are unchanged. The analyzer correlates failed client calls with these server records and reports observed boundary durations and presence only; gate PASS/FAIL remains unchanged.

Local diagnostic-instrumentation validation on 2026-09-04: the prescribed K7/K6/K5 regression suite completed with **99 passed in 9.90s**. The scientific contract remains N=20, BA m=2, seed 42, 240 messages at 0.4 seconds, targets 0/5/10/15 at +1/+26/+51/+76, target included, replacement-IP target binding, 20/20 leave/rejoin/explicit-DU requirements, no retries, and the 3-second RPC deadline.
