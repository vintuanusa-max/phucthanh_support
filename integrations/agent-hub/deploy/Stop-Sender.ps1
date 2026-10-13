$ErrorActionPreference='Stop'
$state=Join-Path $PSScriptRoot 'state\sender'
New-Item -ItemType Directory -Path $state -Force | Out-Null
Set-Content -LiteralPath (Join-Path $state 'stop.flag') -Value 'stop after current operation' -Encoding ascii
Write-Output 'Stop requested. An in-flight send is not recalled; no automatic retry.'
