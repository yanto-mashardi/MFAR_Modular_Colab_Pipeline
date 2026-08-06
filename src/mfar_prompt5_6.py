"""MFAR Prompt 5 and 6: fuzzy coverage, explicit assessment status and monotonic alerts."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from .mfar_core import _membership, run_stage5 as _base_stage5
from .mfar_visuals import stage6_rule_outputs


def _num(value: Any, fallback: float=0.) -> float:
    x=pd.to_numeric(pd.Series([value]),errors="coerce").iloc[0]
    return float(x) if pd.notna(x) and np.isfinite(x) else float(fallback)


def run_stage5(forecast: pd.DataFrame, stage_dir: Path, config_dir: Path):
    definitions=pd.read_csv(Path(config_dir)/"membership_parameters.csv")
    inputs=definitions[definitions.get("scope",pd.Series("input",index=definitions.index)).astype(str).str.lower().ne("output")].copy()
    source=forecast.copy(); columns=sorted(inputs["input_column"].astype(str).unique())
    missing=pd.DataFrame({c:pd.to_numeric(source[c] if c in source else pd.Series(np.nan,index=source.index),errors="coerce").isna() for c in columns},index=source.index)
    source["fuzzy_input_missing_count"]=missing.sum(axis=1)
    source["fuzzy_input_status"]=np.where(source["fuzzy_input_missing_count"].eq(0),"COMPLETE","INCOMPLETE")
    out,used,base_audit=_base_stage5(source,stage_dir,config_dir)
    for c in columns:
        mu=inputs.loc[inputs["input_column"].eq(c),"membership_column"].astype(str).tolist()
        if missing[c].any(): out.loc[missing[c],mu]=np.nan
    coverage=[]; boundary=[]
    for c,defs in inputs.groupby("input_column"):
        mu=defs["membership_column"].astype(str).tolist(); degree=out[mu].max(axis=1,skipna=True)
        coverage.append({"input_column":c,"cases":len(out),"membership_count":len(mu),"missing_input_cases":int(missing[str(c)].sum()),"zero_domain_coverage_cases":int(degree.fillna(0).le(0).sum()),"minimum_max_membership":degree.min()})
        endpoints=pd.to_numeric(defs[["a","b","c","d"]].stack(),errors="coerce").dropna()
        observed=pd.to_numeric(source[c],errors="coerce").dropna()
        upper=max(float(endpoints.max()) if len(endpoints) else 1.,float(observed.quantile(.99)) if len(observed) else 0.,1.)
        x=np.linspace(0,upper*1.25,501); curves=[]
        for _,r in defs.iterrows(): curves.append(_membership(x,str(r["function"]),_num(r.get("a")),_num(r.get("b")),_num(r.get("c")),_num(r.get("d"))))
        maximum=np.max(np.vstack(curves),axis=0)
        boundary.append({"input_column":c,"grid_points":len(x),"uncovered_grid_points":int((maximum<=0).sum()),"minimum_coverage":maximum.min(),"maximum_test_value":x.max()})
    coverage=pd.DataFrame(coverage); boundary=pd.DataFrame(boundary)
    audit=pd.concat([base_audit,pd.DataFrame({"check":["incomplete_fuzzy_input_cases","observed_domain_uncovered_cases","boundary_grid_uncovered_points"],"failed_rows":[int(source["fuzzy_input_missing_count"].gt(0).sum()),int(coverage["zero_domain_coverage_cases"].sum()),int(boundary["uncovered_grid_points"].sum())]})],ignore_index=True)
    stage_dir=Path(stage_dir); out.to_csv(stage_dir/"05_fuzzy_memberships.csv",index=False); coverage.to_csv(stage_dir/"05_membership_domain_coverage.csv",index=False); boundary.to_csv(stage_dir/"05_membership_boundary_tests.csv",index=False); audit.to_csv(stage_dir/"05_fuzzification_audit.csv",index=False)
    return out,used,audit


@dataclass(frozen=True)
class Fired:
    rule_id:str; action:str; consequence:str; raw:float; feasible_strength:float; priority:int; feasible:bool


def _feasible(constraints:pd.DataFrame,phase:str,action:str)->bool:
    x=constraints[constraints["phase"].astype(str).str.upper().eq(str(phase).upper()) & constraints["action"].astype(str).str.upper().eq(str(action).upper())]
    return bool(len(x) and int(x.iloc[0]["feasible"])==1)


def _fire(case:pd.Series,rules:pd.DataFrame,constraints:pd.DataFrame,crisp:bool=False)->list[Fired]:
    result=[]; phase=str(case.get("operational_phase","UNKNOWN"))
    for _,r in rules.iterrows():
        ants=[str(r[c]) for c in ["antecedent_1","antecedent_2","antecedent_3","antecedent_4"] if c in r and pd.notna(r[c]) and str(r[c]).strip()]
        vals=[]
        for a in ants:
            x=pd.to_numeric(pd.Series([case.get(a)]),errors="coerce").iloc[0]
            vals.append(np.nan if pd.isna(x) else float(x>=.5) if crisp else float(x))
        raw=0. if not vals or any(pd.isna(vals)) else (max(vals) if str(r["operator"]).upper()=="MAX" else min(vals))
        raw*=_num(r.get("weight"),1.); action=str(r["response"]).upper(); ok=_feasible(constraints,phase,action)
        result.append(Fired(str(r["rule_id"]),action,str(r["consequence"]),raw,raw if ok else 0.,int(_num(r.get("priority"))),ok))
    return result


def _select(items:list[Fired])->tuple[float,int,str,str]:
    scores={}
    for x in items:
        candidate=(x.feasible_strength,x.priority,x.rule_id)
        if x.action not in scores or candidate>scores[x.action]: scores[x.action]=candidate
    ranked=sorted(((s,p,a,r) for a,(s,p,r) in scores.items()),reverse=True)
    return ranked[0] if ranked and ranked[0][0]>0 else (0.,0,"NO_INTERVENTION","NO_FEASIBLE_RULE")


def operational_alert_score(case:pd.Series)->float:
    q=np.clip(_num(case.get("origin_queue_ratio"))/3,0,1); unavailable=1-np.clip(_num(case.get("berth_availability_at_eta"),1),0,1)
    wait=np.clip(_num(case.get("predicted_wait_min"))/40,0,1); adverse=1-np.clip(_num(case.get("forecast_quality_index",case.get("forecast_confidence",.5))),0,1)
    gap=np.clip(_num(case.get("service_gap_min"))/120,0,1); short=np.clip(_num(case.get("capacity_shortfall_ratio"))/2,0,1)
    return float(100*np.clip(.45*q+.15*unavailable+.10*wait+.10*adverse+.10*gap+.10*short,0,1))


def _label(score:float)->str:
    return "Normal" if score<25 else "Watch" if score<50 else "Warning" if score<75 else "Critical"


def run_stage6(memberships:pd.DataFrame,stage_dir:Path,config_dir:Path):
    rules=pd.read_csv(Path(config_dir)/"fuzzy_rules.csv"); constraints=pd.read_csv(Path(config_dir)/"action_constraints.csv"); definitions=pd.read_csv(Path(config_dir)/"membership_parameters.csv")
    outputs=definitions[definitions.get("scope",pd.Series("input",index=definitions.index)).astype(str).str.lower().eq("output")]
    universe=np.linspace(0,100,1001); curves={str(r["membership_column"]):_membership(universe,str(r["function"]),_num(r.get("a")),_num(r.get("b")),_num(r.get("c")),_num(r.get("d"))) for _,r in outputs.iterrows()}
    rows=[]
    for _,case in memberships.reset_index(drop=True).iterrows():
        fuzzy=_fire(case,rules,constraints); crisp=_fire(case,rules,constraints,True); raw_count=sum(x.raw>0 for x in fuzzy); incomplete=_num(case.get("fuzzy_input_missing_count"))>0
        status="UNASSESSED_INCOMPLETE_INPUT" if incomplete else "UNASSESSED_NO_RULE_COVERAGE" if raw_count==0 else "ASSESSED"
        selected=_select(fuzzy) if status=="ASSESSED" else (0.,0,"NO_INTERVENTION","UNASSESSED"); crisp_selected=_select(crisp) if status=="ASSESSED" else (0.,0,"NO_INTERVENTION","UNASSESSED")
        aggregate=np.zeros_like(universe); consequences={}
        for x in fuzzy:
            key=f"mu_risk_{x.consequence.lower()}"
            if key in curves: aggregate=np.maximum(aggregate,np.minimum(x.raw,curves[key])); consequences[x.consequence]=max(consequences.get(x.consequence,0),x.raw)
        area=float(np.trapezoid(aggregate,universe)); mamdani=float(np.trapezoid(universe*aggregate,universe)/area) if area>0 else np.nan; score=operational_alert_score(case) if status=="ASSESSED" else np.nan
        record={f"firing_{x.rule_id}":x.feasible_strength for x in fuzzy}; record.update({f"raw_firing_{x.rule_id}":x.raw for x in fuzzy}); record.update({"assessment_status":status,"raw_rule_coverage_count":raw_count,"feasible_rule_coverage_count":sum(x.feasible_strength>0 for x in fuzzy),"selected_rule_strength":selected[0],"selected_action":selected[2],"dominant_rule":selected[3],"crisp_selected_action":crisp_selected[2],"fuzzy_crisp_action_agreement":selected[2]==crisp_selected[2],"phase_constraint_applied":True,"infeasible_rule_count":sum((not x.feasible) and x.raw>0 for x in fuzzy),"mamdani_risk_score_raw":mamdani,"mamdani_risk_score":mamdani,"mamdani_aggregate_area":area,"dominant_risk_consequence":max(consequences,key=consequences.get) if consequences else "UNASSESSED","operational_alert_score":score,"operational_alert_label":_label(score) if pd.notna(score) else "UNASSESSED","defuzzification_method":"CENTROID_DIAGNOSTIC_ONLY","decision_score_semantics":"MONOTONIC_OPERATIONAL_ALERT_SCORE"}); rows.append(record)
    out=pd.concat([memberships.reset_index(drop=True),pd.DataFrame(rows)],axis=1); stage_dir=Path(stage_dir); stage_dir.mkdir(parents=True,exist_ok=True)
    out.to_csv(stage_dir/"06_rule_evaluation.csv",index=False); rules.to_csv(stage_dir/"06_fuzzy_rule_catalog.csv",index=False); constraints.to_csv(stage_dir/"06_action_constraints_used.csv",index=False); outputs.to_csv(stage_dir/"06_output_membership_configuration_used.csv",index=False)
    summary=pd.DataFrame([{"rule_id":rid,"raw_active_rows":int(out[f"raw_firing_{rid}"].gt(0).sum()),"active_rows":int(out[f"firing_{rid}"].gt(0).sum()),"mean_firing_strength":out[f"firing_{rid}"].mean(),"max_firing_strength":out[f"firing_{rid}"].max()} for rid in rules["rule_id"].astype(str)])
    summary.to_csv(stage_dir/"06_rule_firing_summary.csv",index=False)
    fcols=[f"firing_{r}" for r in rules["rule_id"].astype(str)]; pd.DataFrame({"decision_case_id":out.get("decision_case_id",pd.Series(range(len(out)))),"positive_feasible_rules":out[fcols].gt(0).sum(axis=1),"assessment_status":out["assessment_status"],"selected_action":out["selected_action"]}).to_csv(stage_dir/"06_rule_conflict_matrix.csv",index=False)
    grid=pd.DataFrame({"origin_queue_ratio":np.linspace(0,5,101),"berth_availability_at_eta":1.,"predicted_wait_min":0.,"forecast_quality_index":.8,"service_gap_min":45.,"capacity_shortfall_ratio":0.}); grid["operational_alert_score"]=grid.apply(operational_alert_score,axis=1); grid["delta_score"]=grid["operational_alert_score"].diff(); grid.to_csv(stage_dir/"06_monotonic_queue_boundary_test.csv",index=False)
    audit=pd.DataFrame({"check":["unassessed_cases","zero_rule_coverage_cases","invalid_selected_strength","queue_monotonicity_violations","missing_alert_score_for_assessed_case"],"failed_rows":[int(out["assessment_status"].ne("ASSESSED").sum()),int(out["raw_rule_coverage_count"].eq(0).sum()),int((~out["selected_rule_strength"].between(0,1)).sum()),int(grid["delta_score"].dropna().lt(-1e-12).sum()),int((out["assessment_status"].eq("ASSESSED")&out["operational_alert_score"].isna()).sum())]}); audit.to_csv(stage_dir/"06_rule_coverage_audit.csv",index=False)
    stage6_rule_outputs(out,rules,summary,stage_dir)
    return out,rules,summary
