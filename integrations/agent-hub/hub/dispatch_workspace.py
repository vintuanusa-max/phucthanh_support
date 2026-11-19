"""Source-bound operator workspace. Inspection does not enqueue work."""
import hashlib
import json
import math

MODES = {
    'auto': 'Theo phiếu / tự xác định',
    'single_face': 'Chuyển nhiệt · Một mặt',
    'separate_faces': 'Chuyển nhiệt · Hai mặt rời',
    'joined_faces': 'Chuyển nhiệt · Hai mặt liền',
    'ready_layout': 'Chuyển nhiệt · Bản dàn sẵn',
    'solid_meter': 'Chuyển nhiệt · Vải mét màu trơn',
    'pattern_meter': 'Chuyển nhiệt · Vải mét hoa văn',
    'pet': 'PET · PNG / TIFF từng vị trí',
}
BUSY = {'preparing','scheduled','planning','awaiting_upload','queued','reading','exporting','publishing','uncertain',
        'scan_queued','scan_running','render_queued','render_running','png_check_queued'}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def source_pool(db,p,bid):
    """Nearby attachments are candidates only, never silently attached."""
    pool = {s['message_id']:dict(s,link_basis='brief') for s in p.get('sources',[])}
    for row in db.execute('SELECT payload FROM artwork_checks WHERE brief_id=?',(bid,)):
        v=json.loads(row[0]);mid=v.get('source_message_id')
        if mid and mid not in pool:
            pool[mid]={'message_id':mid,'assets':[v['asset']],'link_basis':'checked_file','images':[]}
    from hub.source_readiness import readiness
    gate=readiness(db,p)
    for mid,asset in (gate or {}).get('candidates',[]):
        pool.setdefault(mid,{'message_id':mid,'assets':[asset],'images':[],'link_basis':'matched_code'})
    anchors=[s for s in p.get('sources',[]) if s.get('timestamp')]
    for row in db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? ORDER BY rowid DESC LIMIT 1000',(p['account'],p['thread_id'])):
        s=json.loads(row[0]);mid=s.get('message_id')
        if not mid or s.get('recalled') or s.get('revision'):continue
        if mid in pool:
            pool[mid]=dict(s,link_basis=pool[mid]['link_basis'])
        elif s.get('assets') and any(a.get('sender_id') and a['sender_id']==s.get('sender_id') and abs(float(a['timestamp'])-float(s.get('timestamp',0)))<=120 for a in anchors):
            pool[mid]=dict(s,link_basis='nearby_unconfirmed')
    return list(pool.values()),gate

