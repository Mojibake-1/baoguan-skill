---
name: customs-declaration-template
description: Generate Chinese customs declaration workbooks from the company long Excel template 报关单长模板.xlsx and the AMZ stock-plan workbook sheet 报关名. Use when the user asks to make 报关单/报关资料/装箱单/发票/合同 from the long template, mentions 报关资料录入, amz备货计划, 报关名, 申报单价V4, 拼箱/混箱/合并箱数/差异箱/多一两个/少一两个, or needs the template copied, filled, formula-checked, and trimmed without changing source files.
---

# Customs Declaration Long Template

Use this skill for the fixed company workflow: copy the long Excel template, fill only `报关资料录入`, let later sheets calculate from formulas, then delete extra item rows. This is not a generic placeholder-template workflow.

## Required Run Order

1. Collect the current shipment list, actual shipment date, destination country/station, and any packing-specific inputs.
2. Normalize packing before product matching conclusions: blank carton cells, merged carton cells, 拼箱/混箱, and 差异箱 must be resolved first.
3. For any shared/mixed carton group, collect either final allocated gross/net weights with a source note, or the allocation inputs: group warehouse gross weight, each SKU's unit product weight, and whether quantities are per carton or total.
4. Build a declaration JSON and run `scripts/validate_declaration_data.py` before Excel generation whenever there is 拼箱/混箱/合并箱数/差异箱. Do not generate the workbook if validation has errors.
5. Only after validation passes, create the final workbook with Excel COM.
6. Return the final workbook together with a match-audit table comparing the current shipment rows to the source `报关名` rows.

## Non-Negotiable Rules

- Explain the next step and get user confirmation before risky or ambiguous actions. If product matching, dates, country, or source rows are unclear, ask immediately.
- Never modify the source stock-plan workbook or the original long template. Work from read-only opens and local copies.
- Use Excel COM / real Excel automation for the final workbook. Do not save the final long template with `openpyxl`, `pandas`, `xlsxwriter`, or generic spreadsheet exporters; they can strip merged-cell internal styles and leave formula caches empty.
- `openpyxl` may be used only for inspection, source extraction, candidate matching, and JSON/report creation. It must not save the final declaration workbook.
- Before final generation on a new machine or uncertain environment, verify Excel COM is available. If it is unavailable, stop and tell the user. Do not fall back to `openpyxl` for the official final workbook.
- If writing PowerShell for Excel COM on Windows PowerShell 5, keep the `.ps1` file ASCII-only or save it with a UTF-8 BOM. Otherwise Chinese sheet names can be decoded as ANSI garbage. Prefer worksheet indexes and runtime sheet names inside scripts.
- Do not rewrite downstream sheets. After `报关资料录入` is correct, downstream sheets should only have extra rows deleted. The only allowed downstream formula edit is the known `#REF!` repair listed below.
- Do not invent customs data. If `报关名` has no matching product row, stop and ask the user/operations to add the row.
- If `报关名` has no matching product row, run `scripts/notify_missing_product_lark.ps1` once to notify operations contact JOJO before stopping.

- For shared/mixed carton rows, never promise final workbook generation after only confirming destination/date/carton grouping. Also require mixed-carton weight allocation inputs or final allocated gross/net weights with a source note.
- When asking for mixed-carton weight inputs, explicitly request all required fields: group warehouse gross weight, each SKU's unit product weight, and whether quantities are per carton or total. Do not say "or use the existing rule" unless those exact inputs are already available in the current source.

## Source Files

- Long template: use the user-provided `报关单长模板.xlsx`; the skill may also use `assets/declaration-long-template.xlsx` if present.
- Stock plan default source: `\\192.168.0.118\沐星科技\亚马逊\表格\常用\amz备货计划V260316.xlsx`, sheet `报关名`. This shared-drive file is the preferred source because operations updates it frequently.
- At the start of every declaration task, copy the shared-drive stock plan to a local working copy and use that copy for matching. Do not reuse an old local copy unless the user explicitly says to use that exact file.
- If the shared-drive file cannot be reached in the sandbox, request permission to retry the copy outside the sandbox. If the outside-sandbox copy also fails, stop and tell the user. Ask whether they want to provide a temporary local copy. Do not silently fall back to a stale desktop copy.
- `报关名` columns currently used:
  - `A`: 海关编码
  - `B`: 报关商品名称
  - `C`: 产品内容, the primary matching field
  - `D`: 报关规格型号 / model reference
  - `E`: 对应平台 SKU, support only, not the primary key
  - `G`: 申报单价V4, the current unit-price column
  - `H`: pc/ctn
  - `I`: 单箱毛重
  - `J`: 单箱净重
