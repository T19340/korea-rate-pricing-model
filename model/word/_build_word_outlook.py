# -*- coding: utf-8 -*-
"""(나) 8월 인상 이후 전망판 — 부서 제안서 양식.

2026-08-27 인상 이후 시장이 10·11월과 연말을 어떻게 반영하는지, 그리고 회의
당일의 채권 강세가 정책경로에서 온 것인지 그 바깥에서 온 것인지를 가른다.
수치는 output/ 산출물과 원자료에서 직접 읽는다.
"""
import csv
import io
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from _word_style import Report          # noqa: E402
from common import load_ois             # noqa: E402
from m1_step_function import Fitter     # noqa: E402

OUT = HERE.parent / "output"
RAW = HERE.parent.parent / "rawdata"
FIGS = HERE.parent / "figs_paper"
DEST = HERE / "8월금통위_이후_전망.docx"

PRE, POST = date(2026, 8, 26), date(2026, 8, 28)
MEET_DAY = "2026-08-27"


def rows(p):
    return list(csv.DictReader(io.open(p, encoding="utf-8-sig")))


def jload(p):
    return json.load(io.open(p, encoding="utf-8"))


def pct(x):
    return f"{float(x) * 100:.1f}%"


def bp(x):
    return f"{x:+.1f}bp"


# ── 산출물 ──────────────────────────────────────────────────────────
snap = rows(OUT / "m1_snapshot.csv")
ts = {r["date"]: r for r in rows(OUT / "m1_timeseries.csv")}
ktb = {r["date"]: r for r in rows(OUT / "m9_ktb_timeseries.csv")}
irs = jload(OUT / "m11_irs_snapshot.json")
dns = jload(OUT / "m3_meta.json")
scen = rows(OUT / "m4_scenarios.csv")
panel = {r["date"]: r for r in rows(RAW / "ecos_daily" / "daily_rates_panel.csv")}

pre, post, day = ts[PRE.isoformat()], ts[POST.isoformat()], ts[MEET_DAY]

