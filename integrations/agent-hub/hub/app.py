import hashlib
import hmac
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse

from hub.ai_policy import trial
from hub.clients import ERP, Chatwoot, Gemini
from hub.config import Settings
from hub.delivery_policy import delivery_block
from hub.engine import Engine, human_assigned
from hub.models import (
    Capture,
    Control,
    CustomerBinding,
    DeliveryPrepare,
    DeliveryResult,
    Mapping,
    ThreadNames,
)
from hub.store import Store


def create_app(settings=None, engine=None, start_worker=True):
    settings = settings or Settings.environment()
    settings.validate()
    store = engine.store if engine else Store(settings.database)
    engine = engine or Engine(settings, store, Chatwoot(settings), Gemini(settings), ERP(settings))
    from hub.workflow_control import WorkflowControl
    workflow = WorkflowControl(store)
    stop = threading.Event()
    from hub.order_print_bridge import OrderPrintBridge
    print_bridge = OrderPrintBridge(engine)

    from hub.native_auto import initialize as native_init, tick as native_tick
    native_init(engine)
    def monitor_native():
        while not stop.is_set():
            try:native_tick(engine)
            except Exception:logging.getLogger(__name__).exception('Native selector failed')
            stop.wait(5)

    def monitor_customer_approvals():
        from hub.customer_approval_links import tick
        while not stop.is_set():
            try:tick(engine)
            except Exception:logging.getLogger(__name__).exception('Customer approval comparison failed')
            stop.wait(30)

    def monitor_workflow():
        while not stop.is_set():
            try:
                from hub.file_notices import tick as file_notice_tick
                file_notice_tick(engine)
            except Exception:
                logging.getLogger(__name__).exception('File notice monitor failed')
            try:
                workflow.monitor(['hub_worker'] + [prefix+a for a,c in settings.inboxes.items() if c.get('capture_enabled') for prefix in ('reader:', 'artwork:')])
                print_bridge.tick()
            except Exception:
                logging.getLogger(__name__).exception('Workflow monitor failed')
            stop.wait(30)


    def worker():
        while not stop.is_set():
            try:
                workflow.beat('hub_worker')
                worked = engine.process_one()
            except Exception as exc:
                logging.getLogger(__name__).error("Worker operation halted: %s", type(exc).__name__)
                worked = False
            if not worked:
                stop.wait(1)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            from hub.native_auto import recover as native_recover
            native_recover(engine)
        store.recover()
        engine.order_intake.recover()
        engine.artwork_checks.recover()
        thread = None
        if start_worker:
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
        native_thread=threading.Thread(target=monitor_native,daemon=True)
        if start_worker:native_thread.start()
        monitor = threading.Thread(target=monitor_workflow, daemon=True)
        if start_worker: monitor.start()
        approval_thread=threading.Thread(target=monitor_customer_approvals,daemon=True)
        if start_worker:approval_thread.start()
        yield
        stop.set()
        if start_worker: monitor.join(timeout=3)
        if thread:
            thread.join(timeout=3)

    app = FastAPI(title="Phúc Thành Agent Hub", lifespan=lifespan)
    app.state.engine = engine

    def require_admin(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, "Bearer " + settings.admin_token):
            raise HTTPException(401, "Admin authorization required")

    def require_ingest(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, "Bearer " + settings.ingest_token):
            raise HTTPException(401, "Adapter authorization required")

    @app.get('/dispatch', dependencies=[Depends(require_admin)])
    def dispatch_list():
        from hub.dispatch_control import listing
        return listing(engine)

    @app.get('/dispatch/{bid}', dependencies=[Depends(require_admin)])
    def dispatch_detail(bid: str):
        from hub.dispatch_control import detail
        try: return detail(engine,bid)
        except ValueError as ex: raise HTTPException(400,str(ex))

    @app.post('/dispatch/{bid}', dependencies=[Depends(require_admin)])
    def dispatch_submit(bid: str,data: dict):
        from hub.dispatch_control import submit
        try: return submit(engine,bid,data)
        except ValueError as ex: raise HTTPException(409,str(ex))

    @app.get('/adapters/{account}/native-selections', dependencies=[Depends(require_ingest)])
    def native_pending(account: str):
        from hub.native_selection import pending
        return {'job':pending(engine,account)}

    @app.post('/adapters/{account}/native-selections/{identity}', dependencies=[Depends(require_ingest)])
    async def native_result(account: str,identity: str,request: Request):
        from hub.native_selection import result
        raw=await request.body()
        if len(raw)>46000000:raise HTTPException(413,'Payload too large')
        try:return result(engine,account,identity,json.loads(raw))
        except (ValueError,KeyError,TypeError) as ex:raise HTTPException(400,str(ex))

    @app.get('/agentic/status', dependencies=[Depends(require_admin)])
    def agentic_status():
        with store.db() as db:
            runs=[dict(r) for r in db.execute('SELECT * FROM agent_runs ORDER BY updated DESC LIMIT 50')]
            proposals=[dict(r) for r in db.execute('SELECT * FROM agent_proposals ORDER BY created DESC LIMIT 50')]
        return {'scopes':{a:c.get('agentic',{}) for a,c in settings.inboxes.items()},'runs':runs,'proposals':proposals}

    @app.get('/context-agent/status', dependencies=[Depends(require_admin)])
    def context_agent_status():
        with store.db() as db:
            decisions = [dict(r) for r in db.execute(
                "SELECT id,run_id,version,state,decision,created FROM context_decisions ORDER BY created DESC LIMIT 50")]
            work = [dict(r) for r in db.execute(
                "SELECT w.*,r.state AS intake_state,r.result AS intake_result FROM context_work_items w "
                "LEFT JOIN intake_runs r ON r.id=w.run_id ORDER BY w.updated DESC LIMIT 50")]
        return {'scopes': {a:c.get('context_agent', {}) for a,c in settings.inboxes.items()},
                'decisions': decisions, 'work_items': work}

    @app.get('/adapters/{account}/print-evidence', dependencies=[Depends(require_ingest)])
    def print_evidence(account: str):
        return {'job':engine.print_approvals.evidence_request(account)}

    @app.post('/adapters/{account}/file-previews/claim', dependencies=[Depends(require_ingest)])
    def claim_file_preview(account: str):
        if account not in settings.inboxes:
            raise HTTPException(404, "Unknown account")
        return {'job': engine.file_previews.claim(account)}

    @app.post('/adapters/{account}/file-previews/{identity}', dependencies=[Depends(require_ingest)])
    def complete_file_preview(account: str, identity: str, data: dict):
        engine.file_previews.finish(account, identity, data)
        return {'stored': True}

    @app.post('/adapters/{account}/print-evidence/{identity}', dependencies=[Depends(require_ingest)])
    def print_evidence_saved(account: str,identity: str,data: dict):
        engine.print_approvals.evidence_saved(account,identity,data)
        return {'stored':True}

    @app.get('/adapters/{account}/print-deliveries/pending', dependencies=[Depends(require_ingest)])
    def print_delivery_pending(account: str):
        return {'accounts':engine.print_approvals.pending_destinations(account)}

    @app.post('/adapters/{account}/print-deliveries/claim', dependencies=[Depends(require_ingest)])
    def print_delivery_claim(account: str, destination: str | None = None):
        return {'job':engine.print_approvals.claim(account,destination)}

    @app.post('/adapters/{account}/print-deliveries/{identity}', dependencies=[Depends(require_ingest)])
    def print_delivery_result(account: str,identity: str,data: dict):
        engine.print_approvals.delivered(account,identity,data)
        return {'stored':True}

    @app.get('/adapters/{account}/production-slips', dependencies=[Depends(require_ingest)])
    def production_slip_pending(account: str):
        return {'job':engine.production_slips.pending(account)}

    @app.post('/adapters/{account}/production-slips/{identity}', dependencies=[Depends(require_ingest)])
    def production_slip_saved(account: str,identity: str,data: dict):
        engine.production_slips.saved(account,identity,data)
        return {'stored':True}

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": settings.mode, "protocol": 1}

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8-sig")

    @app.get("/admin/status", dependencies=[Depends(require_admin)])
    def status():
        return {
            "mode": settings.mode,
            "gemini_configured": bool(settings.gemini_key),
            "chatwoot_configured": bool(settings.cw_url and settings.cw_token),
            "erp_writes": settings.erp_write,
            "order_intake": {
                a: {**c.get("order_intake", {}), "policy_fresh": engine.order_intake.policy(a) is not None}
                for a, c in settings.inboxes.items()
            },
            "ai_trials": {a: c.get("ai_trials", {}) for a, c in settings.inboxes.items()},
            "live_capture_accounts": [
                a for a, c in settings.inboxes.items() if c.get("capture_enabled") is True
            ],
            "human_delivery_accounts": [
                a
                for a, c in settings.inboxes.items()
                if c.get("delivery_enabled") and c.get("human_delivery_enabled")
            ],
            **store.status(),
        }

    @app.get("/design-briefs", dependencies=[Depends(require_admin)])
    def design_briefs(conversation: int, limit: int = 50):
        with store.db() as db:
            rows = db.execute("SELECT payload FROM design_briefs WHERE conversation=? ORDER BY created DESC LIMIT ?", (conversation, max(1,min(limit,100)))).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "execution_allowed": False}

    @app.get("/admin/{table}", dependencies=[Depends(require_admin)])
    def recent(table: str):
        if table not in {"jobs", "effects", "deliveries", "drafts", "intake_runs"}:
            raise HTTPException(404)
        return store.recent(table)

    @app.post("/admin/conversations/{conversation}/owner", dependencies=[Depends(require_admin)])
    def owner(conversation: int, request: Control):
        with engine.lock:
            if request.owner == "human":
                store.set_owner(conversation, "human")
                if settings.mode == "live" or (engine.trial_for(conversation) or engine.order_intake.agent_loop.conversation_scope(conversation)):
                    engine.cw.status(conversation, "open")
            else:
                if any("ai_trials" in c for c in settings.inboxes.values()) and not engine.trial_for(
                    conversation
                ):
                    raise HTTPException(409, "AI is disabled outside the trial groups")
                if settings.mode == "live" or (engine.trial_for(conversation) or engine.order_intake.agent_loop.conversation_scope(conversation)):
                    current = engine.cw.conversation(conversation)
                    if human_assigned(current):
                        raise HTTPException(409, "Unassign the human agent in Chatwoot before resuming AI")
                    engine.cw.status(conversation, "pending")
                store.set_owner(conversation, "ai")
        return {"owner": request.owner}

    @app.get("/admin/customer-mappings/list", dependencies=[Depends(require_admin)])
    def customer_mappings():
        return {"items": engine.customer_mappings.list()}

    @app.post("/admin/customer-mappings/{account}/{thread_id}", dependencies=[Depends(require_admin)])
    def customer_binding(account: str, thread_id: str, request: CustomerBinding):
        try:
            with engine.lock:
                return engine.customer_mappings.set(
                    account,
                    thread_id,
                    request.customer_id,
                    request.customer_name.strip(),
                    request.expected_version,
                )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/admin/conversations/{conversation}/erp-mapping", dependencies=[Depends(require_admin)])
    def mapping(conversation: int, request: Mapping):
        with store.db() as db:
            changed = db.execute(
                "UPDATE threads SET erp_group=? WHERE conversation=?", (request.group_name, conversation)
            ).rowcount
        if not changed:
            raise HTTPException(404, "No personal channel mapping")
        return {"mapped": True}

    @app.post("/admin/drafts/{draft}/approve", dependencies=[Depends(require_admin)])
    def approve(draft: str):
        try:
            return engine.approve_order(draft)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, "ERP result uncertain; inspect before retry") from exc

    @app.post("/ingest", dependencies=[Depends(require_ingest)])
    async def ingest(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 6_000_000:
                raise HTTPException(413, "Capture size limit")
        try:
            message = Capture.model_validate_json(body)
        except ValueError as exc:
            raise HTTPException(422, "Invalid capture") from exc
        if message.account not in settings.inboxes:
            raise HTTPException(422, "Unknown channel account")
        from hub.order_policy import capture_allowed

        cfg = settings.inboxes[message.account]
        if not capture_allowed(
            cfg.get("capture_policy", {}), cfg.get("channel"), message.thread_id, message.display_name
        ):
            return {"stored": True, "id": "ignored-policy", "ignored": True}
        if message.images:
            scope = trial(settings.inboxes[message.account], message.thread_id)
            if not engine.order_intake.media_scope(message.model_dump()) and (
                not scope or message.timestamp < scope["enabled_after"]
            ):
                raise HTTPException(422, "Images are disabled outside the new-message trial scope")
        if message.assets:
            cfg = settings.inboxes[message.account]
            scope = trial(cfg, message.thread_id)
            if not cfg.get("archive_root") or (
                not engine.order_intake.media_scope(message.model_dump())
                and (not scope or message.timestamp < scope["enabled_after"])
            ):
                raise HTTPException(422, "Archive disabled outside trial")
            for asset in message.assets:
                path = PurePosixPath(asset.relative_path)
                if asset.state == "ready" and (
                    not asset.relative_path
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in asset.relative_path
                    or ":" in asset.relative_path
                ):
                    raise HTTPException(422, "Invalid archive path")
        try:
            return {"id": store.capture(message), "stored": True}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/adapters/{account}/order-policy", dependencies=[Depends(require_ingest)])
    def order_policy(account: str, config: dict):
        if account not in settings.inboxes:
            raise HTTPException(404)
        try:
            engine.order_intake.sync_policy(account, config)
            workflow.beat('reader:' + account)
        except ValueError as exc:
            raise HTTPException(422, "Invalid order policy") from exc
        return {"stored": True, "scope": engine.order_intake.scope(account)}

    @app.get('/adapters/{account}/psd-samples', dependencies=[Depends(require_ingest)])
    def pending_psd(account: str):
        from hub.psd_samples import pending
        return {'job':pending(engine,account)}

    @app.post('/adapters/{account}/psd-samples/{identity}', dependencies=[Depends(require_ingest)])
    async def complete_psd(account: str, identity: str, request: Request):
        from hub.psd_samples import complete
        content=bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content)>8_000_000:raise HTTPException(413,'Preview too large')
        return complete(engine,account,identity,json.loads(content))

    @app.get('/adapters/{account}/jpg-exports', dependencies=[Depends(require_ingest)])
    def pending_jpg(account: str):
        return {'job':engine.artwork_checks.jpg.pending(account)}

    @app.post('/adapters/{account}/jpg-exports/{identity}', dependencies=[Depends(require_ingest)])
    async def complete_jpg(account: str, identity: str, request: Request):
        content=bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content)>48_000_000:raise HTTPException(413,'JPG preview limit')
        try:return engine.artwork_checks.jpg.complete(account,identity,json.loads(content))
        except (ValueError,KeyError) as exc:raise HTTPException(422,'Invalid JPG report') from exc

    @app.get('/adapters/{account}/print-approvals', dependencies=[Depends(require_ingest)])
    def pending_print_approval(account: str):
        with store.db() as d:r=d.execute("SELECT * FROM erp_print_approvals WHERE account=? AND state='queued' LIMIT 1",(account,)).fetchone()
        return {'job':{'id':r['id'],**json.loads(r['payload'])} if r else None}

    @app.post('/adapters/{account}/print-approvals/{identity}', dependencies=[Depends(require_ingest)])
    def complete_print_approval(account: str,identity: str,data: dict):
        with store.db() as d:
            r=d.execute('SELECT * FROM erp_print_approvals WHERE id=? AND account=?',(identity,account)).fetchone()
            if not r:raise HTTPException(404)
            if r['state']!='queued':return {'state':r['state']}
            p=json.loads(r['payload']);state='review' if data.get('error') else 'done'
            expected=[f['group']+'/'+f['name'] for f in p['files']]
            if state=='done' and data.get('paths')!=expected:raise HTTPException(422,'Wrong copy receipt')
            p['detail']=str(data['error'])[:900] if state=='review' else 'Đã duyệt và copy file: '+', '.join(expected)
            p['reported']=False
            d.execute('UPDATE erp_print_approvals SET state=?,payload=? WHERE id=?',(state,json.dumps(p),identity))
        return {'state':state}

    @app.get('/adapters/{account}/pet-exports', dependencies=[Depends(require_ingest)])
    def pending_pet(account: str):
        return {'job':engine.artwork_checks.pet.pending(account)}

    @app.get('/adapters/{account}/pet-exports/{identity}/{name}', dependencies=[Depends(require_ingest)])
    def pet_png(account: str, identity: str, name: str):
        try:
            return FileResponse(engine.artwork_checks.pet.png(account,identity,name), media_type='image/png')
        except ValueError as exc: raise HTTPException(422,str(exc))

    @app.put('/adapters/{account}/pet-exports/{identity}/{name}', dependencies=[Depends(require_ingest)])
    async def upload_pet(account: str, identity: str, name: str, request: Request):
        content=bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content)>64_000_000: raise HTTPException(413,'TIFF upload limit')
        try: engine.artwork_checks.pet.upload(account,identity,name,bytes(content))
        except ValueError as exc: raise HTTPException(422,str(exc))
        return {'stored':True}

    @app.post('/adapters/{account}/pet-exports/{identity}', dependencies=[Depends(require_ingest)])
    def complete_pet(account: str, identity: str, data: dict):
        try: return engine.artwork_checks.pet.complete(account,identity,data)
        except ValueError as exc: raise HTTPException(422,str(exc))

    @app.get('/adapters/{account}/artwork-checks', dependencies=[Depends(require_ingest)])
    def pending_artwork(account: str):
        if account not in settings.inboxes: raise HTTPException(404)
        workflow.beat('artwork:' + account)
        return {'job':engine.artwork_checks.pending(account)}

    @app.post('/adapters/{account}/artwork-checks/{identity}', dependencies=[Depends(require_ingest)])
    async def upload_artwork(account: str, identity: str, request: Request):
        content=bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content)>58_000_000:raise HTTPException(413,'Artwork upload limit')
        try:
            data=json.loads(content)
            engine.artwork_checks.received(account,identity,data)
        except (ValueError,KeyError,TypeError):raise HTTPException(422,'Invalid artwork source')
        return {'stored':True}

    @app.get("/adapters/{account}/order-evidence", dependencies=[Depends(require_ingest)])
    def order_evidence(account: str):
        return {"job": engine.order_intake.evidence_request(account)}

    @app.post("/adapters/{account}/order-evidence/{identity}", dependencies=[Depends(require_ingest)])
    def saved_order_evidence(account: str, identity: str, data: dict):
        try:
            engine.order_intake.evidence_saved(account, identity, data)
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, "Invalid evidence acknowledgement") from exc
        return {"stored": True}

    @app.post("/adapters/{account}/thread-names", dependencies=[Depends(require_ingest)])
    def thread_names(account: str, request: ThreadNames):
        cfg = settings.inboxes.get(account)
        if not cfg or cfg.get("capture_enabled") is not True:
            raise HTTPException(409, "Capture disabled")
        updated = 0
        with engine.lock:
            with store.db() as db:
                rows = db.execute("SELECT * FROM threads WHERE account=?", (account,)).fetchall()
            for row in rows:
                name = request.names.get(row["thread_id"], "").strip()
                if not name or name == row["display_name"]:
                    continue
                engine.cw.rename_contact(row["contact"], name)
                store.bind(account, row["thread_id"], name, row["conversation"], row["contact"])
                updated += 1
        return {"updated": updated}

    @app.post("/webhooks/chatwoot")
    async def webhook(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                raise HTTPException(413)
        timestamp = request.headers.get("x-chatwoot-timestamp", "")
        signature = request.headers.get("x-chatwoot-signature", "")
        try:
            valid_time = abs(time.time() - int(timestamp)) <= 300
        except ValueError:
            valid_time = False
        digest = hmac.new(
            settings.webhook_secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        if not valid_time or not hmac.compare_digest(signature, "sha256=" + digest):
            raise HTTPException(401, "Invalid webhook signature/timestamp")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("Expected object")
            return {"queued": engine.accept_webhook(payload)}
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise HTTPException(422, "Invalid webhook payload") from exc

    @app.post("/adapters/{account}/claim", dependencies=[Depends(require_ingest)])
    def claim(account: str):
        cfg = settings.inboxes.get(account)
        if (
            not cfg
            or not cfg.get("delivery_enabled")
            or (
                settings.mode != "live" and not cfg.get("human_delivery_enabled") and not cfg.get("ai_trials")
            )
        ):
            raise HTTPException(409, "Delivery disabled")
        with engine.lock, store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM deliveries WHERE account=? AND state='queued' ORDER BY rowid LIMIT 1",
                (account,),
            ).fetchone()
            if not row:
                return {"item": None}
            payload = json.loads(row["payload"])
            reason = delivery_block(settings, cfg, payload, row["thread_id"])
            if reason:
                db.execute("UPDATE deliveries SET state='blocked',detail=? WHERE id=?", (reason, row["id"]))
                db.execute(
                    "INSERT OR IGNORE INTO jobs(id,kind,payload,created) VALUES(?,'notice',?,?)",
                    (
                        row["id"] + ":notice",
                        json.dumps({"conversation": row["conversation"], "text": "Chưa gửi Zalo: " + reason}),
                        time.time(),
                    ),
                )
                return {"item": None}
            marker = payload.get("content_attributes", {}).get("phucthanh", {})
            if marker.get("origin") == "ai":
                state = db.execute(
                    "SELECT owner,generation FROM ownership WHERE conversation=?", (row["conversation"],)
                ).fetchone()
                actual = tuple(state) if state else ("ai", 0)
                current = engine.cw.conversation(row["conversation"])
                if (
                    actual != ("ai", marker.get("generation"))
                    or current.get("status") != "pending"
                    or human_assigned(current)
                ):
                    db.execute(
                        "UPDATE deliveries SET state='blocked',detail='Human takeover' WHERE id=?",
                        (row["id"],),
                    )
                    return {"item": None}
            db.execute(
                "UPDATE deliveries SET state='sending',claimed_at=? WHERE id=?", (time.time(), row["id"])
            )
            mapping = db.execute(
                "SELECT display_name FROM threads WHERE account=? AND thread_id=?",
                (account, row["thread_id"]),
            ).fetchone()
            return {
                "item": {
                    "id": row["id"],
                    "thread_id": row["thread_id"],
                    "message": payload,
                    "display_name": mapping[0] if mapping else "",
                }
            }

    @app.post("/adapters/{account}/prepare/{delivery}", dependencies=[Depends(require_ingest)])
    def prepare(account: str, delivery: str, request: DeliveryPrepare):
        with engine.lock, store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM deliveries WHERE id=? AND account=?", (delivery, account)
            ).fetchone()
            if not row or row["state"] != "sending":
                raise HTTPException(409, "Delivery unavailable")
            cfg = settings.inboxes.get(account, {})
            if delivery_block(settings, cfg, json.loads(row["payload"]), row["thread_id"]):
                raise HTTPException(409, "Delivery no longer allowed")
            marker = json.loads(row["payload"]).get("content_attributes", {}).get("phucthanh", {})
            if marker.get("origin") == "ai":
                state = db.execute(
                    "SELECT owner,generation FROM ownership WHERE conversation=?", (row["conversation"],)
                ).fetchone()
                current = engine.cw.conversation(row["conversation"])
                if (tuple(state) if state else ("ai", 0)) != ("ai", marker.get("generation")) or (
                    current.get("status") != "pending" or human_assigned(current)
                ):
                    raise HTTPException(409, "Human takeover before send")
            if row["client_id"] and row["client_id"] != request.client_id:
                raise HTTPException(409, "Client ID already reserved")
            db.execute("UPDATE deliveries SET client_id=? WHERE id=?", (request.client_id, delivery))
        return {"prepared": True}

    @app.post("/adapters/{account}/results/{delivery}", dependencies=[Depends(require_ingest)])
    def result(account: str, delivery: str, request: DeliveryResult):
        with store.db() as db:
            row = db.execute(
                "SELECT * FROM deliveries WHERE id=? AND account=?", (delivery, account)
            ).fetchone()
            if not row:
                raise HTTPException(404)
            if row["state"] != "sending":
                if row["state"] == "confirmed":
                    return {"stored": True, "state": "confirmed"}
                if row["state"] == "uncertain" and row["client_id"]:
                    # A durable result may arrive after Hub restarted. Never requeue.
                    pass
                elif row["state"] == request.state and row["platform_id"] == request.platform_message_id:
                    return {"stored": True}
                else:
                    raise HTTPException(409, "Delivery no longer pending")
            db.execute(
                "UPDATE deliveries SET state=?,detail=?,platform_id=? WHERE id=?",
                (request.state, request.detail, request.platform_message_id, delivery),
            )
        if request.state in {"failed", "blocked", "uncertain", "submitted", "confirmed"}:
            store.enqueue(
                delivery + ":notice",
                "notice",
                {
                    "conversation": row["conversation"],
                    "text": (
                        "Zalo đã tiếp nhận tin: "
                        if request.state in {"submitted", "confirmed"}
                        else "Chưa xác nhận gửi: "
                    )
                    + request.detail,
                },
            )
        return {"stored": True}

    @app.get('/workflow/status', dependencies=[Depends(require_admin)])
    def workflow_status():
        from hub.workflow_status import snapshot
        with store.db() as db:
            briefs = snapshot(db)
        return {'briefs': briefs, 'controls': workflow.state(), 'read_only': True}

    @app.get('/workflow', response_class=HTMLResponse)
    def workflow_page():
        return Path(__file__).with_name('workflow.html').read_text(encoding='utf-8')

    @app.post('/workflow/versions/{identity}/review', dependencies=[Depends(require_admin)])
    def review_version(identity: str, data: dict):
        try:
            return workflow.decide(identity, data.get('decision'), data.get('note'))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return app
