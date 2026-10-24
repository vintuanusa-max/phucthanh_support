"""Native Illustrator duplication plus CMYK-only review rasterization."""
import base64,hashlib,io,json,re,shutil,subprocess
from pathlib import Path
from PIL import Image
import sys
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
import pymupdf as fitz

def vertical_top(height_cm, artwork_height_cm, offset_cm, anchor='top'):
 if anchor not in ('top','bottom'):raise ValueError('Unknown vertical anchor')
 top=offset_cm if anchor=='top' else height_cm-offset_cm-artwork_height_cm
 if offset_cm<0 or top<-.001 or top+artwork_height_cm>height_cm+.001:raise ValueError('Artwork exceeds artboard height')
 return top

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def safe(root,relative):
 root=Path(root).resolve();p=(root/relative).resolve()
 if root not in p.parents or Path(relative).is_absolute():raise ValueError('Path outside archive')
 return p

def source_info(path,panels):
 with fitz.open(path) as d:
  if len(d)!=1 or d[0].rotation:raise ValueError('Nguồn nhiều trang/xoay cần kiểm tra')
  profiles=[]
  for x in range(1,d.xref_length()):
   if d.xref_get_key(x,'N')[1]=='4' and d.xref_is_stream(x):
    raw=d.xref_stream(x)
    if len(raw)>128 and raw[36:40]==b'acsp':profiles.append(raw)
  profiles=list({hashlib.sha256(x).hexdigest():x for x in profiles}.values())
  if len(profiles)!=1:raise ValueError('Thiếu hoặc nhiều ICC CMYK; cần duyệt profile')
  images=d[0].get_image_info(xrefs=True)
  for p in panels:
   for o in p['objects']:
    o['native_bbox']=o['bbox_pt']
    if o['kind']=='image':
     matches=[x for x in images if max(abs(a-b) for a,b in zip(x['bbox'],o['bbox_pt']))<.1]
     if len(matches)!=1 or not matches[0]['xref']:raise ValueError('Không xác định duy nhất ảnh gốc')
     im=matches[0];pix=fitz.Pixmap(d,im['xref'])
     if pix.colorspace.n!=4:raise ValueError('Artwork ảnh không phải CMYK gốc')
     tr=im['transform']
     if abs(tr[1])>.01 or abs(tr[2])>.01 or tr[0]<=0 or tr[3]<=0:raise ValueError('Ảnh nguồn xoay/lật cần duyệt')
     mask=int(d.xref_get_key(im['xref'],'SMask')[1].split()[0]) if d.xref_get_key(im['xref'],'SMask')[0]=='xref' else 0
     crop=(0,0,pix.width,pix.height)
     if mask:
      m=fitz.Pixmap(d,mask);crop=Image.frombytes('L',(m.width,m.height),m.samples).getbbox()
      if not crop:raise ValueError('Artwork rỗng')
     o['crop_fraction']=[crop[0]/pix.width,crop[1]/pix.height,crop[2]/pix.width,crop[3]/pix.height]
  return profiles[0]

