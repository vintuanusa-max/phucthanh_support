import base64, importlib.util, io, sys, types, uuid
from pathlib import Path
from contextlib import contextmanager
from datetime import date
from unittest.mock import Mock
import pytest
from PIL import Image
from hub.slip_orders import parse_fields, product_codes, extract

@pytest.mark.parametrize('code',[None,'','  ','TB1VB-ABC.10 MẪU'])
def test_code_optional_exact_quantity_and_date(code):
    r=parse_fields({'ma_san_pham':code,'so_luong':'3 (gửi lên vp 2c)','ngay_giao_hang':'15/10/2026'})
    assert r['quantity']==3 and r['delivery_date']=='2026-10-15'
    assert r['design_code']==(code.strip() or None if code else None)

@pytest.mark.parametrize('qty',[None,'','0','-2','2.5','2/3','khoảng 3'])
def test_bad_quantity_never_defaults(qty):
    with pytest.raises(ValueError):parse_fields({'so_luong':qty})

@pytest.mark.parametrize('text,sku',[('in CN 2 mặt','TUI'),('in chuyển nhiệt','TUI'),('in PET 1 mặt','PETA4'),('in màng A3','PETA3'),('PET 7x7','PET7X7')])
def test_sku(text,sku):assert product_codes(text)==[sku]

@pytest.mark.parametrize('text',['PET A3 mặt trước A4 mặt sau','CN và PET'])
def test_split_ambiguous_needs_human(text):
    assert product_codes(text)==[]

def test_verification_allows_unknown_code(monkeypatch):
    replies=iter([{'ma_san_pham':None,'so_luong':'2','loai_in':'PET'}]*2)
    monkeypatch.setattr('hub.slip_orders.gemini',lambda *a:next(replies))
    assert extract(None,{})['design_code'] is None

