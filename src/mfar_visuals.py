"""Readable, interactive output exporters for the MFAR notebook pipeline.

CSV/JSON files remain the machine-readable stage contract.  These helpers add
standalone HTML reports and compact Excel workbooks for scientific inspection.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


COLORS = {
    "blue": "#0b5fa5",
    "teal": "#00897b",
    "orange": "#f59e0b",
    "red": "#c62828",
    "green": "#2e7d32",
    "grey": "#64748b",
}


def _plotly():
    try:
        import plotly.express as px
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError as exc:
        raise ImportError(
            "Plotly belum tersedia. Jalankan `pip install plotly openpyxl`."
        ) from exc
    return px, go, make_subplots


def _as_datetime(frame: pd.DataFrame, columns) -> pd.DataFrame:
    out = frame.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    return out


def _card(label: str, value, note: str = "") -> str:
    return (
        '<div class="card"><div class="label">'
        + escape(str(label))
        + '</div><div class="value">'
        + escape(str(value))
        + '</div><div class="note">'
        + escape(str(note))
        + "</div></div>"
    )


def _fig_html(fig) -> str:
    fig.update_layout(
        template="plotly_white",
        font=dict(family="Arial, sans-serif", size=13),
        margin=dict(l=55, r=25, t=70, b=50),
        hovermode="closest",
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def _write_report(path: Path, title: str, subtitle: str, cards, sections) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    card_html = "".join(_card(*c) for c in cards)
    section_html = "".join(
        f'<section><h2>{escape(heading)}</h2>{body}</section>'
        for heading, body in sections
    )
    html = f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<style>
body{{font-family:Arial,sans-serif;background:#f4f7fb;color:#14213d;margin:0}}
.wrap{{max-width:1380px;margin:auto;padding:28px}}
h1{{margin:0 0 6px;color:#083b66}} .subtitle{{color:#526274;margin-bottom:22px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.card,section{{background:white;border-radius:12px;box-shadow:0 2px 12px #001b4420}}
.card{{padding:16px;border-top:4px solid #0b5fa5}}
.label{{font-size:12px;text-transform:uppercase;color:#60758a}}
.value{{font-size:27px;font-weight:700;margin:6px 0;color:#083b66}}
.note{{font-size:12px;color:#64748b}}
section{{padding:12px 16px;margin-top:18px}} section h2{{font-size:18px;margin:8px}}
.guide{{padding:12px 16px;background:#e8f2fb;border-left:5px solid #0b5fa5;border-radius:8px}}
</style></head><body><div class="wrap">
<h1>{escape(title)}</h1><div class="subtitle">{escape(subtitle)}</div>
<div class="cards">{card_html}</div>{section_html}
</div></body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


def write_excel_summary(path: Path, sheets: Mapping[str, pd.DataFrame]) -> Path:
    """Write compact, formatted tables; never place multi-million-row stage data here."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for raw_name, frame in sheets.items():
            name = str(raw_name)[:31]
            safe = frame.copy()
            for col in safe.select_dtypes(include=["datetimetz"]).columns:
                safe[col] = safe[col].dt.tz_localize(None)
            safe.to_excel(writer, sheet_name=name, index=False)
            ws = writer.book[name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True, color="FFFFFF")
                cell.fill = cell.fill.copy(fill_type="solid", fgColor="0B5FA5")
            for column in ws.columns:
                letter = column[0].column_letter
                width = min(42, max(11, max(len(str(c.value or "")) for c in column) + 2))
                ws.column_dimensions[letter].width = width
    return path


