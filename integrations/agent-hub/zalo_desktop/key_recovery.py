"""Persist scan attempts across reader and Zalo restarts."""
import json
import time
from .codec import SnapshotError
from .key_cache import load, save

def acquire(reader, cache, scanner):
    from .idle_reader import allowed,event
    scanner.can_read=lambda:allowed(reader)
    ledger=reader.home/'key-recovery.json'
    try:state=json.loads(ledger.read_text(encoding='utf-8'))
    except FileNotFoundError:state={'attempts':0,'last_scan':0}
    except (ValueError,OSError):raise SnapshotError('key_recovery_state_unreadable')
    reader.recovery_attempts=int(state['attempts'])
    secret=load(cache,reader.root)
    if secret:
        reader.key_source='windows_protected_cache'
        if state['attempts']:persist(ledger,{'attempts':0,'last_scan':0})
        return secret
    if state['attempts']>=3:
        raise SnapshotError('key_scan_failed_3_times_stopped')
    if time.time()-state['last_scan']<60:
        raise SnapshotError('key_scan_retry_wait_60_seconds')
    state={'attempts':state['attempts']+1,'last_scan':time.time()}
    persist(ledger,state)  # Count before scanning, including interrupted scans.
    reader.recovery_attempts=state['attempts']
    reader.key_source='process_memory'
    reader.status('waiting')
    event(reader,"key_scan_start",attempt=state["attempts"])
    try:secret=scanner.find_secret(reader.root)
    except Exception:
        event(reader,"key_scan_failed",attempt=state["attempts"])
        raise SnapshotError('key_scan_failed_3_times_stopped' if state['attempts']>=3 else 'key_scan_failed_retry_pending') from None
    event(reader,"key_scan_success",attempt=state["attempts"])
    save(cache,secret)
    persist(ledger,{'attempts':0,'last_scan':0})
    return secret

def persist(path,state):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state),encoding='utf-8');temp.replace(path)
