"""Only output isolation changes; color, dimensions and artwork remain untouched."""
from pathlib import Path
import re
import shutil
import unicodedata


def ascii_model(text):
    """Fold Vietnamese characters (including D/d stroke) to safe ASCII folder/model identifiers."""
    folded = ''.join(
        c for c in unicodedata.normalize('NFD', str(text).replace('Đ', 'D').replace('đ', 'd'))
        if not unicodedata.combining(c)
    )
    return re.sub(r'[^A-Za-z0-9_-]', '', folded)


def ascii_file_code(text):
    """Fold Vietnamese characters cleanly while keeping dots, underscores, and hyphens for export filenames."""
    folded = ''.join(
        c for c in unicodedata.normalize('NFD', str(text).strip().replace('Đ', 'D').replace('đ', 'd'))
        if not unicodedata.combining(c)
    )
    return re.sub(r'[^A-Za-z0-9_.-]', '', re.sub(r'\s+', '_', folded)).rstrip('.') or 'MODEL'

def worker(job):
    name=job.get('fleet_attempt',{}).get('worker')
    if name is not None and name not in ('designer-main','local-backup'):raise ValueError('Invalid output worker')
    return name

def archive(job,base):
    name=worker(job)
    return Path(base)/'worker-results'/name if name else Path(base)

def local(job,base):
    aid=job.get('fleet_attempt',{}).get('id')
    if aid and not re.fullmatch('[a-f0-9]{32}',aid):raise ValueError('Invalid attempt')
    result=Path(base)/('attempt-'+aid) if aid else Path(base)
    from fleet_client import watch
    watch(job,result)
    return result

def inherit_editable(job,destination):
    source=job.get('source',{}).get('_fleet_output_worker')
    target=worker(job)
    if not source or source==target:return
    if source not in ('designer-main','local-backup'):raise ValueError('Invalid editable source worker')
    origin=Path(destination).parent/source
    # Native stage was accepted before PET; its completed editable remains immutable.
    for path in origin.glob('*.ai'):
        dest=Path(destination)/path.name
        if not dest.exists():
            with path.open('rb') as src,dest.open('xb') as out:shutil.copyfileobj(src,out)
