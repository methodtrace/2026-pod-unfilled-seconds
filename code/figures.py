"""The paper's four figures, drawn from a full-tier output folder (its extracts) and the rules analysis.

Usage: python3 figures.py --res DIR --rules DIR --out DIR
  --res    full-tier output folder (reads extracts/x1_structural, xd_m7, x5_frontier_m7)
  --rules  output folder of analysis_rules.py (reads menu_law.csv)
  --out    where to write fig1..fig4 as PDF (vector, for the manuscript) and PNG (for review)

Needs matplotlib (the only non-standard-library dependency in code/, used for figures only). PDFs carry no
creation date, so reruns give identical files for the same matplotlib version.

Figure 1  structural seconds per break against maxseq for four study menus on grid, hybrid and irregular breaks,
          with the part no pod can reach (rule 1) shaded.
Figure 2  the uncapped floor against the menu's gcd for all 86 menus on irregular breaks, with (g - 1)/2.
Figure 3  unfilled seconds split into structural, demand and readiness parts across demand depth.
Figure 4  the clutter frontier: unsold seconds against ads per break as the per-ad clutter cost rises.
"""
import argparse
import csv
import gzip
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# reference categorical palette, fixed order (validated: adjacent CVD dE >= 9.1 on the light surface); the two
# lighter hues sit below 3:1 contrast, so every series also has its own marker, dash pattern and direct label
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
MARKERS = ["o", "s", "^", "D"]
DASHES = ["-", "--", "-.", ":"]
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e2dc"
NEUTRAL = "#b9b7ae"
STUDY = ["15 30", "15 30 60", "10 15 30", "6 15 30"]

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["STIXGeneral", "DejaVu Serif"], "mathtext.fontset": "stix",
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "legend.fontsize": 7, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.linewidth": 0.6, "lines.linewidth": 1.4, "lines.markersize": 3.5, "pdf.fonttype": 42,
    "savefig.dpi": 300, "axes.spines.top": False, "axes.spines.right": False,
})


def rd(path):
    with gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def braces(m):
    return "{%s}" % ", ".join(m.split())


def style(ax):
    ax.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)


def save(fig, out, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, "%s.%s" % (name, ext)), bbox_inches="tight",
                    metadata={"CreationDate": None} if ext == "pdf" else {"Software": None})
    plt.close(fig)


def fig1(res, rules, out):
    """Structural floor against maxseq, three break laws, four menus; the rule-1 shortfall is shaded as one band
    per panel, for {15, 30}, the menu with the shortest longest part, to keep the panel readable."""
    S = {}
    for r in rd(os.path.join(res, "extracts", "x1_structural.csv.gz")):
        S[(r["law"], r["conv"], r["menu"], r["h"])] = float(r["Ustruct"])
    feas = {}
    for r in rd(os.path.join(rules, "menu_law.csv")):
        for h in range(1, 21):
            feas[(r["law"], r["conv"], r["menu"], str(h))] = float(r["feas_%d" % h])
    panels = [("L1", "a", "Scheduled grid breaks"), ("L2", "a", "Hybrid remainders"),
              ("L3u", "a", "Irregular live breaks")]
    hs = list(range(3, 16))
    fig, axes = plt.subplots(1, 3, figsize=(7.16, 2.35), sharey=True)
    for ax, (law, conv, title) in zip(axes, panels):
        style(ax)
        f = [feas[(law, conv, "15 30", str(h))] for h in hs]
        ax.fill_between(hs, 0, f, color=NEUTRAL, alpha=0.45, linewidth=0, label="no pod reaches it ({15, 30})")
        for i, m in enumerate(STUDY):
            y = [S[(law, conv, m, str(h))] for h in hs]
            yu = S[(law, conv, m, "none")]
            ax.plot(hs, y, color=SERIES[i], marker=MARKERS[i], linestyle=DASHES[i], label=braces(m))
            ax.plot([hs[-1] + 1.4], [yu], color=SERIES[i], marker=MARKERS[i], linestyle="none")
        ax.set_title(title, color=INK, loc="left")
        ax.set_xticks([3, 6, 9, 12, 15, hs[-1] + 1.4])
        ax.set_xticklabels(["3", "6", "9", "12", "15", "none"])
        ax.set_xlabel("maxseq h")
        ax.set_ylim(0, 70)
    axes[0].set_ylabel("structural seconds per break")
    h_, l_ = axes[0].get_legend_handles_labels()
    fig.legend(h_[1:] + h_[:1], l_[1:] + l_[:1], loc="lower center", ncol=5, frameon=False,
               bbox_to_anchor=(0.5, -0.08))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, out, "fig1-cap-regime")


