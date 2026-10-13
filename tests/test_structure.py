"""Kiểm tra cấu trúc sau khi tách main.py: đủ endpoint cũ, chính sách theo kênh, hook tin nhắn."""
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import messages, policy, settings

OLD_ROUTES = {
    ('GET', '/api/logs'), ('GET', '/api/screenshot'), ('GET', '/api/status'), ('GET', '/api/wa-sidebar'),
    ('GET', '/api/whatsapp-debug'), ('GET', '/api/whatsapp-status'), ('GET', '/config'),
    ('POST', '/api/broadcast-zalo'), ('POST', '/api/exit-chat'), ('POST', '/api/pause'), ('POST', '/api/resume'),
    ('POST', '/api/run-openclaw'), ('POST', '/api/scan-now'), ('POST', '/api/send-whatsapp'),
    ('POST', '/api/send-zalo'), ('POST', '/api/stop'), ('POST', '/config'),
    ('GET', '/communication-config'), ('POST', '/communication-config'),
    ('GET', '/api/communication-config'), ('POST', '/api/communication-config'),
    ('GET', '/api/erp-integration/intake'), ('POST', '/api/erp-integration/control'),
    ('POST', '/api/erp-integration/intake/{request_id}/discard'),
    ('POST', '/api/erp-integration/intake/{request_id}/products'),
    ('POST', '/api/erp-integration/intake/{request_id}/retry'),
}


class AppSmokeTests(unittest.TestCase):
    def test_main_exposes_every_old_route_without_starting_channels(self):
        import erp_bridge
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        real_bridge = erp_bridge.Bridge
        bridges = []

        def temp_bridge(root, *args):
            bridge = real_bridge(temp.name, *args)
            bridge.start = lambda: None
            bridges.append(bridge)
            return bridge

        stdout, stderr = sys.stdout, sys.stderr
        try:
            with patch('channels.start_all') as start_all, patch.object(erp_bridge, 'Bridge', temp_bridge), \
                    patch('core.logging_tee.install'):
                sys.modules.pop('main', None)
                main = importlib.import_module('main')
        finally:
            sys.stdout, sys.stderr = stdout, stderr
            for bridge in bridges:
                bridge.close()
        start_all.assert_called_once()
        # Recent FastAPI versions retain included routers lazily; inspect the published API.
        routes = {(method.upper(), path) for path, operations in main.app.openapi()['paths'].items()
                  for method in operations if method in {'get', 'post', 'put', 'patch', 'delete'}}
        self.assertEqual(OLD_ROUTES - routes, set())


class PolicyTests(unittest.TestCase):
    def test_whatsapp_reply_disabled_matches_exact_and_fuzzy_names(self):
        cfg = {'whatsapp_disable_reply_groups': ['Công ty An Bình']}
        with patch('core.policy.load_config', lambda: cfg):
            self.assertTrue(policy.whatsapp_reply_disabled('CÔNG TY AN BÌNH'))
            self.assertTrue(policy.whatsapp_reply_disabled('Cong ty An Binh - Xuong'))
            self.assertFalse(policy.whatsapp_reply_disabled('Khách khác'))
            self.assertFalse(policy.allowed('whatsapp', 'Công ty An Bình', 'receive_messages'))
            self.assertTrue(policy.allowed('whatsapp', 'Khách khác', 'receive_messages'))

    def test_whatsapp_auto_order_uses_skip_groups(self):
        cfg = {'whatsapp_skip_groups': ['Nội bộ']}
        with patch('core.policy.load_config', lambda: cfg), patch('core.policy.get_wa_skip_groups', lambda: cfg['whatsapp_skip_groups']):
            self.assertFalse(policy.allowed('whatsapp', 'nội bộ', 'auto_order'))
            self.assertTrue(policy.allowed('whatsapp', 'Khách A', 'auto_order'))

    def test_zalo_delegates_and_unknown_channel_denied(self):
        with patch('core.policy.zalo_allowed', lambda name, action: (name, action) == ('A', 'auto_order')):
            self.assertTrue(policy.allowed('zalo', 'A', 'auto_order'))
            self.assertFalse(policy.allowed('zalo', 'A', 'receive_messages'))
        self.assertFalse(policy.allowed('messenger', 'A', 'receive_messages'))

    def test_settings_without_config_blocks_zalo_actions(self):
        with tempfile.TemporaryDirectory() as d, patch.object(settings, 'CONFIG_FILE', str(Path(d) / 'missing.json')), \
                patch.object(settings, '_config_cache', {}), patch.object(settings, '_config_last_load', 0.0), \
                patch('builtins.print'):
            self.assertFalse(settings.zalo_allowed('Khách A', 'receive_messages'))


class MessageHookTests(unittest.TestCase):
    def test_publish_delivers_and_isolates_failing_subscriber(self):
        got = []
        def broken(_): raise RuntimeError('boom')
        messages.subscribe(broken)
        messages.subscribe(got.append)
        self.addCleanup(messages.unsubscribe, broken)
        self.addCleanup(messages.unsubscribe, got.append)
        msg = messages.IncomingMessage(channel='zalo', chat_id='A - B', chat_name='A - B', sender='Khách',
                                       message_id='bb_msg_id_1', text='in 100 cái')
        with patch('builtins.print'):
            messages.publish(msg)
        self.assertEqual(got, [msg])


if __name__ == '__main__':
    unittest.main()
