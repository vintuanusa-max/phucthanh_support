"""Photoshop sample export: original canvas/resolution, private preview only."""
import base64,hashlib,json,re,shutil,subprocess,unicodedata,struct
from pathlib import Path
from PIL import Image

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def safe(root,rel):
 root=Path(root).resolve();p=(root/rel).resolve()
 if root not in p.parents or Path(rel).is_absolute():raise ValueError('Unsafe archive path')
 return p

JSX=r"""
var c=__CONFIG__, old=app.displayDialogs,doc=null;
app.displayDialogs=DialogModes.NO;
try {
 doc=app.open(new File(c.source));
 var w=doc.width.as('px'),h=doc.height.as('px'),dpi=doc.resolution;
 if(w<1||h<1||dpi<=0)throw Error('Invalid canvas');
 if(doc.mode!=DocumentMode.CMYK)doc.changeMode(ChangeMode.CMYK);
 if(doc.bitsPerChannel!=BitsPerChannelType.EIGHT)doc.bitsPerChannel=BitsPerChannelType.EIGHT;
 var opt=new JPEGSaveOptions();opt.quality=12;opt.embedColorProfile=true;opt.formatOptions=FormatOptions.STANDARDBASELINE;
 doc.saveAs(new File(c.output),opt,true,Extension.LOWERCASE);
 var report=new File(c.report);report.open('w');report.write(w+'\n'+h+'\n'+dpi);report.close();
} finally {if(doc)doc.close(SaveOptions.DONOTSAVECHANGES);app.displayDialogs=old;}
"""

def metadata(path):
 with Path(path).open('rb') as f:
  sig,version,_,channels,h,w,bits,mode=struct.unpack('>4sH6sHIIHH',f.read(26))
  if sig!=b'8BPS' or version!=1:raise ValueError('Unsupported PSD header')
  n=struct.unpack('>I',f.read(4))[0];f.seek(n,1);n=struct.unpack('>I',f.read(4))[0];end=f.tell()+n;dpi=None
  while f.tell()<end:
   f.read(4);rid=struct.unpack('>H',f.read(2))[0];k=f.read(1)[0];f.read(k);f.read((k+1)%2);size=struct.unpack('>I',f.read(4))[0];data=f.read(size);f.read(size%2)
   if rid==1005:
    x,_,_,y,_,_=struct.unpack('>IHHIHH',data)
    if x!=y:raise ValueError('Non-square source resolution')
    dpi=x/65536
  if not dpi:raise ValueError('PSD has no explicit resolution')
 return w,h,dpi

def run_job(job,cfg,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 done=folder/'verified.json';marker=folder/'started.json'
 if done.exists():
  result=json.loads(done.read_text());r=result['report']
  if sha(r['path'])!=r['sha256']:raise ValueError('Output changed; inspect before retry')
  return result

 a=job['asset'];source=safe(cfg['archive']['root'],a['relative_path'])
 if source.suffix.lower()!='.psd' or source.stat().st_size>1024*1024*1024 or sha(source)!=a['sha256']:raise ValueError('PSD source mismatch/over 1 GiB')
 name=unicodedata.normalize('NFKD',Path(a['name']).stem).encode('ascii','ignore').decode();name=re.sub(r'[^A-Za-z0-9_-]+','_',name).strip('_') or 'PSD_SAMPLE'
 customer=a['relative_path'].replace('\\','/').split('/')[0]
 if not customer or customer in ('.','..','DESIGNER') or ':' in customer:raise ValueError('Missing customer archive folder')
 dest=safe(cfg['archive']['root'],customer+'/DESIGNER/'+name+'/sample_'+job['id'][:12]);dest.mkdir(parents=True,exist_ok=True)
 source_copy=folder/'source.psd';output=folder/(name+'.jpg')
 w,h,dpi=metadata(source)
 if not marker.exists():
  shutil.copyfile(source,source_copy)
  marker.write_text(json.dumps({'source':a['sha256']}))
  conf={'source':str(source_copy),'output':str(output),'report':str(folder/'photoshop-report.txt')}
  script=folder/'export.jsx';script.write_text(JSX.replace('__CONFIG__',json.dumps(conf)),encoding='utf-8')
  from adobe_ready import ready_command
  cmd=ready_command('Photoshop.Application','$app')+"$jsx=[IO.File]::ReadAllText((Join-Path (Get-Location) 'export.jsx')); $app.DoJavaScript($jsx)"
  proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',cmd],cwd=folder,capture_output=True,timeout=600,creationflags=0x08000000)
  (folder/'photoshop.stderr.txt').write_bytes(proc.stderr)
 else:
  if json.loads(marker.read_text()).get('source')!=a['sha256']:raise ValueError('Previous export source mismatch')
 if not output.exists():raise ValueError('PSD export interrupted; inspect before retry, no automatic re-export')
 with Image.open(output) as im:
  if im.mode!='CMYK' or im.size!=(int(w),int(h)):raise ValueError('CMYK/pixel mismatch')
  if abs(im.info.get('dpi',(dpi,dpi))[0]-dpi)>1:raise ValueError('DPI mismatch')
  preview=im.convert('RGB');preview.thumbnail((1200,1200));preview.save(folder/'preview.png')
 for src,target in [(output,dest/output.name),(source,dest/(name+'.psd')),(folder/'preview.png',dest/'preview.png')]:
  if target.exists() and sha(target)!=sha(src):raise ValueError('Output conflict; never overwrite')
  if not target.exists():shutil.copyfile(src,target)
  if sha(target)!=sha(src):raise ValueError('Archive copy mismatch')
 report={'source_sha256':a['sha256'],'mode':'CMYK','source_pixels':[int(w),int(h)],'pixels':[int(w),int(h)],'source_dpi':dpi,'dpi':dpi,'size_cm':[round(w/dpi*2.54,4),round(h/dpi*2.54,4)],'path':str(dest/output.name),'sha256':sha(output),'profile':'embedded ICC verified in JPG' if Image.open(output).info.get('icc_profile') else 'untagged'}
 result={'report':report,'preview':{'mime_type':'image/png','data':base64.b64encode((folder/'preview.png').read_bytes()).decode()}}
 done.write_text(json.dumps(result));return result

def sync_psd(client,cfg):
 prefix='/adapters/'+cfg['account']+'/psd-samples';r=client.get(prefix)
 if r.status_code==404:return 'psd_unavailable'
 r.raise_for_status();job=r.json().get('job')
 if not job:return 'psd_idle'
 if not re.fullmatch('[a-f0-9]{64}',job['id']):raise ValueError('Invalid job')
 try:result=run_job(job,cfg,Path(__file__).parent/'psd-output'/job['id'])
 except Exception as ex:result={'error':str(ex)[:800] if isinstance(ex,ValueError) else type(ex).__name__}
 r=client.post(prefix+'/'+job['id'],json=result,timeout=90);r.raise_for_status();return 'psd_'+r.json()['state']
