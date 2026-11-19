"""Evidence-only screenshot at order preparation; never an AI/artwork source."""
import base64
import copy
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ENABLED_AFTER = 1794909364  # Filled with deployment cutoff; no historical capture replay.

def capture(message, folder):
    stamp=datetime.fromtimestamp(message['timestamp'],timezone(timedelta(hours=7)))
    request={'group':message['display_name'],'body':message['text'].strip(),
             'sender':message['sender'],'date':stamp.strftime('%d/%m/%Y'),'clock':stamp.strftime('%H:%M')}
    path=folder/'request.json';path.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
    target=folder/'chat.png'
    proc=subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-File',str(Path(__file__).with_name('capture-order.ps1')),'-RequestPath',str(path),'-OutputPath',str(target)],capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if proc.returncode or b'verified_group_text_sender_time' not in proc.stdout:
        raise ValueError('Không xác minh được đúng nhóm, tin, người gửi và giờ trên Zalo; không dùng ảnh cửa sổ khác.')
    raw=target.read_bytes()
    if not raw.startswith(b'\x89PNG\r\n\x1a\n') or not 1000<len(raw)<4000000:raise ValueError('Invalid screenshot')
    return raw

def prepare(messages, job_id, nas_root, cache_root, *, capture_fn=capture, enrich_fn=None, now=None):
    if enrich_fn is None:
        from hub.document_preview import enrich as enrich_fn
    original=copy.deepcopy(messages)
    if not original or any(m.get('account')!='zalo-personal-1' for m in original):return messages,False
    if len({m['thread_id'] for m in original})!=1:raise ValueError('Mixed evidence groups')
    now=time.time() if now is None else now
    if max(m['timestamp'] for m in original)<ENABLED_AFTER:return messages,False
    preview_error=None
    try:prepared=enrich_fn(original,nas_root)
    except (ValueError,OSError) as exc:
        prepared=original;preview_error=str(exc)
    missing=preview_error or any((m.get('quoted_image') and not m['quoted_image'].get('resolved')) or any(a.get('state')!='ready' for a in m.get('assets',[])) for m in prepared)
    if not missing and any(m.get('images') for m in prepared):return prepared,True
    candidates=[m for m in prepared if m.get('origin')=='customer' and not m.get('recalled') and not m.get('revision') and len(m.get('text','').strip())>=5 and not m['text'].startswith('[')]
    if not candidates:
        if preview_error:raise ValueError(preview_error)
        return prepared,True
    target=max(candidates,key=lambda m:m['timestamp'])
    signature={k:target.get(k) for k in ('account','thread_id','message_id','text','sender','timestamp','revision','recalled')}
    key=hashlib.sha256(json.dumps({'job':job_id,'source':signature},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    folder=Path(cache_root)/'order-screenshots'/key;folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/'receipt.json'
    raw=None;reason=None
    if receipt.exists():
        prior=json.loads(receipt.read_text(encoding='utf-8'))
        if prior.get('state')=='done' and (folder/'chat.png').exists():
            raw=(folder/'chat.png').read_bytes()
            if hashlib.sha256(raw).hexdigest()!=prior['sha256']:raise ValueError('Screenshot hash mismatch')
        else:reason=prior.get('reason','Lượt chụp trước chưa hoàn tất; không tự chụp lặp.')
    elif not 0<=now-target['timestamp']<=86400:
        reason='Tin đã cũ; không lấy ảnh màn hình hiện tại thay cho tin cũ.'
    else:
        receipt.write_text(json.dumps({'state':'attempting'}),encoding='utf-8')
        try:
            raw=capture_fn(target,folder)
            (folder/'chat.png').write_bytes(raw)
            receipt.write_text(json.dumps({'state':'done','sha256':hashlib.sha256(raw).hexdigest(),'message_id':target['message_id']}),encoding='utf-8')
        except Exception as exc:
            reason=str(exc) if isinstance(exc,ValueError) else 'Không chụp được đúng tin Zalo: '+type(exc).__name__
            receipt.write_text(json.dumps({'state':'review','reason':reason},ensure_ascii=False),encoding='utf-8')
    if raw:
        target.setdefault('images',[]).append({'mime_type':'image/png','data':base64.b64encode(raw).decode(),'preview_label':'ẢNH CHỤP ZALO — bằng chứng trao đổi, không phải artwork để in'})
        target['order_screenshot']={'method':'windows-msaa-printwindow-order-v1','message_id':target['message_id'],'sha256':hashlib.sha256(raw).hexdigest()}
        if preview_error:
            target['evidence_capture_note']='Không mở được nguồn thiết kế; dùng ảnh chụp đoạn chat để nhân viên đối chiếu. '+preview_error
        return prepared,True
    target['evidence_capture_note']=reason or 'Chưa lấy được ảnh chụp Zalo.'
    if preview_error:raise ValueError(preview_error+'; '+target['evidence_capture_note'])
    return prepared,True
