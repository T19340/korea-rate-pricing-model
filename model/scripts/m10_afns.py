# -*- coding: utf-8 -*-
"""Model 10 — AFNS (Christensen-Diebold-Rudebusch 2011, independent-factor)
Kalman-filter ML estimation on month-end KTB zero curves.

This is the Bank of Korea's stated methodology (MPR 2023.3 box I-2: "AFNS
모형을 활용한 자체 추정") run on our own data — the arbitrage-free version of
what m3 approximates in two steps. Purpose:
  (1) replicate the BOK approach itself (authority/validation),
  (2) compare its expectation path / term premium with m3 (DNS-VAR) and the
      OIS step function,
  (3) reproduce the BOK-published 2022.11->2023.01 decomposition direction
      (spread narrowing -136bp, of which expectations -102bp).

Spec (주 사양): 대각 Σ(독립 충격) + 자유 K_P(상관 P-동학)의 AFNS.
CDR가 'correlated-factor'라 부르는 사양은 삼각 Σ까지 자유롭게 두므로, 이
구현은 그 제약판(대각 Σ)이다 — 무재정 정합성은 유지되고 yield adjustment는
대각 Σ 폐형식이 정확히 적용된다(검증 워크플로에서 원문 대조 완료). 독립요인
(대각 K_P)은 강건성으로 병행 추정. 측정오차는 만기 공통 σ_e(CDR 원문은
만기별 — 단순화 제약으로 공시). Estimation sample: 3m..10y (8 tenors;
20/30y excluded — super-long KTB is distorted by insurer demand).

Outputs: m10_afns_meta.json, m10_afns_factors.csv, m10_afns_decomposition.csv,
         m10_afns_expected_path.csv, m10_afns_bok_window.csv
"""
from __future__ import annotations

import csv
import json
from datetime import date

import numpy as np
from scipy.linalg import expm, logm
from scipy.optimize import minimize

from common import OUT, base_rate_history, base_rate_on
from m3_dns_expectation import TENORS_M, bootstrap_zero, month_end_series, ns_loadings

OUT.mkdir(parents=True, exist_ok=True)

EST_TENORS_M = [3, 6, 9, 12, 24, 36, 60, 120]        # 추정: 3m..10y
DT = 1.0 / 12.0


def discrete_dynamics(K: np.ndarray, mu: np.ndarray, sig: np.ndarray):
    """dX = K(mu - X)dt + diag(sig) dW 의 정확 월간 이산화.
    Phi = expm(-K dt); Q = ∫0^dt e^{-Ks} ΣΣ' e^{-K's} ds (수치 적분 60구간)."""
    Phi = expm(-K * DT)
    SS = np.diag(sig ** 2)
    n = 60
    ds = DT / n
    Q = np.zeros((3, 3))
    for j in range(n):
        s = (j + 0.5) * ds
        E = expm(-K * s)
        Q += E @ SS @ E.T * ds
    c = (np.eye(3) - Phi) @ mu
    return Phi, Q, c


# ---------------------------------------------------------------- AFNS pieces
def yield_adjustment(lam: float, sig: np.ndarray, taus: np.ndarray) -> np.ndarray:
    """-A(tau)/tau, CDR(2011) independent-factor closed form (positive,
    subtracted from the NS yield). sig = (s1, s2, s3), rates in decimals/yr."""
    s1, s2, s3 = sig
    t = taus
    lt = lam * t
    e1 = np.exp(-lt)
    e2 = np.exp(-2 * lt)
    A1 = s1 ** 2 * t ** 2 / 6.0
    A2 = s2 ** 2 * (1.0 / (2 * lam ** 2)
                    - (1 - e1) / (lam ** 3 * t)
                    + (1 - e2) / (4 * lam ** 3 * t))
    A3 = s3 ** 2 * (1.0 / (2 * lam ** 2)
                    + e1 / lam ** 2
                    - t * e2 / (4 * lam)
                    - 3 * e2 / (4 * lam ** 2)
                    - 2 * (1 - e1) / (lam ** 3 * t)
                    + 5 * (1 - e2) / (8 * lam ** 3 * t))
    return A1 + A2 + A3


