$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$state=Join-Path $root 'state\sender'
# Explicit stop and uncertain Inspector cleanup always win over automatic recovery.
if((Test-Path "$state\stop.flag") -or (Test-Path "$state\halt.flag")){exit 0}
$existing=Get-CimInstance Win32_Process -Filter "name='python.exe' OR name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*zalo_desktop.sender*' -and $_.CommandLine -like "*$root*" }
if($existing){exit 0}
$stamp=Join-Path $state 'watchdog-last-start.txt'
if(Test-Path $stamp){if(((Get-Date)-(Get-Item $stamp).LastWriteTime).TotalSeconds -lt 180){exit 0}}
(Get-Date).ToString('o') | Set-Content $stamp
# Preserve crash evidence before the launcher opens its log files again.
if(Test-Path "$state\stderr.log"){Copy-Item "$state\stderr.log" "$state\stderr.previous.log" -Force}
& (Join-Path $root 'Start-Sender.ps1')
