import base64,json,subprocess,re,hashlib
from pathlib import Path
from urllib.parse import quote
from native_local import inspect,export,export_combined_ai

def sync_native(client,cfg):
 from worker import read_asset
 prefix='/adapters/'+quote(cfg['account'],safe='')+'/native-selections'
 r=client.get(prefix);r.raise_for_status();job=r.json().get('job')
 if not job:return 'native_idle'
 try:
  raw=base64.b64decode(read_asset(cfg['archive']['root'],job['asset']))
  folder=Path(__file__).parent/'native-output'/job['id']
  if job['state']=='scan_running':data={'scan':inspect(raw,job['asset']['name'],folder,allow_pdf_reimport=True)}
  else:
   efaces=job.get('editable_faces') or []
   evid=str(job.get('editable_version_id') or '')
   multi_editable=len(efaces)>1 and bool(re.fullmatch(r'[0-9a-f]{64}',evid))
   result=export(raw,job['asset']['name'],folder,job['candidates'],job['candidate_ids'],job['width_cm'],'artwork',save_ai=not multi_editable)
   root=Path(cfg['archive']['root']).resolve();group=job['asset']['relative_path'].replace('\\','/').split('/')[0]
   model=re.sub(r'[^\w-]','',job['asset']['name'].rsplit('.',1)[0])
   if multi_editable:
    dest=(root/group/'DESIGNER'/model/'versions'/evid/(model+'_EDITABLE.ai')).resolve()
    if root not in dest.parents:raise ValueError('Editable archive outside root')
    if not dest.exists():
     ai_path=export_combined_ai(raw,job['asset']['name'],folder,efaces,'combined')
     dest.parent.mkdir(parents=True,exist_ok=True)
     try:
      with dest.open('xb') as target:target.write(Path(ai_path).read_bytes())
     except FileExistsError:
      pass
   elif result.get('ai'):
    side=job.get('side','front')
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
  if 'folder' in locals() and folder.is_dir():(folder/'native-worker-error.txt').write_text(__import__('traceback').format_exc(),encoding='utf-8')
  data={'error':str(exc)[:1000] if isinstance(exc,ValueError) else 'Illustrator chưa hoàn tất: '+type(exc).__name__+': '+str(exc)[:400]+'; cần kiểm tra, không tự chạy lại'}
 r=client.post(prefix+'/'+job['id'],json=data,timeout=120);r.raise_for_status()
 return 'native_'+r.json()['state']
