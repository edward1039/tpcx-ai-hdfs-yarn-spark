"""Scalability figures and tables from results/summary.csv (run parse_results.py first).

Outputs in results/:
  aggregate.csv                 mean / std / n per configuration
  scaling_fit.csv               time = fixed + per-row cost, fitted over SFs (experiment A)
  speedup.csv                   speedup and efficiency vs executor cores (experiment B)
  figures/A_time_vs_rows.png    training and serving time vs measured input rows
  figures/A_cost_per_mrow.png   seconds per million input rows vs SF
  figures/A_resources.png       CPU busy and peak swap vs SF
  figures/B_speedup.png         speedup vs executor cores
  figures/C_streams.png         time per serving stream vs number of streams

Usage: python analysis/plot.py [results_dir]
Needs pandas and matplotlib (both are in the kit's lib/python-venv).
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

UC = {"uc3": ("UC3", "#2a78d6"), "uc7": ("UC7", "#eb6834")}
INK, MUTED, GRID = "#1c2230", "#52514e", "#e6e5e0"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#bdbcb6", "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED})


def style(ax, title, xlabel, ylabel):
    ax.set_title(title, loc="left", fontsize=10, fontweight="bold", color=INK)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def rating_col(df):
    cols = [c for c in df.columns if c.startswith("rows_") and "rating" in c]
    return cols[0] if cols else None


def aggregate(ok, keys):
    num = ok.select_dtypes("number").drop(columns=[c for c in keys + ["rep"] if c in ok.columns], errors="ignore")
    g = ok.groupby(keys)[list(num.columns)]
    agg = g.mean().add_suffix("_mean").join(g.std().add_suffix("_std")).join(g.size().rename("n"))
    return agg.reset_index()


def experiment_a(ok, figdir, results):
    a = ok[ok.experiment == "A"]
    if a.empty:
        return
    agg = aggregate(a, ["sf"]).sort_values("sf")
    x = agg["rows_lineitem_mean"] / 1e6 if "rows_lineitem_mean" in agg else agg["sf"]
    xlabel = "LINEITEM training rows (millions)" if "rows_lineitem_mean" in agg else "scale factor"

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9), dpi=200)
    for ax, phase, title in ((axes[0], "train", "Training time"), (axes[1], "serve", "Serving time")):
        for uc, (label, color) in UC.items():
            col = "%s_%s_s" % (uc, phase)
            if col + "_mean" not in agg:
                continue
            ax.errorbar(x, agg[col + "_mean"], yerr=agg[col + "_std"].fillna(0), color=color, lw=2,
                        marker="o", ms=5, capsize=3, label=label)
        top = "uc3_%s_s_mean" % phase
        if phase == "train" and top in agg:
            for xi, yi, sf in zip(x, agg[top], agg["sf"]):
                ax.annotate("SF%d" % sf, (xi, yi), textcoords="offset points", xytext=(0, 8),
                            ha="center", fontsize=7, color=MUTED)
        style(ax, title + " (s)", xlabel, "seconds")
        ax.set_ylim(bottom=0)
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(figdir, "A_time_vs_rows.png"))
    plt.close(fig)

    # seconds per million input rows: falls if fixed costs are amortized, rises if a resource saturates
    rcol = rating_col(a)
    fig, ax = plt.subplots(figsize=(3.6, 2.8), dpi=200)
    pairs = [("uc3", "rows_lineitem")] + ([("uc7", rcol)] if rcol else [])
    for uc, rows in pairs:
        if rows + "_mean" not in agg or "%s_train_s_mean" % uc not in agg:
            continue
        cost = agg["%s_train_s_mean" % uc] / (agg[rows + "_mean"] / 1e6)
        ax.plot(agg["sf"], cost, marker="o", lw=2, color=UC[uc][1], label=UC[uc][0])
    style(ax, "Training cost per million rows", "scale factor", "s / million rows")
    ax.set_xticks(agg["sf"])
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(figdir, "A_cost_per_mrow.png"))
    plt.close(fig)

    if "cpu_busy_mean_pct_mean" in agg:
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6), dpi=200)
        axes[0].bar(agg["sf"].astype(str), agg["cpu_busy_mean_pct_mean"], color="#1baf7a", width=0.6)
        style(axes[0], "Mean CPU busy (%)", "scale factor", "% of all cores")
        axes[1].bar(agg["sf"].astype(str), agg["swap_used_max_mb_mean"], color="#6250d6", width=0.6)
        style(axes[1], "Peak swap used (MB)", "scale factor", "MB")
        fig.tight_layout()
        fig.savefig(os.path.join(figdir, "A_resources.png"))
        plt.close(fig)

    # linear fit: time = fixed + per_row * rows
    fits = []
    for uc, rows in pairs:
        tcol = "%s_train_s" % uc
        if rows not in a or tcol not in a:
            continue
        sub = a.dropna(subset=[tcol, rows])
        if sub[rows].nunique() < 2:
            continue
        xs, ys = sub[rows].values / 1e6, sub["%s_train_s" % uc].values
        slope, intercept = np.polyfit(xs, ys, 1)
        pred = slope * xs + intercept
        r2 = 1 - ((ys - pred) ** 2).sum() / max(((ys - ys.mean()) ** 2).sum(), 1e-12)
        fits.append({"use_case": UC[uc][0], "phase": "training", "rows_column": rows,
                     "fixed_cost_s": round(intercept, 2), "s_per_million_rows": round(slope, 3),
                     "r2": round(r2, 4), "runs": len(sub)})
    if fits:
        pd.DataFrame(fits).to_csv(os.path.join(results, "scaling_fit.csv"), index=False)


def experiment_b(ok, figdir, results):
    b = ok[ok.experiment == "B"]
    if b.empty:
        return
    agg = aggregate(b, ["cores"]).sort_values("cores")
    base = agg[agg.cores == agg.cores.min()].iloc[0]
    fig, ax = plt.subplots(figsize=(3.8, 3.0), dpi=200)
    ax.plot(agg["cores"], agg["cores"] / base["cores"], ls="--", color=MUTED, lw=1, label="ideal")
    rows = []
    for uc, (label, color) in UC.items():
        col = "%s_train_s_mean" % uc
        if col not in agg:
            continue
        sp = base[col] / agg[col]
        ax.plot(agg["cores"], sp, marker="o", lw=2, color=color, label=label + " training")
        for c, s in zip(agg["cores"], sp):
            rows.append({"use_case": label, "cores": c, "train_s": round(agg.loc[agg.cores == c, col].iloc[0], 2),
                         "speedup": round(s, 3), "efficiency": round(s / (c / base["cores"]), 3)})
    style(ax, "Speedup vs executor cores (SF3)", "executor cores", "speedup")
    ax.set_xticks(agg["cores"])
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(figdir, "B_speedup.png"))
    plt.close(fig)
    pd.DataFrame(rows).to_csv(os.path.join(results, "speedup.csv"), index=False)


def experiment_c(ok, figdir):
    c = ok[ok.experiment == "C"]
    if c.empty or "stream_mean_s" not in c:
        return
    agg = aggregate(c, ["streams"]).sort_values("streams")
    fig, ax = plt.subplots(figsize=(3.6, 2.8), dpi=200)
    ax.errorbar(agg["streams"], agg["stream_mean_s_mean"], yerr=agg["stream_mean_s_std"].fillna(0),
                marker="o", lw=2, capsize=3, color="#6250d6")
    style(ax, "Time per serving stream (SF3)", "concurrent streams", "seconds")
    ax.set_xticks(agg["streams"])
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(os.path.join(figdir, "C_streams.png"))
    plt.close(fig)


def main():
    results = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "results")
    df = pd.read_csv(os.path.join(results, "summary.csv"))
    figdir = os.path.join(results, "figures")
    os.makedirs(figdir, exist_ok=True)

    failed = df[(df.get("exit_code", 0) != 0) | (df.get("done", 1) != 1)]
    if not failed.empty:
        print("runs excluded (failed or unfinished):", ", ".join(failed.experiment + "/" + failed.run))
    ok = df.drop(failed.index)

    parts = []
    for exp, keys in (("A", ["sf"]), ("B", ["cores"]), ("C", ["streams"])):
        sub = ok[ok.experiment == exp]
        if not sub.empty:
            agg = aggregate(sub, keys)
            agg.insert(0, "experiment", exp)
            parts.append(agg)
    if parts:
        pd.concat(parts, sort=False).to_csv(os.path.join(results, "aggregate.csv"), index=False)

    experiment_a(ok, figdir, results)
    experiment_b(ok, figdir, results)
    experiment_c(ok, figdir)
    print("figures in", figdir)


if __name__ == "__main__":
    main()
