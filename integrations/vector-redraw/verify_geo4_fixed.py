import sqlite3,json,time,sys,subprocess
from pathlib import Path
import fitz
job='bbd129d9f47b5f947cf8'
db=sqlite3.connect('state.sqlite')
for i in range(130):
 error=db.execute('select error from errors where capture=8391').fetchone()
 if error:raise RuntimeError(error[0])
 row=db.execute('select status from jobs where id=?',(job,)).fetchone()
 if row and row[0].startswith('chatwoot:'):break
 if i%6==0:print(row or 'awaiting scheduled worker',flush=True)
 time.sleep(4)
else:raise TimeoutError()
mid=int(row[0].split(':')[1])
folder=Path(r'W:\A LUOM\DESIGNER')
ai=folder/('Mau-'+job+'.ai');png=ai.with_suffix('.png')
with fitz.open(ai) as doc:print('AI pages, vector drawing count:',len(doc),len(doc[0].get_drawings()),flush=True)
code="""import sys,json
from hub.clients import Chatwoot
from hub.config import Settings
c=Chatwoot(Settings.environment())
mid,size=json.load(sys.stdin)
m=next(x for x in c.history(72) if x['id']==mid)
a=m['attachments'][0]
assert m['conversation_id']==72 and not m['private'] and a['file_type']=='image' and a['file_size']==size
print('Chatwoot verified',mid,a['id'],size)
"""
subprocess.run(['docker','exec','-i','phucthanh-chatwoot-hub-1','/app/.venv/bin/python','-c',code],input=json.dumps([mid,png.stat().st_size]).encode(),check=True)


