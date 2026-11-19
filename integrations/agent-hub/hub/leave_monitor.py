"""Leave requests are evidence for human review, never confirmed attendance."""
import calendar,json,re,time,unicodedata
from datetime import datetime,timedelta,timezone,date
import httpx
from pathlib import Path
from hub.store import event_key
ACCOUNT='zalo-personal-1'
THREAD='g7345600934484454438'
TZ=timezone(timedelta(hours=7))
def fold(s):return ''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn').replace('đ','d')
def parse(m):
    t=fold(m.get('text',''));now=datetime.fromtimestamp(m['timestamp'],TZ).date()
    if not re.search(r'\b(nghi|xin phep)\b',t):return None
    # Only count explicit first-person requests; requests on behalf remain unresolved.
    if not re.search(r'\b(em|e|anh|chi|toi|minh)\s+xin\s+(?:phep\s+)?nghi\b',t) and not re.search(r'cho\s+(?:e|em|anh|chi)\s+.*xin\s+(?:phep\s+)?nghi',t):
        return {'unclear':'Chưa xác định người nghỉ; có thể là xin hộ hoặc tin xác nhận.'}
    if re.search(r'\b(khong|ko|huy|doi|thay|bu|tu|den)\b',t):return {'unclear':'Có hủy/đổi/khoảng ngày hoặc nội dung cần đối chiếu.'}
    matches=re.findall(r'\b(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{4}))?\b',t)
    if not matches:matches=re.findall(r'\b(?:ngay\s+)?(\d{1,2})\s+thang\s+(\d{1,2})(?:\s+nam\s+(\d{4}))?\b',t)
    if len(matches)>1:return {'unclear':'Nhiều ngày trong một tin, cần kiểm tra.'}
    try:
        if matches:d=date(int(matches[0][2] or now.year),int(matches[0][1]),int(matches[0][0]))
        elif re.search(r'\b(ngay mai|mai)\b',t):d=now+timedelta(days=1)
        elif re.search(r'\b(hom nay|bua nay|chieu nay|sang nay|nay)\b',t):d=now
        else:return {'unclear':'Chưa xác định ngày nghỉ cụ thể.'}
    except ValueError:return {'unclear':'Ngày không hợp lệ.'}
    if abs((d-now).days)>62:return {'unclear':'Ngày nghỉ cách xa ngày nhắn, cần kiểm tra năm.'}
    slot='pm' if 'chieu' in t else 'am' if 'sang' in t else 'half' if re.search(r'nua ngay|0[,.]5',t) else 'full'
    return {'date':d.isoformat(),'slot':slot,'shared':bool(re.search(r'\bvoi\b',t))}

def summarize(messages):
    groups={};unclear=[]
    path=Path(__file__).with_name('leave_reviewed.json')
    reviewed=json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    for m in messages:
        if m['message_id'] in reviewed:
            for entry in reviewed[m['message_id']]:
                key=(entry['person_id'],entry['date'][:7]);g=groups.setdefault(key,{'sender':entry['person_name'],'days':{},'messages':[],'shared':False})
                g['days'].setdefault(entry['date'],set()).add(entry['slot'])
                g['messages'].append({**m,'resolved_subject':entry['person_name'],'resolved_date':entry['date'],'resolved_slot':entry['slot'],'review_evidence_ids':entry.get('evidence_ids',[])})
            continue
        p=parse(m)
        if not p:continue
        if 'unclear' in p:unclear.append((m,p['unclear']));continue
        sid=m.get('sender_id')
        if not sid:unclear.append((m,'Thiếu ID người gửi.'));continue
        key=(sid,p['date'][:7]);g=groups.setdefault(key,{'sender':m.get('sender',''),'days':{},'messages':[],'shared':False})
        g['days'].setdefault(p['date'],set()).add(p['slot']);g['messages'].append(m);g['shared']|=p['shared']
    for g in groups.values():
        g['dates']={d:1 if 'full' in slots or {'am','pm'}<=slots else .5 for d,slots in g.pop('days').items()}
        g['total']=sum(g['dates'].values())
    return groups,unclear

class LeaveMonitor:
    def __init__(self,e):
        self.e=e
        with e.store.db() as d:
            d.execute('CREATE TABLE IF NOT EXISTS leave_receipts(id TEXT PRIMARY KEY,fingerprint TEXT,result TEXT)')
    def poll(self):
        cfg=self.e.settings.inboxes.get(ACCOUNT,{}).get('leave_monitor',{})
        if not cfg.get('enabled'):return False
        if getattr(self,'next_poll',0)>time.time():return False
        self.next_poll=time.time()+60
        mapping=self.e.store.thread(account=ACCOUNT,thread_id=THREAD)
        if not mapping:return False
        with self.e.store.db() as d:
            rows=d.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp')>=? ORDER BY json_extract(payload,'$.timestamp')",(ACCOUNT,THREAD,cfg['enabled_after'])).fetchall()
        ms=[json.loads(r[0]) for r in rows]
        ms=[m for m in ms if not self.e.quality_monitor.bot(m) and not m.get('recalled') and not m.get('revision')]
        # Preserve each original/revised message for human attendance review.
        with self.e.store.db() as d:
            rows=d.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp')>=? ORDER BY revision DESC,rowid DESC LIMIT 2001",(ACCOUNT,THREAD,cfg['enabled_after'])).fetchall()
        latest={}
        for row in rows:
            m=json.loads(row[0]);latest.setdefault(m['message_id'],m)
        all_messages=list(latest.values());items=[]
        for m in all_messages:
            if self.e.quality_monitor.bot(m):continue
            result=parse(m)
            if not result:continue
            unclear=result.get('unclear','')
            if result.get('shared'):unclear='Có thể xin nghỉ cùng hoặc xin hộ; chọn người và kiểm tra ngày.'
            if m.get('recalled'):unclear='Tin đã thu hồi, không dùng để ghi nghỉ.'
            elif m.get('revision'):unclear='Tin đã sửa; đối chiếu nguyên văn mới nhất. '+unclear
            items.append({'message_id':m['message_id'],'sender':m.get('sender',''),'sender_id':m.get('sender_id',''),'timestamp':m['timestamp'],'text':m.get('text',''),'suggested_date':result.get('date'),'suggested_days':None if unclear else .5 if result.get('slot')!='full' else 1,'review_reason':unclear,'recalled':bool(m.get('recalled')),'conversation':mapping['conversation']})
        payload={'account':ACCOUNT,'thread_id':THREAD,'last_capture':max((m['timestamp'] for m in all_messages),default=None),'items':sorted(items,key=lambda x:x['timestamp'],reverse=True)[:2000],'truncated':len(rows)>2000}
        try:
            s=self.e.settings
            with httpx.Client(timeout=20) as client:
                response=client.post(s.erp_url.rstrip('/')+'/api/v1/timekeeping/nghi-zalo/snapshot',headers={'X-Zalo-Token':s.erp_token},json=payload);response.raise_for_status()
            return bool(items)
        except Exception:return False
