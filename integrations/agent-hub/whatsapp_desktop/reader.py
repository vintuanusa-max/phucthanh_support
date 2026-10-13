"""New-only WhatsApp Windows capture. No sending, historical replay or order activation."""
import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

import httpx

from .source import load, convert

class SessionBindingRequired(ValueError):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--include-test', action='store_true')
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    home = Path(cfg['state_dir']); home.mkdir(parents=True, exist_ok=True)
    import msvcrt
    lock = (home / 'reader.lock').open('a+b'); lock.seek(0)
    if not lock.read(1): lock.write(b'0'); lock.flush()
    lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    db = sqlite3.connect(home / 'reader.sqlite3')
    db.executescript("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,payload TEXT,state TEXT DEFAULT 'queued');")
    db.execute('CREATE TABLE IF NOT EXISTS media_failures(id TEXT PRIMARY KEY, attempts INTEGER NOT NULL)')
    with db:
        db.execute("INSERT OR IGNORE INTO meta VALUES('cutoff',?)", (str(time.time()),))
    cutoff = float(db.execute("SELECT value FROM meta WHERE key='cutoff'").fetchone()[0])
    from zalo_desktop.vault import Vault
    from .media import enrich
    vault = Vault(home / 'vault', cfg['archive']['root']) if cfg.get('archive') else None
    with httpx.Client(base_url=cfg['hub_url'], headers={'Authorization':'Bearer '+cfg['ingest_token']}, trust_env=False, timeout=20) as client:
        from types import SimpleNamespace
        from zalo_desktop.order_sync import synchronize
        sync = SimpleNamespace(cfg={**cfg,'order_policy_file':cfg['policy_file']},http=client)
        while not (home / 'stop.flag').exists():
            status = {'pid':os.getpid(), 'cutoff':cutoff, 'updated_at':time.time(), 'mode':'capture_only', 'errors':[]}
            try:
                from .native import session_identity
                identity=session_identity()
                pinned=db.execute("SELECT value FROM meta WHERE key='session_identity'").fetchone()
                if not pinned or pinned[0]!=identity:
                    raise SessionBindingRequired('WhatsApp session requires explicit binding')
                policy = json.loads(Path(cfg['policy_file']).read_text(encoding='utf-8-sig'))
                synchronize(sync)
                groups, contacts, metadata, bodies = load()
                if session_identity()!=identity:raise ValueError('WhatsApp session changed during snapshot')
                status['groups'] = len(groups)
                (home / 'groups.json').write_text(json.dumps(groups, ensure_ascii=False, indent=2), encoding='utf-8')
                for meta in metadata:
                    test = args.include_test and meta.get('t') == 1791881743 and str(meta.get('id','')).startswith('true_120363425914147734@g.us_')
                    if float(meta.get('t') or 0) < cutoff and not test: continue
                    if isinstance(meta.get('id'),str) and db.execute('SELECT 1 FROM outbox WHERE id=?',(meta['id'],)).fetchone(): continue
                    message = convert(meta, groups, contacts, bodies, cfg['account'], policy)
                    if not message: continue
                    if vault and meta.get('type') in ('image','document'):
                        try:
                            enrich(message, meta, vault)
                        except Exception as exc:
                            status['errors'].append('media:'+type(exc).__name__)
                            with db:
                                db.execute('INSERT INTO media_failures VALUES(?,1) ON CONFLICT(id) DO UPDATE SET attempts=attempts+1',(message['message_id'],))
                            attempts=db.execute('SELECT attempts FROM media_failures WHERE id=?',(message['message_id'],)).fetchone()[0]
                            if attempts < 3: continue
                            message['text'] += '\n[CẦN NHÂN VIÊN: chưa tải/kiểm chứng được đính kèm WhatsApp]'
                            message['attachments']=['whatsapp-desktop:media-unavailable']
                    if test and message['text'] != 'KIEM TRA WHATSAPP CHATWOOT': raise ValueError('Test mismatch')
                    with db:
                        db.execute('INSERT OR IGNORE INTO outbox(id,payload) VALUES(?,?)',(message['message_id'],json.dumps(message,ensure_ascii=False)))
                from hub.order_policy import capture_allowed
                for mid, encoded in db.execute("SELECT id,payload FROM outbox WHERE state='queued'").fetchall():
                    m=json.loads(encoded)
                    if not capture_allowed(policy,'whatsapp',m['thread_id'],groups.get(m['thread_id'],m['display_name'])):
                        with db:db.execute("UPDATE outbox SET state='ignored_policy' WHERE id=?",(mid,))
                        continue
                    r=client.post('/ingest',json=m);r.raise_for_status();assert r.json().get('stored') is True
                    with db:db.execute("UPDATE outbox SET state='accepted' WHERE id=?",(mid,))
                from .print_sync import synchronize as synchronize_print
                synchronize_print(sync)
                status['counts']=dict(db.execute('SELECT state,count(*) FROM outbox GROUP BY state'))
            except Exception as exc:
                status['errors']=[type(exc).__name__]  # Never persist raw source values or keys.
            status['phase']='running' if not status['errors'] else 'waiting'
            (home/'status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
            if args.once: print(json.dumps(status)); break
            args.include_test=False
            time.sleep(15)
    db.close();lock.close()


if __name__ == '__main__':
    main()
