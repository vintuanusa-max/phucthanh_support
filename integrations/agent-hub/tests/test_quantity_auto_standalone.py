import ast,json,sqlite3,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import httpx
source=(Path(__file__).resolve().parents[1] / 'hub' / 'order_intake.py').read_text()
tree=ast.parse(source)
method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='resolve_customer_binding')
ns={'httpx':httpx}
exec(compile(ast.Module(body=[method],type_ignores=[]),'<method>','exec'),ns)
query=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('SELECT c.id,c.payload FROM captures c JOIN intake_sources'))
class Tests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:')
  self.db.executescript('CREATE TABLE captures(id,payload,account,thread_id);CREATE TABLE intake_sources(capture_id,run_id);CREATE TABLE intake_runs(id,state,payload,result);CREATE TABLE agent_actions(run_id,state,tool,args,result);')
  self.db.execute('INSERT INTO captures VALUES(?,?,?,?)',('c',json.dumps({'timestamp':1000}),'a','g'))
  self.db.execute('INSERT INTO intake_sources VALUES(?,?)',('c','r'))
 def recovered(self,state='review',payload=None,reason='Chờ quá 30 phút, chưa đủ thông tin',qty=1):
  self.db.execute('INSERT INTO intake_runs VALUES(?,?,?,?)',('r',state,json.dumps(payload or {}),json.dumps({'reason':reason})))
  return bool(self.db.execute(query,(0,qty,'a','g',0,2000,2000)).fetchall())
 def test_timeout_quantity(self):self.assertTrue(self.recovered())
 def test_timeout_image(self):self.assertTrue(self.recovered(reason='Đã đọc ảnh sau 30 phút; chưa xác định đủ dữ liệu đơn mới'))
 def test_no_quantity(self):self.assertFalse(self.recovered(qty=0))
 def test_other_review(self):self.assertFalse(self.recovered(reason='NAS evidence failed'))
 def test_created(self):self.assertFalse(self.recovered(state='created'))
 def test_request(self):self.assertFalse(self.recovered(state='waiting_details',payload={'request_id':'sent'}))
 def test_submitted(self):self.assertFalse(self.recovered(state='ignored',payload={'submitted_payload':{}}))
 def test_waiting(self):self.assertTrue(self.recovered(state='waiting_details'))
 def setup_engine(self,code=None,binding=None):
  e=NS(customer_mappings=Mock(),erp=Mock(),note=Mock())
  e.customer_mappings.get.return_value=binding
  e.erp.validate_customer_id.return_value={'name':'KHACH LE'}
  if code:
   r=httpx.Response(code,request=httpx.Request('POST','http://test'))
   e.erp.observe_group.side_effect=httpx.HTTPStatusError('test',request=r.request,response=r)
  return e
 def call(self,e):return ns['resolve_customer_binding'](NS(engine=e),{'account':'a','thread_id':'g','id':'r','conversation':1},'new group')
 def test_existing_binding(self):
  e=self.setup_engine(binding={'customer_id':'known'});self.call(e);e.erp.observe_group.assert_not_called();e.customer_mappings.set.assert_not_called()
 def test_name_matched(self):
  e=self.setup_engine();self.assertIsNone(self.call(e));e.customer_mappings.set.assert_not_called()
 def test_unknown_retail(self):
  e=self.setup_engine(409);self.call(e);e.customer_mappings.set.assert_called_once();e.note.assert_called_once()
 def test_bad_name_retail(self):
  e=self.setup_engine(422);self.call(e);e.customer_mappings.set.assert_called_once()
 def test_outage_no_fallback(self):
  e=self.setup_engine(503)
  with self.assertRaises(httpx.HTTPStatusError):self.call(e)
  e.customer_mappings.set.assert_not_called()
 def test_auth_no_fallback(self):
  e=self.setup_engine(401)
  with self.assertRaises(httpx.HTTPStatusError):self.call(e)
  e.customer_mappings.set.assert_not_called()
 def test_wrong_retail_no_binding(self):
  e=self.setup_engine(409);e.erp.validate_customer_id.return_value={'name':'Other'}
  with self.assertRaises(ValueError):self.call(e)
  e.customer_mappings.set.assert_not_called()
if __name__ == '__main__': unittest.main()
