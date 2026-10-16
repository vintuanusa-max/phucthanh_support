"""Durable at-most-once invocation gate; ambiguous attempts are never retried."""
import hashlib
import json
import sqlite3
import time


class SendLedger:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS attempts (
            delivery TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
            state TEXT NOT NULL, platform_id TEXT, updated REAL NOT NULL)''')
        self.db.commit()

    def reserve(self, delivery, account, thread, text):
        """Commit BEFORE entering the native transport, including after restart."""
        if not all(isinstance(x, str) and x for x in (delivery, account, thread, text)):
            raise ValueError('Missing delivery identity')
        digest = hashlib.sha256(json.dumps(
            [account, thread, text], ensure_ascii=False, separators=(',', ':')
        ).encode()).hexdigest()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old = self.db.execute('SELECT fingerprint FROM attempts WHERE delivery=?', (delivery,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('Delivery identity reused with different payload')
                return False
            self.db.execute('INSERT INTO attempts VALUES(?,?,?,NULL,?)',
                            (delivery, digest, 'uncertain', time.time()))
        return True

    def confirm(self, delivery, platform_id):
        """Only call after independently matching the outgoing source event."""
        if not platform_id:
            raise ValueError('Source event required')
        with self.db:
            row = self.db.execute('SELECT platform_id FROM attempts WHERE delivery=?', (delivery,)).fetchone()
            if row is None or (row[0] and row[0] != str(platform_id)):
                raise ValueError('Unknown or conflicting confirmation')
            self.db.execute("UPDATE attempts SET state='confirmed',platform_id=?,updated=? WHERE delivery=?",
                            (str(platform_id), time.time(), delivery))

    def close(self):
        self.db.close()
