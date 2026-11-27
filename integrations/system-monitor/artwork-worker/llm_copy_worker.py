"""Copy verified DESIGNER outputs without Adobe; atomic no-overwrite publication."""
import hashlib,json,os,uuid,re,unicodedata
from pathlib import Path,PurePosixPath
RECEIPTS=Path(__file__).with_name('llm-copy-receipts')
NEO_FOLDERS={'AN NGUYEN','INJAE','A CHAU'}
def _norm_group(group):
 s=unicodedata.normalize('NFD',str(group or '').replace('đ','d').replace('Đ','D'))
 s=''.join(c for c in s if not unicodedata.combining(c))
 return re.sub(r'\s+',' ',s.upper()).strip()
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def destination(folder,name,sha):
 base=Path(name);pattern=re.compile(re.escape(base.stem)+r'([2-9][0-9]*|1[0-9]+)?'+re.escape(base.suffix),re.I)
 versions=[]
 for path in folder.iterdir():
  match=pattern.fullmatch(path.name)
  if match and path.is_file():versions.append((int(match.group(1) or 1),path))
 for number,path in sorted(versions):
  if digest(path)==sha:return path
 number=max([v[0] for v in versions],default=0)+1
 return folder/(base.stem+('' if number==1 else str(number))+base.suffix)

def copy_files(root,files):
 root=Path(root).resolve();pairs=[];paths=[]
 for f in files:
  rel=PurePosixPath(f['source']);group=f['group'];name=f['name']
  if any(c in group for c in '/\\:') or group in ('','.','..'):raise ValueError('Invalid customer')
  if rel.is_absolute() or '..' in rel.parts or '\\' in str(rel) or ':' in str(rel) or len(rel.parts)<3 or rel.parts[:2]!=(group,'DESIGNER'):raise ValueError('Invalid source')
  target=PurePosixPath(name)
  if Path(name).name!=name or any(c in name for c in '/\\:') or '..' in name or not 1<=len(name)<=120 or any(ord(c)<32 for c in name):raise ValueError('Invalid target')
  if rel.suffix.lower() not in ('.jpg','.jpeg','.tif','.tiff') or target.suffix.lower()!=rel.suffix.lower() or not target.stem.endswith('_LLM'):raise ValueError('Invalid target')
  if rel.suffix.lower() in ('.jpg','.jpeg') and _norm_group(group) in NEO_FOLDERS and not name.startswith('NEO_'):raise ValueError('Invalid NEO target')
  src=(root/str(rel)).resolve();folder=(root/group).resolve()
  if root not in src.parents or root not in folder.parents:raise ValueError('Outside archive')
  if digest(src)!=f['sha256']:raise ValueError('Bản DESIGNER đã thay đổi')
  pairs.append((src,folder,f))
 for src,folder,f in pairs:
  dest=destination(folder,f['name'],f['sha256'])
  if not dest.exists():
   tmp=folder/('.llm-'+uuid.uuid4().hex+'.pending')
   try:
    with src.open('rb') as a,tmp.open('xb') as b:
     while chunk:=a.read(1024*1024):b.write(chunk)
     b.flush();os.fsync(b.fileno())
    if digest(tmp)!=f['sha256']:raise ValueError('Copy hash mismatch')
    if os.name!='nt':raise ValueError('Requires Windows atomic no-replace rename')
    while True:
     try:os.rename(tmp,dest);break
     except FileExistsError:
      dest=destination(folder,f['name'],f['sha256'])
      if dest.exists():break
   finally:tmp.unlink(missing_ok=True)
  if digest(dest)!=f['sha256']:raise ValueError('Destination changed')
  paths.append(f['group']+'/'+dest.name)
 return paths
def sync(client,cfg):
 prefix='/adapters/'+cfg['account']+'/llm-copies';r=client.get(prefix);r.raise_for_status();job=r.json().get('job')
 if not job:return 'llm_copy_idle'
 signature=hashlib.sha256(json.dumps([cfg['account'],job['id'],job['files']],sort_keys=True).encode()).hexdigest()
 RECEIPTS.mkdir(exist_ok=True);receipt=RECEIPTS/(signature+'.json')
 if receipt.exists():result=json.loads(receipt.read_text(encoding='utf-8'))
 else:
  try:result={'paths':copy_files(cfg['archive']['root'],job['files'])}
  except (ValueError,OSError) as exc:result={'error':str(exc)[:900]}
  tmp=receipt.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');tmp.replace(receipt)
 r=client.post(prefix+'/'+job['id'],json=result);r.raise_for_status();return 'llm_copy_'+r.json()['state']
