# -*- coding: utf-8 -*-
"""Generate the report exhibits as inline-able SVGs (JPM-tone, dataviz-validated).

Palette (validated 2026-08-07, node validate_palette.js, white surface):
navy #16487E / dark gold #8F7332 / teal #00838F — CVD dE 12.8, normal 16.1,
contrast all >=3:1. Chroma/lightness bands intentionally traded for the
institutional design system; identity never rides on hue alone (direct labels
+ dash patterns everywhere).
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from common import FIGS, OUT, RAW, base_rate_history

FIGS.mkdir(parents=True, exist_ok=True)

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
    "xtick.color": MUT, "ytick.color": MUT,
    "axes.labelcolor": MUT,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def despine(ax, keep=("left", "bottom")):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save(fig, name):
    fig.savefig(FIGS / name, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("saved", name)


D = lambda s: datetime.strptime(s, "%Y-%m-%d").date()

# ---------------------------------------------------------------- EX1
ts = read_csv(OUT / "m1_timeseries.csv")
ts26 = [r for r in ts if r["date"] >= "2026-01-01" and r.get("prob_next_hike")]
xs = [D(r["date"]) for r in ts26]
ph = [float(r["prob_next_hike"]) * 100 for r in ts26]
pc = [-float(r["prob_next_cut"]) * 100 for r in ts26]
nm = [r["next_meeting"] for r in ts26]

fig, ax = plt.subplots(figsize=(7.6, 3.4))
# break the line at meeting rollovers
seg_x, seg_y = [], []
for i, (x, y) in enumerate(zip(xs, ph)):
    if i and nm[i] != nm[i - 1]:
        ax.plot(seg_x, seg_y, color=NAVY, lw=2.2, solid_capstyle="round")
        seg_x, seg_y = [], []
    seg_x.append(x); seg_y.append(y)
ax.plot(seg_x, seg_y, color=NAVY, lw=2.2, solid_capstyle="round",
        label="시장 내재 인상확률(다음 금통위)")
seg_x, seg_y = [], []
for i, (x, y) in enumerate(zip(xs, pc)):
    if i and nm[i] != nm[i - 1]:
        ax.plot(seg_x, seg_y, color=TEAL, lw=1.4, ls=(0, (4, 3)))
        seg_x, seg_y = [], []
    seg_x.append(x); seg_y.append(y)
ax.plot(seg_x, seg_y, color=TEAL, lw=1.4, ls=(0, (4, 3)),
        label="내재 인하확률(부호 반전)")

bmsi = read_csv(RAW / "surveys" / "bmsi_policy_rate_survey.csv")
bx, by = [], []
for r in bmsi:
    if r["release_date"] >= "2026-01-01" and r["hike_pct"]:
        bx.append(D(r["release_date"])); by.append(float(r["hike_pct"]))
ax.scatter(bx, by, marker="D", s=46, color=GOLD, zorder=5,
           label="BMSI 서베이 인상응답")
for x, y in zip(bx, by):
    ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points",
                xytext=(0, 9), ha="center", fontsize=9, color=GOLD,
                fontweight="bold")

meetings_26 = [("2026-01-15", "동결"), ("2026-02-26", "동결"),
               ("2026-04-10", "동결"), ("2026-05-28", "동결"),
               ("2026-07-16", "인상")]
for ds, decision in meetings_26:
    d_ = D(ds)
    ax.axvline(d_, color=GRID, lw=0.8, zorder=0)
    ax.annotate(("▲" if decision == "인상" else "●"), (d_, 104),
                ha="center", fontsize=8,
                color=(NAVY9 if decision == "인상" else MUT),
                annotation_clip=False)
ax.annotate("금통위 결정  ● 동결  ▲ 인상", xy=(0.01, 1.06),
            xycoords="axes fraction", fontsize=8.5, color=MUT)
ax.set_ylim(-30, 112)
ax.set_ylabel("확률 (%)")
ax.axhline(0, color=AXIS, lw=1.0)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m월"))
ax.legend(loc="upper left", frameon=False, fontsize=9)
despine(ax)
save(fig, "ex1_next_meeting.svg")

# ---------------------------------------------------------------- EX2
hist = base_rate_history()
ts_r = [r for r in ts if r["date"] >= "2026-05-04"]
fig, (axA, axB) = plt.subplots(1, 2, figsize=(8.4, 3.2),
                               gridspec_kw={"width_ratios": [1, 1]})
# (a) implied year-end rate — the well-identified cumulative quantity
xsA = [D(r["date"]) for r in ts_r if r.get("implied_ye_rate")]
ysA = [float(r["implied_ye_rate"]) for r in ts_r if r.get("implied_ye_rate")]
axA.plot(xsA, ysA, color=NAVY, lw=2.2)
bx_, by_ = [xsA[0]], [2.50]
for d_, r_ in hist:
    if xsA[0] <= d_ <= xsA[-1]:
        bx_ += [d_, d_]; by_ += [by_[-1], r_]
bx_.append(xsA[-1]); by_.append(by_[-1])
axA.plot(bx_, by_, color=MUT, lw=1.6)
axA.annotate("내재 연말 기준금리", (xsA[-1], ysA[-1]),
             textcoords="offset points", xytext=(-4, 10), ha="right",
             fontsize=9.5, color=NAVY, fontweight="bold")
axA.annotate("실제 기준금리", (bx_[-1], by_[-1]),
             textcoords="offset points", xytext=(-4, -14), ha="right",
             fontsize=9.5, color=MUT)
for ds, lab, dy in [("2026-05-28", "5/28 매파 동결", 6),
                    ("2026-07-16", "7/16 인상", 6)]:
    axA.axvline(D(ds), color=GRID, lw=0.8)
    axA.annotate(lab, xy=(D(ds), 3.52), xytext=(2, dy),
                 textcoords="offset points", fontsize=8, color=MUT)
axA.set_ylim(2.42, 3.60)
axA.set_ylabel("기준금리 (%)")
axA.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
axA.set_title("(a) 연말까지의 누적 반영", fontsize=10,
              color=NAVY9, loc="left")
despine(axA)
# (b) per-meeting split — honest about identification noise
ts_b = [r for r in ts if r["date"] >= "2026-07-01"]
styles = [("prob_0827", "8/27", NAVY, "-", 2.2),
          ("prob_1022", "10/22", GOLD, (0, (6, 2)), 2.0),
          ("prob_1126", "11/26", TEAL, (0, (2, 2)), 2.0)]
for key, label, color, ls, lw in styles:
    xs2 = [D(r["date"]) for r in ts_b if r.get(key)]
    ys2 = [float(r[key]) * 100 for r in ts_b if r.get(key)]
    axB.plot(xs2, ys2, color=color, ls=ls, lw=lw)
    axB.annotate(label, (xs2[-1], ys2[-1]), textcoords="offset points",
                 xytext=(5, 0), va="center", fontsize=9.5, color=color,
                 fontweight="bold", annotation_clip=False)
axB.axvline(D("2026-07-16"), color=GRID, lw=0.8)
axB.set_ylim(0, 105)
axB.set_ylabel("25bp 인상확률 (%)")
axB.xaxis.set_major_locator(mdates.DayLocator(interval=10))
axB.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
axB.set_title("(b) 회의별 배분 — 인접 회의 간 노이즈", fontsize=10,
              color=NAVY9, loc="left")
despine(axB)
fig.tight_layout(w_pad=2.6)
save(fig, "ex2_target_meetings.svg")

# ---------------------------------------------------------------- EX3
snap = read_csv(OUT / "m1_snapshot.csv")
fit = read_csv(OUT / "m1_fit_detail.csv")
hist = base_rate_history()

fig, (axL, axR) = plt.subplots(1, 2, figsize=(8.4, 3.2),
                               gridspec_kw={"width_ratios": [1.25, 1]})
# left: implied step path
r0 = 2.740
path_x = [D("2026-08-07")]
path_y = [r0]
for r in snap:
    m = D(r["meeting"])
    after = float(r["implied_rate_after"]) + (r0 - 2.75)
    path_x += [m, m]
    path_y += [path_y[-1], after]
path_x.append(D("2027-09-30"))
path_y.append(path_y[-1])
known_end = D("2026-11-26")
kx = [x for x in path_x if x <= D("2026-12-31")]
ky = path_y[:len(kx)]
axL.plot(kx, ky, color=NAVY, lw=2.4)
axL.plot(path_x[len(kx) - 1:], path_y[len(kx) - 1:], color=NAVY, lw=1.6,
         ls=(0, (4, 3)))
axL.axhline(2.75, color=GRID, lw=1.0)
axL.annotate("기준금리 2.75%", xy=(D("2026-08-10"), 2.75),
             xytext=(0, -13), textcoords="offset points", fontsize=8.5,
             color=MUT)
for r in snap:
    m = D(r["meeting"])
    # 스냅샷 CSV의 확률 열을 그대로 반올림(half-up) — 본문 표와 동일 값 보장
    from decimal import Decimal, ROUND_HALF_UP
    p_pct = (Decimal(r["prob_25bp_hike"]) * 100).quantize(0, ROUND_HALF_UP)
    lab = f"{m.month}/{m.day}\n{p_pct}%"
    axL.annotate(lab, (m, float(r["implied_rate_after"]) + (r0 - 2.75)),
                 textcoords="offset points", xytext=(2, 7), fontsize=8,
                 color=NAVY9, ha="left")
axL.annotate("점선: 2027년 일정 미공표 — 분기 노드 가정", xy=(0.03, 0.04),
             xycoords="axes fraction", fontsize=8, color=MUT)
axL.set_ylim(2.65, 3.95)
axL.set_ylabel("내재 익일물 경로 (%)")
axL.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
axL.set_title("(a) OIS 내재 정책금리 경로", fontsize=10, color=NAVY9, loc="left")
despine(axL)

# right: market vs fitted
tn = [r["tenor"] for r in fit]
mk = [float(r["market_mid"]) for r in fit]
md = [float(r["model_fitted"]) for r in fit]
xi = np.arange(len(tn))
axR.plot(xi, md, color=GOLD, lw=1.8, marker="x", ms=7, label="모형 적합")
axR.scatter(xi, mk, s=42, color=NAVY, zorder=5, label="시장 호가(MID)")
axR.set_xticks(xi, [t.replace("개월", "M").replace("1년", "1Y") for t in tn])
axR.set_ylabel("OIS 금리 (%)")
axR.legend(frameon=False, fontsize=9, loc="upper left")
_W = {"1개월": 1.0, "2개월": 1.0, "3개월": 1.0, "6개월": 0.9, "9개월": 0.8,
      "1년": 0.7}
_rmse = float(np.sqrt(np.mean([((float(r["market_mid"]) -
                                 float(r["model_fitted"])) * _W[r["tenor"]]
                                * 100) ** 2 for r in fit])))
axR.annotate(f"가중 RMSE {_rmse:.1f}bp", xy=(0.97, 0.06),
             xycoords="axes fraction", ha="right", fontsize=8.5, color=MUT)
axR.set_title("(b) 시장 호가 대 모형 적합", fontsize=10, color=NAVY9, loc="left")
despine(axR)
fig.tight_layout(w_pad=2.4)
save(fig, "ex3_snapshot.svg")

# ---------------------------------------------------------------- EX4
m3p = read_csv(OUT / "m3_expected_path.csv")
from common import base_rate_on
base_hist_pts = [(d_, r_) for d_, r_ in hist if d_ >= date(2025, 1, 1)]
fig, ax = plt.subplots(figsize=(7.6, 3.3))
bx_, by_ = [date(2025, 1, 1)], [base_rate_on(date(2025, 1, 1), hist)]
for d_, r_ in base_hist_pts:
    bx_ += [d_, d_]
    by_ += [by_[-1], r_]
bx_.append(date(2026, 8, 7)); by_.append(by_[-1])
ax.plot(bx_, by_, color=MUT, lw=1.8, label="실제 기준금리")
ois_x = [D("2026-08-07")] + [D(r["meeting"]) for r in snap]
ois_y = [2.75] + [float(r["implied_rate_after"]) for r in snap]
ax.plot(ois_x, ois_y, color=NAVY, lw=2.2, marker="o", ms=4,
        label="OIS 내재 경로(계단함수)")
def add_m(y0, m0, k):
    mm = m0 - 1 + k
    return date(y0 + mm // 12, mm % 12 + 1, 28)
dx = [add_m(2026, 8, int(r["h_months"])) for r in m3p if int(r["h_months"]) <= 24]
dy = [float(r["expected_base_rate"]) for r in m3p if int(r["h_months"]) <= 24]
ax.plot(dx, dy, color=GOLD, lw=2.0, ls=(0, (5, 2)),
        label="DNS-VAR 기대 기준금리(프리미엄 제거)")
ax.axvline(date(2026, 8, 7), color=GRID, lw=1.0)
ax.annotate("현재", xy=(date(2026, 8, 7), 3.82), ha="center", fontsize=8.5,
            color=MUT)
ax.annotate("격차 = 기간프리미엄\n+ 2027 가정 효과",
            xy=(date(2027, 5, 1), 3.42), fontsize=8.5, color=NAVY9)
ax.set_ylim(2.3, 3.95)
ax.set_ylabel("기준금리 (%)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
ax.legend(frameon=False, fontsize=9, loc="upper left")
despine(ax)
save(fig, "ex4_expected_paths.svg")

# ---------------------------------------------------------------- EX5
sc = read_csv(OUT / "m4_scenarios.csv")
names = [r["maturity"].replace("통안 ", "통안\n").replace("국고 ", "국고\n")
         for r in sc]
emp = [float(r["beta_empirical"]) for r in sc]
dns = [float(r["dns_slope_loading_norm"]) for r in sc]
xi = np.arange(len(sc))
w = 0.38
fig, ax = plt.subplots(figsize=(7.6, 3.2))
b1 = ax.bar(xi - w / 2, emp, w * 0.94, color=NAVY, label="실증 베타(금통위 이벤트 회귀)")
b2 = ax.bar(xi + w / 2, dns, w * 0.94, color=GOLD,
            label="DNS 기울기충격 전파(KIRI 방식)")
for b, v in zip(b1, emp):
    ax.annotate(f"{v:.2f}", (b.get_x() + b.get_width() / 2, v),
                textcoords="offset points", xytext=(0, 3), ha="center",
                fontsize=8, color=NAVY9)
for b, v in zip(b2, dns):
    ax.annotate(f"{v:.2f}", (b.get_x() + b.get_width() / 2, v),
                textcoords="offset points", xytext=(0, 3), ha="center",
                fontsize=8, color=GOLD)
ax.set_xticks(xi, names, fontsize=9)
ax.set_ylabel("서프라이즈 1bp당 반응 (bp)")
ax.set_ylim(0, 1.15)
ax.legend(frameon=False, fontsize=9)
ax.annotate("* 통안 3개월 실증 베타 1.00은 정의상 고정(서프라이즈 측정 지표 자신)",
            xy=(0.01, -0.24), xycoords="axes fraction", fontsize=8, color=MUT,
            annotation_clip=False)
despine(ax)
save(fig, "ex5_passthrough.svg")

print("all figures done")
