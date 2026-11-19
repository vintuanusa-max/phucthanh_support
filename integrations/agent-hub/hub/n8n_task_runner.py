"""Durable per-task execution. Adapters own business validation; no implicit retry."""
import hashlib
import json
import math
import time

KINDS = {'inspect_sources', 'erp_order', 'export_pet', 'export_jpg', 'sample_design', 'reply', 'print_approval'}


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class RejectedBeforeEffect(Exception):
    """Adapter guarantees no external write or queued job occurred."""


class TaskRunner:
    def __init__(self, store, adapters, *, mode='simulation'):
        if mode not in ('simulation', 'production'):
            raise ValueError('Invalid execution mode')
        self.store, self.adapters, self.mode = store, adapters, mode
        with store.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS n8n_task_execution(
                id TEXT PRIMARY KEY, mode TEXT NOT NULL, batch_id TEXT NOT NULL,
                account TEXT NOT NULL, thread_id TEXT NOT NULL, kind TEXT NOT NULL,
                payload TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT '{}', attempts INTEGER NOT NULL DEFAULT 0,
                updated REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS n8n_task_conflicts(
                task_id TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                created REAL NOT NULL, PRIMARY KEY(task_id,fingerprint));
            ''')

    def ingest(self, batch, tasks):
        results = []
        for task in tasks:
            try:
                results.append(self._ingest_one(batch, task))
            except (ValueError, TypeError, KeyError) as exc:
                results.append({'state': 'invalid', 'reason': str(exc)})
        return results

    def _ingest_one(self, batch, task):
        account, group = batch['account'], batch['thread_id']
        if task.get('account') != account or task.get('thread_id') != group:
            raise ValueError('TASK_GROUP_MISMATCH')
        source_ids = sorted(set(map(str, task.get('message_ids', []))))
        sources = {str(m['message_id']): m for m in batch['messages']}
        if not source_ids or not set(source_ids) <= sources.keys():
            raise ValueError('TASK_WRONG_SOURCE')
        images = {str(i) for mid in source_ids for i in sources[mid].get('image_ids', [])}
        assets = {str(a['id']): a for mid in source_ids for a in sources[mid].get('assets', [])}
        aids = sorted(set(map(str, task.get('asset_ids', []))))
        iids = sorted(set(map(str, task.get('image_ids', []))))
        if not set(aids) <= assets.keys() or not set(iids) <= images:
            raise ValueError('TASK_FILE_NOT_IN_SOURCES')
        kind = task.get('task_kind')
        # Quantity/spec/model-generated request_key must not permit a second write
        # for the same source partition. Conflicting revisions require review.
        identity = digest([self.mode, account, group, kind, task.get('model_code'), source_ids, aids, iids])
        payload = {k: task.get(k) for k in ('task_kind', 'model_code', 'intent', 'quantity',
                   'quantity_mode', 'print_positions', 'spec', 'reply_draft')}
        payload.update(account=account, thread_id=group, message_ids=source_ids,
                       asset_ids=aids, image_ids=iids,
                       source_refs=[assets[a] for a in aids], request_id=identity)
        payload['batch_cutoff']=max((m.get('timestamp',0) for m in batch['messages']),default=0)
        fp = digest(payload)
        # Keep review evidence without changing the durable business identity.
        payload['review'] = task.get('review') or []
        payload['evidence'] = task.get('evidence') or []
        state = 'unsupported' if kind not in KINDS else 'waiting_information' if task.get('review') or task.get('state') == 'waiting_information' else ('ready' if self.mode == 'simulation' else 'pending_binding')
        if kind == 'erp_order' and (task.get('intent') != 'order' or
                type(task.get('quantity')) not in (int, float) or not math.isfinite(task['quantity']) or task['quantity'] <= 0 or
                task.get('quantity_mode') not in ('total', 'additional')):
            state = 'waiting_information'
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM n8n_task_execution WHERE id=?', (identity,)).fetchone()
            if old:
                if old['fingerprint'] != fp:
                    db.execute('INSERT OR IGNORE INTO n8n_task_conflicts VALUES(?,?,?,?)', (identity, fp, encoded(payload), time.time()))
                    db.execute("UPDATE n8n_task_execution SET state='conflict' WHERE id=? AND state IN ('ready','waiting_information','failed')", (identity,))
                    return {'id': identity, 'state': 'conflict', 'existing_state': old['state']}
                return {'id': identity, 'state': old['state'], 'duplicate': True}
            db.execute('INSERT INTO n8n_task_execution(id,mode,batch_id,account,thread_id,kind,payload,fingerprint,state,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (identity, self.mode, batch['batch_id'], account, group, str(kind), encoded(payload), fp, state, time.time()))
        return {'id': identity, 'state': state}

    def run(self, *, limit=100):
        if self.mode == 'production':
            raise ValueError('PRODUCTION_NOT_ENABLED: scheduler ownership and adapter bindings require deployment review')
        with self.store.db() as db:
            ids = [r['id'] for r in db.execute("SELECT id FROM n8n_task_execution WHERE mode=? AND state='ready' ORDER BY updated,id LIMIT ?", (self.mode, limit))]
        return [self.run_one(identity) for identity in ids]

    def run_one(self, identity):
        if self.mode != 'simulation':
            raise ValueError('PRODUCTION_NOT_ENABLED')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM n8n_task_execution WHERE id=? AND mode=?', (identity, self.mode)).fetchone()
            if not row or row['state'] != 'ready':
                return {'id': identity, 'state': row['state'] if row else 'not_found'}
            adapter = self.adapters.get(row['kind'])
            if not adapter or getattr(adapter, 'simulation_only', False) is not True:
                return {'id': identity, 'state': 'adapter_unavailable'}
            db.execute("UPDATE n8n_task_execution SET state='executing',attempts=attempts+1,updated=? WHERE id=?", (time.time(), identity))
            payload = json.loads(row['payload'])
        try:
            result = adapter.execute(payload, idempotency_key=identity)
            if result.get('request_id') != identity or result.get('account') != row['account'] or result.get('thread_id') != row['thread_id']:
                raise ValueError('Receipt identity mismatch')
            state = result.get('state')
            if state not in ('done', 'submitted', 'waiting_information'):
                raise ValueError('Invalid receipt state')
            if state in ('done', 'submitted') and not result.get('receipt_id'):
                raise ValueError('Missing durable receipt')
        except RejectedBeforeEffect as exc:
            state, result = 'failed', {'error': str(exc), 'safe_to_retry': True}
        except Exception as exc:
            state, result = 'uncertain', {'error': type(exc).__name__, 'safe_to_retry': False}
        with self.store.db() as db:
            db.execute("UPDATE n8n_task_execution SET state=?,result=?,updated=? WHERE id=? AND state='executing'", (state, encoded(result), time.time(), identity))
        return {'id': identity, 'state': state, 'result': result}

    def retry_rejected(self, identity):
        with self.store.db() as db:
            return db.execute("UPDATE n8n_task_execution SET state='ready',updated=? WHERE id=? AND mode=? AND state='failed' AND json_extract(result,'$.safe_to_retry')=1", (time.time(), identity, self.mode)).rowcount == 1

    def recover(self, *, stale_before):
        with self.store.db() as db:
            return db.execute("UPDATE n8n_task_execution SET state='uncertain',result=?,updated=? WHERE mode=? AND state='executing' AND updated<?", (encoded({'error':'Interrupted execution; reconcile receipt before replay','safe_to_retry':False}), time.time(), self.mode, stale_before)).rowcount

    def snapshot(self):
        with self.store.db() as db:
            return [dict(r) for r in db.execute('SELECT id,batch_id,kind,state,result,attempts FROM n8n_task_execution WHERE mode=? ORDER BY id', (self.mode,))]


def receive_plan(runner, batch, envelope):
    """Bridge the n8n response to isolated tasks; never executes on receipt."""
    if (envelope.get('protocol') != 2 or envelope.get('effects_allowed') is not False
            or any(envelope.get(k) != batch.get(k) for k in ('batch_id', 'revision', 'account', 'thread_id'))):
        raise ValueError('PLAN_ENVELOPE_MISMATCH')
    tasks = envelope.get('tasks', [])
    unsupported = envelope.get('unsupported_tasks', [])
    if not isinstance(tasks, list) or not isinstance(unsupported, list):
        raise ValueError('PLAN_TASKS_REQUIRED')
    return runner.ingest(batch, tasks + [dict(t, task_kind='unsupported') for t in unsupported])
