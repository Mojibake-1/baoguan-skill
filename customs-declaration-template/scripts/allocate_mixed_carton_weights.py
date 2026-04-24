#!/usr/bin/env python3
"""Allocate mixed-carton customs gross/net weights by SKU list-net ratio."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


CENT = Decimal("0.01")
SIX_PLACES = Decimal("0.000001")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Allocate mixed-carton gross/net weights with 2-decimal compensation rounding."
    )
    parser.add_argument("--input", required=True, type=Path, help="mixed carton JSON input")
    parser.add_argument("--output", required=True, type=Path, help="allocation JSON output")
    return parser.parse_args()


def decimal_from(value: Any, field: str) -> Decimal:
    if value is None or value == "":
        raise ValueError(f"Missing required numeric field: {field}")
    try:
        number = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid numeric field {field}: {value!r}") from exc
    return number


def rounded(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def to_number(value: Decimal, places: Decimal = CENT) -> int | float:
    quantized = value.quantize(places, rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return int(quantized)
    return float(quantized)


def compensate_round(exact_values: list[Decimal], target_total: Decimal) -> list[Decimal]:
    if not exact_values:
        return []

    target = rounded(target_total)
    values = [rounded(value) for value in exact_values]
    diff_cents = int((target - sum(values)) / CENT)
    if diff_cents == 0:
        return values

    residuals = [exact - value for exact, value in zip(exact_values, values, strict=True)]
    if diff_cents > 0:
        order = sorted(range(len(values)), key=lambda idx: residuals[idx], reverse=True)
        step = CENT
    else:
        order = sorted(range(len(values)), key=lambda idx: residuals[idx])
        step = -CENT

    for offset in range(abs(diff_cents)):
        idx = order[offset % len(order)]
        next_value = values[idx] + step
        if next_value < 0:
            raise ValueError("Compensation rounding would create a negative allocation.")
        values[idx] = next_value

    if sum(values) != target:
        raise AssertionError("Compensation rounding failed to match the target total.")
    return values


def normalize_groups(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data.get("groups"), list):
        return data["groups"]
    if isinstance(data.get("items"), list):
        return [data]
    raise ValueError("Input JSON must contain groups[] or a top-level items[].")


def allocate_group(group: dict[str, Any], group_index: int) -> dict[str, Any]:
    group_id = str(group.get("carton_group_id") or f"mixed-{group_index + 1}")
    quantity_basis = str(group.get("quantity_basis") or "per_carton")
    if quantity_basis not in {"per_carton", "total"}:
        raise ValueError(f"{group_id}: quantity_basis must be per_carton or total.")

    carton_count = decimal_from(group.get("carton_count", 1), f"{group_id}.carton_count")
    if carton_count <= 0:
        raise ValueError(f"{group_id}: carton_count must be positive.")

    warehouse_gross = decimal_from(
        group.get("warehouse_gross_weight_kg"), f"{group_id}.warehouse_gross_weight_kg"
    )
    if warehouse_gross <= 1:
        raise ValueError(f"{group_id}: warehouse_gross_weight_kg must be greater than 1.")

    multiplier = carton_count if quantity_basis == "per_carton" else Decimal("1")
    target_gross = warehouse_gross * multiplier
    target_net = (warehouse_gross - Decimal("1")) * multiplier

    items = group.get("items") or []
    if not items:
        raise ValueError(f"{group_id}: items[] is required.")

    base_rows: list[dict[str, Any]] = []
    list_net_values: list[Decimal] = []
    for item_index, item in enumerate(items):
        prefix = f"{group_id}.items[{item_index}]"
        quantity = decimal_from(item.get("quantity"), f"{prefix}.quantity")
        unit_weight = decimal_from(item.get("unit_weight_kg"), f"{prefix}.unit_weight_kg")
        if quantity <= 0:
            raise ValueError(f"{prefix}.quantity must be positive.")
        if unit_weight <= 0:
            raise ValueError(f"{prefix}.unit_weight_kg must be positive.")
        list_net = unit_weight * quantity
        list_net_values.append(list_net)
        base_rows.append(
            {
                "source": item,
                "quantity": quantity,
                "unit_weight": unit_weight,
                "list_net": list_net,
            }
        )

    group_list_net = sum(list_net_values)
    if group_list_net <= 0:
        raise ValueError(f"{group_id}: total list net weight must be positive.")

    exact_gross = [(row["list_net"] / group_list_net) * target_gross for row in base_rows]
    exact_net = [(row["list_net"] / group_list_net) * target_net for row in base_rows]
    gross_allocations = compensate_round(exact_gross, target_gross)
    net_allocations = compensate_round(exact_net, target_net)

    output_items: list[dict[str, Any]] = []
    for row, gross, net, exact_g, exact_n in zip(
        base_rows, gross_allocations, net_allocations, exact_gross, exact_net, strict=True
    ):
        source = row["source"]
        ratio = row["list_net"] / group_list_net
        total_quantity = row["quantity"] * multiplier
        total_list_net = row["list_net"] * multiplier
        output_items.append(
            {
                "name": source.get("name", ""),
                "sku": source.get("sku", ""),
                "quantity": to_number(total_quantity, SIX_PLACES),
                "quantity_basis": quantity_basis,
                "unit_weight_kg": to_number(row["unit_weight"], SIX_PLACES),
                "list_net_kg": to_number(total_list_net, SIX_PLACES),
                "allocation_ratio": float(ratio.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)),
                "gross_weight_kg": to_number(gross),
                "net_weight_kg": to_number(net),
                "exact_gross_weight_kg": to_number(exact_g, SIX_PLACES),
                "exact_net_weight_kg": to_number(exact_n, SIX_PLACES),
            }
        )

    return {
        "carton_group_id": group_id,
        "quantity_basis": quantity_basis,
        "carton_count": to_number(carton_count, SIX_PLACES),
        "warehouse_gross_weight_kg": to_number(warehouse_gross),
        "target_gross_weight_kg": to_number(target_gross),
        "target_net_weight_kg": to_number(target_net),
        "list_net_weight_kg": to_number(group_list_net * multiplier, SIX_PLACES),
        "items": output_items,
        "check": {
            "gross_weight_sum_kg": to_number(sum(gross_allocations)),
            "net_weight_sum_kg": to_number(sum(net_allocations)),
            "gross_matches_target": sum(gross_allocations) == rounded(target_gross),
            "net_matches_target": sum(net_allocations) == rounded(target_net),
        },
    }


def main() -> None:
    args = parse_args()
    with args.input.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object.")

    groups = normalize_groups(data)
    allocated_groups = [allocate_group(group, index) for index, group in enumerate(groups)]
    result = {
        "method": "mixed_carton_weight_ratio_v1",
        "rounding": "2_decimals_with_compensation",
        "groups": allocated_groups,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
