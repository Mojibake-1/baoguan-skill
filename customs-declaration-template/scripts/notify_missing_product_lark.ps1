param(
    [Parameter(Mandatory = $true)]
    [string]$Product,

    [string]$Sku,

    [string]$Model,

    [string]$SourceWorkbook,

    [string]$Reason = "源数据表「报关名」未找到本次报关产品，请补充后再生成报关单。",

    [string]$MissingFields,

    [string]$RecipientQuery = "JOJO",

    [string]$Identity = "user",

    [string]$CliPath = "lark-cli",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-LarkCli([string[]]$Arguments) {
    $command = Get-Command $CliPath -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        $fallback = "C:\Users\admin\AppData\Roaming\npm\node_modules\@larksuite\cli\bin\lark-cli.exe"
        if (Test-Path -LiteralPath $fallback -PathType Leaf) {
            $commandPath = $fallback
        } else {
            throw "lark-cli not found in PATH and fallback path is missing: $fallback"
        }
    } else {
        $commandPath = $command.Source
    }
    $output = & $commandPath @Arguments
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if ($exitCode -ne 0) {
        throw $text
    }
    return $text
}

function ConvertFrom-JsonText([string]$Text, [string]$Context) {
    try {
        return $Text | ConvertFrom-Json
    } catch {
        throw "Failed to parse lark-cli JSON from $Context. Raw output: $Text"
    }
}

$searchText = Invoke-LarkCli @("contact", "+search-user", "--query", $RecipientQuery, "--format", "json")
$search = ConvertFrom-JsonText $searchText "contact search"
if (-not $search.ok) {
    throw "Lark contact search failed: $($search.error.message)"
}

$users = @($search.data.users)
if ($users.Count -lt 1) {
    throw "No Lark user found for query: $RecipientQuery"
}

$recipient = $users | Where-Object { $_.name -eq $RecipientQuery } | Select-Object -First 1
if ($null -eq $recipient) {
    $recipient = $users | Select-Object -First 1
}

$lines = @(
    "【报关单数据源缺失提醒】",
    $Reason,
    "产品：$Product"
)
if ($Sku) {
    $lines += "SKU：$Sku"
}
if ($Model) {
    $lines += "型号：$Model"
}
if ($SourceWorkbook) {
    $lines += "源表：$SourceWorkbook"
}
if ($MissingFields) {
    $lines += "缺失字段：$MissingFields"
}
$lines += "处理建议：请在 amz 备货计划「报关名」补齐 HS 编码、报关商品名称、报关规格型号、申报用途、申报单价V4、pc/ctn、单箱毛重、单箱净重。"
$message = $lines -join "`n"

$sendArgs = @(
    "im",
    "+messages-send",
    "--as",
    $Identity,
    "--user-id",
    $recipient.open_id,
    "--text",
    $message,
    "--idempotency-key",
    ("customs-" + ([guid]::NewGuid().ToString("N")))
)
if ($DryRun) {
    $sendArgs += "--dry-run"
}

try {
    $sendText = Invoke-LarkCli $sendArgs
    $sendResult = ConvertFrom-JsonText $sendText "message send"
    if ($DryRun) {
        [ordered]@{
            ok = $true
            dry_run = $true
            recipient_name = $recipient.name
            recipient_open_id = $recipient.open_id
            message = $message
            lark_result = $sendResult
        } | ConvertTo-Json -Depth 8
        exit 0
    }
    if (-not $sendResult.ok) {
        throw "Lark message send failed: $($sendResult.error.message)"
    }
    [ordered]@{
        ok = $true
        dry_run = $false
        recipient_name = $recipient.name
        recipient_open_id = $recipient.open_id
        message_id = $sendResult.data.message_id
    } | ConvertTo-Json -Depth 8
} catch {
    $errorText = $_.Exception.Message
    throw "Lark message was not sent: $errorText"
}
