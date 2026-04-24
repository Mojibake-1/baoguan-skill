# Customs Declaration Field Map

Use this reference to normalize shipment, invoice, packing list, and contract data before filling a customs declaration template.

## Placeholder Patterns

- Single value: `{{declaration.contract_no}}`
- Nested value: `{{domestic_consignor.credit_code}}`
- Commodity repeat row: `{{items[].hs_code}}`, `{{items[].description_cn}}`, `{{items[].quantity}}`
- Explicit array index for a fixed cell: `{{items[0].hs_code}}`

## Common Header Fields

| Chinese label | JSON path |
| --- | --- |
| 预录入编号 | `declaration.pre_entry_no` |
| 海关编号 | `declaration.customs_no` |
| 境内收发货人 | `domestic_consignor.name` |
| 境内收发货人统一社会信用代码 | `domestic_consignor.credit_code` |
| 境外收发货人 | `overseas_consignee.name` |
| 生产销售单位 | `producer_seller.name` |
| 消费使用单位 | `consumer_user.name` |
| 申报单位 | `declaration_agent.name` |
| 申报单位统一社会信用代码 | `declaration_agent.credit_code` |
| 出境关别 / 进境关别 | `declaration.customs_office` |
| 出口日期 / 进口日期 | `shipment.import_export_date` |
| 申报日期 | `declaration.declaration_date` |
| 备案号 | `declaration.record_no` |
| 运输方式 | `shipment.transport_mode` |
| 运输工具名称及航次号 | `shipment.vessel_voyage` |
| 提运单号 | `shipment.bill_no` |
| 监管方式 | `declaration.trade_mode` |
| 征免性质 | `declaration.tax_mode` |
| 许可证号 | `declaration.license_no` |
| 合同协议号 | `declaration.contract_no` |
| 贸易国（地区） | `trade.country` |
| 运抵国（地区） | `trade.destination_country` |
| 指运港 | `shipment.destination_port` |
| 境内货源地 | `shipment.source_place` |
| 成交方式 | `trade.incoterm` |
| 运费 | `trade.freight` |
| 保费 | `trade.insurance` |
| 杂费 | `trade.other_charges` |
| 件数 | `totals.packages` |
| 包装种类 | `totals.package_type` |
| 毛重（千克） | `totals.gross_weight_kg` |
| 净重（千克） | `totals.net_weight_kg` |
| 随附单证 | `docs.attached` |
| 标记唛码及备注 | `shipment.marks_and_notes` |

## Common Commodity Fields

Use these paths inside a repeat row as `{{items[].path}}`.

| Chinese label | Item path |
| --- | --- |
| 项号 | `line_no` |
| 备案序号 | `record_item_no` |
| 商品编号 | `hs_code` |
| 商品名称及规格型号 | `description_cn` or `description_spec` |
| 商品英文名称 | `description_en` |
| 规格型号 | `specification` |
| 数量及单位 | `quantity_unit` |
| 第一数量 | `quantity` |
| 第一计量单位 | `unit` |
| 第二数量 | `second_quantity` |
| 第二计量单位 | `second_unit` |
| 单价 | `unit_price` |
| 总价 | `total_price` |
| 币制 | `currency` |
| 原产国（地区） | `origin_country` |
| 最终目的国（地区） | `destination_country` |
| 境内货源地 | `source_place` |
| 征免 | `tax_exemption` |

## Normalization Rules

- Prefer values from formal source files over free-text notes when there is a conflict.
- Keep numeric values numeric in JSON when the template may calculate totals.
- Store dates as `YYYY-MM-DD` unless the template itself shows another format.
- Do not merge distinct commodity lines unless the user or broker template explicitly requires aggregation.
- Preserve invoice currency codes as uppercase ISO-style values such as `USD`, `EUR`, `CNY`, or `JPY`.
- Use `待补充` only for unknown values, not for values that can be calculated from the source files.

## Review Checklist

- Header parties match the contract or invoice.
- Contract number, transport mode, bill number, and trade term are present when available.
- Package count, gross weight, and net weight match the packing list.
- Commodity line count matches the invoice or the user's intended declaration grouping.
- Each item has HS code, Chinese name, declared quantity, unit, total value, and currency.
- Totals match the source documents after rounding rules used by the template.
- Any generated draft with compliance impact is reviewed by the user's broker or customs compliance owner.
