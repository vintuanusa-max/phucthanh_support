"""Outbound ERP projection/commands; no order writes, no public messages, no RIP."""
import base64,hashlib,io,json,time
from pathlib import Path
import httpx
from PIL import Image
from hub.store import event_key

def thumbnail(raw,role,name):
    with Image.open(io.BytesIO(raw)) as im:
        im=im.convert('RGBA');im.thumbnail((700,700));out=io.BytesIO();im.save(out,format='PNG')
    raw=out.getvalue()
    return {'key':hashlib.sha256(raw).hexdigest(),'role':role,'name':name,'data':base64.b64encode(raw).decode()}

class OrderPrintBridge:
    def __init__(self,e):
        self.e=e;self.cache={}
        with e.store.db() as d:d.execute('CREATE TABLE IF NOT EXISTS erp_print_commands(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,last_state TEXT NOT NULL)')
        with e.store.db() as d:d.execute('CREATE TABLE IF NOT EXISTS erp_print_approvals(id TEXT PRIMARY KEY,account TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL)')
        with e.store.db() as d:d.execute('CREATE TABLE IF NOT EXISTS erp_print_brief_links(brief_id TEXT PRIMARY KEY,order_id TEXT NOT NULL,customer_id TEXT NOT NULL,evidence TEXT NOT NULL)')

    def approve(self,req,linked):
        rows=linked.get(req['order_id'],{}).get('rows',[])
        briefs={r['id'] for r in rows};files=[];accounts=set()
        with self.e.store.db() as d:
            old=d.execute('SELECT state,payload FROM erp_print_approvals WHERE id=?',(req['id'],)).fetchone()
            if old:return old['state'],json.loads(old['payload']).get('detail','Chờ copy TIFF')
            for identity in req['payload']['job_ids']:
                j=d.execute('SELECT * FROM pet_exports WHERE id=?',(identity,)).fetchone()
                kind='pet'
                if not j:
                    j=d.execute('SELECT * FROM jpg_exports WHERE id=?',(identity,)).fetchone();kind='jpg'
                if not j or j['state']!='done':raise ValueError('File chưa xuất xong')
                p=json.loads(j['payload'])
                if p['brief_id'] not in briefs or not self.e.artwork_checks.pet.workflow.current(p['brief_id']):raise ValueError('Hồ sơ không đúng đơn hoặc đã thay thế')
                accounts.add(j['account'])
                if not p.get('archive_relative'):raise ValueError('Thiếu thư mục bản gốc')
                if kind=='jpg':
                    report=p.get('report',{})
                    original=p.get('plan',{}).get('renderer')=='original_pdf_v1'
                    if not (report.get('original_pdf_verified') if original else report.get('native_ai_verified')) or not p.get('verification',{}).get('pass') or not report.get('panels'):raise ValueError('JPG/nguồn chưa xác minh')
                    from hub.approval_names import approved_jpg_name
                    source=p.get('source',{})
                    for panel in report['panels']:
                        if panel.get('mode')!='CMYK' or not panel.get('source_icc_preserved'):raise ValueError('JPG không giữ CMYK gốc')
                        name=approved_jpg_name(source['asset']['name'],source.get('thread_id'),panel['name'],len(report['panels'])>1)
                        item={'source':p['archive_relative']+'/'+panel['file'],'name':name,'group':p['archive_folder'],'sha256':panel['sha256'],'job_id':identity,'mode':'CMYK','icc_sha256':report['icc_sha256']}
                        if original:
                            item.update(original_source=p['archive_relative']+'/'+report['source_copy_file'],original_sha256=report['source_copy_sha256'])
                        else:
                            item.update(ai_source=p['archive_relative']+'/'+report['ai_file'],ai_sha256=report['ai_sha256'])
                        files.append(item)
                else:
                    if not p.get('reports'):raise ValueError('Thiếu TIFF đã xác minh')
                    for report in p['reports']:
                        files.append({'source':p['archive_relative']+'/'+report['name'],'name':report['name'],'group':p['archive_folder'],'sha256':report['sha256'],'job_id':identity})
            if len(accounts)!=1:raise ValueError('Vui lòng duyệt riêng theo từng kênh')
            payload={'files':files,'order_id':req['order_id'],'detail':'Chờ copy file ra thư mục khách'}
            d.execute('INSERT INTO erp_print_approvals VALUES(?,?,?,?)',(req['id'],accounts.pop(),'queued',json.dumps(payload)))
        return 'scheduled',payload['detail']

    def linked(self):
        from hub.print_linking import resolve
        with self.e.store.db() as d:return resolve(d)

    def project(self,oid,entry):
        briefs=[]
        for r in entry['rows'][:20]:
            p=json.loads(r['payload']);assets=[a for s in p.get('sources',[]) for a in s.get('assets',[])]
            jobs=[];images=[]
            with self.e.store.db() as d:
                for table in ('pet_exports','jpg_exports'):
                    for j in d.execute('SELECT id,state,payload FROM '+table+' WHERE account=? AND json_extract(payload,\'$.brief_id\')=?',(r['account'],r['id'])):
                        q=json.loads(j['payload']);jobs.append({'id':j['id'],'state':j['state'],'kind':table,'reason':q.get('review_reason',''),'files':q.get('files',[]),'archive_relative':q.get('archive_relative',''),'manual':bool(q.get('manual_export'))})
                        if table=='jpg_exports' and j['state']=='done':
                            for path in sorted((self.e.artwork_checks.jpg.root/j['id']).glob('*preview.png'))[:8]:
                                images.append(thumbnail(path.read_bytes(),'output',path.name))
                        if table=='pet_exports' and j['state']=='done':
                            for f in q.get('files',[])[:6]:
                                path=self.e.artwork_checks.pet.root/j['id']/f['name']
                                if path.is_file():images.append(thumbnail(path.read_bytes(),'output',f['name']))
            for src in p.get('sources',[]):
                for im in self.e.store.images(src.get('images',[])[:3]):
                    if len([i for i in images if i['role']=='source'])>=6:break
                    images.append(thumbnail(base64.b64decode(im['data']),'source','Tin '+src['message_id']))
            pdf=[a for a in assets if a.get('state')=='ready' and a.get('name','').lower().endswith(('.pdf','.ai'))]
            standalone=p.get('brief',{}).get('image_context')=='standalone_artwork'
            busy=any(j['state'] in ('scheduled','planning','queued','exporting','publishing','uncertain') for j in jobs)
            briefs.append({'id':r['id'],'title':p['brief']['title'],'conversation':r['conversation'],
                'sources':[{'name':a['name'],'path':a.get('relative_path',''),'state':a['state']} for a in assets],
                'jobs':jobs,'images':images[:12],'can_export':not busy and (standalone or len(pdf)==1),
                'export_hint':'Xuất từ artwork sẵn có; không vẽ lại.' if standalone or len(pdf)==1 else 'Chưa xác định artwork riêng; cần kiểm tra nguồn.',
                'missing':p['brief'].get('missing_fields',[])})
        if not briefs:
            briefs.append({'id':'unlinked:'+oid,'title':'Chờ nối đúng mẫu với đơn hàng','conversation':0,'sources':[],'jobs':[],'images':[],'can_export':False,'export_hint':'Chưa đủ bằng chứng nối mẫu riêng của đơn; không tự gán mẫu của đơn khác.','missing':['Cần đối chiếu tin/file nguồn theo từng mẫu.']})
        return {'order_id':oid,'customer_id':entry['customer_id'],'briefs':briefs}

    def schedule(self,req,linked):
        entry=linked.get(req['order_id'])
        r=next((r for r in entry['rows'] if r['id']==req['payload']['brief_id']),None) if entry else None
        if not r:raise ValueError('Không có liên kết duy nhất giữa đơn và hồ sơ')
        p=json.loads(r['payload']);manual=req['payload'];identity=event_key('erp-pet-manual-v1',req['id'])
        if not self.e.artwork_checks.pet.workflow.current(r['id']):raise ValueError('Hồ sơ đã được thay thế')
        from hub.order_policy import capture_allowed
        mapping=self.e.store.thread(account=r['account'],thread_id=r['thread_id']);policy=self.e.order_intake.policy(r['account'])
        if not mapping or not policy or not capture_allowed(policy,self.e.settings.inboxes[r['account']]['channel'],r['thread_id'],mapping['display_name']):raise ValueError('Nhóm không được phép xử lý')
        with self.e.store.db() as d:
            existing=d.execute('SELECT state FROM pet_exports WHERE id=?',(identity,)).fetchone()
            if existing:return identity,existing['state']
            existing=d.execute('SELECT state FROM artwork_checks WHERE id=?',(identity,)).fetchone()
            if existing:return identity,existing['state']
            busy=d.execute("SELECT id FROM pet_exports WHERE json_extract(payload,'$.brief_id')=? AND state IN ('scheduled','planning','queued','exporting','publishing','uncertain')",(r['id'],)).fetchone()
            if busy:raise ValueError('Đang có lượt xuất hoặc kết quả chưa xác định; không chạy thêm')
            pdf=[(s,a) for s in p['sources'] for a in s.get('assets',[]) if a.get('state')=='ready' and a['name'].lower().endswith(('.pdf','.ai'))]
            if pdf:
                if len(pdf)!=1:raise ValueError('Nhiều file gốc: cần chọn đúng phiên bản trước')
                src,a=pdf[0];q={'brief_id':r['id'],'conversation':r['conversation'],'thread_id':r['thread_id'],'source_message_id':src['message_id'],'asset':a,'relation':'brief_source','reference_assets':[],'manual_export':manual}
                d.execute("INSERT INTO artwork_checks(id,brief_id,account,state,payload,created) VALUES(?,?,?,'awaiting_upload',?,?)",(identity,r['id'],r['account'],json.dumps(q),time.time()))
            else:
                if p['brief'].get('image_context')!='standalone_artwork':raise ValueError('Chỉ xuất artwork riêng, không lấy toàn ảnh sản phẩm')
                q={'brief_id':r['id'],'conversation':r['conversation'],'private':True,'auto_rip':False,'mirror':False,'manual_export':manual}
                d.execute("INSERT INTO pet_exports VALUES(?,?,'scheduled',?,?)",(identity,r['account'],json.dumps(q),time.time()))
                d.execute("INSERT OR IGNORE INTO jobs(id,kind,payload,created) VALUES(?,'raster_pet',?,?)",('raster:'+identity,json.dumps({'id':identity}),time.time()))
        return identity,'scheduled'

    def tick(self):
        linked=self.linked();root=self.e.settings.erp_url.rstrip('/')+'/api/v1/integrations/zalo/print-files'
        with httpx.Client(timeout=15,trust_env=False,headers={'X-Zalo-Token':self.e.settings.erp_token}) as c:
            response=c.get(root+'/requests')
            if response.status_code==404:return # ERP owner has not restarted yet.
            response.raise_for_status()
            for req in response.json()['items']:
                try:
                    if req['payload'].get('action')=='approve':
                        state,detail=self.approve(req,linked);receipt={'state':'scheduled' if state=='queued' else state,'detail':detail}
                    else:
                        identity,state=self.schedule(req,linked)
                        receipt={'state':'done' if state=='done' else 'scheduled','detail':'Công việc '+identity}
                        with self.e.store.db() as d:d.execute('INSERT OR IGNORE INTO erp_print_commands VALUES(?,?,?)',(req['id'],identity,''))
                except ValueError as exc:receipt={'state':'review','detail':str(exc)}
                c.post(root+'/requests/'+req['id'],json=receipt).raise_for_status()
            with self.e.store.db() as d:commands=d.execute('SELECT * FROM erp_print_commands').fetchall()
            for cmd in commands:
                with self.e.store.db() as d:
                    job=d.execute('SELECT state FROM pet_exports WHERE id=?',(cmd['job_id'],)).fetchone()
                    if not job:job=d.execute('SELECT state FROM artwork_checks WHERE id=?',(cmd['job_id'],)).fetchone()
                state=job['state'] if job else 'review'
                state=state if state in ('done','review','uncertain') else 'scheduled'
                if state==cmd['last_state']:continue
                c.post(root+'/requests/'+cmd['id'],json={'state':state,'detail':'Công việc '+cmd['job_id']}).raise_for_status()
                with self.e.store.db() as d:d.execute('UPDATE erp_print_commands SET last_state=? WHERE id=?',(state,cmd['id']))
            with self.e.store.db() as d:approvals=d.execute("SELECT * FROM erp_print_approvals WHERE state IN ('done','review')").fetchall()
            for a in approvals:
                p=json.loads(a['payload'])
                if p.get('reported'):continue
                c.post(root+'/requests/'+a['id'],json={'state':a['state'],'detail':p.get('detail','')[:1000]}).raise_for_status()
                p['reported']=True
                with self.e.store.db() as d:d.execute('UPDATE erp_print_approvals SET payload=? WHERE id=?',(json.dumps(p),a['id']))
            for oid,entry in linked.items():
                p=self.project(oid,entry);digest=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()
                if self.cache.get(oid)==digest:continue
                response=c.post(root+'/snapshot',json=p)
                if response.status_code in (404,409):continue # deleted/reassigned, never resurrect.
                response.raise_for_status();self.cache[oid]=digest

