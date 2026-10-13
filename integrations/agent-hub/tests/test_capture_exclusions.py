from hub.order_policy import capture_allowed, sanitize
from zalo_desktop.reader import Reader
from zalo_desktop.vault import Vault


POLICY = sanitize({'zalo_default_read_private_messages': False,
                   'zalo_skip_groups': ['Cty In Phúc Thanh'],
                   'zalo_skip_thread_ids': ['g42']})


def test_private_and_renamed_internal_groups_are_excluded():
    assert not capture_allowed(POLICY, 'zalo', '123', 'Khách')
    assert not capture_allowed(POLICY, 'zalo', 'g42', 'Tên mới')
    assert not capture_allowed(POLICY, 'zalo', 'g43', 'CTY IN PHÚC THANH')
    assert capture_allowed(POLICY, 'zalo', 'g44', 'A THỨC')


def test_vault_does_not_download_excluded_pending_assets(tmp_path):
    vault = Vault(tmp_path / 'state', tmp_path / 'nas')
    vault.capture_filter = lambda m: capture_allowed(POLICY, 'zalo', m['thread_id'], m['display_name'])
    m = dict(account='a', thread_id='123', message_id='1', display_name='Khách',
             sender='X', direction='incoming', timestamp=1, text='',
             _asset_requests=[dict(kind='image', url='https://example.com/private.png')])
    vault.enqueue(m)
    vault.process = lambda *a: (_ for _ in ()).throw(AssertionError('must not download'))
    vault.tick()
    assert vault.counts() == {'ignored_policy': 1}
    assert not (tmp_path / 'nas').exists()


def test_reader_policy_failure_is_closed():
    reader = Reader.__new__(Reader)
    reader.capture_policy = None
    assert not reader.capture_allowed({'thread_id': 'g1'})
