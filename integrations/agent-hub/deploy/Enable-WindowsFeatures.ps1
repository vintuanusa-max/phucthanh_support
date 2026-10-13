$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'windows-features-result.txt'
try {
  Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart | Out-File -LiteralPath $log
  Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -All -NoRestart | Out-File -LiteralPath $log -Append
  'Completed. No restart was performed.' | Out-File -LiteralPath $log -Append
} catch {
  $_.Exception.Message | Out-File -LiteralPath $log -Append
  exit 1
}
