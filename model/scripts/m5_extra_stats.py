# -*- coding: utf-8 -*-
"""Follow-up stats: per-period table, OIS valid-sample split, direction hits."""
import csv
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "output"
rows = list(csv.DictReader(open(OUT / "m5_backtest_meetings.csv",
                                encoding="utf-8-sig")))
for r in rows:
    for k in list(r):
        if k not in ("meeting", "outcome", "msb_asof") and r[k]:
            r[k] = float(r[k])

summary = json.loads((OUT / "m5_backtest_summary.json").read_text("utf-8"))
print("=== per-period Brier (msb / irs / ois / bmsi / clim) ===")
for name, p in summary["periods"].items():
    def fmt(x):
        return "-" if not p.get(x) or p[x][0] is None else f"{p[x][0]:.3f}({p[x][1]})"
    print(f"{name}: n={p['n']} {p['outcomes']} | msb {fmt('brier_msb')} "
          f"irs {fmt('brier_irs')} ois {fmt('brier_ois')} "
          f"bmsi {fmt('brier_bmsi')} clim {p['brier_climatology']:.3f}")


def brier(sub, src):
    vals = []
    for r in sub:
        if not r.get(f"{src}_hike") and r.get(f"{src}_hike") != 0.0:
            continue
        t = {"hike": 0.0, "hold": 0.0, "cut": 0.0}
        t[r["outcome"]] = 1.0
        vals.append(sum((r[f"{src}_{k}"] - t[k]) ** 2 for k in t))
    return (round(float(np.mean(vals)), 3), len(vals)) if vals else (None, 0)


late = [r for r in rows if r["meeting"] >= "2024-10-01"]
print("\n=== 2024-10 이후 (OIS 실질 유효표본) ===")
for s in ("msb", "irs", "ois", "bmsi"):
    print(f"  {s}: {brier(late, s)}")
n = len(late)
freq = {k: sum(1 for r in late if r['outcome'] == k) / n
        for k in ('hike', 'hold', 'cut')}
clim = np.mean([sum((freq[k] - (1.0 if r['outcome'] == k else 0.0)) ** 2
                    for k in freq) for r in late])
print(f"  clim: {clim:.3f} (n={n})")

print("\n=== 방향 감지: 변경 회의에서 올바른 방향에 부여한 확률 ===")
changes = [r for r in rows if r["outcome"] != "hold"
           and r["meeting"] >= "2013-02-01"]
for s in ("msb", "bmsi"):
    ps = [r[f"{s}_{r['outcome']}"] for r in changes
          if isinstance(r.get(f"{s}_hike"), float)]
    det = [p >= 0.5 for p in ps]
    print(f"  {s}: 변경 {len(ps)}회 중 P(정답)>=50%: {sum(det)}회 "
          f"({sum(det)/len(ps):.0%}), 평균 P(정답)={np.mean(ps):.2f}")

print("\n=== 시장이 서베이보다 먼저 안 회의 (msb 정답확률 - bmsi 정답확률 > 0.2) ===")
for r in changes:
    if isinstance(r.get("msb_hike"), float) and isinstance(r.get("bmsi_hike"), float):
        diff = r[f"msb_{r['outcome']}"] - r[f"bmsi_{r['outcome']}"]
        if diff > 0.2:
            print(f"  {r['meeting']} {r['outcome']}: msb {r['msb_'+r['outcome']]:.2f} "
                  f"vs bmsi {r['bmsi_'+r['outcome']]:.2f}")
