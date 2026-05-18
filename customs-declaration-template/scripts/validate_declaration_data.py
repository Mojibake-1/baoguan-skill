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


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def normalize_model_token(value: Any) -> str:
    return "".join(str(value or "").split()).upper()


def declaration_elements_tail(value: Any) -> str | None:
    text = str(value or "").replace("｜", "|").strip()
    if not text or "|" not in text:
        return None
    parts = [part.strip() for part in text.split("|") if part.strip()]
    if not parts:
        return None
    return parts[-1]


def declaration_elements_parts(value: Any) -> list[str]:
    text = str(value or "").replace("｜", "|").strip()
    if not text or "|" not in text:
        return []
    return [part.strip() for part in text.split("|")]


def is_brandless(value: Any) -> bool:
    token = str(value or "").strip().upper().replace(" ", "")
    return token in {"无牌", "无品牌", "NOBRAND", "NO-BRAND", "NONE", "N/A", "NA"}


def validate_model_elements_tail(
    item: dict[str, Any],
    index: int,
    report: dict[str, list[dict[str, Any]]],
) -> None:
    matched_stock_row = item.get("matched_stock_row")
    if not isinstance(matched_stock_row, dict):
        matched_stock_row = {}

    model = first_present(
        item.get("stock_model"),
        item.get("declaration_model"),
        item.get("spec_model"),
        item.get("model"),
        matched_stock_row.get("model"),
        matched_stock_row.get("spec_model"),
        matched_stock_row.get("declaration_model"),
    )
    if model in (None, ""):
        return

    elements = first_present(
        item.get("declaration_elements"),
        item.get("declaration_purpose"),
        item.get("description_spec"),
        item.get("elements"),
    )
    line = line_id(item, index)
    if elements in (None, ""):
        report["errors"].append(
            {
                "line": line,
                "code": "missing_declaration_elements",
                "message": "Item has a stock model but no declaration elements/spec string.",
            }
        )
        return

    tail = declaration_elements_tail(elements)
    if tail is None:
        report["errors"].append(
            {
                "line": line,
                "code": "declaration_elements_missing_model_tail",
                "message": "Declaration elements must end with the stock model after a pipe separator.",
            }
        )
        return

    if normalize_model_token(model) != normalize_model_token(tail):
        report["errors"].append(
            {
                "line": line,
                "code": "model_elements_tail_mismatch",
                "message": (
                    f"Stock model is {model!s}, but declaration elements tail is {tail!s}. "
                    "Fix the source row before generating the workbook."
                ),
            }
        )


def validate_brand_code(
    item: dict[str, Any],
    index: int,
    report: dict[str, list[dict[str, Any]]],
) -> None:
    elements = first_present(
        item.get("declaration_elements"),
        item.get("declaration_purpose"),
        item.get("description_spec"),
        item.get("elements"),
    )
    parts = declaration_elements_parts(elements)
    if len(parts) < 2:
        return

    first_code = parts[0].strip()
    brand = parts[-2].strip()
    expected = "0" if is_brandless(brand) else "4"
    if first_code != expected:
        report["errors"].append(
            {
                "line": line_id(item, index),
                "code": "brand_code_mismatch",
                "message": (
                    f"Declaration elements brand is {brand!s}, so the first segment must be "
                    f"{expected}, but found {first_code!s}."
                ),
            }
        )


def get_stock_value(
    item: dict[str, Any],
    matched_stock_row: dict[str, Any],
    row_names: list[str],
    item_names: list[str],
) -> Any:
    for name in row_names:
        if name in matched_stock_row and matched_stock_row.get(name) not in (None, ""):
            return matched_stock_row.get(name)
    for name in item_names:
        if name in item and item.get(name) not in (None, ""):
            return item.get(name)
    return None


def get_unit_price_v4(item: dict[str, Any], matched_stock_row: dict[str, Any]) -> Any:
    return get_stock_value(
        item,
        matched_stock_row,
        ["unit_price_v4", "price_v4"],
        ["unit_price_v4", "price_v4", "stock_unit_price_v4", "source_unit_price_v4"],
    )


def get_legacy_unit_price(item: dict[str, Any], matched_stock_row: dict[str, Any]) -> Any:
    return get_stock_value(
        item,
        matched_stock_row,
        ["unit_price", "price", "old_unit_price", "unit_price_f"],
        ["unit_price", "price", "old_unit_price", "unit_price_f"],
    )


def validate_unit_price_v4(
    item: dict[str, Any],
    index: int,
    report: dict[str, list[dict[str, Any]]],
) -> None:
    matched_stock_row = item.get("matched_stock_row")
    if not isinstance(matched_stock_row, dict):
        matched_stock_row = {}
    if get_unit_price_v4(item, matched_stock_row) is not None:
        return

    legacy_price = get_legacy_unit_price(item, matched_stock_row)
    report["errors"].append(
        {
            "line": line_id(item, index),
            "code": "missing_unit_price_v4",
            "message": (
                "Missing 申报单价V4. The old 申报单价/申报单价F is not a fallback "
                "and must not be used for workbook generation."
            ),
            "legacy_price_present": legacy_price is not None,
        }
    )


def validate_required_stock_source_fields(
    item: dict[str, Any],
    index: int,
    report: dict[str, list[dict[str, Any]]],
) -> None:
    matched_stock_row = item.get("matched_stock_row")
    if not isinstance(matched_stock_row, dict):
        matched_stock_row = {}

    has_stock_metadata = bool(matched_stock_row) or any(
        key in item
        for key in (
            "stock_pc_per_carton",
            "stock_gross_per_carton",
            "stock_net_per_carton",
            "stock_unit_price_v4",
        )
    )
    if not has_stock_metadata:
        return

    required = [
        (
            "申报单价V4",
            ["unit_price_v4", "price_v4"],
            ["unit_price_v4", "price_v4", "stock_unit_price_v4", "source_unit_price_v4"],
        ),
        (
            "pc/ctn",
            ["stock_pc_per_carton", "pc_per_carton", "pcs_per_carton"],
            ["stock_pc_per_carton", "source_pc_per_carton"],
        ),
        (
            "单箱毛重",
            ["gross_per_carton", "stock_gross_per_carton", "gross_weight_per_carton"],
            ["stock_gross_per_carton", "source_gross_per_carton"],
        ),
        (
            "单箱净重",
            ["net_per_carton", "stock_net_per_carton", "net_weight_per_carton"],
            ["stock_net_per_carton", "source_net_per_carton"],
        ),
    ]
    missing = [
        label
        for label, row_names, item_names in required
        if get_stock_value(item, matched_stock_row, row_names, item_names) is None
    ]
    if missing:
        product = first_present(item.get("source_product_name"), matched_stock_row.get("content"), "")
        sku = first_present(item.get("source_sku"), matched_stock_row.get("platform_sku"), "")
        report["errors"].append(
            {
                "line": line_id(item, index),
                "code": "missing_stock_source_fields",
                "message": (
                    "Matched stock row is missing required source fields: "
                    f"{', '.join(missing)}. Stop and notify operations before generating the workbook."
                ),
                "missing_fields": missing,
                "product": product,
                "sku": sku,
                "stock_row": matched_stock_row.get("stock_plan_row") or matched_stock_row.get("row_no"),
            }
        )


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
        validate_model_elements_tail(item, index, report)
        validate_brand_code(item, index, report)
        validate_unit_price_v4(item, index, report)
        validate_required_stock_source_fields(item, index, report)
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
