"""Customer assent to a staff quantity question, with read-only ERP reconciliation."""
import json,re
from decimal import Decimal
from hub.intake_quiet import human_activity

ACK=re.compile(r'^(?:ok|oke|okay|đúng|đúng rồi|vâng|dạ đúng|dạ ok)(?:\s+(?:anh|chị|em|ạ|nhé|nha))*[.!\s]*$',re.I)

def pair(customer, history, artwork_resolver=None):
    if customer.get('origin')!='customer' or not ACK.fullmatch(customer.get('text','').strip()):return None
    previous=[m for m in history if m['timestamp']<customer['timestamp'] and human_activity(m)]
    # Do not guess across an intervening human message, or an old discussion.
    if not previous:return None
    previous.sort(key=lambda m:m['timestamp'])
    question=previous[-1]
    quote=customer.get('quoted_image') or {}
    if quote.get('message_id'):
        matches=[m for m in previous if m['message_id']==quote['message_id']]
        if len(matches)!=1:raise ValueError('Không tìm được câu hỏi khách xác nhận')
        question=matches[0]
    text=question.get('text','')
    if question.get('origin')!='staff' or customer['timestamp']-question['timestamp']>3600:return None
    if not re.search(r'\bin\b',text,re.I) or not re.search(r'phải\s*(?:không|ko|k)|đúng\s*(?:không|ko)|\?',text,re.I):return None
    if re.search(r'\b(thêm|bù|test|thử|không in|chưa in|nếu)\b',text,re.I):
        raise ValueError('Khách xác nhận câu hỏi in thêm/test/điều kiện; cần kiểm tra đúng ý định')
    amounts=re.findall(r'(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(cái|chiếc|tấm|mét|bộ|áo)\b',text,re.I)
    if not amounts:
        amounts=[(n,'cái') for n in re.findall(r'\bin\s+(\d+)\s+(?:phải|đúng)',text,re.I)]
    if len(amounts)!=1:raise ValueError('Câu hỏi xác nhận chưa có một số lượng và đơn vị rõ ràng')
    # Literal model identity only. Never attach the nearest unrelated artwork.
    models=re.findall(r'\b[A-Z][A-Z0-9]*-[A-Z0-9_-]+(?:\.\d+)?\b',text)
    models+=re.findall(r'[“"]([^”"]{3,100})[”"]',text)
    models=list(dict.fromkeys(models))
    artwork = {}
    if not models and artwork_resolver:
        artwork = artwork_resolver(question, history)
        models = [artwork['model']]
    if len(models)!=1:raise ValueError('Khách đã xác nhận số lượng nhưng câu hỏi chưa chỉ rõ duy nhất mã/tên mẫu; cần nối ảnh/mẫu nội bộ')
    number=amounts[0][0]
    if re.fullmatch(r'\d{1,3}(?:\.\d{3})+',number):number=number.replace('.','')
    amount=Decimal(number.replace(',','.'))
    if amount<=0:raise ValueError('Số lượng xác nhận phải lớn hơn không')
    return dict(question_id=question['message_id'],question_text=text,confirmation_id=customer['message_id'],model=models[0],quantity=str(amount),unit=amounts[0][1],**{k:v for k,v in artwork.items() if k!='model'})

def reconcile(erp,customer_id,proof):
    result=erp.match_order(customer_id,proof['model'])
    if result.get('truncated') or 'matches' not in result:raise ValueError('ERP chưa trả đủ kết quả đối chiếu mẫu xác nhận')
    matches=result['matches']
    if not matches:
        if proof.get('linked_order_id'):raise ValueError('Ảnh đã có liên kết đơn nhưng ERP chưa trả lại đơn; cần đối soát')
        return None
    ids={m['order_id'] for m in matches}
    if proof.get('linked_order_id') and ids != {proof['linked_order_id']}:
        raise ValueError('Liên kết ảnh và kết quả ERP không thống nhất; không tạo thêm')
    if len(ids)!=1:raise ValueError('Mẫu xác nhận có nhiều đơn ERP; không tự chọn đơn gần nhất')
    oid=next(iter(ids));snapshot=erp.quantity_snapshot(customer_id,oid)
    lines=snapshot['lines']
    if len(lines)!=1:raise ValueError('Đơn đã có nhiều dòng; cần xác định dòng khách xác nhận')
    line=lines[0]
    name=line.get('ten_mau') or line.get('model_name')
    quantity=line.get('so_luong',line.get('quantity'))
    if not name or name.strip().casefold()!=proof['model'].strip().casefold() or quantity is None:
        raise ValueError('ERP tìm được đơn liên quan nhưng chưa khớp chính xác tên mẫu/dòng')
    if Decimal(str(quantity))!=Decimal(proof['quantity']):raise ValueError('Khách xác nhận số lượng khác đơn đã có; cần kiểm tra sửa đơn, không tạo thêm')
    return {'id':oid,'ma_don_hang':snapshot.get('order_ref',oid)}

def apply(intake,run,messages):
    proofs=[]
    for m in messages:
        if not ACK.fullmatch(m.get('text','').strip()):continue
        with intake.store.db() as d:
            rows=d.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp') BETWEEN ? AND ? ORDER BY revision DESC",(run['account'],run['thread_id'],m['timestamp']-3600,m['timestamp'])).fetchall()
        seen={}
        for row in rows:
            item=json.loads(row[0]);seen.setdefault(item['message_id'],item)
        def artwork_resolver(question,history):
            from hub.confirmation_artwork import resolve
            binding=intake.engine.customer_mappings.get(run['account'],run['thread_id'])
            if not binding:raise ValueError('Cần ánh xạ khách ERP trước khi nối ảnh xác nhận')
            return resolve(intake,run,question,history,binding)
        proof=pair(m,list(seen.values()),artwork_resolver)
        if proof:proofs.append((m,proof))
    if not proofs:return False
    allowed={proofs[0][0]['message_id'],proofs[0][1].get('image_source_id')}
    if len(proofs)!=1 or any(m['message_id'] not in allowed for m in messages):
        raise ValueError('Xác nhận số lượng nằm cùng nhiều nguồn/yêu cầu; cần kiểm tra liên kết trước khi ghi ERP')
    binding=intake.engine.customer_mappings.get(run['account'],run['thread_id'])
    if not binding:raise ValueError('Xác nhận số lượng cần ánh xạ khách ERP để đối chiếu đơn cũ')
    m,proof=proofs[0]
    existing=reconcile(intake.engine.erp,binding['customer_id'],proof)
    if existing:
        intake.state(run['id'],'duplicate',{'orders':[existing],'reason':'Khách xác nhận số lượng của mẫu đã có; không tạo thêm','quantity_confirmation':proof})
        return True
    # Derived evidence in memory only: retain raw customer capture unchanged.
    m['quantity_confirmation']=proof
    m['text'] += '\n[Xác nhận có đối chiếu: khách trả lời câu hỏi nhân viên '+proof['question_id']+': '+proof['question_text']+'; mẫu '+proof['model']+', số lượng '+proof['quantity']+' '+proof['unit']+'. ERP chưa có kết quả khớp.]'
    return False
