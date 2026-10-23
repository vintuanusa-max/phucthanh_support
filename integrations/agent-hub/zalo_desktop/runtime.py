"""Select only a running Zalo executable under the configured installation root."""
from pathlib import PureWindowsPath
import re
import psutil

def select_session(configured, processes):
    old=PureWindowsPath(configured)
    base=old.parent.parent if re.fullmatch(r'Zalo-[0-9.]+',old.parent.name,re.I) else old.parent
    candidates={}
    for p in processes:
        info=p.info
        exe=info.get('exe') or ''
        path=PureWindowsPath(exe)
        if path.name.lower()!='zalo.exe':continue
        if path.parent.parent!=base or not re.fullmatch(r'Zalo-[0-9.]+',path.parent.name,re.I):continue
        args=info.get('cmdline') or []
        if any(a.startswith('--type=') for a in args):continue
        candidates[(str(path).casefold(),info['pid'])]=str(path)
    if len(candidates)!=1:return None
    identity,exe=next(iter(candidates.items()))
    return identity,exe

def running_session(configured):
    rows=[]
    for p in psutil.process_iter(['pid','exe','cmdline']):
        try:rows.append(p)
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return select_session(configured,rows)
