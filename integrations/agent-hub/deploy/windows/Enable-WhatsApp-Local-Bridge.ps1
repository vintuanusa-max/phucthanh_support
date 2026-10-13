$ErrorActionPreference='Stop'
$report=Join-Path $PSScriptRoot 'whatsapp-local-bridge-install.json'
$key='HKCU:\Software\Policies\Microsoft\Edge\WebView2\AdditionalBrowserArguments'
$name='WhatsApp.Root.exe'
$value='--remote-debugging-port=54329 --remote-debugging-address=127.0.0.1'
try {
 $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
 if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Administrator elevation required'}
 $old=Get-ItemProperty -LiteralPath $key -Name $name -ErrorAction SilentlyContinue
 if($old -and $old.$name -and $old.$name -ne $value){throw 'Existing WhatsApp browser arguments differ; preserve them'}
 New-Item -Path $key -Force | Out-Null
 New-ItemProperty -LiteralPath $key -Name $name -PropertyType String -Value $value -Force | Out-Null
 if((Get-ItemPropertyValue -LiteralPath $key -Name $name) -ne $value){throw 'Registry verification failed'}
 @{installed=$true;application=$name;listen='127.0.0.1:54329';restart_required=$true} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
} catch {
 @{installed=$false;error=$_.Exception.GetType().Name} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
 exit 1
}
