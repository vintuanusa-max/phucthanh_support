<#
.SYNOPSIS
Sync ASCII designer folder naming scripts and install spot-deps (tifffile, numpy, imagecodecs) for Windows Artwork Worker (designer-main / local-backup).
Never modifies worker credentials/configs and NEVER closes Illustrator/Photoshop/CorelDRAW.
#>
[CmdletBinding()]
param(
    [string]$WorkerDir,
    [string]$PythonExe,
    [switch]$CheckOnly,
    [switch]$SkipRestart
)

$ErrorActionPreference = 'Stop'
$SourceDir = $PSScriptRoot
$FilesToSync = @(
    'fleet_paths.py',
    'native_worker.py',
    'pet_worker.py',
    'jpg_worker.py',
    'pattern_export.py',
    'original_pdf_export.py'
)
$ReqFile = Join-Path $SourceDir 'spot-deps-requirements.txt'

function Get-WorkerCimProcesses {
    try {
        return @(Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.Name -match '^python' -and $_.CommandLine -match '(ArtworkInspector|PHUCTHANH_HUB_WORKER)\\(fleet_runner|worker)\.py' })
    } catch {
        return @()
    }
}

function Resolve-WorkerContext {
    param([string]$RequestedDir, [string]$RequestedPy)

    $proc = Get-WorkerCimProcesses | Select-Object -First 1

    $dir = $RequestedDir
    if (-not $dir -and $proc -and $proc.CommandLine -match '([A-Za-z]:\\[^"]*?(?:ArtworkInspector|PHUCTHANH_HUB_WORKER))\\(?:fleet_runner|worker)\.py') {
        $dir = $Matches[1]
    }
    if (-not $dir) {
        $candidates = @(
            'G:\PHUCTHANH_HUB_WORKER',
            (Join-Path $env:LOCALAPPDATA 'PhucThanh\ArtworkInspector'),
            'C:\Users\Admin\AppData\Local\PhucThanh\ArtworkInspector'
        )
        foreach ($c in $candidates) {
            if ($c -and (Test-Path -LiteralPath $c)) { $dir = $c; break }
        }
    }
    if (-not $dir -or -not (Test-Path -LiteralPath $dir)) {
        throw "Khong tim thay thu muc worker (hay truyen -WorkerDir <duong dan>)."
    }

    $py = $RequestedPy
    if (-not $py -and $proc -and $proc.ExecutablePath -and (Test-Path -LiteralPath $proc.ExecutablePath)) {
        $py = $proc.ExecutablePath
    }
    if (-not $py) {
        $pyCandidates = @(
            (Join-Path $dir '.venv\Scripts\python.exe'),
            (Join-Path (Split-Path $dir -Parent) 'ZaloDesktopReader\code\.venv\Scripts\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'PhucThanh\ArtworkInspector\.venv\Scripts\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'PhucThanh\ZaloDesktopReader\code\.venv\Scripts\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
        )
        foreach ($p in $pyCandidates) {
            if ($p -and (Test-Path -LiteralPath $p)) { $py = $p; break }
        }
    }
    if (-not $py) {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $py = $cmd.Source }
    }
    if (-not $py -or -not (Test-Path -LiteralPath $py)) {
        throw "Khong tim thay python.exe cua worker (hay truyen -PythonExe <duong dan>)."
    }
    if ((Split-Path -Leaf $py).ToLowerInvariant() -eq 'pythonw.exe') {
        $consolePy = Join-Path (Split-Path -Parent $py) 'python.exe'
        if (Test-Path -LiteralPath $consolePy) { $py = $consolePy }
    }
    return @{ WorkerDir = $dir; PythonExe = $py }
}

$ctx = Resolve-WorkerContext -RequestedDir $WorkerDir -RequestedPy $PythonExe
$TargetDir = $ctx.WorkerDir
$TargetPy = $ctx.PythonExe
$SpotDepsDir = Join-Path $TargetDir 'spot-deps'

Write-Host "[INFO] WorkerDir : $TargetDir"
Write-Host "[INFO] PythonExe : $TargetPy"
Write-Host "[INFO] SpotDeps  : $SpotDepsDir"
Write-Host "[INFO] Mode      : $(if ($CheckOnly) { 'CHECK_ONLY' } else { 'APPLY_AND_VERIFY' })"

if (-not $CheckOnly) {
    foreach ($f in $FilesToSync) {
        if (-not (Test-Path -LiteralPath (Join-Path $SourceDir $f))) {
            throw "Thieu file nguon trong repo: $f"
        }
    }
    if (-not (Test-Path -LiteralPath $ReqFile)) {
        throw "Thieu spot-deps-requirements.txt: $ReqFile"
    }

    $backupDir = Join-Path $TargetDir ('backup-before-sync-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    foreach ($f in $FilesToSync) {
        $cur = Join-Path $TargetDir $f
        if (Test-Path -LiteralPath $cur) {
            Copy-Item -Force -LiteralPath $cur -Destination (Join-Path $backupDir $f)
        }
        Copy-Item -Force -LiteralPath (Join-Path $SourceDir $f) -Destination $cur
    }
    Write-Host "[OK] Da sao luu ban cu vao $backupDir va cap nhat $($FilesToSync.Count) file .py."

    New-Item -ItemType Directory -Force -Path $SpotDepsDir | Out-Null
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd) {
        Write-Host "[INFO] Dang cai spot-deps bang uv..."
        & $uvCmd.Source pip install --python $TargetPy --target $SpotDepsDir --upgrade --only-binary=:all: -r $ReqFile
        if ($LASTEXITCODE -ne 0) { throw "uv pip install that bai (exit=$LASTEXITCODE)" }
    } else {
        Write-Host "[INFO] Dang cai spot-deps bang python -m pip..."
        & $TargetPy -m pip install --target $SpotDepsDir --upgrade --only-binary=:all: -r $ReqFile
        if ($LASTEXITCODE -ne 0) { throw "pip install that bai (exit=$LASTEXITCODE)" }
    }
    Write-Host "[OK] Da cai dat tifffile, numpy, imagecodecs vao $SpotDepsDir."
}

