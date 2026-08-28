# Raw data

이 폴더의 CSV는 분석 전 원자료입니다. 숫자 변환, 결측치 보간, 계절조정, 리베이스,
빈도 변환 또는 스프레드 계산을 하지 않습니다.

## 하위 폴더 구성

| 폴더 | 내용 | 주기 | 출처 |
|---|---|---|---|
| `ecos/` | 거시·금리 시계열(월평균 중심) | 월·분기 | ECOS 공식 OpenAPI |
| `ecos_daily/` | 금리곡선 일별 종가 15종 + 통합 패널 | 일별 | ECOS 내부 조회 서비스(무인증) |
| `kofia/` | 채권정보센터 시가평가(민평) 커브 13개 만기 | 일별 | KOFIA BISBndSrtPrcSrchSO |
| `infomax/` | KRW IRS 제로커브, KOFR OIS 호가(매수/매도/MID) | 일별 | 연합인포맥스 단말(수기 반입) |
| `bok/` | 금통위 회의일 캘린더, 기준금리 변경 이력 | 이벤트 | 한국은행 웹 |
| `surveys/` | 금투협 BMSI 기준금리 문항 응답 비율 | 월별 | 금투협 보도자료·언론 보도 |

**주의: `ecos/`의 금리 시리즈는 월평균입니다.** 회의일 기준 분석(계단함수 모델,
백테스트)에는 반드시 `ecos_daily/`의 일별 종가를 사용하십시오. 월평균 파일은
거시 통제변수와 장기 추세 확인용입니다.

## 다시 내려받기

```powershell
python scripts/download_daily_rates.py        # 일별 금리곡선 (무인증, 전 구간 일괄)
python scripts/download_kofia_curves.py       # 채권정보센터 민평 커브
python scripts/download_bok_policy_calendar.py
python scripts/download_rawdata.py            # 월평균·거시 (ECOS OpenAPI)
python scripts/validate_rawdata.py            # 중복·결측·해시·기간 검증
```

인증키가 없으면 ECOS의 `sample` 키로 10행씩 나누어 받습니다. 개인 인증키가 있으면
값을 화면에 출력하지 말고 환경변수로만 설정하십시오. 훨씬 적은 요청으로 끝납니다.

```powershell
$env:ECOS_API_KEY='발급받은_키'
python scripts/download_rawdata.py
python scripts/download_rawdata.py --only bok_policy_rate_monthly ktb_3y_monthly
```

`infomax/` 2종은 자동 수집 대상이 아닙니다. 연합인포맥스 단말에서 기존 워크북을 열어
재계산한 뒤 같은 이름으로 덮어쓰십시오. `D1`이 `=TODAY()`라 조회 종료일이 자동으로
오늘이 되고, 시작일·만기 구성·정렬은 그대로 보존됩니다. 시트 구조(1행 조회조건,
2행 IMDH 수식, 3행 헤더, 4행부터 데이터)는 파서가 행 번호로 읽으므로 바뀌면 안 됩니다.
자세한 레이아웃은 각 파일 옆의 `.meta.json`에 있습니다.

## 파일 확인 순서

1. 각 폴더의 `manifest.csv`: 성공 여부, 행 수, 최초·최종 시점, 파일 해시
2. 각 CSV 옆의 `.meta.json`: 출처, 조회조건, 수집시각과 변환 여부
3. `ecos/download_summary.json`: 전체 수집 성공·실패 개수

CSV는 한국어가 Excel에서도 깨지지 않도록 UTF-8 BOM으로 저장됩니다.

## 일별 데이터 정합성 (2026-08-07 검증)

- `ecos_daily`는 공식 OpenAPI와 동일한 값을 주는 ECOS 웹 내부 서비스에서 받았고,
  통안 91일·1년, 국고 3년의 최근 값이 KOFIA 최종호가 15:30 회차와 완전 일치함을
  확인했습니다.
- `kofia/` 시가평가(민평 평균)와 `ecos_daily/`(최종호가)는 **다른 상품**입니다.
  국고 3년 기준 평균 절대차 약 0.5bp, 최대 3.4bp — 교차검증용으로만 비교하십시오.
- 2013년 이후 금통위 개최일 126일 전부에 통안 91일 일별 값이 존재합니다
  (백테스트 결측 없음).
- `ecos_daily`의 기준금리(722Y001 일별)는 공표가 약 2영업일 지연됩니다. 최신
  기준금리는 `bok/policy_rate_change_history.csv`를 정본으로 사용하십시오.

## 중요한 시계열 단절

- KOFR는 2021년 11월 이후만 존재합니다. 그 이전 콜금리와 단순 연결하지 마십시오.
- 국고채 2년물은 2021년 3월 이후입니다.
- CD 산출방식은 2023년 변경되었으므로 모형에 구조변화 더미를 두는 것이 좋습니다.
- 주택가격지수는 기준시점 개편으로 과거 값이 수정될 수 있습니다.
- ECOS의 미국 단기금리(`IR3TIB/USA`)는 2020년 4월 관측치가 공란입니다. 원자료에는
  이를 임의 보간하지 않았고 검증보고서에서 경고로 남겼습니다.
- 각 월의 자료는 발표시차가 다르므로 실시간 백테스트에서는 당시 공표 가능일을
  별도로 관리해야 합니다.

파생변수와 정제 데이터는 추후 `data/processed`에 작성하고 이 원자료는 수정하지
않는 것을 권장합니다.
