"""Illustrator candidate groups and proportional native exports, source unchanged."""
import base64,hashlib,json
from pathlib import Path
from urllib.parse import unquote
from native_patterns import jsx_run
COMMON=r'''
function children(parent){var a=[],items=parent.pageItems;for(var i=0;i<items.length;i++)if(items[i].parent===parent)a.push(items[i]);if(parent.typename==='Layer'){for(var j=0;j<parent.layers.length;j++){var sub=parent.layers[j];if(!sub.visible)continue;var nested=children(sub);for(var k=0;k<nested.length;k++)a.push(nested[k]);}}return a;}
function whiteBacking(p){
if(p.typename!=='PathItem'||!p.filled||p.stroked||p.clipping||p.opacity!==100)return false;
var f=p.fillColor;
// Allow rounding/profile residue, not cream or a colored fabric background.
if(f.typename==='CMYKColor')return Math.max(f.cyan,f.magenta,f.yellow,f.black)<=.5&&(f.cyan+f.magenta+f.yellow+f.black)<=1;
if(f.typename==='RGBColor')return Math.min(f.red,f.green,f.blue)>=254;
if(f.typename==='GrayColor')return f.gray<=.5;
return false;
}
function texts(p){if(p.typename==='TextFrame')return 1;var n=0;if(p.typename==='GroupItem'){var a=children(p);for(var i=0;i<a.length;i++)n+=texts(a[i]);}return n;}
function bounds(p){if(p.typename==='GroupItem'&&p.clipped){var a=children(p);for(var i=0;i<a.length;i++)if(a[i].clipping)return a[i].geometricBounds;}return p.visibleBounds;}
function groupBounds(g){var a=children(g),l=1e9,t=-1e9,r=-1e9,b=1e9;for(var i=0;i<a.length;i++){var c=bounds(a[i]);l=Math.min(l,c[0]);t=Math.max(t,c[1]);r=Math.max(r,c[2]);b=Math.min(b,c[3]);}return a.length?[l,t,r,b]:g.visibleBounds;}
function pageClipContainer(p,d){if(p.typename!=='GroupItem'||!p.clipped)return false;var q=bounds(p),area=(q[2]-q[0])*(q[1]-q[3]);for(var i=0;i<d.artboards.length;i++){var b=d.artboards[i].artboardRect,ba=(b[2]-b[0])*(b[1]-b[3]),overlap=Math.max(0,Math.min(q[2],b[2])-Math.max(q[0],b[0]))*Math.max(0,Math.min(q[1],b[1])-Math.max(q[3],b[3]));if(area>=ba*.9&&area<=ba*1.1&&overlap>=ba*.95)return true;}return false;}
// Source IDs are resolved before any layer/object mutation. Cache only this read phase.
var atDocument=null,atLists={};
function at(d,path){if(atDocument!==d){atDocument=d;atLists={};}var a=path.split('.'),p=d.layers[Number(a[0])],prefix=a[0];for(var i=1;i<a.length;i++){if(!atLists.hasOwnProperty(prefix))atLists[prefix]=children(p);p=atLists[prefix][Number(a[i])];prefix+='.'+a[i];}return p;}
function render(items,folder,name,width,dpi,saveAI){var d=items[0];while(d.typename!=='Document')d=d.parent;d.activate();var oldBoard=d.artboards.getActiveArtboardIndex(),visibility=[],layer=null,board=null,left=1e9,top=-1e9,right=-1e9,bottom=1e9;
try{for(var k=0;k<d.layers.length;k++)visibility.push([d.layers[k],d.layers[k].visible]);layer=d.layers.add();layer.name='TEMP_EXPORT_ONLY';var g=layer.groupItems.add();
for(var i=0;i<items.length;i++){var b=bounds(items[i]);left=Math.min(left,b[0]);top=Math.max(top,b[1]);right=Math.max(right,b[2]);bottom=Math.min(bottom,b[3]);items[i].duplicate(g,ElementPlacement.PLACEATEND);}
var w=right-left,h=top-bottom;if(w<=0||h<=0)throw Error('Empty artwork');var scale=width>0?width/w:1;
if(Math.abs(scale-1)>.000001){g.resize(scale*100,scale*100,true,true,true,true,scale*100,Transformation.TOPLEFT);var actual=groupBounds(g);left=actual[0];top=actual[1];w=actual[2]-actual[0];h=actual[1]-actual[3];}
for(var k=0;k<visibility.length;k++)visibility[k][0].visible=false;layer.visible=true;
board=d.artboards.add([left,top,left+Math.max(w,1),top-Math.max(h,1)]);d.artboards.setActiveArtboardIndex(d.artboards.length-1);
var o=new ExportOptionsPNG24();o.transparency=true;o.artBoardClipping=true;o.antiAliasing=true;o.horizontalScale=dpi/72*100;o.verticalScale=dpi/72*100;d.exportFile(new File(folder+'/'+name+'.png'),ExportType.PNG24,o);
return [w*2.54/72,h*2.54/72];
}finally{if(board)try{board.remove();}catch(e){}if(layer)try{layer.remove();}catch(e){}for(var k=0;k<visibility.length;k++)try{visibility[k][0].visible=visibility[k][1];}catch(e){}d.artboards.setActiveArtboardIndex(oldBoard);}}

'''
SCAN=COMMON+r'''(function(){var d=null,prev=app.documents.length?app.activeDocument:null,old=app.userInteractionLevel,rows=[],count=0,truncated=false;
try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;d=app.open(new File(__SOURCE__));
if(d.placedItems.length)throw Error('Linked images must be embedded');
function walk(parent,path,depth){var a=children(parent);for(var i=0;i<a.length;i++){var p=a[i],id=path+'.'+i;if(p.hidden||p.guides)continue;var b=bounds(p),w=b[2]-b[0],h=b[1]-b[3];if(w<=0||h<=0)continue;
var keep=(depth===0&&d.artboards.length===1)||p.typename==='GroupItem'||p.typename==='RasterItem'||p.typename==='CompoundPathItem'||(p.typename==='PathItem'&&w>30&&h>30);if(depth>4||!keep||(depth>0&&w<=5&&h<=5))continue;var name='candidate_'+count++;try{render([p],__FOLDER__,name,0,Math.min(96,720/Math.max(w,h)*72),false);}catch(err){var ef=new File(__FOLDER__+'/scan-error.txt');ef.open('w');ef.write(id+' '+p.typename+' '+w+'x'+h+' '+String(err));ef.close();throw err;}var dc=[],white=false;if(p.typename==='GroupItem'){var cc=children(p);for(var ci=0;ci<cc.length;ci++)dc.push(id+'.'+ci);}white=whiteBacking(p);rows.push([id,p.typename,encodeURIComponent(p.name||''),b.join(','),name,texts(p),dc.join(','),white?'1':'0'].join('\t'));
if(p.typename==='GroupItem'&&(!p.clipped||pageClipContainer(p,d)))walk(p,id,depth+1);}}
function noteMetadata(parent,path){var a=children(parent);for(var j=0;j<a.length;j++){var q=a[j],id=path+'.'+j;if(q.hidden||q.guides)continue;
if(q.typename==='TextFrame'||q.name==='Manual Dimension'){var b=bounds(q);rows.push(['NOTE',id,q.typename,encodeURIComponent(q.name||''),b.join(','),encodeURIComponent(q.typename==='TextFrame'?q.contents:'')].join('\t'));}
if(q.typename==='GroupItem')noteMetadata(q,id);}}
for(var k=0;k<d.layers.length;k++)if(d.layers[k].visible)noteMetadata(d.layers[k],String(k));
for(var k=0;k<d.layers.length;k++)if(d.layers[k].visible)walk(d.layers[k],String(k),0);
for(var bi=0;bi<d.artboards.length;bi++)rows.push('BOARD\t'+bi+'\t'+encodeURIComponent(d.artboards[bi].name)+'\t'+d.artboards[bi].artboardRect.join(','));var fonts=[];for(var f=0;f<app.textFonts.length;f++)fonts.push(encodeURIComponent(app.textFonts[f].name));return 'FONTS\t'+fonts.join(',')+'\nMETA\t'+(truncated?'1':'0')+'\n'+rows.join('\n');
}finally{try{if(d)d.close(SaveOptions.DONOTSAVECHANGES);}catch(ignore){}app.userInteractionLevel=old;if(prev){try{prev.activate();}catch(e){}}}})()'''
EXPORT=COMMON+r'''(function(){var d=null,old=app.userInteractionLevel,prev=app.documents.length?app.activeDocument:null;
try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;d=app.open(new File(__SOURCE__));if(d.placedItems.length)throw Error('Linked artwork');var specs=__ITEMS__,items=[];
for(var i=0;i<specs.length;i++){var p=at(d,specs[i].id),b=bounds(p);if(p.typename!==specs[i].kind)throw Error('Candidate changed');for(var j=0;j<4;j++)if(Math.abs(b[j]-specs[i].bounds[j])>.05)throw Error('Candidate bounds changed');items.push(p);}
var dims=render(items,__FOLDER__,__NAME__,__WIDTH__,300,__SAVE_AI__);
if(__SAVE_AI__){
var layer=d.layers.add();layer.name='PRINT_ARTWORK_EDITABLE';var g=layer.groupItems.add();
for(var i=0;i<items.length;i++)items[i].duplicate(g,ElementPlacement.PLACEATEND);
var b=groupBounds(g),ratio=__WIDTH__/(b[2]-b[0]);g.resize(ratio*100,ratio*100,true,true,true,true,ratio*100,Transformation.TOPLEFT);
var edge=-1e9,top=-1e9;for(var ai=0;ai<d.artboards.length;ai++){var ab=d.artboards[ai].artboardRect;edge=Math.max(edge,ab[2]);top=Math.max(top,ab[1]);}
var all=d.visibleBounds;edge=Math.max(edge,all[2]);b=groupBounds(g);
g.translate(edge+72-b[0],top-b[1]);b=groupBounds(g);
var added=d.artboards.add(b);added.name='PRINT_ARTWORK_'+__NAME__;d.artboards.setActiveArtboardIndex(d.artboards.length-1);
var opt=new IllustratorSaveOptions();opt.pdfCompatible=true;
d.saveAs(new File(__FOLDER__+'/'+__NAME__+'_editable.ai'),opt);
}
return dims.join(',');
}finally{try{if(d)d.close(SaveOptions.DONOTSAVECHANGES);}catch(ignore){}app.userInteractionLevel=old;if(prev){try{prev.activate();}catch(e){}}}})()'''
def quoted(path):return json.dumps(str(path).replace('\\','/'))
EXPORT_COMBINED_AI=COMMON+r'''(function(){var d=null,prev=app.documents.length?app.activeDocument:null,old=app.userInteractionLevel;try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;d=app.open(new File(__SOURCE__));
var specs=__FACES__,sourceBoardCount=d.artboards.length;var edge=-1e9,top=-1e9;
for(var ai=0;ai<d.artboards.length;ai++){var ab=d.artboards[ai].artboardRect;edge=Math.max(edge,ab[2]);top=Math.max(top,ab[1]);}
var all=d.visibleBounds;edge=Math.max(edge,all[2]);
// Resolve source IDs before inserting a layer, which shifts d.layers indices.
var resolved=[];for(var ri=0;ri<specs.length;ri++){var sourceItems=[];for(var rj=0;rj<specs[ri].items.length;rj++){var itemSpec=specs[ri].items[rj],sourceItem=at(d,itemSpec.id),sourceBounds=bounds(sourceItem);if(sourceItem.typename!==itemSpec.kind)throw Error('Candidate changed');for(var bi=0;bi<4;bi++)if(Math.abs(sourceBounds[bi]-itemSpec.bounds[bi])>.05)throw Error('Candidate bounds changed');sourceItems.push(sourceItem);}resolved.push(sourceItems);}
var layer=d.layers.add();layer.name='PRINT_ARTWORK_EDITABLE';
for(var fi=0;fi<specs.length;fi++){
var spec=specs[fi],items=resolved[fi];
var g=layer.groupItems.add();g.name="PRINT_ARTWORK_"+spec.side;
for(var i=0;i<items.length;i++)items[i].duplicate(g,ElementPlacement.PLACEATEND);
var b=groupBounds(g),ratio=spec.width_pt/(b[2]-b[0]);
g.resize(ratio*100,ratio*100,true,true,true,true,ratio*100,Transformation.TOPLEFT);
b=groupBounds(g);g.translate(edge+72-b[0],top-b[1]);b=groupBounds(g);
var added=d.artboards.add(b);added.name='PRINT_ARTWORK_'+spec.side;edge=Math.max(edge,b[2]);
}
if(d.artboards.length!==sourceBoardCount+specs.length)throw Error('Combined editable artboard count mismatch');
d.artboards.setActiveArtboardIndex(d.artboards.length-1);
var opt=new IllustratorSaveOptions();opt.pdfCompatible=true;
d.saveAs(new File(__FOLDER__+'/'+__NAME__+'_editable.ai'),opt);
return 'ok';
}finally{try{if(d)d.close(SaveOptions.DONOTSAVECHANGES);}catch(ignore){}app.userInteractionLevel=old;if(prev){try{prev.activate();}catch(e){}}}})()'''
def source_copy(raw,name,folder,allow_multi=False):
 import pymupdf as fitz
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 digest=hashlib.sha256(raw).hexdigest()
 src=folder/('source.ai' if name.lower().endswith('.ai') else 'source.pdf')
 if src.exists() and src.read_bytes()!=raw:raise ValueError('Source collision')
 if not src.exists():src.write_bytes(raw)
 with fitz.open(src) as d:
  if not 1<=len(d)<=40 or (len(d)!=1 and not allow_multi):raise ValueError('Native source page count not supported for this operation')
 return src,digest
