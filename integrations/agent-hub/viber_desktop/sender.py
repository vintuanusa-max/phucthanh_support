"""Staff-only Hub adapter. Durable reservation precedes every native invocation."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
from hub.delivery_policy import delivery_block
from .native_sender import invoke
from .send_ledger import SendLedger
from .source import Source


def reconcile(rows, before, text, started):
    return [r for r in rows if r[0] not in before and r[2]=='1' and r[6]=='1'
            and r[7]==text and int(r[1])/1000 >= started-2]


def deliver(item, cfg, source, ledger, client, transport=invoke):
    did=item['id']; message=item['message']; text=message.get('content','')
    policy=dict(channel='viber',delivery_enabled=True,human_delivery_enabled=True,
                delivery_allowed_threads=['viber:g1'],delivery_after=cfg['enabled_after'])
    reason=delivery_block(SimpleNamespace(mode='review'),policy,message,item['thread_id'])
    if reason:
        return dict(state='blocked',detail=reason)
    started=time.time()
    before={r[0] for r in source.read(started-10)}  # Also verifies current profile and group.
    client_id=str(10**15 + int(hashlib.sha256(did.encode()).hexdigest()[:12],16))
    response=client.post(f"/adapters/{cfg['account']}/prepare/{did}",json={'client_id':client_id})
    response.raise_for_status()
    if not ledger.reserve(did,cfg['account'],item['thread_id'],text):
        return dict(state='uncertain',detail='Đã có dấu lần gửi; không tự gửi lại để tránh trùng.')
    try:
        result=transport(text,dry_run=False)
        if not result.get('clean') or not result.get('accepted'):
            return dict(state='uncertain',detail='Chưa xác nhận kết quả Viber; không tự gửi lại.')
        for attempt in range(4):
            matches=reconcile(source.read(started-2),before,text,started)
            if len(matches)==1:
                platform='viber:'+matches[0][0]
                ledger.confirm(did,platform)
                return dict(state='submitted',platform_message_id=platform,
                            detail='Viber Desktop đã ghi nhận đúng tin trong nhóm CDG; chưa xác nhận thiết bị người nhận.')
            if len(matches)>1:
                break
            if attempt<3: time.sleep(1)
    except Exception:
        pass
    return dict(state='uncertain',detail='Chưa đối chiếu được duy nhất một tin Viber; không tự gửi lại.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--one',action='store_true')
    args=parser.parse_args()
    cfg=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    if cfg['account']!='viber-personal-1' or cfg['chat_id']!=1 or cfg['thread_id']!='viber:g1':
        raise RuntimeError('Only verified CDG binding is supported')
    source=Source(cfg['profile'],cfg['chat_id'],cfg['group_name'])
    if args.check:
        source.read(time.time())
        result=invoke('Kiểm tra kết nối nội bộ — không gửi 🧪',dry_run=True)
        print(json.dumps(result))
        if not (result.get('clean') and result.get('context_verified') and not result.get('invoked')):
            raise RuntimeError('Native preflight failed')
        return
    home=Path(cfg['state_dir']);home.mkdir(parents=True,exist_ok=True)
    import msvcrt
    lock=(home/'sender.lock').open('a+b');lock.seek(0)
    if not lock.read(1):lock.write(b'0');lock.flush()
    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    ledger=SendLedger(home/'sender.sqlite3')
    ledger.db.execute('CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY,payload TEXT NOT NULL,reported INTEGER DEFAULT 0)')
    ledger.db.commit()
    with httpx.Client(base_url=cfg['hub_url'],headers={'Authorization':'Bearer '+cfg['ingest_token']},trust_env=False,timeout=30) as client:
        while not (home/'sender-stop.flag').exists():
            status={'updated_at':time.time(),'mode':'staff_text_only','errors':[]}
            try:
                for did,payload in ledger.db.execute('SELECT id,payload FROM results WHERE reported=0').fetchall():
                    response=client.post(f"/adapters/{cfg['account']}/results/{did}",json=json.loads(payload))
                    response.raise_for_status()
                    with ledger.db:ledger.db.execute('UPDATE results SET reported=1 WHERE id=?',(did,))
                    if args.one:
                        return
                response=client.post(f"/adapters/{cfg['account']}/claim")
                response.raise_for_status();item=response.json().get('item')
                if item:
                    try: result=deliver(item,cfg,source,ledger,client)
                    except Exception: result=dict(state='uncertain',detail='Đầu nối chưa hoàn tất; không tự gửi lại.')
                    with ledger.db:
                        ledger.db.execute('INSERT OR IGNORE INTO results(id,payload) VALUES(?,?)',(item['id'],json.dumps(result)))
                    status['last_result']=result['state']
            except Exception as exc:
                status['errors']=[type(exc).__name__]
            (home/'sender-status.json').write_text(json.dumps(status))
            time.sleep(3)


if __name__=='__main__': main()
