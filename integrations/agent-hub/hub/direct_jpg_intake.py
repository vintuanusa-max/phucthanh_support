"""File-driven JPG intake for two configured groups; never consumes ERP sources."""
import json,re,time
from pathlib import Path
from hub.store import event_key
from hub.group_original_jpg import enabled
from hub.source_readiness import norm

def instruction_issues(messages):
    # Instructions remain visible and must never be silently overridden by original-size export.
    issues=[]
    for m in messages:
        if m.get('role')=='bot':continue
        t=norm(m.get('text',''))
        if re.search(r'CHUA IN|DUNG IN|KHOAN IN|DUNG XUAT|CHO .*SUA|KHONG IN|HUY',t):
            issues.append('Khách yêu cầu chờ/dừng: '+m.get('text',''))
        elif re.search(r'DOI (?:KHO|MAU|KICH THUOC)|SUA |VE LAI|CAT |CROP|RESIZE|CHI (?:IN|XUAT)|\d+(?:[.,]\d+)?\s*(?:CM|MM)\b',t):
            issues.append('Cần áp dụng yêu cầu riêng trước khi xuất nguyên khổ: '+m.get('text',''))
    return list(dict.fromkeys(issues))

def collect(collector,run,messages,historical=False):
    from hub.dispatch_admission import allowed
    if not allowed(run,messages):return False
    if historical or not enabled(run['thread_id']):return False
    sources=[dict(m) for m in messages if not m.get('recalled') and not m.get('revision') and m.get('role')!='bot' and m.get('origin') not in ('legacy_bot','erp')]
    for m in sources:
        for asset in m.get('assets',[]):
            if asset.get('state')!='ready' or not re.fullmatch('[a-f0-9]{64}',asset.get('sha256','')):continue
            if not asset.get('name','').lower().endswith(('.ai','.pdf','.psd')):continue
            key=asset.get('sha256') or asset.get('id') or event_key(asset.get('name'),m['message_id'])
            identity=event_key('direct-original-jpg-v1',run['account'],run['thread_id'],key)
            with collector.store.db() as db:
                if db.execute('SELECT 1 FROM design_briefs WHERE id=?',(identity,)).fetchone():continue
                # Existing output/brief owns this exact file, including archived records.
                prior=db.execute("SELECT 1 FROM design_briefs WHERE account=? AND thread_id=? AND EXISTS (SELECT 1 FROM json_each(design_briefs.payload,'$.sources') s,json_each(s.value,'$.assets') a WHERE json_extract(a.value,'$.sha256')=? AND ?!='')",(run['account'],run['thread_id'],asset.get('sha256',''),asset.get('sha256',''))).fetchone()
                if prior:continue
            selected=[]
            for src in sources:
                src=dict(src);src['assets']=[asset] if src['message_id']==m['message_id'] else []
                selected.append(src)
            requirements=[dict(basis='text',text=s['text'],quote=s['text'],message_id=s['message_id']) for s in sources if s.get('text')]
            issues=instruction_issues(sources)
            if re.search(r'PHIEU|LENH SAN XUAT|LENH IN',norm(asset['name'])):issues.append('PDF có tên phiếu lệnh; cần xác nhận là thiết kế trước khi xuất.')
            brief=dict(title=asset['name'],kind='print_export',image_context='standalone_artwork',source_message_ids=[s['message_id'] for s in sources],requirements=requirements,missing_fields=[],conflicts=[],bag_panels=[],bag_facts=[])
            payload=dict(schema_version=1,id=identity,account=run['account'],thread_id=run['thread_id'],conversation_id=run['conversation'],historical_reference=False,status='needs_staff_review',execution_allowed=False,customer_question_sent=False,image_content_verified=False,brief=brief,bag_print={},review_items=issues,sources=selected,archive_root=collector.e.settings.inboxes[run['account']].get('archive_root',''),relation_status='proposed_only',created_at=time.time(),direct_original_jpg=True,export_policy='all_artboards_original_size',instruction_issues=issues)
            with collector.store.db() as db:
                db.execute('INSERT OR IGNORE INTO design_briefs VALUES(?,?,?,?,?,?,?)',(identity,run['id'],run['account'],run['thread_id'],run['conversation'],json.dumps(payload,ensure_ascii=False),payload['created_at']))
            collector.workflow.register(payload)
    return True

def discover(checks,account):
    from hub.order_policy import capture_allowed
    marker=Path(checks.store.path).parent/'direct-original-jpg-enabled-at'
    if not marker.exists():
        try:marker.open('x').write(str(time.time()))
        except FileExistsError:pass
    cutoff=float(marker.read_text())
    policy=checks.e.order_intake.policy(account)
    with checks.store.db() as db:
        minutes=15
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='print_settings'").fetchone():
            row=db.execute('SELECT payload FROM print_settings ORDER BY id DESC LIMIT 1').fetchone()
            if row:minutes=json.loads(row[0]).get('source_wait_minutes',15)
        rows=db.execute("SELECT payload FROM captures WHERE account=? AND json_extract(payload,'$.timestamp')>=? ORDER BY json_extract(payload,'$.timestamp')",(account,cutoff)).fetchall()
    groups={}
    for row in rows:
        m=json.loads(row[0]);thread=m.get('thread_id')
        if enabled(thread) and not m.get('recalled') and not m.get('revision') and m.get('role')!='bot' and m.get('origin') not in ('legacy_bot','erp'):groups.setdefault(thread,[]).append(m)
    for thread,messages in groups.items():
        mapping=checks.store.thread(account=account,thread_id=thread)
        if not policy or not mapping or not capture_allowed(policy,checks.e.settings.inboxes[account]['channel'],thread,mapping['display_name']):continue
        chunks=[]
        for m in messages:
            if not chunks or m['timestamp']-chunks[-1][-1]['timestamp']>minutes*60:chunks.append([])
            chunks[-1].append(m)
        for batch in chunks:
            if time.time()<batch[-1]['timestamp']+minutes*60:continue
            run=dict(id=event_key('direct-jpg-batch',account,thread,[m['message_id'] for m in batch]),account=account,thread_id=thread,conversation=mapping['conversation'])
            collect(checks.e.order_intake.design_briefs,run,batch)


def dispatch_gate(db,brief_id):
    """Recheck quiet time and late instructions immediately before worker claim."""
    row=db.execute('SELECT payload FROM design_briefs WHERE id=?',(brief_id,)).fetchone()
    if not row:return ''
    brief=json.loads(row[0])
    if not brief.get('direct_original_jpg'):return ''
    from hub.source_readiness import collection_window
    window=collection_window(db,brief)
    if window['waiting']:return window['reason']
    latest=max([s.get('timestamp',0) for s in brief.get('sources',[])] or [0])
    late=[json.loads(r[0]) for r in db.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND json_extract(payload,'$.timestamp')>?",(brief['account'],brief['thread_id'],latest))]
    issues=instruction_issues([m for m in late if not m.get('revision') and not m.get('recalled') and m.get('origin') not in ('legacy_bot','erp')])
    if issues:return 'Cần kiểm tra yêu cầu bổ sung: '+' | '.join(issues)
    return ''
