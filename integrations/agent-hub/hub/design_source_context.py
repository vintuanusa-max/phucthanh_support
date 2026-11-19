"""Keep design attachments from the parent batch independent of ERP source IDs."""
import json
EXTENSIONS=('.ai','.pdf','.psd','.cdr','.eps','.svg')
def has_design(messages):
    return any(a.get('name','').lower().endswith(EXTENSIONS) for m in messages for a in m.get('assets',[]))

def enrich(db,run,payload,messages):
    parent=payload.get('proposal_parent') or payload.get('model_parent')
    if not parent:return messages,[]
    row=db.execute('SELECT payload FROM intake_runs WHERE id=? AND account=? AND thread_id=?',(parent,run['account'],run['thread_id'])).fetchone()
    if not row:return messages,[]
    ids=set(json.loads(row[0]).get('messages',[]));selected={m['message_id'] for m in messages};files=[]
    from hub.receipt_match import confirmed_slip
    for mid in ids-selected:
        row=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',(run['account'],run['thread_id'],mid)).fetchone()
        if not row:continue
        m=json.loads(row[0])
        if m.get('recalled') or m.get('revision') or confirmed_slip(db,run['account'],run['thread_id'],mid):continue
        if has_design([m]):files.append(m)
    # A single design in a single-proposal batch can be considered with that
    # model. Multiple files/models remain visible candidates, never guessed.
    proposals=db.execute('SELECT count(*) FROM agent_proposals WHERE run_id=?',(parent,)).fetchone()[0]
    distinct={a.get('sha256') or a.get('id') for m in files+messages for a in m.get('assets',[]) if a.get('name','').lower().endswith(EXTENSIONS)}
    if files and proposals==1 and len(distinct)==1:
        return sorted(messages+files,key=lambda m:m.get('timestamp',0)),[]
    return messages,files