def stage1_quality_outputs(summary, rejection_summary, vessel_summary, stage_dir):
    px, go, make_subplots = _plotly()
    summary_dict = dict(zip(summary["metric"], summary["value"]))
    raw = int(float(summary_dict.get("raw_rows", 0)))
    accepted = int(float(summary_dict.get("accepted_rows", 0)))
    rate = 100 * accepted / max(raw, 1)
    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "xy"}]],
                        subplot_titles=("Komposisi penolakan", "Kepadatan pesan per kapal"))
    if not rejection_summary.empty:
        fig.add_trace(go.Pie(labels=rejection_summary["rejection_reason"],
                             values=rejection_summary["rows"], hole=.5), 1, 1)
    top = vessel_summary.nlargest(15, "messages") if "messages" in vessel_summary else vessel_summary
    fig.add_trace(go.Bar(x=top["mmsi"].astype(str), y=top["messages"], marker_color=COLORS["blue"]), 1, 2)
    fig.update_layout(title="Kualitas input AIS dan representasi kapal", showlegend=True)
    cards = [
        ("Baris AIS mentah", f"{raw:,}", "sebelum cleaning"),
        ("Baris diterima", f"{accepted:,}", f"{rate:.2f}% dari input"),
        ("Baris ditolak", f"{raw-accepted:,}", "alasan dapat ditelusuri"),
        ("Kapal", int(float(summary_dict.get("vessel_count", 0))), "MMSI unik"),
    ]
    guide = '<div class="guide">Gunakan peta HTML Stage 01 untuk memeriksa cakupan spasial. Diagram ini menjelaskan kualitas data, bukan akurasi rekonstruksi.</div>'
    html = _write_report(Path(stage_dir)/"01_data_quality_dashboard.html",
                         "Stage 01 · Kualitas dan cakupan AIS",
                         "Ringkasan cleaning yang dapat dibaca tanpa membuka CSV.", cards,
                         [("Cara membaca", guide), ("Distribusi data", _fig_html(fig))])
    xlsx = write_excel_summary(Path(stage_dir)/"01_readable_summary.xlsx", {
        "Ringkasan": summary, "Alasan Penolakan": rejection_summary,
        "Per Kapal": vessel_summary,
    })
    return [html, xlsx]


def stage2_interpolation_outputs(output_grid, summary, by_vessel, gap_distribution, audit_checks, stage_dir):
    px, go, make_subplots = _plotly()
    d = dict(zip(summary["metric"], summary["value"]))
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Distribusi gap observasi", "P95 gap per kapal"))
    fig.add_trace(go.Bar(x=gap_distribution["range"], y=gap_distribution["rows"], marker_color=COLORS["teal"]), 1, 1)
    fig.add_trace(go.Bar(x=by_vessel["mmsi"].astype(str), y=by_vessel["p95_bracket_gap_min"], marker_color=COLORS["orange"]), 1, 2)
    fig.add_hline(y=float(d.get("maximum_bracket_gap_min", 20)), line_dash="dash", line_color=COLORS["red"], row=1, col=2)
    fig.update_layout(title="Audit interval interpolasi lima menit", showlegend=False)
    failures = int(pd.to_numeric(audit_checks["failed_rows"], errors="coerce").fillna(0).sum())
    cards = [
        ("Grid diterima", f"{len(output_grid):,}", "baris kapal-waktu"),
        ("Kapal", output_grid["mmsi"].nunique(), "MMSI unik"),
        ("Median bracket gap", f"{float(d.get('median_bracket_gap_min', np.nan)):.2f} min", "jarak observasi pembatas"),
        ("Audit gagal", failures, "harus bernilai 0"),
    ]
    guide = '<div class="guide">Validasi spasial utama tersedia sebagai peta terpisah per kapal-hari: <b>02_validation_map_&lt;MMSI&gt;_&lt;tanggal&gt;.html</b>. Peta seluruh periode dipakai untuk cakupan data.</div>'
    html = _write_report(Path(stage_dir)/"02_interpolation_dashboard.html",
                         "Stage 02 · Validasi interpolasi",
                         "Peta untuk geometri lintasan; dashboard untuk kualitas interval dan audit.", cards,
                         [("Artefak validasi", guide), ("Kualitas interpolasi", _fig_html(fig))])
    xlsx = write_excel_summary(Path(stage_dir)/"02_readable_summary.xlsx", {
        "Ringkasan": summary, "Per Kapal": by_vessel,
        "Distribusi Gap": gap_distribution, "Audit": audit_checks,
    })
    return [html, xlsx]


