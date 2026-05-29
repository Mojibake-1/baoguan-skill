# Tencent Docs MCP Agent Notes

This skill can use Tencent Docs MCP for the online declaration shipment/work-scope source.

| Purpose | URL file token | `sheet_id` | Expected title | Expected sheet |
| --- | --- | --- | --- | --- |
| Shipment/work-scope selection | `DRE1ZTlhoZVZBVkdL` | `000001` | `AMZ备货计划及出货安排表` | `备货详情` |

## Authorization Model

Treat Tencent Docs MCP as an internal runtime dependency. The agent should use the locally configured `tencent-docs` server when it exists, including any existing authorization available to the current runtime.

Do not store Tencent Docs tokens, Authorization headers, cookies, or copied `mcporter.json` contents inside this repository, skill zip, chat output, or declaration workbooks. The skill should only document commands and checks.

If authorization is missing, first surface the minimal blocker: local Tencent Docs MCP is not authorized for the current runtime. If the user asks the agent to fix authorization, use:

```powershell
mcporter auth tencent-docs
```

If OAuth is unavailable, use the official Tencent Docs skill's manual token flow locally. Keep the token only in local `mcporter` configuration or environment. Do not ask the user to resend the online sheet until local MCP authorization has been checked and found unavailable.

## Health Check

Run this after any Tencent Docs failure, after runtime environment changes, or before falling back to user-supplied exports:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_tencent_docs_mcp.ps1
```

Expected result: JSON with `ok: true`, the work-scope document listed, and no `errors`.

Use `-IncludeCellSample` only for debugging. It reads the first few rows from the sheet and can expose operational table content in terminal output.

## Calling Convention

Use `--server` and `--tool`; do not call dotted tool names as `tencent-docs.sheet.get_sheet_info`, because some `mcporter` versions parse that as server `tencent-docs` and tool `sheet`.

```powershell
mcporter call --server tencent-docs --tool "manage.query_file_info" file_id=DRE1ZTlhoZVZBVkdL --output json
mcporter call --server tencent-docs --tool "sheet.get_sheet_info" file_id=DRE1ZTlhoZVZBVkdL --output json
mcporter call --server tencent-docs --tool "sheet.get_cell_data" file_id=DRE1ZTlhoZVZBVkdL sheet_id=000001 start_row=0 start_col=0 return_csv=true --output json
```

## Local Exports And Cache

Use the helper script instead of writing ad-hoc export code:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/fetch_shipment_work_scope_from_tencent_docs.ps1
```

The helper writes an `.metadata.json` sidecar next to the downloaded `.xlsx` under `.analysis/tencent-docs/`. On later runs it compares `file_id`, `sheet_id`, online `last_modify_time`, sheet row/column counts, and local workbook SHA-256. If there is no detected difference, it returns `skippedDownload=true` and reuses the local workbook.

Use `-Force` only when a fresh export is intentionally required.

## Troubleshooting

| Symptom | Agent action |
| --- | --- |
| `mcporter` not found | Install or expose `mcporter` in PATH for the current Windows user. |
| `Authorization required` / token error | Run `mcporter auth tencent-docs` in the current runtime environment. |
| `工具: "sheet" 没有注册` or `工具: "manage" 没有注册` | Use `mcporter call --server tencent-docs --tool "sheet.get_sheet_info" ...` rather than a dotted selector. |
| Expected sheet ID missing | Re-check the Tencent Docs file URL/tab and update `SKILL.md` plus `references/work-scope-schema.md` before running declaration generation. |
| Export succeeds but data looks stale | Run the helper with `-Force`, then re-run the health check. |
