import json

import pytest
from test_order_intake import acknowledge, capture, rows
from test_order_intake import intake as intake

CUSTOMER = "5e1f5d50-6c1f-4bc9-8a1f-1bdc12eefad7"


def test_rename_preserves_customer_and_account_scope(intake):
    _, store, engine = intake
    bound = engine.customer_mappings.set("wa-1", "g123", CUSTOMER, "Khách ERP", 0)
    store.bind("wa-1", "g123", "Tên nhóm đổi hoàn toàn", 10, 20)
    assert engine.customer_mappings.get("wa-1", "g123") == bound
    assert engine.customer_mappings.get("other-account", "g123") is None
    assert engine.customer_mappings.list()[0]["display_name"] == "Tên nhóm đổi hoàn toàn"
    with pytest.raises(ValueError):
        engine.customer_mappings.set("wa-1", "g123", CUSTOMER, "Đổi", 0)


def test_bound_order_uses_id_and_rejects_midflight_mapping_changes(intake):
    _, store, engine = intake
    engine.customer_mappings.set("wa-1", "g123", CUSTOMER, "Khách ERP", 0)
    engine.erp.validate_customer_id = lambda identity: {"id": identity}
    engine.erp.observe_group = lambda name: pytest.fail("Must not resolve bound groups by name")
    capture(store, display_name="Tên mới không cần dấu gạch")
    engine.order_intake.poll()
    run = rows(store)[0]
    assert run["state"] == "awaiting_evidence"
    assert json.loads(run["payload"])["customer_binding"]["customer_id"] == CUSTOMER
    acknowledge(engine, run["id"])
    engine.customer_mappings.set("wa-1", "g123", CUSTOMER, "Sửa ánh xạ", 1)
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "review" and not engine.erp.calls


def test_bound_payload_has_exact_ids_after_rename(intake):
    _, store, engine = intake
    engine.customer_mappings.set("wa-1", "g123", CUSTOMER, "Khách ERP", 0)
    engine.erp.validate_customer_id = lambda identity: {"id": identity}
    capture(store, display_name="Tên mới")
    engine.order_intake.poll()
    acknowledge(engine, rows(store)[0]["id"])
    engine.order_intake.poll()
    sent = engine.erp.calls[0]
    assert sent["customer_id"] == CUSTOMER and sent["group_id"] == "g123"
    assert sent["source_account"] == "wa-1" and sent["group_name"] == "Tên mới"
    assert sent["request_id"].startswith("chatwoot-id:")


def test_unsupported_id_api_never_falls_back_to_name(intake):
    _, store, engine = intake
    engine.customer_mappings.set("wa-1", "g123", CUSTOMER, "Khách ERP", 0)

    def unsupported(identity):
        raise ValueError("ERP does not support ID binding")

    engine.erp.validate_customer_id = unsupported
    engine.erp.observe_group = lambda name: pytest.fail("Unsafe name fallback")
    capture(store)
    engine.order_intake.poll()
    assert rows(store)[0]["state"] == "review" and not engine.erp.calls
