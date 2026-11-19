import json
from pathlib import Path
from geometry_redraw import reconstruct as badge
from vector_redraw_export import export_vector
raw=Path(r'C:\Users\Admin\AppData\Local\Temp\codex-clipboard-21dd0db2-83e9-49d5-bc58-be94baabf46a.png').read_bytes()
p=badge(raw,json.loads(Path('test-geometry-plan.json').read_text()))
print([(t['value'],round(t['size']),round(t['curve'])) for t in p['texts']])
print(export_vector(p,Path('W:/'),'A LUOM','g8534414090274815910','Denim-Review-03'))

