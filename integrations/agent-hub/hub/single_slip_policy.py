"""Single-slip v2 policies. Never submit, replay or modify a source capture."""
import json,re

def verified_slip(db,run,payload):
 parent_id=payload.get('proposal_parent');pid=payload.get('verified_proposal_id')
 if not parent_id or not pid:return False
 from hub.agent_order_tasks import saved_proposal
 row=db.execute('SELECT account,thread_id,payload FROM intake_runs WHERE id=?',(parent_id,)).fetchone()
 if not row or (row['account'],row['thread_id'])!=(run['account'],run['thread_id']):return False
 parent=json.loads(row['payload'])
 if parent.get('individual_slip_rules')!=2:return False
 draft=saved_proposal(db,parent_id,pid)
 return bool(draft and len(payload.get('messages',[]))==1 and set(draft['source_message_ids'])==set(payload['messages']))

def inferred_print_code(line):
 import unicodedata
 def folded(value):
  return ''.join(c for c in unicodedata.normalize('NFD',value or '').casefold() if not unicodedata.combining(c)).replace('đ','d')
 note=folded(line.ghi_chu_mau_do)
 title=folded(getattr(line,'ten_mau',''))
 if re.search(r'\b(khong|chua|huy)\s+(?:in\s+)?(?:pet|chuyen nhiet)\b',note):return None
 pet=bool(re.search(r'\bpet\b',note))
 transfer=bool(re.search(r'\b(?:chuyen nhiet|in cn)\b',note))
 if pet and transfer:return None
 if pet:
  # Only inspect print instructions, not dimensions later in sewing/bag notes.
  scopes=re.findall(r'\bpet\b([^;\n]{0,100})',note)
  sizes=set()
  dims=set()
  for scope in scopes:
   scope=re.split(r'\.(?!\d)|\b(?:tui|xuong|may|tai tho|duyet)\b',scope)[0]
   sizes.update(re.findall(r'\ba\s*([2-5])\b',scope))
   dims.update((int(a),int(b),unit) for a,b,unit in re.findall(r'(?<![\d.,])(\d{1,3})\s*[x*×]\s*(\d{1,3})(?![\d.,])\s*(mm|cm)?',scope))
  if len(sizes)==1:return 'PETA'+next(iter(sizes))
  if sizes:return None
  if len(dims)==1:
   a,b,unit=next(iter(dims))
   if unit=='mm':
    if a%10 or b%10:return None
    a//=10;b//=10
   if a>0 and b>0:return f'PET{a}X{b}'
  return None
 bag=bool(re.search(r'\btui\b',note+' '+title))
 one=bool(re.search(r'\b(?:1|mot)\s*mat\b',note))
 full=bool(re.search(r'\bfull\b|\b(?:2|hai)\s*mat\b',note))
 if bag and (transfer or full or re.search(r'\bin\b',note)):
  if one and full:return None
  if one:return 'TUI1MAT'
  if full:return 'TUI'
 return None


def normalize_product(line):
 code=(line.ma_san_pham or '').strip()
 if re.fullmatch(r'(?:PETA[2-5]|PET\d+X\d+|TUI|TUI1MAT)',code,re.I):
  line.ma_san_pham=code.upper()
  return
 mapped=inferred_print_code(line)
 note=line.ghi_chu_mau_do or ''
 if code:
  line.ten_don_hang=code
  note+=' | Mã đọc trên phiếu: '+code+('.' if mapped else '; chờ xác định mã hàng ERP.')
 line.ghi_chu_mau_do=note
 line.ma_san_pham=mapped
