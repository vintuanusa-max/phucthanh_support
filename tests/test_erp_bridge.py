import json
from pathlib import Path
import queue
import tempfile
import unittest

from erp_bridge import Bridge, Store, TransportError, exact_group


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "capture.png"
        self.image.write_bytes(b"test image; analyzer/network are mocked")
        self.q = queue.Queue()
        self.bridge = Bridge(self.root, self.q, lambda *_: True,
                             lambda *_: [{"ma_san_pham":"PET", "so_luong":3,"ngay_giao_hang":"28/09/2026"}])
        self.addCleanup(self.bridge.close)
        self.event = {"id":"event-1","group_name":"An Bình - Đặt hàng","message":"Đơn DH-1 xong hàng"}

    def capture(self):
        return self.bridge.capture("An Bình - Đặt hàng", "msg-1", self.image, "in 3 PET")

    def row(self, table="intake"):
        with self.bridge.store.db() as db:
            return dict(db.execute("SELECT * FROM " + table).fetchone())

    def test_exact_match_preserves_accents_and_full_suffix(self):
        self.assertTrue(exact_group(" AN BÌNH - Đặt  hàng ","An Bình - Đặt hàng"))
        self.assertFalse(exact_group("An Bình - Đặt hàng","An Bình - Nội bộ"))
        self.assertFalse(exact_group("An Binh - Đặt hàng","An Bình - Đặt hàng"))

    def test_capture_deduplicates_source_not_screenshot(self):
        key = self.capture()
        self.image.write_bytes(b"changed screenshot")
        self.assertEqual(key,self.capture())
        self.assertNotEqual(self.row()["image"],b"changed screenshot")
        with self.bridge.store.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM intake").fetchone()[0],1)

    def test_different_message_can_create_same_content_order(self):
        first=self.capture()
        second=self.bridge.capture("An Bình - Đặt hàng","msg-2",self.image,"in 3 PET")
        self.assertNotEqual(first,second)

    def test_missing_source_or_prefix_rejected(self):
        with self.assertRaises(ValueError):
            self.bridge.capture("An Bình - Đặt hàng","",self.image,"x")
        with self.assertRaises(ValueError):
            self.bridge.capture("An Bình","1",self.image,"x")

    def test_lost_response_keeps_frozen_payload(self):
        self.capture()
        calls=[]
        def fail(method,path,payload=None):
            calls.append(payload)
            raise TimeoutError()
        self.bridge.request=fail
        self.bridge.process_intake()
        self.assertEqual(self.row()["state"],"ready")
        self.bridge.analyze=lambda *_: self.fail("must not analyze twice")
        with self.bridge.store.db() as db:
            db.execute("UPDATE intake SET next_try=0")
        self.bridge.request=lambda m,p,payload: (calls.append(payload) or {"status":"created","orders":[{"id":"o1"}]})
        self.bridge.process_intake()
        self.assertEqual(calls[0],calls[1])
        self.assertEqual(calls[0]["orders"][0]["ngay_giao_hang"],"2026-09-28")
        self.assertEqual(self.row()["state"],"created")

    def test_erp_validation_error_is_visible_and_not_retried(self):
        self.capture()
        def reject(*_): raise TransportError(409)
        self.bridge.request=reject
        self.bridge.process_intake()
        self.assertEqual(self.row()["state"],"failed")
        self.assertTrue(self.row()["detail"])

    def test_auto_order_policy_prevents_network(self):
        self.capture()
        self.bridge.allowed=lambda *_:False
        self.bridge.request=lambda *_:self.fail("network called")
        self.bridge.process_intake()
        self.assertEqual(self.row()["state"],"captured")

    def test_empty_ai_result_cannot_create_order(self):
        self.capture()
        self.bridge.analyze=lambda *_:[]
        self.bridge.request=lambda *_:self.fail("network called")
        self.bridge.process_intake()
        self.assertEqual(self.row()["state"],"failed")

    def test_polling_same_event_enqueues_once(self):
        self.bridge.request=lambda *_:{"items":[self.event]}
        self.bridge.pump_deliveries()
        self.bridge.pump_deliveries()
        self.assertEqual(self.q.qsize(),1)
        self.assertTrue(self.bridge.store.claim("event-1"))
        self.assertFalse(self.bridge.store.claim("event-1"))

    def test_event_id_cannot_be_reused_for_other_recipient(self):
        self.bridge.store.ingest(self.event)
        with self.assertRaises(ValueError):
            self.bridge.store.ingest({**self.event,"group_name":"Other - Group"})

    def test_crash_before_enter_can_recover(self):
        self.bridge.store.ingest(self.event)
        self.bridge.store.mark("event-1","processing")
        Store(self.bridge.store.path)
        self.assertEqual(self.row("delivery")["state"],"queued")

    def test_crash_at_enter_is_uncertain_never_requeued(self):
        self.bridge.store.ingest(self.event)
        self.bridge.store.mark("event-1","sending")
        Store(self.bridge.store.path)
        self.assertEqual(self.row("delivery")["state"],"uncertain")

    def test_worker_finally_preserves_submitted_and_blocked(self):
        self.bridge.store.ingest(self.event)
        for state in ("submitted","blocked"):
            self.bridge.store.mark("event-1",state)
            self.bridge.store.fail("event-1")
            self.assertEqual(self.row("delivery")["state"],state)

    def test_failed_report_retries_without_resending_message(self):
        self.bridge.store.ingest(self.event)
        self.bridge.store.mark("event-1","submitted")
        def fail(method,*_):
            if method=="GET": return {"items":[self.event]}
            raise TimeoutError()
        self.bridge.request=fail
        with self.assertRaises(TimeoutError): self.bridge.pump_deliveries()
        self.assertEqual(self.q.qsize(),0)
        self.assertEqual(self.row("delivery")["reported"],0)
        self.bridge.request=lambda method,*_: {"items":[self.event]} if method=="GET" else {"status":"ok"}
        self.bridge.pump_deliveries()
        self.assertEqual(self.q.qsize(),0)
        self.assertEqual(self.row("delivery")["reported"],1)

    def test_disabled_configuration_never_contacts_erp(self):
        self.bridge.request=lambda *_:self.fail("network called")
        self.bridge.run_once()

    def test_second_runtime_cannot_reset_inflight_delivery(self):
        with self.assertRaises(RuntimeError):
            Bridge(self.root, self.q, lambda *_:True, lambda *_:[])


if __name__=="__main__": unittest.main()
