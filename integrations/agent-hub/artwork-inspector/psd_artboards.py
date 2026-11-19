"""All PSD artboards, using installed Adobe export helpers; originals never saved."""
import base64,json,shutil,subprocess,re
from pathlib import Path
from urllib.parse import unquote
from PIL import Image,ImageDraw
JSX=r'''
var c=__CONFIG__,old=app.displayDialogs,units=app.preferences.rulerUnits,doc=null,part=null;
app.displayDialogs=DialogModes.NO;app.preferences.rulerUnits=Units.PIXELS;
try {
 $.evalFile(new File(app.path+'/Presets/Scripts/ArtboardExport.inc'));
 doc=app.open(new File(c.source));
 var dpi=doc.resolution,boards=getABLayerInfo().all,rows=[];
 var opt=new JPEGSaveOptions();opt.quality=12;opt.embedColorProfile=true;opt.formatOptions=FormatOptions.STANDARDBASELINE;
 function savePart(d,n,title,w,h){
  if(Math.abs(d.width.as('px')-w)>1||Math.abs(d.height.as('px')-h)>1)throw Error('Artboard crop mismatch '+n);
  if(d.mode!=DocumentMode.CMYK)d.changeMode(ChangeMode.CMYK);
  if(d.bitsPerChannel!=BitsPerChannelType.EIGHT)d.bitsPerChannel=BitsPerChannelType.EIGHT;
  var filename='artboard_'+n+'.jpg';d.saveAs(new File(c.folder+'/'+filename),opt,true,Extension.LOWERCASE);
  rows.push([n,encodeURIComponent(title),w,h,dpi,filename].join('\t'));
 }
 if(!boards.length){savePart(doc,1,'Canvas',doc.width.as('px'),doc.height.as('px'));}
 else for(var i=0;i<boards.length;i++){
  app.activeDocument=doc;part=doc.duplicate();app.activeDocument=part;
  setEnabled('autoNestEnabled',false);setEnabled('autoPositionEnabled',false);setEnabled('autoExpandEnabled',false);
  var info={exportArtboardBackground:true,fileType:jpegIndex,preserveArtboard:false};
  cleanUnseenAB(boards[i].AMid,boards,true);
  var changed=getABLayerInfo().all;
  var groups=unArtBoard(changed,part,boards[i].AMid,false,info);
  if(!groups)throw Error('Cannot isolate artboard');
  selectAbByOldID(boards[i].AMid,groups);cropFromMask();
  savePart(part,i+1,boards[i].name,boards[i].right-boards[i].left,boards[i].bottom-boards[i].top);
  part.close(SaveOptions.DONOTSAVECHANGES);part=null;
 }
 var f=new File(c.report);f.encoding='UTF8';f.open('w');f.write(Math.max(1,boards.length)+'\n'+rows.join('\n'));f.close();
} finally {
 if(part)part.close(SaveOptions.DONOTSAVECHANGES);
 if(doc)doc.close(SaveOptions.DONOTSAVECHANGES);
 app.preferences.rulerUnits=units;app.displayDialogs=old;
}
'''
def parse_manifest(path):
 lines=Path(path).read_text(encoding='utf-8-sig').splitlines();count=int(lines[0]);panels=[]
 for line in lines[1:]:
  n,title,w,h,dpi,file=line.split('\t')
  if file!=f'artboard_{int(n)}.jpg':raise ValueError('Invalid artboard filename')
  w,h,dpi=float(w),float(h),float(dpi)
  if min(w,h,dpi)<=0 or w*h>350_000_000:raise ValueError('Artboard exceeds safe raster size')
  panels.append(dict(index=int(n),title=unquote(title),pixels=[round(w),round(h)],source_pixels=[round(w),round(h)],dpi=dpi,source_dpi=dpi,file=file,size_cm=[round(w/dpi*2.54,4),round(h/dpi*2.54,4)]))
 if count!=len(panels) or [x['index'] for x in panels]!=list(range(1,count+1)):raise ValueError('Incomplete PSD artboards')
 return panels

