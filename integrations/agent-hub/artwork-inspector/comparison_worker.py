"""Local read-only thumbnails. No Adobe writes, copies, RIP or customer messaging."""
import base64,hashlib,io,json,sys,subprocess
from concurrent.futures import ThreadPoolExecutor
REFERENCE_POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix="file-references")
from pathlib import Path,PureWindowsPath,PurePosixPath
from PIL import Image,ImageOps,ImageCms
ROOTS={'V:':r'\\192.168.1.203\file in','T:':r'\\Myhan1522\thiet ke pet'}
SEARCH_ROOTS={**ROOTS,'Y:':r'\\192.168.1.203\file may in','Z:':r'\\192.168.1.203\pet'}

def resolve(job,archive):
 if job['kind'] in ('source','designer'):
  rel=PurePosixPath(job['path'].replace('\\','/'));root=Path(archive).resolve()
  if rel.is_absolute() or '..' in rel.parts or ':' in str(rel):raise ValueError('Đường dẫn nguồn không hợp lệ')
  path=(root/str(rel)).resolve()
 else:
  p=PureWindowsPath(job['path']);drive=p.drive.upper()
  if drive not in ROOTS or not p.is_absolute() or any(x=='..' or ':' in x for x in p.parts[1:]):raise ValueError('Đường dẫn ảnh xuất không thuộc V/T')
  root=Path(ROOTS[drive]).resolve();path=root.joinpath(*p.parts[1:]).resolve()
 if root not in path.parents:raise ValueError('File ngoài thư mục cho phép')
 if not path.is_file() and path.suffix.lower() in ('.tif','.tiff'):
  other=path.with_suffix('.tiff' if path.suffix.lower()=='.tif' else '.tif')
  if other.is_file():path=other
 if not path.is_file():raise ValueError('Chưa tìm thấy file đúng đường dẫn/tên: '+job['path'])
 return path


def reference_files(job):
 """List names only in this customer's source folder; never open/render matches."""
 import re
 if job.get('kind')!='output':return None
 search_roots=SEARCH_ROOTS
 target=PureWindowsPath(job.get('print_path',job['path']));drive=target.drive.upper()
 if drive not in search_roots or not target.is_absolute() or len(target.parts)<3 or any(x=='..' or ':' in x for x in target.parts[1:]):return None
 stem=PureWindowsPath(job.get('print_path',job['path'])).stem
 keyword=re.sub(r'(?:[. _]+[0-9]+)+$','',stem.rsplit('-',1)[-1]).strip()
 keyword=re.sub(r'^(?:PET|TDVD|DUOI|KET|MAC)\s+','',keyword,flags=re.I).strip()
 result={'keyword':keyword,'files':[],'folder':str(PureWindowsPath(drive+'\\',target.parts[1])),'error':'','truncated':False}
 if len(keyword)<2:
  result['error']='Tên quá ngắn để tìm file tham khảo';return result
 root=Path(search_roots[drive]).resolve();folder=(root/target.parts[1]).resolve()
 if root not in folder.parents:return None
 try:
  if not folder.is_dir():raise OSError('folder unavailable')
  import os
  count=0
  def failed(exc):raise exc
  for directory,dirs,files in os.walk(folder,followlinks=False,onerror=failed):
   dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
   for name in files:
    count+=1
    if count>50000:result['truncated']=True;break
    candidate=Path(directory)/name
    if keyword.casefold() not in name.casefold() or candidate.suffix.lower() not in ('.tif','.tiff','.jpg','.jpeg','.png','.pdf','.ai','.psd','.prt','.prn'):continue
    if candidate.is_symlink():continue
    result['files'].append(str(candidate.relative_to(folder)))
    if len(result['files'])>=500:result['truncated']=True;break
   if result['truncated']:break
  result['files'].sort(key=str.casefold)
 except OSError:result['error']='Chưa đọc được thư mục file tham khảo'
 return result

def png(im,icc=None):
 im.thumbnail((1000,1000))
 if icc and im.mode in ('CMYK','RGB'):
  try:im=ImageCms.profileToProfile(im,ImageCms.ImageCmsProfile(io.BytesIO(icc)),ImageCms.createProfile('sRGB'),outputMode='RGB')
  except (ValueError,OSError):im=im.convert('RGB')
 else:im=im.convert('RGBA')
 out=io.BytesIO();im.save(out,format='PNG',optimize=True)
 return {'data':base64.b64encode(out.getvalue()).decode()}


