import worker as w,json,sqlite3
from pathlib import Path
mid='simulation-denim-autodetect-20261119-geometry-v3'
m=w.call('source',identity=['zalo-personal-1','g8534414090274815910',mid])
raw=w.reference(m,'A LUOM',m['text'])
import base64
plan=w.call('plan',png=base64.b64encode(raw).decode(),brief=m['text'])
Path('test-geometry-plan.json').write_text(json.dumps(plan),encoding='utf8')
print(plan)
