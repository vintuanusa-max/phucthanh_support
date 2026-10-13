"""Opt-in bridge for phucthanh_support; no browser/network work during capture.

Copy this file beside main.py and call start_if_configured() before start_all().
Configuration is loaded only from PHUCTHANH_HUB_CONFIG; absent means disabled.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

_started = False


class Relay:
    def __init__(self, config):
        self.config = config
        self.database = Path(config["database"])
        if str(self.database).startswith(("\\\\", "U:", "W:")):
            raise ValueError("Relay SQLite must be on a local disk")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS spool (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                    state TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
            """)
            db.execute(
                "UPDATE spool SET state='uncertain',detail='Process interrupted' WHERE state='sending'"
            )
        self.last_send = 0.0

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.database, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def capture(self, message):
        account = self.config["channel_accounts"].get(message.channel)
        if not account:
            return
        key = hashlib.sha256(json.dumps([account, message.chat_id, message.message_id]).encode()).hexdigest()
        payload = {
            "account": account,
            "thread_id": message.chat_id,
            "message_id": message.message_id,
            "display_name": message.chat_name,
            "sender": message.sender,
            "direction": "incoming",
            "origin": "customer",
            "text": message.text,
            "attachments": list(message.attachments),
            "timestamp": message.ts,
            "revision": 0,
            "recalled": False,
        }
        with self.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO spool(id,kind,payload,state) VALUES(?,?,?,?)",
                (key, "capture", json.dumps(payload, ensure_ascii=False), "pending"),
            )

    def request(self, path, payload):
        request = Request(
            self.config["hub_url"].rstrip("/") + path,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.config["token"],
            },
        )
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    def flush_one(self):
        with self.db() as db:
            row = db.execute(
                "SELECT id,payload FROM spool WHERE kind='capture' AND state='pending' ORDER BY rowid LIMIT 1"
            ).fetchone()
        if not row:
            return False
        try:
            self.request("/ingest", json.loads(row[1]))
        except HTTPError as exc:
            if exc.code in {400, 401, 403, 404, 409, 422}:
                with self.db() as db:
                    db.execute(
                        "UPDATE spool SET state='failed',detail=? WHERE id=?",
                        ("HTTP " + str(exc.code), row[0]),
                    )
                return True
            raise
        with self.db() as db:
            db.execute("UPDATE spool SET state='stored' WHERE id=?", (row[0],))
        return True

    def report_one(self):
        with self.db() as db:
            row = db.execute(
                "SELECT id,payload,state,detail FROM spool WHERE kind='delivery' AND state IN ('confirmed','submitted','blocked','failed','uncertain') ORDER BY rowid LIMIT 1"
            ).fetchone()
        if not row:
            return False
        payload = json.loads(row[1])
        self.request(
            "/adapters/" + payload["account"] + "/results/" + row[0],
            {
                "state": row[2],
                "detail": row[3],
                "platform_message_id": payload.get("platform_id", ""),
            },
        )
        with self.db() as db:
            db.execute("UPDATE spool SET state='reported' WHERE id=?", (row[0],))
        return True

    def send_whatsapp(self, item):
        from channels.whatsapp_wpp import _get_wa_page
        from core import runtime
        from core.policy import allowed

        thread = item["thread_id"]
        message = item["message"]
        if message.get("attachments") or not thread.endswith(("@c.us", "@g.us", "@lid")):
            return "blocked", "", "Unsupported attachment or thread identifier"
        if runtime.SYSTEM_STATUS == "PAUSED":
            return "blocked", "", "Bot paused"
        with runtime.whatsapp_lock:
            page = _get_wa_page()
            if not page:
                return "blocked", "", "WhatsApp session unavailable"
            target = page.evaluate(
                """async (id) => {
                if (typeof WPP === 'undefined' || !WPP.isReady) return null;
                const chats = await WPP.chat.list();
                const chat = chats.find(c => c.id._serialized === id);
                return chat ? {id: chat.id._serialized, name: chat.name || chat.formattedTitle || chat.id.user} : null;
            }""",
                thread,
            )
            if not target or target["id"] != thread:
                return "blocked", "", "Exact WhatsApp thread not found"
            if not allowed("whatsapp", target["name"], "receive_messages"):
                return "blocked", "", "Channel policy blocked sending"
            # Persist sending before calling. Any exception from this point is uncertain, never replayed.
            result = page.evaluate(
                """async ({id, text}) => {
                const result = await WPP.chat.sendTextMessage(id, text, {waitForAck: true});
                return {id: result.id, ack: result.ack};
            }""",
                {"id": thread, "text": message.get("content") or ""},
            )
            if not result or not result.get("id"):
                return "uncertain", "", "No platform message identifier"
            return (
                ("confirmed" if result.get("ack", 0) >= 1 else "submitted"),
                result["id"],
                "Platform ACK; not a read receipt",
            )

    def delivery_one(self):
        account = self.config["channel_accounts"].get("whatsapp")
        if not self.config.get("whatsapp_delivery_enabled") or not account:
            return False
        if time.monotonic() - self.last_send < 3:
            return False
        item = self.request("/adapters/" + account + "/claim", {})["item"]
        if not item:
            return False
        payload = dict(item, account=account)
        with self.db() as db:
            existing = db.execute("SELECT state FROM spool WHERE id=?", (item["id"],)).fetchone()
            if existing:
                return False
            db.execute(
                "INSERT INTO spool(id,kind,payload,state) VALUES(?,?,?,?)",
                (item["id"], "delivery", json.dumps(payload), "sending"),
            )
        try:
            state, platform_id, detail = self.send_whatsapp(item)
        except Exception:
            state, platform_id, detail = (
                "uncertain",
                "",
                "Browser call failed; verify channel before resending",
            )
        self.last_send = time.monotonic()
        payload["platform_id"] = platform_id
        with self.db() as db:
            db.execute(
                "UPDATE spool SET state=?,payload=?,detail=? WHERE id=?",
                (state, json.dumps(payload), detail, item["id"]),
            )
        return True

    def run(self):
        while True:
            try:
                self.flush_one()
                self.report_one()
                self.delivery_one()
            except Exception as exc:
                print("[Chatwoot relay] " + type(exc).__name__ + "; retained locally")
                time.sleep(5)
            time.sleep(1)


def start_if_configured():
    global _started
    path = os.getenv("PHUCTHANH_HUB_CONFIG")
    if not path or _started:
        return
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not config.get("enabled"):
        return
    if len(config.get("token", "")) < 32:
        raise ValueError("Hub ingest token is required")
    from core.messages import subscribe

    relay = Relay(config)
    subscribe(relay.capture)
    threading.Thread(target=relay.run, daemon=True, name="chatwoot-relay").start()
    _started = True
