import pytest
from decimal import Decimal
from types import SimpleNamespace
from hub.meter_product import meter_quantity,apply_meter_product
from test_order_intake import intake,capture,rows
from hub.models import IntakeDecision
import json
@pytest.mark.parametrize('text,value',[
 ('@Thôngg lô 1205 in cho c 4 mét trên vải kim ánh hộ c',4),
 ('In 4m trên vải kim ánh',4),('in giúp 4,5 mét trên vải',Decimal('4.5')),
 ('in 4.5m tren vai',Decimal('4.5')),
 ('giao thêm 4 mét vải',None),('vải khổ 4 mét',None),
 ('in ảnh trên vải kích thước 4m x 2m',None),('in 4 mét trên vải giá bao nhiêu',None),
 ('không in 4 mét trên vải',None),('in 4 mét trên giấy',None),
 ('in 4m2 trên vải',None),('in 4mm trên vải',None)])
def test_parser(text,value): assert meter_quantity(text)==value
@pytest.mark.parametrize('code,quantity,origin,expected',[(None,4,'customer',True),('MET',4,'customer',True),('PETA4',4,'customer',False),(None,5,'customer',False),(None,4,'staff',False)])
def test_scope(code,quantity,origin,expected):
 line=SimpleNamespace(ma_san_pham=code,so_luong=Decimal(quantity))
 assert apply_meter_product([line],[{'text':'in 4 mét trên vải','origin':origin}]) is expected
 assert line.ma_san_pham==('MET' if expected else code)
def test_intake_maps_met(intake):
 _,store,engine=intake
 capture(store,text='@Thôngg lô 1205 in cho c 4 mét trên vải kim ánh hộ c')
 engine.agent.decision=IntakeDecision(action='draft_order',source_message_ids=[1],orders=[{'ma_san_pham':None,'so_luong':4}])
 engine.order_intake.poll()
 row=rows(store)[0]
 assert row['state']=='awaiting_evidence',row
 assert json.loads(row['payload'])['orders'][0]['ma_san_pham']=='MET'
 assert not engine.erp.calls
