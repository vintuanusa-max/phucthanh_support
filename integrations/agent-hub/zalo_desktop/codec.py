"""Authenticated SQLCipher v4 snapshots. Source files are opened only with rb."""

import hashlib
import hmac
import json
import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PAGE = 4096
RESERVE = 80


class SnapshotError(Exception):
    pass


def fingerprint(path):
    result = []
    for p in (Path(path), Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            st = p.stat()
            with p.open("rb") as stream:
                header = stream.read(96 if str(p).endswith("-shm") else 32)
            result.append((st.st_ino, st.st_size, st.st_mtime_ns, header.hex()))
        except FileNotFoundError:
            result.append(None)
    return json.dumps(result)


def snapshot(path, max_bytes=256 * 1024 * 1024):
    path = Path(path)
    before = fingerprint(path)
    parts = []
    for p in (path, Path(str(path) + "-wal")):
        try:
            with p.open("rb") as stream:
                value = stream.read(max_bytes + 1)
            if len(value) > max_bytes:
                raise SnapshotError("snapshot_size_limit")
            parts.append(value)
        except FileNotFoundError:
            if p == path:
                raise
            parts.append(b"")
    if before != fingerprint(path):
        raise SnapshotError("source_changed_during_read")
    return parts[0], parts[1], before


@dataclass(repr=False)
class PageKey:
    key: bytes = field(repr=False)
    salt: bytes = field(repr=False)

    @classmethod
    def derive(cls, secret, salt):
        return cls(hashlib.pbkdf2_hmac("sha512", secret, salt, 256000, 32), salt)

    def decrypt(self, page, number):
        if len(page) != PAGE or number < 1:
            raise SnapshotError("invalid_page")
        skip = 16 if number == 1 else 0
        mac_key = hashlib.pbkdf2_hmac("sha512", self.key, bytes(b ^ 0x3A for b in self.salt), 2, 32)
        digest = hmac.new(mac_key, page[skip : PAGE - 64] + struct.pack("<I", number), "sha512").digest()
        if not hmac.compare_digest(digest, page[PAGE - 64 :]):
            raise SnapshotError("page_authentication_failed")
        decryptor = Cipher(algorithms.AES(self.key), modes.CBC(page[PAGE - 80 : PAGE - 64])).decryptor()
        body = decryptor.update(page[skip : PAGE - 80]) + decryptor.finalize()
        return (b"SQLite format 3\0" if skip else b"") + body + bytes(RESERVE)


def checksum(data, endian, state=(0, 0)):
    if len(data) % 8:
        raise SnapshotError("wal_checksum_alignment")
    a, b = state
    for x, y in struct.iter_unpack(endian + "II", data):
        a = (a + x + b) & 0xFFFFFFFF
        b = (b + y + a) & 0xFFFFFFFF
    return a, b


def committed_frames(wal):
    """Use only a checksum-valid prefix ending at a commit; reject torn frames."""
    if not wal or len(wal) < 32:
        return {}, None
    magic, version, size = struct.unpack(">III", wal[:12])
    if magic not in (0x377F0682, 0x377F0683) or version != 3007000 or size != PAGE:
        raise SnapshotError("unsupported_wal")
    endian = "<" if magic == 0x377F0682 else ">"
    state = checksum(wal[:24], endian)
    if state != struct.unpack(">II", wal[24:32]):
        raise SnapshotError("wal_header_checksum")
    pending, committed, db_size = {}, {}, None
    for pos in range(32, len(wal) - (24 + PAGE) + 1, 24 + PAGE):
        header, data = wal[pos : pos + 24], wal[pos + 24 : pos + 24 + PAGE]
        # Old frames can remain after WAL reset; salts mark end of this generation.
        if header[8:16] != wal[16:24]:
            break
        number, commit_size = struct.unpack(">II", header[:8])
        state = checksum(data, endian, checksum(header[:8], endian, state))
        if state != struct.unpack(">II", header[16:24]) or not number:
            raise SnapshotError("wal_frame_checksum")
        pending[number] = data
        if commit_size:
            committed.update(pending)
            pending.clear()
            db_size = commit_size
    return committed, db_size


def open_snapshot(database, wal, key):
    if not database or len(database) % PAGE:
        raise SnapshotError("invalid_database_size")
    frames, committed_size = committed_frames(wal)
    count = committed_size or len(database) // PAGE
    if count > 65536:
        raise SnapshotError("snapshot_page_limit")
    plain = bytearray()
    for number in range(1, count + 1):
        page = frames.get(number, database[(number - 1) * PAGE : number * PAGE])
        plain.extend(key.decrypt(page, number))
    plain[18] = plain[19] = 1  # Only our in-memory copy uses rollback mode.
    db = sqlite3.connect(":memory:")
    try:
        db.deserialize(bytes(plain))
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SnapshotError("sqlite_integrity_failed")
        db.row_factory = sqlite3.Row
        return db
    except Exception:
        db.close()
        raise


def decode_field(stored, secret, version):
    """Only the observed ev=0 format is supported; other versions fail closed."""
    if version != 0:
        raise SnapshotError("unsupported_field_version")
    value = json.loads(stored)
    if not isinstance(value, str) or not secret:
        raise SnapshotError("invalid_field")
    units = value.encode("utf-16le", errors="surrogatepass")
    chars = [v ^ secret[i % len(secret)] for i, (v,) in enumerate(struct.iter_unpack("<H", units))]
    decoded = struct.pack("<" + "H" * len(chars), *chars).decode("utf-16le")
    return json.loads(decoded)
