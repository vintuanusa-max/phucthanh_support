import unittest,tempfile,io,json,base64
from pathlib import Path
from PIL import Image
import httpx
from hub.openai_redraw import redraw,cost
from hub.raster_consent import restoration_consent
b=io.BytesIO();Image.new('RGBA',(20,20),(0,128,0,100)).save(b,format='PNG');RAW=b.getvalue()
YES=dict(question_message_id='q',answer_message_id='a',account='z',thread_id='g',sender_id='c',source_message_id='img')
class P:
 def __init__(self,root):self.root=Path(root)
 def ask(self,*a):return {'pass':True,'lines':['TEST 123'],'issues':[]}
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.p=P(self.root)
  from unittest.mock import patch
  original=Path.read_text
  self.keypatch=patch.object(Path,'read_text',lambda path,*a,**kw: 'fake-key' if str(path)=='/data/secrets/openai-api-key' else original(path,*a,**kw));self.keypatch.start()
 def tearDown(self):self.keypatch.stop();self.tmp.cleanup()
 def folder(self,n):
  p=self.root/n;p.mkdir();return p
 def test_success_cross_brief_cache_and_gate(self):
  calls=[]
  def handle(r):calls.append(r);return httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(RAW).decode()}],'usage':{'input_tokens_details':{'image_tokens':880,'text_tokens':122},'output_tokens':1372}})
  with httpx.Client(transport=httpx.MockTransport(handle)) as c:
   d=self.folder('one')
   with self.assertRaises(ValueError):redraw(self.p,RAW,None,d,'front',['TEST 123'],c)
   with self.assertRaises(ValueError):redraw(self.p,RAW,{'question_message_id':'q','answer_message_id':'a'},d,'front',['TEST 123'],c)
   self.assertEqual(len(calls),0)
   self.assertEqual(redraw(self.p,RAW,YES,d,'front',['TEST 123'],c),RAW)
   self.assertEqual(redraw(self.p,RAW,dict(YES,answer_message_id='again'),self.folder('two'),'front',['TEST 123'],c),RAW)
   self.assertEqual(len(calls),1)
   self.assertEqual(json.loads((d/'front.openai.json').read_text())['computed_cost_usd'],.04881)
 def test_uncertain_never_retry_cross_brief(self):
  calls=[]
  def fail(r):calls.append(r);raise httpx.ReadTimeout('timeout')
  with httpx.Client(transport=httpx.MockTransport(fail)) as c:
   for n in ('a','b'):
    with self.assertRaises(ValueError):redraw(self.p,RAW,YES,self.folder(n),'front',['TEST 123'],c)
   self.assertEqual(len(calls),1)
 def test_text_mismatch_blocks(self):
  with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(RAW).decode()}]}))) as c:
   with self.assertRaises(ValueError):redraw(self.p,RAW,YES,self.folder('bad'),'front',['WRONG'],c)
 def context(self):
  return {'account':'z','thread_id':'g','history':[dict(message_id='img',sender_id='c',role='customer',timestamp=1,has_image=True,text=''),dict(message_id='q',sender_id='s',role='staff',timestamp=20,text='Có file không?')],'batch':[dict(message_id='a',sender_id='c',role='customer',timestamp=30,text='không có file') ]}
 def test_consent_image_and_generic_question(self):
  x=restoration_consent(self.context());self.assertEqual(x['source_message_ids'],['img'])
 def test_other_customer_denied(self):
  c=self.context();c['batch'][0]['sender_id']='other';self.assertIsNone(restoration_consent(c))
 def test_old_sample_denied(self):
  c=self.context();c['history'][0]['timestamp']=-2000;self.assertIsNone(restoration_consent(c))
 def test_new_file_promised_denied(self):
  c=self.context();c['batch'][0]['text']='không có file, để gửi sau';self.assertIsNone(restoration_consent(c))
 def test_multi_sample_intervening_text_denied(self):
  c=self.context();c['history'] += [dict(message_id='m',sender_id='c',role='customer',timestamp=5,text='mẫu khác'),dict(message_id='img2',sender_id='c',role='customer',timestamp=10,has_image=True,text='')];self.assertIsNone(restoration_consent(c))
 def test_pair_maket_artwork_allowed(self):
  c=self.context();c['history'].append(dict(message_id='img2',sender_id='c',role='customer',timestamp=10,has_image=True,text=''));self.assertEqual(restoration_consent(c)['source_message_ids'],['img','img2'])
class Followup(unittest.TestCase):
 def test_later_answer_resumes_once_archived_stays_closed(self):
  import sqlite3,time
  from types import SimpleNamespace
  from hub.raster_pet import discover
  from hub.store import event_key
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'raster-enabled-at').write_text('0');(root/'openai-followup-enabled-at').write_text('0')
   db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
   db.executescript("create table pet_exports(id text primary key,account text,state text,payload text,created real);create table jobs(id text primary key,kind text,payload text,created real);create table captures(account text,thread_id text,payload text);")
   store=SimpleNamespace(db=lambda:db)
   now=time.time();answer=dict(message_id='a',sender_id='c',role='customer',timestamp=now,text='không có file')
   ctx={'account':'z','thread_id':'g','batch':[answer],'history':[dict(message_id='img',sender_id='c',role='customer',timestamp=now-20,has_image=True,text=''),dict(message_id='q',sender_id='s',role='staff',timestamp=now-10,text='Có file không?')]}
   checks=SimpleNamespace(store=store,pet=SimpleNamespace(root=root),e=SimpleNamespace(order_intake=SimpleNamespace(context_gate=SimpleNamespace(build=lambda *a:ctx))))
   brief={'account':'z','thread_id':'g','conversation_id':7,'sources':[{'message_id':'img','images':['media']} ]}
   row={'id':'brief','created':now};old=event_key('raster-pet-v1','brief')
   db.execute('insert into pet_exports values(?,?,?,?,?)',(old,'z','review',json.dumps({'awaiting_file_consent':True}),now))
   db.execute('insert into captures values(?,?,?)',('z','g',json.dumps(answer)))
   a=discover(checks,row,brief);b=discover(checks,row,brief)
   self.assertEqual(a,b);self.assertEqual(db.execute('select count(*) from jobs').fetchone()[0],1)
   payload=json.loads(db.execute('select payload from pet_exports where id=?',(a,)).fetchone()[0]);self.assertEqual(payload['followup_message_id'],'a');self.assertTrue(payload['private']);self.assertFalse(payload['auto_rip'])
   db.execute('update pet_exports set state="archived" where id=?',(old,))
   self.assertEqual(discover(checks,row,brief),old);self.assertEqual(db.execute('select count(*) from jobs').fetchone()[0],1)
if __name__=='__main__':unittest.main()

