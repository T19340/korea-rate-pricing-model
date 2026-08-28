# -*- coding: utf-8 -*-
"""Question 2 — pseudo real-time backtest over every scheduled MPC meeting.

For each meeting since 2013 (IRS strip: since 2011), fit the meeting-dated
step function on the LAST trading day before the meeting and record the
implied hike/hold/cut probabilities from three instrument sets:

  msb : MSB 91d + 6M(KOFIA, 2013~) + 1Y, premium-adjusted, call-rate anchor
  irs : CD-IRS zero curve 3M/6M/9M/1Y (2011~), CD91 anchor
        (CD-base wedge assumed constant -> overstates hikes in funding stress)
  ois : KOFR OIS 1M..1Y (2022-04~; broker quotes, CCP-cleared from 2025-10)

Benchmarks: KOFIA BMSI survey shares (when the question was asked) and the
unconditional outcome frequency (climatology). Scoring: 3-way Brier.

Outputs: m5_backtest_meetings.csv, m5_backtest_summary.json, m5_episodes.csv
"""
from __future__ import annotations

import csv
import os
import json
from datetime import date, timedelta

import numpy as np

from common import OUT, base_rate_history, base_rate_on, ecos_daily, kofia_avg, load_irs, load_ois, mpc_meetings
from m1_step_function import (Fitter, fit_deltas, LAMBDA_SMOOTH, SHRINK_2026,
                              SHRINK_2027)

EXCLUDE = {date(2020, 3, 16)}  # emergency inter-meeting cut

hist = base_rate_history()
meetings_all = sorted(m for m in mpc_meetings() if m not in EXCLUDE)


def outcome_of(m: date) -> str:
    before = base_rate_on(m - timedelta(days=1), hist)
    after = base_rate_on(m + timedelta(days=3), hist)
    if after > before + 1e-9:
        return "hike"
    if after < before - 1e-9:
        return "cut"
    return "hold"


def upcoming_nodes(asof: date, horizon: int = 370):
    return [m for m in meetings_all if asof < m <= asof + timedelta(days=horizon)]


def fit_strip(asof: date, obs: dict[int, float], anchor: float,
              weights: dict[int, float]):
    nodes = upcoming_nodes(asof)
    if not nodes or len(obs) < 2:
        return None
    y = np.array([obs[t] for t in sorted(obs)])
    w = np.array([weights[t] for t in sorted(obs)])
    days = sorted(obs)
    is_ph = np.zeros(len(nodes), dtype=bool)
    res = fit_deltas(asof, days, y, w, nodes, is_ph, anchor,
                     smooth=2 * LAMBDA_SMOOTH,
                     shrink26=SHRINK_2026 * 4, shrink27=SHRINK_2027 * 4)
    if res is None:
        return None
    dl, _, _ = res
    return nodes, dl


def probs_from_delta(d_bp: float):
    p_hike = min(max(d_bp / 25.0, 0.0), 1.0)
    p_cut = min(max(-d_bp / 25.0, 0.0), 1.0)
    return p_hike, 1.0 - p_hike - p_cut, p_cut


# ---------------- data
msb91 = ecos_daily("msb_91d_daily")
msb6m = kofia_avg("msb_6m_val_daily")
msb1y = ecos_daily("msb_1y_daily")
call = ecos_daily("call_overnight_daily")
cd91 = ecos_daily("cd_91d_daily")
irs = load_irs()
ois = load_ois()
ft = Fitter()

# quiet-window premium (same rule as m1)
quiet = []
for d_, y1 in msb1y.items():
    if not (2015 <= d_.year <= 2024):
        continue
    b = base_rate_on(d_, hist)
    nxt = next((m for m in meetings_all if m > d_), None)
    if nxt and abs(base_rate_on(nxt + timedelta(days=3), hist) - b) < 1e-9 \
            and abs(y1 - b) < 0.12:
        quiet.append(d_)


