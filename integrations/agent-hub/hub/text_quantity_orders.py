"""Owner policy: explicit customer text quantity creates a new ERP order without AI."""
import json
import re
import unicodedata
from hub.quote_conversation_evidence import fingerprint

METER_AMOUNT = r'(?<![\w.,])\d+(?:[.,]\d+)*\s*(?:mét|met|m)\b'

def explicit_quantity(message):
    if message.get('origin')!='customer' or message.get('revision') or message.get('recalled'):return None
    from hub.color_quantity import parse
    breakdown=parse(message)
    if breakdown is not None:return None if breakdown.get('invalid') else breakdown
    text=unicodedata.normalize('NFC',message.get('text','')).casefold()
    if re.search(METER_AMOUNT, text):
        # A standalone production request is a quantity. Widths, alternatives
        # and mixed instructions need review before any sibling line is sent.
        meter = re.fullmatch(
            r'\s*(?:làm|in|chạy|đặt|lấy|sl|số lượng)\s*:?\s*'
            r'([1-9]\d*(?:\.\d{3})*|0)(?:,(\d{1,2}))?\s*(mét|met|m)'
            r'(?:\s+(?:ạ|nha|nhé|nhe))?[.!]?\s*', text)
        if not meter:
            # Production length followed by fabric/lot context, e.g. INJAE.
            # One meter amount only; questions, alternatives and corrections stay review.
            ambiguous = re.search(r'\?|\b(không|chưa|khoan|đừng|hủy|huỷ|nếu|hoặc|hay|bù|thêm|tổng|thiếu)\b', text)
            if not ambiguous and len(re.findall(METER_AMOUNT, text)) == 1:
                meter = re.fullmatch(
                    r'\s*(?:lô\s+[\w.-]+\s*[:：,-]?\s*)?(?:in|chạy|làm|đặt)\s+'
                    r'([1-9]\d*(?:\.\d{3})*|0)(?:,(\d{1,2}))?\s*(mét|met|m)'
                    r'\s+trên\s+[^\n]+\s*', text)
            if not meter and not ambiguous and len(re.findall(METER_AMOUNT, text)) == 1:
                # Natural customer request: mentions, deadline and fabric notes
                # may surround the quantity. Bind amount to a production verb,
                # not to dates, lot IDs, fabric widths or image dimensions.
                meter = re.search(
                    r'\b(?:in(?:\s+vải(?=\s+cho\b))?|chạy|làm|đặt|lấy)\s+'
                    r'(?:(?:hộ|giúp|giùm|dùm|cho|em|e|anh|a|chị|c|mình|tôi|bên)\s+)*'
                    r'([1-9]\d*(?:\.\d{3})*|0)(?:,(\d{1,2}))?\s*(mét|met|m)\b'
                    r'(?!\s*(?:[x×]|ngang\b|rộng\b|cao\b|dài\b))', text)
            if not meter:
                return None
        from decimal import Decimal
        amount = Decimal(meter[1].replace('.', '') + '.' + (meter[2] or '0'))
        if not 0 < amount <= 1000000:
            return None
        return {'quantity':format(amount.normalize(), 'f'), 'unit':'mét'}
    # Explicit additive stock/new-production allocation, one sample and one total.
    allocation=re.fullmatch(r'\s*([1-9]\d*(?:\.\d{3})*)\s*(?:cái|c)?\s*hàng\s+(?:có\s+)?sẵn\s*\+\s*([1-9]\d*(?:\.\d{3})*)\s*(?:cái|c)?\s*(?:sx|sản\s+xuất)\s+mới\s*[.!]?\s*',text)
    if allocation:
        stock,new=(int(x.replace('.','')) for x in allocation.groups())
        if stock+new<=1000000:
            return {'quantity':str(stock+new),'unit':'cái','model_name':'Đơn theo tin khách (cái)',
                    'line_note':f'{stock} hàng sẵn + {new} sản xuất mới'}
    from hub.quantity_review import described_quantity
    described=described_quantity(text)
    if described:return described
    each=re.fullmatch(r'\s*(?:(?:in|làm|đặt|lấy)\s+)?mỗi\s+mẫu\s*[:：]?\s*([1-9]\d*(?:\.\d{3})*)\s*(cái|chiếc|tấm|c)\s*(?:ạ|nha|nhé|nhe)?[.!]?\s*',text)
    if each:
        amount=int(each[1].replace('.',''))
        if amount<=1000000:return {'quantity':str(amount),'unit':{'c':'cái'}.get(each[2],each[2]),'per_image':True}
    if re.search(r'\?|\b(không|chưa|khoan|đừng|hủy|huỷ|nếu|tổng|còn|thiếu|bù|mỗi|hoặc|hay|đã|giao|nhận)\b|[x×]\s*\d',text):return None
    # Owner policy: dots never represent decimals in customer quantities.
    text=text.replace('.','')
    bare_quantity=re.fullmatch(r'\s*[1-9]\d*\s*(?:cặp|cái|chiếc|tấm|bộ|áo|nón|logo|pet|c)\s*(?:hàng\s+(?:có\s+)?sẵn\s*)?(?:ạ|nha|nhé|nhe)?[.!]?\s*',text)
    if not bare_quantity and not re.search(r'\b(in|đặt|làm|lấy|chạy|ra|giúp|giùm|dùm|sl|số lượng)\b',text):return None
    matches=re.findall(r'(?<![\w.,])([1-9]\d*)\s*(cặp|cái|chiếc|tấm|bộ|áo|nón|logo|pet|c)\b',text)
    if not matches:
        bare=re.fullmatch(r'\s*(?:sl|số lượng)\s*[:：]?\s*([1-9]\d*)\s*(?:ạ|nha|nhé|nhe)?[.!]?\s*',text)
        if not bare:
            bare=re.fullmatch(r'\s*(?:làm|in|đặt|lấy)\s+(?:cho\s+)?(?:em|anh|chị|c|mình|tôi)\s+([1-9]\d*)\s*(?:cái)?\s*(?:ạ|nha|nhé|nhe)?[.!]?\s*',text)
        if bare:matches=[(bare[1],'chưa ghi đơn vị')]
    if len(matches)!=1:return None
    amount=int(matches[0][0])
    if amount>1000000:return None
    unit={'c':'cái','pet':'cái'}.get(matches[0][1],matches[0][1])
    return {'quantity':str(amount),'unit':unit}

