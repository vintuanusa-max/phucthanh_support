from pathlib import Path
import json,base64
import worker
from live_text_worker import export
raw=Path(r'C:\Users\Admin\AppData\Local\Temp\codex-clipboard-21dd0db2-83e9-49d5-bc58-be94baabf46a.png').read_bytes()
p=worker.call('plan',png=base64.b64encode(raw).decode(),brief='Keep every original word and number and make all lettering editable.')
Path('live-denim-plan.json').write_text(json.dumps(p),encoding='utf8')
print([(x['source'],len(x['glyphs'])) for x in p['texts']],flush=True)
print(export(raw,p,Path('W:/'),'A LUOM','g8534414090274815910','Denim-Live-Text-01'))
