param(
    [ValidateSet('audit-latest', 'live-replay')]
    [string]$Mode = 'audit-latest',
    [string]$Cases = '',
    [switch]$All,
    [int]$Timeout = 420
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$reportsDir = Join-Path $scriptDir 'reports'
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$localReport = Join-Path $reportsDir "report-$Mode-$stamp.json"
$containerDir = '/tmp/golden_regression'
$containerReport = "$containerDir/report.json"

if ($Mode -eq 'live-replay' -and -not $All -and [string]::IsNullOrWhiteSpace($Cases)) {
    Write-Error 'With -Mode live-replay, specify either -Cases "SLOWING1_DUAL,SLOWING2_JPG" or -All.'
    exit 2
}

$exitCode = 1
try {
    docker exec phucthanh-chatwoot-hub-1 mkdir -p $containerDir | Out-Null
    docker cp (Join-Path $scriptDir 'run_golden_regression.py') "phucthanh-chatwoot-hub-1:$containerDir/run_golden_regression.py" | Out-Null
    docker cp (Join-Path $scriptDir 'golden_cases.json') "phucthanh-chatwoot-hub-1:$containerDir/golden_cases.json" | Out-Null
    docker exec -u 0 phucthanh-chatwoot-hub-1 chown -R hub:hub $containerDir | Out-Null

    $cmdArgs = @(
        '/app/.venv/bin/python', "$containerDir/run_golden_regression.py",
        '--mode', $Mode,
        '--cases-file', "$containerDir/golden_cases.json",
        '--timeout', "$Timeout",
        '--report-out', $containerReport
    )
    if (-not [string]::IsNullOrWhiteSpace($Cases)) {
        $cmdArgs += @('--cases', $Cases)
    }

    & docker exec phucthanh-chatwoot-hub-1 @cmdArgs
    $exitCode = $LASTEXITCODE

    docker cp "phucthanh-chatwoot-hub-1:$containerReport" $localReport 2>$null
    if (Test-Path $localReport) {
        Write-Host "Report saved: $localReport"
    }
}
finally {
    docker exec -u 0 phucthanh-chatwoot-hub-1 rm -rf $containerDir 2>$null | Out-Null
}

exit $exitCode
