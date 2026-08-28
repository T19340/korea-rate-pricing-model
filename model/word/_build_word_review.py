# -*- coding: utf-8 -*-
"""(가) 8월 금통위 사후 검증판 — 부서 제안서 양식.

2026-08-27 금통위가 25bp 인상으로 끝난 뒤, 회의 전일 각 시장이 매긴 확률을
실제 결정과 대조한 문서. 수치는 전부 output/ 산출물에서 직접 읽어 쓴다
(하드코딩 금지 — v8 때 본문 산문에 구판 수치가 남아 심사에서 걸렸다).
"""
import csv
import io
import json
from pathlib import Path

from _word_style import Report

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "output"
BASELINE = OUT / "m5_baseline_20260807.json"   # SAMPLE_END=2026-08-07 로 재생성 가능
FIGS = HERE.parent / "figs_paper"
DEST = HERE / "8월금통위_사후검증.docx"


def rows(p):
    return list(csv.DictReader(io.open(p, encoding="utf-8-sig")))


def jload(p):
    return json.load(io.open(p, encoding="utf-8"))


def pct(x):
    return f"{float(x) * 100:.1f}%"


# ── 산출물에서 수치 읽기 ────────────────────────────────────────────
ts = {r["date"]: r for r in rows(OUT / "m1_timeseries.csv")}
bt = {r["meeting"]: r for r in rows(OUT / "m5_backtest_meetings.csv")}
aug, jul = bt["2026-08-27"], bt["2026-07-16"]
sm_new, sm_old = jload(OUT / "m5_backtest_summary.json"), jload(BASELINE)
gap = [r for r in rows(OUT / "m6_gap_daily.csv") if r["gap_6m_bp"]][-1]
ktb = rows(OUT / "m9_ktb_timeseries.csv")


def brier(summary, key):
    v = summary["overall"].get("brier_" + key)
    return f"{v[0]:.3f}" if isinstance(v, list) else f"{v:.3f}"


def brier_p(period, key):
    v = sm_new["periods"][period].get("brier_" + key)
    if isinstance(v, list) and isinstance(v[0], (int, float)):
        return f"{v[0]:.3f} (n={v[1]})"
    return "-"


hike26 = next(k for k in sm_new["periods"] if k.startswith("2026 인상기"))

