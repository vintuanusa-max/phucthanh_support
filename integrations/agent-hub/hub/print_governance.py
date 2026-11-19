"""Versioned print plans and approved precedents. Never writes ERP orders."""
import copy
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

TABLES=('jpg_exports','pet_exports')
ACTIVE={'preparing','planning','scheduled','queued','exporting','publishing','uncertain'}
ENGINE_VERSION='print-plan-v1-20261026'
RULE_CATALOG=[
 {'id':'pet-native','when':'PET: group được đối chiếu đúng maket','action':'Giữ kích thước nguồn, cắt sát artwork, giữ chi tiết trắng/nền logo; PNG/TIFF + AI editable, không cữ túi.'},
 {'id':'joined','when':'Phiếu/maket xác nhận túi liền hai mặt','action':'Một tấm sau co; đặt riêng từng mặt, mặt sau xoay180°, giữ kích thước artwork và tràn.'},
 {'id':'separate','when':'Mặt rời hoặc một mặt đã xác nhận','action':'Xuất từng phần riêng; không tự nhân đôi hoặc chia chiều dài thiếu căn cứ.'},
 {'id':'continuous','when':'Sọc/hoa văn trải liền toàn tấm','action':'Dùng nền liên tục, logo độc lập. Giữ nền trắng trong logo; bù bề rộng trắng theo sọc đã đo.'},
 {'id':'plain-white','when':'Nền vải trắng','action':'Không lấy lớp nền mô phỏng; giữ mảng trắng thuộc logo.'},
 {'id':'offsets','when':'Maket có mốc cữ trong group','action':'Canh theo object tham chiếu bên trong; giữ group ngoài và tràn. Miệng trống mặc định5cm; không tự cộng đường may0.5.'},
 {'id':'meter','when':'In mét','action':'Không dấu định vị. Hoa văn phải xác minh bước lặp và hướng; không ép cao20cm.'},
 {'id':'partial','when':'Một số phần đủ nguồn, một số thiếu','action':'Xuất phần đủ nguồn trước; phần thiếu ghi nội bộ, không tự vẽ bù.'}]

def rule_version(conf):return ENGINE_VERSION+':'+str(conf['revision'])

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def compact(value):
    if isinstance(value,dict):
        return {k:compact(v) for k,v in value.items() if k not in ('preview','data','image','images','inline_data')}
    if isinstance(value,list):return [compact(v) for v in value]
    return value

