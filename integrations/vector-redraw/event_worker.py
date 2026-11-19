"""Windows side: one listener, drain in order on a new capture or reconnect."""
import json
import sqlite3
import subprocess
import time
from pathlib import Path
import worker

ROOT=Path(__file__).resolve().parent
def status(state,**info):
    f=ROOT/'event-state.tmp'
    f.write_text(json.dumps(dict(state=state,time=time.time(),**info)),encoding='utf8')
    f.replace(ROOT/'event-state.json')

def serve():
    script=(ROOT/'capture_events.py').read_text(encoding='utf-8-sig')
    delay=2
    while True:
        proc=None
        try:
            status('connecting')
            proc=subprocess.Popen(['docker','exec','-i','phucthanh-chatwoot-hub-1','/app/.venv/bin/python','-u','-c',script,'/data/hub.sqlite3'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
            for line in proc.stdout:
                high=int(line.strip());delay=2
                with sqlite3.connect(ROOT/'state.sqlite') as db:
                    row=db.execute('select n from checkpoint').fetchone()
                    cursor=row[0] if row else 0
                if cursor<high:status('draining',cursor=cursor,through=high)
                while cursor<high:
                    nxt=worker.main()
                    if nxt is None or nxt<=cursor:raise RuntimeError('Hub batch did not advance')
                    cursor=nxt
                status('waiting_for_capture',cursor=cursor)
            raise ConnectionError('Hub listener disconnected')
        except Exception as exc:
            status('reconnecting',error=type(exc).__name__,delay=delay)
        finally:
            if proc is not None:
                proc.stdin.close()
                if proc.poll() is None:
                    try:proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:proc.terminate()
                proc.wait()
        time.sleep(delay);delay=min(60,delay*2)
if __name__=='__main__':serve()
