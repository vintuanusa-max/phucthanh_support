"""Read-only CDR/PSD normalization; durable markers prohibit uncertain retries."""
import hashlib,json,subprocess,shutil
from pathlib import Path

PSD = r'''var c=__C__,d=null,old=app.displayDialogs;app.displayDialogs=DialogModes.NO;
try {
 d=app.open(new File(c.source));
 var groups=[],i;
 for(i=0;i<d.layers.length;i++) if(d.layers[i].visible) {
  if(d.layers[i].typename=='LayerSet') groups.push(i);
  else if(d.layers.length==1 && !d.layers[i].isBackgroundLayer) groups.push(i);
  else if(!d.layers[i].isBackgroundLayer) throw Error('PSD_VISIBLE_UNGROUPED_LAYERS: cần nhóm đủ artwork và chi tiết trắng');
 }
 if(!groups.length||groups.length>8) throw Error('PSD cần một layer artwork hoặc 1-8 group artwork hiển thị');
 var report=[],dpi=d.resolution;
 for(var n=0;n<groups.length;n++) {
  var x=d.duplicate();
  try {
   for(i=0;i<x.layers.length;i++) x.layers[i].visible=(i==groups[n]);
   if(x.mode!=DocumentMode.RGB)x.changeMode(ChangeMode.RGB);
   x.bitsPerChannel=BitsPerChannelType.EIGHT;
   var o=new PNGSaveOptions();x.saveAs(new File(c.folder+'/group_'+n+'.png'),o,true,Extension.LOWERCASE);
   report.push([n,encodeURIComponent(d.layers[groups[n]].name),d.width.as('px'),d.height.as('px'),dpi].join('\t'));
  } finally {x.close(SaveOptions.DONOTSAVECHANGES);}
 }
 var f=new File(c.folder+'/groups.tsv');f.open('w');f.write(report.join('\n'));f.close();
} finally {if(d)d.close(SaveOptions.DONOTSAVECHANGES);app.displayDialogs=old;}'''

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def normalize(root,asset,folder):
    root=Path(root).resolve();src=(root/asset['relative_path']).resolve()
    if root not in src.parents or src.stat().st_size>1024**3 or digest(src)!=asset['sha256']:raise ValueError('Normalization source mismatch')
    suffix=src.suffix.lower()
    if suffix not in ('.cdr','.psd'):raise ValueError('Unsupported normalization input')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    result=folder/'normalized.json';marker=folder/'started'
    if result.exists():
        a=json.loads(result.read_text());target=(root/a['relative_path']).resolve()
        if root not in target.parents or digest(target)!=a['sha256']:raise ValueError('Normalized PDF changed')
        return a
    if marker.exists():raise ValueError('Normalization interrupted; inspect before retry')
    marker.write_text(asset['sha256']);copy=folder/('source'+suffix);shutil.copyfile(src,copy)
    pdf=folder/'normalized.pdf'
    if suffix=='.cdr':
        (folder/'paths.json').write_text(json.dumps({'source':str(copy),'output':str(pdf)}))
        command="$ErrorActionPreference='Stop'; $p=Get-Content -Raw paths.json|ConvertFrom-Json; $a=New-Object -ComObject CorelDRAW.Application.19; $d=$a.OpenDocument($p.source); try {$d.PublishToPDF($p.output)} finally {$d.Close()}"
    else:
        from adobe_ready import ready_command
        (folder/'convert.jsx').write_text(PSD.replace('__C__',json.dumps({'source':str(copy),'folder':str(folder)})),encoding='utf-8')
        command=ready_command('Photoshop.Application','$app')+"$app.DoJavaScript([IO.File]::ReadAllText((Join-Path (Get-Location) 'convert.jsx')))"
    run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=120 if suffix=='.cdr' else 600,creationflags=0x08000000)
    if run.returncode:
        (folder/'error.txt').write_bytes(run.stderr)
        raise ValueError('Native conversion failed; inspect '+str(folder/'error.txt'))
    import pymupdf as fitz
    if suffix=='.psd':
        from PIL import Image
        doc=fitz.open()
        for line in (folder/'groups.tsv').read_text().splitlines():
            n,name,w,h,dpi=line.split('\t');w,h,dpi=map(float,(w,h,dpi));png=folder/('group_'+n+'.png')
            if dpi<=0 or w*h>350_000_000:raise ValueError('Invalid PSD size')
            with Image.open(png) as im:
                if im.mode!='RGBA' or not im.getchannel('A').getbbox() or im.getchannel('A').getextrema()[0]==255:
                    raise ValueError('PSD group has no transparent exterior; inspect background')
            page=doc.new_page(width=w/dpi*72,height=h/dpi*72);page.insert_image(page.rect,filename=str(png))
        doc.save(pdf);doc.close()
    with fitz.open(pdf) as d:
        if not 1<=len(d)<=8 or d.needs_pass:raise ValueError('Invalid normalized PDF')
    group=asset['relative_path'].replace('\\','/').split('/')[0]
    rel=group+'/DESIGNER/_source_adapters/'+asset['sha256']+'/normalized.pdf'
    dest=(root/rel).resolve()
    if root not in dest.parents:raise ValueError('Unsafe normalized destination')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and digest(dest)!=digest(pdf):raise ValueError('Normalized destination collision')
    if not dest.exists():
        with dest.open('xb') as f:f.write(pdf.read_bytes())
    a=dict(asset,name=Path(asset['name']).stem+'.pdf',relative_path=rel,sha256=digest(dest),state='ready',kind='file')
    a['normalization']={'source_sha256':asset['sha256'],'source_name':asset['name'],'format':suffix,'version':1}
    result.write_text(json.dumps(a));return a
