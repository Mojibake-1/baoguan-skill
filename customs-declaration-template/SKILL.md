---
name: customs-declaration-template
description: Generate Chinese customs declaration workbooks from the company long Excel template 报关单长模板.xlsx and the AMZ stock-plan workbook sheet 报关名. Use when the user asks to make 报关单/报关资料/装箱单/发票/合同 from the long template, mentions 报关资料录入, amz备货计划, 报关名, 申报单价V4, 拼箱/混箱/合并箱数/差异箱/多一两个/少一两个, or needs the template copied, filled, formula-checked, and trimmed without changing source files.
---

# Customs Declaration Long Template

Use this skill for the fixed company workflow: copy the long Excel template, fill only `报关资料录入`, let later sheets calculate from formulas, then delete extra item rows. This is not a generic placeholder-template workflow.

## Multi-Declaration Subagent Dispatch

When a source workbook contains multiple declaration tickets/workbooks and subagents are available, split the source into ticket-scoped inputs first, then dispatch one worker subagent per declaration ticket. Each worker owns exactly one declaration workbook and must only write its own ticket-scoped `.analysis/.../ticket-*` files and output workbook; do not assign one worker to generate multiple tickets.

Use the newest available model for these workers with `reasoning_effort=xhigh` (currently prefer GPT-5.5 when available). The main agent remains responsible for shared source copying, ticket splitting, supplement files, final cross-ticket reconciliation, edits to renamed final outputs, and final Excel COM validation. Each worker must report changed paths, carton/quantity totals, validation output, and blockers. If product matching, brand, store ownership, carton packing, or red-marked difference boxes are ambiguous, the worker must stop and report the blocker instead of inventing data.

## Required Run Order

