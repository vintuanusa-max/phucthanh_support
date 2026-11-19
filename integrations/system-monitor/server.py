"""Local read-only status dashboard; never exposes configuration or message bodies."""
import concurrent.futures,json,os,subprocess,threading,time,urllib.request,secrets,re,psutil
from pathlib import Path
from sender_health import sender_status
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(os.environ['LOCALAPPDATA'])/'PhucThanh'
CREATE_NO_WINDOW=0x08000000
CACHE={'updated':0,'cards':[]}
CSRF=secrets.token_urlsafe(32)
SAFE_OPEN_LOCK=threading.Lock()
SERVICE_LOCK=threading.Lock()
def dispatch(path,method='GET',body=None):
 if not re.fullmatch(r'/dispatch(?:/(?:[a-f0-9]{64}|settings|intake|activity|execution|manual))?',path):raise ValueError('Invalid path')
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
   if errors:
    state='warn' if alive else 'bad'
    text+=' · Có lỗi được ghi nhận (cần kiểm tra log)'
   if name=='Đọc Zalo' and data.get('source_pause') and not errors and alive and age<=180:
    return card(name,'ok',text+' · Tạm hoãn đọc khi dùng Zalo / chờ nghỉ 30 giây; vẫn chuyển tin đã lưu.')
   if name=='Đọc Zalo' and (age>180 or data.get('phase')=='waiting' or data.get('key_in_memory') is False):
    state='bad'
    text+=' · CẢNH BÁO: Zalo chưa đồng bộ tin. Kiểm tra tương thích sau cập nhật; giữ nguyên hàng đợi để khôi phục.'
    recovery=data.get('recovery',{})
    if recovery.get('needs_review'):
     if recovery.get('stopped_after_limit'):
      text+=' · ĐÃ DỪNG TỰ QUÉT KHÓA: thất bại 3/3 lần. Cần kiểm tra và xử lý thủ công.'
     else:
      text+=' · Đang phục hồi khóa: '+str(recovery.get('attempts',0))+'/3 lần; cách nhau ít nhất 60 giây.'
    if recovery.get('zalo_version'):text+=' · '+recovery['zalo_version']
  return card(name,state,text)
 except Exception:return card(name,'bad','Chưa đọc được trạng thái')
