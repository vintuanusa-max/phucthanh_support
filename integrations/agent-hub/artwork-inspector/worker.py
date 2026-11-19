"""Read archived PDF/AI bytes for Hub inspection; never changes source files."""
import os
os.environ["OPENBLAS_NUM_THREADS"]="1"
os.environ["OMP_NUM_THREADS"]="1"
import argparse
import base64
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx

MAX_BYTES=256*1024*1024

def read_asset(root,asset,limit=MAX_BYTES,raw_result=False):
    root=Path(root).resolve();relative=Path(asset['relative_path'])
    if relative.is_absolute():raise ValueError('Absolute asset path')
    path=(root/relative).resolve()
    if root not in path.parents:raise ValueError('Asset outside archive')
    if path.stat().st_size>limit:raise ValueError('FileTooLarge')
    with path.open('rb') as f:raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError('FileTooLarge')
    if hashlib.sha256(raw).hexdigest()!=asset['sha256']:raise ValueError('SourceHashMismatch')
    return raw if raw_result else base64.b64encode(raw).decode()

def sync(cfg):
    parsed=urlparse(cfg['hub_url'])
    if parsed.hostname not in ('127.0.0.1','localhost') or parsed.scheme!='http':raise ValueError('Expected local Hub')
    with httpx.Client(base_url=cfg['hub_url'],headers={'Authorization':'Bearer '+cfg['ingest_token']},timeout=65,trust_env=False,follow_redirects=False) as c:
        from psd_worker import sync_psd
        psd_state=sync_psd(c,cfg)
        from native_worker import sync_native
        native_state=sync_native(c,cfg)
        from preview_worker import sync_preview
        try:
            preview_state=sync_preview(c,cfg)
        except Exception as exc:
            preview_state='preview_error:'+type(exc).__name__
        from jpg_worker import sync_jpg
        jpg_state=sync_jpg(c,cfg,Path(__file__).parent/'jpg-output')
        from approval_worker import sync_approval
        approval_state=sync_approval(c,cfg)
        from pet_worker import sync_pet
        pet_state=sync_pet(c,cfg,Path(__file__).parent/'pet-output')
        prefix='/adapters/'+cfg['account']+'/artwork-checks'
        r=c.get(prefix);r.raise_for_status();job=r.json().get('job')
        if not job:return native_state+';'+pet_state+';'+jpg_state+';'+preview_state
        try:
            normalized=None
            if job['asset']['name'].lower().endswith(('.cdr','.psd')):
                from format_adapter import normalize
                normalized=normalize(cfg['archive']['root'],job['asset'],Path(__file__).parent/'format-adapters'/job['asset']['sha256'])
                source_raw=read_asset(cfg['archive']['root'],normalized,raw_result=True)
            else:
                source_raw=read_asset(cfg['archive']['root'],job['asset'],raw_result=True)
            data={'shared_source':True,'references':{}} if job.get('shared_source') else {'data':base64.b64encode(source_raw).decode(),'references':{}}
            if normalized:data['normalized_asset']=normalized
            asset=normalized or job['asset'];group=asset['relative_path'].replace('\\','/').split('/')[0]
            if group in ('CANAVI','CANAVI HCM2') and asset['name'].lower().endswith('.ai'):
                try:
                    from native_patterns import inspect
                    data['native_patterns']=inspect(source_raw,Path(__file__).parent/'native-inspection'/asset['sha256'])
                except Exception as exc:data['native_pattern_error']='Native inspection: '+type(exc).__name__
            if (job.get('manual_export') or group in ('CANAVI','CANAVI HCM2')) and asset['name'].lower().endswith(('.ai','.pdf')) and (job.get('manual_export') or not data.get('native_patterns',{}).get('objects')):
                try:
                    from native_local import inspect as inspect_groups
                    data['native_groups']=inspect_groups(source_raw,asset['name'],Path(__file__).parent/'jpg-native-inspection'/asset['sha256'])
                    from native_local import inspect_solid_fills
                    data['native_groups']=inspect_solid_fills(source_raw,asset['name'],Path(__file__).parent/'jpg-native-inspection'/asset['sha256'],data['native_groups'])
                except Exception as exc:data['native_group_error']='Native group inspection: '+type(exc).__name__
            for ref in job.get('reference_assets',[]):
                try:data['references'][ref['sha256']]=read_asset(cfg['archive']['root'],ref,4*1024*1024)
                except (OSError,ValueError):pass
        except (OSError,ValueError,__import__("subprocess").TimeoutExpired) as exc:
            data={'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
        r=c.post(prefix+'/'+job['id'],json=data);r.raise_for_status()
        return 'source_registered' if 'shared_source' in data else ('source_uploaded' if 'data' in data else 'source_needs_review')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',action='append',required=True);parser.add_argument('--state',required=True);parser.add_argument('--once',action='store_true');args=parser.parse_args()
    state=Path(args.state);state.parent.mkdir(parents=True,exist_ok=True)
    import msvcrt
    lock=state.with_suffix('.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    while True:
        from comparison_worker import ensure_started
        ensure_started(args.config)
        report={'time':time.time(),'accounts':{}}
        try:
            configs=[json.loads(Path(path).read_text(encoding='utf-8-sig')) for path in args.config]
            first=configs[0]
            parsed=urlparse(first['hub_url'])
            if parsed.hostname not in ('127.0.0.1','localhost') or parsed.scheme!='http':raise ValueError('Expected local Hub')
            with httpx.Client(base_url=first['hub_url'],headers={'Authorization':'Bearer '+first['ingest_token']},timeout=60,trust_env=False) as waiter:
                response=waiter.post('/workers/artwork/wait',json={'accounts':[cfg['account'] for cfg in configs]})
                response.raise_for_status();ready=set(response.json()['accounts'])
        except Exception as exc:
            report['accounts']={'dispatch':'error:'+type(exc).__name__}
            state.write_text(json.dumps(report),encoding='utf-8')
            if args.once:break
            time.sleep(30);continue
        for path in args.config:
            account=Path(path).parent.name
            try:
                cfg=json.loads(Path(path).read_text(encoding='utf-8-sig'));account=cfg['account']
                report['accounts'][account]=sync(cfg) if account in ready else 'waiting_hub'
            except httpx.HTTPStatusError as exc:
                # Never log headers, URL query, response bodies or credentials.
                report['accounts'][account]='error:HTTP'+str(exc.response.status_code)+' '+exc.request.method+' '+exc.request.url.path
            except Exception as exc:report['accounts'][account]='error:'+type(exc).__name__
        tmp=state.with_suffix('.tmp');tmp.write_text(json.dumps(report),encoding='utf-8');tmp.replace(state)
        if args.once:break
        time.sleep(30)

if __name__=='__main__':main()

