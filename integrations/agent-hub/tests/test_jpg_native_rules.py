import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from hub.jpg_plan import validate
from hub.workflow_rules import jpg_size
from hub.jpg_native import validate_scan
class Rules(unittest.TestCase):
 def test_shrink(self):
  self.assertEqual(jpg_size(46,47.5,'raw_fabric','bag_panel'),(44,45))
  self.assertEqual(jpg_size(50,70,'raw_fabric','bag_panel'),(48,65))
  self.assertEqual(jpg_size(50,92,'raw_fabric','bag_panel'),(48,87))
  self.assertEqual(jpg_size(160,20,'explicit_output','meter_fabric'),(160,20))
 def test_joined_seams(self):
  obj=dict(id='0.1',kind='GroupItem',native=True,page=1,bounds=[0,100,100,0])
  comps=[dict(object_ids=['0.1'],side=side,x_cm=2,y_cm=4,width_cm=20,rotation=rot,vertical_anchor=anchor,horizontal_alignment='left',sources=['brief']) for side,rot,anchor in [('front',0,'top'),('back',180,'bottom')]]
  p=dict(process='sublimation',issues=[],order_code='TEST',panels=[dict(name='joined',kind='bag_panel',construction='joined_two_faces',sources=['brief'],basis_explanation='test',width_cm=50,height_cm=92,canvas_basis='raw_fabric',background_object_id='',components=comps)])
  result=validate(p,[obj],['brief'])['panels'][0]
  self.assertEqual(result['output_cm'],[48,87]);self.assertTrue(result['corner_marks'])
  self.assertEqual([(x['x_cm'],x['y_cm'],x['rotation']) for x in result['components']],[(2.5,4.5,0),(2.5,4.5,180)])
 def test_hash_guard(self):
  with self.assertRaises(ValueError):validate_scan({'source_sha256':'wrong'},'actual')
 def test_meter_no_marks(self):
  obj=dict(id='0.1',kind='PathItem',native=True,page=1)
  p=dict(process='sublimation',issues=[],order_code='TEST',panels=[dict(name='meter',kind='meter_fabric',construction='meter_fabric',sources=['brief'],basis_explanation='test',width_cm=160,height_cm=20,canvas_basis='explicit_output',background_object_id='0.1',components=[])])
  self.assertFalse(validate(p,[obj],['brief'])['panels'][0]['corner_marks'])
if __name__=='__main__':unittest.main()
