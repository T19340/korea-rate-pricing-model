# -*- coding: utf-8 -*-
"""Out-of-sample validation of the shock framework in section 04.

The claim being tested: predicted meeting-day move at maturity tau
    = beta(tau) x model_surprise,
    model_surprise = actual decision (bp) - day-before implied delta (bp).

Design (no look-ahead):
  * betas estimated ONLY on 2011-2019 meeting days (Kuttner regression,
    surprise proxy = MSB 91d day change, active days |s|>=1bp);
  * the day-before implied delta comes from the MSB-strip step function
    (same machinery as the m5 backtest, uncapped delta);
  * validation sample: scheduled meetings 2020-01..2026-07 (2020-03-16
    emergency meeting excluded), realized moves = day changes on decision day.

Outputs: m7_validation_meetings.csv, m7_validation_summary.json
"""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta

import numpy as np

from common import OUT, base_rate_history, base_rate_on, ecos_daily, kofia_avg, mpc_meetings
from m1_step_function import fit_deltas, LAMBDA_SMOOTH, SHRINK_2026, SHRINK_2027

EXCLUDE = {date(2020, 3, 16)}
hist = base_rate_history()
meetings_all = sorted(m for m in mpc_meetings() if m not in EXCLUDE)

msb91 = ecos_daily("msb_91d_daily")
msb6m = kofia_avg("msb_6m_val_daily")
msb1y = ecos_daily("msb_1y_daily")
call = ecos_daily("call_overnight_daily")
ktb2 = dict(kofia_avg("ktb_2y_val_daily"))
ktb2.update(ecos_daily("ktb_2y_daily"))
MATS = [("msb91", msb91, "통안 3개월"), ("msb6m", msb6m, "통안 6개월"),
        ("msb1y", msb1y, "통안 1년"), ("ktb2", ktb2, "국고 2년"),
        ("ktb3", ecos_daily("ktb_3y_daily"), "국고 3년"),
        ("ktb5", ecos_daily("ktb_5y_daily"), "국고 5년"),
        ("ktb10", ecos_daily("ktb_10y_daily"), "국고 10년"),
        ("ktb20", ecos_daily("ktb_20y_daily"), "국고 20년"),
        ("ktb30", ecos_daily("ktb_30y_daily"), "국고 30년")]


def day_change(series, d):
    prev = None
    for lag in range(1, 6):
        if (d - timedelta(days=lag)) in series:
            prev = d - timedelta(days=lag)
            break
    if prev is None or d not in series:
        return None
    return (series[d] - series[prev]) * 100


def outcome_bp(m):
    return round((base_rate_on(m + timedelta(days=3), hist)
                  - base_rate_on(m - timedelta(days=1), hist)) * 100)


# ---- 1) betas on the PRE sample only (2011-2019)
pre_meetings = [m for m in meetings_all
                if date(2011, 1, 1) <= m <= date(2019, 12, 31)]
pre_events = [(m, day_change(msb91, m)) for m in pre_meetings]
pre_events = [(m, s) for m, s in pre_events if s is not None and abs(s) >= 1.0]
betas = {}
for key, series, name in MATS:
    pairs = [(s, day_change(series, m)) for m, s in pre_events]
    pairs = [(x, y) for x, y in pairs if y is not None]
    if len(pairs) < 10:
        continue
    x = np.array([p[0] for p in pairs])
    y = np.array([p[1] for p in pairs])
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    betas[key] = round(float(coef[1]), 3)
print("[m7] pre-2020 betas (n_events=%d):" % len(pre_events), betas)


