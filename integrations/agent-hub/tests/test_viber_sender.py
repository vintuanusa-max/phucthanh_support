import time
from types import SimpleNamespace
from viber_desktop.send_ledger import SendLedger
from viber_desktop.sender import deliver, reconcile


def test_native_send_is_not_repeated_after_ambiguous_result(tmp_path):
    calls=[]
    source=SimpleNamespace(read=lambda cutoff: [])
    client=SimpleNamespace(post=lambda *a,**kw: SimpleNamespace(raise_for_status=lambda: None))
    cfg={'enabled_after':time.time()-10,'account':'viber-personal-1'}
    item={'id':'cw:9','thread_id':'viber:g1','message':{'content':'test','private':False,
          'sender':{'type':'user','id':4},'created_at':time.time()}}
    ledger=SendLedger(tmp_path/'sender.db')
    def transport(text,**kwargs):
        calls.append(text)
        return {'accepted':False,'clean':True}
    assert deliver(item,cfg,source,ledger,client,transport)['state']=='uncertain'
    assert deliver(item,cfg,source,ledger,client,transport)['state']=='uncertain'
    assert calls==['test']
    ledger.close()


def test_private_note_is_blocked_before_source_or_transport(tmp_path):
    def forbidden(*a,**kw): raise AssertionError('Should not be called')
    item={'id':'cw:1','thread_id':'viber:g1','message':{'private':True,'content':'AI note'}}
    cfg={'enabled_after':time.time()-10,'account':'viber-personal-1'}
    ledger=SendLedger(tmp_path/'sender.db')
    assert deliver(item,cfg,SimpleNamespace(read=forbidden),ledger,None,forbidden)['state']=='blocked'
    ledger.close()


def test_source_match_excludes_old_incoming_and_different_text():
    now=time.time()
    def row(eid,direction='1',text='hello',stamp=None):
        return [eid,str(int((stamp or now)*1000)),direction,'1','','','1',text,'']
    rows=[row('old'),row('new'),row('incoming','0'),row('other',text='different'),row('stale',stamp=now-30)]
    assert [r[0] for r in reconcile(rows,{'old'},'hello',now)]==['new']
