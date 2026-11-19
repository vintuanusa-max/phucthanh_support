"""Close only positively identified Illustrator font dialogs during a job.

SC_CLOSE is the window-targeted equivalent of Alt+F4. Never close the main
application or accept Save/Replace/Convert dialogs. No export retries here.
"""
import ctypes
import json
import threading
import time
from pathlib import Path


def is_font_dialog(process, window_class, text):
    text = text.casefold()
    return (process.casefold().endswith('illustrator.exe')
            and window_class == '#32770'
            and any(x in text for x in ('missing fonts', 'missing font', 'font not found',
                                       'fonts are missing', 'thiếu font', 'thiếu phông'))
            and not any(x in text for x in ('save changes', 'lưu thay đổi', 'overwrite')))


class FontDialogGuard:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.stop = threading.Event()

    def __enter__(self):
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=3)

    def watch(self):
        from ctypes import wintypes as w
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        k.OpenProcess.restype = w.HANDLE
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        k.CloseHandle.argtypes = [w.HANDLE]
        u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        u.GetWindow.argtypes = [w.HWND, w.UINT]
        u.GetWindow.restype = w.HWND
        u.IsWindowVisible.argtypes = [w.HWND]
        u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        u.EnumChildWindows.argtypes = [w.HWND, callback, w.LPARAM]
        u.EnumWindows.argtypes = [callback, w.LPARAM]
        u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        seen = set()
        def text(hwnd):
            b = ctypes.create_unicode_buffer(4096)
            u.GetWindowTextW(hwnd, b, len(b))
            return b.value
        @callback
        def visit(hwnd, _):
            if hwnd in seen or not u.IsWindowVisible(hwnd):
                return True
            cls = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(hwnd, cls, len(cls))
            if cls.value != '#32770' or not u.GetWindow(hwnd, 4):
                return True
            pid = w.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            handle = k.OpenProcess(0x1000, False, pid.value)
            if not handle:
                return True
            try:
                path, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
                if not k.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                    return True
            finally:
                k.CloseHandle(handle)
            if not path.value.casefold().endswith('illustrator.exe'):
                return True
            labels = [text(hwnd)]
            @callback
            def child(h, _):
                labels.append(text(h))
                return True
            u.EnumChildWindows(hwnd, child, 0)
            message = '\n'.join(labels)
            if is_font_dialog(path.value, cls.value, message) and len(seen) < 2:
                seen.add(hwnd)
                with (self.folder/'font-dialog-events.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'time':time.time(), 'pid':pid.value, 'message':message,
                                        'action':'SC_CLOSE_font_dialog'}, ensure_ascii=False)+'\n')
                u.PostMessageW(hwnd, 0x112, 0xF060, 0)
            return True
        while not self.stop.is_set():
            u.EnumWindows(visit, 0)
            self.stop.wait(2)
