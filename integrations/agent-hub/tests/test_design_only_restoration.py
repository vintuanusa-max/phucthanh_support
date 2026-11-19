import pytest
from types import SimpleNamespace
from hub.raster_consent import owner_restoration_consent
from hub.workflow_errors import issue

B={'id':'brief','account':'z','thread_id':'group','sources':[{'message_id':'design','images':['logo']} ]}
A={'authorized':True,'brief_id':'brief','image_id':'logo'}

def test_owner_authorizes_only_selected_source():
 c=owner_restoration_consent(B,A,'request')
 assert c['source_message_ids']==['design'] and c['method']=='explicit_owner_restoration'

@pytest.mark.parametrize('change',[{'authorized':False},{'brief_id':'old-order'},{'image_id':'tigifood'}])
def test_cross_sample_or_missing_permission_rejected(change):
 with pytest.raises(ValueError):owner_restoration_consent(B,dict(A,**change),'request')

def test_no_owner_request_no_implicit_consent():
 assert owner_restoration_consent(B,None,'request') is None

def test_permission_notice_is_not_pdf_error():
 assert issue('Cần nhân viên hỏi file và khách xác nhận không có trước phục dựng')['code']=='RESTORATION_PERMISSION'

def test_enhance_only_cannot_buy_redraw(tmp_path,monkeypatch):
 import io
 from PIL import Image
 import hub.raster_router as r
 calls=[];out=io.BytesIO();im=Image.new('RGBA',(20,20),'white');im.putpixel((10,10),(0,128,0,255));im.save(out,format='PNG');raw=out.getvalue()
 pet=SimpleNamespace(ask=lambda *a:{'action':'redraw','reason':'blurred','lines':['TEST'],'legible':True,'background':'white','white_artwork':True,'blocking_issues':[]})
 monkeypatch.setattr(r,'redraw',lambda *a,**kw:(calls.append(kw['model']) or raw))
 face={};r.route(pet,raw,{'enhance_only':True},tmp_path,'front',face)
 assert calls==['nightmareai/real-esrgan'] and face['background']=='alpha'

def test_image_failure_is_not_dimension_error():
 assert issue('OpenAI cần kiểm tra nội bộ; không tự gọi lại')['code']=='RASTER_VERIFY_REVIEW'

def test_historical_quantity_rejected_before_ai_or_erp(monkeypatch):
 from hub.agent_loop import AgentLoop
 import hub.agent_loop as m
 def forbidden(*a):raise AssertionError('Should not call AI')
 monkeypatch.setattr(m,'verify_action',forbidden)
 agent=AgentLoop.__new__(AgentLoop)
 args={'items':[{'so_luong':224,'ma_san_pham':None,'ten_mau':'TIGIFOOD'}],'source_message_ids':['old-quantity','size']}
 with pytest.raises(ValueError,match='Wrong draft source:'):
  agent.execute({},'propose_order_draft',args,{'batch':[{'message_id':'size','text':'Chiều cao khoảng 6p5'}]})
