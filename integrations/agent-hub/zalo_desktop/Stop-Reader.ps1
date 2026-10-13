$ErrorActionPreference='Stop'
Set-Content -LiteralPath (Join-Path $PSScriptRoot 'state\stop.flag') -Value 'stop' -Encoding ASCII
Write-Output 'Stop requested. The reader will finish its current read and exit; Zalo remains open.'
