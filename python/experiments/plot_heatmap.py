"""
Heatmap: improver × guidance combination, colored by
average % improvement over baseline (higher = better).

Run from the repo root:
    python python/experiments/plot_heatmap.py
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import os

CSV = os.path.join(os.path.dirname(__file__), "results", "step2_improver_screen.csv")

df = pd.read_csv(CSV)

# ── Build a human-readable guidance label ────────────────────────────────────
def guidance_label(row):
    if row["granular"] and row["tabu"]:
        return "granular + tabu"
    elif row["granular"]:
        return "granular"
    else:
        return "none"

df["guidance"] = df.apply(guidance_label, axis=1)

# ── Normalize objective per instance so large instances don't dominate ───────
# For each instance, compute the best objective seen across all modes.
# Cell metric: how many % above the per-instance best?  (0 = best on that instance)
df["instance_best"] = df.groupby("instance")["objective"].transform("min")
df["pct_above_best"] = (df["objective"] - df["instance_best"]) / df["instance_best"] * 100

# ── Pivot: rows = improver, cols = guidance, value = mean pct_above_best ─────
GUIDANCE_ORDER = ["none", "granular", "granular + tabu"]
improvers = sorted(df["improver"].unique())

pivot_above = (
    df.groupby(["improver", "guidance"])["pct_above_best"]
    .mean()
    .unstack("guidance")
    .reindex(columns=GUIDANCE_ORDER)
)

# Also keep percent_improvement_over_baseline for annotation
pivot_pct = (
    df.groupby(["improver", "guidance"])["percent_improvement_over_baseline"]
    .mean()
    .unstack("guidance")
    .reindex(columns=GUIDANCE_ORDER)
)

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, max(4, len(improvers) * 1.4)))

data = pivot_above.values          # lower = better (% above per-instance best)
vmin, vmax = 0, np.nanmax(data) if np.nanmax(data) > 0 else 1

# Green-yellow-red: 0 (green, best) → max (red, worst)
cmap = mcolors.LinearSegmentedColormap.from_list(
    "gyr", ["#2ecc71", "#f1c40f", "#e74c3c"]
)
im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")

ax.set_xticks(range(len(GUIDANCE_ORDER)))
ax.set_xticklabels(GUIDANCE_ORDER, fontsize=11)
ax.set_yticks(range(len(pivot_above.index)))
ax.set_yticklabels(pivot_above.index, fontsize=11)

ax.set_xlabel("Guidance", fontsize=12)
ax.set_ylabel("Improver", fontsize=12)
ax.set_title(
    "Improver × Guidance — avg % above per-instance best (lower = better)\n"
    "Annotations: [% above best | avg % improvement over constructor baseline]",
    fontsize=10,
    pad=12,
)

# Annotate each cell
for i, improver in enumerate(pivot_above.index):
    for j, guidance in enumerate(GUIDANCE_ORDER):
        above = pivot_above.loc[improver, guidance]
        pct   = pivot_pct.loc[improver, guidance]
        if pd.isna(above):
            txt = "n/a"
        else:
            txt = f"+{above:.1f}%\n({pct:+.1f}%)"
        brightness = data[i, j] / vmax if vmax > 0 else 0
        color = "white" if brightness > 0.55 else "black"
        ax.text(j, i, txt, ha="center", va="center", fontsize=9, color=color)

plt.colorbar(im, ax=ax, label="% above per-instance best (lower = better)", shrink=0.8)
plt.tight_layout()

out = os.path.join(os.path.dirname(__file__), "heatmap_improver_guidance.png")
plt.savefig(out, dpi=150)
print(f"Saved → {out}")
plt.show()
