# -*- coding: utf-8 -*-
"""Regime-stratified re-run of the pooled validation statistics.

The pooled numbers in m7 (corr over 53 meetings) and m4 (betas over 2011-2026)
average across regimes. This script splits everything by cycle:

  (a) shock-validation stats (corr / sign-hit / RMSE) per regime per maturity;
  (b) event-study betas per regime;
  (c) direction detection at turning points, hikes vs cuts separately.

Outputs: m8_regime_validation.csv, m8_regime_betas.csv, m8_summary.json
"""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta

import numpy as np

from common import OUT, base_rate_history, base_rate_on, ecos_daily, kofia_avg, mpc_meetings

hist = base_rate_history()
meetings_all = sorted(m for m in mpc_meetings() if m != date(2020, 3, 16))

REGIMES = [
    ("2020.1~2021.7 완화·동결", date(2020, 1, 1), date(2021, 7, 31)),
    ("2021.8~2023.1 급속 인상", date(2021, 8, 1), date(2023, 1, 31)),
    ("2023.2~2024.9 동결", date(2023, 2, 1), date(2024, 9, 30)),
    ("2024.10~2026.5 인하", date(2024, 10, 1), date(2026, 5, 31)),
    ("2026.6~ 인상 재개", date(2026, 6, 1), date(2026, 12, 31)),
]
BETA_REGIMES = [
    ("2011~2019", date(2011, 1, 1), date(2019, 12, 31)),
    ("2020.1~2021.7", date(2020, 1, 1), date(2021, 7, 31)),
    ("2021.8~2023.1", date(2021, 8, 1), date(2023, 1, 31)),
    ("2023.2~2024.9", date(2023, 2, 1), date(2024, 9, 30)),
    ("2024.10~2026.7", date(2024, 10, 1), date(2026, 7, 31)),
]

msb91 = ecos_daily("msb_91d_daily")
series_map = {
    "msb91": (msb91, "통안 3개월"),
    "msb1y": (ecos_daily("msb_1y_daily"), "통안 1년"),
    "ktb3": (ecos_daily("ktb_3y_daily"), "국고 3년"),
    "ktb10": (ecos_daily("ktb_10y_daily"), "국고 10년"),
}


def day_change(series, d):
    for lag in range(1, 6):
        if (d - timedelta(days=lag)) in series:
            prev = d - timedelta(days=lag)
            break
    else:
        return None
    if d not in series:
        return None
    return (series[d] - series[prev]) * 100


def regime_of(d, regimes):
    for name, a, b in regimes:
        if a <= d <= b:
            return name
    return None


# ---------- (a) shock validation by regime (reuse m7 output)
val = list(csv.DictReader(open(OUT / "m7_validation_meetings.csv",
                               encoding="utf-8-sig")))
rows_out = []
for reg_name, a, b in REGIMES:
    sub = [r for r in val if a <= date.fromisoformat(r["meeting"]) <= b]
    for key, (_, label) in series_map.items():
        pairs = [(float(r[f"pred_{key}"]), float(r[f"real_{key}"]),
                  float(r["model_surprise_bp"]))
                 for r in sub if r.get(f"pred_{key}") and r.get(f"real_{key}")]
        if len(pairs) < 5:
            continue
        p = np.array([x[0] for x in pairs])
        q = np.array([x[1] for x in pairs])
        corr = float(np.corrcoef(p, q)[0, 1]) if len(pairs) > 2 else np.nan
        big = [(x, y) for x, y, s in pairs if abs(s) >= 3]
        sign = (sum(1 for x, y in big if x * y > 0) / len(big)) if big else None
        rows_out.append({
            "regime": reg_name, "maturity": label, "n": len(pairs),
            "corr": round(corr, 2),
            "sign_hit": round(sign, 2) if sign is not None else "",
            "n_big": len(big),
            "rmse_model_bp": round(float(np.sqrt(np.mean((p - q) ** 2))), 1),
            "rmse_zero_bp": round(float(np.sqrt(np.mean(q ** 2))), 1),
        })
with open(OUT / "m8_regime_validation.csv", "w", newline="",
          encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
    w.writeheader()
    w.writerows(rows_out)

# ---------- (b) event-study betas by regime
beta_rows = []
for reg_name, a, b in BETA_REGIMES:
    ms = [m for m in meetings_all if a <= m <= b]
    events = [(m, day_change(msb91, m)) for m in ms]
    events = [(m, s) for m, s in events if s is not None and abs(s) >= 1.0]
    for key, (series, label) in series_map.items():
        if key == "msb91":
            continue
        pairs = [(s, day_change(series, m)) for m, s in events]
        pairs = [(x, y) for x, y in pairs if y is not None]
        if len(pairs) < 6:
            continue
        x = np.array([p[0] for p in pairs])
        y = np.array([p[1] for p in pairs])
        X = np.column_stack([np.ones_like(x), x])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ coef
        se = float(np.sqrt(np.sum(resid ** 2) / max(len(x) - 2, 1)
                           / np.sum((x - x.mean()) ** 2)))
        beta_rows.append({"regime": reg_name, "maturity": label,
                          "beta": round(float(coef[1]), 2),
                          "se": round(se, 2), "n_events": len(pairs)})
with open(OUT / "m8_regime_betas.csv", "w", newline="",
          encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(beta_rows[0].keys()))
    w.writeheader()
    w.writerows(beta_rows)

# ---------- (c) turning-point direction detection, hikes vs cuts
bt = list(csv.DictReader(open(OUT / "m5_backtest_meetings.csv",
                              encoding="utf-8-sig")))


def turn_stats(direction):
    """First change of a cycle (direction differs from previous change)."""
    changes = []
    prev_dir = None
    for r in bt:
        if r["outcome"] == "hold":
            continue
        is_turn = (r["outcome"] != prev_dir)
        prev_dir = r["outcome"]
        if r["outcome"] == direction and is_turn and r["meeting"] >= "2013-02-01":
            changes.append(r)
    out = []
    for r in changes:
        rec = {"meeting": r["meeting"]}
        for src in ("msb", "bmsi"):
            v = r.get(f"{src}_{direction}")
            rec[src] = round(float(v), 2) if v not in ("", None) else None
        out.append(rec)
    return out


summary = {
    "turning_points": {"hike_turns": turn_stats("hike"),
                       "cut_turns": turn_stats("cut")},
    "note": "corr on n<15 has s.e. ~0.25-0.5; treat regime rows as direction, "
            "not precision.",
}
(OUT / "m8_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

print("=== (a) 국면별 충격 검증 ===")
for r in rows_out:
    print(f"  {r['regime']} | {r['maturity']}: n={r['n']} corr={r['corr']} "
          f"sign={r['sign_hit']} rmse {r['rmse_model_bp']} vs zero {r['rmse_zero_bp']}")
print("\n=== (b) 국면별 베타 ===")
for r in beta_rows:
    print(f"  {r['regime']} | {r['maturity']}: beta={r['beta']} (se {r['se']}, "
          f"n={r['n_events']})")
print("\n=== (c) 전환점 방향 감지 ===")
print(json.dumps(summary["turning_points"], ensure_ascii=False, indent=1))
