"""Explicit same-customer question/answer authorization for raster cleanup."""
import re
from hub.workflow_rules import normalize

def owner_restoration_consent(brief, approval, request_id):
    """A scoped owner command, never inferred from ordinary customer prose."""
    if not approval:return None
    if approval.get('authorized') is not True or approval.get('brief_id')!=brief.get('id'):
        raise ValueError('Phê duyệt phục hồi không khớp hồ sơ')
    image_id=approval.get('image_id')
    sources=[s for s in brief.get('sources',[]) if image_id and image_id in s.get('images',[])]
    if len(sources)!=1 or not request_id:raise ValueError('Phê duyệt phục hồi chưa gắn đúng một ảnh nguồn')
    src=sources[0]
    return {'method':'explicit_owner_restoration','owner_request_id':request_id,
            'question_message_id':'owner-request:'+request_id,'answer_message_id':'owner-approval:'+request_id,
            'account':brief['account'],'thread_id':brief['thread_id'],'sender_id':'owner',
            'source_message_ids':[src['message_id']],'image_id':image_id,
            'enhance_only':approval.get('enhance_only') is True}

def restoration_consent(context):
    batch=context.get('batch',[]);ids={m['message_id'] for m in batch}
    customers={m.get('sender_id') for m in batch if m.get('role')=='customer' and m.get('sender_id')}
    messages={m['message_id']:m for m in context.get('history',[])+batch}
    ordered=sorted(messages.values(),key=lambda m:m['timestamp'])
    for answer in reversed(ordered):
        if answer['message_id'] not in ids or answer.get('role')!='customer' or answer.get('sender_id') not in customers:continue
        text=normalize(answer.get('text',''))
        if not (re.search(r'\b(khong co (file|tep)|ko co (file|tep)|khong co dau|chi co (vay|vay thoi|nhieu day|hinh nay|anh nay)|co moi (hinh|anh) nay)\b',text) or re.fullmatch(r'(da |em |dạ )?(khong|ko) co( a| anh| chi| nhe)?[.! ]*',text)):continue
        if re.search(r'\b(se gui|de gui|gui sau|tim lai|co file roi)\b',text):continue
        # Only the most recent staff question; don't reuse unrelated old dialogue.
        previous=[m for m in ordered if m.get('role')=='staff' and 0<answer['timestamp']-m['timestamp']<=1800]
        if not previous:continue
        question=previous[-1];q=normalize(question.get('text',''))
        if not re.search(r'\b(file|tep)\b',q):continue
        if not re.search(r'\b(co|gui|cho|khong|ko)\b',q):continue
        other=[m for m in ordered if question['timestamp']<m['timestamp']<answer['timestamp'] and m.get('role')=='customer' and m.get('sender_id')!=answer.get('sender_id')]
        if other:continue
        # Bound consent to images from this customer in this short dialogue.
        # Multiple image messages need explicit evidence; never spend on a guess.
        candidates=[m for m in ordered if m.get('has_image') and m.get('sender_id')==answer['sender_id'] and 0<=answer['timestamp']-m['timestamp']<=1800]
        if not candidates:continue
        source=candidates[0]
        if candidates[-1]['timestamp']-source['timestamp']>300:continue
        if any(m.get('role')=='customer' and m.get('text','').strip() and not m.get('has_image') and source['timestamp']<m['timestamp']<candidates[-1]['timestamp'] for m in ordered):continue
        if any(m.get('has_image') and m.get('sender_id')!=answer['sender_id'] and source['timestamp']<m['timestamp']<=answer['timestamp'] for m in ordered):continue
        return {'question_message_id':question['message_id'],'answer_message_id':answer['message_id'],'sender_id':answer['sender_id'],'source_message_ids':[m['message_id'] for m in candidates],'account':context.get('account'),'thread_id':context.get('thread_id'),'method':'confirmed_no_design_file'}
    return None
