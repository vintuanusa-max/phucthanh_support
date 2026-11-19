from PIL import Image
import numpy as np,cv2
from pathlib import Path
ref=Image.open(r'C:\Users\Admin\.codex\visualizations\2026\11\19\01a1f1d2-fcb0-7c21-a2d4-3c1d93acb511\Denim-Supply-preview.png').convert('RGB')
def frame(im):
 im=im.convert('RGBA'); bg=Image.new('RGB',im.size,'white');bg.paste(im,mask=im.getchannel('A'))
 a=np.array(bg);mask=np.min(a,axis=2)<210
 y,x=np.where(mask);a=a[y.min():y.max()+1,x.min():x.max()+1]
 return cv2.resize(a,(800,660),interpolation=cv2.INTER_AREA)
target=frame(ref)
for name in ['5d8f41d28289ae50b3a5','dc68d3f6ce98f9b104b3']:
 im=Image.open(Path(r'W:\A LUOM\DESIGNER')/('Mau-'+name+'.png'))
 a=frame(im);print(name,'MAE',np.abs(a.astype(float)-target).mean(),flush=True)
 im.thumbnail((720,600));im.save(name+'.png')

