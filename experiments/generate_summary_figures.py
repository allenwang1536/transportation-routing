"""
Generates two summary figures for the experiments folder:

  Table 1 (table1_worker_config_justification.png)
    9-cell grid: avg % improvement over baseline from step2_improver_screen.csv
    Rows = improver, Cols = guidance config
    Highlights the three chosen worker configurations.

  Figure 2 (fig2_full_5min_results.png)
    Line graph of final objective per instance for independent / one_way /
    bidirectional, from full_5min_20260504.csv.

Run from the repo root:
    conda run -n csci1470 python experiments/generate_summary_figures.py
"""

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "experiments"

# ─────────────────────────────────────────────────────────────────────────────
# TABLE 1 — Worker config justification
# ─────────────────────────────────────────────────────────────────────────────

def make_table1():
    df = pd.read_csv(ROOT / "python/experiments/results/step2_improver_screen.csv")

    def guidance(row):
        if row.granular and row.tabu:   return "granular + tabu"
        if row.granular:                return "granular"
        return "none"
    df["guidance"] = df.apply(guidance, axis=1)

    col_order = ["none", "granular", "granular + tabu"]
    row_order  = ["destroy_repair", "ejection_chains", "relocate_swap"]
    row_labels = ["destroy_repair", "ejection_chains", "relocate_swap"]

    pivot = (df.groupby(["improver", "guidance"])["percent_improvement_over_baseline"]
               .mean()
               .unstack()
               .reindex(index=row_order, columns=col_order))

    # Three cells we actually chose (row, col)
    chosen = {
        ("destroy_repair",  "granular"):       "W1",
        ("ejection_chains", "granular"):       "W2",
        ("relocate_swap",   "granular + tabu"): "W3",
    }

    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.axis("off")

    col_header = ["none", "granular", "granular + tabu"]
    cell_text  = []
    cell_colors = []

    for imp in row_order:
        row_vals   = []
        row_colors = []
        for col in col_order:
            val  = pivot.loc[imp, col]
            tag  = chosen.get((imp, col), "")
            label = f"{val:.2f}%"
            if tag:
                label = f"{val:.2f}%\n← {tag}"
            row_vals.append(label)

            # Color scheme: chosen cells gold, best-in-row (if not chosen) light green
            best_col = pivot.loc[imp].idxmax()
            if tag:
                row_colors.append("#ffd966")      # gold — chosen worker config
            elif col == best_col:
                row_colors.append("#d9ead3")      # light green — best in row
            else:
                row_colors.append("#f9f9f9")
        cell_text.append(row_vals)
        cell_colors.append(row_colors)

    table = ax.table(
        cellText=cell_text,
        cellColours=cell_colors,
        rowLabels=row_labels,
        colLabels=col_header,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.35, 2.2)

    # Bold the chosen cells
    for (imp, col), tag in chosen.items():
        r = row_order.index(imp) + 1   # +1 because row 0 = header
        c = col_order.index(col)
        cell = table[r, c]
        cell.set_text_props(fontweight="bold")

    # Column header styling
    for c in range(len(col_header)):
        table[0, c].set_facecolor("#cfe2f3")
        table[0, c].set_text_props(fontweight="bold")

    # Row label styling
    for r in range(1, len(row_order) + 1):
        table[r, -1].set_facecolor("#ead1dc")

    # Legend
    gold_patch  = mpatches.Patch(color="#ffd966", label="Chosen worker config (W1/W2/W3)")
    green_patch = mpatches.Patch(color="#d9ead3", label="Best in row (not chosen)")
    ax.legend(handles=[gold_patch, green_patch], loc="lower right",
              bbox_to_anchor=(1.0, -0.08), fontsize=9, framealpha=0.9)

    ax.set_title(
        "Avg % improvement over constructor baseline — improver × guidance\n"
        "(step2_improver_screen.csv, 10 s runs, all instances, seed 0)",
        fontsize=11, pad=14,
    )

    # Footnote for the relocate_swap choice
    footnote = (
        "* W3 uses relocate_swap + granular + tabu even though relocate_swap + none scores "
        "highest in isolation (+4.52%).\n"
        "  Difference is small (< 1 pp). With tabu enabled, W3 follows a distinct search "
        "trajectory from W1/W2 (both no-tabu),\n"
        "  improving ensemble diversity. Diagnostics confirmed W3 contributed the highest "
        "pool-acceptance rate (48%) among workers."
    )
    fig.text(0.01, -0.04, footnote, ha="left", va="top", fontsize=8,
             color="#444444", wrap=True)

    outpath = OUT / "table1_worker_config_justification.png"
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved → {outpath}")


# ─────────────────────────────────────────────────────────────────────────────
# FIGURE 2 — Final results across all instances
# ─────────────────────────────────────────────────────────────────────────────

def instance_sort_key(name: str) -> int:
    try:
        return int(name.split("_")[0])
    except ValueError:
        return 10**9

