import base64,json,subprocess,re,hashlib
from pathlib import Path
from urllib.parse import quote
from native_local import inspect,export

def sync_native(client,cfg):
 from worker import read_asset
 prefix='/adapters/'+quote(cfg['account'],safe='')+'/native-selections'
 r=client.get(prefix);r.raise_for_status();job=r.json().get('job')
 if not job:return 'native_idle'
 try:
  raw=base64.b64decode(read_asset(cfg['archive']['root'],job['asset']))
  folder=Path(__file__).parent/'native-output'/job['id']
  if job['state']=='scan_running':data={'scan':inspect(raw,job['asset']['name'],folder)}
  else:
   result=export(raw,job['asset']['name'],folder,job['candidates'],job['candidate_ids'],job['width_cm'],'artwork')
   if result.get('ai'):
    root=Path(cfg['archive']['root']).resolve();group=job['asset']['relative_path'].replace('\\','/').split('/')[0]
    model=re.sub(r'[^\w-]','',job['asset']['name'].rsplit('.',1)[0]);side=job.get('side','front')
    if not re.fullmatch(r'[a-z0-9_]+',side):raise ValueError('Invalid side')
    dest=(root/group/'DESIGNER'/model/'versions'/job['id']/(model+'_'+side+'_editable.ai')).resolve()
    if root not in dest.parents:raise ValueError('Editable archive outside root')
    dest.parent.mkdir(parents=True,exist_ok=True);ai=Path(result['ai']).read_bytes()
    if dest.exists():
     if dest.read_bytes()!=ai:raise ValueError('Editable archive collision')
    else:
     with dest.open('xb') as target:target.write(ai)
   data={'png':base64.b64encode(Path(result['png']).read_bytes()).decode()}
 except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
  data={'error':str(exc)[:1000] if isinstance(exc,ValueError) else 'Illustrator chưa hoàn tất: '+type(exc).__name__+'; cần kiểm tra, không tự chạy lại'}
 r=client.post(prefix+'/'+job['id'],json=data,timeout=120);r.raise_for_status()
 return 'native_'+r.json()['state']
