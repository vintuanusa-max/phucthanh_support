"""CANAVI source readiness; no AI calls, no queue mutation, no ERP writes."""
import re,json,unicodedata

def norm(s):
 return ''.join(c for c in unicodedata.normalize('NFD',str(s).upper().replace('Đ','D')) if not unicodedata.combining(c))
def code_of(p):
 b=p.get('brief',{})
 values=[(p.get('bag_print') or {}).get('design_code','')]
 values += [f.get('value','') for f in b.get('bag_facts',[]) if norm(f.get('field','')) in ('DESIGN_CODE','MA SAN PHAM')]
 values.append(b.get('title',''))
 values += [a.get('name','') for s in p.get('sources',[]) for a in s.get('assets',[]) if a.get('name','').lower().endswith(('.ai','.pdf'))]
 for value in values:
  match=re.search(r'\b[A-Z0-9]+-[A-Z0-9+_-]+(?:\.[A-Z0-9_-]+)+',norm(value))
  if match:return match.group(0)
  from hub.receipt_match import keys
  aliases=keys(value)
  if len(aliases)==1:
   base,month=next(iter(aliases));return base+'.'+str(month)
 return ''
def matches(code,name):
 return bool(code and re.search(r'(?<![A-Z0-9_.+-])'+re.escape(code)+r'(?![A-Z0-9_.+-])',norm(name).removesuffix('.AI').removesuffix('.PDF')))
def canavi(p):
 return p.get('thread_id') in {'g1790239230897256718','g2671966061008128194'} or any(norm(a.get('relative_path','').replace('\\','/').split('/')[0]).startswith('CANAVI') for s in p.get('sources',[]) for a in s.get('assets',[]))
def readiness(db,p):
 reuse=existing_design(db,p)
 if reuse:return reuse
 if p.get('direct_pet_source'):return None
 if not canavi(p):return None
 from hub.source_coverage import assess,verified_code,codes
 b=p.get('brief',{});code=verified_code(db,p) or code_of(p)
 if not code:
  parsed=codes((p.get('bag_print') or {}).get('design_code','') or b.get('title',''))
  if len(parsed)==1:code=parsed[0]['base']+('.'+str(parsed[0]['month']) if parsed[0]['month'] else '')
 slip=b.get('image_context')=='production_slip' or 'PHIEU LENH' in norm(b.get('title',''))
 from hub.receipt_match import confirmed_slip
 slip=slip or any(confirmed_slip(db,p['account'],p['thread_id'],s['message_id']) for s in p.get('sources',[]) if s.get('images'))
 result=assess(db,p,code)
 from hub.direct_pet_intake import is_pet_asset
 pet_files=result.get('candidates',[])
 if pet_files and all(is_pet_asset(p['thread_id'],a) for _,a in pet_files):slip=True
 if not slip:result.update(status='review',reason='Chờ phiếu lệnh in của đúng mẫu',candidates=[])
 return dict(result,ready=result['status']=='covered',code=code)

def group_source_message(m):
 # Bot replies, reactions and logistics do not keep a customer batch open.
 if m.get('recalled') or m.get('revision'):return False
 # Human design attachments extend the print batch regardless of staff/customer role.
 if m.get('role')!='bot' and any(a.get('name','').lower().endswith(('.ai','.pdf','.psd')) for a in m.get('assets',[])):return True
 if m.get('direction')=='outgoing' or m.get('role') in ('internal','staff','bot'):return False
 if m.get('images'):return True
 if any(a.get('kind')=='image' or a.get('name','').lower().endswith(('.ai','.pdf','.png','.jpg','.jpeg','.jxl','.webp','.tif','.tiff','.eps','.svg','.psd')) for a in m.get('assets',[])):return True
 text=norm(m.get('text',''))
 return bool(re.search(r'PHIEU LENH|LENH IN|MAKET|MARKET|FILE|THIET KE|ARTWORK|IN THEM|SO LUONG|KICH THUOC|CHIEU CAO|CHIEU NGANG|CHIEU RONG|DOI MAU|SUA MAU|MAU IN|MAU SAC|CMYK|https?://|\b\d+(?:[.,]\d+)?\s*(?:CM|MM|CAI|TAM|MET)\b',text,re.I))

