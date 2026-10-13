import hashlib
import hmac
import json
import sqlite3
import struct

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from zalo_desktop.codec import (
    PAGE,
    PageKey,
    SnapshotError,
    checksum,
    committed_frames,
    decode_field,
    open_snapshot,
)
from zalo_desktop.reader import capture
from zalo_desktop.state import State


def encrypt_page(plain, key, number):
    skip = 16 if number == 1 else 0
    iv = bytes([number]) * 16
    enc = Cipher(algorithms.AES(key.key), modes.CBC(iv)).encryptor()
    body = enc.update(plain[skip : PAGE - 80]) + enc.finalize()
    hk = hashlib.pbkdf2_hmac("sha512", key.key, bytes(x ^ 0x3A for x in key.salt), 2, 32)
    mac = hmac.new(hk, body + iv + struct.pack("<I", number), "sha512").digest()
    return (key.salt if skip else b"") + body + iv + mac


def empty_page(version):
    db = sqlite3.connect(":memory:")
    db.execute(f"PRAGMA user_version={version}")
    page = bytearray(db.serialize())
    db.close()
    assert len(page) == PAGE
    page[20] = 80
    page[105:107] = struct.pack(">H", PAGE - 80)
    return bytes(page)


def wal_bytes(frames):
    header = struct.pack(">6I", 0x377F0682, 3007000, PAGE, 0, 11, 22)
    state = checksum(header, "<")
    wal = header + struct.pack(">II", *state)
    for number, size, data in frames:
        prefix = struct.pack(">II", number, size)
        state = checksum(data, "<", checksum(prefix, "<", state))
        wal += prefix + header[16:24] + struct.pack(">II", *state) + data
    return wal


def test_committed_wal_overrides_main_and_uncommitted_tail_is_ignored():
    key = PageKey(b"k" * 32, b"s" * 16)
    main = encrypt_page(empty_page(1), key, 1)
    new = encrypt_page(empty_page(42), key, 1)
    uncommitted = encrypt_page(empty_page(99), key, 1)
    wal = wal_bytes([(1, 1, new), (1, 0, uncommitted)])
    db = open_snapshot(main, wal, key)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 42
    assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    with pytest.raises(sqlite3.OperationalError):
        db.execute("CREATE TABLE forbidden(x)")
    db.close()


def test_wal_torn_tail_uses_prior_commit():
    page = bytes(PAGE)
    wal = wal_bytes([(1, 1, page), (1, 0, page)])
    assert committed_frames(wal[:-100])[1] == 1


@pytest.mark.parametrize("offset", [8, 28, 48, 60])
def test_wal_corruption_rejected(offset):
    wal = bytearray(wal_bytes([(1, 1, bytes(PAGE))]))
    wal[offset] ^= 1
    with pytest.raises(SnapshotError):
        committed_frames(bytes(wal))


def test_page_mac_rejects_wrong_key_or_corruption():
    key = PageKey(b"k" * 32, b"s" * 16)
    data = encrypt_page(empty_page(1), key, 1)
    with pytest.raises(SnapshotError):
        PageKey(b"x" * 32, key.salt).decrypt(data, 1)
    damaged = bytearray(data)
    damaged[40] ^= 1
    with pytest.raises(SnapshotError):
        key.decrypt(bytes(damaged), 1)


def encode_field(value, secret):
    text = json.dumps(value, ensure_ascii=False)
    units = struct.unpack("<" + "H" * (len(text.encode("utf-16le")) // 2), text.encode("utf-16le"))
    encrypted = [v ^ secret[i % len(secret)] for i, v in enumerate(units)]
    return json.dumps(
        struct.pack("<" + "H" * len(encrypted), *encrypted).decode("utf-16le", errors="surrogatepass")
    )


def test_field_unicode_and_fail_closed_version():
    secret = b"6" * 32
    assert decode_field(encode_field("Xin chào 👋", secret), secret, 0) == "Xin chào 👋"
    with pytest.raises(SnapshotError):
        decode_field("anything", secret, 1)


def test_baseline_restart_no_history_and_durable_dedup(tmp_path):
    state = State(tmp_path / "state.db", "identity")
    assert state.initialize({"old.db": "fingerprint"}, 1000) == 1000
    old = {"thread_id": "a", "message_id": "1", "timestamp": 1.0}
    new = {"thread_id": "a", "message_id": "2", "timestamp": 1.001}
    assert state.record("old.db", "new", [old, new]) == 1
    state.db.close()
    state = State(tmp_path / "state.db", "identity")
    assert state.initialize({}, 9000) == 1000
    assert state.record("old.db", "newer", [new]) == 0
    assert len(state.pending()) == 1
    state.accepted("a", "2", "hub-key")
    assert not state.pending()
    with pytest.raises(ValueError):
        State(tmp_path / "state.db", "another-account")


def test_direction_and_media_placeholder():
    cfg = {"user_id": "self", "account": "zalo-1"}
    row = {
        "serverTime": "2000",
        "sendDttm": "2000",
        "fromUid": "0",
        "dName": "Me",
        "msgId": "1",
        "msgType": 2,
        "message": "not decoded",
        "ev": 1,
    }
    msg = capture(row, "g123", cfg, b"k")
    assert msg["direction"] == "outgoing"
    assert msg["attachments"]
    assert msg["display_name"] == "Nhóm Zalo (đang lấy tên)"


def test_old_wal_generation_is_not_replayed():
    wal = bytearray(wal_bytes([(1, 1, bytes(PAGE))]))
    wal[40] ^= 1
    assert committed_frames(bytes(wal)) == ({}, None)


def test_offline_hub_does_not_block_local_capture():
    from zalo_desktop.reader import Reader

    reader = Reader.__new__(Reader)
    reader.cfg = {}
    reader.errors = {}
    reader.secret = b"test-only"
    calls = []
    reader.read_changed = lambda: calls.append("capture")

    def unavailable():
        calls.append("flush")
        raise TimeoutError()

    reader.flush = unavailable
    reader.status = lambda phase: calls.append(phase)
    reader.tick()
    reader.tick()
    assert calls == ["capture", "flush", "waiting", "capture", "flush", "waiting"]
    assert reader.errors["hub"] == "TimeoutError"


def test_lazy_metadata_pages_wal_and_readonly(tmp_path):
    import apsw

    from zalo_desktop.groups import Pages, ReadVFS

    secret = b"test-only-secret"
    key = PageKey.derive(secret, b"s" * 16)
    path = tmp_path / "Index.db"
    raw = encrypt_page(empty_page(1), key, 1)
    wal = wal_bytes(
        [(1, 1, encrypt_page(empty_page(42), key, 1)), (1, 0, encrypt_page(empty_page(99), key, 1))]
    )
    path.write_bytes(raw)
    path.with_name("Index.db-wal").write_bytes(wal)
    pages = Pages(path, secret)
    vfs = ReadVFS(pages)
    try:
        db = apsw.Connection(
            "file:metadata?immutable=1", flags=apsw.SQLITE_OPEN_READONLY | apsw.SQLITE_OPEN_URI, vfs=vfs.name
        )
        assert list(db.execute("PRAGMA user_version")) == [(42,)]
        with pytest.raises(apsw.ReadOnlyError):
            db.execute("CREATE TABLE forbidden(x)")
        db.close()
        assert path.read_bytes() == raw
        assert path.with_name("Index.db-wal").read_bytes() == wal
    finally:
        vfs.unregister()
        pages.file.close()
