"""Windows Zalo Desktop -> Agent Hub. Never sends back to Zalo."""

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .codec import PageKey, SnapshotError, decode_field, fingerprint, open_snapshot, snapshot
from .state import State


def capture(row, thread, cfg, secret, db=None):
    stamp = int(row["serverTime"] or row["sendDttm"] or 0)
    if stamp <= 0:
        raise SnapshotError("missing_message_timestamp")
    outgoing = str(row["fromUid"]) in ("0", cfg["user_id"])
    group = thread.startswith("g")
    sender = (row["dName"] or "").strip()
    name = cfg.get("thread_names", {}).get(thread)
    if not name:
        name = (
            ("Nhóm Zalo (đang lấy tên)")
            if group
            else (sender if sender and not outgoing else "Zalo " + thread)
        )
    attachments = []
    images = []
    assets = []
    archive = cfg.get("archive", {})
    archive_scope = archive.get("threads", {}).get(thread)
    if not archive_scope and cfg.get("order_policy") and cfg.get("order_intake", {}).get("enabled_after"):
        from hub.order_policy import eligible

        if eligible(
            cfg["order_policy"],
            "zalo",
            {
                "thread_id": thread,
                "display_name": name,
                "sender": sender,
                "direction": "outgoing" if outgoing else "incoming",
                "origin": "customer",
            },
        ):
            archive_scope = cfg["order_intake"]
    archive_active = bool(archive_scope and stamp / 1000 >= archive_scope["enabled_after"])
    if row["msgType"] == 1 and row["ev"] == 0:
        text = decode_field(row["message"], secret, row["ev"])
        if not isinstance(text, str):
            raise SnapshotError("nontext_message")
        if archive_active:
            assets = [
                {"kind": "link", "url": url.rstrip(".,;!?)]}"), "name": ""}
                for url in dict.fromkeys(re.findall(r'https://[^\s<>"\x00-\x1f]+', text))
            ][:10]
    else:
        text = "[Tin Zalo loại " + str(row["msgType"]) + "; xem trên ứng dụng Zalo]"
        attachments = ["zalo-desktop:unsupported:" + str(row["msgType"])]
        scope = cfg.get("image_threads", {}).get(thread)
        if archive_active and row["ev"] == 0:
            try:
                metadata = decode_field(row["message"], secret, row["ev"])
                if row["msgType"] == 2:
                    assets = [{"kind": "image", "url": metadata["oriUrl"], "name": ""}]
                    caption = metadata.get("title", "")
                    text = (
                        caption
                        if isinstance(caption, str) and caption.strip()
                        else "[Ảnh Zalo lưu trong kho NAS]"
                    )
                    attachments = []
                elif isinstance(metadata, dict) and metadata.get("href", "").startswith("https://"):
                    assets = [{"kind": "file", "url": metadata["href"], "name": metadata.get("title", "")}]
                    text = "[File Zalo: " + metadata.get("title", "file") + "]"
                    attachments = []
            except (KeyError, TypeError, ValueError, SnapshotError):
                pass
        elif row["msgType"] == 2 and row["ev"] == 0 and scope and stamp / 1000 >= scope["enabled_after"]:
            caption = ""
            try:
                from .media import fetch_image

                metadata = decode_field(row["message"], secret, row["ev"])
                caption = metadata.get("title", "")
                caption = caption if isinstance(caption, str) else ""
                images = [fetch_image(metadata)]
                text = caption if caption.strip() else "[Ảnh từ Zalo]"
                attachments = []
            except Exception:
                # Never persist signed URLs or exception strings containing them.
                text = (
                    caption + "\n" if caption.strip() else ""
                ) + "[Không lấy được ảnh Zalo; nhân viên cần xem trên Zalo]"
    if len(text) > 20000:
        text = text[:19930] + "\n[Nội dung dài; xem đầy đủ trên Zalo]"
        attachments = ["zalo-desktop:long-message"]
    result = {
        "account": cfg["account"],
        "thread_id": thread,
        "message_id": str(row["msgId"]),
        "client_message_id": str(row["cliMsgId"] or "") if "cliMsgId" in row.keys() else "",
        "display_name": name[:300],
        "sender": sender[:300],
        "sender_id": str(row["fromUid"]),
        "direction": "outgoing" if outgoing else "incoming",
        "origin": "staff" if outgoing else "customer",
        "text": text,
        "attachments": attachments,
        "images": images,
        "timestamp": stamp / 1000,
        "revision": 0,
        "recalled": False,
    }
    if assets:
        result["_asset_requests"] = assets
    from .quotes import attach_quote

    attach_quote(result, row, db, secret, archive_active)
    return result


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    root = Path(cfg["message_dir"]).resolve()
    state = Path(cfg["state_dir"]).resolve()
    if root == state or root in state.parents or str(state).startswith("\\\\"):
        raise ValueError("State must be separate local storage")
    if root.name != "Message" or root.parent.name != "Core" or root.parent.parent.name != cfg["user_id"]:
        raise ValueError("Source/account mismatch")
    url = urlparse(cfg["hub_url"])
    if url.hostname not in ("localhost", "127.0.0.1") or url.scheme != "http":
        raise ValueError("This version only connects to the local hub")
    if len(cfg["ingest_token"]) < 32:
        raise ValueError("Missing ingest token")
    return cfg


