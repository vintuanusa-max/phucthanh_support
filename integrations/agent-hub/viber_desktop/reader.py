"""New messages only; durable ingestion. No automatic ERP or public AI replies."""
import argparse
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx
from .source import Source, convert
from zalo_desktop.media import normalize_image
from zalo_desktop.vault import customer_folder, safe_name


def archive(message, source_path, cfg):
    path = Path(source_path).resolve()
    roots = [Path(p).resolve() for p in cfg['media_roots']]
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError('Media outside Viber folders')
    if path.stat().st_size > 50*1024*1024:
        raise ValueError('Media too large')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    identity = hashlib.sha256((message['account']+'\0'+message['message_id']).encode()).hexdigest()
    name = safe_name(path.name)
    relative = '/'.join([customer_folder(message['display_name']), datetime.fromtimestamp(message['timestamp']).strftime('%Y-%m'), 'originals', identity[:12]+'__'+name])
    target = Path(cfg['archive_root'])/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix+'.tmp')
        temporary.write_bytes(raw)
        temporary.replace(target)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError('Archive checksum mismatch')
    image = normalize_image(raw)
    message['images'] = [image]
    message['assets'] = [dict(id=identity, name=name, kind='image', state='ready', relative_path=relative,
                              sha256=digest, size=len(raw), mime_type=image['mime_type'])]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--once',action='store_true')
    args=parser.parse_args();cfg=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    home=Path(cfg['state_dir']);home.mkdir(parents=True,exist_ok=True)
    import msvcrt
    lock=(home/'reader.lock').open('a+b');lock.seek(0)
    if not lock.read(1):lock.write(b'0');lock.flush()
    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    db=sqlite3.connect(home/'reader.sqlite3')
    db.executescript("CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,payload TEXT,state TEXT DEFAULT 'queued');")
    source=Source(cfg['profile'],cfg['chat_id'],cfg['group_name'])
    with httpx.Client(base_url=cfg['hub_url'],headers={'Authorization':'Bearer '+cfg['ingest_token']},trust_env=False,timeout=30) as client:
        from types import SimpleNamespace
        from zalo_desktop.order_sync import synchronize
        order_sync = SimpleNamespace(cfg=cfg,http=client)
        while not (home/'stop.flag').exists():
            status={'pid':os.getpid(),'updated_at':time.time(),'mode':'capture_only','errors':[]}
            try:
                if cfg.get('order_policy_file'):
                    synchronize(order_sync)
                for row in source.read(cfg['enabled_after']):
                    message=convert(row,cfg['account'],cfg['thread_id'],cfg['group_name'])
                    if not message or db.execute('SELECT 1 FROM outbox WHERE id=?',(message['message_id'],)).fetchone():continue
                    if row[6]=='2':
                        try:archive(message,row[8],cfg)
                        except Exception as exc:
                            status['errors'].append('media:'+type(exc).__name__)
                            continue  # Retry original; never claim that missing media was archived.
                    with db:db.execute('INSERT INTO outbox(id,payload) VALUES(?,?)',(message['message_id'],json.dumps(message,ensure_ascii=False)))
                for mid,payload in db.execute("SELECT id,payload FROM outbox WHERE state='queued'").fetchall():
                    response=client.post('/ingest',content=payload.encode(),headers={'Content-Type':'application/json'})
                    response.raise_for_status();result=response.json()
                    if result.get('stored') is not True or result.get('ignored'):raise RuntimeError('Ingest not accepted')
                    with db:db.execute("UPDATE outbox SET state='accepted' WHERE id=?",(mid,))
            except Exception as exc:status['errors'].append(type(exc).__name__)
            status['counts']=dict(db.execute('SELECT state,count(*) FROM outbox GROUP BY state'))
            (home/'status.json').write_text(json.dumps(status),encoding='utf-8')
            if args.once:print(json.dumps(status));break
            time.sleep(15)


if __name__=='__main__':main()
