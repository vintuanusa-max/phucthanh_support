from pathlib import Path
import base64,worker
p=Path('C:/Users/Admin/AppData/Local/Temp/codex-clipboard-21dd0db2-83e9-49d5-bc58-be94baabf46a.png')
out=Path('denim-detail-api-05.png')
if not out.exists():out.write_bytes(base64.b64decode(worker.call('reference_image',png=base64.b64encode(p.read_bytes()).decode()),validate=True))
print(out.stat().st_size)
