import json,time
import pytest
from test_order_intake import intake,capture
from test_trial_images import IMAGE
from hub.quote_recovery import recover_quotes
from hub.order_groups import image_groups
@pytest.mark.parametrize('wrong_sender',[False,True])
def test_exact_quote_recovery(intake,wrong_sender):
 _,store,_=intake
 capture(store,'1',client_message_id='client1',sender_id='customer',images=[IMAGE],timestamp=time.time()-200)
 capture(store,'2',sender_id='customer',text='25 bộ',timestamp=time.time()-180)
 capture(store,'3',sender_id='customer',text='theo ảnh',timestamp=time.time()-160,attachments=['zalo-desktop:quoted-image-unresolved'],quoted_image={'message_id':'0','sender':'','timestamp':0,'client_message_id':'client1','sender_id':'wrong' if wrong_sender else 'customer','resolved':False})
 with store.db() as d:ms=[json.loads(r[0]) for r in d.execute('select payload from captures order by rowid')]
 recover_quotes(store,ms)
 assert ms[-1]['quoted_image']['resolved'] is (not wrong_sender)
 if not wrong_sender:
  assert ms[-1]['images'] and not ms[-1]['attachments'] and len(image_groups(ms))==1
  with store.db() as d:count=d.execute('select count(*) from media').fetchone()[0]
  recover_quotes(store,ms)
  with store.db() as d:assert d.execute('select count(*) from media').fetchone()[0]==count
