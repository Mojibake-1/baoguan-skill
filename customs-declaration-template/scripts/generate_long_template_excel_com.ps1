param(
    [Parameter(Mandatory = $true)]
    [string]$TemplatePath,

    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath([string]$PathValue) {
    $executionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PathValue)
}

function U([int[]]$Codes) {
    return -join ($Codes | ForEach-Object { [char]$_ })
}

function Get-Prop($Object, [string[]]$Names, $Default = $null) {
    foreach ($name in $Names) {
        if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $name) {
            $value = $Object.$name
            if ($null -ne $value -and (-not ($value -is [string]) -or $value -ne "")) {
                return $value
            }
        }
    }
    return $Default
}

function Get-NestedProp($Object, [string]$Path, $Default = $null) {
    $current = $Object
    foreach ($part in $Path.Split(".")) {
        if ($null -eq $current -or -not ($current.PSObject.Properties.Name -contains $part)) {
            return $Default
        }
        $current = $current.$part
    }
    if ($null -eq $current -or ($current -is [string] -and $current -eq "")) {
        return $Default
    }
    return $current
}

function Get-FirstNested($Object, [string[]]$Paths, $Default = $null) {
    foreach ($path in $Paths) {
        $value = Get-NestedProp $Object $path $null
        if ($null -ne $value -and $value -ne "") {
            return $value
        }
    }
    return $Default
}

function To-Date([object]$Value) {
    if ($Value -is [datetime]) {
        return $Value.Date
    }
    $text = [string]$Value
    foreach ($format in @("yyyy-MM-dd", "yyyy/M/d", "yyyy/M/dd", "yyyy/MM/d", "yyyy/MM/dd", "yyyyMMdd")) {
        try {
            return [datetime]::ParseExact($text, $format, [Globalization.CultureInfo]::InvariantCulture).Date
        } catch {
        }
    }
    return ([datetime]::Parse($text)).Date
}

function Get-ContractDate([datetime]$ShipDate) {
    $contractDate = $ShipDate.AddDays(-22)
    if ($contractDate.DayOfWeek -eq [DayOfWeek]::Saturday) {
        return $contractDate.AddDays(-1)
    }
    if ($contractDate.DayOfWeek -eq [DayOfWeek]::Sunday) {
        return $contractDate.AddDays(-2)
    }
    return $contractDate
}

function Get-CountryCode([string]$Country, [object]$Data) {
    $code = Get-FirstNested $Data @("trade.country_code", "country_code") $null
    if ($code) {
        return [string]$code
    }

    $ukCn = U @(0x82F1, 0x56FD)
    $usCn = U @(0x7F8E, 0x56FD)
    $caCn = U @(0x52A0, 0x62FF, 0x5927)

    if ($Country -match "UK|United Kingdom" -or $Country.Contains($ukCn)) {
        return "UK"
    }
    if ($Country -match "US|USA|United States" -or $Country.Contains($usCn)) {
        return "US"
    }
    if ($Country -match "CA|Canada" -or $Country.Contains($caCn)) {
        return "CA"
    }
    throw "Missing country code for destination country. Add trade.country_code or country_code to the JSON."
}

function Set-MergedValue($Worksheet, [string]$Address, [object]$Value) {
    $range = $Worksheet.Range($Address)
    $target = $range.MergeArea.Cells.Item(1, 1)
    if ($Value -is [datetime]) {
        $numberFormat = $target.NumberFormat
        $target.Value2 = $Value.ToOADate()
        $target.NumberFormat = $numberFormat
    } elseif ($Value -is [ValueType]) {
        $target.Value2 = [double]$Value
    } else {
        $target.Value = $Value
    }
}

function Delete-RowsIfNeeded($Worksheet, [int]$StartRow, [int]$EndRow) {
    if ($StartRow -le $EndRow) {
        $Worksheet.Rows("${StartRow}:${EndRow}").Delete() | Out-Null
    }
}

