# -*- coding: utf-8 -*-
"""Exhibits 9-10 — the two follow-up validations.

9. OIS-vs-MSB 6M gap time series: the structural richness of MSB and the
   mark-lag jumps around hawkish events.
10. Backtest timeline 2013-2026: meeting-level net implied probability
    (hike minus cut) from the MSB strip and OIS vs BMSI, with outcomes.
"""
from __future__ import annotations

import csv
from datetime import date, datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from common import FIGS, OUT

NAVY, GOLD, TEAL = "#16487E", "#8F7332", "#00838F"
NAVY9, GRID, AXIS, MUT = "#0E2A47", "#D6D6D6", "#0E2A47", "#6E6E6E"
RED = "#A52A2A"

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

D = lambda s: datetime.strptime(s, "%Y-%m-%d").date()


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


# ------------------------------------------------------------- EX9: gap
gap = read_csv(OUT / "m6_gap_daily.csv")
xs = [D(r["date"]) for r in gap if r["gap_6m_bp"]]
g6 = [float(r["gap_6m_bp"]) for r in gap if r["gap_6m_bp"]]
med = float(np.median(g6))

fig, ax = plt.subplots(figsize=(7.6, 3.1))
ax.plot(xs, g6, color=NAVY, lw=1.4)
ax.axhline(med, color=GOLD, lw=1.6, ls=(0, (6, 3)))
ax.axhline(0, color=AXIS, lw=1.0)
ax.annotate(f"골드 점선 = 전 표본 중위값 +{med:.1f}bp (통안의 구조적 강세)",
            xy=(D("2023-06-01"), -6), fontsize=9, color=GOLD,
            fontweight="bold", ha="center")
ax.annotate("2022 가을 자금경색", xy=(D("2022-10-20"), 84), xytext=(28, -2),
            textcoords="offset points", fontsize=8.5, color=MUT,
            arrowprops=dict(arrowstyle="-", color=MUT, lw=0.8))
for ds in ("2026-05-28", "2026-07-16"):
    ax.axvline(D(ds), color=GRID, lw=0.9)
ax.annotate("2026 매파 재가격\n(5/28·7/16)", xy=(D("2026-06-20"), 24),
            xytext=(-115, 26), textcoords="offset points", fontsize=8.5,
            color=NAVY9, arrowprops=dict(arrowstyle="-", color=MUT, lw=0.8))
lo, hi = min(g6) - 3, max(g6) + 3
ax.set_ylim(lo, hi)
ax.set_ylabel("OIS 6개월 - 통안 6개월 (bp)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
despine(ax)
save(fig, "ex_gap.svg")

# --------------------------------------------------------- EX10: backtest
bt = read_csv(OUT / "m5_backtest_meetings.csv")
rows = [r for r in bt if r["meeting"] >= "2013-02-01"]


def net(r, src):
    h, c = r.get(f"{src}_hike"), r.get(f"{src}_cut")
    if h in ("", None) or c in ("", None):
        return None
    return float(h) - float(c)


fig, ax = plt.subplots(figsize=(8.6, 3.4))
mx = [D(r["meeting"]) for r in rows if net(r, "msb") is not None]
my = [net(r, "msb") for r in rows if net(r, "msb") is not None]
ax.plot(mx, my, color=NAVY, lw=1.0, alpha=0.5, zorder=2)
ax.scatter(mx, my, s=22, color=NAVY, zorder=3, label="통안 스트립 내재(전일)")
bx = [D(r["meeting"]) for r in rows if net(r, "bmsi") is not None]
by = [net(r, "bmsi") for r in rows if net(r, "bmsi") is not None]
ax.scatter(bx, by, s=26, marker="D", color=GOLD, zorder=4, alpha=0.85,
           label="BMSI 서베이")
ox = [D(r["meeting"]) for r in rows
      if r["meeting"] >= "2024-10-01" and net(r, "ois") is not None]
oy = [net(r, "ois") for r in rows
      if r["meeting"] >= "2024-10-01" and net(r, "ois") is not None]
ax.scatter(ox, oy, s=30, marker="s", facecolors="none", edgecolors=TEAL,
           linewidths=1.6, zorder=5, label="KOFR OIS(2024.10~)")
for r in rows:
    d_ = D(r["meeting"])
    if r["outcome"] == "hike":
        ax.annotate("▲", (d_, 1.13), ha="center", fontsize=7, color=NAVY9,
                    annotation_clip=False)
    elif r["outcome"] == "cut":
        ax.annotate("▼", (d_, -1.22), ha="center", fontsize=7, color=RED,
                    annotation_clip=False)
ax.axhline(0, color=AXIS, lw=1.0)
ax.set_ylim(-1.32, 1.32)
ax.set_yticks([-1, -0.5, 0, 0.5, 1])
ax.set_ylabel("내재 순확률 (인상 - 인하)")
ax.annotate("상단 ▲ = 실제 인상, 하단 ▼ = 실제 인하", xy=(0.99, 1.06),
            xycoords="axes fraction", ha="right", fontsize=8.5, color=MUT)
# 2024-11-28 주석은 하드코드 대신 데이터에서 직접 읽는다 (v8 교정)
_r1128 = next(r for r in rows if r["meeting"] == "2024-11-28")
_m_net = net(_r1128, "msb")
_b_net = net(_r1128, "bmsi")
ax.annotate(f"'깜짝 인하' 2024-11:\n시장 {_m_net:+.2f} vs 서베이 {_b_net:+.2f}",
            xy=(D("2024-11-28"), _m_net), xytext=(-300, -6),
            textcoords="offset points", fontsize=8.5, color=NAVY9,
            arrowprops=dict(arrowstyle="-", color=MUT, lw=0.8,
                            shrinkB=4))
ax.xaxis.set_major_locator(mdates.YearLocator(2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
leg = ax.legend(loc="upper left", frameon=True, fontsize=8.5, ncols=1,
                framealpha=0.92)
leg.get_frame().set_edgecolor("none")
despine(ax)
save(fig, "ex_backtest.svg")

print("validation figures done")
