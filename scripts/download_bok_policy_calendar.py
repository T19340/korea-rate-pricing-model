#!/usr/bin/env python3
"""Download official BOK policy-rate changes and MPC meeting dates."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "rawdata" / "bok"
SOURCE_PAGES = OUTPUT_ROOT / "source_pages"
RATE_URL = (
    "https://www.bok.or.kr/portal/singl/baseRate/list.do"
    "?dataSeCd=01&menuNo=200643"
)
MEETING_URL = (
    "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do"
    "?mtgSe=A&menuNo=200755&pYear={year}"
)
USER_AGENT = "korea-rate-pricing-model/1.0 (research data download)"


def fetch_text(url: str, attempts: int = 5) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=45) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(0.75 * (2 ** (attempt - 1)), 6.0))
    raise RuntimeError(f"BOK request failed after {attempts} attempts: {last_error}")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_rate_history(page: str) -> list[dict[str, object]]:
    pattern = re.compile(
        r'<tr>\s*<td[^>]*class="fb"[^>]*>\s*(\d{4})\s*</td>'
        r'\s*<td[^>]*>\s*(\d{1,2})월\s*(\d{1,2})일\s*</td>'
        r'\s*<td[^>]*>\s*([0-9.]+)\s*</td>',
        re.IGNORECASE | re.DOTALL,
    )
    rows: list[dict[str, object]] = []
    for year, month, day, rate in pattern.findall(page):
        effective = date(int(year), int(month), int(day))
        rows.append(
            {
                "effective_date": effective.isoformat(),
                "rate_percent": rate,
                "source_url": RATE_URL,
            }
        )
    rows.sort(key=lambda row: str(row["effective_date"]))
    if not rows:
        raise RuntimeError("No policy-rate rows were parsed from the BOK page")
    return rows


def parse_meetings(page: str, year: int, source_url: str) -> list[dict[str, object]]:
    pattern = re.compile(
        r'<th[^>]*scope="row"[^>]*>\s*(\d{1,2})월\s*(\d{1,2})일'
        r'(?:\(([^)]+)\))?\s*</th>',
        re.IGNORECASE | re.DOTALL,
    )
    rows: list[dict[str, object]] = []
    today = date.today()
    for month, day, weekday in pattern.findall(page):
        meeting_date = date(year, int(month), int(day))
        rows.append(
            {
                "meeting_date": meeting_date.isoformat(),
                "year": year,
                "month": int(month),
                "day": int(day),
                "weekday_korean": html.unescape(weekday.strip()),
                "status_at_download": "scheduled" if meeting_date > today else "held",
                "source_url": source_url,
            }
        )
    if not rows:
        raise RuntimeError(f"No MPC meeting dates were parsed for {year}")
    return rows


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SOURCE_PAGES.mkdir(parents=True, exist_ok=True)
    downloaded_at = datetime.now(timezone.utc).isoformat()

    rate_page = fetch_text(RATE_URL)
    rate_html_path = SOURCE_PAGES / "policy_rate_history.html"
    rate_html_path.write_text(rate_page, encoding="utf-8")
    rate_rows = parse_rate_history(rate_page)
    rate_csv_path = OUTPUT_ROOT / "policy_rate_change_history.csv"
    write_csv(
        rate_csv_path,
        ["effective_date", "rate_percent", "source_url"],
        rate_rows,
    )

    meeting_rows: list[dict[str, object]] = []
    page_records: list[dict[str, object]] = []
    for year in range(2008, date.today().year + 1):
        url = MEETING_URL.format(year=year)
        page = fetch_text(url)
        path = SOURCE_PAGES / f"mpc_meetings_{year}.html"
        path.write_text(page, encoding="utf-8")
        parsed = parse_meetings(page, year, url)
        meeting_rows.extend(parsed)
        page_records.append(
            {
                "year": year,
                "source_url": url,
                "relative_path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": digest(path),
                "meetings_parsed": len(parsed),
            }
        )
        print(f"{year}: {len(parsed)} MPC meeting date(s)")

    unique_meetings = {row["meeting_date"]: row for row in meeting_rows}
    meeting_rows = [unique_meetings[key] for key in sorted(unique_meetings)]
    meeting_csv_path = OUTPUT_ROOT / "mpc_meeting_calendar.csv"
    write_csv(
        meeting_csv_path,
        [
            "meeting_date",
            "year",
            "month",
            "day",
            "weekday_korean",
            "status_at_download",
            "source_url",
        ],
        meeting_rows,
    )

    manifest_rows = [
        {
            "dataset": "policy_rate_change_history",
            "rows": len(rate_rows),
            "first_date": rate_rows[0]["effective_date"],
            "last_date": rate_rows[-1]["effective_date"],
            "downloaded_at_utc": downloaded_at,
            "relative_path": str(rate_csv_path.relative_to(PROJECT_ROOT)),
            "sha256": digest(rate_csv_path),
            "source_url": RATE_URL,
        },
        {
            "dataset": "mpc_meeting_calendar",
            "rows": len(meeting_rows),
            "first_date": meeting_rows[0]["meeting_date"],
            "last_date": meeting_rows[-1]["meeting_date"],
            "downloaded_at_utc": downloaded_at,
            "relative_path": str(meeting_csv_path.relative_to(PROJECT_ROOT)),
            "sha256": digest(meeting_csv_path),
            "source_url": MEETING_URL.format(year="{year}"),
        },
    ]
    write_csv(
        OUTPUT_ROOT / "manifest.csv",
        [
            "dataset",
            "rows",
            "first_date",
            "last_date",
            "downloaded_at_utc",
            "relative_path",
            "sha256",
            "source_url",
        ],
        manifest_rows,
    )
    (OUTPUT_ROOT / "download_metadata.json").write_text(
        json.dumps(
            {
                "downloaded_at_utc": downloaded_at,
                "source": "Bank of Korea",
                "policy_rate_changes": len(rate_rows),
                "mpc_meetings": len(meeting_rows),
                "source_pages": page_records,
                "transformation": (
                    "HTML table cells were mechanically parsed into ISO dates and CSV; "
                    "no rates or meeting dates were inferred."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Finished: {len(rate_rows)} policy-rate changes and "
        f"{len(meeting_rows)} MPC meeting dates."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
