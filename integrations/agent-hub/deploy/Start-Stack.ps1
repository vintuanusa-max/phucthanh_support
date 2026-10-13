$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.env')) { & .\Initialize-Config.ps1 }
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $candidate = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
    if (Test-Path -LiteralPath $candidate) { $docker = Get-Item -LiteralPath $candidate }
    else { throw 'Docker Desktop is not installed.' }
}
$exe = if ($docker.Source) { $docker.Source } else { $docker.FullName }
& $exe info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop in Linux containers mode first.' }
& $exe compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration invalid.' }
& $exe compose up -d postgres redis
if ($LASTEXITCODE -ne 0) { throw 'Database services failed.' }
& $exe compose run --rm rails bundle exec rails db:chatwoot_prepare
if ($LASTEXITCODE -ne 0) { throw 'Database preparation failed.' }
& $exe compose up -d --build rails sidekiq hub
if ($LASTEXITCODE -ne 0) { throw 'Services failed to start.' }
Write-Output 'Chatwoot: http://localhost:3000 ; Agent Hub: http://localhost:8095'
