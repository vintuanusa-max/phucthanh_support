"""Versioned model choices for existing Hub adapters; no job execution."""
import json,re,time,sqlite3
from pathlib import Path
from contextlib import closing

def defaults():return {'revision':0,'analysis':'','vision':'','redraw':''}
def get(database):
 with closing(sqlite3.connect(str(database))) as db:
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name='execution_models'").fetchone():return defaults()
  r=db.execute('SELECT payload FROM execution_models ORDER BY revision DESC LIMIT 1').fetchone()
 return json.loads(r[0]) if r else defaults()
def select(settings,stage,fallback=None):
 return get(settings.database).get(stage) or fallback or settings.gemini_model
def has_images(value):
 if isinstance(value,dict):return any(k in value for k in ('inline_data','inlineData')) or any(has_images(v) for v in value.values())
 return isinstance(value,list) and any(has_images(v) for v in value)
def update(store,data):
 if set(data) not in ({'revision','analysis','vision','redraw'},{'revision','analysis','vision','redraw','prompts'}):raise ValueError('Cấu hình không hợp lệ')
 if 'prompts' in data:
  if not isinstance(data['prompts'],dict) or set(data['prompts'])!={'route','agent','verify'}:raise ValueError('Prompt không hợp lệ')
  if any(not isinstance(v,str) or not 30<=len(v)<=30000 for v in data['prompts'].values()):raise ValueError('Prompt cần từ 30 đến 30000 ký tự')
 for k in ('analysis','vision','redraw'):
  v=data[k]
  if not isinstance(v,str) or len(v)>100 or (v and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]*',v)):raise ValueError('ID model không hợp lệ')
  if v and not v.startswith('gpt-image-' if k=='redraw' else 'gemini-'):raise ValueError('Model phải thuộc API đang tích hợp')
 with store.db() as db:
  db.execute('BEGIN IMMEDIATE')
  db.execute('CREATE TABLE IF NOT EXISTS execution_models(revision INTEGER PRIMARY KEY,payload TEXT,created REAL)')
  row=db.execute('SELECT payload FROM execution_models ORDER BY revision DESC LIMIT 1').fetchone()
  old=json.loads(row[0]) if row else defaults()
  if type(data['revision']) is not int or data['revision']!=old['revision']:raise ValueError('Cấu hình đã đổi; tải lại')
  saved={**old,**data,'revision':old['revision']+1}
  db.execute('INSERT INTO execution_models VALUES(?,?,?)',(saved['revision'],json.dumps(saved),time.time()))
 return saved

