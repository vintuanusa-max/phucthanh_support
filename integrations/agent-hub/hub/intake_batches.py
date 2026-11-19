from copy import deepcopy

def grouped(items, seconds):
    """Presentation only: group source-time sessions, never mutate runs/claims."""
    buckets={}
    for x in items:
        # Slips without source range remain separate (do not guess associations).
        key=(x['account'],x.get('thread_id') or x['id'])
        buckets.setdefault(key,[]).append(x)
    output=[]
    for rows in buckets.values():
        sessions=[]
        for x in sorted(rows,key=lambda a:(a.get('first_timestamp') or a['created'],a['created'])):
            start=x.get('first_timestamp') or x['created']; end=x.get('last_timestamp') or start
            if sessions and start<=sessions[-1][0]+seconds:
                sessions[-1][0]=max(sessions[-1][0],end);sessions[-1][1].append(x)
            else:sessions.append([end,[x]])
        for end,steps in sessions:
            steps=sorted(steps,key=lambda a:a['created'])
            latest=deepcopy(steps[-1]); orders={o['id']:o for s in steps for o in s.get('orders',[]) if o.get('id')}
            latest['orders']=list(orders.values());latest['steps']=steps
            latest['kind']='Đợt tin/ảnh';latest['created']=max(s['created'] for s in steps)
            if orders:
                latest['display_group']='done';latest['reason']='Đã xử lý ERP · '+str(len(orders))+' đơn · '+str(len(steps))+' bước'
            elif any(s.get('display_group')=='review' for s in steps):
                latest['display_group']='review'
            output.append(latest)
    return sorted(output,key=lambda a:a['created'],reverse=True)
