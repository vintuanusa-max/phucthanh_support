from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
folder=Path('W:/A LUOM/DESIGNER')
src=Image.open(r'C:\Users\Admin\AppData\Local\Temp\codex-clipboard-21dd0db2-83e9-49d5-bc58-be94baabf46a.png').convert('RGB')
new=Image.open(folder/'Mau-Denim-Live-Serif-Match-04.png').convert('RGB')
old=Image.open(folder/'Mau-Denim-Live-Type-Path-03.png').convert('RGB')
rows=[[src,'Ảnh gốc'],[old,'Bản trước · Cooper Black'],[new,'Bản mới']]
out=Image.new('RGB',(1340,650),'#faf8f4');draw=ImageDraw.Draw(out);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
for j,(im,label) in enumerate(rows):
 y=12+j*213;draw.text((12,y),label,font=font,fill='#182635')
 for box,x in [((245,235,1280,488),12),((310,590,1240,857),704)]:
  patch=im.crop(box);patch.thumbnail((660,179));out.paste(patch,(x,y+28))
out.save(folder/'Denim-Title-Font-Comparison-04.png')

