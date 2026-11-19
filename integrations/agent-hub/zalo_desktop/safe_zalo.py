"""Shared source-read lock and explicit safe-open handshake."""
import ctypes as C
from ctypes import wintypes as W
import json
import time
import uuid
import msvcrt
import psutil

def windows(visible=True):
    api=C.WinDLL('user32',use_last_error=True)
    api.IsWindowVisible.argtypes=[W.HWND]
    api.GetWindowLongW.argtypes=[W.HWND,C.c_int]
    api.GetWindowTextLengthW.argtypes=[W.HWND]
    api.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
    api.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    found=[]
    callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    @callback
    def visit(hwnd,_):
        try:
            if visible and not api.IsWindowVisible(hwnd):return True
            style=api.GetWindowLongW(hwnd,-16)&0xffffffff
            if not (style & 0x00C00000 or style & 0x00040000):return True  # exclude frameless toast/tool windows
            n=api.GetWindowTextLengthW(hwnd)
            if not n:return True
            title=C.create_unicode_buffer(n+1);api.GetWindowTextW(hwnd,title,n+1)
            pid=W.DWORD();api.GetWindowThreadProcessId(hwnd,C.byref(pid))
            if psutil.Process(pid.value).name().casefold()=='zalo.exe' and 'zalo' in title.value.casefold():found.append(hwnd)
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        return True
    api.EnumWindows.argtypes=[callback,W.LPARAM]
    if not api.EnumWindows(visit,0):raise OSError('Cannot inspect Zalo windows')
    return found

def lock(home):
    f=(home/'source-read.lock').open('a+b')
    if (home/'source-read.lock').stat().st_size==0:f.write(b'0');f.flush()
    f.seek(0)
    try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:f.close();return None
    return f

def unlock(f):
    f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1);f.close()

def request(home):
    path=home/'safe-open.json'
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    data={'id':uuid.uuid4().hex,'state':'waiting','requested':time.time()}
    save(home,data);return data

def save(home,data):
    p=home/'safe-open.json';tmp=home/'safe-open.tmp'
    tmp.write_text(json.dumps(data),encoding='utf-8');tmp.replace(p)

def open_requested(home):
    data=request(home)
    f=None
    try:
        until=time.monotonic()+45
        while time.monotonic()<until:
            f=lock(home)
            if f:break
            time.sleep(.2)
        if not f:raise ValueError('Lượt đọc chưa kết thúc; chưa mở Zalo. Bộ đọc đang được yêu cầu tạm dừng.')
        handles=windows(False)
        if not handles:raise ValueError('Không tìm thấy cửa sổ Zalo đang chạy; chưa mở ứng dụng.')
        api=C.WinDLL('user32');api.ShowWindowAsync.argtypes=[W.HWND,C.c_int];api.SetForegroundWindow.argtypes=[W.HWND]
        for hwnd in handles:
            api.ShowWindowAsync(hwnd,9);api.SetForegroundWindow(hwnd)
        for _ in range(25):
            if windows():
                data.update(state='opened',opened=time.time());save(home,data)
                return {'detail':'Đã mở Zalo sau khi lượt đọc kết thúc. Chỉ đọc lại khi đóng xuống khay.'}
            time.sleep(.2)
        raise ValueError('Chưa xác nhận cửa sổ Zalo đã mở; giữ tạm dừng đọc.')
    finally:
        if f:unlock(f)
