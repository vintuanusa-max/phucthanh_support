$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$python='C:\Users\Admin\AppData\Local\PhucThanh\ZaloDesktopReader\code\.venv\Scripts\python.exe'
$argsList=@(('"'+(Join-Path $root 'worker.py')+'"'),'--state',('"'+(Join-Path $root 'state.json')+'"'))
foreach($configPath in (Get-Content (Join-Path $root 'config-paths.json') -Raw | ConvertFrom-Json)){
    $argsList+=@('--config',('"'+$configPath+'"'))
}
Start-Process -FilePath $python -ArgumentList $argsList -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'stdout.log') -RedirectStandardError (Join-Path $root 'stderr.log')
