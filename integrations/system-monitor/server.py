"""Local read-only status dashboard; never exposes configuration or message bodies."""
import concurrent.futures,json,os,subprocess,threading,time,urllib.request,secrets,re,psutil
from pathlib import Path
from sender_health import sender_status
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(os.environ['LOCALAPPDATA'])/'PhucThanh'
CREATE_NO_WINDOW=0x08000000
CACHE={'updated':0,'cards':[]}
CSRF=secrets.token_urlsafe(32)
def dispatch(path,method='GET',body=None):
 if not re.fullmatch(r'/dispatch(?:/[a-f0-9]{64})?',path):raise ValueError('Invalid path')
 code="import sys,json,httpx; from hub.config import Settings; q=json.load(sys.stdin); s=Settings.environment(); r=httpx.request(q['method'],'http://127.0.0.1:8095'+q['path'],headers={'Authorization':'Bearer '+s.admin_token},json=q.get('body'),timeout=20); print(json.dumps({'status':r.status_code,'data':r.json()}))"
 args=[r'C:\Program Files\Docker\Docker\resources\bin\docker.exe','exec','-i','-e','PYTHONPATH=/app','phucthanh-chatwoot-hub-1','/app/.venv/bin/python','-c',code]
 r=subprocess.run(args,input=json.dumps(dict(path=path,method=method,body=body)),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25,creationflags=CREATE_NO_WINDOW)
 if r.returncode:raise ValueError('Không kết nối được bộ điều phối')
 return json.loads(r.stdout)
def command(args,timeout=12):
 return subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,creationflags=CREATE_NO_WINDOW)
def card(name,state,detail):return dict(name=name,state=state,detail=detail)
def probe(name,url):
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=3) as r:
   return card(name,'ok' if r.status<400 else 'warn','HTTP '+str(r.status))
 except Exception:return card(name,'bad','Không kết nối được; kiểm tra dịch vụ/mạng')
def read_status(name,path,alive,worker=False):
 try:
  data=json.loads(path.read_text(encoding='utf-8-sig'));stamp=float(data.get('updated_at',data.get('time',0)));age=max(0,int(time.time()-stamp))
  if age>1e10:age=0
  state='bad' if not alive else ('warn' if age>180 else 'ok')
  text=('Đang chạy' if alive else 'ĐÃ DỪNG')+' · cập nhật '+str(age)+' giây trước'
  if worker:
   values=[str(v) for v in data.get('accounts',{}).values()]
   if any('error' in v for v in values):state='warn' if alive else 'bad'
   text+=' · '+' | '.join(values)
  else:
   text+=' · '+str(data.get('phase',data.get('mode','')))
   errors=data.get('errors',[])
   if errors:text+=' · Có lỗi được ghi nhận (cần kiểm tra log)'
  return card(name,state,text)
 except Exception:return card(name,'bad','Chưa đọc được trạng thái')