JSX=r'''(function(){
var c=__CONFIG__, d=null, previous=app.documents.length?app.activeDocument:null, old=app.userInteractionLevel, cm=72/2.54;
function fail(s){throw Error(s);}
function same(a,b){for(var k=0;k<4;k++)if(Math.abs(a[k]-b[k])>.3)return false;return true;}
try{
 app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;
 d=app.open(new File(c.source));
 if(d.documentColorSpace!==DocumentColorSpace.CMYK)fail('Source document is not CMYK');
 if(d.artboards.length!==1)fail('Multiple source artboards require review');
 var origin=d.artboards[0].artboardRect, original=[];
 for(var z=0;z<d.pageItems.length;z++)original.push(d.pageItems[z]);
 function find(o){
  var b=o.native_bbox, expected=[origin[0]+b[0],origin[1]-b[1],origin[0]+b[2],origin[1]-b[3]], found=[];
  for(var j=0;j<original.length;j++){
   var it=original[j];if((o.kind==='image'&&it.typename!=='RasterItem')||(o.kind==='vector_path'&&it.typename!=='PathItem'))continue;
   if(same(it.geometricBounds,expected))found.push(it);
  }
  if(found.length!==1)fail('Object not uniquely matched: '+o.id);
  var it=found[0],parent=it.parent;
  if(it.hidden||it.opacity!==100||it.blendingMode!==BlendModes.NORMAL)fail('Hidden/transparent artwork');
  while(parent&&parent.typename!=='Document'){
   if(parent.typename==='GroupItem'){
    if(parent.opacity!==100||parent.blendingMode!==BlendModes.NORMAL)fail('Transparency needs review');
    if(parent.clipped){if(o.kind==='image'&&!o.clip_group)o.clip_group=parent;var clips=[];for(var ci=0;ci<parent.pathItems.length;ci++)if(parent.pathItems[ci].clipping)clips.push(parent.pathItems[ci]);
     if(clips.length!==1||clips[0].pathPoints.length!==4)fail('Complex clipping needs review');
     var cb=clips[0].geometricBounds,ib=it.geometricBounds; if(o.kind==='image'&&o.crop_fraction){var cf=o.crop_fraction,iw=ib[2]-ib[0],ih=ib[1]-ib[3];ib=[ib[0]+iw*cf[0],ib[1]-ih*cf[1],ib[0]+iw*cf[2],ib[1]-ih*cf[3]];}
     if(cb[0]>ib[0]+.75||cb[1]<ib[1]-.75||cb[2]<ib[2]-.75||cb[3]>ib[3]+.75)fail('Clipped artwork needs review');
     for(var ci=0;ci<4;ci++){var pt=clips[0].pathPoints[ci],a=pt.anchor;
      if((Math.abs(a[0]-cb[0])>.1&&Math.abs(a[0]-cb[2])>.1)||(Math.abs(a[1]-cb[1])>.1&&Math.abs(a[1]-cb[3])>.1)||a[0]!==pt.leftDirection[0]||a[1]!==pt.leftDirection[1]||a[0]!==pt.rightDirection[0]||a[1]!==pt.rightDirection[1])fail('Non-rectangular clipping');}
    }
   }parent=parent.parent;
  }
  if(it.typename==='PathItem'){
   if(it.clipping)fail('Clipping path');
   if(it.filled&&it.fillColor.typename!=='CMYKColor')fail('Non-process CMYK fill');
   if(it.stroked&&it.strokeColor.typename!=='CMYKColor')fail('Non-process CMYK stroke');
  }
  return it;
 }
 var nextY=-4000, bgSwatches={};
 for(var n=0;n<c.panels.length;n++){
  var p=c.panels[n], w=p.output_cm[0],h=p.output_cm[1],x=0,y=nextY, layer=d.layers.add();layer.name='PRINT_'+p.name;
  if(y-h*cm < -16000)fail('Artboards exceed Illustrator canvas');nextY=y-h*cm-100;
  var ab=d.artboards.add([x,y,x+w*cm,y-h*cm]);ab.name='PRINT_'+p.name;
  var map={};for(var q=0;q<p.objects.length;q++)map[p.objects[q].id]=p.objects[q];
  if(p.background_object_id){var bg=find(map[p.background_object_id]);if(!bg.filled||bg.fillColor.typename!=='CMYKColor')fail('Background not original CMYK');var r=layer.pathItems.rectangle(y,x,w*cm,h*cm);r.filled=true;var bc=bg.fillColor,bkey=[bc.cyan,bc.magenta,bc.yellow,bc.black].join('_');if(!bgSwatches[bkey]){var sp=d.spots.add();sp.name='CANAVI_BG_'+n;sp.colorType=ColorModel.PROCESS;sp.color=bc;bgSwatches[bkey]=sp;}var linked=new SpotColor();linked.spot=bgSwatches[bkey];linked.tint=100;r.fillColor=linked;r.stroked=false;r.name='SOURCE_CMYK_BACKGROUND';}
  for(var j=0;j<p.components.length;j++){
   var a=p.components[j],g=layer.groupItems.add(),crop=null,ids=a.object_ids;
   if(ids.length===1&&map[ids[0]].kind==='image')crop=map[ids[0]].crop_fraction;
   for(var k=0;k<ids.length;k++){var originalItem=find(map[ids[k]]);originalItem.duplicate(g,ElementPlacement.PLACEATEND);}
   if(ids.length===1&&map[ids[0]].clip_group){var cp=map[ids[0]].clip_group;for(var ck=0;ck<cp.pathItems.length;ck++)if(cp.pathItems[ck].clipping){cp.pathItems[ck].duplicate(g,ElementPlacement.PLACEATBEGINNING);g.clipped=true;}}
   if(ids.length>1){for(var k=0;k<ids.length;k++)if(map[ids[k]].kind==='image')fail('Mixed image group needs review');}
   var visibleW=g.width,visibleH=g.height;
   if(crop){visibleW*=crop[2]-crop[0];visibleH*=crop[3]-crop[1];}
   if(visibleW<=0||visibleH<=0)fail('Empty geometry');var scale=a.width_cm*cm/visibleW;
   var anchor=a.vertical_anchor||'top';if(anchor!=='top'&&anchor!=='bottom')fail('Unknown vertical anchor');var top=anchor==='bottom'?h-a.y_cm-visibleH*scale/cm:a.y_cm;
   if(a.y_cm<0||top<-.001||top+visibleH*scale/cm>h+.001)fail('Artwork exceeds artboard height');
   g.resize(scale*100,scale*100);
   if(a.rotation===180){g.rotate(180);if(crop)crop=[1-crop[2],1-crop[3],1-crop[0],1-crop[1]];}
   g.position=[x+a.x_cm*cm-(crop?g.width*crop[0]:0),y-top*cm+(crop?g.height*crop[1]:0)];g.name='ORIGINAL_ARTWORK_'+j;
  }
  if(p.corner_marks){var black=new CMYKColor();black.black=100;black.cyan=black.magenta=black.yellow=0;
   var corners=[[x,y,1,-1],[x+w*cm,y,-1,-1],[x,y-h*cm,1,1],[x+w*cm,y-h*cm,-1,1]];
   for(var k=0;k<4;k++){var v=corners[k],mark=layer.pathItems.add();mark.setEntirePath([[v[0]+v[2]*cm,v[1]],[v[0],v[1]],[v[0],v[1]+v[3]*cm]]);mark.filled=false;mark.stroked=true;mark.strokeColor=black;mark.strokeWidth=.72;mark.name='L_1CM';}
  }
 }
 d.artboards[0].name='SOURCE_REFERENCE_DO_NOT_PRINT';var opts=new IllustratorSaveOptions();opts.pdfCompatible=true;opts.embedICCProfile=true;d.saveAs(new File(c.output),opts);d.close(SaveOptions.DONOTSAVECHANGES);d=null;
 d=app.open(new File(c.output));if(d.artboards.length!==c.panels.length+1||d.documentColorSpace!==DocumentColorSpace.CMYK)fail('Saved AI verification');
 return 'verified';
}finally{if(d)d.close(SaveOptions.DONOTSAVECHANGES);app.userInteractionLevel=old;if(previous){try{previous.activate();}catch(e){}}}
})()'''

