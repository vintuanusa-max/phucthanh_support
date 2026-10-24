"""Match quantity additions; unmatched requests become separate delta-only orders."""
import json
import re
import time
from decimal import Decimal
from hub.order_policy import key
from hub.store import event_key


def addition_request(messages):
    from hub.order_intake import piece_quantities, sender_key
    candidates=[m for m in messages if re.search(r'\b(in|đặt|làm|lấy)\s+thêm\b',key(m.get('text','')))]
    if not candidates:return None
    if len(candidates)!=1:raise ValueError('Nhiều yêu cầu đặt thêm trong cùng lượt; cần tách mẫu')
    source=candidates[0];text=key(source['text'])
    if re.search(r'\?|\b(không|chưa|khoan|đừng|hủy|huỷ|nếu|bù)\b',text):
        raise ValueError('Chưa có xác nhận đặt thêm rõ ràng')
    values=piece_quantities(text)
    if len(values)!=1 or next(iter(values))<=0:raise ValueError('Thiếu số lượng đặt thêm rõ ràng')
    if any(sender_key(m)!=sender_key(source) or m.get('revision') or m.get('recalled') for m in messages):
        raise ValueError('Nguồn đặt thêm xen người hoặc đã sửa/thu hồi')
    totals=set()
    for m in messages:
        if m['message_id']!=source['message_id']:
            totals.update(piece_quantities(m.get('text','')))
    if len(totals)>1:raise ValueError('Có nhiều tổng số lượng khác nhau')
    return {'source_message_id':source['message_id'],'delta':next(iter(values)),
            'total':next(iter(totals)) if totals else None}


def resolve_quote(store,message):
    with store.db() as d:return resolve_quote_db(d,message)


def resolve_quote_db(d,message):
    q=message.get('quoted_image') or {}
    if not q:return None
    rows=d.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND (message_id=? OR (?<>'' AND json_extract(payload,'$.client_message_id')=?)) ORDER BY revision DESC",
            (message['account'],message['thread_id'],q.get('message_id',''),q.get('client_message_id',''),q.get('client_message_id',''))).fetchall()
    found={}
    for row in rows:
        m=json.loads(row[0]);found.setdefault(m['message_id'],m)
    if len(found)!=1:return None
    m=next(iter(found.values()))
    if m.get('revision') or m.get('recalled') or not m.get('images') or m['timestamp']>=message['timestamp']:return None
    if q.get('sender_id') and q['sender_id']!=m.get('sender_id'):return None
    return m


def match_terms(messages):
    """Literal identifiers only; never search generic quantity/approval phrases."""
    terms=set()
    for m in messages:
        for a in m.get('assets',[]):
            name=a.get('filename') or a.get('name') or ''
            if name:terms.add(name.replace('\\','/').rsplit('/',1)[-1])
        text=m.get('text','')
        for term in re.findall(r'["“]([^"”]{5,180})["”]',text):terms.add(term.strip())
        for term in re.findall(r'(?i)([\w-]{5,}\.(?:prt|pdf|ai|cdr|psd))\b',text):terms.add(term)
    return sorted(t for t in terms if 5<=len(t)<=180 and not re.fullmatch(r'[\d\W]+',t))[:5]


def fallback_sources(messages):
    # Preserve the source text and disclose missing quote; do not fabricate an image.
    out=[]
    for m in messages:
        m=dict(m)
        if m.get('quoted_image') and not m['quoted_image'].get('resolved'):
            m['text']=m.get('text','')+'\n[Chưa lấy được ảnh trích dẫn; nhân viên bổ sung mẫu trước khi in.]'
            m['quoted_image']=None
        out.append(m)
    return out


