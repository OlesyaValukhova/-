param(
    [string]$Python = 'C:\Users\olesy\PycharmProjects\JupyterProject2\.venv\Scripts\python.exe',
    [int]$InterfaceIndex = 14,
    [switch]$ProbeDetails,
    [switch]$City,
    [string]$ResumePages = '',
    [switch]$CollectDetails,
    [string]$DetailsCatalogue = '',
    [string]$DetailsDirectory = ''
)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
if ($DetailsCatalogue) {
    if ($City -or $ProbeDetails -or $ResumePages) { throw 'DetailsCatalogue cannot be combined with catalogue collection options.' }
    $DetailsCatalogue = (Resolve-Path -LiteralPath $DetailsCatalogue).Path
}
$run = Join-Path $project ('data\navigator\direct-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $run | Out-Null
$created = @()
if ($City -and $ProbeDetails) { throw 'City and the legacy diagnostic probe are mutually exclusive.' }
Start-Transcript -Path (Join-Path $run 'routing.log') | Out-Null
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator rights required to create a temporary host route.'
    }
    $gateway = (Get-NetIPConfiguration -InterfaceIndex $InterfaceIndex).IPv4DefaultGateway.NextHop
    if (-not $gateway) { throw 'Selected interface has no IPv4 gateway.' }
    $addresses = @(Resolve-DnsName 'dopobr.petersburgedu.ru' -Type A |
        Where-Object Type -eq 'A' | Select-Object -ExpandProperty IPAddress -Unique)
    if (-not $addresses.Count) { throw 'No website IPv4 address found.' }
    foreach ($address in $addresses) {
        $prefix = "$address/32"
        $existing = @(Get-NetRoute -DestinationPrefix $prefix -ErrorAction SilentlyContinue)
        if ($existing.Count) { throw "Existing host route for $prefix; refusing to change it." }
        New-NetRoute -DestinationPrefix $prefix -InterfaceIndex $InterfaceIndex -NextHop $gateway `
            -RouteMetric 1 -PolicyStore ActiveStore | Out-Null
        $created += $prefix
        $selected = Find-NetRoute -RemoteIPAddress $address
        $route = $selected | Where-Object { $_.PSObject.Properties.Name -contains 'DestinationPrefix' }
        if (-not ($route | Where-Object InterfaceIndex -eq $InterfaceIndex)) {
            throw "Wi-Fi route was not selected for $address."
        }
        Write-Output "DIRECT ROUTE: $address via $gateway interface $InterfaceIndex"
    }
    # Windows PowerShell 5 treats redirected native stderr as ErrorRecord.
    # Keep its full traceback in the log; use native exit codes for success.
    $ErrorActionPreference = 'Continue'
    $saved = Join-Path $project 'data\navigator\retry-20261020-144028\pages.json'
    if ($ResumePages) { $saved = (Resolve-Path -LiteralPath $ResumePages).Path }
    $output = Join-Path $run 'catalogue'
    if ($DetailsCatalogue) {
        $detailsOutput = if ($DetailsDirectory) { $DetailsDirectory } else { Join-Path $run 'program-details' }
        & $Python -u (Join-Path $PSScriptRoot 'collect_program_details.py') `
            --catalogue $DetailsCatalogue --output $detailsOutput --timeout 20 --delay 1 --failure-stop 3 2>&1 |
            Tee-Object -FilePath (Join-Path $run 'details.log')
    } elseif ($ProbeDetails) {
        & $Python -u (Join-Path $PSScriptRoot 'probe_navigator_details.py') --output $output 2>&1 |
            Tee-Object -FilePath (Join-Path $run 'collector.log')
    } elseif ($City) {
        $collectorArgs = @('-u', (Join-Path $PSScriptRoot 'parse_navigator.py'), '--direct-http',
            '--url', 'https://dopobr.petersburgedu.ru/api/program/list_odo/?limit=100&offset=0&ordering=rating_avg_desc&page=1',
            '--output', $output, '--max-pages', '1000', '--delay', '1', '--timeout', '20', '--retries', '1')
        if ($ResumePages) { $collectorArgs += @('--resume', $saved) }
        & $Python @collectorArgs 2>&1 | Tee-Object -FilePath (Join-Path $run 'collector.log')
        $catalogueExit = $LASTEXITCODE
        if ($CollectDetails -and $catalogueExit -eq 0) {
            & $Python -u (Join-Path $PSScriptRoot 'collect_program_details.py') `
                --catalogue (Join-Path $output 'pages.json') --output (Join-Path $run 'program-details') `
                --timeout 20 --delay 1 --failure-stop 3 2>&1 |
                Tee-Object -FilePath (Join-Path $run 'details.log')
        }
    } else {
        & $Python -u (Join-Path $PSScriptRoot 'parse_navigator.py') --direct-http --resume $saved `
            --output $output --delay 2 --timeout 15 --retries 2 2>&1 |
            Tee-Object -FilePath (Join-Path $run 'collector.log')
    }
    Write-Output "Collector exit code: $LASTEXITCODE"
} catch {
    $_ | Out-String | Write-Output
} finally {
    $ErrorActionPreference = 'Stop'
    foreach ($prefix in $created) {
        Remove-NetRoute -DestinationPrefix $prefix -InterfaceIndex $InterfaceIndex -NextHop $gateway `
            -PolicyStore ActiveStore -Confirm:$false
        Write-Output "REMOVED TEMPORARY ROUTE: $prefix"
    }
    Stop-Transcript | Out-Null
}
