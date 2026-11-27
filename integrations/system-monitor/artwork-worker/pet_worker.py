from fleet_paths import archive as fleet_archive, local as fleet_local, inherit_editable, ascii_model
"""Windows PET review adapter. No legacy workflow import, printer or watch folder."""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageChops, ImageFilter, ImageOps


LEGACY_SPOT_POLICY = 'white-preserve-color-contract1-v1'
from white_ink_auto import POLICY as SPOT_POLICY, rgb_coverage

def spot_coverage(image, policy=SPOT_POLICY):
    """300dpi: adaptive color choke; preserve white and thin features.

    RGB >=250 in all channels is white (small raster rounding tolerance).
    Erode total alpha, then restore white coverage so adjoining white/color
    regions do not acquire an artificial unprinted seam.
    Transparent canvas edges are padded before erosion.
    """
    if policy == SPOT_POLICY:
        return rgb_coverage(image)
    if policy == 'auto-rgb-luma-cmyk-total-white100-black40-v3':
        return rgb_coverage(image, adaptive=False)
    if policy != LEGACY_SPOT_POLICY:
        raise ValueError('Unknown spot policy: '+str(policy))
    rgba=image.convert('RGBA');r,g,b,alpha=rgba.split()
    white=ImageChops.darker(ImageChops.darker(r,g),b).point(lambda v:255 if v>=250 else 0)
    white=ImageChops.multiply(white,alpha)
    padded=ImageOps.expand(alpha,border=1,fill=0)
    contracted=padded.filter(ImageFilter.MinFilter(3)).crop((1,1,alpha.width+1,alpha.height+1))
    return ImageChops.lighter(white,contracted)


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
   // Replace the action's uniform choke with the per-pixel white/color mask.
   var maskDoc=app.open(new File(x.mask));
   var replacement=maskDoc.channels[0].duplicate(d);
   maskDoc.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=d;
   for(var z=d.channels.length-1;z>=0;z--){if(d.channels[z].name==='spot_1')d.channels[z].remove();}
   replacement.name='spot_1';replacement.kind=ChannelType.SPOTCOLOR;
   var white=new SolidColor();white.rgb.red=255;white.rgb.green=255;white.rgb.blue=255;
   replacement.color=white;replacement.opacity=100;
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
        opaque=src.getchannel('A').getextrema()==(255,255)
        normal=im.tag_v2.get(277)==5 and tuple(im.tag_v2.get(338,())) in ((1,0),(2,0))
        solid=opaque and im.tag_v2.get(277)==4 and tuple(im.tag_v2.get(338,()))==(0,)
        if im.format != 'TIFF' or not (normal or solid):
            raise ValueError('TIFF thiếu alpha hoặc kênh trắng')
        if list(im.size) != info['pixels'] or im.size != src.size or any(abs(x-300)>.1 for x in im.info.get('dpi',(0,0))):
            raise ValueError('TIFF sai kích thước/DPI')
        if normal and src.getchannel('A').tobytes() != im.getchannel('A').tobytes():
            raise ValueError('Alpha TIFF khác PNG, không gửi bản này')
    return {'name':tiff.name,'spot':'spot_1','spot_nonempty':True,'alpha_preserved':True,'sha256':hashlib.sha256(tiff.read_bytes()).hexdigest()}


def export_photoshop(folder, files):
    configs=[]
    for info in files:
        png=folder/info['name'];tiff=png.with_suffix('.tiff')
        mask=folder/(png.name+'.spot-mask.png')
        with Image.open(png) as source:
            coverage=spot_coverage(source)
            if coverage.getbbox() is None:
                raise ValueError('Spot rỗng sau contract1px; cần duyệt chi tiết quá nhỏ')
            ImageOps.invert(coverage).save(mask,dpi=(300,300))
        configs.append({'png':str(png).replace('\\','/'),'tiff':str(tiff).replace('\\','/'),'mask':str(mask).replace('\\','/')})
    script=folder/'white.jsx';script.write_text(JSX.replace('__CONFIG__',json.dumps(configs,ensure_ascii=True)),encoding='utf-8')
    # No shell interpolation of file names. PowerShell reads a fixed JSX file in cwd.
    command=__import__("adobe_ready").ready_command("Photoshop.Application","$app")+"$jsx=[IO.File]::ReadAllText((Join-Path (Get-Location) 'white.jsx')); $app.DoJavaScript($jsx)"
    run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=360)
    (folder/'photoshop-process.json').write_text(json.dumps({'returncode':run.returncode,'stdout':run.stdout.decode(errors='replace')[-4000:],'stderr':run.stderr.decode(errors='replace')[-4000:]},ensure_ascii=False),encoding='utf-8')
    if run.returncode or run.stdout.decode(errors='replace').strip() != ','.join(['verified']*len(files)):
        raise ValueError('Photoshop chưa xác minh xong TIFF; không tự chạy lại action')
    for info in files:
        verify_spot_coverage(folder/info['name'],(folder/info['name']).with_suffix('.tiff'))
    (folder/'spot-policy.json').write_text(json.dumps({'policy':SPOT_POLICY,'white_contract_px':0,'color_contract_px':'adaptive 0..1','thin_features':'preserve 1-2px','transition_blur_px':1.5,'white_rgb_min':250,'color_mode':'RGB','density_basis':'RGB luma','white_percent':100,'black_percent':40,'solidity':100,'pixel_verified':True}),encoding='utf-8')
    return [verify_tiff(folder/f['name'],(folder/f['name']).with_suffix('.tiff'),f) for f in files]