def uncovered_quantities(messages):
    """Never silently consume quantity-bearing customer text as mere context."""
    result=[]
    for m in messages:
        if m.get('origin')!='customer' or m.get('revision') or m.get('recalled'):continue
        text=unicodedata.normalize('NFC',m.get('text','')).casefold()
        candidate=re.search(r'(?<!\w)\d[\d.,]*\s*(?:cặp|cái|chiếc|tấm|bộ|áo|nón|logo|pet|c)\b|\b(?:sl|số lượng)\s*[:：]?\s*\d',text)
        meter_request = re.search(METER_AMOUNT, text) and re.search(r'\b(?:làm|in|chạy|đặt|lấy|sl|số lượng)\b', text)
        if (candidate or meter_request) and not explicit_quantity(m):result.append(m['message_id'])
    return result

def quantity_groups(messages):
    from hub.color_quantity import groups
    selected=[explicit_quantity(m) for m in messages if explicit_quantity(m)]
    if selected and all(q.get('model_name') for q in selected):return groups(messages)
    from hub.order_groups import image_groups
    result=[]
    for image_group in image_groups(messages):
        current=[];has_quantity=False
        for _,m in image_group:
            quantity=explicit_quantity(m)
            if quantity and has_quantity:
                if not (m.get('quoted_image') or m.get('quoted_file')):return []
                result.append(current);current=[];has_quantity=False
            current.append(m);has_quantity|=bool(quantity)
        if current:result.append(current)
    return [g for g in result if sum(bool(explicit_quantity(m)) for m in g)==1]


def source_proof(messages):
    import hashlib,base64
    return {m['message_id']:{'digest':fingerprint(m),'images':[hashlib.sha256(base64.b64decode(im['data'])).hexdigest() for im in m.get('images',[])]} for m in messages}

def customer_image_sources(messages):
    """One original customer photo = one sample. Staff/quoted images are not samples."""
    import hashlib,base64
    out=[];seen=set()
    for m in messages:
        if m.get('origin')!='customer' or m.get('revision') or m.get('recalled') or m.get('quoted_image'):continue
        images=m.get('images',[])
        if m.get('conversation_screenshot'):images=images[:-1]
        for index,im in enumerate(images):
            digest=hashlib.sha256(base64.b64decode(im['data'])).hexdigest()
            if digest in seen:continue
            seen.add(digest);out.append({'message_id':m['message_id'],'image_index':index,'sha256':digest})
    return out

