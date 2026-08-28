# -*- coding: utf-8 -*-
"""Appendix worked-example table + EX11 (shock validation scatter)."""
from __future__ import annotations

import csv
import json
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import FIGS, OUT, tenor_days, load_ois
from m1_step_function import Fitter, model_rate

NAVY, GOLD, TEAL = "#16487E", "#8F7332", "#00838F"
NAVY9, GRID, AXIS, MUT = "#0E2A47", "#D6D6D6", "#0E2A47", "#6E6E6E"
RED = "#A52A2A"

plt.rcParams.update({
    "svg.fonttype": "none",
    "font.family": "sans-serif",
    "font.sans-serif": ["Malgun Gothic", "Inter", "Segoe UI", "sans-serif"],
    "axes.unicode_minus": False, "font.size": 10.5,
    "axes.edgecolor": AXIS, "axes.linewidth": 1.2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
    "axes.axisbelow": True,
    "xtick.color": MUT, "ytick.color": MUT, "axes.labelcolor": MUT,
    "figure.facecolor": "white", "axes.facecolor": "white",
})

# ---------------- appendix worked example: hold-path column for the 8/7 fit
ois = load_ois()
ft = Fitter()
latest = max(ois)
res = ft.fit(latest, ois[latest])
print("워크스루 표 (", latest, " r0=", res["r0"], ")")
print("만기 | 시장호가 | 동결경로값 | 초과분bp | 모형적합 | 잔차bp")
for t, ym, yf in zip(res["tenors"], res["y"], res["fitted"]):
    d_ = tenor_days(latest, t)
    hold = model_rate(latest, d_, res["r0"], res["nodes"],
                      np.zeros(len(res["nodes"])))
    print(f"{t} | {ym:.4f} | {hold:.4f} | {(ym-hold)*100:+.1f} | "
          f"{yf:.4f} | {(ym-yf)*100:+.1f}")

# ---------------- EX11: shock validation scatter, colored by regime
from datetime import date

rows = list(csv.DictReader(open(OUT / "m7_validation_meetings.csv",
                                encoding="utf-8-sig")))
REGIMES = [
    ("완화·동결 20.1~21.7", date(2020, 1, 1), date(2021, 7, 31), MUT, "o"),
    ("급속 인상 21.8~23.1", date(2021, 8, 1), date(2023, 1, 31), GOLD, "^"),
    ("동결 23.2~24.9", date(2023, 2, 1), date(2024, 9, 30), TEAL, "s"),
    ("인하 24.10~", date(2024, 10, 1), date(2026, 12, 31), NAVY, "o"),
]


def regime_style(dstr):
    d_ = date.fromisoformat(dstr)
    for name, a, b, color, marker in REGIMES:
        if a <= d_ <= b:
            return name, color, marker
    return None, MUT, "o"


fig, (axA, axB, axC) = plt.subplots(1, 3, figsize=(11.8, 3.4))
for ax, key, name in [(axA, "msb91", "통안 3개월"), (axB, "ktb3", "국고 3년"),
                      (axC, "ktb10", "국고 10년")]:
    lim = 28
    ax.plot([-lim, lim], [-lim, lim], color=GRID, lw=1.2)
    ax.axhline(0, color=AXIS, lw=0.9)
    ax.axvline(0, color=AXIS, lw=0.9)
    for reg_name, a, b, color, marker in REGIMES:
        p, q = [], []
        for r in rows:
            if not (r.get(f"pred_{key}") and r.get(f"real_{key}")):
                continue
            d_ = date.fromisoformat(r["meeting"])
            if a <= d_ <= b:
                p.append(float(r[f"pred_{key}"]))
                q.append(float(r[f"real_{key}"]))
        ax.scatter(p, q, s=34, color=color, marker=marker, alpha=0.85,
                   zorder=3, label=reg_name if ax is axA else None)
    epi = next(r for r in rows if r["meeting"] == "2025-01-16")
    ax.scatter([float(epi[f"pred_{key}"])], [float(epi[f"real_{key}"])],
               s=70, facecolors="none", edgecolors=RED, linewidths=1.8,
               zorder=5)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("예측 변동 = β × 서프라이즈 (bp)")
    ax.set_title(name, fontsize=10.5, color=NAVY9, loc="left")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
axA.set_ylabel("실제 당일 변동 (bp)")
axA.annotate("45도 선 = 완벽한 예측", xy=(9, 15.5), fontsize=8.5, color=MUT,
             rotation=38)
axA.annotate("국면별 상관: 완화 +0.71 · 급속 인상 +0.82\n동결 +0.17 · 인하 +0.35",
             xy=(0.03, 0.02), xycoords="axes fraction", fontsize=8, color=NAVY9)
axB.annotate("국면별 상관: 완화 +0.52 · 급속 인상 −0.48\n동결 +0.15 · 인하 +0.41",
             xy=(0.03, 0.02), xycoords="axes fraction", fontsize=8, color=NAVY9)
axC.annotate("국면별 상관: 완화 +0.32 · 급속 인상 −0.41\n동결 +0.06 · 인하 +0.29",
             xy=(0.03, 0.02), xycoords="axes fraction", fontsize=8, color=NAVY9)
axB.annotate("빨간 테두리 = 2025-01-16\n깜짝 동결(회견발 반전)",
             xy=(float(epi["pred_ktb3"]), float(epi["real_ktb3"])),
             xytext=(-30, -52), textcoords="offset points", fontsize=8,
             color=RED, arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))
leg = axA.legend(loc="upper left", frameon=True, fontsize=7.8, framealpha=0.92)
leg.get_frame().set_edgecolor("none")
fig.tight_layout(w_pad=2.4)
fig.savefig(FIGS / "ex_shock_validation.svg", bbox_inches="tight",
            pad_inches=0.15)
print("saved ex_shock_validation.svg")