def inbound_status(path,alive):
 try:
  data=json.loads(path.read_text(encoding='utf-8-sig'))
  queued=int(data.get('outbox',{}).get('queued',0));stamp=float(data.get('updated_at',0))
  review=int(data.get('outbox',{}).get('delivery_review',0))
  issues=data.get('delivery_issues',[])
  source_error=data.get('errors',{}).get('source')
  hub=data.get('errors',{}).get('hub');stale=time.time()-stamp>180
  state='bad' if hub or source_error or review or issues or stale or not alive else ('warn' if queued else 'ok')
  detail=str(queued)+' tin đã đọc đang chờ chuyển vào Chatwoot.'
  if review:detail+=' '+str(review)+' tin lỗi đã tách riêng, cần kiểm tra; các tin khác vẫn đồng bộ.'
  for issue in issues[:5]:detail+=' · Tin '+issue['message_id']+': '+issue['reason']
  if source_error:detail+=' Lỗi nguồn: '+str(source_error)+'.'
  if hub:detail+=' Hub từ chối/không nhận được tin: '+str(hub)+'.'
  if not alive:detail+=' Bộ đọc đã dừng.'
  if stale:detail+=' Trạng thái đã cũ; số tin chờ là lần ghi nhận cuối.'
  pause=data.get('source_pause')
  if not alive or stale:activity='Bộ đọc đã dừng / trạng thái đã cũ'
  elif source_error=='waiting_for_single_running_zalo_session':activity='CHƯA ĐỌC ĐƯỢC — không tìm thấy một phiên Zalo hợp lệ'
  elif source_error:activity='CHƯA ĐỌC ĐƯỢC — lỗi nguồn Zalo'
  elif data.get('source_reading'):activity='ĐANG ĐỌC DỮ LIỆU ZALO'
  elif pause in ('zalo_foreground','zalo_window_open'):activity='TẠM HOÃN — cửa sổ Zalo đang mở'
  elif pause=='safe_open_requested':activity='ĐANG CHỜ MỞ ZALO AN TOÀN — tạm dừng đọc'
  elif pause=='window_state_unknown':activity='TẠM HOÃN — chưa xác định được cửa sổ Zalo'
  elif pause=='waiting_30_seconds':activity='CHỜ ĐỦ 30 GIÂY sau khi đóng Zalo xuống khay'
  else:activity='ĐỌC NỀN KHI ZALO Ở KHAY — đang nghỉ giữa các lượt'
  if pause:detail+=' Đang hoãn đọc Zalo khi người dùng thao tác / chờ nghỉ 30 giây.'
  try:
   from reader_lifecycle import status as lifecycle_read
   lifecycle=lifecycle_read(path.parent)
   labels={'stopping':'ĐANG DỪNG HẲN TIẾN TRÌNH BỘ ĐỌC','stopped':'BỘ ĐỌC ĐÃ THOÁT — chờ mở Zalo','stopped_window_open':'BỘ ĐỌC ĐÃ TẮT HẲN — cửa sổ Zalo đang mở','waiting_tray':'BỘ ĐỌC ĐANG TẮT — chờ xuống khay đủ 30 giây','starting':'ĐANG BẬT LẠI BỘ ĐỌC','waiting_zalo':'BỘ ĐỌC ĐANG TẮT — chưa thấy phiên Zalo chính'}
   labels.update(manual_stop='BỘ ĐỌC ĐÃ DỪNG — cờ dừng thủ công',reader_missing='BỘ ĐỌC KHÔNG CHẠY — cần kiểm tra khởi động')
   if lifecycle.get('error'):
    activity='LỖI GIÁM SÁT BỘ ĐỌC — '+lifecycle['error'];state='bad'
    detail+=' Thao tác lỗi: '+lifecycle.get('error_operation','chưa rõ')+'.'
   elif time.time()-lifecycle.get('updated_at',0)<15 and lifecycle.get('state') in labels:
    activity=labels[lifecycle['state']]
    if lifecycle['state'] in ('waiting_zalo','reader_missing'):state='bad'
    elif not (hub or review or issues):state='warn' if queued else 'ok'
   elif time.time()-lifecycle.get('updated_at',0)>=15:
    activity='LỖI GIÁM SÁT BỘ ĐỌC — trạng thái điều khiển đã cũ';state='bad'
  except Exception:
   activity='LỖI GIÁM SÁT BỘ ĐỌC — không đọc được trạng thái điều khiển';state='bad'
  return dict(activity=activity,last_read_start=data.get("last_read_start"),last_read_end=data.get("last_read_end"),state=state,queued=queued,review=review,issues=issues,updated_at=stamp,detail=detail,label='Cần xử lý' if state=='bad' else ('Có tin chờ' if queued else 'Đã chuyển hết tin đã đọc'),action='Tin lỗi được giữ nguyên, không gửi lại tự động khi cần kiểm tra. Đây là chiều Zalo → Chatwoot, độc lập với bộ gửi tin ra Zalo.')
 except Exception:
  return dict(state='bad',queued=None,updated_at=0,label='Chưa rõ trạng thái',detail='Không đọc được hàng đợi Zalo → Chatwoot; không thể xác nhận đã đồng bộ.',action='Kiểm tra bộ đọc và tệp trạng thái.')

def snapshot():
 proc=[]
 for process in psutil.process_iter(['pid','name','cmdline']):
  try:
   info=process.info
   if re.search('python|Photoshop|Illustrator',info.get('name') or '',re.I):
    proc.append({'pid':info.get('pid'),'Name':info['name'],'CommandLine':' '.join(info.get('cmdline') or [])})
  except (psutil.NoSuchProcess,psutil.AccessDenied):
   continue
 def alive(marker):return any(marker.lower() in str(p.get('CommandLine','')).lower() for p in proc)
 sender=sender_status(ROOT/"ZaloDesktopReader/state/sender",alive("zalo_desktop.sender"))
 inbound=inbound_status(ROOT/"ZaloDesktopReader/state/status.json",alive("zalo_desktop.reader"))
 cards=[card("Tin Zalo → Chatwoot",inbound["state"],inbound["detail"])]
 for title,folder in [('Đọc Zalo','ZaloDesktopReader'),('Đọc WhatsApp','WhatsAppDesktopReader'),('Đọc Viber','ViberDesktopReader')]:
  cards.append(read_status(title,ROOT/folder/'state/status.json',alive(folder)))
 cards.append(read_status('Đọc / xuất file Windows',ROOT/'ArtworkInspector/state.json',alive('artworkinspector\\worker.py'),True))
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
bot=None
if c.execute("SELECT 1 FROM sqlite_master WHERE name='bot101_runtime'").fetchone():
 row=c.execute('SELECT state,detail,request_id,updated FROM bot101_runtime WHERE id=1').fetchone()
 if row:bot=dict(row)