def quantity_lines(quantity,run_id,photos):
    if quantity.get('per_image'):
        if not 1<=len(photos)<=30:raise ValueError('Cần 1–30 ảnh khách gửi để tạo dòng theo mỗi mẫu')
        return [{'ma_san_pham':None,'ten_mau':'Mẫu theo ảnh khách '+str(i+1),
                 'so_luong':quantity['quantity'],'ghi_chu_mau_do':'',
                 'print_position_group':'each-image:'+run_id} for i in range(len(photos))]
    return [{'ma_san_pham':None,'ten_mau':quantity.get('model_name') or 'Đơn theo tin khách ('+quantity['unit']+')',
             'so_luong':quantity['quantity'],'ghi_chu_mau_do':quantity.get('line_note','')}]


def validate_quantity_sources(marker,messages):
    if marker.get('batch_items'):
        items=[{'message_id':m['message_id'],'details':explicit_quantity(m)} for m in messages if explicit_quantity(m)]
        return not uncovered_quantities(messages) and items==marker['batch_items'] and marker['sources']==source_proof(messages)
    if marker.get('operator_decisions'):
        return marker['sources']==source_proof(messages)
    if uncovered_quantities(messages):return False
    quantities=[m for m in messages if explicit_quantity(m)]
    if len(quantities)!=1:return False
    m=quantities[0]
    expected={'quantity':marker['quantity'],'unit':marker['unit']}
    if marker.get('model_name'):expected.update(model_name=marker['model_name'],line_note=marker.get('line_note',''))
    if marker.get('per_image'):expected['per_image']=True
    if explicit_quantity(m)!=expected:return False
    if marker.get('per_image') and (not marker.get('image_sources') or marker['image_sources']!=customer_image_sources(messages)):return False
    if marker.get('sources'):
        return marker.get('quantity_message_id')==m['message_id'] and marker['sources']==source_proof(messages)
    return len(messages)==1 and fingerprint(m)==marker['source_digest']


def try_prepare(intake,run,payload,messages,*,batch=False):
    if payload.get('submitted_payload') or payload.get('request_id'):return False
    if uncovered_quantities(messages):return False
    quantities=[m for m in messages if explicit_quantity(m)]
    if not quantities or (not batch and len(quantities)!=1):return False
    m=quantities[0];quantity=explicit_quantity(m)
    if not quantity:return False
    if not all(intake.accepts(item) for item in quantities) or not intake.quiet_now(run,payload):return False
    from hub.color_quantity import pending_media
    if any(explicit_quantity(item).get('model_name') for item in quantities) and any(pending_media(x) for x in messages):
        intake.state(run['id'],'review',{'reason':'Đã rõ mẫu và tổng '+quantity['quantity']+' cái; ảnh đính kèm chưa tải được, cần lấy đủ ảnh trước khi tạo đơn.','proposed_orders':quantity_lines(quantity,run['id'],[])})
        return True
    from hub.intake_lifecycle import reusable
    from hub.evidence_document import select_sources
    with intake.store.db() as db:
        sources=select_sources(db,run['account'],run['thread_id'],[x['message_id'] for x in messages])
        source=next(x for x in sources if x['message_id']==m['message_id'])
        if any(not reusable(db,{'payload':json.dumps(x),'source_result':'{}'}) for x in messages):return False
        from hub.previous_image_batch import select as previous_images
        previous=previous_images(db,run,payload,sources)
        current_sources=sources
        if previous:
            sources=sorted(previous['sources']+sources,key=lambda x:(x['timestamp'],x['message_id']))
    if any(x.get('quoted_image') and not x.get('images') for x in sources):
        intake.state(run['id'],'review',{'reason':'Số lượng đã rõ; cần chụp đúng đoạn chat Zalo có ảnh trích dẫn làm bằng chứng trước khi lên đơn.','quote_screenshot_required':True})
        return True
    binding=intake.resolve_customer_binding(run,payload['group_name'])
    if not binding:return False
    photos=customer_image_sources(sources) if quantity.get('per_image') else []
    if quantity.get('per_image') and not 1<=len(photos)<=30:
        intake.state(run['id'],'review',{'reason':'Mỗi mẫu đã có số lượng; cần 1–30 ảnh khách gửi đã tải đủ, không tính ảnh nhân viên.'})
        return True
    # Only check whether THIS incoming message was already processed, not an old order/model.
    for item in quantities:
        existing=intake.engine.erp.match_order(binding['customer_id'],item['message_id'])
        if existing.get('truncated') or existing.get('matches'):
            intake.state(run['id'],'review',{'reason':'Tin đặt này đã có tham chiếu ERP; không tạo trùng'})
            return True
    payload['messages']=[x['message_id'] for x in sources]
    if previous:
        payload['previous_image_batch']={k:v for k,v in previous.items() if k!='sources'}
    payload.update(customer_binding=binding,request_id='chatwoot-id:'+run['id'],
        text_quantity_order={'source_digest':fingerprint(source),'quantity_message_id':m['message_id'],'sources':source_proof(sources),**quantity,**({'image_sources':photos} if quantity.get('per_image') else {})},image_groups_verified=True,
        orders=quantity_lines(quantity,run['id'],photos))
    if batch:
        items=[{'message_id':item['message_id'], 'details':explicit_quantity(item)} for item in quantities]
        payload['text_quantity_order']={'batch_items':items,'sources':source_proof(sources)}
        payload['orders']=[quantity_lines(item['details'],run['id'],[])[0] for item in items]
    with intake.store.db() as db:
        if previous:
            db.execute('BEGIN IMMEDIATE')
            checked=previous_images(db,run,payload,current_sources)
            if not checked or checked['run_id']!=previous['run_id'] or source_proof(checked['sources'])!=source_proof(previous['sources']):
                return False
        changed=db.execute("UPDATE intake_runs SET state='awaiting_evidence',payload=?,result=? WHERE id=? AND state IN ('review','analyzing','waiting_details') AND json_extract(payload,'$.request_id') IS NULL AND json_extract(payload,'$.submitted_payload') IS NULL",
          (json.dumps(payload,ensure_ascii=False),json.dumps({'reason':'Số lượng rõ trong tin chữ; lên đơn mới, không nhận diện ảnh/xác minh mẫu bằng AI'},ensure_ascii=False),run['id'])).rowcount
    return bool(changed)


