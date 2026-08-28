# -*- coding: utf-8 -*-
"""Model 9 — how much of the hike path do KTB (국고채) yields price in?

Same meeting-dated step function as the MSB cross-check, applied to the KTB
short-end strip: 3M/6M/9M valuation (민평 5사 평균, 2013~) + 1Y (ECOS daily).
KTB carries its own richness premium (지표물·담보 수요), estimated on the
same quiet windows as the MSB phi and subtracted before fitting.

Outputs: m9_ktb_snapshot.csv, m9_ktb_timeseries.csv (model/output/)
"""
from __future__ import annotations

import csv
from datetime import date, timedelta

import numpy as np

from common import OUT, base_rate_history, base_rate_on, ecos_daily, kofia_avg, mpc_meetings
from m1_step_function import (Fitter, fit_deltas, LAMBDA_SMOOTH, SHRINK_2026,
                              SHRINK_2027, TARGETS_2026)

ktb = {
    91: kofia_avg("ktb_3m_val_daily"),
    182: kofia_avg("ktb_6m_val_daily"),
    273: kofia_avg("ktb_9m_val_daily"),
    365: ecos_daily("ktb_1y_daily"),
}
W = {91: 1.0, 182: 0.9, 273: 0.8, 365: 0.7}
call = ecos_daily("call_overnight_daily")
ft = Fitter()
hist = base_rate_history()
meetings = sorted(mpc_meetings())

# quiet-window premium (same rule as the MSB branch)
msb1y = ecos_daily("msb_1y_daily")
quiet = []
for d_, y1 in msb1y.items():
    if not (2015 <= d_.year <= 2024):
        continue
    b = base_rate_on(d_, hist)
    nxt = next((m for m in meetings if m > d_), None)
    if nxt and abs(base_rate_on(nxt + timedelta(days=3), hist) - b) < 1e-9 \
            and abs(y1 - b) < 0.12:
        quiet.append(d_)


def phi(series):
    sp = sorted(series[d_] - base_rate_on(d_, hist)
                for d_ in quiet if d_ in series)
    return sp[len(sp) // 2] if sp else 0.0


PHI = {d_: phi(s) for d_, s in ktb.items()}
print("[m9] KTB phi (quiet n=%d): " % len(quiet)
      + " ".join(f"{k}d={v*100:.1f}bp" for k, v in PHI.items()))


def anchor_for(asof: date):
    for lag in range(0, 6):
        d_ = asof - timedelta(days=lag)
        if d_ in call:
            return call[d_]
    return None


def fit_day(asof: date):
    obs, wts = {}, {}
    for d_, series in ktb.items():
        if asof in series:
            obs[d_] = series[asof] - PHI[d_]
            wts[d_] = W[d_]
    r0 = anchor_for(asof)
    if r0 is None or len(obs) < 3:
        return None
    nodes, is_ph = ft.nodes_for(asof)
    y = np.array([obs[t] for t in sorted(obs)])
    w = np.array([wts[t] for t in sorted(obs)])
    res = fit_deltas(asof, sorted(obs), y, w, nodes, is_ph, r0,
                     smooth=2 * LAMBDA_SMOOTH,
                     shrink26=SHRINK_2026 * 2, shrink27=SHRINK_2027 * 2)
    if res is None:
        return None
    dl, rmse, _ = res
    return nodes, is_ph, dl, rmse, r0


# snapshot
latest = max(d for d in ktb[91] if d in ktb[182])
res = fit_day(latest)
nodes, is_ph, dl, rmse, r0 = res
base_now = base_rate_on(latest, hist)
with open(OUT / "m9_ktb_snapshot.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["asof", "meeting", "assumed_node", "delta_bp",
                "prob_25bp_hike", "implied_rate_after"])
    cum = base_now
    for n, d_, ph in zip(nodes, dl, is_ph):
        cum += d_
        w.writerow([latest, n, int(ph), round(d_ * 100, 1),
                    round(min(max(d_ / 0.25, 0), 1), 3), round(cum, 3)])
print(f"[m9] snapshot {latest} r0={r0:.3f} rmse={rmse*100:.2f}bp")
ye = base_now + sum(d_ for n, d_, ph in zip(nodes, dl, is_ph)
                    if not ph and n.year == 2026)
for n, d_, ph in zip(nodes, dl, is_ph):
    tag = " (2027 가정)" if ph else ""
    print(f"     {n}{tag}: {d_*100:+.1f}bp -> P={min(max(d_/0.25,0),1):.0%}")
print(f"[m9] 연말 내재 {ye:.3f}%")

# recent time series
rows = []
for asof in sorted(d for d in ktb[91] if d >= date(2026, 5, 1)):
    r = fit_day(asof)
    if r is None:
        continue
    nds, fls, d_, _, _ = r
    row = {"date": asof.isoformat()}
    ye_c = base_rate_on(asof, hist) + sum(
        x for n, x, ph in zip(nds, d_, fls) if not ph and n.year == 2026)
    row["implied_ye_rate"] = round(ye_c, 3)
    for tgt in TARGETS_2026:
        if tgt in nds:
            row[f"prob_{tgt.strftime('%m%d')}"] = round(
                min(max(d_[nds.index(tgt)] / 0.25, 0), 1), 3)
    rows.append(row)
fields = sorted({k for r in rows for k in r}, key=lambda k: (k != "date", k))
with open(OUT / "m9_ktb_timeseries.csv", "w", newline="", encoding="utf-8-sig") as f:
    wtr = csv.DictWriter(f, fieldnames=fields)
    wtr.writeheader()
    wtr.writerows(rows)
print(f"[m9] timeseries rows: {len(rows)}; latest: {rows[-1]}")
