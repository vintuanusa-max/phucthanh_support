"""Native PatternColor replication for validated, full-coverage CANAVI panels."""
import base64,hashlib,json
from pathlib import Path
from PIL import Image
from native_patterns import jsx_run

BUILD=r'''(function(){var c=__CONFIG__,d=null,old=app.userInteractionLevel,prev=app.documents.length?app.activeDocument:null,cm=72/2.54;
function fail(s){throw Error(s);}function same(a,b){for(var i=0;i<4;i++)if(Math.abs(a[i]-b[i])>.1)return false;return true;}
try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;if(new File(c.output).exists)fail('Existing AI');d=app.open(new File(c.source));if(d.documentColorSpace!==DocumentColorSpace.CMYK||d.artboards.length!==c.source_count)fail('Source artboards/CMYK mismatch');
var originals=[],refs={},backgrounds={};for(var n=0;n<d.artboards.length;n++)originals.push(d.artboards[n].artboardRect);
for(var n=0;n<c.objects.length;n++){var o=c.objects[n],p=d.pathItems[o.index];if(p.fillColor.typename!=='PatternColor'||p.fillColor.pattern.name!==o.pattern||!same(p.geometricBounds,o.native_bbox))fail('Native pattern mismatch');var pc=p.fillColor,mt=pc.matrix;if(Math.abs(mt.mValueA-1)>.00001||Math.abs(mt.mValueB)>.00001||Math.abs(mt.mValueC)>.00001||Math.abs(mt.mValueD-1)>.00001||Math.abs(pc.rotation)>.00001||Math.abs(pc.scaleFactor[0]-100)>.00001||Math.abs(pc.scaleFactor[1]-100)>.00001||pc.reflect)fail('Pattern transform not identity');refs[o.id]=p;var bg=null;for(var z=0;z<d.pathItems.length;z++){var q=d.pathItems[z];if(q===p||!q.filled||q.fillColor.typename!=='CMYKColor'||q.hidden||q.opacity!==100||!same(q.geometricBounds,o.native_bbox))continue;if(bg)fail('Ambiguous pattern background');bg=q;}if(bg)backgrounds[o.id]=bg.fillColor;}
function place(id,layer,x,y,w,h,rot,shift){var p=refs[id].duplicate(layer,ElementPlacement.PLACEATBEGINNING);p.stroked=false;p.resize(w*cm/p.width*100,h*cm/p.height*100,true,false,false,false,100,Transformation.TOPLEFT);if(rot)p.rotate(180,true,true,true,true,Transformation.CENTER);p.position=[x,y];if(shift){p.translate(shift[0],shift[1],false,false,false,true);}p.name=rot?'BACK_180_NATIVE_PATTERN':'NATIVE_PATTERN';}
var black=new CMYKColor();black.black=100;black.cyan=black.magenta=black.yellow=0;
for(var n=0;n<c.panels.length;n++){var a=c.panels[n],w=a.output_cm[0],h=a.output_cm[1],x=-7500,y=-a.pattern_index*3800-(a.kind==='meter_fabric'?a.bag_height_cm*cm+100:0),b=[x,y,x+w*cm,y-h*cm];if(b[0]<-16300||b[2]>16300||b[3]<-16300)fail('Canvas limit');
for(var z=0;z<originals.length;z++){var q=originals[z];if(b[0]<q[2]&&b[2]>q[0]&&b[1]>q[3]&&b[3]<q[1])fail('Source overlap');}
var layer=d.layers.add();layer.name='PRINT_'+a.name;var bg=layer.layers.add();bg.name='BACKGROUND_PATTERN_EDITABLE';d.artboards.add(b).name='PRINT_'+a.name;
if(backgrounds[a.front_id]){var r=bg.pathItems.rectangle(y,x,w*cm,h*cm);r.filled=true;r.fillColor=backgrounds[a.front_id];r.stroked=false;r.name='ORIGINAL_CMYK_BACKGROUND';}
if(a.kind==='meter_fabric'){place(a.front_id,bg,x,y,w,h,false);}else{place(a.front_id,bg,x,y,w,h/2,false);place(a.back_id,bg,x,y-h*cm/2,w,h/2,true,a.back_pattern_shift_pt);}
if(a.corner_marks){var corners=[[x,y,1,-1],[x+w*cm,y,-1,-1],[x,y-h*cm,1,1],[x+w*cm,y-h*cm,-1,1]];for(var k=0;k<4;k++){var v=corners[k],m=layer.pathItems.add();m.setEntirePath([[v[0]+v[2]*cm,v[1]],[v[0],v[1]],[v[0],v[1]+v[3]*cm]]);m.filled=false;m.stroked=true;m.strokeColor=black;m.strokeWidth=.72;m.name='L_1CM';}}
}
var opt=new IllustratorSaveOptions();opt.pdfCompatible=true;opt.embedICCProfile=true;d.saveAs(new File(c.output),opt);d.close(SaveOptions.DONOTSAVECHANGES);d=null;d=app.open(new File(c.output));if(d.artboards.length!==c.source_count+c.panels.length||d.documentColorSpace!==DocumentColorSpace.CMYK)fail('Saved AI invalid');return 'verified';
}finally{if(d)d.close(SaveOptions.DONOTSAVECHANGES);app.userInteractionLevel=old;if(prev){try{prev.activate();}catch(e){}}}})()'''

