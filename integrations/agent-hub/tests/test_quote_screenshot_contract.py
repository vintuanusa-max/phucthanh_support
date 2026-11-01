import tempfile,json,base64
from pathlib import Path
from hub import quote_conversation_evidence as q, models, store, evidence_document as evidence
from PIL import Image
from io import BytesIO
buffer=BytesIO()
Image.new('RGB',(120,80),'white').save(buffer,format='PNG')
raw=buffer.getvalue()
m=dict(account='test',thread_id='test-group',message_id='test-new',sender='Test customer',sender_id='test-customer',display_name='TEST',origin='customer',text='@Thiết Kế mẫu này làm e thêm 50 pet nữa ạ',timestamp=200,revision=0,recalled=False,quoted_image=dict(message_id='test-old',client_message_id='test-old-client',sender_id='test-staff',sender='Test staff',timestamp=100,resolved=True),assets=[dict(id='a'*64,name='file',kind='image',state='failed',error='file_link_expired_or_unavailable')])
assert q.explicit_extra(m)==50
for text in ['làm thêm 50 pet?', 'không làm thêm 50 pet','làm thêm 50 pet và 60 pet','làm thêm 50 pet và thiết kế lại','làm thêm 50 pet, tổng 100','mai nha']:assert q.explicit_extra(dict(m,text=text)) is None,text
proof=dict(image=dict(mime_type='image/png',data=base64.b64encode(raw).decode()),source_digest=q.fingerprint(m),quote_id='test-old',method='windows-msaa-printwindow-v1')
with tempfile.TemporaryDirectory() as t:
 st=store.Store(Path(t)/'test.sqlite3');key=st.capture(models.Capture.model_validate(dict(m,conversation_evidence=proof)))
 assert st.capture(models.Capture.model_validate(dict(m,conversation_evidence=proof)))==key
 with st.db() as d:
  row=json.loads(d.execute('select payload from captures').fetchone()[0]);assert row['images']==[] and 'conversation_evidence' not in row
  assert d.execute('select count(*) from quote_conversation_evidence').fetchone()[0]==1
  assert len(evidence.select_sources(d,'test','test-group',['test-new'])[0]['images'])==1
  assert q.load(d,dict(row,text='changed')) is None
  try:q.register(d,dict(row,thread_id='wrong-group'),proof);raise AssertionError('wrong group accepted')
  except ValueError:pass
print('PASS isolated: capture, no AI image, evidence, no duplicates, wrong source rejection, quantity guard')

# Corrupted bytes cannot be reused as evidence.
with tempfile.TemporaryDirectory() as t:
 st=store.Store(Path(t)/'test.sqlite3')
 st.capture(models.Capture.model_validate(dict(m,conversation_evidence=proof)))
 with st.db() as d:
  d.execute("UPDATE quote_conversation_evidence SET png=?",(b'corrupt',))
  try:q.load(d,m);raise AssertionError('corruption accepted')
  except ValueError:pass
for changes in ({'origin':'staff'},{'recalled':True},{'revision':1}):
 assert q.explicit_extra(dict(m,**changes)) is None
print('PASS hash integrity, staff, recalled and revised source guards')

# Exercise the deterministic intake path with fake ERP lookup only.
from types import SimpleNamespace
from unittest.mock import Mock, patch
with tempfile.TemporaryDirectory() as t:
 st=store.Store(Path(t)/'test.sqlite3')
 st.capture(models.Capture.model_validate(dict(m,conversation_evidence=proof)))
 with st.db() as d:
  d.execute("CREATE TABLE intake_runs (id TEXT PRIMARY KEY,state TEXT,payload TEXT,result TEXT)")
  d.execute("INSERT INTO intake_runs VALUES ('run','analyzing','{}','{}')")
 lookup=Mock(return_value={'matches':[]})
 intake=SimpleNamespace(store=st,state=Mock(),accepts=lambda _:True,
  quiet_now=lambda *_:True,resolve_customer_binding=lambda *_:{'customer_id':'fake'},
  engine=SimpleNamespace(erp=SimpleNamespace(match_order=lookup)))
 with patch('hub.intake_lifecycle.reusable',return_value=True):
  assert q.try_prepare(intake,{'id':'run'},{'group_name':'TEST'},[m])
  with st.db() as d:
   state,payload=d.execute("SELECT state,payload FROM intake_runs").fetchone()
  payload=json.loads(payload)
  assert state=='awaiting_evidence' and payload['orders'][0]['so_luong']=='50'
  assert payload['request_id']=='chatwoot-id:run'
  assert not q.try_prepare(intake,{'id':'run'},{'submitted_payload':{'request_id':'done'}},[m])
  lookup.return_value={'matches':[{'id':'already-exists'}]}
  assert q.try_prepare(intake,{'id':'run'},{'group_name':'TEST'},[m])
  assert intake.state.call_args.args[1]=='review'
  with patch('hub.quote_conversation_evidence.load',return_value=None):
   assert q.try_prepare(intake,{'id':'run'},{'group_name':'TEST'},[m])
   assert intake.state.call_args.args[2]['quote_screenshot_required']
print('PASS fake intake: awaiting evidence, stable request ID, submitted/existing order guard, missing proof review')
