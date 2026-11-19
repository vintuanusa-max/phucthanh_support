"""Service status inspection and safe allowlisted restart helpers for SystemMonitor."""
import os
import subprocess
import time
from pathlib import Path
import psutil

ROOT = Path(os.environ['LOCALAPPDATA']) / 'PhucThanh'
CREATE_NO_WINDOW = 0x08000000
DOCKER_EXE = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
VENV_PY = ROOT / 'ZaloDesktopReader/code/.venv/Scripts/python.exe'
AGENT_HUB_DIR = Path(r'C:\Users\Admin\Documents\Codex\2026-10-12\hi-n-m-y-t-nh\work\agent-hub')

CONFIG_ARGS = [
    '--config', str(ROOT / 'ZaloDesktopReader/reader.local.json'),
    '--config', str(ROOT / 'WhatsAppDesktopReader/reader.local.json'),
    '--config', str(ROOT / 'ViberDesktopReader/reader.local.json'),
]

SERVICES = [
    {
        'id': 'artwork_worker',
        'name': 'ArtworkInspector Worker (Xuất AI/PET/JPG)',
        'group': 'Xuất file Windows',
        'kind': 'ps1',
        'marker': 'artworkinspector\\worker.py',
        'script': str(ROOT / 'ArtworkInspector/Start.ps1'),
    },
    {
        'id': 'comparison_worker',
        'name': 'ArtworkInspector Comparison Worker (Đối chiếu mẫu)',
        'group': 'Xuất file Windows',
        'kind': 'python',
        'marker': 'comparison_worker.py',
        'exe': str(VENV_PY),
        'args': [str(ROOT / 'ArtworkInspector/comparison_worker.py'), '--watch', *CONFIG_ARGS],
        'cwd': str(ROOT / 'ArtworkInspector'),
    },
    {
        'id': 'zalo_reader',
        'name': 'Đọc Zalo → Chatwoot (zalo_desktop.reader)',
        'group': 'Bộ đọc / gửi tin',
        'kind': 'ps1',
        'marker': 'zalo_desktop.reader',
        'script': str(ROOT / 'ZaloDesktopReader/Start-Reader.ps1'),
    },
    {
        'id': 'zalo_sender',
        'name': 'Gửi Zalo (zalo_desktop.sender)',
        'group': 'Bộ đọc / gửi tin',
        'kind': 'ps1',
        'marker': 'zalo_desktop.sender',
        'script': str(ROOT / 'ZaloDesktopReader/Start-Sender.ps1'),
        'halt_flag': str(ROOT / 'ZaloDesktopReader/state/sender/halt.flag'),
    },
    {
        'id': 'whatsapp_reader',
        'name': 'Đọc WhatsApp (whatsapp_desktop.reader)',
        'group': 'Bộ đọc / gửi tin',
        'kind': 'ps1',
        'marker': 'whatsapp_desktop.reader',
        'script': str(ROOT / 'WhatsAppDesktopReader/Start-Reader.ps1'),
    },
    {
        'id': 'viber_reader',
        'name': 'Đọc Viber (viber_desktop.reader)',
        'group': 'Bộ đọc / gửi tin',
        'kind': 'ps1',
        'marker': 'viber_desktop.reader',
        'script': str(ROOT / 'ViberDesktopReader/Start-Reader.ps1'),
    },
    {
        'id': 'viber_sender',
        'name': 'Gửi Viber (viber_desktop.sender)',
        'group': 'Bộ đọc / gửi tin',
        'kind': 'ps1',
        'marker': 'viber_desktop.sender',
        'script': str(ROOT / 'ViberDesktopReader/Start-Sender.ps1'),
    },
    {
        'id': 'hub_docker',
        'name': 'Hub AI Container (phucthanh-chatwoot-hub-1)',
        'group': 'Docker',
        'kind': 'docker',
        'containers': ['phucthanh-chatwoot-hub-1'],
    },
    {
        'id': 'chatwoot_docker',
        'name': 'Chatwoot Containers (rails + sidekiq)',
        'group': 'Docker',
        'kind': 'docker',
        'containers': ['phucthanh-chatwoot-rails-1', 'phucthanh-chatwoot-sidekiq-1'],
    },
    {
        'id': 'system_monitor_api',
        'name': 'Monitor API (system_monitor.py)',
        'group': 'Giám sát',
        'kind': 'readonly',
        'marker': 'system_monitor.py',
    },
    {
        'id': 'system_monitor_ui',
        'name': 'Bảng điều phối này (SystemMonitor :8096)',
        'group': 'Giám sát',
        'kind': 'readonly',
        'marker': 'systemmonitor\\server.py',
    },
]


