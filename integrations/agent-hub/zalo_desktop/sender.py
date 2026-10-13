"""Durable, at-most-once staff sender. Uses the existing Desktop runtime only."""

import argparse
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx
import psutil

from .reader import load_config


class Journal:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,result TEXT,reported INTEGER DEFAULT 0)"
        )
        self.db.commit()

    def reserve(self, key):
        with self.db:
            return (
                self.db.execute(
                    "INSERT OR IGNORE INTO attempts(id,result) VALUES(?,?)",
                    (key, json.dumps({"state": "uncertain", "detail": "Sender interrupted; do not resend"})),
                ).rowcount
                == 1
            )

    def result(self, key, result):
        with self.db:
            self.db.execute("UPDATE attempts SET result=? WHERE id=?", (json.dumps(result), key))

    def pending(self):
        return self.db.execute("SELECT id,result FROM attempts WHERE reported=0").fetchall()

    def reported(self, key):
        with self.db:
            self.db.execute("UPDATE attempts SET reported=1 WHERE id=?", (key,))


class Sender:
    def __init__(self, cfg):
        self.cfg = cfg
        self.home = Path(cfg["state_dir"]) / "sender"
        self.home.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(self.home / "sender.sqlite3")
        self.http = httpx.Client(
            base_url=cfg["hub_url"],
            timeout=15,
            trust_env=False,
            headers={"Authorization": "Bearer " + cfg["ingest_token"]},
        )
        self.base = f"/adapters/{cfg['account']}"
        self.halted = (self.home / "halt.flag").exists()

    def transport(self, item, action, client_id=""):
        candidates = []
        for process in psutil.process_iter(["pid", "exe", "cmdline"]):
            if (process.info["exe"] or "").lower() != self.cfg["zalo_exe"].lower():
                continue
            if not any(a.startswith("--type=") for a in process.info["cmdline"] or []):
                candidates.append(process.pid)
        if len(candidates) != 1:
            return {"state": "blocked", "detail": "Zalo Desktop chưa mở hoặc không đúng phiên"}
        request = {
            "action": action,
            "pid": candidates[0],
            "zalo_exe": self.cfg["zalo_exe"],
            "user_id": self.cfg["user_id"],
            "thread_id": item["thread_id"],
            "display_name": item["display_name"],
            "text": item["message"]["content"],
            "client_id": client_id,
        }
        try:
            completed = subprocess.run(
                [self.cfg["node_exe"], str(Path(__file__).with_name("desktop_transport.cjs"))],
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=45,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            result = json.loads(completed.stdout)
            if result.get("cleanup") is not True:
                self.halted = True
                (self.home / "halt.flag").write_text("Inspector cleanup needs verification", encoding="utf-8")
            return result
        except Exception:
            self.halted = True
            (self.home / "halt.flag").write_text(
                "Transport interrupted; inspect before restart", encoding="utf-8"
            )
            return {"state": "uncertain", "detail": "Đầu gửi gián đoạn; không tự gửi lại"}

    def report(self):
        for key, encoded in self.journal.pending():
            response = self.http.post(self.base + "/results/" + key, json=json.loads(encoded))
            response.raise_for_status()
            self.journal.reported(key)

    def dispatch(self, item):
        key = item["id"]
        if not self.journal.reserve(key):
            return
        try:
            result = self.transport(item, "prepare")
            if result.get("state") == "ready" and not self.halted:
                cid = result["client_id"]
                prepared = self.http.post(self.base + "/prepare/" + key, json={"client_id": cid})
                prepared.raise_for_status()
                # Journal already contains uncertain before the only external send attempt.
                result = self.transport(item, "send", cid)
            elif result.get("state") == "ready":
                result = {"state": "blocked", "detail": "Chẩn đoán chưa đóng sạch; không gửi"}
            if result.get("state") not in {"submitted", "confirmed", "blocked", "failed", "uncertain"}:
                result = {"state": "uncertain", "detail": "Kết quả đầu gửi không hợp lệ"}
            self.journal.result(
                key, {k: result[k] for k in ("state", "platform_message_id", "detail") if k in result}
            )
        except Exception:
            self.journal.result(
                key, {"state": "uncertain", "detail": "Chưa xác minh được kết quả; không gửi lại"}
            )

    def tick(self):
        self.report()
        if self.halted:
            return
        response = self.http.post(self.base + "/claim")
        if response.status_code == 409:
            return
        response.raise_for_status()
        item = response.json().get("item")
        if item:
            self.dispatch(item)
            self.report()

    def status(self, error=""):
        tmp = self.home / "status.tmp"
        tmp.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "updated_at": time.time(),
                    "phase": "halted" if self.halted else ("waiting" if error else "running"),
                    "error": error,
                    "pending_results": len(self.journal.pending()),
                }
            ),
            encoding="utf-8",
        )
        tmp.replace(self.home / "status.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    sender = Sender(load_config(args.config))
    import msvcrt

    with (sender.home / "sender.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            while not (sender.home / "stop.flag").exists():
                error = ""
                try:
                    sender.tick()
                except Exception as exc:
                    error = type(exc).__name__
                sender.status(error)
                if args.once:
                    return
                time.sleep(3)
        finally:
            sender.http.close()
            sender.journal.db.close()


if __name__ == "__main__":
    main()
