"""Read-only file job observer; effects are private notes, never ERP/job retries."""
import hashlib
import json
import re
import time

TABLES=('pet_exports','jpg_exports','native_selections','artwork_checks')
TERMINAL={'done','archived','superseded','cancelled','confirmed'}
STAGES={'reading':'Đọc PDF/AI và kiểm tra nguồn','awaiting_upload':'Chờ worker tải file nguồn','queued':'Chờ worker nhận xuất','exporting':'Worker xuất PNG/TIFF hoặc JPG','planning':'AI phân tích/chọn artwork','publishing':'Đưa preview vào Chatwoot','scan_queued':'Chờ Illustrator đọc file','scan_running':'Illustrator đọc cụm artwork','candidates_ready':'Đã đọc cụm artwork','render_queued':'Chờ Illustrator xuất PNG','render_running':'Illustrator xuất PNG','png_check_queued':'Kiểm tra PNG trước TIFF','verifying':'AI kiểm chứng artwork','waiting_verify':'Chờ kiểm chứng PNG','waiting_scan':'Chờ đọc đối tượng','review':'Cần kiểm tra','uncertain':'Kết quả chưa xác minh'}

def safe(value):
    text=str(value or '')
    text=re.sub(r'https?://\S+','[URL đã ẩn]',text)
    text=re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+',r'\1[đã ẩn]',text)
    text=re.sub(r'(?:sk-|r8_|ghp_|AIza)[A-Za-z0-9_-]{12,}','[khóa đã ẩn]',text)
    text=re.sub(r'\b[A-Za-z0-9+/=_-]{80,}\b','[dữ liệu dài đã ẩn]',text)
    return text[:1000]

