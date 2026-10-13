import pytest

from zalo_desktop.reader import capture


@pytest.mark.parametrize("archive", [True, False])
def test_same_message_caption_and_image_preserved(monkeypatch, archive):
    caption = "BẰNG CHỨNG TEST: đặt MET số lượng 5\nDùng ảnh này"
    monkeypatch.setattr(
        "zalo_desktop.reader.decode_field",
        lambda *a: {"title": caption, "oriUrl": "https://photo-stal-1.zdn.vn/test.jpg"},
    )
    monkeypatch.setattr(
        "zalo_desktop.media.fetch_image", lambda *a: {"mime_type": "image/png", "data": "test"}
    )
    cfg = {"account": "z", "user_id": "owner", "image_threads": {"g1": {"enabled_after": 1}}}
    if archive:
        cfg["archive"] = {"threads": {"g1": {"enabled_after": 1}}}
    row = {
        "serverTime": 10000,
        "fromUid": "customer",
        "dName": "Khách",
        "msgType": 2,
        "ev": 0,
        "message": "encoded",
        "msgId": "photo1",
    }
    result = capture(row, "g1", cfg, b"unused")
    assert result["text"] == caption
    assert result.get("_asset_requests") if archive else result["images"]
    assert not result["attachments"]


def test_image_then_separate_text_remain_distinct(monkeypatch):
    monkeypatch.setattr("zalo_desktop.reader.decode_field", lambda value, *a: value)
    cfg = {"account": "z", "user_id": "owner", "archive": {"threads": {"g1": {"enabled_after": 1}}}}
    row = {
        "serverTime": 10000,
        "fromUid": "customer",
        "dName": "Khách",
        "msgType": 2,
        "ev": 0,
        "message": {"title": "", "oriUrl": "https://photo-stal-1.zdn.vn/test.jpg"},
        "msgId": "photo1",
    }
    photo = capture(row, "g1", cfg, b"unused")
    text = capture({**row, "msgType": 1, "msgId": "text2", "message": "MET x5"}, "g1", cfg, b"unused")
    assert photo["text"] == "[Ảnh Zalo lưu trong kho NAS]" and photo.get("_asset_requests")
    assert text["text"] == "MET x5" and text["message_id"] != photo["message_id"]
    assert not text.get("_asset_requests")
