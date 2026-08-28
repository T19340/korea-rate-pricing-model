# -*- coding: utf-8 -*-
"""m11 — CD-IRS strip snapshot: the market-convention gauge as lens 6.

Fits the same meeting-dated step function on the CD-IRS zero curve
3M/6M/9M/1Y with a CD91 anchor, exactly as the m5 backtest's `irs` gauge
(weights 1.0/0.9/0.8/0.7, smooth x2, shrink x4). The CD-to-base-rate wedge
is assumed constant over the horizon, so the fitted jumps read as base-rate
jumps. Caveat carried from m5: CD embeds a bank funding spread that is
neither constant nor policy-related in stress periods, and the backtest
Brier (0.377 over 124 meetings) is worse than climatology (0.353) — this
lens is shown for transparency, not adopted as a primary gauge.

Output: m11_irs_snapshot.json
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import numpy as np

from common import (OUT, base_rate_history, base_rate_on, ecos_daily, load_irs,
                    model_config, mpc_meetings)
from m1_step_function import fit_deltas, LAMBDA_SMOOTH, SHRINK_2026, SHRINK_2027

# 리포트 재현용 as-of 고정. 현재 시점을 보려면 환경변수로만 덮어쓴다
# (기본값을 바꾸면 v16 리포트의 수치가 재현되지 않는다).
#   ASOF_CAP=2026-08-24 python m11_irs_snapshot.py
ASOF_CAP = date.fromisoformat(
    os.environ.get("ASOF_CAP", model_config()["irs_snapshot_asof"]))

hist = base_rate_history()
meetings_all = sorted(mpc_meetings())
irs = load_irs()
cd91 = ecos_daily("cd_91d_daily")

asof = max(d for d in irs if d <= ASOF_CAP)
q = irs[asof]
obs = {}
for tn, days_ in [("03M", 91), ("06M", 182), ("09M", 273), ("01Y", 365)]:
    if tn in q:
        obs[days_] = q[tn]
anchor_d = max(d for d in cd91 if d <= asof)
anchor = cd91[anchor_d]
base = base_rate_on(asof, hist)

nodes = [m for m in meetings_all if asof < m <= asof + timedelta(days=370)]
days = sorted(obs)
y = np.array([obs[t] for t in days])
wts_all = {91: 1.0, 182: 0.9, 273: 0.8, 365: 0.7}
w = np.array([wts_all[t] for t in days])
is_ph = np.zeros(len(nodes), dtype=bool)
dl, _, _ = fit_deltas(asof, days, y, w, nodes, is_ph, anchor,
                      smooth=2 * LAMBDA_SMOOTH,
                      shrink26=SHRINK_2026 * 4, shrink27=SHRINK_2027 * 4)

per_meeting = []
cum_ye = 0.0
for m, d_ in zip(nodes, dl):
    bp = d_ * 100
    if m.year == 2026:
        cum_ye += bp
    per_meeting.append({
        "meeting": m.isoformat(), "delta_bp": round(bp, 1),
        "p_hike": round(min(max(bp / 25.0, 0.0), 1.0), 3),
    })

out = {
    "asof": asof.isoformat(),
    "anchor_cd91": anchor, "anchor_date": anchor_d.isoformat(),
    "base_rate": base, "cd_wedge_bp": round((anchor - base) * 100, 1),
    "tenors_pct": {str(k): v for k, v in obs.items()},
    "per_meeting": per_meeting,
    "cum_2026_bp": round(cum_ye, 1),
    "implied_yearend": round(base + cum_ye / 100, 3),
    "hikes_equiv": round(cum_ye / 25.0, 2),
}
with open(OUT / "m11_irs_snapshot.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print("asof", asof, "| CD91 anchor", anchor, f"(wedge {out['cd_wedge_bp']}bp)",
      "| base", base)
print("tenors:", obs)
for r in per_meeting[:6]:
    print(f"  {r['meeting']}  {r['delta_bp']:+6.1f}bp  P(hike)={r['p_hike']:.0%}")
print(f"cum 2026 {out['cum_2026_bp']}bp -> year-end {out['implied_yearend']}%"
      f" ({out['hikes_equiv']} hikes)")
