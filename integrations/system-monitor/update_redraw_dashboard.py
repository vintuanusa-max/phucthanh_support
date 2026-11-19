from pathlib import Path
import sqlite3,json,subprocess,hashlib
base=Path.cwd();v=base.parent/'VectorRedraw'
schema="create table if not exists redraw_clusters(job text primary key,account text,thread text,message text,source text,conversation integer,group_name text,brief text,created real,archive_group text)"
db=sqlite3.connect(v/'state.sqlite');db.execute(schema)
known=dict(db.execute('select id,status from jobs'))
q="""from hub.config import Settings
import sqlite3,json
d=sqlite3.connect(Settings.environment().database)
print(json.dumps(d.execute('select c.account,c.thread_id,c.message_id,t.conversation,t.display_name,json_extract(c.payload,\'$.text\'),json_extract(c.payload,\'$.timestamp\') from captures c join threads t using(account,thread_id) where c.revision=0').fetchall()))"""
# Use parameter-safe SQL quoting inside container script.
q=q[:q.index('print(')]+'''print(json.dumps(d.execute("select c.account,c.thread_id,c.message_id,t.conversation,t.display_name,json_extract(c.payload,'$.text'),json_extract(c.payload,'$.timestamp') from captures c join threads t using(account,thread_id) where c.revision=0").fetchall()))'''
for a,t,m,c,g,brief,ts in json.loads(subprocess.check_output(['docker','exec','phucthanh-chatwoot-hub-1','/app/.venv/bin/python','-c',q])):
 k=hashlib.sha256(json.dumps([a,t,m]).encode()).hexdigest()[:20]
 if k in known:db.execute('insert or ignore into redraw_clusters values(?,?,?,?,?,?,?,?,?,?)',(k,a,t,m,m,c,g,brief,ts,'A LUOM' if t=='g8534414090274815910' else g))
db.commit();print('verified history matched',db.execute('select count(*) from redraw_clusters').fetchone()[0])
def edit(p,old,new):
 s=p.read_text(encoding='utf-8-sig');assert s.count(old)==1,old[:80]
 q=p.with_suffix('.redraw-tmp');q.write_text(s.replace(old,new),encoding='utf8');q.replace(p)
p=v/'worker.py';needle='    source=call("source",identity=identity)'
edit(p,needle,'''    db.execute('''+repr(schema)+''')
    quoted=m.get("quoted_image") or m.get("quoted_file") or {}
    archive="A LUOM" if m["thread_id"]=="g8534414090274815910" else group
    db.execute("insert or ignore into redraw_clusters values(?,?,?,?,?,?,?,?,?,?)",(job,*identity,quoted.get("message_id") or identity[2],conv,group,m.get("text",""),m["timestamp"],archive));db.commit()
'''+needle)
edit(p,"        except Exception as exc:db.execute(","        except Exception as exc:\n            failure_key=hashlib.sha256(json.dumps([m['account'],m['thread_id'],m['message_id']]).encode()).hexdigest()[:20]\n            db.execute(\"update jobs set status=? where id=? and status not like 'chatwoot:%'\",('error:'+type(exc).__name__,failure_key))\n            db.execute(")
p=base/'server.py';needle="  if self.path.startswith('/batch/'):"
edit(p,needle,'''  if self.path=='/api/redraw-clusters':
   import sqlite3
   from contextlib import closing
   path=Path(__file__).resolve().parent.parent/'VectorRedraw'/'state.sqlite'
   with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
    db.row_factory=sqlite3.Row
    rows=db.execute("select c.*,coalesce(j.status,'received') as status from redraw_clusters c left join jobs j on j.id=c.job order by c.created desc limit 300").fetchall()
   self.reply(200,{'clusters':[dict(r) for r in rows]});return
'''+needle)
p=base/'dispatch.html'
edit(p,"'Đọc yêu cầu trước khi xử lý',875","'Yêu cầu · AI chỉnh sửa · PNG',875")
edit(p,'"redraw": {\n    "input": "', '"redraw": {\n    "input": "Worker Windows nhận sự kiện Hub và xử lý tuần tự yêu cầu vẽ kèm ảnh/PDF đã liên kết. CANAVI và CANAVI HCM2 giữ nhánh riêng. Illustrator giữ nền, tạo chữ chỉnh sửa được và nhúng bản ảnh chi tiết từ API; lưu AI/PNG vào DESIGNER của nhóm rồi đăng PNG vào đúng hội thoại Chatwoot. ')
needle="if(pane==='files'){let count=0;"
edit(p,needle,'''if(pane==='files' && selected==='redraw'){
 const box=el('section');root.append(box);box.append(el('strong','Cụm vẽ lại Illustrator'));
 fetch('/api/redraw-clusters',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(({clusters})=>{
 const items=clusters.filter(c=>!scope||batches.some(b=>b.account===c.account&&(b.source_ids||[]).some(id=>String(id)===c.message||String(id)===c.source)));
 if(!items.length)box.append(el('p','Chưa có cụm vẽ lại trong phạm vi đang chọn.'));
 for(const c of items){const item=el('details');item.className='flow-detail';item.append(el('summary',c.group_name+' · '+formatCreated(c.created)+' · '+c.status),el('p',c.brief),el('p','Hội thoại #'+c.conversation+' · Tin yêu cầu '+c.message+' · Tin nguồn '+c.source+' · Job '+c.job));
 if(c.status.startsWith('chatwoot:'))item.append(el('p','Đã đăng PNG · tin #'+c.status.split(':')[1]),el('p',['W:',c.archive_group,'DESIGNER','Mau-'+c.job+'.ai / .png'].join(String.fromCharCode(92))));box.append(item);}
 }).catch(()=>box.append(el('p','Chưa tải được lịch sử worker.')));
}
'''+needle)
