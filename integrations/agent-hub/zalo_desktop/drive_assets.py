"""Expand a completed, hash-verified Drive snapshot; no network or source writes."""
import base64,hashlib,json,re
from pathlib import Path

def expand_drive_assets(root, asset, message):
    if asset.get('state')!='ready' or not str(asset.get('relative_path','')).replace('\\','/').endswith('/_snapshot.json'):
        return []
    root=Path(root).resolve(); index=(root/asset['relative_path']).resolve()
    if root not in index.parents: raise ValueError('Drive snapshot outside archive')
    raw=index.read_bytes()
    if len(raw)>2000000 or hashlib.sha256(raw).hexdigest()!=asset['sha256']: raise ValueError('Drive snapshot hash mismatch')
    snap=json.loads(raw)
    if not snap.get('complete') or any(str(snap.get(k))!=str(message.get(k)) for k in ('account','thread_id','message_id')): raise ValueError('Drive source mismatch')
    files=snap.get('files',[])
    if len(files)>100: raise ValueError('Drive snapshot needs review')
    result=[]
    for f in files:
        path=(index.parent/f['path']).resolve()
        if index.parent not in path.parents: raise ValueError('Drive child outside snapshot')
        if path.stat().st_size>32*1024*1024: continue
        data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
        if sha!=f['sha256']: raise ValueError('Drive child hash mismatch')
        ext='.pdf' if data.startswith(b'%PDF-') else '.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if data.startswith(b'\xff\xd8') else ''
        if not ext: continue
        name=f['name']
        if not name.lower().endswith(('.pdf','.ai','.png','.jpg','.jpeg')):name+=ext
        result.append({'id':hashlib.sha256((asset['id']+f['path']+sha).encode()).hexdigest(),'name':name,'kind':'file','state':'ready','relative_path':path.relative_to(root).as_posix(),'sha256':sha,'size':len(data),'mime_type':'application/pdf' if ext=='.pdf' else 'image/png' if ext=='.png' else 'image/jpeg','error':''})
    return result
