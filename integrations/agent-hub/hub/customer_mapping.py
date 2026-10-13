"""Explicit account/group ID -> ERP customer UUID bindings, independent of display names."""

import json
import time


class CustomerMappings:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS customer_mappings (
                    account TEXT NOT NULL, thread_id TEXT NOT NULL, customer_id TEXT NOT NULL,
                    customer_name TEXT NOT NULL, version INTEGER NOT NULL, updated REAL NOT NULL,
                    PRIMARY KEY(account,thread_id));
                CREATE TABLE IF NOT EXISTS customer_mapping_audit (
                    id INTEGER PRIMARY KEY, account TEXT NOT NULL, thread_id TEXT NOT NULL,
                    previous TEXT, current TEXT NOT NULL, created REAL NOT NULL);
            """)

    def get(self, account, thread_id):
        with self.store.db() as db:
            row = db.execute(
                "SELECT * FROM customer_mappings WHERE account=? AND thread_id=?", (account, thread_id)
            ).fetchone()
        return dict(row) if row else None

    def set(self, account, thread_id, customer_id, customer_name, expected_version):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM threads WHERE account=? AND thread_id=?", (account, thread_id)
            ).fetchone():
                raise ValueError("Nhóm chưa được bộ đọc xác nhận")
            old = db.execute(
                "SELECT * FROM customer_mappings WHERE account=? AND thread_id=?", (account, thread_id)
            ).fetchone()
            version = old["version"] if old else 0
            if version != expected_version:
                raise ValueError("Ánh xạ đã thay đổi; tải lại trước khi lưu")
            current = dict(
                account=account,
                thread_id=thread_id,
                customer_id=str(customer_id),
                customer_name=customer_name,
                version=version + 1,
                updated=time.time(),
            )
            db.execute(
                "INSERT OR REPLACE INTO customer_mappings VALUES(?,?,?,?,?,?)", tuple(current.values())
            )
            db.execute(
                "INSERT INTO customer_mapping_audit(account,thread_id,previous,current,created) VALUES(?,?,?,?,?)",
                (
                    account,
                    thread_id,
                    json.dumps(dict(old)) if old else None,
                    json.dumps(current, ensure_ascii=False),
                    current["updated"],
                ),
            )
        return current

    def list(self):
        with self.store.db() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT t.account,t.thread_id,t.display_name,t.conversation,m.customer_id,m.customer_name,"
                    "COALESCE(m.version,0) AS version FROM threads t LEFT JOIN customer_mappings m "
                    "ON m.account=t.account AND m.thread_id=t.thread_id ORDER BY t.display_name"
                )
            ]
