"""Explicit PET design files use native artwork dimensions, not a production slip."""
import json,re,time
from hub.store import event_key
from hub.source_readiness import norm
from hub.export_routing import JPG_GROUPS

def is_pet_asset(thread, asset):
    from hub.canavi_slip_policy import GROUPS
    if thread in GROUPS:return False
    name=norm(asset.get('name',''))
    return thread not in JPG_GROUPS and bool(re.search(r'\bPET\b',name)) and name.lower().endswith(('.ai','.pdf')) and not re.search(r'PHIEU|LENH SAN XUAT',name)

def collect(collector, run, messages, historical=False):
    from hub.canavi_slip_policy import sender_id
    if sender_id(collector.intake.policy(run['account']),run):return False
    from hub.dispatch_admission import allowed
    if not allowed(run,messages):return False
    if historical:return False
    files=[(m,a) for m in messages if not m.get('recalled') and not m.get('revision') and m.get('role')!='bot' for a in m.get('assets',[]) if a.get('name','').lower().endswith(('.ai','.pdf','.psd','.cdr'))]
    accepted=[(m,a) for m,a in files if is_pet_asset(run['thread_id'],a)]
    for m,a in accepted:
        if a.get('state')!='ready' or not re.fullmatch('[a-f0-9]{64}',a.get('sha256','')):continue
        identity=event_key('direct-pet-file-v1',run['account'],run['thread_id'],a['sha256'])
        with collector.store.db() as db:
            if db.execute("SELECT 1 FROM design_briefs WHERE account=? AND thread_id=? AND EXISTS(SELECT 1 FROM json_each(payload,'$.sources') s,json_each(s.value,'$.assets') a WHERE json_extract(a.value,'$.sha256')=?)",(run['account'],run['thread_id'],a['sha256'])).fetchone():continue
        # Keep human text instructions, never send batch/slip images to PET planning.
        sources=[dict(x,images=[],assets=[a] if x['message_id']==m['message_id'] else []) for x in messages if not x.get('recalled') and not x.get('revision') and x.get('role')!='bot']
        requirements=[dict(basis='text',text=x['text'],quote=x['text'],message_id=x['message_id']) for x in sources if x.get('text')]
        brief=dict(title=a['name'],kind='print_export',image_context='standalone_artwork',source_message_ids=[x['message_id'] for x in sources],requirements=requirements,missing_fields=[],conflicts=[],bag_panels=[],bag_facts=[])
        p=dict(schema_version=1,id=identity,account=run['account'],thread_id=run['thread_id'],conversation_id=run['conversation'],historical_reference=False,status='needs_staff_review',execution_allowed=False,customer_question_sent=False,image_content_verified=False,brief=brief,bag_print={},review_items=[],sources=sources,archive_root=collector.e.settings.inboxes[run['account']].get('archive_root',''),relation_status='proposed_only',created_at=time.time(),direct_pet_source=True,n8n_export_kind='export_pet')
        with collector.store.db() as db:db.execute('INSERT OR IGNORE INTO design_briefs VALUES(?,?,?,?,?,?,?)',(identity,run['id'],run['account'],run['thread_id'],run['conversation'],json.dumps(p,ensure_ascii=False),p['created_at']))
        collector.workflow.register(p)
    return bool(accepted) and len(accepted)==len(files)

def source_only(brief, asset):
    """Drop slip/layout facts from the PET export context, not from ERP storage."""
    b=dict(brief.get('brief',{}))
    b.update(bag_facts=[],bag_panels=[],missing_fields=[],conflicts=[])
    b['requirements']=[r for r in b.get('requirements',[]) if r.get('basis')=='text']
    b['owner_instruction']='PET: không đọc phiếu lệnh, không suy kích thước từ cữ/khổ vải. Chọn đủ artwork/group theo maket trong file, xuất nguyên kích thước đối tượng nguồn. Giữ chữ trắng, nền trong suốt. Preview nội bộ, chưa RIP/gửi khách.'
    return dict(brief,brief=b,bag_print={},sources=[dict(s,images=[]) for s in brief.get('sources',[])],direct_pet_source=True,n8n_export_kind='export_pet')
