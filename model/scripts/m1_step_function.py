# -*- coding: utf-8 -*-
"""Model 1 — meeting-dated step function fitted to the KOFR OIS curve.

Path: r(s) = r0 + sum_k delta_k * 1{s >= meeting_k}. The starting level r0 is
calibrated from the 1-week OIS quote (no meeting sits inside a 1-week window
on normal days), which absorbs the OIS-KOFR basis. Jumps delta_k are found by
weighted least squares on MID quotes (1M..1Y) with (a) a smoothness penalty
across adjacent meetings and (b) mild shrinkage, stronger on the assumed 2027
placeholder nodes. P_k = delta_k / 25bp, clipped to [0, 1].

Outputs: m1_snapshot.csv, m1_fit_detail.csv, m1_timeseries.csv,
         m1_msb_crosscheck.csv  (all under model/output/)
"""
from __future__ import annotations

import csv
import math
from datetime import date, timedelta

import numpy as np

from common import (ASSUMED_FUTURE_NODES, OUT, base_rate_history, base_rate_on,
                    ecos_daily, kofia_avg, kofr_daily, load_ois, mpc_meetings,
                    target_meetings, tenor_days)

OUT.mkdir(parents=True, exist_ok=True)

# 대상 연도의 회의는 캘린더에서 읽는다(config/model.json 의 target_year).
TARGETS = target_meetings()
TARGETS_2026 = TARGETS          # 이전 이름 유지(호환)
FIT_TENORS = ["1개월", "2개월", "3개월", "6개월", "9개월", "1년"]
TENOR_W = {"1개월": 1.0, "2개월": 1.0, "3개월": 1.0, "6개월": 0.9,
           "9개월": 0.8, "1년": 0.7}
LAMBDA_SMOOTH = 2.0e-3
SHRINK_2026 = 2.0e-4
SHRINK_2027 = 1.0e-3
STEP = 0.25  # 25bp


def model_rate(asof: date, days: int, r0: float, nodes: list[date],
               deltas: np.ndarray) -> float:
    """Par fixed rate of a single-payment OIS over `days`.

    Convention (KRX KOFR OIS spec): floating leg compounds daily; the quoted
    fixed rate is SIMPLE-annualized Act/365 —
        K = (365/D) * [prod(1 + r_i/365) - 1].
    v7 fix: the earlier effective-annual form ((prod)^(365/D)-1) flattened the
    hold path to one value at every tenor and biased front-end jumps down.
    """
    segments, prev, cur = [], 0, r0
    for b, dlt in sorted(((n - asof).days, dl) for n, dl in zip(nodes, deltas)):
        if b >= days:
            break
        if b > prev:
            segments.append((b - prev, cur))
            prev = b
        cur += dlt
    segments.append((days - prev, cur))
    lg = sum(n * math.log(1 + r / 100 / 365) for n, r in segments)
    return (math.exp(lg) - 1) * 365 / days * 100


def jac_row(asof: date, days: int, nodes: list[date]) -> np.ndarray:
    out = np.zeros(len(nodes))
    for k, n in enumerate(nodes):
        b = (n - asof).days
        if b < days:
            out[k] = max(0.0, (days - max(b, 0)) / days)
    return out


def fit_deltas(asof: date, obs_days: list[int], obs_vals: np.ndarray,
               weights: np.ndarray, nodes: list[date], is_ph: np.ndarray,
               r0: float, smooth: float = None, shrink26: float = None,
               shrink27: float = None):
    """Shared Gauss-Newton fit: full nonlinear repricing of every jump path.

    Returns (deltas, weighted_rmse_pct, fitted_values). Used by the headline
    fitter, the MSB/KTB cross-checks, and the m5/m7 backtests so every result
    rests on the same (corrected) pricing engine.
    """
    smooth = LAMBDA_SMOOTH if smooth is None else smooth
    shrink26 = SHRINK_2026 if shrink26 is None else shrink26
    shrink27 = SHRINK_2027 if shrink27 is None else shrink27
    K = len(nodes)
    D = np.zeros((max(K - 1, 1), K))
    for i in range(K - 1):
        D[i, i], D[i, i + 1] = -1.0, 1.0
    shrink = np.diag(np.where(is_ph, shrink27, shrink26))
    W = np.diag(weights)

    def price_vec(dl):
        return np.array([model_rate(asof, d_, r0, nodes, dl)
                         for d_ in obs_days])

    deltas = np.zeros(K)
    eps = 1e-4
    for _ in range(8):
        f0 = price_vec(deltas)
        J = np.zeros((len(obs_days), K))
        for k in range(K):
            dd = deltas.copy()
            dd[k] += eps
            J[:, k] = (price_vec(dd) - f0) / eps
        lhs = J.T @ W @ J + smooth * D.T @ D + shrink
        rhs = J.T @ W @ (obs_vals - f0)
        try:
            step = np.linalg.solve(lhs, rhs)
        except np.linalg.LinAlgError:
            return None
        deltas = deltas + step
        if np.max(np.abs(step)) < 1e-6:
            break
    fitted = price_vec(deltas)
    rmse = float(np.sqrt(np.mean(((obs_vals - fitted) * weights) ** 2)))
    return deltas, rmse, fitted


