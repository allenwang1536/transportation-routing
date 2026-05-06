"""
Diversity diagnostics visualizer for the GA + 3-worker solver.

Usage (from repo root):
    conda run -n csci1470 python experiments/plot_diversity.py \\
        experiments/diag_386_47_1_<timestamp>

Pass the prefix (without _*.csv suffix).  Four figures are produced and
saved as PNGs next to the CSV files.
"""

import sys
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

# ── Color palette ─────────────────────────────────────────────────────────────
WORKER_COLORS = {"worker_0": "#e74c3c", "worker_1": "#3498db", "worker_2": "#2ecc71"}
SOURCE_COLORS  = {**WORKER_COLORS, "hgs_child": "#9b59b6", "seed": "#95a5a6"}
SOURCE_ORDER   = ["worker_0", "worker_1", "worker_2", "hgs_child", "seed"]
SOURCE_LABELS  = {"worker_0": "W0 (destroy_repair)", "worker_1": "W1 (ejection_chains)",
                  "worker_2": "W2 (relocate_swap)",  "hgs_child": "HGS child",
                  "seed": "Seed"}


def load(prefix: str):
    p = Path(prefix)
    div  = pd.read_csv(str(p) + "_worker_diversity.csv")
    inj  = pd.read_csv(str(p) + "_injections.csv")
    snap = pd.read_csv(str(p) + "_pop_snapshots.csv")
    return div, inj, snap