def snapshot():
 proc=[]
 for process in psutil.process_iter(['name','cmdline']):
  try:
   info=process.info
   if re.search('python|Photoshop|Illustrator',info.get('name') or '',re.I):
    proc.append({'Name':info['name'],'CommandLine':' '.join(info.get('cmdline') or [])})
  except (psutil.NoSuchProcess,psutil.AccessDenied):
   continue
 def alive(marker):return any(marker.lower() in str(p.get('CommandLine','')).lower() for p in proc)
 sender=sender_status(ROOT/"ZaloDesktopReader/state/sender",alive("zalo_desktop.sender"))
 cards=[]
 for title,folder in [('Đọc Zalo','ZaloDesktopReader'),('Đọc WhatsApp','WhatsAppDesktopReader'),('Đọc Viber','ViberDesktopReader')]:
  cards.append(read_status(title,ROOT/folder/'state/status.json',alive(folder)))
 cards.append(read_status('Đọc / xuất file Windows',ROOT/'ArtworkInspector/state.json',alive('ArtworkInspector'),True))
 for app in ('Photoshop','Illustrator'):
  opened=any(app.lower() in str(p.get('Name','')).lower() for p in proc)
  cards.append(card(app,'ok' if opened else 'idle','Đã mở (chưa xác nhận COM sẵn sàng)' if opened else 'Chưa mở — worker sẽ tự gọi mở khi cần'))
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  cards+=list(pool.map(lambda args:probe(*args),[('Hub AI','http://127.0.0.1:8095/health'),('Chatwoot','http://127.0.0.1:3000/app/login'),('ERP','http://192.168.1.203:8000/login')]))
 queue={};jobs=[]
 try:
  code="""import sqlite3,json
c=sqlite3.connect('file:/data/hub.sqlite3?mode=ro',uri=True);c.row_factory=sqlite3.Row
tables=['artwork_checks','pet_exports','jpg_exports'];jobs=[]
for t in tables:
 for r in c.execute('select * from '+t+' order by created desc limit 12'):
  p=json.loads(r['payload']);result=json.loads(r['result']) if t=='artwork_checks' else {}
  source=p.get('source',p)
  jobs.append({'step':t,'state':r['state'],'name':p.get('plan',{}).get('order_code') or source.get('asset',{}).get('name',''),'reason':p.get('review_reason') or '; '.join(result.get('errors',[])),'created':r['created']})
print(json.dumps({'queues':{t:[list(r) for r in c.execute('select state,count(*) from '+t+' group by state')] for t in tables},'jobs':sorted(jobs,key=lambda x:x['created'],reverse=True)[:20]}))
"""
  docker=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
  out=command([docker,'exec','phucthanh-chatwoot-hub-1','/app/.venv/bin/python','-c',code])
  data=json.loads(out.stdout);queue=data['queues'];jobs=data['jobs']
 except Exception:cards.append(card('Hàng đợi file','warn','Chưa đọc được thống kê Docker'))
 return dict(updated=time.time(),cards=cards,queues=queue,jobs=jobs,zalo_sender=sender)
def poll():
 global CACHE
 while True:
  try:CACHE=snapshot()
  except Exception:CACHE={'updated':time.time(),'cards':[card('Giám sát','bad','Lỗi thu thập trạng thái')]}
  time.sleep(20)
class Handler(BaseHTTPRequestHandler):
 def reply(self,code,data):
  raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
 def do_POST(self):
  if self.headers.get('Host') not in ('127.0.0.1:8096','localhost:8096') or self.headers.get('Origin') not in ('http://127.0.0.1:8096','http://localhost:8096') or not secrets.compare_digest(self.headers.get('X-CSRF',''),CSRF):self.reply(403,{'detail':'Chỉ điều phối từ trang nội bộ'});return
  if not re.fullmatch(r'/api/dispatch/[a-f0-9]{64}',self.path):self.send_error(404);return
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<=16000:raise ValueError('Yêu cầu quá dài')
   result=dispatch(self.path[4:],'POST',json.loads(self.rfile.read(size)));self.reply(result['status'],result['data'])
  except Exception as ex:self.reply(400,{'detail':str(ex) if isinstance(ex,ValueError) else 'Không gửi được yêu cầu; kiểm tra trạng thái trước khi thử lại'})
 def do_GET(self):
  if self.headers.get('Host') not in ('127.0.0.1:8096','localhost:8096'):self.send_error(403);return
  if self.path=='/api/session':self.reply(200,{'csrf':CSRF});return
  if self.path.startswith('/api/dispatch'):
   try:
    result=dispatch(self.path[4:]);self.reply(result['status'],result['data'])
   except Exception:self.reply(503,{'detail':'Bộ điều phối chưa sẵn sàng'})
   return
  if self.path not in ('/','/api/status'):self.send_error(404);return
  raw=json.dumps(CACHE,ensure_ascii=False).encode() if self.path=='/api/status' else Path(__file__).with_name('dispatch.html').read_bytes()
  self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8' if self.path=='/api/status' else 'text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
 def log_message(self,*args):pass
if __name__=='__main__':
 server=ThreadingHTTPServer(('127.0.0.1',8096),Handler)
 threading.Thread(target=poll,daemon=True).start();server.serve_forever()

