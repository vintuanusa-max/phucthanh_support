"""Future-only explicit preview replies with a durable one-attempt send journal."""
import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "vendor"))
from document_preview import render_asset, contact_sheet


def sync_preview(client, cfg):
    prefix = "/adapters/" + cfg["account"] + "/file-previews"
    response = client.post(prefix + "/claim")
    response.raise_for_status()
    job = response.json().get("job")
    if not job:
        return "preview_idle"
    journal_dir = ROOT / "preview-journal"
    journal_dir.mkdir(exist_ok=True)
    journal = journal_dir / (job["id"] + ".json")
    result = {"state": "blocked", "detail": ""}
    try:
        with journal.open("x", encoding="utf-8") as f:
            json.dump({"state": "claimed", "thread_id": job["thread_id"]}, f)
    except FileExistsError:
        result = {"state": "uncertain", "detail": "Existing send journal; no automatic retry"}
        client.post(prefix+"/"+job["id"], json=result).raise_for_status()
        return "preview_duplicate_blocked"
    sending = False
    try:
        pages = render_asset(cfg["archive"]["root"], job["asset"])
        png = contact_sheet(pages)
        source = (Path(cfg["archive"]["root"]) / job["asset"]["relative_path"]).resolve()
        dest = source.parent.parent / "previews" / (job["asset"]["sha256"][:20]+"-v1")
        dest.mkdir(parents=True, exist_ok=True)
        for i, image in enumerate(pages, 1):
            path = dest / f"page-{i:03}.jpg"
            content = base64.b64decode(image["data"])
            if path.exists() and path.read_bytes() != content:
                raise ValueError("Existing preview differs")
            path.write_bytes(content)
        (dest / "all-pages.png").write_bytes(png)
        result["directory"] = str(dest)
        payload = {**job, "image_base64": base64.b64encode(png).decode(),
                   "caption": f"Ảnh xem nội dung file {job['asset']['name']} ({len(pages)} trang). Đây là bản xem, chưa phải file in đã xử lý."}
        if job["account"] == "zalo-personal-1":
            from preview_transport import transport
            if transport(payload, prepare=True).get("state") != "ready":
                raise ValueError("Zalo Desktop chưa sẵn sàng gửi ảnh")
            sending = True
            journal.write_text(json.dumps({"state":"sending","thread_id":job["thread_id"]}), encoding="utf-8")
            sent = transport(payload)
        elif job["account"] == "whatsapp-personal-1":
            wa = Path.home() / "AppData/Local/PhucThanh/WhatsAppDesktopReader/code"
            sys.path.insert(0, str(wa))
            from whatsapp_desktop.print_sync import whatsapp_ready
            if not whatsapp_ready():
                raise ValueError("WhatsApp Desktop chưa sẵn sàng gửi ảnh")
            import sqlite3
            from whatsapp_desktop.native import session_identity
            with sqlite3.connect("file:"+str(Path(cfg["state_dir"])/"reader.sqlite3")+"?mode=ro", uri=True) as db:
                binding = db.execute("SELECT value FROM meta WHERE key='session_identity'").fetchone()
            if not binding or session_identity() != binding[0]:
                raise ValueError("WhatsApp session changed; explicit binding required")
            sending = True
            journal.write_text(json.dumps({"state":"sending","thread_id":job["thread_id"]}), encoding="utf-8")
            proc = subprocess.run([r"C:\Program Files\nodejs\node.exe", str(ROOT/"send_preview.mjs")],
                input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True,
                timeout=65, creationflags=subprocess.CREATE_NO_WINDOW)
            if proc.returncode:
                raise ValueError("WhatsApp delivery outcome unknown")
            sent = json.loads(proc.stdout)
        else:
            raise ValueError("Kênh chưa hỗ trợ gửi preview")
        result.update(sent)
    except Exception as exc:
        result.update(state="uncertain" if sending else "blocked",
                      detail=str(exc)[:300] if isinstance(exc, ValueError) else type(exc).__name__)
    journal.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    client.post(prefix + "/" + job["id"], json=result).raise_for_status()
    return "preview_" + result["state"]