def reimport_pdf_pages(src, folder):
 """Discard broken Illustrator private edit data, retain validated PDF page content."""
 import pymupdf as fitz
 src=Path(src)
 if src.suffix.lower()!='.pdf':raise ValueError('PDF reimport requires PDF source')
 target=Path(folder)/'source-pages.pdf'
 with fitz.open(src) as original:
  rebuilt=fitz.open(stream=src.read_bytes(),filetype='pdf')
  for page in rebuilt:
   rebuilt.xref_set_key(page.xref,'PieceInfo','null')
   kind,unit_value=rebuilt.xref_get_key(page.xref,'UserUnit')
   unit=float(unit_value) if kind in ('int','float') else 1.0
   if unit!=1:
    if list(page.annots() or []):raise ValueError('PDF UserUnit annotations need review')
    stream=b'q '+str(unit).encode()+b' 0 0 '+str(unit).encode()+b' 0 0 cm\n'+b'\n'.join(rebuilt.xref_stream(x) for x in page.get_contents())+b'\nQ'
    xref=rebuilt.get_new_xref();rebuilt.update_object(xref,'<<>>');rebuilt.update_stream(xref,stream);page.set_contents(xref)
    for key in ('MediaBox','CropBox','BleedBox','TrimBox','ArtBox'):
     typ,value=rebuilt.xref_get_key(page.xref,key)
     if typ=='array':
      values=[float(v)*unit for v in value.strip('[]').split()]
      rebuilt.xref_set_key(page.xref,key,'['+' '.join(format(v,'.12g') for v in values)+']')
    rebuilt.xref_set_key(page.xref,'UserUnit','1')
  rebuilt.xref_set_key(rebuilt.pdf_catalog(),'PieceInfo','null')
  try:
   for a,b in zip(original,rebuilt):
    if a.rect!=b.rect or a.rotation!=b.rotation:raise ValueError('PDF reimport geometry mismatch')
    matrix=fitz.Matrix(min(1,1600/max(a.rect.width,a.rect.height)),min(1,1600/max(a.rect.width,a.rect.height)))
    x=a.get_pixmap(matrix=matrix,alpha=True);y=b.get_pixmap(matrix=matrix,alpha=True)
    if (x.width,x.height,x.n,x.samples)!=(y.width,y.height,y.n,y.samples):raise ValueError('PDF reimport appearance mismatch')
   # Rebuild on each job: candidate identity is validated again by kind/bounds at export.
   if target.exists():target.unlink()
   rebuilt.save(target,garbage=4,deflate=True)
  finally:rebuilt.close()
 return target

