"""Only supervise reader process/window lifecycle; never access Zalo data."""
import json
import time
import threading
import subprocess
import psutil
import uuid
import traceback

_live={}

def status(home):
    return dict(_live) if _live else read(home)

guard=threading.RLock()

def processes(home):
    root=str(home.parent).casefold()
    result=[]
    for p in psutil.process_iter(['pid','name','cmdline']):
        try:
            args=' '.join(p.info['cmdline'] or []).casefold()
            if (p.info['name'] or '').casefold() in ('python.exe','pythonw.exe') and 'zalo_desktop.reader' in args and root in args:result.append(p)
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return result

def read(home):
    p=home/'reader-lifecycle.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}

def save(home,data):
    p=home/'reader-lifecycle.json';tmp=home/('reader-lifecycle.'+uuid.uuid4().hex+'.tmp')
    value={**data,'updated_at':time.time()}
    try:
        for attempt in range(4):
            try:
                tmp.write_text(json.dumps(value),encoding='utf-8');tmp.replace(p)
                _live.clear();_live.update(value)
                return
            except PermissionError:
                if attempt==3:raise
                time.sleep(.05*(attempt+1))
    except OSError as exc:
        _live.clear();_live.update(value,error=type(exc).__name__,error_operation='save_lifecycle',error_file=str(getattr(exc,'filename','') or p))
        raise
    finally:
        try:tmp.unlink(missing_ok=True)
        except OSError:pass

def stop(home):
    data=read(home)
    flag=home/'stop.flag'
    owned=data.get('owned_stop',False) or not flag.exists()
    flag.write_text('safe-open full reader shutdown',encoding='ascii')
    data.update(state='stopping',owned_stop=owned,closed_since=None)
    save(home,data)
    return data

def wait_stopped(home):
    data=stop(home)
    end=time.monotonic()+45
    while time.monotonic()<end:
        if not processes(home):
            data.update(state='stopped');save(home,data);return
        time.sleep(.25)
    raise ValueError('Bộ đọc chưa thoát hẳn; chưa mở Zalo. Hãy thử lại khi trạng thái báo đã dừng.')

def step(home,shown,main_exists):
    data=read(home)
    for key in ('error','error_operation','error_file'):data.pop(key,None)
    running=bool(processes(home))
    data.update(reader_running=running,window_open=shown,main_exists=main_exists)
    if shown:
        if running or not data.get('owned_stop'):
            data=stop(home)
        data.update(state='stopping' if running else 'stopped_window_open',closed_since=None)
        save(home,data);return
    if not main_exists:
        if running or not data.get('owned_stop'):data=stop(home)
        data.update(state='waiting_zalo',closed_since=None);save(home,data);return
    if not data.get('owned_stop'):
        data.update(state='running' if running else 'manual_stop' if (home/'stop.flag').exists() else 'reader_missing',closed_since=None)
        save(home,data);return
    # A failed safe-open request must not immediately restart the reader.
    if data.get('state') in ('stopping','stopped'):
        save(home,data);return
    if running:
        data.update(state='running',owned_stop=False,closed_since=None);save(home,data);return
    since=data.get('closed_since') or time.time()
    if time.time()-since<30:
        data.update(state='waiting_tray',closed_since=since);save(home,data);return
    if time.time()-data.get('last_start',0)<60:
        save(home,data);return
    # Remove only the pause request owned by safe-open; Start-Reader enforces one instance.
    (home/'safe-open.json').unlink(missing_ok=True)
    data.update(state='starting',last_start=time.time(),closed_since=since);save(home,data)
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(home.parent/'Start-Reader.ps1')],timeout=20,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)

def supervise(home):
    from safe_zalo import windows
    while True:
        try:
            with guard:step(home,bool(windows()),bool(windows(False)))
        except Exception as exc:
            try:
                data=dict(_live) if _live else read(home)
                data.update(error=type(exc).__name__,error_operation=traceback.extract_tb(exc.__traceback__)[-1].name,error_file=str(getattr(exc,'filename','') or ''))
                _live.clear();_live.update(data,updated_at=time.time())
                save(home,data)
            except Exception:pass
        time.sleep(2)
