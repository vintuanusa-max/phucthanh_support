"""Post-approval change notices. Never silently reinterpret a new photo as approved."""
import hashlib
import json
import re
import time

from hub.order_policy import capture_allowed, key


def quantities(text):
    values = re.findall(r'(?<![\w.,])\d+(?:[.,]\d+)?\s*(?:cái|chiếc|áo|bộ|c)(?!\w)', key(text))
    values += re.findall(r'(?:số lượng|sl)\s*[:=]?\s*\d+(?:[.,]\d+)?', key(text))
    return list(dict.fromkeys(values))


def relevant(message):
    text=key(message.get('text'))
    return bool(message.get('images') or message.get('attachments') or quantities(text) or re.fullmatch(r'\d+(?:[.,]\d+)?',text)
                or re.search(r'\b(sửa|đổi|thay|tăng|giảm|hủy|huỷ|dừng|khoan|chốt lại|duyệt lại|in lại|lấy mẫu|mẫu mới|thêm|bớt)\b',text))


def correction(text):
    return bool(re.search(r'\b(sửa|đổi|thay|tăng|giảm|hủy|huỷ|dừng|khoan|bớt)\b', key(text)))


def linked_changes(fresh, root, confirmation, original_ids, unique_recent):
    """Require correction intent AND an explicit reference, never group recency alone."""
    sender = confirmation.get('sender_id') or key(confirmation.get('sender'))
    selected = []
    for m in fresh:
        if m['timestamp'] <= confirmation['timestamp'] or m.get('recalled'):
            continue
        if (m.get('sender_id') or key(m.get('sender'))) != sender:
            continue
        text = key(m.get('text'))
        quote = m.get('quoted_image') or {}
        exact = (quote.get('resolved') and quote.get('message_id') in original_ids) or ('chot-in-'+root[:16] in text)
        verbal = unique_recent and 0 < m['timestamp']-confirmation['timestamp'] <= 900 and bool(re.search(r'(đơn|mẫu) (vừa|mới) (chốt|duyệt)', text))
        new_order = bool(re.search(r'(đơn mới|đơn khác|mẫu khác|làm mẫu|lm mẫu)', text))
        if new_order:
            if selected: break
            continue
        if correction(text) and (exact or verbal):
            selected.append(m)
        elif selected and 0 <= m['timestamp']-selected[-1]['timestamp'] <= 120 and relevant(m):
            if quote and not exact: break
            selected.append(m)
        elif selected:
            break
    return selected[:8]


def describe(old, changes, root, version, ambiguous=False):
    old_text=[m['text'] for m in old if m.get('text') and not m['text'].startswith('[Ảnh')]
    new_text=[m['text'] for m in changes if m.get('text') and not m['text'].startswith('[Ảnh')]
    before=' | '.join(old_text[-3:]) or 'Hồ sơ trước không có nội dung chữ xác định số lượng'
    after=' | '.join(new_text[-5:]) or 'Khách gửi ảnh/file mới, chưa có lời xác nhận thay mẫu'
    photos=[m for m in changes if m.get('images')]
    explicit_swap=any(re.search(r'\b(đổi|thay|lấy mẫu|mẫu mới)\b',key(m.get('text'))) for m in changes)
    lines=[f'THAY ĐỔI SAU DUYỆT — LẦN {version}',
           'TẠM DỪNG IN THEO BẢN CŨ — nhân viên kiểm tra thay đổi trước khi in tiếp.',
           'Hồ sơ gốc: CHOT-IN-'+root[:16],
           'Số lượng/nội dung trước (nguyên văn): '+before[:450],
           'Tin mới của khách (nguyên văn): '+after[:900]]
    if photos:
        lines.append('Ảnh: có ảnh mới đề nghị thay mẫu; CHƯA TỰ COI LÀ ĐÃ DUYỆT.' if explicit_swap else
                     'Ảnh: có ảnh mới sau duyệt; CHƯA XÁC ĐỊNH là thay mẫu hay đơn mới. Không tự thay ảnh cũ.')
    else:
        lines.append('Ảnh: chưa có ảnh mẫu mới trong lượt bổ sung này.')
    if ambiguous:lines.append('CHƯA XÁC ĐỊNH CHẮC HỒ SƠ: nhóm có nhiều lượt duyệt/người đặt. Nhân viên đối chiếu trước khi áp dụng.')
    if any(m.get('attachments') for m in changes):lines.append('Có file/ảnh chưa đọc được: kiểm tra tệp gốc trên NAS hoặc hội thoại.')
    lines.append('Thông báo này cập nhật hồ sơ duyệt in; không tự sửa đơn ERP hoặc cho phép tiếp tục in.')
    return '\n'.join(lines)


