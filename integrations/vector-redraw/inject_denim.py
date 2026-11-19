import base64,sqlite3,json,sys,time
from hub.config import Settings
from hub.models import Capture
from hub.clients import Chatwoot
s=Settings.environment()
db=sqlite3.connect(s.database)
acct='zalo-personal-1';thread='g8534414090274815910';mid='simulation-denim-autodetect-20261119-v1'
group,conv=db.execute('select display_name,conversation from threads where account=? and thread_id=?',(acct,thread)).fetchone()
assert conv==72 and Chatwoot(s).conversation(conv)['meta']['sender']['name']==group
m=Capture(account=acct,thread_id=thread,message_id=mid,display_name=group,sender='Simulation',sender_id='redraw-test',origin='customer',direction='incoming',timestamp=time.time(),text='v\u1ebd l\u1ea1i m\u1eabu n\u00e0y',images=[{'mime_type':'image/png','data':sys.stdin.read().strip()}])
db.execute('insert into captures(id,account,thread_id,message_id,revision,payload) values(?,?,?,?,?,?)',(mid,acct,thread,mid,0,m.model_dump_json()))
db.commit()
print('simulation capture',db.execute('select rowid from captures where id=?',(mid,)).fetchone()[0])
