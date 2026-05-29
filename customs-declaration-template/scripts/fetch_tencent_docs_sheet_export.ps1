param(
    [Parameter(Mandatory = $true)][string]$FileId,
    [Parameter(Mandatory = $true)][string]$SheetId,
    [string]$OutputPath,
    [int]$PollSeconds = 5,
    [int]$TimeoutSeconds = 180,
    [switch]$Force
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

function Get-XlsxMediaCount {
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
        try {
            return @($zip.Entries | Where-Object {
                $_.FullName -like "xl/media/*" -or $_.FullName -like "xl/drawings/media/*"
            }).Count
        } finally {
            $zip.Dispose()
        }
    } catch {
        return $null
    }
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $downloadDir = Join-Path (Get-Location) ".analysis\tencent-docs"
    $OutputPath = Join-Path $downloadDir "$FileId-$SheetId-latest.xlsx"
}

$OutputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
$MetadataPath = [System.IO.Path]::ChangeExtension($OutputPath, ".metadata.json")
$outputDir = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$fileInfo = Invoke-TencentDocsTool -Tool "manage.query_file_info" -Arguments @("file_id=$FileId")
if ($fileInfo.type -ne "sheet") {
    throw "Tencent Docs file $FileId is type '$($fileInfo.type)', expected 'sheet'"
}

$sheetInfo = Invoke-TencentDocsTool -Tool "sheet.get_sheet_info" -Arguments @("file_id=$FileId")
$targetSheet = @($sheetInfo.sheets | Where-Object { $_.sheet_id -eq $SheetId }) | Select-Object -First 1
if ($null -eq $targetSheet) {
    $knownSheets = (@($sheetInfo.sheets | ForEach-Object { "$($_.sheet_name):$($_.sheet_id)" }) -join ", ")
    throw "Sheet id $SheetId not found in $FileId. Known sheets: $knownSheets"
}

if (-not $Force -and (Test-Path -LiteralPath $OutputPath) -and (Test-Path -LiteralPath $MetadataPath)) {
    $cached = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json
    $currentWorkbookSha256 = Get-FileSha256 -Path $OutputPath
    $cacheMatches = (
        $cached.fileId -eq $FileId -and
        $cached.sheetId -eq $SheetId -and
        $cached.lastModifyTime -eq $fileInfo.last_modify_time -and
        [int]$cached.rowCount -eq [int]$targetSheet.row_count -and
        [int]$cached.colCount -eq [int]$targetSheet.col_count -and
        $cached.workbookSha256 -eq $currentWorkbookSha256
    )

    if ($cacheMatches) {
        $result = [ordered]@{
            fileId = $FileId
            sheetId = $SheetId
            title = $fileInfo.title
            sheetName = $targetSheet.sheet_name
            rowCount = $targetSheet.row_count
            colCount = $targetSheet.col_count
            lastModifyTime = $fileInfo.last_modify_time
            outputPath = $OutputPath
            metadataPath = $MetadataPath
            bytes = (Get-Item -LiteralPath $OutputPath).Length
            workbookSha256 = $currentWorkbookSha256
            mediaCount = Get-XlsxMediaCount -Path $OutputPath
            skippedDownload = $true
            skipReason = "local workbook hash and metadata match Tencent Docs"
        }

        $result | ConvertTo-Json -Depth 4
        exit 0
    }
}

$exportTask = Invoke-TencentDocsTool -Tool "manage.export_file" -Arguments @("file_id=$FileId")
if ([string]::IsNullOrWhiteSpace($exportTask.task_id)) {
    throw "Tencent Docs export did not return task_id"
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$progress = $null
do {
    Start-Sleep -Seconds $PollSeconds
    $progress = Invoke-TencentDocsTool -Tool "manage.export_progress" -Arguments @("task_id=$($exportTask.task_id)")
    if ([int]$progress.progress -ge 100 -and -not [string]::IsNullOrWhiteSpace($progress.file_url)) {
        break
    }
} while ((Get-Date) -lt $deadline)

if ($null -eq $progress -or [int]$progress.progress -lt 100 -or [string]::IsNullOrWhiteSpace($progress.file_url)) {
    throw "Tencent Docs export did not finish within $TimeoutSeconds seconds"
}

Invoke-WebRequest -Uri $progress.file_url -OutFile $OutputPath -UseBasicParsing

$downloadedAt = (Get-Date).ToString("o")
$mediaCount = Get-XlsxMediaCount -Path $OutputPath
$workbookSha256 = Get-FileSha256 -Path $OutputPath

$metadata = [ordered]@{
    fileId = $FileId
    sheetId = $SheetId
    title = $fileInfo.title
    sheetName = $targetSheet.sheet_name
    rowCount = $targetSheet.row_count
    colCount = $targetSheet.col_count
    createName = $fileInfo.create_name
    createTime = $fileInfo.create_time
    lastModifyName = $fileInfo.last_modify_name
    lastModifyTime = $fileInfo.last_modify_time
    downloadedAt = $downloadedAt
    workbookSha256 = $workbookSha256
    mediaCount = $mediaCount
}

$metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $MetadataPath -Encoding UTF8

$result = [ordered]@{
    fileId = $FileId
    sheetId = $SheetId
    title = $fileInfo.title
    sheetName = $targetSheet.sheet_name
    rowCount = $targetSheet.row_count
    colCount = $targetSheet.col_count
    lastModifyTime = $fileInfo.last_modify_time
    outputPath = $OutputPath
    metadataPath = $MetadataPath
    bytes = (Get-Item -LiteralPath $OutputPath).Length
    workbookSha256 = $workbookSha256
    mediaCount = $mediaCount
    skippedDownload = $false
}

$result | ConvertTo-Json -Depth 4