def selected_source(src,folder,candidates):
 flags={bool(c.get('pdf_page_reimport')) for c in candidates}
 if len(flags)>1:raise ValueError('Mixed native source representations')
 return reimport_pdf_pages(src,folder) if flags=={True} else src

def refresh_white_metadata(data, src, folder, cache):
 # Cached image renders stay valid: refresh only native fill metadata once.
 if data.get('white_backing_version') == 2:return data
 ids=[c['id'] for c in data['candidates'] if c.get('kind')=='PathItem']
 code=COMMON+r"""(function(){var d=null,old=app.userInteractionLevel,prev=app.documents.length?app.activeDocument:null;try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;d=app.open(new File(__SOURCE__));var ids=__IDS__,out=[];for(var i=0;i<ids.length;i++)if(whiteBacking(at(d,ids[i])))out.push(ids[i]);return out.join('\n');}finally{if(d)d.close(SaveOptions.DONOTSAVECHANGES);app.userInteractionLevel=old;if(prev)try{prev.activate();}catch(e){}}})()"""
 found=set(jsx_run(code.replace('__SOURCE__',quoted(src)).replace('__IDS__',json.dumps(ids)),folder).splitlines()) if ids else set()
 for c in data['candidates']:
  if c.get('kind')=='PathItem':c['verified_white_fill']=c['id'] in found
 data['white_backing_version']=2
 cache.write_text(json.dumps(data),encoding='utf-8')
 return data