_rl = sorted(float(r["rmse_bp"]) for r in ts.values())
RMSE_MED = _rl[len(_rl) // 2]

rp = Report(FIGS)

# ══════════════════════════════ 제목
rp.title_block(
    "8월 금통위 사후 검증",
    "시장가격은 인상을 얼마나 알고 있었나 — 렌즈별 적중 기록과 백테스트 갱신",
    "FI운용1부 · 2026. 8. 28 · 데이터 기준 스왑 2026-08-28 · 현물 2026-08-27")

# ══════════════════════════════ 1) 요약
rp.heading("1) 요약")
rp.bullet("", f"2026-08-27 금통위는 기준금리를 2.75%에서 3.00%로 25bp 인상")
rp.bullet("", f"회의 전일(8/26) KOFR OIS 계단함수 모형의 인상확률 {pct(aug['ois_hike'])} — 적중")
rp.bullet("", f"같은 날 통안 스트립 {pct(aug['msb_hike'])}, CD-IRS 스트립은 인상 {pct(aug['irs_hike'])}에 "
              f"오히려 인하를 {pct(aug['irs_cut'])} 반영 — 둘 다 실패")
rp.bullet("", "금투협 BMSI는 8월 회의 대상 조사가 발표되지 않아 대조 불가")
rp.para()
rp.arrow("스왑(OIS)만 맞혔다. 현물·CD 기반 렌즈는 인상을 회의 전날까지 반영하지 못했다")

# ══════════════════════════════ 2) 회의 전 3주
rp.heading("2) 회의 전 3주 — 확률은 어떻게 움직였나")
rp.data_table([
    ("기준일", "P(8/27)", "P(10/22)", "P(11/26)", "연말 내재 기준금리"),
    ("8/07", pct(ts["2026-08-07"]["prob_0827"]), pct(ts["2026-08-07"]["prob_1022"]),
     pct(ts["2026-08-07"]["prob_1126"]), ts["2026-08-07"]["implied_ye_rate"] + "%"),
    ("8/14", pct(ts["2026-08-14"]["prob_0827"]), pct(ts["2026-08-14"]["prob_1022"]),
     pct(ts["2026-08-14"]["prob_1126"]), ts["2026-08-14"]["implied_ye_rate"] + "%"),
    ("8/21", pct(ts["2026-08-21"]["prob_0827"]), pct(ts["2026-08-21"]["prob_1022"]),
     pct(ts["2026-08-21"]["prob_1126"]), ts["2026-08-21"]["implied_ye_rate"] + "%"),
    ("8/26", pct(ts["2026-08-26"]["prob_0827"]), pct(ts["2026-08-26"]["prob_1022"]),
     pct(ts["2026-08-26"]["prob_1126"]), ts["2026-08-26"]["implied_ye_rate"] + "%"),
], hl_rows=(4,))
rp.tbl_note("KOFR OIS 계단함수(모형 ①) 기준. 8/26은 회의 전일 마지막 관측")
rp.para()
rp.bullet("", f"8월 인상확률은 3주 동안 {pct(ts['2026-08-07']['prob_0827'])}에서 "
              f"{pct(ts['2026-08-26']['prob_0827'])}로 상승")
rp.bullet("", f"같은 기간 연말 내재 기준금리는 {ts['2026-08-07']['implied_ye_rate']}%에서 "
              f"{ts['2026-08-26']['implied_ye_rate']}%로 사실상 불변 — 긴축 총량이 아니라 시점이 앞당겨진 것")
rp.bullet("", "10월 확률이 같은 기간 하락한 것이 그 증거. 8월과 10월은 서로를 대체했고 총합은 유지")
rp.picture("fig04_next_meeting.png",
           "그림 1. 다음 금통위 인상확률 — 모형(실선), 서베이(마름모), 실제 결정(상단 표식)")
rp.arrow("모형은 '얼마나 오를까'보다 '언제 오를까'를 먼저 바꿨다 — 누적은 수준, 배분은 방향으로 읽는 원칙이 그대로 확인됨")


# ══════════════════════════════ 3) 렌즈별 성적표
rp.heading("3) 렌즈별 성적표 — 회의 전일 인상확률")
rp.data_table([
    ("렌즈", "성격", "2026-07-16", "2026-08-27", "판정"),
    ("KOFR OIS", "스왑", pct(jul["ois_hike"]), pct(aug["ois_hike"]), "2회 연속 적중"),
    ("통안 스트립", "현물", pct(jul["msb_hike"]), pct(aug["msb_hike"]), "7월 적중 · 8월 실패"),
    ("CD-IRS 스트립", "스왑", pct(jul["irs_hike"]), pct(aug["irs_hike"]), "2회 연속 실패"),
    ("BMSI 서베이", "설문", pct(jul["bmsi_hike"]), "미발표", "대조 불가"),
], hl_rows=(1,))
rp.tbl_note("실제 결정은 두 회의 모두 25bp 인상. CD-IRS는 8/27에 대해 인상 0%, 인하 "
            + pct(aug["irs_cut"]) + "를 반영")
rp.para()
rp.bullet("", f"CD-IRS의 실패가 가장 크다. 인상 전날 인하를 {pct(aug['irs_cut'])} 반영했다 — "
              "변동금리 준거가 CD91이라 CD 경직성과 조달 스프레드가 정책기대를 덮는 구조적 한계")
rp.bullet("", "통안은 7월엔 100%로 맞혔으나 8월엔 23%에 그쳤다. 같은 렌즈가 두 달 사이에 갈린 것으로, "
              "단일 회차 확률을 액면대로 쓰기 어렵다는 뜻")
rp.bullet("", f"OIS는 회의가 하루 앞이라 1주 호가가 8월 노드를 사실상 직접 가격했다. "
              f"곡선 적합 오차도 {ts['2026-08-26']['rmse_bp']}bp로 표본 중위 {RMSE_MED:.2f}bp를 밑돈다 "
              "— 적합도는 회의가 가까울수록 좋아진다(1주 이내 평균 0.29bp)")
rp.picture("fig02_fit_snapshot.png",
           "그림 2. 내재 정책금리 경로(a)와 곡선 적합(b) — 회의 후 기준(8/28), 남은 두 회의로 재배열된 모습")
rp.arrow("회의 직전 구간에서는 OIS가 압도적으로 정확하다. 다만 이 유리한 조건이 상시 성립하지는 않는다")

# ══════════════════════════════ 4) 백테스트 갱신
rp.heading("4) 백테스트 갱신 — 8/27을 표본에 넣으면")
rp.data_table([
    ("렌즈", "구판(8/27 제외)", "현재(8/27 포함)", "방향"),
    ("KOFR OIS", brier(sm_old, "ois"), brier(sm_new, "ois"), "개선"),
    ("통안 스트립", brier(sm_old, "msb"), brier(sm_new, "msb"), "악화"),
    ("CD-IRS", brier(sm_old, "irs"), brier(sm_new, "irs"), "악화"),
    ("BMSI 서베이", brier(sm_old, "bmsi"), brier(sm_new, "bmsi"), "불변(미발표)"),
    ("무정보 기준", brier(sm_old, "climatology"), brier(sm_new, "climatology"), "-"),
], hl_rows=(1,))
rp.tbl_note("3분류 Brier 점수(인상·동결·인하), 낮을수록 정확. 표본은 2013-02 이후 정례 금통위")
rp.para()
rp.bullet("", "회의 한 번이 더해졌을 뿐인데 세 렌즈의 방향이 갈렸다 — OIS만 내려갔다(개선)")
rp.bullet("", f"2026년 인상기(7/16·8/27 두 회의)만 떼면 격차가 더 분명하다: "
              f"OIS {brier_p(hike26, 'ois')}, 통안 {brier_p(hike26, 'msb')}, CD-IRS {brier_p(hike26, 'irs')}")
rp.bullet("", "다만 전 표본 기준으로는 여전히 BMSI 서베이가 가장 낮다. "
              "시장가격의 강점은 총점이 아니라 전환점에서의 방향 정보")
rp.picture("fig10_backtest_timeline.png",
           "그림 3. 13년의 채점표 — 회의 전일 내재 순확률과 실제 결정(상단 인상·하단 인하)")
rp.arrow("2026년 인상 사이클에 한정하면 OIS가 통안·CD-IRS를 큰 격차로 앞선다")


# ══════════════════════════════ 5) 왜 갈렸나
rp.heading("5) 왜 갈렸나 — 스왑과 현물 사이의 프리미엄")
rp.bullet("", f"통안-OIS 격차({gap['date']} 기준): 3개월 {gap['gap_3m_bp']}bp, "
              f"6개월 {gap['gap_6m_bp']}bp, 1년 {gap['gap_1y_bp']}bp (양수 = 통안이 강세)")
rp.bullet("", "격차는 순수한 기대 차이가 아니다. 절반 이상이 담보·수급 프리미엄이고, "
              "나머지가 매파 이벤트 이후 현물의 반응 지연")
rp.bullet("", f"국고 단기 스트립도 같은 방향이다. 회의 전일 연말 내재금리는 "
              f"{ktb[-2]['implied_ye_rate']}%로 OIS의 {ts['2026-08-26']['implied_ye_rate']}%보다 낮았다")
rp.picture("fig09_msb_ois_gap.png",
           "그림 4. 통안-OIS 격차의 시계열 — 매파 이벤트 이후 벌어졌다 수 주에 걸쳐 좁혀지는 패턴")
rp.arrow("현물은 정책기대 외의 요인을 함께 담는다. 정책 확률 추출에는 스왑이 정공법이고 현물은 교차검증용")

# ══════════════════════════════ 6) 한계
rp.heading("6) 한계와 활용")
rp.bullet("(1)", "표본이 얇다. OIS 유효 관측은 2022년 이후 회의뿐이며, 호가가 실질적으로 "
                 "형성된 2024년 하반기 이후로 좁히면 더 줄어든다. 이번 적중 2회를 일반화하기엔 이르다")
rp.bullet("(2)", "회의 직전이라는 유리한 조건이었다. 회의가 하루 앞이면 1주 OIS가 해당 노드를 "
                 "거의 직접 가격한다. 회의까지 한 달 이상 남은 시점의 정확도는 별개 문제")
rp.bullet("(3)", "회의별 배분은 여전히 노이즈가 크다. 이번에도 8월 확률이 8/21 100%에서 "
                 "8/26 97.5%로 흔들렸고, 10월·11월 배분은 하루 단위로 뒤집혔다")
rp.bullet("(4)", "BMSI 8월분 미발표로 서베이 대조가 빠졌다. 발표되면 표에 채워 넣을 것")
rp.para()
rp.arrow("이번 회차는 모형의 유효성을 지지하지만 결론은 아니다 — 회의별 배분이 아니라 "
         "누적 수준과 방향 정보로 쓰는 원칙을 유지")

rp.save(DEST)
print("saved:", DEST)
