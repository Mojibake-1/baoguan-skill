#!/usr/bin/env python3
"""Validate declaration JSON for shared cartons, difference cartons, and totals."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


CENT = Decimal("0.01")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate customs declaration data JSON.")
    parser.add_argument("--input", required=True, type=Path, help="approved declaration JSON")
    parser.add_argument("--output", type=Path, help="optional JSON validation report path")
    parser.add_argument("--max-small-delta-units", type=Decimal, default=Decimal("2"))
    parser.add_argument("--max-small-delta-pct", type=Decimal, default=Decimal("0.05"))
    return parser.parse_args()


def as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    return format(normalized, "f")


def get_nested(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def line_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("line") or item.get("line_no") or index + 1)


def validate_quantity_delta(
    item: dict[str, Any],
    index: int,
    report: dict[str, list[dict[str, Any]]],
    max_units: Decimal,
    max_pct: Decimal,
) -> None:
    pcs = as_decimal(item.get("pcs_per_carton") or item.get("pcs_per_ctn"))
    physical_cartons = as_decimal(item.get("physical_cartons") or item.get("cartons"))
    quantity = as_decimal(item.get("quantity") or item.get("total"))
    if pcs is None or physical_cartons is None or quantity is None:
        return

    standard = pcs * physical_cartons
    delta = quantity - standard
    declared_delta = as_decimal(item.get("quantity_delta"))
    line = line_id(item, index)

    if declared_delta is not None and declared_delta != delta:
        report["errors"].append(
            {
                "line": line,
                "code": "quantity_delta_mismatch",
                "message": (
                    f"quantity_delta is {fmt(declared_delta)} but actual quantity minus "
                    f"standard quantity is {fmt(delta)}."
                ),
            }
        )

    if delta == 0:
        return

    if declared_delta is None:
        report["warnings"].append(
            {
                "line": line,
                "code": "missing_quantity_delta",
                "message": f"Actual quantity differs from carton math by {fmt(delta)}.",
            }
        )

    delta_abs = abs(delta)
    pct = delta_abs / standard if standard != 0 else Decimal("0")
    severity = "small_difference_carton"
    if delta_abs > max_units or pct > max_pct:
        severity = "large_difference_requires_confirmation"

    report["warnings"].append(
        {
            "line": line,
            "code": severity,
            "message": (
                f"standard={fmt(standard)}, actual={fmt(quantity)}, delta={fmt(delta)}, "
                f"delta_pct={fmt((pct * Decimal('100')).quantize(Decimal('0.01')))}%."
            ),
        }
    )


def validate_carton_groups(items: list[dict[str, Any]], report: dict[str, list[dict[str, Any]]]) -> None:
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, item in enumerate(items):
        group_id = item.get("carton_group_id")
        if group_id:
            groups[str(group_id)].append((index, item))

    for group_id, rows in groups.items():
        physical_values = {
            as_decimal(item.get("physical_cartons"))
            for _, item in rows
            if as_decimal(item.get("physical_cartons")) is not None
        }
        if len(physical_values) > 1:
            report["errors"].append(
                {
                    "group": group_id,
                    "code": "conflicting_physical_cartons",
                    "message": "Rows in the same carton group have different physical_cartons.",
                }
            )
            continue

        physical = next(iter(physical_values), None)
        carton_sum = sum((as_decimal(item.get("cartons")) or Decimal("0")) for _, item in rows)
        if physical is not None and carton_sum != physical:
            report["errors"].append(
                {
                    "group": group_id,
                    "code": "carton_group_sum_mismatch",
                    "message": (
                        f"Sum of declaration-row cartons is {fmt(carton_sum)}, "
                        f"but physical_cartons is {fmt(physical)}."
                    ),
                }
            )

        if len(rows) > 1:
            carriers = [item for _, item in rows if item.get("carton_role") == "group-carton-carrier"]
            if not carriers:
                report["warnings"].append(
                    {
                        "group": group_id,
                        "code": "missing_group_carton_carrier",
                        "message": "Shared carton group has no group-carton-carrier row.",
                    }
                )
            allocation_source = next(
                (
                    item.get("mixed_weight_source")
                    or item.get("weight_allocation_source")
                    or item.get("allocated_weight_source")
                    for _, item in rows
                    if item.get("mixed_weight_source")
                    or item.get("weight_allocation_source")
                    or item.get("allocated_weight_source")
                ),
                None,
            )
            has_allocated_weights = all(
                as_decimal(item.get("gross_weight_kg")) is not None
                and as_decimal(item.get("net_weight_kg")) is not None
                for _, item in rows
            )
            if not allocation_source:
                report["errors"].append(
                    {
                        "group": group_id,
                        "code": "missing_mixed_weight_allocation_source",
                        "message": (
                            "Shared carton group is missing mixed weight allocation source. "
                            "Ask for warehouse gross weight, each SKU unit product weight, "
                            "and whether quantities are per carton or total; or provide final "
                            "allocated gross/net weights with a source note."
                        ),
                    }
                )
            elif not has_allocated_weights:
                report["errors"].append(
                    {
                        "group": group_id,
                        "code": "missing_mixed_allocated_weights",
                        "message": "Shared carton group has allocation source but not every row has gross/net weights.",
                    }
                )


def validate_totals(data: dict[str, Any], items: list[dict[str, Any]], report: dict[str, list[dict[str, Any]]]) -> None:
    expected_packages = as_decimal(get_nested(data, "totals.packages") or data.get("packages"))
    expected_gross = as_decimal(get_nested(data, "totals.gross_weight_kg") or data.get("gross_weight_kg"))
    expected_net = as_decimal(get_nested(data, "totals.net_weight_kg") or data.get("net_weight_kg"))

    carton_sum = sum((as_decimal(item.get("cartons")) or Decimal("0")) for item in items)
    gross_sum = sum((as_decimal(item.get("gross_weight_kg")) or Decimal("0")) for item in items)
    net_sum = sum((as_decimal(item.get("net_weight_kg")) or Decimal("0")) for item in items)

    if expected_packages is not None and carton_sum != expected_packages:
        report["errors"].append(
            {
                "code": "package_total_mismatch",
                "message": f"Item cartons sum to {fmt(carton_sum)}, expected {fmt(expected_packages)}.",
            }
        )
    if expected_gross is not None and q2(gross_sum) != q2(expected_gross):
        report["errors"].append(
            {
                "code": "gross_total_mismatch",
                "message": f"Item gross weight sums to {fmt(q2(gross_sum))}, expected {fmt(q2(expected_gross))}.",
            }
        )
    if expected_net is not None and q2(net_sum) != q2(expected_net):
        report["errors"].append(
            {
                "code": "net_total_mismatch",
                "message": f"Item net weight sums to {fmt(q2(net_sum))}, expected {fmt(q2(expected_net))}.",
            }
        )

    report["totals"] = [
        {
            "cartons": fmt(carton_sum),
            "gross_weight_kg": fmt(q2(gross_sum)),
            "net_weight_kg": fmt(q2(net_sum)),
        }
    ]


def main() -> None:
    args = parse_args()
    with args.input.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object.")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Input JSON must contain non-empty items[].")

    report: dict[str, list[dict[str, Any]]] = {
        "errors": [],
        "warnings": [],
        "totals": [],
    }
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            report["errors"].append(
                {"line": str(index + 1), "code": "invalid_item", "message": "Item must be an object."}
            )
            continue
        validate_quantity_delta(item, index, report, args.max_small_delta_units, args.max_small_delta_pct)

    validate_carton_groups(items, report)
    validate_totals(data, items, report)
    report["status"] = [{"ok": not report["errors"]}]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    print(
        f"ok={not report['errors']} errors={len(report['errors'])} "
        f"warnings={len(report['warnings'])}"
    )
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
