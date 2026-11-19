"""Loopback-only batch viewer: readonly sources, separate cached image previews."""
import html,io,json,os,re,subprocess,threading,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from PIL import Image,ImageOps
import pillow_jxl
ROOT=Path(__file__).parent
CACHE=ROOT/'batch-preview-cache'
LOCK=threading.BoundedSemaphore(2)
DOCKER=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'

def read(q):
 p=subprocess.run([DOCKER,'exec','-i','-e','PYTHONPATH=/app','phucthanh-chatwoot-hub-1','/app/.venv/bin/python','-c',(ROOT/'batch_reader.py').read_text(encoding='utf-8-sig')],input=json.dumps(q).encode(),capture_output=True,timeout=25,creationflags=0x08000000)
 if p.returncode:raise ValueError('Không tìm thấy cụm/ảnh hoặc Hub chưa sẵn sàng.')
 return p.stdout

def batch(identity):return json.loads(read({'op':'view','batch':identity}))
def esc(v):return html.escape(str(v or ''),quote=True)
def stamp(v):
 try:return datetime.fromtimestamp(float(v),timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S')
 except (ValueError,TypeError,OverflowError):return ''
def image_asset(a):return Path(str(a.get('name',''))).suffix.lower() in ('.jpg','.jpeg','.png','.jxl','.webp','.gif','.bmp','.tif','.tiff')
def images(m):
 if m.get('image_ids'):return [('m',i) for i in range(len(m['image_ids']))]
 return [('a',i) for i,a in enumerate(m.get('assets',[])) if image_asset(a)]
def render(b):
 chunks=[]
 for i,m in enumerate(b['messages']):
  role=m.get('role');label={'customer':'Khách','staff':'Nhân viên'}.get(role,'Khác')
  photos=''.join(f'<a href="/batch/{b["id"]}/image/{i}/{kind}/{n}" target="_blank" rel="noopener"><img src="/batch/{b["id"]}/image/{i}/{kind}/{n}" loading="lazy" alt="Ảnh {n+1} — nếu chưa tải được, bấm để xem lỗi"></a>' for kind,n in images(m))
  files=''.join('<li>'+esc(a.get('name','File chưa có tên'))+(' · chưa tải đủ' if a.get('state') not in ('ready',None) else '')+'</li>' for a in m.get('assets',[])+m.get('unresolved_assets',[]) if not image_asset(a))
  chunks.append(f'<article class="{ "staff" if role=="staff" else "customer" }"><header><strong>{esc(m.get("sender"))}</strong> <span>{label} · {stamp(m.get("timestamp"))}</span></header><div class="text">{esc(m.get("text"))}</div><div class="images">{photos}</div><ul>{files}</ul><small>Tin nguồn: {esc(m.get("message_id"))}</small></article>')
 return ('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cụm tin · '+esc(b['group'])+'</title><style>body{font:16px system-ui;background:#eef2f6;color:#183047;margin:0}main{max-width:1050px;margin:auto;padding:24px}h1{font-size:25px}article{background:white;border-radius:12px;padding:18px;margin:16px 0;border-left:5px solid #2671c7}.staff{border-left-color:#cd8a24;background:#fffaf0}header span,small{color:#566477;font-size:13px}header{margin-bottom:12px}.text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6}.images{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px}.images img{max-width:100%;width:300px;max-height:440px;object-fit:contain;background:repeating-conic-gradient(#eee 0% 25%,white 0% 50%) 0/16px 16px;border:1px solid #d7dfe6;border-radius:7px}li{overflow-wrap:anywhere}small{display:block;margin-top:12px}</style><main><a href="/">← Điều phối</a><h1>'+esc(b['group'])+'</h1><p>'+str(len(b['messages']))+' tin · Gom '+esc(b.get('wait_minutes'))+' phút · '+stamp(b['created'])+' (Việt Nam)</p><p>Chỉ xem nguồn đã gửi n8n. Ảnh là preview; file gốc được giữ nguyên. Không chạy lại đơn hay xuất file.</p>'+''.join(chunks)+'</main></html>').encode()

def archive_bytes(b,mindex,index):
 asset=b['messages'][mindex]['assets'][index]
 if not image_asset(asset):raise ValueError('Chỉ cho xem ảnh.')
 configs=json.loads((ROOT.parent/'ArtworkInspector/config-paths.json').read_text(encoding='utf-8-sig'))
 root=None
 for name in configs:
  cfg=json.loads(Path(name).read_text(encoding='utf-8-sig'))
  if cfg.get('account')==b['account']:root=Path(cfg['archive']['root']).resolve();break
 if root is None:raise ValueError('Chưa cấu hình kho nguồn.')
 rel=asset.get('relative_path','').replace('\\','/')
 if not rel or ':' in rel or '..' in Path(rel).parts or Path(rel).is_absolute():raise ValueError('Đường dẫn nguồn không hợp lệ.')
 path=(root/rel).resolve()
 if root not in path.parents or path.stat().st_size>32*1024*1024:raise ValueError('Ảnh quá lớn hoặc ngoài kho nguồn.')
 raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=asset.get('sha256'):raise ValueError('Nguồn thay đổi, không hiển thị nhầm phiên bản.')
 return raw

def convert(raw):
 with Image.open(io.BytesIO(raw)) as original:
  if original.width*original.height>80_000_000:raise ValueError('Ảnh quá lớn để xem nhanh.')
  im=ImageOps.exif_transpose(original);im.thumbnail((1400,1400))
  transparent='A' in im.getbands() or 'transparency' in im.info
  im=im.convert('RGBA' if transparent else 'RGB');out=io.BytesIO()
  im.save(out,format='PNG' if transparent else 'JPEG',**({} if transparent else {'quality':85}))
  return out.getvalue(),'image/png' if transparent else 'image/jpeg'

def preview(identity,mindex,kind,index):
 key=f'{identity}-{mindex}-{kind}-{index}'
 with LOCK:
  CACHE.mkdir(exist_ok=True)
  for suffix,mime in (('.png','image/png'),('.jpg','image/jpeg')):
   p=CACHE/(key+suffix)
   if p.exists():return p.read_bytes(),mime
  b=batch(identity)
  if (kind,index) not in images(b['messages'][mindex]):raise ValueError('Ảnh không thuộc tin nguồn.')
  raw=read({'op':'image','batch':identity,'message':mindex,'image':index}) if kind=='m' else archive_bytes(b,mindex,index)
  data,mime=convert(raw);p=CACHE/(key+('.png' if mime=='image/png' else '.jpg'));p.write_bytes(data)
  return data,mime

def serve(handler,path):
 match=re.fullmatch(r'/batch/([a-f0-9]{64})(?:/image/(\d+)/(m|a)/(\d+))?',path)
 if not match:return False
 try:
  identity,mindex,kind,index=match.groups()
  if mindex is None:data,mime=render(batch(identity)),'text/html; charset=utf-8'
  else:data,mime=preview(identity,int(mindex),kind,int(index))
  handler.send_response(200);handler.send_header('Content-Type',mime);handler.send_header('Cache-Control','private, no-store');handler.send_header('X-Content-Type-Options','nosniff');handler.send_header('Referrer-Policy','no-referrer');handler.send_header('Content-Security-Policy',"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'");handler.end_headers();handler.wfile.write(data)
 except Exception as exc:handler.send_error(503,'Preview unavailable; check source or Hub')
 return True