def poll_changes(owner):
    route=owner.route()
    if not route or not route.get('changes_enabled_after'):return False
    engine=owner.engine
    with engine.store.db() as db:
        roots=db.execute("SELECT p.* FROM print_approvals p WHERE json_extract(p.payload,'$.kind') IS NULL AND EXISTS(SELECT 1 FROM print_deliveries d WHERE d.approval_id=p.id) ORDER BY p.created DESC").fetchall()
    grouped={}
    for root in roots:grouped.setdefault((root['account'],root['thread_id']),[]).append(root)
    for (account,thread),candidates in grouped.items():
        from hub.quality_monitor import monitored
        if monitored(account,thread):continue
        cfg=engine.settings.inboxes.get(account,{})
        policy=engine.order_intake.policy(account)
        mapping=engine.store.thread(account=account,thread_id=thread)
        if not policy or not mapping or not capture_allowed(policy,cfg.get('channel'),thread,mapping['display_name']):continue
        with engine.store.db() as db:
            # A rolling day bounds implicit association. Older explicit corrections still
            # require staff to identify the order; never silently attach by group name.
            rows=db.execute("SELECT c.payload FROM captures c WHERE c.account=? AND c.thread_id=? AND json_extract(c.payload,'$.timestamp')>=? AND NOT EXISTS(SELECT 1 FROM print_change_sources x WHERE x.account=c.account AND x.thread_id=c.thread_id AND x.message_id=c.message_id) ORDER BY json_extract(c.payload,'$.timestamp')",(account,thread,max(route['changes_enabled_after'],time.time()-86400))).fetchall()
            fresh=[json.loads(r[0]) for r in rows]
            internal={key(n) for n in policy.get(cfg.get('channel','')+'_internal_members',[])}
            fresh=[m for m in fresh if m.get('origin')=='customer' and m.get('direction')=='incoming' and key(m.get('sender')) not in internal]
            if not fresh:continue
            # A short quiet window collects "change qty" followed by the actual value.
            if fresh[-1]['timestamp']>time.time()-30:continue
            matched=[]
            for r in candidates:
                src=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(account,thread,r['confirmation_id'])).fetchone()
                if src:
                    c=json.loads(src[0])
                    if c['timestamp']<fresh[-1]['timestamp']:matched.append((r,c))
            if not matched:continue
            selected_roots=[]
            for candidate, confirm in matched:
                original=json.loads(candidate['payload']).get('messages',[])
                recent=[c for _,c in matched if 0 < fresh[-1]['timestamp']-c['timestamp'] <= 900]
                selected=linked_changes(fresh,candidate['id'],confirm,original,len(recent)==1)
                if selected:selected_roots.append((candidate,confirm,selected))
            if len(selected_roots)!=1:continue
            root,confirmation,changes=selected_roots[0]
            previous=db.execute("SELECT payload FROM print_approvals WHERE json_extract(payload,'$.root_id')=? AND COALESCE(json_extract(payload,'$.invalidated'),0)=0 AND COALESCE(json_extract(payload,'$.correction_notice'),0)=0 ORDER BY created DESC LIMIT 1",(root['id'],)).fetchone()
            prior=json.loads(previous[0]) if previous else json.loads(root['payload'])
            version=int(prior.get('change_version',0))+1
            old_ids=prior.get('messages',[])[-12:]
            old=[json.loads(db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(account,thread,mid)).fetchone()[0]) for mid in old_ids]
            ids=list(dict.fromkeys(old_ids+[m['message_id'] for m in changes]))
            ambiguous=False
            notice=describe(old,changes,root['id'],version,ambiguous)
            identity=hashlib.sha256(json.dumps(['print-change',account,thread,root['id'],[m['message_id'] for m in changes]]).encode()).hexdigest()
            payload={'kind':'amendment','root_id':root['id'],'change_version':version,'destination':route,
                     'confirmation':changes[-1]['message_id'],'messages':ids,'notice':notice,
                     'new_message_ids':[m['message_id'] for m in changes]}
            db.execute('BEGIN IMMEDIATE')
            if any(db.execute('SELECT 1 FROM print_change_sources WHERE account=? AND thread_id=? AND message_id=?',(account,thread,m['message_id'])).fetchone() for m in changes):continue
            db.execute('INSERT OR IGNORE INTO print_approvals VALUES(?,?,?,?,?,?,?)',(identity,account,thread,changes[-1]['message_id'],'awaiting_evidence',json.dumps(payload,ensure_ascii=False),time.time()))
            exists=db.execute('SELECT id FROM print_approvals WHERE id=?',(identity,)).fetchone()
            if not exists:continue
            for m in changes:db.execute('INSERT INTO print_change_sources VALUES(?,?,?,?)',(account,thread,m['message_id'],identity))
        return True
    return False
