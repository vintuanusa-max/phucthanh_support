from datetime import datetime,timezone,timedelta

def verified_reference_only(message):
    """ERP may identify an old template without bytes; never authorizes printing."""
    q=message.get('quoted_file') or {}
    assets=message.get('assets',[])
    return bool(q.get('resolved') is True and q.get('message_id') and q.get('name')
                and assets and not message.get('images')
                and set(message.get('attachments',[])) <= {'vault:download-failed'}
                and all(a.get('kind')=='file' and a.get('name')==q['name'] for a in assets))

def description(ref):
    date=datetime.fromtimestamp(ref['timestamp'],timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M') if ref.get('timestamp') else 'chưa xác minh ngày'
    return ('Trả lời file: '+(ref.get('name') or '[chưa lấy được tên]')+' · '+date
            +' · ID nguồn '+ref.get('message_id','')
            + (' · Đã đối chiếu đúng tin gốc; số lượng lấy từ tin mới.' if ref.get('resolved') else ' · Chưa lấy được file gốc: '+ref.get('error','unknown')))
