import base64
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from hub.media import decode_image


def event_key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                  state TEXT NOT NULL DEFAULT 'queued', detail TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS ownership (
                  conversation INTEGER PRIMARY KEY, owner TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS threads (
                  account TEXT NOT NULL, thread_id TEXT NOT NULL, display_name TEXT NOT NULL,
                  conversation INTEGER UNIQUE NOT NULL, contact INTEGER NOT NULL,
                  erp_group TEXT, PRIMARY KEY(account, thread_id));
                CREATE TABLE IF NOT EXISTS captures (
                  id TEXT PRIMARY KEY, account TEXT NOT NULL, thread_id TEXT NOT NULL,
                  message_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                  UNIQUE(account,thread_id,message_id,revision));
                CREATE TABLE IF NOT EXISTS effects (
                  id TEXT PRIMARY KEY, conversation INTEGER NOT NULL, kind TEXT NOT NULL,
                  payload TEXT NOT NULL, state TEXT NOT NULL, response TEXT);
                CREATE TABLE IF NOT EXISTS deliveries (
                  id TEXT PRIMARY KEY, account TEXT NOT NULL, thread_id TEXT NOT NULL,
                  conversation INTEGER NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
                  detail TEXT NOT NULL DEFAULT '', platform_id TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS drafts (
                  id TEXT PRIMARY KEY, conversation INTEGER NOT NULL, payload TEXT NOT NULL,
                  state TEXT NOT NULL DEFAULT 'draft', result TEXT);
                CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state,created);
                CREATE TABLE IF NOT EXISTS media (
                  id TEXT PRIMARY KEY, capture_id TEXT NOT NULL, mime_type TEXT NOT NULL, data BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS order_sources (
                  conversation INTEGER NOT NULL,message_id INTEGER NOT NULL,draft_id TEXT NOT NULL,
                  PRIMARY KEY(conversation,message_id));
            """)
            if "client_id" not in {r[1] for r in db.execute("PRAGMA table_info(deliveries)")}:
                db.execute("ALTER TABLE deliveries ADD COLUMN client_id TEXT NOT NULL DEFAULT ''")
            if "claimed_at" not in {r[1] for r in db.execute("PRAGMA table_info(deliveries)")}:
                db.execute("ALTER TABLE deliveries ADD COLUMN claimed_at REAL NOT NULL DEFAULT 0")
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS delivery_client ON deliveries(account,thread_id,client_id) "
                "WHERE client_id<>''"
            )

    def reconcile_echo(self, message):
        if message.get("direction") != "outgoing" or not message.get("client_message_id"):
            return False
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM deliveries WHERE account=? AND thread_id=? AND client_id=?",
                (message["account"], message["thread_id"], message["client_message_id"]),
            ).fetchone()
            if not row or json.loads(row["payload"]).get("content") != message["text"]:
                return False
            db.execute(
                "UPDATE deliveries SET state='confirmed',platform_id=?,detail='Zalo Desktop echo verified' WHERE id=?",
                (message["message_id"], row["id"]),
            )
            return True

    def expire_deliveries(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,conversation FROM deliveries WHERE state IN ('sending','submitted') "
                "AND claimed_at>0 AND claimed_at<?",
                (time.time() - 120,),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE deliveries SET state='uncertain',detail='Echo timeout; do not resend' WHERE id=?",
                    (row["id"],),
                )
                db.execute(
                    "INSERT OR IGNORE INTO jobs(id,kind,payload,created) VALUES(?,'notice',?,?)",
                    (
                        row["id"] + ":timeout",
                        json.dumps(
                            {
                                "conversation": row["conversation"],
                                "text": "Chưa xác minh tin trên Zalo sau 2 phút. Kiểm tra nhóm trước khi gửi lại.",
                            }
                        ),
                        time.time(),
                    ),
                )

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def enqueue(self, key, kind, payload):
        with self.db() as db:
            return bool(
                db.execute(
                    "INSERT OR IGNORE INTO jobs(id,kind,payload,created) VALUES(?,?,?,?)",
                    (key, kind, json.dumps(payload, ensure_ascii=False), time.time()),
                ).rowcount
            )

    def capture(self, message):
        data = message.model_dump()
        key = event_key(message.account, message.thread_id, message.message_id, message.revision)
        media = [(decode_image(i), i["mime_type"]) for i in data.pop("images", [])]
        data["images"] = [event_key(key, hashlib.sha256(raw).hexdigest()) for raw, _ in media]
        encoded = json.dumps(data, ensure_ascii=False)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload FROM captures WHERE id=?", (key,)).fetchone()
            if existing and any(
                json.loads(existing[0]).get(field, [] if field in {"images", "assets"} else None)
                != data.get(field)
                for field in ("text", "attachments", "direction", "recalled", "images", "assets", "quoted_image")
            ):
                raise ValueError("Same capture ID/revision with different payload")
            for media_id, (raw, mime) in zip(data["images"], media, strict=True):
                db.execute("INSERT OR IGNORE INTO media VALUES(?,?,?,?)", (media_id, key, mime, raw))
            db.execute(
                "INSERT OR IGNORE INTO captures VALUES(?,?,?,?,?,?)",
                (key, message.account, message.thread_id, message.message_id, message.revision, encoded),
            )
            db.execute(
                "INSERT OR IGNORE INTO jobs(id,kind,payload,created) VALUES(?,?,?,?)",
                (key, "capture", encoded, time.time()),
            )
        return key

    def images(self, ids):
        with self.db() as db:
            result = []
            for media_id in ids:
                row = db.execute("SELECT mime_type,data FROM media WHERE id=?", (media_id,)).fetchone()
                if not row:
                    raise ValueError("Missing captured image")
                result.append({"mime_type": row[0], "data": base64.b64encode(row[1]).decode("ascii")})
            return result

    def recover(self):
        with self.db() as db:
            db.execute(
                "UPDATE jobs SET state='uncertain',detail='Interrupted; reconcile before retry' WHERE state='processing'"
            )
            db.execute("UPDATE effects SET state='uncertain' WHERE state='sending'")
            db.execute(
                "UPDATE deliveries SET state='uncertain',detail='Worker interrupted' WHERE state='sending'"
            )
            db.execute("UPDATE drafts SET state='uncertain' WHERE state='sending'")

    def claim(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE state='queued' ORDER BY created,rowid LIMIT 1"
            ).fetchone()
            if row:
                db.execute("UPDATE jobs SET state='processing' WHERE id=?", (row["id"],))
                return dict(row)

    def finish(self, key, state, detail=""):
        with self.db() as db:
            db.execute("UPDATE jobs SET state=?,detail=? WHERE id=?", (state, detail, key))

    def ownership(self, conversation):
        with self.db() as db:
            row = db.execute(
                "SELECT owner,generation FROM ownership WHERE conversation=?", (conversation,)
            ).fetchone()
            return tuple(row) if row else ("ai", 0)

    def set_owner(self, conversation, owner):
        with self.db() as db:
            db.execute(
                """INSERT INTO ownership VALUES(?,?,1) ON CONFLICT(conversation)
                DO UPDATE SET owner=excluded.owner,generation=generation+1""",
                (conversation, owner),
            )

    def bind(self, account, thread_id, name, conversation, contact):
        with self.db() as db:
            db.execute(
                """INSERT INTO threads(account,thread_id,display_name,conversation,contact)
                VALUES(?,?,?,?,?) ON CONFLICT(account,thread_id) DO UPDATE SET
                display_name=excluded.display_name""",
                (account, thread_id, name, conversation, contact),
            )

    def thread(self, conversation=None, account=None, thread_id=None):
        with self.db() as db:
            if conversation is not None:
                row = db.execute("SELECT * FROM threads WHERE conversation=?", (conversation,)).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM threads WHERE account=? AND thread_id=?", (account, thread_id)
                ).fetchone()
            return dict(row) if row else None

    def status(self):
        with self.db() as db:
            result = {}
            for table in ("jobs", "effects", "deliveries", "drafts"):
                result[table] = {
                    row[0]: row[1] for row in db.execute(f"SELECT state,count(*) FROM {table} GROUP BY state")
                }
            result["captures"] = db.execute("SELECT count(*) FROM captures").fetchone()[0]
            return result

    def recent(self, table):
        if table not in {"effects", "drafts", "jobs", "deliveries", "intake_runs"}:
            raise ValueError("Invalid table")
        with self.db() as db:
            return [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 100")]