def tick(engine, now=None):
    now=time.time() if now is None else now
    pending=[]
    with engine.store.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS file_notice_watch(id TEXT PRIMARY KEY,signature TEXT,since REAL,notified TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS file_notice_meta(key TEXT PRIMARY KEY,value REAL)')
        db.execute("INSERT OR IGNORE INTO file_notice_meta VALUES('enabled_at',?)",(now,))
        enabled=db.execute("SELECT value FROM file_notice_meta WHERE key='enabled_at'").fetchone()[0]
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        beats={r['service']:r['seen'] for r in db.execute('SELECT * FROM workflow_beats')} if 'workflow_beats' in tables else {}
        for table in TABLES:
            if table not in tables:continue
            for row in db.execute('SELECT * FROM '+table):
                p=json.loads(row['payload']);state=row['state'];auto=p.get('auto_status','')
                if table=='artwork_checks':
                    result=json.loads(row['result'] or '{}');p={**p,'error':result.get('error') or result.get('reason') or result.get('review_items') or p.get('error','')}
                    p.setdefault('brief_id',row['brief_id'])
                if state in TERMINAL:continue
                bid=p.get('brief_id') or (row['brief_id'] if 'brief_id' in row.keys() else None)
                if bid and not engine.artwork_checks.pet.workflow.current(bid):continue
                # Once native selection owns this source, source-parser warnings are diagnostic only.
                native=db.execute('SELECT 1 FROM native_selections WHERE brief_id=? LIMIT 1',(bid,)).fetchone() if bid and 'native_selections' in tables else None
                if native and table=='artwork_checks':continue
                if native and table=='pet_exports' and p.get('source',{}).get('asset',{}).get('name')=='Raster source images':continue
                conversation=p.get('conversation')
                if not conversation and p.get('brief_id') and 'design_briefs' in tables:
                    b=db.execute('SELECT conversation FROM design_briefs WHERE id=?',(p['brief_id'],)).fetchone();conversation=b[0] if b else None
                if not conversation:continue
                if table=='native_selections' and auto=='selected':
                    missing=p.get('blocked_parts',[])
                    if missing:
                        reason=safe('Đã chuyển xuất các vị trí đủ nguồn; phần còn thiếu không chặn file: '+'; '.join(missing))
                        signature=hashlib.sha256(reason.encode()).hexdigest()
                        identity='partial:'+row['id']
                        old=db.execute('SELECT * FROM file_notice_watch WHERE id=?',(identity,)).fetchone()
                        if not old or old['notified']!=signature:
                            db.execute('INSERT OR IGNORE INTO file_notice_watch VALUES(?,?,?,NULL)',(identity,signature,now))
                            pending.append((identity,signature,conversation,'',bid or row['id'],'PARTIAL_READY',reason,'review'))
                    # Child jobs own rendering/worker status; a selected parent is not stalled.
                    continue
                reason=safe(p.get('error') or p.get('review_reason') or p.get('review_items') or '')
                stage=auto if auto in ('planning','verifying','waiting_verify','waiting_scan') else state
                sig=hashlib.sha256(json.dumps([state,auto,reason]).encode()).hexdigest()
                identity=table+':'+row['id'];old=db.execute('SELECT * FROM file_notice_watch WHERE id=?',(identity,)).fetchone()
                since=old['since'] if old and old['signature']==sig else now
                db.execute('INSERT INTO file_notice_watch VALUES(?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET signature=excluded.signature,since=excluded.since',(identity,sig,since))
                beat=beats.get('artwork:'+row['account'])
                offline=(now-beat>1200) if beat else now-since>1200
                code='';action=''
                if state in ('review','failed','error','uncertain') or auto=='review':
                    code='RESULT_UNCERTAIN' if state=='uncertain' else 'FILE_REVIEW'
                    action='Mở hồ sơ ở trang điều phối, đối chiếu nguồn/preview và lý do dưới đây. Không chạy lại nếu kết quả lần trước chưa rõ.'
                elif offline and stage not in ('planning','verifying','publishing'):
                    code='WORKER_HEARTBEAT_STALE'
                    reason='Không nhận heartbeat worker hơn 20 phút; chưa thể phân biệt ứng dụng dừng, máy mất mạng hoặc tác vụ Adobe đang chiếm luồng.'
                    action='Kiểm tra máy bot đã đăng nhập, mạng/NAS, ArtworkInspector và hộp thoại Illustrator/Photoshop tại http://127.0.0.1:8096/. Đối chiếu file đã có trước khi chạy lại.'
                elif now-since>1800:
                    code='FILE_STAGE_STALE';reason=reason or 'Trạng thái không đổi hơn 30 phút kể từ lần quan sát; chưa xác định nguyên nhân.'
                    action='Xem lịch sử job và dịch vụ tương ứng ở điều phối 8096. Kiểm tra nguồn, Adobe hoặc kết nối AI/Chatwoot. Không tự xuất lại job chưa rõ kết quả.'
                if not code:continue
                notice=hashlib.sha256((identity+sig+code).encode()).hexdigest()
                if not old and row['created']<enabled and code in ('FILE_REVIEW','RESULT_UNCERTAIN'):
                    db.execute('UPDATE file_notice_watch SET notified=? WHERE id=?',(notice,identity));continue
                if old and old['notified']==notice:continue
                source=p.get('source',{});asset=source.get('asset',{}) if isinstance(source,dict) else {}
                name=safe(asset.get('name') or p.get('asset',{}).get('name') or p.get('brief_id') or row['id'])
                text=('XUẤT FILE — CẢNH BÁO NỘI BỘ ['+code+']\nNguồn: '+name+'\nHồ sơ/job: '+row['id']+'\nLuồng: '+table+'\nĐang kẹt: '+STAGES.get(stage,stage)+' ('+state+')\nChi tiết: '+(reason or 'Chưa có lý do chi tiết từ worker; cần xem nhật ký job.')+'\nCần làm: '+action+'\nChỉ cảnh báo file; không tạo/sửa đơn ERP, không tự chạy lại, chưa RIP/gửi khách.')
                pending.append((identity,notice,conversation,text,bid or row['id'],code,reason,stage))
    # Durable Engine.effect id prevents repeat sends, including ambiguous outcomes.
    grouped={}
    for item in pending:grouped.setdefault((item[2],item[4]),[]).append(item)
    for (conversation,bid),items in list(grouped.items())[:10]:
        # One actionable summary per current sample revision, not one message per source/stage.
        summaries=sorted(set(STAGES.get(x[7],x[7])+': '+(x[6] or 'Chưa xác định được nguyên nhân; xem chi tiết điều phối.') for x in items))
        notice=hashlib.sha256(json.dumps([conversation,bid,summaries],ensure_ascii=False).encode()).hexdigest()
        text='FILE IN — CẦN KIỂM TRA NỘI BỘ\nHồ sơ: '+bid+'\n'+'\n'.join(summaries[:4])+'\nChi tiết và nguồn: http://127.0.0.1:8096/#brief='+bid+'\nChưa RIP/gửi khách; không tạo lại đơn ERP.'
        try:engine.note('file-watch:'+notice,conversation,text,apply_capture=True)
        except Exception:continue
        with engine.store.db() as db:
            for identity,original_notice,*_ in items:db.execute('UPDATE file_notice_watch SET notified=? WHERE id=?',(original_notice,identity))
