# korea_rate_pricing_model — 작업 전 반드시 읽을 것

## 일일 입력은 자동으로 갱신된다 (손대지 말 것)

예약 작업 `RateModel_1720` 이 **평일 17:20** 에 아래를 전부 갱신한다.
래퍼는 `C:\Users\USER\Cowork\일일자동실행\1720_금리모형` 에 있다.

- `rawdata/infomax/KOFR_OIS.xlsx`, `IRS_KRWKRW.xlsx` — 인포맥스 연동 엑셀을 열었다 저장
- `rawdata/ecos_daily/` — `scripts/download_daily_rates.py` (통안·국고·CD·CP·콜·KOFR)
- `rawdata/kofia/valuation/` — `scripts/download_kofia_curves.py` (민평 커브)
- `rawdata/bok/` — `scripts/download_bok_policy_calendar.py` (금통위 일정·기준금리 이력)

즉 **m1(계단함수)·m6(통안-OIS 격차)·m9(국고 스트립) 의 입력은 늘 최신이다.**
수동으로 같은 일을 하려면 한 줄이면 된다:

```powershell
C:\Python314\python.exe "C:\Users\USER\Cowork\일일자동실행\1720_금리모형\update_model.py"
```

`scripts/download_rawdata.py`(ECOS 공식 OpenAPI, 키 필요)는 **일일 실행에 필요 없다.**
그것이 만드는 `rawdata/ecos/rates/kofr_daily.csv` 가 2026-08-05 에 멈춰 있는 것은
정상이다 — `common.kofr_daily()` 가 읽은 직후 더 최신인
`rawdata/ecos_daily/daily_rates_panel.csv` 로 덮어쓴다(겹치는 구간 값 전량 일치 확인).

---

## 리포트·백테스트·그림을 다시 만들 때는 먼저 이 게이트를 통과할 것

`report.html`·`build_report.py`·`m5_backtest.py`·`m12_regime_profiles.py`·
`make_figs*.py` 를 돌리는 작업이면 **아래 세 가지가 자동 갱신 대상이 아니다.**
그냥 재실행하면 낡은 입력으로 새 리포트를 찍게 된다.

### ① BMSI 서베이 — 수기 반입, 지금 낡아 있다

`rawdata/surveys/bmsi_policy_rate_survey.csv`

마지막 행이 **2026-07-16 금통위 대상**(2026-07-14 공표)이다. 그 뒤의
**2026-08-27 금통위 건이 비어 있다.** 백테스트의 "모형 vs 서베이" 대조와
검증 앵커가 이 파일에 걸려 있으므로, 리포트를 새로 만들 때는 먼저 최신
BMSI(금투협 채권시장지표)를 찾아 한 행 추가해야 한다. 열 구성은 파일 헤더와
기존 행의 `note` 서술 방식을 그대로 따를 것.

### ② PCA 입력 — 수기 반입, 2026-08-10 이후 갱신 없음

`rawdata/PCA/` 의 세 파일(`BOK_PCA_1D_1W_1M_Shock_Result_평균회귀X.xlsx`,
`BOK_PCA_25bp_Surprise_Report_5bp_Filter.docx`, `Zero Spot and Consensus.xlsx`).
`make_figs_pca.py`·`m12_regime_profiles.py` 가 쓴다. 새 충격 이벤트를 반영하려면
원본을 다시 받아야 한다.

### ③ `config/model.json` — 사이클이 바뀌면 사람이 고쳐야 한다

```
target_year          : 2026
assumed_future_nodes : ["2027-01-15", "2027-04-15", "2027-07-15"]
```

- 해가 바뀌면 `target_year` 를 올린다.
- **한국은행이 다음 해 금통위 일정을 공표하면 `assumed_future_nodes` 를 비운다.**
  비우지 않으면 실제 회의가 있는데도 산출물에 "(가정)" 노드가 계속 남는다.
  캘린더(`rawdata/bok/mpc_meeting_calendar.csv`)에 다음 해 일정이 들어왔는데
  이 목록이 비어 있지 않으면 그때가 고칠 때다.
- `irs_snapshot_asof` 는 리포트 재현용 고정값이다(환경변수 `ASOF_CAP` 로 덮어쓸 수 있음).

---

## 산출물을 재실행한 뒤에는 '구판 수치 소탕'이 필수다

재실행하면 백테스트·베타·격차 수치가 통째로 바뀐다. 그런데 본문 산문과 그림
주석에는 이전 판 숫자가 남아 독립 심사에서 출고 불가 판정을 받은 적이 있다
(v7→v8, 10여 곳). **재실행 후에는 개정 이력의 이전 값을 전부 grep 해서 남은
곳을 찾아 고칠 것.** 그림 주석은 하드코드하지 말고 산출물 CSV 에서 계산해
넣는다(`make_figs*.py` 가 그렇게 고쳐져 있다).

집계로 뒷받침하는 주장("인상 전환은 매번 서베이 우위" 같은)은 **쓰기 전에
다시 집계할 것.** 그 주장은 재집계에서 반례(2022-01·2026-07 시장 우위)가
나와 철회했다.

---

## 본문 수정 경로

`model/report.html` 을 직접 고치지 말 것. `model/report_template.html` 을 고치고
`model/scripts/build_report.py` 로 재조립한다.

## 사외 반출 금지

부서 내부 저장소다. 인포맥스 단말 데이터가 포함돼 있어 공개 전환·사외 공유를
하지 않는다(`LICENSE` 명시).
