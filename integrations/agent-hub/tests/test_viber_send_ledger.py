import pytest
from viber_desktop.send_ledger import SendLedger


def test_crash_after_reservation_never_resends(tmp_path):
    path = tmp_path / 'send.sqlite3'
    first = SendLedger(path)
    assert first.reserve('cw:1', 'viber', 'viber:g1', 'hello')
    first.close()
    recovered = SendLedger(path)
    assert not recovered.reserve('cw:1', 'viber', 'viber:g1', 'hello')
    recovered.confirm('cw:1', 'event:42')
    assert not recovered.reserve('cw:1', 'viber', 'viber:g1', 'hello')
    recovered.close()


def test_concurrent_adapters_and_conflicting_payload(tmp_path):
    path = tmp_path / 'send.sqlite3'
    first, second = SendLedger(path), SendLedger(path)
    assert first.reserve('cw:1', 'viber', 'viber:g1', 'hello')
    assert not second.reserve('cw:1', 'viber', 'viber:g1', 'hello')
    with pytest.raises(ValueError):
        second.reserve('cw:1', 'viber', 'viber:g2', 'hello')
    # Two deliberate staff messages with identical text are different deliveries.
    assert second.reserve('cw:2', 'viber', 'viber:g1', 'hello')
    first.close()
    second.close()


def test_confirmation_requires_source_identity(tmp_path):
    ledger = SendLedger(tmp_path / 'send.sqlite3')
    with pytest.raises(ValueError):
        ledger.confirm('unknown', 'event:1')
    assert ledger.reserve('cw:1', 'viber', 'viber:g1', 'hello')
    with pytest.raises(ValueError):
        ledger.confirm('cw:1', '')
    ledger.confirm('cw:1', 'event:1')
    ledger.confirm('cw:1', 'event:1')
    with pytest.raises(ValueError):
        ledger.confirm('cw:1', 'event:2')
    ledger.close()
