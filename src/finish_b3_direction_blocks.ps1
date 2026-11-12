$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$result = Join-Path $root 'results\blocksnet-b3-directions-citywide-20261112'
$summary = Join-Path $result 'summary.json'
$python = 'C:\Users\olesy\AppData\Local\Programs\Python\Python311\python.exe'

while (-not (Test-Path -LiteralPath $summary)) {
    Start-Sleep -Seconds 20
}

Set-Location $root
& $python 'src\aggregate_b3_age_profiles_blocks.py' `
    '--input' 'results\blocksnet-b3-directions-citywide-20261112' `
    '--out' 'results\age-profiles-blocks-b3-20261112'