def run(job,cfg,folder):
 from psd_worker import safe,sha,metadata
 from adobe_ready import ready_command
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);done=folder/'verified.json';marker=folder/'started.json'
 if done.exists():
  result=json.loads(done.read_text(encoding='utf-8'))
  for p in result['report']['panels']:
   if sha(p['path'])!=p['sha256']:raise ValueError('Output changed; no re-export')
  return result
 a=job['asset'];source=safe(cfg['archive']['root'],a['relative_path'])
 if source.suffix.lower()!='.psd' or source.stat().st_size>1024**3 or sha(source)!=a['sha256']:raise ValueError('PSD source mismatch')
 metadata(source)
 customer=a['relative_path'].replace('\\','/').split('/')[0]
 name=re.sub(r'[^A-Za-z0-9_-]+','_',Path(a['name']).stem).strip('_') or 'PSD'
 dest=safe(cfg['archive']['root'],customer+'/DESIGNER/'+name+'/sample_'+job['id'][:12]);dest.mkdir(parents=True,exist_ok=True)
 manifest=folder/'artboards.tsv'
 if not marker.exists():
  shutil.copyfile(source,folder/'source.psd');marker.write_text(json.dumps({'source':a['sha256'],'all_artboards':True}),encoding='utf-8')
  config=dict(source=str(folder/'source.psd'),folder=str(folder),report=str(manifest))
  (folder/'export.jsx').write_text(JSX.replace('__CONFIG__',json.dumps(config)),encoding='utf-8')
  cmd=ready_command('Photoshop.Application','$app')+"$jsx=[IO.File]::ReadAllText((Join-Path (Get-Location) 'export.jsx')); $app.DoJavaScript($jsx)"
  proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',cmd],cwd=folder,capture_output=True,timeout=600,creationflags=0x08000000)
  (folder/'photoshop.stderr.txt').write_bytes(proc.stderr)
 elif json.loads(marker.read_text()).get('source')!=a['sha256']:raise ValueError('Source changed')
 if not manifest.exists():raise ValueError('PSD artboard export incomplete; inspect before retry')
 panels=parse_manifest(manifest);thumbs=[]
 for p in panels:
  output=folder/p['file']
  with Image.open(output) as im:
   if im.mode!='CMYK' or list(im.size)!=p['source_pixels'] or any(abs(v-p['dpi'])>1 for v in im.info.get('dpi',(0,0))):raise ValueError('PSD artboard pixel/color/DPI mismatch')
   preview=im.convert('RGB');preview.thumbnail((580,580));thumbs.append(preview)
  p.update(mode='CMYK',path=str(dest/p['file']),sha256=sha(output))
 for src,target in [(source,dest/(name+'.psd'))]+[(folder/p['file'],Path(p['path'])) for p in panels]:
  if target.exists() and sha(target)!=sha(src):raise ValueError('Output conflict; no overwrite')
  if not target.exists():shutil.copyfile(src,target)
  if sha(target)!=sha(src):raise ValueError('NAS copy mismatch')
 # Bounded overview; individual JPGs remain full resolution on NAS.
 cell=max(80,min(600,2400//max(1,(len(thumbs)+1)//2)))
 sheet=Image.new('RGB',(2*cell,((len(thumbs)+1)//2)*cell),'white');draw=ImageDraw.Draw(sheet)
 for i,im in enumerate(thumbs):
  im.thumbnail((cell-8,cell-24));x=(i%2)*cell;y=(i//2)*cell;sheet.paste(im,(x,y+22));draw.text((x+4,y+4),'Artboard '+str(i+1),fill='black')
 preview_path=folder/'preview.png';sheet.save(preview_path)
 report=dict(panels[0],source_sha256=a['sha256'],panels=panels,artboard_count=len(panels),all_artboards=True)
 result=dict(report=report,preview=dict(mime_type='image/png',data=base64.b64encode(preview_path.read_bytes()).decode()))
 done.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');return result
