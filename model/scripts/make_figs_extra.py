# -*- coding: utf-8 -*-
"""Three additional didactic exhibits (same palette/specs as make_figs.py).

A. Step-function concept diagram — how one 2M OIS quote encodes the August
   meeting probability (the report's key intuition, drawn instead of told).
B. Expectation vs term-premium decomposition by maturity (model 3 output).
C. Expected curve reaction to an August hike vs hold (model 4 scenarios).
"""
from __future__ import annotations

import csv
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from common import FIGS, OUT

NAVY, GOLD, TEAL = "#16487E", "#8F7332", "#00838F"
NAVY9, GRID, AXIS, MUT = "#0E2A47", "#D6D6D6", "#0E2A47", "#6E6E6E"

plt.rcParams.update({
    "svg.fonttype": "none",
    "font.family": "sans-serif",
    "font.sans-serif": ["Malgun Gothic", "Inter", "Segoe UI", "sans-serif"],
    "axes.unicode_minus": False,
    "font.size": 10.5,
    "axes.edgecolor": AXIS, "axes.linewidth": 1.2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
    "axes.axisbelow": True,
    "xtick.color": MUT, "ytick.color": MUT, "axes.labelcolor": MUT,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def despine(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save(fig, name):
    fig.savefig(FIGS / name, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("saved", name)


# ---------------------------------------------------------------- A. concept
fig, ax = plt.subplots(figsize=(7.6, 3.4))
d0, dm, d1 = date(2026, 8, 7), date(2026, 8, 27), date(2026, 10, 7)
r0, hike = 2.74, 2.99
quote = 2.84

ax.fill_between([d0, dm], r0, 2.60, color=NAVY, alpha=0.06, lw=0)
ax.fill_between([dm, d1], r0, 2.60, color=NAVY, alpha=0.06, lw=0)
ax.plot([d0, dm], [r0, r0], color=NAVY, lw=2.6, solid_capstyle="round")
ax.plot([dm, d1], [r0, r0], color=NAVY, lw=2.0, ls=(0, (3, 3)))
ax.plot([dm, d1], [hike, hike], color=NAVY, lw=2.6, solid_capstyle="round")
ax.plot([dm, dm], [r0, hike], color=NAVY, lw=1.2, ls=(0, (1, 2)))
ax.axhline(quote, color=GOLD, lw=2.0, ls=(0, (6, 3)))
ax.axvline(dm, color=GRID, lw=0.9)

ax.annotate("회의 전 20일: 2.74%", xy=(date(2026, 8, 16), r0),
            xytext=(0, -16), textcoords="offset points", ha="center",
            fontsize=9.5, color=NAVY9)
ax.annotate("인상 시: 2.99%", xy=(date(2026, 9, 16), hike),
            xytext=(0, 8), textcoords="offset points", ha="center",
            fontsize=9.5, color=NAVY9, fontweight="bold")
ax.annotate("동결 시: 2.74%", xy=(date(2026, 9, 16), r0),
            xytext=(0, -16), textcoords="offset points", ha="center",
            fontsize=9.5, color=MUT)
ax.annotate("시장이 실제로 매긴 2개월 OIS = 2.84%\n= 두 경로의 확률가중 평균",
            xy=(date(2026, 9, 3), quote), xytext=(0, 10),
            textcoords="offset points", ha="center", fontsize=9.5,
            color=GOLD, fontweight="bold")
ax.annotate("8/27 금통위", xy=(dm, 2.615), ha="center", fontsize=9, color=MUT)
ax.annotate("회의 뒤 41일 — 인상이 확실하면 2개월 고정금리가 16.9bp 높아야 한다.\n"
            "실제로는 9.4bp 높다 → 약 56% 반영 (호가 6개 결합 적합은 50%)",
            xy=(0.985, 0.05),
            xycoords="axes fraction", ha="right", fontsize=9, color=NAVY9)
ax.set_ylim(2.58, 3.10)
ax.set_ylabel("하루짜리 금리 경로 (%)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
ax.grid(axis="x", visible=False)
despine(ax)
save(fig, "ex_concept.svg")

# ---------------------------------------------------------- B. decomposition
dec = read_csv(OUT / "m3_decomposition.csv")
rows = [r for r in dec if r["term_premium_bp"] not in ("", None)]
labels = {3: "3개월", 6: "6개월", 9: "9개월", 12: "1년", 24: "2년", 36: "3년"}
tenors = [int(r["tenor_months"]) for r in rows]
ylds = [float(r["zero_yield"]) for r in rows]
exps = [float(r["avg_expected_short"]) for r in rows]
prem = [float(r["term_premium_bp"]) for r in rows]
xi = np.arange(len(rows))

fig, ax = plt.subplots(figsize=(7.6, 3.2))
for i, (y_, e_) in enumerate(zip(ylds, exps)):
    ax.plot([i, i], [e_, y_], color=GRID, lw=2.4, zorder=1)
ax.scatter(xi, ylds, s=58, color=NAVY, zorder=3, label="실제 금리(민평)")
ax.scatter(xi, exps, s=58, color=GOLD, zorder=3, marker="D",
           label="기대 단기금리 평균(DNS-VAR)")
for i, p_ in enumerate(prem):
    top = max(ylds[i], exps[i])
    ax.annotate(f"{p_:+.0f}bp", (i, top), textcoords="offset points",
                xytext=(0, 9), ha="center", fontsize=9,
                color=(NAVY9 if p_ >= 0 else "#A52A2A"))
ax.set_xticks(xi, [labels[t] for t in tenors])
ax.set_ylabel("금리 (%)")
ax.set_ylim(2.75, 4.05)
ax.legend(frameon=False, fontsize=9, loc="upper left")
ax.annotate("표시 수치 = 기간프리미엄(실제 금리 - 기대 평균)", xy=(0.99, 0.05),
            xycoords="axes fraction", ha="right", fontsize=8.5, color=MUT)
ax.grid(axis="x", visible=False)
despine(ax)
save(fig, "ex_decomposition.svg")

# ---------------------------------------------------------- C. curve reaction
sc = read_csv(OUT / "m4_scenarios.csv")
names = [r["maturity"].replace("통안 ", "통안").replace("국고 ", "국고")
         for r in sc]
hike_e = [float(r["hike_move_bp_empirical"]) for r in sc]
hold_e = [float(r["hold_move_bp_empirical"]) for r in sc]
xi = np.arange(len(sc))

fig, ax = plt.subplots(figsize=(7.6, 3.2))
ax.axhline(0, color=AXIS, lw=1.2)
ax.plot(xi, hike_e, color=NAVY, lw=2.4, marker="o", ms=6)
ax.plot(xi, hold_e, color=TEAL, lw=2.0, marker="s", ms=5, ls=(0, (5, 2)))
ax.annotate("인상 시 (서프라이즈 +12.4bp)", (xi[2], hike_e[2]),
            textcoords="offset points", xytext=(10, 10), fontsize=9.5,
            color=NAVY, fontweight="bold")
ax.annotate("동결 시 (서프라이즈 -12.6bp)", (xi[2], hold_e[2]),
            textcoords="offset points", xytext=(10, -16), fontsize=9.5,
            color=TEAL, fontweight="bold")
for i in (0, 4, 6):
    ax.annotate(f"{hike_e[i]:+.0f}", (xi[i], hike_e[i]),
                textcoords="offset points", xytext=(0, 8), ha="center",
                fontsize=8.5, color=NAVY9)
    ax.annotate(f"{hold_e[i]:+.0f}", (xi[i], hold_e[i]),
                textcoords="offset points", xytext=(0, -13), ha="center",
                fontsize=8.5, color=TEAL)
ax.fill_between(xi, hike_e, hold_e, color=NAVY, alpha=0.05, lw=0)
ax.set_xticks(xi, names, fontsize=9)
ax.set_ylabel("발표 당일 예상 금리 변화 (bp)")
ax.set_ylim(-17, 18)
ax.annotate("실증 베타 기준. P=50%이므로 두 시나리오의 폭이 거의 대칭이다.",
            xy=(0.99, 0.04), xycoords="axes fraction", ha="right",
            fontsize=8.5, color=MUT)
ax.grid(axis="x", visible=False)
despine(ax)
save(fig, "ex_scenario_curve.svg")

print("extra figures done")