- Do not use old price column `F` when the user says to use `申报单价V4`.

## Daily Invocation

If the user says only "帮我做报关单" or similar, assume this skill should run. The user is expected to provide the current shipment list in the message or as a spreadsheet/screenshot. The minimum per-task inputs are:

- current product list / 本次要做的货物清单
- actual shipment date / 本次实际发货日期
- destination country or station / 目的国或站点
- PCS/CTN
- cartons / 箱数
- total quantity / 总数量

If any of these are missing, ask only for the missing data. Do not ask the user to restate source paths or template paths unless the default shared-drive source is unreachable or the template version is in question.

Hard input gate:

- If the current user message does not include a shipment list, spreadsheet, screenshot, or explicit path to the current shipment source, do not generate a workbook. Ask the user to provide the current shipment list or source file.
- Do not infer the current shipment from `.analysis`, `outputs`, previously generated workbooks, simulated JSON files, screenshots from prior turns, or filenames unless the user explicitly says to use that exact artifact.
- Do not reuse prior test data such as `simulated-*`, `mock-*`, or an existing `*模拟.xlsx` file for a real or new declaration request.
- Destination country/station must come from the current user-provided task source or direct user confirmation. Never infer it from the stock-plan workbook, owner names, SKU, old files, or prior runs.
- If a screenshot is partial and only shows carton counts or totals, ask for the missing product rows or the full packing screenshot before generating.
- If carton-count cells are blank beside product rows, do not backfill a nearby nonblank carton count into every row. Treat the blanks as possible merged-cell/shared-carton evidence and ask for confirmation before generating.
- If a shared/mixed carton group is present and the source does not include mixed-carton weight allocation inputs, ask for them before generating: warehouse gross weight for the group, each SKU's unit product weight, and whether the quantities are per carton or total for the group. Do not assume mixed-carton gross/net weights from full-carton stock-plan weights.
- The only data that should be carried forward automatically is the fresh shared-drive `报关名` copy for product matching; shipment quantities and packing groups must come from the current user-provided shipment source.

If a screenshot or source table shows one carton count merged across multiple product rows, treat it as a shared physical carton group (拼箱/混箱), not as independent cartons for every row. Read `references/packing-scenarios.md` before normalizing those rows.

For any shared/mixed carton group, the final workbook cannot be generated until all of these are known:

- whether the merged carton count really applies to the grouped rows
- whether small quantity deltas are intentional difference cartons
- mixed-carton warehouse gross weight and each SKU's unit product weight, unless the current source already provides final allocated gross/net weights
- whether mixed-carton quantities are per carton or total for the group

If you ask the user for missing shared/mixed carton confirmations, include the missing weight allocation inputs in the same question.
Do not phrase the weight question as only "provide warehouse gross weight or confirm existing rule"; that is incomplete without per-SKU unit weights or final allocated gross/net weights.

## Start-of-Task Copy

Before matching products, create a fresh local copy of the stock plan:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/copy_latest_stock_plan.ps1 `
  -DestinationDir "C:\path\to\workspace\.analysis"
```

The script returns a JSON record containing the shared source path, source modified time, copy time, and local copy path. Save or include those facts in the run report so it is auditable which stock-plan version was used.

If a new computer cannot access the shared drive, ask the user for the correct network path, VPN/LAN status, or a temporary local file. Treat temporary local files as one-off fallbacks only.

