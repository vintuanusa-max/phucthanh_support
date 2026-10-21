"""Conservative print approvals, separate from ERP order creation and channel delivery."""
import hashlib
import json
import re
import time

from hub.order_policy import capture_allowed, key


def is_reprint(text):
    text = key(text)
    if re.search(r'\b(chưa|không|đừng|khoan|hủy|huỷ|đợi|chờ|test)\b|\?', text):
        return False
    return bool(re.search(r'\b(in bù|bù cho|bù thêm)\b', text) and re.search(r'\d+\s*(cái|chiếc|c|áo|bộ)\b', text))


def select_reprint(message, history):
    if not is_reprint(message['text']):
        raise ValueError('Chưa có yêu cầu in bù rõ số lượng')
    same = [m for m in history if (m['account'], m['thread_id']) == (message['account'], message['thread_id'])
            and message['timestamp']-120 <= m['timestamp'] <= message['timestamp']+120]
    photos = [m for m in same if m.get('images') and author(m)==author(message)]
    if any(m['timestamp'] > message['timestamp'] and author(m)==author(message) and not m.get('images') and m['message_id']!=message['message_id'] for m in history):
        raise ValueError('Khách bổ sung sau yêu cầu in bù; cần đối chiếu')
    if not photos or any(m.get('revision') or m.get('recalled') or m.get('attachments') for m in [message]+photos):
        raise ValueError('Cần ảnh mẫu in bù đầy đủ từ đúng khách')
    if any(m.get('origin')=='customer' and author(m)!=author(message) for m in same):
        raise ValueError('Khách trao đổi xen kẽ; cần xác định ảnh in bù')
    chosen = sorted({m['message_id']:m for m in [message]+photos}.values(),key=lambda m:(m['timestamp'],m['message_id']))
    if sum(len(m.get('images',[])) for m in chosen)>8:
        raise ValueError('Quá nhiều ảnh in bù')
    return chosen


def is_confirmation(text):
    text = key(text)
    if re.search(r'\b(chưa|không|đừng|khoan|hủy|huỷ|đợi|chờ|sửa|thử|test)\b|\?', text):
        return False
    if re.fullmatch(r'ok(?:ay)?[,.! ]*(?:nhé|nhe|nha)[.! ]*', text):
        return True
    return bool(re.search(r'\b(ok[,.! ]*in|in\s+(nhé|nhe|nha|đi)|chốt\s+(in|mẫu)|duyệt\s+mẫu|in\s+theo\s+mẫu)\b', text))


def author(message):
    return message.get('sender_id') or key(message.get('sender',''))


def select_approval(confirmation, history):
    """Never use another group's image, a quote thumbnail, or an unresolved attachment."""
    if not is_confirmation(confirmation['text']):
        raise ValueError('Chưa có câu chốt in rõ ràng')
    if confirmation.get('revision') or confirmation.get('recalled'):
        raise ValueError('Tin xác nhận đã sửa/thu hồi')
    same = [m for m in history if (m['account'],m['thread_id']) == (confirmation['account'],confirmation['thread_id'])
            and confirmation['timestamp']-1800 <= m['timestamp'] <= confirmation['timestamp']]
    same.sort(key=lambda m:(m['timestamp'],m['message_id']))
    quote = confirmation.get('quoted_image')
    if quote:
        if not quote.get('resolved') or not confirmation.get('images') or confirmation.get('attachments'):
            raise ValueError('Không lấy được đúng ảnh khách trích dẫn')
        chosen=[confirmation]
    else:
        photos=[m for m in same if m.get('images')]
        if not photos:
            raise ValueError('Chưa có ảnh mẫu đã kiểm chứng')
        last=photos[-1]
        if re.fullmatch(r'ok(?:ay)?[,.! ]*(?:nhé|nhe|nha)[.! ]*',key(confirmation['text'])):
            if confirmation['timestamp']-last['timestamp']>300:
                raise ValueError('Câu OK chưa gắn rõ với ảnh mẫu gần đây')
        chosen=[m for m in photos if author(m)==author(last) and last['timestamp']-120 <= m['timestamp']]
        if any(author(m)!=author(last) for m in photos if m['timestamp']>=chosen[0]['timestamp']):
            raise ValueError('Nhiều người gửi mẫu xen kẽ; cần chọn đúng mẫu')
        # A different customer's photo is never attributed to this customer.
        if last.get('origin')!='staff' and author(last)!=author(confirmation):
            raise ValueError('Ảnh thuộc khách khác')
        between=[m for m in same if m['timestamp']>=chosen[0]['timestamp'] and m['message_id']!=confirmation['message_id']]
        if any(m.get('origin')=='customer' and author(m)!=author(confirmation) for m in between):
            raise ValueError('Nhiều khách trao đổi xen kẽ; cần nhân viên chọn ảnh')
        if any(m.get('attachments') or m.get('revision') or m.get('recalled') for m in chosen):
            raise ValueError('Ảnh mẫu chưa đầy đủ hoặc đã sửa')
        # Preserve short follow-up details from the approving customer, including quantity/placement.
        chosen += [m for m in between if author(m)==author(confirmation) and m not in chosen]
        if confirmation not in chosen:chosen.append(confirmation)
    if len(chosen)>12 or sum(len(m.get('images',[])) for m in chosen)>8:
        raise ValueError('Quá nhiều ảnh/tin; cần nhân viên tách mẫu')
    return sorted(chosen,key=lambda m:(m['timestamp'],m['message_id']))


