import pytest
from hub.confirmation_artwork import select_image
from hub.quantity_confirmation import pair,reconcile
from test_quantity_confirmation import erp

def m(mid,stamp,images=None,**kw):
 return dict(account='a',thread_id='g',message_id=mid,timestamp=stamp,images=images or [],origin='staff',sender='Staff',text='',**kw)

def test_one_uninterrupted_image():
 image=m('image',10,['i']);q=m('q',20)
 assert select_image(q,[image,q])['message_id']=='image'

def test_question_has_image():
 q=m('q',20,['i']);assert select_image(q,[q])==q

def test_explicit_quote_chooses_correct_image_among_many():
 a=m('a',10,['a']);b=m('b',11,['b']);q=m('q',20,quoted_image={'message_id':'a'})
 assert select_image(q,[a,b,q])==a

@pytest.mark.parametrize('history',[ [m('a',10,['a']),m('b',11,['b'])], [m('a',10,['a']),m('text',15)], [m('a',10,['a','b'])], [m('a',-1000,['a'])] ])
def test_ambiguity_blocks(history):
 with pytest.raises(ValueError):select_image(m('q',20),history)

def test_missing_quote_not_fallback():
 with pytest.raises(ValueError):select_image(m('q',20,quoted_image={'message_id':'absent'}),[m('a',10,['a'])])

def test_pair_generic_question_retains_photo_provenance():
 q=m('q',20);q['text']='này in 500 phải ko?'
 customer=m('ack',30);customer.update(origin='customer',text='ok')
 p=pair(customer,[m('image',10,['i']),q],lambda *a:dict(model='LOGO ABC',image_source_id='image',image_sha256='hash',linked_order_id=None))
 assert p['model']=='LOGO ABC' and p['quantity']=='500' and p['image_source_id']=='image'

def test_existing_image_link_cannot_silently_become_new_order():
 with pytest.raises(ValueError):reconcile(erp([]),'c',dict(model='TDVB-SEE.10',quantity='500',linked_order_id='old'))

def test_resolve_reads_once_and_reuses_hash(tmp_path,monkeypatch):
 from test_human_batch_requests import engine
 from hub.confirmation_artwork import resolve
 import hub.intake_preflight as preflight
 s,e=engine(tmp_path)
 monkeypatch.setattr(s,'images',lambda ids:[{'mime_type':'image/png','data':'YWJj'}])
 calls=[]
 def ask(*args):
  calls.append(1)
  return dict(model='LOGO ABC',evidence='LOGO ABC',uncertain=False,multiple_models=False)
 monkeypatch.setattr(preflight,'ask',ask)
 q=m('q',20,quoted_image={'message_id':'image'});source=m('image',10,['i'])
 run=dict(account='a',thread_id='g')
 a=resolve(e.order_intake,run,q,[source,q],{'customer_id':'c'})
 b=resolve(e.order_intake,run,q,[source,q],{'customer_id':'c'})
 assert a==b and len(calls)==1 and a['image_source_id']=='image'