def verify_spot_coverage(png,tiff,policy=SPOT_POLICY):
    import sys
    dependencies=Path(__file__).parent/'spot-deps'
    if dependencies.is_dir() and str(dependencies) not in sys.path:
        sys.path.insert(0,str(dependencies))
    import tifffile
    import numpy as np
    with Image.open(png) as source:
        expected=np.asarray(spot_coverage(source,policy))
        opaque=source.getchannel('A').getextrema()==(255,255)
    with tifffile.TiffFile(tiff) as file:
        raw=file.pages[0].asarray(maxworkers=1)
    channels=4 if opaque and raw.shape==(*expected.shape,4) else 5
    if raw.shape != (*expected.shape,channels) or not np.array_equal(255-raw[:,:,channels-1],expected):
        raise ValueError('Spot không khớp quy tắc trắng0px/màu1px; cần kiểm tra')


def sync_pet(client, cfg, local_root):
    prefix='/adapters/'+quote(cfg['account'],safe='')+'/pet-exports'
    response=client.get(prefix);response.raise_for_status();job=response.json().get('job')
    if not job:return 'pet_idle'
    identity=job['id']
    if len(identity)!=64 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('Invalid job id')
    folder=fleet_local(job,Path(local_root)/identity);folder.mkdir(parents=True,exist_ok=True)
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
        import re
        model=ascii_model(job.get('archive_model') or job['plan']['order_code'])
        if not model or model.upper() in {'CON','PRN','AUX','NUL'}:raise ValueError('Invalid model folder')
        version=str(job.get('source',{}).get('editable_version_id') or identity)
        if not re.fullmatch(r'[0-9a-f]{64}',version):raise ValueError('Invalid editable version')
        archive=fleet_archive(job,archive_root/group/'DESIGNER'/model/'versions'/version).resolve()
        if archive_root not in archive.parents:raise ValueError('Archive outside root')
        archive.mkdir(parents=True,exist_ok=True)
        inherit_editable(job,archive)
        for info,report in zip(job['files'],reports):
            png=folder/info['name'];tiff=png.with_suffix('.tiff')
            if hashlib.sha256(png.read_bytes()).hexdigest()!=info['sha256']:
                raise ValueError('PNG đã đổi sau khi duyệt bản tách')
            if (folder/'spot-policy.json').exists():
                saved_policy=json.loads((folder/'spot-policy.json').read_text(encoding='utf-8')).get('policy',LEGACY_SPOT_POLICY)
                verify_spot_coverage(png,tiff,saved_policy)
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
        if (folder/'spot-policy.json').exists():
            manifest['spot_policy']=json.loads((folder/'spot-policy.json').read_text(encoding='utf-8'))
        (archive/('manifest-'+identity+'.json' if version!=identity else 'manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        r=client.post(prefix+'/'+identity,json={'reports':reports},timeout=180);r.raise_for_status()
        response=r.json()
        from editable_handoff import notify
        notify(client,prefix+'/'+identity,response,folder,archive)
        return 'pet_'+response['state']
    except (ValueError, subprocess.TimeoutExpired) as exc:
        reason=str(exc) if isinstance(exc,ValueError) else 'Photoshop quá thời gian; cần kiểm tra, không tự chạy lại'
        r=client.post(prefix+'/'+identity,json={'error':reason});r.raise_for_status()
        return 'pet_review'



