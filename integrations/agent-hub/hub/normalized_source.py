"""Bind a worker-derived PDF to the exact immutable source on the shared archive."""
from pathlib import Path
import hashlib

def validate(root, original, derived):
    if original['name'].lower().split('.')[-1] not in ('cdr','psd'):
        raise ValueError('Unexpected normalization source')
    meta=derived.get('normalization',{})
    if meta.get('version')!=1 or meta.get('source_sha256')!=original['sha256'] or meta.get('source_name')!=original['name']:
        raise ValueError('Normalized source binding mismatch')
    group=original['relative_path'].replace('\\','/').split('/')[0]
    expected=group+'/DESIGNER/_source_adapters/'+original['sha256']+'/normalized.pdf'
    if derived.get('relative_path')!=expected or not derived.get('name','').lower().endswith('.pdf'):
        raise ValueError('Unexpected normalized path')
    root=Path(root).resolve()
    for asset,limit in ((original,1024**3),(derived,128*1024**2)):
        path=(root/asset['relative_path']).resolve()
        if root not in path.parents or path.stat().st_size>limit:raise ValueError('Unsafe normalization source')
        with path.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=asset['sha256']:raise ValueError('Normalization hash mismatch')
    path=root/expected
    with path.open('rb') as f:
        if f.read(5)!=b'%PDF-':raise ValueError('Normalized file is not PDF')
    return dict(derived)