class OrderAdditions:
    def __init__(self,intake):
        self.intake=intake;self.e=intake.engine;self.store=intake.store
        with self.store.db() as d:
            d.executescript('''CREATE TABLE IF NOT EXISTS order_source_links(
                account TEXT,thread_id TEXT,message_id TEXT,customer_id TEXT,order_id TEXT,
                verified TEXT NOT NULL,PRIMARY KEY(account,thread_id,message_id));
                CREATE TABLE IF NOT EXISTS order_additions(
                id TEXT PRIMARY KEY,account TEXT,thread_id TEXT,source_message_id TEXT,state TEXT,payload TEXT,result TEXT,
                UNIQUE(account,thread_id,source_message_id));''')

    def target(self,run,messages,binding):
        originals=[resolve_quote(self.store,m) for m in messages if m.get('quoted_image')]
        if not originals or any(m is None for m in originals):raise ValueError('Chưa tìm duy nhất ảnh gốc trích dẫn')
        candidates=set();verified_files=set()
        with self.store.db() as d:
            for m in originals:
                link=d.execute('SELECT order_id,verified FROM order_source_links WHERE account=? AND thread_id=? AND message_id=? AND customer_id=?',
                    (run['account'],run['thread_id'],m['message_id'],binding['customer_id'])).fetchone()
                if link:
                    candidates.add(link[0]);verified_files.update(json.loads(link[1]).get('files',[]));continue
                rows=d.execute("SELECT payload,result FROM intake_runs WHERE account=? AND thread_id=? AND state='created'",(run['account'],run['thread_id'])).fetchall()
                found=set()
                for row in rows:
                    p=json.loads(row[0]);r=json.loads(row[1])
                    if m['message_id'] in p.get('messages',[]) and r.get('customer_id')==binding['customer_id']:
                        if len(r.get('orders',[]))==1:found.add(r['orders'][0]['id'])
                        else:raise ValueError('Ảnh nguồn thuộc lượt nhiều đơn; chưa xác định dòng cần tăng')
                if len(found)!=1:raise ValueError('Chưa có liên kết chắc chắn từ ảnh gốc tới đơn ERP; nhân viên đối chiếu')
                candidates.update(found)
        if len(candidates)!=1:raise ValueError('Trích dẫn liên quan nhiều đơn ERP')
        return next(iter(candidates)),verified_files

    def match_target(self,run,messages,binding):
        terms=match_terms(messages)
        if not terms:return None
        sets=[];files=set()
        for term in terms:
            r=self.e.erp.match_order(binding['customer_id'],term)
            if r.get('truncated'):return None
            matches=r.get('matches',[])
            if not matches:return None
            sets.append({m['order_id'] for m in matches})
        candidates=set.intersection(*sets)
        if len(candidates)!=1:return None
        order_id=next(iter(candidates))
        # Do not treat a matching order-level note as proof that every face should increase.
        snapshot=self.e.erp.quantity_snapshot(binding['customer_id'],order_id)
        if len(snapshot['lines'])>1:return None
        return order_id,files

    def new_addition(self,run,messages,request,binding,identity,previous=None):
        payload=json.loads(run['payload'])
        note=('In thêm riêng từ đơn '+str(previous['order_ref'])+'; giữ nguyên đơn đã chuyển sản xuất.') if previous else 'Đặt thêm riêng: chưa xác định duy nhất đơn cũ. Đối chiếu mẫu trước khi in.'
        payload.update(customer_binding=binding,request_id='chatwoot-id:'+run['id'],
            addition_fallback={'source_message_id':request['source_message_id'],'delta':str(request['delta']),'previous_order_id':previous.get('order_id') if previous else None},
            orders=[{'ma_san_pham':None,'ten_mau':None,'so_luong':str(request['delta']),
                     'ghi_chu_mau_do':note}])
        with self.store.db() as d:
            d.execute('INSERT INTO order_additions VALUES(?,?,?,?,?,?,?)',
                (identity,run['account'],run['thread_id'],request['source_message_id'],'new_order',json.dumps({'run_id':run['id']}),'{}'))
            d.execute("UPDATE intake_runs SET state='awaiting_evidence',payload=? WHERE id=?",(json.dumps(payload,ensure_ascii=False),run['id']))
        self.intake.notify(run,f"{note} Chuẩn bị đơn Lên mẫu riêng {request['delta']} cái, mã hàng Chờ mã. Không dùng tổng số lượng cũ; mẫu cần đối chiếu theo bằng chứng.")

    def notice(self,run,messages,identity,text):
        route=self.e.print_approvals.route()
        if not route:
            self.intake.notify(run,text)
            return
        ids=[m['message_id'] for m in messages]
        payload={'kind':'order_addition','destination':route,'confirmation':ids[-1],
                 'messages':ids,'new_message_ids':ids,'notice':text,'missing_quote_disclosed':True}
        with self.store.db() as d:
            d.execute('INSERT OR IGNORE INTO print_approvals VALUES(?,?,?,?,?,?,?)',
                (identity,run['account'],run['thread_id'],ids[-1],'awaiting_evidence',json.dumps(payload,ensure_ascii=False),time.time()))
            for mid in ids:d.execute('INSERT OR IGNORE INTO print_change_sources VALUES(?,?,?,?)',(run['account'],run['thread_id'],mid,identity))
        self.intake.notify(run,text)

    def recover_notice(self):
        # A crash after ERP confirmation must not lose the production notification.
        with self.store.db() as d:
            row=d.execute("SELECT * FROM order_additions a WHERE state IN ('done','new_created') AND json_extract(payload,'$.local_notice') IS NOT NULL AND NOT EXISTS(SELECT 1 FROM print_approvals p WHERE p.id=a.id) LIMIT 1").fetchone()
        if not row:return False
        p=json.loads(row['payload'])['local_notice']
        self.notice(p['run'],p['messages'],row['id'],p['text'])
        self.intake.state(p['run']['id'],'created' if row['state']=='new_created' else 'amended',json.loads(row['result']))
        return True

    def handle(self,run,messages):
        if not any(re.search(r'\b(in|đặt|làm|lấy)\s+thêm\b',key(m.get('text',''))) for m in messages):return False
        identity=event_key('order-addition',run['account'],run['thread_id'],[m['message_id'] for m in messages])
        try:
            request=addition_request(messages)
            binding=self.e.customer_mappings.get(run['account'],run['thread_id'])
            if not binding:raise ValueError('Nhóm chưa liên kết khách ERP')
            with self.store.db() as d:
                old=d.execute('SELECT state,result,payload FROM order_additions WHERE account=? AND thread_id=? AND source_message_id=?',
                    (run['account'],run['thread_id'],request['source_message_id'])).fetchone()
                if old:
                    if old[0]=='new_order' and json.loads(old[2]).get('run_id')==run['id']:return True
                    if old[0]=='new_created':
                        self.intake.state(run['id'],'created',json.loads(old[1]));return True
                    self.intake.state(run['id'],'amended' if old[0]=='done' else 'review',json.loads(old[1]) if old[0]=='done' else {'reason':'Yêu cầu đặt thêm đã ghi nhận; không tự cộng lại'})
                    return True
            try:
                target=self.target(run,messages,binding)
            except ValueError:
                originals=[resolve_quote(self.store,m) for m in messages if m.get('quoted_image')]
                target=self.match_target(run,messages+[m for m in originals if m],binding)
            if target is None:
                self.new_addition(run,messages,request,binding,identity)
                return True
            order_id,verified_files=target
            snapshot=self.e.erp.quantity_snapshot(binding['customer_id'],order_id)
            if not snapshot.get('status'):
                raise ValueError('ERP chưa trả trạng thái đơn; không tự sửa')
            if snapshot['status'] not in ('len_mau','mau_co_san','dang_chay_giay'):
                self.new_addition(run,messages,request,binding,identity,previous=snapshot)
                return True
            if snapshot.get('mutation_policy') != 'quantity-states-v2':
                raise ValueError('Cần nạp API ma trận trạng thái tăng/giảm mới; chưa tự cộng đơn cũ')
            if 'recent' not in snapshot:raise ValueError('ERP cần nạp API giới hạn 3 ngày trước khi đối chiếu đơn cũ')
            if not snapshot['recent']:
                self.new_addition(run,messages,request,binding,identity)
                return True
            if len(snapshot['lines'])>1 and (not verified_files or {l.get('file') for l in snapshot['lines']}!=verified_files):
                self.new_addition(run,messages,request,binding,identity)
                return True
            quantities={Decimal(str(l['quantity'])) for l in snapshot['lines']}
            if len(quantities)!=1:raise ValueError('Các dòng khác số lượng; cần chỉ rõ mặt/dòng đặt thêm')
            before=next(iter(quantities));after=before+request['delta']
            if request['total'] is not None and after!=request['total']:
                raise ValueError('Tổng khách chốt không bằng số lượng ERP cộng phần thêm; không tự cộng')
            body={'request_id':identity,'customer_id':binding['customer_id'],'order_id':order_id,
                  'source_account':run['account'],'group_id':run['thread_id'],
                  'source_message_id':request['source_message_id'],'delta':str(request['delta']),
                  'lines':[{'id':l['id'],'expected':str(l['quantity']),'target':str(after)} for l in snapshot['lines']]}
            with self.store.db() as d:d.execute('INSERT INTO order_additions VALUES(?,?,?,?,?,?,?)',
                (identity,run['account'],run['thread_id'],request['source_message_id'],'sending',json.dumps(body),'{}'))
            receipt=self.e.erp.add_quantity(body)
            text=f"KHÁCH ĐẶT THÊM — ĐÃ CẬP NHẬT ERP\nĐơn {snapshot['order_ref']}: {before} → {after} cái/dòng.\nCHỈ IN THÊM {request['delta']} cái cho mỗi dòng đã đối chiếu; không in lại tổng {after}. Giữ nguyên file, giá và trạng thái."
            local={**body,'local_notice':{'run':dict(run),'messages':messages,'text':text}}
            with self.store.db() as d:d.execute("UPDATE order_additions SET state='done',payload=?,result=? WHERE id=?",(json.dumps(local,ensure_ascii=False),json.dumps(receipt),identity))
            self.intake.state(run['id'],'amended',receipt)
        except Exception as exc:
            reason=str(exc) if isinstance(exc,ValueError) else 'API cập nhật chưa sẵn sàng hoặc kết quả chưa rõ; kiểm tra ERP, không tự thử lại'
            text='KHÁCH YÊU CẦU ĐẶT THÊM — CẦN ĐỐI CHIẾU ERP\n'+reason+'\nCHƯA XÁC NHẬN CẬP NHẬT. Không in dựa riêng vào thông báo này; nhân viên kiểm tra tin/ảnh đính kèm.'
            self.intake.state(run['id'],'review',{'reason':reason,'addition':True})
        self.notice(run,messages,identity,text)
        return True
