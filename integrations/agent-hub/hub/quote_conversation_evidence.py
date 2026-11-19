"""Conversation screenshots are order evidence, never artwork or AI image inputs."""
import base64
import hashlib
import json
import re
import unicodedata


def fingerprint(message):
    keys = ('account', 'thread_id', 'message_id', 'sender_id', 'text',
            'timestamp', 'quoted_image', 'revision', 'recalled')
    value={k: message.get(k) for k in keys}
    value['timestamp']=float(value['timestamp'])
    value['revision']=int(value.get('revision') or 0)
    value['recalled']=bool(value.get('recalled'))
    if value.get('quoted_image'):
        value['quoted_image']=dict(value['quoted_image'],timestamp=float(value['quoted_image']['timestamp']))
    return hashlib.sha256(json.dumps(value,ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def explicit_extra(message):
    """Narrow text-only fast path; uncertainty falls back to normal analysis."""
    q = message.get('quoted_image') or {}
    if (message.get('revision') or message.get('recalled') or
        message.get('origin') != 'customer' or not q.get('resolved') or
        not all(q.get(k) for k in ('message_id', 'client_message_id', 'sender_id', 'timestamp')) or
        q['timestamp'] >= message['timestamp']):
        return None
    text = unicodedata.normalize('NFC', message.get('text', '')).casefold()
    text = re.sub(r'@\s*thiết\s*kế\b', '', text)
    if re.search(r'\?|\b(không|chưa|khoan|đừng|hủy|huỷ|nếu|bù|tổng|thiết kế|lên mẫu|làm mẫu)\b', text):
        return None
    if re.search(r'\b(mỗi|hoặc|hay)\b|[x×]\s*\d',text):return None
    matches = re.findall(r'\b(?:ra|làm|in|đặt|lấy)\s+(?:pet\s+)?(?:(?:e|em|anh|chị|tôi)\s+)?thêm\s+(\d+)\s*(pet|c|cái|chiếc|tấm|bộ|áo)\b', text)
    quantities = re.findall(r'(?<![\w.])(\d+)\s*(?:pet|c|cái|chiếc|tấm|bộ|áo)\b', text)
    if len(matches) != 1 or quantities != [matches[0][0]]:
        return None
    amount = int(matches[0][0])
    return amount if 0 < amount <= 1000000 else None


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS quote_conversation_evidence (
        account TEXT,thread_id TEXT,message_id TEXT,source_digest TEXT NOT NULL,
        quote_id TEXT NOT NULL,png BLOB NOT NULL,sha256 TEXT NOT NULL,
        provenance TEXT NOT NULL,PRIMARY KEY(account,thread_id,message_id))''')


def load(db, message):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='quote_conversation_evidence'").fetchone():
        return None
    row = db.execute('SELECT source_digest,quote_id,png,sha256 FROM quote_conversation_evidence WHERE account=? AND thread_id=? AND message_id=?',
        tuple(message[k] for k in ('account','thread_id','message_id'))).fetchone()
    if not row or row[0] != fingerprint(message) or row[1] != (message.get('quoted_image') or {}).get('message_id'):
        return None
    if hashlib.sha256(row[2]).hexdigest() != row[3]:
        raise ValueError('Conversation evidence hash mismatch')
    return {'mime_type':'image/png','data':base64.b64encode(row[2]).decode()}


def register(db, message, proof):
    if (proof.get('source_digest') != fingerprint(message) or
        proof.get('quote_id') != (message.get('quoted_image') or {}).get('message_id') or
        proof.get('method') != 'windows-msaa-printwindow-v1' or
        explicit_extra(message) is None or
        not any(a.get('error')=='file_link_expired_or_unavailable' for a in message.get('assets',[]))):
        raise ValueError('Conversation screenshot source mismatch')
    from hub.media import decode_image
    raw=decode_image(proof['image'])
    if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw)>4000000:
        raise ValueError('Invalid conversation screenshot')
    ensure(db)
    db.execute('INSERT OR IGNORE INTO quote_conversation_evidence VALUES(?,?,?,?,?,?,?,?)',
        (message['account'],message['thread_id'],message['message_id'],fingerprint(message),
         proof['quote_id'],raw,hashlib.sha256(raw).hexdigest(),json.dumps({'method':proof['method']})))


def try_prepare(intake, run, payload, messages):
    if len(messages) != 1 or payload.get('submitted_payload'):
        return False
    m = messages[0]
    quantity = explicit_extra(m)
    ready_image=bool(m.get('images'))
    if quantity is None or (not ready_image and not any(a.get('error')=='file_link_expired_or_unavailable' for a in m.get('assets',[]))):
        return False
    from hub.intake_lifecycle import reusable
    with intake.store.db() as db:
        image_hashes=[]
        if ready_image:
            from hub.evidence_document import select_sources
            sources=select_sources(db,run['account'],run['thread_id'],[m['message_id']])
            image_hashes=[hashlib.sha256(base64.b64decode(im['data'])).hexdigest() for im in sources[0]['images']]
            if not image_hashes:return False
        elif not load(db, m):
            intake.state(run['id'],'review',{'reason':'Ảnh trích dẫn cũ đã mất; chưa chụp/xác minh được đúng đoạn chat Zalo. Số lượng đã rõ trong tin chữ; không gọi AI đọc ảnh.','quote_screenshot_required':True})
            return True
        if not reusable(db, {'payload':json.dumps(m),'source_result':'{}'}):
            return False
    if not intake.accepts(m) or not intake.quiet_now(run, payload):
        return False
    binding = intake.resolve_customer_binding(run, payload['group_name'])
    if not binding:
        return False
    # An exact source reference found on ERP requires reconciliation, never replay.
    matches = intake.engine.erp.match_order(binding['customer_id'],m['message_id'])
    if matches.get('truncated') or matches.get('matches'):
        intake.state(run['id'],'review',{'reason':'ERP có tham chiếu tin nguồn này; đối soát, không tạo lại'})
        return True
    q = m['quoted_image']
    title='PET đặt thêm theo mẫu trích dẫn' if re.search(r'\bpet\b',m['text'],re.I) else 'Đặt thêm theo mẫu trích dẫn'
    evidence_note='Ảnh trích dẫn đã lưu làm bằng chứng.' if ready_image else 'Ảnh đính kèm là ảnh chụp hội thoại; file gốc cũ chưa tải được. Đối chiếu mẫu trước khi in.'
    note = (f"Đặt thêm {quantity} theo ảnh trích dẫn {q['message_id']}. "
            f"Tin đặt mới {m['message_id']}. {evidence_note}\n" + m['text'])
    payload.update(customer_binding=binding, request_id='chatwoot-id:'+run['id'],
        quote_evidence_order={'source_digest':fingerprint(m),'quantity':quantity,'image_hashes':image_hashes},
        image_groups_verified=True,
        orders=[{'ma_san_pham':None,'ten_mau':title,
            'so_luong':str(quantity),'ghi_chu_mau_do':note}])
    with intake.store.db() as db:
        changed=db.execute("UPDATE intake_runs SET state='awaiting_evidence',payload=?,result=? WHERE id=? AND state IN ('review','analyzing','waiting_details') AND json_extract(payload,'$.submitted_payload') IS NULL",
            (json.dumps(payload,ensure_ascii=False),json.dumps({'reason':'Số lượng đặt thêm rõ trong tin chữ; giữ nguồn trích dẫn, không gọi AI đọc ảnh'},ensure_ascii=False),run['id'])).rowcount
    return bool(changed)