function Merge-InputCartonGroup($Worksheet, [int]$StartIndex, [int]$EndIndex, [object]$CartonValue) {
    if ($EndIndex -le $StartIndex) {
        return
    }

    $firstRow = 21 + ($StartIndex * 2)
    $lastRow = 21 + ($EndIndex * 2) + 1

    for ($index = $StartIndex; $index -le $EndIndex; $index++) {
        $row = 21 + ($index * 2)
        $range = $Worksheet.Range("G$row")
        if ($range.MergeCells) {
            $range.MergeArea.UnMerge() | Out-Null
        }
        $Worksheet.Range("G$row").ClearContents() | Out-Null
        $Worksheet.Range("G$($row + 1)").ClearContents() | Out-Null
    }

    $mergeRange = $Worksheet.Range("G${firstRow}:G${lastRow}")
    $mergeRange.Merge() | Out-Null
    $mergeRange.HorizontalAlignment = -4108
    $mergeRange.VerticalAlignment = -4108
    Set-MergedValue $Worksheet "G$firstRow" $CartonValue
}

function Merge-InputSharedCartonGroups($Worksheet, [object[]]$Items) {
    $runStart = $null
    $runGroupId = $null
    $runCartons = $null

    for ($index = 0; $index -le $Items.Count; $index++) {
        $item = if ($index -lt $Items.Count) { $Items[$index] } else { $null }
        $groupId = if ($null -ne $item) { Get-Prop $item @("carton_group_id", "cartonGroupId") $null } else { $null }

        if ($groupId -and $null -ne $runGroupId -and ([string]$groupId) -eq ([string]$runGroupId)) {
            continue
        }

        if ($null -ne $runGroupId) {
            $runEnd = $index - 1
            if ($runEnd -gt $runStart) {
                Merge-InputCartonGroup $Worksheet $runStart $runEnd $runCartons
            }
        }

        if ($groupId) {
            $runStart = $index
            $runGroupId = $groupId
            $runCartons = Get-Prop $item @("physical_cartons", "cartons", "packages") $null
        } else {
            $runStart = $null
            $runGroupId = $null
            $runCartons = $null
        }
    }
}

function Repair-FormulaIfRef($Worksheet, [string]$Address, [string]$Formula) {
    $cell = $Worksheet.Range($Address)
    $current = [string]$cell.Formula
    if ($current -match "#REF!") {
        $cell.Formula = $Formula
    }
}

$templateFullPath = Resolve-FullPath $TemplatePath
$dataFullPath = Resolve-FullPath $DataPath
$outputFullPath = Resolve-FullPath $OutputPath

if (-not (Test-Path -LiteralPath $templateFullPath)) {
    throw "Template not found: $templateFullPath"
}
if (-not (Test-Path -LiteralPath $dataFullPath)) {
    throw "Data JSON not found: $dataFullPath"
}
if ((Test-Path -LiteralPath $outputFullPath) -and -not $Force) {
    throw "Output already exists. Pass -Force to overwrite: $outputFullPath"
}

$outputParent = Split-Path -Parent $outputFullPath
if ($outputParent -and -not (Test-Path -LiteralPath $outputParent)) {
    New-Item -ItemType Directory -Path $outputParent | Out-Null
}

Copy-Item -LiteralPath $templateFullPath -Destination $outputFullPath -Force

$data = Get-Content -LiteralPath $dataFullPath -Raw -Encoding UTF8 | ConvertFrom-Json
$items = @($data.items)
if ($items.Count -lt 1) {
    throw "Data JSON must contain at least one item in items[]."
}
if ($items.Count -gt 30) {
    throw "The long template supports at most 30 item lines."
}

$country = Get-FirstNested $data @("country", "trade.destination_country", "trade.country") $null
if (-not $country) {
    throw "Destination country is required."
}
$shipDateRaw = Get-FirstNested $data @("ship_date", "shipment.actual_ship_date", "shipment.import_export_date", "declaration.declaration_date") $null
if (-not $shipDateRaw) {
    throw "Actual shipment/declaration date is required."
}

