from pathlib import Path
from PIL import Image
import worker as w, tempfile, base64, hashlib, json, subprocess
from datetime import datetime
def hub(code,data=None):
 r=subprocess.run(["docker","exec","-i","phucthanh-chatwoot-hub-1","/app/.venv/bin/python","-c",code],input=json.dumps(data).encode(),capture_output=True,timeout=120)
 if r.returncode: raise RuntimeError(r.stderr.decode(errors="replace")[-800:])
 return json.loads(r.stdout)
lookup="""import json,sqlite3
from hub.clients import Chatwoot
from hub.config import Settings
s=Settings.environment()
db=sqlite3.connect(s.database)
group,=db.execute('select display_name from threads where account=? and thread_id=? and conversation=?',('zalo-personal-1','g8534414090274815910',72)).fetchone()
cw=Chatwoot(s);conv=cw.conversation(72)
assert conv['meta']['sender']['name']==group and conv['id']==72
"""
group=hub(lookup+"print(json.dumps(group))")
raw=Path(r'C:\Users\Admin\AppData\Local\Temp\codex-clipboard-21dd0db2-83e9-49d5-bc58-be94baabf46a.png').read_bytes()
job='Denim-Test-'+datetime.now().strftime('%Y%m%d-%H%M%S')
print('Calling configured OpenAI redraw API',flush=True)
flat=w.call('draw',png=base64.b64encode(raw).decode(),brief='Preserve WORKERS OVERALL, DENIM SUPPLY, 999, DENIM FACTORY, SINCE 1985, QUALITY DENIM. Use flat crimson, navy, cream and tan. Remove embroidery texture.')
(w.ROOT/group).mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'flat.png';p.write_bytes(base64.b64decode(flat,validate=True));Image.open(p).verify()
 ai,png=w.export_vector(p,w.ROOT,group,'g8534414090274815910',job)
raw=png.read_bytes()
print('AI and PNG saved',ai.stat().st_size,len(raw),flush=True)
publish=lookup+"""import sys,base64
a=json.load(sys.stdin);data=base64.b64decode(a['png'])
reply=cw.request('POST','conversations/72/messages',data={'private':'false','message_type':'outgoing','content':'Mẫu Denim vẽ lại — bản kiểm thử.'},files={'attachments[]':(a['name'],data,'image/png')})
print(json.dumps(reply['id']))
"""
mid=hub(publish,{'name':png.name,'png':base64.b64encode(raw).decode()})
print('POST receipt',mid,flush=True)
verify=lookup+"""import sys
mid=json.load(sys.stdin)
msg=next(m for m in cw.history(72) if m['id']==mid)
a=msg['attachments'][0]
assert not msg['private'] and msg['conversation_id']==72 and a['file_type']=='image'
print(json.dumps([msg['id'],a['id'],a.get('file_size')]))
"""
print('Verified',hub(verify,mid),ascii(str(ai)),flush=True)
