"""Foreground-aware, bounded source reads and metadata-only cycle logging."""
import ctypes as C
from ctypes import wintypes as W
import json
import time
import psutil

def zalo_foreground():
    api=C.WinDLL('user32',use_last_error=True)
    api.GetForegroundWindow.restype=W.HWND
    api.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    pid=W.DWORD();window=api.GetForegroundWindow()
    if not window:return True  # No reliable desktop observation: defer source access.
    api.GetWindowThreadProcessId(window,C.byref(pid))
    try:return psutil.Process(pid.value).name().casefold()=='zalo.exe'
    except (psutil.NoSuchProcess,psutil.AccessDenied):return True

def allowed(reader):
    from .safe_zalo import windows
    now=time.monotonic()
    if not hasattr(reader,'idle_since'):reader.idle_since=now
    request=reader.home/'safe-open.json'
    try:
        shown=bool(windows())
        pending=json.loads(request.read_text(encoding='utf-8')) if request.exists() else None
    except (OSError,ValueError):
        reader.source_pause='window_state_unknown';reader.idle_since=now;return False
    if shown:
        reader.idle_since=now;reader.source_pause='zalo_window_open';return False
    if pending and pending.get('state')!='opened':
        reader.idle_since=now;reader.source_pause='safe_open_requested';return False
    if now-reader.idle_since<30:
        reader.source_pause='waiting_30_seconds';return False
    if pending:request.unlink(missing_ok=True)
    reader.source_pause=None;return True

def stable(reader,path,mark):
    if not hasattr(reader,'source_marks'):reader.source_marks={}
    now=time.monotonic();old=reader.source_marks.get(str(path))
    if not old or old[0]!=mark:
        reader.source_marks[str(path)]=(mark,now);return False
    return now-old[1]>=10

def event(reader,kind,**fields):
    path=reader.home/'read-cycles.jsonl'
    if path.exists() and path.stat().st_size>2_000_000:
        path.replace(path.with_suffix('.previous.jsonl'))
    with path.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'time':time.time(),'event':kind,**fields},ensure_ascii=False)+'\n')