def split_explicit(intake,run,payload,messages):
    if len(messages)<2 or payload.get('request_id') or payload.get('submitted_payload'):return False
    uncovered=uncovered_quantities(messages)
    if uncovered:
        from hub.text_quantity_policy import total_quantity_request
        if total_quantity_request(messages):return False
        intake.state(run['id'],'review',{'reason':'Cụm còn tin có số lượng chưa xác định rõ; không tạo thiếu một phần. Nhân viên kiểm tra cả cụm.','uncovered_quantity_message_ids':uncovered})
        return True
    from hub.quantity_review import described_quantity, folded
    quantities=[(m,explicit_quantity(m)) for m in messages]
    ambiguous=[m['message_id'] for m,q in quantities if q and (
        (q['quantity']=='1' and re.search(r'\b1\s*(?:cai\s+)?mau\b',folded(m.get('text','')))) or
        (described_quantity(m.get('text','')) and sum(1 for _,other in quantities if other and other['quantity']==q['quantity'])>1))]
    if ambiguous:
        intake.state(run['id'],'review',{'reason':'Cần phân biệt tin đặt với yêu cầu làm mẫu hoặc số lượng được nhắc lại.','uncovered_quantity_message_ids':ambiguous})
        return True
    groups=quantity_groups(messages)
    selected=[m for m in messages if explicit_quantity(m)]
    if any(explicit_quantity(m).get('per_image') for m in selected):
        if len(selected)==1:return False
        intake.state(run['id'],'review',{'reason':'Cụm có yêu cầu mỗi mẫu kèm số lượng khác; cần xác nhận phạm vi, không tự nhân hoặc bỏ số lượng.'})
        return True
    # Several explicit requests in one collection window are independent orders.
    if len(selected)<2:return False
    covered=[m['message_id'] for g in groups for m in g if explicit_quantity(m)]
    if len(groups)!=len(selected) or sorted(covered)!=sorted(m['message_id'] for m in selected):
        intake.state(run['id'],'review',{'reason':'Có nhiều số lượng nhưng chưa tách rõ mẫu/ảnh tương ứng; không tạo thiếu một phần.','quantity_message_ids':[m['message_id'] for m in selected]})
        return True
    prepared=try_prepare(intake,run,payload,messages,batch=True)
    if not prepared:
        intake.state(run['id'],'review',{'reason':'Chưa đủ điều kiện chuẩn bị tất cả dòng sản phẩm trong cùng đơn.'})
    return True
