param(
    [string]$SourcePath,

    [string]$DestinationDir = ".analysis"
)

$ErrorActionPreference = "Stop"

function U([int[]]$Codes) {
    return -join ($Codes | ForEach-Object { [char]$_ })
}

function Get-DefaultSourcePath {
    $root = "\\192.168.0.118\"
    $company = U @(0x6C90, 0x661F, 0x79D1, 0x6280)
    $amazon = U @(0x4E9A, 0x9A6C, 0x900A)
    $table = U @(0x8868, 0x683C)
    $common = U @(0x5E38, 0x7528)
    $file = (U @(0x0061, 0x006D, 0x007A, 0x5907, 0x8D27, 0x8BA1, 0x5212, 0x0056, 0x0032, 0x0036, 0x0030, 0x0033, 0x0031, 0x0036, 0x002E, 0x0078, 0x006C, 0x0073, 0x0078))
    return $root + $company + "\" + $amazon + "\" + $table + "\" + $common + "\" + $file
}

function Resolve-OutputDir([string]$PathValue) {
    $resolved = $executionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PathValue)
    if (-not (Test-Path -LiteralPath $resolved)) {
        New-Item -ItemType Directory -Path $resolved | Out-Null
    }
    return $resolved
}

if (-not $SourcePath) {
    $SourcePath = Get-DefaultSourcePath
}

if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw "Stock-plan source is not reachable. Ask the user to confirm network access or provide a temporary local copy."
}

$sourceItem = Get-Item -LiteralPath $SourcePath
$destinationFullPath = Resolve-OutputDir $DestinationDir
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destinationPath = Join-Path $destinationFullPath ("amz-stock-plan-current-" + $timestamp + ".xlsx")

Copy-Item -LiteralPath $SourcePath -Destination $destinationPath -Force
$copyItem = Get-Item -LiteralPath $destinationPath

$result = [ordered]@{
    source_path = $SourcePath
    source_last_write_time = $sourceItem.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
    copied_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    local_copy_path = $copyItem.FullName
    local_copy_size = $copyItem.Length
}

$result | ConvertTo-Json -Depth 3
