import json
import sqlite3

import pytest

from zalo_desktop.quotes import attach_quote
from hub.models import Capture


@pytest.fixture
def source(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('create table message(msgId,cliMsgId,toUid,fromUid,msgType,ev,serverTime,sendDttm,dName,message)')
    db.execute('insert into message values(?,?,?,?,?,?,?,?,?,?)',
        ('42','111','g123','staff',2,0,1000,1000,'Nhân viên','encrypted'))
    monkeypatch.setattr('zalo_desktop.quotes.decode_field', lambda *a: {'oriUrl':'https://photo.zdn.vn/original.jpg'})
    yield db
    db.close()


def resolve(db, **overrides):
    q = dict(globalMsgId='42',cliMsgId='111',ownerId='staff',ts=1000,cliMsgType=32,
             attach='{"href":"https://wrong.example/untrusted.jpg"}')
    q.update(overrides)
    m = dict(account='a',thread_id='g123',message_id='43',display_name='Khách',sender='Customer',
             timestamp=2,text='@Nhân viên mẫu ok SL=100c',attachments=[],images=[])
    attach_quote(m, {'quote':json.dumps(q)}, db, b'key', True)
    return m


def test_exact_staff_quote_uses_original_not_quote_url(source):
    m=resolve(source)
    assert m['quoted_image']['resolved']
    assert m['quoted_image']['sender']=='Nhân viên'
    assert m.pop('_asset_requests')[0]['url']=='https://photo.zdn.vn/original.jpg'
    assert Capture.model_validate(m).quoted_image.message_id=='42'


@pytest.mark.parametrize('changed', [dict(globalMsgId='99'),dict(ownerId='other'),dict(cliMsgId='222'),dict(ts=999)])
def test_missing_or_mismatched_reference_never_uses_nearest_photo(source, changed):
    m=resolve(source,**changed)
    assert not m['quoted_image']['resolved']
    assert '_asset_requests' not in m
    assert 'zalo-desktop:quoted-image-unresolved' in m['attachments']


def test_cross_group_and_future_source_rejected(source):
    source.execute("update message set toUid='g999'")
    assert not resolve(source)['quoted_image']['resolved']
    source.execute("update message set toUid='g123',serverTime=3000")
    assert not resolve(source,ts=3000)['quoted_image']['resolved']
