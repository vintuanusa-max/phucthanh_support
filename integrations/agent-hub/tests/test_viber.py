from viber_desktop.source import convert
from hub.order_policy import capture_allowed, eligible

def test_caption_and_staff_identity():
    row=['544','1792055341272','1','1','','\u2068Thiết Kế\u2069','2','caption','image.jpg']
    m=convert(row,'viber-personal-1','viber:g1','CDG')
    assert m['text']=='caption' and m['origin']=='staff' and m['sender']=='Thiết Kế'
    assert m['timestamp']==1792055341.272

def test_system_message_ignored():
    assert convert(['543','1792055341272','1','1','','staff','65','rename',''],'a','viber:g1','CDG') is None

def test_fail_closed_scope():
    assert not capture_allowed({},'viber','viber:g1','CDG')
    assert capture_allowed({'viber_allowed_thread_ids':['viber:g1']},'viber','viber:g1','renamed')
    assert not capture_allowed({'viber_allowed_thread_ids':['viber:g1']},'viber','private:1','CDG')
    assert not eligible({},'viber',{})

def test_public_ai_never_delivered_even_live():
    import time
    from types import SimpleNamespace
    from hub.delivery_policy import delivery_block
    cfg=dict(channel='viber',delivery_enabled=True,human_delivery_enabled=True,
             delivery_allowed_threads=['viber:g1'],delivery_after=time.time()-60)
    human=dict(sender={'type':'user','id':4},private=False,content='test',created_at=time.time())
    assert delivery_block(SimpleNamespace(mode='live'),cfg,human,'viber:g1')==''
    for patch in [dict(private=True),dict(sender={'type':'agent_bot','id':4}),
                  dict(content_attributes={'phucthanh':{'origin':'ai'}}),dict(created_at=time.time()-600)]:
        assert delivery_block(SimpleNamespace(mode='live'),cfg,{**human,**patch},'viber:g1')
    assert delivery_block(SimpleNamespace(mode='live'),cfg,human,'viber:g2')
