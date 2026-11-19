import hashlib
import json
import re
import unicodedata

from hub.evidence_document import select_sources
from hub.intake_intent import evidence
from hub.intake_lifecycle import reusable

SLIP_GROUPS = {'g1790239230897256718', 'g2671966061008128194'}


def folded(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold().replace('đ', 'd'))
                   if not unicodedata.combining(c))


def described_quantity(text):
    # The colour is optional. Accent folding applies only to recognition.
    match = re.fullmatch(r'\s*([1-9]\d{0,6})\s*(?:(?:cai|chiec)\s+)?(non|ao|tui)\s+(?:trang|do|den|vang|cam|hong|tim|nau|xam|xanh(?: la| bien| bich)?)(?:\s+(?:nha|nhe|a))?[.!]?\s*', folded(text))
    if match and int(match[1]) <= 1000000:
        return {'quantity': match[1], 'unit': {'non':'nón','ao':'áo','tui':'túi'}[match[2]]}


def choices(messages):
    result = {}
    for m in messages:
        text = m.get('text', '').strip()
        if m.get('origin') != 'customer' or text.startswith('['):
            continue
        numbers = re.findall(r'(?<![\w.,])([1-9]\d*(?:\.\d{3})*)(?![\d.,])', text)
        values = list(dict.fromkeys(n.replace('.', '') for n in numbers if len(n.replace('.', '')) <= 7 and int(n.replace('.', '')) <= 1000000))
        if values:
            result[m['message_id']] = values
    return result


def version(messages):
    encoded = json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def eligible(run, p, res):
    return (run['state']=='review' and run['thread_id'] not in SLIP_GROUPS
            and bool(res.get('uncovered_quantity_message_ids')) and not res.get('orders')
            and not any(p.get(k) for k in ('orders','request_id','submitted_payload','model_parent','proposal_parent')))


def lines_for(messages, decisions):
    candidates = choices(messages)
    if not isinstance(decisions, dict) or set(decisions) != set(candidates):
        raise ValueError('Cần duyệt đủ các tin chứa số trong cụm.')
    lines = []
    for mid, values in candidates.items():
        decision = decisions[mid]
        if decision in ('sample','repeat','context'):
            continue
        if decision not in values:
            raise ValueError('Số lượng đã chọn không khớp tin khách.')
        lines.append({'ma_san_pham':None,'ten_mau':'Đơn theo tin khách','so_luong':decision,'ghi_chu_mau_do':''})
    if not 1 <= len(lines) <= 30:
        raise ValueError('Chọn từ 1 đến 30 dòng đặt hàng.')
    return lines


def sources_for_run(db, run, payload):
    marker = payload.get('text_quantity_order', {})
    selected = payload['messages']
    if marker.get('operator_decisions'):
        messages = evidence(db,run,payload)
        if version(messages)!=marker['source_version'] or lines_for(messages,marker['operator_decisions'])!=payload['orders']:
            raise ValueError('Nguồn hoặc số lượng đã duyệt thay đổi.')
        selected = marker['evidence_ids']
    return select_sources(db,run['account'],run['thread_id'],selected)


def approve(engine, data):
    intake = engine.order_intake
    with engine.lock, engine.store.db() as db:
        run = db.execute('SELECT * FROM intake_runs WHERE id=?',(data['id'],)).fetchone()
        if not run:
            raise ValueError('Không tìm thấy hồ sơ.')
        p = json.loads(run['payload'])
        res = json.loads(run['result'] or '{}')
        if not eligible(run,p,res):
            raise ValueError('Hồ sơ đã được xử lý hoặc không còn chờ duyệt số lượng.')
        messages = evidence(db,run,p)
        if len(messages)!=len(p['messages']) or version(messages)!=data['version']:
            raise ValueError('Tin nguồn đã thay đổi. Làm mới hồ sơ.')
        lines = lines_for(messages,data['decisions'])
        if not engine.intake_management.enabled(run['account']) or not engine.settings.erp_write:
            raise ValueError('Kênh lên đơn đang tắt.')
        if any(not intake.accepts(m) or not reusable(db,{'payload':json.dumps(m),'source_result':'{}'}) for m in messages):
            raise ValueError('Nguồn đã được dùng hoặc quyền nhận tin đã đổi.')
        binding = engine.customer_mappings.get(run['account'],run['thread_id'])
        if not binding:
            raise ValueError('Cần ánh xạ khách hàng trước khi duyệt.')
        selected=data.get('evidence_ids')
        if not isinstance(selected,list) or not 1 <= len(selected) <= 20 or len(selected)!=len(set(selected)) or not set(selected)<=set(p['messages']):
            raise ValueError('Chọn 1–20 tin của cụm làm bằng chứng.')
        if any(mid not in selected for mid,v in data['decisions'].items() if v.isdecimal()):
            raise ValueError('Ảnh chứng cứ cần có các tin chốt số lượng.')
        sources = select_sources(db,run['account'],run['thread_id'],selected)
        from hub.text_quantity_orders import source_proof
        for mid, value in data['decisions'].items():
            if value.isdecimal():
                found = engine.erp.match_order(binding['customer_id'],mid)
                if found.get('truncated') or found.get('matches'):
                    raise ValueError('Tin đặt đã có tham chiếu ERP hoặc kết quả đối chiếu chưa đủ.')
        p.update(customer_binding=binding, request_id='chatwoot-id:'+run['id'], orders=lines,
                 image_groups_verified=True, text_quantity_order={'operator_decisions':data['decisions'],
                 'evidence_ids':selected,'source_version':data['version'],'sources':source_proof(sources),'review_reason':res.get('reason')})
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT * FROM intake_runs WHERE id=?',(run['id'],)).fetchone()
        if current['state']!='review' or current['payload']!=run['payload'] or current['result']!=run['result']:
            raise ValueError('Hồ sơ đã thay đổi. Làm mới trước khi duyệt.')
        if version(evidence(db,current,p))!=data['version']:
            raise ValueError('Nguồn đã thay đổi trong khi duyệt.')
        if any(not reusable(db,{'payload':json.dumps(m),'source_result':'{}'}) for m in messages):
            raise ValueError('Nguồn vừa được xử lý ở hồ sơ khác.')
        clash=db.execute("""SELECT 1 FROM intake_runs r,json_each(r.payload,'$.messages') j
              WHERE r.id<>? AND r.account=? AND r.thread_id=?
              AND r.state IN ('awaiting_evidence','evidence_ready','sending','uncertain')
              AND j.value IN (SELECT value FROM json_each(?)) LIMIT 1""",
              (run['id'],run['account'],run['thread_id'],json.dumps(p['messages']))).fetchone()
        if clash:raise ValueError('Có hồ sơ khác đang xử lý cùng tin. Cần đối chiếu trước khi duyệt.')
        db.execute("UPDATE intake_runs SET state='awaiting_evidence',payload=?,result=? WHERE id=?",
                   (json.dumps(p,ensure_ascii=False),json.dumps({'reason':'Đã duyệt số lượng cả cụm, chờ ảnh bằng chứng.'},ensure_ascii=False),run['id']))
    return {'state':'awaiting_evidence','lines':len(lines)}
