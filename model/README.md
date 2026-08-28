# model/ — 금통위 내재 인상확률 분석과 애널리스트 리포트

`rawdata/`를 입력으로 2026년 8·10·11월 금통위의 시장 내재 인상확률을 추정하고,
그 결과를 애널리스트 리포트(HTML)로 정리하는 작업 폴더입니다.

## 산출물

- **`report.html`** — 최종 리포트. **완전 자립형**: 외부 CDN·웹폰트 의존이 없어 오프라인·사내망에서도
  동일하게 렌더된다. 수식은 사전 렌더된 벡터(SVG, 클릭 시 LaTeX 복사 유지), Exhibit 12종 인라인 SVG,
  A4 인쇄 대응(약 34쪽). 3절에 한은 방법론(AFNS) 재현·대조와 여섯 렌즈 교차검증, 5절에 검증
  3종(통안-OIS 격차 분해·2013~2026 백테스트 124회·충격 산술 표본외 검증), 부록에 계산
  명세(데이터·모수·워크스루·β표·채점 규칙·재현 절차) 수록.
- `report_template.html` — 본문 원본(SVG 자리표시자 포함). 수정은 여기서 하고 `build_report.py`로 재조립
- **`study/`** — 방법론 학습 문서(blueprint-study-note 형식). 정본 `study/step_method_study.html`,
  단일 파일 배포본 `step_method_study_standalone.html`(3MB, 그림·수식 내장), 동반 워크북
  `step_method_workbook.ipynb`(셀 (a)~(h), 데이터 내장·어디서나 실행, 8/7 공표값 0.05bp 재현 +
  7/15 졸업시험). 재조립: `_build_notebook.py` → `_execute_notebook.py` → `_extra_figures.py` →
  `_assemble.py`(본문 `_body1~4.html` + 워크북 코드·출력 자동 삽입) → `_build_standalone.py`
- **`word/`** — 리포트의 Word 판 `금통위_인상확률_계단함수모형.docx`(8쪽, 부서 제안서 양식 —
  HY견고딕 제목 블록·HY신명조 개조식·"→" 결론·AFNS 재현·충격 분석·과거 사이클 검증 포함).
  재조립: `_build_word.py`. 양식 정의는 `_word_style.py`(`Report` 클래스)에 있고 세 빌더가 공유한다.
  회차 리포트는 `_build_word_review.py`(사후 검증판)·`_build_word_outlook.py`(전망판).
  렌더 검수는 `python _verify_any.py <docx> [...]` — Word COM으로 PDF를 뽑아 페이지 수·빈 페이지·그림 수를 본다.
  본문 수치는 전부 `output/`에서 읽는다(하드코딩 금지)
- **`figs_paper/`** — 학술 논문식(바탕 세리프·흑백·마커 구분) Exhibit 전체 세트 14종
  (PNG 300dpi + SVG). 생산: `scripts/make_figs_paper.py`(01~12) + `make_figs_pca.py`(13) +
  `m12_regime_profiles.py`(14). Word 판이 이 그림을 사용
- `output/` — 모델 산출 CSV·JSON (리포트의 모든 수치 근거)
- `figs/` — Exhibit SVG 12종 + 수식 SVG 4종 (`make_figs.py`·`make_figs_extra.py`·`make_figs_afns.py`·`make_figs_pca.py`·`m12_regime_profiles.py`·`make_equations.py` 산출)

## 스크립트 (실행 순서)

```powershell
cd model/scripts
python m1_step_function.py    # 모델 1: KOFR OIS 계단함수 → 회의별 내재 인상폭·확률
python m3_dns_expectation.py  # 모델 3: DNS-VAR 기대·기간프리미엄 분해 (AFNS 실무판)
python m4_event_study.py      # 모델 4: 금통위 이벤트 회귀 베타 + KIRI식 DNS 충격 전파
python m5_backtest.py         # 백테스트: 2013~2026 정례 금통위 124회, 통안·IRS·OIS vs BMSI (3분류 Brier)
python m5_extra_stats.py      # 백테스트 부속 통계 (기간별·OIS 유효표본·방향 감지)
python m6_gap.py              # 통안-OIS 격차 분해 (구조적 프리미엄·이벤트 반응 지연)
python m7_shock_validation.py # 충격 산술 표본외 검증 (2011-19 베타 → 2020-26 적용)
python m8_regime_analysis.py  # 국면 층화: 검증 상관·베타·전환점 감지를 사이클별로 분해
python m9_ktb_strip.py        # 국고 단기 스트립(3·6·9M·1Y 민평) 내재 반영도 — 누적만 유효, 배분 식별 불가
python m10_afns.py            # AFNS(한은 방법론, CDR 2011) 칼만 ML 재현 — 기대·프리미엄 분해, BOK 공표창 대조, 자가검증
python m11_irs_snapshot.py    # CD-IRS 스트립 스냅샷(렌즈 ⑥, 관행 잣대) — 연말 누적만 유효, 배분 식별 불가
python m12_regime_profiles.py # 국면별 당일 프로파일(실증/PCA/DNS 대조) — Exhibit 12 + Word 그림 8 생산
python make_appendix_data.py  # 부록 워크스루 수치 + Exhibit 11 (검증 산점도)
python make_figs.py           # Exhibit SVG 5종 (시계열·스냅샷·검증·경로·파급)
python make_figs_extra.py     # 해설 Exhibit 3종 (개념도·분해·시나리오 커브)
python make_figs_validation.py # 검증 Exhibit 2종 (격차 시계열·백테스트 타임라인)
python make_figs_afns.py      # AFNS 재현 Exhibit (figs/ex_afns.svg)
python make_figs_pca.py       # PCA 병행 재추정 Exhibit 2종(figs/ex_pca_*.svg) + Word용 fig13(figs_paper/)
python make_equations.py      # 수식 SVG 4종 (오프라인용 사전 렌더)
python build_report.py        # report_template.html + SVG → report.html
```

`common.py`가 rawdata 로딩을 담당한다. 데이터 갱신 후 위 순서로 다시 돌리면
리포트의 수치 근거(output/)와 그림이 재계산된다(본문 텍스트의 수치는 수동 갱신).

## 모델 요약

| 모델 | 입력 | 산출 | 핵심 파일 |
|---|---|---|---|
| m1 계단함수 | KOFR OIS 1주~1년 MID | 회의별 Δbp·확률, 연말 내재 금리, 일별 시계열 | m1_snapshot / m1_timeseries |
| m1 교차검증 | 통안 91일·6개월·1년(프리미엄 차감) | 동일 구조의 2차 의견 | m1_msb_crosscheck |
| m3 DNS-VAR | 민평 국고 월말 커브(2013~) | 기대 단기금리 경로·기간프리미엄 | m3_expected_path / m3_meta |
| m4 충격 분석 | 금통위 150회 이벤트 + m3의 λ | 만기별 파급 베타·시나리오 표 | m4_betas / m4_scenarios |

## 주요 가정 (리포트 5절과 동일)

25bp 격자, 2027년 금통위 일정은 분기 노드 가정, OIS 기간프리미엄 무보정(단기 시계 한정 사용),
통안 프리미엄 φ는 BMSI 동결 응답 우세 구간에서 추정, KOFR OIS는 한국자금중개 호가(체결가 아님).
