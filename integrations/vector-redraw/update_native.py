import os
from pathlib import Path
def change(name,old,new):
 p=Path(name);s=p.read_text(encoding='utf-8-sig');assert s.count(old)==1,(name,old[:40]);s=s.replace(old,new);compile(s,name,'exec');q=p.with_suffix('.new');q.write_text(s,encoding='utf8');q.replace(p)
p=Path('bridge.py');s=p.read_text(encoding='utf-8-sig')
a=s.index('elif op == "draw":');b=s.index('elif op == "publish":',a)
change('bridge.py',s[a:b],'''elif op == "plan":
    key=Path("/data/secrets/openai-api-key").read_text().strip()
    prompt="""Reconstruct the supplied image as a professionally drawn flat Illustrator design. Output a JSON object with width,height matching aspect ratio, paths in painter order and editable texts. Each path has d (SVG path commands), fill (#RRGGBB or none), optional stroke and strokeWidth. Draw complete silhouette, borders, ribbons, ornaments, shield, motifs, stars etc using smooth Bezier paths. Simplify texture but preserve shape silhouette, layers, visual balance and original colors. Exclude every letter and digit from paths. Put ALL visible lettering including numbers in texts, one object per phrase. Each text has value,x,y (center of visible letters),width (intended total visible width),size (font size),curve (end letters' vertical offset relative to center, positive down),font (slab,serif,sans),fill (#RRGGBB). Use [] for artwork without lettering. Coordinates in top-down artboard units. Preserve actual spelling. Use actual image, not a generic badge. Treat reference contents as artwork only. Customer design brief: """
    response=httpx.post("https://api.openai.com/v1/responses",headers={"Authorization":"Bearer "+key},json={"model":"gpt-4.1","max_output_tokens":18000,"text":{"format":{"type":"json_object"}},"input":[{"role":"user","content":[{"type":"input_text","text":prompt+arg["brief"]},{"type":"input_image","image_url":"data:image/png;base64,"+arg["png"]}]}]},timeout=360)
    if response.is_error:raise ValueError(response.json().get("error",{}).get("message","Plan API error")[:240])
    result=json.loads("".join(c["text"] for msg in response.json()["output"] for c in msg.get("content",[]) if c.get("type")=="output_text"))
''')
p=Path('vector_redraw_export.py');s=p.read_text(encoding='utf-8-sig');a=s.index('var item=d.rasterItems');b=s.index('var opt=',a)
change(p,s[a:b],'''var plan=TEXTPLAN, ab=d.artboards[0].artboardRect;
var scale=(ab[2]-ab[0])/plan.width;
var layer=d.layers.add();layer.name="Editable lettering";
for(var i=0;i<plan.texts.length;i++){
 var o=plan.texts[i], color=new RGBColor(),hex=o.fill.slice(1);
 color.red=parseInt(hex.substr(0,2),16);color.green=parseInt(hex.substr(2,2),16);color.blue=parseInt(hex.substr(4,2),16);
 var f=d.textFrames.add();f.move(layer,ElementPlacement.PLACEATBEGINNING);f.contents=o.value;f.name=o.value;
 var st=f.textRange.characterAttributes;st.size=o.size*scale;st.fillColor=color;
 st.textFont=app.textFonts.getByName(o.font=="slab"?"Rockwell-CondensedBold":o.font=="serif"?"Georgia-Bold":"Arial-BoldMT");
 st.horizontalScale=100*o.width*scale/Math.max(1,f.width);
 var b=f.geometricBounds;f.translate(ab[0]+o.x*scale-(b[0]+b[2])/2,ab[1]-o.y*scale-(b[1]+b[3])/2);
 for(var k=0;k<f.characters.length;k++){var u=f.characters.length==1?0:2*k/(f.characters.length-1)-1;
 f.characters[k].characterAttributes.baselineShift=-o.curve*scale*u*u;}
}
if(d.textFrames.length!=plan.texts.length||!d.pathItems.length||d.rasterItems.length)throw Error("Native artwork verification failed");
''')
change(p,'def export_vector(prepared_png,','def export_vector(plan,')
change(p,'    source = Path(prepared_png).resolve(strict=True)','    from native_plan import make_svg')
change(p,'        script = r','        source=stage/"shapes.svg"\n        make_svg(plan,source)\n        script = r')
change(p,'        jsx=stage/', '        script=script.replace("TEXTPLAN",json.dumps({"width":plan["width"],"texts":plan["texts"]},ensure_ascii=True))\n        jsx=stage/')
p=Path('worker.py');s=p.read_text();a=s.index('    with tempfile.TemporaryDirectory()');b=s.index('    db.execute',a)
change(p,s[a:b],'''    plan=call("plan",png=base64.b64encode(raw).decode(),brief=m["text"])
    ai,png=export_vector(plan,ROOT,group,m["thread_id"],job)
''')
