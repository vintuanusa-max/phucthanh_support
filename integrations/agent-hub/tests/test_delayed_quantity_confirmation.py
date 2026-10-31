import ast,copy,json,types
from pathlib import Path
from decimal import Decimal,InvalidOperation
p=Path(__file__).resolve().parents[1]/'hub'/'conversation_confirmation.py'
ns={'json':json,'Decimal':Decimal,'InvalidOperation':InvalidOperation}
exec(compile(ast.Module(body=[n for n in ast.parse(p.read_text(encoding='utf-8')).body if not isinstance(n,(ast.Import,ast.ImportFrom))],type_ignores=[]),str(p),'exec'),ns)
q={'message_id':'q','text':'NAVICO in bao nhiêu cái chú?','timestamp':1000,'origin':'staff','role':'staff'}
a={'message_id':'a','text':'100 cái','timestamp':5000,'origin':'customer','role':'customer'}
proof={'status':'confirmed','covered_batch_ids':['q','a'],'confirmations':[{'question_id':'q','confirmation_id':'a','model':'NAVICO','mode':'total','quantity':'100','unit':'cái','evidence':[{'message_id':'q','quote':q['text']},{'message_id':'a','quote':a['text']}]}]}
ctx={'batch':[q,a],'history':[]};assert ns['validate'](copy.deepcopy(proof),ctx)[0]['quantity']=='100'
old=copy.deepcopy(proof);old['covered_batch_ids']=['a']
try:ns['validate'](old,{'batch':[a],'history':[q]})
except ValueError:pass
else:raise AssertionError('unreclaimed old question must stay blocked')
class DB:
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def execute(self,*a):return self
 def fetchall(self):return [(json.dumps(a),)] # Recent history lacks old question
states=[]
intake=types.SimpleNamespace(store=types.SimpleNamespace(db=lambda:DB()),engine=types.SimpleNamespace(settings=types.SimpleNamespace(gemini_model='fake'),customer_mappings=types.SimpleNamespace(get=lambda *a:{'customer_id':'customer'}),erp=object()),state=lambda *a:states.append(a))
ns['fingerprint']=lambda x:'test';ns['ask']=lambda *a:copy.deepcopy(proof)
ns['cached']=lambda store,key,fn:(fn(),False);ns['reconcile']=lambda *a:None
run={'id':'r','account':'z','thread_id':'same'}
assert ns['apply'](intake,run,copy.deepcopy([q,a])) is False
# Complete image + question + answer, including question's role in scope.
proof['covered_batch_ids']=['i','q','a'];proof['confirmations'][0]['image_source_id']='i'
i={'message_id':'i','text':'image','timestamp':900,'origin':'customer','role':'customer'}
assert ns['apply'](intake,run,copy.deepcopy([i,q,a])) is False
extra={'message_id':'other','text':'mẫu khác 200 cái','timestamp':5001,'origin':'customer','role':'customer'}
proof['covered_batch_ids'].append('other')
try:ns['apply'](intake,run,copy.deepcopy([i,q,a,extra]))
except ValueError as e:assert 'Còn nguồn' in str(e)
else:raise AssertionError('independent request must not be dropped')
proof['covered_batch_ids'].remove('other');ns['reconcile']=lambda *a:{'id':'existing'}
assert ns['apply'](intake,run,copy.deepcopy([i,q,a])) is True
assert states[-1][1]=='duplicate'
print('PASS delayed reclaimed batch; question+answer+image; unrelated request blocked; old unbound question blocked; existing ERP duplicate blocked. No API/ERP writes.')
