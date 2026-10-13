$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$existing=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*whatsapp_desktop.reader*' }
if($existing){Write-Output 'WhatsApp reader already running';exit 0}
$stop=Join-Path $root 'state/stop.flag'
if(Test-Path -LiteralPath $stop){Remove-Item -LiteralPath $stop}
$env:PYTHONPATH=Join-Path $root 'code'
Start-Process -FilePath (Join-Path $root 'code/.venv/Scripts/python.exe') -ArgumentList @('-m','whatsapp_desktop.reader','--config',('"'+(Join-Path $root 'reader.local.json')+'"')) -WorkingDirectory (Join-Path $root 'code') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'stdout.log') -RedirectStandardError (Join-Path $root 'stderr.log')
Write-Output 'WhatsApp reader started'