# ── Figure 1: Worker pairwise diversity over time ─────────────────────────────
def plot_worker_diversity(div: pd.DataFrame, out: str):
    fig, ax = plt.subplots(figsize=(12, 4))

    pairs = [
        ("dist_W0_W1", "W0 vs W1", "#e67e22"),
        ("dist_W0_W2", "W0 vs W2", "#27ae60"),
        ("dist_W1_W2", "W1 vs W2", "#2980b9"),
    ]
    for col, label, color in pairs:
        valid = div[div[col] >= 0]
        if valid.empty:
            continue
        ax.plot(valid["time_s"], valid[col], label=label, color=color,
                linewidth=1.2, alpha=0.85)

    ax.set_xlabel("Wall-clock time (s)", fontsize=11)
    ax.set_ylabel("Broken-pairs distance", fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.set_title("Pairwise worker diversity over time\n"
                 "(high = workers exploring different regions; crash to 0 = convergence)",
                 fontsize=11)
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  → {out}")


# ── Figure 2: Injection acceptance breakdown ──────────────────────────────────
def plot_injections_overview(inj: pd.DataFrame, out: str):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # ── 2a: Acceptance counts (stacked bar) ───────────────────────────────────
    ax = axes[0]
    sources = [s for s in SOURCE_ORDER if s in inj["source"].values]
    accepted_counts  = [inj[(inj["source"] == s) & (inj["accepted"] == 1)].shape[0] for s in sources]
    rejected_counts  = [inj[(inj["source"] == s) & (inj["accepted"] == 0)].shape[0] for s in sources]
    x = np.arange(len(sources))
    bars_a = ax.bar(x, accepted_counts,  label="Accepted", color=[SOURCE_COLORS[s] for s in sources],
                    alpha=0.85)
    bars_r = ax.bar(x, rejected_counts, bottom=accepted_counts, label="Rejected",
                    color=[SOURCE_COLORS[s] for s in sources], alpha=0.35, hatch="//")
    for i, (a, r) in enumerate(zip(accepted_counts, rejected_counts)):
        total = a + r
        pct = 100 * a / total if total > 0 else 0
        ax.text(i, total + 1, f"{pct:.0f}%", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([SOURCE_LABELS.get(s, s) for s in sources], rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Count")
    ax.set_title("Acceptance count by source\n(% = acceptance rate)", fontsize=10)
    ax.legend(fontsize=9)

    # ── 2b: Diversity score by source (violin) ────────────────────────────────
    ax = axes[1]
    data_accepted  = [inj[(inj["source"] == s) & (inj["accepted"] == 1)]["diversity_score"].values
                      for s in sources]
    data_rejected  = [inj[(inj["source"] == s) & (inj["accepted"] == 0)]["diversity_score"].values
                      for s in sources]
    x = np.arange(len(sources))
    w = 0.35
    bp_a = ax.boxplot([d for d in data_accepted if len(d) > 0],
                      positions=[xi - w/2 for xi, d in zip(x, data_accepted) if len(d) > 0],
                      widths=w, patch_artist=True, showfliers=False,
                      boxprops=dict(facecolor="#cfe2f3"), medianprops=dict(color="black"))
    if any(len(d) > 0 for d in data_rejected):
        bp_r = ax.boxplot([d for d in data_rejected if len(d) > 0],
                          positions=[xi + w/2 for xi, d in zip(x, data_rejected) if len(d) > 0],
                          widths=w, patch_artist=True, showfliers=False,
                          boxprops=dict(facecolor="#fce8e8"), medianprops=dict(color="black"))
    ax.set_xticks(x)
    ax.set_xticklabels([SOURCE_LABELS.get(s, s) for s in sources], rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Diversity score (broken-pairs dist to nearest pool member)")
    ax.set_title("Diversity of accepted (blue) vs rejected (red)\n"
                 "candidates by source", fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    # ── 2c: Running max diversity contributed per source ──────────────────────
    ax = axes[2]
    for s in sources:
        sub = inj[(inj["source"] == s) & (inj["accepted"] == 1)].sort_values("time_s")
        if sub.empty:
            continue
        running_max = sub["diversity_score"].cummax()
        ax.plot(sub["time_s"], running_max, label=SOURCE_LABELS.get(s, s),
                color=SOURCE_COLORS.get(s, "gray"), linewidth=1.5)
    ax.set_xlabel("Wall-clock time (s)", fontsize=10)
    ax.set_ylabel("Running max diversity score of accepted candidates", fontsize=9)
    ax.set_title("Running max diversity contributed\n(addresses: does max matter more than avg?)",
                 fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  → {out}")


# ── Figure 3: Injection scatter (diversity × time, color=source) ──────────────
def plot_injection_scatter(inj: pd.DataFrame, out: str):
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    for ax, show_accepted in zip(axes, [True, False]):
        sub = inj[inj["accepted"] == (1 if show_accepted else 0)]
        for s in SOURCE_ORDER:
            rows = sub[sub["source"] == s]
            if rows.empty:
                continue
            ax.scatter(rows["time_s"], rows["diversity_score"],
                       c=SOURCE_COLORS.get(s, "gray"),
                       label=SOURCE_LABELS.get(s, s),
                       alpha=0.5, s=8,
                       marker="o" if show_accepted else "x")
        ax.set_xlabel("Wall-clock time (s)")
        ax.set_ylabel("Diversity score")
        ax.set_ylim(-0.02, 1.05)
        title = "Accepted" if show_accepted else "Rejected"
        ax.set_title(f"{title} pool insertions over time\n"
                     "(diversity = broken-pairs dist to nearest pool member)", fontsize=10)
        ax.legend(fontsize=8, markerscale=2)
        ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  → {out}")


# ── Figure 4: Population health over time ─────────────────────────────────────
def plot_pop_health(snap: pd.DataFrame, inj: pd.DataFrame, out: str):
    fig, ax1 = plt.subplots(figsize=(12, 4))

    # Left: avg pairwise diversity
    ax1.set_xlabel("Wall-clock time (s)")
    ax1.set_ylabel("Avg pairwise diversity (pool)", color="#2980b9")
    ax1.plot(snap["time_s"], snap["avg_pairwise_dist"],
             color="#2980b9", linewidth=2, label="Avg pool diversity")
    ax1.tick_params(axis="y", labelcolor="#2980b9")
    ax1.set_ylim(0, 1.0)

    # Right: best + worst objective
    ax2 = ax1.twinx()
    ax2.set_ylabel("Objective", color="#e74c3c")
    ax2.plot(snap["time_s"], snap["best_obj"],
             color="#e74c3c", linewidth=2, linestyle="-",  label="Pool best obj")
    ax2.plot(snap["time_s"], snap["worst_obj"],
             color="#e74c3c", linewidth=1.2, linestyle="--", alpha=0.5, label="Pool worst obj")
    ax2.tick_params(axis="y", labelcolor="#e74c3c")

    # Worker push timeline (rug plot at top)
    for s in ["worker_0", "worker_1", "worker_2"]:
        pushes = inj[(inj["source"] == s) & (inj["accepted"] == 1)]["time_s"]
        ax1.vlines(pushes, 0.98, 1.02, color=SOURCE_COLORS[s], linewidth=0.8, alpha=0.4)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=9)

    ax1.set_title("Population health over time\n"
                  "(rug marks at top = accepted worker injections by color)", fontsize=10)
    ax1.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  → {out}")


# ── Figure 5: Worker objective trajectory ─────────────────────────────────────
def plot_worker_objectives(inj: pd.DataFrame, out: str):
    fig, ax = plt.subplots(figsize=(12, 4))

    for s in ["worker_0", "worker_1", "worker_2"]:
        sub = inj[inj["source"] == s].sort_values("time_s")
        if sub.empty:
            continue
        # Running minimum objective submitted by this worker over time
        running_min = sub["objective"].cummin()
        ax.step(sub["time_s"], running_min,
                label=SOURCE_LABELS[s], color=WORKER_COLORS[s], linewidth=1.8, where="post")

    ax.set_xlabel("Wall-clock time (s)")
    ax.set_ylabel("Worker personal best objective (submitted to pool)")
    ax.set_title("Worker objective trajectory\n"
                 "(running minimum of each worker's pushed objectives)", fontsize=10)
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  → {out}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python plot_diversity.py <diag_prefix>", file=sys.stderr)
        sys.exit(1)

    prefix = sys.argv[1]
    div, inj, snap = load(prefix)

    print(f"Loaded diagnostics from {prefix}_*.csv")
    print(f"  worker_diversity: {len(div)} rows")
    print(f"  injections:       {len(inj)} rows  "
          f"({inj['accepted'].sum()} accepted, {(~inj['accepted'].astype(bool)).sum()} rejected)")
    print(f"  pop_snapshots:    {len(snap)} rows")
    print()
    print("Generating plots...")

    plot_worker_diversity(div,    prefix + "_fig1_worker_diversity.png")
    plot_injections_overview(inj, prefix + "_fig2_injections_overview.png")
    plot_injection_scatter(inj,   prefix + "_fig3_injection_scatter.png")
    plot_pop_health(snap, inj,    prefix + "_fig4_pop_health.png")
    plot_worker_objectives(inj,   prefix + "_fig5_worker_objectives.png")

    # ── Summary stats ─────────────────────────────────────────────────────────
    print("\n── Injection summary ──────────────────────────────────────────────")
    g = inj.groupby("source")
    summary = pd.DataFrame({
        "total":         g.size(),
        "accepted":      g["accepted"].sum(),
        "accept_rate":   g["accepted"].mean().map("{:.1%}".format),
        "div_mean_acc":  inj[inj["accepted"]==1].groupby("source")["diversity_score"].mean().map("{:.3f}".format),
        "div_max_acc":   inj[inj["accepted"]==1].groupby("source")["diversity_score"].max().map("{:.3f}".format),
    }).reindex(SOURCE_ORDER).dropna(how="all")
    print(summary.to_string())

    if not div.empty:
        print("\n── Worker pairwise diversity (final values) ───────────────────────")
        last = div.iloc[-1]
        print(f"  W0 vs W1: {last.get('dist_W0_W1', 'N/A'):.4f}")
        print(f"  W0 vs W2: {last.get('dist_W0_W2', 'N/A'):.4f}")
        print(f"  W1 vs W2: {last.get('dist_W1_W2', 'N/A'):.4f}")


if __name__ == "__main__":
    main()
