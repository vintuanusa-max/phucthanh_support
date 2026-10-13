"""Read legacy policy, and save the Hub's evidence on the existing NAS share."""

import base64
import json
import time
from pathlib import Path

from hub.evidence_document import erp_evidence_png, save_document
from hub.order_policy import sanitize


def synchronize(reader):
    path = reader.cfg.get("order_policy_file")
    if not path or time.monotonic() - getattr(reader, "last_order_sync", 0) < 30:
        return
    reader.last_order_sync = time.monotonic()
    # No credentials or unrelated legacy settings leave the Windows host.
    reader.cfg.pop("order_policy", None)
    policy = sanitize(json.loads(Path(path).read_text(encoding="utf-8-sig")))
    prefix = f"/adapters/{reader.cfg['account']}"
    response = reader.http.post(prefix + "/order-policy", json=policy)
    response.raise_for_status()
    reader.cfg["order_policy"] = policy
    reader.cfg["order_intake"] = response.json()["scope"]
    response = reader.http.get(prefix + "/order-evidence")
    response.raise_for_status()
    job = response.json().get("job")
    if not job:
        return
    try:
        result = save_document(job["messages"], job["reference"], reader.cfg["archive"]["root"])
        image = erp_evidence_png(result)
        payload = {**result, "image_base64": base64.b64encode(image).decode()}
    except Exception as exc:
        reader.http.post(
            prefix + "/order-evidence/" + job["id"], json={"error": type(exc).__name__}
        ).raise_for_status()
        raise
    reader.http.post(prefix + "/order-evidence/" + job["id"], json=payload).raise_for_status()