def unpack(theta_v: np.ndarray, spec: str):
    """spec='indep': [lnλ, lnκ1..3, μ1..3, lnσ1..3, lnσe] (11)
    spec='corr' : [lnλ, K 9원소, μ1..3, lnσ1..3, lnσe] (17), K 대각은 exp."""
    lam = np.exp(theta_v[0])
    if spec == "indep":
        K = np.diag(np.exp(theta_v[1:4]))
        rest = theta_v[4:]
    else:
        K = theta_v[1:10].reshape(3, 3).copy()
        K[np.diag_indices(3)] = np.exp(np.diag(K))
        rest = theta_v[10:]
    mu = rest[0:3]
    sig = np.exp(rest[3:6])
    sig_e = np.exp(rest[6])
    return lam, K, mu, sig, sig_e


def stationary_cov(Phi, Q):
    """P = Phi P Phi' + Q 의 해 (vec 트릭)."""
    n = Phi.shape[0]
    M = np.eye(n * n) - np.kron(Phi, Phi)
    return np.linalg.solve(M, Q.reshape(-1)).reshape(n, n)


def kalman_loglik(theta_v: np.ndarray, Y: np.ndarray, taus: np.ndarray,
                  spec: str = "corr", return_states: bool = False):
    """Y: T x N zero yields in decimals. OU-AFNS Kalman filter."""
    lam, K, mu, sig, sig_e = unpack(theta_v, spec)
    if lam < 0.03 or lam > 3.0:
        return 1e10
    eigK = np.linalg.eigvals(K)
    if np.any(eigK.real < 1e-4) or np.any(np.abs(eigK) > 60):
        return 1e10
    B = ns_loadings(lam, taus)                       # N x 3
    yadj = yield_adjustment(lam, sig, taus)          # N
    Phi, Qm, c = discrete_dynamics(K, mu, sig)
    if np.any(np.abs(np.linalg.eigvals(Phi)) >= 0.9999):
        return 1e10
    H = np.eye(len(taus)) * sig_e ** 2

    x = mu.copy()
    try:
        P = stationary_cov(Phi, Qm)
    except np.linalg.LinAlgError:
        return 1e10
    ll = 0.0
    T = Y.shape[0]
    xs = np.zeros((T, 3))
    for t_i in range(T):
        x_pred = c + Phi @ x
        P_pred = Phi @ P @ Phi.T + Qm
        y_pred = B @ x_pred - yadj
        v = Y[t_i] - y_pred
        S = B @ P_pred @ B.T + H
        try:
            Sinv_v = np.linalg.solve(S, v)
            sign, logdet = np.linalg.slogdet(S)
            if sign <= 0:
                return 1e10
        except np.linalg.LinAlgError:
            return 1e10
        ll += -0.5 * (len(taus) * np.log(2 * np.pi) + logdet + v @ Sinv_v)
        Kg = P_pred @ B.T @ np.linalg.inv(S)
        x = x_pred + Kg @ v
        P = (np.eye(3) - Kg @ B) @ P_pred
        xs[t_i] = x
    if return_states:
        return ll, xs, dict(lam=lam, K=K, mu=mu, sig=sig, sig_e=sig_e,
                            B=B, yadj=yadj, Phi=Phi, c=c)
    return -ll


def estimate(Y, taus, theta0, spec="corr"):
    res = minimize(kalman_loglik, theta0, args=(Y, taus, spec),
                   method="L-BFGS-B",
                   options={"maxiter": 600, "ftol": 1e-11})
    return res


def expected_short_path(x_last, K, mu, months):
    """E[L_h + S_h] under P, h=1..months (monthly grid, decimals)."""
    out = []
    Ad = expm(-K * DT)
    xh = x_last.copy()
    for _ in range(months):
        xh = mu + Ad @ (xh - mu)
        out.append(xh[0] + xh[1])
    return np.array(out)


