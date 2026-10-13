"""Durable ERP transport; importing this module never starts GUI/network work."""
import base64
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import unicodedata

import requests


def normalized(value):
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def exact_group(expected, actual):
    return normalized(expected) == normalized(actual)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS intake (
                  id TEXT PRIMARY KEY, group_name TEXT NOT NULL, image BLOB NOT NULL,
                  target_text TEXT NOT NULL, payload TEXT, state TEXT NOT NULL DEFAULT 'captured',
                  detail TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
                  next_try REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS delivery (
                  id TEXT PRIMARY KEY, group_name TEXT NOT NULL, message TEXT NOT NULL,
                  state TEXT NOT NULL DEFAULT 'queued', detail TEXT NOT NULL DEFAULT '',
                  reported INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS groups (name TEXT PRIMARY KEY, reported INTEGER NOT NULL DEFAULT 0);
            """)
            columns = {r["name"] for r in db.execute("PRAGMA table_info(intake)")}
            if "source" not in columns:
                db.execute("ALTER TABLE intake ADD COLUMN source TEXT NOT NULL DEFAULT 'zalo'")
            # A crash after/before Enter cannot be distinguished. Never replay it automatically.
            db.execute("UPDATE delivery SET state='uncertain',detail='Bot dừng khi đang gửi; cần kiểm tra Zalo',reported=0 WHERE state='sending'")
            db.execute("UPDATE delivery SET state='queued' WHERE state IN ('dispatched','processing')")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def capture(self, group, source_id, image_path, target_text, source="zalo"):
        if source not in ("zalo", "whatsapp") or not group.strip():
            raise ValueError("Nguồn hoặc tên chat không hợp lệ")
        if not source_id:
            raise ValueError("Thiếu định danh tin nhắn Zalo")
        if source == "zalo" and ("-" not in group or not group.partition("-")[0].strip()):
            raise ValueError("Nhóm chưa đúng dạng Tên khách - ...")
        image = Path(image_path).read_bytes()
        if len(image) > 5 * 1024 * 1024:
            raise ValueError("Ảnh chụp lớn hơn 5MB")
        identity = normalized(group) + "\0" + source_id if source == "zalo" else "whatsapp\0" + source_id
        key = hashlib.sha256(identity.encode()).hexdigest()
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO intake(id,group_name,image,target_text,source) VALUES (?,?,?,?,?)",
                       (key, group.strip(), image, target_text, source))
            if source == "zalo":
                db.execute("INSERT OR IGNORE INTO groups(name) VALUES (?)", (group.strip(),))
        return key

    def ingest(self, event):
        with self.db() as db:
            old = db.execute("SELECT * FROM delivery WHERE id=?", (event["id"],)).fetchone()
            if old and (old["group_name"] != event["group_name"] or old["message"] != event["message"]):
                raise ValueError("Nội dung sự kiện ERP thay đổi")
            db.execute("INSERT OR IGNORE INTO delivery(id,group_name,message) VALUES (?,?,?)",
                       (event["id"], event["group_name"], event["message"]))

    def claim(self, event_id):
        with self.db() as db:
            return db.execute("UPDATE delivery SET state='processing' WHERE id=? AND state='dispatched'",
                              (event_id,)).rowcount == 1

    def mark(self, event_id, state, detail=""):
        if not event_id:
            return
        with self.db() as db:
            db.execute("UPDATE delivery SET state=?,detail=?,reported=0 WHERE id=?", (state, detail[:500], event_id))

    def fail(self, event_id):
        if not event_id:
            return
        with self.db() as db:
            db.execute("""UPDATE delivery SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'failed' END,
                detail='Không xác nhận được thao tác gửi; cần kiểm tra',reported=0
                WHERE id=? AND state NOT IN ('submitted','blocked')""", (event_id,))


class Bridge:
    def __init__(self, root, send_queue, allowed, analyze, source_allowed=None):
        self.root = Path(root)
        lock_path = self.root / "data" / "erp_integration" / "bridge.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = open(lock_path, "a+b")
        if lock_path.stat().st_size == 0:
            self._lock.write(b"0")
            self._lock.flush()
        self._lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock.close()
            raise RuntimeError("Đã có tiến trình kết nối ERP trên máy này")
        self.store = Store(self.root / "data" / "erp_integration" / "bridge.sqlite3")
        self.send_queue, self.allowed, self.analyze = send_queue, allowed, analyze
        self.source_allowed = source_allowed
        self.session = requests.Session()
        self.session.trust_env = False

    def close(self):
        self.session.close()
        self._lock.close()

    def settings(self):
        path = self.root / "erp_config.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def request(self, method, path, payload=None):
        cfg = self.settings()
        url = cfg.get("erp_url", "").rstrip("/")
        if not cfg.get("enabled") or len(cfg.get("token", "")) < 32 or not url.startswith(("http://", "https://")):
            raise ValueError("Chưa cấu hình kết nối ERP")
        response = self.session.request(method, url + "/api/v1/integrations/zalo" + path,
            json=payload, headers={"X-Zalo-Token": cfg["token"]}, timeout=(5, 30), allow_redirects=False)
        if response.status_code >= 400:
            # Only expected validation detail is shown to the admin; never headers/config/HTML.
            detail = ""
            if response.status_code in (400,409,413,422):
                try:
                    value = response.json().get("detail")
                    if isinstance(value, str):
                        detail = value[:400]
                except ValueError:
                    pass
            raise TransportError(response.status_code, detail)
        if not 200 <= response.status_code < 300:
            raise TransportError(response.status_code)
        return response.json()

    def capture(self, group, source_id, image_path, target_text, source="zalo"):
        # Persist BEFORE scan history is saved; disabled transport keeps intake for later.
        return self.store.capture(group, source_id, image_path, target_text, source)

    def observe(self, group):
        if "-" in group:
            with self.store.db() as db:
                db.execute("INSERT OR IGNORE INTO groups(name) VALUES (?)", (group.strip(),))

    def process_intake(self):
        with self.store.db() as db:
            row = db.execute("SELECT * FROM intake WHERE state IN ('captured','ready') AND next_try<=? ORDER BY rowid LIMIT 1", (time.time(),)).fetchone()
        if not row:
            return
        permitted = (self.source_allowed(row["source"], row["group_name"], "auto_order")
                     if self.source_allowed else row["source"] == "zalo" and self.allowed(row["group_name"], "auto_order"))
        if not permitted:
            with self.store.db() as db:
                db.execute("UPDATE intake SET next_try=?,detail='Đang tắt tự lên đơn' WHERE id=?", (time.time()+60,row["id"]))
            return
        try:
            if row["source"] == "whatsapp":
                capabilities = self.request("GET", "/health")
                if "whatsapp" not in capabilities.get("intake_sources", []):
                    raise TransportError(503, "ERP cần khởi động lại để nhận đơn WhatsApp")
            payload = json.loads(row["payload"]) if row["payload"] else None
            if payload is None:
                image_path = self.store.path.parent / (row["id"] + ".png")
                image_path.write_bytes(row["image"])
                try:
                    extracted = self.analyze(str(image_path), row["target_text"])
                finally:
                    image_path.unlink(missing_ok=True)
                if not isinstance(extracted, list) or not extracted:
                    raise ValueError("Không trích xuất được đơn hàng")
                lines = []
                for item in extracted:
                    due = (item.get("ngay_giao_hang") or "").strip()
                    if due:
                        due = datetime.strptime(due, "%d/%m/%Y").date().isoformat()
                    lines.append({"ma_san_pham": item.get("ma_san_pham"), "ten_mau": item.get("ma_san_pham"), "so_luong": item.get("so_luong"),
                                  "ghi_chu_mau_do": item.get("ghi_chu_mau_do") or "", "ngay_giao_hang": due or None})
                payload = {"request_id": row["id"], "group_name": row["group_name"], "orders": lines,
                           "image_base64": base64.b64encode(row["image"]).decode()}
                if row["source"] == "whatsapp":
                    payload["source"] = "whatsapp"
                # Freeze extracted payload BEFORE network attempt. A lost response must resend identical bytes.
                with self.store.db() as db:
                    db.execute("UPDATE intake SET payload=?,state='ready' WHERE id=?", (json.dumps(payload,ensure_ascii=False), row["id"]))
            response = self.request("POST", "/orders", payload)
            if response.get("status") != "created" or not response.get("orders"):
                raise ValueError("ERP chưa xác nhận tạo đơn")
            with self.store.db() as db:
                db.execute("UPDATE intake SET state='created',detail=? WHERE id=?",
                           (json.dumps(response,ensure_ascii=False),row["id"]))
        except Exception as exc:
            permanent = isinstance(exc, ValueError) or isinstance(exc, TransportError) and exc.status in (400,409,413,422)
            with self.store.db() as db:
                db.execute("UPDATE intake SET state=CASE WHEN ? THEN 'failed' ELSE state END,attempts=attempts+1,next_try=?,detail=? WHERE id=?",
                           (permanent, time.time()+min(300, 10*2**min(row["attempts"],5)),
                            (getattr(exc,"detail","") or f"{type(exc).__name__}: cần kiểm tra cấu hình/khách/mã hàng")[:500],row["id"]))

    def pump_deliveries(self):
        response = self.request("GET", "/outbox")
        for event in response["items"]:
            self.store.ingest(event)
        with self.store.db() as db:
            rows = db.execute("SELECT * FROM delivery WHERE state='queued' ORDER BY rowid LIMIT 50").fetchall()
            for row in rows:
                db.execute("UPDATE delivery SET state='dispatched' WHERE id=?", (row["id"],))
        for row in rows:
            self.send_queue.put({"customer_name": row["group_name"], "message": row["message"], "erp_event_id": row["id"]})
        with self.store.db() as db:
            reports = db.execute("SELECT * FROM delivery WHERE reported=0 AND state IN ('submitted','failed','blocked','uncertain') LIMIT 50").fetchall()
        for row in reports:
            self.request("POST", f"/outbox/{row['id']}/result", {"state": row["state"], "detail": row["detail"]})
            with self.store.db() as db:
                db.execute("UPDATE delivery SET reported=1 WHERE id=? AND state=?", (row["id"],row["state"]))

    def run_once(self):
        if not self.settings().get("enabled"):
            return
        self.pump_deliveries()
        self.process_intake()
        with self.store.db() as db:
            names = db.execute("SELECT name FROM groups WHERE reported=0 LIMIT 10").fetchall()
        for row in names:
            try:
                self.request("POST", "/groups/observe", {"group_name": row["name"]})
            except TransportError as exc:
                if exc.status not in (409,422):
                    raise
                continue
            with self.store.db() as db:
                db.execute("UPDATE groups SET reported=1 WHERE name=?", (row["name"],))

    def start(self):
        def loop():
            last_log = 0
            while True:
                try:
                    self.run_once()
                except Exception as exc:
                    if time.time()-last_log > 60:
                        print(f"[ERP bridge] {type(exc).__name__}; hàng đợi giữ nguyên để thử lại")
                        last_log = time.time()
                time.sleep(5)
        threading.Thread(target=loop, name="erp-zalo-bridge", daemon=True).start()


class TransportError(Exception):
    def __init__(self, status, detail=""):
        self.status = status
        self.detail = detail
        super().__init__(f"ERP HTTP {status}")
