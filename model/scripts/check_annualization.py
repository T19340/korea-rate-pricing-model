# -*- coding: utf-8 -*-
"""Independent check of the codex audit's central claim.

Claim: OIS fixed legs quote SIMPLE annualized (Act/365) par rates —
    K = (365/D) * [prod(1 + R_i/365) - 1]
while m1's model_rate() uses the effective-annual form
    K_wrong = prod(...)^(365/D) - 1,
flattening the hold path to 2.778% at every tenor and depressing the
front-end implied jumps. If true, refitting today's curve with the correct
convention should (a) move the August delta up sharply, (b) improve RMSE.

This script does NOT touch m1 outputs; it refits 2026-08-07 side by side.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from common import base_rate_history, base_rate_on, load_ois, mpc_meetings, tenor_days
from m1_step_function import Fitter, model_rate, FIT_TENORS, TENOR_W, LAMBDA_SMOOTH, SHRINK_2026, SHRINK_2027


def model_rate_simple(asof, days, r0, nodes, deltas):
    """Correct convention: simple-annualized Act/365 par rate."""
    segments, prev, cur = [], 0, r0
    for b, dlt in sorted(((n - asof).days, dl) for n, dl in zip(nodes, deltas)):
        if b >= days:
            break
        if b > prev:
            segments.append((b - prev, cur))
            prev = b
        cur += dlt
    segments.append((days - prev, cur))
    growth = 1.0
    for n_days, rate in segments:
        growth *= (1 + rate / 100 / 365) ** n_days
    return (growth - 1) * 365 / days * 100


def fit(asof, quotes, nodes, is_ph, r0, pricer):
    tenors = [t for t in FIT_TENORS if t in quotes]
    y = np.array([quotes[t] for t in tenors])
    w = np.array([TENOR_W[t] for t in tenors])
    days = [tenor_days(asof, t) for t in tenors]
    K = len(nodes)

    def price_vec(deltas):
        return np.array([pricer(asof, d_, r0, nodes, deltas) for d_ in days])

    deltas = np.zeros(K)
    D = np.zeros((max(K - 1, 1), K))
    for i in range(K - 1):
        D[i, i], D[i, i + 1] = -1.0, 1.0
    shrink = np.diag(np.where(is_ph, SHRINK_2027, SHRINK_2026))
    for _ in range(8):  # Gauss-Newton with numerical jacobian
        f0 = price_vec(deltas)
        J = np.zeros((len(days), K))
        eps = 1e-4
        for k in range(K):
            dd = deltas.copy()
            dd[k] += eps
            J[:, k] = (price_vec(dd) - f0) / eps
        lhs = J.T @ np.diag(w) @ J + LAMBDA_SMOOTH * D.T @ D + shrink
        rhs = J.T @ np.diag(w) @ (y - f0)
        step = np.linalg.solve(lhs, rhs)
        deltas = deltas + step
        if np.max(np.abs(step)) < 1e-6:
            break
    resid = y - price_vec(deltas)
    rmse = float(np.sqrt(np.mean((resid * w) ** 2)))
    return deltas, rmse, dict(zip(tenors, resid * 100))


ois = load_ois()
ft = Fitter()
asof = max(ois)
quotes = ois[asof]
nodes, is_ph = ft.nodes_for(asof)
r0 = ft.r0_for(asof, quotes)

print(f"asof={asof} r0={r0}")
print("\n평탄 경로(2.740%)의 만기별 모형값 — 관행 대조:")
for t in FIT_TENORS:
    d_ = tenor_days(asof, t)
    wrong = model_rate(asof, d_, r0, nodes, np.zeros(len(nodes)))
    right = model_rate_simple(asof, d_, r0, nodes, np.zeros(len(nodes)))
    print(f"  {t}: 기존(유효연율) {wrong:.4f}%  올바른(단리연율화) {right:.4f}%  차이 {(wrong-right)*100:+.1f}bp")

for name, pricer in [("기존(유효연율)", model_rate), ("교정(단리연율화)", model_rate_simple)]:
    deltas, rmse, resid = fit(asof, quotes, nodes, is_ph, r0, pricer)
    print(f"\n=== {name} 적합 ===  가중 RMSE {rmse*100:.2f}bp")
    cum = 0.0
    for n, dl, ph in zip(nodes, deltas, is_ph):
        tag = " (2027 가정)" if ph else ""
        if n.year == 2026:
            cum += dl
        print(f"  {n}{tag}: {dl*100:+.1f}bp -> P={min(max(dl/0.25,0),1):.0%}")
    print(f"  2026 누적: {cum*100:+.1f}bp -> 연말 내재 {base_rate_on(asof, ft.hist)+cum:.3f}%")