def export(job,src,folder):
 if job['plan'].get('renderer')=='original_pdf_v1':
  from original_pdf_export import export as pdf_export
  return pdf_export(job,src,folder)
 if job['plan'].get('renderer')=='native_pattern_v1':
  from pattern_export import export as native_export
  return native_export(job,src,folder)
 panels=job['plan']['panels'];icc=source_info(src,panels)
 target=folder/(job['plan']['order_code'].replace(' ','_')+'_EDITABLE.ai')
 config={'source':str(src).replace('\\','/'),'output':str(target).replace('\\','/'),'panels':panels}
 (folder/'export.jsx').write_text(JSX.replace('__CONFIG__',json.dumps(config,ensure_ascii=True)),encoding='utf-8')
 command="$ErrorActionPreference='Stop'; $ai=New-Object -ComObject Illustrator.Application; $s=[IO.File]::ReadAllText((Join-Path (Get-Location) 'export.jsx')); $ai.DoJavaScript($s)"
 r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=240)
 if r.returncode or r.stdout.decode(errors='replace').strip()!='verified':raise ValueError('Illustrator chưa xác minh được AI; giữ file để kiểm tra, không tự chạy lại')
 reports=[];previews=[]
 with fitz.open(target) as doc:
  if len(doc)!=len(panels)+1:raise ValueError('AI page count mismatch')
  for n,p in enumerate(panels,1):
   page=doc[n];w,h=p['output_cm']
   if abs(page.rect.width*2.54/72-w)>.02 or abs(page.rect.height*2.54/72-h)>.02:raise ValueError('AI artboard size mismatch')
   pix=page.get_pixmap(matrix=fitz.Matrix(300/72,300/72),colorspace=fitz.csCMYK,alpha=False)
   im=Image.frombytes('CMYK',(pix.width,pix.height),pix.samples);dest=folder/(job['plan']['order_code'].replace(' ','_')+'_'+p['name']+'.jpg')
   im.save(dest,quality=100,subsampling=0,dpi=(300,300),icc_profile=icc)
   with Image.open(dest) as check:
    if check.mode!='CMYK' or check.info.get('icc_profile')!=icc:raise ValueError('JPG CMYK/ICC mismatch')
   preview=page.get_pixmap(matrix=fitz.Matrix(min(1,1000/page.rect.width),min(1,1000/page.rect.width)),colorspace=fitz.csRGB,alpha=False).tobytes('png')
   (folder/(p['name']+'_preview.png')).write_bytes(preview)
   previews.append({'mime_type':'image/png','data':base64.b64encode(preview).decode()})
   reports.append({'name':p['name'],'size_cm':p['output_cm'],'corner_marks':p['corner_marks'],'mode':'CMYK','dpi':300,'source_icc_preserved':True,'file':dest.name,'sha256':sha(dest)})
 return {'report':{'source_sha256':sha(src),'panels':reports,'native_ai_verified':True,'ai_file':target.name,'ai_sha256':sha(target),'icc_sha256':hashlib.sha256(icc).hexdigest(),'archive_relative':job['archive_relative']},'previews':previews}