class Reader:
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = Path(cfg["message_dir"])
        self.home = Path(cfg["state_dir"])
        identity = cfg["user_id"] + "|" + cfg["account"] + "|" + str(self.root.resolve())
        self.state = State(self.home / "reader.sqlite3", identity)
        self.secret = None
        self.keys = {}
        self.last_probe = 0
        self.last_names = 0
        self.names_mark = None
        self.group_names = {}
        self.errors = {}
        self.load_capture_policy()
        self.vault = None
        if cfg.get("archive", {}).get("root"):
            from .vault import Vault

            self.vault = Vault(self.home / "vault", cfg["archive"]["root"])
            self.vault.capture_filter = self.capture_allowed
            self.vault.start()
        self.http = httpx.Client(
            base_url=cfg["hub_url"],
            timeout=15,
            trust_env=False,
            headers={"Authorization": "Bearer " + cfg["ingest_token"]},
        )

    def load_capture_policy(self):
        path = self.cfg.get("order_policy_file")
        self.capture_policy = None
        self.capture_policy = json.loads(Path(path).read_text(encoding="utf-8-sig")) if path else {}

    def capture_allowed(self, message):
        from hub.order_policy import capture_allowed

        if self.capture_policy is None:
            return False
        return capture_allowed(
            self.capture_policy, "zalo", message["thread_id"],
            self.cfg.get("thread_names", {}).get(message["thread_id"], message.get("display_name", "")),
        )

    def initialize(self):
        marks = {p.name: fingerprint(p) for p in self.root.glob("*.db")}
        return self.state.initialize(marks, int(time.time() * 1000))

    def status(self, phase):
        data = {
            "phase": phase,
            "cutoff_ms": self.state.cutoff,
            "updated_at": time.time(),
            "pid": os.getpid(),
            "outbox": self.state.counts(),
            "key_in_memory": bool(self.secret),
            "group_names": len(self.group_names),
            "errors": self.errors,
            "source_mode": "read_only",
            "channel_send": False,
            "archive": self.vault.counts() if self.vault else {},
        }
        tmp = self.home / "status.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.home / "status.json")

    def refresh_names(self):
        from .groups import read_groups

        if not self.secret or time.monotonic() - self.last_names < 60:
            return
        self.last_names = time.monotonic()
        path = self.root.parent / "Index.db"
        if fingerprint(path) != self.names_mark:
            names, mark = read_groups(path, self.secret)
            self.group_names = names
            self.names_mark = mark
            self.cfg["thread_names"] = {**self.cfg.get("thread_names", {}), **names}
        response = self.http.post(
            f"/adapters/{self.cfg['account']}/thread-names", json={"names": self.group_names}
        )
        response.raise_for_status()

    def read_changed(self):
        from .memory import MemoryReader

        if not self.secret:
            if time.monotonic() - self.last_probe < 60:
                return
            self.last_probe = time.monotonic()
            self.secret = MemoryReader(self.cfg["zalo_exe"]).find_secret(self.root)
        try:
            self.refresh_names()
            self.errors.pop("group_names", None)
        except Exception as exc:
            self.errors["group_names"] = type(exc).__name__
        for path in sorted(self.root.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not self.capture_allowed({"thread_id": path.stem}):
                continue  # Do not snapshot, decrypt, enqueue or download excluded conversations.
            tag = hashlib.sha256(path.name.encode()).hexdigest()[:12]
            try:
                mark = fingerprint(path)
                if self.state.unchanged(path.name, mark):
                    continue
                raw, wal, mark = snapshot(path, self.cfg.get("max_snapshot_mb", 256) * 1048576)
                salt = raw[:16]
                if salt not in self.keys:
                    self.keys[salt] = PageKey.derive(self.secret, salt)
                db = open_snapshot(raw, wal, self.keys[salt])
                try:
                    rows = db.execute(
                        "SELECT msgId,cliMsgId,fromUid,toUid,dName,msgType,serverTime,sendDttm,message,ev,quote "
                        "FROM message WHERE CAST(COALESCE(NULLIF(serverTime,''),sendDttm) AS INTEGER)>? "
                        "ORDER BY CAST(serverTime AS INTEGER),msgId",
                        (self.state.cutoff,),
                    )
                    messages = [
                        capture(row, path.stem, self.cfg, self.secret, db)
                        for row in rows
                        if not self.state.db.execute(
                            "SELECT 1 FROM outbox WHERE thread=? AND msg=?", (path.stem, str(row["msgId"]))
                        ).fetchone()
                    ]
                finally:
                    db.close()
                if self.vault:
                    for message in messages:
                        self.vault.enqueue(message)
                self.state.record(path.name, mark, messages)
                self.errors.pop(tag, None)
            except Exception as exc:
                self.errors[tag] = str(exc) if isinstance(exc, SnapshotError) else type(exc).__name__
                # No checkpoint on errors; the next cycle retries this source.
                if isinstance(exc, SnapshotError) and str(exc) == "page_authentication_failed":
                    self.secret = None
                    self.keys.clear()
                    break

    def flush(self):
        for thread, msg, encoded in self.state.pending():
            message = json.loads(encoded)
            if not self.capture_allowed(message):
                with self.state.db:
                    self.state.db.execute(
                        "UPDATE outbox SET state='ignored_policy' WHERE thread=? AND msg=?",
                        (thread, msg),
                    )
                continue
            if self.vault:
                message = self.vault.enrich(message)
                if message is None:
                    continue
            response = self.http.post("/ingest", json=message)
            response.raise_for_status()
            result = response.json()
            if result.get("stored") is not True:
                raise ValueError("Hub did not acknowledge capture")
            self.state.accepted(thread, msg, result["id"])
            if self.vault:
                self.vault.release(message)

    def tick(self):
        self.load_capture_policy()  # Local policy failure stops both capture and flush.
        # Keep capturing locally while Hub is offline; the durable queue drains on recovery.
        try:
            from .order_sync import synchronize

            synchronize(self)
            self.errors.pop("order_sync", None)
        except Exception as exc:
            self.errors["order_sync"] = type(exc).__name__
        try:
            self.read_changed()
            self.errors.pop("source", None)
        except Exception as exc:
            self.errors["source"] = str(exc) if isinstance(exc, SnapshotError) else type(exc).__name__
        try:
            self.flush()
            self.errors.pop("hub", None)
        except Exception as exc:
            self.errors["hub"] = type(exc).__name__
        self.status("waiting" if self.errors or not self.secret else "running")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    reader = Reader(load_config(args.config))
    # A local byte lock is released by Windows automatically if the process exits.
    import msvcrt

    lock = (reader.home / "reader.lock").open("a+b")
    lock.seek(0)
    if lock.read(1) == b"":
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        if args.initialize:
            reader.initialize()
            reader.status("initialized")
            print("New-only baseline initialized; existing history excluded.")
            return
        _ = reader.state.cutoff
        while True:
            if (reader.home / "stop.flag").exists():
                reader.status("stopped")
                return
            try:
                reader.errors.pop("service", None)
                reader.tick()
            except Exception as exc:
                reader.errors["service"] = str(exc) if isinstance(exc, SnapshotError) else type(exc).__name__
                reader.status("waiting")
            if args.once:
                print(json.dumps({"outbox": reader.state.counts(), "errors": reader.errors}))
                return
            time.sleep(max(5, reader.cfg.get("poll_seconds", 10)))
    finally:
        if reader.vault:
            reader.vault.stop.set()
        lock.close()
        reader.http.close()
        reader.state.db.close()


if __name__ == "__main__":
    main()
