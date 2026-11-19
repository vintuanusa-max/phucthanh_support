import worker as w,sqlite3
identity=['zalo-personal-1','g8534414090274815910','simulation-denim-autodetect-20261119-geometry-v4']
db=sqlite3.connect('state.sqlite')
row=db.execute('select error from errors where capture=8391').fetchone()
assert row and 'allocate' in row[0]
db.execute("delete from jobs where id=? and status='drawing'",('bbd129d9f47b5f947cf8',))
db.commit()
m=w.call('source',identity=identity);w.process(db,m,72,m['display_name'])
print(db.execute('select status from jobs where id=?',('bbd129d9f47b5f947cf8',)).fetchone())
