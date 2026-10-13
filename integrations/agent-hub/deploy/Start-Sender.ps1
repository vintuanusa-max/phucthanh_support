$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$existing=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*zalo_desktop.sender*' -and $_.CommandLine -like "*$root*" }
if($existing){ Write-Output 'Zalo sender already running.'; exit 0 }
$state=Join-Path $root 'state\sender'
New-Item -ItemType Directory -Path $state -Force | Out-Null
if(Test-Path -LiteralPath (Join-Path $state 'halt.flag')){ throw 'Sender halted. Verify Inspector cleanup and uncertain sends before clearing halt.flag.' }
$stopPath=Join-Path $state 'stop.flag'
if(Test-Path -LiteralPath $stopPath){Remove-Item -LiteralPath $stopPath}
$python=Join-Path $root 'code\.venv\Scripts\python.exe'
$config=Join-Path $root 'reader.local.json'
Start-Process -FilePath $python -ArgumentList @('-m','zalo_desktop.sender','--config',('"'+$config+'"')) -WorkingDirectory (Join-Path $root 'code') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $state 'stdout.log') -RedirectStandardError (Join-Path $state 'stderr.log')
Write-Output 'Zalo staff sender started. See state\sender\status.json.'
