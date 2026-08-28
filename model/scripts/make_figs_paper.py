# -*- coding: utf-8 -*-
"""학술 논문식(흑백 세리프) Exhibit 전체 세트 → model/figs_paper/.

디자인 규칙: 바탕(Batang) 세리프 · 흑백/회색조 · 사방 스파인 + 안쪽 눈금 ·
그리드 없음 · 시리즈 구분은 색이 아니라 선형(실선/파선/쇄선)과 마커(채움/빈) ·
그림 안 제목 없음(캡션은 문서 몫), 패널 태그 (a)/(b)만.
산출: figNN_slug.png(300dpi) + .svg
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from common import OUT, RAW, base_rate_history, base_rate_on

FIGP = OUT.parents[0] / "figs_paper"
FIGP.mkdir(parents=True, exist_ok=True)

BLACK, G3, G5, G7 = "#000000", "#4d4d4d", "#808080", "#b8b8b8"

plt.rcParams.update({
    "svg.fonttype": "none",
    "font.family": "serif",
    "font.serif": ["Batang", "Times New Roman", "DejaVu Serif"],
    "axes.unicode_minus": False,
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.edgecolor": "black", "axes.linewidth": 0.7,
    "xtick.direction": "in", "ytick.direction": "in",
    "xtick.top": True, "ytick.right": True,
    "xtick.major.size": 3.0, "ytick.major.size": 3.0,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.grid": False,
    "legend.fontsize": 8, "legend.frameon": True, "legend.fancybox": False,
    "legend.edgecolor": "black", "legend.framealpha": 1.0,
    "figure.facecolor": "white", "axes.facecolor": "white",
    "lines.linewidth": 1.1,
})

D = lambda s: datetime.strptime(s, "%Y-%m-%d").date()


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save(fig, slug):
    for ext, kw in [(".png", {"dpi": 300}), (".svg", {})]:
        fig.savefig(FIGP / (slug + ext), bbox_inches="tight",
                    pad_inches=0.05, **kw)
    plt.close(fig)
    print("saved", slug)


def tag(ax, label):
    ax.text(0.0, 1.02, label, transform=ax.transAxes, ha="left",
            va="bottom", fontsize=9)


def slim_legend(leg):
    leg.get_frame().set_linewidth(0.6)


def pct_half_up(prob_str):
    return f"{(Decimal(prob_str) * 100).quantize(0, ROUND_HALF_UP)}%"


# ══════════════════════════════════════════════ 현재 시점 앵커
# 기준금리 2.75, r0 2.740, 기준일 2026-08-07이 그림 곳곳에 박혀 있었다.
# 데이터를 갱신해도 축선·라벨이 옛 시점을 가리켜, 8/27 인상 뒤에는 "기준금리
# 2.75%"라는 틀린 주석이 그대로 찍혔다. 산출물에서 읽어 쓴다.
_snap_anchor = read_csv(OUT / "m1_snapshot.csv")
_ts_anchor = {r["date"]: r for r in read_csv(OUT / "m1_timeseries.csv")}
ASOF_S = _snap_anchor[0]["asof"]
ASOF = D(ASOF_S)
R0 = float(_ts_anchor[ASOF_S]["r0"])
BASE = base_rate_on(ASOF, base_rate_history())


# ══════════════════════════════════════════════ fig01 개념도
fig, ax = plt.subplots(figsize=(6.8, 2.9))
d0, dm, d1 = date(2026, 8, 7), date(2026, 8, 27), date(2026, 10, 7)
r0, hike, quote = 2.74, 2.99, 2.84
ax.plot([d0, dm], [r0, r0], color=BLACK, lw=1.5)
ax.plot([dm, d1], [hike, hike], color=BLACK, lw=1.5)
ax.plot([dm, d1], [r0, r0], color=BLACK, lw=1.2, ls=(0, (5, 3)))
ax.plot([dm, dm], [r0, hike], color=G7, lw=0.8, ls=(0, (1, 2)))
ax.plot([d0, d1], [quote, quote], color=G5, lw=1.2, ls=(0, (7, 2, 1, 2)))
ax.text(date(2026, 8, 16), r0 - 0.035, "회의 전: 2.740%", ha="center",
        va="top", fontsize=8)
ax.text(date(2026, 9, 16), hike + 0.02, "인상 시: 2.990% (확률 P)",
        ha="center", fontsize=8)
ax.text(date(2026, 9, 16), r0 - 0.035, "동결 시: 2.740% (확률 1-P)",
        ha="center", va="top", fontsize=8)
ax.text(date(2026, 9, 2), quote + 0.02,
        "시장 호가 2.840% = 두 경로의 확률가중 평균", ha="center", fontsize=8)
ax.text(dm, 2.63, "8/27 금통위", ha="center", fontsize=7.5, color=G3)
ax.set_ylim(2.60, 3.06)
ax.set_ylabel("익일물 금리 경로 (%)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
save(fig, "fig01_concept")

# ══════════════════════════════════════════════ fig02 적합 스냅샷
snap = read_csv(OUT / "m1_snapshot.csv")
fit = read_csv(OUT / "m1_fit_detail.csv")
fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.4, 2.9),
                               gridspec_kw={"width_ratios": [1.25, 1]})
r0v = R0
px, py = [ASOF], [r0v]
for r in snap:
    m = D(r["meeting"])
    after = float(r["implied_rate_after"]) + (r0v - BASE)
    px += [m, m]
    py += [py[-1], after]
px.append(D("2027-09-30"))
py.append(py[-1])
kx = [x for x in px if x <= D("2026-12-31")]
ky = py[:len(kx)]
axL.plot(kx, ky, color=BLACK, lw=1.4)
axL.plot(px[len(kx) - 1:], py[len(kx) - 1:], color=BLACK, lw=1.1,
         ls=(0, (4, 3)))
axL.axhline(BASE, color=G7, lw=0.7, ls=(0, (1, 2)))
axL.text(ASOF + timedelta(days=6), BASE - 0.018, f"기준금리 {BASE:.2f}%",
         fontsize=7, color=G3, va="top")
for r in snap:
    m = D(r["meeting"])
    lab = f"{m.month}/{m.day}\n{pct_half_up(r['prob_25bp_hike'])}"
    axL.annotate(lab, (m, float(r["implied_rate_after"]) + (r0v - BASE)),
                 textcoords="offset points", xytext=(2, 5), fontsize=6.8)
axL.text(0.52, 0.05, "점선: 2027년 분기 노드 가정", transform=axL.transAxes,
         fontsize=7, color=G3)
axL.set_ylim(min(py) - 0.12, max(py) + 0.30)
axL.set_ylabel("내재 익일물 경로 (%)")
axL.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
tag(axL, "(a) 내재 정책금리 경로")

tn = [r["tenor"] for r in fit]
mk = [float(r["market_mid"]) for r in fit]
md = [float(r["model_fitted"]) for r in fit]
xi = np.arange(len(tn))
axR.plot(xi, md, color=BLACK, lw=1.0, marker="s", ms=3.2,
         mfc=BLACK, label="모형 적합")
axR.plot(xi, mk, ls="none", marker="o", ms=5, mfc="white", mec=BLACK,
         mew=0.9, label="시장 호가(MID)")
_W = {"1개월": 1.0, "2개월": 1.0, "3개월": 1.0, "6개월": 0.9, "9개월": 0.8,
      "1년": 0.7}
_rmse = float(np.sqrt(np.mean([((float(r["market_mid"]) -
                                 float(r["model_fitted"])) * _W[r["tenor"]]
                                * 100) ** 2 for r in fit])))
axR.text(0.97, 0.06, f"가중 RMSE {_rmse:.1f}bp", transform=axR.transAxes,
         ha="right", fontsize=7.5, color=G3)
axR.set_xticks(xi, [t.replace("개월", "M").replace("1년", "1Y") for t in tn])
axR.set_ylabel("OIS 금리 (%)")
leg = axR.legend(loc="upper left")
slim_legend(leg)
tag(axR, "(b) 시장 호가 대 모형 적합")
fig.tight_layout(w_pad=2.0)
save(fig, "fig02_fit_snapshot")

# ══════════════════════════════════════════════ fig03 누적 vs 배분
ts = read_csv(OUT / "m1_timeseries.csv")
hist = base_rate_history()
ts_r = [r for r in ts if r["date"] >= "2026-05-04"]
fig, (axA, axB) = plt.subplots(1, 2, figsize=(7.4, 2.9))
xsA = [D(r["date"]) for r in ts_r if r.get("implied_ye_rate")]
ysA = [float(r["implied_ye_rate"]) for r in ts_r if r.get("implied_ye_rate")]
axA.plot(xsA, ysA, color=BLACK, lw=1.3, label="내재 연말 기준금리")
bx_, by_ = [xsA[0]], [2.50]
for d_, r_ in hist:
    if xsA[0] <= d_ <= xsA[-1]:
        bx_ += [d_, d_]
        by_ += [by_[-1], r_]
bx_.append(xsA[-1])
by_.append(by_[-1])
axA.plot(bx_, by_, color=G5, lw=1.1, label="실제 기준금리")
for ds, lab in [("2026-05-28", "5/28"), ("2026-07-16", "7/16")]:
    axA.axvline(D(ds), color=G7, lw=0.7, ls=(0, (1, 2)))
    axA.text(D(ds), 3.55, lab, ha="center", fontsize=7, color=G3)
axA.set_ylim(2.42, 3.62)
axA.set_ylabel("기준금리 (%)")
axA.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
leg = axA.legend(loc="lower right")
slim_legend(leg)
tag(axA, "(a) 연말까지의 누적 반영")

ts_b = [r for r in ts if r["date"] >= "2026-07-01"]
styles = [("prob_0827", "8/27", "-", BLACK, 1.3),
          ("prob_1022", "10/22", (0, (5, 2)), G3, 1.1),
          ("prob_1126", "11/26", (0, (7, 2, 1, 2)), G5, 1.1)]
for key, label, ls, c, lw in styles:
    xs2 = [D(r["date"]) for r in ts_b if r.get(key)]
    ys2 = [float(r[key]) * 100 for r in ts_b if r.get(key)]
    axB.plot(xs2, ys2, color=c, ls=ls, lw=lw, label=label)
axB.axvline(D("2026-07-16"), color=G7, lw=0.7, ls=(0, (1, 2)))
axB.set_ylim(0, 105)
axB.set_ylabel("25bp 인상확률 (%)")
axB.xaxis.set_major_locator(mdates.DayLocator(interval=10))
axB.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
leg = axB.legend(loc="lower left", ncols=3, columnspacing=0.9,
                 handlelength=1.7)
slim_legend(leg)
tag(axB, "(b) 회의별 배분")
fig.tight_layout(w_pad=2.0)
save(fig, "fig03_cumulative_allocation")

# ══════════════════════════════════════════════ fig04 다음 회의 확률
ts26 = [r for r in ts if r["date"] >= "2026-01-01" and r.get("prob_next_hike")]
xs = [D(r["date"]) for r in ts26]
ph = [float(r["prob_next_hike"]) * 100 for r in ts26]
pc = [-float(r["prob_next_cut"]) * 100 for r in ts26]
nm = [r["next_meeting"] for r in ts26]

fig, ax = plt.subplots(figsize=(7.4, 3.1))


def plot_segmented(ax, xs, ys, nm, **kw):
    seg_x, seg_y = [], []
    first = True
    for i, (x, y) in enumerate(zip(xs, ys)):
        if i and nm[i] != nm[i - 1]:
            ax.plot(seg_x, seg_y, **{k: v for k, v in kw.items()
                                     if k != "label"})
            seg_x, seg_y = [], []
    # (마지막 세그먼트에만 라벨)
        seg_x.append(x)
        seg_y.append(y)
    ax.plot(seg_x, seg_y, **kw)


plot_segmented(ax, xs, ph, nm, color=BLACK, lw=1.3,
               label="시장 내재 인상확률(다음 금통위)")
plot_segmented(ax, xs, pc, nm, color=G5, lw=1.0, ls=(0, (5, 2)),
               label="내재 인하확률(부호 반전)")

bmsi = read_csv(RAW / "surveys" / "bmsi_policy_rate_survey.csv")
bx, by = [], []
for r in bmsi:
    if r["release_date"] >= "2026-01-01" and r["hike_pct"]:
        bx.append(D(r["release_date"]))
        by.append(float(r["hike_pct"]))
ax.plot(bx, by, ls="none", marker="D", ms=5, mfc="white", mec=BLACK, mew=0.9,
        label="BMSI 서베이 인상응답", zorder=5)
for x, y in zip(bx, by):
    ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points",
                xytext=(0, 8), ha="center", fontsize=7.5)

meetings_26 = [("2026-01-15", "hold"), ("2026-02-26", "hold"),
               ("2026-04-10", "hold"), ("2026-05-28", "hold"),
               ("2026-07-16", "hike")]
for ds, dec in meetings_26:
    d_ = D(ds)
    ax.axvline(d_, color=G7, lw=0.6, ls=(0, (1, 2)), zorder=0)
    if dec == "hike":
        ax.scatter([d_], [106], marker="^", s=26, color=BLACK, clip_on=False,
                   zorder=6)
    else:
        ax.scatter([d_], [106], marker="o", s=18, facecolors="white",
                   edgecolors=G3, linewidths=0.9, clip_on=False, zorder=6)
h_dec = [Line2D([], [], ls="none", marker="^", ms=5, mfc=BLACK, mec=BLACK,
                label="실제 인상(상단 표식)"),
         Line2D([], [], ls="none", marker="o", ms=5, mfc="white", mec=G3,
                label="실제 동결(상단 표식)")]
ax.set_ylim(-30, 112)
ax.set_ylabel("확률 (%)")
ax.axhline(0, color=BLACK, lw=0.7)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m월"))
handles, labels = ax.get_legend_handles_labels()
leg = ax.legend(handles + h_dec, labels + [h.get_label() for h in h_dec],
                loc="upper left", ncols=1)
slim_legend(leg)
save(fig, "fig04_next_meeting")

# ══════════════════════════════════════════════ fig05 기대 경로 비교
m3p = read_csv(OUT / "m3_expected_path.csv")
fig, ax = plt.subplots(figsize=(6.8, 2.9))
base_pts = [(d_, r_) for d_, r_ in hist if d_ >= date(2025, 1, 1)]
bx_, by_ = [date(2025, 1, 1)], [3.00]
for d_, r_ in base_pts:
    bx_ += [d_, d_]
    by_ += [by_[-1], r_]
bx_.append(ASOF)
by_.append(by_[-1])
ax.plot(bx_, by_, color=G5, lw=1.1, label="실제 기준금리")
ois_x = [ASOF] + [D(r["meeting"]) for r in snap]
ois_y = [R0] + [float(r["implied_rate_after"]) for r in snap]
ax.plot(ois_x, ois_y, color=BLACK, lw=1.3, marker="o", ms=3.2,
        label="OIS 내재 경로(계단함수)")


def add_m(y0, m0, k):
    mm = m0 - 1 + k
    return date(y0 + mm // 12, mm % 12 + 1, 28)


dx = [add_m(2026, 8, int(r["h_months"])) for r in m3p
      if int(r["h_months"]) <= 24]
dy = [float(r["expected_base_rate"]) for r in m3p if int(r["h_months"]) <= 24]
ax.plot(dx, dy, color=BLACK, lw=1.1, ls=(0, (5, 2)), marker="s", ms=3.4,
        mfc="white", mec=BLACK, mew=0.8, label="DNS-VAR 기대(프리미엄 제거)")
ax.axvline(ASOF, color=G7, lw=0.7, ls=(0, (1, 2)))
ax.set_ylabel("기준금리 (%)")
leg = ax.legend(loc="lower left")
slim_legend(leg)
save(fig, "fig05_expected_paths")

# ══════════════════════════════════════════════ fig06 기대·프리미엄 분해
dec = read_csv(OUT / "m3_decomposition.csv")
rows6 = [r for r in dec if r["term_premium_bp"] not in ("", None)]
labels6 = {3: "3개월", 6: "6개월", 9: "9개월", 12: "1년", 24: "2년", 36: "3년"}
tenors6 = [int(r["tenor_months"]) for r in rows6]
ylds = [float(r["zero_yield"]) for r in rows6]
exps = [float(r["avg_expected_short"]) for r in rows6]
prem = [float(r["term_premium_bp"]) for r in rows6]
xi = np.arange(len(rows6))
fig, ax = plt.subplots(figsize=(6.8, 2.9))
for i, (y_, e_) in enumerate(zip(ylds, exps)):
    ax.plot([i, i], [e_, y_], color=G7, lw=1.4, zorder=1)
ax.plot(xi, ylds, ls="none", marker="o", ms=5.5, mfc=BLACK, mec=BLACK,
        zorder=3, label="실제 금리(민평)")
ax.plot(xi, exps, ls="none", marker="D", ms=5, mfc="white", mec=BLACK,
        mew=0.9, zorder=3, label="기대 단기금리 평균(DNS-VAR)")
for i, p_ in enumerate(prem):
    top = max(ylds[i], exps[i])
    ax.annotate(f"{p_:+.0f}bp", (i, top), textcoords="offset points",
                xytext=(0, 7), ha="center", fontsize=7.5)
ax.set_xticks(xi, [labels6[t] for t in tenors6])
ax.set_ylabel("금리 (%)")
ax.set_ylim(2.75, 4.10)
leg = ax.legend(loc="upper left")
slim_legend(leg)
save(fig, "fig06_decomposition")

# ══════════════════════════════════════════════ fig07 전달률 (1bp당)
sc = read_csv(OUT / "m4_scenarios.csv")
names7 = [r["maturity"].replace("통안 ", "통안").replace("국고 ", "국고")
          for r in sc]
be = [float(r["beta_empirical"]) for r in sc]
bd = [float(r["dns_slope_loading_norm"]) for r in sc]
xi = np.arange(len(sc))
w = 0.38
fig, ax = plt.subplots(figsize=(7.0, 2.9))
ax.bar(xi - w / 2, be, w, facecolor="#6a6a6a", edgecolor=BLACK, lw=0.7,
       label="실증 베타(이벤트 회귀)")
ax.bar(xi + w / 2, bd, w, facecolor="white", edgecolor=BLACK, lw=0.7,
       hatch="////", label="DNS 기울기충격 전파")
ax.axhline(0, color=BLACK, lw=0.7)
ax.set_xticks(xi, names7, fontsize=7.5)
ax.set_ylabel("전달률 (bp / 서프라이즈 1bp)")
ax.text(0.98, 0.90, "만기별 이동폭 = 전달률 × 서프라이즈\n(8월 인상 시 서프라이즈 +12.4bp)",
        transform=ax.transAxes, ha="right", fontsize=7.5)
leg = ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.80))
slim_legend(leg)
save(fig, "fig07_passthrough")

# ══════════════════════════════════════════════ fig08 시나리오 커브
hike_e = [float(r["hike_move_bp_empirical"]) for r in sc]
hold_e = [float(r["hold_move_bp_empirical"]) for r in sc]
xi = np.arange(len(sc))
fig, ax = plt.subplots(figsize=(7.0, 2.9))
ax.axhline(0, color=BLACK, lw=0.7)
ax.plot(xi, hike_e, color=BLACK, lw=1.3, marker="o", ms=4.2, mfc=BLACK,
        label="인상 시 (서프라이즈 +12.4bp)")
ax.plot(xi, hold_e, color=BLACK, lw=1.1, ls=(0, (5, 2)), marker="o", ms=4.2,
        mfc="white", mec=BLACK, mew=0.8, label="동결 시 (서프라이즈 -12.6bp)")
for i in (0, 4, 6):
    ax.annotate(f"{hike_e[i]:+.0f}", (xi[i], hike_e[i]),
                textcoords="offset points", xytext=(0, 7), ha="center",
                fontsize=7.5)
    ax.annotate(f"{hold_e[i]:+.0f}", (xi[i], hold_e[i]),
                textcoords="offset points", xytext=(0, -11), ha="center",
                fontsize=7.5)
ax.set_xticks(xi, names7, fontsize=7.5)
ax.set_ylabel("발표 당일 예상 변화 (bp)")
ax.set_ylim(-17, 18)
leg = ax.legend(loc="upper right")
slim_legend(leg)
save(fig, "fig08_scenario_curves")

# ══════════════════════════════════════════════ fig09 통안-OIS 격차
gap = read_csv(OUT / "m6_gap_daily.csv")
gxs = [D(r["date"]) for r in gap if r["gap_6m_bp"]]
g6 = [float(r["gap_6m_bp"]) for r in gap if r["gap_6m_bp"]]
med = float(np.median(g6))
fig, ax = plt.subplots(figsize=(7.0, 2.8))
ax.plot(gxs, g6, color=BLACK, lw=0.8)
ax.axhline(med, color=G5, lw=1.1, ls=(0, (5, 2)))
ax.axhline(0, color=BLACK, lw=0.6)
ax.text(D("2023-08-01"), med - 9, f"전 표본 중위값 +{med:.1f}bp",
        fontsize=7.5, color=G3, ha="center")
ax.text(D("2022-10-20"), 80, "2022 자금경색", fontsize=7.5, color=G3,
        ha="center")
for ds in ("2026-05-28", "2026-07-16"):
    ax.axvline(D(ds), color=G7, lw=0.7, ls=(0, (1, 2)))
ax.text(D("2026-04-01"), 62, "2026 매파\n재가격", fontsize=7.5, color=G3,
        ha="center")
ax.set_ylim(min(g6) - 4, max(g6) + 5)
ax.set_ylabel("OIS 6개월 - 통안 6개월 (bp)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
save(fig, "fig09_msb_ois_gap")

# ══════════════════════════════════════════════ fig10 백테스트 타임라인
bt = read_csv(OUT / "m5_backtest_meetings.csv")
rows10 = [r for r in bt if r["meeting"] >= "2013-02-01"]


def net(r, src):
    h, c = r.get(f"{src}_hike"), r.get(f"{src}_cut")
    if h in ("", None) or c in ("", None):
        return None
    return float(h) - float(c)


fig, ax = plt.subplots(figsize=(7.8, 3.1))
mx = [D(r["meeting"]) for r in rows10 if net(r, "msb") is not None]
my = [net(r, "msb") for r in rows10 if net(r, "msb") is not None]
ax.plot(mx, my, color=G7, lw=0.6, zorder=2)
ax.plot(mx, my, ls="none", marker="o", ms=2.8, mfc=BLACK, mec=BLACK,
        zorder=3, label="통안 스트립 내재(전일)")
bx = [D(r["meeting"]) for r in rows10 if net(r, "bmsi") is not None]
by = [net(r, "bmsi") for r in rows10 if net(r, "bmsi") is not None]
ax.plot(bx, by, ls="none", marker="D", ms=3.6, mfc="white", mec=BLACK,
        mew=0.8, zorder=4, label="BMSI 서베이")
ox = [D(r["meeting"]) for r in rows10
      if r["meeting"] >= "2024-10-01" and net(r, "ois") is not None]
oy = [net(r, "ois") for r in rows10
      if r["meeting"] >= "2024-10-01" and net(r, "ois") is not None]
ax.plot(ox, oy, ls="none", marker="s", ms=4.4, mfc="none", mec=BLACK,
        mew=1.0, zorder=5, label="KOFR OIS(2024.10~)")
hx = [D(r["meeting"]) for r in rows10 if r["outcome"] == "hike"]
cx = [D(r["meeting"]) for r in rows10 if r["outcome"] == "cut"]
ax.scatter(hx, [1.16] * len(hx), marker="^", s=14, color=BLACK,
           clip_on=False, zorder=6, label="실제 인상(상단)")
ax.scatter(cx, [-1.22] * len(cx), marker="v", s=14, facecolors="white",
           edgecolors=BLACK, linewidths=0.7, clip_on=False, zorder=6,
           label="실제 인하(하단)")
ax.axhline(0, color=BLACK, lw=0.6)
_r1128 = next(r for r in rows10 if r["meeting"] == "2024-11-28")
_mn, _bn = net(_r1128, "msb"), net(_r1128, "bmsi")
ax.annotate(f"'깜짝 인하' 2024-11: 시장 {_mn:+.2f} vs 서베이 {_bn:+.2f}",
            xy=(D("2024-11-28"), _mn), xytext=(-215, -22),
            textcoords="offset points", fontsize=7.5,
            arrowprops=dict(arrowstyle="-", color=G5, lw=0.7, shrinkB=3))
ax.set_ylim(-1.34, 1.34)
ax.set_yticks([-1, -0.5, 0, 0.5, 1])
ax.set_ylabel("내재 순확률 (인상 - 인하)")
ax.xaxis.set_major_locator(mdates.YearLocator(2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
leg = ax.legend(loc="upper left", ncols=2, columnspacing=0.9, fontsize=7.2,
                handlelength=1.4)
slim_legend(leg)
save(fig, "fig10_backtest_timeline")

# ══════════════════════════════════════════════ fig11 충격 산술 표본외
rows11 = read_csv(OUT / "m7_validation_meetings.csv")
REGIMES = [
    ("완화·동결 20.1~21.7", date(2020, 1, 1), date(2021, 7, 31),
     dict(marker="o", mfc="white", mec=G3, mew=0.9, ms=4.6)),
    ("급속 인상 21.8~23.1", date(2021, 8, 1), date(2023, 1, 31),
     dict(marker="^", mfc=BLACK, mec=BLACK, ms=5.0)),
    ("동결 23.2~24.9", date(2023, 2, 1), date(2024, 9, 30),
     dict(marker="s", mfc="white", mec=BLACK, mew=0.9, ms=4.2)),
    ("인하 24.10~", date(2024, 10, 1), date(2026, 12, 31),
     dict(marker="D", mfc="#8a8a8a", mec=BLACK, mew=0.5, ms=4.2)),
]
CORR = {"msb91": "완화 +0.71 · 급속 +0.82\n동결 +0.17 · 인하 +0.35",
        "ktb3": "완화 +0.52 · 급속 -0.48\n동결 +0.15 · 인하 +0.41",
        "ktb10": "완화 +0.32 · 급속 -0.41\n동결 +0.06 · 인하 +0.29"}
fig, (axA, axB, axC) = plt.subplots(1, 3, figsize=(10.4, 3.0))
for ax, key, panel in [(axA, "msb91", "(a) 통안 3개월"),
                       (axB, "ktb3", "(b) 국고 3년"),
                       (axC, "ktb10", "(c) 국고 10년")]:
    lim = 28
    ax.plot([-lim, lim], [-lim, lim], color=G7, lw=0.8)
    ax.axhline(0, color=BLACK, lw=0.5)
    ax.axvline(0, color=BLACK, lw=0.5)
    for reg_name, a, b, mkw in REGIMES:
        p, q = [], []
        for r in rows11:
            if not (r.get(f"pred_{key}") and r.get(f"real_{key}")):
                continue
            d_ = date.fromisoformat(r["meeting"])
            if a <= d_ <= b:
                p.append(float(r[f"pred_{key}"]))
                q.append(float(r[f"real_{key}"]))
        ax.plot(p, q, ls="none", zorder=3,
                label=(reg_name if ax is axA else None), **mkw)
    epi = next(r for r in rows11 if r["meeting"] == "2025-01-16")
    ax.plot([float(epi[f"pred_{key}"])], [float(epi[f"real_{key}"])],
            ls="none", marker="o", ms=9, mfc="none", mec=BLACK, mew=1.1,
            zorder=5)
    ax.text(0.03, 0.97, CORR[key], transform=ax.transAxes, va="top",
            fontsize=7.2)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("예측 변동 = β × 서프라이즈 (bp)", fontsize=8)
    tag(ax, panel)
axA.set_ylabel("실제 당일 변동 (bp)")
axB.annotate("2025-01-16 깜짝 동결\n(회견발 반전)",
             xy=(float(epi["pred_ktb3"]), float(epi["real_ktb3"])),
             xytext=(-2, -46), textcoords="offset points", fontsize=7.2,
             arrowprops=dict(arrowstyle="-", color=G5, lw=0.7))
leg = axA.legend(loc="lower right", fontsize=6.8, handlelength=1.0,
                 borderpad=0.4, labelspacing=0.3)
slim_legend(leg)
fig.tight_layout(w_pad=2.0)
save(fig, "fig11_shock_validation")

# ══════════════════════════════════════════════ fig12 AFNS 재현·비교
m10p = read_csv(OUT / "m10_afns_expected_path.csv")
m3p2 = read_csv(OUT / "m3_expected_path.csv")
m10d = read_csv(OUT / "m10_afns_decomposition.csv")
m3d = read_csv(OUT / "m3_decomposition.csv")

fig, (axA, axB) = plt.subplots(1, 2, figsize=(7.4, 2.9))
H12 = 10   # 앞 10개월만 — 너머는 평균회귀 사전믿음이 지배(v15)
hs = np.arange(1, H12 + 1)
afns_p = [float(r["expected_base_rate"]) for r in m10p][:H12]
dns_p = [float(r["expected_base_rate"]) for r in m3p2][:H12]
ois_x = [0] + [(D(r["meeting"]) - ASOF).days / 30.4
               for r in snap]
ois_y = [R0] + [float(r["implied_rate_after"]) for r in snap]
axA.step(ois_x, ois_y, where="post", color=G7, lw=1.2,
         label="OIS 내재(프리미엄 포함)")
axA.plot(hs, afns_p, color=BLACK, lw=1.4, label="AFNS 기대(한은 방법론)")
axA.plot(hs, dns_p, color=G3, lw=1.1, ls=(0, (5, 2)),
         label="DNS-VAR 기대(2단계 근사)")
axA.axhline(BASE, color=G7, lw=0.6, ls=(0, (1, 2)))
axA.set_xlim(0, H12 + 0.2)
axA.set_xlabel("개월 후", fontsize=8)
axA.set_ylabel("기대 기준금리 (%)")
leg = axA.legend(loc="lower right", fontsize=7)
slim_legend(leg)
tag(axA, "(a) 기대 기준금리 경로(앞 10개월)")

t10 = [int(r["tenor_months"]) for r in m10d]
tp10 = [float(r["tp_obs_bp"]) for r in m10d]
t3 = [int(r["tenor_months"]) for r in m3d if r["term_premium_bp"] not in ("", None)]
tp3 = [float(r["term_premium_bp"]) for r in m3d if r["term_premium_bp"] not in ("", None)]
axB.axhline(0, color=BLACK, lw=0.6)
axB.plot(t10, tp10, color=BLACK, lw=1.2, marker="o", ms=4, mfc=BLACK,
         label="AFNS")
axB.plot(t3, tp3, ls="none", marker="D", ms=4.6, mfc="white", mec=BLACK,
         mew=0.9, label="DNS-VAR")
axB.set_xscale("log")
axB.set_xticks([3, 6, 12, 24, 36, 60, 120],
               ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "10Y"], fontsize=7.5)
axB.minorticks_off()
axB.set_xlabel("만기", fontsize=8)
axB.set_ylabel("기간프리미엄 (bp)")
leg = axB.legend(loc="upper left", fontsize=7)
slim_legend(leg)
tag(axB, "(b) 만기별 기간프리미엄")
axB.annotate("3M 음수 = 웨지·적합 잔차", xy=(3, tp10[0]),
             xytext=(4.6, 42), fontsize=6.5, color=G3,
             arrowprops=dict(arrowstyle="-", color=G3, lw=0.6))
fig.tight_layout(w_pad=2.0)
save(fig, "fig12_afns_comparison")

print("paper figures done ->", FIGP)