def stage3_berth_outputs(state, audit, stage_dir):
    px, go, make_subplots = _plotly()
    x = _as_datetime(state, ["grid_time", "berth_entry_time", "predicted_berth_release_time"])
    occupied = x[x["is_at_berth"].astype(bool)].copy()
    episodes = pd.DataFrame()
    if not occupied.empty:
        episodes = (occupied.groupby(["mmsi", "berth_episode_id"], as_index=False)
                    .agg(vessel_name=("vessel_name", "first"), berth=("occupied_berth_id", "first"),
                         start=("grid_time", "min"), observed_end=("grid_time", "max"),
                         predicted_release=("predicted_berth_release_time", "max")))
        episodes["finish"] = episodes[["observed_end", "predicted_release"]].max(axis=1)
        episodes["resource"] = episodes["vessel_name"].fillna(episodes["mmsi"].astype(str))
        timeline = px.timeline(episodes, x_start="start", x_end="finish", y="berth", color="resource",
                               hover_data=["mmsi", "observed_end", "predicted_release"],
                               title="Episode okupansi dan prediksi pelepasan dermaga")
        timeline.update_yaxes(autorange="reversed")
    else:
        timeline = go.Figure().update_layout(title="Tidak ada episode sandar")
    trans = x.sort_values(["mmsi", "grid_time"]).copy()
    trans["next_status"] = trans.groupby("mmsi")["operational_status"].shift(-1)
    flow = trans.dropna(subset=["operational_status", "next_status"])
    flow = flow[flow["operational_status"].ne(flow["next_status"])]
    counts = flow.groupby(["operational_status", "next_status"]).size().reset_index(name="count")
    labels = pd.Index(pd.concat([counts["operational_status"], counts["next_status"]]).astype(str).unique())
    sankey = go.Figure(go.Sankey(node=dict(label=labels.tolist()), link=dict(
        source=counts["operational_status"].map({v:i for i,v in enumerate(labels)}),
        target=counts["next_status"].map({v:i for i,v in enumerate(labels)}), value=counts["count"])))
    sankey.update_layout(title="Aliran perubahan status operasional")
    cards = [
        ("Episode sandar", len(episodes), "kapal–episode"),
        ("Dermaga teramati", occupied["occupied_berth_id"].nunique() if not occupied.empty else 0, "berth ID"),
        ("Transisi status", int(counts["count"].sum()) if not counts.empty else 0, "perubahan antarstatus"),
        ("Audit gagal", int(audit["failed_rows"].sum()), "harus bernilai 0"),
    ]
    html = _write_report(Path(stage_dir)/"03_berth_monitoring_story.html",
                         "Stage 03 · Cerita operasi dermaga",
                         "Timeline menjelaskan okupansi; Sankey menjelaskan aliran status.", cards,
                         [("Timeline dermaga", _fig_html(timeline)), ("Transisi operasional", _fig_html(sankey))])
    xlsx = write_excel_summary(Path(stage_dir)/"03_readable_summary.xlsx", {
        "Episode Dermaga": episodes, "Audit": audit,
    })
    return [html, xlsx]


