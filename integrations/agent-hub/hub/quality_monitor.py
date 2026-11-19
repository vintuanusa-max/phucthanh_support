"""File In monitoring: candidate reports only, never employee blame or KPI deduction."""
import json,re,time,unicodedata
from datetime import datetime,timedelta,timezone
import httpx
from hub.store import event_key
GROUPS={'zalo-personal-1':'g3307527274697028144','whatsapp-personal-1':'120363407119559834@g.us'}
def monitored(account,thread):return GROUPS.get(account)==thread or (account=='zalo-personal-1' and thread=='g7345600934484454438')

TZ=timezone(timedelta(hours=7))
SCAN_HOURS=(8,12,18)
# Both exact group IDs verified against current desktop reader inventory.
ACTIVE_ACCOUNTS={'zalo-personal-1','whatsapp-personal-1'}

def latest_slot(now):
    local=datetime.fromtimestamp(now,TZ)
    slots=[local.replace(hour=h,minute=0,second=0,microsecond=0) for h in SCAN_HOURS]
    candidates=[s for s in slots if s<=local]
    return (max(candidates) if candidates else slots[-1]-timedelta(days=1)).timestamp()

def category(text):
    text=' '.join(''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn').replace('đ','d').split())
    for label,pattern in [('Mất màu',r'\bmat mau\b'),('Cạ giấy',r'\bca giay\b'),('Hư',r'\bhu\b'),('Lỗi',r'\bloi\b'),('Sai',r'\bsai\b')]:
        if re.search(pattern,text):return label
    return None

class QualityMonitor:
    def __init__(self,e):
        self.e=e
        with e.store.db() as d:d.execute('CREATE TABLE IF NOT EXISTS quality_events(id TEXT PRIMARY KEY,state TEXT,payload TEXT,next_try REAL DEFAULT 0,result TEXT)')
        with e.store.db() as d:
            d.execute('CREATE TABLE IF NOT EXISTS quality_scan_schedule(id integer PRIMARY KEY,activated REAL NOT NULL,completed REAL NOT NULL DEFAULT 0)')
            d.execute('INSERT OR IGNORE INTO quality_scan_schedule(id,activated) VALUES(1,?)',(time.time(),))
    def bot(self,m):
        if m.get('origin') in ('ai','bot','hub_note'):return True
        with self.e.store.db() as d:
            ids={str(m.get('message_id','')),str(m.get('client_message_id',''))}-{''}
            for r in d.execute('SELECT platform_id,client_id,payload FROM deliveries WHERE account=? AND thread_id=?',(m['account'],m['thread_id'])):
                if ids & ({r[0],r[1]}-{''}):return True
                if m.get('direction')=='outgoing' and json.loads(r[2]).get('content')==m.get('text'):return True
            for r in d.execute('SELECT result FROM print_deliveries WHERE account=? AND thread_id=?',(m['account'],m['thread_id'])):
                v=json.loads(r[0] or '{}')
                for k in ('message_id','client_id'):
                    x=str(v.get(k) or '')
                    if x in ids or any(i and ('_'+i+'_') in x for i in ids):return True
        return 'CHOT-IN-' in m.get('text','')
    def poll(self):
        now=time.time();slot=latest_slot(now)
        if getattr(self,'completed_slot',None)==slot:return False
        with self.e.store.db() as d:
            schedule=d.execute('SELECT activated,completed FROM quality_scan_schedule WHERE id=1').fetchone()
        if slot<schedule['activated'] or slot<=schedule['completed']:
            self.completed_slot=slot;return False
        start=schedule['activated']
        with self.e.store.db() as d:
            pending=d.execute("SELECT * FROM quality_events WHERE state='pending' AND next_try<=? AND CAST(json_extract(payload,'$.timestamp') AS REAL)>=? AND CAST(json_extract(payload,'$.timestamp') AS REAL)<=? ORDER BY id LIMIT 1",(slot,start,slot)).fetchone()
        if pending:
            p=json.loads(pending['payload']);s=self.e.settings
            try:
                with httpx.Client(timeout=20,follow_redirects=False) as c:
                    r=c.post(s.erp_url.rstrip('/')+'/api/v1/quality/ingest',headers={'X-Zalo-Token':s.erp_token},json=p);r.raise_for_status()
                    result=r.json()
                    if result.get('status')!='recorded' or not result.get('id') or result.get('points_deducted')!=0:raise ValueError('ERP chưa bật tiếp nhận phiếu')
                with self.e.store.db() as d:d.execute("UPDATE quality_events SET state='done',result=? WHERE id=?",(json.dumps(result),pending['id']))
            except Exception:
                # Retry only at the next scheduled scan, never continuously.
                with self.e.store.db() as d:d.execute('UPDATE quality_events SET next_try=? WHERE id=?',(slot+1,pending['id']))
            return True
        for account,thread in GROUPS.items():
            if account not in ACTIVE_ACCOUNTS:continue
            mapping=self.e.store.thread(account=account,thread_id=thread)
            if not mapping:continue
            with self.e.store.db() as d:
                rows=d.execute("SELECT c.id,c.payload FROM captures c WHERE c.account=? AND c.thread_id=? AND json_extract(c.payload,'$.timestamp')>=? AND json_extract(c.payload,'$.timestamp')<=? AND NOT EXISTS(SELECT 1 FROM quality_events q WHERE q.id=c.id) ORDER BY json_extract(c.payload,'$.timestamp') LIMIT 100",(account,thread,start,slot)).fetchall()
            for row in rows:
                m=json.loads(row['payload']);label=category(m.get('text',''))
                if not label or self.bot(m) or m.get('revision') or m.get('recalled'):
                    with self.e.store.db() as d:d.execute('INSERT OR IGNORE INTO quality_events(id,state,payload) VALUES(?,?,?)',(row['id'],'ignored','{}'))
                    continue
                with self.e.store.db() as d:
                    history=[json.loads(r[0]) for r in d.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp') BETWEEN ? AND ? ORDER BY json_extract(payload,'$.timestamp') DESC LIMIT 10",(account,thread,m['timestamp']-900,m['timestamp']))]
                context=[{k:x.get(k) for k in ('message_id','sender','timestamp','text','quoted_image','assets')} for x in reversed(history)]
                p={'source_key':row['id'],'account':account,'thread_id':thread,'message_id':m['message_id'],'timestamp':m['timestamp'],'sender':m.get('sender',''),'text':m.get('text','')[:12000],'conversation':mapping['conversation'],'category':label,'summary':'Từ khóa '+label.lower()+': '+m.get('text','')[:1300],'context':context}
                with self.e.store.db() as d:d.execute('INSERT OR IGNORE INTO quality_events(id,state,payload) VALUES(?,?,?)',(row['id'],'pending',json.dumps(p,ensure_ascii=False)))
            if rows:return True
        with self.e.store.db() as d:d.execute('UPDATE quality_scan_schedule SET completed=? WHERE id=1',(slot,))
        self.completed_slot=slot
        return False
