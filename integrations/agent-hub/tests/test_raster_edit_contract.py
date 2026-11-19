import base64,io,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from PIL import Image
from hub import raster_instructions as ins
from hub import openai_redraw as oa
from hub import raster_router as rr
ctx={'batch':[{'message_id':'m1','sender_id':'c','role':'customer','text':'Lên mẫu đổi OLD thành NEW theo ghi chú'}]}
images={'img1':({}, {'message_id':'source1'})}
spec={'mode':'edit','request_message_id':'m1','request_quote':'Lên mẫu đổi OLD thành NEW theo ghi chú','evidence':[{'kind':'text','source_id':'m1','quote':'đổi OLD thành NEW'},{'kind':'image','source_id':'img1','quote':'NEW'}],'changes':['Replace OLD with NEW'],'expected_lines':['NEW'],'preserve':['white border'],'reason':'customer change'}
permission=ins.permission(spec,ctx,images,'test','thread','img1');permission['source_message_id']='source1'
assert permission and ins.validate(spec,ctx,images)
for change in ({'request_message_id':'wrong'},{'request_quote':'invented'},{'mode':'preserve'},{'evidence':[{'kind':'image','source_id':'other','quote':'NEW'}]}):
 try:ins.validate(dict(spec,**change),ctx,images);raise AssertionError('bad proof accepted')
 except ValueError:pass
assert 'NEW' in ins.generation_prompt(['NEW'],spec)
assert 'intentional' in ins.verification_prompt(spec)
buf=io.BytesIO();im=Image.new('RGBA',(30,30),(0,0,0,0));im.paste((255,255,255,255),(8,8,22,22));im.save(buf,format='PNG');raw=buf.getvalue()
class Response:
 status_code=200;headers={'x-request-id':'fake'}
 def json(self):return {'data':[{'b64_json':base64.b64encode(raw).decode()}],'usage':{}}
class Client:
 def __init__(self):self.calls=[]
 def post(self,*args,**kw):self.calls.append(kw);return Response()
read=Path.read_text
with tempfile.TemporaryDirectory() as t:
 folder=Path(t)/'face';folder.mkdir()
 pet=SimpleNamespace(root=Path(t),e=SimpleNamespace(settings=SimpleNamespace()),ask=Mock(return_value={'pass':True,'lines':['NEW'],'issues':[]}))
 client=Client()
 def local_read(p,*a,**kw):return 'fake-test-key' if str(p)=='/data/secrets/openai-api-key' else read(p,*a,**kw)
 with patch('hub.execution_models.select',return_value='fake-model'),patch.object(Path,'read_text',local_read):
  assert oa.redraw(pet,raw,permission,folder,'front',['NEW'],client=client,instructions=spec)==raw
  assert 'Replace OLD with NEW' in client.calls[0]['data']['prompt']
  assert oa.redraw(pet,raw,permission,folder,'front',['NEW'],client=client,instructions=spec)==raw
  other=Path(t)/'other';other.mkdir();oa.redraw(pet,raw,permission,other,'front',['NEW'],client=client,instructions=spec)
  assert len(client.calls)==1,'duplicate paid call'
  try:oa.redraw(pet,raw,permission,folder,'front',['NEW'],client=client,instructions=dict(spec,changes=['different']));raise AssertionError('changed edit reused')
  except ValueError:pass
  receipt=json.loads((folder/'front.openai.json').read_text());receipt['state']='submitting';(folder/'front.openai.json').write_text(json.dumps(receipt))
  try:oa.redraw(pet,raw,permission,folder,'front',['NEW'],client=client,instructions=spec);raise AssertionError('uncertain retried')
  except ValueError:pass
  assert len(client.calls)==1
# White details take segmentation even under enhance_only; no exterior-white shortcut.
with tempfile.TemporaryDirectory() as t:
 plan={'action':'keep','reason':'clear','lines':['OLD'],'legible':True,'background':'white','white_artwork':True,'blocking_issues':[]}
 pet=SimpleNamespace(ask=Mock(return_value=plan));face={}
 with patch.object(rr,'redraw',return_value=raw) as segmentation:
  rr.route(pet,raw,dict(permission,enhance_only=True),Path(t),'front',face)
  assert segmentation.call_args.kwargs['model']=='men1scus/birefnet' and face['background']=='alpha'
# Raster sizing and white pixels survive export without Adobe/RIP.
from hub.raster_pet import render
with tempfile.TemporaryDirectory() as t:
 target=Path(t)/'sample.png';face={'background':'alpha','white_artwork':True,'product_kind':'other','dimensions_basis':'explicit_measurement','width_cm':0,'height_cm':6.5,'side':'front'}
 result=render(raw,face,target)
 with Image.open(target) as output:assert output.getpixel((output.width//2,output.height//2))[:3]==(255,255,255)
 assert abs(result['height_cm']-6.5)<.001
print('PASS source binding, edit prompts, verification, at-most-once/cache, changed/uncertain receipt guards, white preservation and PNG dimensions; zero real API/ERP calls')
