#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the approved customs declaration output filename."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


INVALID_FILENAME_RE = re.compile(r'[\\/:*?"<>|]+')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a standardized declaration output filename.")
    parser.add_argument("--data", type=Path, help="Normalized declaration JSON.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for the approved declaration file.")
    parser.add_argument("--extension", default=".xlsx", help="Output extension, default .xlsx.")
    parser.add_argument("--country", help="Country/region label, for example 加拿大.")
    parser.add_argument("--country-code", help="Destination country code, for example US. Lowercase is used in filenames.")
    parser.add_argument("--logistics-channel", help="物流商及渠道, used to build the filename prefix.")
    parser.add_argument("--logistics-prefix", help="Explicit filename prefix, overrides --logistics-channel.")
    parser.add_argument("--include-country", action="store_true", help="Deprecated; logistics filenames now use lowercase country code.")
    parser.add_argument("--packages", type=int, help="Package/carton count used before 件.")
    parser.add_argument("--date", help="Declaration-document date as YYYY-MM-DD, YYYY/M/D, YYYYMMDD, or YYMMDD. Default: today.")
    parser.add_argument("--allow-existing", action="store_true", help="Do not add -2/-3 when the file already exists.")
    return parser.parse_args()


def load_data(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Data JSON must contain an object at the top level.")
    return data


def get_path(root: dict[str, Any], path: str) -> Any:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def first_value(root: dict[str, Any], paths: list[str]) -> Any:
    for path in paths:
        value = get_path(root, path)
        if value not in (None, ""):
            return value
    return None


def parse_output_date(value: str | None, data: dict[str, Any]) -> str:
    raw = value or first_value(
        data,
        [
            "declaration_date",
            "declaration.declaration_date",
            "declaration.document_date",
            "document_date",
            "declaration.created_date",
            "created_date",
            "ship_date",
            "shipment.actual_ship_date",
            "shipment.import_export_date",
        ],
    )
    if not raw:
        return date.today().strftime("%y%m%d")

    text = str(raw).strip()
    if re.fullmatch(r"\d{6}", text):
        return text
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%y%m%d")
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {text}")


def safe_filename_part(value: Any) -> str:
    text = str(value or "").strip()
    text = INVALID_FILENAME_RE.sub("", text)
    text = re.sub(r"\s+", "", text)
    return text


def logistics_prefix(value: Any) -> str:
    text = safe_filename_part(value)
    if not text:
        return ""
    if text.startswith("宝通达"):
        return "宝通达"
    if text.startswith("海光"):
        return "海光"
    for suffix in ("纽约卡派", "美中特惠", "普船海卡", "卡派", "海卡", "特惠"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text


def derive_country_code(country: Any) -> str:
    text = str(country or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in {"US", "USA"} or "美国" in text or "UNITEDSTATES" in upper.replace(" ", ""):
        return "us"
    if upper == "UK" or "英国" in text or "UNITEDKINGDOM" in upper.replace(" ", ""):
        return "uk"
    if upper == "CA" or "加拿大" in text or "CANADA" in upper:
        return "ca"
    return safe_filename_part(text).lower()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def main() -> None:
    args = parse_args()
    data = load_data(args.data)

    country = args.country or first_value(data, ["country", "trade.destination_country", "trade.country"])
    country_code = args.country_code or first_value(data, ["country_code", "trade.country_code"])
    channel = args.logistics_channel or first_value(
        data,
        [
            "logistics_channel",
            "shipment.logistics_channel",
            "shipment.logistics",
            "shipment.channel",
            "trade.logistics_channel",
        ],
    )
    prefix = safe_filename_part(args.logistics_prefix) or logistics_prefix(channel)
    packages = (
        args.packages
        if args.packages is not None
        else first_value(data, ["totals.packages", "packages", "package_count"])
    )
    if packages in (None, "") and isinstance(data.get("items"), list):
        packages = sum(float(item.get("cartons", 0) or 0) for item in data["items"])

    output_date = parse_output_date(args.date, data)

    if country in (None, ""):
        raise ValueError("Country is required. Pass --country or set country/trade.destination_country in data.")
    if packages in (None, ""):
        raise ValueError("Package count is required. Pass --packages or set totals.packages in data.")

    try:
        package_count = int(float(str(packages)))
    except ValueError as exc:
        raise ValueError(f"Invalid package count: {packages}") from exc

    extension = args.extension if args.extension.startswith(".") else "." + args.extension
    country_part = safe_filename_part(country)
    if prefix:
        filename_prefix = prefix + safe_filename_part(country_code or derive_country_code(country)).lower()
    else:
        filename_prefix = country_part
    filename = f"{filename_prefix}{package_count}件报关单资料{output_date}{extension}"
    output_path = args.output_dir / filename
    if not args.allow_existing:
        output_path = unique_path(output_path)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(output_path)


if __name__ == "__main__":
    main()
