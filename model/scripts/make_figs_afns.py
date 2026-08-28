# -*- coding: utf-8 -*-
"""EX12 — AFNS 재현·비교 (HTML 리포트용, JPM 팔레트)."""
from __future__ import annotations

import csv
from datetime import date, datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import FIGS, OUT

NAVY, GOLD, TEAL = "#16487E", "#8F7332", "#00838F"
NAVY9, GRID, AXIS, MUT = "#0E2A47", "#D6D6D6", "#0E2A47", "#6E6E6E"

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

D = lambda s: datetime.strptime(s, "%Y-%m-%d").date()


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def despine(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


m10p = read_csv(OUT / "m10_afns_expected_path.csv")
m3p = read_csv(OUT / "m3_expected_path.csv")
m10d = read_csv(OUT / "m10_afns_decomposition.csv")
m3d = read_csv(OUT / "m3_decomposition.csv")
snap = read_csv(OUT / "m1_snapshot.csv")

fig, (axA, axB) = plt.subplots(1, 2, figsize=(8.6, 3.3))

# 앞 10개월만 — 그 너머는 모형의 평균회귀 사전믿음이 지배해 오독을 부른다(v15)
H = 10
hs = np.arange(1, H + 1)
afns_p = [float(r["expected_base_rate"]) for r in m10p][:H]
dns_p = [float(r["expected_base_rate"]) for r in m3p][:H]
ois_x = [0] + [(D(r["meeting"]) - date(2026, 8, 7)).days / 30.4 for r in snap]
ois_y = [2.75] + [float(r["implied_rate_after"]) for r in snap]
axA.step(ois_x, ois_y, where="post", color=MUT, lw=1.6,
         label="OIS 내재(프리미엄 포함)")
axA.plot(hs, afns_p, color=NAVY, lw=2.4, label="AFNS 기대(한은 방법론 재현)")
axA.plot(hs, dns_p, color=GOLD, lw=2.0, ls=(0, (5, 2)),
         label="DNS-VAR 기대(2단계 근사)")
axA.axhline(2.75, color=GRID, lw=1.0)
axA.annotate("기준금리 2.75%", xy=(2.6, 2.75), xytext=(0, 5),
             textcoords="offset points", fontsize=8.5, color=MUT, ha="center")
axA.annotate(f"연말: OIS {ois_y[3]:.2f} / AFNS {afns_p[3]:.2f} / "
             f"DNS {dns_p[3]:.2f}%", xy=(0.03, 0.92),
             xycoords="axes fraction", fontsize=9, color=NAVY9)
axA.set_xlim(0, H + 0.2)
axA.set_xlabel("개월 후")
axA.set_ylabel("기대 기준금리 (%)")
axA.legend(loc="upper left", bbox_to_anchor=(0.0, 0.88), frameon=False,
           fontsize=8.5)
axA.set_title("(a) 기대 기준금리 경로 — 세 모형, 앞 10개월", fontsize=10,
              color=NAVY9, loc="left")
axA.text(0.98, 0.04, "10개월 너머는 평균회귀 성질이 지배 — 본문 참조",
         transform=axA.transAxes, ha="right", fontsize=7.5, color=MUT)
despine(axA)

t10 = [int(r["tenor_months"]) for r in m10d]
tp10 = [float(r["tp_obs_bp"]) for r in m10d]
t3 = [int(r["tenor_months"]) for r in m3d
      if r["term_premium_bp"] not in ("", None)]
tp3 = [float(r["term_premium_bp"]) for r in m3d
       if r["term_premium_bp"] not in ("", None)]
axB.axhline(0, color=AXIS, lw=1.0)
axB.plot(t10, tp10, color=NAVY, lw=2.2, marker="o", ms=5, label="AFNS")
axB.plot(t3, tp3, ls="none", marker="D", ms=6, mfc="none", mec=GOLD,
         mew=1.6, label="DNS-VAR")
axB.set_xscale("log")
axB.set_xticks([3, 6, 12, 24, 36, 60, 120],
               ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "10Y"])
axB.minorticks_off()
axB.grid(axis="x", visible=False)
axB.set_xlabel("만기")
axB.set_ylabel("기간프리미엄 (bp)")
axB.legend(loc="upper left", frameon=False, fontsize=9)
axB.set_title("(b) 만기별 기간프리미엄", fontsize=10, color=NAVY9, loc="left")
axB.annotate("3M 음수는 시작점 웨지·적합 잔차\n(경제적 프리미엄 아님 — 0 부근으로 읽기)",
             xy=(3, tp10[0]), xytext=(4.6, 48), fontsize=8, color=MUT,
             arrowprops=dict(arrowstyle="-", color=MUT, lw=0.8))
despine(axB)

fig.tight_layout(w_pad=2.4)
fig.savefig(FIGS / "ex_afns.svg", bbox_inches="tight", pad_inches=0.15)
fig.savefig(FIGS / "ex_afns.png", dpi=200, bbox_inches="tight",
            pad_inches=0.15)
print("saved ex_afns.svg/.png")