$shipDate = To-Date $shipDateRaw
$contractDate = Get-ContractDate $shipDate
$countryCode = Get-CountryCode ([string]$country) $data
$contractNo = "HS-{0}-{1}" -f $countryCode, $contractDate.ToString("yyyyMMdd")
$defaultUnit = U @(0x4E2A)

$excel = $null
$workbook = $null

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false

    $workbook = $excel.Workbooks.Open($outputFullPath)

    # Worksheet order in the long template:
    # 1 input, 2 customs declaration, 3 packing list, 4 invoice, 5 contract,
    # 6 warehouse authorization, 7 declaration elements, 8 customs authorization.
    $inputSheet = $workbook.Worksheets.Item(1)
    $customsSheet = $workbook.Worksheets.Item(2)
    $packingSheet = $workbook.Worksheets.Item(3)
    $invoiceSheet = $workbook.Worksheets.Item(4)
    $contractSheet = $workbook.Worksheets.Item(5)
    $elementsSheet = $workbook.Worksheets.Item(7)

    Set-MergedValue $inputSheet "G3" $shipDate
    Set-MergedValue $inputSheet "E11" ([string]$country)
    Set-MergedValue $inputSheet "K10" $contractDate
    Set-MergedValue $inputSheet "K9" $contractNo

    for ($index = 0; $index -lt $items.Count; $index++) {
        $item = $items[$index]
        $row = 21 + ($index * 2)
        $lineNo = Get-Prop $item @("line_no", "line") ($index + 1)
        $unit = Get-Prop $item @("unit") $defaultUnit
        $unitPrice = Get-Prop $item @("unit_price", "unit_price_v4", "price_v4", "price") $null
        if ($null -eq $unitPrice) {
            throw "Missing unit price for item line $lineNo."
        }

        Set-MergedValue $inputSheet "B$row" $lineNo
        Set-MergedValue $inputSheet "C$row" (Get-Prop $item @("hs_code") $null)
        Set-MergedValue $inputSheet "E$row" (Get-Prop $item @("declaration_name", "description_cn") $null)
        Set-MergedValue $inputSheet "E$($row + 1)" (Get-Prop $item @("declaration_elements", "description_spec", "elements") $null)
        Set-MergedValue $inputSheet "G$row" (Get-Prop $item @("cartons", "packages") $null)
        Set-MergedValue $inputSheet "H$row" (Get-Prop $item @("gross_weight_kg", "gross_weight", "gross") $null)
        Set-MergedValue $inputSheet "I$row" (Get-Prop $item @("net_weight_kg", "net_weight", "net") $null)
        Set-MergedValue $inputSheet "J$row" (Get-Prop $item @("quantity", "total") $null)
        Set-MergedValue $inputSheet "K$row" $unit
        Set-MergedValue $inputSheet "L$row" $unitPrice
    }

    $n = $items.Count

    Delete-RowsIfNeeded $inputSheet (21 + 2 * $n) 80
    Delete-RowsIfNeeded $customsSheet (20 + 3 * $n) 109
    Delete-RowsIfNeeded $packingSheet (15 + 2 * $n) 74
    Delete-RowsIfNeeded $invoiceSheet (15 + $n) 44
    Delete-RowsIfNeeded $contractSheet (19 + $n) 48
    Delete-RowsIfNeeded $elementsSheet (6 + $n) 35

    Merge-InputSharedCartonGroups $inputSheet $items

    $inputName = $inputSheet.Name
    Repair-FormulaIfRef $customsSheet "H39" "=$inputName!J34"
    Repair-FormulaIfRef $customsSheet "J39" "=$inputName!K34"
    Repair-FormulaIfRef $customsSheet "H42" "=$inputName!J36"
    Repair-FormulaIfRef $customsSheet "J42" "=$inputName!K36"

    $excel.CalculateFullRebuild()
    $workbook.Save()
} finally {
    if ($null -ne $workbook) {
        $workbook.Close($true) | Out-Null
    }
    if ($null -ne $excel) {
        $excel.Quit() | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

Write-Output $outputFullPath
