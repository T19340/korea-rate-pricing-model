#!/usr/bin/env python3
"""Download the configured raw series from the Bank of Korea ECOS API.

The script works with the ECOS ``sample`` key, which is limited to 10 rows per
request, and automatically switches to larger pages when ECOS_API_KEY is set.
No data transformations are performed: API rows are written as returned.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "series.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "rawdata" / "ecos"
USER_AGENT = "korea-rate-pricing-model/1.0 (research data download)"


def current_end_time(cycle: str) -> str:
    now = datetime.now()
    if cycle == "D":
        return now.strftime("%Y%m%d")
    if cycle == "M":
        return now.strftime("%Y%m")
    if cycle == "Q":
        quarter = (now.month - 1) // 3 + 1
        return f"{now.year}Q{quarter}"
    if cycle == "A":
        return str(now.year)
    raise ValueError(f"Unsupported cycle: {cycle}")


def api_url(
    base_url: str,
    api_key: str,
    start_index: int,
    end_index: int,
    spec: dict[str, Any],
    end_time: str,
) -> str:
    parts = [
        base_url.rstrip("/"),
        quote(api_key, safe=""),
        "json",
        "kr",
        str(start_index),
        str(end_index),
        quote(spec["stat_code"], safe=""),
        quote(spec["cycle"], safe=""),
        quote(spec["start_time"], safe=""),
        quote(end_time, safe=""),
    ]
    parts.extend(quote(str(item), safe="") for item in spec.get("items", []))
    return "/".join(parts)


def redacted_url(url: str, api_key: str) -> str:
    return url.replace(f"/{quote(api_key, safe='')}/", "/<ECOS_API_KEY>/")


def get_json(url: str, attempts: int = 5) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(0.75 * (2 ** (attempt - 1)), 6.0))
    raise RuntimeError(f"ECOS request failed after {attempts} attempts: {last_error}")


def extract_response(payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    if "StatisticSearch" in payload:
        body = payload["StatisticSearch"]
        return int(body["list_total_count"]), list(body.get("row", []))
    if "RESULT" in payload:
        result = payload["RESULT"]
        raise RuntimeError(f"ECOS {result.get('CODE')}: {result.get('MESSAGE')}")
    raise RuntimeError(f"Unexpected ECOS response keys: {list(payload)}")


def fetch_series(
    base_url: str,
    api_key: str,
    page_size: int,
    workers: int,
    spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], str, str]:
    end_time = spec.get("end_time") or current_end_time(spec["cycle"])
    first_url = api_url(base_url, api_key, 1, page_size, spec, end_time)
    total, first_rows = extract_response(get_json(first_url))
    if total == 0:
        return [], end_time, redacted_url(first_url, api_key)

    pages: dict[int, list[dict[str, Any]]] = {1: first_rows}
    starts = list(range(page_size + 1, total + 1, page_size))

    def fetch_page(start_index: int) -> tuple[int, list[dict[str, Any]]]:
        end_index = min(start_index + page_size - 1, total)
        url = api_url(base_url, api_key, start_index, end_index, spec, end_time)
        _, rows = extract_response(get_json(url))
        return start_index, rows

    if starts:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(fetch_page, start) for start in starts]
            for future in as_completed(futures):
                start_index, rows = future.result()
                pages[start_index] = rows

    rows: list[dict[str, Any]] = []
    for start_index in sorted(pages):
        rows.extend(pages[start_index])
    if len(rows) != total:
        raise RuntimeError(f"Expected {total} rows, received {len(rows)}")
    return rows, end_time, redacted_url(first_url, api_key)


def ordered_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "STAT_CODE",
        "STAT_NAME",
        "ITEM_CODE1",
        "ITEM_NAME1",
        "ITEM_CODE2",
        "ITEM_NAME2",
        "ITEM_CODE3",
        "ITEM_NAME3",
        "ITEM_CODE4",
        "ITEM_NAME4",
        "UNIT_NAME",
        "WGT",
        "TIME",
        "DATA_VALUE",
    ]
    present = {key for row in rows for key in row}
    return [key for key in preferred if key in present] + sorted(present - set(preferred))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ordered_fieldnames(rows)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "status",
        "slug",
        "category",
        "description",
        "stat_code",
        "cycle",
        "items",
        "rows",
        "first_time",
        "last_time",
        "downloaded_at_utc",
        "relative_path",
        "sha256",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return {row["slug"]: row for row in csv.DictReader(handle)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", nargs="*", help="Download only the named slugs")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    base_url = config["api_base_url"]
    api_key = os.environ.get("ECOS_API_KEY", "sample").strip() or "sample"
    using_sample = api_key == "sample"
    page_size = 10 if using_sample else 1000
    workers = max(1, min(args.workers, 8))
    selected = set(args.only or [])
    all_specs = config["series"]
    specs = [s for s in all_specs if not selected or s["slug"] in selected]
    unknown = selected - {s["slug"] for s in specs}
    if unknown:
        print(f"Unknown series slug(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "manifest.csv"
    manifest_by_slug = read_manifest(manifest_path) if selected else {}
    config_order = [spec["slug"] for spec in all_specs]
    failures = 0
    downloaded_at = datetime.now(timezone.utc).isoformat()
    print(
        f"Downloading {len(specs)} ECOS series with "
        f"{'sample key (10-row pages)' if using_sample else 'ECOS_API_KEY'}..."
    )

    for index, spec in enumerate(specs, start=1):
        slug = spec["slug"]
        category_dir = args.output / spec["category"]
        csv_path = category_dir / f"{slug}.csv"
        meta_path = category_dir / f"{slug}.meta.json"
        record = {
            "status": "error",
            "slug": slug,
            "category": spec["category"],
            "description": spec["description"],
            "stat_code": spec["stat_code"],
            "cycle": spec["cycle"],
            "items": "|".join(spec.get("items", [])),
            "rows": 0,
            "first_time": "",
            "last_time": "",
            "downloaded_at_utc": downloaded_at,
            "relative_path": str(csv_path.relative_to(PROJECT_ROOT)),
            "sha256": "",
            "error": "",
        }
        try:
            rows, end_time, request_template = fetch_series(
                base_url, api_key, page_size, workers, spec
            )
            if not rows:
                raise RuntimeError("ECOS returned zero rows")
            write_csv(csv_path, rows)
            times = [str(row.get("TIME", "")) for row in rows if row.get("TIME")]
            metadata = {
                "source_name": config["source_name"],
                "source_url": config["source_url"],
                "downloaded_at_utc": downloaded_at,
                "request_template_first_page": request_template,
                "query": {**spec, "end_time": end_time},
                "row_count": len(rows),
                "first_time": min(times) if times else None,
                "last_time": max(times) if times else None,
                "encoding": "UTF-8 with BOM",
                "transformation": "None; ECOS row fields are preserved as returned.",
            }
            write_json(meta_path, metadata)
            record.update(
                status="ok",
                rows=len(rows),
                first_time=metadata["first_time"] or "",
                last_time=metadata["last_time"] or "",
                sha256=sha256(csv_path),
            )
            print(
                f"[{index:02d}/{len(specs):02d}] {slug}: "
                f"{len(rows)} rows ({record['first_time']}..{record['last_time']})"
            )
        except Exception as exc:  # keep a complete status manifest on partial failure
            failures += 1
            record["error"] = str(exc).replace("\n", " ")
            print(f"[{index:02d}/{len(specs):02d}] {slug}: ERROR {exc}", file=sys.stderr)
        manifest_by_slug[slug] = record
        ordered_manifest = [
            manifest_by_slug[name] for name in config_order if name in manifest_by_slug
        ]
        write_manifest(manifest_path, ordered_manifest)

    write_json(
        args.output / "download_summary.json",
        {
            "downloaded_at_utc": downloaded_at,
            "source_name": config["source_name"],
            "using_sample_key": using_sample,
            "series_requested_this_run": len(specs),
            "series_succeeded_this_run": len(specs) - failures,
            "series_failed_this_run": failures,
            "series_in_manifest": len(manifest_by_slug),
            "manifest": "manifest.csv",
        },
    )
    print(f"Finished: {len(specs) - failures} succeeded, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
