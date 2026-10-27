import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hub'))
import json,sqlite3,unittest
from intake_lifecycle import reusable,explicit_addition,explicit_total
class Lifecycle(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.executescript('CREATE TABLE order_source_links(account,thread_id,message_id); CREATE TABLE intake_runs(account,thread_id,state,payload,result);')
  self.row={'payload':json.dumps({'account':'a','thread_id':'g','message_id':'old'}),'source_result':'{}'}
 def tearDown(self):self.db.close()
 def test_pending_reusable(self):self.assertTrue(reusable(self.db,self.row))
 def test_payment_not_reused(self):
  for intent in ['payment','invoice','delivery','approval','complaint']:
   self.assertFalse(reusable(self.db,{**self.row,'source_result':json.dumps({'intent':intent})}))
 def test_created_and_uncertain_not_reused(self):
  for state in ['created','duplicate','sending','uncertain']:
   self.db.execute('DELETE FROM intake_runs');self.db.execute('INSERT INTO intake_runs VALUES(?,?,?,?,?)',('a','g',state,json.dumps({'messages':['old']}),'{}'))
   self.assertFalse(reusable(self.db,self.row))
 def test_submitted_not_reused(self):
  self.db.execute('INSERT INTO intake_runs VALUES(?,?,?,?,?)',('a','g','review',json.dumps({'messages':['old'],'submitted_payload':{}}),'{}'));self.assertFalse(reusable(self.db,self.row))
 def test_deleted_erp_retains_link(self):
  self.db.execute('INSERT INTO order_source_links VALUES(?,?,?)',('a','g','old'));self.assertFalse(reusable(self.db,self.row))
 def test_new_source_same_design_allowed(self):
  self.db.execute('INSERT INTO order_source_links VALUES(?,?,?)',('a','g','different'));self.assertTrue(reusable(self.db,self.row))
 def test_addition_keeps_new_quantity_context(self):
  self.assertTrue(explicit_addition([{'text':'In thêm 200 cái mẫu cũ'}]));self.assertFalse(explicit_addition([{'text':'Đã thanh toán 300 khăn'}]))
 def test_only_explicit_total(self):
  self.assertFalse(explicit_total('đơn trước 600 cái'));self.assertFalse(explicit_total('đã thanh toán 300 khăn'));self.assertTrue(explicit_total('tổng cộng 800 cái'))
if __name__=='__main__':unittest.main()