def workspace(e,p,bid,js,native):
    with e.store.db() as db:
        pool,gate=source_pool(db,p,bid)
        from hub.source_readiness import collection_window
        window=collection_window(db,p)
        from hub.receipt_match import confirmed_slip
        roles={s['message_id']:('Phiếu lệnh sản xuất' if confirmed_slip(db,p['account'],p['thread_id'],s['message_id']) else 'Maket / ảnh tham chiếu — cần đối chiếu' if s.get('images') else 'File thiết kế / tài liệu') for s in pool}
        details=[]
        for table in ('artwork_checks','jpg_exports','pet_exports'):
            clause='brief_id=?' if table=='artwork_checks' else "json_extract(payload,'$.brief_id')=?"
            for r in db.execute('SELECT * FROM '+table+' WHERE '+clause+' ORDER BY created DESC',(bid,)):
                v=json.loads(r['payload']);result=json.loads(r['result']) if table=='artwork_checks' else {}
                details.append({'id':r['id'],'kind':table,'state':r['state'],'created':r['created'],
                    'reason':v.get('review_reason') or '; '.join(result.get('errors',[])),
                    'parts':v.get('part_table',[]),'plan_ready':bool(v.get('export_plan_ready')),
                    'has_plan':bool(v.get('plan')),'report':v.get('report'),
                    'native_error':result.get('technical',{}).get('native_group_error',''),
                    'missing':result.get('comparison',{}).get('missing_fields',[]),
                    'path':v.get('archive_relative',''),'parent':v.get('parent_job_id'),
                    'owner_spec':v.get('owner_export_spec') or v.get('source',{}).get('owner_export_spec')})
    sources=[]
    for s in pool:
        previews=[]
        for imid in s.get('images',[])[:2]:
            try:
                im=e.store.images([imid])[0]
                if len(im['data'])<4000000:previews.append(im)
            except (IndexError,KeyError,OSError,ValueError):pass
        role_label=roles[s['message_id']]
        has_design_asset=any(a.get('name','').lower().endswith(('.pdf','.ai','.psd','.cdr')) for a in s.get('assets',[]))
        suggested_role='production_slip' if role_label=='Phiếu lệnh sản xuất' else ('design_file' if has_design_asset else ('maket_image' if s.get('images') else 'message_only'))
        sources.append({k:s.get(k) for k in ('message_id','sender','timestamp','text','assets','link_basis')}|{'images':previews,'role':role_label,'suggested_role':suggested_role,'default_selected':s.get('link_basis')!='nearby_unconfirmed'})
    # Optimistic revision includes source and work state, not images or wall clock.
    revision=digest({'brief':p,'jobs':details,'native':[(x.get('id'),x.get('state'),x.get('auto_status')) for x in native],
                     'sources':[(s['message_id'],s.get('assets'),s['link_basis']) for s in pool]})
    stages=[{'id':k,'label':v,'state':'pending','reason':'Chưa có bằng chứng đã chạy'} for k,v in [
        ('sources','Ghép phiếu · maket · thiết kế'),('receive','Nhận và kiểm tra file'),('read','AI đọc và đối chiếu'),
        ('layout','Xác định cấu tạo · khổ vải'),('artwork','Chọn cụm artwork · lập phương án'),
        ('export','Xuất file'),('verify','Kiểm chứng bản xuất'),('complete','Lưu bản xuất nội bộ')]]
    def setstage(i,state,reason):stages[i].update(state=state,reason=reason)
    checks=[x for x in details if x['kind']=='artwork_checks']
    exports=[x for x in details if x['kind']!='artwork_checks']
    if checks:exports=[x for x in exports if x['created']>=checks[0]['created']]
    setstage(0,'done' if checks or not gate or gate.get('ready') else 'blocked',(gate or {}).get('reason') or 'Nguồn gắn trong hồ sơ')
    if window['waiting'] and not checks:setstage(0,'waiting',window['reason'])
    if checks:
        latest=checks[0]
        setstage(1,'waiting' if latest['state']=='awaiting_upload' else 'done','Chờ bộ đọc nhận file' if latest['state']=='awaiting_upload' else 'Tác vụ đã qua bước nhận file')
        if latest['state'] in ('queued','reading'):setstage(2,'running','Đang chờ / đọc và đối chiếu nguồn')
        elif latest['state'] not in ('awaiting_upload','archived','superseded'):
            setstage(2,'blocked' if latest['reason'] else 'done',latest['reason'] or 'Đã có kết quả đối chiếu')
    if exports:
        # Latest root is the current attempt; old failures stay in history only.
        roots=[x for x in exports if not x['parent']]
        root=max(roots or exports,key=lambda x:x['created'])
        current=[root]+[x for x in exports if x['parent']==root['id']]
        parts=root['parts'];missing=[m for a in parts for m in a.get('missing',[])]
        unknown=any(a.get('kind')=='unknown' for a in parts)
        setstage(3,'blocked' if unknown or missing else ('done' if parts or root['has_plan'] else 'running'),'; '.join(missing) or ('Chưa xác định cấu tạo tấm vải' if unknown else 'Theo phân loại / phương án của lượt hiện tại'))
        if any(x['has_plan'] for x in current):setstage(4,'done','Đã lập phương án; xem thông số và kiểm tra ở Phương Án Xuất')
        if root['state']=='review' and stages[3]['state']!='blocked':setstage(4,'blocked',root['reason'] or root['native_error'] or 'Cần kiểm tra phương án / cụm artwork')
        active=[x for x in current if x['state'] in BUSY]
        if active:
            x=active[0]
            if x['state'] in ('queued','exporting'):setstage(5,'running','Chờ / đang xuất trên worker')
            elif x['state']=='publishing':setstage(6,'running','Đang kiểm chứng / lưu kết quả')
            else:setstage(4,'running',x['reason'] or 'Đang chuẩn bị phương án')
        completed=[x for x in current if x['state']=='done']
        if completed:
            all_done=all(x['state'] in ('done','delegated') for x in current)
            setstage(5,'done' if all_done else 'partial','Đã có bản xuất của '+str(len(completed))+' phần')
            setstage(6,'done' if all_done else 'partial','Các phần done đã qua quy trình kiểm chứng; xem từng tác vụ')
            setstage(7,'done' if all_done else 'partial','Đã lưu nội bộ; không đồng nghĩa đã RIP hoặc gửi khách')
    for n in native:
        if n.get('auto_status')=='review' and n.get('error'):setstage(4,'blocked',n['error'])
        elif n.get('state') in BUSY or n.get('auto_status') in ('planning','verifying','waiting_verify','waiting_scan'):setstage(4,'running',n.get('error') or 'Illustrator: '+str(n.get('auto_status') or n['state']))
    blockers=[s for s in stages if s['state']=='blocked']
    running=[s for s in stages if s['state'] in ('running','waiting')]
    focus=(running or blockers or [stages[-1] if stages[-1]['state']=='done' else next((s for s in stages if s['state']=='pending'),stages[-1])])[0]
    from hub.dispatch_stage import status,timeline
    with e.store.db() as db:progress=status(db,p,bid,e.artwork_checks.pet.workflow.current(bid),'collecting_sources' if window['waiting'] else 'waiting_sources' if gate and not gate.get('ready') else '',(gate or {}).get('reason',''))
    stages=timeline(progress)
    focus=next((s for s in stages if s['id']==progress['stage']),dict(id='cancelled',label='Đã hủy',state='blocked',reason=progress['reason']))
    return {'revision':revision,'sources':sources,'gate':gate,'window':window,'stages':stages,'focus':focus,
            'attempts':details,'modes':[{'id':k,'label':v} for k,v in MODES.items()],
            'facts':p.get('brief',{}).get('bag_facts',[]),'bag_print':p.get('bag_print',{}),
            'busy':any(x['state'] in BUSY for x in js) or any(x.get('state') in BUSY or x.get('auto_status') in ('planning','verifying','waiting_verify','waiting_scan') for x in native)}