def fig2(rules, out):
    rows = [r for r in rd(os.path.join(rules, "menu_law.csv")) if r["law"] in ("L3u", "L7")]
    fig, ax = plt.subplots(figsize=(3.5, 2.5))
    style(ax)
    gs = sorted({int(r["g"]) for r in rows})
    ax.plot([0, 31], [-0.5, 15], color=INK2, linewidth=0.9, linestyle="-", zorder=1)
    ax.text(26.5, 11.0, "(g - 1)/2", color=INK2, fontsize=7, ha="center")
    for i, (law, lab, lo) in enumerate((("L3u", "breaks 60 to 240 s", 60), ("L7", "breaks 240 to 360 s", 240))):
        rs = [r for r in rows if r["law"] == law]
        past = [r for r in rs if int(r["conductor"]) <= lo]
        before = [r for r in rs if int(r["conductor"]) > lo]
        dx = -0.35 if i == 0 else 0.35
        ax.plot([int(r["g"]) + dx for r in past], [float(r["S_unc"]) for r in past], marker=MARKERS[i],
                linestyle="none", color=SERIES[i], markersize=4, markeredgecolor="white", markeredgewidth=0.5,
                label="%s, past the conductor (%d)" % (lab, len(past)), zorder=3)
        if before:
            ax.plot([int(r["g"]) + dx for r in before], [float(r["S_unc"]) for r in before], marker=MARKERS[i],
                    linestyle="none", markerfacecolor="none", color=SERIES[i], markersize=4,
                    label="%s, breaks below the conductor (%d)" % (lab, len(before)), zorder=3)
    ax.set_xlabel("gcd g of the menu (seconds)")
    ax.set_ylabel("uncapped structural seconds per break")
    ax.set_xticks(gs)
    ax.set_xlim(0, 31)
    ax.set_ylim(-0.5, 16)
    ax.legend(loc="upper left", frameon=False, handletextpad=0.3)
    fig.tight_layout()
    save(fig, out, "fig2-lattice-floor")


def fig3(res, out):
    rows = rd(os.path.join(res, "extracts", "xd_m7.csv.gz"))
    pick = defaultdict(dict)
    for r in rows:
        if r["law"] == "L3u" and r["h"] == "6" and r["count_law"] == "poisson" and r["weights"] == "d1530":
            pick[r["menu"]][int(r["lam"])] = r
    rho = 0.95
    fig, axes = plt.subplots(1, 2, figsize=(7.16, 2.35), sharey=True)
    colors = [SERIES[0], SERIES[1], SERIES[3]]
    for ax, m in zip(axes, ("15 30", "10 15 30")):
        style(ax)
        lams = sorted(pick[m])
        st = [float(pick[m][l]["Ustruct"]) for l in lams]
        de = [float(pick[m][l]["demand_part"]) for l in lams]
        re_ = [(1 - rho) * (float(pick[m][l]["ET"]) - float(pick[m][l]["U"])) for l in lams]
        ys = [st, de, re_]
        labs = ["structural", "demand", r"readiness ($\rho$ = 0.95)"]
        hatch = [None, "////", "...."]
        base = [0.0] * len(lams)
        for i in range(3):
            top = [b + y for b, y in zip(base, ys[i])]
            ax.fill_between(lams, base, top, color=colors[i], alpha=0.85, linewidth=0.8, edgecolor="#fcfcfb",
                            hatch=hatch[i], label=labs[i])
            base = top
        ax.set_xscale("log", base=2)
        ax.set_xticks(lams)
        ax.set_xticklabels([str(l) for l in lams])
        ax.set_xlabel(r"expected creatives per break $\lambda$ (15/30-dominant mix)")
        ax.set_title("%s, maxseq 6, irregular live breaks" % braces(m), loc="left", color=INK)
        ax.annotate("structural %.2f s" % st[-1], (lams[-1], st[-1] / 2), xytext=(-5, 0), textcoords="offset points", ha="right", va="center", fontsize=7, color="white")
    axes[0].set_ylabel("unfilled seconds per break")
    h_, l_ = axes[0].get_legend_handles_labels()
    fig.legend(h_, l_, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.06))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, out, "fig3-decomposition")


def fig4(res, out):
    rows = rd(os.path.join(res, "extracts", "x5_frontier_m7.csv.gz"))
    sel = defaultdict(list)
    for r in rows:
        if r["law"] == "L3u" and r["lam"] == "64" and r["scheme"] == "balanced" and r["h"] == "none" \
                and r["anchor"] == "base":
            sel[" ".join(r["menu"].strip("{}").split(","))].append(r)
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    style(ax)
    for i, m in enumerate(STUDY):
        rs = sorted(sel[m], key=lambda r: float(r["c_dollars"]))
        x = [float(r["ads"]) for r in rs]
        y = [float(r["unfilled_s"]) for r in rs]
        ax.plot(x, y, color=SERIES[i], marker=MARKERS[i], linestyle=DASHES[i], label=braces(m))
        below = m == "6 15 30"   # its zero-cost end sits beside {10, 15, 30}'s; label it underneath
        ax.annotate(braces(m), (x[0], y[0]), textcoords="offset points", xytext=(-6 if below else 0, -7 if below else 6),
                    fontsize=6.5, color=INK2, ha="center", va="top" if below else "bottom")
    ax.set_ylim(bottom=-5)  # room for the label under the zero-cost end of {6, 15, 30}
    ax.set_xlabel("ads per break")
    ax.set_ylabel("unsold seconds per break")
    ax.legend(loc="upper right", frameon=False, title="per-ad cost \\$0 (right end) to \\$20 CPM (left end)",
              title_fontsize=6.5)
    fig.tight_layout()
    save(fig, out, "fig4-clutter-frontier")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    fig1(a.res, a.rules, a.out)
    fig2(a.rules, a.out)
    fig3(a.res, a.out)
    fig4(a.res, a.out)
    print("figures written to", a.out)


if __name__ == "__main__":
    main()