class Fitter:
    def __init__(self):
        self.meetings = sorted(mpc_meetings())
        self.hist = base_rate_history()
        self.kofr = kofr_daily()

    def nodes_for(self, asof: date, horizon: int = 370):
        known_end = max(self.meetings)
        nodes = [m for m in self.meetings
                 if asof < m <= asof + timedelta(days=horizon)]
        ph = [n for n in ASSUMED_FUTURE_NODES
              if n > known_end and asof < n <= asof + timedelta(days=horizon)]
        alln = sorted(nodes + ph)
        return alln, np.array([n in ph for n in alln])

    def r0_for(self, asof: date, quotes: dict[str, float]) -> float:
        wk = quotes.get("1주")
        meeting_in_week = any(asof < m <= asof + timedelta(days=7)
                              for m in self.meetings)
        if wk is not None and not meeting_in_week:
            return wk
        # fallback: latest KOFR + trailing (1W OIS - KOFR) basis is unavailable
        # without same-day KOFR; use KOFR level as-is.
        for lag in range(8):
            d = asof - timedelta(days=lag)
            if d in self.kofr:
                return self.kofr[d]
        return base_rate_on(asof, self.hist)

    def fit(self, asof: date, quotes: dict[str, float]):
        tenors = [t for t in FIT_TENORS if t in quotes]
        if len(tenors) < 4:
            return None
        nodes, is_ph = self.nodes_for(asof)
        r0 = self.r0_for(asof, quotes)
        y = np.array([quotes[t] for t in tenors])
        w = np.array([TENOR_W[t] for t in tenors])
        days = [tenor_days(asof, t) for t in tenors]
        res = fit_deltas(asof, days, y, w, nodes, is_ph, r0)
        if res is None:
            return None
        deltas, rmse, fitted = res
        return {"nodes": nodes, "is_ph": is_ph, "deltas": deltas, "r0": r0,
                "tenors": tenors, "y": y, "fitted": fitted, "rmse": rmse}


