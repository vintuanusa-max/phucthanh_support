from hub.pending_guard import reason_for


def test_disabled_ai_and_human_owner_open():
    assert reason_for({'status': 'pending'}, [], None, 'ai', 1000)
    assert reason_for({'status': 'pending'}, [], {'enabled_after': 1}, 'human', 1000)


def test_timeout_does_not_count_private_note_as_reply():
    history = [{'id': 1, 'message_type': 0, 'created_at': 700},
               {'id': 2, 'message_type': 1, 'private': True, 'created_at': 999}]
    assert reason_for({'status': 'pending'}, history, {'enabled_after': 1}, 'ai', 1000)
    assert not reason_for({'status': 'pending'}, history, {'enabled_after': 1}, 'ai', 999)
    history.append({'id': 3, 'message_type': 1, 'private': False})
    assert not reason_for({'status': 'pending'}, history, {'enabled_after': 1}, 'ai', 1000)


def test_preserve_staff_statuses():
    for status in ['open', 'resolved', 'snoozed']:
        assert not reason_for({'status': status}, [], None, 'human', 1000)
