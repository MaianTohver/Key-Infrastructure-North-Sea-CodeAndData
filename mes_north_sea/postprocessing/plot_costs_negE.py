"""
Two-panel cost analysis: absolute costs + indexed growth
Usage: /opt/anaconda3/bin/python plot_emission_reduction_costs.py
"""

from __future__ import annotations
from pathlib import Path
import h5py
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_DIR = Path("/Users/maiant/PycharmProjects/Key-Infrastructure-North-Sea-CodeAndData/results/2040/emission_reduction/RE_only/cy2009")

SCENARIOS = {
    "20260531094812_RE_only_minCost_neg0.20_cy2009-1": 0.20,
    "20260531120208_RE_only_minCost_neg0.40_cy2009-1": 0.40,
    "20260531142902_RE_only_minCost_neg0.60_cy2009-1": 0.60,
}

COST_COMPONENTS = {
    "cost_capex_tecs":  "Tech CAPEX",
    "cost_capex_netws": "Network CAPEX",
    "cost_opex_tecs":   "Tech OPEX",
    "cost_opex_netws":  "Network OPEX",
    "cost_imports":     "Import costs",
    "carbon_cost":      "Carbon cost",
}

COLORS = {
    "Tech CAPEX":     "#fefecd",
    "Network CAPEX":  "#cfe2d4",
    "Tech OPEX":      "#ffff9c",
    "Network OPEX":   "#a1b5a6",
    "Import costs":   "#c9c9c5",
    "Carbon cost":    "#a6bddb",
}

SCALE = 1e9  # EUR → bn EUR
OUTPUT_DIR = BASE_DIR / "plots"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_scenario(folder: str) -> dict:
    h5_path = BASE_DIR / folder / "optimization_results.h5"
    with h5py.File(h5_path, "r") as f:
        result = {}
        for key, label in COST_COMPONENTS.items():
            result[label] = float(f[f"summary/{key}"][()]) / SCALE
        result["Total cost"] = float(f["summary/total_cost"][()]) / SCALE
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    records = []
    for folder, target in SCENARIOS.items():
        data = load_scenario(folder)
        data["target"] = target
        records.append(data)

    df = pd.DataFrame(records).set_index("target").sort_index()
    labels = [f"{t:.0%}" for t in df.index]
    x = np.arange(len(df))
    bar_width = 0.5

    # Indexed to first scenario (0.2)
    df_indexed = (df.drop(columns="Total cost").div(df.drop(columns="Total cost").iloc[0]) - 1) * 100

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # ── Panel 1: Stacked bar ──────────────────────────────────────────────────
    bottom = np.zeros(len(df))
    for label, color in COLORS.items():
        if label not in df.columns:
            continue
        vals = df[label].values
        ax1.bar(x, vals, bar_width, bottom=bottom, label=label,
                color=color, edgecolor="white", linewidth=0.5)
        bottom += vals

    ax1.plot(x, df["Total cost"].values, color="black", marker="o",
             linewidth=1.8, markersize=7, label="Total system cost", zorder=5)

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=11)
    ax1.set_xlabel("Negative emission target", fontsize=11)
    ax1.set_ylabel("System cost (bn EUR/yr)", fontsize=11)
    ax1.set_title("Absolute system costs", fontsize=11)
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    ax1.legend(fontsize=8.5, framealpha=0.9)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    # ── Panel 2: Indexed growth ───────────────────────────────────────────────
    markers = ["o", "s", "^", "D", "v"]
    line_colors = [COLORS[l] for l in df_indexed.columns]

    for (label, color, marker) in zip(df_indexed.columns, line_colors, markers):
        ax2.plot(x, df_indexed[label].values, marker=marker,
                 color=color, linewidth=2, markersize=7, label=label)

    ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)

    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=11)
    ax2.set_xlabel("Negative emission target", fontsize=11)
    ax2.set_ylabel("Cost increase relative to 20% target (%)", fontsize=11)
    ax2.set_title("Percentage increase per cost component relative to the 20% target scenario", fontsize=11)
    ax2.legend(fontsize=8.5, framealpha=0.9)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    plt.tight_layout()

    out_pdf = OUTPUT_DIR / "cost_vs_neg_emission_target_baseline+space.pdf"
    out_png = OUTPUT_DIR / "cost_vs_neg_emission_target_baseline+space.png"
    fig.savefig(out_pdf, bbox_inches="tight")
    fig.savefig(out_png, bbox_inches="tight", dpi=150)
    print(f"Saved: {out_pdf}")
    plt.show()


if __name__ == "__main__":
    main()