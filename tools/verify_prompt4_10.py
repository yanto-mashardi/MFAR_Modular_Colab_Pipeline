#!/usr/bin/env python3
"""Verify MFAR Prompt 4–10 methodological contracts and write acceptance records."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

CANONICAL={"stage_output/stage_01/01_ais_clean.csv":32245,"stage_output/stage_01/01_ais_rejected.csv":113,"stage_output/stage_02/02_vessel_interpolated_grid.csv":40328,"stage_output/stage_02/02_interpolation_rejected_grid.csv":61408,"stage_output/stage_03/03_input_state_enhanced.csv":40328}


def rows(path:Path)->int: return len(pd.read_csv(path,low_memory=False))
def metric(frame:pd.DataFrame,name:str):
    x=frame.loc[frame["metric"].eq(name),"value"]
    return x.iloc[0] if len(x) else None
def numeric(value): return pd.to_numeric(pd.Series([value]),errors="coerce").iloc[0]

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--drive-root",type=Path,required=True); p.add_argument("--validation-root",type=Path,required=True); p.add_argument("--json",type=Path,required=True); a=p.parse_args(); root=a.drive_root; checks=[]
    def check(prompt,name,passed,actual=None,expected=None,severity="ERROR",detail=""):
        checks.append({"prompt":prompt,"check":name,"status":"PASS" if bool(passed) else ("DISCLOSURE" if severity=="DISCLOSURE" else "FAIL"),"actual":actual,"expected":expected,"severity":severity,"detail":detail})
    for rel,expected in CANONICAL.items():
        actual=rows(root/rel) if (root/rel).is_file() else None; check(10,f"unchanged_rows::{rel}",actual==expected,actual,expected)

    s4=root/"stage_output/stage_04"; s5=root/"stage_output/stage_05"; s6=root/"stage_output/stage_06"; s7=root/"stage_output/stage_07"
    forecast=pd.read_csv(s4/"04_fuzzy_input.csv",low_memory=False); qsum=pd.read_csv(s4/"04_quality_index_summary.csv"); berth=pd.read_csv(s4/"04_berth_availability_audit.csv"); eta=pd.read_csv(s4/"04_eta_benchmark_summary.csv"); fsum=pd.read_csv(s4/"04_forecast_summary.csv")
    quality_cols=["ais_continuity_score","trip_history_support_score","turnaround_prior_support_score","berth_projection_completeness_score","forecast_quality_index"]
    check(4,"prospective_case_count_preserved",len(forecast)==543,len(forecast),543)
    check(4,"quality_components_present",all(c in forecast for c in quality_cols),[c for c in quality_cols if c not in forecast],"none")
    check(4,"quality_index_bounded",forecast["forecast_quality_index"].between(0,1).all(),int((~forecast["forecast_quality_index"].between(0,1)).sum()),0)
    semantics=forecast["forecast_confidence_semantics"].astype(str).unique().tolist(); check(4,"quality_semantics_not_probability",semantics==["DATA_QUALITY_INDEX_NOT_CALIBRATED_PROBABILITY"],semantics,"DATA_QUALITY_INDEX_NOT_CALIBRATED_PROBABILITY")
    differs=not np.allclose(pd.to_numeric(forecast["forecast_quality_index"],errors="coerce"),pd.to_numeric(forecast["legacy_forecast_confidence"],errors="coerce"),equal_nan=True); check(4,"legacy_gap_product_replaced",differs,differs,True)
    check(4,"quality_calibration_written",len(qsum)>0,len(qsum),">0")

    coverage=pd.read_csv(s5/"05_membership_domain_coverage.csv"); boundary=pd.read_csv(s5/"05_membership_boundary_tests.csv"); audit5=pd.read_csv(s5/"05_fuzzification_audit.csv"); rules=pd.read_csv(s6/"06_fuzzy_rule_catalog.csv"); evaluated=pd.read_csv(s6/"06_rule_evaluation.csv",low_memory=False); audit6=pd.read_csv(s6/"06_rule_coverage_audit.csv"); monotonic=pd.read_csv(s6/"06_monotonic_queue_boundary_test.csv")
    check(5,"fuzzification_audit_zero",pd.to_numeric(audit5["failed_rows"],errors="coerce").fillna(0).sum()==0,int(pd.to_numeric(audit5["failed_rows"],errors="coerce").fillna(0).sum()),0)
    check(5,"observed_membership_domain_complete",pd.to_numeric(coverage["zero_domain_coverage_cases"],errors="coerce").fillna(0).sum()==0,int(pd.to_numeric(coverage["zero_domain_coverage_cases"],errors="coerce").fillna(0).sum()),0)
    check(5,"membership_boundaries_complete",pd.to_numeric(boundary["uncovered_grid_points"],errors="coerce").fillna(0).sum()==0,int(pd.to_numeric(boundary["uncovered_grid_points"],errors="coerce").fillna(0).sum()),0)
    fallback=set(rules.loc[rules.get("rule_type",pd.Series(index=rules.index,dtype=str)).astype(str).eq("FALLBACK"),"rule_id"].astype(str)); check(5,"fallback_rules_configured",fallback=={"R12","R13","R14","R15"},sorted(fallback),["R12","R13","R14","R15"])
    check(5,"zero_rule_coverage_removed",evaluated["raw_rule_coverage_count"].eq(0).sum()==0,int(evaluated["raw_rule_coverage_count"].eq(0).sum()),0)
    check(5,"unassessed_cases_explicit_and_zero",evaluated["assessment_status"].ne("ASSESSED").sum()==0,int(evaluated["assessment_status"].ne("ASSESSED").sum()),0)

    berth_fail=int(pd.to_numeric(berth["failed_rows"],errors="coerce").fillna(0).sum()); check(6,"berth_gate_audit_zero",berth_fail==0,berth_fail,0)
    wait=pd.to_numeric(forecast["predicted_wait_min"],errors="coerce"); availability=pd.to_numeric(forecast["berth_availability_at_eta"],errors="coerce")
    check(6,"wait_nonnegative",wait.ge(0).all(),int(wait.lt(0).sum()),0); check(6,"availability_binary",availability.isin([0,1]).all(),int((~availability.isin([0,1])).sum()),0)
    incons=int((availability.eq(1)&wait.gt(0)).sum()+(availability.eq(0)&wait.le(0)).sum()); check(6,"availability_wait_consistent",incons==0,incons,0)
    positive=int(wait.gt(0).sum()); check(6,"positive_wait_support",True,positive,"reported",severity="DISCLOSURE",detail="NO_POSITIVE_WAIT_SUPPORT" if positive==0 else "POSITIVE_WAIT_OBSERVED")
    violations=int(pd.to_numeric(monotonic["delta_score"],errors="coerce").dropna().lt(-1e-12).sum()); check(6,"operational_alert_monotonic_in_queue",violations==0,violations,0)
    agreement=100*evaluated["fuzzy_crisp_action_agreement"].astype(str).str.lower().isin(["true","1"]).mean(); check(6,"fuzzy_crisp_comparison_available",0<=agreement<=100,agreement,"0..100")

    eta_cases=numeric(metric(eta,"eta_interval_cases")); model=numeric(metric(eta,"eta_model_mae_min")); base=numeric(metric(eta,"eta_fixed_baseline_mae_min")); skill=numeric(metric(eta,"eta_skill_vs_fixed")); corrected=numeric(metric(eta,"eta_online_corrected_mae_min")); coverage_value=numeric(metric(eta,"eta_interval_empirical_coverage"))
    check(7,"eta_benchmark_cases_present",pd.notna(model) and pd.notna(base),{"model_mae":model,"baseline_mae":base},"finite")
    check(7,"eta_skill_score_finite",pd.notna(skill) and np.isfinite(skill),skill,"finite")
    check(7,"online_corrected_mae_present",pd.notna(corrected),corrected,"finite")
    check(7,"prediction_interval_cases_present",pd.notna(eta_cases) and eta_cases>0,eta_cases,">0")
    check(7,"interval_coverage_bounded",pd.notna(coverage_value) and 0<=coverage_value<=1,coverage_value,"0..1")
    history=pd.to_numeric(forecast["online_error_history_count"],errors="coerce"); ordered=forecast.assign(_t=pd.to_datetime(forecast["decision_time"],errors="coerce"),_h=history).sort_values(["_t","mmsi"]); check(7,"online_history_count_non_decreasing",ordered["_h"].diff().fillna(0).ge(0).all(),int(ordered["_h"].diff().fillna(0).lt(0).sum()),0)

    sim=pd.read_csv(s7/"07_scenario_baseline_vs_actions.csv",low_memory=False); daily=pd.read_csv(s7/"07_daily_scenario_by_port.csv"); overall=pd.read_csv(s7/"07_overall_scenario_evaluation.csv"); sensitivity=pd.read_csv(s7/"07_sensitivity_scenarios.csv"); robust=pd.read_csv(s7/"07_robustness_summary.csv"); integrated=pd.read_csv(s7/"07_integrated_audit.csv"); claims=pd.read_csv(s7/"07_claim_governance.csv")
    residual=max(pd.to_numeric(sim["baseline_mass_balance_residual_ce"],errors="coerce").abs().max(),pd.to_numeric(sim["scenario_mass_balance_residual_ce"],errors="coerce").abs().max()); check(8,"queue_mass_balance",residual<=1e-9,residual,"<=1e-9")
    negative=int((pd.to_numeric(sim["queue_ce"],errors="coerce")<0).sum()+(pd.to_numeric(sim["queue_ce_after"],errors="coerce")<0).sum()); check(8,"queues_nonnegative",negative==0,negative,0)
    capacity_bad=int((pd.to_numeric(sim["baseline_service_ce"],errors="coerce")>pd.to_numeric(sim["baseline_service_capacity_ce"],errors="coerce")+1e-9).sum()+(pd.to_numeric(sim["scenario_service_ce"],errors="coerce")>pd.to_numeric(sim["scenario_service_capacity_ce"],errors="coerce")+1e-9).sum()); check(8,"actual_service_not_above_capacity",capacity_bad==0,capacity_bad,0)
    evaluation_type=str(metric(overall,"evaluation_type")); check(8,"counterfactual_wording",evaluation_type=="CONFIGURED_COUNTERFACTUAL_SCENARIO_NOT_EMPIRICAL_VALIDATION",evaluation_type,"CONFIGURED_COUNTERFACTUAL_SCENARIO_NOT_EMPIRICAL_VALIDATION")

    check(9,"full_factorial_sensitivity",len(sensitivity)==27,len(sensitivity),27)
    j=pd.to_numeric(sensitivity["accepted_action_jaccard_vs_base"],errors="coerce"); check(9,"action_stability_bounded",j.between(0,1).all(),int((~j.between(0,1)).sum()),0)
    sr=pd.to_numeric(sensitivity["maximum_mass_balance_residual_ce"],errors="coerce").abs().max(); check(9,"sensitivity_mass_balance",sr<=1e-9,sr,"<=1e-9")
    check(9,"robustness_summary_written",len(robust)>=6,len(robust),">=6")

    blocking=integrated[integrated["severity"].astype(str).str.upper().eq("ERROR")]; blocking_fail=int(pd.to_numeric(blocking["failed_rows"],errors="coerce").fillna(0).sum()); check(10,"integrated_blocking_audit_zero",blocking_fail==0,blocking_fail,0)
    disclosure=integrated[integrated["severity"].astype(str).str.upper().eq("DISCLOSURE")]; check(10,"expert_validation_disclosed",len(disclosure)>0 and claims["status"].astype(str).eq("NOT_AVAILABLE").any(),claims["status"].tolist(),"NOT_AVAILABLE")
    check(10,"release_manifest_written",(s7/"07_release_manifest.json").is_file(),(s7/"07_release_manifest.json").is_file(),True)
    check(10,"manuscript_metrics_written",(s7/"07_manuscript_metrics.csv").is_file(),(s7/"07_manuscript_metrics.csv").is_file(),True)

    report={"schema_version":"1.0","generated_at_utc":datetime.now(timezone.utc).isoformat(),"status":"PASS" if all(c["status"]!="FAIL" for c in checks) else "FAIL","checks":checks,"diagnostics":{"prospective_cases":len(forecast),"positive_wait_cases":positive,"fuzzy_crisp_agreement_percent":agreement,"eta_model_mae_min":model,"eta_fixed_baseline_mae_min":base,"eta_online_corrected_mae_min":corrected,"eta_skill_vs_fixed":skill,"eta_interval_empirical_coverage":coverage_value,"accepted_recommendations":numeric(metric(overall,"operational_recommendations_accepted")),"queue_effect_events":numeric(metric(overall,"queue_effect_events")),"median_daily_queue_area_reduction_percent":numeric(metric(overall,"median_daily_queue_area_reduction_percent")),"sensitivity_scenarios":len(sensitivity),"minimum_action_jaccard":j.min(),"expert_validation_status":"NOT_AVAILABLE"}}
    a.json.parent.mkdir(parents=True,exist_ok=True); a.json.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8"); a.validation_root.mkdir(parents=True,exist_ok=True)
    titles={4:"Forecast quality index",5:"Fuzzy coverage and UNASSESSED handling",6:"Berth gate and monotonic alert logic",7:"ETA benchmarks and prospective intervals",8:"Mass-balanced scenario simulator",9:"Sensitivity and robustness",10:"Integrated audit and claim governance"}
    for prompt in range(4,11):
        subset=[c for c in checks if c["prompt"]==prompt]; status="PASS" if all(c["status"]!="FAIL" for c in subset) else "FAIL"; folder=a.validation_root/f"prompt{prompt}"; folder.mkdir(parents=True,exist_ok=True); lines=[f"# Prompt {prompt} Acceptance Record","",f"- Scope: {titles[prompt]}",f"- Overall status: **{status}**","","| Check | Status | Actual | Expected |","|---|---:|---:|---:|"]
        for c in subset: lines.append(f"| `{c['check']}` | {c['status']} | {c.get('actual','')} | {c.get('expected','')} |")
        if prompt==6: lines += ["","## Support disclosure","",f"Positive predicted-wait cases: **{positive}**. Zero support is reported as a limitation and is not converted into artificial variation."]
        if prompt==10: lines += ["","## Claim boundary","","Expert criterion validation remains `NOT_AVAILABLE` because no expert-labeled decision dataset was supplied. Scenario outcomes are configured counterfactual results, not empirical causal effects."]
        (folder/f"PROMPT_{prompt}_ACCEPTANCE.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,default=str)); return 0 if report["status"]=="PASS" else 1

if __name__=="__main__": raise SystemExit(main())
