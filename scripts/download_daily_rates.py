# -*- coding: utf-8 -*-
"""Download daily market-rate series from the Bank of Korea ECOS internal endpoint.

The monthly files under ``rawdata/ecos`` come from the official OpenAPI. Daily
series are too long for the 10-row ``sample`` key, so this script uses the
ECOS website's own JSON service (trxCd OSUUA02R01), which needs no key and
returns an arbitrary date range in one call. Values are identical to the
OpenAPI (verified against KTB 3Y over 3,140 business days in 2026-07).

Outputs (convention matches download_rawdata.py):
  rawdata/ecos_daily/rates/<slug>.csv        tidy: date,value
  rawdata/ecos_daily/rates/<slug>.meta.json  source, codes, range, row count
  rawdata/ecos_daily/manifest.csv            one row per series with sha256
  rawdata/ecos_daily/daily_rates_panel.csv   wide convenience panel (all series)
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "series_daily.json"
OUTPUT_DIR = PROJECT_ROOT / "rawdata" / "ecos_daily"
ENDPOINT = "https://ecos.bok.or.kr/serviceEndpoint/httpService/request.json"


def call_ecos(trx: str, data: dict, page_cnt: int = 100000, timeout: int = 300) -> dict:
    body = {
        "header": {
            "guidSeq": 1, "trxCd": trx, "scrId": "IECOSPCS01", "sysCd": "03",
            "fstChnCd": "WEB", "langDvsnCd": "KO", "envDvsnCd": "D",
            "sndRspnDvsnCd": "S", "sndDtm": datetime.now().strftime("%Y%m%d"),
            "ipAddr": "", "usrId": "IECOSPC", "pageNum": 1, "pageCnt": page_cnt,
        },
        "data": data,
    }
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    Path(path).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    try:
        proc = subprocess.run(
            ["curl", "-sS", "--ssl-no-revoke", "-m", str(timeout), "-X", "POST",
             "-H", "Content-Type: application/json",
             "-H", "Referer: https://ecos.bok.or.kr/",
             "--data-binary", "@" + path, ENDPOINT],
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
        return json.loads(proc.stdout.decode("utf-8", "replace"))
    finally:
        os.unlink(path)


def fetch_table(stat_code: str, stat_name: str, item_group: str,
                items: list[tuple[str, str]], start: str, end: str) -> list[dict]:
    ds_list = [
        {"dsId": stat_code, "dsNm": stat_name, "dsEngNm": stat_name,
         "dsItmId1": "ACC_ITEM", "dsItmGrpId1": item_group,
         "dsItmVal1": code, "dsItmValNm1": name, "dsItmValEngNm1": name}
        for code, name in items
    ]
    payload = {
        "statSrchDsList": ds_list,
        "statSrchFreqList": [{"freq": "D", "vlidStDtm": start, "vlidEndDtm": end}],
        "statTyp": "E", "statDataCvsnCdList": ["00"], "viewType": "01",
        "holidayYn": "Y",
    }
    response = call_ecos("OSUUA02R01", payload)
    detail = response.get("message", {}).get("detailMsgs")
    if detail:
        raise RuntimeError(str(detail))
    return json.loads(response["data"]["jsonCtnt"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y%m%d")
    segments = [(s, today if e == "today" else e) for s, e in config["download_segments"]]
    downloaded_at = datetime.now(timezone.utc).isoformat()

    # slug -> {date: value}; fetch each table once per segment with all items
    values: dict[str, dict[str, str]] = {}
    slug_info: dict[str, dict] = {}
    for table in config["tables"]:
        items = [(s["item"], s["slug"]) for s in table["series"]]
        for spec in table["series"]:
            slug_info[spec["slug"]] = {**spec, "stat_code": table["stat_code"],
                                       "stat_name": table["stat_name"]}
            values.setdefault(spec["slug"], {})
        code_to_slug = {code: slug for code, slug in items}
        for start, end in segments:
            print(f"[{table['stat_code']}] {start}..{end} ({len(items)} items)")
            rows = fetch_table(table["stat_code"], table["stat_name"],
                               table["item_group"], items, start, end)
            for row in rows:
                slug = code_to_slug.get(row.get("코드(계정항목)"))
                if slug is None:
                    continue
                for key, raw in row.items():
                    if len(key) == 8 and key.isdigit() and raw not in (None, "", "-"):
                        iso = f"{key[:4]}-{key[4:6]}-{key[6:]}"
                        values[slug][iso] = str(raw)

    # per-series tidy files + manifest
    rates_dir = OUTPUT_DIR / "rates"
    rates_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for slug, series_values in values.items():
        info = slug_info[slug]
        dates = sorted(series_values)
        if info.get("panel_only"):
            print(f"  {slug}: {len(dates)} rows (panel only, no per-series file)")
            continue
        csv_path = rates_dir / f"{slug}.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "value"])
            for date in dates:
                writer.writerow([date, series_values[date]])
        meta = {
            "source_name": config["source_name"],
            "source_url": config["source_url"],
            "endpoint": config["endpoint"],
            "endpoint_note": config["endpoint_note"],
            "downloaded_at_utc": downloaded_at,
            "query": {"stat_code": info["stat_code"], "stat_name": info["stat_name"],
                      "item_code": info["item"], "cycle": "D",
                      "segments": [list(s) for s in segments]},
            "description": info["description"],
            "row_count": len(dates),
            "first_time": dates[0] if dates else None,
            "last_time": dates[-1] if dates else None,
            "encoding": "UTF-8 with BOM",
            "transformation": "Wide (date-keyed) service response reshaped to tidy date,value rows; holiday placeholders ('-'/empty) dropped. Values otherwise as returned.",
        }
        meta_path = rates_dir / f"{slug}.meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        manifest.append({
            "status": "ok" if dates else "error",
            "slug": slug, "category": "rates_daily",
            "description": info["description"],
            "stat_code": info["stat_code"], "cycle": "D", "items": info["item"],
            "rows": len(dates),
            "first_time": dates[0] if dates else "",
            "last_time": dates[-1] if dates else "",
            "downloaded_at_utc": downloaded_at,
            "relative_path": str(csv_path.relative_to(PROJECT_ROOT)),
            "sha256": sha256(csv_path),
            "error": "" if dates else "no rows returned",
        })
        print(f"  {slug}: {len(dates)} rows ({dates[0] if dates else '-'}"
              f"..{dates[-1] if dates else '-'})")

    manifest_path = OUTPUT_DIR / "manifest.csv"
    fields = ["status", "slug", "category", "description", "stat_code", "cycle",
              "items", "rows", "first_time", "last_time", "downloaded_at_utc",
              "relative_path", "sha256", "error"]
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)

    # wide convenience panel (includes panel_only series such as KOFR)
    panel_slugs = [s["slug"] for t in config["tables"] for s in t["series"]]
    all_dates = sorted({d for slug in panel_slugs for d in values.get(slug, {})})
    panel_path = OUTPUT_DIR / "daily_rates_panel.csv"
    header = ["date"] + [("kofr" if slug == "kofr_panel_only" else slug.removesuffix("_daily"))
                         for slug in panel_slugs]
    with panel_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for date in all_dates:
            writer.writerow([date] + [values[slug].get(date, "") for slug in panel_slugs])
    panel_meta = {
        "downloaded_at_utc": downloaded_at,
        "description": "Convenience wide panel of all daily series in this directory. "
                       "kofr column mirrors rawdata/ecos/rates/kofr_daily.csv (canonical per-series file).",
        "row_count": len(all_dates),
        "first_time": all_dates[0] if all_dates else None,
        "last_time": all_dates[-1] if all_dates else None,
        "columns": header,
        "sha256": None,
    }
    panel_meta["sha256"] = sha256(panel_path)
    (OUTPUT_DIR / "daily_rates_panel.meta.json").write_text(
        json.dumps(panel_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"panel: {len(all_dates)} rows -> {panel_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