class PrintApprovals:
    def __init__(self, engine):
        self.engine=engine
        with engine.store.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS print_approvals(
                id TEXT PRIMARY KEY, account TEXT NOT NULL, thread_id TEXT NOT NULL,
                confirmation_id TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
                created REAL NOT NULL, UNIQUE(account,thread_id,confirmation_id));
                CREATE TABLE IF NOT EXISTS print_deliveries(id TEXT PRIMARY KEY, approval_id TEXT NOT NULL, account TEXT NOT NULL,thread_id TEXT NOT NULL,state TEXT NOT NULL,result TEXT,UNIQUE(approval_id,account));
                CREATE TABLE IF NOT EXISTS print_change_sources(account TEXT NOT NULL,thread_id TEXT NOT NULL,message_id TEXT NOT NULL,approval_id TEXT NOT NULL,PRIMARY KEY(account,thread_id,message_id));''')
            db.execute("UPDATE print_approvals SET state='uncertain' WHERE state='sending'")
            db.execute("UPDATE print_deliveries SET state='uncertain' WHERE state='sending'")

    def route(self):
        for account,cfg in self.engine.settings.inboxes.items():
            route=cfg.get('print_forward',{})
            if route.get('enabled_after') and route.get('thread_id'):
                return {'account':account,**route}
        return None

    def poll(self):
        route=self.route()
        if not route:return False
        from hub.print_changes import poll_changes
        if poll_changes(self):return True
        with self.engine.store.db() as db:
            rows=db.execute("SELECT c.payload FROM captures c LEFT JOIN print_approvals p ON p.account=c.account AND p.thread_id=c.thread_id AND p.confirmation_id=c.message_id WHERE p.id IS NULL AND NOT EXISTS(SELECT 1 FROM print_change_sources x WHERE x.account=c.account AND x.thread_id=c.thread_id AND x.message_id=c.message_id) AND json_extract(c.payload,'$.timestamp')>=? AND json_extract(c.payload,'$.timestamp')<? ORDER BY json_extract(c.payload,'$.timestamp') DESC LIMIT 500",(route['enabled_after'],time.time()-120)).fetchall()
        for row in rows:
            m=json.loads(row[0])
            from hub.quality_monitor import monitored
            if monitored(m['account'],m['thread_id']):continue
            cfg=self.engine.settings.inboxes.get(m['account'],{})
            policy=self.engine.order_intake.policy(m['account'])
            if policy is None or not (is_confirmation(m['text']) or is_reprint(m['text'])):continue
            if m['origin']!='customer' or m['direction']!='incoming' or (m['account'],m['thread_id'])==(route['account'],route['thread_id']):continue
            if not capture_allowed(policy,cfg.get('channel'),m['thread_id'],m['display_name']):continue
            if key(m['sender']) in {key(n) for n in policy.get(cfg.get('channel','')+'_internal_members',[])}:continue
            with self.engine.store.db() as db:
                history=[json.loads(r[0]) for r in db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,\'$.timestamp\')>=?',(m['account'],m['thread_id'],m['timestamp']-1800))]
            # Wait for all messages in this group to settle; a subsequent correction needs review.
            if any(x['timestamp']>time.time()-120 for x in history):continue
            identity=hashlib.sha256(json.dumps([m['account'],m['thread_id'],m['message_id']]).encode()).hexdigest()
            payload={'destination':route,'confirmation':m['message_id']}
            try:
                reprint=is_reprint(m['text'])
                if not reprint and any(x['timestamp']>m['timestamp'] and author(x)==author(m) and not is_confirmation(x['text']) for x in history):
                    raise ValueError('Khách có tin bổ sung sau câu chốt; cần kiểm tra lại')
                chosen=select_reprint(m,history) if reprint else select_approval(m,history)
                if reprint:
                    payload.update(kind='reprint',notice='YÊU CẦU IN BÙ — '+m['text']+'\nĐối chiếu đúng ảnh và số lượng; không phải thay đổi sau duyệt. Không tự tạo đơn ERP mới.')
                payload['messages']=[x['message_id'] for x in chosen]
                photo_ids=sorted({a['sha256'] for x in chosen for a in x.get('assets',[]) if a.get('kind')=='image' and a.get('sha256')})
                if not photo_ids:photo_ids=sorted(str(i) for x in chosen for i in x.get('images',[]))
                payload['fingerprint']=hashlib.sha256(json.dumps([m['account'],m['thread_id'],photo_ids]+([m['message_id']] if reprint else [])).encode()).hexdigest()
                with self.engine.store.db() as db:
                    previous=db.execute("SELECT 1 FROM print_approvals WHERE json_extract(payload,'$.fingerprint')=?",(payload['fingerprint'],)).fetchone()
                if previous:raise ValueError('Loạt ảnh này đã có hồ sơ chốt in; kiểm tra trước khi gửi lại')
                state='awaiting_evidence'
            except ValueError as exc:
                state='review';payload['reason']=str(exc)
            with self.engine.store.db() as db:
                db.execute('INSERT OR IGNORE INTO print_approvals VALUES(?,?,?,?,?,?,?)',(identity,m['account'],m['thread_id'],m['message_id'],state,json.dumps(payload,ensure_ascii=False),time.time()))
            if state=='review':
                mapping=self.engine.store.thread(account=m['account'],thread_id=m['thread_id'])
                if mapping:self.engine.note(identity+':print-review',mapping['conversation'],'CHỐT IN CẦN KIỂM TRA: '+payload['reason'],apply_capture=True)
            return True
        return False

    def evidence_request(self, adapter):
        from hub.evidence_document import select_sources
        route=self.route()
        if not route or route['account']!=adapter:return None
        with self.engine.store.db() as db:
            row=db.execute("SELECT * FROM print_approvals WHERE state='awaiting_evidence' ORDER BY created LIMIT 1").fetchone()
            if not row:return None
            payload=json.loads(row['payload'])
            messages=select_sources(db,row['account'],row['thread_id'],payload['messages'])
            if payload.get('missing_quote_disclosed'):
                from hub.order_additions import fallback_sources
                messages=fallback_sources(messages)
        return dict(id=row['id'],messages=messages,reference='CHOT-IN-'+row['id'][:16],notice=payload.get('notice'),new_message_ids=payload.get('new_message_ids',[]))

    def evidence_saved(self, adapter, identity, result):
        from hub.media import decode_image
        route=self.route()
        if not route or route['account']!=adapter:raise ValueError('Wrong adapter')
        with self.engine.store.db() as db:
            row=db.execute("SELECT * FROM print_approvals WHERE id=? AND state='awaiting_evidence'",(identity,)).fetchone()
            if not row:raise ValueError('No pending print evidence')
            payload=json.loads(row['payload'])
            if result.get('error'):
                payload['reason']='Lưu bằng chứng NAS thất bại';state='review'
            else:
                raw=decode_image({'mime_type':'image/png','data':result['image_base64']})
                if not raw.startswith(b'\x89PNG\r\n\x1a\n') or result.get('source_message_ids')!=payload['messages']:
                    raise ValueError('Evidence source mismatch')
                payload['evidence']=result;state='ready'
            db.execute('UPDATE print_approvals SET state=?,payload=? WHERE id=?',(state,json.dumps(payload,ensure_ascii=False),identity))

    def pending_destinations(self,adapter):
        route=self.route()
        if not route or route['account']!=adapter or not route.get('delivery_enabled'):return []
        targets=route.get('destinations') or [{'account':adapter,'thread_id':route['thread_id']}]
        with self.engine.store.db() as db:
            return [t['account'] for t in targets if db.execute("SELECT 1 FROM print_approvals p WHERE state='ready' AND NOT EXISTS(SELECT 1 FROM print_deliveries d WHERE d.approval_id=p.id AND d.account=?) LIMIT 1",(t['account'],)).fetchone()]

    def claim(self, adapter, destination=None):
        route=self.route()
        if not route or route['account']!=adapter or not route.get('delivery_enabled'):return None
        targets=route.get('destinations') or [{'account':adapter,'thread_id':route['thread_id']}]
        target=next((t for t in targets if t['account']==(destination or adapter)),None)
        if not target:return None
        with self.engine.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM print_approvals p WHERE state='ready' AND NOT EXISTS(SELECT 1 FROM print_deliveries d WHERE d.approval_id=p.id AND d.account=?) ORDER BY created LIMIT 1",(target['account'],)).fetchone()
            if not row:return None
            payload=json.loads(row['payload'])
            if payload['destination']['thread_id']!=route['thread_id']:raise ValueError('Destination changed')
            from hub.evidence_document import select_sources
            try:select_sources(db,row['account'],row['thread_id'],payload['messages'])
            except ValueError:
                db.execute("UPDATE print_approvals SET state='review' WHERE id=?",(row['id'],));return None
            policy=self.engine.order_intake.policy(row['account'])
            cfg=self.engine.settings.inboxes[row['account']]
            mapping=self.engine.store.thread(account=row['account'],thread_id=row['thread_id'])
            if not policy or not mapping:return None
            if not capture_allowed(policy,cfg['channel'],row['thread_id'],mapping['display_name']):
                db.execute("UPDATE print_approvals SET state='blocked_policy' WHERE id=?",(row['id'],));return None
            source=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(row['account'],row['thread_id'],row['confirmation_id'])).fetchone()
            m=json.loads(source[0])
            if m.get('revision') or m.get('recalled'):
                db.execute("UPDATE print_approvals SET state='review' WHERE id=?",(row['id'],));return None
            newer=db.execute("SELECT 1 FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp')>? AND json_extract(payload,'$.origin')='customer' LIMIT 1",(row['account'],row['thread_id'],m['timestamp'])).fetchone()
            if payload.get('kind')=='reprint':
                selected=select_sources(db,row['account'],row['thread_id'],payload['messages'])
                newer=db.execute("SELECT 1 FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp')>? AND json_extract(payload,'$.origin')='customer' LIMIT 1",(row['account'],row['thread_id'],max(x['timestamp'] for x in selected))).fetchone()
            if newer and payload.get('kind') not in ('amendment','order_addition'):
                db.execute("UPDATE print_approvals SET state='review' WHERE id=?",(row['id'],));return None
            delivery_id=hashlib.sha256((row['id']+':'+target['account']).encode()).hexdigest()
            db.execute("INSERT INTO print_deliveries VALUES(?,?,?,?,?,NULL)",(delivery_id,row['id'],target['account'],target['thread_id'],'sending'))
            caption='CHỐT IN — '+mapping['display_name']+'\nKhách: '+m['sender']+'\nXác nhận: '+m['text']+'\nHồ sơ: CHOT-IN-'+row['id'][:16]
            if payload.get('kind') in ('amendment','reprint','order_addition'):caption=payload['notice']+'\nNhóm: '+mapping['display_name']+'\nBản cập nhật: CHOT-IN-'+row['id'][:16]
            return dict(id=delivery_id,approval_id=row['id'],account=target['account'],thread_id=target['thread_id'],caption=caption,image_base64=payload['evidence']['image_base64'])

    def delivered(self,adapter,identity,result):
        route=self.route()
        if not route or route['account']!=adapter:raise ValueError('Wrong adapter')
        state=result.get('state')
        if state not in ('confirmed','submitted','uncertain','blocked'):raise ValueError('Invalid delivery state')
        with self.engine.store.db() as db:
            row=db.execute("SELECT * FROM print_deliveries WHERE id=? AND state='sending'",(identity,)).fetchone()
            if not row:return
            result={k:result.get(k) for k in ('state','message_id','ack','client_id')}
            db.execute('UPDATE print_deliveries SET state=?,result=? WHERE id=?',(state,json.dumps(result),identity))
            targets=route.get('destinations') or [{'account':adapter,'thread_id':route['thread_id']}]
            states={r['account']:r['state'] for r in db.execute('SELECT account,state FROM print_deliveries WHERE approval_id=?',(row['approval_id'],))}
            complete=all(states.get(t['account'])=='confirmed' for t in targets)
            if complete:
                db.execute("UPDATE print_approvals SET state='confirmed' WHERE id=?",(row['approval_id'],))
            approval=db.execute('SELECT account,thread_id,payload FROM print_approvals WHERE id=?',(row['approval_id'],)).fetchone()
        if complete:
            is_change=json.loads(approval['payload']).get('kind')=='amendment'
            label='ĐÃ BÁO THAY ĐỔI SAU DUYỆT: ' if is_change else 'ĐÃ CHUYỂN DUYỆT IN: '
            if json.loads(approval['payload']).get('kind')=='order_addition':label='ĐÃ BÁO YÊU CẦU ĐẶT THÊM: '
            mapping=self.engine.store.thread(account=approval['account'],thread_id=approval['thread_id'])
            if mapping:self.engine.note(row['approval_id']+':print-complete',mapping['conversation'],label+'Bản tổng hợp ảnh và tin xác nhận đã gửi tới nhóm File In - Giấy In - Màng Pet trên các kênh đã cấu hình. Hồ sơ CHOT-IN-'+row['approval_id'][:16]+'. Việc này độc lập với tạo đơn ERP; cảnh báo thiếu thông tin ERP cần được xử lý riêng.',apply_capture=True)
        if state in ('uncertain','blocked','submitted'):
            mapping=self.engine.store.thread(account=approval['account'],thread_id=approval['thread_id'])
            if mapping:self.engine.note(identity+':print-delivery',mapping['conversation'],'CHUYỂN CHỐT IN CẦN KIỂM TRA: '+row['account']+' — '+state+'. Không tự gửi lại để tránh trùng.',apply_capture=True)