def make_fig2():
    csv_path = next(ROOT.glob("experiments/full_5min_*.csv"), None)
    if csv_path is None:
        raise FileNotFoundError("No full_5min_*.csv found in experiments/")

    df = pd.read_csv(csv_path)
    instances = sorted(df["instance"].unique(), key=instance_sort_key)

    # Normalize: % gap above the per-instance best model
    per_inst_min = df.groupby("instance")["objective"].min().rename("min_obj")
    df = df.join(per_inst_min, on="instance")
    df["gap_pct"] = (df["objective"] - df["min_obj"]) / df["min_obj"] * 100

    MODELS = ["independent", "one_way", "bidirectional"]
    MODEL_LABEL = {
        "independent":   "Independent (no sharing)",
        "one_way":       "One-way (workers → GA pool)",
        "bidirectional": "Bidirectional (full sharing)",
    }
    MODEL_COLOR = {
        "independent":   "#e74c3c",
        "one_way":       "#f39c12",
        "bidirectional": "#27ae60",
    }

    n  = len(instances)
    nb = len(MODELS)
    width  = 0.22
    gap    = 0.03
    group_w = nb * width + (nb - 1) * gap
    offsets = np.array([i * (width + gap) - group_w / 2 + width / 2 for i in range(nb)])

    fig, ax = plt.subplots(figsize=(16, 5))

    for bi, model in enumerate(MODELS):
        sub = df[df["model"] == model].set_index("instance")
        gaps = np.array([sub.loc[inst, "gap_pct"] if inst in sub.index else np.nan
                         for inst in instances])
        xs = np.arange(n) + offsets[bi]
        ax.bar(xs, gaps, width=width,
               color=MODEL_COLOR[model], label=MODEL_LABEL[model],
               alpha=0.85, zorder=3)
        # Annotate bars that are meaningfully above zero
        for xi, g in zip(xs, gaps):
            if np.isfinite(g) and g > 0.05:
                ax.text(xi, g + 0.03, f"{g:.1f}%",
                        ha="center", va="bottom", fontsize=6.5,
                        color=MODEL_COLOR[model], fontweight="bold")

    x_labels = [inst.replace(".vrp", "") for inst in instances]
    ax.set_xticks(np.arange(n))
    ax.set_xticklabels(x_labels, rotation=35, ha="right", fontsize=8.5)
    ax.set_xlabel("Instance (ordered by customer count)", fontsize=11)
    ax.set_ylabel("% above per-instance best model (lower = better)", fontsize=11)
    ax.set_title(
        "% gap from best model per instance — 5-minute runs, seed 42\n"
        "(0 = tied for best on that instance; bars show how much worse each model is)",
        fontsize=11,
    )
    ax.legend(fontsize=10, loc="upper left")
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=0.35)
    ax.grid(axis="x", alpha=0.12)

    plt.tight_layout()
    outpath = OUT / "fig2_full_5min_results.png"
    plt.savefig(outpath, dpi=150)
    plt.close()
    print(f"Saved → {outpath}")


# ─────────────────────────────────────────────────────────────────────────────
# TABLE 2 — Baseline vs bidirectional comparison
# ─────────────────────────────────────────────────────────────────────────────

def make_comparison_table():
    base = pd.read_csv(ROOT / "experiments/hgs_full_5min_20260505.csv")[["instance", "objective"]]
    base = base.rename(columns={"objective": "baseline"})

    mt = pd.read_csv(next(ROOT.glob("experiments/full_5min_*.csv")))
    bidir = mt[mt["model"] == "bidirectional"][
        ["instance", "objective", "accepted_seeds", "accepted_children", "accepted_migrants"]
    ].copy()
    bidir["total_accepted"] = (
        bidir["accepted_seeds"] + bidir["accepted_children"] + bidir["accepted_migrants"]
    )
    bidir = bidir.rename(columns={"objective": "bidirectional"})

    df = base.merge(bidir[["instance", "bidirectional", "total_accepted"]], on="instance")
    df["pct_diff"] = (df["bidirectional"] - df["baseline"]) / df["baseline"] * 100
    df = df.sort_values("instance", key=lambda s: s.map(instance_sort_key))

    col_labels = [
        "Instance",
        "Baseline obj\n(HGS standalone)",
        "Bidirectional obj\n(3-worker MT)",
        "% diff\n(neg = MT better)",
        "Accepted pool\ninsertions",
    ]

    cell_text   = []
    cell_colors = []
    for _, row in df.iterrows():
        pct = row["pct_diff"]
        pct_str = f"{pct:+.2f}%" if pct != 0 else "—"
        cell_text.append([
            row["instance"].replace(".vrp", ""),
            f"{row['baseline']:,.2f}",
            f"{row['bidirectional']:,.2f}",
            pct_str,
            f"{int(row['total_accepted']):,}",
        ])
        if pct < -0.5:
            diff_color = "#d9ead3"   # green — meaningful improvement
        elif pct < 0:
            diff_color = "#f3f9ef"   # pale green — minor improvement
        else:
            diff_color = "#f9f9f9"
        cell_colors.append(["#f9f9f9", "#f9f9f9", "#f9f9f9", diff_color, "#f9f9f9"])

    fig, ax = plt.subplots(figsize=(13, 7.5))
    ax.axis("off")

    table = ax.table(
        cellText=cell_text,
        cellColours=cell_colors,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1.0, 1.7)

    for c in range(len(col_labels)):
        table[0, c].set_facecolor("#cfe2f3")
        table[0, c].set_text_props(fontweight="bold")

    ax.set_title(
        "HGS standalone (baseline) vs bidirectional multithreaded — 5-minute runs, seed 42\n"
        "Accepted pool insertions = accepted_seeds + accepted_children + accepted_migrants",
        fontsize=11, pad=14,
    )

    green_patch = mpatches.Patch(color="#d9ead3", label="% improvement > 0.5 pp")
    pale_patch  = mpatches.Patch(color="#f3f9ef", label="% improvement 0–0.5 pp")
    ax.legend(handles=[green_patch, pale_patch], loc="lower right",
              bbox_to_anchor=(1.0, -0.04), fontsize=9, framealpha=0.9)

    outpath = OUT / "table2_baseline_vs_bidirectional.png"
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved → {outpath}")


if __name__ == "__main__":
    make_table1()
    make_fig2()
    make_comparison_table()
