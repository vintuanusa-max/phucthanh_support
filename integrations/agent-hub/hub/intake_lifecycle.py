"""Source reuse rules; image cache is never an order ledger."""
import json
import re

NON_ORDER = {'payment','delivery','delivery_update','invoice','progress','progress_query','complaint','approval','sample_approval','conversation_only','cancellation'}

def reusable(db, row):
    result = json.loads(row['source_result'] or '{}')
    if result.get('intent') in NON_ORDER or result.get('print_approval_id') or result.get('sample_job_id'):
        return False
    m = json.loads(row['payload'])
    args = (m['account'], m['thread_id'], m['message_id'])
    if db.execute('SELECT 1 FROM order_source_links WHERE account=? AND thread_id=? AND message_id=?', args).fetchone():
        return False
    # Check stable channel message ID, not only capture ID: revisions are not new orders.
    return not db.execute("SELECT 1 FROM intake_runs r, json_each(r.payload,'$.messages') j WHERE r.account=? AND r.thread_id=? AND j.value=? AND (r.state IN ('created','duplicate','sending','uncertain') OR json_extract(r.payload,'$.submitted_payload') IS NOT NULL OR json_extract(r.result,'$.orders[0].id') IS NOT NULL)", args).fetchone()

def explicit_addition(messages):
    return any(re.search(r'\b(in|đặt|làm|lấy)\s+thêm\b', m.get('text','').casefold()) for m in messages)

def explicit_total(text):
    return bool(re.search(r'\b(tổng|tổng cộng|tất cả|cộng lại|thành)\b', text.casefold()))