# ---- 2) day-before implied delta from the MSB strip
def implied_delta(m):
    d = None
    for lag in range(1, 8):
        if (m - timedelta(days=lag)) in msb91:
            d = m - timedelta(days=lag)
            break
    if d is None or d not in call:
        return None
    PHI = {"91": 0.008, "6m": 0.011, "1y": 0.039}
    obs = {91: msb91[d] - PHI["91"]}
    wts = {91: 1.0}
    if d in msb6m:
        obs[182] = msb6m[d] - PHI["6m"]; wts[182] = 0.9
    if d in msb1y:
        obs[365] = msb1y[d] - PHI["1y"]; wts[365] = 0.7
    if len(obs) < 2:
        return None
    nodes = [x for x in meetings_all if d < x <= d + timedelta(days=370)]
    if m not in nodes:
        return None
    y = np.array([obs[t] for t in sorted(obs)])
    w = np.array([wts[t] for t in sorted(obs)])
    days = sorted(obs)
    is_ph = np.zeros(len(nodes), dtype=bool)
    res = fit_deltas(d, days, y, w, nodes, is_ph, call[d],
                     smooth=2 * LAMBDA_SMOOTH,
                     shrink26=SHRINK_2026 * 4, shrink27=SHRINK_2027 * 4)
    if res is None:
        return None
    dl, _, _ = res
    return dl[nodes.index(m)] * 100


# ---- 3) validation loop 2020-2026
rows = []
for m in meetings_all:
    if not (date(2020, 1, 1) <= m <= date(2026, 7, 31)):
        continue
    delta = implied_delta(m)
    if delta is None:
        continue
    actual = outcome_bp(m)
    surprise = actual - delta
    rec = {"meeting": m.isoformat(), "actual_bp": actual,
           "implied_delta_bp": round(delta, 1),
           "model_surprise_bp": round(surprise, 1)}
    for key, series, _ in MATS:
        realized = day_change(series, m)
        if realized is None or key not in betas:
            continue
        rec[f"pred_{key}"] = round(betas[key] * surprise, 1)
        rec[f"real_{key}"] = round(realized, 1)
    rows.append(rec)

fields = ["meeting", "actual_bp", "implied_delta_bp", "model_surprise_bp"] + \
    [f"{p}_{k}" for k, _, _ in MATS for p in ("pred", "real")]
with open(OUT / "m7_validation_meetings.csv", "w", newline="",
          encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)

summary = {"pre_beta_sample_events": len(pre_events),
           "betas_pre2020": betas, "n_validation": len(rows), "stats": {}}
for key, _, name in MATS:
    pairs = [(r[f"pred_{key}"], r[f"real_{key}"]) for r in rows
             if f"pred_{key}" in r and f"real_{key}" in r]
    if len(pairs) < 8:
        continue
    p = np.array([a for a, _ in pairs])
    q = np.array([b for _, b in pairs])
    corr = float(np.corrcoef(p, q)[0, 1])
    rmse_model = float(np.sqrt(np.mean((p - q) ** 2)))
    rmse_zero = float(np.sqrt(np.mean(q ** 2)))
    big = [(a, b) for (a, b), r in zip(pairs, rows)
           if abs(r["model_surprise_bp"]) >= 3.0]
    sign_hit = (sum(1 for a, b in big if a * b > 0) / len(big)) if big else None
    summary["stats"][name] = {
        "n": len(pairs), "corr": round(corr, 2),
        "rmse_model_bp": round(rmse_model, 1),
        "rmse_zero_bp": round(rmse_zero, 1),
        "sign_hit_surprise_ge3bp": round(sign_hit, 2) if sign_hit else None,
        "n_big": len(big),
    }

EPISODES = ["2024-10-11", "2024-11-28", "2025-01-16", "2025-05-29",
            "2026-07-16"]
summary["episodes"] = [
    {k: r[k] for k in r if k in ("meeting", "actual_bp", "implied_delta_bp",
                                 "model_surprise_bp", "pred_msb91",
                                 "real_msb91", "pred_msb1y", "real_msb1y",
                                 "pred_ktb3", "real_ktb3", "pred_ktb10",
                                 "real_ktb10")}
    for r in rows if r["meeting"] in EPISODES]

(OUT / "m7_validation_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
