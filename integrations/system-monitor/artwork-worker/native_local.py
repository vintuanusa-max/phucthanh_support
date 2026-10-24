"""Illustrator candidate groups and proportional native exports, source unchanged."""
import base64,hashlib,json
from pathlib import Path
from urllib.parse import unquote
from native_patterns import jsx_run
COMMON=r'''
function children(parent){var a=[],items=parent.pageItems;for(var i=0;i<items.length;i++)if(items[i].parent===parent)a.push(items[i]);return a;}
function texts(p){if(p.typename==='TextFrame')return 1;var n=0;if(p.typename==='GroupItem'){var a=children(p);for(var i=0;i<a.length;i++)n+=texts(a[i]);}return n;}
function bounds(p){if(p.typename==='GroupItem'&&p.clipped){var a=children(p);for(var i=0;i<a.length;i++)if(a[i].clipping)return a[i].geometricBounds;}return p.visibleBounds;}
function at(d,path){var a=path.split('.'),p=d.layers[Number(a[0])];for(var i=1;i<a.length;i++)p=children(p)[Number(a[i])];return p;}
function render(items,folder,name,width,dpi,saveAI){var d=items[0];while(d.typename!=='Document')d=d.parent;d.activate();var oldBoard=d.artboards.getActiveArtboardIndex(),visibility=[],layer=null,board=null,left=1e9,top=-1e9,right=-1e9,bottom=1e9;
try{for(var k=0;k<d.layers.length;k++)visibility.push([d.layers[k],d.layers[k].visible]);layer=d.layers.add();layer.name='TEMP_EXPORT_ONLY';var g=layer.groupItems.add();
for(var i=0;i<items.length;i++){var b=bounds(items[i]);left=Math.min(left,b[0]);top=Math.max(top,b[1]);right=Math.max(right,b[2]);bottom=Math.min(bottom,b[3]);items[i].duplicate(g,ElementPlacement.PLACEATEND);}
var w=right-left,h=top-bottom;if(w<=0||h<=0)throw Error('Empty artwork');var scale=width>0?width/w:1;
if(Math.abs(scale-1)>.000001){g.resize(scale*100,scale*100,true,true,true,true,scale*100,Transformation.TOPLEFT);var actual=g.visibleBounds;left=actual[0];top=actual[1];w*=scale;h*=scale;}
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
var name='candidate_'+count++;try{render([p],__FOLDER__,name,0,Math.min(96,720/Math.max(w,h)*72),false);}catch(err){var ef=new File(__FOLDER__+'/scan-error.txt');ef.open('w');ef.write(id+' '+p.typename+' '+w+'x'+h+' '+String(err));ef.close();throw err;}rows.push([id,p.typename,encodeURIComponent(p.name||''),b.join(','),name,texts(p)].join('\t'));
if(p.typename==='GroupItem'&&!p.clipped)walk(p,id,depth+1);}}
for(var k=0;k<d.layers.length;k++)if(d.layers[k].visible)walk(d.layers[k],String(k),0);
for(var bi=0;bi<d.artboards.length;bi++)rows.push('BOARD\t'+bi+'\t'+encodeURIComponent(d.artboards[bi].name)+'\t'+d.artboards[bi].artboardRect.join(','));var fonts=[];for(var f=0;f<app.textFonts.length;f++)fonts.push(encodeURIComponent(app.textFonts[f].name));return 'FONTS\t'+fonts.join(',')+'\nMETA\t'+(truncated?'1':'0')+'\n'+rows.join('\n');
}finally{try{if(d)d.close(SaveOptions.DONOTSAVECHANGES);}catch(ignore){}app.userInteractionLevel=old;if(prev){try{prev.activate();}catch(e){}}}})()'''
EXPORT=COMMON+r'''(function(){var d=null,old=app.userInteractionLevel,prev=app.documents.length?app.activeDocument:null;
try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;d=app.open(new File(__SOURCE__));if(d.placedItems.length)throw Error('Linked artwork');var specs=__ITEMS__,items=[];
for(var i=0;i<specs.length;i++){var p=at(d,specs[i].id),b=bounds(p);if(p.typename!==specs[i].kind)throw Error('Candidate changed');for(var j=0;j<4;j++)if(Math.abs(b[j]-specs[i].bounds[j])>.05)throw Error('Candidate bounds changed');items.push(p);}
return render(items,__FOLDER__,__NAME__,__WIDTH__,300,true).join(',');
}finally{try{if(d)d.close(SaveOptions.DONOTSAVECHANGES);}catch(ignore){}app.userInteractionLevel=old;if(prev){try{prev.activate();}catch(e){}}}})()'''
def quoted(path):return json.dumps(str(path).replace('\\','/'))
def source_copy(raw,name,folder):
 import pymupdf as fitz
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 digest=hashlib.sha256(raw).hexdigest()
 src=folder/('source.ai' if name.lower().endswith('.ai') else 'source.pdf')
 if src.exists() and src.read_bytes()!=raw:raise ValueError('Source collision')
 if not src.exists():src.write_bytes(raw)
 with fitz.open(src) as d:
  if len(d)!=1:raise ValueError('Native selection currently requires one PDF page; choose a single-page source')
 return src,digest
