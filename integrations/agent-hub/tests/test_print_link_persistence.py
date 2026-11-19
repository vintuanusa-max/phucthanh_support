import json,sqlite3
from hub.print_linking import persist,resolve
c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
c.executescript('''CREATE TABLE design_briefs(id TEXT,run_id TEXT,account TEXT,thread_id TEXT,payload TEXT,created REAL);CREATE TABLE intake_runs(id TEXT,account TEXT,thread_id TEXT,state TEXT,payload TEXT,result TEXT);CREATE TABLE production_slip_orders(id TEXT,state TEXT,payload TEXT,result TEXT);''')
def brief(id,run,sha):c.execute('insert into design_briefs values(?,?,?,?,?,?)',(id,run,'z','g',json.dumps({'sources':[{'message_id':sha,'assets':[{'sha256':sha}]}]}),1))
b={'source_account':'z','group_id':'g','customer_id':'c','asset_sha256':'slip'}
v=dict(b,orders=[{'id':'order1'}])
c.execute('insert into production_slip_orders values(?,?,?,?)',('s','duplicate',json.dumps({'body':b}),json.dumps(v)))
persist(c);assert not c.execute('select * from erp_print_brief_links').fetchall()
brief('b','later','slip');persist(c);persist(c)
assert c.execute('select order_id from erp_print_brief_links where brief_id="b"').fetchone()[0]=='order1'
assert c.execute('select count(*) from erp_print_brief_links').fetchone()[0]==1
brief('b2','r','m2');brief('b3','r','m3')
c.execute('insert into intake_runs values(?,?,?,?,?,?)',('r','z','g','created',json.dumps({'print_line_sources':[['m2'],['m3']],'submitted_payload':{'orders':[{'so_luong':2},{'so_luong':3}]}}),json.dumps({'customer_id':'c','orders':[{'id':'order2'},{'id':'order3'}]})))
persist(c)
assert dict(c.execute('select brief_id,order_id from erp_print_brief_links'))=={'b':'order1','b2':'order2','b3':'order3'}
# Existing explicit links are immutable, even if intake lineage later changes.
c.execute("update intake_runs set result=? where id='r'",(json.dumps({'customer_id':'c','orders':[{'id':'wrong2'},{'id':'wrong3'}]}),));persist(c)
assert c.execute('select order_id from erp_print_brief_links where brief_id="b2"').fetchone()[0]=='order2'
print('PASS: slip order_payload, duplicate receipt, late brief, repeated sync, multi-order per-source binding, immutable links')

