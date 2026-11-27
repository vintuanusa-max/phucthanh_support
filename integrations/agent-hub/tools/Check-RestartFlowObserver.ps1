param(
    [switch]$RestartObserver
)

$ErrorActionPreference = 'Stop'
$viewCfgPath = 'C:\Users\Admin\Documents\Codex\2026-10-12\hi-n-m-y-t-nh\work\erp-flow-view\view.private.json'
$pyExe = 'C:\Users\Admin\AppData\Local\PhucThanh\ZaloDesktopReader\code\.venv\Scripts\python.exe'
$failed = $false

Write-Host '=== KIEM TRA HUB & DICH VU XEM LUONG (FLOW OBSERVER) ==='

# 1. Check Hub container & port 8095
$hubStatus = docker inspect phucthanh-chatwoot-hub-1 --format '{{.State.Status}}' 2>$null
if ($LASTEXITCODE -ne 0 -or $hubStatus -ne 'running') {
    Write-Host "[LOI] phucthanh-chatwoot-hub-1 chua chay ($hubStatus)."
    $failed = $true
} else {
    $hubHealth = docker exec phucthanh-chatwoot-hub-1 /app/.venv/bin/python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8095/health', timeout=5).status)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $hubHealth -match '200') {
        Write-Host '[OK]  Hub phucthanh-chatwoot-hub-1: running (HTTP 200 /health)'
    } else {
        Write-Host '[LOI] Hub /health khong phan hoi 200.'
        $failed = $true
    }
}

# 2. Ensure Hub is connected to phucthanh-flow-view-net
$netMembers = docker network inspect phucthanh-flow-view-net --format '{{range .Containers}}{{.Name}} {{end}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '[LOI] Khong tim thay mang docker phucthanh-flow-view-net.'
    $failed = $true
} else {
    if ($netMembers -notmatch 'phucthanh-chatwoot-hub-1') {
        Write-Host '[FIX] Noi lai phucthanh-chatwoot-hub-1 vao phucthanh-flow-view-net...'
        docker network connect phucthanh-flow-view-net phucthanh-chatwoot-hub-1 | Out-Null
    }
    Write-Host '[OK]  Mang phucthanh-flow-view-net da co phucthanh-chatwoot-hub-1'
}

# 3. Check & auto-start phucthanh-flow-observer (with unless-stopped)
$obsStatus = docker inspect phucthanh-flow-observer --format '{{.State.Status}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '[LOI] Khong tim thay container phucthanh-flow-observer.'
    $failed = $true
} else {
    $restartPol = docker inspect phucthanh-flow-observer --format '{{.HostConfig.RestartPolicy.Name}}' 2>$null
    if ($restartPol -ne 'unless-stopped') {
        Write-Host '[FIX] Bat RestartPolicy=unless-stopped cho phucthanh-flow-observer...'
        docker update --restart unless-stopped phucthanh-flow-observer | Out-Null
    }
    if ($RestartObserver -and $obsStatus -eq 'running') {
        Write-Host '[FIX] Khoi dong lai phucthanh-flow-observer theo yeu cau...'
        docker restart phucthanh-flow-observer | Out-Null
        Start-Sleep -Seconds 2
    } elseif ($obsStatus -ne 'running') {
        Write-Host "[FIX] phucthanh-flow-observer dang $obsStatus -> dang khoi dong lai..."
        docker start phucthanh-flow-observer | Out-Null
        Start-Sleep -Seconds 3
    }
    $obsNow = docker inspect phucthanh-flow-observer --format '{{.State.Status}}|{{.HostConfig.RestartPolicy.Name}}' 2>$null
    Write-Host "[OK]  phucthanh-flow-observer: $obsNow"
}

# 4. Verify HTTP 200 on http://192.168.1.57:8097 without printing any keys
if (-not (Test-Path $viewCfgPath)) {
    Write-Host "[LOI] Khong tim thay file cau hinh $viewCfgPath"
    $failed = $true
} elseif (-not (Test-Path $pyExe)) {
    Write-Host "[LOI] Khong tim thay Python tai $pyExe"
    $failed = $true
} else {
    $pyCode = @'
import json, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

key = json.loads(Path(r"C:\Users\Admin\Documents\Codex\2026-10-12\hi-n-m-y-t-nh\work\erp-flow-view\view.private.json").read_text(encoding="utf-8-sig"))["key"]
today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
for path in ("/operations/health", f"/batches?day={today}"):
    req = urllib.request.Request("http://192.168.1.57:8097" + path, headers={"X-Flow-Key": key})
    with urllib.request.urlopen(req, timeout=8) as resp:
        print(f"HTTP_{path.split('?')[0]}={resp.status}")
'@
    $pyOut = $pyCode | & $pyExe - 2>&1
    if ($LASTEXITCODE -eq 0) {
        $pyOut | ForEach-Object { Write-Host "[OK]  $_" }
    } else {
        Write-Host "[LOI] Khong goi duoc http://192.168.1.57:8097: $pyOut"
        $failed = $true
    }
}

if ($failed) {
    Write-Host 'KET QUA: LOI — kiem tra cac dong [LOI] o tren.'
    exit 1
}
Write-Host 'KET QUA: OK — Luong Thuc Thi ERP san sang (F5 trinh duyet ERP de xem).'
exit 0
