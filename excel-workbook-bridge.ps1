$ErrorActionPreference = 'Stop'
$workbookPath = 'C:\Users\skybl\Downloads\2026년 10월 수변전 일지 - 본관.xlsx'
$backupPath = 'C:\Users\skybl\Downloads\2026년 10월 수변전 일지 - 본관.before-html-entry.xlsx'
$listenPrefix = 'http://127.0.0.1:8766/'

function Send-Json($response, [int]$status, $body) {
  $json = ConvertTo-Json -InputObject $body -Depth 8 -Compress
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
  $response.StatusCode = $status
  $response.ContentType = 'application/json; charset=utf-8'
  $response.Headers['Access-Control-Allow-Origin'] = '*'
  $response.Headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
  $response.Headers['Access-Control-Allow-Headers'] = 'Content-Type'
  $response.ContentLength64 = $bytes.Length
  $response.OutputStream.Write($bytes, 0, $bytes.Length)
  $response.Close()
}

function Set-ExcelValue($worksheet, [string]$address, $value) {
  $cell = $worksheet.Range($address)
  if ($null -eq $value -or [string]::IsNullOrWhiteSpace([string]$value)) {
    $cell.ClearContents()
  } else {
    $number = 0.0
    if ([double]::TryParse([string]$value, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$number)) {
      $cell.Value2 = $number
    } else {
      $cell.Value2 = [string]$value
    }
  }
}

function Get-Field($record, [string]$time, [string]$group, [string]$field) {
  $row = $record.observations.$time
  if ($null -eq $row) { return $null }
  $groupData = $row.$group
  if ($null -eq $groupData) { return $null }
  return $groupData.$field
}