def init(store):
    with store.db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS print_plan_versions(id TEXT PRIMARY KEY,job_id TEXT,kind TEXT,brief_id TEXT,scope TEXT,source_hash TEXT,evidence_hash TEXT,rule_version TEXT,plan TEXT,state TEXT,created REAL);
        CREATE INDEX IF NOT EXISTS print_plan_brief ON print_plan_versions(brief_id,created);
        CREATE TABLE IF NOT EXISTS print_plan_actions(id TEXT PRIMARY KEY,brief_id TEXT,action TEXT,payload TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS print_settings(id INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT,created REAL);
        ''')
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM print_settings').fetchone():
            value={'revision':1,'enabled':True,'rules':{'mouth_blank_cm':5,'white_backing_extra_stripes':1,'preserve_native_artwork':True,'pet_bag_offsets':False},
                   'stages':{name:{'primary':'','fallback':'','attempts':2,'enabled':True} for name in ('classify','localize','select','layout','verify','other')},
                   'max_output_tokens':12000,'daily_call_limit':200,'cache_enabled':True}
            db.execute('INSERT INTO print_settings(payload,created) VALUES(?,?)',(json.dumps(value),time.time()))

def settings(store):
    init(store)
    with store.db() as db:r=db.execute('SELECT id,payload FROM print_settings ORDER BY id DESC LIMIT 1').fetchone()
    return dict({'source_wait_minutes':15},**dict(json.loads(r['payload']),revision=r['id']))

def update_settings(store,value):
    init(store);old=settings(store);new=copy.deepcopy(old)
    if 'restore_revision' in value:
        with store.db() as db:r=db.execute('SELECT payload FROM print_settings WHERE id=?',(value['restore_revision'],)).fetchone()
        if not r:raise ValueError('Không có phiên bản cấu hình')
        new=json.loads(r['payload'])
    else:
        for key in ('enabled','cache_enabled'):
            if key in value:
                if type(value[key]) is not bool:raise ValueError('Cấu hình bật/tắt không hợp lệ')
                new[key]=value[key]
        for key,low,high in [('source_wait_minutes',1,120),('daily_call_limit',1,10000),('max_output_tokens',1024,16000)]:
            if key in value:
                if type(value[key]) is not int or not low<=value[key]<=high:raise ValueError('Giới hạn không hợp lệ')
                new[key]=value[key]
        if 'stages' in value:
            for stage,conf in value['stages'].items():
                if stage not in new['stages']:raise ValueError('Bước không hợp lệ')
                if set(conf)-{'primary','fallback','attempts','enabled'}:raise ValueError('Trường model không hợp lệ')
                c=dict(new['stages'][stage],**conf)
                for key in ('primary','fallback'):
                    if c[key] not in ('','gemini-2.5-pro','gemini-2.5-flash'):raise ValueError('Model chưa được hỗ trợ trong pipeline này')
                if type(c['enabled']) is not bool or type(c['attempts']) is not int or not 1<=c['attempts']<=2:raise ValueError('Cấu hình model không hợp lệ')
                new['stages'][stage]=c
        if 'rules' in value:
            r=value['rules'];allowed={'mouth_blank_cm','white_backing_extra_stripes'}
            if set(r)-allowed:raise ValueError('Quy tắc an toàn này cần sửa code và kiểm thử, không đổi trực tiếp')
            for k,v in r.items():
                if type(v) not in (int,float) or not 0<=v<= (10 if k=='mouth_blank_cm' else 2):raise ValueError('Thông số quy tắc ngoài phạm vi')
                new['rules'][k]=v
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT max(id) FROM print_settings').fetchone()[0]
        if value.get('expected_revision')!=current:raise ValueError('Cấu hình đã đổi; tải lại trước khi lưu')
        db.execute('INSERT INTO print_settings(payload,created) VALUES(?,?)',(json.dumps(new),time.time()))
    return settings(store)

def evidence(store,bid):
    with store.db() as db:r=db.execute('SELECT account,thread_id,payload FROM design_briefs WHERE id=?',(bid,)).fetchone()
    if not r:raise ValueError('Không có hồ sơ nguồn')
    p=json.loads(r['payload']);b=p.get('brief',{})
    # Exact reuse includes the full interpreted brief. Conservative false negatives
    # are preferable to matching names or accidentally ignoring a new instruction.
    assets=sorted({a.get('sha256') for s in p.get('sources',[]) for a in s.get('assets',[]) if a.get('sha256')})
    images=sorted(digest(s.get('images',[])) for s in p.get('sources',[]) if s.get('images'))
    normalized={k:v for k,v in b.items() if k not in ('source_message_ids','proposed_previous_id','resolved_missing_fields','replaces_requirement_message_ids')}
    normalized=copy.deepcopy(normalized)
    for req in normalized.get('requirements',[]):
        if isinstance(req,dict):req.pop('message_id',None)
    text=[{k:s[k] for k in ('text','content','body','caption','owner_instruction') if k in s} for s in p.get('sources',[])]
    return str(r['account'])+':'+str(r['thread_id']),digest({'brief':normalized,'assets':assets,'images':images,'messages':text})

def record(store,kind,jid,p,state):
    if kind not in TABLES or not p.get('plan') or not p.get('brief_id'):return
    init(store);scope,eh=evidence(store,p['brief_id']);rule=p.get('rule_version') or 'legacy_unversioned'
    source=p.get('source',{}).get('asset',{}).get('sha256') or p['plan'].get('source_sha256','')
    identity=digest([kind,jid,p['plan'],rule]);serialized=json.dumps(p['plan'],ensure_ascii=False)
    with store.db() as db:
        db.execute('INSERT OR IGNORE INTO print_plan_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(identity,jid,kind,p['brief_id'],scope,source,eh,rule,serialized,state,time.time()))
        db.execute('UPDATE print_plan_versions SET state=? WHERE id=? AND state NOT IN (\'approved\',\'rejected\')',(state,identity))
    return identity

def is_approved(db,kind,jid):
    # Approval is explicit, never inferred from successful export/AI verification.
    return bool(db.execute("SELECT 1 FROM workflow_versions WHERE kind=? AND export_id=? AND state='approved'",(kind,jid)).fetchone())

def bind_rules(store,p):
    if not p.get('plan') or p.get('rule_version'):return
    conf=settings(store);p['rule_version']=rule_version(conf);p['rule_snapshot']=conf['rules']
    for panel in p['plan'].get('panels',[]):
        panel['white_backing_extra_stripes']=conf['rules']['white_backing_extra_stripes']
        for c in panel.get('components',[]):
            if c.get('mouth_allowance_source')=='blank':
                new=conf['rules']['mouth_blank_cm'];delta=new-c.get('mouth_allowance_cm',5)
                c['mouth_allowance_cm']=new;c['y_cm']+=delta
                if c['y_cm']<0:raise ValueError('Cữ âm sau áp dụng quy tắc')

def reusable(store,bid,source_hash,kind):
    init(store);scope,eh=evidence(store,bid);revision=rule_version(settings(store))
    with store.db() as db:
        rows=db.execute('SELECT * FROM print_plan_versions WHERE scope=? AND evidence_hash=? AND source_hash=? AND kind=? AND rule_version=? ORDER BY created DESC',(scope,eh,source_hash,kind,revision)).fetchall()
        for r in rows:
            if is_approved(db,kind,r['job_id']):return {'plan':json.loads(r['plan']),'derived_from':r['job_id'],'rule_version':revision,'reuse_reason':'exact_source_requirements_rules_approved'}
    return None

def matches(store,version):
    with store.db() as db:
        rows=db.execute('SELECT * FROM print_plan_versions WHERE scope=? AND job_id!=? ORDER BY created DESC LIMIT 200',(version['scope'],version['job_id'])).fetchall()
        out=[];seen=set()
        for r in rows:
            if (r['kind'],r['job_id']) in seen or not is_approved(db,r['kind'],r['job_id']):continue
            seen.add((r['kind'],r['job_id']))
            exact=bool(r['source_hash'] and r['source_hash']==version['source_hash'] and r['evidence_hash']==version['evidence_hash'] and r['rule_version']==version['rule_version'] and r['kind']==version['kind'] and digest(json.loads(r['plan']))==digest(json.loads(version['plan'])))
            old=json.loads(r['plan']);new=json.loads(version['plan'])
            if r['kind']!=version['kind']:continue
            changes=diff_plan(old,new)
            same_layout=layout_signature(old)==layout_signature(new)
            if not same_layout and r['source_hash']!=version['source_hash']:continue
            out.append({'id':r['id'],'job_id':r['job_id'],'kind':r['kind'],'match':'exact' if exact else 'similar_layout','source_same':r['source_hash']==version['source_hash'],'rules_same':r['rule_version']==version['rule_version'],'changed_fields':changes[:40],'approved':True,'same_layout':same_layout})
    return sorted(out,key=lambda x:(x['match']=='exact',x['source_same'],x['same_layout']),reverse=True)[:10]

def layout_signature(plan):
    return digest([{'construction':p.get('construction'), 'output':p.get('output_cm'),
      'background':p.get('background_mode'), 'sides':[c.get('side') for c in p.get('components',[])],
      'side':p.get('side'), 'dimensions':[p.get('width_cm'),p.get('height_cm')]}
      for p in plan.get('panels',plan.get('faces',[]))])

def diff_plan(old,new,path=''):
    if old==new:return []
    if isinstance(old,dict) and isinstance(new,dict):
        return [v for k in sorted(set(old)|set(new)) for v in diff_plan(old.get(k),new.get(k),path+'.'+k)]
    if isinstance(old,list) and isinstance(new,list) and len(old)==len(new):
        return [v for i,(a,b) in enumerate(zip(old,new)) for v in diff_plan(a,b,path+'['+str(i)+']')]
    return [path.lstrip('.')]

def reusable_pet(store,bid,source_hash,context):
    """Reuse selection only when ALL exported positions in the batch were approved."""
    candidate=reusable(store,bid,source_hash,'pet_exports')
    if not candidate:return None
    recipe=candidate['plan'].get('selection_recipe')
    if not recipe or recipe.get('context_hash')!=digest(context):return None
    with store.db() as db:
        batch=db.execute('SELECT payload FROM native_selections WHERE id=?',(recipe['batch_id'],)).fetchone()
        children=json.loads(batch['payload']).get('children',[]) if batch else []
        if not children or not all(is_approved(db,'pet_exports',child) for child in children):return None
    return copy.deepcopy(recipe['plan'])

def detail(e,bid):
    init(e.store)
    # Lazily index existing jobs for display, never enqueue or approve history.
    live_by_job={}
    with e.store.db() as db:
        rows=[(t,dict(r)) for t in TABLES for r in db.execute('SELECT * FROM '+t+" WHERE json_extract(payload,'$.brief_id')=?",(bid,))]
    for t,r in rows:
        p_obj=json.loads(r['payload'])
        live_by_job[(t,r['id'])]={'state':r['state'],'payload':p_obj}
        record(e.store,t,r['id'],p_obj,r['state'])
    with e.store.db() as db:
        versions=[dict(r) for r in db.execute('SELECT * FROM print_plan_versions WHERE brief_id=? ORDER BY created DESC',(bid,))]
        history=[dict(r) for r in db.execute('SELECT id,action,created,payload FROM print_plan_actions WHERE brief_id=? ORDER BY created DESC LIMIT 30',(bid,))]
        for v in versions:v['approved']=is_approved(db,v['kind'],v['job_id'])
    for v in versions:
        v['matches']=matches(e.store,v);v['plan_hash']=digest(json.loads(v['plan']));v['plan']=compact(json.loads(v['plan']))
        live=live_by_job.get((v['kind'],v['job_id'])) or {}
        lp=live.get('payload') or {}
        v['live_state']=live.get('state',v['state'])
        v['is_draft_plan']=bool(lp.get('is_draft_plan') or v['plan'].get('is_draft_plan'))
        v['technical_verified']=bool(lp.get('technical_verified'))
        v['awaiting_verify_approval']=bool(lp.get('awaiting_verify_approval'))
        raw_ver=lp.get('verification')
        raw_rep=lp.get('report')
        if isinstance(raw_ver,dict) and ('checks' in raw_ver or 'reports' in raw_ver):
            v['verification']=raw_ver
        elif raw_ver or raw_rep:
            v['verification']={
                'reports':[raw_rep] if isinstance(raw_rep,dict) else (raw_rep if isinstance(raw_rep,list) else []),
                'checks':[raw_ver] if isinstance(raw_ver,dict) else [],
            }
        else:
            v['verification']=None
        v['archive_relative']=lp.get('archive_relative','')
        v['review_reason']=lp.get('review_reason','')
    return {'versions':versions,'history':history,'rule_revision':rule_version(settings(e.store)),'rules':RULE_CATALOG}

def _load_known_objects(e, bid, jid, plan, source_sha):
    known = {}
    for panel in plan.get('panels', []):
        for o in panel.get('objects', []):
            if isinstance(o, dict) and o.get('id'):
                known[o['id']] = {k: v for k, v in o.items() if k != 'preview'}
    root_checks = Path(e.store.path).parent / 'artwork-checks'
    cand_paths = [root_checks / jid / 'native-groups.json']
    with e.store.db() as db:
        for r in db.execute('SELECT id, payload FROM artwork_checks WHERE brief_id=? ORDER BY created DESC', (bid,)):
            cp = json.loads(r['payload'])
            if not source_sha or cp.get('asset', {}).get('sha256') == source_sha:
                cand_paths.append(root_checks / r['id'] / 'native-groups.json')
    for ng_path in cand_paths:
        if ng_path.is_file():
            try:
                ng = json.loads(ng_path.read_text(encoding='utf-8'))
                for c in ng.get('candidates', []):
                    if isinstance(c, dict) and c.get('id') and c['id'] not in known:
                        known[c['id']] = {k: v for k, v in c.items() if k != 'preview'} | {'page': 1, 'native': True}
            except Exception:
                pass
    return known

def retry(e,bid,data):
    """Only resume a verified export plan; never replay uncertain publication."""
    from hub.dispatch_control import jobs,ACTIVE as BUSY
    from hub.order_policy import capture_allowed
    kind=data.get('kind');jid=data.get('job_id');note=str(data.get('note','')).strip()
    if kind not in TABLES or not 5<=len(note)<=3000:raise ValueError('Chọn lượt xuất và ghi yêu cầu từ5–3000 ký tự')
    init(e.store)
    with e.store.db() as db:
        row=db.execute('SELECT * FROM '+kind+' WHERE id=?',(jid,)).fetchone()
        brief=db.execute('SELECT * FROM design_briefs WHERE id=?',(bid,)).fetchone()
    if not row or not brief:raise ValueError('Không có lượt xuất')
    p=json.loads(row['payload'])
    if p.get('brief_id')!=bid or row['state'] not in ('review','done') or not p.get('plan'):raise ValueError('Chỉ chạy lại bản có phương án và kết quả xác định')
    if kind=='jpg_exports' and not (p.get('export_plan_ready') or p.get('is_draft_plan')) and not (row['state']=='done' and p.get('report')):raise ValueError('Phương án chưa qua kiểm tra để xuất; cần chạy bước phân tích nguồn')

    if p.get('publication_started') or row['state']=='uncertain':raise ValueError('Cần đối chiếu gửi preview trước khi chạy lại')
    if data.get('expected_plan')!=digest(p['plan']):raise ValueError('Phương án đã đổi; tải lại trước khi điều chỉnh')
    patch=data.get('adjustments',[])
    if kind!='jpg_exports' and patch:raise ValueError('PET: dùng chọn lại artwork/kích thước trong công cụ Illustrator hiện có')
    plan=copy.deepcopy(p['plan'])
    plan.pop('is_draft_plan',None)
    source_sha = p.get('source', {}).get('asset', {}).get('sha256') or plan.get('source_sha256', '')
    known_objs = _load_known_objects(e, bid, jid, plan, source_sha) if kind == 'jpg_exports' else {}
    allowed_keys = {
        'panel', 'component',
        'x_cm', 'y_cm', 'width_cm', 'horizontal_alignment',
        'raw_width_cm', 'raw_height_cm', 'output_width_cm', 'output_height_cm',
        'product_type', 'material', 'shrink_compensation',
        'background_mode', 'background_cmyk',
        'object_ids', 'background_object_id', 'clip_to_artboard',
    }
    allowed_bg_modes = {'none', 'solid_cmyk', 'preserve_source', 'registered_per_face', 'continuous_stripes', 'full_artboard_pattern'}
    from hub.shrinkage_config import calculate_artboard_size
    for change in patch:
        if not isinstance(change, dict) or set(change) - allowed_keys:
            raise ValueError('Chỉ chỉnh kích thước, cữ in, căn lề hoặc màu nền CMYK hợp lệ')
        try:
            if type(change.get('panel')) is not int or change['panel'] < 0:
                raise ValueError()
            panel = plan['panels'][change['panel']]
        except (KeyError, IndexError, ValueError, TypeError):
            raise ValueError('Không tìm thấy phần in')
        if 'clip_to_artboard' in change:
            if type(change['clip_to_artboard']) is not bool:
                raise ValueError('Cấu hình cắt tràn viền không hợp lệ')
            panel['clip_to_artboard'] = change['clip_to_artboard']
        if 'background_object_id' in change:
            bg_id = str(change.get('background_object_id') or '').strip()
            if bg_id and not re.fullmatch(r'\d+(?:\.\d+)+', bg_id):
                raise ValueError('ID đối tượng nền không hợp lệ (ví dụ: 0.1)')
            panel['background_object_id'] = bg_id
            if bg_id and bg_id in known_objs and bg_id not in {o.get('id') for o in panel.get('objects', [])}:
                panel.setdefault('objects', []).append(copy.deepcopy(known_objs[bg_id]))
        if panel.get('kind') == 'bag_panel' and panel.get('edge_finish') in ('unknown', '', None):
            panel['edge_finish'] = 'fold'
            panel['seam_allowance_cm'] = 0
            if not panel.get('edge_finish_evidence'):
                panel['edge_finish_evidence'] = 'Mặc định gấp miệng (fold, seam=0) theo quy chuẩn xưởng'
        if 'raw_width_cm' in change or 'raw_height_cm' in change:
            raw_w = change.get('raw_width_cm', panel.get('width_cm'))
            raw_h = change.get('raw_height_cm', panel.get('height_cm'))
            if type(raw_w) not in (int, float) or type(raw_h) not in (int, float) or not (0 < raw_w <= 10000 and 0 < raw_h <= 10000):
                raise ValueError('Kích thước khổ vải gốc không hợp lệ')
            out_w, out_h = calculate_artboard_size(
                float(raw_w), float(raw_h),
                basis='raw_fabric',
                kind=panel.get('kind', 'bag'),
                product_type=str(change.get('product_type', 'bag')),
                material=str(change.get('material', 'canvas')),
                shrink_compensation=float(change.get('shrink_compensation', 0.0)),
            )
            panel['width_cm'] = round(float(raw_w), 2)
            panel['height_cm'] = round(float(raw_h), 2)
            panel['output_cm'] = [out_w, out_h]
        if 'output_width_cm' in change or 'output_height_cm' in change:
            cur_out = panel.get('output_cm') or [panel.get('width_cm', 0), panel.get('height_cm', 0)]
            out_w = change.get('output_width_cm', cur_out[0])
            out_h = change.get('output_height_cm', cur_out[1])
            if type(out_w) not in (int, float) or type(out_h) not in (int, float) or not (0 < out_w <= 10000 and 0 < out_h <= 10000):
                raise ValueError('Kích thước artboard xuất không hợp lệ')
            panel['output_cm'] = [round(float(out_w), 2), round(float(out_h), 2)]
        if 'background_mode' in change or 'background_cmyk' in change:
            bg_mode = change.get('background_mode', 'solid_cmyk' if 'background_cmyk' in change else panel.get('background_mode', 'preserve_source'))
            if bg_mode not in allowed_bg_modes:
                raise ValueError('Chế độ nền không hợp lệ')
            if bg_mode == 'solid_cmyk':
                cmyk = change.get('background_cmyk', panel.get('background_cmyk'))
                if not isinstance(cmyk, (list, tuple)) or len(cmyk) != 4 or any(type(v) not in (int, float) or not (0.0 <= float(v) <= 100.0) for v in cmyk):
                    raise ValueError('Màu nền CMYK phải gồm 4 kênh [C, M, Y, K] từ 0 đến 100%')
                panel['background_mode'] = 'solid_cmyk'
                panel['background_cmyk'] = [round(float(v), 2) for v in cmyk]
            elif bg_mode == 'none':
                panel['background_mode'] = 'none'
                panel.pop('background_object_id', None)
                panel.pop('background_cmyk', None)
            elif bg_mode == 'preserve_source':
                panel.pop('background_cmyk', None)
                if panel.get('background_mode') in ('solid_cmyk', 'none'):
                    panel.pop('background_mode', None)
            else:
                panel['background_mode'] = bg_mode
        if 'component' in change and change['component'] is not None:
            try:
                if type(change['component']) is not int or change['component'] < 0:
                    raise ValueError()
                c = panel['components'][change['component']]
            except (KeyError, IndexError, ValueError, TypeError):
                raise ValueError('Không tìm thấy phần in')
            if 'object_ids' in change:
                raw_oids = change['object_ids']
                oid_list = [x.strip() for x in (raw_oids.split(',') if isinstance(raw_oids, str) else (raw_oids if isinstance(raw_oids, list) else [])) if isinstance(x, str) and x.strip()]
                if not oid_list or any(not re.fullmatch(r'\d+(?:\.\d+)+', x) for x in oid_list):
                    raise ValueError('Danh sách ID group artwork không hợp lệ (ví dụ: 0.18)')
                c['object_ids'] = oid_list
                existing_obj_ids = {o.get('id') for o in panel.get('objects', [])}
                for oid in oid_list:
                    if oid in known_objs and oid not in existing_obj_ids:
                        panel.setdefault('objects', []).append(copy.deepcopy(known_objs[oid]))
                        existing_obj_ids.add(oid)
                if 'width_cm' not in change:
                    src_objs = [known_objs[oid] for oid in oid_list if oid in known_objs and isinstance(known_objs[oid].get('bounds'), list) and len(known_objs[oid]['bounds']) == 4]
                    if src_objs:
                        b = [o['bounds'] for o in src_objs]
                        c['width_cm'] = round((max(x[2] for x in b) - min(x[0] for x in b)) * 2.54 / 72, 2)
            allow_bleed = bool(c.get('preserve_source_bleed') or panel.get('clip_to_artboard') or c.get('clip_to_artboard'))
            if 'width_cm' in change:
                w_val = change['width_cm']
                max_w = panel['output_cm'][0] * 2 if allow_bleed else panel['output_cm'][0]
                if type(w_val) not in (int, float) or not (0 < w_val <= max_w):
                    raise ValueError('Chiều rộng artwork vượt khổ hoặc không hợp lệ')
                c['width_cm'] = round(float(w_val), 2)
            for key in ('x_cm', 'y_cm'):
                if key in change:
                    val = change[key]
                    if type(val) not in (int, float) or not (-panel['output_cm'][0] if allow_bleed else 0) <= val <= max(panel['output_cm']):
                        raise ValueError('Cữ ngoài khổ')
                    c[key] = round(float(val), 2)
            if 'horizontal_alignment' in change:
                if change['horizontal_alignment'] not in ('left', 'center'):
                    raise ValueError('Căn ngang không hợp lệ')
                c['horizontal_alignment'] = change['horizontal_alignment']
            if c.get('horizontal_alignment') == 'center':
                c['x_cm'] = (panel['output_cm'][0] - c['width_cm']) / 2
            if not allow_bleed:
                if c['x_cm'] + c['width_cm'] > panel['output_cm'][0] + 1e-4:
                    raise ValueError('Artwork vượt khổ')
                if c['y_cm'] + c.get('height_cm', 0) > panel['output_cm'][1] + 1e-4:
                    raise ValueError('Artwork vượt chiều cao khổ')
            else:
                if c['x_cm'] >= panel['output_cm'][0] or c['x_cm'] + c['width_cm'] <= 0 or c['y_cm'] >= panel['output_cm'][1]:
                    raise ValueError('Artwork tràn không giao với khổ xuất')
        else:
            for c in panel.get('components', []):
                allow_bleed = bool(c.get('preserve_source_bleed') or panel.get('clip_to_artboard') or c.get('clip_to_artboard'))
                if c.get('horizontal_alignment') == 'center':
                    c['x_cm'] = (panel['output_cm'][0] - c['width_cm']) / 2
                if not allow_bleed:
                    if c['x_cm'] + c['width_cm'] > panel['output_cm'][0] + 1e-4:
                        raise ValueError('Artwork vượt khổ')
                    if c['y_cm'] + c.get('height_cm', 0) > panel['output_cm'][1] + 1e-4:
                        raise ValueError('Artwork vượt chiều cao khổ')
                else:
                    if c['x_cm'] >= panel['output_cm'][0] or c['x_cm'] + c['width_cm'] <= 0 or c['y_cm'] >= panel['output_cm'][1]:
                        raise ValueError('Artwork tràn không giao với khổ xuất')
    plan.pop('is_draft_plan', None)
    plan['issues'] = []
    identity=digest(['controlled-retry-v1',bid,kind,jid,plan,note])
    revision=p.get('rule_version','legacy_unversioned')
    with e.store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        native_busy=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_selections'").fetchone() and db.execute("SELECT 1 FROM native_selections WHERE brief_id=? AND (state IN ('scan_queued','scan_running','render_queued','render_running','png_check_queued','uncertain') OR json_extract(payload,'$.auto_status') IN ('planning','verifying','waiting_verify','waiting_scan'))",(bid,)).fetchone()
        if native_busy or any(j['state'] in BUSY|ACTIVE for j in jobs(db,bid)):raise ValueError('Có lượt đang chạy/chưa rõ kết quả')
        if db.execute('SELECT 1 FROM print_plan_actions WHERE id=?',(identity,)).fetchone():
            identity=digest(['controlled-retry-v1',bid,kind,jid,plan,note,time.time()])
        latest=db.execute('SELECT payload,state FROM '+kind+' WHERE id=?',(jid,)).fetchone()
        if latest['state'] not in ('review','done') or digest(json.loads(latest['payload']).get('plan'))!=data['expected_plan']:raise ValueError('Phương án đã đổi trong lúc thao tác')
        # PET rerender requires the original PNG files; do not fabricate a new queue.
        if kind=='pet_exports':raise ValueError('Dùng nút xuất lại PNG/TIFF từ cụm đã chọn; không tái dùng TIFF chưa xác minh')
        source=p.get('source',{}).get('asset',{});current=json.loads(brief['payload'])
        if source.get('sha256') not in {a.get('sha256') for s in current.get('sources',[]) for a in s.get('assets',[])}:raise ValueError('Nguồn không còn thuộc hồ sơ')
        fresh={k:copy.deepcopy(p[k]) for k in ('source','brief_id','archive_folder','conversation','catalog','part_table','rule_snapshot') if k in p}
        fresh.update(plan=plan,private=True,auto_rip=False,rule_version=revision,derived_from=jid,owner_instruction=note)
        fresh['export_plan_ready']=True
        from hub.jpg_exports import output_directory
        fresh['archive_relative']=output_directory(fresh['archive_folder'],plan['order_code'],identity,time.time())
        db.execute('INSERT INTO jpg_exports VALUES(?,?,?,?,?)',(identity,row['account'],'preparing',json.dumps(fresh),time.time()))
        db.execute('INSERT INTO print_plan_actions VALUES(?,?,?,?,?)',(identity,bid,'retry_export',json.dumps({'parent':jid,'adjustments':patch,'note':note}),time.time()))
    root=e.artwork_checks.jpg.root;dest=root/identity
    try:
        dest.mkdir(exist_ok=True)
        src_ctx = root/jid/'context.json'
        context = json.loads(src_ctx.read_text(encoding='utf-8')) if src_ctx.is_file() else []
        context.append({'text':'OWNER_APPROVED_PLAN_ADJUSTMENTS: '+json.dumps(patch,ensure_ascii=False)+'. Chủ xưởng sửa cữ tại điều phối; đối chiếu phương án mới cho các cữ này. Các phần khác vẫn theo nguồn.'})
        (dest/'context.json').write_text(json.dumps(context,ensure_ascii=False),encoding='utf-8')
    except (OSError,ValueError,AttributeError):
        fresh['review_reason']='Thiếu/không đọc được context.json; cần đọc lại nguồn. Chưa xếp hàng xuất.'
        with e.store.db() as db:db.execute("UPDATE jpg_exports SET state='review',payload=? WHERE id=?",(json.dumps(fresh),identity))
        raise ValueError('Thiếu ngữ cảnh để kiểm tra preview; chưa xếp hàng xuất')
    with e.store.db() as db:db.execute("UPDATE jpg_exports SET state='queued' WHERE id=?",(identity,))
    record(e.store,kind,identity,fresh,'queued')
    return {'id':identity,'message':'Đã xếp hàng xuất từ phương án; không gọi lại AI phân tích. Preview vẫn chờ duyệt nội bộ.'}

def approve_verified_output(e, bid, data):
    """Step 6 operator approval when technical verification passed but AI flagged visual review."""
    kind = data.get('kind', 'jpg_exports')
    jid = data.get('job_id')
    note = str(data.get('note', '')).strip()
    if kind != 'jpg_exports' or not jid or not 5 <= len(note) <= 1000:
        raise ValueError('Chọn bản xuất JPG và ghi căn cứ duyệt từ 5–1000 ký tự')
    init(e.store)
    with e.store.db() as db:
        row = db.execute('SELECT * FROM jpg_exports WHERE id=?', (jid,)).fetchone()
    if not row or row['state'] != 'review':
        raise ValueError('Chỉ duyệt bản xuất đang chờ kiểm tra (state=review)')
    p = json.loads(row['payload'])
    if p.get('brief_id') != bid:
        raise ValueError('Lượt xuất không thuộc hồ sơ')
    if not p.get('technical_verified') or not p.get('report') or not p.get('archive_relative'):
        raise ValueError('Bản xuất chưa qua kiểm tra kỹ thuật (CMYK/300DPI/NAS) nên chưa thể duyệt thẳng; hãy dùng Xuất lại từ phương án')
    if data.get('expected_plan') and data.get('expected_plan') != digest(p.get('plan')):
        raise ValueError('Phương án đã đổi; tải lại trước khi duyệt')
    root = e.artwork_checks.jpg.root
    verified_file = root / jid / 'verified_output.json'
    previews = []
    if verified_file.is_file():
        try:
            previews = json.loads(verified_file.read_text(encoding='utf-8')).get('previews') or []
        except Exception:
            previews = []
    prev_ver = p.get('verification') if isinstance(p.get('verification'), dict) else {}
    check = dict(
        prev_ver,
        **{
            'pass': True,
            'issues': [],
            'previous_issues': prev_ver.get('issues', []),
            'approved_by_operator': note,
            'approved_at': time.time(),
        }
    )
    p['verification'] = check
    p.pop('awaiting_verify_approval', None)
    p.pop('review_reason', None)
    p.pop('review_issue', None)
    p.pop('review_detail', None)
    account = row['account']
    report = p['report']
    report_panels = report.get('panels', []) if isinstance(report, dict) else []
    original = p['plan'].get('renderer') == 'original_pdf_v1'
    from hub.canavi_artwork_policy import review_note
    archive_root = e.settings.inboxes.get(account, {}).get('archive_root', '').rstrip('\\/')
    result = e.effect(
        'jpg-files:' + jid,
        p['conversation'],
        'message',
        {
            'private': True,
            'message_type': 'outgoing',
            'content': (
                ('JPG CMYK THEO ARTBOARD GỐC, ĐÃ DUYỆT KIỂM TRA\n' if original else 'CANAVI — JPG CMYK + AI ĐÃ XUẤT & DUYỆT KIỂM TRA\n')
                + p['plan']['order_code']
                + review_note(p['plan'], check)
                + '\nGhi chú duyệt bản xuất: ' + note
                + '\n' + '\n'.join(x['name'] + ': ' + str(x['size_cm']) + ' cm' for x in report_panels)
                + '\nNAS: ' + archive_root + '\\' + p['archive_relative'].replace('/', '\\')
                + '\nĐã kiểm tra kỹ thuật CMYK/300DPI & duyệt nội bộ.'
            ),
            '_images': previews,
            'content_attributes': {'phucthanh': {'origin': 'hub_note', 'event_id': 'jpg-files:' + jid}},
        },
        apply_capture=True,
    )
    p['message_id'] = result.get('id')
    e.artwork_checks.jpg.save(jid, p, 'done')
    e.artwork_checks.jpg.workflow.version('jpg_exports', jid, p)
    record(e.store, 'jpg_exports', jid, p, 'done')
    with e.store.db() as db:
        db.execute(
            'INSERT OR IGNORE INTO print_plan_actions VALUES(?,?,?,?,?)',
            (digest(['approve_verified_output', jid, time.time()]), bid, 'approve_verified_output', json.dumps({'job_id': jid, 'note': note}), time.time()),
        )
    return {'id': jid, 'state': 'done', 'message': 'Đã duyệt bản xuất đạt chuẩn và chuyển sang Hoàn thành.'}

def approve_plan(e,bid,data):
    kind=data.get('kind');jid=data.get('job_id');note=str(data.get('note','')).strip()
    if kind not in TABLES or not 5<=len(note)<=1000:raise ValueError('Ghi căn cứ duyệt từ5–1000 ký tự')
    workflow=e.artwork_checks.pet.workflow
    with e.store.db() as db:r=db.execute('SELECT * FROM '+kind+' WHERE id=?',(jid,)).fetchone()
    if not r or r['state']!='done':raise ValueError('Chỉ lưu làm mẫu chuẩn sau khi xuất hoàn tất')
    p=json.loads(r['payload'])
    if p.get('brief_id')!=bid:raise ValueError('Lượt xuất không thuộc hồ sơ')
    if data.get('expected_plan')!=digest(p.get('plan')):raise ValueError('Phương án đã đổi; tải lại trước khi duyệt')
    workflow.version(kind,jid,p)
    with e.store.db() as db:version=db.execute('SELECT id FROM workflow_versions WHERE kind=? AND export_id=? ORDER BY created DESC LIMIT 1',(kind,jid)).fetchone()
    if not version:raise ValueError('Chưa có báo cáo file đã xác minh')
    workflow.decide(version['id'],'approved',note)
    record(e.store,kind,jid,p,'approved')
    with e.store.db() as db:db.execute('INSERT OR IGNORE INTO print_plan_actions VALUES(?,?,?,?,?)',(digest(['approve',kind,jid,p['plan']]),bid,'approve_plan',json.dumps({'job_id':jid,'note':note}),time.time()))
    return {'message':'Đã duyệt làm mẫu chuẩn để đối chiếu. Không copy file, RIP hoặc gửi khách.'}