def inspect(raw,name,folder):
 folder=Path(folder);src,digest=source_copy(raw,name,folder);cache=folder/'candidates.json'
 if cache.exists():
  data=json.loads(cache.read_text());assert data['source_sha256']==digest;return data
 marker=folder/'scan.started'
 if marker.exists():raise ValueError('Previous native scan uncertain; inspect before retry')
 marker.write_text(digest)
 try:text=jsx_run(SCAN.replace('__SOURCE__',quoted(src)).replace('__FOLDER__',quoted(folder)),folder)
 except ValueError as exc:
  error=folder/'scan-error.txt'
  if error.exists():raise ValueError('Illustrator: '+error.read_text(errors='replace')[:900]) from exc
  raise
 rows=[];truncated=False;installed=[];boards=[]
 for line in text.splitlines():
  v=line.split('\t')
  if v[0]=='FONTS':installed=[unquote(x) for x in v[1].split(',')];continue
  if v[0]=='BOARD':
   b=[float(x) for x in v[3].split(',')];boards.append(dict(index=int(v[1]),name=unquote(v[2]),bounds=b,width_cm=(b[2]-b[0])*2.54/72,height_cm=(b[1]-b[3])*2.54/72));continue
  if v[0]=='META':truncated=v[1]=='1';continue
  if len(v)!=6:continue
  b=[float(x) for x in v[3].split(',')]
  rows.append(dict(id=v[0],kind=v[1],name=unquote(v[2]),live_text_count=int(v[5]),bounds=b,width_cm=(b[2]-b[0])*2.54/72,height_cm=(b[1]-b[3])*2.54/72,preview=base64.b64encode((folder/(v[4]+'.png')).read_bytes()).decode()))
 if not rows:raise ValueError('No native candidates')
 import pymupdf as fitz
 with fitz.open(src) as doc:fonts=sorted(set(f[3].split('+')[-1] for page in doc for f in page.get_fonts()))
 data=dict(scan_version=2,artboards=boards,source_sha256=digest,candidates=rows,truncated=truncated,source_fonts=fonts,missing_fonts=[f for f in fonts if f not in installed])
 with fitz.open(src) as doc:
  if len(boards)!=len(doc):raise ValueError('Không đối chiếu được artboard với trang PDF; cần kiểm tra nguồn')
  for board,page in zip(boards,doc):
   bw=board['bounds'][2]-board['bounds'][0];bh=board['bounds'][1]-board['bounds'][3]
   if abs(bw-page.rect.width)>1 or abs(bh-page.rect.height)>1:raise ValueError('Tọa độ artboard/PDF không khớp; không tự khoanh vùng')
   pix=page.get_pixmap(matrix=fitz.Matrix(1400/max(bw,bh),1400/max(bw,bh)),alpha=False)
   board['preview']=base64.b64encode(pix.tobytes('png')).decode()
 cache.write_text(json.dumps(data));return data
def export(raw,name,folder,candidates,ids,width_cm,output):
 folder=Path(folder);src,digest=source_copy(raw,name,folder)
 chosen=[c for c in candidates if c['id'] in ids]
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
 if marker.exists():raise ValueError('Previous native export uncertain; no automatic replay')
 marker.write_text(digest)
 code=EXPORT.replace('__SOURCE__',quoted(src)).replace('__FOLDER__',quoted(folder)).replace('__ITEMS__',json.dumps(chosen)).replace('__NAME__',json.dumps(output)).replace('__WIDTH__',str(width_cm*72/2.54))
 # Preview data is not needed in executable object descriptors.
 code=EXPORT.replace('__SOURCE__',quoted(src)).replace('__FOLDER__',quoted(folder)).replace('__ITEMS__',json.dumps([{k:c[k] for k in ('id','kind','bounds')} for c in chosen])).replace('__NAME__',json.dumps(output)).replace('__WIDTH__',str(width_cm*72/2.54))
 dims=[float(x) for x in jsx_run(code,folder).split(',')]
 from PIL import Image
 png=folder/(output+'.png')
 with Image.open(png) as im:im.save(folder/'normalized.png',dpi=(300,300))
 (folder/'normalized.png').replace(png)
 result={'width_cm':dims[0],'height_cm':dims[1],'png':str(png),'ai':None,'sha256':hashlib.sha256(png.read_bytes()).hexdigest()}
 done.write_text(json.dumps(result));return result
