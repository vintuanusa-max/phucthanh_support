"""Resolve Viber only within its known per-user installation; detect DLL upgrades."""
import os
from pathlib import Path
import psutil

def active_exe(base=None, processes=None):
 base=Path(base or Path(os.environ['LOCALAPPDATA'])/'Viber').resolve()
 found=set()
 for p in processes if processes is not None else psutil.process_iter(['exe']):
  try:
   path=Path(p.info.get('exe') or '').resolve()
   if path.name.lower()=='viber.exe' and path.is_relative_to(base):found.add(path)
  except (OSError,psutil.NoSuchProcess,psutil.AccessDenied):continue
 if len(found)>1:raise RuntimeError('Ambiguous Viber installations')
 return next(iter(found)) if found else None

def installation():
 return (active_exe() or Path(os.environ['LOCALAPPDATA'])/'Viber'/'Viber.exe').parent

def signature(root):
 return tuple((name,(root/name).stat().st_size,(root/name).stat().st_mtime_ns) for name in ('Viber.exe','Qt6Core.dll','Qt6Sql.dll','plugins/sqldrivers/qsqlite.dll'))
