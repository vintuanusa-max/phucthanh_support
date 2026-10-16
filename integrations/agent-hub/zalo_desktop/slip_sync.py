"""Copy verified production slips inside the existing archive; never move originals."""
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

from .vault import safe_name


def copy_slip(job,root):
    root=Path(root).resolve()
    asset=job['asset'];digest=asset['sha256']
    if not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Invalid hash')
    relative=Path(asset['relative_path'])
    source=(root/relative).resolve()
    if relative.is_absolute() or root not in source.parents:raise ValueError('Source outside archive')
    folder=job['folder']
    if folder!=safe_name(folder) or folder in ('.','..'):raise ValueError('Invalid customer folder')
    directory=(root/folder/'DON HANG').resolve()
    if root not in directory.parents:raise ValueError('Destination outside archive')
    with source.open('rb') as file:
        if hashlib.file_digest(file,'sha256').hexdigest()!=digest:raise ValueError('Original hash mismatch')
    name='LENH_'+digest[:16]+'__'+safe_name(asset.get('name') or source.name)
    target=directory/name;directory.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        temporary=target.with_name(target.name+'.'+str(os.getpid())+'.part')
        try:
            shutil.copyfile(source,temporary)
            # No overwrite of another file. Identical names have identical content hashes.
            if target.exists():temporary.unlink()
            else:temporary.rename(target)
        finally:temporary.unlink(missing_ok=True)
    with target.open('rb') as file:
        if hashlib.file_digest(file,'sha256').hexdigest()!=digest:raise ValueError('Destination hash mismatch')
    result={'name':name,'sha256':digest,'relative_path':target.relative_to(root).as_posix()}
    if source.suffix.lower()=='.jxl':
        import pillow_jxl  # Register decoder; keep the original JPEG XL unchanged.
        from PIL import Image
        preview=target.with_suffix('.png')
        if not preview.exists():
            with Image.open(source) as image:
                if image.width*image.height>24_000_000:raise ValueError('Preview size limit')
                temp=preview.with_name(preview.name+'.part')
                image.convert('RGB').save(temp,format='PNG');temp.replace(preview)
        result['preview_name']=preview.name
    record=target.with_name(target.name+'.source.json')
    if not record.exists():
        record.write_text(json.dumps({'account':job['account'],'thread_id':job['thread_id'],
            'source_message_id':job['source_message_id'],'trigger_message_id':job['trigger_message_id'],
            'heading':job['heading'],'original_relative_path':asset['relative_path'],**result},ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def synchronize(reader):
    if time.monotonic()-getattr(reader,'last_slip_sync',0)<20:return
    reader.last_slip_sync=time.monotonic()
    prefix='/adapters/'+reader.cfg['account']+'/production-slips'
    response=reader.http.get(prefix);response.raise_for_status()
    job=response.json().get('job')
    if not job:return
    result=copy_slip(job,reader.cfg['archive']['root'])
    reader.http.post(prefix+'/'+job['id'],json=result).raise_for_status()
