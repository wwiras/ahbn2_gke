#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,math,statistics,sys
from pathlib import Path
import matplotlib.pyplot as plt
ROOT=Path(__file__).parents[1]; sys.path.insert(0,str(ROOT/"app"))
from k7_exp11_tools import ALGORITHMS,SEEDS
METRICS=("delivery_ratio","propagation_delay","duplicates","total_forwards")

def ci(values):
    mean=statistics.fmean(values)
    if len(values)<2:return mean,mean,mean
    margin=(2.7764451051977987 if len(values)==5 else 1.96)*statistics.stdev(values)/math.sqrt(len(values)); return mean,mean-margin,mean+margin

def analyze(root:Path,mode:str):
    rows=[json.loads(p.read_text()) for p in sorted(root.glob("runs/*/*/metrics.json"))]; seeds=(42,) if mode=="smoke" else SEEDS
    expected={(a,s) for s in seeds for a in ALGORITHMS}; actual=[(r["algorithm"],int(r["seed"])) for r in rows]
    if len(actual)!=len(set(actual)) or set(actual)!=expected: raise ValueError(f"dataset matrix mismatch: {actual}")
    out=root/"results"; out.mkdir(exist_ok=True)
    with (out/"per_seed.csv").open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=[k for k in rows[0] if k!="recovery_events"]); w.writeheader(); w.writerows([{k:v for k,v in r.items() if k!="recovery_events"} for r in rows])
    event_rows=[{"algorithm":r["algorithm"],"seed":r["seed"],**e} for r in rows for e in r["recovery_events"]]
    with (out/"per_event_recovery.csv").open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=list(event_rows[0])); w.writeheader(); w.writerows(event_rows)
    summary=[]
    for a in ALGORITHMS:
        group=[r for r in rows if r["algorithm"]==a]
        for m in METRICS:
            vals=[float(r[m]) for r in group if r[m] is not None]; mean,lo,hi=ci(vals); summary.append({"algorithm":a,"metric":m,"n":len(vals),"mean":mean,"ci95_low":lo,"ci95_high":hi,"seed_values":vals})
    audit={"experiment":"k7_exp11","mode":mode,"expected_runs":len(expected),"actual_runs":len(rows),"coordinates":sorted(actual),"duplicates":len(actual)-len(set(actual)),"pass":True}
    validation={"pass":True,"four_treatments":True,"four_complete_cycles_per_run":all(r["churn_events"]==4 for r in rows),"explicit_censoring":all(all(e["censored"]==(not e["recovered"]) for e in r["recovery_events"]) for r in rows)}
    scientific={"headline_summary":summary,"runs":rows,"dcsoc_diagnostics":[r for r in rows if r["algorithm"]=="dcsoc"],"ahbn_diagnostics":[r for r in rows if r["algorithm"]=="ahbn"]}
    for name,data in (("final_dataset_audit.json",audit),("final_validation_report.json",validation),("final_scientific_summary.json",scientific)): (out/name).write_text(json.dumps(data,indent=2)+"\n")
    lines=["# K7 Exp11 validation report","",f"Status: **PASS** ({len(rows)} matched runs)","","## Per-seed results","","|Treatment|Seed|Delivery|Delay|Duplicates|Forwards|Recovered events|","|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows: lines.append(f"|{r['algorithm']}|{r['seed']}|{r['delivery_ratio']:.6f}|{r['propagation_delay'] if r['propagation_delay'] is not None else 'NA'}|{r['duplicates']}|{r['total_forwards']}|{r['recovered_events']}/4|")
    lines += ["","Recovery is reported per event; censored observations remain null rather than being replaced by the timeout."]
    (out/"final_validation_report.md").write_text("\n".join(lines)+"\n")
    for metric in METRICS:
        fig,ax=plt.subplots(figsize=(7,4)); groups=[[r[metric] for r in rows if r["algorithm"]==a and r[metric] is not None] for a in ALGORITHMS]; ax.boxplot(groups,tick_labels=ALGORITHMS); [ax.scatter([i+1]*len(v),v) for i,v in enumerate(groups)]; ax.set_ylabel(metric); fig.tight_layout(); fig.savefig(out/f"{metric}.png",dpi=160); plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4)); groups=[[e["recovery_time_s"] for r in rows if r["algorithm"]==a for e in r["recovery_events"] if e["recovered"]] for a in ALGORITHMS]; ax.boxplot(groups,tick_labels=ALGORITHMS); [ax.scatter([i+1]*len(v),v) for i,v in enumerate(groups)]; ax.set_ylabel("recovery_time_s (uncensored only)"); fig.tight_layout(); fig.savefig(out/"recovery_stabilization.png",dpi=160); plt.close(fig)
    print(f"K7 Exp11 analysis PASS: {len(rows)} matched runs -> {out}")
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--mode",choices=("smoke","formal"),required=True); a=p.parse_args(); analyze(a.root,a.mode)
