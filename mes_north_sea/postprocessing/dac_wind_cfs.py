"""
DAC operational pattern analysis across negative emission targets.
- Capacity factors computed only over nodes with installed DAC
- Wind-DAC correlation analysis added
Usage: /opt/anaconda3/bin/python plot_dac_operation.py
"""

from __future__ import annotations
from pathlib import Path
import h5py
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import pearsonr

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_DIR = Path(
    "/Users/maiant/PycharmProjects/Key-Infrastructure-North-Sea-CodeAndData"
    "/results/2040/emission_reduction/cy1995"
)

SCENARIOS = {
    "20250505122003_RE_only_minCost_E0.80_neg0.20_cy1995-1": 0.20,
    "20260505083229_RE_only_minCost_E0.80_neg0.40_cy1995-1": 0.40,
    "20260505102000_RE_only_minCost_E0.80_neg0.60_cy1995-1": 0.60,
    "20260505122003_RE_only_minCost_E0.80_neg0.80_cy1995-1": 0.80,
}

OFFSHORE_SUFFIX = ["_A", "_B", "_C", "_D", "_E", "_F", "_G", "_H",
                   "_I", "_J", "_K", "_L", "_ST1", "_ST2"]

DAC_TEC_ONSHORE  = "DAC_Adsorption_onshore"
DAC_TEC_OFFSHORE = "DAC_Adsorption_offshore"
WIND_OFFSHORE    = "Offshore_Wind"
WIND_ONSHORE     = "Onshore_Wind"

OUTPUT_DIR = BASE_DIR / "plots"
OUTPUT_DIR.mkdir(exist_ok=True)
HOURS = 8760


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_offshore(node: str) -> bool:
    return any(node.endswith(s) for s in OFFSHORE_SUFFIX)