def export(job,src,folder):
    import pymupdf as fitz
    plan=job['plan'];folder=Path(folder);target=folder/(plan['order_code'].replace(' ','_')+'_EDITABLE.ai')
    from pattern_repeat import periods
    exact=periods(src);known={o['id']:o for o in plan['native_objects']}
    for panel in plan['panels']:
        if panel['kind']=='meter_fabric':
            proof=exact.get(known[panel['front_id']]['page'],{})
            if not proof or abs(panel['output_cm'][1]-proof['height_cm'])>1e-8:
                raise ValueError('Meter height does not match verified source period')
    with fitz.open(src) as d:
        count=len(d);profiles={hashlib.sha256(d.xref_stream(x)).hexdigest():d.xref_stream(x) for x in range(1,d.xref_length()) if d.xref_get_key(x,'N')[1]=='4' and d.xref_is_stream(x) and d.xref_stream(x)[36:40]==b'acsp'}
    if len(profiles)!=1:raise ValueError('Need unique source CMYK ICC')
    icc=next(iter(profiles.values()))
    config=dict(source=str(src).replace('\\','/'),output=str(target).replace('\\','/'),source_count=count,objects=plan['native_objects'],panels=plan['panels'])
    if jsx_run(BUILD.replace('__CONFIG__',json.dumps(config)),folder)!='verified':raise ValueError('Native pattern AI not verified')
    previews=[];reports=[]
    with fitz.open(target) as d:
        if len(d)!=count+len(plan['panels']):raise ValueError('Saved page count mismatch')
        for i,p in enumerate(plan['panels']):
            page=d[count+i];w,h=p['output_cm']
            if abs(page.rect.width*2.54/72-w)>.02 or abs(page.rect.height*2.54/72-h)>.02:raise ValueError('Output size mismatch')
            pix=page.get_pixmap(dpi=300,colorspace=fitz.csCMYK,alpha=False)
            name=plan['order_code'].replace(' ','_')+'_'+p['name']+'.jpg';out=folder/name
            Image.frombytes('CMYK',(pix.width,pix.height),pix.samples).save(out,quality=100,subsampling=0,dpi=(300,300),icc_profile=icc)
            with Image.open(out) as check:
                if check.mode!='CMYK' or check.info.get('icc_profile')!=icc:raise ValueError('CMYK ICC mismatch')
            scale=1100/max(page.rect.width,page.rect.height);preview=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB).tobytes('png');(folder/(p['name']+'_preview.png')).write_bytes(preview)
            previews.append(dict(mime_type='image/png',data=base64.b64encode(preview).decode()))
            reports.append(dict(name=p['name'],size_cm=p['output_cm'],corner_marks=p['corner_marks'],mode='CMYK',dpi=300,source_icc_preserved=True,file=name,sha256=hashlib.sha256(out.read_bytes()).hexdigest()))
    return dict(report=dict(source_sha256=hashlib.sha256(Path(src).read_bytes()).hexdigest(),panels=reports,native_ai_verified=True,ai_file=target.name,ai_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),icc_sha256=hashlib.sha256(icc).hexdigest(),archive_relative=job['archive_relative']),previews=previews)
