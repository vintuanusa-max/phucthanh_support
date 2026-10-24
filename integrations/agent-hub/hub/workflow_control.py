"""Internal workflow observability, immutable lineage and explicit review.

No ERP calls, public messages, RIP or automatic retries in this module.
"""
import hashlib
import json
import time

from hub.workflow_errors import issue


class WorkflowControl:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS workflow_beats(service TEXT PRIMARY KEY,seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_alerts(id TEXT PRIMARY KEY,state TEXT NOT NULL,detail TEXT NOT NULL,first REAL NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_lineage(brief_id TEXT PRIMARY KEY,family TEXT NOT NULL,previous TEXT,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_versions(id TEXT PRIMARY KEY,brief_id TEXT NOT NULL,family TEXT NOT NULL,kind TEXT NOT NULL,export_id TEXT NOT NULL,manifest TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,version_id TEXT NOT NULL,decision TEXT NOT NULL,note TEXT NOT NULL,created REAL NOT NULL);
            ''')

    def beat(self, service):
        with self.store.db() as db:
            db.execute('INSERT INTO workflow_beats VALUES(?,?) ON CONFLICT(service) DO UPDATE SET seen=excluded.seen', (service,time.time()))

    def current(self, brief_id):
        with self.store.db() as db:
            archived = db.execute("SELECT 1 FROM design_briefs WHERE id=? AND json_extract(payload,'$.dispatch_archived_at') IS NOT NULL", (brief_id,)).fetchone()
            if archived:
                return False
            row = db.execute('SELECT family FROM workflow_lineage WHERE brief_id=?',(brief_id,)).fetchone()
            if not row:
                return True
            latest = db.execute('SELECT brief_id FROM workflow_lineage WHERE family=? ORDER BY created DESC,brief_id DESC LIMIT 1',(row['family'],)).fetchone()
            return latest['brief_id'] == brief_id

    def merge(self, payload):
        """Merge only explicit same-sender source linkage, never just nearby messages."""
        proposed = payload['brief'].get('proposed_previous_id')
        if not proposed:
            return payload
        with self.store.db() as db:
            row = db.execute('SELECT payload FROM design_briefs WHERE id=? AND account=? AND thread_id=?',
                             (proposed,payload['account'],payload['thread_id'])).fetchone()
        if not row:
            return payload
        old = json.loads(row['payload'])
        with self.store.db() as db:
            candidates = db.execute('SELECT id,payload FROM design_briefs WHERE account=? AND thread_id=? ORDER BY created DESC LIMIT 30',(payload['account'],payload['thread_id'])).fetchall()
        shared = set(old['brief']['source_message_ids']).intersection(payload['brief']['source_message_ids'])
        others = [r for r in candidates if r['id']!=proposed and self.current(r['id']) and shared.intersection(json.loads(r['payload'])['brief']['source_message_ids'])]
        if others:
            payload['relation_status']='needs_review'
            payload['review_items'].append('Nguồn chung thuộc nhiều hồ sơ; cần nhân viên chọn đúng mẫu.')
            return payload
        old_ids = {s['message_id'] for s in old['sources']}
        old_senders = {s.get('sender_id') for s in old['sources'] if s.get('role')=='customer' and s.get('sender_id')}
        fresh = [s for s in payload['sources'] if s['message_id'] not in old_ids and s.get('role')=='customer']
        # Shared concrete source ID or explicit quote of a source; sender name alone is insufficient.
        linked = bool(old_ids.intersection(payload['brief']['source_message_ids']))
        for s in fresh:
            q = s.get('quoted_image') or {}
            linked |= any(str(q.get(k,'')) in old_ids for k in ('message_id','quoted_message_id','source_message_id'))
        if not linked or not fresh or any(not s.get('sender_id') or s['sender_id'] not in old_senders for s in fresh) or not self.current(proposed):
            payload['review_items'].append('Chưa nối chắc chắn hồ sơ cũ: cần xác nhận đúng mẫu/người gửi trước khi thay thế.')
            payload['relation_status'] = 'needs_review'
            return payload
        payload['sources'] = list({s['message_id']:s for s in old['sources']+payload['sources']}.values())
        b, previous = payload['brief'], old['brief']
        replaced = set(b.get('replaces_requirement_message_ids', []))
        old_requirement_ids = {r['message_id'] for r in previous['requirements']}
        if not replaced <= old_requirement_ids:
            raise ValueError('Unknown replaced requirement')
        requirements = [r for r in previous['requirements'] if r['message_id'] not in replaced] + b['requirements']
        b['requirements'] = list({(r['message_id'],r['quote']):r for r in requirements}.values())
        resolved = set(b.get('resolved_missing_fields', []))
        if not resolved <= set(previous.get('missing_fields',[])):
            raise ValueError('Unknown resolved field')
        b['missing_fields'] = sorted((set(previous.get('missing_fields',[]))-resolved) | set(b['missing_fields']))
        b['source_message_ids'] = list(dict.fromkeys(previous['source_message_ids']+b['source_message_ids']))
        # Conflicts remain reviewable; only missing fields explicitly resolved by extraction can clear.
        b['conflicts'] = list(dict.fromkeys(previous.get('conflicts',[])+b.get('conflicts',[])))
        from hub.bag_design import bag_plan
        for key in ('bag_facts','bag_panels'):
            if not b.get(key): b[key]=previous.get(key,[])
        from hub.bag_design import BagFact, BagPanel
        payload['bag_print']=bag_plan([BagFact.model_validate(x) for x in b['bag_facts']], [BagPanel.model_validate(x) for x in b['bag_panels']])
        payload['review_items'] = list(dict.fromkeys(payload['review_items']+b['missing_fields']+b['conflicts']))
        payload['relation_status'] = 'linked_revision'
        payload['revision_changes'] = {'previous':proposed,'new_messages':[s['message_id'] for s in fresh],
                                       'resolved_fields':sorted(resolved),'replaced_requirement_messages':sorted(replaced)}
        return payload

    def register(self, payload):
        previous = payload['brief'].get('proposed_previous_id') if payload.get('relation_status')=='linked_revision' else None
        with self.store.db() as db:
            row = db.execute('SELECT family FROM workflow_lineage WHERE brief_id=?',(previous,)).fetchone() if previous else None
            family = row['family'] if row else (previous or payload['id'])
            if previous:
                db.execute('INSERT OR IGNORE INTO workflow_lineage VALUES(?,?,NULL,?)',(previous,family,payload['created_at']-.001))
            db.execute('INSERT OR IGNORE INTO workflow_lineage VALUES(?,?,?,?)',(payload['id'],family,previous,payload['created_at']))
            if previous:
                db.execute("UPDATE workflow_versions SET state='superseded' WHERE family=? AND brief_id!=?",(family,payload['id']))

    def version(self, kind, export_id, payload):
        manifest = payload.get('reports') if kind=='pet_exports' else payload.get('report')
        if not manifest:
            return
        serialized = json.dumps(manifest,sort_keys=True,ensure_ascii=False)
        identity = hashlib.sha256((kind+export_id+serialized).encode()).hexdigest()
        state='awaiting_approval' if self.current(payload['brief_id']) else 'superseded'
        with self.store.db() as db:
            line = db.execute('SELECT family FROM workflow_lineage WHERE brief_id=?',(payload['brief_id'],)).fetchone()
            family = line['family'] if line else payload['brief_id']
            db.execute('INSERT OR IGNORE INTO workflow_versions VALUES(?,?,?,?,?,?,?,?)',
                       (identity,payload['brief_id'],family,kind,export_id,serialized,state,time.time()))

    def decide(self, identity, decision, note):
        if decision not in ('approved','rejected') or not isinstance(note,str) or not note.strip() or len(note)>1000:
            raise ValueError('Chọn quyết định và ghi lý do duyệt (1–1000 ký tự).')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM workflow_versions WHERE id=?',(identity,)).fetchone()
            if not row or row['state']=='superseded':
                raise ValueError('Phiên bản không tồn tại hoặc đã hết hiệu lực.')
            latest = db.execute('SELECT brief_id FROM workflow_lineage WHERE family=? ORDER BY created DESC,brief_id DESC LIMIT 1',(row['family'],)).fetchone()
            if latest and latest['brief_id']!=row['brief_id']:
                raise ValueError('Có hồ sơ mới; không duyệt phiên bản cũ.')
            if row['state']==decision:
                return {'stored':True,'unchanged':True}
            db.execute('UPDATE workflow_versions SET state=? WHERE id=?',(decision,identity))
            db.execute('INSERT INTO workflow_reviews(version_id,decision,note,created) VALUES(?,?,?,?)',(identity,decision,note.strip(),time.time()))
        return {'stored':True,'rip_allowed':False,'customer_send_allowed':False}

    def monitor(self, expected, now=None):
        now = time.time() if now is None else now
        self.index_versions()
        active = {}
        with self.store.db() as db:
            for service in expected:
                db.execute('INSERT OR IGNORE INTO workflow_beats VALUES(?,?)',(service,now))
            for r in db.execute('SELECT * FROM workflow_beats'):
                age = now-r['seen']
                threshold = 1200 if r['service']=='hub_worker' or r['service'].startswith('artwork:') else 300
                if age>threshold:
                    active['service:'+r['service']]={'code':'SERVICE_STALE','service':r['service'],'last_seen':r['seen'],'action':'Kiểm tra dịch vụ đang chạy; không phát lại tác vụ chưa rõ kết quả.'}
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('pet_exports','jpg_exports','intake_runs'):
                if table not in tables: continue
                for r in db.execute('SELECT id,state,created FROM '+table+" WHERE state IN ('queued','exporting','planning','sending','uncertain','evidence_ready')"):
                    if now-r['created']>1800:
                        active[table+':'+r['id']]={'code':'QUEUE_STALE','stage':table,'job_id':r['id'],'state':r['state'],
                                                  'action':'Đối chiếu kết quả thật trước khi chạy lại; uncertain không tự phát lại.'}
            for key,detail in active.items():
                db.execute('INSERT INTO workflow_alerts VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,detail=excluded.detail,updated=excluded.updated',
                           (key,'active',json.dumps(detail,ensure_ascii=False),now,now))
            for row in db.execute("SELECT id FROM workflow_alerts WHERE state='active'").fetchall():
                if row['id'] not in active:
                    db.execute("UPDATE workflow_alerts SET state='recovered',updated=? WHERE id=?",(now,row['id']))

    def index_versions(self):
        with self.store.db() as db:
            # Register existing completed exports for inspection without publishing or re-exporting them.
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rows=[]
            for kind in ('pet_exports','jpg_exports'):
                if kind in tables:
                    rows += [(kind,dict(r)) for r in db.execute('SELECT id,payload FROM '+kind+" WHERE state='done'")]
        for kind,row in rows:
            self.version(kind,row['id'],json.loads(row['payload']))

    def state(self):
        with self.store.db() as db:
            return {'services':[dict(r) for r in db.execute('SELECT * FROM workflow_beats')],
                    'alerts':[dict(r) for r in db.execute('SELECT * FROM workflow_alerts ORDER BY updated DESC LIMIT 200')],
                    'versions':[dict(r) for r in db.execute('SELECT * FROM workflow_versions ORDER BY created DESC LIMIT 300')],
                    'reviews':[dict(r) for r in db.execute('SELECT * FROM workflow_reviews ORDER BY id DESC LIMIT 300')]}
