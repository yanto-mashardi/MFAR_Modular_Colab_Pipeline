"""Readable, interactive output exporters for the MFAR notebook pipeline.

CSV/JSON files remain the machine-readable stage contract.  These helpers add
standalone HTML reports and compact Excel workbooks for scientific inspection.
"""

from __future__ import annotations

from copy import copy
from html import escape
import json
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
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _write_report(path: Path, title: str, subtitle: str, cards, sections) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    card_html = "".join(_card(*c) for c in cards)
    section_html = "".join(
        f'<section><h2>{escape(heading)}</h2>{body}</section>'
        for heading, body in sections
    )
    try:
        from plotly.offline import get_plotlyjs
        plotly_js = get_plotlyjs()
    except ImportError as exc:
        raise ImportError("Plotly belum tersedia untuk dashboard mandiri.") from exc
    html = f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<script>{plotly_js}</script>
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
.filter-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:12px 0}}
.filter-grid label{{font-size:12px;color:#526274;font-weight:700}}
.filter-grid select{{display:block;width:100%;margin-top:5px;padding:9px;border:1px solid #b8c5d1;border-radius:7px;background:#fff}}
.dynamic-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}}
.dynamic-card{{background:#f7fafc;border-left:4px solid #00897b;padding:12px;border-radius:8px}}
.dynamic-card .v{{font-size:22px;font-weight:700;color:#083b66;margin-top:4px}}
.plot{{height:430px;margin-top:8px}} .data-note{{font-size:12px;color:#64748b}}
</style></head><body><div class="wrap">
<h1>{escape(title)}</h1><div class="subtitle">{escape(subtitle)}</div>
<div class="cards">{card_html}</div>{section_html}
</div></body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


def _json_records(frame: pd.DataFrame) -> list[dict]:
    """Convert a dashboard frame to strict browser-safe JSON records."""
    safe = frame.copy()
    for col in safe.columns:
        if pd.api.types.is_datetime64_any_dtype(safe[col]):
            safe[col] = safe[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return json.loads(safe.to_json(orient="records", date_format="iso"))


def _dynamic_explorer(
    frame: pd.DataFrame,
    explorer_id: str,
    filters: list[tuple[str, str]],
    metrics: list[tuple[str, str, str]],
    charts: list[dict],
    table_columns: list[str] | None = None,
) -> str:
    """Create a self-contained multi-filter dashboard backed by Plotly.

    Filters are conjunctive and update every chart, KPI card, and preview row.
    This is deliberately separate from Plotly legend toggles, which do not
    constitute analytical filtering.
    """
    if frame.empty:
        return '<div class="guide">Tidak ada data yang tersedia untuk pilihan ini.</div>'
    data = _json_records(frame)
    spec = {
        "id": explorer_id,
        "filters": [{"column": c, "label": l} for c, l in filters if c in frame],
        "metrics": [
            {"label": label, "column": col, "aggregation": agg}
            for label, col, agg in metrics if col in frame or agg == "count"
        ],
        "charts": charts,
        "tableColumns": [c for c in (table_columns or []) if c in frame],
    }
    payload = json.dumps({"data": data, "spec": spec}, ensure_ascii=False, separators=(",", ":"))
    root = escape(explorer_id)
    return f"""
<div id="{root}" class="dynamic-explorer">
  <div class="filter-grid" data-role="filters"></div>
  <div class="dynamic-cards" data-role="metrics"></div>
  <div data-role="charts"></div>
  <div class="data-note" data-role="note"></div>
  <div style="overflow:auto"><table data-role="table" style="width:100%;border-collapse:collapse;font-size:12px"></table></div>
</div>
<script>
(function(payload){{
 const root=document.getElementById(payload.spec.id), raw=payload.data, spec=payload.spec;
 const filterBox=root.querySelector('[data-role="filters"]');
 const selections={{}};
 const norm=v=>v===null||v===undefined||v===''?'(kosong)':String(v);
 spec.filters.forEach(f=>{{
   const label=document.createElement('label'); label.textContent=f.label;
   const select=document.createElement('select'); select.dataset.column=f.column;
   const values=[...new Set(raw.map(r=>norm(r[f.column])))].sort();
   select.innerHTML='<option value="__ALL__">Semua</option>'+values.map(v=>`<option value="${{v.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;')}}">${{v}}</option>`).join('');
   select.addEventListener('change',render); label.appendChild(select); filterBox.appendChild(label);
 }});
 function filtered(){{
   const selected=[...filterBox.querySelectorAll('select')].filter(s=>s.value!=='__ALL__');
   return raw.filter(r=>selected.every(s=>norm(r[s.dataset.column])===s.value));
 }}
 function numeric(rows,col){{return rows.map(r=>Number(r[col])).filter(Number.isFinite)}}
 function aggregate(rows,m){{
   if(m.aggregation==='count') return rows.length.toLocaleString('id-ID');
   const v=numeric(rows,m.column); if(!v.length) return '—';
   if(m.aggregation==='sum') return v.reduce((a,b)=>a+b,0).toLocaleString('id-ID',{{maximumFractionDigits:2}});
   if(m.aggregation==='max') return Math.max(...v).toLocaleString('id-ID',{{maximumFractionDigits:2}});
   if(m.aggregation==='median'){{v.sort((a,b)=>a-b); const k=Math.floor(v.length/2); return (v.length%2?v[k]:(v[k-1]+v[k])/2).toLocaleString('id-ID',{{maximumFractionDigits:2}})}}
   return (v.reduce((a,b)=>a+b,0)/v.length).toLocaleString('id-ID',{{maximumFractionDigits:2}});
 }}
 function groups(rows,col){{const out={{}}; rows.forEach(r=>{{const k=col?norm(r[col]):'Data';(out[k]||(out[k]=[])).push(r)}});return out}}
 function traces(rows,c){{
   const gs=groups(rows,c.color); let result=[];
   Object.entries(gs).forEach(([name,g])=>{{
     if(c.type==='line') result.push({{type:'scatter',mode:'lines',name,x:g.map(r=>r[c.x]),y:g.map(r=>r[c.y]),connectgaps:false}});
     else if(c.type==='scatter') result.push({{type:'scatter',mode:'markers',name,x:g.map(r=>r[c.x]),y:g.map(r=>r[c.y]),text:c.hover?g.map(r=>c.hover.map(h=>`${{h}}: ${{norm(r[h])}}`).join('<br>')):undefined,hovertemplate:'%{{text}}<extra>%{{fullData.name}}</extra>'}});
     else if(c.type==='bar-count'){{const counts={{}};g.forEach(r=>{{const k=norm(r[c.x]);counts[k]=(counts[k]||0)+1}});result.push({{type:'bar',name,x:Object.keys(counts),y:Object.values(counts)}})}}
     else if(c.type==='bar-mean'){{const vals={{}};g.forEach(r=>{{const k=norm(r[c.x]),v=Number(r[c.y]);if(Number.isFinite(v))(vals[k]||(vals[k]=[])).push(v)}});result.push({{type:'bar',name,x:Object.keys(vals),y:Object.values(vals).map(a=>a.reduce((x,y)=>x+y,0)/a.length)}})}}
     else if(c.type==='histogram') result.push({{type:'histogram',name,x:numeric(g,c.x),opacity:.72}});
   }}); return result;
 }}
 function render(){{
   const rows=filtered();
   root.querySelector('[data-role="metrics"]').innerHTML=spec.metrics.map(m=>`<div class="dynamic-card"><div>${{m.label}}</div><div class="v">${{aggregate(rows,m)}}</div></div>`).join('');
   const chartBox=root.querySelector('[data-role="charts"]');
   if(!chartBox.children.length) spec.charts.forEach((c,i)=>{{const d=document.createElement('div');d.className='plot';d.id=spec.id+'-plot-'+i;chartBox.appendChild(d)}});
   spec.charts.forEach((c,i)=>Plotly.react(spec.id+'-plot-'+i,traces(rows,c),{{title:c.title,template:'plotly_white',hovermode:'closest',barmode:'group',xaxis:{{title:c.xTitle||c.x,rangeslider:{{visible:!!c.rangeSlider}}}},yaxis:{{title:c.yTitle||c.y}},margin:{{t:65,r:25,b:60,l:65}}}},{{responsive:true,displaylogo:false}}));
   root.querySelector('[data-role="note"]').textContent=`Menampilkan ${{rows.length.toLocaleString('id-ID')}} dari ${{raw.length.toLocaleString('id-ID')}} baris. Semua filter diterapkan bersamaan.`;
   const cols=spec.tableColumns, sample=rows.slice(0,50), table=root.querySelector('[data-role="table"]');
   table.innerHTML=cols.length?`<thead><tr>${{cols.map(c=>`<th style="text-align:left;padding:6px;border-bottom:1px solid #ccd6df">${{c}}</th>`).join('')}}</tr></thead><tbody>${{sample.map(r=>`<tr>${{cols.map(c=>`<td style="padding:6px;border-bottom:1px solid #edf1f4">${{norm(r[c])}}</td>`).join('')}}</tr>`).join('')}}</tbody>`:'';
 }}
 render();
}})({payload});
</script>"""


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
                header_font = copy(cell.font)
                header_font.bold = True
                header_font.color = "FFFFFF"
                cell.font = header_font
                header_fill = copy(cell.fill)
                header_fill.fill_type = "solid"
                header_fill.fgColor = "0B5FA5"
                cell.fill = header_fill
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
    vessels = vessel_summary.copy(); vessels["mmsi_label"] = vessels["mmsi"].astype(str)
    explorer = _dynamic_explorer(
        vessels, "stage1-explorer", [("mmsi_label", "Kapal")],
        [("Kapal terpilih", "", "count"), ("Jumlah pesan", "messages", "sum"),
         ("Median SOG (kn)", "median_sog_kn", "mean"), ("P95 gap (min)", "p95_gap_min", "mean")],
        [{"type": "bar-mean", "x": "mmsi_label", "y": "messages", "title": "Pesan AIS per kapal",
          "xTitle": "MMSI", "yTitle": "Pesan"},
         {"type": "scatter", "x": "median_sog_kn", "y": "p95_gap_min", "color": "mmsi_label",
          "hover": ["messages", "maximum_gap_min"], "title": "Kecepatan dan kontinuitas data",
          "xTitle": "Median SOG (kn)", "yTitle": "P95 gap (min)"}],
        ["mmsi", "messages", "start_time", "end_time", "median_sog_kn", "p95_gap_min", "maximum_gap_min"],
    )
    html = _write_report(Path(stage_dir)/"01_data_quality_dashboard.html",
                         "Stage 01 · Kualitas dan cakupan AIS",
                         "Ringkasan cleaning yang dapat dibaca tanpa membuka CSV.", cards,
                         [("Cara membaca", guide), ("Penyaring kapal", explorer),
                          ("Distribusi data keseluruhan", _fig_html(fig))])
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
    vessels = by_vessel.copy(); vessels["mmsi_label"] = vessels["mmsi"].astype(str)
    explorer = _dynamic_explorer(
        vessels, "stage2-explorer", [("mmsi_label", "Kapal")],
        [("Kapal terpilih", "", "count"), ("Baris grid", "interpolated_rows", "sum"),
         ("Median bracket gap (min)", "median_bracket_gap_min", "mean"),
         ("P95 bracket gap (min)", "p95_bracket_gap_min", "mean")],
        [{"type": "bar-mean", "x": "mmsi_label", "y": "p95_bracket_gap_min",
          "title": "P95 bracket gap per kapal", "xTitle": "MMSI", "yTitle": "Menit"},
         {"type": "scatter", "x": "median_sog", "y": "p95_bracket_gap_min", "color": "mmsi_label",
          "hover": ["interpolated_rows", "start_grid_time", "end_grid_time"],
          "title": "Kecepatan dan kualitas interpolasi", "xTitle": "Median SOG (kn)", "yTitle": "P95 gap (min)"}],
        ["mmsi", "interpolated_rows", "start_grid_time", "end_grid_time", "median_sog",
         "median_bracket_gap_min", "p95_bracket_gap_min"],
    )
    html = _write_report(Path(stage_dir)/"02_interpolation_dashboard.html",
                         "Stage 02 · Validasi interpolasi",
                         "Peta untuk geometri lintasan; dashboard untuk kualitas interval dan audit.", cards,
                         [("Artefak validasi", guide), ("Penyaring kapal", explorer),
                          ("Kualitas interpolasi keseluruhan", _fig_html(fig))])
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
        episodes["evaluation_date"] = episodes["start"].dt.strftime("%Y-%m-%d")
        episodes["duration_min"] = episodes["finish"].sub(episodes["start"]).dt.total_seconds().div(60)
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
    explorer = _dynamic_explorer(
        episodes, "stage3-explorer",
        [("evaluation_date", "Tanggal"), ("resource", "Kapal"), ("berth", "Dermaga")],
        [("Episode terpilih", "", "count"), ("Rerata durasi (min)", "duration_min", "mean"),
         ("Durasi maksimum (min)", "duration_min", "max")],
        [{"type": "bar-mean", "x": "evaluation_date", "y": "duration_min", "color": "berth",
          "title": "Durasi episode per tanggal dan dermaga", "xTitle": "Tanggal", "yTitle": "Menit"},
         {"type": "bar-count", "x": "berth", "color": "resource", "title": "Jumlah episode per dermaga dan kapal"}],
        ["evaluation_date", "resource", "berth", "start", "finish", "duration_min"],
    )
    html = _write_report(Path(stage_dir)/"03_berth_monitoring_story.html",
                         "Stage 03 · Cerita operasi dermaga",
                         "Timeline menjelaskan okupansi; Sankey menjelaskan aliran status.", cards,
                         [("Penyaring analitis", explorer), ("Timeline dermaga", _fig_html(timeline)),
                          ("Transisi operasional", _fig_html(sankey))])
    xlsx = write_excel_summary(Path(stage_dir)/"03_readable_summary.xlsx", {
        "Episode Dermaga": episodes, "Audit": audit,
    })
    return [html, xlsx]


def stage4_forecast_outputs(queue, forecast, event_log, summary, eta_audit, departure_audit, stage_dir):
    px, go, make_subplots = _plotly()
    q = _as_datetime(queue, ["simulation_time"])
    f = _as_datetime(forecast, ["simulation_time", "decision_time", "baseline_departure_time",
                                "predicted_departure_time", "predicted_eta",
                                "predicted_berth_available_time_at_eta"])
    if not f.empty:
        f["evaluation_date"] = f["simulation_time"].dt.strftime("%Y-%m-%d")
        f["mmsi_label"] = f["mmsi"].astype(str)
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
    fig.update_layout(title="Forecast pre-departure pada temporal holdout")
    s = dict(zip(summary["metric"], summary["value"]))
    cards = [
        ("Hari holdout", int(float(s.get("evaluation_days", 0))), "periode evaluasi Maret"),
        ("Keputusan pre-departure", int(float(s.get("predeparture_decisions", 0))), "sebelum keberangkatan"),
        ("Antrean maksimum", f"{float(s.get('max_queue_ce', np.nan)):.2f} CE", "baseline"),
        ("Rata-rata wait", f"{float(s.get('mean_predicted_wait_min', np.nan)):.2f} min", "pada ETA"),
        ("Berth unavailable", int(float(s.get("unavailable_at_eta_rows", 0))), "kasus forecast"),
        ("MAE ETA holdout", f"{float(s.get('eta_holdout_mae_min', np.nan)):.2f} min", "vs kedatangan aktual"),
    ]
    guide = '<div class="guide">Ukuran titik ETA menunjukkan prediksi waktu tunggu. Arahkan kursor untuk melihat kapal dan dermaga tujuan. Validasi forecast tetap dibedakan dari simulasi intervensi Stage 07.</div>'
    explorer = _dynamic_explorer(
        f, "stage4-explorer",
        [("evaluation_date", "Tanggal"), ("origin", "Pelabuhan asal"),
         ("destination", "Pelabuhan tujuan"), ("mmsi_label", "Kapal"),
         ("assigned_destination_berth", "Dermaga tujuan")],
        [("Kasus terpilih", "", "count"), ("Rerata wait (min)", "predicted_wait_min", "mean"),
         ("MAE ETA (min)", "absolute_eta_error_min", "mean"),
         ("Rerata confidence", "forecast_confidence", "mean")],
        [{"type": "scatter", "x": "predicted_eta", "y": "predicted_wait_min", "color": "origin",
          "hover": ["mmsi", "destination", "assigned_destination_berth", "forecast_confidence"],
          "title": "ETA dan waktu tunggu terpilih", "xTitle": "Predicted ETA", "yTitle": "Wait (min)", "rangeSlider": True},
         {"type": "histogram", "x": "eta_error_min", "color": "origin",
          "title": "Distribusi galat ETA", "xTitle": "Galat ETA (min)"},
         {"type": "bar-mean", "x": "evaluation_date", "y": "predicted_wait_min", "color": "origin",
          "title": "Rerata waktu tunggu harian", "xTitle": "Tanggal", "yTitle": "Menit"}],
        ["evaluation_date", "mmsi", "origin", "destination", "decision_time", "predicted_departure_time",
         "predicted_eta", "predicted_wait_min", "eta_error_min", "forecast_confidence"],
    )
    html = _write_report(Path(stage_dir)/"04_operational_forecast_dashboard.html",
                         "Stage 04 · Forecast pre-departure pada temporal holdout",
                         "Parameter dikalibrasi pada periode terdahulu; kasus evaluasi berasal dari periode setelah cutoff.", cards,
                         [("Cara membaca", guide), ("Penyaring analitis", explorer),
                          ("Eksplorasi waktu keseluruhan", _fig_html(fig))])
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
    cases = _as_datetime(df, ["simulation_time", "decision_time"])
    if not cases.empty:
        cases["evaluation_date"] = cases["simulation_time"].dt.strftime("%Y-%m-%d")
        cases["mmsi_label"] = cases["mmsi"].astype(str)
        cases["dominant_membership"] = cases[mu_cols].idxmax(axis=1).str.replace("mu_", "", regex=False)
        cases["maximum_membership"] = cases[mu_cols].max(axis=1)
    cards = [
        ("Kasus", len(df), "event forecast"), ("Variabel membership", len(mu_cols), "kolom μ"),
        ("Membership maksimum", f"{view.max().max():.2f}", "batas teoritis 1"),
        ("Audit gagal", int(audit["failed_rows"].sum()), "harus bernilai 0"),
    ]
    explorer = _dynamic_explorer(
        cases, "stage5-explorer",
        [("evaluation_date", "Tanggal"), ("mmsi_label", "Kapal"), ("origin", "Pelabuhan asal"),
         ("destination", "Pelabuhan tujuan"), ("dominant_membership", "Membership dominan")],
        [("Kasus terpilih", "", "count"), ("Rerata degree maksimum", "maximum_membership", "mean"),
         ("Rerata queue ratio", "origin_queue_ratio", "mean"), ("Rerata wait (min)", "predicted_wait_min", "mean")],
        [{"type": "bar-count", "x": "dominant_membership", "color": "origin",
          "title": "Membership dominan pada pilihan aktif"},
         {"type": "scatter", "x": "simulation_time", "y": "maximum_membership", "color": "mmsi_label",
          "hover": ["origin", "destination", "predicted_wait_min", "origin_queue_ratio"],
          "title": "Derajat membership maksimum per kasus", "xTitle": "Waktu keputusan", "yTitle": "μ maksimum", "rangeSlider": True}],
        ["evaluation_date", "mmsi", "origin", "destination", "simulation_time", "dominant_membership",
         "maximum_membership", "origin_queue_ratio", "predicted_wait_min"],
    )
    html = _write_report(Path(stage_dir)/"05_fuzzy_case_explorer.html",
                         "Stage 05 · Eksplorasi fuzzification",
                         "Frekuensi keaktifan dan sidik-jari membership tiap kasus.", cards,
                         [("Penyaring kasus", explorer), ("Himpunan aktif keseluruhan", _fig_html(fig)),
                          ("Matriks membership", _fig_html(heat))])
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
    cases = _as_datetime(out, ["simulation_time", "decision_time"])
    if not cases.empty:
        cases["evaluation_date"] = cases["simulation_time"].dt.strftime("%Y-%m-%d")
        cases["mmsi_label"] = cases["mmsi"].astype(str)
    cards = [
        ("Kasus", len(out), "dievaluasi"), ("Rule aktif", int((rule_summary["active_rows"] > 0).sum()), "dari katalog"),
        ("Tindakan berbeda", out["selected_action"].nunique(), "hasil inferensi"),
        ("Mean strength", f"{out['selected_rule_strength'].mean():.3f}", "tindakan terpilih"),
    ]
    explorer = _dynamic_explorer(
        cases, "stage6-explorer",
        [("evaluation_date", "Tanggal"), ("mmsi_label", "Kapal"), ("origin", "Pelabuhan asal"),
         ("operational_phase", "Fase"), ("dominant_rule", "Rule dominan"),
         ("selected_action", "Tindakan")],
        [("Kasus terpilih", "", "count"), ("Rerata firing strength", "selected_rule_strength", "mean"),
         ("Rerata risk score", "mamdani_risk_score", "mean")],
        [{"type": "bar-count", "x": "selected_action", "color": "operational_phase",
          "title": "Tindakan menurut fase operasi"},
         {"type": "scatter", "x": "simulation_time", "y": "selected_rule_strength", "color": "selected_action",
          "hover": ["mmsi", "dominant_rule", "mamdani_risk_score", "origin"],
          "title": "Kekuatan rule sepanjang holdout", "xTitle": "Waktu keputusan", "yTitle": "Firing strength", "rangeSlider": True}],
        ["evaluation_date", "mmsi", "origin", "operational_phase", "dominant_rule", "selected_action",
         "selected_rule_strength", "mamdani_risk_score"],
    )
    html = _write_report(Path(stage_dir)/"06_rule_action_flow.html",
                         "Stage 06 · Aliran rule ke tindakan",
                         "Sankey memperlihatkan rule yang benar-benar menggerakkan rekomendasi.", cards,
                         [("Penyaring rule dan tindakan", explorer), ("Rule → tindakan keseluruhan", _fig_html(fig))])
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
    fig.update_layout(title="Evaluasi skenario tindakan sepanjang periode holdout", barmode="group")
    status = x["critical_case_status"].value_counts().rename_axis("status").reset_index(name="rows")
    donut = go.Figure(go.Pie(labels=status["status"], values=status["rows"], hole=.55))
    donut.update_layout(title="Status perubahan kondisi kritis")
    daily_plot = go.Figure()
    if "queue_area_reduction_percent" in daily:
        for port, group in daily.groupby("port_id"):
            daily_plot.add_trace(go.Bar(
                x=group["evaluation_date"].astype(str),
                y=group["queue_area_reduction_percent"],
                name=str(port),
            ))
    daily_plot.add_hline(y=0, line_color=COLORS["grey"])
    daily_plot.update_layout(
        title="Perubahan queue area per hari dan pelabuhan",
        yaxis_title="Reduction (%)", barmode="group",
    )
    metrics = dict(zip(overall["metric"], overall["value"]))
    cards = [
        ("Kritis baseline", int(float(metrics.get("total_critical_baseline", 0))), "baris 5 menit"),
        ("Kritis setelah", int(float(metrics.get("total_critical_after", 0))), "baris 5 menit"),
        ("Hari evaluasi", int(float(metrics.get("evaluation_days", 0))), "temporal holdout"),
        ("Median queue area", f"{float(metrics.get('median_daily_queue_area_reduction_percent', np.nan)):.2f}%", "per hari-pelabuhan"),
        ("Rekomendasi operasional", len(accepted), "NO_INTERVENTION dikecualikan"),
    ]
    action_at_time = pd.DataFrame(columns=["simulation_time", "port_id", "applied_action"])
    if not extra.empty:
        action_at_time = extra.copy()
        action_at_time["simulation_time"] = pd.to_datetime(action_at_time["simulation_time"], errors="coerce")
        action_at_time = (action_at_time.groupby(["simulation_time", "port_id"], as_index=False)["action"]
                          .agg(lambda s: ", ".join(sorted(set(map(str, s))))).rename(columns={"action": "applied_action"}))
    explorer_frame = x.merge(action_at_time, on=["simulation_time", "port_id"], how="left")
    explorer_frame["applied_action"] = explorer_frame["applied_action"].fillna("NONE")
    explorer_frame["evaluation_date"] = explorer_frame["simulation_time"].dt.strftime("%Y-%m-%d")
    baseline_long = explorer_frame.copy(); baseline_long["scenario"] = "BASELINE"; baseline_long["queue_selected_ce"] = baseline_long["queue_ce"]
    after_long = explorer_frame.copy(); after_long["scenario"] = "AFTER_ACTION"; after_long["queue_selected_ce"] = after_long["queue_ce_after"]
    explorer_frame = pd.concat([baseline_long, after_long], ignore_index=True)
    explorer = _dynamic_explorer(
        explorer_frame, "stage7-explorer",
        [("evaluation_date", "Tanggal"), ("port_id", "Pelabuhan"), ("scenario", "Skenario"),
         ("critical_case_status", "Status kritis"), ("applied_action", "Tindakan diterapkan")],
        [("Interval terpilih", "", "count"), ("Rerata antrean (CE)", "queue_selected_ce", "mean"),
         ("Antrean maksimum (CE)", "queue_selected_ce", "max"),
         ("Total layanan intervensi (CE)", "intervention_service_ce", "sum")],
        [{"type": "line", "x": "simulation_time", "y": "queue_selected_ce", "color": "scenario",
          "title": "Antrean pada pilihan aktif", "xTitle": "Waktu", "yTitle": "Queue (CE)", "rangeSlider": True},
         {"type": "bar-count", "x": "critical_case_status", "color": "scenario",
          "title": "Status kondisi kritis pada pilihan aktif"}],
        ["evaluation_date", "simulation_time", "port_id", "scenario", "queue_selected_ce",
         "critical_case_status", "applied_action", "intervention_service_ce"],
    )
    guide = '<div class="guide">Garis putus-putus adalah baseline. Garis penuh adalah hasil setelah intervensi. Batang pada panel bawah menunjukkan waktu dan kapasitas layanan tambahan; ini membedakan rekomendasi fuzzy dari intervensi yang benar-benar diterapkan.</div>'
    html = _write_report(Path(stage_dir)/"07_scenario_evaluation_dashboard.html",
                         "Stage 07 · Evaluasi skenario tindakan",
                         "Hasil skenario internal pada temporal holdout; bukan validasi empiris dampak intervensi.", cards,
                         [("Cara membaca", guide), ("Penyaring skenario", explorer), ("Skenario waktu keseluruhan", _fig_html(fig)),
                          ("Distribusi dampak harian", _fig_html(daily_plot)),
                          ("Perubahan status kritis", _fig_html(donut))])
    xlsx = write_excel_summary(Path(stage_dir)/"07_readable_results.xlsx", {
        "Ringkasan Utama": overall, "Per Pelabuhan": daily,
        "Rekomendasi Diterima": accepted, "Event Intervensi": extra,
    })
    return [html, xlsx]
