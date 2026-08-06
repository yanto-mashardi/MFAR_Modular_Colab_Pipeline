"""MFAR Prompt 4, 6 and 7: quality semantics, berth gate and ETA benchmarks."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from .mfar_core import _params
from .mfar_prompt3_runtime import run_stage4 as _prompt3

QUALITY_SEMANTICS = "DATA_QUALITY_INDEX_NOT_CALIBRATED_PROBABILITY"


def _num(value: Any, fallback: float = 0.0) -> float:
    x = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(x) if pd.notna(x) and np.isfinite(x) else float(fallback)


def _series(frame: pd.DataFrame, name: str, fallback: Any = np.nan) -> pd.Series:
    return frame[name] if name in frame else pd.Series(fallback, index=frame.index)


def _quality(frame: pd.DataFrame, params: dict[str, float]) -> pd.DataFrame:
    out = frame.copy()
    max_gap = max(_num(params.get("max_interpolation_gap_min"), 20), 1)
    gap = pd.to_numeric(_series(out, "bracket_gap_min", max_gap), errors="coerce").fillna(max_gap).clip(lower=0)
    out["ais_continuity_score"] = np.exp(-gap / max_gap)
    out["trip_history_support_score"] = np.where(pd.to_datetime(_series(out, "trip_history_latest_time", pd.NaT), errors="coerce").notna(), 1.0, 0.35)
    source = _series(out, "turnaround_estimate_source", "UNKNOWN").astype(str).str.upper()
    out["turnaround_prior_support_score"] = np.select(
        [source.str.contains("VESSEL_PORT"), source.str.contains("VESSEL"), source.str.contains("PORT"), source.str.contains("GLOBAL"), source.str.contains("PRIOR"), source.str.contains("FALLBACK")],
        [1.00, .90, .75, .60, .80, .35], default=.50)
    berth_ok = (_series(out, "assigned_destination_berth").notna()
                & pd.to_datetime(_series(out, "predicted_berth_available_time_at_eta", pd.NaT), errors="coerce").notna())
    out["berth_projection_completeness_score"] = np.where(berth_ok, 1.0, .40)
    weights = np.array([
        _num(params.get("quality_weight_ais_continuity"), .40),
        _num(params.get("quality_weight_trip_history"), .25),
        _num(params.get("quality_weight_turnaround_prior"), .20),
        _num(params.get("quality_weight_berth_projection"), .15),
    ])
    if not np.isfinite(weights).all() or weights.sum() <= 0: weights = np.array([.40,.25,.20,.15])
    weights /= weights.sum()
    matrix = out[["ais_continuity_score","trip_history_support_score","turnaround_prior_support_score","berth_projection_completeness_score"]].to_numpy(float)
    out["legacy_forecast_confidence"] = pd.to_numeric(_series(out, "forecast_confidence"), errors="coerce")
    out["forecast_quality_index"] = np.clip(matrix @ weights, 0, 1)
    out["forecast_confidence"] = out["forecast_quality_index"]
    out["forecast_confidence_semantics"] = QUALITY_SEMANTICS
    out["forecast_quality_formula_version"] = "P4_WEIGHTED_INDEPENDENT_COMPONENTS_V1"
    return out


def _berth_gate(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = frame.copy()
    eta = pd.to_datetime(out["predicted_eta"], errors="coerce")
    available = pd.to_datetime(out["predicted_berth_available_time_at_eta"], errors="coerce")
    out["predicted_wait_min"] = available.sub(eta).dt.total_seconds().div(60).clip(lower=0).fillna(0)
    out["berth_slot_conflict_at_eta"] = out["predicted_wait_min"].gt(0)
    out["berth_availability_at_eta"] = (~out["berth_slot_conflict_at_eta"]).astype(float)
    out["berth_availability_model"] = "DETERMINISTIC_PROJECTED_SLOT_GATE"
    out["berth_wait_evidence"] = "CAUSAL_RESERVATION_LEDGER"
    audit = pd.DataFrame({"check":["negative_wait","nonbinary_availability","availability_wait_inconsistency","missing_berth","missing_slot_time"],"failed_rows":[
        int(out["predicted_wait_min"].lt(0).sum()), int((~out["berth_availability_at_eta"].isin([0.,1.])).sum()),
        int((out["berth_availability_at_eta"].eq(1)&out["predicted_wait_min"].gt(0)).sum()+(out["berth_availability_at_eta"].eq(0)&out["predicted_wait_min"].le(0)).sum()),
        int(out["assigned_destination_berth"].isna().sum()), int(available.isna().sum())]})
    return out, audit


def _eta_benchmarks(frame: pd.DataFrame, params: dict[str, float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = frame.sort_values(["decision_time","mmsi"]).reset_index(drop=True).copy()
    for col in ["decision_time","predicted_departure_time","predicted_eta","observed_destination_berth_time"]:
        out[col] = pd.to_datetime(out[col], errors="coerce")
    fixed = _num(params.get("eta_fixed_baseline_min"), 50)
    min_hist = int(_num(params.get("eta_interval_min_history"), 10))
    q = _num(params.get("eta_interval_quantile"), .90)
    out["eta_fixed_baseline"] = out["predicted_departure_time"] + pd.to_timedelta(fixed, unit="m")
    corrections=[]; widths=[]; counts=[]
    for _, row in out.iterrows():
        past = out[out["observed_destination_berth_time"].notna() & out["observed_destination_berth_time"].lt(row["decision_time"])]
        errors = pd.to_numeric(past["eta_error_min"], errors="coerce").dropna()
        counts.append(len(errors)); corrections.append(float(errors.median()) if len(errors) else 0.)
        widths.append(float(errors.abs().quantile(q)) if len(errors) >= min_hist else np.nan)
    out["online_bias_correction_min"] = corrections
    out["online_error_history_count"] = counts
    out["online_interval_halfwidth_min"] = widths
    out["eta_online_bias_corrected"] = out["predicted_eta"] - pd.to_timedelta(out["online_bias_correction_min"], unit="m")
    out["eta_interval_lower"] = out["eta_online_bias_corrected"] - pd.to_timedelta(out["online_interval_halfwidth_min"], unit="m")
    out["eta_interval_upper"] = out["eta_online_bias_corrected"] + pd.to_timedelta(out["online_interval_halfwidth_min"], unit="m")
    obs = out["observed_destination_berth_time"]
    out["fixed_baseline_error_min"] = out["eta_fixed_baseline"].sub(obs).dt.total_seconds().div(60)
    out["fixed_baseline_absolute_error_min"] = out["fixed_baseline_error_min"].abs()
    out["online_corrected_error_min"] = out["eta_online_bias_corrected"].sub(obs).dt.total_seconds().div(60)
    out["online_corrected_absolute_error_min"] = out["online_corrected_error_min"].abs()
    out["online_interval_contains_observation"] = obs.notna() & out["eta_interval_lower"].notna() & obs.between(out["eta_interval_lower"],out["eta_interval_upper"])
    valid = out["absolute_eta_error_min"].notna()
    interval_valid = valid & out["online_interval_halfwidth_min"].notna()
    model = out.loc[valid,"absolute_eta_error_min"].mean(); base = out.loc[valid,"fixed_baseline_absolute_error_min"].mean(); corrected = out.loc[valid,"online_corrected_absolute_error_min"].mean()
    summary = pd.DataFrame({"metric":["eta_model_mae_min","eta_fixed_baseline_mae_min","eta_online_corrected_mae_min","eta_skill_vs_fixed","eta_online_corrected_skill_vs_fixed","eta_interval_nominal_coverage","eta_interval_empirical_coverage","eta_interval_cases"],"value":[
        model,base,corrected,1-model/base if pd.notna(base) and base>0 else np.nan,1-corrected/base if pd.notna(base) and base>0 else np.nan,q,out.loc[interval_valid,"online_interval_contains_observation"].mean() if interval_valid.any() else np.nan,int(interval_valid.sum())]})
    return out, summary


def _quality_calibration(frame: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    valid = frame[frame["absolute_eta_error_min"].notna()].copy()
    if valid.empty: return pd.DataFrame(), pd.DataFrame({"metric":["quality_error_spearman"],"value":[np.nan]})
    valid["quality_quartile"] = pd.qcut(valid["forecast_quality_index"],4,duplicates="drop")
    table = valid.groupby("quality_quartile",observed=False,dropna=False).agg(cases=("decision_case_id","size"),mean_quality_index=("forecast_quality_index","mean"),eta_mae_min=("absolute_eta_error_min","mean"),eta_bias_min=("eta_error_min","mean")).reset_index()
    rho = valid[["forecast_quality_index","absolute_eta_error_min"]].corr(method="spearman").iloc[0,1]
    return table, pd.DataFrame({"metric":["quality_error_spearman","quality_index_min","quality_index_max"],"value":[rho,valid["forecast_quality_index"].min(),valid["forecast_quality_index"].max()]})


def _merge_summary(summary: pd.DataFrame, *frames: pd.DataFrame, extra: dict[str,Any]|None=None) -> pd.DataFrame:
    metrics={}
    for frame in frames: metrics.update(dict(zip(frame["metric"],frame["value"])))
    metrics.update(extra or {})
    base=summary[~summary["metric"].isin(metrics)].copy()
    return pd.concat([base,pd.DataFrame({"metric":list(metrics),"value":list(metrics.values())})],ignore_index=True)


def run_stage4(state, episodes, rates, profiles, berths, stage_dir: Path, config_dir: Path):
    queue,event_log,forecast,summary,eta_audit,departure_audit = _prompt3(state,episodes,rates,profiles,berths,stage_dir,config_dir)
    params=_params(config_dir); stage_dir=Path(stage_dir)
    forecast=_quality(forecast,params); forecast,berth_audit=_berth_gate(forecast); forecast,eta_summary=_eta_benchmarks(forecast,params)
    quality_table,quality_summary=_quality_calibration(forecast)
    summary=_merge_summary(summary,eta_summary,quality_summary,extra={"forecast_quality_semantics":QUALITY_SEMANTICS,"berth_availability_model":"DETERMINISTIC_PROJECTED_SLOT_GATE","positive_predicted_wait_cases":int(forecast["predicted_wait_min"].gt(0).sum()),"mean_predicted_wait_min":forecast["predicted_wait_min"].mean()})
    for name in ["04_fuzzy_input.csv","04_predeparture_forecast.csv","04_daily_vessel_forecast.csv","04_forecast_quality_components.csv","04_eta_benchmark_cases.csv"]: forecast.to_csv(stage_dir/name,index=False)
    quality_table.to_csv(stage_dir/"04_quality_error_calibration.csv",index=False); quality_summary.to_csv(stage_dir/"04_quality_index_summary.csv",index=False)
    berth_audit.to_csv(stage_dir/"04_berth_availability_audit.csv",index=False); eta_summary.to_csv(stage_dir/"04_eta_benchmark_summary.csv",index=False)
    summary.to_csv(stage_dir/"04_forecast_summary.csv",index=False); summary.to_csv(stage_dir/"04_ais_eta_berth_summary.csv",index=False)
    cols=["decision_case_id","mmsi","origin","destination","decision_time","predicted_departure_time","observed_departure_time","predicted_eta","eta_online_bias_corrected","eta_fixed_baseline","observed_destination_berth_time","eta_error_min","absolute_eta_error_min","online_corrected_error_min","online_corrected_absolute_error_min","fixed_baseline_error_min","fixed_baseline_absolute_error_min","online_interval_halfwidth_min","online_interval_contains_observation","forecast_quality_index","forecast_confidence_semantics"]
    forecast.loc[forecast["observed_destination_berth_time"].notna(),cols].to_csv(stage_dir/"04_temporal_holdout_validation.csv",index=False)
    return queue,event_log,forecast,summary,eta_audit,departure_audit
