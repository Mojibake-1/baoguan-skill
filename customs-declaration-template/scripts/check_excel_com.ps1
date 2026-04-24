$ErrorActionPreference = "Stop"

$excel = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $version = $excel.Version
    $build = $excel.Build
    [ordered]@{
        excel_com_available = $true
        version = $version
        build = $build
    } | ConvertTo-Json -Depth 2
} catch {
    [ordered]@{
        excel_com_available = $false
        error = $_.Exception.Message
    } | ConvertTo-Json -Depth 2
    exit 1
} finally {
    if ($null -ne $excel) {
        $excel.Quit() | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