def white_spot_preview(path, im):
 """Display a sole Photoshop spot plate on an otherwise blank white RGB TIFF.
 The original file and ink channels are never rewritten.
 """
 import struct
 if im.format!='TIFF' or im.mode!='RGB' or im.tag_v2.get(338)!=(0,) or im.tag_v2.get(277)!=4 or im.tag_v2.get(258)!=(8,8,8,8):return None
 resources=im.tag_v2.get(34377,b'');names=[];offset=0
 while offset+12<=len(resources):
  if resources[offset:offset+4]!=b'8BIM':break
  rid=struct.unpack_from('>H',resources,offset+4)[0]
  end=offset+6+((resources[offset+6]+2)//2)*2
  if end+4>len(resources):break
  length=struct.unpack_from('>I',resources,end)[0];payload=resources[end+4:end+4+length]
  if len(payload)!=length:break
  if rid==1006:
   pos=0
   while pos<len(payload):
    size=payload[pos];names.append(payload[pos+1:pos+1+size].decode('latin1'));pos+=size+1
  offset=end+4+length+(length%2)
 if len(names)!=1 or not names[0].casefold().startswith('spot'):return None
 if im.getextrema()!=((255,255),(255,255),(255,255)):return None
 if path.stat().st_size>256*1024**2:raise ValueError('TIFF spot quá lớn để tạo preview riêng')
 data=bytearray(path.read_bytes());endian='<' if data[:2]==b'II' else '>'
 if struct.unpack_from(endian+'H',data,2)[0]!=42:raise ValueError('Preview spot chưa hỗ trợ BigTIFF')
 start=struct.unpack_from(endian+'I',data,4)[0];count=struct.unpack_from(endian+'H',data,start)[0]
 for i in range(count):
  pos=start+2+i*12;tag,kind,num=struct.unpack_from(endian+'HHI',data,pos)
  if tag==338 and kind==3 and num==1:
   # In-memory decoder hint only: recover the fourth channel discarded as RGBX.
   struct.pack_into(endian+'H',data,pos+8,2)
   with Image.open(io.BytesIO(data)) as decoded:
    plate=ImageOps.invert(decoded.getchannel('A'))
    result=Image.new('RGBA',decoded.size,'white');result.putalpha(plate)
    return result
 raise ValueError('Không đọc được kênh spot của TIFF')

def render(job,archive):
 fallback=False
 try:path=resolve(job,archive)
 except ValueError as exc:
  if job['kind']!='output' or not job.get('fallback') or not str(exc).startswith('Chưa tìm thấy'):raise
  job={**job,'kind':'designer','path':job['fallback']['path'],'sha256':job['fallback']['sha256']}
  path=resolve(job,archive);fallback=True
 before=path.stat()
 if before.st_size>1024**3:raise ValueError('Nguồn vượt 1GiB; cần tạo preview riêng')
 suffix=path.suffix.lower()
 # JPEG bytes are reused for hashing/decoding, avoiding a second NAS read.
 jpeg_bytes=path.read_bytes() if suffix in ('.jpg','.jpeg') and before.st_size<=64*1024**2 else None
 if jpeg_bytes is not None:digest=hashlib.sha256(jpeg_bytes).hexdigest()
 else:
  with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 if job.get('sha256') and digest!=job['sha256']:raise ValueError('SHA256 file gốc không khớp')
 images=[]
 if suffix in ('.jpg','.jpeg'):
  Image.MAX_IMAGE_PIXELS=350_000_000
  with Image.open(io.BytesIO(jpeg_bytes) if jpeg_bytes is not None else path) as im:
   if im.width*im.height>350_000_000:raise ValueError('Ảnh vượt giới hạn preview350MP')
   icc=im.info.get('icc_profile')
   if jpeg_bytes is not None and len(jpeg_bytes)<=2_000_000 and max(im.size)<=1200 and im.mode=='RGB' and not icc and im.getexif().get(274,1)==1:
    images=[{'data':base64.b64encode(jpeg_bytes).decode()}]
   else:
    im.draft('RGB',(1000,1000));im.thumbnail((1000,1000))
    frame=ImageOps.exif_transpose(im)
    if icc and frame.mode in ('CMYK','RGB'):
     frame=ImageCms.profileToProfile(frame,ImageCms.ImageCmsProfile(io.BytesIO(icc)),ImageCms.createProfile('sRGB'),outputMode='RGB')
    else:frame=frame.convert('RGB')
    out=io.BytesIO();frame.save(out,format='JPEG',quality=85)
    images=[{'data':base64.b64encode(out.getvalue()).decode()}]
 elif suffix in ('.pdf','.ai'):
  import pymupdf as fitz
  with fitz.open(path) as doc:
   if doc.needs_pass or not 1<=len(doc)<=8:raise ValueError('File khóa hoặc quá 8artboard/trang; chưa tạo đủ preview')
   for page in doc:
    pix=page.get_pixmap(matrix=fitz.Matrix(1000/max(page.rect.width,page.rect.height),1000/max(page.rect.width,page.rect.height)),colorspace=fitz.csRGB,alpha=True)
    images.append(png(Image.open(io.BytesIO(pix.tobytes('png')))))
 elif suffix in ('.jpg','.jpeg','.png','.webp','.tif','.tiff','.psd'):
  Image.MAX_IMAGE_PIXELS=350_000_000
  with Image.open(path) as im:
   count=max(1,getattr(im,'n_frames',1)) if suffix in ('.tif','.tiff') else 1
   if count>8:raise ValueError('TIFF quá 8trang; cần kiểm tra preview')
   spot=white_spot_preview(path,im) if count==1 and suffix in ('.tif','.tiff') else None
   if spot is not None:images.append(png(spot))
   for n in range(0 if spot is not None else count):
    if suffix in ('.tif','.tiff'):im.seek(n)
    if im.width*im.height>350_000_000:raise ValueError('Ảnh vượt giới hạn preview350MP')
    icc=im.info.get('icc_profile');im.draft('RGB',(1000,1000))
    frame=im.copy();images.append(png(ImageOps.exif_transpose(frame),icc))
 else:raise ValueError('Định dạng chưa hỗ trợ preview')
 after=path.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('File thay đổi khi đọc; tải lại preview')
 return {'images':images,'source_sha256':digest,'used_fallback':fallback}

def sync(client,cfg):
 if cfg['account']!='zalo-personal-1':return 'idle'
 prefix='/adapters/'+cfg['account']+'/order-comparison-previews'
 r=client.get(prefix)
 if r.status_code==404:return 'waiting_erp_restart'
 r.raise_for_status();reply=r.json();job=reply.get('job')
 if not job:return 'idle'
 try:
  proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--render'],input=json.dumps({'job':job,'archive':cfg['archive']['root']}),text=True,encoding='utf-8',capture_output=True,timeout=100,creationflags=0x08000000)
  if proc.returncode:raise ValueError('Bộ tạo preview lỗi; kiểm tra định dạng/khả năng đọc file')
  result=json.loads(proc.stdout)
 except subprocess.TimeoutExpired:result={'error':'Tạo preview quá100giây; nguồn giữ nguyên, cần kiểm tra'}
 except Exception as exc:result={'error':str(exc)[:450] if isinstance(exc,ValueError) else type(exc).__name__}
 # Rolling deployment: old ERP only accepts PNG until its restart.
 if reply.get('preview_version',1)<2:
  for item in result.get('images',[]):
   with Image.open(io.BytesIO(base64.b64decode(item['data']))) as im:
    if im.format=='JPEG':item.update(png(im))
 response=client.post(prefix+'/'+job['id'],json=result);response.raise_for_status()
 if job.get('kind')=='output' and reply.get('preview_version',1)>=2:REFERENCE_POOL.submit(send_references,cfg,job)
 return response.json()['state']


def send_references(cfg,job):
 """Separate bounded worker; preview has already been delivered before scheduling."""
 import httpx
 try:
  proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--references'],input=json.dumps({'job':job}),text=True,encoding='utf-8',capture_output=True,timeout=30,creationflags=0x08000000)
  if proc.returncode:raise ValueError('reference process failed')
  refs=json.loads(proc.stdout)
  if not isinstance(refs,dict):raise ValueError('invalid reference report')
 except Exception:
  refs={'keyword':PureWindowsPath(job['path']).stem,'folder':'','files':[],'error':'Tìm tên file quá lâu hoặc thư mục chưa truy cập được; nhấn Làm mới sau.','truncated':False}
 try:
  with httpx.Client(base_url=cfg['hub_url'],headers={'Authorization':'Bearer '+cfg['ingest_token']},timeout=35,trust_env=False) as client:
   response=client.post('/adapters/'+cfg['account']+'/order-comparison-previews/'+job['id'],json={'reference_only':True,'references':refs});response.raise_for_status()
 except Exception:
  pass  # Preview remains available; the next cache refresh retries references.


def ensure_started(configs):
 import time
 state=Path(__file__).with_name('comparison-state.json')
 try:
  if time.time()-state.stat().st_mtime<180:return
 except OSError:pass
 args=[sys.executable,str(Path(__file__).resolve()),'--watch']
 for path in configs:args.extend(['--config',path])
 subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)

