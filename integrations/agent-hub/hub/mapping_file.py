"""Validated ID mapping file; no credentials and no ERP order mutations."""
import json,uuid
from pathlib import Path
RETAIL='aa6e7f8c-67d2-4fe8-85c2-c8c60a604a99'
def read_config(path):
 return validate(json.loads(Path(path).read_text(encoding='utf-8-sig')))

def validate(data):
 if data.get('schema_version')!=1:raise ValueError('Unsupported mapping schema')
 default=data.get('default_customer',{})
 if default.get('customer_id')!=RETAIL or default.get('customer_name')!='KHACH LE':raise ValueError('Default must be KHACH LE')
 if not isinstance(data.get('mappings'),list):raise ValueError('Mappings must be a list')
 result={}
 for row in data['mappings']:
  account=row.get('account');thread=row.get('thread_id');name=row.get('customer_name')
  if account not in ('zalo-personal-1','whatsapp-personal-1','viber-personal-1') or not isinstance(thread,str) or not thread.strip() or not isinstance(name,str) or not name.strip():raise ValueError('Invalid mapping row')
  cid=str(uuid.UUID(row['customer_id']))
  identity=(account,thread)
  if identity in result:raise ValueError('Duplicate account/thread ID')
  result[identity]={'customer_id':cid,'customer_name':name.strip()}
 return default,result


def synchronize(config,path):
 import os,tempfile
 data=config['erp_customer_mappings']
 validate(data)
 path=Path(path)
 raw=json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)
 if path.exists() and path.read_text(encoding='utf-8-sig')==raw:return
 fd,tmp=tempfile.mkstemp(prefix='mapping-',suffix='.json',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(raw)
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
