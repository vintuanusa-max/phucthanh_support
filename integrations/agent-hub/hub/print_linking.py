"""Read-only, evidence-based projection links. No order/export side effects."""
import json

def resolve(db):
    briefs=[dict(r) for r in db.execute('SELECT * FROM design_briefs ORDER BY created DESC')]
    result={}
    def add(oid,cid,b=None):
        if not oid or not cid:return
        e=result.setdefault(oid,{'customer_id':cid,'rows':[]})
        if e['customer_id']!=cid:return
        if b and not any(x['id']==b['id'] for x in e['rows']):e['rows'].append(b)
    explicit={r['brief_id']:dict(r) for r in db.execute('SELECT * FROM erp_print_brief_links')}
    for r in db.execute("SELECT * FROM intake_runs WHERE state='created'"):
        v=json.loads(r['result'] or '{}');p=json.loads(r['payload']);orders=v.get('orders',[]);cid=v.get('customer_id')
        candidates=[b for b in briefs if b['run_id']==r['id'] and b['account']==r['account'] and b['thread_id']==r['thread_id']]
        sources=p.get('print_line_sources',[])
        submitted=p.get('submitted_payload',{}).get('orders',[])
        valid=len(sources)==len(submitted)==len(orders) and all(float(x.get('so_luong',0))>0 for x in submitted)
        for i,o in enumerate(orders):
            add(o['id'],cid)
            chosen=[]
            for b in candidates:
                bp=json.loads(b['payload']);manual=bp.get('verified_erp_order_id')
                if b['id'] in explicit:continue
                if manual:
                    if manual==o['id']:chosen.append(b)
                    continue
                if len(orders)==1 and len(candidates)==1:chosen.append(b);continue
                if valid and sources[i]:
                    mids={s['message_id'] for s in bp.get('sources',[]) if s.get('assets') or s.get('images')}
                    owned=set(sources[i]);others=set().union(*(set(x) for n,x in enumerate(sources) if n!=i))
                    if mids and mids<=owned and not mids&others:chosen.append(b)
            # Multiple design candidates cannot be assigned from source proximity.
            if len(chosen)==1:add(o['id'],cid,chosen[0])
    slips=[]
    for r in db.execute("SELECT * FROM production_slip_orders WHERE state='created'"):
        v=json.loads(r['result'] or '{}');p=json.loads(r['payload']).get('body',{})
        for o in v.get('orders',[]):
            add(o['id'],v.get('customer_id'))
            slips.append((o['id'],v,p))
    for oid,v,p in slips:
        sha=p.get('asset_sha256');account=p.get('source_account');thread=p.get('group_id')
        if not sha or not account or not thread:continue
        if (v.get('source_account'),v.get('group_id'),v.get('customer_id'),v.get('asset_sha256'))!=(account,thread,p.get('customer_id'),sha):continue
        owners={x for x,_,q in slips if (q.get('source_account'),q.get('group_id'),q.get('asset_sha256'))==(account,thread,sha)}
        if len(owners)!=1:continue
        for b in briefs:
            if b['id'] in explicit or b['account']!=account or b['thread_id']!=thread:continue
            bp=json.loads(b['payload'])
            known={q.get('asset_sha256') for _,_,q in slips if q.get('source_account')==account and q.get('group_id')==thread}
            hashes={a.get('sha256') for s in bp.get('sources',[]) for a in s.get('assets',[])}
            if hashes&known!={sha}:continue
            if any(a.get('sha256')==sha for s in bp.get('sources',[]) for a in s.get('assets',[])):
                add(oid,v.get('customer_id'),b)
    for b in briefs:
        if b['id'] in explicit:
            x=explicit[b['id']];add(x['order_id'],x['customer_id'],b)
    return result
