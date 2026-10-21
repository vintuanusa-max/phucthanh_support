import json,time
from test_hub import setup
from hub.quality_monitor import category,monitored,GROUPS

def test_scoped_and_candidate_only():
 assert monitored('zalo-personal-1',GROUPS['zalo-personal-1'])
 assert not monitored('other',GROUPS['zalo-personal-1'])
 assert category('file thiếu dấu')=='Sai nội dung'
 assert category('in sai màu')=='Sai màu'
 assert category('ok in nhé') is None
 # Negation is still only a review candidate, never confirmed fault.
 assert category('không có chuyện in sai')=='Lỗi in'

def test_no_auto_order_or_reply_for_monitor_group(setup):
 settings,store,e=setup
 account='zalo-personal-1';thread=GROUPS[account]
 settings.inboxes[account]={'channel':'zalo'}
 store.bind(account,thread,'Renamed File In',11,21)
 assert e.order_intake.accepts({'account':account,'thread_id':thread}) is False
 e.process_incoming('x',{'conversation':{'id':11},'content':'In thêm 70c'})
 assert not e.erp.calls and not e.cw.sent

def test_candidate_durable_once_private_and_bot_ignored(setup):
 settings,store,e=setup;a='zalo-personal-1';g=GROUPS[a]
 settings.inboxes[a]={'channel':'zalo','quality_monitor':{'enabled_after':1},'capture_enabled':True}
 store.bind(a,g,'File In',11,21)
 m={'account':a,'thread_id':g,'message_id':'m','timestamp':time.time()-180,'sender':'Reporter','text':'in sai màu','direction':'incoming','origin':'customer'}
 with store.db() as d:d.execute('INSERT INTO captures VALUES(?,?,?,?,?,?)',('c',a,g,'m',0,json.dumps(m)))

 assert e.quality_monitor.poll() is True
 with store.db() as d:
  p=json.loads(d.execute("SELECT payload FROM quality_events WHERE id='c'").fetchone()[0])
  d.execute("UPDATE quality_events SET next_try=? WHERE id='c'",(time.time()+300,))
 assert 'employee_id' not in p and 'order_id' not in p
 assert e.quality_monitor.poll() is False
 job=store.claim();assert job['kind']=='notice'
 e.process_notice(job['id'],json.loads(job['payload']))
 assert e.cw.sent[-1]['private'] is True
 assert e.quality_monitor.bot({**m,'direction':'outgoing'}) is False
 assert e.quality_monitor.bot({**m,'text':'CHOT-IN-abcdef in sai màu'}) is True
 assert e.quality_monitor.bot(m) is False