def inspect(raw,name,folder,allow_pdf_reimport=False):
 folder=Path(folder);src,digest=source_copy(raw,name,folder,allow_multi=True);cache=folder/'candidates.json'
 if cache.exists():
  data=json.loads(cache.read_text());assert data['source_sha256']==digest
  if data.get('scan_version',0)>=5:return refresh_white_metadata(data,selected_source(src,folder,data['candidates']),folder,cache)
 shared=Path(__file__).parent/'jpg-native-inspection'/digest/'candidates.json'
 if shared.exists() and shared!=cache:
  data=json.loads(shared.read_text());assert data['source_sha256']==digest
  if data.get('scan_version',0)>=5:
   cache.write_text(json.dumps(data));return refresh_white_metadata(data,selected_source(src,folder,data['candidates']),folder,cache)
 marker=folder/'scan.started'
 marker.unlink(missing_ok=True)
 marker.write_text(digest)
 reimported=False
 try:
  try:text=jsx_run(SCAN.replace('__SOURCE__',quoted(src)).replace('__FOLDER__',quoted(folder)),folder)
  except ValueError as exc:
   if not allow_pdf_reimport or src.suffix.lower()!='.pdf' or 'must be embedded' not in str(exc):raise
   src=reimport_pdf_pages(src,folder);reimported=True
   text=jsx_run(SCAN.replace('__SOURCE__',quoted(src)).replace('__FOLDER__',quoted(folder)),folder)
 except ValueError as exc:
  error=folder/'scan-error.txt'
  if error.exists():raise ValueError('Illustrator: '+error.read_text(errors='replace')[:900]) from exc
  raise
 finally:
  marker.unlink(missing_ok=True)
 rows=[];truncated=False;installed=[];boards=[];annotations=[]
 for line in text.splitlines():
  v=line.split('\t')
  if v[0]=='NOTE':
   annotations.append(dict(id=v[1],kind=v[2],name=unquote(v[3]),bounds=[float(x) for x in v[4].split(',')],text=unquote(v[5])))
   continue
  if v[0]=='FONTS':installed=[unquote(x) for x in v[1].split(',')];continue
  if v[0]=='BOARD':
   b=[float(x) for x in v[3].split(',')];boards.append(dict(index=int(v[1]),name=unquote(v[2]),bounds=b,width_cm=(b[2]-b[0])*2.54/72,height_cm=(b[1]-b[3])*2.54/72));continue
  if v[0]=='META':truncated=v[1]=='1';continue
  if len(v) not in (6,8):continue
  b=[float(x) for x in v[3].split(',')]
  rows.append(dict(id=v[0],kind=v[1],name=unquote(v[2]),live_text_count=int(v[5]),bounds=b,width_cm=(b[2]-b[0])*2.54/72,height_cm=(b[1]-b[3])*2.54/72,preview=base64.b64encode((folder/(v[4]+'.png')).read_bytes()).decode()))
  if len(v)>7:
   rows[-1]['direct_child_ids']=v[6].split(',') if v[6] else []
   rows[-1]['verified_white_fill']=v[7]=='1'
 if reimported:
  for row in rows:row['pdf_page_reimport']=True
 if not rows:raise ValueError('No native candidates')
 import pymupdf as fitz
 with fitz.open(src) as doc:fonts=sorted(set(f[3].split('+')[-1] for page in doc for f in page.get_fonts()))
 data=dict(scan_version=5,white_backing_version=2,annotations=annotations,artboards=boards,source_sha256=digest,candidates=rows,truncated=truncated,source_fonts=fonts,missing_fonts=[f for f in fonts if f not in installed])
 with fitz.open(src) as doc:
  if len(boards)!=len(doc):raise ValueError('Không đối chiếu được artboard với trang PDF; cần kiểm tra nguồn')
  for board,page in zip(boards,doc):
   bw=board['bounds'][2]-board['bounds'][0];bh=board['bounds'][1]-board['bounds'][3]
   clip=None
   if abs(bw-page.rect.width)>1 or abs(bh-page.rect.height)>1:
    # AI's PDF may include bleed; use an explicit matching trim/art box only.
    if page.rotation==0:
     for box in (page.trimbox,page.artbox):
      if abs(bw-box.width)<=1 and abs(bh-box.height)<=1 and page.rect.contains(box):
       clip=box;break
    if clip is None:raise ValueError('Tọa độ artboard/PDF không khớp; không tự khoanh vùng')
    board['preview_pdf_box']=list(clip)
   pix=page.get_pixmap(matrix=fitz.Matrix(1400/max(bw,bh),1400/max(bw,bh)),clip=clip,alpha=False)
   board['preview']=base64.b64encode(pix.tobytes('png')).decode()
 cache.write_text(json.dumps(data));return data
