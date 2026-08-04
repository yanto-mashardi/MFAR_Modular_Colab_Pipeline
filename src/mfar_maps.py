"""Deterministic, semantically audited Folium maps for MFAR Stages 01–02."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


ESRI_OCEAN_BASE = (
    "https://services.arcgisonline.com/ArcGIS/rest/services/"
    "Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
)
ESRI_OCEAN_REFERENCE = (
    "https://services.arcgisonline.com/ArcGIS/rest/services/"
    "Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}"
)
GEBCO_2026_WMS = "https://wms.gebco.net/2026/mapserv?"
GEBCO_2026_LAYER = "gebco_2026_2"
ESRI_OCEAN_ATTRIBUTION = (
    "Tiles &copy; Esri; data: Esri, Garmin, GEBCO, NOAA NGDC, "
    "and other contributors"
)
GEBCO_ATTRIBUTION = "Bathymetry: GEBCO Compilation Group (2026), GEBCO_2026 Grid"


def _haversine_nm(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 3440.065 * 2 * np.arcsin(np.sqrt(a))


def segment_trajectories(
    frame: pd.DataFrame,
    time_col: str,
    max_gap_min: float = 20.0,
    max_jump_nm: float = 1.5,
) -> pd.DataFrame:
    """Split tracks at vessel/day/time-gap/spatial-jump boundaries."""
    out = frame.copy()
    out[time_col] = pd.to_datetime(out[time_col], errors="coerce")
    out = out.dropna(subset=[time_col, "mmsi", "latitude", "longitude"])
    out = out.sort_values(["mmsi", time_col]).reset_index(drop=True)
    group = out.groupby("mmsi", sort=False)
    gap = group[time_col].diff().dt.total_seconds().div(60)
    prev_lat = group["latitude"].shift()
    prev_lon = group["longitude"].shift()
    jump = _haversine_nm(prev_lat, prev_lon, out["latitude"], out["longitude"])
    day_change = group[time_col].shift().dt.date.ne(out[time_col].dt.date)
    status = out.get("operational_status", pd.Series("", index=out.index)).astype(str)
    prev_status = status.groupby(out["mmsi"]).shift().fillna("")
    voyage_boundary = (
        prev_status.str.startswith("AT_BERTH")
        & status.str.match(r"DEPARTING|SAILING")
    )
    boundary = gap.isna() | gap.gt(max_gap_min) | pd.Series(jump, index=out.index).gt(max_jump_nm) | day_change | voyage_boundary
    out["map_segment_id"] = boundary.groupby(out["mmsi"]).cumsum().astype(int)
    out["map_gap_min"] = gap
    out["map_jump_nm"] = jump
    return out


def audit_folium_html(path: Path, expected_points: int, expected_segments: int) -> dict:
    """Fail when generated HTML cannot represent the requested layers."""
    text = Path(path).read_text(encoding="utf-8")
    declared = re.findall(r"(?:var|let|const)\s+([a-z_]+_[0-9a-f]{32})\s*=", text)
    duplicate_ids = len(declared) - len(set(declared))
    circle_count = text.count("L.circleMarker(")
    polyline_count = text.count("L.polyline(")
    tile_count = text.count("L.tileLayer(")
    wms_count = text.count("L.tileLayer.wms(")
    checks = {
        "html_bytes": Path(path).stat().st_size,
        "declared_js_objects": len(declared),
        "duplicate_js_ids": duplicate_ids,
        "rendered_point_layers": circle_count,
        "rendered_polyline_layers": polyline_count,
        "tile_layers": tile_count,
        "wms_layers": wms_count,
        "has_ocean_basemap": "World_Ocean_Base" in text,
        "has_ocean_reference": "World_Ocean_Reference" in text,
        "has_gebco_2026": GEBCO_2026_WMS in text and GEBCO_2026_LAYER in text,
        "has_navigation_disclaimer": "bukan untuk navigasi" in text.lower(),
        "has_layer_control": "L.control.layers(" in text,
        "expected_sampled_points": int(expected_points),
        "expected_track_segments": int(expected_segments),
    }
    failures = []
    if duplicate_ids:
        failures.append(f"{duplicate_ids} JavaScript IDs are duplicated")
    if tile_count < 3:
        failures.append("ocean basemap, reference labels, or fallback basemap is missing")
    if wms_count < 1:
        failures.append("GEBCO bathymetry WMS layer is missing")
    if not checks["has_ocean_basemap"]:
        failures.append("Esri World Ocean Base is missing")
    if not checks["has_ocean_reference"]:
        failures.append("Esri World Ocean Reference is missing")
    if not checks["has_gebco_2026"]:
        failures.append("explicit GEBCO 2026 bathymetry is missing")
    if not checks["has_navigation_disclaimer"]:
        failures.append("navigation-safety disclaimer is missing")
    if not checks["has_layer_control"]:
        failures.append("layer control is missing")
    if circle_count < expected_points:
        failures.append(f"only {circle_count}/{expected_points} point layers")
    if polyline_count < expected_segments:
        failures.append(f"only {polyline_count}/{expected_segments} trajectory layers")
    if "fitBounds(" not in text:
        failures.append("map bounds were not fitted")
    checks["status"] = "PASS" if not failures else "FAIL"
    checks["failures"] = failures
    audit_path = Path(path).with_suffix(".map-audit.json")
    audit_path.write_text(json.dumps(checks, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError(f"Semantic map audit failed for {path.name}: {'; '.join(failures)}")
    return checks


def build_validation_map(
    frame: pd.DataFrame,
    berths: pd.DataFrame,
    path: Path,
    time_col: str,
    original: pd.DataFrame | None = None,
    original_time_col: str = "timestamp",
    max_points: int = 2500,
    max_original_points: int = 1200,
) -> tuple[Path, pd.DataFrame, dict]:
    """Create a map whose lines never connect unrelated voyages or days."""
    import folium
    from branca.element import Element
    from folium.plugins import Fullscreen, MeasureControl

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    segmented = segment_trajectories(frame, time_col)
    if segmented.empty:
        raise ValueError("No valid spatial records available for map generation")
    if len(segmented) > max_points:
        take = np.linspace(0, len(segmented) - 1, max_points).astype(int)
        points = segmented.iloc[take].copy()
    else:
        points = segmented.copy()

    center = [float(segmented["latitude"].median()), float(segmented["longitude"].median())]
    fmap = folium.Map(location=center, zoom_start=12, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles=ESRI_OCEAN_BASE,
        name="Peta laut · Esri Ocean Base",
        attr=ESRI_OCEAN_ATTRIBUTION,
        overlay=False,
        control=True,
        show=True,
        max_native_zoom=9,
        max_zoom=16,
    ).add_to(fmap)
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="Peta jalan · OpenStreetMap (fallback)",
        overlay=False,
        control=True,
        show=False,
    ).add_to(fmap)
    folium.raster_layers.WmsTileLayer(
        url=GEBCO_2026_WMS,
        layers=GEBCO_2026_LAYER,
        name="Batimetri berwarna · GEBCO 2026",
        attr=GEBCO_ATTRIBUTION,
        fmt="image/png",
        transparent=True,
        overlay=True,
        control=True,
        show=True,
        opacity=0.62,
        version="1.3.0",
    ).add_to(fmap)
    folium.TileLayer(
        tiles=ESRI_OCEAN_REFERENCE,
        name="Label dan kedalaman laut · Esri",
        attr=ESRI_OCEAN_ATTRIBUTION,
        overlay=True,
        control=True,
        show=True,
        max_native_zoom=9,
        max_zoom=16,
    ).add_to(fmap)

    berth_layer = folium.FeatureGroup(name="Terminal dan titik muat", show=True)
    for port_id, terminal in berths.groupby("port_id", sort=False):
        terminal_lat = float(pd.to_numeric(terminal["latitude"], errors="coerce").mean())
        terminal_lon = float(pd.to_numeric(terminal["longitude"], errors="coerce").mean())
        folium.Marker(
            [terminal_lat, terminal_lon],
            tooltip=f"Terminal {port_id}",
            popup=(f"<b>Terminal {port_id}</b><br>Lokasi pusat dari titik "
                   "dermaga pada konfigurasi penelitian."),
            icon=folium.Icon(color="darkblue", icon="anchor", prefix="fa"),
        ).add_to(berth_layer)
    for _, berth in berths.iterrows():
        folium.CircleMarker(
            [float(berth["latitude"]), float(berth["longitude"])],
            radius=6,
            color="#f9a825",
            weight=2,
            fill=True,
            fill_color="#ffeb3b",
            fill_opacity=0.92,
            tooltip=f"Titik muat · {berth['berth_id']}",
            popup=(f"<b>{berth['port_id']} · {berth['berth_id']}</b><br>"
                   f"Koordinat: {float(berth['latitude']):.6f}, "
                   f"{float(berth['longitude']):.6f}<br>"
                   f"Radius okupansi model: {float(berth['occupancy_radius_nm']):.2f} NM"),
        ).add_to(berth_layer)
    berth_layer.add_to(fmap)

    colors = ["#0b5fa5", "#ef6c00", "#7b1fa2", "#00897b", "#c62828", "#455a64"]
    track_layer = folium.FeatureGroup(name="Lintasan kapal", show=True)
    segment_count = 0
    for (mmsi, segment_id), group in segmented.groupby(["mmsi", "map_segment_id"], sort=False):
        if len(group) < 2:
            continue
        color = colors[hash(str(mmsi)) % len(colors)]
        folium.PolyLine(
            group[["latitude", "longitude"]].to_numpy().tolist(),
            color=color,
            weight=3,
            opacity=0.75,
            tooltip=f"MMSI {mmsi} · segmen {segment_id}",
        ).add_to(track_layer)
        segment_count += 1
    track_layer.add_to(fmap)

    point_layer = folium.FeatureGroup(name="Titik hasil tahap", show=True)
    for _, row in points.iterrows():
        folium.CircleMarker(
            [float(row["latitude"]), float(row["longitude"])],
            radius=2.5,
            color="#0b5fa5",
            weight=1,
            fill=True,
            fill_opacity=0.75,
            tooltip=f"MMSI {row['mmsi']} · {row[time_col]}",
        ).add_to(point_layer)
    point_layer.add_to(fmap)

    original_count = 0
    if original is not None and not original.empty:
        original_layer = folium.FeatureGroup(name="Titik AIS asli", show=True)
        source = original.dropna(subset=["latitude", "longitude"]).copy()
        if len(source) > max_original_points:
            source = source.iloc[np.linspace(0, len(source) - 1, max_original_points).astype(int)]
        for _, row in source.iterrows():
            folium.CircleMarker(
                [float(row["latitude"]), float(row["longitude"])], radius=1.5,
                color="#333333", weight=1, fill=True, fill_opacity=0.55,
                tooltip=f"AIS asli · {row.get(original_time_col, '')}",
            ).add_to(original_layer)
        original_layer.add_to(fmap)
        original_count = len(source)

    note = Element("""
    <div style="position:fixed;bottom:28px;left:10px;z-index:9999;max-width:310px;
                background:rgba(255,255,255,.94);padding:9px 11px;border:1px solid #667;
                border-radius:5px;font:12px/1.35 Arial;color:#17233b">
      <b>Peta laut dan batimetri</b><br>
      Aktifkan “Batimetri berwarna · GEBCO 2026” pada kontrol layer. Nilai elevasi
      GEBCO menggunakan meter; nilai negatif berada di bawah muka laut. Resolusi
      grid global 15 arc-second tidak mewakili survei hidrografi rinci di alur sempit.
      <b>Visualisasi ini bukan untuk navigasi atau keselamatan pelayaran.</b>
    </div>
    """)
    fmap.get_root().html.add_child(note)
    Fullscreen(position="topleft", title="Layar penuh", title_cancel="Keluar layar penuh").add_to(fmap)
    MeasureControl(position="topleft", primary_length_unit="nautical-miles").add_to(fmap)
    folium.LatLngPopup().add_to(fmap)

    fmap.fit_bounds([
        [float(segmented["latitude"].min()), float(segmented["longitude"].min())],
        [float(segmented["latitude"].max()), float(segmented["longitude"].max())],
    ])
    folium.LayerControl(collapsed=False).add_to(fmap)
    fmap.save(str(path))
    audit = audit_folium_html(path, len(points) + original_count, segment_count)
    summary = (segmented.groupby(["mmsi", "map_segment_id"], as_index=False)
               .agg(start=(time_col, "min"), end=(time_col, "max"), points=(time_col, "size"),
                    max_gap_min=("map_gap_min", "max"), max_jump_nm=("map_jump_nm", "max")))
    return path, summary, audit
