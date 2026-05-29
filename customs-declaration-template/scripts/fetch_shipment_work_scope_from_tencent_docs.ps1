param(
    [string]$OutputPath = "",
    [int]$PollSeconds = 5,
    [int]$TimeoutSeconds = 180,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $downloadDir = Join-Path (Get-Location) ".analysis\tencent-docs"
    $OutputPath = Join-Path $downloadDir "shipment-work-scope-latest.xlsx"
}

$fetchScript = Join-Path $PSScriptRoot "fetch_tencent_docs_sheet_export.ps1"
$args = @{
    FileId = "DRE1ZTlhoZVZBVkdL"
    SheetId = "000001"
    OutputPath = $OutputPath
    PollSeconds = $PollSeconds
    TimeoutSeconds = $TimeoutSeconds
}

if ($Force) {
    & $fetchScript @args -Force
} else {
    & $fetchScript @args
}
