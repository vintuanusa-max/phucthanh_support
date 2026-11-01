param([string]$RequestPath,[string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName Accessibility
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies Accessibility,System.Drawing -Path (Join-Path $PSScriptRoot 'ZaloQuoteCapture.cs')
$r=Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
[ZaloQuoteCapture]::Capture($r.group,$r.body,$r.sender,$r.quote_sender,$r.clock,$r.date,[IO.Path]::GetFullPath($OutputPath))