Before final generation, verify desktop Excel COM:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_excel_com.ps1
```

If this script fails, the agent may still do matching, candidate review, and data preparation, but must not create the official final long-template workbook. Ask the user to use a Windows machine with desktop Microsoft Excel installed, or to install/repair Excel.

## New Computer Setup Checklist

On a new machine, confirm these before the first production run:

- The shared-drive stock plan path is reachable and can be copied read-only.
- Desktop Microsoft Excel is installed on Windows, because final generation relies on Excel COM.
- The bundled template `assets/declaration-long-template.xlsx` is still the approved company template, or the user provides the updated template.
- The stock-plan `报关名` columns still match the expected structure, especially `C 产品内容`, `G 申报单价V4`, `H pc/ctn`, `I 单箱毛重`, and `J 单箱净重`.
- The output folder is confirmed.
- Any new destination country code is confirmed by the user before generating the contract number.
- The first generated file is compared against a known-good historical declaration workbook for formulas, row deletion, merged-cell styles, formula cache values, and date formats.

## Product Matching

1. Match by the current task's product name against `报关名!C 产品内容`.
2. Normalize conservatively: remove trailing country/site suffixes such as `UK`, `US`, `CA`, `UC-CA`, `UC`, `DE`, extra spaces, and punctuation. Keep meaningful model, pack count, and product words.
3. If full name fails, extract core terms. Example: `2个装三角拖UK` -> `2个装三角拖`, which can match `2个装三角拖把头`.
4. Use SKU/model only as supporting evidence or tie-breaker after name and pack/quantity plausibility. Do not use SKU as the primary key.
5. If multiple plausible candidates exist, show candidate rows with `产品内容`, `报关商品名称`, `报关规格型号`, `海关编码`, `申报单价V4`, `pc/ctn`, `毛重`, `净重`, and ask the user to choose.
6. If source `pc/ctn` conflicts with the current task, first determine whether it is a true mismatch or a declared 差异箱. For 差异箱, keep the stock-plan `pc/ctn` as the standard, write the current task's actual total quantity, and record `quantity_delta = actual_total - standard_pc_per_ctn * physical_cartons`. If operations/user confirms a true mismatch, write the current task's total quantity and keep source row data for HS/name/elements/weights/price.

For every accepted match, keep an audit record for the final user-facing match table:

- current shipment product name
- current SKU/model
- current `PCS/CTN`, physical cartons, declaration cartons, and total quantity
- matched source row number
- source `C 产品内容`, `D 报关规格型号`, `E 对应平台 SKU`, and `H pc/ctn`
- matched HS code, declaration name, and `申报单价V4`
- match status/notes such as exact match, SKU-assisted match, name differs, pc/ctn differs, shared carton group, or difference carton

When no product row matches, send a Feishu notification before stopping. This step is mandatory even if the user did not ask for notification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/notify_missing_product_lark.ps1 `
  -Product "产品名称" `
  -Sku "平台SKU" `
  -Model "申报型号" `
  -SourceWorkbook "C:\path\to\fresh-stock-plan-copy.xlsx"
```

On this machine, run the installed script path `C:\Users\admin\.codex\skills\customs-declaration-template\scripts\notify_missing_product_lark.ps1` with outside-sandbox permission from the start; do not try to run Lark CLI inside the sandbox first.

The notification script searches `JOJO` in Feishu contacts and sends a direct text message. It has a fallback path for the local Lark CLI, so run the script rather than checking `lark-cli` manually. If the script is blocked by sandbox access to Lark CLI or local credentials, request outside-sandbox permission and retry the same script once. If the send still fails, report only that the notification was not sent.

## Complex Packing Scenarios

For 拼箱/混箱/merged carton cells/差异箱 tasks, normalize the shipment before building the final data JSON. Use `references/packing-scenarios.md` for the full rules and examples.

- Distinguish `physical_cartons` from declaration-row `cartons`. `physical_cartons` is the real box count used for matching and standard quantity math. `cartons` is the value written to `报关资料录入!G`.
- For a shared carton group, never write the same physical carton count on every SKU row. In working JSON, write the group's carton count on the first line of the group and `0` on the other lines, so the package total is not overstated. In the final workbook, merge the `报关资料录入` column `G` cells across that shared group and display the carton count once.
- If the source has visible carton counts `10`, `7`, and one shared `5` with blank cells on adjacent product rows, the package total is `22`, not `37`. Blank carton cells are not independent 5-carton rows.
- Preserve the actual user/source total quantity in `quantity`. Do not silently replace it with `pc/ctn * 箱数`.
- For every line where actual quantity differs from the standard calculation, record the difference in `quantity_delta` and include a short note such as `5箱标准每箱7，实际36，+1`.
- If a difference is larger than 2 units or larger than 5%, ask the user to confirm before final generation.
- Do not multiply full-carton stock weights across every row in a shared carton group unless the user or operations confirms that allocation. Prefer explicit mixed-carton gross/net weights or an approved allocation note.
- If mixed-carton gross/net allocation inputs are missing, stop and ask for them before final workbook generation.
- If the source provides 仓库毛重, SKU 单品重量, and SKU 数量 for a mixed carton, allocate line gross/net weights with `scripts/allocate_mixed_carton_weights.py`; it applies the fixed `仓库毛重 - 1kg` net-weight rule and 2-decimal compensation rounding.
- Even for simulated packing tests, do not simulate HS code, declaration name, declaration elements/申报用途, or unit price if the shared stock-plan source is reachable. Match those fields from the fresh `报关名` copy, and clearly label only the packing-specific fields as simulated.
- Run `scripts/validate_declaration_data.py` on the approved JSON before final generation whenever the task includes 拼箱, 混箱, 合并箱数, or 差异箱.

