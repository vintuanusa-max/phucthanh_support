"""Pure quiet-window grouping; no persistence or ERP writes."""

def human_activity(message):
    # Origin is assigned by the reader, never inferred from an @mention.
    return (message.get('origin') in ('customer', 'staff')
            and bool(message.get('sender', '').strip())
            and not message.get('recalled') and not message.get('revision'))
def settled_batch(rows, now, wait_seconds):
    if not rows:return []
    batch=[];last=None
    for row in rows:
        stamp=float(row[1]['timestamp'])
        if last is not None and stamp-last>wait_seconds:break
        batch.append(row);last=stamp
    if now-last<wait_seconds or any(row[2]!='done' for row in batch):return []
    return batch
