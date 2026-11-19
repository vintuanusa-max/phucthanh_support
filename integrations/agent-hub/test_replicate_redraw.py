import io,json,os,tempfile,unittest
from pathlib import Path
from PIL import Image
import httpx
from hub.replicate_redraw import redraw
b=io.BytesIO();Image.new('RGB',(32,20),'white').save(b,format='PNG');RAW=b.getvalue()
CONSENT={'question_message_id':'q','answer_message_id':'a'}
class Pet:
 def __init__(self,mismatch=False,legible=True):self.n=0;self.mismatch=mismatch;self.legible=legible
 def ask(self,*args):
  self.n+=1
  if self.n==1:return {'legible':self.legible,'lines':['CẦN THƠ','123'],'white_artwork':False,'issues':[]}
  return {'pass':True,'lines':['CẦN THƠ','124' if self.mismatch else '123'],'issues':[]}
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.key=self.root/'key';self.key.write_text('dummy-test-token');os.environ['REPLICATE_TOKEN_FILE']=str(self.key);self.posts=0
 def tearDown(self):self.t.cleanup()
 def client(self,url='https://test.replicate.delivery/result.png',fail=False):
  def handle(r):
   if r.method=='POST':
    self.posts+=1
    if fail:raise httpx.ReadTimeout('unknown outcome')
    body=json.loads(r.content);self.assertIn('input_image',body['input'])
    return httpx.Response(200,json={'id':'test123','status':'succeeded','output':url})
   self.assertNotIn('authorization',r.headers);return httpx.Response(200,content=RAW)
  return httpx.Client(transport=httpx.MockTransport(handle))
 def run_redraw(self,pet=None,consent=CONSENT,**kw):return redraw(pet or Pet(),RAW,consent,self.root,'front',client=self.client(**kw))
 def test_success_cached_and_secret_absent(self):
  self.assertEqual(self.run_redraw(),RAW);self.assertEqual(self.run_redraw(),RAW);self.assertEqual(self.posts,1)
  self.assertNotIn('dummy-test-token',(self.root/'front.replicate.json').read_text())
 def test_no_consent_no_submit(self):
  with self.assertRaises(ValueError):self.run_redraw(consent=None)
  self.assertEqual(self.posts,0)
 def test_illegible_no_submit(self):
  with self.assertRaises(ValueError):self.run_redraw(Pet(legible=False))
  self.assertEqual(self.posts,0)
 def test_wrong_digits_no_export_no_retry(self):
  with self.assertRaises(ValueError):self.run_redraw(Pet(mismatch=True))
  with self.assertRaises(ValueError):self.run_redraw()
  self.assertEqual(self.posts,1);self.assertEqual(json.loads((self.root/'front.replicate.json').read_text())['state'],'review')
 def test_unknown_submission_no_retry(self):
  with self.assertRaises(ValueError):self.run_redraw(fail=True)
  with self.assertRaises(ValueError):self.run_redraw()
  self.assertEqual(self.posts,1)
 def test_external_output_rejected(self):
  with self.assertRaises(ValueError):self.run_redraw(url='https://example.org/logo.png')
  self.assertFalse((self.root/'front.replicate.png').exists())
if __name__=='__main__':unittest.main()