def sync_jpg(client,cfg,local_root):
 prefix='/adapters/'+cfg['account']+'/jpg-exports';r=client.get(prefix);r.raise_for_status();job=r.json().get('job')
 if not job:return 'jpg_idle'
 if not re.fullmatch('[a-f0-9]{64}',job['id']):raise ValueError('Invalid job ID')
 folder=Path(local_root)/job['id'];folder.mkdir(parents=True,exist_ok=True);done=folder/'verified.json';marker=folder/'started.json'
 try:
  if done.exists():
   result=json.loads(done.read_text(encoding='utf-8'))
   dest=safe(cfg['archive']['root'],job['archive_relative']);report=result['report']
   expected=[(report.get('ai_file',report.get('source_copy_file')),report.get('ai_sha256',report.get('source_copy_sha256')))]+[(x['file'],x['sha256']) for x in report['panels']]
   if any(sha(safe(dest,name))!=digest for name,digest in expected):raise ValueError('File sau xuất đã thay đổi; cần kiểm tra')
  elif marker.exists():raise ValueError('Xuất bị gián đoạn; cần kiểm tra, không tự tạo lại')
  else:
   a=job['source']['asset'];src=safe(cfg['archive']['root'],a['relative_path'])
   if src.stat().st_size>32*1024*1024 or sha(src)!=a['sha256']:raise ValueError('Source changed')
   copy=folder/('source'+src.suffix);shutil.copyfile(src,copy)
   marker.write_text(json.dumps({'job':job['id'],'source':a['sha256']}))
   result=export(job,copy,folder)
   dest=safe(cfg['archive']['root'],job['archive_relative']);dest.mkdir(parents=True,exist_ok=True)
   files=[result['report'].get('ai_file',result['report'].get('source_copy_file'))]+[p['file'] for p in result['report']['panels']]+[p['name']+'_preview.png' for p in result['report']['panels']]
   for name in files:
    out=dest/name
    if out.exists() and sha(out)!=sha(folder/name):raise ValueError('Archive output conflict')
    if not out.exists():shutil.copyfile(folder/name,out)
    if sha(out)!=sha(folder/name):raise ValueError('Archive verification failed')
   (dest/'plan.json').write_text(json.dumps(job['plan'],ensure_ascii=False,indent=2),encoding='utf-8')
   (dest/'report.json').write_text(json.dumps(result['report'],indent=2),encoding='utf-8')
   done.write_text(json.dumps(result),encoding='utf-8')
 except Exception as exc:result={'error':str(exc)[:1000] if isinstance(exc,ValueError) else type(exc).__name__}
 r=client.post(prefix+'/'+job['id'],json=result,timeout=240);r.raise_for_status();return 'jpg_'+r.json().get('state','review')