def stage4_forecast_outputs(queue, forecast, event_log, summary, eta_audit, departure_audit, stage_dir):
    px, go, make_subplots = _plotly()
    q = _as_datetime(queue, ["simulation_time"])
    f = _as_datetime(forecast, ["simulation_time", "ais_departure_time", "predicted_eta", "predicted_berth_available_time_at_eta"])
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False,
                        subplot_titles=("Profil antrean baseline", "Keberangkatan–ETA dan prediksi waktu tunggu"),
                        vertical_spacing=.15)
    for port, g in q.groupby("port_id"):
        fig.add_trace(go.Scatter(x=g["simulation_time"], y=g["queue_ce"], mode="lines", name=f"Queue {port}"), 1, 1)
    fig.add_hline(y=3 * 30, line_dash="dash", line_color=COLORS["red"], annotation_text="rasio kritis = 3", row=1, col=1)
    if not f.empty:
        fig.add_trace(go.Scatter(x=f["predicted_eta"], y=f["mmsi"].astype(str), mode="markers",
                                 marker=dict(size=np.clip(f["predicted_wait_min"].fillna(0)+8, 8, 35),
                                             color=f["predicted_wait_min"], colorscale="YlOrRd", showscale=True,
                                             colorbar=dict(title="Wait min")),
                                 text=f["assigned_destination_berth"], name="Predicted ETA"), 2, 1)
    fig.update_layout(title="Forecast operasional harian 07.00–24.00")
    s = dict(zip(summary["metric"], summary["value"]))
    cards = [
        ("Keberangkatan AIS", int(float(s.get("ais_departures_used", 0))), "bukti aktual"),
        ("Antrean maksimum", f"{float(s.get('max_queue_ce', np.nan)):.2f} CE", "baseline"),
        ("Rata-rata wait", f"{float(s.get('mean_predicted_wait_min', np.nan)):.2f} min", "pada ETA"),
        ("Berth unavailable", int(float(s.get("unavailable_at_eta_rows", 0))), "kasus forecast"),
    ]
    guide = '<div class="guide">Ukuran titik ETA menunjukkan prediksi waktu tunggu. Arahkan kursor untuk melihat kapal dan dermaga tujuan. Validasi forecast tetap dibedakan dari simulasi intervensi Stage 07.</div>'
    html = _write_report(Path(stage_dir)/"04_operational_forecast_dashboard.html",
                         "Stage 04 · Forecast tanpa intervensi",
                         "Perbandingan antrean waktu dan risiko ketersediaan dermaga pada ETA.", cards,
                         [("Cara membaca", guide), ("Eksplorasi waktu", _fig_html(fig))])
    xlsx = write_excel_summary(Path(stage_dir)/"04_readable_results.xlsx", {
        "Ringkasan": summary, "Forecast Kapal": f, "Event AIS": event_log,
        "Audit ETA": eta_audit, "Audit Keberangkatan": departure_audit,
    })
    return [html, xlsx]


def stage5_fuzzy_outputs(df, audit, stage_dir):
    px, go, make_subplots = _plotly()
    mu_cols = [c for c in df.columns if c.startswith("mu_")]
    view = df[mu_cols].copy()
    active = (view > 0).sum().sort_values(ascending=False).head(18)
    fig = go.Figure(go.Bar(x=active.values, y=active.index.str.replace("mu_", "", regex=False),
                           orientation="h", marker_color=COLORS["teal"]))
    fig.update_layout(title="Frekuensi himpunan fuzzy aktif", yaxis=dict(autorange="reversed"),
                      xaxis_title="Jumlah kasus dengan membership > 0")
    heat_view = view.head(100).T
    heat = go.Figure(go.Heatmap(z=heat_view.values, x=[str(i+1) for i in range(heat_view.shape[1])],
                                y=heat_view.index.str.replace("mu_", "", regex=False), colorscale="Viridis",
                                zmin=0, zmax=1, colorbar=dict(title="μ")))
    heat.update_layout(title="Sidik-jari fuzzy hingga 100 kasus pertama", xaxis_title="Urutan kasus")
    cards = [
        ("Kasus", len(df), "event forecast"), ("Variabel membership", len(mu_cols), "kolom μ"),
        ("Membership maksimum", f"{view.max().max():.2f}", "batas teoritis 1"),
        ("Audit gagal", int(audit["failed_rows"].sum()), "harus bernilai 0"),
    ]
    html = _write_report(Path(stage_dir)/"05_fuzzy_case_explorer.html",
                         "Stage 05 · Eksplorasi fuzzification",
                         "Frekuensi keaktifan dan sidik-jari membership tiap kasus.", cards,
                         [("Himpunan aktif", _fig_html(fig)), ("Matriks membership", _fig_html(heat))])
    fuzzy_summary = pd.DataFrame({"membership": mu_cols, "active_cases": [(view[c] > 0).sum() for c in mu_cols],
                                  "mean_degree": [view[c].mean() for c in mu_cols],
                                  "max_degree": [view[c].max() for c in mu_cols]})
    xlsx = write_excel_summary(Path(stage_dir)/"05_readable_summary.xlsx", {
        "Ringkasan Membership": fuzzy_summary, "Audit": audit,
    })
    return [html, xlsx]


