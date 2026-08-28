# -*- coding: utf-8 -*-
"""Model 3 — DNS-VAR expectation/term-premium decomposition (practical AFNS).

Month-end KTB zero curves (bootstrapped from KOFIA evaluator-average par
yields, 2013-01..latest) are fitted to the three-factor Nelson-Siegel form
with a grid-searched decay lambda. Factor P-dynamics follow a VAR(1); the
model-implied expected short-rate path is E[L+S] with a calibration wedge to
the policy rate. Term premium(tau) = y(tau) - mean expected short rate.

This is the two-step implementation of the AFNS framework the Bank of Korea
uses (MPR 2023.3 box I-2; BOK WP 2024-11): the no-arbitrage yield-adjustment
mainly shifts premium levels, not the near-term expectation path.

Outputs: m3_expected_path.csv, m3_decomposition.csv, m3_factors.csv,
         m3_meta.json (under model/output/)
"""
from __future__ import annotations

import csv
import json
from datetime import date

import numpy as np

from common import OUT, base_rate_history, base_rate_on, kofia_avg

OUT.mkdir(parents=True, exist_ok=True)

TENORS_M = {"ktb_3m": 3, "ktb_6m": 6, "ktb_9m": 9, "ktb_1y": 12, "ktb_2y": 24,
            "ktb_3y": 36, "ktb_5y": 60, "ktb_10y": 120, "ktb_20y": 240,
            "ktb_30y": 360}


def month_end_series(slug: str) -> dict[str, float]:
    daily = kofia_avg(f"{slug}_val_daily")
    by_month: dict[str, tuple[date, float]] = {}
    for d, v in daily.items():
        key = f"{d.year}-{d.month:02d}"
        if key not in by_month or d > by_month[key][0]:
            by_month[key] = (d, v)
    return {k: v for k, (_, v) in sorted(by_month.items())}


def bootstrap_zero(par: dict[int, float]) -> dict[int, float]:
    """Semiannual par bootstrap; tenors < 12m treated as zero rates."""
    zeros: dict[float, float] = {}
    for m in (3, 6, 9):
        if m in par:
            zeros[m / 12] = par[m] / 100
    grid = sorted(t for t in par if t >= 12)
    par_y = {t / 12: par[t] / 100 for t in grid}
    yrs = sorted(par_y)

    def par_at(t: float) -> float:
        if t <= yrs[0]:
            return par_y[yrs[0]]
        for a, b in zip(yrs, yrs[1:]):
            if a <= t <= b:
                return par_y[a] + (par_y[b] - par_y[a]) * (t - a) / (b - a)
        return par_y[yrs[-1]]

    def zero_at(t: float) -> float:
        keys = sorted(zeros)
        if t <= keys[0]:
            return zeros[keys[0]]
        for a, b in zip(keys, keys[1:]):
            if a <= t <= b:
                return zeros[a] + (zeros[b] - zeros[a]) * (t - a) / (b - a)
        return zeros[keys[-1]]

    horizon = max(yrs)
    n_steps = int(round(horizon * 2))
    for i in range(1, n_steps + 1):
        t = i / 2
        if t < 1.0 and t in zeros:
            continue
        c = par_at(t) / 2
        pv_coupons = sum(c / (1 + zero_at(j / 2) / 2) ** j for j in range(1, i))
        z = ((1 + c) / (1 - pv_coupons)) ** (1 / i) * 2 - 2
        zeros[t] = z
    return {m: zeros[min(zeros, key=lambda k: abs(k - m / 12))] * 100
            for m in TENORS_M.values()}


def ns_loadings(lam: float, taus_yr: np.ndarray) -> np.ndarray:
    x = lam * taus_yr
    slope = (1 - np.exp(-x)) / x
    curv = slope - np.exp(-x)
    return np.column_stack([np.ones_like(x), slope, curv])


