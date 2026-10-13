import base64
import json
import sqlite3
from io import BytesIO

import pytest
from PIL import Image
from test_trial_images import PNG

from hub.evidence_document import erp_evidence_png, render_document, save_document, select_sources


def message(identity="1", text="Đặt MET số lượng 5 — dùng ảnh vừa gửi"):
    return {
        "account": "z",
        "thread_id": "g123",
        "message_id": identity,
        "display_name": "Gia đình thử",
        "sender": "Nguyễn Văn Ánh",
        "direction": "incoming",
        "text": text,
        "timestamp": 1791858987.711,
        "images": [],
        "assets": [],
    }


def test_unicode_source_preserved_and_png_with_image(tmp_path):
    messages = [
        message(),
        {
            **message("2", "[Ảnh Zalo lưu trong kho NAS]"),
            "images": [{"mime_type": "image/png", "data": base64.b64encode(PNG).decode()}],
        },
    ]
    result = save_document(messages, "DH-TEST", tmp_path)
    from pathlib import Path

    root = Path(result["directory"])
    record = json.loads((root / "source.json").read_text(encoding="utf-8"))
    assert record["messages"][0]["text"] == messages[0]["text"]
    assert record["kind"] == "message_compilation_not_screenshot"
    assert record["messages"][1]["image_hashes"]
    with Image.open(root / "page-001.png") as image:
        assert image.format == "PNG" and image.width == 1400
    assert save_document(messages, "DH-TEST", tmp_path) == result
    (root / "page-001.png").write_bytes(b"modified")
    with pytest.raises(ValueError):
        save_document(messages, "DH-TEST", tmp_path)


def test_long_text_paginates_without_truncating():
    text = "Nội dung nguyên văn có dấu tiếng Việt\n" * 90
    _, manifest, pages = render_document([message(text=text)], "DH-TEST")
    assert len(pages) >= 2 and manifest["messages"][0]["text"] == text
    assert all(len(page) < 5_000_000 and Image.open(BytesIO(page)).format == "PNG" for page in pages)


def test_all_pages_preserved_for_erp_and_tamper_rejected(tmp_path):
    from pathlib import Path
    doc = save_document([message(text='Nội dung\n' * 90)], 'MULTI', tmp_path)
    raw = erp_evidence_png(doc)
    assert len(doc['pages']) > 1
    with Image.open(BytesIO(raw)) as img:
        assert img.size == (1400, 1980 * len(doc['pages']))
    assert erp_evidence_png(doc) == raw
    (Path(doc['directory']) / doc['pages'][0]['name']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        erp_evidence_png(doc)


def test_reject_mixed_group_and_recalled():
    with pytest.raises(ValueError):
        render_document([message(), {**message("2"), "thread_id": "g456"}], "DH-TEST")
    with pytest.raises(ValueError):
        render_document([{**message(), "recalled": True}], "DH-TEST")


def test_selection_binds_image_and_group():
    db = sqlite3.connect(":memory:")
    db.executescript(
        "CREATE TABLE captures(id,account,thread_id,message_id,revision,payload); CREATE TABLE media(id,capture_id,mime_type,data);"
    )
    payload = {**message(), "images": ["im1"]}
    db.execute("INSERT INTO captures VALUES(?,?,?,?,?,?)", ("cap", "z", "g123", "1", 0, json.dumps(payload)))
    db.execute("INSERT INTO media VALUES(?,?,?,?)", ("im1", "other-capture", "image/png", PNG))
    with pytest.raises(ValueError):
        select_sources(db, "z", "g123", ["1"])
    with pytest.raises(ValueError):
        select_sources(db, "z", "other-group", ["1"])
    db.execute("UPDATE media SET capture_id='cap'")
    assert select_sources(db, "z", "g123", ["1"])[0]["images"][0]["data"] == base64.b64encode(PNG).decode()
