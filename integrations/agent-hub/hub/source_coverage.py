"""Source coverage by model, month and PDF-compatible artboard evidence."""
import hashlib,json,os,re,unicodedata,sqlite3
from pathlib import Path
from difflib import SequenceMatcher

SCHEMA=1
_MEMORY_CACHE={}
TOKEN=re.compile(r'(?<![A-Z0-9_-])([A-Z][A-Z0-9]{1,10}-[A-Z0-9]+(?:-[A-Z0-9]+)*(?:\+\d+)*(?:\.(?:0?[1-9]|1[0-2]))?)(?![A-Z0-9.+_-])')
def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',str(s).upper().replace('Đ','D')) if not unicodedata.combining(c))
def codes(text):
 text=re.sub(r'\.(AI|PDF)\b','',norm(text));out=[]
 for match in TOKEN.finditer(text):
  raw=match.group(1);month=None
  m=re.search(r'\.(\d{1,2})$',raw)
  if m:month=int(m.group(1));raw=raw[:m.start()]
  bits=raw.split('+');bases=[bits[0]]
  if len(bits)>1:
   prefix=re.sub(r'\d+$','',bits[0])
   if prefix==bits[0]:continue
   bases += [prefix+x for x in bits[1:]]
  for base in bases:
   item={'base':base,'month':month}
   if item not in out:out.append(item)
 return out

_COLOR_VARIANT_RE=re.compile(r'(?:TRANG|DEN|DO|VANG|XANH|HONG|KEM|NAU|TIM|XAM)$')

def _base_match(a,b):
 if a==b:return True
 if '-' in a and '-' in b:
  pa,sa=a.split('-',1);pb,sb=b.split('-',1)
  if re.sub(r'\d+','',pa)==re.sub(r'\d+','',pb):
   if sa==sb:return True
   da,db=bool(re.search(r'\d+$',sa)),bool(re.search(r'\d+$',sb))
   stem_a,stem_b=re.sub(r'\d+$','',sa),re.sub(r'\d+$','',sb)
   if da!=db and stem_a==stem_b and len(stem_a)>=2:return True
   ca,cb=_COLOR_VARIANT_RE.sub('',sa),_COLOR_VARIANT_RE.sub('',sb)
   if (ca==sb and len(ca)>=3) or (cb==sa and len(cb)>=3):return True
 return False

def initialize(db):
 db.executescript('''CREATE TABLE IF NOT EXISTS source_coverage_cache(sha TEXT PRIMARY KEY,payload TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS source_code_verifications(account TEXT,thread_id TEXT,message_id TEXT,sha TEXT,code TEXT,evidence TEXT,PRIMARY KEY(account,thread_id,message_id,sha));''')

def verified_code(db,p):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='source_code_verifications'").fetchone():return ''
 for s in p.get('sources',[]):
  for a in s.get('assets',[]):
   r=db.execute('SELECT code FROM source_code_verifications WHERE account=? AND thread_id=? AND message_id=? AND sha=?',(p['account'],p['thread_id'],s['message_id'],a.get('sha256',''))).fetchone()
   if r:return r[0]
 # CANAVI's order model comes from the classified slip, not an old maket label.
 from hub.canavi_slip_policy import GROUPS
 if p.get('account')=='zalo-personal-1' and p.get('thread_id') in GROUPS:
  from hub.receipt_match import confirmed_slip
  slip_ids={str(s['message_id']) for s in p.get('sources',[]) if s.get('images') and confirmed_slip(db,p['account'],p['thread_id'],s['message_id'])}
  values={f['value'].strip() for f in p.get('brief',{}).get('bag_facts',[]) if f.get('field')=='design_code' and f.get('basis')=='image' and f.get('source_message_ids') and set(map(str,f['source_message_ids']))<=slip_ids}
  if len(values)==1:return next(iter(values))
 return ''

def inspect_asset(db,a):
 sha=a.get('sha256','');root=os.environ.get('HUB_SOURCE_ARCHIVE','')
 if not root or not re.fullmatch('[a-f0-9]{64}',sha):return {'state':'unverified','pages':[]}
 try:
  base=Path(root).resolve();path=(base/a['relative_path']).resolve();path.relative_to(base)
  stat=path.stat()
  if not path.is_file() or stat.st_size>128*1024*1024:raise ValueError('size')
  stamp=[stat.st_size,stat.st_mtime_ns]
  cached=_MEMORY_CACHE.get((sha,str(path)))
  if cached and cached.get('stamp')==stamp:return cached
  row=db.execute('SELECT payload FROM source_coverage_cache WHERE sha=?',(sha,)).fetchone()
  if row:
   saved=json.loads(row[0])
   if saved.get('schema')==SCHEMA and saved.get('stamp')==stamp:return saved
  with path.open('rb') as f:
   if hashlib.file_digest(f,'sha256').hexdigest()!=sha:raise ValueError('hash')
  try:import pymupdf as fitz
  except ImportError:import fitz
  with fitz.open(path) as document:
   if not 1<=len(document)<=40:raise ValueError('pages')
   pages=[{'page':i+1,'codes':codes(page.get_text())} for i,page in enumerate(document)]
  saved={'schema':SCHEMA,'stamp':stamp,'state':'indexed','pages':pages}
  if len(_MEMORY_CACHE)>=128:_MEMORY_CACHE.pop(next(iter(_MEMORY_CACHE)))
  _MEMORY_CACHE[(sha,str(path))]=saved
  try:db.execute('INSERT OR REPLACE INTO source_coverage_cache VALUES(?,?)',(sha,json.dumps(saved)))
  except sqlite3.OperationalError as exc:
   if 'locked' not in str(exc).lower():raise
  return saved
 except (OSError,ValueError,KeyError,RuntimeError,ImportError):return {'state':'unverified','pages':[]}

