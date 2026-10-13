"""Archive print evidence and dispatch at most once through an available Desktop transport."""
import base64
import json
import subprocess
import time
from pathlib import Path

import httpx

from hub.evidence_document import save_document,erp_evidence_png


def synchronize(reader):
    if time.monotonic()-getattr(reader,'last_print_sync',0)<15:return
    reader.last_print_sync=time.monotonic()
    prefix='/adapters/'+reader.cfg['account']
    response=reader.http.get(prefix+'/print-evidence');response.raise_for_status()
    job=response.json().get('job')
    if job:
        try:
            try:
                result=save_document(job['messages'],job['reference'],reader.cfg['archive']['root'],notice=job.get('notice'),new_message_ids=job.get('new_message_ids'))
                png=erp_evidence_png(result)
            except ValueError:
                if not job.get('notice'):raise
                # A large photo must not suppress a stop-printing warning. Preserve
                # source IDs/text/NAS references, explicitly mark omitted photo pixels.
                text_only=[{**m,'images':[]} for m in job['messages']]
                notice=job['notice']+'\nẢNH KHÔNG ĐÍNH KÈM ĐƯỢC DO GIỚI HẠN: xem ảnh gốc trên NAS/hội thoại trước khi in.'
                result=save_document(text_only,job['reference'],reader.cfg['archive']['root'],notice=notice,new_message_ids=job.get('new_message_ids'))
                png=erp_evidence_png(result)
            result['image_base64']=base64.b64encode(png).decode()
        except Exception as exc:result={'error':type(exc).__name__}
        reader.http.post(prefix+'/print-evidence/'+job['id'],json=result).raise_for_status()
    if not reader.cfg.get('print_delivery_enabled'):return
    pending=reader.http.get(prefix+'/print-deliveries/pending');pending.raise_for_status()
    for account in pending.json().get('accounts',[]):
        try:
            if account.startswith('zalo'):
                from zalo_desktop.print_transport import transport
                if transport({'thread_id':'g3307527274697028144'},prepare=True).get('state')!='ready':continue
            elif not whatsapp_ready():continue
            dispatch(reader,prefix,account)
        except Exception as exc:
            # Keep the other channel and capture running; never repeat a claimed send.
            status=Path(reader.cfg['state_dir'])/('print-error-'+account+'.json')
            status.write_text(json.dumps({'time':time.time(),'error':type(exc).__name__}),encoding='utf-8')


def whatsapp_ready():
    import psutil
    listeners=[c for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port==54329]
    if not listeners or any(c.laddr.ip not in ('127.0.0.1','::1') for c in listeners):return False
    for connection in listeners:
        process=psutil.Process(connection.pid)
        if process.name().lower()!='msedgewebview2.exe' or not any(p.name().lower()=='whatsapp.root.exe' for p in process.parents()):return False
    try:
        with httpx.Client(trust_env=False,timeout=2) as local:
            local.get('http://127.0.0.1:54329/json/version').raise_for_status()
        return True
    except httpx.HTTPError:return False


def dispatch(reader,prefix,account):
    response=reader.http.post(prefix+'/print-deliveries/claim',params={'destination':account});response.raise_for_status()
    job=response.json().get('job')
    if not job:return
    journal=Path(reader.cfg['state_dir'])/('print-'+job['id']+'.json')
    try:
        with journal.open('x',encoding='utf-8') as file:
            json.dump({'state':'sending','id':job['id'],'destination':job['thread_id']},file)
    except FileExistsError:
        reader.http.post(prefix+'/print-deliveries/'+job['id'],json={'state':'uncertain'}).raise_for_status();return
    try:
        if account.startswith('zalo'):
            from zalo_desktop.print_transport import transport
            result=transport(job)
        else:
            command=[r'C:\Program Files\nodejs\node.exe',str(Path(__file__).with_name('send_print.mjs'))]
            proc=subprocess.run(command,input=json.dumps(job),text=True,encoding='utf-8',capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
            if proc.returncode:raise ValueError('Desktop send outcome unknown')
            result=json.loads(proc.stdout)
    except Exception:result={'state':'uncertain'}
    journal.write_text(json.dumps({'id':job['id'],**result}),encoding='utf-8')
    reader.http.post(prefix+'/print-deliveries/'+job['id'],json=result).raise_for_status()
