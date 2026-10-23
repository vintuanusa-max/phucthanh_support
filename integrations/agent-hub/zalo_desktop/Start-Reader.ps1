param([switch]$Automatic)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$mutex=New-Object System.Threading.Mutex($false,'Local\PhucThanhZaloReaderStart')
if(-not $mutex.WaitOne(0)){exit 0}
try {
 $stopPath=Join-Path $root 'state\stop.flag'
 if($Automatic -and (Test-Path -LiteralPath $stopPath)){exit 0}
 $existing=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*zalo_desktop.reader*' -and $_.CommandLine -like "*$root*" }
 if($existing){exit 0}
 if(Test-Path -LiteralPath $stopPath){Remove-Item -LiteralPath $stopPath}
 $python=Join-Path $root 'code\.venv\Scripts\python.exe'
 $config=Join-Path $root 'reader.local.json'
 Start-Process -FilePath $python -ArgumentList @('-m','zalo_desktop.reader','--config',('"'+$config+'"')) -WorkingDirectory (Join-Path $root 'code') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'state\stdout.log') -RedirectStandardError (Join-Path $root 'state\stderr.log')
} finally {$mutex.ReleaseMutex();$mutex.Dispose()}
