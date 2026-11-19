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
  if not 1<=len(d)<=40 or any(p.rotation for p in d):raise ValueError('Nguồn quá nhiều trang/xoay cần kiểm tra')
  if len(d)>1 and any(not o.get('native') for p in panels for o in p['objects']):raise ValueError('Multi-board export requires native IDs')
  profiles=[]
  for x in range(1,d.xref_length()):
   if d.xref_get_key(x,'N')[1]=='4' and d.xref_is_stream(x):
    raw=d.xref_stream(x)
    if len(raw)>128 and raw[36:40]==b'acsp':profiles.append(raw)
  profiles=list({hashlib.sha256(x).hexdigest():x for x in profiles}.values())
  if len(profiles)>1:raise ValueError('Nhiều ICC CMYK; cần duyệt profile')
  images=d[0].get_image_info(xrefs=True)
  for p in panels:
   for o in p['objects']:
    if o.get('native'):continue
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
  return profiles[0] if profiles else None

JSX=r'''(function(){
var c=__CONFIG__, d=null, previous=app.documents.length?app.activeDocument:null, old=app.userInteractionLevel, cm=72/2.54;
function fail(s){throw Error(s);}
function same(a,b){for(var k=0;k<4;k++)if(Math.abs(a[k]-b[k])>.3)return false;return true;}
try{
 app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;
 d=app.open(new File(c.source));
 if(d.documentColorSpace!==DocumentColorSpace.CMYK)fail('Source document is not CMYK');
 if(d.artboards.length!==c.source_count)fail('Source artboard count changed');
 var origin=d.artboards[0].artboardRect, original=[];
 for(var z=0;z<d.pageItems.length;z++)original.push(d.pageItems[z]);
 var nativeItems={};
 // Resolve paths before adding layers: Illustrator layer insertion changes indices.
 for(var pn=0;pn<c.panels.length;pn++)for(var on=0;on<c.panels[pn].objects.length;on++){
  var spec=c.panels[pn].objects[on];if(!spec.native)continue;
  var item=at(d,spec.id);if(!item||item.typename!==spec.kind||!same(bounds(item),spec.bounds))fail('Native group changed: '+spec.id);
  nativeItems[spec.id]=item;
 }
 function find(o){
  if(o.native)return nativeItems[o.id];
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
 
 function continuousStripes(bg,dest,x,y,w,h,gapColor){
  // Reconstruct only simple, measured source geometry. Never resize artwork.
  var originalBox=bounds(bg),leaves=[],axis=null,g=dest.groupItems.add();
  function walk(q){
   if(q.hidden||q.opacity!==100||q.blendingMode!==BlendModes.NORMAL)fail('Stripe transparency/visibility requires review');
   if(q.typename==='GroupItem'){var a=children(q);for(var j=0;j<a.length;j++)if(!a[j].clipping)walk(a[j]);return;}
   if(q.typename!=='PathItem')fail('Unsupported stripe primitive: '+q.typename);
   var b=q.geometricBounds,points=q.pathPoints,color,vertical;
   for(var k=0;k<points.length;k++){var p=points[k],v=p.anchor;if(v[0]!==p.leftDirection[0]||v[1]!==p.leftDirection[1]||v[0]!==p.rightDirection[0]||v[1]!==p.rightDirection[1])fail('Curved stripes require review');}
   if(!q.closed&&points.length===2&&!q.filled&&q.stroked){
    color=q.strokeColor;var a=points[0].anchor,z=points[1].anchor;
    if(q.strokeDashes.length||q.strokeOverprint)fail('Dashed/overprint stripe requires review');
    vertical=Math.abs(a[0]-z[0])<.001;
    if(!vertical&&Math.abs(a[1]-z[1])>=.001)fail('Diagonal stripe requires review');
    if(q.strokeWidth<=0)fail('Invalid stripe width');
    b=vertical?[a[0]-q.strokeWidth/2,Math.max(a[1],z[1]),a[0]+q.strokeWidth/2,Math.min(a[1],z[1])]:[Math.min(a[0],z[0]),a[1]+q.strokeWidth/2,Math.max(a[0],z[0]),a[1]-q.strokeWidth/2];
    var vb=q.visibleBounds;
    if(vertical&&(Math.abs(vb[0]-b[0])>.02||Math.abs(vb[2]-b[2])>.02)||!vertical&&(Math.abs(vb[1]-b[1])>.02||Math.abs(vb[3]-b[3])>.02))fail('Nonuniform stroke appearance requires review');
   }else if(q.closed&&points.length===4&&q.filled&&!q.stroked){
    color=q.fillColor;if(q.fillOverprint)fail('Overprint stripe requires review');
    for(var k=0;k<4;k++){var v=points[k].anchor;if((Math.abs(v[0]-b[0])>.02&&Math.abs(v[0]-b[2])>.02)||(Math.abs(v[1]-b[1])>.02&&Math.abs(v[1]-b[3])>.02))fail('Nonrectangular stripe requires review');}
    if(Math.max(b[2]-b[0],b[1]-b[3])<2*Math.min(b[2]-b[0],b[1]-b[3]))fail('Stripe direction ambiguous');
    vertical=b[1]-b[3]>b[2]-b[0];
   }else fail('Unsupported stripe path');
   if(color.typename!=='CMYKColor')fail('Stripe must retain process CMYK');
   if(axis!==null&&axis!==vertical)fail('Mixed stripe directions');axis=vertical;
   leaves.push({box:b,color:color});
  }
  walk(bg);if(leaves.length<2)fail('Insufficient stripe geometry');
  var vertical=axis,dx=x+w/2-(originalBox[0]+originalBox[2])/2,dy=y-h/2-(originalBox[1]+originalBox[3])/2;
  var holes=[],intervals=[],sourceStart=vertical?originalBox[0]:originalBox[3],sourceEnd=vertical?originalBox[2]:originalBox[1];
  for(var i=0;i<leaves.length;i++){
   var z=leaves[i],b=z.box,l=vertical?b[0]:b[3],r=vertical?b[2]:b[1];
   // Paired segments create the original negative-space logo backing.
   for(var j=i+1;j<leaves.length;j++){
    var q=leaves[j],bb=q.box,ll=vertical?bb[0]:bb[3],rr=vertical?bb[2]:bb[1];
    if(Math.abs(l-ll)>.25||Math.abs(r-rr)>.25)continue;
    var high=vertical?Math.min(b[3],bb[3]):Math.min(b[2],bb[2]),low=vertical?Math.max(b[1],bb[1]):Math.max(b[0],bb[0]);
    if(vertical){var upper=b[1]>bb[1]?b:bb,lower=b[1]>bb[1]?bb:b;if(upper[3]>lower[1]+.02)holes.push([Math.min(l,ll),upper[3],Math.max(r,rr),lower[1]]);}
    else{var left=b[0]<bb[0]?b:bb,right=b[0]<bb[0]?bb:b;if(right[0]>left[2]+.02)holes.push([left[2],Math.max(r,rr),right[0],Math.min(l,ll)]);}
   }
   var item=vertical?g.pathItems.rectangle(y,b[0]+dx,b[2]-b[0],h):g.pathItems.rectangle(b[1]+dy,x,w,b[1]-b[3]);
   item.filled=true;item.stroked=false;item.fillColor=z.color;item.name='SOURCE_STRIPE_'+i;intervals.push([l,r]);
  }
  intervals.sort(function(a,b){return a[0]-b[0];});
  // Preserve actual spacing, even when source stripes are not mathematically uniform.
  if(intervals[0][0]>sourceStart+.03||intervals[intervals.length-1][1]<sourceEnd-.03)fail('Stripe field does not cover source frame');
  var start=vertical?x:y-h,end=vertical?x+w:y,shift=vertical?dx:dy;
  if(intervals[0][0]+shift>start+.03||intervals[intervals.length-1][1]+shift<end-.03)fail('Stripe field too narrow; repetition needs review');
  if(gapColor){if(gapColor.length!==4||gapColor.join(',')!=='0,0,0,0')fail('Nonwhite stripe gaps need original fill geometry');}
  // Unpainted gaps remain unpainted, exactly as in the source; CMYK JPG paper is white.
  var clip=dest.groupItems.add();g.move(clip,ElementPlacement.PLACEATEND);var mask=clip.pathItems.rectangle(y,x,w,h);mask.filled=false;mask.stroked=false;mask.clipping=true;clip.clipped=true;clip.name='CONTINUOUS_SOURCE_STRIPES';
  var stripeWidth=null,consistent=true;
  for(var sw=0;sw<leaves.length;sw++){var leaf=leaves[sw],col=leaf.color;
   if(col.cyan===0&&col.magenta===0&&col.yellow===0&&col.black===0)continue;
   var thickness=vertical?leaf.box[2]-leaf.box[0]:leaf.box[1]-leaf.box[3];
   if(stripeWidth===null)stripeWidth=thickness;else if(Math.abs(stripeWidth-thickness)>.03)consistent=false;
  }
  holes.stripeWidth=consistent?stripeWidth:null;
  return holes;
 }
 function restoreStripeKnockouts(holes,sourceBox,placedBox,rotation,layer,artboardCenterX,extraStripes){
  var matches=[],white=new CMYKColor();white.cyan=white.magenta=white.yellow=white.black=0;
  for(var i=0;i<holes.length;i++){var b=holes[i];if(b[2]>sourceBox[0]&&b[0]<sourceBox[2]&&b[1]>sourceBox[3]&&b[3]<sourceBox[1])matches.push(b);}
  if(!matches.length)return;
  if(typeof holes.stripeWidth!=='number'||holes.stripeWidth<=0)fail('White backing expansion needs one verified source stripe width');
  var union=matches[0].slice(0);for(var u=1;u<matches.length;u++){var v=matches[u];union=[Math.min(union[0],v[0]),Math.max(union[1],v[1]),Math.max(union[2],v[2]),Math.min(union[3],v[3])];}
  // Owner rule: add ONE colored stripe in total, half on each horizontal side.
  if(typeof extraStripes!=='number'||!isFinite(extraStripes)||extraStripes<0||extraStripes>2)fail('Invalid white backing stripe allowance');union[0]-=holes.stripeWidth*extraStripes/2;union[2]+=holes.stripeWidth*extraStripes/2;matches=[union];
  var sx=(sourceBox[0]+sourceBox[2])/2,sy=(sourceBox[1]+sourceBox[3])/2,px=(placedBox[0]+placedBox[2])/2,py=(placedBox[1]+placedBox[3])/2;
  var group=layer.groupItems.add();group.name='SOURCE_NEGATIVE_SPACE_WHITE';
  for(var i=0;i<matches.length;i++){var b=matches[i],left=rotation===180?px-(b[2]-sx):px+(b[0]-sx),top=rotation===180?py-(b[3]-sy):py+(b[1]-sy);var q=group.pathItems.rectangle(top,left,b[2]-b[0],b[1]-b[3]);if(typeof artboardCenterX==='number')q.translate(artboardCenterX-(left+(b[2]-b[0])/2),0);q.filled=true;q.stroked=false;q.fillColor=white;}
  group.zOrder(ZOrderMethod.SENDTOBACK);
 }



 var bgSwatches={},stage='packing',left=d.visibleBounds[0],right=d.visibleBounds[2],bottom=d.visibleBounds[3];
 for(var si=0;si<d.artboards.length;si++){var br=d.artboards[si].artboardRect;left=Math.min(left,br[0]);right=Math.max(right,br[2]);bottom=Math.min(bottom,br[3]);}
 var cursorX=left,cursorY=bottom-100,rowHeight=0;
 function slot(w,h){if(cursorX>left&&cursorX+w>right){cursorX=left;cursorY-=rowHeight+100;rowHeight=0;}var result=[cursorX,cursorY];cursorX+=w+100;rowHeight=Math.max(rowHeight,h);return result;}
 for(var n=0;n<c.panels.length;n++){
  var p=c.panels[n], w=p.output_cm[0],h=p.output_cm[1],pos=slot(w*cm,h*cm),x=pos[0],y=pos[1],layer=d.layers.add();stage='panel '+p.name;layer.name='PRINT_'+p.name;
  
  var ab=d.artboards.add([x,y,x+w*cm,y-h*cm]);ab.name='PRINT_'+p.name;
  var stripeHoles=[],map={};for(var q=0;q<p.objects.length;q++)map[p.objects[q].id]=p.objects[q];
  if(p.background_object_id&&p.background_mode!=='registered_per_face'){var bg=find(map[p.background_object_id]);var backgroundLayer=layer.layers.add();backgroundLayer.name="BACKGROUND_EDIT_COLOR";if(p.background_mode==='continuous_stripes'){if(p.stripe_gap_cmyk&&!p.stripe_gap_evidence)fail('Missing stripe gap evidence');stripeHoles=continuousStripes(bg,backgroundLayer,x,y,w*cm,h*cm,p.stripe_gap_cmyk);}else if(bg.typename==='PathItem'){if(!bg.filled||bg.fillColor.typename!=='CMYKColor')fail('Background not original CMYK');var r=backgroundLayer.pathItems.rectangle(y,x,w*cm,h*cm);r.filled=true;var bc=bg.fillColor,bkey=[bc.cyan,bc.magenta,bc.yellow,bc.black].join('_');if(!bgSwatches[bkey]){var sp=d.spots.add();sp.name='CANAVI_BG_'+n;sp.colorType=ColorModel.PROCESS;sp.color=bc;bgSwatches[bkey]=sp;}var linked=new SpotColor();linked.spot=bgSwatches[bkey];linked.tint=100;r.fillColor=linked;r.stroked=false;r.name='SOURCE_CMYK_BACKGROUND';}else{var bgg=bg.duplicate(backgroundLayer,ElementPlacement.PLACEATEND);if(bgg.typename==='GroupItem'&&bgg.clipped){bgg.clipped=false;var bgkids=children(bgg);for(var bgi=bgkids.length-1;bgi>=0;bgi--)if(bgkids[bgi].clipping)bgkids[bgi].remove();}var bgb=bounds(bgg),bgw=bgb[2]-bgb[0],bgh=bgb[1]-bgb[3];if(bgw<=0||bgh<=0)fail('Empty background group');bgg.resize((w*cm/bgw)*100,(h*cm/bgh)*100,true,true,true,true,100,Transformation.TOPLEFT);var bgp=bounds(bgg);bgg.translate(x-bgp[0],y-bgp[1]);bgg.name='SOURCE_GROUP_BACKGROUND';}}
  for(var j=0;j<p.components.length;j++){
   var a=p.components[j],artworkLayer=layer.layers.add();artworkLayer.name="ARTWORK_"+a.side;var g=artworkLayer.groupItems.add(),crop=null,ids=a.object_ids;
   if(ids.length===1&&map[ids[0]].kind==='image')crop=map[ids[0]].crop_fraction;
   for(var k=0;k<ids.length;k++){var originalItem=find(map[ids[k]]);originalItem.duplicate(g,ElementPlacement.PLACEATEND);}
   if(ids.length===1&&map[ids[0]].clip_group){var cp=map[ids[0]].clip_group;for(var ck=0;ck<cp.pathItems.length;ck++)if(cp.pathItems[ck].clipping){cp.pathItems[ck].duplicate(g,ElementPlacement.PLACEATBEGINNING);g.clipped=true;}}
   if(ids.length>1){for(var k=0;k<ids.length;k++)if(map[ids[k]].kind==='image')fail('Mixed image group needs review');}
   var gb=groupBounds(g),visibleW=gb[2]-gb[0],visibleH=gb[1]-gb[3];var sourceCenter=[(gb[0]+gb[2])/2,(gb[1]+gb[3])/2];
   if(crop){visibleW*=crop[2]-crop[0];visibleH*=crop[3]-crop[1];}
   if(visibleW<=0||visibleH<=0)fail('Empty geometry');var scale=a.preserve_native_size?1:a.width_cm*cm/visibleW;if(a.preserve_native_size&&Math.abs(a.width_cm-visibleW/cm)>.02)fail('Native size mismatch');
   var anchor=a.vertical_anchor||'top';if(anchor!=='top'&&anchor!=='bottom')fail('Unknown vertical anchor');var top=anchor==='bottom'?h-a.y_cm-visibleH*scale/cm:a.y_cm;
   if(!a.preserve_source_bleed&&(a.y_cm<0||top<-.001||top+visibleH*scale/cm>h+.001))fail('Artwork exceeds artboard height');
   if(!a.preserve_native_size)g.resize(scale*100,scale*100,true,true,true,true,scale*100,Transformation.TOPLEFT);
   if(a.rotation===180){g.rotate(180);if(crop)crop=[1-crop[2],1-crop[3],1-crop[0],1-crop[1]];}
   var placed=groupBounds(g);g.translate(x+a.x_cm*cm-(crop?g.width*crop[0]:0)-placed[0],y-top*cm+(crop?g.height*crop[1]:0)-placed[1]);g.name='ORIGINAL_ARTWORK_'+j;if(a.horizontal_alignment==='center'){var centered=groupBounds(g);g.translate(x+w*cm/2-(centered[0]+centered[2])/2,0);}if(stripeHoles.length)restoreStripeKnockouts(stripeHoles,gb,groupBounds(g),a.rotation,artworkLayer,a.horizontal_alignment==='center'?x+w*cm/2:null,typeof p.white_backing_extra_stripes==='number'?p.white_backing_extra_stripes:1);
   if(p.background_mode==='registered_per_face'&&a.background_object_id){
    var bl=layer.layers.add();bl.name='BACKGROUND_'+a.side;bl.zOrder(ZOrderMethod.SENDTOBACK);
    var bg=find(map[a.background_object_id]),dup=bg.duplicate(bl,ElementPlacement.PLACEATEND),bb=bounds(dup);
    var dx=((bb[0]+bb[2])/2-sourceCenter[0])*scale,dy=((bb[1]+bb[3])/2-sourceCenter[1])*scale;
    dup.resize(scale*100,scale*100,true,true,true,true,scale*100,Transformation.CENTER);
    if(a.rotation===180){dup.rotate(180);dx=-dx;dy=-dy;}
    var abox=groupBounds(g),db=bounds(dup);
    dup.translate((abox[0]+abox[2])/2+dx-(db[0]+db[2])/2,(abox[1]+abox[3])/2+dy-(db[1]+db[3])/2);
    var clipGroup=bl.groupItems.add();dup.move(clipGroup,ElementPlacement.PLACEATEND);
    var joined=p.construction==='joined_two_faces',ch=joined?h*cm/2:h*cm,ct=joined&&a.side==='back'?y-ch:y;
    var mask=clipGroup.pathItems.rectangle(ct,x,w*cm,ch);mask.filled=false;mask.stroked=false;mask.clipping=true;clipGroup.clipped=true;
   }

  }
  if(p.corner_marks){var black=new CMYKColor();black.black=100;black.cyan=black.magenta=black.yellow=0;
   var corners=[[x,y,1,-1],[x+w*cm,y,-1,-1],[x,y-h*cm,1,1],[x+w*cm,y-h*cm,-1,1]];
   for(var k=0;k<4;k++){var v=corners[k],mark=layer.pathItems.add();mark.setEntirePath([[v[0]+v[2]*cm,v[1]],[v[0],v[1]],[v[0],v[1]+v[3]*cm]]);mark.filled=false;mark.stroked=true;mark.strokeColor=black;mark.strokeWidth=.72;mark.name='L_1CM';}
  }
 }
 /* Preserve all original artboard names. */var opts=new IllustratorSaveOptions();opts.pdfCompatible=true;opts.embedICCProfile=true;d.saveAs(new File(c.output),opts);d.close(SaveOptions.DONOTSAVECHANGES);d=null;
 d=app.open(new File(c.output));if(d.artboards.length!==c.panels.length+c.source_count||d.documentColorSpace!==DocumentColorSpace.CMYK)fail('Saved AI verification');
 return 'verified';
}catch(error){throw Error('JPG '+stage+': '+String(error));}finally{if(d){try{d.close(SaveOptions.DONOTSAVECHANGES);}catch(closeError){}}try{app.userInteractionLevel=old;}catch(resetError){}if(previous){try{previous.activate();}catch(e){}}}
})()'''