@pytest.fixture
def endpoint(monkeypatch):
    for name in ['psycopg','psycopg.types','psycopg.types.json','backend_v2','backend_v2.db','backend_v2.routers']:
        monkeypatch.setitem(sys.modules,name,types.ModuleType(name))
    sys.modules['psycopg.types.json'].Jsonb=lambda x:x
    back=sys.modules['backend_v2'];back.uploads=types.SimpleNamespace(save=Mock(return_value='saved.png'),remove=Mock())
    back.zalo_integration=types.SimpleNamespace(payload_hash=lambda x:'hash',customer_by_id=lambda c,i:{'id':i})
    class Model:
        def __init__(self,**kw):self.__dict__.update(kw)
    orders=types.SimpleNamespace(DongIn=Model,DonHangCreate=Model,create_order_in_transaction=Mock(return_value=uuid.uuid4()))
    sys.modules['backend_v2.routers'].orders_router=orders
    sys.modules['backend_v2.db'].transaction=lambda:None
    spec=importlib.util.spec_from_file_location('test_slip_endpoint',Path(__file__).resolve().parents[2]/'erp-slip/slip_intake.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.test_orders=orders
    return mod

def payload(mod,**changes):
    image=io.BytesIO();Image.new('RGB',(2,2),'white').save(image,format='PNG')
    raw=dict(request_id='r1',customer_id=str(uuid.uuid4()),source='zalo',source_account='acc',group_id='group',group_name='CANAVI',source_message_id='m1',asset_sha256='a'*64,quantity=3,product_codes=['TUI'],image_base64=base64.b64encode(image.getvalue()).decode(),design_code=None)
    raw.update(changes);return mod.Slip(**raw)

class DB:
    def __init__(self,old=None,duplicates=None):self.old=old;self.duplicates=duplicates or [];self.queries=[];self.result=None
    def execute(self,sql,args=()):
        self.queries.append((sql,args));self.result=None
        if 'SELECT payload_hash' in sql:self.result=self.old
        elif ' AS day' in sql:self.result={'day':date(2026,10,15)}
        elif 'SELECT id,ma_don_hang FROM don_hang WHERE doi_tac_id' in sql:self.result=self.duplicates
        elif 'SELECT id,ma_hang' in sql:self.result=[{'id':uuid.uuid4(),'ma_hang':'TUI'}]
        elif 'SELECT id,ma_don_hang FROM don_hang WHERE id=' in sql:self.result={'id':uuid.uuid4(),'ma_don_hang':'DH-test'}
        return self
    def fetchone(self):return self.result
    def fetchall(self):return self.result or []

def connect(mod,db):
    @contextmanager
    def tx():yield db
    mod.transaction=tx

def test_missing_code_creates_len_mau_with_image(endpoint):
    m=endpoint;d=DB();connect(m,d);r=m.create(payload(m))
    assert r['status']=='created' and r['auto_order_name']
    order=m.test_orders.create_order_in_transaction.call_args.args[1]
    assert order.ten_don_hang is None and order.trang_thai=='len_mau'
    assert order.dong[0].loai_san_pham_id is not None
    queries=[x[0] for x in d.queries]
    assert next(i for i,s in enumerate(queries) if 'INSERT INTO zalo_intake' in s)<next(i for i,s in enumerate(queries) if 'INSERT INTO zalo_order_source' in s)
    assert m.uploads.save.called

def test_receipt_replay_does_not_write(endpoint):
    m=endpoint;d=DB(old={'payload_hash':'hash','response':{'status':'created'}});connect(m,d)
    assert m.create(payload(m))=={'status':'created'}
    assert not m.test_orders.create_order_in_transaction.called

def test_same_day_existing_code_not_recreated(endpoint):
    m=endpoint;d=DB(duplicates=[{'id':uuid.uuid4(),'ma_don_hang':'DH-old'}]);connect(m,d)
    assert m.create(payload(m,design_code='TB1VB-A MẪU'))['status']=='duplicate'
    assert not m.test_orders.create_order_in_transaction.called
    assert any("Asia/Ho_Chi_Minh" in s and '::date=%s' in s for s,a in d.queries)

def test_quantity_required_server_side(endpoint):
    with pytest.raises(ValueError):payload(endpoint,quantity=0)

def test_cleanup_after_db_failure(endpoint):
    m=endpoint;d=DB();real=d.execute
    def fail(sql,args=()):
        if 'INSERT INTO anh_don_hang' in sql:raise RuntimeError('db failed')
        return real(sql,args)
    d.execute=fail;connect(m,d)
    with pytest.raises(RuntimeError):m.create(payload(m))
    m.uploads.remove.assert_called_once_with('saved.png')

def test_machine_auth_required(endpoint):
    from fastapi import FastAPI, APIRouter, HTTPException
    from fastapi.testclient import TestClient
    app=FastAPI();router=APIRouter()
    def denied():raise HTTPException(401,'no token')
    endpoint.register_routes(router,denied);app.include_router(router)
    client=TestClient(app)
    assert client.get('/production-slip/capabilities').status_code==401
    assert client.post('/production-slip/orders',json=payload(endpoint).model_dump(mode='json')).status_code==401

def test_unrelated_unknown_slips_not_deduped_by_placeholder(endpoint):
    m=endpoint;d=DB();connect(m,d);m.create(payload(m))
    assert not any('WHERE doi_tac_id=%s' in sql for sql,args in d.queries)

from test_order_intake import intake, capture

def test_recognized_slip_reserved_from_generic_pipeline(intake):
    settings,store,engine=intake
    settings.inboxes['wa-1']['production_slips']={'auto_order':True}
    capture(store,text='in 3 cái')
    with store.db() as db:
        m=__import__('json').loads(db.execute('SELECT payload FROM captures LIMIT 1').fetchone()[0])
        db.execute('INSERT INTO production_slips VALUES(?,?,?,?,?,?)',('slip',m['account'],m['thread_id'],m['message_id'],'copied','{}'))
    assert engine.order_intake.accepts(m) is False

def test_restart_never_replays_uncertain_slip(intake):
    from hub.slip_orders import SlipOrders
    _,store,engine=intake
    with store.db() as db:db.execute("INSERT INTO production_slip_orders VALUES('x','sending','{}','{}')")
    SlipOrders(engine)
    with store.db() as db:assert db.execute("SELECT state FROM production_slip_orders WHERE id='x'").fetchone()[0]=='uncertain'

def test_uncertain_code_verification_does_not_block_order(monkeypatch):
    replies=iter([{'ma_san_pham':'TB?VB-MẪU','so_luong':'2','loai_in':'PET'},{'ma_san_pham':'TB1VB-MẪU','so_luong':'2','loai_in':'PET'}])
    monkeypatch.setattr('hub.slip_orders.gemini',lambda *a:next(replies))
    result=extract(None,{})
    assert result['quantity']==2 and result['design_code'] is None

def test_verified_exact_code_is_kept(monkeypatch):
    replies=iter([{'ma_san_pham':'TB1VB-ABC.10 MẪU','so_luong':'2','loai_in':'PET'},{'ma_san_pham':'TB1VB-ABC.10 MẪU','so_luong':'2','loai_in':'PET'}])
    monkeypatch.setattr('hub.slip_orders.gemini',lambda *a:next(replies))
    assert extract(None,{})['design_code']=='TB1VB-ABC.10 MẪU'

@pytest.mark.parametrize('codes',[[],['PET99X99']])
def test_missing_catalog_code_creates_waiting_product(endpoint,codes):
    m=endpoint;d=DB();connect(m,d);result=m.create(payload(m,design_code='TB1VB-EXACT.10 MẪU',product_codes=codes))
    order=m.test_orders.create_order_in_transaction.call_args.args[1]
    assert order.ten_don_hang=='TB1VB-EXACT.10 MẪU'
    assert order.dong[0].loai_san_pham_id is None and result['waiting_product_code']
    assert 'CHỜ MÃ HÀNG' in order.ghi_chu

def test_quantity_disagreement_blocks_submission(monkeypatch):
    values=iter([{'so_luong':'2','loai_in':'PET'},{'so_luong':'3','loai_in':'PET'}])
    monkeypatch.setattr('hub.slip_orders.gemini',lambda *a:next(values))
    with pytest.raises(ValueError):extract(None,{})

@pytest.mark.parametrize('text',['','không rõ','khác'])
def test_unrecognized_type_waits_for_catalog_code(text):assert product_codes(text)==[]
