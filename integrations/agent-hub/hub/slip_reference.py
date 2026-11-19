"""Production slips are ERP/reference records, never independent export roots."""
import json,time
_cache={}

def slip_messages(db,account,thread):
    key=(account,thread);now=time.monotonic()
    old=_cache.get(key)
    if old and now-old[0]<5:return old[1]
    ids=set()
    for row in db.execute("SELECT payload FROM intake_runs WHERE account=? AND thread_id=? AND json_extract(payload,'$.individual_slip')=1",key):
        ids.update(str(x) for x in json.loads(row[0]).get('messages',[]))
    _cache[key]=(now,ids)
    return ids

def reference_only(db,p):
    if p.get('dispatch_role')=='erp_reference':return True
    if p.get('direct_pet_source'):return False
    sources=p.get('sources',[])
    known=slip_messages(db,p['account'],p['thread_id'])
    slip_ids={str(s['message_id']) for s in sources if str(s['message_id']) in known}
    slip=p.get('brief',{}).get('image_context')=='production_slip' or bool(slip_ids)
    if not slip:return False
    # A distinct design attachment owns the export; retain its linked slip evidence.
    design=any(str(s['message_id']) not in slip_ids and a.get('name','').lower().endswith(('.ai','.pdf','.psd','.cdr','.eps','.svg')) for s in sources for a in s.get('assets',[]))
    return not design and not p.get('direct_pet_source')

def mark(db,p):
    if reference_only(db,p):
        p.update(dispatch_role='erp_reference',execution_allowed=False)
    return p
