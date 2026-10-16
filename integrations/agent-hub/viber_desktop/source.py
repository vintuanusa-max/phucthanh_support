"""Read encrypted snapshots using the active Desktop key, retained only in RAM."""
import os
import re
import tempfile
from pathlib import Path

from zalo_desktop.codec import snapshot
from zalo_desktop.memory import MemoryReader


class Source:
    def __init__(self, profile, chat_id, group_name):
        from .qt_readonly import QtSql
        self.qt = QtSql()
        self.profile = Path(profile).resolve()
        self.chat_id = int(chat_id)
        self.group_name = group_name
        self.key = None

    def unlock(self, path):
        def check(key):
            if not self.qt.open(path):
                raise RuntimeError('Snapshot unavailable')
            if self.qt.query("PRAGMA hexkey='" + key.decode('ascii') + "'") is None:
                return False
            return bool(self.qt.query("SELECT name FROM sqlite_master WHERE name='ChatInfo'"))
        if self.key and check(self.key):
            return
        self.key = None
        seen = set()
        reader = MemoryReader(Path(os.environ['LOCALAPPDATA'])/'Viber/Viber.exe')
        for data in reader.chunks(seconds=45):
            candidates = [m[1] for m in re.finditer(rb'(?<![0-9a-fA-F])([0-9a-fA-F]{32}|[0-9a-fA-F]{64}|[0-9a-fA-F]{128})(?![0-9a-fA-F])', data)]
            candidates.extend(m[0].replace(b'\0', b'') for m in re.finditer(rb'(?:(?:[0-9a-fA-F])\x00){32,128}', data))
            for candidate in candidates:
                if len(candidate) not in (32,64,128) or candidate in seen:
                    continue
                seen.add(candidate)
                if check(candidate):
                    self.key = candidate
                    return
        raise RuntimeError('Session key unavailable')

    def read(self, cutoff):
        raw, wal, _ = snapshot(self.profile/'viber.db', 32*1024*1024)
        with tempfile.TemporaryDirectory(prefix='pt-viber-copy-') as directory:
            path = Path(directory)/'snapshot.db'
            path.write_bytes(raw)
            if wal:
                Path(str(path)+'-wal').write_bytes(wal)
            try:
                self.unlock(path)
                group = self.qt.query(f'SELECT Name FROM ChatInfo WHERE ChatID={self.chat_id}')
                if not group or group[0][0] != self.group_name:
                    raise RuntimeError('Group binding requires review')
                rows = self.qt.query(
                    'SELECT e.EventID,e.TimeStamp,e.Direction,e.ContactID,c.Name,c.ClientName,m.Type,m.Body,m.PayloadPath '
                    'FROM Events e JOIN Messages m ON m.EventID=e.EventID LEFT JOIN Contact c ON c.ContactID=e.ContactID '
                    f'WHERE e.ChatID={self.chat_id} AND e.Type=0 AND e.TimeStamp>={int(cutoff*1000)} ORDER BY e.EventID',
                    columns=9, limit=10000)
                if rows is None:
                    raise RuntimeError('Message query failed')
                return rows
            finally:
                self.qt.close()


def convert(row, account, thread_id, group_name):
    eid, stamp, direction, sender_id, name, client_name, kind, body, path = row
    if kind not in ('1','2'):
        return None
    outgoing = direction == '1'
    sender = (name or client_name).strip('\u2068\u2069')
    return dict(account=account, thread_id=thread_id, message_id='viber:'+eid,
                display_name=group_name, sender=sender, sender_id=sender_id,
                direction='outgoing' if outgoing else 'incoming', origin='staff' if outgoing else 'customer',
                text=body, timestamp=int(stamp)/1000)