def collection_window(db,p,now=None):
 import time
 from datetime import datetime,timezone,timedelta
 now=time.time() if now is None else now
 minutes=15
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='print_settings'").fetchone():
  setting=db.execute('SELECT payload FROM print_settings ORDER BY id DESC LIMIT 1').fetchone()
  if setting:minutes=json.loads(setting[0]).get('source_wait_minutes',15)
 ids={s['message_id'] for s in p.get('sources',[])};last=0;count=0
 for row in db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? ORDER BY rowid DESC LIMIT 1000',(p['account'],p['thread_id'])):
  m=json.loads(row[0])
  if m.get('revision') or m.get('recalled'):continue
  related=(m.get('message_id') in ids and m.get('direction')!='outgoing') or group_source_message(m)
  if p.get('direct_original_jpg'):
   related=m.get('origin') not in ('legacy_bot','erp') and m.get('role')!='bot'
  if related:
   last=max(last,float(m.get('timestamp',0)));count+=1
 # Without source timestamps, do not silently start a new timer on every poll.
 due=last+minutes*60
 waiting=bool(last and now<due)
 stamp=datetime.fromtimestamp(due,timezone(timedelta(hours=7))).strftime('%H:%M:%S %d/%m/%Y')
 return {'scope':'group','source_count':count,'waiting':waiting,'ready_at':due,'last_source_at':last,'minutes':minutes,'reason':('Đang gom cả đợt gửi của nhóm '+str(minutes)+' phút; dự kiến kiểm tra lúc '+stamp+' (giờ Việt Nam). Tin/file nguồn mới trong cùng nhóm sẽ tính lại thời gian chờ; hết thời gian mới ghép phiếu và thiết kế theo từng mã mẫu.') if waiting else ''}


def existing_design(db,p):
 # Only explicit customer evidence scoped to this model. Never infer from a filename.
 code=code_of(p)
 if not code:return None
 sources=p.get('sources',[])
 candidates=[p]
 # Design-team replies may refer to our model-specific missing-file reminder.
 for row in db.execute("SELECT payload FROM design_briefs WHERE account=? AND thread_id='g600695897323562880' ORDER BY created DESC LIMIT 100",(p.get('account'),)):
  other=json.loads(row[0])
  if code_of(other)!=code:continue
  ss=other.get('sources',[])
  reminder=any('NHAC BO SUNG FILE THIET KE' in norm(x.get('text','')) and matches(code,x.get('text','')) for x in ss)
  own_time=max([float(x.get('timestamp',0)) for x in sources] or [0])
  reply_time=max([float(x.get('timestamp',0)) for x in ss] or [0])
  if reminder and own_time and own_time<=reply_time<=own_time+7*86400:candidates.append(other)
 for candidate in candidates:
  ss=candidate.get('sources',[])
  texts=[x for x in ss if x.get('direction')!='outgoing' and not x.get('recalled') and not x.get('revision') and x.get('role') not in ('staff','internal','bot')]
  text=' '.join(norm(x.get('text','')) for x in texts)
  if re.search(r'DOI MAU|SUA MAU|DOI KICH THUOC|SUA THIET KE|VE LAI|XUAT LAI|FILE MOI',text):continue
  for x in texts:
   t=norm(x.get('text',''))
   reuse=re.search(r'FILE NHU MAU TRUOC|(?:DUNG|GIU|LAY|IN) (?:LAI |NGUYEN )?(?:FILE|MAU) CU',t)
   short=code.split('-')[-1].split('.')[0]
   # An explicit model mention avoids applying a batch reply to every slip.
   if reuse and (matches(code,t) or re.search(r'\b'+re.escape(short)+r'\b',t)):
    return {'ready':False,'status':'reuse_existing','code':code,'candidates':[], 'evidence_message_id':x.get('message_id'), 'reason':'Dùng mẫu cũ — không yêu cầu file mới, không tự xuất lại. Cần gửi lại mẫu cũ để khách duyệt trước khi in; chưa xác nhận đã duyệt.'}
 return None
