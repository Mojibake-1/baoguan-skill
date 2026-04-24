# Packing Scenarios

Use this reference when the shipment source includes 拼箱, 混箱, merged carton cells, 差异箱, 多一两个, 少一两个, or QQ-document packing rows that cannot be read directly by Codex.

## Terms

- `physical_cartons`: real boxes in the warehouse/shipment.
- `cartons`: declaration-row package count written to `报关资料录入!G`.
- `carton_group_id`: shared ID for rows packed in the same physical carton group.
- `carton_role`: `group-carton-carrier` for the row that carries the carton count; `co-packed-line` for rows sharing that carton count.
- `pcs_per_carton`: standard stock-plan or warehouse box specification.
- `quantity`: actual declared quantity from the shipment source.
- `quantity_delta`: `quantity - pcs_per_carton * physical_cartons`.

## Reading Merged Carton Cells

When one carton-count cell visually spans multiple SKU rows, the number applies to the whole group. Do not copy it to every row.

Only use merged carton cells that are visible in the current user-provided shipment source. Do not borrow merged-carton structure from prior generated workbooks or test outputs.

Example interpretation:

| Source visual shape | Meaning |
| --- | --- |
| three SKU rows share one `5` in the carton column | one 5-carton mixed group containing all three SKU rows |
| row A has `10`, row B has blank because of merge | row B shares row A's carton group |
| visible nonblank carton cells are `10`, `7`, and one shared `5` across four rows | package total is `22`, not `37` |
| row total is red and differs by 1 or 2 | 差异箱, not necessarily a bad match |

Default declaration policy:

1. Assign the shared `physical_cartons` to the first item in the group.
2. Set `cartons: 0` for later rows in the same group.
3. Keep every row's actual `quantity`.
4. Keep `carton_group_id` and `carton_role` in the working JSON/report for audit.
5. In the final `报关资料录入` worksheet, merge column `G` across the shared group rows and show the carton count once, instead of displaying `5 / 0 / 0 / 0`.

If operations requires a different package-count allocation, ask for that rule before final generation.

## Difference Cartons

Use 差异箱 when actual quantity differs from the standard carton math but the product identity is clear.

Calculation:

```text
standard_quantity = pcs_per_carton * physical_cartons
quantity_delta = actual_quantity - standard_quantity
```

Decision rules:

- `quantity_delta = 0`: normal full carton.
- `abs(quantity_delta) <= 2` and `abs(quantity_delta) / standard_quantity <= 5%`: acceptable small 差异箱 if the source marks or implies the difference.
- Larger differences require user/operations confirmation before generating the workbook.
- Do not demote a strong product match solely because of a small declared 差异箱.
- Always preserve actual quantity in the declaration row.

## Mixed-Carton Weight Allocation

Use this when a mixed carton provides warehouse gross weight plus per-SKU unit weight and quantity.

Inputs:

- warehouse gross weight / 仓库毛重
- each SKU's unit product weight / 单品重量
- each SKU's quantity / 数量

If any of these inputs are missing from the current source, ask the user for them before final workbook generation. Do not replace them with the stock-plan full-carton gross/net weights for each SKU.

Per SKU:

```text
sku_list_net = unit_weight * quantity
group_list_net = sum(sku_list_net)
ratio = sku_list_net / group_list_net
sku_customs_net = (warehouse_gross_weight - 1) * ratio
sku_customs_gross = warehouse_gross_weight * ratio
```

The fixed `1 kg` difference is treated as packaging or box-material weight, so:

```text
group_customs_net = warehouse_gross_weight - 1
group_customs_gross = warehouse_gross_weight
```

Round each SKU gross/net weight to 2 decimals and use compensation rounding so totals match exactly:

- sum of SKU customs gross weight equals warehouse gross weight
- sum of SKU customs net weight equals warehouse gross weight minus 1

For repeated mixed cartons such as `x2` or `x3`, first calculate the 1-carton standard allocation, then multiply each SKU's quantity/gross/net by the carton count.

Use `scripts/allocate_mixed_carton_weights.py` to perform this calculation instead of redoing it by hand.

## Working JSON Shape

Use English keys in JSON even when the source labels are Chinese:

```json
{
  "groups": [
    {
      "carton_group_id": "mix-001",
      "warehouse_gross_weight_kg": 19.8,
      "carton_count": 1,
      "items": [
        {
          "name": "sample-a",
          "sku": "SKU-A",
          "unit_weight_kg": 0.35,
          "quantity": 8
        }
      ]
    }
  ]
}
```

For `carton_count > 1`, `quantity` means one-carton quantity unless `quantity_basis` is set to `total`.

## Review Prompts

Ask the user only for missing operational facts:

- "这几行是不是同一个拼箱组？"
- "红色数量是差异箱实际数量吗，还是录入错误？"
- "仓库毛重对应的是单箱，还是这组 xN 的总重量？"
- "拼箱重量是否按单品重量占比分摊，并固定扣 1kg 包装差？"
