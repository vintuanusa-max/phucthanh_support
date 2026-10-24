"""Bridge accepted Drive orders to existing artwork review; never creates ERP orders."""
import json,time
from hub.store import event_key

def collect_drive_order(engine,run,payload,messages):
    if not any(m.get('images') or any(a.get('state')=='ready' and a.get('name','').lower().endswith(('.pdf','.ai')) for a in m.get('assets',[])) for m in messages):return
    identity=event_key('drive-order-design-v1',run['id'])
    with engine.store.db() as d:
        if d.execute('select 1 from design_briefs where run_id=?',(run['id'],)).fetchone():return
        sources=[{**m,'role':'customer','chatwoot_message_id':None} for m in messages]
        title=' / '.join(x.get('ten_mau') or 'Mẫu khách đặt' for x in payload.get('orders',[]))
        brief={'title':title,'kind':'design_clarification','source_message_ids':[m['message_id'] for m in messages],
          'requirements':[{'text':m['text'],'quote':m['text'],'message_id':m['message_id']} for m in messages],
          'missing_fields':[],'conflicts':[],'bag_facts':[]}
        p={'schema_version':1,'id':identity,'account':run['account'],'thread_id':run['thread_id'],'conversation_id':run['conversation'],
          'historical_reference':False,'status':'needs_staff_review','execution_allowed':False,'customer_question_sent':False,
          'image_content_verified':False,'brief':brief,'bag_print':None,'review_items':['Đối chiếu file đã tải với đúng maket, chưa RIP/gửi khách.'],
          'sources':sources,'archive_root':engine.settings.inboxes[run['account']]['archive_root'],'relation_status':'proposed_only','created_at':time.time()}
        d.execute('insert or ignore into design_briefs values(?,?,?,?,?,?,?)',(identity,run['id'],run['account'],run['thread_id'],run['conversation'],json.dumps(p,ensure_ascii=False),time.time()))
    engine.note('design:'+identity,run['conversation'],'HỒ SƠ MẪU TỪ ẢNH/FILE/LINK KHÁCH GỬI — '+title+'\nĐã nối toàn bộ ảnh và file của yêu cầu. Đối chiếu maket, artwork và kích thước trước khi xuất. Thiếu thông tin chỉ giữ luồng file, không chặn đơn ERP. Chỉ preview nội bộ; chưa RIP/gửi khách.',apply_capture=True)