def run():
    series = {slug: month_end_series(slug) for slug in TENORS_M}
    months = sorted(set.intersection(*(set(s) for s in series.values())))
    curves = {}
    for mkey in months:
        par = {TENORS_M[slug]: series[slug][mkey] for slug in TENORS_M}
        curves[mkey] = bootstrap_zero(par)
    taus = np.array(sorted(TENORS_M.values())) / 12.0
    Y = np.array([[curves[mk][int(t * 12)] for t in taus] for mk in months])

    # lambda grid search on cross-sectional fit
    best = None
    for lam in np.arange(0.15, 1.55, 0.05):
        X = ns_loadings(lam, taus)
        beta, *_ = np.linalg.lstsq(X, Y.T, rcond=None)
        rmse = float(np.sqrt(np.mean((Y.T - X @ beta) ** 2)))
        if best is None or rmse < best[1]:
            best = (lam, rmse, beta.T)
    lam, fit_rmse, F = best
    L, S, C = F[:, 0], F[:, 1], F[:, 2]

    # VAR(1) on factors
    Z = F - F.mean(axis=0)
    A, *_ = np.linalg.lstsq(Z[:-1], Z[1:], rcond=None)
    A = A.T
    eig = np.abs(np.linalg.eigvals(A))
    mu = F.mean(axis=0)

    hist = base_rate_history()
    latest_key = months[-1]
    y_, m_ = map(int, latest_key.split("-"))
    latest_date = date(y_, m_, 28)
    base_now = base_rate_on(latest_date, hist)
    short_now = L[-1] + S[-1]
    wedge = short_now - base_now

    # expected short-rate path, 36 months
    path = []
    f = F[-1].copy()
    for h in range(1, 37):
        f = mu + A @ (f - mu)
        path.append(f[0] + f[1])
    exp_base = [p - wedge for p in path]

    with open(OUT / "m3_expected_path.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["h_months", "expected_short_rate", "expected_base_rate"])
        for h, (p, b) in enumerate(zip(path, exp_base), 1):
            w.writerow([h, round(p, 3), round(b, 3)])

    # decomposition at latest month
    with open(OUT / "m3_decomposition.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["tenor_months", "zero_yield", "avg_expected_short",
                    "term_premium_bp"])
        full = [short_now] + path
        for t_m in sorted(TENORS_M.values()):
            n = max(1, min(t_m, 36))
            avg_exp = float(np.mean(full[:n + 1]))
            yld = curves[latest_key][t_m]
            if t_m <= 36:
                tp = (yld - avg_exp) * 100
            else:
                tp = float("nan")
            w.writerow([t_m, round(yld, 3), round(avg_exp, 3),
                        round(tp, 1) if tp == tp else ""])

    with open(OUT / "m3_factors.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["month", "level", "slope", "curvature", "short_proxy"])
        for mk, l_, s_, c_ in zip(months, L, S, C):
            w.writerow([mk, round(l_, 3), round(s_, 3), round(c_, 3),
                        round(l_ + s_, 3)])

    meta = {
        "lambda_per_year": round(float(lam), 3),
        "cross_section_rmse_bp": round(fit_rmse * 100, 2),
        "sample": [months[0], months[-1]],
        "n_months": len(months),
        "var_eigenvalues_abs": [round(float(e), 3) for e in sorted(eig)[::-1]],
        "short_proxy_now": round(float(short_now), 3),
        "base_rate_now": base_now,
        "wedge_bp": round(float(wedge) * 100, 1),
        "expected_base_2026_12": round(exp_base[3], 3),
        "expected_base_2027_08": round(exp_base[11], 3),
        "expected_base_2028_08": round(exp_base[23], 3),
        "note": "two-step DNS + VAR(1); expectation under P-measure, no "
                "no-arbitrage adjustment; premium for tenor>36m not computed "
                "(needs longer path).",
    }
    (OUT / "m3_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("[m3]", json.dumps(meta, indent=1))


if __name__ == "__main__":
    run()
