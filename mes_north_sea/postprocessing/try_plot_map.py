"""
Clean DAC placement map — 3 scenarios at neg=0.20

Usage:
    python plot_dac_map.py

Requirements:
    pip install geopandas matplotlib h5py numpy pandas openpyxl
"""
from __future__ import annotations
from pathlib import Path
import geopandas as gpd
import h5py
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import numpy as np
import pandas as pd


# ── config ────────────────────────────────────────────────────────────────────

RESULTS_BASE = Path(
    "/Users/maiant/PycharmProjects/Key-Infrastructure-North-Sea-CodeAndData"
    "/results/2040/emission_reduction"
)
NODES_FILE = Path(
    "/Users/maiant/PycharmProjects/Key-Infrastructure-North-Sea-CodeAndData"
    "/mes_north_sea/clean_data/nodes/nodes_2040.xlsx"
)
WORLD_ZIP  = Path("/tmp/ne_110m_admin_0_countries.zip")
OUT_PATH   = Path(
    "/Users/maiant/PycharmProjects/Key-Infrastructure-North-Sea-CodeAndData"
    "/results/figures/DAC_placement_neg0.20.png"
)

CY   = 2009
FRAC = 0.20

SCENARIOS = {
    "RE only":      "RE_only",
    "Onshore DAC":  "Onshore_DAC_only",
    "Offshore DAC": "Offshore_DAC_only",
}

EXTENT = (-5.5, 13, 49.5, 62.5)

COLOR_OFFSHORE = "#1d6fa4"
COLOR_ONSHORE  = "#c0392b"
COLOR_NODE_BG  = "#cccccc"

MAX_AREA = 1200
MIN_AREA = 30

COUNTRY_CENTROIDS = {
    "BE": (4.5,  50.5),
    "DE": (10.0, 51.0),
    "DK": (10.0, 56.0),
    "NL": (5.5,  52.2),
    "NO": (9.0,  61.5),
    "UK": (-2.0, 54.0),
}


# ── helpers ───────────────────────────────────────────────────────────────────

def get_scalar(ds) -> float:
    return float(np.array(ds[()]).flat[0])


