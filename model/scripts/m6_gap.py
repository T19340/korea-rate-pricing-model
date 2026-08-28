# -*- coding: utf-8 -*-
"""Question 1 — why is the MSB strip more dovish than KOFR OIS?

Decomposes the OIS-vs-MSB gap at matched tenors (6M, 1Y) into
(a) instrument own-basis (OIS 1W vs KOFR vs call vs base rate),
(b) a level gap vs its own quiet-period norm (collateral/demand premium),
(c) mark-lag dynamics: does the gap jump on hawkish event days (5/28, 7/16)
    and then decay as evaluator marks catch up with broker quotes?

Output: m6_gap_daily.csv, m6_gap_summary.json (model/output/)
"""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta

import numpy as np

from common import OUT, base_rate_history, base_rate_on, ecos_daily, kofia_avg, kofr_daily, load_ois

hist = base_rate_history()
ois = load_ois()
msb6m = kofia_avg("msb_6m_val_daily")
msb1y = ecos_daily("msb_1y_daily")
msb91 = ecos_daily("msb_91d_daily")
call = ecos_daily("call_overnight_daily")
kofr = kofr_daily()

rows = []
for d in sorted(ois):
    if d < date(2022, 4, 1):
        continue
    q = ois[d]
    r = {"date": d.isoformat()}
    if "6개월" in q and d in msb6m:
        r["gap_6m_bp"] = round((q["6개월"] - msb6m[d]) * 100, 1)
    if "1년" in q and d in msb1y:
        r["gap_1y_bp"] = round((q["1년"] - msb1y[d]) * 100, 1)
    if "3개월" in q and d in msb91:
        r["gap_3m_bp"] = round((q["3개월"] - msb91[d]) * 100, 1)
    if "1주" in q and d in kofr:
        r["ois1w_minus_kofr_bp"] = round((q["1주"] - kofr[d]) * 100, 1)
    if d in call:
        r["call_minus_base_bp"] = round((call[d] - base_rate_on(d, hist)) * 100, 1)
    rows.append(r)

with open(OUT / "m6_gap_daily.csv", "w", newline="", encoding="utf-8-sig") as f:
    fields = ["date", "gap_3m_bp", "gap_6m_bp", "gap_1y_bp",
              "ois1w_minus_kofr_bp", "call_minus_base_bp"]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)


def stats(key, since=None, until=None):
    vals = [r[key] for r in rows if key in r
            and (since is None or r["date"] >= since)
            and (until is None or r["date"] <= until)]
    if not vals:
        return None
    return {"n": len(vals), "median": round(float(np.median(vals)), 1),
            "mean": round(float(np.mean(vals)), 1),
            "last": vals[-1]}


def around(key, day, before=5, after=15):
    d0 = date.fromisoformat(day)
    pre = [r[key] for r in rows if key in r
           and (d0 - timedelta(days=before)).isoformat() <= r["date"] < day]
    post = []
    for k in range(1, after + 1):
        dk = (d0 + timedelta(days=k)).isoformat()
        v = next((r[key] for r in rows if r["date"] == dk and key in r), None)
        if v is not None:
            post.append((dk, v))
    return {"pre_mean": round(float(np.mean(pre)), 1) if pre else None,
            "post": post[:8]}


summary = {
    "note": "gap = OIS(MID) - MSB(민평/최종호가), bp. 양수 = 통안이 OIS보다 강세(저금리).",
    "full_2022_04": {k: stats(k) for k in ["gap_3m_bp", "gap_6m_bp", "gap_1y_bp"]},
    "calm_2023H2_2024H1": {k: stats(k, "2023-07-01", "2024-06-30")
                           for k in ["gap_6m_bp", "gap_1y_bp"]},
    "pre_hawk_2026H1": {k: stats(k, "2026-01-01", "2026-05-27")
                        for k in ["gap_6m_bp", "gap_1y_bp"]},
    "since_hawkish_hold": {k: stats(k, "2026-05-28")
                           for k in ["gap_3m_bp", "gap_6m_bp", "gap_1y_bp"]},
    "own_basis_recent20d": {
        "ois1w_minus_kofr_bp": stats("ois1w_minus_kofr_bp", "2026-07-07"),
        "call_minus_base_bp": stats("call_minus_base_bp", "2026-07-07"),
    },
    "event_527_hawkish_hold": {k: around(k, "2026-05-28")
                               for k in ["gap_6m_bp", "gap_1y_bp"]},
    "event_716_hike": {k: around(k, "2026-07-16")
                       for k in ["gap_6m_bp", "gap_1y_bp"]},
}
(OUT / "m6_gap_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