# RMSE는 '적합도'지 '신뢰도'가 아니다. 분위와 만기별 잔차를 함께 실어
# 0.77bp가 어디서 왔는지 본문에서 짚을 수 있게 한다.
_rl = sorted(float(r["rmse_bp"]) for r in ts.values())
RMSE_MED = _rl[len(_rl) // 2]


def rmse_rank(x):
    return sum(1 for v in _rl if v <= float(x)) / len(_rl) * 100


resid = {r["tenor"]: float(r["resid_bp"]) for r in rows(OUT / "m1_fit_detail.csv")}


def rest(row):
    """8월분을 뺀 잔여 인상 회수 — 회의 전후를 같은 기준으로 비교하기 위한 값."""
    return float(row["prob_1022"]) + float(row["prob_1126"])


def ye(row):
    return float(row["implied_ye_rate"])


# 2027 가정 구간의 누적 — 시계열 파일에 없어서 그 자리에서 다시 적합한다
ois_q = load_ois()
ft = Fitter()


def tail_2027(asof):
    res = ft.fit(asof, ois_q[asof])
    return sum(float(d) for d, ph in zip(res["deltas"], res["is_ph"]) if ph) * 100


t27_pre, t27_post = tail_2027(PRE), tail_2027(POST)

# 회의 당일 현물 금리 변화
CASH = [("통안 91일", "msb_91d"), ("통안 1년", "msb_1y"), ("국고 1년", "ktb_1y"),
        ("국고 3년", "ktb_3y"), ("국고 10년", "ktb_10y")]
cash_rows, cash_chg = [], {}
for label, key in CASH:
    a, b = float(panel["2026-08-26"][key]), float(panel[MEET_DAY][key])
    cash_chg[label] = (b - a) * 100
    cash_rows.append((label, f"{a:.3f}", f"{b:.3f}", bp(cash_chg[label])))

# OIS 호가 변화
ois_rows = []
for t in ["1주", "3개월", "6개월", "1년"]:
    a, b = ois_q[PRE].get(t), ois_q[POST].get(t)
    ois_rows.append((t, f"{a:.3f}", f"{b:.3f}", bp((b - a) * 100)))

rp = Report(FIGS)

# ══════════════════════════════ 제목
rp.title_block(
    "8월 인상 이후, 시장은 무엇을 반영하고 있나",
    "10·11월 금통위 인상확률과 연말 기준금리 재점검 — 완화적 발언은 어디를 움직였나",
    "FI운용1부 · 2026. 8. 28 · 데이터 기준 스왑 2026-08-28 · 현물 2026-08-27")

# ══════════════════════════════ 1) 요약
rp.heading("1) 요약")
d_post = (ye(post) - float(post["r0"])) * 100
rp.bullet("", "기준금리 3.00%. 남은 2026년 금통위는 10/22와 11/26 두 번")
rp.bullet("", f"현재(8/28) OIS 계단함수: 10월 {pct(post['prob_1022'])}, "
              f"11월 {pct(post['prob_1126'])}, 연말 내재 기준금리 {post['implied_ye_rate']}%")
rp.bullet("", f"연말까지 남은 인상은 {d_post:.1f}bp, 25bp 환산 {d_post / 25:.2f}회")
rp.bullet("", "회의 당일 채권시장은 강세였다. 그러나 그 강세는 정책경로에서 오지 않았다")
rp.para()
rp.arrow("완화적 발언은 1년 이내 정책경로가 아니라 그 바깥(장기 구간·기간프리미엄)을 움직였다")

# ══════════════════════════════ 2) 현재 반영 상태
rp.heading("2) 현재 시장이 반영한 경로")
rp.data_table(
    [("금통위", "내재 인상폭", "25bp 인상확률", "회의 후 내재 기준금리")]
    + [(r["meeting"] + (" (가정)" if r["assumed_node"] == "1" else ""),
        r["delta_bp"] + "bp", pct(r["prob_25bp_hike"]), r["implied_rate_after"] + "%")
       for r in snap],
    hl_rows=(1, 2))
rp.tbl_note("2027년 행은 일정 미공표에 따른 분기 노드 가정치 — 수축을 건 추정이라 액면 확률로 읽지 않음")
rp.para()
rp.bullet("", f"시장은 10월을 건너뛰고 11월에 한 번 더 올리는 경로를 반영 "
              f"(10월 {pct(post['prob_1022'])} 대 11월 {pct(post['prob_1126'])})")
rp.bullet("", f"곡선 적합 오차는 {post['rmse_bp']}bp로 회의 전일 {pre['rmse_bp']}bp보다 커졌으나, "
              f"잔차가 1개월({resid['1개월']:+.2f}bp)·2개월({resid['2개월']:+.2f}bp)에만 몰려 있다. "
              f"3개월 이상은 {max(abs(v) for k, v in resid.items() if k not in ('1개월', '2개월')):.2f}bp "
              "이내로 맞는다 (7절 참조)")
rp.picture("fig02_fit_snapshot.png",
           "그림 1. 내재 정책금리 경로(a)와 곡선 적합(b) — 인상 이후 남은 두 회의로 재배열된 모습")
rp.arrow(f"10월 대 11월의 배분보다 합계 {rest(post):.2f}회를 볼 것 — 배분은 하루 단위로 뒤집힌다")


# ══════════════════════════════ 3) 회의 전후
rp.heading("3) 회의 전후 — 무엇이 바뀌었나")
rp.data_table([
    ("기준일", "기준금리", "P(10/22)", "P(11/26)", "연말 내재", "잔여 인상"),
    ("8/26 (회의 전)", f"{float(pre['r0']):.2f}%", pct(pre["prob_1022"]),
     pct(pre["prob_1126"]), pre["implied_ye_rate"] + "%", f"{rest(pre):.2f}회"),
    ("8/27 (회의 후 종가)", f"{float(day['r0']):.2f}%", pct(day["prob_1022"]),
     pct(day["prob_1126"]), day["implied_ye_rate"] + "%", f"{rest(day):.2f}회"),
    ("8/28", f"{float(post['r0']):.2f}%", pct(post["prob_1022"]),
     pct(post["prob_1126"]), post["implied_ye_rate"] + "%", f"{rest(post):.2f}회"),
], hl_rows=(3,))
rp.tbl_note("각 행은 그날 자신의 OIS 종가로 적합한 값이다. 8/27은 결정·간담회가 끝난 뒤의 종가이므로 "
            "사후 가격이다(회의 전 정보로 채점하는 백테스트는 별도로 직전 영업일을 쓴다). "
            "'잔여 인상'은 8월분을 제외한 10·11월 확률의 합")
rp.para()
rp.bullet("", f"8월분을 걷어내고 보면 회의 전 {rest(pre):.2f}회에서 회의 후 {rest(post):.2f}회로 늘었다")
rp.bullet("", f"연말 내재 기준금리도 {pre['implied_ye_rate']}%에서 {post['implied_ye_rate']}%로 "
              f"{(ye(post) - ye(pre)) * 100:+.1f}bp 상승")
rp.bullet("", "즉 1년 이내 정책경로에서는 인상 기대가 꺾인 흔적이 없다. 오히려 소폭 굳었다")
rp.arrow("'향후 인상 기대 후퇴'라는 통념은 최소한 OIS 1년 이내 구간에서는 확인되지 않는다")

# ══════════════════════════════ 4) 강세는 어디에서 왔나
rp.heading("4) 그렇다면 당일 강세는 어디에서 왔나")
rp.bullet("(1)", "현물 금리는 인상에도 불구하고 내렸다 (8/26 → 8/27 종가)")
rp.data_table([("만기", "8/26", "8/27", "변화")] + cash_rows)
rp.tbl_note("CD 91일은 정책금리에 연동돼 기계적으로 상승하므로 제외")
rp.para()
rp.bullet("(2)", "그런데 같은 기간 OIS 호가는 오히려 올랐다 (8/26 → 8/28)")
rp.data_table([("만기", "8/26", "8/28", "변화")] + ois_rows)
rp.tbl_note("1주 상승은 기준금리 인상이 오버나이트에 반영된 기계적 변화")
rp.para()
rp.bullet("", f"강세는 국고 3년({bp(cash_chg['국고 3년'])})과 10년({bp(cash_chg['국고 10년'])})에 "
              f"집중됐고, 통안 1년({bp(cash_chg['통안 1년'])})을 비롯한 1년 이하는 소폭에 그쳤다")
rp.bullet("", f"2027년 가정 구간의 누적 인상폭은 회의 전 {t27_pre:.1f}bp에서 {t27_post:.1f}bp로 "
              f"{t27_post - t27_pre:+.1f}bp 축소 — 방향은 완화적이나 크기가 작고, "
              "일정 미공표 구간이라 신뢰도가 낮다")
rp.picture("fig08_scenario_curves.png",
           "그림 2. 인상·동결 두 갈래 시나리오 곡선 — 정책 충격이 만기별로 퍼지는 폭")
rp.arrow("완화적 발언의 효과는 정책경로(1년 이내)가 아니라 그 너머의 기간프리미엄에서 나타났다")


# ══════════════════════════════ 5) 교차검증
rp.heading("5) 교차검증 — 다른 렌즈는 무엇을 말하나")
rp.data_table([
    ("렌즈", "성격", "기준일", "연말 내재/기대 기준금리"),
    ("국고 단기 스트립", "현물", MEET_DAY, ktb[MEET_DAY]["implied_ye_rate"] + "%"),
    ("KOFR OIS", "스왑", POST.isoformat(), post["implied_ye_rate"] + "%"),
    ("CD-IRS 스트립", "스왑", irs["asof"], f"{irs['implied_yearend']}%"),
    ("DNS-VAR 기대", "모형", dns["sample"][1], f"{dns['expected_base_2026_12']}%"),
], hl_rows=(2,))
rp.tbl_note("CD-IRS는 백테스트에서 무정보 이하라 누적치의 참고로만 사용. "
            "국고 스트립은 회의별 배분이 진동해 누적만 읽는다")
rp.para()
rp.bullet("", f"국고 스트립도 회의 전 대비 상승했다 — 8/26 {ktb['2026-08-26']['implied_ye_rate']}%에서 "
              f"{ktb[MEET_DAY]['implied_ye_rate']}%")
rp.bullet("", f"DNS-VAR 기대 경로는 2026년 말 {dns['expected_base_2026_12']}%, "
              f"2027년 8월 {dns['expected_base_2027_08']}%로 완만한 추가 인상 후 되돌림을 시사")
rp.bullet("", "네 렌즈가 모두 연말 3.0% 이상을 가리킨다. 방향은 일치하고 폭만 다르다")
rp.arrow("서로 다른 원리의 렌즈가 같은 방향이면 신뢰 — 이번에는 '연말 3.0% 이상'에서 수렴")

# ══════════════════════════════ 6) 시나리오
rp.heading("6) 10월 금통위 시나리오 — 만기별 노출")
rp.data_table(
    [("만기", "실증 베타", "인상 시", "동결 시")]
    + [(r["maturity"], r["beta_empirical"], r["hike_move_bp_empirical"] + "bp",
        r["hold_move_bp_empirical"] + "bp") for r in scen],
    font_size=10)
rp.tbl_note(f"10/22 인상확률 {pct(post['prob_1022'])} 기준의 서프라이즈 산술. "
            "베타는 2011~2019 표본이며 표본외 검증에서 크기는 과대 추정되는 경향")
rp.para()
rp.bullet("", "현재 10월 인상확률이 낮아, 인상 시 서프라이즈는 크고 동결 시는 거의 무반응인 비대칭 구조")
rp.bullet("", "크기보다 방향과 상대 순서를 볼 것 — 표본외 검증에서 단기물만 방향 정보가 유효했다")
rp.picture("fig11_shock_validation.png",
           "그림 3. 표본외 성적 — 대각선을 거스르는 점은 3년·10년 모두 급속 인상기에 집중")
rp.arrow("10월은 동결이 기본 시나리오이나, 인상 시 단기물 노출이 비대칭적으로 크다")

# ══════════════════════════════ 7) 한계
rp.heading("7) 한계")
rp.bullet("(1)", f"적합 오차(RMSE) {post['rmse_bp']}bp는 표본(2025-07~) 중위 {RMSE_MED:.2f}bp보다 크지만 "
                 f"하위 {rmse_rank(post['rmse_bp']):.0f}% 수준으로 이상치는 아니다. 회의까지 남은 거리가 "
                 "이 지표를 지배한다 — 회의 1주 이내 평균 0.29bp, 41~60일 전 평균 0.69bp")
rp.bullet("(2)", f"이번 상승은 모형 악화가 아니라 흡수할 계단이 사라진 결과다. 1개월 계약(만기 9월 말) "
                 f"안에 금통위가 없어 모형은 1개월을 r0와 같게 볼 수밖에 없는데, 시장은 "
                 f"{resid['1개월']:+.2f}bp 높게 부른다. 이 앞단 베이시스는 정책기대가 아니며, "
                 "6개월~1년이 0.02bp로 맞는 만큼 10·11월 노드 추정에는 영향이 없다")
rp.bullet("(3)", "다만 RMSE는 적합도이지 식별력이 아니다. 곡선을 잘 맞춰도 총량을 회의별로 "
                 "쪼개는 일은 별개이며, 호가 ±1틱 교란의 몬테카를로에서 배분 대역은 회의별로 "
                 "4~22%p에 달했다. 남은 회의가 둘뿐이고 10월이 55일 뒤라 지금은 특히 얇다")
rp.bullet("(4)", "현물은 8/27까지, 스왑은 8/28까지다. 장기물 강세가 이어졌는지는 다음 회차에서 확인")
rp.bullet("(5)", "2027년 구간은 금통위 일정 미공표로 분기 노드를 가정한 값이다. "
                 "10개월 너머는 평균회귀 사전믿음이 지배하므로 추세로만 읽을 것")
rp.bullet("(6)", "간담회 발언의 효과와 그 밖의 요인(수급·해외금리)을 이 자료는 분리하지 않는다. "
                 "당일 변화의 귀속에는 별도 이벤트 스터디가 필요")
rp.para()
rp.arrow("결론은 '연말 3.2% 부근, 11월 인상이 기본 경로'이며 배분보다 누적으로 관리할 것")

rp.save(DEST)
print("saved:", DEST)
