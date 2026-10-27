import pytest
from types import SimpleNamespace
from hub.intake_preflight import route,obvious_non_order,can_skip

@pytest.mark.parametrize('text,intent',[
 ('Xem lại mẫu này sao bị lệch vậy em?','complaint'),
 ('Logo này bị mờ rồi','complaint'),('Ảnh mẫu này sao bị gì đó','complaint'),
 ('Mẫu này sai màu sao vậy?','complaint'),('Đơn này xong chưa?','progress'),
 ('Mẫu này giá bao nhiêu?','quote'),('Báo giá mẫu này nhé','quote'),
 ('Gửi hàng chưa em?','delivery'),('Cho hỏi chất liệu gì vậy?','information'),
 ('Túi này vải gì?','information')])
def test_question_with_photo_zero_ai_zero_erp(text,intent,monkeypatch):
 calls=[];intake=SimpleNamespace(state=lambda *a:calls.append(a))
 monkeypatch.setattr('hub.intake_preflight.ask',lambda *a:pytest.fail('AI must not run'))
 assert route(intake,{'id':'r'},[{'message_id':'m','text':text,'images':['fake-photo']}])
 assert calls[0][1]=='ignored' and calls[0][2]['intent']==intent and not calls[0][2]['image_read'] and not calls[0][2]['erp_committed']

@pytest.mark.parametrize('tail',['in thêm 200 cái','đặt thêm 50','cho em 300 cái','in 400','làm mẫu thử','làm luôn như hình','em cần in mẫu này','200 cái nhé'])
def test_mixed_request_never_fast_skip(tail):
 messages=[{'message_id':'1','text':'Mẫu này bị mờ, '+tail,'images':['photo']}]
 assert obvious_non_order(messages) is None
 if 'thêm' in tail or 'cái' in tail:
  assert not can_skip(dict(intent='complaint',certain=True,has_order_or_sample_request=False,source_message_ids=['1'],reason='bad classifier'),messages)

def test_separate_new_quantity_survives():
 assert obvious_non_order([{'text':'Mẫu này bị lệch','images':['p']},{'text':'200'}]) is None

def test_unknown_image_or_extra_file_not_discarded():
 assert obvious_non_order([{'text':'[Ảnh Zalo]','images':['p']}]) is None
 assert obvious_non_order([{'text':'Mẫu này bị lệch','images':['p']},{'text':'[Ảnh Zalo]','images':['q']}]) is None
 assert obvious_non_order([{'text':'Mẫu này bị lệch','assets':[{'name':'new.pdf'}]}]) is None

def test_quantity_is_not_rewritten():
 msgs=[{'text':'100 cái trước bị lệch, in thêm 200 cái','images':['p']}]
 before=repr(msgs);assert obvious_non_order(msgs) is None;assert repr(msgs)==before

@pytest.mark.parametrize('text',['100 cái trước bị lệch, in thêm 200 cái','Mẫu này sao bị mờ? In thêm 200 cái','Hàng cũ chưa rõ nét; đặt thêm 200 cái'])
def test_new_delta_from_separate_complaint_clause(text):
 from hub.order_additions import addition_request
 r=addition_request([{'text':text,'message_id':'n','sender':'Khách','sender_id':'c'}]);assert r['delta']==200 and r['total'] is None
@pytest.mark.parametrize('text',['Không in thêm 200 cái','Nếu sửa được mẫu, in thêm 200 cái','Mẫu bị mờ, in thêm 200 cái?','Mẫu bị lệch, in thêm 200 cái và 300 cái'])
def test_conditional_or_conflicting_addition_still_blocks(text):
 from hub.order_additions import addition_request
 with pytest.raises(ValueError):addition_request([{'text':text,'message_id':'n','sender':'Khách','sender_id':'c'}])
