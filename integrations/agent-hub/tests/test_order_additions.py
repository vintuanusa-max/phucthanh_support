import json
from decimal import Decimal
import pytest
from hub.order_additions import addition_request,resolve_quote_db

def msg(text,mid='m',**kw):
    return dict(account='a',thread_id='g',message_id=mid,sender='Khach',sender_id='s',timestamp=20,text=text,**kw)

def test_delta_and_total_not_double_added():
    r=addition_request([msg('1.070c nhe','a'),msg('In thêm 70c','b')])
    assert r['total']==1070 and r['delta']==70 and r['source_message_id']=='b'

@pytest.mark.parametrize('text',['Không in thêm 70c','In thêm 70c?','In thêm 70c và 30c','In thêm'])
def test_uncertain_not_committed(text):
    with pytest.raises(ValueError):addition_request([msg(text)])

def test_resolve_client_quote_scoped_and_latest_revision():
    import sqlite3
    d=sqlite3.connect(':memory:');d.execute('CREATE TABLE captures(account,thread_id,message_id,revision,payload)')
    old=msg('photo','old',client_message_id='client',images=['i']);old['timestamp']=10
    for group in ['other','g']:
        d.execute('INSERT INTO captures VALUES(?,?,?,?,?)',('a',group,'old',0,json.dumps({**old,'thread_id':group})))
    q=msg('1070c',quoted_image={'message_id':'0','client_message_id':'client','sender_id':'s','resolved':False})
    assert resolve_quote_db(d,q)['message_id']=='old'
    d.execute('INSERT INTO captures VALUES(?,?,?,?,?)',('a','g','old',1,json.dumps({**old,'revision':1})))
    assert resolve_quote_db(d,q) is None

def test_mixed_sender_or_inconsistent_totals_blocked():
    with pytest.raises(ValueError):addition_request([msg('In thêm 70c'),{**msg('1070c','b'),'sender_id':'other'}])
    with pytest.raises(ValueError):addition_request([msg('In thêm 70c'),msg('1070c','b'),msg('1100c','c')])

def test_no_addition_leaves_new_order_path():
    assert addition_request([msg('In 70c')]) is None

def test_recovery_queues_once_without_calling_erp():
    import sqlite3
    from types import SimpleNamespace
    from hub.order_additions import OrderAdditions
    d=sqlite3.connect(':memory:');d.row_factory=sqlite3.Row
    d.execute('CREATE TABLE print_approvals(id PRIMARY KEY,account,thread_id,confirmation,state,payload,created)')
    d.execute('CREATE TABLE print_change_sources(account,thread_id,message_id,identity,PRIMARY KEY(account,thread_id,message_id))')
    states=[];notes=[]
    intake=SimpleNamespace(store=SimpleNamespace(db=lambda:d),engine=SimpleNamespace(print_approvals=SimpleNamespace(route=lambda:{'account':'dest'})),notify=lambda *a:notes.append(a),state=lambda *a:states.append(a))
    additions=OrderAdditions(intake)
    run={'id':'run','account':'a','thread_id':'g'}
    payload={'local_notice':{'run':run,'messages':[msg('In thêm 70c')],'text':'confirmed'}}
    d.execute('INSERT INTO order_additions VALUES(?,?,?,?,?,?,?)',('event','a','g','m','done',json.dumps(payload),'{}'));d.commit()
    assert additions.recover_notice() is True
    assert additions.recover_notice() is False
    assert len(notes)==1 and states==[('run','amended',{})]
    assert d.execute('SELECT count(*) FROM print_approvals').fetchone()[0]==1

def test_literal_search_terms_not_generic_quantity():
    from hub.order_additions import match_terms
    assert match_terms([msg('In thêm 70c')])==[]
    assert match_terms([msg('In thêm mẫu “ENVIRONMENTAL SOLUTION” 70c')])==['ENVIRONMENTAL SOLUTION']

def test_unmatched_addition_stages_delta_only_and_reserves_source():
    import sqlite3
    from types import SimpleNamespace
    from hub.order_additions import OrderAdditions
    d=sqlite3.connect(':memory:');d.row_factory=sqlite3.Row
    d.execute('CREATE TABLE intake_runs(id PRIMARY KEY,state,payload)')
    d.execute('INSERT INTO intake_runs VALUES(?,?,?)',('r','analyzing','{}'));d.commit()
    notes=[]
    intake=SimpleNamespace(store=SimpleNamespace(db=lambda:d),engine=SimpleNamespace(),notify=lambda *a:notes.append(a))
    a=OrderAdditions(intake)
    run={'id':'r','account':'a','thread_id':'g','payload':'{"messages":["a","b"]}'}
    a.new_addition(run,[msg('1070c','a'),msg('In thêm 70c','b')],{'delta':Decimal(70),'source_message_id':'b'},{'customer_id':'c'},'event')
    row=d.execute('SELECT * FROM intake_runs').fetchone();p=json.loads(row['payload'])
    assert row['state']=='awaiting_evidence' and p['orders'][0]['so_luong']=='70'
    assert p['orders'][0]['ma_san_pham'] is None and p['customer_binding']['customer_id']=='c'
    assert d.execute('SELECT state FROM order_additions').fetchone()[0]=='new_order'
    with pytest.raises(sqlite3.IntegrityError):a.new_addition(run,[],{'delta':Decimal(70),'source_message_id':'b'},{'customer_id':'c'},'other')

def test_unavailable_quote_disclosed_without_fabricating_image():
    from hub.order_additions import fallback_sources
    original=msg('In thêm 70c',quoted_image={'resolved':False},images=[])
    result=fallback_sources([original])[0]
    assert result['images']==[] and result['quoted_image'] is None and 'Chưa lấy được ảnh' in result['text']
    assert original['quoted_image']=={'resolved':False}