def export(raw,name,folder,candidates,ids,width_cm,output,save_ai=True):
 folder=Path(folder);src,digest=source_copy(raw,name,folder,allow_multi=True)
 chosen=[c for c in candidates if c['id'] in ids]
 src=selected_source(src,folder,chosen)
 if len(chosen)!=len(ids) or not chosen:raise ValueError('Unknown candidate')
 if any(a!=b and b.startswith(a+'.') for a in ids for b in ids):raise ValueError('Cannot select a group and its child together')
 if not 0.1<=width_cm<=160:raise ValueError('Invalid width')
 if not output.replace('_','').isalnum():raise ValueError('Invalid output name')
 marker=folder/(output+'.started')
 done=folder/(output+'.verified.json')
 if done.exists():
  result=json.loads(done.read_text());png=Path(result['png'])
  if hashlib.sha256(png.read_bytes()).hexdigest()!=result['sha256']:raise ValueError('Saved PNG changed')
  return result
 marker.unlink(missing_ok=True)
 marker.write_text(digest)
 try:
  code=EXPORT.replace('__SOURCE__',quoted(src)).replace('__FOLDER__',quoted(folder)).replace('__ITEMS__',json.dumps(chosen)).replace('__NAME__',json.dumps(output)).replace('__WIDTH__',str(width_cm*72/2.54))
  # Preview data is not needed in executable object descriptors.
  code=EXPORT.replace('__SOURCE__',quoted(src)).replace('__FOLDER__',quoted(folder)).replace('__ITEMS__',json.dumps([{k:c[k] for k in ('id','kind','bounds')} for c in chosen])).replace('__NAME__',json.dumps(output)).replace('__WIDTH__',str(width_cm*72/2.54)).replace('__SAVE_AI__','true' if save_ai else 'false')
  dims=[float(x) for x in jsx_run(code,folder).split(',')]
  from PIL import Image
  png=folder/(output+'.png')
  with Image.open(png) as im:im.save(folder/'normalized.png',dpi=(300,300))
  (folder/'normalized.png').replace(png)
  ai=folder/(output+'_editable.ai')
  if save_ai and not ai.is_file():raise ValueError('Editable AI was not saved')
  result={'width_cm':dims[0],'height_cm':dims[1],'png':str(png),'ai':str(ai) if save_ai else '','sha256':hashlib.sha256(png.read_bytes()).hexdigest()}
  done.write_text(json.dumps(result));return result
 finally:
  marker.unlink(missing_ok=True)
