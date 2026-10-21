from datetime import datetime,timezone,timedelta
from hub.leave_monitor import parse,summarize
TS=datetime(2026,10,1,8,tzinfo=timezone(timedelta(hours=7))).timestamp()
def msg(text,id='1',sid='person'):
 return dict(text=text,message_id=id,sender_id=sid,sender='Test',timestamp=TS)
def test_dates_half_and_repeats():
 ms=[msg('Em xin nghỉ 5/10'),msg('Em xin nghỉ 5/10','2'),msg('Em xin phép nghỉ chiều 8/10','3')]
 g,u=summarize(ms);assert not u and g[('person','2026-10')]['total']==1.5
def test_two_halves_same_day_and_next_month():
 g,_=summarize([msg('Em xin nghỉ sáng nay'),msg('Em xin nghỉ chiều nay','2'),msg('Em xin nghỉ 1/11','3')])
 assert g[('person','2026-10')]['total']==1
 assert g[('person','2026-11')]['total']==1
def test_on_behalf_not_sender():
 assert 'unclear' in parse(msg('B Phương xin phép nghỉ chiều 15/10'))
 g,u=summarize([msg('Anh chị cho e với B Phương xin nghỉ 5/10')])
 assert g[('person','2026-10')]['shared'] and len(g)==1
def test_corrections_and_unknown():
 for t in ['Em không xin nghỉ nữa','Em xin đổi ngày nghỉ 5/10','Em xin nghỉ thứ 2','Em xin nghỉ 31/2','Em xin nghỉ từ 5/10 đến 8/10']:
  assert 'unclear' in parse(msg(t))
def test_tomorrow_word_date_and_sender_ids():
 assert parse(msg('Anh xin phép nghỉ ngày mai'))['date']=='2026-10-02'
 assert parse(msg('Anh xin phép nghỉ ngày 6 tháng 10'))['date']=='2026-10-06'
 g,_=summarize([msg('Em xin nghỉ 5/10',sid='a'),msg('Em xin nghỉ 5/10',sid='b')]);assert len(g)==2
