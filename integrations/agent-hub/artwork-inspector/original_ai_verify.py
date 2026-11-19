"""Verify a hash-bound AI copy against its PDF artboards before CMYK rendering."""
import json,hashlib
from pathlib import Path

SCAN=r'''(function(){var d=null,old=app.userInteractionLevel,prev=app.documents.length?app.activeDocument:null,rows=[];
try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;d=app.open(new File(__SOURCE__));
if(d.documentColorSpace!==DocumentColorSpace.CMYK)throw Error('AI must be CMYK');
if(d.placedItems.length)throw Error('Linked artwork needs embedding and review');
if(d.textFrames.length)throw Error('Live text requires font verification before export');
for(var i=0;i<d.artboards.length;i++)rows.push(d.artboards[i].artboardRect.join(','));
return rows.join('\n');
}finally{if(d)d.close(SaveOptions.DONOTSAVECHANGES);app.userInteractionLevel=old;if(prev){try{prev.activate();}catch(e){}}}})()'''

def verify_sizes(text,panels):
 rows=[[float(v) for v in x.split(',')] for x in text.strip().splitlines() if x.strip()]
 if len(rows)!=len(panels):raise ValueError('AI native artboards differ from PDF pages')
 for b,p in zip(rows,panels):
  if len(b)!=4:raise ValueError('Invalid AI artboard')
  sizes=[(b[2]-b[0])*2.54/72,(b[1]-b[3])*2.54/72]
  if any(abs(a-c)>.02 for a,c in zip(sizes,p['output_cm'])):raise ValueError('AI native artboard size differs from PDF preview')
 return rows

def verify(src,panels,folder):
 from native_patterns import jsx_run
 folder=Path(folder);native=folder/'native-source.ai'
 raw=Path(src).read_bytes();digest=hashlib.sha256(raw).hexdigest()
 if native.exists() and hashlib.sha256(native.read_bytes()).hexdigest()!=digest:raise ValueError('AI copy conflict')
 native.write_bytes(raw)
 text=jsx_run(SCAN.replace('__SOURCE__',json.dumps(str(native).replace('\\','/'))),folder)
 rows=verify_sizes(text,panels)
 if hashlib.sha256(native.read_bytes()).hexdigest()!=digest:raise ValueError('AI bytes changed during verification')
 return dict(source_sha256=digest,artboards=rows,mode='CMYK',linked_items=0,live_text_frames=0)