# ---------------------------------------------------------------- selftest
def yadj_numeric_check(lam, sig, taus):
    """yield_adjustment 폐형식을 정의 적분과 독립 대조 — 전사 오류 방지선.
    A(tau)/tau = (1/2tau) ∫0^tau [s1²s² + s2²((1-e^{-λs})/λ)²
                                  + s3²((1-e^{-λs})/λ - s e^{-λs})²] ds"""
    s1, s2, s3 = sig
    out = []
    for t in taus:
        n = 4000
        s = (np.arange(n) + 0.5) * (t / n)
        b2 = (1 - np.exp(-lam * s)) / lam
        b3 = b2 - s * np.exp(-lam * s)
        integ = np.sum(s1 ** 2 * s ** 2 + s2 ** 2 * b2 ** 2
                       + s3 ** 2 * b3 ** 2) * (t / n)
        out.append(integ / (2 * t))
    diff_bp = float(np.max(np.abs(
        np.array(out) - yield_adjustment(lam, sig, np.array(taus)))) * 1e4)
    return diff_bp


def selftest(theta_true, taus, spec, T=164, seeds=(7, 11, 23)):
    """Synthetic recovery on the SHIPPED spec/params: simulate from the given
    truth, re-estimate per seed, and report the recovery-error DISTRIBUTION of
    the objects we use (연말 h=4 기대, 36개월 경로 RMSE). 검증 워크플로 지적
    반영 — 합격/불합격 도장이 아니라 추정 잡음의 크기를 그대로 공시한다."""
    lam, K, mu, sig, sig_e = unpack(theta_true, spec)
    yadj_diff = yadj_numeric_check(lam, sig, taus)
    B = ns_loadings(lam, taus)
    yadj = yield_adjustment(lam, sig, taus)
    Phi, Qm, c = discrete_dynamics(K, mu, sig)
    cQ = np.linalg.cholesky(Qm + 1e-14 * np.eye(3))
    h4_err, path_rmse, lam_hat = [], [], []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        x = mu.copy()
        Ys = np.zeros((T, len(taus)))
        xs_true = np.zeros((T, 3))
        for t_i in range(T):
            x = c + Phi @ x + cQ @ rng.standard_normal(3)
            xs_true[t_i] = x
            Ys[t_i] = B @ x - yadj + sig_e * rng.standard_normal(len(taus))
        start = theta_true + rng.uniform(-0.2, 0.2, size=len(theta_true))
        res = estimate(Ys, taus, start, spec)
        lam_h, K_h, mu_h, sig_h, sig_e_h = unpack(res.x, spec)
        path_true = expected_short_path(xs_true[-1], K, mu, 36)
        _, xs_h, _ = kalman_loglik(res.x, Ys, taus, spec, return_states=True)
        path_hat = expected_short_path(xs_h[-1], K_h, mu_h, 36)
        h4_err.append(float((path_hat[3] - path_true[3]) * 1e4))
        path_rmse.append(float(np.sqrt(np.mean(
            (path_true - path_hat) ** 2)) * 1e4))
        lam_hat.append(float(lam_h))
    report = {
        "yadj_closed_vs_numeric_bp": round(yadj_diff, 6),
        "seeds": list(seeds),
        "lambda_true_vs_hat": [round(lam, 3),
                               [round(v, 3) for v in lam_hat]],
        "h4_expected_err_bp": [round(v, 1) for v in h4_err],
        "path36_rmse_bp": [round(v, 1) for v in path_rmse],
    }
    ok = yadj_diff < 1e-4 and max(abs(v) for v in h4_err) < 25
    return ok, report