def _docker_states():
    states = {}
    try:
        r = subprocess.run(
            [DOCKER_EXE, 'ps', '-a', '--format', '{{.Names}}|{{.State}}|{{.Status}}'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=8, creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = line.split('|', 2)
                if len(parts) == 3:
                    states[parts[0].strip()] = (parts[1].strip(), parts[2].strip())
    except Exception:
        pass
    return states


def _matching_pids(marker):
    pids = []
    m = marker.lower()
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (p.info.get('name') or '').lower()
            if 'python' not in name:
                continue
            cmd = ' '.join(p.info.get('cmdline') or []).lower()
            if m in cmd:
                pids.append(p.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def collect_services(ps_procs=None):
    """Return status list for all registered PhucThanh services."""
    docker_map = _docker_states()
    if ps_procs is None:
        ps_procs = []
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'python' in (p.info.get('name') or '').lower():
                    ps_procs.append({
                        'pid': p.info['pid'],
                        'Name': p.info.get('name') or '',
                        'CommandLine': ' '.join(p.info.get('cmdline') or []),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    out = []
    for svc in SERVICES:
        kind = svc['kind']
        if kind == 'docker':
            c_names = svc['containers']
            statuses = [docker_map.get(c, ('unknown', 'Không đọc được Docker')) for c in c_names]
            running = all(st == 'running' for st, _ in statuses)
            state = 'ok' if running else 'bad'
            detail = ' · '.join(f'{c}: {txt}' for c, (_, txt) in zip(c_names, statuses))
            out.append({
                'id': svc['id'],
                'name': svc['name'],
                'group': svc['group'],
                'running': running,
                'state': state,
                'detail': detail,
                'can_restart': True,
            })
        else:
            marker = svc['marker'].lower()
            pids = [
                p.get('pid') for p in ps_procs
                if marker in str(p.get('CommandLine', '')).lower()
            ]
            # Fallback if ps_procs didn't include pid
            if not pids and any(marker in str(p.get('CommandLine', '')).lower() for p in ps_procs):
                pids = _matching_pids(svc['marker'])
            running = len(pids) > 0
            state = 'ok' if running else 'bad'
            detail = f"Đang chạy (PID {', '.join(str(x) for x in pids)})" if running else 'ĐÃ TẮT — chưa thấy tiến trình'
            halt = svc.get('halt_flag')
            if halt and Path(halt).exists():
                state = 'warn' if running else 'bad'
                detail += ' · Có halt.flag (cần kiểm tra trước khi chạy lại)'
            out.append({
                'id': svc['id'],
                'name': svc['name'],
                'group': svc['group'],
                'running': running,
                'state': state,
                'detail': detail,
                'can_restart': kind != 'readonly',
            })
    return out


def _stop_marker(marker):
    pids = _matching_pids(marker)
    procs = []
    for pid in pids:
        try:
            p = psutil.Process(pid)
            p.terminate()
            procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(procs, timeout=2.5)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return len(pids)


def restart_service(service_id):
    """Safely stop and restart an allowlisted service by ID."""
    svc = next((s for s in SERVICES if s['id'] == service_id), None)
    if not svc or svc['kind'] == 'readonly':
        raise ValueError('Dịch vụ không hợp lệ hoặc chỉ đọc')

    kind = svc['kind']
    if kind == 'docker':
        r = subprocess.run(
            [DOCKER_EXE, 'restart', *svc['containers']],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=45, creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            raise ValueError((r.stderr or r.stdout or 'Lỗi docker restart').strip())
        return {'ok': True, 'id': service_id, 'message': f"Đã khởi động lại {', '.join(svc['containers'])}"}

    halt = svc.get('halt_flag')
    if halt and Path(halt).exists():
        raise ValueError('Đang có halt.flag — kiểm tra lý do dừng trước khi khởi động lại')

    stopped = _stop_marker(svc['marker'])
    if kind == 'ps1':
        r = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', svc['script']],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15, creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            raise ValueError('Lỗi chạy script khởi động (mã ' + str(r.returncode) + ')')
    elif kind == 'python':
        subprocess.Popen(
            [svc['exe'], *svc['args']],
            cwd=svc['cwd'],
            creationflags=CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    time.sleep(1.2)
    pids = _matching_pids(svc['marker'])
    if not pids:
        raise ValueError('Đã chạy lệnh khởi động nhưng chưa thấy tiến trình mới lên')
    return {
        'ok': True,
        'id': service_id,
        'pids': pids,
        'message': f"Đã khởi động lại {svc['name']} (dừng {stopped} tiến trình cũ, PID mới: {', '.join(str(x) for x in pids)})",
    }
