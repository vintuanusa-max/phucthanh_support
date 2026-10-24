"""Copy approved TIFFs only, preserve source, never overwrite another revision."""
import hashlib,os,uuid
from PIL import Image
from pathlib import Path,PurePosixPath

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def copy_approved(root,files):
 root=Path(root).resolve();pairs=[];targets={}
 for f in files:
  group,name=f['group'],f['name']
  if not group or group in ('.','..') or any(c in group for c in '/\\:'):raise ValueError('Invalid customer folder')
  if Path(name).name!=name or any(c in name for c in '/\\:') or Path(name).suffix.lower() not in ('.tif','.tiff','.jpg','.jpeg'):raise ValueError('Invalid TIFF name')
  rel=PurePosixPath(f['source'])
  if rel.is_absolute() or '..' in rel.parts or '\\' in f['source'] or ':' in f['source']:raise ValueError('Invalid source')
  src=(root/str(rel)).resolve();dest=(root/group/name).resolve()
  if root not in src.parents or root not in dest.parents or src.parent==dest.parent or rel.parts[0]!=group:raise ValueError('Source outside customer')
  if dest in targets and targets[dest]!=f['sha256']:raise ValueError('Hai bản TIFF khác nhau cùng tên; duyệt riêng từng bản')
  targets[dest]=f['sha256']
  if digest(src)!=f['sha256']:raise ValueError('TIFF nguồn đã thay đổi')
  if Path(name).suffix.lower() in ('.jpg','.jpeg'):
   Image.MAX_IMAGE_PIXELS=350_000_000
   with Image.open(src) as im:
    if im.format!='JPEG' or im.mode!='CMYK' or hashlib.sha256(im.info.get('icc_profile',b'')).hexdigest()!=f.get('icc_sha256'):raise ValueError('JPG CMYK/ICC không đúng bản đã xuất')
   original=bool(f.get('original_source'))
   ai_rel=PurePosixPath(f.get('original_source') if original else f.get('ai_source',''))
   if ai_rel.is_absolute() or '..' in ai_rel.parts or '\\' in str(ai_rel) or ':' in str(ai_rel):raise ValueError('Invalid AI source')
   ai=(root/str(ai_rel)).resolve()
   if root not in ai.parents or ai.parent!=src.parent or ai.suffix.lower() not in (('.pdf','.ai') if original else ('.ai',)) or digest(ai)!=f.get('original_sha256' if original else 'ai_sha256'):raise ValueError('AI gốc chưa xác minh')
  if dest.exists() and digest(dest)!=f['sha256']:raise ValueError('Đã có TIFF khác cùng tên: '+group+'/'+name+'; chưa ghi đè')
  pairs.append((src,dest,f))
 for src,dest,f in pairs:
  if dest.exists():
   if digest(dest)!=f['sha256']:raise ValueError('Destination changed')
   continue
  tmp=dest.parent/('.approval-'+uuid.uuid4().hex+'.pending')
  try:
   with src.open('rb') as inp,tmp.open('xb') as out:
    while True:
     b=inp.read(1024*1024)
     if not b:break
     out.write(b)
    out.flush();os.fsync(out.fileno())
   if digest(tmp)!=f['sha256']:raise ValueError('Copy hash mismatch')
   # Windows rename is atomic and refuses an existing destination.
   if os.name!='nt':raise ValueError('Copy worker requires Windows no-replace rename')
   try:os.rename(tmp,dest)
   except FileExistsError:
    if digest(dest)!=f['sha256']:raise ValueError('Tên file vừa bị dùng bởi bản khác')
  finally:
   if tmp.exists():tmp.unlink()
  if digest(dest)!=f['sha256']:raise ValueError('Destination hash mismatch')
 return [f['group']+'/'+f['name'] for f in files]

def sync_approval(client,cfg):
 prefix='/adapters/'+cfg['account']+'/print-approvals'
 r=client.get(prefix)
 if r.status_code==404:return 'approval_idle'
 r.raise_for_status();job=r.json().get('job')
 if not job:return 'approval_idle'
 try:result={'paths':copy_approved(cfg['archive']['root'],job['files'])}
 except (ValueError,OSError) as exc:result={'error':str(exc)[:900]}
 r=client.post(prefix+'/'+job['id'],json=result);r.raise_for_status()
 return 'approval_'+r.json()['state']

