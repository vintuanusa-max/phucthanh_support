"""Version/account-pinned native photo delivery; caller owns the durable send claim."""
import json
import subprocess
from pathlib import Path

import psutil


def transport(job, prepare=False):
    runtime=Path.home()/'AppData/Local/PhucThanh/ZaloDesktopReader'
    halt=runtime/'state/print-transport-halt.flag'
    if halt.exists():return {'state':'blocked'}
    cfg=json.loads((runtime/'reader.local.json').read_text(encoding='utf-8-sig'))
    pids=[p.pid for p in psutil.process_iter(['exe','cmdline'])
          if (p.info['exe'] or '').lower()==cfg['zalo_exe'].lower()
          and not any(a.startswith('--type=') for a in (p.info['cmdline'] or []))]
    if len(pids)!=1:return {'state':'blocked'}
    request={**job,'pid':pids[0],'zalo_exe':cfg['zalo_exe'],'user_id':cfg['user_id'],
             'action':'prepare' if prepare else 'send'}
    proc=subprocess.run([cfg['node_exe'],str(Path(__file__).with_name('preview_photo_transport.cjs'))],
                        input=json.dumps(request),text=True,encoding='utf-8',capture_output=True,
                        timeout=65,creationflags=subprocess.CREATE_NO_WINDOW)
    result=json.loads(proc.stdout)
    if not result.get('cleanup'):
        halt.write_text('Inspector cleanup needs review',encoding='utf-8')
        return {'state':'uncertain'}
    return result
