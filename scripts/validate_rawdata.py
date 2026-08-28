#!/usr/bin/env python3
"""Run deterministic integrity checks on downloaded ECOS raw files."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "series.json"
RAW_ROOT = PROJECT_ROOT / "rawdata" / "ecos"
MANIFEST_PATH = RAW_ROOT / "manifest.csv"
BOK_ROOT = PROJECT_ROOT / "rawdata" / "bok"
BOK_MANIFEST_PATH = BOK_ROOT / "manifest.csv"
REPORT_PATH = PROJECT_ROOT / "rawdata" / "validation_report.json"
REQUIRED_COLUMNS = {"STAT_CODE", "ITEM_CODE1", "TIME", "DATA_VALUE"}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_period(value: str, cycle: str) -> tuple[int, int, int]:
    if cycle == "D" and re.fullmatch(r"\d{8}", value):
        parsed = datetime.strptime(value, "%Y%m%d").date()
        return parsed.year, parsed.month, parsed.day
    if cycle == "M" and re.fullmatch(r"\d{6}", value):
        return int(value[:4]), int(value[4:]), 1
    if cycle == "Q" and re.fullmatch(r"\d{4}Q[1-4]", value):
        return int(value[:4]), (int(value[-1]) - 1) * 3 + 1, 1
    raise ValueError(f"invalid {cycle} period: {value}")


def period_index(value: str, cycle: str) -> int:
    year, month, day = parse_period(value, cycle)
    if cycle == "D":
        return date(year, month, day).toordinal()
    if cycle == "M":
        return year * 12 + month - 1
    if cycle == "Q":
        return year * 4 + (month - 1) // 3
    raise ValueError(cycle)


def allowed_freshness_lag(cycle: str) -> int:
    return {"D": 10, "M": 3, "Q": 2}[cycle]


def current_period_index(cycle: str) -> int:
    today = date.today()
    if cycle == "D":
        return today.toordinal()
    if cycle == "M":
        return today.year * 12 + today.month - 1
    if cycle == "Q":
        return today.year * 4 + (today.month - 1) // 3
    raise ValueError(cycle)


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    specs = {spec["slug"]: spec for spec in config["series"]}
    with MANIFEST_PATH.open("r", newline="", encoding="utf-8-sig") as handle:
        manifest = {row["slug"]: row for row in csv.DictReader(handle)}

    checks: list[dict[str, Any]] = []
    error_count = 0
    warning_count = 0

    def add(slug: str, severity: str, check: str, message: str) -> None:
        nonlocal error_count, warning_count
        checks.append(
            {"slug": slug, "severity": severity, "check": check, "message": message}
        )
        if severity == "error":
            error_count += 1
        elif severity == "warning":
            warning_count += 1

    missing_manifest = sorted(set(specs) - set(manifest))
    extra_manifest = sorted(set(manifest) - set(specs))
    for slug in missing_manifest:
        add(slug, "error", "manifest_coverage", "configured series is absent from manifest")
    for slug in extra_manifest:
        add(slug, "warning", "manifest_coverage", "manifest series is absent from config")

    profile: list[dict[str, Any]] = []
    for slug, spec in specs.items():
        entry = manifest.get(slug)
        if entry is None:
            continue
        path = PROJECT_ROOT / entry["relative_path"]
        meta_path = path.with_suffix(".meta.json")
        if entry["status"] != "ok":
            add(slug, "error", "download_status", entry.get("error") or "download failed")
            continue
        if not path.exists():
            add(slug, "error", "file_exists", f"missing file: {path}")
            continue
        if not meta_path.exists():
            add(slug, "error", "metadata_exists", f"missing metadata: {meta_path}")
            continue

        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            columns = set(reader.fieldnames or [])
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            add(slug, "error", "required_columns", f"missing: {missing_columns}")

        actual_hash = file_hash(path)
        if actual_hash != entry["sha256"]:
            add(slug, "error", "sha256", "file hash differs from manifest")
        if int(entry["rows"]) != len(rows) or int(meta["row_count"]) != len(rows):
            add(
                slug,
                "error",
                "row_count",
                f"csv={len(rows)}, manifest={entry['rows']}, metadata={meta['row_count']}",
            )

        times = [row.get("TIME", "").strip() for row in rows]
        empty_times = sum(not value for value in times)
        duplicate_times = len(times) - len(set(times))
        if empty_times:
            add(slug, "error", "time_completeness", f"{empty_times} empty TIME values")
        if duplicate_times:
            add(slug, "error", "time_uniqueness", f"{duplicate_times} duplicate TIME values")

        parsed_indices: list[int] = []
        for value in times:
            try:
                parsed_indices.append(period_index(value, spec["cycle"]))
            except ValueError as exc:
                add(slug, "error", "time_format", str(exc))
                break
        if parsed_indices and parsed_indices != sorted(parsed_indices):
            add(slug, "error", "time_order", "TIME values are not ascending")
        if parsed_indices and parsed_indices[-1] > current_period_index(spec["cycle"]):
            add(slug, "error", "future_period", f"last period is in the future: {times[-1]}")

        empty_values = 0
        invalid_values = 0
        finite_values: list[float] = []
        for row in rows:
            raw_value = row.get("DATA_VALUE", "").strip()
            if not raw_value:
                empty_values += 1
                continue
            try:
                numeric = float(raw_value.replace(",", ""))
                if not math.isfinite(numeric):
                    invalid_values += 1
                else:
                    finite_values.append(numeric)
            except ValueError:
                invalid_values += 1
        if empty_values:
            add(slug, "error", "value_completeness", f"{empty_values} empty DATA_VALUE values")
        if invalid_values:
            add(slug, "error", "numeric_validity", f"{invalid_values} non-numeric values")

        wrong_stat = sum(row.get("STAT_CODE") != spec["stat_code"] for row in rows)
        wrong_items = 0
        for row in rows:
            observed = [row.get(f"ITEM_CODE{i}", "") for i in range(1, len(spec["items"]) + 1)]
            if observed != spec["items"]:
                wrong_items += 1
        if wrong_stat:
            add(slug, "error", "stat_code", f"{wrong_stat} rows have the wrong STAT_CODE")
        if wrong_items:
            add(slug, "error", "item_codes", f"{wrong_items} rows have unexpected item codes")

        missing_periods = 0
        if spec["cycle"] in {"M", "Q"} and len(parsed_indices) > 1:
            expected = parsed_indices[-1] - parsed_indices[0] + 1
            missing_periods = expected - len(set(parsed_indices))
            if missing_periods:
                add(
                    slug,
                    "warning",
                    "period_continuity",
                    f"{missing_periods} period(s) are absent between first and last observation",
                )

        freshness_lag = (
            current_period_index(spec["cycle"]) - parsed_indices[-1]
            if parsed_indices
            else None
        )
        if freshness_lag is not None and freshness_lag > allowed_freshness_lag(spec["cycle"]):
            add(
                slug,
                "warning",
                "freshness",
                f"last observation {times[-1]} is {freshness_lag} {spec['cycle']} period(s) behind",
            )

        profile.append(
            {
                "slug": slug,
                "category": spec["category"],
                "cycle": spec["cycle"],
                "rows": len(rows),
                "first_time": min(times) if times else None,
                "last_time": max(times) if times else None,
                "duplicate_times": duplicate_times,
                "empty_values": empty_values,
                "invalid_values": invalid_values,
                "missing_periods_between_endpoints": missing_periods,
                "minimum": min(finite_values) if finite_values else None,
                "maximum": max(finite_values) if finite_values else None,
                "freshness_lag_periods": freshness_lag,
            }
        )

    bok_profiles: list[dict[str, Any]] = []
    policy_dates: list[date] = []
    meeting_dates: list[date] = []
    if not BOK_MANIFEST_PATH.exists():
        add("bok_policy_calendar", "error", "manifest_exists", "BOK manifest is missing")
    else:
        with BOK_MANIFEST_PATH.open("r", newline="", encoding="utf-8-sig") as handle:
            bok_manifest = list(csv.DictReader(handle))
        for entry in bok_manifest:
            dataset = entry["dataset"]
            path = PROJECT_ROOT / entry["relative_path"]
            if not path.exists():
                add(dataset, "error", "file_exists", f"missing file: {path}")
                continue
            with path.open("r", newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            if len(rows) != int(entry["rows"]):
                add(
                    dataset,
                    "error",
                    "row_count",
                    f"csv={len(rows)}, manifest={entry['rows']}",
                )
            if file_hash(path) != entry["sha256"]:
                add(dataset, "error", "sha256", "file hash differs from manifest")

            date_field = (
                "effective_date" if dataset == "policy_rate_change_history" else "meeting_date"
            )
            raw_dates = [row.get(date_field, "") for row in rows]
            parsed_dates: list[date] = []
            for value in raw_dates:
                try:
                    parsed_dates.append(date.fromisoformat(value))
                except ValueError:
                    add(dataset, "error", "date_format", f"invalid ISO date: {value}")
                    break
            if len(raw_dates) != len(set(raw_dates)):
                add(dataset, "error", "date_uniqueness", "duplicate dates found")
            if parsed_dates and parsed_dates != sorted(parsed_dates):
                add(dataset, "error", "date_order", "dates are not ascending")

            if dataset == "policy_rate_change_history":
                policy_dates = parsed_dates
                invalid_rates = 0
                for row in rows:
                    try:
                        value = float(row["rate_percent"])
                        if not 0 <= value <= 30:
                            invalid_rates += 1
                    except (KeyError, ValueError):
                        invalid_rates += 1
                if invalid_rates:
                    add(
                        dataset,
                        "error",
                        "rate_validity",
                        f"{invalid_rates} invalid policy-rate values",
                    )
            elif dataset == "mpc_meeting_calendar":
                meeting_dates = parsed_dates
                invalid_status = sum(
                    row.get("status_at_download") not in {"held", "scheduled"} for row in rows
                )
                if invalid_status:
                    add(
                        dataset,
                        "error",
                        "status_validity",
                        f"{invalid_status} invalid meeting-status values",
                    )

            bok_profiles.append(
                {
                    "dataset": dataset,
                    "rows": len(rows),
                    "first_date": min(raw_dates) if raw_dates else None,
                    "last_date": max(raw_dates) if raw_dates else None,
                }
            )

        if policy_dates and meeting_dates:
            meeting_set = set(meeting_dates)
            uncovered_changes: list[str] = []
            for changed_on in policy_dates:
                if changed_on < date(2008, 1, 1):
                    continue
                # The emergency 2020 cut became effective one day after its MPC meeting.
                if changed_on not in meeting_set and date.fromordinal(changed_on.toordinal() - 1) not in meeting_set:
                    uncovered_changes.append(changed_on.isoformat())
            if uncovered_changes:
                add(
                    "bok_policy_calendar",
                    "error",
                    "change_meeting_coverage",
                    f"rate changes not covered by same/prior-day MPC meetings: {uncovered_changes}",
                )

    report = {
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "Bank of Korea ECOS series and official policy calendar",
        "intended_grain": "one observation per configured series and TIME value",
        "series_configured": len(specs),
        "series_profiled": len(profile),
        "bok_datasets_profiled": len(bok_profiles),
        "errors": error_count,
        "warnings": warning_count,
        "status": "pass" if error_count == 0 else "fail",
        "profiles": profile,
        "bok_profiles": bok_profiles,
        "findings": checks,
        "notes": [
            "Freshness warnings use broad frequency-specific tolerances and do not account for each source's release calendar.",
            "Daily continuity is not tested because weekends and Korean market holidays are expected gaps.",
            "A continuity warning can reflect a legitimate source omission; inspect the named series before imputation.",
        ],
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Validation {report['status'].upper()}: {len(profile)}/{len(specs)} series, "
        f"{error_count} error(s), {warning_count} warning(s)."
    )
    for finding in checks:
        print(
            f"{finding['severity'].upper():7s} {finding['slug']} "
            f"[{finding['check']}]: {finding['message']}"
        )
    print(f"Report: {REPORT_PATH}")
    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
