"""Local durable download queue -> NAS originals + manifest + analysis previews."""

import hashlib
import json
import re
import shutil
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .downloads import download
from .media import normalize_image


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", unicodedata.normalize("NFC", value)).strip(" .")[:120]
    if not value or value.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    }:
        value = "_" + (value or "file")
    return value


class Vault:
    def __init__(self, home, root):
        self.home, self.root = Path(home), Path(root)
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / "vault.sqlite3"
        self.stop = threading.Event()
        with self.db() as db:
            db.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS groups (id TEXT PRIMARY KEY, folder TEXT NOT NULL UNIQUE);
              CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,payload TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'queued',
                result TEXT NOT NULL DEFAULT '{}',error TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL DEFAULT 0);
              UPDATE assets SET state='queued' WHERE state='working';
            """)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=20)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def counts(self):
        with self.db() as db:
            return dict(db.execute("SELECT state,count(*) FROM assets GROUP BY state"))

    def enqueue(self, message):
        requests = message.pop("_asset_requests", [])
        if not requests:
            return
        message["assets"] = []
        for index, item in enumerate(requests):
            key = hashlib.sha256(
                json.dumps([message["account"], message["thread_id"], message["message_id"], index]).encode()
            ).hexdigest()
            payload = {
                **item,
                **({'quoted_image': message['quoted_image']} if message.get('quoted_image') else {}),
                **{
                    k: message[k]
                    for k in (
                        "account",
                        "thread_id",
                        "message_id",
                        "display_name",
                        "sender",
                        "direction",
                        "timestamp",
                        "text",
                    )
                },
            }
            with self.db() as db:
                db.execute(
                    "INSERT OR IGNORE INTO assets(id,payload) VALUES(?,?)",
                    (key, json.dumps(payload, ensure_ascii=False)),
                )
            message["assets"].append(
                {
                    "id": key,
                    "name": safe_name(item.get("name") or "file"),
                    "kind": item["kind"],
                    "state": "pending",
                }
            )

    def release(self, message):
        for asset in message.get("assets", []):
            if asset["state"] != "ready" or not re.fullmatch("[a-f0-9]{64}", asset["id"]):
                continue
            for suffix in (".download", ".download.json", ".preview.json"):
                (self.home / (asset["id"] + suffix)).unlink(missing_ok=True)

    def enrich(self, message):
        if not message.get("assets"):
            return message
        assets, images = [], []
        for asset in message["assets"]:
            with self.db() as db:
                row = db.execute(
                    "SELECT state,result,error FROM assets WHERE id=?", (asset["id"],)
                ).fetchone()
            if not row or row[0] in ("queued", "working"):
                return None
            result = json.loads(row[1])
            assets.append({**asset, "state": row[0], **result, "error": row[2]})
            preview_path = self.home / (asset["id"] + ".preview.json")
            if row[0] == "ready" and (asset["kind"] == "image" or preview_path.exists()):
                try:
                    image = json.loads(
                        (self.home / (asset["id"] + ".preview.json")).read_text(encoding="utf-8")
                    )
                    images.append(image)
                except (OSError, ValueError):
                    message["attachments"].append("vault:preview-unavailable")
            elif row[0] != "ready":
                message["attachments"].append("vault:download-failed")
        message["assets"], message["images"] = assets, images[:1]
        return message

    def folder(self, payload):
        identity = payload["account"] + ":" + payload["thread_id"]
        with self.db() as db:
            old = db.execute("SELECT folder FROM groups WHERE id=?", (identity,)).fetchone()
            if old:
                return old[0]
            name = safe_name(payload["display_name"])
            if name.casefold() in {r[0].casefold() for r in db.execute("SELECT folder FROM groups")}:
                name += "__" + hashlib.sha256(identity.encode()).hexdigest()[:8]
            db.execute("INSERT INTO groups VALUES(?,?)", (identity, name))
            return name

    def process(self, key, payload):
        from .drive import archive_folder, folder_id

        if folder_id(payload["url"]):
            return archive_folder(self, key, payload)
        local = self.home / (key + ".download")
        info_path = self.home / (key + ".download.json")
        if local.exists() and info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))
        else:
            part = self.home / (key + ".part")
            info = download(payload["url"], part)
            part.replace(local)
            info_path.write_text(json.dumps(info), encoding="utf-8")
        name = safe_name(payload.get("name") or info["name"])
        if (
            payload["kind"] == "image"
            or info["mime"].startswith("image/")
            or Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".jxl"}
        ):
            try:
                if local.stat().st_size > 4 * 1024 * 1024:
                    raise ValueError("Image preview limit")
                preview = normalize_image(local.read_bytes())
                (self.home / (key + ".preview.json")).write_text(json.dumps(preview), encoding="utf-8")
            except Exception:
                pass  # Archive the original even when AI preview cannot be generated.
        with local.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        month = datetime.fromtimestamp(payload["timestamp"]).strftime("%Y-%m")
        relative = Path(self.folder(payload)) / month / "originals" / (key[:12] + "__" + name)
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary = destination.with_name(destination.name + ".part")
            shutil.copyfile(local, temporary)
            temporary.replace(destination)
        with destination.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise OSError("NAS hash mismatch")
        result = {
            "name": name,
            "relative_path": relative.as_posix(),
            "sha256": digest,
            "size": info["bytes"],
            "mime_type": info["mime"],
        }
        manifest = destination.with_name(destination.name + ".source.json")
        manifest_tmp = manifest.with_name(manifest.name + ".part")
        manifest_tmp.write_text(
            json.dumps({**payload, **result, "asset_id": key}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest_tmp.replace(manifest)
        return result

    def tick(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id,payload,attempts FROM assets WHERE state='queued' AND next_try<=? ORDER BY rowid LIMIT 1",
                (time.time(),),
            ).fetchone()
            if not row:
                return False
            db.execute("UPDATE assets SET state='working' WHERE id=?", (row[0],))
        try:
            payload = json.loads(row[1])
            if hasattr(self, "capture_filter") and not self.capture_filter(payload):
                with self.db() as db:
                    db.execute("UPDATE assets SET state='ignored_policy' WHERE id=?", (row[0],))
                return True
            result = self.process(row[0], payload)
            with self.db() as db:
                db.execute(
                    "UPDATE assets SET state='ready',result=?,error='' WHERE id=?",
                    (json.dumps(result, ensure_ascii=False), row[0]),
                )
        except Exception as exc:
            # NAS/network failures retry in this independent queue; no raw signed URL in errors.
            transient = isinstance(exc, (OSError, TimeoutError)) or type(exc).__module__.startswith("httpx")
            state = "queued" if transient and row[2] < 3 else "failed"
            with self.db() as db:
                db.execute(
                    "UPDATE assets SET state=?,error=?,attempts=attempts+1,next_try=? WHERE id=?",
                    (state, type(exc).__name__, time.time() + 30, row[0]),
                )
        return True

    def run(self):
        while not self.stop.is_set():
            try:
                if not self.tick():
                    self.stop.wait(2)
            except Exception:
                self.stop.wait(5)
