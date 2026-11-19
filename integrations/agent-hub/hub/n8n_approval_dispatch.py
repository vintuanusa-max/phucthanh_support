"""Semantic approval -> existing evidence worker and delivery ledger, never direct send."""
import hashlib
import json
import time
from pathlib import Path
from hub.n8n_policy_gate import check, normalize


def tick(engine):
    marker=Path(engine.store.path).parent/'n8n-approval-enabled-after'
    if not marker.exists():return []
    boundary=float(marker.read_text())
    with engine.store.db() as db:
        rows=db.execute("SELECT * FROM n8n_task_execution WHERE mode='production' AND kind='print_approval' AND state='pending_binding'").fetchall()
    results=[]
    for row in rows:
        p=json.loads(row['payload'])
        if p.get('batch_cutoff',0)<boundary:continue
        try:results.append(start(engine,dict(row),p))
        except Exception as exc:
            with engine.store.db() as db:
                db.execute("UPDATE n8n_task_execution SET state='waiting_information',result=?,updated=? WHERE id=? AND state='pending_binding'",(json.dumps({'reason':str(exc)[:500] if isinstance(exc,ValueError) else type(exc).__name__,'safe_to_retry':False},ensure_ascii=False),time.time(),row['id']))
    return results


def start(engine,task,p):
    route=engine.print_approvals.route()
    if not route:raise ValueError('Chưa cấu hình nhóm nhận duyệt in.')
    spec=p.get('spec') or {}
    if spec.get('approval_scope')!='print':raise ValueError('Chưa xác định khách duyệt IN; không gửi từ OK chung chung.')
    with engine.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT state FROM n8n_task_execution WHERE id=?',(task['id'],)).fetchone()
        if not current or current[0]!='pending_binding':return {'state':'already_claimed'}
        group=db.execute('SELECT * FROM threads WHERE account=? AND thread_id=?',(task['account'],task['thread_id'])).fetchone()
        if not group or check(engine,task['account'],task['thread_id'],group['display_name']):raise ValueError('Nhóm bị bỏ qua hoặc policy chưa sẵn sàng.')
        policy=engine.order_intake.policy(task['account']); channel=engine.settings.inboxes[task['account']]['channel']
        messages={}
        for mid in p['message_ids']:
            row=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(task['account'],task['thread_id'],mid)).fetchone()
            if not row:raise ValueError('Thiếu tin nguồn duyệt in.')
            m=normalize(json.loads(row[0]),policy,channel)
            if m.get('revision') or m.get('recalled'):raise ValueError('Tin duyệt/mẫu đã sửa hoặc thu hồi.')
            messages[mid]=m
        confirmation=messages.get(str(spec.get('confirmation_message_id')))
        quote=spec.get('confirmation_quote')
        if not confirmation or confirmation.get('origin')!='customer' or confirmation.get('direction')!='incoming':raise ValueError('Cần lời xác nhận từ khách đúng nhóm.')
        if not isinstance(quote,str) or not quote.strip() or quote not in confirmation.get('text',''):raise ValueError('Trích dẫn câu duyệt không khớp nguồn.')
        if confirmation['timestamp']<route['enabled_after']:raise ValueError('Không phát lại thông báo cũ.')
        photo_ids=spec.get('approval_image_message_ids')
        if not isinstance(photo_ids,list) or not 1<=len(photo_ids)<=8 or any(str(mid) not in messages for mid in photo_ids):raise ValueError('Chưa gắn đúng tin ảnh mẫu được duyệt.')
        photos=[messages[str(mid)] for mid in photo_ids]
        if any(m['timestamp']>confirmation['timestamp'] or not m.get('images') or m.get('attachments') for m in photos):raise ValueError('Ảnh mẫu không đầy đủ hoặc gửi sau câu duyệt.')
        if any(m.get('origin')!='staff' and (m.get('sender_id') or m.get('sender'))!=(confirmation.get('sender_id') or confirmation.get('sender')) for m in photos):raise ValueError('Ảnh thuộc khách khác; cần đối chiếu nội bộ.')
        later=db.execute("SELECT 1 FROM captures WHERE account=? AND thread_id=? AND CAST(json_extract(payload,'$.timestamp') AS REAL)>? AND json_extract(payload,'$.origin')='customer' LIMIT 1",(task['account'],task['thread_id'],confirmation['timestamp'])).fetchone()
        if later:raise ValueError('Khách có tin sau câu duyệt; cần xác nhận lại phiên bản mẫu.')
        hashes=sorted({a['sha256'] for m in photos for a in m.get('assets',[]) if a.get('kind')=='image' and a.get('sha256')})
        if not hashes:hashes=sorted({str(i) for m in photos for i in m.get('images',[])})
        fingerprint=hashlib.sha256(json.dumps([task['account'],task['thread_id'],hashes]).encode()).hexdigest()
        identity=hashlib.sha256(json.dumps([task['account'],task['thread_id'],confirmation['message_id']]).encode()).hexdigest()
        old=db.execute('SELECT id FROM print_approvals WHERE id=? OR (account=? AND thread_id=? AND json_extract(payload,\'$.fingerprint\')=?)',(identity,task['account'],task['thread_id'],fingerprint)).fetchall()
        if len(old)>1:raise ValueError('Có nhiều hồ sơ duyệt liên quan; không gửi thêm.')
        if old:identity=old[0]['id']
        else:
            chosen=sorted([m for m in messages.values() if m['timestamp']<=confirmation['timestamp'] and (m in photos or not m.get('images'))],key=lambda m:(m['timestamp'],m['message_id']))
            selected=list(dict.fromkeys(m['message_id'] for m in chosen))
            payload={'destination':route,'confirmation':confirmation['message_id'],'messages':selected,'fingerprint':fingerprint,'n8n_task_id':task['id']}
            db.execute('INSERT INTO print_approvals VALUES(?,?,?,?,?,?,?)',(identity,task['account'],task['thread_id'],confirmation['message_id'],'awaiting_evidence',json.dumps(payload,ensure_ascii=False),time.time()))
        db.execute("UPDATE n8n_task_execution SET state='submitted',result=?,attempts=attempts+1,updated=? WHERE id=?",(json.dumps({'receipt_id':identity,'receipt_table':'print_approvals','safe_to_retry':False,'reused':bool(old)}),time.time(),task['id']))
    return {'state':'submitted','receipt_id':identity}
