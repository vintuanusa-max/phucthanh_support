$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$exe = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$script = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bootstrap.rb') -Raw
$result = $script | & $exe compose exec -T rails bundle exec rails runner -
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap failed; review Docker logs.' }
$line = $result | Where-Object { $_ -like 'PHUCTHANH_BOOTSTRAP=*' } | Select-Object -Last 1
if (-not $line) { throw 'Bootstrap returned no result.' }
$config = $line.Substring('PHUCTHANH_BOOTSTRAP='.Length) | ConvertFrom-Json
$envPath = Join-Path $PSScriptRoot '.env'
$contents = Get-Content -LiteralPath $envPath
# Preserve the independently enabled capture flag; bootstrap never enables channel delivery.
$inboxLine = $contents | Where-Object { $_ -like 'HUB_INBOXES=*' } | Select-Object -First 1
if ($inboxLine) {
    $previousInboxes = $inboxLine.Substring('HUB_INBOXES='.Length) | ConvertFrom-Json
    foreach ($entry in $config.inboxes.PSObject.Properties) {
        $old = $previousInboxes.PSObject.Properties[$entry.Name]
        if ($old -and $old.Value.capture_enabled -eq $true) {
            $entry.Value | Add-Member -NotePropertyName capture_enabled -NotePropertyValue $true -Force
        }
    }
}
$updates = @{
    CW_ACCOUNT = [string]$config.account
    CW_BOT_ID = [string]$config.bot_id
    CW_TOKEN = [string]$config.token
    HUB_INBOXES = ($config.inboxes | ConvertTo-Json -Compress -Depth 5)
}
$contents = foreach ($line in $contents) {
    $key = ($line -split '=',2)[0]
    if ($updates.ContainsKey($key)) { "$key=$($updates[$key])" } else { $line }
}
[IO.File]::WriteAllLines($envPath, $contents, (New-Object Text.UTF8Encoding($false)))
if ($config.admin_password) {
    @{email=$config.admin_email; password=$config.admin_password} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'admin-login.local.json') -Encoding utf8
}
& $exe compose up -d --force-recreate hub
if ($LASTEXITCODE -ne 0) { throw 'Hub restart failed.' }
Write-Output 'Created inboxes and Gemini Agent Bot. Login details saved locally. Mode remains review.'
