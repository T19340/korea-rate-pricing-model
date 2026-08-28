# -*- coding: utf-8 -*-
"""Download daily mark-to-market (시가평가기준수익률) curves from the KOFIA Bond
Information Service (채권정보센터, kofiabond.or.kr).

Adds the tenors the ECOS daily table does not carry: MSB 3M/6M/9M and the KTB
par matrix (3M..30Y) used to build month-end zero curves for the AFNS model.

Evaluator regime: until 2023-01-06 the grid carries 4 evaluators
(NICE·KAP·KIS·FN), from 2023-01-09 five (adding EG) plus the evaluator
average requested with creditEstOrgCd=A20000. Values are daily closes.

Outputs (convention matches download_rawdata.py):
  rawdata/kofia/valuation/<slug>.csv        tidy: date + evaluator columns
  rawdata/kofia/valuation/<slug>.meta.json
  rawdata/kofia/manifest.csv
  rawdata/kofia/kofia_curve_panel_daily.csv wide evaluator_avg panel (all tenors)
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "rawdata" / "kofia"
URL = "https://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/"
REF = ("https://www.kofiabond.or.kr/websquare/websquare.html"
       "?w2xPath=/xml/startest/BISBndSrtPrcTrm.xml")

EVAL_COLS = ["nice_pni", "kap", "kis", "fn", "eg", "evaluator_avg", "kofia"]
SEGMENTS = [
    ("20130101", "20230106", "", ["A10002", "A10003", "A10004", "A10005", ""]),
    ("20230109", None, "A20000", ["A10002", "A10003", "A10004", "A10005", "A10006"]),
]

# (slug, bond_type_code, tenor_code, description)
INSTRUMENTS = [
    ("msb_3m_val_daily", "4000000", "0003", "통안증권 3개월 민평 시가평가(교차검증용)"),
    ("msb_6m_val_daily", "4000000", "0006", "통안증권 6개월 민평 시가평가 — ECOS 일별표에 없는 핵심 만기"),
    ("msb_9m_val_daily", "4000000", "0009", "통안증권 9개월 민평 시가평가(존재 시)"),
    ("ktb_3m_val_daily", "1010000", "0003", "국고채 3개월 민평 — AFNS 단기구간"),
    ("ktb_6m_val_daily", "1010000", "0006", "국고채 6개월 민평 — AFNS 단기구간"),
    ("ktb_9m_val_daily", "1010000", "0009", "국고채 9개월 민평 — AFNS 단기구간"),
    ("ktb_1y_val_daily", "1010000", "0100", "국고채 1년 민평(ECOS 교차검증)"),
    ("ktb_18m_val_daily", "1010000", "0150", "국고채 1년6개월 민평"),
    ("ktb_2y_val_daily", "1010000", "0200", "국고채 2년 민평(ECOS 2021-03 이전 구간 보강)"),
    ("ktb_30m_val_daily", "1010000", "0250", "국고채 2년6개월 민평"),
    ("ktb_3y_val_daily", "1010000", "0300", "국고채 3년 민평(ECOS 교차검증)"),
    ("ktb_5y_val_daily", "1010000", "0500", "국고채 5년 민평"),
    ("ktb_10y_val_daily", "1010000", "1000", "국고채 10년 민평"),
    ("ktb_20y_val_daily", "1010000", "2000", "국고채 20년 민평"),
    ("ktb_30y_val_daily", "1010000", "3000", "국고채 30년 민평"),
]


def pf_call(dto_xml: str, timeout: int = 300) -> str:
    body = (
        '<?xml version="1.0" encoding="utf-8"?>\n<message>\n  <proframeHeader>\n'
        "    <pfmAppName>BIS-KOFIABOND</pfmAppName>\n"
        "    <pfmSvcName>BISBndSrtPrcSrchSO</pfmSvcName>\n"
        "    <pfmFnName>selectTrm</pfmFnName>\n"
        "  </proframeHeader>\n  <systemHeader></systemHeader>\n"
        f"{dto_xml}\n</message>"
    )
    fd, path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    Path(path).write_text(body, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["curl", "-sS", "--ssl-no-revoke", "-m", str(timeout), "-X", "POST",
             "-H", "Content-Type: application/xml; charset=UTF-8",
             "-H", "Referer: " + REF,
             "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "Chrome/120 Safari/537.36",
             "--data-binary", "@" + path, URL],
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
        return proc.stdout.decode("utf-8", "replace")
    finally:
        os.unlink(path)


def query_pairs(start: str, end: str, org: str, evaluators: list[str],
                pairs: list[tuple[str, str]]) -> list[dict]:
    dto = ("  <BISBndSrtPrcTrmDTO>\n"
           f"    <standardDt1>{start}</standardDt1>\n"
           f"    <standardDt2>{end}</standardDt2>\n"
           f"    <creditEstOrgCd>{org}</creditEstOrgCd>\n")
    for i, code in enumerate(evaluators, start=1):
        dto += f"    <val{i}>{code}</val{i}>\n"
    slot = 31
    for bond_type, tenor in pairs:
        dto += f"    <val{slot}>{bond_type}</val{slot}>\n"
        slot += 1
        dto += f"    <val{slot}>{tenor}</val{slot}>\n"
        slot += 1
    dto += "  </BISBndSrtPrcTrmDTO>"
    text = pf_call(dto)
    rows = []
    for block in re.findall(r"<BISBndSrtPrcTrmDTO>(.*?)</BISBndSrtPrcTrmDTO>", text, re.S):
        record = dict(re.findall(r"<([a-zA-Z0-9_]+)>([^<]*)</\1>", block))
        if re.match(r"^\d{8}$", record.get("standardDt", "")):
            rows.append(record)
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    today = datetime.now().strftime("%Y%m%d")
    downloaded_at = datetime.now(timezone.utc).isoformat()
    # slug -> {iso_date: {col: value}}
    data: dict[str, dict[str, dict[str, str]]] = {s[0]: {} for s in INSTRUMENTS}

    for group_start in range(0, len(INSTRUMENTS), 2):
        group = INSTRUMENTS[group_start:group_start + 2]
        pairs = [(bond, tenor) for _, bond, tenor, _ in group]
        for seg_start, seg_end, org, evaluators in SEGMENTS:
            end = seg_end or today
            rows = query_pairs(seg_start, end, org, evaluators, pairs)
            print(f"  pairs {[s for s, *_ in group]} {seg_start}..{end}: {len(rows)} rows")
            for record in rows:
                raw_date = record["standardDt"]
                iso = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                for gi, (slug, *_rest) in enumerate(group):
                    entry = {}
                    for ci, col in enumerate(EVAL_COLS):
                        value = (record.get(f"val{gi * 7 + ci + 1}") or "").strip()
                        entry[col] = value
                    if any(entry.values()):
                        data[slug][iso] = entry

    valuation_dir = OUTPUT_DIR / "valuation"
    valuation_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for slug, bond_type, tenor, description in INSTRUMENTS:
        series = data[slug]
        dates = sorted(series)
        if not dates:
            print(f"  {slug}: EMPTY (tenor not offered) — skipped")
            manifest.append({
                "status": "empty", "slug": slug, "category": "valuation",
                "description": description, "stat_code": f"{bond_type}/{tenor}",
                "cycle": "D", "items": tenor, "rows": 0, "first_time": "",
                "last_time": "", "downloaded_at_utc": downloaded_at,
                "relative_path": "", "sha256": "",
                "error": "no rows returned for this bond-type/tenor",
            })
            continue
        csv_path = valuation_dir / f"{slug}.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date"] + EVAL_COLS)
            for date in dates:
                writer.writerow([date] + [series[date].get(c, "") for c in EVAL_COLS])
        meta = {
            "source_name": "KOFIA Bond Information Service 시가평가기준수익률(기간물)",
            "source_url": "https://www.kofiabond.or.kr/",
            "endpoint": URL,
            "service": "BIS-KOFIABOND / BISBndSrtPrcSrchSO / selectTrm",
            "downloaded_at_utc": downloaded_at,
            "query": {"bond_type_code": bond_type, "tenor_code": tenor,
                      "segments": [
                          {"range": [s, e or today], "creditEstOrgCd": o,
                           "evaluators": ev} for s, e, o, ev in SEGMENTS]},
            "description": description,
            "columns": {"nice_pni": "NICE피앤아이", "kap": "한국자산평가",
                        "kis": "키스자산평가", "fn": "에프엔자산평가",
                        "eg": "이지자산평가(2023-01-09부터)",
                        "evaluator_avg": "평가사 평균", "kofia": "협회 고시"},
            "row_count": len(dates),
            "first_time": dates[0], "last_time": dates[-1],
            "encoding": "UTF-8 with BOM",
            "transformation": "None beyond reshaping service rows to date x evaluator columns.",
        }
        (valuation_dir / f"{slug}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest.append({
            "status": "ok", "slug": slug, "category": "valuation",
            "description": description, "stat_code": f"{bond_type}/{tenor}",
            "cycle": "D", "items": tenor, "rows": len(dates),
            "first_time": dates[0], "last_time": dates[-1],
            "downloaded_at_utc": downloaded_at,
            "relative_path": str(csv_path.relative_to(PROJECT_ROOT)),
            "sha256": sha256(csv_path), "error": "",
        })
        print(f"  {slug}: {len(dates)} rows ({dates[0]}..{dates[-1]})")

    manifest_path = OUTPUT_DIR / "manifest.csv"
    fields = ["status", "slug", "category", "description", "stat_code", "cycle",
              "items", "rows", "first_time", "last_time", "downloaded_at_utc",
              "relative_path", "sha256", "error"]
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)

    # wide evaluator_avg panel
    ok_slugs = [s for s, *_ in INSTRUMENTS if data[s]]
    all_dates = sorted({d for s in ok_slugs for d in data[s]})
    panel_path = OUTPUT_DIR / "kofia_curve_panel_daily.csv"
    header = ["date"] + [s.removesuffix("_val_daily") for s in ok_slugs]
    with panel_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for date in all_dates:
            writer.writerow([date] + [data[s].get(date, {}).get("evaluator_avg", "")
                                      for s in ok_slugs])
    (OUTPUT_DIR / "kofia_curve_panel_daily.meta.json").write_text(json.dumps({
        "downloaded_at_utc": downloaded_at,
        "description": "Wide panel of evaluator-average (평가사 평균) valuation yields; "
                       "input for month-end AFNS zero-curve construction.",
        "row_count": len(all_dates),
        "first_time": all_dates[0] if all_dates else None,
        "last_time": all_dates[-1] if all_dates else None,
        "columns": header, "sha256": sha256(panel_path),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"panel: {len(all_dates)} rows -> {panel_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
