"""Persistent new-only cursor and idempotent local outbox, separate from Zalo data."""

import json
import sqlite3
import time
from pathlib import Path


class State:
    def __init__(self, path, identity):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,fingerprint TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS outbox(thread TEXT,msg TEXT,payload TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'queued',hub_id TEXT,PRIMARY KEY(thread,msg));
        """)
        self.identity = identity
        old = self.get("identity")
        if old and old != identity:
            raise ValueError("State belongs to another account or source")

    def get(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    @property
    def cutoff(self):
        value = self.get("cutoff_ms")
        if value is None:
            raise ValueError("Initialize new-only baseline before starting")
        return int(value)

    def initialize(self, fingerprints, now_ms=None):
        if self.get("cutoff_ms") is not None:
            return self.cutoff
        cutoff = now_ms if now_ms is not None else int(time.time() * 1000)
        with self.db:
            self.db.execute("INSERT INTO meta VALUES(?,?)", ("identity", self.identity))
            self.db.execute("INSERT INTO meta VALUES(?,?)", ("cutoff_ms", str(cutoff)))
            self.db.executemany("INSERT INTO files VALUES(?,?)", fingerprints.items())
        return cutoff

    def unchanged(self, path, fingerprint):
        old = self.db.execute("SELECT fingerprint FROM files WHERE path=?", (path,)).fetchone()
        return old and old[0] == fingerprint

    def record(self, path, fingerprint, captures):
        added = 0
        with self.db:
            for msg in captures:
                if msg["timestamp"] * 1000 <= self.cutoff:
                    continue
                added += self.db.execute(
                    "INSERT OR IGNORE INTO outbox(thread,msg,payload) VALUES(?,?,?)",
                    (msg["thread_id"], msg["message_id"], json.dumps(msg, ensure_ascii=False)),
                ).rowcount
            self.db.execute(
                "INSERT INTO files VALUES(?,?) ON CONFLICT(path) DO UPDATE "
                "SET fingerprint=excluded.fingerprint",
                (path, fingerprint),
            )
        return added

    def pending(self):
        return self.db.execute(
            "SELECT thread,msg,payload FROM outbox WHERE state='queued' ORDER BY rowid LIMIT 50"
        ).fetchall()

    def accepted(self, thread, message, hub_id):
        with self.db:
            self.db.execute(
                "UPDATE outbox SET state='accepted',hub_id=? WHERE thread=? AND msg=?",
                (hub_id, thread, message),
            )

    def counts(self):
        return dict(self.db.execute("SELECT state,count(*) FROM outbox GROUP BY state"))
