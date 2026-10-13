$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$existing=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*zalo_desktop.reader*' -and $_.CommandLine -like "*$root*" }
if($existing){ Write-Output 'Zalo reader already running.'; exit 0 }
$stopPath=Join-Path $root 'state\stop.flag'
if(Test-Path -LiteralPath $stopPath){Remove-Item -LiteralPath $stopPath}
$python=Join-Path $root 'code\.venv\Scripts\python.exe'
$config=Join-Path $root 'reader.local.json'
Start-Process -FilePath $python -ArgumentList @('-m','zalo_desktop.reader','--config',('"'+$config+'"')) -WorkingDirectory (Join-Path $root 'code') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'state\stdout.log') -RedirectStandardError (Join-Path $root 'state\stderr.log')
Write-Output 'Zalo reader started. See state\status.json.'