function Save-Record($payload) {
  if (-not (Test-Path -LiteralPath $workbookPath -PathType Leaf)) { throw "원본 엑셀 파일을 찾을 수 없습니다: $workbookPath" }
  $date = [string]$payload.date
  if ($date -notmatch '^2026-10-(0[1-9]|[12][0-9]|3[01])$') { throw '저장할 날짜는 2026년 10월이어야 합니다.' }
  $day = [int]$date.Substring(8, 2)
  $sheetName = '{0:D2}일' -f $day
  $record = $payload.record
  if ($null -eq $record -or $null -eq $record.observations) { throw '입력 기록 데이터가 올바르지 않습니다.' }

  $excel = $null; $books = $null; $book = $null; $sheets = $null; $daily = $null; $summary = $null; $saved = $false
  try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $books = $excel.Workbooks
    $book = $books.Open($workbookPath, 0, $false)
    $sheets = $book.Worksheets
    $daily = $sheets.Item($sheetName)
    $summary = $sheets.Item(1)

    if (-not (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
      Copy-Item -LiteralPath $workbookPath -Destination $backupPath
    }

    $slotRows = @(10, 11, 12, 13, 14)
    $times = @('08:00', '11:00', '14:00', '16:00', '23:59')
    $mainColumns = @{ kv='F'; a1='I'; a2='L'; a3='O'; pf='R'; kw='U'; hz='Y'; tr1='AB'; tr2='AE' }
    $vcbColumns = @{ kv='AH'; kw='AK'; pf='AN'; a='AQ'; upsKw='AT'; upsA='AX'; emergencyKw='BB'; emergencyA='BF'; hvacKw='BJ'; hvacA='BN'; generalKw='BR'; generalA='BV'; lightingKw='BZ'; lightingA='CD' }
    $auxColumns = @{ lighting='AQ'; general='AV'; hvac='BA'; emergency='BF'; ups='BK' }
    $chillerColumns = @{ chillerKw='R'; chillerA='V'; chiller2Kw='Z'; chiller2A='AD' }
    $secondaryColumns = @{ lowLightingV='AP'; lowLightingKw='AT'; lowLightingA='AX'; lowGeneralV='R'; lowGeneralKw='V'; lowGeneralA='Z'; lowEmergencyV='AD'; lowEmergencyKw='AH'; lowEmergencyA='AL' }
    $rectifierColumns = @{ rectifierV='BP'; rectifierA='BT'; batteryV='BY'; batteryA='CC' }

    for ($i = 0; $i -lt $times.Length; $i++) {
      $time = $times[$i]; $row = $slotRows[$i]
      foreach ($key in $mainColumns.Keys) { Set-ExcelValue $daily ($mainColumns[$key] + $row) (Get-Field $record $time 'main' $key) }
      foreach ($key in $vcbColumns.Keys) { Set-ExcelValue $daily ($vcbColumns[$key] + $row) (Get-Field $record $time 'vcb' $key) }
      foreach ($key in $auxColumns.Keys) { Set-ExcelValue $daily ($auxColumns[$key] + ($row + 10)) (Get-Field $record $time 'transformer' $key) }
      foreach ($key in $chillerColumns.Keys) { Set-ExcelValue $daily ($chillerColumns[$key] + ($row + 10)) (Get-Field $record $time 'chiller' $key) }
      foreach ($key in $secondaryColumns.Keys) { Set-ExcelValue $daily ($secondaryColumns[$key] + ($row + 10)) (Get-Field $record $time 'secondary' $key) }
      foreach ($key in $rectifierColumns.Keys) { Set-ExcelValue $daily ($rectifierColumns[$key] + ($row + 10)) (Get-Field $record $time 'secondary' $key) }
    }

    $meterColumns = @('N', 'W', 'AF', 'AO', 'AX')
    for ($i = 0; $i -lt $meterColumns.Length; $i++) {
      Set-ExcelValue $daily ($meterColumns[$i] + '38') $record.meters.current[$i]
      Set-ExcelValue $daily ($meterColumns[$i] + '39') $record.meters.previous[$i]
    }

    foreach ($kind in @('substation', 'industrial')) {
      $monthly = $record.meters.monthlyClose.$kind
      $labelRows = if ($kind -eq 'substation') { @(28, 29, 30, 31, 32, 33, 34) } else { @(28, 29, 30, 31, 32, 33, 34) }
      $labelColumn = if ($kind -eq 'substation') { 'BD' } else { 'BS' }
      $valueColumns = if ($kind -eq 'substation') { @('BF', 'BK', 'BM') } else { @('BU', 'BZ', 'CB') }
      for ($i = 0; $i -lt $labelRows.Length; $i++) {
        $row = $labelRows[$i]
        Set-ExcelValue $daily ($valueColumns[0] + $row) $monthly.current[$i]
        Set-ExcelValue $daily ($valueColumns[1] + $row) $monthly.previous[$i]
        $daily.Range($valueColumns[2] + $row).Formula = "=$($valueColumns[0])$row-$($valueColumns[1])$row"
      }
    }

    Set-ExcelValue $summary ('J' + ($day + 1)) $record.operator
    Set-ExcelValue $daily 'C44' $record.notes
    $book.Save()
    $saved = $true

    $warnings = [System.Collections.Generic.List[string]]::new()
    if ($record.meters.current[5] -or $record.meters.previous[5] -or $record.meters.current[6] -or $record.meters.previous[6]) { $warnings.Add('원본 엑셀에 일일 계량기 9·10 입력 셀이 없어 저장하지 않았습니다.') }
    foreach ($time in $times) {
      if ((Get-Field $record $time 'chiller' 'capacitorKw') -or (Get-Field $record $time 'chiller' 'capacitorA')) { $warnings.Add('원본 엑셀에 냉동기 콘덴서 입력 셀이 없어 저장하지 않았습니다.'); break }
      if (Get-Field $record $time 'transformer' 'trTemp') { $warnings.Add('원본 엑셀에서 변압기 TR온도 입력 셀과 전등/전열 표기가 같은 열을 사용하므로 TR온도 값은 저장하지 않았습니다.'); break }
    }
    return @{ ok = $true; sheet = $sheetName; savedPath = $workbookPath; backupPath = $backupPath; warnings = @($warnings) }
  } finally {
    if ($book -ne $null) { $book.Close($saved) }
    if ($excel -ne $null) { $excel.Quit() }
    foreach ($comObject in @($daily, $summary, $sheets, $book, $books, $excel)) {
      if ($comObject -ne $null) { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($comObject) }
    }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
  }
}

$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add($listenPrefix)
$listener.Start()
Write-Output "Excel 입력 도우미 실행 중: $listenPrefix"
while ($listener.IsListening) {
  $context = $listener.GetContext()
  $request = $context.Request
  $response = $context.Response
  if ($request.HttpMethod -eq 'OPTIONS') {
    $response.StatusCode = 204
    $response.Headers['Access-Control-Allow-Origin'] = '*'
    $response.Headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    $response.Headers['Access-Control-Allow-Headers'] = 'Content-Type'
    $response.Close()
    continue
  }
  if ($request.HttpMethod -eq 'GET' -and $request.Url.AbsolutePath -eq '/health') {
    Send-Json $response 200 @{ ok = $true; workbook = $workbookPath }
    continue
  }
  if ($request.HttpMethod -ne 'POST' -or $request.Url.AbsolutePath -ne '/save') {
    Send-Json $response 404 @{ ok = $false; error = '요청 경로를 찾을 수 없습니다.' }
    continue
  }
  try {
    $reader = [System.IO.StreamReader]::new($request.InputStream, $request.ContentEncoding)
    $payload = $reader.ReadToEnd() | ConvertFrom-Json
    $result = Save-Record $payload
    Send-Json $response 200 $result
  } catch {
    Send-Json $response 500 @{ ok = $false; error = $_.Exception.Message }
  }
}