## Header Rules

Fill these cells on `报关资料录入`:

- `G3`: 申报日期 = actual shipment date / 实际发货时间.
- `E11`: 抵运国 = destination country for this shipment.
- `K10`: 合同日期 = actual shipment date minus 22 days; if that result is Saturday or Sunday, move back to the previous Friday. Write a fixed date value, not the original formula.
- `K9`: 合同协议号 = `HS-{country_code}-{yyyymmdd}` using the adjusted contract date.
- When writing dates with Excel COM, preserve the target cell's existing number format. Do not let Excel auto-change `G3` from the template's date format.

Known country codes:

- 英国 `UK`
- 美国 `US`
- 加拿大 `CA`

Ask the user before inventing a new country code.

## Item Area

On `报关资料录入`, item rows start at row 21. Each item uses two rows: 21/22, 23/24, 25/26, through 79/80. Write only the top-left cell of merged areas.

For item `i`, top row = `21 + (i - 1) * 2`:

- `B{row}`: 项号
- `C{row}`: 海关商品编码 from `报关名!A`
- `E{row}`: 商品名称 from `报关名!B`
- `E{row+1}`: 申报要素/spec string from `报关名!G` or the confirmed generated declaration elements
- `G{row}`: 件数 = declaration-row `cartons`. For shared carton groups, this may be `0` on co-packed rows so physical cartons are counted only once.
- `H{row}`: 毛重 KG = cartons * `报关名!I`, unless the user provides an approved override
- `I{row}`: 净重 KG = cartons * `报关名!J`, unless the user provides an approved override
- `J{row}`: 数量 = current task actual total quantity. If this differs from `pc/ctn * physical_cartons`, record the 差异箱 reason and use the actual total after confirmation.
- `K{row}`: 单位, usually `个`
- `L{row}`: 单价 from `报关名!G 申报单价V4`

## Row Deletion Rules

After filling `n` item lines, delete only extra item rows:

- `报关资料录入`: delete from `21 + 2*n` through `80`
- `报关单`: delete from `20 + 3*n` through `109`
- `装箱单`: delete from `15 + 2*n` through `74`
- `发票`: delete from `15 + n` through `44`
- `合同`: delete from `19 + n` through `48`
- `申报要素`: delete from `6 + n` through `35`
- `存仓委托书` and `报关委托书`: do not delete rows unless the user explicitly asks.

For 9 item lines, this means `报关资料录入 39:80`, `报关单 47:109`, `装箱单 33:74`, `发票 24:44`, `合同 28:48`, and `申报要素 15:35`.

## Known Formula Repair

Excel row deletion in this template may create `#REF!` in four cells on `报关单`. After deletion and before final save, if these cells contain `#REF!`, repair them exactly:

- `报关单!H39` -> `=报关资料录入!J34`
- `报关单!J39` -> `=报关资料录入!K34`
- `报关单!H42` -> `=报关资料录入!J36`
- `报关单!J42` -> `=报关资料录入!K36`

Do not otherwise rewrite downstream formulas.

## File Naming

Final workbook name:

```text
{目的国中文名}{件数}件报关单资料{YYMMDD}.xlsx
```

`件数` means the package/carton total, i.e. the sum of `报关资料录入` column `G`, not the number of product rows. Example: 9 product rows with cartons `10+1+1+4+2+1+6+4+18` is `47件`, so the file name should use `加拿大47件报关单资料260423.xlsx`.

Use actual shipment date for `{YYMMDD}` unless the user says otherwise. If the target file exists, create a `-2`, `-3`, etc. variant instead of overwriting.

