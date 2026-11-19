import hashlib
from pathlib import Path, PureWindowsPath

def shared_source(root, asset, limit):
    """Resolve only the persisted job asset; never trust a client-supplied path."""
    relative = str(asset.get('relative_path', '')).replace('\\', '/')
    if not relative or PureWindowsPath(relative).drive or relative.startswith('/') or any(x in ('', '.', '..') for x in relative.split('/')) or ':' in relative:
        raise ValueError('Invalid shared source relative path')
    base = Path(root).resolve(strict=True)
    path = (base / relative).resolve(strict=True)
    if base not in path.parents or not path.is_file():
        raise ValueError('Source outside shared archive')
    size = path.stat().st_size
    if not 0 < size <= limit:
        raise ValueError('Shared source exceeds size limit or is empty')
    digest = hashlib.sha256()
    total = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            total += len(chunk)
            if total > limit:
                raise ValueError('Shared source exceeds size limit')
            digest.update(chunk)
    if total != size or digest.hexdigest() != asset.get('sha256'):
        raise ValueError('Shared source SHA256 mismatch')
    return path
