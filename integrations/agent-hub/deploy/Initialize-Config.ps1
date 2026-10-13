param([string]$ExistingBotConfig = '')
$ErrorActionPreference = 'Stop'
$target = Join-Path $PSScriptRoot '.env'
if (Test-Path -LiteralPath $target) { throw '.env exists; edit it instead of replacing secrets.' }
function New-Secret {
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    return [Convert]::ToBase64String($bytes)
}
$content = Get-Content -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Raw
foreach ($name in @('POSTGRES_PASSWORD','REDIS_PASSWORD','SECRET_KEY_BASE','HUB_ADMIN_TOKEN','HUB_INGEST_TOKEN','CW_WEBHOOK_SECRET')) {
    $content = $content.Replace("$name=", "$name=$(New-Secret)")
}
if ($ExistingBotConfig) {
    $bot = Get-Content -LiteralPath $ExistingBotConfig -Raw | ConvertFrom-Json
    if (-not $bot.gemini_api_key) { throw 'Existing bot config has no Gemini key.' }
    $content = $content.Replace('GEMINI_API_KEY=', "GEMINI_API_KEY=$($bot.gemini_api_key)")
}
[IO.File]::WriteAllText($target, $content, (New-Object Text.UTF8Encoding($false)))
Write-Output 'Created .env with generated secrets. Secret values were not printed.'