Use `scripts/name_declaration_output.py` for naming when convenient.

## Final Generation Script

After product rows are confirmed, create an approved JSON data file and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_long_template_excel_com.ps1 `
  -TemplatePath "C:\path\to\报关单长模板.xlsx" `
  -DataPath "C:\path\to\approved-data.json" `
  -OutputPath "C:\path\to\加拿大47件报关单资料260423.xlsx"
```

The JSON may use either normalized fields or the report shape produced during matching:

```json
{
  "country": "加拿大",
  "ship_date": "2026-04-23",
  "items": [
    {
      "line": 1,
      "hs_code": "8508709000",
      "declaration_name": "吸尘器配件",
      "declaration_elements": "4|0|供真空吸尘器更换使用|MXZONE|TS5PRO",
      "cartons": 10,
      "gross_weight_kg": 164,
      "net_weight_kg": 154,
      "quantity": 300,
      "unit": "个",
      "unit_price_v4": 5.5
    }
  ]
}
```

For shared-carton or difference-carton tasks, include audit fields in each item when available:

```json
{
  "packing": {
    "carton_policy": "first-line-carrier"
  },
  "items": [
    {
      "line": 1,
      "carton_group_id": "mixed-5-a",
      "carton_role": "group-carton-carrier",
      "physical_cartons": 5,
      "pcs_per_carton": 32,
      "quantity_delta": 0,
      "cartons": 5,
      "quantity": 160
    },
    {
      "line": 2,
      "carton_group_id": "mixed-5-a",
      "carton_role": "co-packed-line",
      "physical_cartons": 5,
      "pcs_per_carton": 7,
      "quantity_delta": 1,
      "cartons": 0,
      "quantity": 36,
      "note": "5箱标准每箱7，实际36，+1"
    }
  ]
}
```

For mixed-carton weight allocation, prepare a JSON file shaped like `assets/sample-mixed-carton-weights.json` and run:

```powershell
python scripts/allocate_mixed_carton_weights.py `
  --input assets/sample-mixed-carton-weights.json `
  --output outputs/mixed-carton-weight-allocation.json
```

Before final generation, validate the approved declaration JSON:

```powershell
python scripts/validate_declaration_data.py `
  --input assets/sample-complex-packing-declaration-data.json `
  --output outputs/complex-packing-validation-report.json
```

The script copies the template to the output path, fills `报关资料录入`, deletes extra rows, repairs known `#REF!` formulas, recalculates with Excel, and saves.

## Final Checks

Before returning the workbook:

- Confirm no formula errors such as `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, or `#N/A`.
- Confirm formula caches are present by checking downstream totals after Excel recalculation, especially `装箱单!E35/H35/I35`, `发票!J24`, `合同!J28`, `存仓委托书!C10/C11/D12`, and `报关委托书!B20/C20`.
- Confirm previous merged-cell style risk areas still have styles across all cells: `装箱单!B39:D42`, `发票!B29:D31`, `合同!E30:J31`, `报关委托书!A1:G1`, `报关委托书!A10:G10`, plus merged ranges in `存仓委托书`.
- Confirm destination country, declaration date, contract date, contract number, unit price column, package total, quantity total, gross weight, and net weight.
- For 拼箱/混箱, confirm package total uses unique physical cartons and is not multiplied by product-row count.
- For 差异箱, confirm every non-zero `quantity_delta` is visible in the review notes or report and was not treated as a matching failure.
- Provide a match-audit table for user review. Keep it compact in the final response for normal shipments; for larger shipments, also save a sidecar CSV next to the final workbook.
- The match-audit table must compare current shipment vs source `报关名` at minimum: `本次产品名`, `本次SKU/型号`, `本次PCS/CTN`, `本次箱数/总数量`, `源表行`, `源表产品内容`, `源表SKU/规格型号`, `源表pc/ctn`, `HS编码`, `申报品名`, `申报单价V4`, `匹配备注`.
- If any row has a name mismatch, SKU/model correction, pc/ctn mismatch, shared carton, or difference carton, make that visible in `匹配备注` instead of only mentioning it in prose.
- If a visual/reference workbook is provided, compare sheet structure, formulas, row deletions, and formatting coverage against it.

## Legacy Generic Script

`scripts/fill_template.py` is for simple placeholder templates only. Do not use it to save this long customs declaration workbook.
