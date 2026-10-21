"""Windows PET review adapter. No legacy workflow import, printer or watch folder."""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import quote
from PIL import Image


JSX = r'''(function(){
var cfg=__CONFIG__, oldDialogs=app.displayDialogs, previous=app.documents.length?app.activeDocument:null;
var reports=[];
try {
 app.displayDialogs=DialogModes.NO;
 for(var n=0;n<cfg.length;n++){
  var x=cfg[n], d=null, target=new File(x.tiff);
  if(target.exists || (new File(x.tiff.replace(/\.tiff$/,'.tif'))).exists)throw new Error('Existing TIFF: reconcile first');
  try{
   d=app.open(new File(x.png));var w=d.width.as('px'),h=d.height.as('px');
   if(Math.abs(d.resolution-300)>0.1)throw new Error('PNG DPI');
   app.doAction('WHITE_1','IN_PHUC_THANH_ACTIONS');
   if(d.width.as('px')!==w || d.height.as('px')!==h)throw new Error('Action changed geometry');
   var opt=new TiffSaveOptions();opt.transparency=true;opt.alphaChannels=true;opt.spotColors=true;opt.layers=false;opt.imageCompression=TIFFEncoding.TIFFLZW;
   d.saveAs(target,opt,true,Extension.LOWERCASE);d.close(SaveOptions.DONOTSAVECHANGES);d=null;
   if(!target.exists){var actual=new File(x.tiff.replace(/\.tiff$/,'.tif'));if(actual.exists)actual.rename(target.name);}
   if(!target.exists)throw new Error('Missing TIFF');
   d=app.open(target);var found=false,nonempty=false;
   for(var c=0;c<d.channels.length;c++){
    if(d.channels[c].name==='spot_1' && d.channels[c].kind===ChannelType.SPOTCOLOR){
     found=true;var hist=d.channels[c].histogram;for(var j=0;j<255;j++){if(hist[j]>0){nonempty=true;break;}}
    }
   }
   if(!found || !nonempty || d.width.as('px')!==w || d.height.as('px')!==h || Math.abs(d.resolution-300)>0.1)throw new Error('Saved TIFF failed spot/size verification');
   reports.push('verified');
  }finally{if(d)d.close(SaveOptions.DONOTSAVECHANGES);}
 }
}finally{app.displayDialogs=oldDialogs;if(previous){try{app.activeDocument=previous;}catch(e){}}}
return reports.join(',');
})()'''


def verify_tiff(png, tiff, info):
    with Image.open(png) as src, Image.open(tiff) as im:
        if im.format != 'TIFF' or im.tag_v2.get(277) != 5 or tuple(im.tag_v2.get(338, ())) not in ((1,0),(2,0)):
            raise ValueError('TIFF thiếu alpha hoặc kênh trắng')
        if list(im.size) != info['pixels'] or im.size != src.size or any(abs(x-300)>.1 for x in im.info.get('dpi',(0,0))):
            raise ValueError('TIFF sai kích thước/DPI')
        if src.getchannel('A').tobytes() != im.getchannel('A').tobytes():
            raise ValueError('Alpha TIFF khác PNG, không gửi bản này')
    return {'name':tiff.name,'spot':'spot_1','spot_nonempty':True,'alpha_preserved':True,'sha256':hashlib.sha256(tiff.read_bytes()).hexdigest()}


def export_photoshop(folder, files):
    configs=[]
    for info in files:
        png=folder/info['name'];tiff=png.with_suffix('.tiff')
        configs.append({'png':str(png).replace('\\','/'),'tiff':str(tiff).replace('\\','/')})
    script=folder/'white.jsx';script.write_text(JSX.replace('__CONFIG__',json.dumps(configs,ensure_ascii=True)),encoding='utf-8')
    # No shell interpolation of file names. PowerShell reads a fixed JSX file in cwd.
    command="$ErrorActionPreference='Stop'; $app=New-Object -ComObject Photoshop.Application; $jsx=[IO.File]::ReadAllText((Join-Path (Get-Location) 'white.jsx')); $app.DoJavaScript($jsx)"
    run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=240)
    if run.returncode or run.stdout.decode(errors='replace').strip() != ','.join(['verified']*len(files)):
        raise ValueError('Photoshop chưa xác minh xong TIFF; không tự chạy lại action')
    return [verify_tiff(folder/f['name'],(folder/f['name']).with_suffix('.tiff'),f) for f in files]


def sync_pet(client, cfg, local_root):
    prefix='/adapters/'+quote(cfg['account'],safe='')+'/pet-exports'
    response=client.get(prefix);response.raise_for_status();job=response.json().get('job')
    if not job:return 'pet_idle'
    identity=job['id']
    if len(identity)!=64 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('Invalid job id')
    folder=Path(local_root)/identity;folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'started.json';done=folder/'verified.json'
    try:
        if done.exists():
            reports=json.loads(done.read_text(encoding='utf-8'))
        elif marker.exists():
            raise ValueError('Lần xuất trước bị gián đoạn; cần kiểm tra file có sẵn, không tự chạy lại')
        else:
            for info in job['files']:
                name=info['name']
                if Path(name).name!=name or not name.endswith('.png') or ':' in name or '\\' in name:
                    raise ValueError('Invalid filename')
                r=client.get(prefix+'/'+identity+'/'+quote(name,safe=''));r.raise_for_status()
                if hashlib.sha256(r.content).hexdigest()!=info['sha256']:raise ValueError('PNG hash mismatch')
                (folder/name).write_bytes(r.content)
            marker.write_text(json.dumps({'id':identity,'files':job['files']}),encoding='utf-8')
            reports=export_photoshop(folder,job['files'])
            done.write_text(json.dumps(reports),encoding='utf-8')
        archive_root=Path(cfg['archive']['root']).resolve()
        group=job['archive_folder']
        if not group or group in ('.','..') or any(c in group for c in '/\\:'):raise ValueError('Invalid archive group')
        archive=(archive_root/group/'DESIGN_BRIEFS'/'PET_AUTO'/identity).resolve()
        if archive_root not in archive.parents:raise ValueError('Archive outside root')
        archive.mkdir(parents=True,exist_ok=True)
        for info,report in zip(job['files'],reports):
            png=folder/info['name'];tiff=png.with_suffix('.tiff')
            if hashlib.sha256(png.read_bytes()).hexdigest()!=info['sha256']:
                raise ValueError('PNG đã đổi sau khi duyệt bản tách')
            checked=verify_tiff(png,tiff,info)
            if checked!=report:raise ValueError('Verified artifact changed')
            for source in (png,tiff):
                dest=archive/source.name
                raw=source.read_bytes()
                if dest.exists() and dest.read_bytes()!=raw:raise ValueError('Archive collision')
                if not dest.exists():
                    with dest.open('xb') as f:f.write(raw)
            r=client.put(prefix+'/'+identity+'/'+quote(tiff.name,safe=''),content=tiff.read_bytes(),timeout=120);r.raise_for_status()
        manifest={'id':identity,'plan':job['plan'],'source':job['source'],'reports':reports,'private':True,'auto_rip':False}
        (archive/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        r=client.post(prefix+'/'+identity,json={'reports':reports},timeout=180);r.raise_for_status()
        return 'pet_'+r.json()['state']
    except (ValueError, subprocess.TimeoutExpired) as exc:
        reason=str(exc) if isinstance(exc,ValueError) else 'Photoshop quá thời gian; cần kiểm tra, không tự chạy lại'
        r=client.post(prefix+'/'+identity,json={'error':reason});r.raise_for_status()
        return 'pet_review'
