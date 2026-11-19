import base64, json, sqlite3, sys
from pathlib import Path
import httpx
from hub.clients import Chatwoot
from hub.config import Settings
from hub.execution_models import select

cfg = Settings.environment()
db = sqlite3.connect("file:" + cfg.database + "?mode=ro", uri=True)
arg = json.load(sys.stdin)
op = arg["op"]
if op == "start":
    result = db.execute("select coalesce(max(rowid),0) from captures").fetchone()[0]
elif op == "batch":
    rows = db.execute("""select c.rowid,c.payload,t.conversation,t.display_name from captures c
        join threads t using(account,thread_id) where c.rowid>? order by c.rowid limit 12""",(arg["cursor"],)).fetchall()
    result = [[i,json.loads(p),conv,name] for i,p,conv,name in rows]
elif op == "source":
    row = db.execute("""select payload from captures where account=? and thread_id=? and message_id=?
        order by revision desc limit 1""",arg["identity"]).fetchone()
    result = json.loads(row[0]) if row else None
elif op == "reference_image":
    key=Path("/data/secrets/openai-api-key").read_text().strip()
    from hub.execution_models import select
    model=select(cfg,"redraw","gpt-image-2.5-sunburst")
    raw=base64.b64decode(arg["png"],validate=True)
    prompt="Reproduce this original artwork as faithfully as possible, retaining exact lettering, numbers, proportions, fine ornament, colors, texture, margins and composition. Preserve original lettering even if a separate editable revision is requested. Deliver the detailed reference image."
    response=httpx.post("https://api.openai.com/v1/images/edits",headers={"Authorization":"Bearer "+key},data={"model":model,"quality":"high","size":"auto","n":"1","output_format":"png","prompt":prompt},files={"image":("source.png",raw,"image/png")},timeout=400)
    response.raise_for_status()
    result=response.json()["data"][0]["b64_json"]
elif op == "plan":
    key=Path("/data/secrets/openai-api-key").read_text().strip()
    import io
    from PIL import Image
    w,h=Image.open(io.BytesIO(base64.b64decode(arg["png"]))).size
    prompt=f"""Analyze lettering only. Canvas is {w} x {h} original pixels. Return JSON with texts array. If brief requests specific changes, include only affected lines, else include ALL readable text and digits, including small lettering. For each line give source (exact original), value (requested replacement or original), font (slab/serif/sans/sans-bold/italic/script/mono), fill (#RRGGBB), stroke (#RRGGBB or none), background (#RRGGBB immediately behind lettering), and glyphs: one [left,top,right,bottom] close axis-aligned box per nonspace original character in reading order. Use original image pixels, carefully measure each glyph including its outline. Do not describe ornament paths. Preserve spelling. Customer brief: """
    response=httpx.post("https://api.openai.com/v1/responses",headers={"Authorization":"Bearer "+key},json={"model":"gpt-5.5","reasoning":{"effort":"medium"},"max_output_tokens":28000,"text":{"format":{"type":"json_object"}},"input":[{"role":"user","content":[{"type":"input_text","text":prompt+arg["brief"]},{"type":"input_image","detail":"high","image_url":"data:image/png;base64,"+arg["png"]}]}]},timeout=410)
    if response.is_error:raise ValueError(response.json().get("error",{}).get("message","Plan API error")[:240])
    result=json.loads("".join(c["text"] for msg in response.json()["output"] for c in msg.get("content",[]) if c.get("type")=="output_text"))
elif op == "publish":
    account,thread,mid = arg["identity"]
    row = db.execute("""select t.conversation,c.payload from threads t join captures c using(account,thread_id)
        where t.account=? and t.thread_id=? and c.message_id=? order by revision desc limit 1""",(account,thread,mid)).fetchone()
    if not row or row[0]!=arg["conversation"] or json.loads(row[1]).get("recalled"):
        raise ValueError("Conversation or source changed")
    reply = Chatwoot(cfg).request("POST",f"conversations/{row[0]}/messages",data={"private":"false","message_type":"outgoing","content":"Máº«u váº½ láº¡i Ä‘á»ƒ báº¡n xem trÆ°á»›c."},
        files={"attachments[]":("Mau-"+arg["job"]+".png",base64.b64decode(arg["png"],validate=True),"image/png")})
    if not reply.get("attachments") or not reply.get("id"):raise ValueError("Unconfirmed attachment")
    result = reply["id"]
else:raise ValueError("Unknown operation")
print(json.dumps(result,ensure_ascii=True))


