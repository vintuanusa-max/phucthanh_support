"""Read group metadata through authenticated, lazy, read-only virtual pages."""

import uuid
from pathlib import Path

import apsw

from .codec import PAGE, PageKey, SnapshotError, committed_frames, fingerprint


class Pages:
    def __init__(self, path, secret):
        self.path = Path(path)
        self.before = fingerprint(path)
        self.file = self.path.open("rb")
        try:
            self.key = PageKey.derive(secret, self.file.read(16))
            walpath = Path(str(path) + "-wal")
            if walpath.exists():
                with walpath.open("rb") as stream:
                    wal = stream.read(512 * 1048576 + 1)
                if len(wal) > 512 * 1048576:
                    raise SnapshotError("metadata_wal_size_limit")
            else:
                wal = b""
            self.frames, count = committed_frames(wal)
            self.size = (count * PAGE) if count else self.path.stat().st_size
            self.cache = {}
        except Exception:
            self.file.close()
            raise

    def xRead(self, amount, offset):
        result = bytearray()
        while amount:
            number, within = offset // PAGE + 1, offset % PAGE
            if number not in self.cache:
                raw = self.frames.get(number)
                if raw is None:
                    self.file.seek((number - 1) * PAGE)
                    raw = self.file.read(PAGE)
                plain = self.key.decrypt(raw, number)
                if number == 1:
                    plain = plain[:18] + b"\x01\x01" + plain[20:]
                self.cache[number] = plain
            take = min(amount, PAGE - within)
            result.extend(self.cache[number][within : within + take])
            offset += take
            amount -= take
        return bytes(result)

    def xFileSize(self):
        return self.size

    def xClose(self):
        pass

    def xLock(self, level):
        pass

    def xUnlock(self, level):
        pass

    def xCheckReservedLock(self):
        return False

    def xFileControl(self, op, ptr):
        return False

    def xSectorSize(self):
        return PAGE

    def xDeviceCharacteristics(self):
        return apsw.SQLITE_IOCAP_IMMUTABLE

    def xWrite(self, data, offset):
        raise apsw.ReadOnlyError("read only")

    def xTruncate(self, size):
        raise apsw.ReadOnlyError("read only")

    def xSync(self, flags):
        raise apsw.ReadOnlyError("read only")


class ReadVFS(apsw.VFS):
    def __init__(self, pages):
        self.name = "zalo_metadata_" + uuid.uuid4().hex
        self.pages = pages
        super().__init__(self.name, "")

    def xOpen(self, name, flags):
        if not flags[0] & apsw.SQLITE_OPEN_MAIN_DB or flags[0] & apsw.SQLITE_OPEN_READWRITE:
            raise apsw.ReadOnlyError("read only")
        flags[1] = apsw.SQLITE_OPEN_READONLY
        return self.pages

    def xAccess(self, name, flags):
        return False

    def xDelete(self, name, syncdir):
        raise apsw.ReadOnlyError("read only")


def read_groups(path, secret):
    pages = Pages(path, secret)
    vfs = ReadVFS(pages)
    db = None
    try:
        db = apsw.Connection(
            "file:zalo-metadata?immutable=1",
            flags=apsw.SQLITE_OPEN_READONLY | apsw.SQLITE_OPEN_URI,
            vfs=vfs.name,
        )
        db.execute("PRAGMA trusted_schema=OFF")
        rows = list(db.execute('SELECT userId,displayName FROM "group"'))
        names = {}
        for uid, name in rows:
            uid = str(uid)
            thread = uid if uid.startswith("g") else "g" + uid
            if thread[1:].isdigit() and isinstance(name, str) and name.strip():
                names[thread] = name.strip()[:300]
        if fingerprint(path) != pages.before:
            raise SnapshotError("metadata_changed_during_read")
        return names, pages.before
    finally:
        if db is not None:
            db.close()
        vfs.unregister()
        pages.file.close()