def export_combined_ai(raw,name,folder,faces,output='combined'):
 folder=Path(folder);src,digest=source_copy(raw,name,folder,allow_multi=True)
 src=selected_source(src,folder,[c for f in faces for c in f['candidates'] if c['id'] in f['candidate_ids']])
 if not output.replace('_','').isalnum():raise ValueError('Invalid output name')
 specs=[]
 for f in faces:
  ids=f['candidate_ids'];chosen=[c for c in f['candidates'] if c['id'] in ids]
  if len(chosen)!=len(ids) or not chosen:raise ValueError('Unknown candidate')
  if not 0.1<=f['width_cm']<=160:raise ValueError('Invalid width')
  specs.append({'side':str(f['side']),'items':[{k:c[k] for k in ('id','kind','bounds')} for c in chosen],'width_pt':f['width_cm']*72/2.54})
 ai=folder/(output+'_editable.ai')
 if not ai.is_file():
  code=EXPORT_COMBINED_AI.replace('__SOURCE__',quoted(src)).replace('__FOLDER__',quoted(folder)).replace('__FACES__',json.dumps(specs)).replace('__NAME__',json.dumps(output))
  jsx_run(code,folder)
 if not ai.is_file():raise ValueError('Combined editable AI was not saved')
 import pymupdf as fitz
 with fitz.open(src) as original, fitz.open(ai) as combined:
  if len(combined)!=len(original)+len(specs):raise ValueError('Combined editable AI must retain source artboards and add every print face')
 return ai


