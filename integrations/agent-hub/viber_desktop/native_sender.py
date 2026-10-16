"""Build-pinned bounded transport. Caller must reserve a durable delivery first."""
import hashlib
import os
import time
from pathlib import Path

BUILD = '4935dcf7f240237978d25b6ca3d15989d073737e00b71fdf22c2a5f059979398'


def invoke(text, *, dry_run=True):
    import frida
    import psutil
    exe=Path(os.environ['LOCALAPPDATA'])/'Viber/Viber.exe'
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=BUILD:
        raise RuntimeError('Viber version changed; transport disabled')
    candidates=[]
    for process in psutil.process_iter(['exe']):
        try:
            if process.info['exe'] and Path(process.info['exe']).resolve()==exe.resolve():
                candidates.append(process.pid)
        except (psutil.NoSuchProcess,psutil.AccessDenied):
            continue
    if len(candidates)!=1:
        raise RuntimeError('Expected one Viber process')
    events=[]
    session=frida.attach(candidates[0])
    script=None
    try:
        script=session.create_script(Path(__file__).with_suffix('.js').read_text(encoding='utf-8'))
        def receive(message,data):
            events.append(message['payload'] if message.get('type')=='send' else
                          {'phase':'error','detail':message.get('description','')[:200]})
        script.on('message',receive)
        script.load()
        script.exports_sync.queue(text,dry_run)
        deadline=time.monotonic()+18
        while time.monotonic()<deadline:
            if any(e.get('phase') in ('stopped','timeout','error') for e in events):
                break
            time.sleep(.05)
        result=next((e for e in events if e.get('phase')=='result'),None)
        if not result or not any(e.get('phase')=='stopped' for e in events):
            return {'invoked':any(e.get('phase')=='invoking' for e in events),'clean':False,'error':'No completed result'}
        return result
    finally:
        if script:
            try: script.unload()
            finally: session.detach()
        else:
            session.detach()
