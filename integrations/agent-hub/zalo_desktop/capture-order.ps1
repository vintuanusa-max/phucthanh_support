param([string]$RequestPath,[string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName Accessibility,System.Drawing
Add-Type -ReferencedAssemblies Accessibility,System.Drawing -Path (Join-Path $PSScriptRoot 'ZaloOrderCapture.cs')
$r=Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
[ZaloOrderCapture]::Capture($r.group,$r.body,$r.sender,'',$r.clock,$r.date,[IO.Path]::GetFullPath($OutputPath))
