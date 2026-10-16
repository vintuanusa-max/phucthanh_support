import json
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    database: str = "data/hub.sqlite3"
    mode: str = "review"
    admin_token: str = ""
    ingest_token: str = ""
    webhook_secret: str = ""
    cw_url: str = ""
    cw_token: str = ""
    cw_account: int = 1
    cw_bot_id: int = 0
    inboxes: dict = field(default_factory=dict)
    gemini_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    knowledge_file: str = "knowledge.json"
    erp_url: str = ""
    erp_token: str = ""
    erp_write: bool = False

    @classmethod
    def environment(cls):
        return cls(
            database=os.getenv("HUB_DATABASE", "data/hub.sqlite3"),
            mode=os.getenv("HUB_MODE", "review"),
            admin_token=os.getenv("HUB_ADMIN_TOKEN", ""),
            ingest_token=os.getenv("HUB_INGEST_TOKEN", ""),
            webhook_secret=os.getenv("CW_WEBHOOK_SECRET", ""),
            cw_url=os.getenv("CW_URL", ""),
            cw_token=os.getenv("CW_TOKEN", ""),
            cw_account=int(os.getenv("CW_ACCOUNT", "1")),
            cw_bot_id=int(os.getenv("CW_BOT_ID", "0")),
            inboxes=json.loads(os.getenv("HUB_INBOXES", "{}")),
            gemini_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            knowledge_file=os.getenv("HUB_KNOWLEDGE", "knowledge.json"),
            erp_url=os.getenv("ERP_URL", ""),
            erp_token=os.getenv("ERP_TOKEN", ""),
            erp_write=os.getenv("ERP_WRITE_ENABLED", "false").lower() == "true",
        )

    def validate(self):
        if self.mode not in {"review", "live"}:
            raise ValueError("HUB_MODE must be review or live")
        for name in ("admin_token", "ingest_token", "webhook_secret"):
            if len(getattr(self, name)) < 32:
                raise ValueError(f"{name} must contain at least 32 characters")
        ids = []
        for account, entry in self.inboxes.items():
            if not account or entry.get("channel") not in {"zalo", "whatsapp", "viber", "native"}:
                raise ValueError("Invalid inbox configuration")
            ids.append(int(entry["inbox_id"]))
            scopes = entry.get("ai_trials", {})
            if not isinstance(scopes, dict):
                raise ValueError("ai_trials must map exact thread IDs to activation timestamps")
            for thread, scope in scopes.items():
                if not thread.startswith("g") or not thread[1:].isdigit() or not isinstance(scope, dict):
                    raise ValueError("Invalid AI trial group")
                if not isinstance(scope.get("enabled_after"), (int, float)) or scope["enabled_after"] <= 0:
                    raise ValueError("Trial requires an activation timestamp")
            if scopes and not (self.cw_bot_id and self.cw_url and self.cw_token and self.gemini_key):
                raise ValueError("AI trial requires Chatwoot bot and Gemini credentials")
        if len(ids) != len(set(ids)):
            raise ValueError("Each account must have its own inbox")
        if self.mode == "live" and not (self.cw_url and self.cw_token):
            raise ValueError("Live mode requires Chatwoot credentials")