def inspect_solid_fills(raw,name,folder,scan):
 """Read real CMYK fill metadata; PDF rectangles may only be outlines."""
 folder=Path(folder);src,digest=source_copy(raw,name,folder,allow_multi=True)
 if scan['source_sha256']!=digest:raise ValueError('Fill/source mismatch')
 src=selected_source(src,folder,scan['candidates'])
 cache=folder/'solid-fills.json'
 if cache.exists():fills=json.loads(cache.read_text())
 else:
  code=COMMON+r'''(function(){var d=null,prev=app.documents.length?app.activeDocument:null,old=app.userInteractionLevel;try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;d=app.open(new File(__SOURCE__));var ids=__IDS__,out=[];for(var i=0;i<ids.length;i++){var p=at(d,ids[i]);if(p.typename==='PathItem'&&p.filled&&!p.clipping&&p.fillColor.typename==='CMYKColor')out.push(ids[i]);}return out.join('\n');}finally{if(d)d.close(SaveOptions.DONOTSAVECHANGES);app.userInteractionLevel=old;if(prev)try{prev.activate();}catch(e){}}})()'''
  code=code.replace('__SOURCE__',quoted(src)).replace('__IDS__',json.dumps([c['id'] for c in scan['candidates'] if c['kind']=='PathItem']))
  fills=jsx_run(code,folder).splitlines();cache.write_text(json.dumps(fills),encoding='utf-8')
 for c in scan['candidates']:c['solid_cmyk_fill']=c['id'] in fills
 return scan
