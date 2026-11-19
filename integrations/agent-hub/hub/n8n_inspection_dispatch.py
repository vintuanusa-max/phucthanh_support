"""Read assigned customer images using existing hash cache, replan metadata once."""
import hashlib,json,time
from pathlib import Path
from hub.n8n_policy_gate import check,normalize

def tick(engine):
    marker=Path(engine.store.path).parent/'n8n-inspection-enabled-after'
    if not marker.exists():return
    boundary=float(marker.read_text())
    with engine.store.db() as db:
        rows=db.execute("SELECT * FROM n8n_task_execution WHERE kind='inspect_sources' AND mode='production' AND state IN ('pending_binding','waiting_information') AND attempts=0 ORDER BY updated").fetchall()
    for row in rows:
        p=json.loads(row['payload'])
        if p.get('batch_cutoff',0)<boundary:continue
        try:start(engine,dict(row),p)
        except Exception as exc:
            with engine.store.db() as db:
                db.execute("UPDATE n8n_task_execution SET state='waiting_information',attempts=MAX(attempts,1),result=?,updated=? WHERE id=? AND state!='done'",(json.dumps({'reason':str(exc)[:400] if isinstance(exc,ValueError) else type(exc).__name__,'safe_to_retry':False},ensure_ascii=False),time.time(),row['id']))
        break

def start(engine,task,p,reader=None):
    if reader is None:
        from hub.intake_preflight import observations
        reader=observations
    with engine.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT state,attempts FROM n8n_task_execution WHERE id=?',(task['id'],)).fetchone()
        if not current or current['attempts'] or current['state'] not in ('pending_binding','waiting_information'):return
        parent=db.execute('SELECT payload FROM n8n_batch_outbox WHERE id=?',(task['batch_id'],)).fetchone()
        if not parent:raise ValueError('Không tìm thấy cụm nguồn để đọc bổ sung.')
        envelope=json.loads(parent[0]);group=envelope['groups'][0]
        if group.get('inspection_round',0)>=1:raise ValueError('Đã đọc bổ sung một lượt; cần kiểm tra kết quả, không lặp API.')
        if check(engine,task['account'],task['thread_id'],group.get('group','')):raise ValueError('Nhóm bỏ qua hoặc policy chưa sẵn sàng.')
        policy=engine.order_intake.policy(task['account']);channel=engine.settings.inboxes[task['account']]['channel']
        wanted=set(p.get('image_ids') or []);messages=[]
        for mid in p['message_ids']:
            row=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(task['account'],task['thread_id'],mid)).fetchone()
            if not row:raise ValueError('Thiếu tin nguồn cần đọc.')
            m=normalize(json.loads(row[0]),policy,channel)
            if m.get('revision') or m.get('recalled'):raise ValueError('Nguồn đã đổi/thu hồi; cần gom lại.')
            images=[i for i in m.get('images',[]) if str(i) in wanted]
            if images and m.get('origin')=='customer' and m.get('direction')!='outgoing':messages.append({**m,'images':images})
        if not messages:raise ValueError('Không có ảnh khách được chỉ định. AI/PDF/PSD cần đi nhánh xuất file để Worker đọc; ảnh nhân viên chỉ làm ngữ cảnh.')
        latest=db.execute("SELECT MAX(CAST(json_extract(payload,'$.timestamp') AS REAL)) FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.origin') IN ('customer','staff')",(task['account'],task['thread_id'])).fetchone()[0]
        if latest and latest>p['batch_cutoff']:raise ValueError('Có tin mới; không đọc cụm cũ thiếu ngữ cảnh.')
        db.execute("UPDATE n8n_task_execution SET state='executing',attempts=1,updated=? WHERE id=?",(time.time(),task['id']))
    observations=reader(engine,{'account':task['account'],'thread_id':task['thread_id']},messages)
    if not observations:raise ValueError('Chưa đọc được ảnh; kiểm tra nguồn NAS.')
    identity=hashlib.sha256(('inspection:'+task['id']).encode()).hexdigest()
    group.update(batch_id=identity,revision=identity,inspection_round=1,inspection_parent_task=task['id'],source_observations=observations)
    with engine.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT OR IGNORE INTO n8n_batch_outbox(id,account,thread_id,revision,payload,state,result,created,updated) VALUES(?,?,?,?,?,'queued',NULL,?,?)",(identity,task['account'],task['thread_id'],identity,json.dumps(envelope,ensure_ascii=False),time.time(),time.time()))
        db.execute("UPDATE n8n_task_execution SET state='done',result=?,updated=? WHERE id=? AND state='executing'",(json.dumps({'receipt_id':identity,'receipt_table':'n8n_batch_outbox','reason':'Đã đọc ảnh bằng cache theo hash; gửi kết quả chữ để n8n phân loại tiếp. Chưa ghi ERP.','safe_to_retry':False,'observation_count':len(observations)},ensure_ascii=False),time.time(),task['id']))
