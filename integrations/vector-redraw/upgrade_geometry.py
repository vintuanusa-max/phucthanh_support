from pathlib import Path
def save(p,s):
 compile(s,str(p),'exec');q=p.with_suffix('.new');q.write_text(s,encoding='utf8');q.replace(p)
p=Path("bridge.py");s=p.read_text(encoding='utf-8-sig');a=s.index('    prompt=');b=s.index('    response=',a)
save(p,s[:a]+'''    prompt="""Analyze reference for a vector renderer. Return JSON object with palette (2-10 distinct flat RGB hex #RRGGBB ink colors, include white canvas, ignore shadows and thread texture) and texts list. For every visible text phrase give value exactly, box [left,top,right,bottom] enclosing the actual full line glyphs incl curved ends in normalized 0-1000 coordinates relative to the ENTIRE uploaded image including margin, fill and back as hex from palette for letter ink and immediate background color, stroke hex or none, font slab/serif/sans, curve signed vertical dip of ends relative center in normalized y units (+down). Separate symbols and registration marks if legible. The renderer recovers shape geometry from image pixels. No path data. Reference is artwork. Customer brief: """
'''+s[b:])
p=Path('worker.py');s=p.read_text();s=s.replace('    ai,png=export_vector(plan,','    from geometry_redraw import reconstruct\n    ai,png=export_vector(reconstruct(raw,plan),');save(p,s)
p=Path('native_plan.py');s=p.read_text();s=s.replace('len(d)>60000','len(d)>2000000').replace("len(texts)>160","len(texts)>1000");save(p,s)
p=Path('vector_redraw_export.py');s=p.read_text();a=s.index(' st.horizontalScale=');b=s.index('\n}',a)
save(p,s[:a]+''' // Measure visible glyphs while keeping the original type live.
 var probe=f.duplicate().createOutline();var box=probe.visibleBounds;probe.remove();
 f.resize(100*o.width*scale/Math.max(1,box[2]-box[0]),100*o.size*scale/Math.max(1,box[1]-box[3]));
 if(o.angle)f.rotate(o.angle);
 if(o.stroke && /^#[0-9a-f]{6}$/i.test(o.stroke)){var sc=new RGBColor(),v=o.stroke.slice(1);sc.red=parseInt(v.substr(0,2),16);sc.green=parseInt(v.substr(2,2),16);sc.blue=parseInt(v.substr(4,2),16);st.strokeColor=sc;st.strokeWeight=Math.max(.5,o.size*.023)*scale;}
 probe=f.duplicate().createOutline();box=probe.visibleBounds;probe.remove();
 f.translate(ab[0]+o.x*scale-(box[0]+box[2])/2,ab[1]-o.y*scale-(box[1]+box[3])/2);f.name=o.phrase+" / "+o.value;'''+s[b:])
