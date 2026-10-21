"""Explicit customer file-view requests, separate from AI reply/order policies."""
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path


def view_request(text):
    value = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    if re.search(r"\b(khong|dung|chua|ko)\s+(can\s+)?(gui|mo|xem)\b(?!\s+(duoc|dc))", value):
        return False
    return bool(re.search(
        r"\b(file|pdf|\.ai)\b.*\b(in gi|xem|mo|khong mo|ko mo)|"
        r"\b(mo|xem)\s+(giup|gium|ho)\b.*\b(file|pdf)\b|"
        r"\b(khong|ko)\s+mo\s+(duoc|dc)\b", value))


def pdf_assets(message):
    return [a for a in message.get("assets", []) if a.get("state") == "ready"
            and Path(a.get("name", "")).suffix.lower() in (".pdf", ".ai")]


class FilePreviews:
    def __init__(self, engine):
        self.e = engine
        with engine.store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS file_preview_meta (id INTEGER PRIMARY KEY, enabled REAL)")
            db.execute("INSERT OR IGNORE INTO file_preview_meta VALUES(1,?)", (time.time(),))
            db.execute("""CREATE TABLE IF NOT EXISTS file_previews (
                id TEXT PRIMARY KEY, account TEXT, thread_id TEXT, conversation INTEGER,
                state TEXT, payload TEXT, result TEXT, created REAL)""")

    def permitted(self, message):
        from hub.order_policy import eligible, allowed
        from hub.quality_monitor import monitored
        cfg = self.e.settings.inboxes.get(message["account"], {})
        policy = self.e.order_intake.policy(message["account"])
        return bool(policy and cfg.get("capture_enabled") is True
                    and eligible(policy, cfg.get("channel"), message)
                    and allowed(policy, cfg.get("channel"), message["display_name"], "receive_messages")
                    and not monitored(message["account"], message["thread_id"]))

    def scan(self, account):
        now = time.time()
        with self.e.store.db() as db:
            cutoff = db.execute("SELECT enabled FROM file_preview_meta WHERE id=1").fetchone()[0]
            rows = db.execute(
                "SELECT id,payload FROM captures WHERE account=? ORDER BY rowid DESC LIMIT 500",
                (account,)).fetchall()
            abandoned = [dict(r) for r in db.execute(
                "SELECT * FROM file_previews WHERE account=? AND state='claimed' AND created<?",
                (account, now-900))]
        for abandoned_job in abandoned:
            self.finish(account, abandoned_job["id"], {"state": "uncertain", "detail": "Worker interrupted; manual reconciliation required"})
        for row in reversed(rows):
            message = json.loads(row["payload"])
            if not cutoff <= message["timestamp"] <= now-60 or not view_request(message.get("text", "")):
                continue
            identity = hashlib.sha256(("file-preview:"+account+":"+message["thread_id"]+":"+message["message_id"]).encode()).hexdigest()
            with self.e.store.db() as db:
                if db.execute("SELECT 1 FROM file_previews WHERE id=?", (identity,)).fetchone():
                    continue
            if not self.permitted(message):
                continue
            mapping = self.e.store.thread(account=account, thread_id=message["thread_id"])
            if not mapping:
                continue
            quote = message.get("quoted_image") or {}
            source = [message] if pdf_assets(message) else []
            if not source:
                for candidate in rows:
                    prior = json.loads(candidate["payload"])
                    if prior["thread_id"] != message["thread_id"] or prior.get("recalled") or prior.get("revision"):
                        continue
                    if quote.get("message_id"):
                        match = prior["message_id"] == quote["message_id"]
                    else:
                        match = (bool(message.get("sender_id")) and prior.get("sender_id") == message["sender_id"]
                                 and message["timestamp"]-600 <= prior["timestamp"] <= message["timestamp"]+60)
                    if match and pdf_assets(prior):
                        source.append(prior)
            assets = {a["sha256"]: a for m in source for a in pdf_assets(m)}
            state = "queued" if len(assets) == 1 else "review"
            if self.e.settings.inboxes[account].get("channel") not in ("zalo", "whatsapp"):
                state = "review"
            payload = {"request": message, "sources": source, "asset": next(iter(assets.values()), None)}
            with self.e.store.db() as db:
                db.execute("INSERT OR IGNORE INTO file_previews VALUES(?,?,?,?,?,?,?,?)",
                           (identity, account, message["thread_id"], mapping["conversation"], state,
                            json.dumps(payload, ensure_ascii=False), "{}", now))
            if state == "review":
                self.review(identity, mapping["conversation"],
                            "Khách yêu cầu xem file: chưa xác định duy nhất PDF/AI hoặc kênh chưa hỗ trợ gửi ảnh. Cần nhân viên kiểm tra.")

    def review(self, identity, conversation, text):
        self.e.effect(identity+":open", conversation, "status", {"status": "open"}, apply_capture=True)
        self.e.note(identity+":review", conversation, text, apply_capture=True)

    def claim(self, account):
        with self.e.lock:
            self.scan(account)
            with self.e.store.db() as db:
                row = db.execute("SELECT * FROM file_previews WHERE account=? AND state='queued' ORDER BY created LIMIT 1",
                                 (account,)).fetchone()
                if not row:
                    return None
                job = dict(row)
                payload = json.loads(job["payload"])
                invalid = False
                # Source revisions/recalls invalidate the delivery, including after queue creation.
                for original in [payload["request"], *payload["sources"]]:
                    latest = db.execute(
                        "SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1",
                        (account, job["thread_id"], original["message_id"])).fetchone()
                    current = json.loads(latest[0]) if latest else {}
                    if current.get("recalled") or current.get("revision") or not current:
                        invalid = True
                        break
                if not self.permitted(payload["request"]):
                    invalid = True
                # Never reclaim: an interrupted delivery requires manual reconciliation.
                db.execute("UPDATE file_previews SET state=? WHERE id=? AND state='queued'",
                           ("review" if invalid else "claimed", job["id"]))
            if invalid:
                self.review(job["id"], job["conversation"],
                            "Chưa gửi bản xem: tin/file nguồn hoặc chính sách nhóm đã thay đổi. Cần nhân viên đối chiếu.")
                return None
            return {"id": job["id"], "account": account, "thread_id": job["thread_id"],
                    "request_id": payload["request"]["message_id"], "asset": payload["asset"],
                    "purpose": "customer_file_preview"}

    def finish(self, account, identity, result):
        with self.e.lock:
            with self.e.store.db() as db:
                row = db.execute("SELECT * FROM file_previews WHERE id=? AND account=?", (identity, account)).fetchone()
                if not row or row["state"] != "claimed":
                    return
                state = result.get("state")
                if state not in ("confirmed", "submitted", "blocked", "uncertain"):
                    raise ValueError("Invalid preview delivery result")
                safe = {k: result.get(k, "") for k in ("state", "message_id", "directory", "detail")}
                db.execute("UPDATE file_previews SET state=?,result=? WHERE id=?",
                           (state, json.dumps(safe, ensure_ascii=False), identity))
            text = ("ĐÃ GỬI BẢN XEM FILE" if state == "confirmed" else
                    "ĐÃ CHUYỂN BẢN XEM CHO ỨNG DỤNG; chưa xác nhận giao" if state == "submitted" else
                    "CẦN NHÂN VIÊN: Chưa xác nhận gửi bản xem file; không tự gửi lại để tránh trùng")
            text += "\nYêu cầu: " + json.loads(row["payload"])["request"]["message_id"]
            text += "\nKho bản xem: " + safe["directory"] + "\n" + safe["detail"]
            if state in ("blocked", "uncertain"):
                self.review(identity, row["conversation"], text)
            else:
                self.e.note(identity+":result", row["conversation"], text, apply_capture=True)
