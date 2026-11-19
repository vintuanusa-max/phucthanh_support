"""Export a prepared flat artwork preview as native Illustrator paths and PNG."""
from pathlib import Path
import json
import re
import subprocess
import tempfile

CANAVI_THREADS = {"g1790239230897256718", "g2671966061008128194"}

def export_vector(plan, archive_root, group, thread_id, job_id):
    if not thread_id or thread_id in CANAVI_THREADS or group.strip().upper() in {"CANAVI", "CANAVI HCM2"}:
        raise ValueError("Excluded or unknown group")
    root = Path(archive_root).resolve(strict=True)
    customer = (root / group).resolve(strict=True)
    if customer.parent != root or customer.name != group:
        raise ValueError("Invalid group archive")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", job_id):
        raise ValueError("Invalid job id")
    dest = (customer / "DESIGNER").resolve()
    if dest.parent != customer:
        raise ValueError("Invalid output folder")
    dest.mkdir(exist_ok=True)
    from native_plan import make_svg
    ai = dest / ("Mau-" + job_id + ".ai")
    png = ai.with_suffix(".png")
    if ai.exists() or png.exists():
        raise FileExistsError("Existing job output")
    with tempfile.TemporaryDirectory(dir=dest) as temp:
        stage = Path(temp)
        source=stage/"shapes.svg"
        make_svg(plan,source)
        script = r"""(function(){
var previous=app.userInteractionLevel, d;
try {
app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;
d=app.open(new File(INPUT));
var plan=TEXTPLAN, ab=d.artboards[0].artboardRect;
var scale=(ab[2]-ab[0])/plan.width;
var layer=d.layers.add();layer.name="Editable lettering";
for(var i=0;i<plan.texts.length;i++){
 var o=plan.texts[i], color=new RGBColor(),hex=o.fill.slice(1);
 color.red=parseInt(hex.substr(0,2),16);color.green=parseInt(hex.substr(2,2),16);color.blue=parseInt(hex.substr(4,2),16);
 if(o.arc){
 var group=layer.groupItems.add();group.name=o.value;
 var arr=[],sum=0;
 var fonts={"slab":"Rockwell-CondensedBold","serif":"Georgia-Bold","sans":"ArialMT","sans-bold":"Arial-BoldMT","script":"SegoeScript","mono":"CourierNewPSMT","italic":"Georgia-Italic"};
 var face;try{face=app.textFonts.getByName(fonts[o.font]||"ArialMT");}catch(err){face=app.textFonts.getByName("ArialMT");}
 for(var j=0;j<o.value.length;j++){var ch=group.textFrames.add();ch.contents=o.value[j];var cs=ch.textRange.characterAttributes;cs.size=o.size*scale;cs.fillColor=color;cs.textFont=face;if(o.stroke!="none"){var ec=new RGBColor();var edge=o.stroke.slice(1);ec.red=parseInt(edge.substr(0,2),16);ec.green=parseInt(edge.substr(2,2),16);ec.blue=parseInt(edge.substr(4,2),16);cs.strokeColor=ec;cs.strokeWeight=2.8*scale;}var advance=o.value[j]==" "?o.size*.32*scale:ch.width;arr.push([ch,advance]);sum+=advance;}
 var cursor=-o.width/2;
 for(var j=0;j<arr.length;j++){var ch=arr[j][0],advance=arr[j][1]/sum*o.width,dx=cursor+advance/2,u=2*dx/o.width;cursor+=advance;
 if(o.value[j]==" "){ch.remove();continue;} ch.resize(Math.min(100,100*advance*.88/Math.max(ch.width,1)),100);
 ch.textRange.characterAttributes.textFont=face;if(o.font=="slab"){ch.textRange.characterAttributes.strokeColor=color;ch.textRange.characterAttributes.strokeWeight=o.size*.029*scale;} ch.rotate(-Math.atan(4*o.curve*u/o.width)*180/Math.PI);
 var g=ch.duplicate().createOutline(),b=g.visibleBounds;g.remove();
 ch.translate(ab[0]+(o.x+dx)*scale-(b[0]+b[2])/2,ab[1]-(o.y+o.curve*u*u)*scale-(b[1]+b[3])/2);}
 if(o.angle)group.rotate(o.angle);continue;}
 var f=d.textFrames.add();f.move(layer,ElementPlacement.PLACEATBEGINNING);f.contents=o.value;f.name=o.value;
 var st=f.textRange.characterAttributes;st.size=o.size*scale;st.fillColor=color;
 st.textFont=app.textFonts.getByName(o.font=="slab"?"Rockwell-CondensedBold":o.font=="serif"?"Georgia-Bold":"Arial-BoldMT");
 // Measure visible glyphs while keeping the original type live.
 var probe=f.duplicate().createOutline();var box=probe.visibleBounds;probe.remove();
 f.resize(100*o.width*scale/Math.max(1,box[2]-box[0]),100*o.size*scale/Math.max(1,box[1]-box[3]));
 if(o.angle)f.rotate(o.angle);
 if(o.stroke && /^#[0-9a-f]{6}$/i.test(o.stroke)){var sc=new RGBColor(),v=o.stroke.slice(1);sc.red=parseInt(v.substr(0,2),16);sc.green=parseInt(v.substr(2,2),16);sc.blue=parseInt(v.substr(4,2),16);st.strokeColor=sc;st.strokeWeight=Math.max(.5,o.size*.023)*scale;}
 probe=f.duplicate().createOutline();box=probe.visibleBounds;probe.remove();
 f.translate(ab[0]+o.x*scale-(box[0]+box[2])/2,ab[1]-o.y*scale-(box[1]+box[3])/2);f.name=o.phrase+" / "+o.value;
}
if((plan.texts.length && !d.textFrames.length)||!d.pathItems.length||d.rasterItems.length)throw Error("Native artwork verification failed");
var opt=new IllustratorSaveOptions();opt.pdfCompatible=true;
d.saveAs(new File(AIFILE),opt);
var preview=new ExportOptionsPNG24();preview.artBoardClipping=true;
d.exportFile(new File(PNGFILE),ExportType.PNG24,preview);
}finally{if(d)d.close(SaveOptions.DONOTSAVECHANGES);app.userInteractionLevel=previous;}
})()"""
        for label, path in (("INPUT",source),("AIFILE",stage/ai.name),("PNGFILE",stage/png.name)):
            script=script.replace(label,json.dumps(path.as_posix()))
        script=script.replace("TEXTPLAN",json.dumps({"width":plan["width"],"texts":plan["texts"]},ensure_ascii=True))
        jsx=stage/"render.jsx"
        jsx.write_text(script,encoding="utf-8")
        command="$ErrorActionPreference='Stop'; $app=New-Object -ComObject Illustrator.Application; $app.DoJavaScriptFile($env:PT_REDRAW_JSX)"
        import os
        subprocess.run(["powershell","-NoProfile","-Command",command], env={**os.environ,"PT_REDRAW_JSX":str(jsx)},check=True,timeout=180)
        for target in (ai,png):
            if not (stage/target.name).stat().st_size:
                raise ValueError("Empty Illustrator export")
        (stage/ai.name).rename(ai)
        try:
            (stage/png.name).rename(png)
        except OSError:
            ai.unlink()
            raise
    return ai,png