def stage6_rule_outputs(out, rule_catalog, rule_summary, stage_dir):
    px, go, make_subplots = _plotly()
    flow = out.groupby(["dominant_rule", "selected_action"]).size().reset_index(name="cases")
    labels = pd.Index(pd.concat([flow["dominant_rule"], flow["selected_action"]]).astype(str).unique())
    idx = {v:i for i,v in enumerate(labels)}
    fig = go.Figure(go.Sankey(node=dict(label=labels.tolist(), pad=16, thickness=16), link=dict(
        source=flow["dominant_rule"].map(idx), target=flow["selected_action"].map(idx), value=flow["cases"])))
    fig.update_layout(title="Aliran rule dominan menuju tindakan terpilih")
    action = out["selected_action"].value_counts().rename_axis("action").reset_index(name="cases")
    cards = [
        ("Kasus", len(out), "dievaluasi"), ("Rule aktif", int((rule_summary["active_rows"] > 0).sum()), "dari katalog"),
        ("Tindakan berbeda", out["selected_action"].nunique(), "hasil inferensi"),
        ("Mean strength", f"{out['selected_rule_strength'].mean():.3f}", "tindakan terpilih"),
    ]
    html = _write_report(Path(stage_dir)/"06_rule_action_flow.html",
                         "Stage 06 · Aliran rule ke tindakan",
                         "Sankey memperlihatkan rule yang benar-benar menggerakkan rekomendasi.", cards,
                         [("Rule → tindakan", _fig_html(fig))])
    xlsx = write_excel_summary(Path(stage_dir)/"06_readable_results.xlsx", {
        "Tindakan": action, "Ringkasan Rule": rule_summary, "Katalog Rule": rule_catalog,
    })
    return [html, xlsx]


def stage7_intervention_outputs(sim, accepted, extra, daily, overall, stage_dir):
    px, go, make_subplots = _plotly()
    x = _as_datetime(sim, ["simulation_time"])
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        subplot_titles=("Antrean baseline vs setelah intervensi", "Layanan tambahan pada waktu intervensi"))
    for port, g in x.groupby("port_id"):
        fig.add_trace(go.Scatter(x=g["simulation_time"], y=g["queue_ce"], mode="lines",
                                 name=f"Baseline {port}", line=dict(dash="dot")), 1, 1)
        fig.add_trace(go.Scatter(x=g["simulation_time"], y=g["queue_ce_after"], mode="lines",
                                 name=f"After {port}"), 1, 1)
        fig.add_trace(go.Bar(x=g["simulation_time"], y=g["intervention_service_ce"],
                             name=f"Intervention {port}"), 2, 1)
    fig.update_layout(title="Validasi skenario intervensi sepanjang hari", barmode="group")
    status = x["critical_case_status"].value_counts().rename_axis("status").reset_index(name="rows")
    donut = go.Figure(go.Pie(labels=status["status"], values=status["rows"], hole=.55))
    donut.update_layout(title="Status perubahan kondisi kritis")
    metrics = dict(zip(overall["metric"], overall["value"]))
    cards = [
        ("Kritis baseline", int(float(metrics.get("total_critical_baseline", 0))), "baris 5 menit"),
        ("Kritis setelah", int(float(metrics.get("total_critical_after", 0))), "baris 5 menit"),
        ("Kritis terselesaikan", int(float(metrics.get("critical_resolved", 0))), "resolved"),
        ("Queue area turun", f"{float(metrics.get('queue_area_reduction_percent', np.nan)):.2f}%", "baseline vs intervensi"),
        ("Rekomendasi diterima", len(accepted), "setelah cooldown"),
    ]
    guide = '<div class="guide">Garis putus-putus adalah baseline. Garis penuh adalah hasil setelah intervensi. Batang pada panel bawah menunjukkan waktu dan kapasitas layanan tambahan; ini membedakan rekomendasi fuzzy dari intervensi yang benar-benar diterapkan.</div>'
    html = _write_report(Path(stage_dir)/"07_intervention_validation_dashboard.html",
                         "Stage 07 · Validasi intervensi",
                         "Perubahan antrean, waktu intervensi, dan penyelesaian kondisi kritis.", cards,
                         [("Cara membaca", guide), ("Skenario waktu", _fig_html(fig)),
                          ("Perubahan status kritis", _fig_html(donut))])
    xlsx = write_excel_summary(Path(stage_dir)/"07_readable_results.xlsx", {
        "Ringkasan Utama": overall, "Per Pelabuhan": daily,
        "Rekomendasi Diterima": accepted, "Event Intervensi": extra,
    })
    return [html, xlsx]
