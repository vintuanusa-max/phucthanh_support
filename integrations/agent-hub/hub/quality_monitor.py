"""File In monitoring: candidate reports only, never employee blame or KPI deduction."""
import json,re,time,unicodedata
import httpx
from hub.store import event_key
GROUPS={'zalo-personal-1':'g3307527274697028144','whatsapp-personal-1':'120363407119559834@g.us'}
def monitored(account,thread):return GROUPS.get(account)==thread or (account=='zalo-personal-1' and thread=='g7345600934484454438')

def category(text):
    text=''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn').replace('đ','d')
    for label,pattern in [('Sai màu',r'\b(sai mau|lech mau|khong dung mau|ko dung mau)\b'),('Sai nội dung',r'\b(thieu chu|thieu dau|sai chu|sai chinh ta|thieu logo)\b'),('Lỗi in',r'\b(in sai|in hu|in loi|khong dung|ko dung|in nguoc|in lech|sai kich thuoc|sai file|nham file|loi in|hong ban in)\b')]:
        if re.search(pattern,text):return label
    return None

class QualityMonitor:
    def __init__(self,e):
        self.e=e
        with e.store.db() as d:d.execute('CREATE TABLE IF NOT EXISTS quality_events(id TEXT PRIMARY KEY,state TEXT,payload TEXT,next_try REAL DEFAULT 0,result TEXT)')
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
        with self.e.store.db() as d:
            pending=d.execute("SELECT * FROM quality_events WHERE state='pending' AND next_try<=? LIMIT 1",(time.time(),)).fetchone()
        if pending:
            p=json.loads(pending['payload']);s=self.e.settings
            try:
                with httpx.Client(timeout=20,follow_redirects=False) as c:
                    r=c.post(s.erp_url.rstrip('/')+'/api/v1/quality/ingest',headers={'X-Zalo-Token':s.erp_token},json=p);r.raise_for_status()
                    result=r.json();assert result.get('id') and result.get('points_deducted')==0
                with self.e.store.db() as d:d.execute("UPDATE quality_events SET state='done',result=? WHERE id=?",(json.dumps(result),pending['id']))
            except Exception:
                with self.e.store.db() as d:d.execute('UPDATE quality_events SET next_try=? WHERE id=?',(time.time()+120,pending['id']))
            return True
        for account,thread in GROUPS.items():
            start=self.e.settings.inboxes.get(account,{}).get('quality_monitor',{}).get('enabled_after')
            if not start:continue
            with self.e.store.db() as d:
                rows=d.execute("SELECT c.id,c.payload FROM captures c WHERE c.account=? AND c.thread_id=? AND json_extract(c.payload,'$.timestamp')>=? AND json_extract(c.payload,'$.timestamp')<? AND NOT EXISTS(SELECT 1 FROM quality_events q WHERE q.id=c.id) ORDER BY json_extract(c.payload,'$.timestamp') LIMIT 30",(account,thread,start,time.time()-120)).fetchall()
            for row in rows:
                m=json.loads(row['payload']);label=category(m.get('text',''))
                if not label or self.bot(m) or m.get('revision') or m.get('recalled'):
                    with self.e.store.db() as d:d.execute('INSERT OR IGNORE INTO quality_events(id,state,payload) VALUES(?,?,?)',(row['id'],'ignored','{}'))
                    continue
                mapping=self.e.store.thread(account=account,thread_id=thread)
                if not mapping:continue
                with self.e.store.db() as d:
                    history=[json.loads(r[0]) for r in d.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp') BETWEEN ? AND ? ORDER BY json_extract(payload,'$.timestamp') DESC LIMIT 10",(account,thread,m['timestamp']-900,m['timestamp']))]
                context=[{k:x.get(k) for k in ('message_id','sender','timestamp','text','quoted_image','assets')} for x in reversed(history)]
                p={'source_key':row['id'],'account':account,'thread_id':thread,'message_id':m['message_id'],'timestamp':m['timestamp'],'sender':m.get('sender',''),'text':m.get('text','')[:12000],'conversation':mapping['conversation'],'category':label,'summary':'Dấu hiệu '+label.lower()+': cần đọc ngữ cảnh và duyệt, chưa quy trách nhiệm.','context':context}
                with self.e.store.db() as d:d.execute('INSERT OR IGNORE INTO quality_events(id,state,payload) VALUES(?,?,?)',(row['id'],'pending',json.dumps(p,ensure_ascii=False)))
                self.e.store.enqueue(row['id']+':quality','notice',{'conversation':mapping['conversation'],'quality_review':True,'text':'PHIẾU LỖI CHỜ DUYỆT — '+label+'\nTin của '+m.get('sender','')+': '+m.get('text','')[:3000]+'\nChưa xác nhận lỗi thực tế; người báo không mặc định là người gây lỗi. Quản trị đối chiếu đơn/mã mẫu và chọn nhân viên trong ERP. KPI chưa bị trừ.'})
                return True
        return False
