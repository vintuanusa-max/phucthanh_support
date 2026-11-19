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
  var originalBox=bounds(bg),leaves=[],axis=null,g=dest.groupItems.add(),baseColor=null;
  var origW=originalBox[2]-originalBox[0],origH=originalBox[1]-originalBox[3];
  function isNonWhiteCmyk(c){return c&&c.typename==='CMYKColor'&&(c.cyan>.2||c.magenta>.2||c.yellow>.2||c.black>.2);}
  function isBaseRect(ib){
   var iw=ib[2]-ib[0],ih=ib[1]-ib[3];
   if(iw<origW*.70||ih<origH*.70||iw>origW*1.35||ih>origH*1.35)return false;
   var ix0=Math.max(ib[0],originalBox[0]),ix1=Math.min(ib[2],originalBox[2]),iy0=Math.max(ib[3],originalBox[3]),iy1=Math.min(ib[1],originalBox[1]);
   return ix1>ix0&&iy1>iy0&&((ix1-ix0)*(iy1-iy0))>=origW*origH*.60;
  }
  function walk(q){
   if(q.hidden||q.opacity!==100||q.blendingMode!==BlendModes.NORMAL)fail('Stripe transparency/visibility requires review');
   if(q.typename==='GroupItem'){var a=children(q);for(var j=0;j<a.length;j++)if(!a[j].clipping)walk(a[j]);return;}
   if(q.typename==='CompoundPathItem'){
    if(!q.pathItems||!q.pathItems.length||q.pathItems[0].clipping)return;
    var subs=[];for(var ci=0;ci<q.pathItems.length;ci++)if(!q.pathItems[ci].clipping)subs.push(q.pathItems[ci]);
    for(var ci=0;ci<subs.length;ci++){
     var sb=subs[ci].geometricBounds,enclosed=false;
     for(var cj=0;cj<subs.length;cj++){if(ci===cj)continue;var ob=subs[cj].geometricBounds;if(ob[0]<=sb[0]+.1&&ob[1]>=sb[1]-.1&&ob[2]>=sb[2]-.1&&ob[3]<=sb[3]+.1&&((ob[2]-ob[0])>(sb[2]-sb[0])+.2||(ob[1]-ob[3])>(sb[1]-sb[3])+.2)){enclosed=true;break;}}
     if(!enclosed)walk(subs[ci]);
    }
    return;
   }
   if(q.typename!=='PathItem')fail('Unsupported stripe primitive: '+q.typename);
   var b=q.geometricBounds,points=q.pathPoints,color,vertical;
   if(!q.filled&&!q.stroked)return;
   if(points.length<2)return;
   if(q.filled&&isNonWhiteCmyk(q.fillColor)&&isBaseRect(b)&&Math.max(b[2]-b[0],b[1]-b[3])<2*Math.min(b[2]-b[0],b[1]-b[3])){if(!baseColor)baseColor=q.fillColor;return;}
   for(var k=0;k<points.length;k++){var p=points[k],v=p.anchor;if(v[0]!==p.leftDirection[0]||v[1]!==p.leftDirection[1]||v[0]!==p.rightDirection[0]||v[1]!==p.rightDirection[1])fail('Curved stripes require review');}
   if(!q.closed&&points.length>=2&&!q.filled&&q.stroked){
    color=q.strokeColor;var a=points[0].anchor,z=points[points.length-1].anchor;
    if(q.strokeDashes.length||q.strokeOverprint)fail('Dashed/overprint stripe requires review');
    vertical=true;var horiz=true;
    for(var k=1;k<points.length;k++){var pk=points[k].anchor;if(Math.abs(pk[0]-a[0])>=.001)vertical=false;if(Math.abs(pk[1]-a[1])>=.001)horiz=false;}
    if(!vertical&&!horiz)fail('Diagonal stripe requires review');
    if(q.strokeWidth<=0)fail('Invalid stripe width');
    b=vertical?[a[0]-q.strokeWidth/2,Math.max(a[1],z[1]),a[0]+q.strokeWidth/2,Math.min(a[1],z[1])]:[Math.min(a[0],z[0]),a[1]+q.strokeWidth/2,Math.max(a[0],z[0]),a[1]-q.strokeWidth/2];
    var vb=q.visibleBounds;
    if(vertical&&(Math.abs(vb[0]-b[0])>.02||Math.abs(vb[2]-b[2])>.02)||!vertical&&(Math.abs(vb[1]-b[1])>.02||Math.abs(vb[3]-b[3])>.02))fail('Nonuniform stroke appearance requires review');
   }else if(points.length>=4&&q.filled&&(!q.stroked||q.strokeWidth<=2.0)){
    color=q.fillColor;if(q.fillOverprint)fail('Overprint stripe requires review');
    if(q.stroked)b=q.visibleBounds;
    var area2=0;for(var k=0;k<points.length;k++){var v1=points[k].anchor,v2=points[(k+1)%points.length].anchor;if(Math.abs(v1[0]-v2[0])>.02&&Math.abs(v1[1]-v2[1])>.02)fail('Nonrectangular stripe requires review');area2+=v1[0]*v2[1]-v2[0]*v1[1];}
    var boxArea=(b[2]-b[0])*(b[1]-b[3]);if(Math.abs(Math.abs(area2)/2-boxArea)>0.5)fail('Nonrectangular stripe requires review');
    if(Math.max(b[2]-b[0],b[1]-b[3])<2*Math.min(b[2]-b[0],b[1]-b[3]))fail('Stripe direction ambiguous');
    vertical=b[1]-b[3]>b[2]-b[0];
   }else fail('Unsupported stripe path (closed='+q.closed+',pts='+points.length+',filled='+q.filled+',stroked='+q.stroked+',sw='+q.strokeWidth+')');
   if(color.typename!=='CMYKColor')fail('Stripe must retain process CMYK');
   if(axis!==null&&axis!==vertical)fail('Mixed stripe directions');axis=vertical;
   leaves.push({box:b,color:color});
  }
  walk(bg);
  var mergedLeaves=[];
  for(var li=0;li<leaves.length;li++){
   var lb=leaves[li].box,lc=leaves[li].color,subsumed=false;
   for(var lj=0;lj<leaves.length;lj++){
    if(li===lj)continue;
    var ob=leaves[lj].box,oc=leaves[lj].color;
    if(Math.abs(lc.cyan-oc.cyan)<1&&Math.abs(lc.magenta-oc.magenta)<1&&Math.abs(lc.yellow-oc.yellow)<1&&Math.abs(lc.black-oc.black)<1&&ob[0]<=lb[0]+.2&&ob[1]>=lb[1]-.2&&ob[2]>=lb[2]-.2&&ob[3]<=lb[3]+.2&&((ob[2]-ob[0])>(lb[2]-lb[0])+.2||(ob[1]-ob[3])>(lb[1]-lb[3])+.2)){subsumed=true;break;}
   }
   if(!subsumed)mergedLeaves.push(leaves[li]);
  }
  leaves=mergedLeaves;
  if(leaves.length<2)fail('Insufficient stripe geometry');
  if(!baseColor){
   function findBaseIn(container){
    var items=container.pageItems;
    for(var fi=items.length-1;fi>=0;fi--){
     var it=items[fi];
     if(it===bg||it.hidden)continue;
     if(it.typename==='GroupItem'){var res=findBaseIn(it);if(res)return res;}
     else if(it.typename==='PathItem'&&!it.clipping&&it.filled&&isNonWhiteCmyk(it.fillColor)&&isBaseRect(it.geometricBounds))return it.fillColor;
    }
    return null;
   }
   if(bg.parent)baseColor=findBaseIn(bg.parent);
   if(!baseColor&&bg.layer&&bg.layer!==bg.parent)baseColor=findBaseIn(bg.layer);
  }
  if(baseColor){
   var baseRect=g.pathItems.rectangle(y,x,w,h);baseRect.filled=true;baseRect.stroked=false;baseRect.fillColor=baseColor;baseRect.name='SOURCE_STRIPE_BASE_COLOR';baseRect.zOrder(ZOrderMethod.SENDTOBACK);
  }
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
  // Preserve actual spacing, even when source stripes are not mathematically uniform; periodic extension below covers [start, end].
  var start=vertical?x:y-h,end=vertical?x+w:y,shift=vertical?dx:dy;
  if(intervals[0][0]+shift>start+.03||intervals[intervals.length-1][1]+shift<end-.03){
   var cols=[];
   for(var ci=0;ci<leaves.length;ci++){
    var lb=leaves[ci].box,cl=vertical?lb[0]:lb[3],cr=vertical?lb[2]:lb[1],cc=leaves[ci].color,found=false;
    for(var cj=0;cj<cols.length;cj++){
     if(Math.abs(cols[cj].l-cl)<=.25&&Math.abs(cols[cj].r-cr)<=.25&&Math.abs(cols[cj].c.cyan-cc.cyan)<.5&&Math.abs(cols[cj].c.magenta-cc.magenta)<.5&&Math.abs(cols[cj].c.yellow-cc.yellow)<.5&&Math.abs(cols[cj].c.black-cc.black)<.5){found=true;break;}
    }
    if(!found)cols.push({l:cl,r:cr,w:cr-cl,c:cc});
   }
   cols.sort(function(a,b){return a.l-b.l;});
   var srcCols=cols.length>=4?cols.slice(1,cols.length-1):cols;
   var period=0,kMatch=0;
   for(var k=1;k<=Math.min(6,srcCols.length-1);k++){
    var cand=srcCols[k].l-srcCols[0].l;
    if(cand<=.5)continue;
    var ok=true;
    for(var m=0;m+k<srcCols.length;m++){
     if(Math.abs((srcCols[m+k].l-srcCols[m].l)-cand)>4.0||Math.abs(srcCols[m+k].w-srcCols[m].w)>3.0){ok=false;break;}
     var c1=srcCols[m].c,c2=srcCols[m+k].c;
     if(Math.abs(c1.cyan-c2.cyan)>1.5||Math.abs(c1.magenta-c2.magenta)>1.5||Math.abs(c1.yellow-c2.yellow)>1.5||Math.abs(c1.black-c2.black)>1.5){ok=false;break;}
    }
    if(ok){var spans=Math.floor((srcCols.length-1)/k);period=spans>0?(srcCols[spans*k].l-srcCols[0].l)/spans:cand;kMatch=k;break;}
   }
   if(period<=0){var dbg=[];for(var di=0;di<Math.min(5,cols.length);di++)dbg.push(cols[di].l.toFixed(1)+':'+cols[di].w.toFixed(1));fail('Stripe field too narrow; repetition needs review (cols='+cols.length+' '+dbg.join(',')+')');}
   var minEdge=cols[0].l+shift,maxEdge=cols[cols.length-1].r+shift,extIdx=0;
   for(var step=-1;minEdge>start+.03;step--){
    var anyAdded=false;
    for(var pIdx=kMatch-1;pIdx>=0;pIdx--){
     var sc=srcCols[pIdx],nl=sc.l+step*period+shift,nr=sc.r+step*period+shift;
     if(nr<start-period-1)continue;
     var ex=vertical?g.pathItems.rectangle(y,nl,sc.w,h):g.pathItems.rectangle(nr,x,w,sc.w);
     ex.filled=true;ex.stroked=false;ex.fillColor=sc.c;ex.name='EXTENDED_STRIPE_L_'+(extIdx++);
     intervals.push([nl-shift,nr-shift]);minEdge=Math.min(minEdge,nl);anyAdded=true;
    }
    if(!anyAdded&&srcCols[0].l+step*period+shift<start-period-1)break;
    if(step<-200)fail('Stripe field repetition overflow');
   }
   for(var step=1;maxEdge<end-.03;step++){
    var anyAdded=false;
    for(var pIdx=0;pIdx<kMatch;pIdx++){
     var sc=srcCols[srcCols.length-kMatch+pIdx],nl=sc.l+step*period+shift,nr=sc.r+step*period+shift;
     if(nl>end+period+1)continue;
     var ex=vertical?g.pathItems.rectangle(y,nl,sc.w,h):g.pathItems.rectangle(nr,x,w,sc.w);
     ex.filled=true;ex.stroked=false;ex.fillColor=sc.c;ex.name='EXTENDED_STRIPE_R_'+(extIdx++);
     intervals.push([nl-shift,nr-shift]);maxEdge=Math.max(maxEdge,nr);anyAdded=true;
    }
    if(!anyAdded&&srcCols[srcCols.length-1].r+step*period+shift>end+period+1)break;
    if(step>200)fail('Stripe field repetition overflow');
   }
   intervals.sort(function(a,b){return a[0]-b[0];});
   if(intervals[0][0]+shift>start+.03||intervals[intervals.length-1][1]+shift<end-.03)fail('Stripe field too narrow; repetition needs review');
  }
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
  var matches=[],yFallback=false,white=new CMYKColor();white.cyan=white.magenta=white.yellow=white.black=0;
  for(var i=0;i<holes.length;i++){var b=holes[i];if(b[2]>sourceBox[0]&&b[0]<sourceBox[2]&&b[1]>sourceBox[3]&&b[3]<sourceBox[1])matches.push(b);}
  if(!matches.length){for(var i=0;i<holes.length;i++){var b=holes[i];if(b[1]>sourceBox[3]&&b[3]<sourceBox[1])matches.push(b);}if(matches.length)yFallback=true;}
  if(!matches.length)return;
  if(typeof holes.stripeWidth!=='number'||holes.stripeWidth<=0)fail('White backing expansion needs one verified source stripe width');
  var union=matches[0].slice(0);for(var u=1;u<matches.length;u++){var v=matches[u];union=[Math.min(union[0],v[0]),Math.max(union[1],v[1]),Math.max(union[2],v[2]),Math.min(union[3],v[3])];}
  var expanded=true;
  while(expanded){
   expanded=false;
   for(var hi=0;hi<holes.length;hi++){
    var hb=holes[hi];
    if(Math.abs(hb[1]-union[1])<1.0&&Math.abs(hb[3]-union[3])<1.0&&(hb[0]<union[0]||hb[2]>union[2])&&hb[2]>=union[0]-holes.stripeWidth*2.5&&hb[0]<=union[2]+holes.stripeWidth*2.5){
     union=[Math.min(union[0],hb[0]),Math.max(union[1],hb[1]),Math.max(union[2],hb[2]),Math.min(union[3],hb[3])];
     expanded=true;
    }
   }
  }
  // Owner rule: add ONE colored stripe in total, half on each horizontal side.
  if(typeof extraStripes!=='number'||!isFinite(extraStripes)||extraStripes<0||extraStripes>2)fail('Invalid white backing stripe allowance');union[0]-=holes.stripeWidth*extraStripes/2;union[2]+=holes.stripeWidth*extraStripes/2;matches=[union];
  var sx=yFallback?(union[0]+union[2])/2:(sourceBox[0]+sourceBox[2])/2,sy=(sourceBox[1]+sourceBox[3])/2,px=(placedBox[0]+placedBox[2])/2,py=(placedBox[1]+placedBox[3])/2;
  var group=layer.groupItems.add();group.name='SOURCE_NEGATIVE_SPACE_WHITE';
  for(var i=0;i<matches.length;i++){var b=matches[i],left=rotation===180?px-(b[2]-sx):px+(b[0]-sx),top=rotation===180?py-(b[3]-sy):py+(b[1]-sy);var q=group.pathItems.rectangle(top,left,b[2]-b[0],b[1]-b[3]);if(typeof artboardCenterX==='number')q.translate(artboardCenterX-(left+(b[2]-b[0])/2),0);q.filled=true;q.stroked=false;q.fillColor=white;}
  group.zOrder(ZOrderMethod.SENDTOBACK);
 }


 function isClipItem(it){
  if(!it)return false;
  if(it.typename==='PathItem')return Boolean(it.clipping);
  if(it.typename==='CompoundPathItem')return it.pathItems&&it.pathItems.length>0&&Boolean(it.pathItems[0].clipping);
  return false;
 }
 function releaseClippingMasks(grp){
  if(!grp||grp.typename!=='GroupItem')return grp;
  if(grp.clipped){
   var kids=children(grp);
   for(var i=kids.length-1;i>=0;i--)if(isClipItem(kids[i]))kids[i].remove();
   if(grp.clipped){try{grp.clipped=false;}catch(e){}}
   if(grp.clipped){
    var rem0=children(grp),fresh=grp.parent.groupItems.add();
    for(var k=0;k<rem0.length;k++)rem0[k].move(fresh,ElementPlacement.PLACEATEND);
    grp.remove();
    grp=fresh;
   }
  }
  var rem=children(grp);
  for(var j=0;j<rem.length;j++)if(rem[j].typename==='GroupItem')releaseClippingMasks(rem[j]);
  return grp;
 }
 function colorKey(col){
  if(!col)return '';
  if(col.typename==='CMYKColor')return 'C:'+Math.round(col.cyan)+','+Math.round(col.magenta)+','+Math.round(col.yellow)+','+Math.round(col.black);
  if(col.typename==='RGBColor')return 'R:'+Math.round(col.red)+','+Math.round(col.green)+','+Math.round(col.blue);
  if(col.typename==='GrayColor')return 'G:'+Math.round(col.gray);
  if(col.typename==='SpotColor'&&col.spot)return 'S:'+col.spot.name+':'+Math.round(col.tint);
  return col.typename;
 }
 function detectPatternPeriod(grp,bgW,bgH){
  var leaves=[];
  function collect(it){
   if(leaves.length>=600||!it||it.hidden)return;
   if(it.typename==='PathItem'){
    if(it.filled&&!it.clipping){
     var b=it.geometricBounds,pw=b[2]-b[0],ph=b[1]-b[3];
     if(pw>0.5&&ph>0.5)leaves.push({b:b,c:colorKey(it.fillColor)});
    }
    return;
   }
   if(it.typename==='GroupItem'){
    var cc=children(it);
    for(var i=0;i<cc.length;i++)collect(cc[i]);
   }
  }
  collect(grp);
  function axisPeriod(isX){
   var buckets={};
   for(var i=0;i<leaves.length;i++){
    var lv=leaves[i],pos=isX?lv.b[0]:lv.b[1],key=String(Math.round(pos));
    if(!buckets[key])buckets[key]={pos:pos,items:[]};
    buckets[key].items.push({other:Math.round(isX?lv.b[1]:lv.b[0]),c:lv.c});
   }
   var cols=[],ks=[];
   for(var k in buckets)if(buckets.hasOwnProperty(k))ks.push(buckets[k]);
   ks.sort(function(a,b){return isX?(a.pos-b.pos):(b.pos-a.pos);});
   for(var i=0;i<ks.length;i++){
    if(cols.length&&Math.abs(ks[i].pos-cols[cols.length-1].pos)<=1.0){
     cols[cols.length-1].items=cols[cols.length-1].items.concat(ks[i].items);
    }else if(ks[i].items.length>=2){
     cols.push(ks[i]);
    }
   }
   if(cols.length<3)return 0;
   function sigMatch(c1,c2){
    var hits=0;
    for(var i=0;i<c1.items.length;i++){
     for(var j=0;j<c2.items.length;j++){
      if(Math.abs(c1.items[i].other-c2.items[j].other)<=1.5){
       if(c1.items[i].c!==c2.items[j].c)return false;
       hits++;break;
      }
     }
    }
    return hits>=2;
   }
   for(var per=1;per<=Math.min(6,cols.length-2);per++){
    var pSpan=Math.abs(cols[per].pos-cols[0].pos);
    if(pSpan<2)continue;
    var ok=true;
    for(var m=0;m+per<cols.length;m++){
     if(Math.abs(Math.abs(cols[m+per].pos-cols[m].pos)-pSpan)>2.0||!sigMatch(cols[m],cols[m+per])){ok=false;break;}
    }
    if(ok){var count=Math.floor((cols.length-1)/per);return count>0?Math.abs(cols[count*per].pos-cols[0].pos)/count:pSpan;}
   }
   return 0;
  }
  var px=axisPeriod(true),py=axisPeriod(false);
  var stepX=(px>0&&bgW>=px)?Math.floor((bgW+0.5)/px)*px:bgW;
  var stepY=(py>0&&bgH>=py)?Math.floor((bgH+0.5)/py)*py:bgH;
  return {stepX:stepX>0?stepX:bgW,stepY:stepY>0?stepY:bgH};
 }
 function renderFullArtboardPattern(p,layer,x,y,wPt,hPt,map,frontReg){
  var bgId=(frontReg&&frontReg.bgId)||p.background_object_id;
  if(!bgId||!map[bgId])return;
  var backgroundLayer=layer.layers.add();backgroundLayer.name='BACKGROUND_EDIT_COLOR';
  var bg=find(map[bgId]),baseDup=bg.duplicate(backgroundLayer,ElementPlacement.PLACEATEND);
  baseDup=releaseClippingMasks(baseDup);
  var bb=groupBounds(baseDup),bgW=bb[2]-bb[0],bgH=bb[1]-bb[3];
  if(bgW<=0||bgH<=0)fail('Empty full_artboard_pattern background');
  if(frontReg){
   var sc=frontReg.scale||1;
   var bgCx=(bb[0]+bb[2])/2,bgCy=(bb[1]+bb[3])/2;
   var dx=(bgCx-frontReg.sourceCenter[0])*sc,dy=(bgCy-frontReg.sourceCenter[1])*sc;
   if(Math.abs(sc-1)>0.001)baseDup.resize(sc*100,sc*100,true,true,true,true,sc*100,Transformation.CENTER);
   var nb=groupBounds(baseDup),ncx=(nb[0]+nb[2])/2,ncy=(nb[1]+nb[3])/2;
   baseDup.translate(frontReg.placedCenter[0]+dx-ncx,frontReg.placedCenter[1]+dy-ncy);
  }else{
   var bgCx=(bb[0]+bb[2])/2,bgCy=(bb[1]+bb[3])/2;
   baseDup.translate((x+wPt/2)-bgCx,(y-hPt/2)-bgCy);
  }
  bb=groupBounds(baseDup);bgW=bb[2]-bb[0];bgH=bb[1]-bb[3];
  var step=detectPatternPeriod(baseDup,bgW,bgH);
  var minIx=bb[0]>x+0.5?-Math.ceil((bb[0]-x)/step.stepX):0;
  var maxIx=bb[2]<x+wPt-0.5?Math.ceil((x+wPt-bb[2])/step.stepX):0;
  var minIy=bb[3]>y-hPt+0.5?-Math.ceil((bb[3]-(y-hPt))/step.stepY):0;
  var maxIy=bb[1]<y-0.5?Math.ceil((y-bb[1])/step.stepY):0;
  if((maxIx-minIx+1)*(maxIy-minIy+1)>64)fail('Pattern tile count exceeds safe limit');
  var patContainer=backgroundLayer.groupItems.add();
  baseDup.move(patContainer,ElementPlacement.PLACEATEND);
  for(var ix=minIx;ix<=maxIx;ix++){
   for(var iy=minIy;iy<=maxIy;iy++){
    if(ix===0&&iy===0)continue;
    var dupTile=baseDup.duplicate(patContainer,ElementPlacement.PLACEATEND);
    dupTile.translate(ix*step.stepX,iy*step.stepY);
   }
  }
  var patClip=backgroundLayer.groupItems.add();
  patContainer.move(patClip,ElementPlacement.PLACEATEND);
  var patMask=patClip.pathItems.rectangle(y,x,wPt,hPt);
  patMask.filled=false;patMask.stroked=false;patMask.clipping=true;
  patClip.clipped=true;patClip.name='FULL_ARTBOARD_PATTERN';
  backgroundLayer.zOrder(ZOrderMethod.SENDTOBACK);
 }

 var bgSwatches={},stage='packing',left=d.visibleBounds[0],top=d.visibleBounds[1],right=d.visibleBounds[2],bottom=d.visibleBounds[3],abLeft=1e9,abTop=-1e9,abRight=-1e9,abBottom=1e9;
 for(var si=0;si<d.artboards.length;si++){var br=d.artboards[si].artboardRect;left=Math.min(left,br[0]);top=Math.max(top,br[1]);right=Math.max(right,br[2]);bottom=Math.min(bottom,br[3]);abLeft=Math.min(abLeft,br[0]);abTop=Math.max(abTop,br[1]);abRight=Math.max(abRight,br[2]);abBottom=Math.min(abBottom,br[3]);}
 var maxRight=abRight+100+6000,cursorX=abRight+100,cursorY=abTop,rowHeight=0,usedTopBand=false;
 function slot(w,h){if(cursorX>abRight+100&&cursorX+w>maxRight){cursorX=abRight+100;cursorY-=rowHeight+100;rowHeight=0;}if(!usedTopBand&&cursorY-h<abBottom-2500){usedTopBand=true;cursorX=abLeft;cursorY=abTop+100+h;rowHeight=0;}var result=[cursorX,cursorY];cursorX+=w+100;rowHeight=Math.max(rowHeight,h);return result;}
 for(var n=0;n<c.panels.length;n++){
  var p=c.panels[n], w=p.output_cm[0],h=p.output_cm[1],pos=slot(w*cm,h*cm),x=pos[0],y=pos[1],layer=d.layers.add();stage='panel '+p.name;layer.name='PRINT_'+p.name;
  var ab=null;
  try{ab=d.artboards.add([x,y,x+w*cm,y-h*cm]);}catch(aoocErr){
   var cands=[[abRight+100+(n*(w*cm+100)),abTop],[abLeft+(n*(w*cm+100)),abTop],[abLeft,abTop+100+h*cm],[abLeft,abBottom-50],[0,h*cm/2]],lastErr=aoocErr;
   for(var ci=0;ci<cands.length;ci++){try{var cand=cands[ci];ab=d.artboards.add([cand[0],cand[1],cand[0]+w*cm,cand[1]-h*cm]);x=cand[0];y=cand[1];break;}catch(e2){lastErr=e2;}}
   if(!ab)throw lastErr;
  }
  ab.name='PRINT_'+p.name;
  var stripeHoles=[],frontReg=null,map={};for(var q=0;q<p.objects.length;q++)map[p.objects[q].id]=p.objects[q];
  if(p.special_kind){specialPart(p,layer,x,y,w,h,map);continue;}
  if(p.background_mode==='solid_cmyk'&&p.background_cmyk&&p.background_cmyk.length===4){var backgroundLayer=layer.layers.add();backgroundLayer.name="BACKGROUND_EDIT_COLOR";var r=backgroundLayer.pathItems.rectangle(y,x,w*cm,h*cm);r.filled=true;var bc=new CMYKColor();bc.cyan=Number(p.background_cmyk[0]);bc.magenta=Number(p.background_cmyk[1]);bc.yellow=Number(p.background_cmyk[2]);bc.black=Number(p.background_cmyk[3]);var bkey=[bc.cyan,bc.magenta,bc.yellow,bc.black].join('_');if(!bgSwatches[bkey]){var sp=d.spots.add();sp.name='CANAVI_SOLID_BG_'+n;sp.colorType=ColorModel.PROCESS;sp.color=bc;bgSwatches[bkey]=sp;}var linked=new SpotColor();linked.spot=bgSwatches[bkey];linked.tint=100;r.fillColor=linked;r.stroked=false;r.name='CUSTOM_CMYK_BACKGROUND';}else if(p.background_mode!=='none'&&p.background_mode!=='full_artboard_pattern'&&p.background_object_id&&(p.background_mode!=='registered_per_face'||(map[p.background_object_id]&&map[p.background_object_id].kind==='PathItem'))){var bg=find(map[p.background_object_id]);var backgroundLayer=layer.layers.add();backgroundLayer.name="BACKGROUND_EDIT_COLOR";if(p.background_mode==='continuous_stripes'){if(p.stripe_gap_cmyk&&!p.stripe_gap_evidence)fail('Missing stripe gap evidence');stripeHoles=continuousStripes(bg,backgroundLayer,x,y,w*cm,h*cm,p.stripe_gap_cmyk);}else if(bg.typename==='PathItem'){var rawCol=bg.filled?bg.fillColor:(bg.stroked?bg.strokeColor:null);if(!rawCol)fail('Background not original CMYK');if(rawCol.typename==='GradientColor'||rawCol.typename==='PatternColor'){var bgg=bg.duplicate(backgroundLayer,ElementPlacement.PLACEATEND);var bgb=bounds(bgg),bgw=bgb[2]-bgb[0],bgh=bgb[1]-bgb[3];if(bgw<=0||bgh<=0)fail('Empty gradient background');bgg.resize((w*cm/bgw)*100,(h*cm/bgh)*100,true,true,true,true,100,Transformation.TOPLEFT);var bgp=bounds(bgg);bgg.translate(x-bgp[0],y-bgp[1]);bgg.name='SOURCE_GRADIENT_BACKGROUND';}else{var bc=null;if(rawCol.typename==='CMYKColor'){bc=rawCol;}else if(rawCol.typename==='GrayColor'){bc=new CMYKColor();bc.cyan=0;bc.magenta=0;bc.yellow=0;bc.black=rawCol.gray;}else if(rawCol.typename==='SpotColor'&&rawCol.spot&&rawCol.spot.color){var sc=rawCol.spot.color;if(sc.typename==='CMYKColor'){var tt=(typeof rawCol.tint==='number'?rawCol.tint:100)/100;bc=new CMYKColor();bc.cyan=sc.cyan*tt;bc.magenta=sc.magenta*tt;bc.yellow=sc.yellow*tt;bc.black=sc.black*tt;}else if(sc.typename==='RGBColor'){var arr=app.convertSampleColor(ImageColorSpace.RGB,[sc.red,sc.green,sc.blue],ImageColorSpace.CMYK,ColorConvertPurpose.defaultpurpose);bc=new CMYKColor();bc.cyan=arr[0];bc.magenta=arr[1];bc.yellow=arr[2];bc.black=arr[3];}else if(sc.typename==='LABColor'||sc.typename==='LabColor'){var arr=app.convertSampleColor(ImageColorSpace.LAB,[sc.l,sc.a,sc.b],ImageColorSpace.CMYK,ColorConvertPurpose.defaultpurpose);bc=new CMYKColor();bc.cyan=arr[0];bc.magenta=arr[1];bc.yellow=arr[2];bc.black=arr[3];}}else if(rawCol.typename==='RGBColor'){var arr=app.convertSampleColor(ImageColorSpace.RGB,[rawCol.red,rawCol.green,rawCol.blue],ImageColorSpace.CMYK,ColorConvertPurpose.defaultpurpose);bc=new CMYKColor();bc.cyan=arr[0];bc.magenta=arr[1];bc.yellow=arr[2];bc.black=arr[3];}else if(rawCol.typename==='LABColor'||rawCol.typename==='LabColor'){var arr=app.convertSampleColor(ImageColorSpace.LAB,[rawCol.l,rawCol.a,rawCol.b],ImageColorSpace.CMYK,ColorConvertPurpose.defaultpurpose);bc=new CMYKColor();bc.cyan=arr[0];bc.magenta=arr[1];bc.yellow=arr[2];bc.black=arr[3];}if(!bc)fail('Background not original CMYK');var r=backgroundLayer.pathItems.rectangle(y,x,w*cm,h*cm);r.filled=true;var bkey=[bc.cyan,bc.magenta,bc.yellow,bc.black].join('_');if(!bgSwatches[bkey]){var sp=d.spots.add();sp.name='CANAVI_BG_'+n;sp.colorType=ColorModel.PROCESS;sp.color=bc;bgSwatches[bkey]=sp;}var linked=new SpotColor();linked.spot=bgSwatches[bkey];linked.tint=100;r.fillColor=linked;r.stroked=false;r.name='SOURCE_CMYK_BACKGROUND';}}else{var bgg=bg.duplicate(backgroundLayer,ElementPlacement.PLACEATEND);bgg=releaseClippingMasks(bgg);var bgb=bounds(bgg),bgw=bgb[2]-bgb[0],bgh=bgb[1]-bgb[3];if(bgw<=0||bgh<=0)fail('Empty background group');bgg.resize((w*cm/bgw)*100,(h*cm/bgh)*100,true,true,true,true,100,Transformation.TOPLEFT);var bgp=bounds(bgg);bgg.translate(x-bgp[0],y-bgp[1]);bgg.name='SOURCE_GROUP_BACKGROUND';}}
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
   var allowBleed=Boolean(a.preserve_source_bleed||p.clip_to_artboard||a.clip_to_artboard);
   if(!allowBleed&&(a.y_cm<0||top<-.001||top+visibleH*scale/cm>h+.001))fail('Artwork exceeds artboard height');
   if(!a.preserve_native_size)g.resize(scale*100,scale*100,true,true,true,true,scale*100,Transformation.TOPLEFT);
   if(a.rotation===180){g.rotate(180);if(crop)crop=[1-crop[2],1-crop[3],1-crop[0],1-crop[1]];}
   var placed=groupBounds(g);g.translate(x+a.x_cm*cm-(crop?g.width*crop[0]:0)-placed[0],y-top*cm+(crop?g.height*crop[1]:0)-placed[1]);g.name='ORIGINAL_ARTWORK_'+j;if(a.horizontal_alignment==='center'){var centered=groupBounds(g);g.translate(x+w*cm/2-(centered[0]+centered[2])/2,0);if(a._visual_center_dx_cm)g.translate(Number(a._visual_center_dx_cm)*cm,0);}if(a.side==='front'||(!frontReg&&j===0)){var pc=groupBounds(g);frontReg={sourceCenter:sourceCenter,placedCenter:[(pc[0]+pc[2])/2,(pc[1]+pc[3])/2],scale:scale,bgId:a.background_object_id||p.background_object_id};}if(stripeHoles.length)restoreStripeKnockouts(stripeHoles,gb,groupBounds(g),a.rotation,artworkLayer,a.horizontal_alignment==='center'?x+w*cm/2:null,typeof p.white_backing_extra_stripes==='number'?p.white_backing_extra_stripes:1);
   if(p.clip_to_artboard||a.clip_to_artboard){var artClip=artworkLayer.groupItems.add();g.move(artClip,ElementPlacement.PLACEATEND);var artMask=artClip.pathItems.rectangle(y,x,w*cm,h*cm);artMask.filled=false;artMask.stroked=false;artMask.clipping=true;artClip.clipped=true;artClip.name='CLIPPED_ARTWORK_'+j;}
   if(p.background_mode==='registered_per_face'&&a.background_object_id){
    var bl=layer.layers.add();bl.name='BACKGROUND_'+a.side;bl.zOrder(ZOrderMethod.SENDTOBACK);
    var bg=find(map[a.background_object_id]),dup=bg.duplicate(bl,ElementPlacement.PLACEATEND);dup=releaseClippingMasks(dup);var bb=bounds(dup);
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
  if(p.background_mode==='full_artboard_pattern'&&p.background_object_id){renderFullArtboardPattern(p,layer,x,y,w*cm,h*cm,map,frontReg);}
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

def _measure_visual_center_adjustments(target, panels, source_count):
 """Measure actual non-white ink bounds per centered component so transparent raster/vector padding doesn't skew centering."""
 changed = False
 with fitz.open(target) as doc:
  for n, p in enumerate(panels, source_count):
   if p.get('background_mode', 'none') != 'none':
    continue
   w, h = p['output_cm']
   page = doc[n]
   scale = min(1.0, 1000.0 / page.rect.width)
   pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
   im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
   pw, ph = im.size
   px = im.load()
   y_pad = int(round(1.15 / h * ph))
   joined = p.get('construction') == 'joined_two_faces'
   for a in p.get('components', []):
    if a.get('horizontal_alignment') != 'center':
     continue
    y0 = y_pad if not joined or a.get('vertical_anchor', 'top') == 'top' else ph // 2
    y1 = ph - y_pad if not joined or a.get('vertical_anchor', 'top') == 'bottom' else ph // 2
    xs = []
    for yy in range(max(y_pad, y0), min(ph - y_pad, y1)):
     for xx in range(pw):
      r, g, b = px[xx, yy]
      if r < 245 or g < 245 or b < 245:
       xs.append(xx)
    if not xs:
     continue
    left_cm = min(xs) / pw * w
    right_cm = (pw - 1 - max(xs)) / pw * w
    dx_cm = (right_cm - left_cm) / 2.0
    if abs(dx_cm) > 0.12:
     a['_visual_center_dx_cm'] = round(dx_cm, 4)
     changed = True
 return changed


def export(job,src,folder):
 if job['plan'].get('renderer')=='original_pdf_v1':
  from original_pdf_export import export as pdf_export
  return pdf_export(job,src,folder)
 if job['plan'].get('renderer')=='native_pattern_v1':
  from pattern_export import export as native_export
  return native_export(job,src,folder)
 if job['plan'].get('source_sha256') and job['plan']['source_sha256']!=sha(src):raise ValueError('Native plan/source mismatch')
 import copy
 panels=copy.deepcopy(job['plan']['panels']);icc=source_info(src,panels)
 with fitz.open(src) as original:source_count=len(original)
 target=folder/(job['plan']['order_code'].replace(' ','_')+'_EDITABLE.ai')
 config={'source':str(src).replace('\\','/'),'output':str(target).replace('\\','/'),'panels':panels,'source_count':source_count}
 from native_local import COMMON
 from jpg_special_jsx import JSX as SPECIAL_JSX
 def _run_jsx(cfg):
  (folder/'export.jsx').write_text((COMMON+JSX.replace(" var bgSwatches={}",SPECIAL_JSX+" var bgSwatches={}")).replace('__CONFIG__',json.dumps(cfg,ensure_ascii=True)),encoding='utf-8')
  command=__import__("adobe_ready").ready_command("Illustrator.Application","$ai")+"$s=[IO.File]::ReadAllText((Join-Path (Get-Location) 'export.jsx')); $ai.DoJavaScript($s)"
  from font_dialog_guard import FontDialogGuard
  from native_patterns import recover_illustrator_271
  with FontDialogGuard(folder):
   r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=360)
  if r.returncode and recover_illustrator_271(r):
   with FontDialogGuard(folder):
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=360)
  if r.returncode or r.stdout.decode(errors='replace').strip()!='verified':
   (folder/'illustrator-error.txt').write_bytes(r.stderr+r.stdout)
   raise ValueError('Illustrator chưa xác minh AI: '+r.stderr.decode(errors='replace')[:800])
 _run_jsx(config)
 if _measure_visual_center_adjustments(target, panels, source_count):
  _run_jsx(config)
 reports=[];previews=[];repeat_previews=[]
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
   if p.get('special_kind')=='pattern_meter':
    tw,th=p['tile_cm'];scale=min(2,600/(max(tw,th)*72/2.54))
    cell=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=fitz.Rect(0,0,min(tw,w)*72/2.54,th*72/2.54),colorspace=fitz.csRGB,alpha=False)
    # For periods wider than the web only the vertical seam occurs in this output.
    tile=Image.frombytes('RGB',(cell.width,cell.height),cell.samples)
    grid=Image.new('RGB',(tile.width*(2 if tw<=w else 1),tile.height*2))
    for xx in range(2 if tw<=w else 1):
     for yy in range(2):grid.paste(tile,(xx*tile.width,yy*tile.height))
    buf=io.BytesIO();grid.save(buf,format='PNG');repeat_previews.append({'mime_type':'image/png','data':base64.b64encode(buf.getvalue()).decode()})
   reports.append({'name':p['name'],'size_cm':p['output_cm'],'corner_marks':p['corner_marks'],'mode':'CMYK','dpi':300,'source_icc_preserved':bool(icc),'untagged_source':icc is None,'file':dest.name,'sha256':sha(dest)})
 return {'report':{'source_sha256':sha(src),'panels':reports,'native_ai_verified':True,'ai_file':target.name,'ai_sha256':sha(target),'icc_sha256':hashlib.sha256(icc).hexdigest() if icc else None,'archive_relative':job['archive_relative']},'previews':previews,'repeat_previews':repeat_previews}

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
   if src.stat().st_size>256*1024*1024 or sha(src)!=a['sha256']:raise ValueError('Source changed')
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
