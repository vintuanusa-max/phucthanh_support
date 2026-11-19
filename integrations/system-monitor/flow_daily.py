"""Daily execution statistics for the local flow diagram."""
import datetime as dt
import json,sqlite3,subprocess,threading,time
from pathlib import Path
from contextlib import closing
HERE=Path(__file__).resolve().parent
TZ=dt.timezone(dt.timedelta(hours=7))
lock=threading.Lock()
cached=None
def daily():
    global cached
    with lock:
        now=dt.datetime.now(TZ);day=now.date().isoformat()
        if cached and cached['day']==day and time.time()-cached['asof']<5:return cached
        start=now.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        script=(HERE/'hub_flow_daily.py').read_text(encoding='utf-8-sig')
        r=subprocess.run(['docker','exec','phucthanh-chatwoot-hub-1','/app/.venv/bin/python','-c',script,str(start),str(start+86400)],capture_output=True,timeout=10,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        view=json.loads(r.stdout)
        root=HERE.parent/'VectorRedraw'
        with closing(sqlite3.connect((root/'state.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
            rows=db.execute("select c.created,j.status from redraw_clusters c join jobs j on j.id=c.job where c.created>=? and c.created<?",(start,start+86400)).fetchall()
            for node,subset in [('redraw',rows),('redraw_delivery',[r for r in rows if r[1].startswith('chatwoot:')])]:
                view['counts'][node]=dict(n=len(subset),unit="cụm theo ngày tiếp nhận")
                view['events'] += [[int(t),node] for t,_ in subset]
            live=json.loads((root/'event-state.json').read_text())
            if live.get('state')=='draining':
                # Only the current task, not an old job stuck in drawing.
                cursor=live.get('cursor');high=live.get('through')
                if cursor is not None and high is not None:
                    for node,phase in [('redraw','drawing'),('redraw_delivery','publishing')]:
                        view['active'][node]=db.execute("select count(*) from flow_active a join jobs j on j.id=a.job where j.status=? and a.capture>? and a.capture<=?",(phase,cursor,high)).fetchone()[0]
        cached=dict(view,day=day,asof=time.time());return cached