print(json.dumps({'bot101':bot,'queues':{t:[list(r) for r in c.execute('select state,count(*) from '+t+' group by state')] for t in tables},'jobs':sorted(jobs,key=lambda x:x['created'],reverse=True)[:20]}))
"""
  docker=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
  out=command([docker,'exec','phucthanh-chatwoot-hub-1','/app/.venv/bin/python','-c',code])
  data=json.loads(out.stdout);queue=data['queues'];jobs=data['jobs']
  bot=data.get('bot101')
  cards.append(card('API gửi tin máy 101',('bad' if bot['state'] in ('error','blocked','uncertain') else 'ok') if bot else 'idle',(bot['detail']+' · '+bot.get('request_id','')) if bot else 'Chờ tin cần gửi; không gọi API khi rảnh.'))
 except Exception:cards.append(card('Hàng đợi file','warn','Chưa đọc được thống kê Docker'))
 from service_control import collect_services
 return dict(updated=time.time(),cards=cards,services=collect_services(proc),queues=queue,jobs=jobs,zalo_sender=sender,zalo_inbound=inbound)
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
  if self.path=='/api/zalo/safe-open':
   if not SAFE_OPEN_LOCK.acquire(False):self.reply(409,{'detail':'Đang chờ mở Zalo an toàn'});return
   try:
    from safe_zalo import open_requested
    self.reply(200,open_requested(ROOT/'ZaloDesktopReader/state'))
   except Exception as ex:self.reply(409,{'detail':str(ex) if isinstance(ex,ValueError) else 'Chưa mở Zalo; giữ bộ đọc tạm dừng để kiểm tra.'})
   finally:SAFE_OPEN_LOCK.release()
   return
  if self.path=='/api/service/restart':
   if not SERVICE_LOCK.acquire(False):self.reply(409,{'detail':'Đang khởi động lại một dịch vụ khác, vui lòng đợi'});return
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=2048:raise ValueError('Yêu cầu không hợp lệ')
    body=json.loads(self.rfile.read(size))
    from service_control import restart_service
    res=restart_service(str(body.get('id') or ''))
    global CACHE
    CACHE=snapshot()
    self.reply(200,res)
   except Exception as ex:self.reply(400,{'detail':str(ex) if isinstance(ex,ValueError) else 'Không khởi động lại được dịch vụ'})
   finally:SERVICE_LOCK.release()
   return
  if not re.fullmatch(r'/api/dispatch/(?:[a-f0-9]{64}|settings|intake|execution|manual)',self.path):self.send_error(404);return
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<=16000:raise ValueError('Yêu cầu quá dài')
   result=dispatch(self.path[4:],'POST',json.loads(self.rfile.read(size)));self.reply(result['status'],result['data'])
  except Exception as ex:self.reply(400,{'detail':str(ex) if isinstance(ex,ValueError) else 'Không gửi được yêu cầu; kiểm tra trạng thái trước khi thử lại'})
 def do_GET(self):
  if self.headers.get('Host') not in ('127.0.0.1:8096','localhost:8096'):self.send_error(403);return
  if self.path=='/api/flow-today':
   from flow_daily import daily
   try:self.reply(200,daily())
   except Exception:self.reply(503,{'detail':'Không đọc được thống kê trực tiếp'})
   return
  if self.path=='/flow-motion.js':
   raw=Path(__file__).with_name('flow-motion.js').read_bytes()
   self.send_response(200);self.send_header('Content-Type','application/javascript; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw);return
  if self.path=='/api/redraw-clusters':
   import sqlite3
   from contextlib import closing
   path=Path(__file__).resolve().parent.parent/'VectorRedraw'/'state.sqlite'
   with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
    db.row_factory=sqlite3.Row
    rows=db.execute("select c.*,j.status as status from redraw_clusters c inner join jobs j on j.id=c.job order by c.created desc limit 300").fetchall()
   self.reply(200,{'clusters':[dict(r) for r in rows]});return
  if self.path.startswith('/batch/'):
   from batch_view import serve
   if not serve(self,self.path):self.send_error(404)
   return
  if self.path=='/api/session':self.reply(200,{'csrf':CSRF});return
  if self.path.startswith('/api/dispatch'):
   try:
    result=dispatch(self.path[4:]);self.reply(result['status'],result['data'])
   except Exception:self.reply(503,{'detail':'Bộ điều phối chưa sẵn sàng'})
   return
  if self.path not in ('/','/api/status'):self.send_error(404);return
  current=dict(CACHE)
  if self.path=='/api/status':
   try:
    live=json.loads((ROOT/'ZaloDesktopReader/state/status.json').read_text(encoding='utf-8-sig'))
    current['zalo_inbound']=inbound_status(ROOT/'ZaloDesktopReader/state/status.json',live.get('phase')!='stopped')
   except Exception:pass
  raw=json.dumps(current,ensure_ascii=False).encode() if self.path=='/api/status' else Path(__file__).with_name('dispatch.html').read_bytes()
  self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8' if self.path=='/api/status' else 'text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
 def log_message(self,*args):pass
if __name__=='__main__':
 server=ThreadingHTTPServer(('127.0.0.1',8096),Handler)
 from reader_lifecycle import supervise
 threading.Thread(target=supervise,args=(ROOT/'ZaloDesktopReader/state',),daemon=True).start()
 threading.Thread(target=poll,daemon=True).start();server.serve_forever()


