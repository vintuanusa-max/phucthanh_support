"""Owner policy: exact groups, original design size, deterministic export only."""
import json, os, time
from pathlib import Path
GROUPS={'g5402324928935037742','g3427098896227768665'}

def enabled(thread):
 return thread in GROUPS

def route(checks,row,brief):
 p=json.loads(row['payload']);a=p['asset']
 if not enabled(p['thread_id']) or p['relation']!='brief_source':return False
 marker=Path(checks.store.path).parent/'original-jpg-groups-enabled-at'
 if not marker.exists():
  try:marker.open('x').write(str(time.time()))
  except FileExistsError:pass
 allowed=marker.with_name('original-jpg-groups-resume.json')
 resume=json.loads(allowed.read_text()) if allowed.exists() else []
 if brief.get('created_at',0)<float(marker.read_text()) and row['brief_id'] not in resume:return False
 if not a['name'].lower().endswith(('.ai','.pdf','.psd')):return False
 if row['state']!='awaiting_upload':return True
 from hub.shared_source import shared_source
 try:
  if brief.get('instruction_issues'):raise ValueError(' | '.join(brief['instruction_issues']))
  source=shared_source(os.environ['HUB_SOURCE_ARCHIVE'],a,1024**3 if a['name'].lower().endswith('.psd') else 128*1024**2)
  if a['name'].lower().endswith('.psd'):
   from hub.psd_samples import init
   init(checks.e)
   payload={'title':'JPG nguyên khổ — '+a['name'],'request':'Xuất toàn bộ artboard JPG CMYK nguyên khổ PSD. '+ '\n'.join(s.get('text','') for s in brief.get('sources',[])),
    'all_artboards':True,'messages':[p['source_message_id']],'asset':a,'sample_only':False,'brief_id':row['brief_id'],'policy':'original_psd_size','source_timestamp':row['created'],'reason':''}
   with checks.store.db() as db:
    prior=db.execute("SELECT id FROM psd_samples WHERE account=? AND thread_id=? AND json_extract(payload,'$.asset.sha256')=?",(row['account'],p['thread_id'],a['sha256'])).fetchone()
    if not prior:db.execute('INSERT OR IGNORE INTO psd_samples VALUES(?,?,?,?,?,?,?)',(row['id'],row['account'],p['thread_id'],p['conversation'],'queued',json.dumps(payload,ensure_ascii=False),time.time()))
  else:
   comparison={'print_process':'sublimation','process_sources':['owner_group_policy:'+p['thread_id']],'same_design':'proposed','file_role':'artwork','findings':[],'decision_method':'configured_group_original_size_no_ai'}
   checks.jpg.prepare(row,brief,{},[],[],comparison,source)
  result={'state':'routed_jpg','execution_allowed':False,'errors':[],'routing_policy':'original_size_no_ai','source':p}
 except Exception as exc:
  result={'state':'needs_staff_review','execution_allowed':False,'errors':[str(exc)[:300]],'routing_policy':'original_size_no_ai','source':p}
 with checks.store.db() as db:db.execute("UPDATE artwork_checks SET state='done',result=? WHERE id=? AND state='awaiting_upload'",(json.dumps(result,ensure_ascii=False),row['id']))
 return True
