"""Current-Windows-user DPAPI cache; authenticate cached keys against source DB."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
from .codec import PAGE, PageKey, SnapshotError

class Blob(C.Structure):
    _fields_=[('size',W.DWORD),('data',C.POINTER(C.c_ubyte))]

def crypt(data, protect):
    buf=C.create_string_buffer(data)
    source=Blob(len(data),C.cast(buf,C.POINTER(C.c_ubyte)));target=Blob()
    api=C.WinDLL('crypt32',use_last_error=True)
    fn=api.CryptProtectData if protect else api.CryptUnprotectData
    fn.argtypes=[C.POINTER(Blob),C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,W.DWORD,C.POINTER(Blob)]
    fn.restype=W.BOOL
    if not fn(C.byref(source),None,None,None,None,1,C.byref(target)):
        raise OSError('Windows key protection failed')
    kernel=C.WinDLL('kernel32');kernel.LocalFree.argtypes=[C.c_void_p]
    kernel.LocalFree.restype=C.c_void_p
    try:return C.string_at(target.data,target.size)
    finally:kernel.LocalFree(target.data)

def save(path, secret):
    path=Path(path);temp=path.with_suffix('.tmp')
    temp.write_bytes(crypt(secret,True));os.replace(temp,path)

def load(path, root):
    try:secret=crypt(Path(path).read_bytes(),False)
    except (OSError,ValueError):return None
    if len(secret) not in (32,64):return None
    for path in sorted(Path(root).glob('*.db'),key=lambda p:p.stat().st_mtime,reverse=True)[:8]:
        try:
            with path.open('rb') as f:page=f.read(PAGE)
            if len(page)!=PAGE:continue
            PageKey.derive(secret,page[:16]).decrypt(page,1)
            return secret
        except (OSError,SnapshotError,ValueError):continue
    return None