# ---------------------------------------------------------------- main
def run():
    series = {slug: month_end_series(slug) for slug in TENORS_M}
    months = sorted(set.intersection(*(set(s) for s in series.values())))
    curves = {}
    for mkey in months:
        par = {TENORS_M[slug]: series[slug][mkey] for slug in TENORS_M}
        curves[mkey] = bootstrap_zero(par)
    taus = np.array(EST_TENORS_M) / 12.0
    Y = np.array([[curves[mk][t] for t in EST_TENORS_M]
                  for mk in months]) / 100.0        # decimals

    # ---- starting values from the two-step DNS (m3 logic)
    B0 = ns_loadings(0.55, taus)
    beta, *_ = np.linalg.lstsq(B0, Y.T, rcond=None)
    F0 = beta.T
    resid0 = F0[1:] - F0[:-1]
    kap0 = np.clip(-np.log(np.clip(np.diag(
        np.corrcoef(F0[:-1].T, F0[1:].T)[:3, 3:]), 0.05, 0.995)) / DT,
        0.05, 4.0)
    sig0 = np.clip(resid0.std(axis=0) / np.sqrt(DT), 1e-4, 0.05)
    theta0_ind = np.concatenate([
        [np.log(0.55)], np.log(kap0), F0.mean(axis=0),
        np.log(sig0), [np.log(0.0006)],
    ])

    # ---- 1단계: 독립요인 (강건성 기록 + 상관 사양의 출발점)
    best_ind = None
    for k, start in enumerate([theta0_ind, theta0_ind + np.array(
            [0.3, .2, -.2, .2, 0.002, -0.002, 0.001, .2, .2, -.2, .3])]):
        res = estimate(Y, taus, start, spec="indep")
        if best_ind is None or res.fun < best_ind.fun:
            best_ind = res
    lam_i, K_i, mu_i, sig_i, sig_e_i = unpack(best_ind.x, "indep")
    print(f"[m10] indep: nll={best_ind.fun:.2f} lam={lam_i:.3f}")

    # ---- 2단계: 상관요인 (주 사양). K 출발점 = 2단계 요인 VAR의 -log(A)/dt
    Z0 = F0 - F0.mean(axis=0)
    A0, *_ = np.linalg.lstsq(Z0[:-1], Z0[1:], rcond=None)
    K_var = np.real(logm(np.linalg.inv(A0.T))) / DT      # A=e^{-K dt}
    K_start = K_var.copy()
    diag0 = np.clip(np.diag(K_start), 0.05, 8.0)
    K_start[np.diag_indices(3)] = np.log(diag0)
    theta0_cor = np.concatenate([
        [best_ind.x[0]], K_start.reshape(-1),
        unpack(best_ind.x, "indep")[2],
        best_ind.x[7:10], [best_ind.x[10]],
    ])
    # 독립 최적해 자체도 상관 사양의 출발점(비대각 0)으로 추가
    K_ind_start = np.zeros((3, 3))
    K_ind_start[np.diag_indices(3)] = np.log(np.diag(K_i))
    theta0_cor2 = np.concatenate([
        [best_ind.x[0]], K_ind_start.reshape(-1),
        mu_i, best_ind.x[7:10], [best_ind.x[10]],
    ])

    best = None
    for k, start in enumerate([theta0_cor, theta0_cor2]):
        res = estimate(Y, taus, start, spec="corr")
        print(f"[m10] corr start {k}: nll={res.fun:.2f} conv={res.success}")
        if best is None or res.fun < best.fun:
            best = res
    # polish 재출발 — 최적점에서 시작하면 즉시 success로 닫혀야 정상
    polish = estimate(Y, taus, best.x, spec="corr")
    if polish.fun <= best.fun:
        best = polish
    print(f"[m10] polish: nll={best.fun:.2f} conv={best.success} "
          f"msg={getattr(best, 'message', '')}")
    ll, xs, mp = kalman_loglik(best.x, Y, taus, "corr", return_states=True)
    lam, K, mu, sig, sig_e = unpack(best.x, "corr")
    kap_eig = np.linalg.eigvals(K)

    # ---- synthetic recovery self-test — 출고 사양·적합 파라미터를 진리값으로
    ok, st_report = selftest(best.x, taus, "corr")
    print("[m10] selftest(shipped spec):", "OK" if ok else "CHECK", st_report)

    fitted = xs @ mp["B"].T - mp["yadj"]
    rmse_bp = float(np.sqrt(np.mean((Y - fitted) ** 2)) * 1e4)

    hist = base_rate_history()
    y_, m_ = map(int, months[-1].split("-"))
    base_now = base_rate_on(date(y_, m_, 28), hist)
    short_now = float(xs[-1, 0] + xs[-1, 1]) * 100
    wedge = short_now - base_now

    # ---- expected path (P-measure), 120 months
    epath = expected_short_path(xs[-1], K, mu, 120) * 100

    # 독립요인 사양의 연말 기대(강건성 기록)
    _, xs_i, _ = kalman_loglik(best_ind.x, Y, taus, "indep",
                               return_states=True)
    ep_i = expected_short_path(xs_i[-1], K_i, mu_i, 24) * 100
    wedge_i = float(xs_i[-1, 0] + xs_i[-1, 1]) * 100 - base_now
    exp_base_ind_ye = round(float(ep_i[3]) - wedge_i, 3)
    with open(OUT / "m10_afns_expected_path.csv", "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["h_months", "expected_short_rate", "expected_base_rate"])
        for h in range(120):
            w.writerow([h + 1, round(epath[h], 3), round(epath[h] - wedge, 3)])

    # ---- decomposition at latest month (obs-based TP, m3-comparable + model)
    with open(OUT / "m10_afns_decomposition.csv", "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["tenor_months", "zero_yield", "model_yield",
                    "avg_expected_short", "tp_obs_bp", "tp_model_bp",
                    "yield_adj_bp"])
        full = np.concatenate([[short_now], epath])
        for i, t_m in enumerate(EST_TENORS_M):
            avg_exp = float(np.mean(full[:t_m + 1]))
            yld = curves[months[-1]][t_m]
            ymod = float(fitted[-1, i]) * 100
            w.writerow([t_m, round(yld, 3), round(ymod, 3), round(avg_exp, 3),
                        round((yld - avg_exp) * 100, 1),
                        round((ymod - avg_exp) * 100, 1),
                        round(float(mp["yadj"][i]) * 1e4, 1)])

    # ---- factors
    with open(OUT / "m10_afns_factors.csv", "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["month", "level", "slope", "curvature", "short_proxy"])
        for mk, x in zip(months, xs):
            w.writerow([mk, round(x[0] * 100, 3), round(x[1] * 100, 3),
                        round(x[2] * 100, 3), round((x[0] + x[1]) * 100, 3)])

    # ---- BOK window replication: "2022.11~2023.1월중" 변화 = 10월말 -> 1월말
    # (검증 워크플로 확인: 일별 ECOS 국고3y 기준 10월말->1월말 스프레드 변화가
    #  한은 공표 -136bp와 정확히 일치. 11월말 시작이면 에피소드 절반 누락.)
    bok = {}
    for mk in ("2022-10", "2023-01"):
        i = months.index(mk)
        yy, mm = map(int, mk.split("-"))
        b = base_rate_on(date(yy, mm, 28), hist)
        ep = expected_short_path(xs[i], K, mu, 36) * 100
        full = np.concatenate([[float(xs[i, 0] + xs[i, 1]) * 100], ep])
        avg3y = float(np.mean(full[:37]))
        y3 = curves[mk][36]
        bok[mk] = dict(base=b, y3=y3, spread=(y3 - b) * 100,
                       exp3y=avg3y, exp_minus_base=(avg3y - b) * 100,
                       tp=(y3 - avg3y) * 100)
    d_spread = bok["2023-01"]["spread"] - bok["2022-10"]["spread"]
    d_exp = bok["2023-01"]["exp_minus_base"] - bok["2022-10"]["exp_minus_base"]
    d_tp = bok["2023-01"]["tp"] - bok["2022-10"]["tp"]
    d_base = (bok["2023-01"]["base"] - bok["2022-10"]["base"]) * 100
    d_exp_pure = bok["2023-01"]["exp3y"] * 100 - bok["2022-10"]["exp3y"] * 100
    # d_exp(기대-기준금리)가 한은의 '순기대단기금리' 몫(-102bp)에, d_exp_pure
    # (기대 자체의 변화)가 각주의 '순수 기대'(-52bp)에 대응한다:
    # -102 + 실현 인상 +50 = -52 산술과 동일 구조.
    with open(OUT / "m10_afns_bok_window.csv", "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["month", "base", "ktb3y_zero", "spread_bp",
                    "avg_exp_short_3y", "exp_minus_base_bp", "tp_bp"])
        for mk, d in bok.items():
            w.writerow([mk, d["base"], round(d["y3"], 3),
                        round(d["spread"], 1), round(d["exp3y"], 3),
                        round(d["exp_minus_base"], 1), round(d["tp"], 1)])
        w.writerow(["delta", "", "", round(d_spread, 1), "",
                    round(d_exp, 1), round(d_tp, 1)])
        w.writerow(["delta_base_bp", round(d_base, 1), "", "", "", "", ""])
        w.writerow(["delta_exp_pure_bp", round(d_exp_pure, 1),
                    "(기대 자체 변화 = 순기대 몫 + 실현 인상)", "", "", "", ""])

    meta = {
        "model": "AFNS correlated-factor (CDR 2011), Kalman ML "
                 "(independent-factor as robustness)",
        "sample": [months[0], months[-1]],
        "n_months": len(months),
        "est_tenors_m": EST_TENORS_M,
        "lambda_per_year": round(float(lam), 4),
        "K_P": [[round(float(v), 4) for v in row] for row in K],
        "K_P_eig_real": [round(float(e.real), 4) for e in kap_eig],
        "eig_half_life_months": [round(float(np.log(2) / max(e.real, 1e-6)
                                             * 12), 1) for e in kap_eig],
        "mu_pct": [round(float(v) * 100, 3) for v in mu],
        "sigma_pct": [round(float(v) * 100, 3) for v in sig],
        "sigma_e_bp": round(float(sig_e) * 1e4, 2),
        "loglik": round(float(ll), 1),
        "loglik_indep": round(float(-best_ind.fun), 1),
        "fit_rmse_bp": round(rmse_bp, 2),
        "indep_robustness": {
            "lambda": round(float(lam_i), 4),
            "expected_base_2026_12": exp_base_ind_ye,
        },
        "yield_adj_bp_at": {str(t): round(float(
            yield_adjustment(lam, sig, np.array([t / 12.0]))[0]) * 1e4, 1)
            for t in (12, 36, 60, 120)},
        "short_proxy_now": round(short_now, 3),
        "base_rate_now": base_now,
        "wedge_bp": round(wedge * 100, 1),
        "expected_base_2026_12": round(float(epath[3]) - wedge, 3),
        "expected_base_2027_08": round(float(epath[11]) - wedge, 3),
        "expected_base_2028_08": round(float(epath[23]) - wedge, 3),
        "bok_window": {"window": "2022-10월말 -> 2023-01월말 (한은 표기 "
                                 "'2022.11~2023.1월중' 변화)",
                       "d_spread_bp": round(d_spread, 1),
                       "d_exp_minus_base_bp": round(d_exp, 1),
                       "d_exp_pure_bp": round(d_exp_pure, 1),
                       "d_base_bp": round(d_base, 1),
                       "d_tp_bp": round(d_tp, 1),
                       "bok_published": {"d_spread_bp": -136,
                                         "d_net_exp_bp": -102,
                                         "d_pure_exp_bp_fn7": -52},
                       "note": "상태는 전체 표본(2013~2026) 파라미터로 필터링"
                               "(사후 분해, 실시간 재현 아님)"},
        "long_run_expected_base": round(float(mu[0] + mu[1]) * 100 - wedge, 2),
        "K_P_eig_imag": [round(float(e.imag), 4) for e in kap_eig],
        "opt_message": str(getattr(best, "message", "")),
        "selftest_ok": bool(ok),
        "selftest": st_report,
    }
    (OUT / "m10_afns_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[m10]", json.dumps(meta, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    run()
