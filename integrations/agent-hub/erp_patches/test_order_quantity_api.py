import uuid
import pytest
from fastapi import HTTPException
from order_quantity_intake import Addition,validate_lines

def request():
    line=str(uuid.uuid4())
    r=Addition(request_id='x'*64,customer_id=uuid.uuid4(),order_id=uuid.uuid4(),source_account='zalo',group_id='g',source_message_id='m',delta='70',lines=[{'id':line,'expected':'1000','target':'1070'}])
    return r,line

def test_delta_guard():
    r,line=request();data=r.model_dump();data['lines'][0]['target']=2070
    with pytest.raises(ValueError):Addition(**data)

def test_compare_and_swap_rejects_changed_or_extra_lines():
    r,line=request();validate_lines([{'id':line,'so_luong':'1000'}],r.lines)
    for lines in [[{'id':line,'so_luong':'1070'}],[{'id':line,'so_luong':'1000'},{'id':str(uuid.uuid4()),'so_luong':'1000'}]]:
        with pytest.raises(HTTPException) as exc:validate_lines(lines,r.lines)
        assert exc.value.status_code==409

def test_three_calendar_days_vietnam_boundaries():
    from datetime import datetime,timezone
    from order_quantity_intake import recent_order
    now=datetime(2026,10,17,1,tzinfo=timezone.utc)
    assert recent_order('2026-10-15T00:00:00+07:00',now)
    assert recent_order('2026-10-17T08:00:00+07:00',now)
    assert not recent_order('2026-10-14T23:59:59+07:00',now)
    assert not recent_order('2026-10-18T00:00:00+07:00',now)
    assert not recent_order(None,now)
    assert recent_order('2026-10-14T17:00:00+00:00',now)