1. Collect the current shipment list, declaration-document date (the date the customs declaration workbook is being made; default to today's local date if the user does not specify another date), destination country/station, and any packing-specific inputs.
2. Normalize packing before product matching conclusions: blank carton cells, merged carton cells, 拼箱/混箱, and 差异箱 must be resolved first.
3. For any shared/mixed carton group, collect either final allocated gross/net weights with a source note, or the allocation inputs: group warehouse gross weight, each SKU's unit product weight, and whether quantities are per carton or total.
4. Match products against `报关名`. If a product cannot be matched or has multiple plausible candidates, stop and ask the user with the candidate rows.
5. Before adopting any matched row, validate the `报关名` row integrity rules below, especially `报关规格型号` vs `申报用途/申报要素` tail consistency, brand code consistency, and required source fields. If a matched row fails, stop before JSON/workbook generation.
6. Build a declaration JSON and run `scripts/validate_declaration_data.py --source-shipment-json <ticket-source.json>` before Excel generation. This source-quantity audit is mandatory for every real declaration JSON that has `source_row` or `source_rows`, and it is especially mandatory for 拼箱/混箱/合并箱数/差异箱. Do not generate the workbook if validation has errors.
7. Only after validation passes, create the final workbook with Excel COM.
8. Return the final workbook path(s) and concise validation notes. Do not include a full match-audit table by default.

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
- Treat a `报关名` row as invalid if `报关规格型号` does not match the last pipe-separated segment of `申报用途/申报要素`. This is a source-data error, not a tolerable match. Do not silently use the row, and do not rewrite the tail yourself unless the user explicitly confirms the correct source value.
- Treat a `报关名` row as invalid if `申报用途/申报要素` brand logic is inconsistent: penultimate segment `无牌` requires first segment `0`; any named brand such as `MXZONE` or `Ucoolbe` requires first segment `4`.
- Treat a `报关名` row as incomplete if the row used for the declaration lacks the new `申报单价V4`, `pc/ctn`, `单箱毛重`, or `单箱净重`. Stop and notify operations before generating the workbook. The old `申报单价` / `申报单价F` column is not a fallback.
- Do not send a full current-shipment-vs-`报关名` match table in every final response. Only show matching details when something is unmatched, ambiguous, or needs the user's choice.
- `pc/ctn` is not completely fixed. A source `pc/ctn` difference by itself is not an unmatched-product problem and should not trigger a user-facing warning unless it affects carton math, mixed-carton allocation, or a real quantity discrepancy that needs confirmation.
- Shipment source quantity is the declaration quantity source of truth. For every item with `source_row` or `source_rows`, `quantity` must equal the original AMZ/ticket source row quantity sum exactly. This includes red-marked difference quantities. Mixed-carton allocation inputs are allowed to allocate gross/net weights only; they must never overwrite `quantity`.
- Treat `source_quantity_mismatch` or `missing_source_quantity_audit` from `scripts/validate_declaration_data.py` as a hard blocker. Do not downgrade it to a warning, and do not proceed because Excel totals match the generated JSON.

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
  - `D`: 单位, support only; final workbook still writes `个`
  - `E`: 报关规格型号 / model reference
  - `F`: 对应平台 SKU, support only, not the primary key
  - `H`: 申报单价V4, the current unit-price column
  - `I`: 申报用途 / 申报要素, copied into `报关资料录入!E{row+1}`
  - `J`: pc/ctn
  - `K`: 单箱毛重
  - `L`: 单箱净重
- Do not use old price columns such as `G` when the user says to use `申报单价V4`.

## 报关名 Row Integrity Rules

Apply these checks to fresh shared-drive `报关名` rows, user-provided copied rows, supplement rows, and final declaration JSON before generating a workbook:

- `报关规格型号` is the model code in `报关名!E`, such as `MF001`.
- `申报用途/申报要素` is the pipe-separated declaration element string in `报关名!I`, such as `0|0|供真空吸尘器更换使用|无牌|MF001`.
- The last non-empty segment after `|` in `申报用途/申报要素` must equal `报关规格型号` after trimming whitespace. Example: `E=MF001` and `I=...|MF001` is valid; `E=MF001` and `I=...|PET001` is invalid.
- The penultimate `申报用途/申报要素` segment is the brand marker. If it is `无牌`, the first segment must be `0`. If it is a named brand, including `MXZONE`, `Ucoolbe`, or another non-empty brand name, the first segment must be `4`.
- `申报单价V4` in `报关名!H` is the only allowed unit price source. Do not read or copy the old `申报单价` / `申报单价F` column, even if it has a value and V4 is blank.
- The matched source row must have the new `申报单价V4`, `pc/ctn`, `单箱毛重`, and `单箱净重`. If any are blank, this is not an agent-fillable value; stop and notify operations.
- A mismatch or missing required source field means the row, copied source, or supplement is wrong. Stop and show the source row, product content, SKU, `报关规格型号`, the full `申报用途/申报要素`, and the missing/conflicting field. Ask the user or operations to correct the source row or provide the correct row.
- When building declaration JSON, preserve either top-level `stock_model`/`spec_model` or `matched_stock_row.model`, and preserve `matched_stock_row.unit_price_v4`, `matched_stock_row.stock_pc_per_carton`, `matched_stock_row.gross_per_carton`, and `matched_stock_row.net_per_carton` so `scripts/validate_declaration_data.py` can enforce these checks.

If `scripts/validate_declaration_data.py` reports `missing_stock_source_fields`, run the notification script once before stopping:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/notify_missing_product_lark.ps1 `
  -Product "产品名称" `
  -Sku "平台SKU" `
  -Model "报关规格型号" `
  -SourceWorkbook "C:\path\to\fresh-stock-plan-copy.xlsx" `
  -Reason "源数据表「报关名」中本次报关行缺少必填字段，不能生成报关单。旧申报单价不能替代申报单价V4。" `
  -MissingFields "申报单价V4, pc/ctn, 单箱毛重"
```

## Daily Invocation

If the user says only "帮我做报关单" or similar, assume this skill should run. The user is expected to provide the current shipment list in the message or as a spreadsheet/screenshot. The minimum per-task inputs are:

- current product list / 本次要做的货物清单
- declaration-document date / 报关单资料制作日期（默认今天；不要默认使用实际发货日期）
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
- The stock-plan `报关名` columns still match the expected structure, especially `C 产品内容`, `E 报关规格型号`, `H 申报单价V4`, `I 申报用途/申报要素`, `J pc/ctn`, `K 单箱毛重`, and `L 单箱净重`.
- The output folder is confirmed.
- Any new destination country code is confirmed by the user before generating the contract number.
- The first generated file is compared against a known-good historical declaration workbook for formulas, row deletion, merged-cell styles, formula cache values, and date formats.

## Product Matching

1. Match by the current task's product name against `报关名!C 产品内容`.
2. Normalize conservatively: remove trailing country/site suffixes such as `UK`, `US`, `CA`, `UC-CA`, `UC`, `DE`, extra spaces, and punctuation. Keep meaningful model, pack count, and product words.
3. If full name fails, extract core terms. Example: `2个装三角拖UK` -> `2个装三角拖`, which can match `2个装三角拖把头`.
4. Use SKU/model only as supporting evidence or tie-breaker after name and pack/quantity plausibility. Do not use SKU as the primary key.
5. If multiple plausible candidates exist, show candidate rows with `产品内容`, `报关商品名称`, `报关规格型号`, `申报用途/申报要素`, `海关编码`, `申报单价V4`, `pc/ctn`, `毛重`, `净重`, and ask the user to choose.
6. If source `pc/ctn` conflicts with the current task, do not treat that alone as a failed match. Use the current task's actual total quantity and carton data. Only ask the user when the product identity is unclear, the quantity discrepancy is not explained by the shipment source, or the mixed-carton weight allocation depends on the conflict.

## Unmatched or Ambiguous Match Output

Do not output a full matching table after every successful task.

Only show matching details to the user when:

- no `报关名` row can be matched for a current product;
- multiple plausible candidates exist and the user must choose;
- product name/SKU/model evidence conflicts enough to affect the HS code, declaration name, declaration elements, model-tail consistency, brand code consistency, required source fields, or unit price;
- a quantity/difference-carton issue exceeds the confirmation threshold and is not already clearly marked by the user's source.

When asking the user, include the relevant candidate rows with `产品内容`, `报关商品名称`, `报关规格型号`, `申报用途/申报要素`, `海关编码`, `申报单价V4`, `pc/ctn`, `毛重`, and `净重`.

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
- In mixed-carton groups, use allocation-input SKU quantities only as the denominator for weight allocation. After allocation, reset/verify each declaration item `quantity` against the AMZ/ticket source row quantity. If the allocation input quantity differs from the source row quantity, the source row quantity wins for declaration `quantity`, and the mismatch must be visible in the validation report before generation.
- Red-marked quantity cells are intentional operational overrides, not values to recalculate. Never replace a red source quantity with a carton-standard quantity, stock-plan `pc/ctn`, or mixed-carton allocation quantity.
- For every line where actual quantity differs from the standard calculation, record the difference in `quantity_delta` and include a short note such as `5箱标准每箱7，实际36，+1`.
- If a difference is larger than 2 units or larger than 5%, ask the user to confirm before final generation.
- Do not multiply full-carton stock weights across every row in a shared carton group unless the user or operations confirms that allocation. Prefer explicit mixed-carton gross/net weights or an approved allocation note.
- If mixed-carton gross/net allocation inputs are missing, stop and ask for them before final workbook generation.
- If the source provides 仓库毛重, SKU 单品重量, and SKU 数量 for a mixed carton, allocate line gross/net weights with `scripts/allocate_mixed_carton_weights.py`; it applies the fixed `仓库毛重 - 1kg` net-weight rule and 2-decimal compensation rounding.
- Even for simulated packing tests, do not simulate HS code, declaration name, declaration elements/申报用途, or unit price if the shared stock-plan source is reachable. Match those fields from the fresh `报关名` copy, and clearly label only the packing-specific fields as simulated.
- Run `scripts/validate_declaration_data.py --source-shipment-json <ticket-source.json>` on the approved JSON before final generation. If the declaration JSON contains `source_row` or `source_rows` and the validator is run without the source file, validation must fail.

## Header Rules

Fill these cells on `报关资料录入`:

- `G3`: 申报日期 = declaration-document date / 做报关单资料当天日期. This is not the actual shipment date unless the user explicitly says the declaration-document date should be the shipment date.
- `E11`: 抵运国 = destination country for this shipment.
- `K10`: 合同日期 = declaration-document date minus 22 days; if that result is Saturday or Sunday, move back to the previous Friday. Write a fixed date value, not the original formula.
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
- `E{row+1}`: 申报要素/spec string from `报关名!I` or the confirmed generated declaration elements
- `G{row}`: 件数 = declaration-row `cartons`. For shared carton groups, this may be `0` on co-packed rows so physical cartons are counted only once.
- `H{row}`: 毛重 KG = cartons * `报关名!K`, unless the user provides an approved override
- `I{row}`: 净重 KG = cartons * `报关名!L`, unless the user provides an approved override
- `J{row}`: 数量 = original AMZ/ticket source row quantity sum for that declaration item. If this differs from `pc/ctn * physical_cartons`, record the 差异箱 reason and use the source actual quantity after confirmation. Do not take `J{row}` from mixed-carton allocation inputs except when the user explicitly identifies those inputs as the corrected AMZ source quantity.
- `K{row}`: 单位 = `个`. Always write `个` for every declaration item; do not copy `报关名` or JSON item-level units such as `套`.
- `L{row}`: 单价 from `报关名!H 申报单价V4` only. Do not fall back to the old `申报单价` / `申报单价F` column.

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
{物流商简称}{目的国代码小写}{件数}件报关单资料{YYMMDD}.xlsx
```

Use the current shipment source column `物流商及渠道` for the filename prefix whenever it is present, so operations do not need to rename files later. Normalize it to the recognizable logistics/vendor prefix:

- `宝通达纽约卡派` or other `宝通达...` -> `宝通达`
- `海光普船海卡` or other `海光...` -> `海光`
- otherwise use the leading logistics/vendor name from the cell, removing route/channel suffixes only when obvious.

If multiple logistics channels are combined into one declaration workbook, ask the user which prefix to use unless all channels share the same vendor prefix.

Always append the destination country code in lowercase after the logistics prefix. Known examples:

- `宝通达纽约卡派` + 美国 + 26件 + 2026-04-30 -> `宝通达us26件报关单资料260430.xlsx`
- `海光普船海卡` + 美国 + 40件 + 2026-04-30 -> `海光us40件报关单资料260430.xlsx`

Known lowercase country codes: 美国 `us`, 英国 `uk`, 加拿大 `ca`. Ask before inventing a new country code.

`件数` means the package/carton total, i.e. the sum of `报关资料录入` column `G`, not the number of product rows. Example: 9 product rows with cartons `10+1+1+4+2+1+6+4+18` is `47件`, so a Canada file with no logistics channel could be `加拿大47件报关单资料260423.xlsx`.

Use declaration-document date for `{YYMMDD}` unless the user says otherwise. Do not use actual shipment date for the filename by default. If the target file exists, create a `-2`, `-3`, etc. variant instead of overwriting.

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
  "declaration_date": "2026-04-23",
  "items": [
    {
      "line": 1,
      "hs_code": "8508709000",
      "declaration_name": "吸尘器配件",
      "declaration_elements": "4|0|供真空吸尘器更换使用|MXZONE|TS5PRO",
      "stock_model": "TS5PRO",
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

Before final generation on a real declaration, validate the approved declaration JSON against the original extracted ticket source:

```powershell
python scripts/validate_declaration_data.py `
  --input .analysis/tickets-YYMMDD/ticket-XX-declaration-data.json `
  --source-shipment-json .analysis/tickets-YYMMDD/ticket-XX-source.json `
  --output .analysis/tickets-YYMMDD/ticket-XX-validation-report.json
```

The script copies the template to the output path, fills `报关资料录入`, deletes extra rows, repairs known `#REF!` formulas, recalculates with Excel, and saves.

## Final Checks

Before returning the workbook:

- Confirm no formula errors such as `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, or `#N/A`.
- Confirm formula caches are present by checking downstream totals after Excel recalculation, especially `装箱单!E35/H35/I35`, `发票!J24`, `合同!J28`, `存仓委托书!C10/C11/D12`, and `报关委托书!B20/C20`.
- Confirm previous merged-cell style risk areas still have styles across all cells: `装箱单!B39:D42`, `发票!B29:D31`, `合同!E30:J31`, `报关委托书!A1:G1`, `报关委托书!A10:G10`, plus merged ranges in `存仓委托书`.
- Confirm destination country, declaration date, contract date, contract number, unit price column, package total, quantity total, gross weight, and net weight.
- Independently compare each final `报关资料录入!J` quantity against the original AMZ/ticket source row quantity sum, not only against the declaration JSON. Excel matching JSON is insufficient if the JSON was built from the wrong quantity source.
- Confirm every item with `stock_model`, `spec_model`, or `matched_stock_row.model` has `declaration_elements` whose last `|` segment matches that model.
- Confirm every `declaration_elements` string uses `0|` when the brand segment is `无牌`, and `4|` when the brand segment is a named brand such as `MXZONE` or `Ucoolbe`.
- Confirm every matched stock row used for generation has the new `申报单价V4`, `pc/ctn`, `单箱毛重`, and `单箱净重`; if any are missing, stop and notify operations. A present old `申报单价` / `申报单价F` still counts as missing price if `申报单价V4` is blank.
- For 拼箱/混箱, confirm package total uses unique physical cartons and is not multiplied by product-row count.
- For 差异箱, confirm every non-zero `quantity_delta` is accounted for in the working notes/report, was not treated as a matching failure, and still equals the original source row actual quantity.
- If every product matched cleanly, return only the workbook path(s) and concise validation notes. Do not include a full match-audit table by default.
- If any product is unmatched or ambiguous, stop and ask the user with the candidate/missing-product details before generating the final workbook.
- If a visual/reference workbook is provided, compare sheet structure, formulas, row deletions, and formatting coverage against it.

## Legacy Generic Script

`scripts/fill_template.py` is for simple placeholder templates only. Do not use it to save this long customs declaration workbook.