def watch(configs):
 import time,msvcrt,httpx
 state=Path(__file__).with_name('comparison-state.json');lock=state.with_suffix('.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
 try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
 except OSError:return
 while True:
  result='idle'
  try:
   for path in configs:
    cfg=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if cfg['account']!='zalo-personal-1':continue
    from urllib.parse import urlparse
    u=urlparse(cfg['hub_url'])
    if u.hostname not in ('127.0.0.1','localhost') or u.scheme!='http':raise ValueError('Expected local Hub')
    with httpx.Client(base_url=cfg['hub_url'],headers={'Authorization':'Bearer '+cfg['ingest_token']},timeout=35,trust_env=False) as client:result=sync(client,cfg)
  except Exception as exc:result='error:'+type(exc).__name__
  state.write_text(json.dumps({'time':time.time(),'state':result}),encoding='utf-8');time.sleep(1 if result in ('done','error') else 3)

if __name__=='__main__':
 if '--watch' in sys.argv:
  import argparse
  parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');parser.add_argument('--config',action='append',required=True);args=parser.parse_args();watch(args.config)
 else:
  try:
   q=json.load(sys.stdin)
   result=reference_files(q['job']) if '--references' in sys.argv else render(q['job'],q['archive'])
  except Exception as exc:result={'error':str(exc)[:450] if isinstance(exc,(ValueError,OSError)) else type(exc).__name__}
  print(json.dumps(result))
