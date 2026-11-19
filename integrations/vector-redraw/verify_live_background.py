import json,cv2,numpy as np
from pathlib import Path
from PIL import Image
from live_text_worker import clean
raw=Path(r'C:\Users\Admin\AppData\Local\Temp\codex-clipboard-21dd0db2-83e9-49d5-bc58-be94baabf46a.png').read_bytes()
im,lines,mask=clean(raw,json.loads(Path('live-denim-plan.json').read_text()))
orig=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
print('Background modified percent',round(100*np.count_nonzero(mask)/mask.size,2),'outside mask differing pixels',np.count_nonzero(np.any(im[:,:,:3][mask==0]!=orig[mask==0],axis=1)))
png=Image.open('W:/A LUOM/DESIGNER/Mau-Denim-Live-Text-01.png');png.thumbnail((768,512));png.save('live-text-preview.png')
