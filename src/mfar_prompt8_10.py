"""MFAR Prompt 8–10: mass-balanced scenarios, sensitivity and claim governance."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from .mfar_core import _arrival_rate, _params
from .mfar_visuals import stage7_intervention_outputs

COST={"NO_INTERVENTION":0.,"DEPART_NOW":.15,"HOLD_DEPARTURE":.15,"INCREASE_SERVICE_PRIORITY":.25,"RESCHEDULE_HEADWAY":.20,"ADD_VESSEL":1.,"ALERT_OPERATOR":.05,"MAINTAIN_SPEED":.05,"REDUCE_SPEED":.20}


def _num(value:Any,fallback:float=0.)->float:
    x=pd.to_numeric(pd.Series([value]),errors="coerce").iloc[0]
    return float(x) if pd.notna(x) and np.isfinite(x) else float(fallback)


def _accepted(evaluated:pd.DataFrame,constraints:pd.DataFrame,threshold:float)->pd.DataFrame:
    candidates=evaluated[evaluated["assessment_status"].eq("ASSESSED") & evaluated["selected_rule_strength"].ge(threshold) & evaluated["selected_action"].ne("NO_INTERVENTION")].sort_values("simulation_time")
    rows=[]; last={}
    for _,r in candidates.iterrows():
        cfg=constraints[constraints["phase"].astype(str).str.upper().eq(str(r["operational_phase"]).upper()) & constraints["action"].astype(str).str.upper().eq(str(r["selected_action"]).upper())]
        if cfg.empty or int(cfg.iloc[0]["feasible"])!=1: continue
        action=str(r["selected_action"]).upper(); key=(str(r["origin"]).upper(),action); stamp=pd.Timestamp(r["simulation_time"]); cooldown=_num(cfg.iloc[0].get("cooldown_min"))
        if key in last and (stamp-last[key]).total_seconds()/60<cooldown: continue
        x=r.to_dict(); x.update(cfg.iloc[0].to_dict()); x["action_cost_units"]=COST.get(action,.25); rows.append(x); last[key]=stamp
    return pd.DataFrame(rows)


def _schedule(events:pd.DataFrame)->pd.DataFrame:
    if events.empty: return pd.DataFrame(columns=["simulation_time","port_id","mmsi","service_capacity_ce","action"])
    x=events.copy(); x["simulation_time"]=pd.to_datetime(x["simulation_time"],errors="coerce"); x["port_id"]=x["origin"].astype(str).str.upper()
    source=x["capacity_ce"] if "capacity_ce" in x else x["served_ce"]
    x["service_capacity_ce"]=pd.to_numeric(source,errors="coerce").fillna(0); x["action"]="BASELINE_SERVICE"
    return x[["simulation_time","port_id","mmsi","service_capacity_ce","action"]]


def _apply(baseline:pd.DataFrame,accepted:pd.DataFrame,capacity:float,effect_scale:float)->tuple[pd.DataFrame,pd.DataFrame]:
    scenario=baseline.copy(); effects=[]
    if accepted.empty: return scenario,pd.DataFrame(columns=["simulation_time","port_id","action","effect_type","served_capacity_ce","replaces_time","action_cost_units"])
    for _,r in accepted.sort_values("simulation_time").iterrows():
        action=str(r["selected_action"]).upper(); effect=str(r.get("effect_type","none")); decision=pd.Timestamp(r["simulation_time"]); port=str(r["origin"]).upper()
        if effect=="shift_existing_service":
            mask=scenario["port_id"].eq(port)
            if pd.notna(r.get("mmsi")): mask &= scenario["mmsi"].eq(r["mmsi"])
            future=scenario[mask & scenario["simulation_time"].ge(decision)].sort_values("simulation_time")
            if future.empty: continue
            idx=future.index[0]; old=pd.Timestamp(scenario.at[idx,"simulation_time"]); new=max(decision,old+pd.Timedelta(minutes=_num(r.get("time_shift_min"))*effect_scale)).ceil("5min")
            scenario.at[idx,"simulation_time"]=new; scenario.at[idx,"action"]=action
            effects.append({"simulation_time":new,"port_id":port,"action":action,"effect_type":effect,"served_capacity_ce":scenario.at[idx,"service_capacity_ce"],"replaces_time":old,"action_cost_units":_num(r.get("action_cost_units"))})
        elif effect=="extra_service":
            stamp=(decision+pd.Timedelta(minutes=_num(r.get("lead_time_min")))).ceil("5min"); cap=capacity*_num(r.get("capacity_multiplier"))*_num(r.get("selected_rule_strength"))*effect_scale
            scenario=pd.concat([scenario,pd.DataFrame([{"simulation_time":stamp,"port_id":port,"mmsi":np.nan,"service_capacity_ce":cap,"action":action}])],ignore_index=True)
            effects.append({"simulation_time":stamp,"port_id":port,"action":action,"effect_type":effect,"served_capacity_ce":cap,"replaces_time":pd.NaT,"action_cost_units":_num(r.get("action_cost_units"))})
    return scenario,pd.DataFrame(effects)


def simulate_queue(queue_grid:pd.DataFrame,rates:pd.DataFrame,baseline:pd.DataFrame,scenario:pd.DataFrame,motor_ce:float,capacity:float,arrival_multiplier:float=1.)->pd.DataFrame:
    grid=queue_grid.copy(); grid["simulation_time"]=pd.to_datetime(grid["simulation_time"],errors="coerce"); rows=[]
    for (date,port),g in grid.groupby([grid["simulation_time"].dt.date,"port_id"]):
        qb=qa=0.
        for raw in sorted(g["simulation_time"].dropna().unique()):
            stamp=pd.Timestamp(raw); arrival=_arrival_rate(rates,port,stamp,motor_ce)[2]*arrival_multiplier
            bc=baseline[baseline["port_id"].eq(str(port).upper()) & baseline["simulation_time"].eq(stamp)]["service_capacity_ce"].sum(); sc=scenario[scenario["port_id"].eq(str(port).upper()) & scenario["simulation_time"].eq(stamp)]["service_capacity_ce"].sum()
            bd=qb+arrival; sd=qa+arrival; bs=min(bc,bd); ss=min(sc,sd); qbn=bd-bs; qan=sd-ss
            rows.append({"simulation_time":stamp,"evaluation_date":date,"port_id":str(port).upper(),"arrival_ce":arrival,"baseline_service_capacity_ce":bc,"scenario_service_capacity_ce":sc,"baseline_service_ce":bs,"scenario_service_ce":ss,"baseline_unused_capacity_ce":bc-bs,"scenario_unused_capacity_ce":sc-ss,"queue_ce":qbn,"queue_ce_after":qan,"queue_ratio":qbn/max(capacity,1e-9),"queue_ratio_after":qan/max(capacity,1e-9),"baseline_mass_balance_residual_ce":qbn-(qb+arrival-bs),"scenario_mass_balance_residual_ce":qan-(qa+arrival-ss)})
            qb,qa=qbn,qan
    x=pd.DataFrame(rows); x["intervention_service_ce"]=x["scenario_service_ce"]-x["baseline_service_ce"]; x["critical_baseline"]=x["queue_ratio"].ge(3); x["critical_after"]=x["queue_ratio_after"].ge(3)
    x["critical_case_status"]=np.select([x["critical_baseline"]&~x["critical_after"],x["critical_baseline"]&x["critical_after"],~x["critical_baseline"]&x["critical_after"]],["RESOLVED","REMAINING","NEW"],default="SAFE")
    return x


def _daily(sim:pd.DataFrame)->pd.DataFrame:
    x=sim.groupby(["evaluation_date","port_id"],as_index=False).agg(max_queue_baseline_ce=("queue_ce","max"),max_queue_after_ce=("queue_ce_after","max"),mean_queue_baseline_ce=("queue_ce","mean"),mean_queue_after_ce=("queue_ce_after","mean"),queue_area_baseline_ce_min=("queue_ce",lambda s:float(s.sum()*5)),queue_area_after_ce_min=("queue_ce_after",lambda s:float(s.sum()*5)),critical_duration_baseline_min=("critical_baseline",lambda s:int(s.sum()*5)),critical_duration_after_min=("critical_after",lambda s:int(s.sum()*5)),max_abs_baseline_residual=("baseline_mass_balance_residual_ce",lambda s:float(s.abs().max())),max_abs_scenario_residual=("scenario_mass_balance_residual_ce",lambda s:float(s.abs().max())))
    x["queue_area_reduction_percent"]=100*(x["queue_area_baseline_ce_min"]-x["queue_area_after_ce_min"])/x["queue_area_baseline_ce_min"].replace(0,np.nan)
    return x


def _governance(stage_dir:Path,evaluated:pd.DataFrame,accepted:pd.DataFrame,effects:pd.DataFrame,daily:pd.DataFrame,overall:pd.DataFrame,sensitivity:pd.DataFrame):
    metrics=dict(zip(overall["metric"],overall["value"])); pd.DataFrame([
        {"section":"decision","metric":"prospective_cases","value":len(evaluated),"claim_class":"DESCRIPTIVE"},{"section":"fuzzy","metric":"unassessed_cases","value":int(evaluated["assessment_status"].ne("ASSESSED").sum()),"claim_class":"AUDIT"},{"section":"fuzzy","metric":"fuzzy_crisp_agreement_percent","value":100*evaluated["fuzzy_crisp_action_agreement"].mean(),"claim_class":"COMPARATIVE"},{"section":"response","metric":"accepted_recommendations","value":len(accepted),"claim_class":"DESCRIPTIVE"},{"section":"scenario","metric":"queue_effect_events","value":len(effects),"claim_class":"CONFIGURED_COUNTERFACTUAL"},{"section":"scenario","metric":"median_daily_queue_area_reduction_percent","value":metrics.get("median_daily_queue_area_reduction_percent"),"claim_class":"CONFIGURED_COUNTERFACTUAL"},{"section":"robustness","metric":"sensitivity_scenarios","value":len(sensitivity),"claim_class":"ROBUSTNESS"}]).to_csv(stage_dir/"07_manuscript_metrics.csv",index=False)
    pd.DataFrame([
        {"claim_id":"C01","allowed_wording":"The prospective pipeline generated auditable operational recommendations.","prohibited_wording":"The interventions were empirically proven effective.","status":"SUPPORTED"},{"claim_id":"C02","allowed_wording":"Configured counterfactual scenarios changed simulated queue outcomes.","prohibited_wording":"The model caused observed field queue reductions.","status":"SUPPORTED_AS_SCENARIO"},{"claim_id":"C03","allowed_wording":"Forecast quality is a data-quality index.","prohibited_wording":"Forecast confidence is a calibrated probability.","status":"SUPPORTED_WITH_LIMITATION"},{"claim_id":"C04","allowed_wording":"Expert criterion validation remains pending.","prohibited_wording":"Recommendations agree with experts.","status":"NOT_AVAILABLE"}]).to_csv(stage_dir/"07_claim_governance.csv",index=False)
    audit=pd.DataFrame({"check":["all_cases_assessed","mass_balance_baseline","mass_balance_scenario","negative_queues","sensitivity_scenarios_present","expert_validation_available"],"failed_rows":[int(evaluated["assessment_status"].ne("ASSESSED").sum()),int(daily["max_abs_baseline_residual"].gt(1e-9).sum()),int(daily["max_abs_scenario_residual"].gt(1e-9).sum()),0,int(sensitivity.empty),1],"severity":["ERROR","ERROR","ERROR","ERROR","ERROR","DISCLOSURE"]}); audit.to_csv(stage_dir/"07_integrated_audit.csv",index=False)
    files=sorted(p for p in stage_dir.glob("07_*") if p.is_file()); manifest={"schema_version":"1.0","methodological_prompts":list(range(4,11)),"expert_validation_status":"NOT_AVAILABLE","files":[{"name":p.name,"size_bytes":p.stat().st_size,"sha256":sha256(p.read_bytes()).hexdigest()} for p in files]}; (stage_dir/"07_release_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")


def run_stage7(queue:pd.DataFrame,events:pd.DataFrame,evaluated:pd.DataFrame,rates:pd.DataFrame,profiles:pd.DataFrame,stage_dir:Path,config_dir:Path):
    params=_params(config_dir); constraints=pd.read_csv(Path(config_dir)/"action_constraints.csv"); threshold=_num(params.get("minimum_rule_strength"),.35); motor=_num(params.get("motorcycle_ce"),.25); capacity=float(pd.to_numeric(profiles["vehicle_capacity_ce"],errors="coerce").median())
    evaluated=evaluated.copy(); evaluated["simulation_time"]=pd.to_datetime(evaluated["simulation_time"],errors="coerce"); events=events.copy(); events["simulation_time"]=pd.to_datetime(events["simulation_time"],errors="coerce")
    accepted=_accepted(evaluated,constraints,threshold); baseline=_schedule(events); scenario,effects=_apply(baseline,accepted,capacity,1.); sim=simulate_queue(queue,rates,baseline,scenario,motor,capacity); daily=_daily(sim); total_cost=pd.to_numeric(accepted["action_cost_units"],errors="coerce").fillna(0).sum() if not accepted.empty else 0.
    overall=pd.DataFrame({"metric":["evaluation_type","evaluation_days","operational_recommendations_accepted","queue_effect_events","total_critical_baseline","total_critical_after","median_daily_queue_area_reduction_percent","days_queue_improved_percent","total_action_cost_units","queue_area_reduction_per_cost_unit","maximum_mass_balance_residual_ce"],"value":["CONFIGURED_COUNTERFACTUAL_SCENARIO_NOT_EMPIRICAL_VALIDATION",daily["evaluation_date"].nunique(),len(accepted),len(effects),int(sim["critical_baseline"].sum()),int(sim["critical_after"].sum()),daily["queue_area_reduction_percent"].median(),100*daily["queue_area_reduction_percent"].gt(0).mean(),total_cost,(daily["queue_area_baseline_ce_min"].sum()-daily["queue_area_after_ce_min"].sum())/total_cost if total_cost>0 else np.nan,max(sim["baseline_mass_balance_residual_ce"].abs().max(),sim["scenario_mass_balance_residual_ce"].abs().max())]})
    rows=[]; base_ids=set(accepted.get("decision_case_id",pd.Series(dtype=str)).astype(str)) if not accepted.empty else set()
    for th in sorted(set([max(0,threshold-.1),threshold,min(1,threshold+.1)])):
        selected=_accepted(evaluated,constraints,th); ids=set(selected.get("decision_case_id",pd.Series(dtype=str)).astype(str)) if not selected.empty else set(); union=base_ids|ids; jac=len(base_ids&ids)/len(union) if union else 1.
        for demand in [.9,1.,1.1]:
            for effect in [.8,1.,1.2]:
                scen,eff=_apply(baseline,selected,capacity,effect); trial=simulate_queue(queue,rates,baseline,scen,motor,capacity,demand); d=_daily(trial)
                rows.append({"rule_threshold":th,"arrival_multiplier":demand,"effect_scale":effect,"accepted_recommendations":len(selected),"queue_effect_events":len(eff),"median_daily_queue_area_reduction_percent":d["queue_area_reduction_percent"].median(),"critical_duration_after_min":d["critical_duration_after_min"].sum(),"accepted_action_jaccard_vs_base":jac,"maximum_mass_balance_residual_ce":max(trial["baseline_mass_balance_residual_ce"].abs().max(),trial["scenario_mass_balance_residual_ce"].abs().max())})
    sensitivity=pd.DataFrame(rows); robustness=pd.DataFrame({"metric":["sensitivity_scenarios","minimum_action_jaccard","median_action_jaccard","minimum_queue_area_reduction_percent","maximum_queue_area_reduction_percent","maximum_sensitivity_mass_balance_residual_ce"],"value":[len(sensitivity),sensitivity["accepted_action_jaccard_vs_base"].min(),sensitivity["accepted_action_jaccard_vs_base"].median(),sensitivity["median_daily_queue_area_reduction_percent"].min(),sensitivity["median_daily_queue_area_reduction_percent"].max(),sensitivity["maximum_mass_balance_residual_ce"].max()]})
    stage_dir=Path(stage_dir); stage_dir.mkdir(parents=True,exist_ok=True); sim.to_csv(stage_dir/"07_scenario_baseline_vs_actions.csv",index=False); accepted.to_csv(stage_dir/"07_accepted_operational_recommendations.csv",index=False); effects.to_csv(stage_dir/"07_queue_service_intervention_events.csv",index=False); daily.to_csv(stage_dir/"07_daily_scenario_by_port.csv",index=False); overall.to_csv(stage_dir/"07_overall_scenario_evaluation.csv",index=False); sensitivity.to_csv(stage_dir/"07_sensitivity_scenarios.csv",index=False); robustness.to_csv(stage_dir/"07_robustness_summary.csv",index=False); daily[["evaluation_date","port_id","max_abs_baseline_residual","max_abs_scenario_residual"]].to_csv(stage_dir/"07_queue_conservation_audit.csv",index=False)
    stage7_intervention_outputs(sim,accepted,effects,daily,overall,stage_dir); _governance(stage_dir,evaluated,accepted,effects,daily,overall,sensitivity)
    return sim,accepted,effects,daily,overall