def load_nodes(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Nodes_used")
    df.columns = [c.strip() for c in df.columns]
    df = df[~df["Type"].isin(["New_CO2_Storage_2040"])].copy()
    df = df.rename(columns={"x": "lon", "y": "lat"})
    return df[["Node", "Type", "Country", "lon", "lat"]]


def find_h5(stage: str, cy: int, frac: float) -> Path | None:
    folder = RESULTS_BASE / stage / f"cy{cy}"
    if not folder.exists():
        return None
    pattern = f"*_minCost_neg{frac:.2f}_cy{cy}-*/optimization_results.h5"
    matches = list(folder.glob(pattern))
    return matches[0] if matches else None


def load_dac(h5_path: Path, node_locs: pd.DataFrame) -> pd.DataFrame:
    records = []
    with h5py.File(h5_path, "r") as f:
        nodes_grp = f["design/nodes/period1"]
        for node in nodes_grp:
            for tec in nodes_grp[node]:
                if "DAC" not in tec:
                    continue
                size = get_scalar(nodes_grp[node][tec]["size"])
                if size < 1e-3:
                    continue
                records.append({
                    "node": node,
                    "size_mw": size,
                    "is_offshore": "offshore" in tec.lower(),
                })

    if not records:
        return pd.DataFrame(columns=["node", "size_mw", "is_offshore", "lon", "lat"])

    df = pd.DataFrame(records)
    df = df.merge(
        node_locs[["Node", "lon", "lat"]].rename(columns={"Node": "node"}),
        on="node", how="left"
    )
    missing = df[df["lon"].isna()]["node"].tolist()
    if missing:
        print(f"  [warn] no coordinates for: {missing}")
    return df.dropna(subset=["lon", "lat"])


def area_scale(sizes: pd.Series, vmax: float) -> np.ndarray:
    if vmax == 0:
        return np.full(len(sizes), MIN_AREA)
    return MIN_AREA + (sizes / vmax) * (MAX_AREA - MIN_AREA)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    node_locs = load_nodes(NODES_FILE)

    if WORLD_ZIP.exists():
        world = gpd.read_file(f"zip://{WORLD_ZIP}").to_crs("EPSG:4326")
    else:
        raise FileNotFoundError(
            f"Download shapefile:\n"
            f"  curl -L -o {WORLD_ZIP} "
            f"https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
        )

    # Load scenario data
    scenario_data = {}
    for label, stage in SCENARIOS.items():
        h5 = find_h5(stage, CY, FRAC)
        if h5 is None:
            print(f"[skip] missing h5 for {stage}")
            continue
        print(f"Loading {label}: {h5}")
        scenario_data[label] = load_dac(h5, node_locs)

    if not scenario_data:
        raise RuntimeError("No h5 files found. Check RESULTS_BASE path.")

    # Consistent size scale across all scenarios
    all_sizes = pd.concat([df["size_mw"] for df in scenario_data.values()])
    vmax = all_sizes.max() if not all_sizes.empty else 1.0

    # ── figure ────────────────────────────────────────────────────────────────
    ncols = len(scenario_data)
    fig, axes = plt.subplots(1, ncols, figsize=(6 * ncols, 7))
    if ncols == 1:
        axes = [axes]

    lon_min, lon_max, lat_min, lat_max = EXTENT

    bg_nodes = node_locs[
        node_locs["lon"].between(lon_min, lon_max) &
        node_locs["lat"].between(lat_min, lat_max)
    ]

    for ax, (label, df) in zip(axes, scenario_data.items()):
        # Basemap
        world.plot(ax=ax, color="#f0f0f0", edgecolor="#b0b0b0", linewidth=0.5)
        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        ax.set_aspect("equal")

        # Background nodes
        ax.scatter(bg_nodes["lon"], bg_nodes["lat"],
                   s=18, color=COLOR_NODE_BG, zorder=2,
                   linewidths=0, alpha=0.8)

        # Split offshore and onshore
        off = df[df["is_offshore"]]
        on  = df[~df["is_offshore"]]

        # Country labels on land — only for countries with built offshore DAC
        countries_with_offshore_dac = set(off["node"].str[:2].tolist()) if not off.empty else set()
        print(f"  [{label}] countries with offshore DAC: {countries_with_offshore_dac}")

        for country, (cx, cy_coord) in COUNTRY_CENTROIDS.items():
            if country in countries_with_offshore_dac:
                ax.text(
                    cx, cy_coord, country,
                    fontsize=9, fontweight="bold",
                    color="#333333", ha="center", va="center",
                    zorder=6,
                    bbox=dict(boxstyle="round,pad=0.25", fc="white",
                              alpha=0.75, ec="none"),
                )

        # Country labels on land — for countries with built onshore DAC
        countries_with_onshore_dac = set(on["node"].str[:2].tolist()) if not on.empty else set()
        print(f"  [{label}] countries with onshore DAC: {countries_with_onshore_dac}")

        for country, (cx, cy_coord) in COUNTRY_CENTROIDS.items():
            if country in countries_with_onshore_dac and country not in countries_with_offshore_dac:
                ax.text(
                    cx, cy_coord, country,
                    fontsize=9, fontweight="bold",
                    color="#333333", ha="center", va="center",
                    zorder=6,
                    bbox=dict(boxstyle="round,pad=0.25", fc="white",
                              alpha=0.75, ec="none"),
                )

        # Offshore DAC markers
        if not off.empty:
            ax.scatter(off["lon"], off["lat"],
                       s=area_scale(off["size_mw"], vmax),
                       color=COLOR_OFFSHORE, marker="o",
                       edgecolors="white", linewidths=0.8,
                       zorder=5, alpha=0.9)

        # Onshore DAC markers
        if not on.empty:
            ax.scatter(on["lon"], on["lat"],
                       s=area_scale(on["size_mw"], vmax),
                       color=COLOR_ONSHORE, marker="o",
                       edgecolors="white", linewidths=0.8,
                       zorder=5, alpha=0.9)

        ax.set_title(label, fontsize=13, fontweight="bold", pad=10)
        ax.set_xlabel("Longitude", fontsize=9)
        ax.set_ylabel("Latitude" if ax == axes[0] else "", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    # ── legend ────────────────────────────────────────────────────────────────
    ref_sizes = [10000, 30000, 50000]
    ref_handles = [
        mlines.Line2D([0], [0], marker="o", color="w",
                      markerfacecolor="#888888",
                      markersize=np.sqrt(area_scale(pd.Series([s]), vmax)[0]),
                      label=f"{s:,} MW")
        for s in ref_sizes
    ]

    type_handles = [
        mlines.Line2D([0], [0], marker="o", color="w",
                      markerfacecolor=COLOR_OFFSHORE,
                      markersize=10, label="Offshore DAC"),
        mlines.Line2D([0], [0], marker="o", color="w",
                      markerfacecolor=COLOR_ONSHORE,
                      markersize=10, label="Onshore DAC"),
        mlines.Line2D([0], [0], marker="o", color="w",
                      markerfacecolor=COLOR_NODE_BG,
                      markersize=6, label="Node (no DAC)"),
    ]

    fig.legend(
        handles=type_handles + ref_handles,
        loc="lower center", ncol=len(type_handles) + len(ref_handles),
        fontsize=9, frameon=False,
        bbox_to_anchor=(0.5, -0.04),
    )

    neg_mt = FRAC * 50.34
    fig.suptitle(
        f"DAC installed capacity — neg. emission target {neg_mt:.1f} Mt CO₂/yr  (cy{CY})",
        fontsize=13, fontweight="bold", y=1.01,
    )

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(OUT_PATH, dpi=180, bbox_inches="tight")
    fig.savefig(OUT_PATH.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved: {OUT_PATH}")
    print(f"Saved: {OUT_PATH.with_suffix('.pdf')}")


if __name__ == "__main__":
    main()