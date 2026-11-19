import base64, hashlib, io, json, re, sqlite3, subprocess, sys, tempfile, unicodedata
from pathlib import Path
import fitz
from PIL import Image
from vector_redraw_export import CANAVI_THREADS, export_vector

HOME_DIR=Path(__file__).resolve().parent
ROOT=Path(r"\\192.168.1.203\n8n_upload")
BRIDGE=(HOME_DIR/"bridge.py").read_text(encoding="utf-8-sig")
def call(op,**args):
    run=subprocess.run(["docker","exec","-i","phucthanh-chatwoot-hub-1","/app/.venv/bin/python","-c",BRIDGE],
        input=json.dumps(dict(op=op,**args)).encode(),creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True,timeout=450)
    if run.returncode:raise RuntimeError(run.stderr.decode(errors="replace").splitlines()[-1][:220])
    return json.loads(run.stdout)

def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFD",text.lower().replace("Ãƒâ€žÃ¢â‚¬Ëœ","d")) if not unicodedata.combining(c))

def requested(m):
    text=normalized(m.get("text",""))
    return (m.get("direction")=="incoming" and m.get("origin")=="customer" and not m.get("recalled")
        and not re.search(r"\b(khong|khoi|dung|chua|ko|huy)\b.{0,30}\b(ve|dung|lam)",text)
        and re.search(r"\b(ve lai|ve mau|lam mau|dung lai (?:mau|hinh|logo)|vector hoa)\b",text))

def reference(source,group,brief):
    assets=[a for a in source.get("assets",[]) if Path(a["name"]).suffix.lower() in {".pdf",".png",".jpeg",".jpg",".webp"}]
    if len(assets)>1:raise ValueError("Multiple source files")
    if assets:
        a=assets[0]; relative=Path(a["relative_path"]); path=(ROOT/relative).resolve(strict=True)
        if a["state"]!="ready" or not relative.parts or relative.parts[0]!=group or (ROOT/group).resolve() not in path.parents or path.stat().st_size>64_000_000:raise ValueError("Invalid archive source")
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=a["sha256"]:raise ValueError("Archive changed")
        if path.suffix.lower()==".pdf":
            with fitz.open(stream=raw,filetype="pdf") as pdf:
                page=re.search(r"\btrang\s+(\d+)\b",normalized(brief))
                if len(pdf)!=1 and not page:raise ValueError("PDF page ambiguous")
                num=int(page[1]) if page else 1
                if not 1<=num<=len(pdf):raise ValueError("Invalid page")
                p=pdf[num-1]; scale=min(3,2000/max(p.rect.width,p.rect.height))
                raw=p.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes("png")
    else:
        images=source.get("images",[])
        if len(images)!=1:raise ValueError("No unique linked image")
        raw=base64.b64decode(images[0]["data"],validate=True)
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>32_000_000:raise ValueError("Image exceeds size limit")
        im.thumbnail((2048,2048)); out=io.BytesIO(); im.convert("RGBA").save(out,format="PNG"); return out.getvalue()

def process(db,m,conv,group):
    if not requested(m) or m["thread_id"] in CANAVI_THREADS or group.upper().strip() in {"CANAVI","CANAVI HCM2"}:return
    if not group or Path(group).name!=group or group in {".",".."}:raise ValueError("Invalid group")
    identity=[m["account"],m["thread_id"],m["message_id"]]
    job=hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]
    if db.execute("select 1 from jobs where id=?",(job,)).fetchone():return
    db.execute('create table if not exists redraw_clusters(job text primary key,account text,thread text,message text,source text,conversation integer,group_name text,brief text,created real,archive_group text)')
    quoted=m.get("quoted_image") or m.get("quoted_file") or {}
    archive="A LUOM" if m["thread_id"]=="g8534414090274815910" else group

    source=call("source",identity=identity)
    if not source or source.get("revision")!=m.get("revision") or source.get("recalled"):return
    quote=m.get("quoted_image") or m.get("quoted_file")
    if quote:
        if not quote.get("resolved"):raise ValueError("Unresolved quote")
        source=call("source",identity=identity[:2]+[quote["message_id"]])
    if not source or source.get("recalled"):raise ValueError("Unavailable source")
    archive_group = group
    if m["thread_id"] == "g8534414090274815910":
        archive_group = normalized(group.split("-",1)[0]).strip().upper()
        if archive_group != "A LUOM":
            raise ValueError("Unexpected A LUOM archive name")
    raw=reference(source,archive_group,m["text"])
    group = archive_group
    if not (ROOT/group).is_dir():raise ValueError("Missing group archive")
    db.execute("insert or ignore into redraw_clusters values(?,?,?,?,?,?,?,?,?,?)",(job,*identity,quoted.get("message_id") or identity[2],conv,group,m.get("text",""),m["timestamp"],archive))
    db.execute("insert into jobs values(?,?)",(job,"drawing"));db.commit()
    plan=call("plan",png=base64.b64encode(raw).decode(),brief=m["text"])
    from live_text_worker import export
    detail=base64.b64decode(call("reference_image",png=base64.b64encode(raw).decode()),validate=True)
    ai,png=export(raw,plan,ROOT,group,m["thread_id"],job,detail)
    db.execute("update jobs set status='publishing' where id=?",(job,));db.commit()
    receipt=call("publish",identity=identity,conversation=conv,job=job,png=base64.b64encode(png.read_bytes()).decode())
    db.execute("update jobs set status=? where id=?",("chatwoot:"+str(receipt),job));db.commit()

def main():
    db=sqlite3.connect(HOME_DIR/"state.sqlite")
    db.executescript("create table if not exists checkpoint(n integer);create table if not exists jobs(id text primary key,status text);create table if not exists errors(capture integer primary key,error text);")
    row=db.execute("select n from checkpoint").fetchone()
    if row is None:
        db.execute("insert into checkpoint values(?)",(call("start"),));db.commit();return
    for i,m,conv,group in call("batch",cursor=row[0]):
        try:
            if requested(m):
                key=hashlib.sha256(json.dumps([m['account'],m['thread_id'],m['message_id']]).encode()).hexdigest()[:20]
                db.execute('delete from flow_active');db.execute('insert into flow_active values(?,?)',(i,key));db.commit()
            process(db,m,conv,group)
        except Exception as exc:
            failure_key=hashlib.sha256(json.dumps([m['account'],m['thread_id'],m['message_id']]).encode()).hexdigest()[:20]
            db.execute("update jobs set status=? where id=? and status not like 'chatwoot:%'",('error:'+type(exc).__name__,failure_key))
            db.execute("insert or replace into errors values(?,?)",(i,str(exc)[:250]))
        db.execute("delete from flow_active")
        db.execute("update checkpoint set n=?",(i,));db.commit()
    cursor=db.execute("select n from checkpoint").fetchone()[0]
    db.close()
    return cursor
if __name__=="__main__":main()

