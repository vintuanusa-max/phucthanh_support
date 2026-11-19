"""Read-only presentation of recorded intake evidence; never plans/replays orders."""
import re

def describe(row,p,result,messages,wait_seconds):
    state=row['state']
    blocked=set(result.get('uncovered_quantity_message_ids',[]))
    submitted=bool(p.get('submitted_payload'))
    done=state in ('created','amended','duplicate')
    stage=('Đã xử lý ERP' if done else 'Đã gửi ERP, chưa xác nhận kết quả' if state in ('sending','uncertain') or submitted else
           'Chờ kiểm tra nội dung' if state in ('review','failed','error') else
           'Chuẩn bị ảnh chứng cứ' if state=='awaiting_evidence' else 'Chờ gửi ERP' if state=='evidence_ready' else
           'Gom tin / chờ xử lý' if state in ('waiting_details','analyzing','queued') else 'Đã dừng / lưu lịch sử')
    method=('Số lượng từ tin chữ; ảnh giữ làm chứng cứ, không dùng AI đọc mẫu' if p.get('text_quantity_order') else
            'Có đề xuất đã lưu' if p.get('orders') else 'Chưa có đề xuất đơn được lưu')
    sources=[]
    for m in messages:
        text=str(m.get('text',''));is_blocked=m.get('message_id') in blocked
        issue=''
        if is_blocked:
            issue=('Yêu cầu theo từng mẫu; chưa xác định mẫu nào ứng với số lượng này.' if re.search(r'mỗi\s+mẫu',text,re.I)
                   else 'Tin có số lượng chưa được hiểu đầy đủ; cần kiểm tra trước khi tạo đơn.')
        sources.append({'id':m.get('message_id'),'sender':m.get('sender',''),'role':m.get('origin',''),
                        'timestamp':m.get('timestamp'), 'text':text[:4000], 'text_truncated':len(text)>4000,
                        'image_count':len(m.get('images',[])), 'file_count':len(m.get('assets',[])),
                        'blocked':is_blocked,'issue':issue})
    quantities=[{'name':o.get('ten_mau',''),'quantity':str(o.get('so_luong',''))} for o in p.get('orders',[])]
    from hub.quantity_review import choices,eligible,version
    review={'version':version(messages),'choices':choices(messages)} if eligible(row,p,result) else None
    return {'quantity_review':review,'stage':stage,'method':method,'erp':('Đã xử lý ERP' if done else 'Đã gửi; xem kết quả xác nhận' if submitted else 'Chưa gửi tạo đơn ERP'),
            'reason':str(result.get('reason',''))[:1500], 'sources':sources,'proposed_lines':quantities,
            'wait_minutes':wait_seconds//60,'last_source':p.get('last_timestamp'),
            'note':'Trạng thái và đề xuất đã lưu; không phải nhật ký từng lời gọi AI.'}
