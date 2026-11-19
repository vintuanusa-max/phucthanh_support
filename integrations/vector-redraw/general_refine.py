from pathlib import Path
import json,base64,concurrent.futures
from PIL import Image,ImageDraw,ImageFont
import worker
from geometry_redraw import reconstruct
from vector_redraw_export import export_vector
folder=Path(__file__).resolve().parent/'general-review';folder.mkdir(exist_ok=True)
alt=Image.new('RGB',(900,420),'#fff6e6');g=ImageDraw.Draw(alt)
g.rounded_rectangle((45,50,285,365),radius=32,fill='#17695f');g.polygon([(72,280),(146,129),(179,194),(206,158),(264,280)],fill='#f2c767')
for t,xy,sz,f in [('NORTHLINE',(333,105),68,'arialbd.ttf'),('Studio 27',(339,214),52,'georgiai.ttf')]:g.text(xy,t,font=ImageFont.truetype('C:/Windows/Fonts/'+f,sz),fill='#193b3b')
g.line((342,300,793,300),fill='#bf6546',width=7);alt.save(folder/'independent.png')
def run(pair):
 name,path=pair;raw=path.read_bytes();plan=worker.call('plan',png=base64.b64encode(raw).decode(),brief='Reconstruct as clean flat native Illustrator artwork with editable lettering.')
 (folder/(name+'.json')).write_text(json.dumps(plan,ensure_ascii=False),encoding='utf8')
 return name,raw,plan
inputs=[('Denim-General-01',Path(r'C:\Users\Admin\AppData\Local\Temp\codex-clipboard-21dd0db2-83e9-49d5-bc58-be94baabf46a.png')),('Independent-General-01',folder/'independent.png')]
for name,path in inputs:
    raw=path.read_bytes();p=json.loads((folder/(name+'.json')).read_text(encoding='utf8'))
    name=name.replace('-01','-02')
    target=(Path('W:/'),'A LUOM') if name.startswith('Denim') else (folder.parent,folder.name)
    ai,png=export_vector(reconstruct(raw,p),*target,'local-qa',name)
    im=Image.open(png);im.thumbnail((768,512));im.save(folder/(name+'.png'))
