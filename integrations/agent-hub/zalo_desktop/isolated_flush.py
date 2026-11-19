"""Per-message delivery isolation; preserve payloads and Hub idempotency."""
import json
import time
from pathlib import PurePosixPath
import httpx

def wire_paths(message):
    for asset in message.get('assets',[]):
        if asset.get('state')!='ready':continue
        value=str(asset.get('relative_path','')).replace('\\','/')
        path=PurePosixPath(value)
        if not value or path.is_absolute() or '..' in path.parts or ':' in value:
            raise ValueError('invalid_relative_archive_path')
        asset['relative_path']=path.as_posix()
    return message

def flush(reader):
    db=reader.state.db
    db.execute('CREATE TABLE IF NOT EXISTS delivery_errors(thread TEXT,msg TEXT,error TEXT,next_try REAL,PRIMARY KEY(thread,msg))')
    rows=db.execute("SELECT o.thread,o.msg,o.payload FROM outbox o LEFT JOIN delivery_errors e ON e.thread=o.thread AND e.msg=o.msg WHERE o.state='queued' AND COALESCE(e.next_try,0)<=? ORDER BY COALESCE(e.next_try,0),o.rowid LIMIT 50",(time.time(),)).fetchall()
    def failed(thread,msg,reason,review=False,delay=60):
        with db:
            db.execute('INSERT OR REPLACE INTO delivery_errors VALUES(?,?,?,?)',(thread,msg,reason,time.time()+delay))
            if review:db.execute("UPDATE outbox SET state='delivery_review' WHERE thread=? AND msg=? AND state='queued'",(thread,msg))
    for thread,msg,encoded in rows:
        try:
            message=json.loads(encoded)
            if not reader.capture_allowed(message):
                with db:db.execute("UPDATE outbox SET state='ignored_policy' WHERE thread=? AND msg=?",(thread,msg))
                continue
            if reader.vault:
                message=reader.vault.enrich(message)
                if message is None:
                    failed(thread,msg,'waiting_for_asset',delay=30)
                    continue
            wire_paths(message)
            response=reader.http.post('/ingest',json=message)
            response.raise_for_status()
            result=response.json()
            if result.get('stored') is not True:raise ValueError('missing_hub_acknowledgement')
            reader.state.accepted(thread,msg,result['id'])
            with db:db.execute('DELETE FROM delivery_errors WHERE thread=? AND msg=?',(thread,msg))
        except httpx.HTTPStatusError as exc:
            code=exc.response.status_code
            reason='HTTP '+str(code)
            try:
                detail=exc.response.json().get('detail')
                if isinstance(detail,str):reason+=': '+detail[:160]
            except ValueError:pass
            failed(thread,msg,reason,review=code in (400,409,413,422))
            continue
        except (ValueError,KeyError,TypeError) as exc:
            failed(thread,msg,type(exc).__name__,review=True)
            continue
        except Exception as exc:
            failed(thread,msg,type(exc).__name__)
            continue
        # A post-ack archive error must never resend an accepted capture.
        if reader.vault:
            try:reader.vault.release(message)
            except Exception as exc:failed(thread,msg,'archive_release:'+type(exc).__name__)
    issues=[{'message_id':r[0],'state':r[1],'reason':r[2]} for r in db.execute("SELECT o.msg,o.state,e.error FROM delivery_errors e JOIN outbox o ON o.thread=e.thread AND o.msg=e.msg ORDER BY e.next_try DESC LIMIT 10")]
    reader.delivery_issues=issues
    if issues:reader.errors['delivery']='Tin/file lỗi được tách riêng; các tin khác vẫn đồng bộ'
    else:reader.errors.pop('delivery',None)
