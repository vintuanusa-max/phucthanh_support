import json
import socket
import time
from pathlib import Path

import pytest
from test_trial_images import PNG

from zalo_desktop.downloads import download_url, validate_public_url
from zalo_desktop.vault import Vault, safe_name


def test_nas_image_keeps_original_and_message_identity(tmp_path, monkeypatch):
    vault = Vault(tmp_path / "local", tmp_path / "nas")
    calls = []

    def fake_download(url, destination):
        calls.append(url)
        Path(destination).write_bytes(PNG)
        return {"name": "test.png", "mime": "image/png", "bytes": len(PNG)}

    monkeypatch.setattr("zalo_desktop.vault.download", fake_download)
    original = dict(
        account="zalo",
        thread_id="g123",
        message_id="123",
        display_name="Nhóm thử",
        sender="Khách",
        direction="incoming",
        timestamp=time.time(),
        text="Ảnh đặt hàng",
        attachments=[],
        images=[],
        _asset_requests=[{"kind": "image", "url": "https://files.example/test.png", "name": ""}],
    )
    first = json.loads(json.dumps(original))
    vault.enqueue(first)
    assert vault.enrich(json.loads(json.dumps(first))) is None
    assert vault.tick()
    enriched = vault.enrich(first)
    asset = enriched["assets"][0]
    assert asset["state"] == "ready"
    assert (vault.root / asset["relative_path"]).read_bytes() == PNG
    manifest = json.loads(
        (vault.root / (asset["relative_path"] + ".source.json")).read_text(encoding="utf-8")
    )
    assert manifest["message_id"] == "123" and manifest["sender"] == "Khách"
    assert enriched["images"][0]["mime_type"] == "image/png"
    second = json.loads(json.dumps(original))
    vault.enqueue(second)
    assert not vault.tick() and len(calls) == 1
    assert len(list((tmp_path / "nas").rglob("*.png"))) == 1
    vault.release(enriched)
    assert not list((tmp_path / "local").glob("*.download"))
    assert (vault.root / asset["relative_path"]).exists()


def test_nas_failure_keeps_spool_and_retries_without_redownload(tmp_path, monkeypatch):
    vault = Vault(tmp_path / "local", tmp_path / "nas")
    count = []

    def fake_download(url, path):
        count.append(1)
        path.write_bytes(b"PDF test")
        return {"name": "test.pdf", "mime": "application/pdf", "bytes": 8}

    monkeypatch.setattr("zalo_desktop.vault.download", fake_download)
    msg = dict(
        account="z",
        thread_id="g1",
        message_id="1",
        display_name="Trial",
        sender="",
        direction="incoming",
        timestamp=time.time(),
        text="",
        attachments=[],
        _asset_requests=[{"kind": "file", "url": "https://example/test", "name": "test.pdf"}],
    )
    vault.enqueue(msg)
    monkeypatch.setattr("zalo_desktop.vault.shutil.copyfile", lambda *a: (_ for _ in ()).throw(OSError()))
    vault.tick()
    assert list(vault.home.glob("*.download"))
    assert vault.enrich(msg) is None
    with vault.db() as db:
        db.execute("UPDATE assets SET next_try=0")
    vault.tick()
    assert len(count) == 1


def test_group_identity_and_safe_paths(tmp_path):
    vault = Vault(tmp_path / "local", tmp_path / "nas")
    a = vault.folder({"account": "z", "thread_id": "g1", "display_name": "Nhóm"})
    b = vault.folder({"account": "z", "thread_id": "g2", "display_name": "Nhóm"})
    assert a != b
    assert vault.folder({"account": "z", "thread_id": "g1", "display_name": "Đã đổi tên"}) == a
    assert "/" not in safe_name("../../evil.exe") and "\\" not in safe_name("a\\b")
    assert safe_name("CON.txt").startswith("_")


def test_private_download_destinations_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError):
        validate_public_url("https://example.com/file")
    with pytest.raises(ValueError):
        validate_public_url("file:///c:/secret")
    assert "drive.usercontent.google.com/download?" in download_url(
        "https://drive.google.com/file/d/abc123456789/view"
    )
    with pytest.raises(ValueError):
        download_url("https://drive.google.com/drive/folders/abc123456789")


def test_public_backend_pins_validated_ip(monkeypatch):
    from httpcore import SyncBackend

    from zalo_desktop.downloads import PublicBackend

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    )
    seen = []
    monkeypatch.setattr(SyncBackend, "connect_tcp", lambda self, host, *a: seen.append(host) or object())
    PublicBackend().connect_tcp("files.example", 443)
    assert seen == ["8.8.8.8"]


def test_undefined_cdn_filename_uses_url_name():
    import httpx

    from zalo_desktop.downloads import filename_from_response

    response = httpx.Response(200, headers={"content-disposition": 'attachment; filename="undefined"'})
    assert filename_from_response(response, "https://photo-stal-1.zadn.vn/path/test.jpg") == "test.jpg"