def prepare_request(e,bid,data):
    from hub.dispatch_control import detail
    live=detail(e,bid);w=live.get('workspace')
    if not w or data.get('expected_revision')!=w['revision']:raise ValueError('Hồ sơ đã thay đổi; làm mới trước khi tiếp tục')
    if w['busy']:raise ValueError('Có lượt đang chạy hoặc chưa rõ kết quả; không tạo thêm lượt')
    spec=data.get('export_spec')
    if not isinstance(spec,dict) or spec.get('mode') not in MODES:raise ValueError('Chọn loại xuất hợp lệ')
    mode=spec['mode'];clean={'mode':mode}
    for key in ('fabric_width_cm','fabric_height_cm'):
        value=spec.get(key)
        if value not in (None,''):
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=10000:raise ValueError('Khổ vải phải là số cm lớn hơn 0')
            clean[key]=value
    if mode in ('single_face','separate_faces','joined_faces') and not all(k in clean for k in ('fabric_width_cm','fabric_height_cm')):raise ValueError('Cần khổ vải ngang và dài; không dùng kích thước túi thành phẩm thay thế')
    if mode in ('single_face','separate_faces','joined_faces'):
        if spec.get('dimension_basis') not in ('raw_fabric','post_shrink'):raise ValueError('Chọn khổ trước co hay sau co')
        clean['dimension_basis']=spec['dimension_basis']
    if mode=='joined_faces':
        if spec.get('join_axis') not in ('bottom','side'):raise ValueError('Chọn nối qua đáy hoặc qua hông')
        clean['join_axis']=spec['join_axis']
    for cue_key in ('cue_y_cm','cue_x_cm'):
        cue_val=spec.get(cue_key)
        if cue_val not in (None,''):
            if type(cue_val) not in (int,float) or not math.isfinite(cue_val) or not 0<=cue_val<=10000:raise ValueError('Cữ in phải là số cm từ 0 trở lên')
            clean[cue_key]=round(float(cue_val),2)
    if spec.get('horizontal_alignment') not in (None,''):
        if spec.get('horizontal_alignment') not in ('left','center'):raise ValueError('Căn ngang không hợp lệ')
        clean['horizontal_alignment']=spec['horizontal_alignment']
    if spec.get('background_mode') not in (None,''):
        if spec.get('background_mode') not in ('preserve_source','solid_cmyk','none','registered_per_face','continuous_stripes'):raise ValueError('Chế độ nền không hợp lệ')
        clean['background_mode']=spec['background_mode']
        if clean['background_mode']=='solid_cmyk':
            cmyk=spec.get('background_cmyk')
            if not isinstance(cmyk,(list,tuple)) or len(cmyk)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=float(v)<=100 for v in cmyk):
                raise ValueError('Màu nền CMYK phải gồm 4 kênh [C, M, Y, K] từ 0 đến 100%')
            clean['background_cmyk']=[round(float(v),2) for v in cmyk]
    for meta_key in ('product_type','material'):
        if spec.get(meta_key) not in (None,'') and isinstance(spec.get(meta_key),str):
            clean[meta_key]=spec[meta_key].strip()[:64]
    raw_artboards=spec.get('selected_artboards',data.get('selected_artboards'))
    if raw_artboards not in (None,'',[]):
        if isinstance(raw_artboards,str):
            parts=[x.strip() for x in raw_artboards.split(',') if x.strip()]
            if not all(x.isdigit() and 1<=int(x)<=200 for x in parts):
                raise ValueError('Danh sách Artboard cần xuất phải là các số nguyên dương (ví dụ: 1, 2)')
            clean['selected_artboards']=sorted({int(x) for x in parts})
        elif isinstance(raw_artboards,list) and all(isinstance(x,int) and not isinstance(x,bool) and 1<=x<=200 for x in raw_artboards):
            clean['selected_artboards']=sorted(set(raw_artboards))
        else:
            raise ValueError('Danh sách Artboard cần xuất không hợp lệ')
    raw_roles=spec.get('source_roles',data.get('source_roles'))
    if raw_roles not in (None,{},''):
        if not isinstance(raw_roles,dict) or any(not isinstance(k,str) or v not in ('production_slip','design_file','maket_image','message_only','ignore') for k,v in raw_roles.items()):
            raise ValueError('Vai trò nguồn không hợp lệ')
        clean['source_roles']=dict(raw_roles)
    answers=data.get('field_answers',{})
    if not isinstance(answers,dict) or len(answers)>40 or any(not isinstance(k,str) or not isinstance(v,str) or len(k)>1000 or len(v)>1000 for k,v in answers.items()):raise ValueError('Thông tin bổ sung không hợp lệ')
    clean['field_answers']={k:v.strip() for k,v in answers.items() if v.strip()}
    note=str(data.get('note','')).strip()
    if not 5<=len(note)<=1800:raise ValueError('Ghi căn cứ / yêu cầu 5–1800 ký tự')
    ids=data.get('source_ids')
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids):raise ValueError('Chọn nguồn đã đối chiếu')
    with e.store.db() as db:
        p=json.loads(db.execute('SELECT payload FROM design_briefs WHERE id=?',(bid,)).fetchone()[0])
        pool,_=source_pool(db,p,bid)
    byid={s['message_id']:s for s in pool}
    if len(set(ids))!=len(ids) or any(i not in byid for i in ids):raise ValueError('Nguồn không thuộc hồ sơ / đợt gửi đang đối chiếu')
    if data.get('sources_confirmed') is not True:raise ValueError('Cần xác nhận đúng nguồn của mẫu này')
    chosen=[{k:v for k,v in byid[i].items() if k!='link_basis'} for i in ids]
    sha=data.get('sha256')
    if not any(a.get('state')=='ready' and a.get('sha256')==sha and a.get('name','').lower().endswith(('.pdf','.ai','.psd','.png','.jpg','.jpeg','.tif','.tiff')) for s in chosen for a in s.get('assets',[])):raise ValueError('Chọn file PDF/AI sẵn sàng trong các nguồn đã xác nhận')
    clean['source_ids']=sorted(ids)
    instruction='Thông số chủ xưởng xác nhận cho lượt xuất này: '+json.dumps(clean,ensure_ascii=False,sort_keys=True)+'\nCăn cứ / yêu cầu: '+note
    if len(instruction)>3000:raise ValueError('Thông tin bổ sung quá dài; rút gọn còn dưới 3000 ký tự')
    return dict(data,note=instruction,_owner_context={'sources':chosen,'spec':clean},action='')