Write-Host "[INFO] Dang chay tu kiem tra py_compile + ASCII naming + imagecodecs LZW roundtrip..."
$selfTest = @'
import io, os, py_compile, sys
from pathlib import Path

worker_dir = Path(os.environ['PT_WORKER_DIR'])
spot_deps = Path(os.environ['PT_SPOT_DEPS'])
files = ['fleet_paths.py', 'native_worker.py', 'pet_worker.py', 'jpg_worker.py', 'pattern_export.py', 'original_pdf_export.py']

sys.path.insert(0, str(worker_dir))
for name in files:
    fp = worker_dir / name
    assert fp.is_file(), f'Missing {fp}'
    py_compile.compile(str(fp), doraise=True)
print('PY_COMPILE_OK')

from fleet_paths import ascii_model, ascii_file_code
assert ascii_model('FILE IN PET TB3V\u0110-KEMNGHIA.11') == 'FILEINPETTB3VD-KEMNGHIA11'
assert ascii_model('File in PET TDV\u0110-HUB.11') == 'FileinPETTDVD-HUB11'
assert ascii_file_code('T\u0110VB-THOSAN.09') == 'TDVB-THOSAN.09'
assert ascii_file_code('File in CHUY\u1ec2N NHI\u1ec6T VB-LHP.03') == 'File_in_CHUYEN_NHIET_VB-LHP.03'
print('ASCII_OK')

if spot_deps.is_dir():
    sys.path.insert(0, str(spot_deps))
import numpy as np
import tifffile
import imagecodecs

arr = np.zeros((12, 16, 5), dtype=np.uint8)
arr[2:10, 2:14, :4] = 200
arr[3:9, 3:13, 4] = 255
buf = io.BytesIO()
tifffile.imwrite(buf, arr, photometric='rgb', planarconfig='contig', extrasamples=[2, 0], compression='lzw')
buf.seek(0)
with tifffile.TiffFile(buf) as tf:
    decoded = tf.pages[0].asarray(maxworkers=1)
assert decoded.shape == arr.shape and np.array_equal(decoded, arr), f'Mismatch {decoded.shape}'
print('LZW_SPOT_DECODE_OK', 'imagecodecs=' + getattr(imagecodecs, '__version__', '?'), 'tifffile=' + getattr(tifffile, '__version__', '?'))
'@

$oldWd = $env:PT_WORKER_DIR
$oldSd = $env:PT_SPOT_DEPS
try {
    $env:PT_WORKER_DIR = $TargetDir
    $env:PT_SPOT_DEPS = $SpotDepsDir
    $selfTest | & $TargetPy -
    if ($LASTEXITCODE -ne 0) { throw "Tu kiem tra Python that bai (exit=$LASTEXITCODE)" }
} finally {
    if ($null -eq $oldWd) { Remove-Item Env:PT_WORKER_DIR -ErrorAction SilentlyContinue } else { $env:PT_WORKER_DIR = $oldWd }
    if ($null -eq $oldSd) { Remove-Item Env:PT_SPOT_DEPS -ErrorAction SilentlyContinue } else { $env:PT_SPOT_DEPS = $oldSd }
}

if (-not $CheckOnly -and -not $SkipRestart) {
    $workerProcs = Get-WorkerCimProcesses
    if ($workerProcs.Count -gt 0) {
        Write-Host "[INFO] Dang khoi dong lai $($workerProcs.Count) tien trinh worker Python (khong dong toi Photoshop/Illustrator/Corel)..."
        foreach ($wp in $workerProcs) {
            Stop-Process -Id $wp.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 2
    }

    $started = $false
    $startupLnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\PhucThanh Hub Worker.lnk'
    if (Test-Path -LiteralPath $startupLnk) {
        Start-Process -FilePath $startupLnk
        Write-Host "[OK] Da khoi dong worker qua '$startupLnk'."
        $started = $true
    }

    if (-not $started) {
        $task = $null
        try {
            $task = Get-ScheduledTask -ErrorAction Stop |
                Where-Object { $_.TaskName -match 'PhucThanh.*(Export|Monitor|Artwork|Fleet)' } |
                Select-Object -First 1
        } catch {
            $task = $null
        }
        if ($task) {
            Start-ScheduledTask -TaskName $task.TaskName
            Write-Host "[OK] Da kich hoat Scheduled Task '$($task.TaskName)'."
            $started = $true
        }
    }

    if (-not $started) {
        $startPs1 = Join-Path $TargetDir 'Start.ps1'
        if (Test-Path -LiteralPath $startPs1) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startPs1
            Write-Host "[OK] Da chay lai worker bang '$startPs1'."
            $started = $true
        }
    }

    if (-not $started) {
        Write-Host "[WARN] Chua tu dong khoi dong lai duoc; hay mo lai worker thu cong."
    }
}

Write-Host "[OK] Hoan tat kiem tra va dong bo ArtworkInspector!"
