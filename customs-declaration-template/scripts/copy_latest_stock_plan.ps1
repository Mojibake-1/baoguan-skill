# Copy the latest AMZ stock-plan workbook from the shared drive to a local
# .analysis snapshot. Operations re-versions the workbook (amz<plan>V<YYMMDD>)
# whenever they update it, so the source file name is never fixed: this script
# always scans the shared folder and picks the newest version.

param(
    [string]$SourcePath,

    [string]$DestinationDir = ".analysis"
)

$ErrorActionPreference = "Stop"

function U([int[]]$Codes) {
    return -join ($Codes | ForEach-Object { [char]$_ })
}

# Shared-drive folder that holds the AMZ stock-plan workbook.
function Get-StockPlanDir {
    $root = "\\192.168.0.118\"
    $company = U @(0x6C90, 0x661F, 0x79D1, 0x6280)
    $amazon = U @(0x4E9A, 0x9A6C, 0x900A)
    $table = U @(0x8868, 0x683C)
    $common = U @(0x5E38, 0x7528)
    return $root + $company + "\" + $amazon + "\" + $table + "\" + $common
}

# Newest AMZ stock-plan workbook in a folder, ranked by the V<YYMMDD> version
# stamp in the file name, then by last-write time. Excel lock files (~$...)
# are ignored.
function Get-LatestStockPlan([string]$Dir) {
    $prefix = "amz" + (U @(0x5907, 0x8D27, 0x8BA1, 0x5212))
    $candidates = @(Get-ChildItem -LiteralPath $Dir -File |
        Where-Object { $_.Name -like ($prefix + "*.xlsx") -and $_.Name -notlike '~$*' })
    if ($candidates.Count -eq 0) {
        throw "No AMZ stock-plan workbook ($prefix*.xlsx) found in: $Dir"
    }
    $ranked = $candidates | Sort-Object `
        @{ Expression = { if ($_.BaseName -match 'V(\d+)') { [int64]$Matches[1] } else { [int64]0 } }; Descending = $true }, `
        @{ Expression = { $_.LastWriteTime }; Descending = $true }
    return @($ranked)[0].FullName
}

function Resolve-OutputDir([string]$PathValue) {
    $resolved = $executionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PathValue)
    if (-not (Test-Path -LiteralPath $resolved)) {
        New-Item -ItemType Directory -Path $resolved | Out-Null
    }
    return $resolved
}

# Resolve the source workbook:
#   (no -SourcePath)      scan the shared-drive folder, take the latest
#   -SourcePath <folder>  scan that folder, take the latest
#   -SourcePath <file>    use that file as-is (explicit override)
$selectionMode = "explicit-file"
if (-not $SourcePath) {
    $dir = Get-StockPlanDir
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
        throw "Stock-plan shared folder is not reachable: $dir. Confirm network access to the shared drive."
    }
    $SourcePath = Get-LatestStockPlan $dir
    $selectionMode = "latest-in-share"
}
elseif (Test-Path -LiteralPath $SourcePath -PathType Container) {
    $SourcePath = Get-LatestStockPlan $SourcePath
    $selectionMode = "latest-in-folder"
}

if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw "Stock-plan source is not reachable: $SourcePath. Ask the user to confirm network access or provide a temporary local copy."
}

$sourceItem = Get-Item -LiteralPath $SourcePath
$destinationFullPath = Resolve-OutputDir $DestinationDir
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destinationPath = Join-Path $destinationFullPath ("amz-stock-plan-current-" + $timestamp + ".xlsx")

Copy-Item -LiteralPath $SourcePath -Destination $destinationPath -Force
$copyItem = Get-Item -LiteralPath $destinationPath

$result = [ordered]@{
    selection_mode         = $selectionMode
    source_path            = $SourcePath
    source_file_name       = $sourceItem.Name
    source_last_write_time = $sourceItem.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
    copied_at              = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    local_copy_path        = $copyItem.FullName
    local_copy_size        = $copyItem.Length
}

$result | ConvertTo-Json -Depth 3