def phi(series):
    sp = sorted(series[d_] - base_rate_on(d_, hist) for d_ in quiet if d_ in series)
    return sp[len(sp) // 2] if sp else 0.0


PHI = {"91": phi(msb91), "6m": phi(msb6m), "1y": phi(msb1y)}

# BMSI by target meeting
bmsi = {}
with open(OUT.parents[1] / "rawdata" / "surveys" / "bmsi_policy_rate_survey.csv",
          encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["target_meeting"]:
            m = date.fromisoformat(r["target_meeting"])
            vals = {}
            for k, col in [("hike", "hike_pct"), ("hold", "hold_pct"),
                           ("cut", "cut_pct")]:
                vals[k] = float(r[col]) / 100 if r[col] else None
            known = {k: v for k, v in vals.items() if v is not None}
            if known and sum(known.values()) >= 0.45:
                if len(known) == 2 and abs(sum(known.values()) - 1.0) > 0.02:
                    missing = [k for k in vals if vals[k] is None][0]
                    vals[missing] = max(0.0, 1.0 - sum(known.values()))
                elif len(known) == 1:
                    dominant = list(known)[0]
                    rest = 1.0 - known[dominant]
                    for k in vals:
                        if vals[k] is None:
                            vals[k] = rest if k == "hold" and dominant != "hold" \
                                else (rest if dominant == "hold" and k != "hike"
                                      else 0.0)
                    # single-share rows: assign remainder to hold (or to cut in
                    # cut cycles via the hold-dominant branch) — crude, flagged
                s = sum(v or 0 for v in vals.values())
                if s > 0:
                    bmsi[m] = {k: (v or 0) / s for k, v in vals.items()}


def last_before(series_dates, m):
    for lag in range(1, 8):
        d = m - timedelta(days=lag)
        if d in series_dates:
            return d
    return None


# 표본 끝은 하드코딩하지 않는다. 2026-07-31로 고정돼 있어서 8/27 회의가 열린
# 뒤에도 백테스트에 들어오지 않았다. 이미 열렸고(결정이 확정됐고) 회의 전날
# 호가가 있는 회의까지를 표본으로 삼는다.
# 기본은 데이터가 있는 데까지. 특정 시점의 기준선을 다시 뽑을 때만 환경변수로 고정한다
#   SAMPLE_END=2026-08-07 python m5_backtest.py
SAMPLE_END = (date.fromisoformat(os.environ["SAMPLE_END"])
              if os.environ.get("SAMPLE_END") else max(d for d in load_ois()))
rows = []
for m in meetings_all:
    if not (date(2011, 1, 1) <= m <= SAMPLE_END):
        continue
    rec = {"meeting": m.isoformat(), "outcome": outcome_of(m)}

    # MSB strip
    d = last_before(msb91, m)
    if d and m >= date(2013, 2, 1):
        obs, wts = {}, {}
        obs[91] = msb91[d] - PHI["91"]; wts[91] = 1.0
        if d in msb6m:
            obs[182] = msb6m[d] - PHI["6m"]; wts[182] = 0.9
        if d in msb1y:
            obs[365] = msb1y[d] - PHI["1y"]; wts[365] = 0.7
        anchor = call.get(d)
        if anchor and len(obs) >= 2:
            fit = fit_strip(d, obs, anchor, wts)
            if fit:
                nodes, dl = fit
                if m in nodes:
                    ph, po, pc = probs_from_delta(dl[nodes.index(m)] * 100)
                    rec.update(msb_hike=round(ph, 3), msb_hold=round(po, 3),
                               msb_cut=round(pc, 3), msb_asof=d.isoformat())

    # IRS strip
    d = last_before(irs, m)
    if d:
        q = irs[d]
        obs = {}
        for tn, days_ in [("03M", 91), ("06M", 182), ("09M", 273), ("01Y", 365)]:
            if tn in q:
                obs[days_] = q[tn]
        anchor = cd91.get(d)
        if anchor and len(obs) >= 3:
            wts = {91: 1.0, 182: 0.9, 273: 0.8, 365: 0.7}
            fit = fit_strip(d, obs, anchor, {k: wts[k] for k in obs})
            if fit:
                nodes, dl = fit
                if m in nodes:
                    ph, po, pc = probs_from_delta(dl[nodes.index(m)] * 100)
                    rec.update(irs_hike=round(ph, 3), irs_hold=round(po, 3),
                               irs_cut=round(pc, 3))

    # OIS
    d = last_before(ois, m)
    if d and m >= date(2022, 4, 1):
        res = ft.fit(d, ois[d])
        if res and m in res["nodes"]:
            ph, po, pc = probs_from_delta(
                res["deltas"][res["nodes"].index(m)] * 100)
            rec.update(ois_hike=round(ph, 3), ois_hold=round(po, 3),
                       ois_cut=round(pc, 3))

    if m in bmsi:
        rec.update(bmsi_hike=round(bmsi[m]["hike"], 3),
                   bmsi_hold=round(bmsi[m]["hold"], 3),
                   bmsi_cut=round(bmsi[m]["cut"], 3))
    rows.append(rec)

fields = ["meeting", "outcome", "msb_asof"] + \
    [f"{s}_{k}" for s in ("msb", "irs", "ois", "bmsi")
     for k in ("hike", "hold", "cut")]
with open(OUT / "m5_backtest_meetings.csv", "w", newline="",
          encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)


def brier(sub, src):
    vals = []
    for r in sub:
        if f"{src}_hike" not in r:
            continue
        t = {"hike": 0.0, "hold": 0.0, "cut": 0.0}
        t[r["outcome"]] = 1.0
        vals.append(sum((r[f"{src}_{k}"] - t[k]) ** 2 for k in t))
    return (round(float(np.mean(vals)), 4), len(vals)) if vals else (None, 0)


def clim_brier(sub):
    n = len(sub)
    freq = {k: sum(1 for r in sub if r["outcome"] == k) / n
            for k in ("hike", "hold", "cut")}
    vals = []
    for r in sub:
        t = {"hike": 0.0, "hold": 0.0, "cut": 0.0}
        t[r["outcome"]] = 1.0
        vals.append(sum((freq[k] - t[k]) ** 2 for k in t))
    return round(float(np.mean(vals)), 4)


PERIODS = [
    ("2013-2016 인하기(2.75→1.25)", "2013-01-01", "2016-12-31"),
    ("2017-2019.6 인상기(→1.75)", "2017-01-01", "2019-06-30"),
    ("2019.7-2021.7 인하기(→0.50)", "2019-07-01", "2021-07-31"),
    ("2021.8-2023.1 인상기(→3.50)", "2021-08-01", "2023-01-31"),
    ("2023.2-2024.9 동결기", "2023-02-01", "2024-09-30"),
    ("2024.10-2026.5 인하기(→2.50)", "2024-10-01", "2026-05-31"),
    ("2026 인상기", "2026-06-01", SAMPLE_END.isoformat()),
]

summary = {"phi_bp": {k: round(v * 100, 1) for k, v in PHI.items()},
           "quiet_days": len(quiet), "periods": {}, "overall": {}}
sub_all = [r for r in rows if r["meeting"] >= "2013-02-01"]
for name, a, b in PERIODS:
    sub = [r for r in sub_all if a <= r["meeting"] <= b]
    if not sub:
        continue
    summary["periods"][name] = {
        "n": len(sub),
        "outcomes": {k: sum(1 for r in sub if r["outcome"] == k)
                     for k in ("hike", "hold", "cut")},
        **{f"brier_{s}": brier(sub, s) for s in ("msb", "irs", "ois", "bmsi")},
        "brier_climatology": clim_brier(sub),
    }
summary["overall"] = {
    "n": len(sub_all),
    **{f"brier_{s}": brier(sub_all, s) for s in ("msb", "irs", "ois", "bmsi")},
    "brier_climatology": clim_brier(sub_all),
}
common = [r for r in sub_all if "bmsi_hike" in r and "msb_hike" in r]
summary["head_to_head_bmsi_subset"] = {
    "n": len(common),
    **{f"brier_{s}": brier(common, s) for s in ("msb", "irs", "ois", "bmsi")},
    "brier_climatology": clim_brier(common),
}

EPISODES = ["2021-08-26", "2022-07-13", "2022-10-12", "2024-10-11",
            "2024-11-28", "2025-01-16", "2025-05-29", "2026-05-28",
            "2026-07-16", "2026-08-27"]
epi_rows = [r for r in rows if r["meeting"] in EPISODES]
with open(OUT / "m5_episodes.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(epi_rows)

(OUT / "m5_backtest_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
print("\nEpisodes:")
for r in epi_rows:
    print(" ", r["meeting"], r["outcome"],
          {k: r.get(k) for k in ("msb_hike", "msb_cut", "irs_hike", "irs_cut",
                                 "ois_hike", "ois_cut", "bmsi_hike",
                                 "bmsi_cut") if k in r})