def run():
    ois = load_ois()
    ft = Fitter()

    # ---------- snapshot
    latest = max(ois)
    res = ft.fit(latest, ois[latest])
    base_now = base_rate_on(latest, ft.hist)
    with open(OUT / "m1_snapshot.csv", "w", newline="", encoding="utf-8-sig") as f:
        wtr = csv.writer(f)
        wtr.writerow(["asof", "meeting", "assumed_node", "delta_bp",
                      "prob_25bp_hike", "implied_rate_after"])
        cum = base_now
        for n, dlt, ph in zip(res["nodes"], res["deltas"], res["is_ph"]):
            cum += dlt
            wtr.writerow([latest, n, int(ph), round(dlt * 100, 1),
                          round(min(max(dlt / STEP, 0), 1), 3), round(cum, 3)])
    with open(OUT / "m1_fit_detail.csv", "w", newline="", encoding="utf-8-sig") as f:
        wtr = csv.writer(f)
        wtr.writerow(["asof", "tenor", "market_mid", "model_fitted", "resid_bp"])
        for t, ym, yf in zip(res["tenors"], res["y"], res["fitted"]):
            wtr.writerow([latest, t, ym, round(yf, 4), round((ym - yf) * 100, 2)])
    print(f"[m1] {latest} r0={res['r0']:.3f} rmse={res['rmse'] * 100:.2f}bp")
    for n, dlt, ph in zip(res["nodes"], res["deltas"], res["is_ph"]):
        tag = " (2027 가정)" if ph else ""
        print(f"     {n}{tag}: {dlt * 100:+.1f}bp -> P={min(max(dlt / STEP, 0), 1):.0%}")

    # ---------- time series
    rows = []
    for asof in sorted(d for d in ois if d >= date(2025, 7, 1)):
        r = ft.fit(asof, ois[asof])
        if r is None:
            continue
        row = {"date": asof.isoformat(), "r0": round(r["r0"], 3),
               "rmse_bp": round(r["rmse"] * 100, 2)}
        ye_cum = sum(dl for n, dl, ph in zip(r["nodes"], r["deltas"], r["is_ph"])
                     if not ph and n.year == 2026)
        row["implied_ye_rate"] = round(base_rate_on(asof, ft.hist) + ye_cum, 3)
        nxt = next((n for n, ph in zip(r["nodes"], r["is_ph"]) if not ph), None)
        if nxt is not None:
            d_bp = r["deltas"][r["nodes"].index(nxt)] * 100
            row["next_meeting"] = nxt.isoformat()
            row["delta_next_bp"] = round(d_bp, 1)
            row["prob_next_hike"] = round(min(max(d_bp / 25.0, 0), 1), 3)
            row["prob_next_cut"] = round(min(max(-d_bp / 25.0, 0), 1), 3)
        for tgt in TARGETS_2026:
            if tgt in r["nodes"]:
                d_bp = r["deltas"][r["nodes"].index(tgt)] * 100
                row[f"delta_{tgt.strftime('%m%d')}_bp"] = round(d_bp, 1)
                row[f"prob_{tgt.strftime('%m%d')}"] = round(
                    min(max(d_bp / 25.0, 0), 1), 3)
        rows.append(row)
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k != "date", k))
    with open(OUT / "m1_timeseries.csv", "w", newline="", encoding="utf-8-sig") as f:
        wtr = csv.DictWriter(f, fieldnames=fields)
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"[m1] timeseries rows: {len(rows)}; latest row: {rows[-1]}")

    # ---------- MSB strip cross-check
    msb91 = ecos_daily("msb_91d_daily")
    msb6m = kofia_avg("msb_6m_val_daily")
    msb1y = ecos_daily("msb_1y_daily")
    call = ecos_daily("call_overnight_daily")

    quiet = []
    for d_, y1 in msb1y.items():
        if not (2015 <= d_.year <= 2024):
            continue
        b = base_rate_on(d_, ft.hist)
        nxt = next((m for m in ft.meetings if m > d_), None)
        if nxt is None:
            continue
        if abs(base_rate_on(nxt + timedelta(days=1), ft.hist) - b) < 1e-9 \
                and abs(y1 - b) < 0.12:
            quiet.append(d_)

    def phi(series):
        sp = sorted(series[d_] - base_rate_on(d_, ft.hist)
                    for d_ in quiet if d_ in series)
        return sp[len(sp) // 2] if sp else 0.0

    phis = {"91d": phi(msb91), "6m": phi(msb6m), "1y": phi(msb1y)}
    print(f"[m1] MSB phi (quiet n={len(quiet)}): "
          + " ".join(f"{k}={v * 100:.1f}bp" for k, v in phis.items()))

    msb_days = {"91d": 91, "6m": 182, "1y": 365}
    msb_w = {"91d": 1.0, "6m": 0.9, "1y": 0.7}
    rows = []
    for asof in sorted(d for d in msb91 if d >= date(2025, 7, 1)):
        obs = {}
        if asof in msb91:
            obs["91d"] = msb91[asof] - phis["91d"]
        if asof in msb6m:
            obs["6m"] = msb6m[asof] - phis["6m"]
        if asof in msb1y:
            obs["1y"] = msb1y[asof] - phis["1y"]
        if len(obs) < 3:
            continue
        nodes, is_ph = ft.nodes_for(asof)
        # anchor: call rate level (call-base wedge persists through the path)
        r0 = call.get(asof)
        if r0 is None:
            continue
        y = np.array([obs[t] for t in obs])
        w = np.array([msb_w[t] for t in obs])
        days = [msb_days[t] for t in obs]
        res = fit_deltas(asof, days, y, w, nodes, is_ph, r0,
                         smooth=2 * LAMBDA_SMOOTH,
                         shrink26=SHRINK_2026 * 2, shrink27=SHRINK_2027 * 2)
        if res is None:
            continue
        dl, _, _ = res
        row = {"date": asof.isoformat()}
        ye_cum = sum(d_ for n, d_, ph in zip(nodes, dl, is_ph)
                     if not ph and n.year == 2026)
        row["implied_ye_rate"] = round(base_rate_on(asof, ft.hist) + ye_cum, 3)
        for tgt in TARGETS_2026:
            if tgt in nodes:
                row[f"prob_{tgt.strftime('%m%d')}"] = round(
                    min(max(dl[nodes.index(tgt)] * 100 / 25.0, 0), 1), 3)
        rows.append(row)
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k != "date", k))
    with open(OUT / "m1_msb_crosscheck.csv", "w", newline="", encoding="utf-8-sig") as f:
        wtr = csv.DictWriter(f, fieldnames=fields)
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"[m1] MSB cross-check rows: {len(rows)}; latest: {rows[-1] if rows else None}")


if __name__ == "__main__":
    run()
