import json
import time

import pytest

from zalo_desktop.drive import FolderPage, archive_folder, folder_id
from zalo_desktop.vault import Vault


def test_folder_url_and_html():
    assert folder_id("https://drive.google.com/drive/folders/abcdefghijk") == "abcdefghijk"
    assert folder_id("https://evil.test/drive/folders/abcdefghijk") is None
    page = FolderPage()
    page.feed(
        '<title>Test folder</title><a href="https://drive.google.com/file/d/abcdefghijk/view"><b>File</b>.pdf</a>'
    )
    assert page.title == "Test folder" and page.links[0][1] == "File.pdf"


def test_snapshot_nested_files_resume_and_source(tmp_path, monkeypatch):
    vault = Vault(tmp_path / "local", tmp_path / "nas")
    root_url = "https://drive.google.com/drive/folders/rootabcdefgh"
    child_url = "https://drive.google.com/drive/folders/childabcdefgh"

    def listing(url):
        if url == root_url:
            return "Folder", [{"id": "childabcdefgh", "url": child_url, "name": "../sub", "folder": True}]
        return "Child", [
            {
                "id": "fileabcdefgh",
                "url": "https://drive.google.com/file/d/fileabcdefgh/view",
                "name": "test.pdf",
                "folder": False,
            }
        ]

    calls = []

    def fetch(url, path, **kwargs):
        calls.append(url)
        path.write_bytes(b"%PDF test")
        return {"name": "test.pdf", "mime": "application/pdf", "bytes": 9}

    monkeypatch.setattr("zalo_desktop.drive.list_folder", listing)
    monkeypatch.setattr("zalo_desktop.drive.download", fetch)
    payload = {
        "account": "z",
        "thread_id": "g1",
        "display_name": "Trial",
        "timestamp": time.time(),
        "url": root_url,
        "message_id": "100",
    }
    result = archive_folder(vault, "a" * 64, payload)
    index = vault.root / result["relative_path"]
    data = json.loads(index.read_text())
    assert data["complete"] and len(data["files"]) == 1 and data["message_id"] == "100"
    assert (index.parent / data["files"][0]["path"]).read_bytes() == b"%PDF test"
    assert archive_folder(vault, "a" * 64, payload)["sha256"] == result["sha256"]
    assert len(calls) == 1


def test_failed_child_does_not_claim_complete(tmp_path, monkeypatch):
    vault = Vault(tmp_path / "local", tmp_path / "nas")
    monkeypatch.setattr(
        "zalo_desktop.drive.list_folder",
        lambda url: (
            "Folder",
            [
                {
                    "id": "fileabcdefgh",
                    "url": "https://drive.google.com/file/d/fileabcdefgh/view",
                    "name": "test.pdf",
                    "folder": False,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "zalo_desktop.drive.download", lambda *a, **k: (_ for _ in ()).throw(ValueError("No access"))
    )
    payload = {
        "account": "z",
        "thread_id": "g1",
        "display_name": "Trial",
        "timestamp": time.time(),
        "url": "https://drive.google.com/drive/folders/rootabcdefgh",
    }
    with pytest.raises(ValueError):
        archive_folder(vault, "b" * 64, payload)
    assert not list(vault.root.rglob("_snapshot.json"))
