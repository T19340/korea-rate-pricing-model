# -*- coding: utf-8 -*-
"""Model 4 — what an August hike would do to the curve.

Two complementary answers:
(a) Empirical: Kuttner-style event study. On each MPC decision day the change
    in the MSB 91d yield proxies the policy surprise; yield changes at longer
    maturities regressed on that surprise give per-maturity pass-through betas.
(b) Structural: KIRI(태현욱 외 2019)-style DNS factor propagation. A policy
    shock is a short-end shock; mapped into the slope factor it propagates to
    maturity tau with loading (1-exp(-lam*tau))/(lam*tau), using the lambda
    estimated in model 3.

Scenario table: surprise on 2026-08-27 = (1 - P_Aug) * 25bp for a hike,
-P_Aug * 25bp for a hold, with P_Aug taken from model 1.

Outputs: m4_betas.csv, m4_scenarios.csv (under model/output/)
"""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta

import numpy as np

from common import OUT, base_rate_history, base_rate_on, ecos_daily, kofia_avg, mpc_meetings

MATURITIES = [
    ("msb_91d", "통안 3개월", 0.25, "ecos"),
    ("msb_6m", "통안 6개월", 0.5, "kofia"),
    ("msb_1y", "통안 1년", 1.0, "ecos"),
    ("ktb_2y", "국고 2년", 2.0, "kofia2y"),
    ("ktb_3y", "국고 3년", 3.0, "ecos_ktb"),
    ("ktb_5y", "국고 5년", 5.0, "ecos_ktb"),
    ("ktb_10y", "국고 10년", 10.0, "ecos_ktb"),
    ("ktb_20y", "국고 20년", 20.0, "ecos_ktb"),
    ("ktb_30y", "국고 30년", 30.0, "ecos_ktb"),
]


def load_series():
    out = {}
    for slug, _, _, kind in MATURITIES:
        if kind == "ecos":
            out[slug] = ecos_daily(f"{slug}_daily")
        elif kind == "ecos_ktb":
            out[slug] = ecos_daily(f"{slug}_daily")
        elif kind == "kofia":
            out[slug] = kofia_avg("msb_6m_val_daily")
        elif kind == "kofia2y":
            merged = dict(kofia_avg("ktb_2y_val_daily"))
            merged.update(ecos_daily("ktb_2y_daily"))
            out[slug] = merged
    return out


def day_change(series: dict[date, float], d: date) -> float | None:
    prev = None
    for lag in range(1, 6):
        p = d - timedelta(days=lag)
        if p in series:
            prev = p
            break
    if prev is None or d not in series:
        return None
    return (series[d] - series[prev]) * 100  # bp


def run():
    series = load_series()
    # 상한을 date(2026, 8, 1)로 박아두면 이후 회의가 영영 표본에 안 들어온다.
    sample_end = max(series["msb_91d"]) if series.get("msb_91d") else date.today()
    meetings = [m for m in mpc_meetings() if date(2011, 1, 1) <= m <= sample_end]
    hist = base_rate_history()

    # surprise proxy per meeting: MSB 91d change on decision day
    events = []
    for m in meetings:
        s = day_change(series["msb_91d"], m)
        if s is None:
            continue
        b_before = base_rate_on(m - timedelta(days=1), hist)
        b_after = base_rate_on(m + timedelta(days=2), hist)
        events.append({"meeting": m, "surprise_bp": s,
                       "decision_bp": round((b_after - b_before) * 100)})

    # betas
    beta_rows = []
    surprises = np.array([e["surprise_bp"] for e in events])
    active = np.abs(surprises) >= 1.0  # information-bearing days
    for slug, name, tau, _ in MATURITIES:
        pairs = []
        for e, act in zip(events, active):
            if not act:
                continue
            dy = day_change(series[slug], e["meeting"])
            if dy is not None:
                pairs.append((e["surprise_bp"], dy))
        if len(pairs) < 10:
            continue
        x = np.array([p[0] for p in pairs])
        y = np.array([p[1] for p in pairs])
        X = np.column_stack([np.ones_like(x), x])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ coef
        se = float(np.sqrt(np.sum(resid ** 2) / (len(x) - 2)
                           / np.sum((x - x.mean()) ** 2)))
        r2 = 1 - float(np.sum(resid ** 2) / np.sum((y - y.mean()) ** 2))
        beta_rows.append({"slug": slug, "name": name, "tau_yr": tau,
                          "beta": round(float(coef[1]), 3),
                          "se": round(se, 3), "r2": round(r2, 3),
                          "n": len(pairs)})

    with open(OUT / "m4_betas.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(beta_rows[0].keys()))
        w.writeheader()
        w.writerows(beta_rows)
    print(f"[m4] events={len(events)} active(|s|>=1bp)={int(active.sum())}")
    for r in beta_rows:
        print(f"     {r['name']}: beta={r['beta']} (se {r['se']}, R2 {r['r2']}, n {r['n']})")

    # KIRI-style DNS slope-shock propagation with model-3 lambda
    lam = json.loads((OUT / "m3_meta.json").read_text(encoding="utf-8"))["lambda_per_year"]

    def slope_loading(tau):
        x = lam * tau
        return (1 - np.exp(-x)) / x

    ref = slope_loading(0.25)  # normalize so the 3m point moves 1:1

    # scenario: P(next scheduled meeting) from model 1 snapshot.
    # 2026-08-27 was hardcoded here; the row vanished from the snapshot the day
    # that meeting was held (nodes are future meetings only), so the run died
    # with StopIteration. Take the first non-assumed node instead - that is the
    # next real meeting, whichever one it happens to be.
    with open(OUT / "m1_snapshot.csv", encoding="utf-8-sig") as f:
        snap = list(csv.DictReader(f))
    nxt = next(r for r in snap if str(r["assumed_node"]).strip() in ("0", "False", ""))
    p_aug = float(nxt["prob_25bp_hike"])
    next_meeting = nxt["meeting"]
    surprise_hike = (1 - p_aug) * 25.0
    surprise_hold = -p_aug * 25.0

    with open(OUT / "m4_scenarios.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["maturity", "tau_yr", "beta_empirical",
                    "dns_slope_loading_norm",
                    "hike_move_bp_empirical", "hike_move_bp_dns",
                    "hold_move_bp_empirical", "hold_move_bp_dns"])
        for r in beta_rows:
            tau = r["tau_yr"]
            dns_l = slope_loading(tau) / ref
            w.writerow([r["name"], tau, r["beta"], round(float(dns_l), 3),
                        round(r["beta"] * surprise_hike, 1),
                        round(float(dns_l) * surprise_hike, 1),
                        round(r["beta"] * surprise_hold, 1),
                        round(float(dns_l) * surprise_hold, 1)])
    print(f"[m4] P({next_meeting})={p_aug:.0%} -> hike surprise {surprise_hike:.1f}bp, "
          f"hold surprise {surprise_hold:.1f}bp")

    with open(OUT / "m4_events.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["meeting", "surprise_bp", "decision_bp"])
        w.writeheader()
        for e in events:
            w.writerow({"meeting": e["meeting"].isoformat(),
                        "surprise_bp": round(e["surprise_bp"], 1),
                        "decision_bp": e["decision_bp"]})


if __name__ == "__main__":
    run()
