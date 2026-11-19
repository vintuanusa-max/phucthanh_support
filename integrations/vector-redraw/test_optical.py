from pathlib import Path
import json
import live_text_worker as live
original_clean=live.clean
def record(*args):
    result,lines,mask=original_clean(*args)
    Path('fit05.json').write_text(json.dumps(lines,ensure_ascii=False),encoding='utf8')
    return result,lines,mask
live.clean=record
raw=Path(r'C:\Users\Admin\AppData\Local\Temp\codex-clipboard-21dd0db2-83e9-49d5-bc58-be94baabf46a.png').read_bytes()
plan=json.loads(Path('live-denim-plan.json').read_text())
print(live.export(raw,plan,Path('W:/'),'A LUOM','g8534414090274815910','Denim-Optical-05',Path('denim-detail-api-05.png').read_bytes()))