def safe_read(group, key: str) -> np.ndarray | None:
    return group[key][()] if key in group else None


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_scenario(h5_path: Path) -> dict:
    # Per-node accumulators for capacity factor (only nodes with DAC)
    dac_on_cf_nodes  = []   # (total_output, max_possible) per node
    dac_off_cf_nodes = []

    # System-wide hourly aggregates
    dac_on_hourly   = np.zeros(HOURS)
    dac_off_hourly  = np.zeros(HOURS)
    wind_off_hourly = np.zeros(HOURS)  # aggregated capacity factor * size
    wind_on_hourly  = np.zeros(HOURS)

    # For correlation: collect matching (dac, wind) hourly pairs per node
    dac_on_wind_pairs  = []  # list of (dac_8760, wind_8760) arrays
    dac_off_wind_pairs = []

    with h5py.File(h5_path, "r") as f:
        design = f["design/nodes/period1"]
        tec_op = f["operation/technology_operation/period1"]

        for node in tec_op.keys():
            op_node  = tec_op[node]
            offshore = is_offshore(node)

            # ── Wind hourly output ──
            wind_series = None
            for wind_tec in [WIND_OFFSHORE, WIND_ONSHORE]:
                if wind_tec in op_node:
                    elec = safe_read(op_node[wind_tec], "electricity_output")
                    cf   = safe_read(op_node[wind_tec], "cap_factor")
                    if elec is not None:
                        if wind_tec == WIND_OFFSHORE:
                            wind_off_hourly += elec
                            wind_series = elec
                        else:
                            wind_on_hourly += elec
                            if wind_series is None:
                                wind_series = elec

            # ── DAC ──
            for tec_name, hourly_arr, cf_list, pair_list in [
                (DAC_TEC_ONSHORE,  dac_on_hourly,  dac_on_cf_nodes,  dac_on_wind_pairs),
                (DAC_TEC_OFFSHORE, dac_off_hourly, dac_off_cf_nodes, dac_off_wind_pairs),
            ]:
                if tec_name not in op_node:
                    continue

                co2 = safe_read(op_node[tec_name], "CO2captured_output")
                if co2 is None:
                    continue

                # Get installed size — only count this node if size > 0
                size = 0.0
                if node in design and tec_name in design[node]:
                    size = float(design[node][tec_name]["size"][()].flat[0])

                if size > 0:
                    # Capacity factor: mean hourly output / (size/8760 per hour)
                    # size is annual tCO2, so max hourly = size/8760
                    elec = safe_read(op_node[tec_name], "electricity_input")
                    max_elec = float(np.max(elec)) if elec is not None and np.max(elec) > 0 else 0.0
                    cf_val = float(np.mean(elec)) / max_elec if max_elec > 0 else np.nan
                    cf_list.append(cf_val)

                    hourly_arr += co2

                    # Wind correlation for this node
                    if wind_series is not None and len(wind_series) == HOURS:
                        pair_list.append((co2, wind_series))

    # Aggregate capacity factors (mean over active nodes only)
    def mean_cf(cf_list):
        valid = [v for v in cf_list if not np.isnan(v)]
        return float(np.mean(valid)) if valid else np.nan

    # Wind-DAC correlation: pool all node pairs
    def pooled_correlation(pairs):
        if not pairs:
            return np.nan, np.nan
        dac_all  = np.concatenate([p[0] for p in pairs])
        wind_all = np.concatenate([p[1] for p in pairs])
        # Remove hours where both are zero
        mask = (dac_all > 0) | (wind_all > 0)
        if mask.sum() < 10:
            return np.nan, np.nan
        r, p = pearsonr(dac_all[mask], wind_all[mask])
        return float(r), float(p)

    r_on,  _ = pooled_correlation(dac_on_wind_pairs)
    r_off, _ = pooled_correlation(dac_off_wind_pairs)

    return {
        "dac_onshore_cf":      mean_cf(dac_on_cf_nodes),
        "dac_offshore_cf":     mean_cf(dac_off_cf_nodes),
        "dac_onshore_hourly":  dac_on_hourly,
        "dac_offshore_hourly": dac_off_hourly,
        "wind_offshore_hourly":wind_off_hourly,
        "wind_onshore_hourly": wind_on_hourly,
        "corr_dac_on_wind":    r_on,
        "corr_dac_off_wind":   r_off,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    data = {}
    for folder, target in SCENARIOS.items():
        h5 = BASE_DIR / folder / "optimization_results.h5"
        if not h5.exists():
            print(f"Missing: {h5} — skipping")
            continue
        print(f"Loading {target:.0%}...")
        data[target] = extract_scenario(h5)

    targets = sorted(data.keys())
    labels  = [f"{t:.0%}" for t in targets]
    x       = np.arange(len(targets))
    blues   = plt.cm.Blues(np.linspace(0.4, 0.9, len(targets)))

    # ── Figure 1: Capacity factors (fixed) ───────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 5))

    for key, label, color, marker in [
        ("dac_onshore_cf",  "DAC onshore",  "#2c7bb6", "o"),
        ("dac_offshore_cf", "DAC offshore", "#74c476", "s"),
    ]:
        vals = [data[t].get(key, np.nan) for t in targets]
        if any(not np.isnan(v) for v in vals):
            ax.plot(x, vals, marker=marker, color=color,
                    linewidth=2, markersize=8, label=label)
            # Annotate values
            for xi, v in zip(x, vals):
                if not np.isnan(v):
                    ax.annotate(f"{v:.2f}", (xi, v),
                                textcoords="offset points", xytext=(0, 8),
                                ha="center", fontsize=9, color=color)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_xlabel("Negative emission target", fontsize=11)
    ax.set_ylabel("Capacity factor (–)", fontsize=11)
    ax.set_ylim(0, 1.1)
    ax.set_title("DAC capacity factor vs negative emission target\n(averaged over nodes with installed capacity)",
                 fontsize=11)
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "dac_capacity_factors.png", bbox_inches="tight", dpi=150)
    fig.savefig(OUTPUT_DIR / "dac_capacity_factors.pdf", bbox_inches="tight")
    print("Saved: dac_capacity_factors")
    plt.show()

    # ── Figure 2: Load duration curves ───────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("DAC load duration curves — North Sea 2040",
                 fontsize=13, fontweight="bold")

    for ax, key, title in [
        (axes[0], "dac_onshore_hourly",  "DAC onshore — CO₂ captured (t/hr)"),
        (axes[1], "dac_offshore_hourly", "DAC offshore — CO₂ captured (t/hr)"),
    ]:
        has_data = False
        for t, color in zip(targets, blues):
            series = data[t][key]
            if series.sum() == 0:
                continue
            ax.plot(np.sort(series)[::-1], color=color,
                    linewidth=1.8, label=f"{t:.0%}")
            has_data = True

        if has_data:
            ax.set_xlabel("Hours (sorted)", fontsize=11)
            ax.set_ylabel("CO₂ captured (t/hr)", fontsize=11)
            ax.set_title(title, fontsize=11)
            ax.legend(title="Target", fontsize=9)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
        else:
            ax.set_visible(False)

    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "dac_duration_curves.png", bbox_inches="tight", dpi=150)
    fig.savefig(OUTPUT_DIR / "dac_duration_curves.pdf", bbox_inches="tight")
    print("Saved: dac_duration_curves")
    plt.show()

    # ── Figure 3: Wind-DAC correlation ───────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 5))

    for key, label, color, marker in [
        ("corr_dac_on_wind",  "DAC onshore vs wind",  "#2c7bb6", "o"),
        ("corr_dac_off_wind", "DAC offshore vs wind", "#74c476", "s"),
    ]:
        vals = [data[t].get(key, np.nan) for t in targets]
        if any(not np.isnan(v) for v in vals):
            ax.plot(x, vals, marker=marker, color=color,
                    linewidth=2, markersize=8, label=label)
            for xi, v in zip(x, vals):
                if not np.isnan(v):
                    ax.annotate(f"{v:.2f}", (xi, v),
                                textcoords="offset points", xytext=(0, 8),
                                ha="center", fontsize=9, color=color)

    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_xlabel("Negative emission target", fontsize=11)
    ax.set_ylabel("Pearson correlation (–)", fontsize=11)
    ax.set_ylim(-1, 1)
    ax.set_title("Correlation between DAC operation and local wind output\n"
                 "(positive = DAC follows wind, negative = DAC avoids wind periods)",
                 fontsize=11)
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "dac_wind_correlation.png", bbox_inches="tight", dpi=150)
    fig.savefig(OUTPUT_DIR / "dac_wind_correlation.pdf", bbox_inches="tight")
    print("Saved: dac_wind_correlation")
    plt.show()

    # ── Print summary table ───────────────────────────────────────────────────
    print("\n── Summary ──")
    print(f"{'Target':>8} {'CF onshore':>12} {'CF offshore':>13} "
          f"{'r(DAC_on, wind)':>17} {'r(DAC_off, wind)':>18}")
    for t in targets:
        d = data[t]
        print(f"{t:>8.0%} "
              f"{d['dac_onshore_cf']:>12.3f} "
              f"{d['dac_offshore_cf']:>13.3f} "
              f"{d['corr_dac_on_wind']:>17.3f} "
              f"{d['corr_dac_off_wind']:>18.3f}")


if __name__ == "__main__":
    main()