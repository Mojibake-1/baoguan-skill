param(
    [switch]$IncludeCellSample
)

$ErrorActionPreference = "Stop"

function Invoke-TencentDocsTool {
    param(
        [Parameter(Mandatory = $true)][string]$Tool,
        [string[]]$Arguments = @()
    )

    $mcporterArgs = @(
        "call",
        "--server", "tencent-docs",
        "--tool", $Tool
    ) + $Arguments + @("--output", "json")

    $raw = & mcporter @mcporterArgs
    if ($LASTEXITCODE -ne 0) {
        throw "mcporter call failed for $Tool"
    }

    $text = ($raw | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "mcporter returned empty output for $Tool"
    }

    return $text | ConvertFrom-Json
}

$docs = @(
    [ordered]@{
        key = "shipmentWorkScope"
        fileId = "DRE1ZTlhoZVZBVkdL"
        sheetId = "000001"
        purpose = "customs declaration shipment/work-scope selection"
    }
)

$result = [ordered]@{
    ok = $true
    mcporterFound = $false
    tencentDocsServerListed = $false
    docs = @()
    errors = @()
    hints = @()
}

if ($null -eq (Get-Command mcporter -ErrorAction SilentlyContinue)) {
    $result.ok = $false
    $result.errors += "mcporter not found in PATH"
    $result.hints += "Install mcporter or run from the Windows user profile where mcporter is configured."
    $result | ConvertTo-Json -Depth 8
    exit 1
}

$result.mcporterFound = $true

try {
    $listOutput = & mcporter list tencent-docs
    if ($LASTEXITCODE -eq 0 -and (($listOutput | Out-String) -match "tencent-docs")) {
        $result.tencentDocsServerListed = $true
    } else {
        $result.ok = $false
        $result.errors += "tencent-docs server is not listed by mcporter"
        $result.hints += "Run mcporter auth tencent-docs or configure the tencent-docs MCP server for this Windows user."
    }
} catch {
    $result.ok = $false
    $result.errors += "failed to list tencent-docs server: $($_.Exception.Message)"
    $result.hints += "Run mcporter auth tencent-docs or configure the tencent-docs MCP server for this Windows user."
}

foreach ($doc in $docs) {
    $docResult = [ordered]@{
        key = $doc.key
        fileId = $doc.fileId
        sheetId = $doc.sheetId
        ok = $true
    }

    try {
        $fileInfo = Invoke-TencentDocsTool -Tool "manage.query_file_info" -Arguments @("file_id=$($doc.fileId)")
        $sheetInfo = Invoke-TencentDocsTool -Tool "sheet.get_sheet_info" -Arguments @("file_id=$($doc.fileId)")
        $targetSheet = @($sheetInfo.sheets | Where-Object { $_.sheet_id -eq $doc.sheetId }) | Select-Object -First 1

        $docResult.title = $fileInfo.title
        $docResult.lastModifyTime = $fileInfo.last_modify_time
        $docResult.type = $fileInfo.type
        $docResult.purpose = $doc.purpose

        if ($fileInfo.type -ne "sheet") {
            $docResult.ok = $false
            $docResult.typeMismatch = $true
            $result.ok = $false
            $result.errors += "$($doc.key): expected file type 'sheet' but got '$($fileInfo.type)'"
        }

        if ($null -eq $targetSheet) {
            $knownSheets = (@($sheetInfo.sheets | ForEach-Object { "$($_.sheet_name):$($_.sheet_id)" }) -join ", ")
            $docResult.ok = $false
            $docResult.sheetMissing = $true
            $docResult.knownSheets = $knownSheets
            $result.ok = $false
            $result.errors += "$($doc.key): sheet id '$($doc.sheetId)' not found"
        } else {
            $docResult.sheetName = $targetSheet.sheet_name
            $docResult.rowCount = $targetSheet.row_count
            $docResult.colCount = $targetSheet.col_count
        }

        if ($IncludeCellSample -and $null -ne $targetSheet) {
            $cellData = Invoke-TencentDocsTool -Tool "sheet.get_cell_data" -Arguments @(
                "file_id=$($doc.fileId)",
                "sheet_id=$($doc.sheetId)",
                "start_row=0",
                "end_row=5",
                "start_col=0",
                "end_col=10",
                "return_csv=true"
            )
            $docResult.cellSampleCsv = $cellData.csv_data
        }
    } catch {
        $docResult.ok = $false
        $docResult.error = $_.Exception.Message
        $result.ok = $false
        $result.errors += "$($doc.key): $($_.Exception.Message)"
    }

    $result.docs += $docResult
}

if (-not $result.ok) {
    $result.hints += "Do not ask the user to resend Tencent Docs files until this health check has been tried."
    $result.hints += "Do not commit or print Tencent Docs tokens. Re-authorize locally with mcporter auth tencent-docs when needed."
}

$result | ConvertTo-Json -Depth 8

if ($result.ok) {
    exit 0
}

exit 1
