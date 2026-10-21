from types import SimpleNamespace
import pytest
from hub.order_groups import image_groups, validate_group_quantity


def test_image_quantity_then_album_and_colour_quantities():
    messages = [{'images':['a'], 'text':''}, {'text':'66m in chuyển nhiệt.500 in Pet'},
                {'images':['b'], 'text':''}, {'images':['c'], 'text':''},
                {'text':'125 trắng,125 đen chỉnh lại như yêu cầu của khách'}, {'text':'Hàng sẵn'}]
    groups = image_groups(messages)
    assert [[n for n, _ in g] for g in groups] == [[1,2],[3,4,5,6]]
    validate_group_quantity([SimpleNamespace(so_luong=66),SimpleNamespace(so_luong=500)],messages[:2])
    with pytest.raises(ValueError):
        validate_group_quantity([SimpleNamespace(so_luong=500)],messages[2:])


def test_album_without_quantity_stays_together():
    assert len(image_groups([{'images':['a']},{'images':['b']},{'images':['c']},{'text':'100 cái'}])) == 1


def test_caption_quantity_and_followup_image():
    assert len(image_groups([{'images':['a'],'text':'100 cái'}, {'images':['b'],'text':'50 cái'}])) == 2

def test_separate_group_models_and_one_durable_request(intake, monkeypatch):
    from hub.models import IntakeDecision
    from test_order_intake import capture, rows
    from test_trial_images import IMAGE
    import json,time
    _,store,engine=intake
    values=[dict(images=[IMAGE],text='ảnh'),dict(text='66m chuyển nhiệt 500 PET'),
            dict(images=[IMAGE],text='ảnh trắng'),dict(images=[IMAGE],text='ảnh đen'),
            dict(text='125 trắng 125 đen'),dict(text='Hàng sẵn')]
    for n,v in enumerate(values,1):capture(store,str(n),timestamp=time.time()-220+n,**v)
    seen=[]
    def decide(ctx):
        seen.append(ctx)
        ids=[m['id'] for m in ctx['messages']]
        qty=[66,500] if ids==[1,2] else [125,125]
        return IntakeDecision(action='draft_order',source_message_ids=ids,orders=[dict(ma_san_pham=None,so_luong=q) for q in qty])
    engine.agent.decide=decide
    monkeypatch.setattr('hub.agent_loop.verify_action',lambda *args:None)
    engine.order_intake.poll()
    row=rows(store)[0]
    assert row['state']=='awaiting_evidence'
    payload=json.loads(row['payload'])
    assert payload['image_groups']==[['1','2'],['3','4','5','6']]
    assert len(seen[0]['images'])==1 and len(seen[1]['images'])==2
    assert [float(o['so_luong']) for o in payload['orders']]==[66,500,125,125]
    assert not engine.erp.calls
    engine.order_intake.poll()
    assert len(rows(store))==1
from test_order_intake import intake

def test_group_verifier_rejects_before_any_erp_write(intake, monkeypatch):
    from hub.models import IntakeDecision
    from test_order_intake import capture, rows
    from test_trial_images import IMAGE
    import time
    _,store,engine=intake
    for n,v in enumerate([dict(images=[IMAGE],text='ảnh'),dict(text='10 cái'),dict(images=[IMAGE],text='20 cái')],1):
        capture(store,str(n),timestamp=time.time()-220+n,**v)
    engine.agent.decide=lambda c:IntakeDecision(action='draft_order',source_message_ids=[m['id'] for m in c['messages']],orders=[dict(ma_san_pham=None,so_luong=10)])
    def reject(*args):raise ValueError('uncertain relationship')
    monkeypatch.setattr('hub.agent_loop.verify_action',reject)
    engine.order_intake.poll()
    assert rows(store)[0]['state']=='review' and not engine.erp.calls
