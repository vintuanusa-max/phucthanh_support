"""Windows-only read access to Zalo's current SQLCipher session; no injection/dumps."""

import ctypes as C
import hashlib
import hmac
import re
import time
from ctypes import wintypes as W
from pathlib import Path

import psutil

from .codec import PAGE, PageKey, SnapshotError, decode_field, open_snapshot, snapshot


class MemoryReader:
    def __init__(self, exe):
        self.exe = str(Path(exe).resolve()).casefold()
        self.api = C.WinDLL("kernel32", use_last_error=True)

        class MBI(C.Structure):
            _fields_ = [
                ("base", C.c_void_p),
                ("allocation", C.c_void_p),
                ("allocation_protect", W.DWORD),
                ("size", C.c_size_t),
                ("state", W.DWORD),
                ("protect", W.DWORD),
                ("type", W.DWORD),
            ]

        self.MBI = MBI
        k = self.api
        k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        k.OpenProcess.restype = W.HANDLE
        k.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(MBI), C.c_size_t]
        k.VirtualQueryEx.restype = C.c_size_t
        k.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
        k.ReadProcessMemory.restype = W.BOOL
        k.CloseHandle.argtypes = [W.HANDLE]
        k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]

    def processes(self):
        result = []
        for p in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            try:
                if (p.info["exe"] or "").casefold() == self.exe:
                    node = any("node.mojom.NodeService" in a for a in p.info["cmdline"] or [])
                    result.append((not node, p.info["pid"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return [pid for _, pid in sorted(result)]

    def chunks(self, seconds=30):
        deadline = time.monotonic() + seconds
        k = self.api
        for pid in self.processes():
            handle = k.OpenProcess(0x410, False, pid)  # QUERY_INFORMATION | VM_READ only
            if not handle:
                continue
            try:
                exe, size = C.create_unicode_buffer(32768), W.DWORD(32768)
                if not k.QueryFullProcessImageNameW(handle, 0, exe, C.byref(size)):
                    continue
                if exe.value.casefold() != self.exe:
                    continue
                address, info = 0, self.MBI()
                while time.monotonic() < deadline and k.VirtualQueryEx(
                    handle, C.c_void_p(address), C.byref(info), C.sizeof(info)
                ):
                    base, size = info.base or 0, info.size
                    address = base + size
                    if not size or address <= base:
                        break
                    if info.state != 0x1000 or info.type != 0x20000 or info.protect & 0x101:
                        continue
                    if not info.protect & 0xEE:
                        continue
                    overlap = b""
                    for offset in range(0, size, 1048576):
                        if time.monotonic() >= deadline:
                            return
                        n = min(1048576, size - offset)
                        buf, got = C.create_string_buffer(n), C.c_size_t()
                        if not k.ReadProcessMemory(handle, C.c_void_p(base + offset), buf, n, C.byref(got)):
                            overlap = b""
                            continue
                        data = overlap + buf.raw[: got.value]
                        yield data
                        overlap = data[-256:]
            finally:
                k.CloseHandle(handle)

    def find_secret(self, message_dir):
        catalog = {}
        paths = sorted(Path(message_dir).glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[:400]:
            if path.stat().st_size > 30 * 1024 * 1024:
                continue
            with path.open("rb") as stream:
                page = stream.read(PAGE)
            if len(page) == PAGE:
                catalog[page[:16]] = path, page
        sample, key = None, None
        pattern = re.compile(rb"x'([0-9a-fA-F]{96})'")
        chunks = self.chunks()
        try:
            for data in chunks:
                for match in pattern.finditer(data):
                    packed = bytes.fromhex(match[1].decode())
                    if packed[32:] not in catalog:
                        continue
                    path, page = catalog[packed[32:]]
                    candidate = PageKey(packed[:32], packed[32:])
                    try:
                        candidate.decrypt(page, 1)
                        raw, wal, _ = snapshot(path, 30 * 1024 * 1024)
                        db = open_snapshot(raw, wal, candidate)
                        try:
                            row = db.execute(
                                "SELECT message FROM message WHERE msgType=1 AND ev=0 "
                                "ORDER BY CAST(serverTime AS INTEGER) DESC LIMIT 1"
                            ).fetchone()
                        finally:
                            db.close()
                        if row:
                            sample, key = row[0], candidate
                            break
                    except (SnapshotError, ValueError):
                        continue
                if sample:
                    break
        finally:
            chunks.close()
        if not sample:
            raise SnapshotError("no_verified_session_database")
        pattern = re.compile(rb"(?<![0-9a-fA-F])([0-9a-fA-F]{32}|[0-9a-fA-F]{64})(?![0-9a-fA-F])")
        seen = set()
        chunks = self.chunks()
        try:
            for data in chunks:
                for payload in (data, data.replace(b"\0", b"")):
                    for match in pattern.finditer(payload):
                        secret = match[1]
                        if secret in seen:
                            continue
                        seen.add(secret)
                        try:
                            text = decode_field(sample, secret, 0)
                            if not isinstance(text, str):
                                continue
                        except (ValueError, UnicodeError, SnapshotError):
                            continue
                        derived = hashlib.pbkdf2_hmac("sha512", secret, key.salt, 256000, 32)
                        if hmac.compare_digest(derived, key.key):
                            return secret
        finally:
            chunks.close()
        raise SnapshotError("session_secret_unavailable")