def assess(db,p,code):
 from hub.receipt_match import same_model, day_bounds, keys
 target=codes(code)
 if not target and len(keys(code))==1:
  base,month=next(iter(keys(code)));target=[{'base':base,'month':month}]
 if len(target)!=1:return {'status':'review','reason':'Mã phiếu chưa rõ; cần đối chiếu ảnh, không nhắc thiếu file','candidates':[],'evidence':[]}
 target=target[0];stamps=[float(s.get('timestamp',0)) for s in p.get('sources',[]) if s.get('timestamp')];anchor=min(stamps) if stamps else 0
 start,end=day_bounds(anchor) if anchor else (0,0)
 seen=set();found=[];evidence=[];uncertain=[]
 for r in db.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND CAST(json_extract(payload,'$.timestamp') AS REAL)>=? AND EXISTS (SELECT 1 FROM json_each(json_extract(captures.payload,'$.assets')) WHERE lower(json_extract(value,'$.name')) LIKE '%.ai' OR lower(json_extract(value,'$.name')) LIKE '%.pdf') ORDER BY rowid DESC",(p['account'],p['thread_id'],start)):
  msg=json.loads(r[0])
  if msg.get('revision') or msg.get('recalled'):continue
  ts=float(msg.get('timestamp',0))
  if not anchor or not start<=ts<end:continue
  for a in msg.get('assets',[]):
   if not a.get('name','').lower().endswith(('.ai','.pdf')):continue
   identity=a.get('sha256') or a.get('id') or (msg['message_id'],a['name'])
   if identity in seen:continue
   seen.add(identity)
   # Bare filenames may only satisfy the current receipt period, not arbitrary old history.
   if not start<=ts<end:continue
   names=codes(a['name'])
   if a.get('state')!='ready':
    if not names or any(_base_match(x['base'],target['base']) for x in names):uncertain.append('File đã nhận nhưng chưa đọc được: '+a['name'])
    continue
   doc=inspect_asset(db,a);pages=[];known=[]
   for page in doc['pages']:
    known+=page['codes']
    if any(_base_match(x['base'],target['base']) and (not x['month'] or not target['month'] or x['month']==target['month']) for x in page['codes']):pages.append(page['page'])
   conflicting=any(_base_match(x['base'],target['base']) and x['month'] and target['month'] and x['month']!=target['month'] for x in names+known)
   if pages and not conflicting:
    matched={**a,'source_match':{'code':code,'pages':pages,'basis':'artboard_text_and_same_group_receipt'}}
    found.append((msg['message_id'],matched));evidence.append({'file':a['name'],'pages':pages,'code':code});continue
   exactname=any(_base_match(x['base'],target['base']) for x in names) or same_model(code,a['name'])
   # Filename coverage authorizes reading/selection, never final export approval.
   # Outlined AI artwork often has no extractable code text. Requiring that text
   # before inspection deadlocks multi-model files such as QUEEN1+2+3.11.ai.
   if exactname and not conflicting:
    matched={**a,'source_match':{'code':code,'pages':[],
              'basis':'model_and_month_same_group_receipt_day_requires_artboard_selection'}}
    found.append((msg['message_id'],matched))
    evidence.append({'file':a['name'],'pages':[],'code':code,
                     'requires_artboard_selection':True})
    continue
   nearby=any(x['base'].split('-',1)[0]==target['base'].split('-',1)[0] and SequenceMatcher(None,x['base'].split('-',1)[1],target['base'].split('-',1)[1]).ratio()>=.65 for x in known+names)
   if conflicting:uncertain.append('Khác tháng/phiên bản: '+a['name'])
   elif exactname or nearby or not known:uncertain.append('Có file cần đối chiếu mã/artboard: '+a['name'])
 ai_stems={re.sub(r'\.(AI|PDF)$','',norm(a.get('name',''))) for _,a in found if norm(a.get('name','')).endswith('.AI')}
 if ai_stems:
  found=[(mid,a) for mid,a in found if not (norm(a.get('name','')).endswith('.PDF') and re.sub(r'\.(AI|PDF)$','',norm(a.get('name',''))) in ai_stems)]
  evidence=[ev for ev in evidence if not (norm(ev.get('file','')).endswith('.PDF') and re.sub(r'\.(AI|PDF)$','',norm(ev.get('file',''))) in ai_stems)]
 if len({a.get('sha256') for _,a in found})>1:return {'status':'review','reason':'Nhiều phiên bản nguồn cùng mã; cần chọn đúng phiên bản','candidates':[],'evidence':evidence}
 if found:return {'status':'covered','reason':'Đã ghép file đúng mã mẫu/tháng, cùng nhóm và ngày nhận; dùng thông tin phiếu để lập phương án xuất','candidates':found,'evidence':evidence}
 if uncertain:return {'status':'review','reason':'; '.join(dict.fromkeys(uncertain)),'candidates':[],'evidence':[]}
 return {'status':'missing','reason':'Chờ file thiết kế đúng mẫu '+code,'candidates':[],'evidence':[]}
