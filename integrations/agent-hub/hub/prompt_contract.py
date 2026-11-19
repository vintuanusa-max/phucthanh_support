"""Contracts between text routing, tools and verification. No direct ERP/send calls."""
import json

def check_verdict(value):
 if not isinstance(value,dict) or type(value.get('approved')) is not bool:raise ValueError('VERIFY_INVALID: thiếu approved boolean')
 if value['approved'] is True:
  if value.get('issues'):raise ValueError('VERIFY_CONFLICT: approved=true nhưng còn issues')
  return value
 issues=value.get('issues',[])
 detail='; '.join(str(x.get('code','VERIFY_REJECTED'))+' ['+str(x.get('field',''))+']: '+str(x.get('repair','')) for x in issues if isinstance(x,dict)) if isinstance(issues,list) else ''
 raise ValueError(('VERIFY_REJECTED: '+str(value.get('reason','Không đủ căn cứ'))+'; '+detail)[:1800])

def attach_preflight(store,run,context):
 with store.db() as db:
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name='intake_route_audit'").fetchone():return
  row=db.execute('SELECT result FROM intake_route_audit WHERE run_id=?',(run['id'],)).fetchone()
 if row:context['preflight']=json.loads(row[0])

def validate_draft_sources(draft,context):
 batch={m['message_id']:m for m in context['batch']};history={m['message_id']:m for m in context['history']}
 ids=set(draft.source_message_ids);refs=set(draft.reference_message_ids)
 if not ids or not ids<=batch.keys():raise ValueError('SOURCE_BATCH: nguồn tác vụ phải thuộc batch hiện tại; nguồn lịch sử dùng reference_message_ids')
 if any(i.ma_san_pham is not None and i.ma_san_pham.strip().casefold()=='chờ mã' for i in draft.items):raise ValueError('PRODUCT_CODE: dùng JSON null, không dùng chuỗi Chờ mã')
 # Current-source orders do not depend on an inferred history binding.
 # Preserve the source ledger check even when the model supplied no history.
 for old in context.get('candidates',[]):
  if old.get('erp_orders') and ids.intersection(old.get('source_message_ids',[])):raise ValueError('SOURCE_CONSUMED: tin xác nhận đã gắn đơn ERP; đối soát, không tạo lại')
 draft.reference_message_ids=[]
 draft.history_binding={}


def handoff_approval(agent,run,args,context):
 ids=set(args.get('source_message_ids',[]));batch={m['message_id']:m for m in context['batch']}
 if not ids or not ids<=batch.keys() or any(batch[i].get('role')!='customer' for i in ids):raise ValueError('APPROVAL_SOURCE: chỉ ID xác nhận khách trong batch')
 if not agent.e.print_approvals.route():raise ValueError('APPROVAL_ROUTE: chưa có tuyến duyệt in được cấu hình')
 with agent.store.db() as db:
  db.execute('CREATE TABLE IF NOT EXISTS agent_approval_handoffs(account TEXT,thread_id TEXT,message_id TEXT,run_id TEXT,PRIMARY KEY(account,thread_id,message_id))')
  for mid in ids:db.execute('INSERT OR IGNORE INTO agent_approval_handoffs VALUES(?,?,?,?)',(run['account'],run['thread_id'],mid,run['id']))
  rows=db.execute('SELECT confirmation_id,state FROM print_approvals WHERE account=? AND thread_id=?',(run['account'],run['thread_id'])).fetchall()
 states=[dict(r) for r in rows if r['confirmation_id'] in ids]
 return {'state':'handed_to_existing_approval_flow','approval_states':states,'sent_to_customer':False,'erp_committed':False,'reason':'Luồng duyệt Hub tiếp tục đối chiếu ảnh và chống trùng; bàn giao không có nghĩa đã gửi.'}


def optional_delivery_verdict(value,args):
 """Missing optional delivery dates cannot veto an otherwise valid order.
 Nonempty incorrect dates, quantities and unknown/mixed issues still block.
 """
 import re
 if not isinstance(value,dict) or value.get('approved') is not False:return value
 issues=value.get('issues');items=args.get('items',[])
 if not isinstance(issues,list) or not issues or not items:return value
 def optional(issue):
  if not isinstance(issue,dict):return False
  field=str(issue.get('field',''))
  m=re.fullmatch(r'items\[(\d+)\]\.ngay_giao_hang',field)
  if m:
   n=int(m[1]);return n<len(items) and items[n].get('ngay_giao_hang') in (None,'')
  return field=='ngay_giao_hang' and all(i.get('ngay_giao_hang') in (None,'') for i in items)
 if all(optional(i) for i in issues):
  return dict(value,approved=True,issues=[],optional_warnings=issues,reason='Ngày giao không bắt buộc; để trống theo chính sách, các trường bắt buộc đã qua kiểm chứng.')
 return value
