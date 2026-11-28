$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$all=@(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'")
$worker=Join-Path $env:LOCALAPPDATA 'PhucThanh\ArtworkInspector\worker.py'
if(-not ($all | Where-Object {$_.CommandLine -and $_.CommandLine.Contains($worker)})){
 & (Join-Path $env:LOCALAPPDATA 'PhucThanh\ArtworkInspector\Start.ps1')
}
$fastWorker=Join-Path $env:LOCALAPPDATA 'PhucThanh\ArtworkInspector\fast_worker.py'
if((Test-Path $fastWorker) -and -not ($all | Where-Object {$_.CommandLine -and $_.CommandLine.Contains($fastWorker)})){
 $python=Join-Path $env:LOCALAPPDATA 'PhucThanh\ZaloDesktopReader\code\.venv\Scripts\python.exe'
 $cfgListPath=Join-Path $env:LOCALAPPDATA 'PhucThanh\ArtworkInspector\config-paths.json'
 if((Test-Path $python) -and (Test-Path $cfgListPath)){
  $fastArgs=@('"'+$fastWorker+'"')
  foreach($cfgPath in (Get-Content $cfgListPath -Raw | ConvertFrom-Json)){
   if(Test-Path $cfgPath){ $fastArgs+=@('--config',('"'+$cfgPath+'"')) }
  }
  Start-Process -FilePath $python -ArgumentList $fastArgs -WorkingDirectory (Split-Path $fastWorker) -WindowStyle Hidden
 }
}
$server=Join-Path $root 'server.py'
if(-not ($all | Where-Object {$_.CommandLine -and $_.CommandLine.Contains($server)})){
 $python=Join-Path $env:LOCALAPPDATA 'PhucThanh\ZaloDesktopReader\code\.venv\Scripts\python.exe'
 Start-Process -FilePath $python -ArgumentList @('"'+$server+'"') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'stdout.log') -RedirectStandardError (Join-Path $root 'stderr.log')
}