def export(job,src,folder):
 if job['plan'].get('renderer')=='original_pdf_v1':
  from original_pdf_export import export as pdf_export
  return pdf_export(job,src,folder)
 if job['plan'].get('renderer')=='native_pattern_v1':
  from pattern_export import export as native_export
  return native_export(job,src,folder)
 if job['plan'].get('source_sha256') and job['plan']['source_sha256']!=sha(src):raise ValueError('Native plan/source mismatch')
 panels=job['plan']['panels'];icc=source_info(src,panels)
 with fitz.open(src) as original:source_count=len(original)
 target=folder/(job['plan']['order_code'].replace(' ','_')+'_EDITABLE.ai')
 config={'source':str(src).replace('\\','/'),'output':str(target).replace('\\','/'),'panels':panels,'source_count':source_count}
 from native_local import COMMON
 (folder/'export.jsx').write_text((COMMON+JSX).replace('__CONFIG__',json.dumps(config,ensure_ascii=True)),encoding='utf-8')
 command=__import__("adobe_ready").ready_command("Illustrator.Application","$ai")+"$s=[IO.File]::ReadAllText((Join-Path (Get-Location) 'export.jsx')); $ai.DoJavaScript($s)"
 from font_dialog_guard import FontDialogGuard
 with FontDialogGuard(folder):
  r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=360)
 if r.returncode or r.stdout.decode(errors='replace').strip()!='verified':
  (folder/'illustrator-error.txt').write_bytes(r.stderr+r.stdout)
  raise ValueError('Illustrator chưa xác minh AI: '+r.stderr.decode(errors='replace')[:800])
 reports=[];previews=[]
 with fitz.open(target) as doc:
  if len(doc)!=len(panels)+source_count:raise ValueError('AI page count mismatch')
  for n,p in enumerate(panels,source_count):
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
   reports.append({'name':p['name'],'size_cm':p['output_cm'],'corner_marks':p['corner_marks'],'mode':'CMYK','dpi':300,'source_icc_preserved':bool(icc),'untagged_source':icc is None,'file':dest.name,'sha256':sha(dest)})
 return {'report':{'source_sha256':sha(src),'panels':reports,'native_ai_verified':True,'ai_file':target.name,'ai_sha256':sha(target),'icc_sha256':hashlib.sha256(icc).hexdigest() if icc else None,'archive_relative':job['archive_relative']},'previews':previews}

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
   if src.stat().st_size>128*1024*1024 or sha(src)!=a['sha256']:raise ValueError('Source changed')
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





