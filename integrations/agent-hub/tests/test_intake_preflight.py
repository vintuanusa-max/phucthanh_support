import sys,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import contextmanager
@contextmanager
def database(path):
 c=sqlite3.connect(str(path))
 try:
  with c: yield c
 finally:c.close()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hub'))
import intake_preflight as m
class Tests(unittest.TestCase):
 def test_skip_only_complete(self):
  ms=[{'message_id':'1'},{'message_id':'2'}]
  v=dict(intent='payment',certain=True,has_order_or_sample_request=False,source_message_ids=['1','2'],reason='paid')
  self.assertTrue(m.can_skip(v,ms))
  for change in [dict(certain=False),dict(has_order_or_sample_request=True),dict(source_message_ids=['1']),dict(intent='unknown'),dict(intent='approval'),dict(intent='order')]:
   self.assertFalse(m.can_skip({**v,**change},ms))
 def test_cache_reuse_and_changed_input(self):
  with tempfile.TemporaryDirectory() as d:
   store=SimpleNamespace(db=lambda:database(Path(d)/'db'))
   calls=[]
   def compute():calls.append(1);return {'text':'20c'}
   self.assertFalse(m.cached(store,'a',compute)[1]);self.assertTrue(m.cached(store,'a',compute)[1])
   self.assertFalse(m.cached(store,'b',compute)[1]);self.assertEqual(len(calls),2)
 def test_images_only_not_skipped(self):
  self.assertFalse(m.route(None,{},[{'text':'[Ảnh Zalo lưu trong kho NAS]','images':['a']}]))
 def test_observation_scoped_and_message_reference(self):
  with tempfile.TemporaryDirectory() as d:
   store=SimpleNamespace(db=lambda:database(Path(d)/'db'),images=lambda ids:[{'mime_type':'image/png','data':'YWJj'}])
   e=SimpleNamespace(store=store,settings=SimpleNamespace(gemini_model='test'))
   with patch.object(m,'ask',return_value={'text':'20','description':'logo','uncertain':False}) as ask:
    a=m.observations(e,{'account':'a','thread_id':'g'},[{'message_id':'1','images':['a']}])
    b=m.observations(e,{'account':'a','thread_id':'g'},[{'message_id':'2','images':['a']}])
    self.assertTrue(b[0]['cache_hit']);self.assertEqual(b[0]['message_id'],'2');self.assertEqual(ask.call_count,1)
    m.observations(e,{'account':'a','thread_id':'other'},[{'message_id':'2','images':['a']}]);self.assertEqual(ask.call_count,2)
if __name__=='__main__':unittest.main()
