from whatsapp_desktop.source import convert


def test_v8_one_byte_display_names():
    from whatsapp_desktop.source import text_field
    assert text_field(b'Ch\xe2u')=='Châu'
    assert text_field({'unexpected':1})==''


def test_group_join_direction_and_policy():
    thread='123@g.us';m={'id':'false_123@g.us_MSG_sender@lid','t':100,'rowId':42,'type':'chat'}
    g={thread:'Khách A'};b={'42':(thread,100,'Đặt 5')}
    result=convert(m,g,{'sender@lid':'Khách'},b,'wa',{})
    assert result['text']=='Đặt 5' and result['sender']=='Khách' and result['origin']=='customer'
    assert convert(m,g,{},b,'wa',{'whatsapp_skip_groups':['Khách A']}) is None
    m['id']='true_123@g.us_MSG_sender@lid'
    assert convert(m,g,{},b,'wa',{})['origin']=='staff'


def test_private_and_unknown_content_are_not_orders():
    assert convert({'id':'false_123@c.us_MSG','t':100}, {},{}, {},'wa',{}) is None
    m={'id':'false_123@g.us_MSG_sender@lid','t':100,'type':'image'}
    assert convert(m,{'123@g.us':'Group'}, {},{},'wa',{})['attachments']
