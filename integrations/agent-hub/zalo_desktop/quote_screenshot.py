"""Bounded, one-attempt native Zalo fallback for expired quoted order images."""
import base64
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path


def capture(vault, message):
    from hub.quote_conversation_evidence import explicit_extra, fingerprint
    if (message.get('images') or explicit_extra(message) is None or
        not any(a.get('error') == 'file_link_expired_or_unavailable' for a in message.get('assets', [])) or
        not 0 <= time.time()-message['timestamp'] <= 86400):
        return None
    digest = fingerprint(message)
    folder = vault.home / 'quote-evidence' / digest
    folder.mkdir(parents=True, exist_ok=True)
    receipt = folder / 'receipt.json'
    image = folder / 'chat.png'
    if receipt.exists():
        value=json.loads(receipt.read_text(encoding='utf-8'))
        if value.get('state') != 'done' or not image.exists():
            return None
        if hashlib.sha256(image.read_bytes()).hexdigest()!=value.get('sha256'):
            return None
    else:
        # A crash/timeout never triggers an unbounded UI loop.
        receipt.write_text(json.dumps({'state':'attempting'}),encoding='utf-8')
        q=message['quoted_image']
        source=folder/'request.json'
        source.write_text(json.dumps({'group':message['display_name'],
            'body':message['text'].split('\n')[-1].strip(), 'sender':message['sender'],
            'quote_sender':q['sender'],
            'date':datetime.fromtimestamp(message['timestamp'],timezone(timedelta(hours=7))).strftime('%d/%m/%Y'),
            'clock':datetime.fromtimestamp(message['timestamp'],timezone(timedelta(hours=7))).strftime('%H:%M')},ensure_ascii=False),encoding='utf-8')
        script=Path(__file__).with_name('capture-verified-quote.ps1')
        try:
            process=subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                '-NoProfile','-File',str(script),'-RequestPath',str(source),'-OutputPath',str(image)],
                capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
            if process.returncode or not image.exists():
                raise ValueError('Zalo group/message not verified or screenshot failed')
            raw=image.read_bytes()
            if not raw.startswith(b'\x89PNG\r\n\x1a\n') or not 1000<len(raw)<4000000:
                raise ValueError('Invalid screenshot')
            stamp=datetime.fromtimestamp(message['timestamp'],timezone(timedelta(hours=7))).strftime('%Y-%m')
            dest=vault.root/vault.folder(message)/stamp/'evidence'/('zalo-quote-'+digest+'.png')
            dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists() and dest.read_bytes()!=raw:
                raise ValueError('Evidence already exists with different bytes')
            if not dest.exists():shutil.copyfile(image,dest)
            receipt.write_text(json.dumps({'state':'done','sha256':hashlib.sha256(raw).hexdigest(),'path':str(dest)}),encoding='utf-8')
        except Exception as exc:
            receipt.write_text(json.dumps({'state':'review','reason':type(exc).__name__+': cannot verify exact Zalo message'}),encoding='utf-8')
            return None
    return {'image':{'mime_type':'image/png','data':base64.b64encode(image.read_bytes()).decode()},
        'source_digest':digest,'quote_id':message['quoted_image']['message_id'],
        'method':'windows-msaa-printwindow-v1'}
