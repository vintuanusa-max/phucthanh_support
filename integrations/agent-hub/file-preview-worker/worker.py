"""Read archived PDF/AI bytes for Hub inspection; never changes source files."""
import argparse
import base64
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx

MAX_BYTES=32*1024*1024

def read_asset(root,asset,limit=MAX_BYTES):
    root=Path(root).resolve();relative=Path(asset['relative_path'])
    if relative.is_absolute():raise ValueError('Absolute asset path')
    path=(root/relative).resolve()
    if root not in path.parents:raise ValueError('Asset outside archive')
    if path.stat().st_size>limit:raise ValueError('FileTooLarge')
    with path.open('rb') as f:raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError('FileTooLarge')
    if hashlib.sha256(raw).hexdigest()!=asset['sha256']:raise ValueError('SourceHashMismatch')
    return base64.b64encode(raw).decode()

def sync(cfg):
    parsed=urlparse(cfg['hub_url'])
    if parsed.hostname not in ('127.0.0.1','localhost') or parsed.scheme!='http':raise ValueError('Expected local Hub')
    with httpx.Client(base_url=cfg['hub_url'],headers={'Authorization':'Bearer '+cfg['ingest_token']},timeout=65,trust_env=False,follow_redirects=False) as c:
        from preview_worker import sync_preview
        try:
            preview_state=sync_preview(c,cfg)
        except Exception as exc:
            preview_state='preview_error:'+type(exc).__name__
        from jpg_worker import sync_jpg
        jpg_state=sync_jpg(c,cfg,Path(__file__).parent/'jpg-output')
        from pet_worker import sync_pet
        pet_state=sync_pet(c,cfg,Path(__file__).parent/'pet-output')
        prefix='/adapters/'+cfg['account']+'/artwork-checks'
        r=c.get(prefix);r.raise_for_status();job=r.json().get('job')
        if not job:return pet_state+';'+jpg_state+';'+preview_state
        try:
            data={'data':read_asset(cfg['archive']['root'],job['asset']),'references':{}}
            for ref in job.get('reference_assets',[]):
                try:data['references'][ref['sha256']]=read_asset(cfg['archive']['root'],ref,4*1024*1024)
                except (OSError,ValueError):pass
        except (OSError,ValueError) as exc:
            data={'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
        r=c.post(prefix+'/'+job['id'],json=data);r.raise_for_status()
        return 'source_uploaded' if 'data' in data else 'source_needs_review'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',action='append',required=True);parser.add_argument('--state',required=True);parser.add_argument('--once',action='store_true');args=parser.parse_args()
    state=Path(args.state);state.parent.mkdir(parents=True,exist_ok=True)
    import msvcrt
    lock=state.with_suffix('.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    while True:
        report={'time':time.time(),'accounts':{}}
        for path in args.config:
            account=Path(path).parent.name
            try:
                cfg=json.loads(Path(path).read_text(encoding='utf-8-sig'));account=cfg['account'];report['accounts'][account]=sync(cfg)
            except Exception as exc:report['accounts'][account]='error:'+type(exc).__name__
        tmp=state.with_suffix('.tmp');tmp.write_text(json.dumps(report),encoding='utf-8');tmp.replace(state)
        if args.once:break
        time.sleep(30)

if __name__=='__main__':main()
