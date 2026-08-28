# -*- coding: utf-8 -*-
"""학습 노트의 보강 그림 2장 — 실측 데이터 기반 (노트북 계약과 무관).

01-kofr-base-history.png     KOFR·기준금리·1주 OIS 실측 (r0 캘리브레이션 동기)
12-cumulative-vs-allocation.png  연말 내재(안정) vs 8월 배분(진동) 시계열

입력: ../../rawdata (common.py 로더), ../output/m1_timeseries.csv
"""
from __future__ import annotations

import csv
import sys
from datetime import date, datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from common import OUT, base_rate_history, base_rate_on, kofr_daily, load_ois

INK, MUTE, GRID = "#0A0A0A", "#6E6E6E", "#D6D6D6"
CADRED, CADBLUE, ORANGE = "#C53030", "#2D7EAA", "#ED8936"

plt.rcParams.update({
    "font.family": ["Malgun Gothic", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.dpi": 128, "savefig.dpi": 128, "savefig.bbox": "tight",
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": INK, "axes.linewidth": 0.8,
    "axes.titlesize": 10.5, "axes.titlepad": 6,
    "axes.labelsize": 9, "axes.labelcolor": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
    "xtick.color": INK, "ytick.color": INK,
    "legend.fontsize": 8, "legend.frameon": False,
    "lines.linewidth": 1.4,
})

FIGDIR = HERE / "figs"
FIGDIR.mkdir(exist_ok=True)

START, END = date(2026, 2, 1), date(2026, 8, 7)

# ── 01 — KOFR · 기준금리 · 1주 OIS (§1.1/§2.2에 임베드) ──────────────
kofr = kofr_daily()
hist = base_rate_history()
ois = load_ois()

ds = sorted(d for d in kofr if START <= d <= END)
base_line = [base_rate_on(d, hist) for d in ds]
ois_ds = sorted(d for d in ois if START <= d <= END and "1주" in ois[d])

fig, ax = plt.subplots(figsize=(7.6, 3.2))
ax.step(ds, base_line, where="post", color=INK, lw=1.8, label="기준금리")
ax.plot(ds, [kofr[d] for d in ds], color=CADBLUE, lw=1.1, label="KOFR (익일물 실거래)")
ax.plot(ois_ds, [ois[d]["1주"] for d in ois_ds], color=ORANGE, lw=1.1,
        label="KOFR OIS 1주 호가")
mpc_days = [date(2026, 2, 26), date(2026, 4, 10), date(2026, 5, 28),
            date(2026, 7, 16)]
for i, m in enumerate(mpc_days):
    ax.axvline(m, color=GRID, lw=0.8)
    ax.annotate("금통위", xy=(m, 2.845), ha="center", fontsize=7, color=MUTE)
ax.annotate("7/16 인상 직전 — 1주 호가(주황)만\n회의 결과를 미리 가격에 반영한다",
            xy=(date(2026, 7, 8), 2.62), fontsize=8, color="#B05A10",
            ha="right")
ax.set_ylim(2.30, 2.88)
ax.set_ylabel("금리 (%)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m월"))
ax.legend(loc="lower right", ncols=1)
ax.set_title("하루짜리 금리의 세 얼굴 — 기준금리·KOFR·1주 OIS (2026)")
fig.tight_layout()
fig.savefig(FIGDIR / "01-kofr-base-history.png")
plt.close(fig)
print("saved 01-kofr-base-history.png")

# ── 12 — 연말 내재(안정) vs 8월 배분(진동) (§4.4에 임베드) ──────────
rows = []
with open(OUT / "m1_timeseries.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        if date(2026, 5, 1) <= d <= END and r.get("prob_0827") and r.get("implied_ye_rate"):
            rows.append((d, float(r["implied_ye_rate"]),
                         float(r["prob_0827"]) * 100))

ds2 = [r[0] for r in rows]
fig, (axT, axB) = plt.subplots(2, 1, figsize=(7.6, 4.4), sharex=True,
                               height_ratios=[1, 1])
axT.plot(ds2, [r[1] for r in rows], color=INK, lw=1.5)
axT.set_ylabel("연말 내재 기준금리 (%)")
axT.set_ylim(2.95, 3.52)
axT.set_title("같은 모형, 같은 기간 — 누적(위)은 추세, 배분(아래)은 진동")
axB.plot(ds2, [r[2] for r in rows], color=CADBLUE, lw=1.5)
axB.set_ylabel("8/27 인상확률 (%)")
axB.set_ylim(0, 100)
hi = max(rows, key=lambda r: r[2])
lo = min((r for r in rows if r[0] > hi[0]), key=lambda r: r[2], default=None)
axB.annotate(f"{hi[0].strftime('%m/%d')} {hi[2]:.0f}%", xy=(hi[0], hi[2]),
             xytext=(8, -14), textcoords="offset points", fontsize=8,
             color=CADRED)
if lo:
    axB.annotate(f"{lo[0].strftime('%m/%d')} {lo[2]:.0f}%", xy=(lo[0], lo[2]),
                 xytext=(6, -12), textcoords="offset points", fontsize=8,
                 color=CADRED)
    ye_lo = next(r[1] for r in rows if r[0] == lo[0])
    axT.scatter([lo[0]], [ye_lo], s=40, facecolors="none",
                edgecolors=CADRED, linewidths=1.4, zorder=5)
    axT.annotate(f"{lo[0].strftime('%m/%d')} — 배분이 26%로 무너진 날,\n"
                 f"누적은 오히려 기간 최고점({ye_lo:.2f}%)",
                 xy=(lo[0], ye_lo), xytext=(12, -30),
                 textcoords="offset points", fontsize=8, color=CADRED)
for ax_ in (axT, axB):
    ax_.axvline(date(2026, 7, 16), color=GRID, lw=0.8)
axB.annotate("7/16 금통위", xy=(date(2026, 7, 16), 6), fontsize=7,
             color=MUTE, ha="center")
axB.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
fig.tight_layout()
fig.savefig(FIGDIR / "12-cumulative-vs-allocation.png")
plt.close(fig)
print("saved 12-cumulative-vs-allocation.png")
print("rows:", len(rows), "max prob:", hi, "min after:", lo)
