"""Operator quiet-window release. Uses the normal poller and source claims."""
import hashlib,json,time

def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS intake_run_now(id TEXT PRIMARY KEY,account TEXT NOT NULL,thread_id TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,run_id TEXT)')

def identity(account, thread, rows):
    value=[account,thread,sorted([(i or '',m['message_id'],m.get('revision',0),m['timestamp']) for i,m,_ in rows])]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def first_group(rows, wait):
    result=[];last=None
    for row in rows:
        stamp=float(row[1]['timestamp'])
        if last is not None and stamp-last>wait:break
        result.append(row);last=stamp
    return result

def pending(e):
    intake=e.order_intake;items=[];wait=e.intake_management.seconds()
    from hub.intake_quiet import human_activity
    with e.store.db() as db:
        init(db)
        for account in e.settings.inboxes:
            if not e.intake_management.enabled(account):continue
            scope=intake.scope(account)
            if not scope.get('enabled_after') or intake.policy(account) is None:continue
            records=db.execute("SELECT c.id,c.payload,j.state AS job_state FROM captures c LEFT JOIN jobs j ON j.id=c.id LEFT JOIN intake_sources s ON s.capture_id=c.id WHERE c.account=? AND s.capture_id IS NULL AND json_extract(c.payload,'$.timestamp')>=? ORDER BY json_extract(c.payload,'$.timestamp'),c.rowid",(account,scope['enabled_after'])).fetchall()
            threads={}
            for row in records:
                m=json.loads(row['payload'])
                if intake.accepts(m):threads.setdefault(m['thread_id'],[]).append((row['id'],m,row['job_state']))
            for thread,rows in threads.items():
                # Include internal human activity even when it is not an intake source.
                extra=db.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp')>=?",(account,thread,rows[0][1]['timestamp'])).fetchall()
                for row in extra:
                    m=json.loads(row[0])
                    if human_activity(m) and not intake.accepts(m):rows.append((None,m,'done'))
                rows.sort(key=lambda x:float(x[1]['timestamp']))
                rows=first_group(rows,wait)
                token=identity(account,thread,rows)
                ticket=db.execute('SELECT state FROM intake_run_now WHERE id=?',(token,)).fetchone()
                ready=all(r[2]=='done' for r in rows)
                items.append({'id':token,'account':account,'thread_id':thread,'group':rows[0][1].get('display_name',thread),
                    'last_timestamp':rows[-1][1]['timestamp'],'deadline':rows[-1][1]['timestamp']+wait,
                    'ready':ready,'queued':bool(ticket and ticket[0]=='queued'),
                    'messages':[{'sender':m.get('sender',''),'text':m.get('text',''),'time':m['timestamp'],'images':len(m.get('images',[])),'files':[a.get('name','') for a in m.get('assets',[])]} for _,m,_ in rows]})
    return sorted(items,key=lambda x:x['last_timestamp'],reverse=True)

def request(e,data):
    if set(data)!={'action','id'}:raise ValueError('Yêu cầu chạy không hợp lệ')
    item=next((x for x in pending(e) if x['id']==data['id']),None)
    if not item:raise ValueError('Cụm đã thay đổi hoặc đã xử lý; bấm Làm mới để kiểm tra')
    if not item['ready']:raise ValueError('Nguồn còn đang đồng bộ; chưa được chạy thiếu tin/ảnh')
    with e.store.db() as db:
        init(db)
        db.execute("INSERT OR IGNORE INTO intake_run_now VALUES(?,?,?,'queued',?,NULL)",(item['id'],item['account'],item['thread_id'],time.time()))
    return {'message':'Đã yêu cầu chạy ngay. Hub sẽ nhận qua hàng đợi hiện có; không tạo thêm lượt khi bấm trùng.','id':item['id']}

def ticket(store,account,thread,rows,wait):
    rows=first_group(rows,wait)
    if not rows:return None
    token=identity(account,thread,rows)
    with store.db() as db:
        init(db)
        found=db.execute("SELECT id FROM intake_run_now WHERE id=? AND state='queued'",(token,)).fetchone()
    return token if found else None
