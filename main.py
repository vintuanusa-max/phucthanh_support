"""Bot Zalo / WhatsApp Phúc Thành — điểm vào.

Lệnh chạy giữ nguyên: ``uvicorn main:app --host 0.0.0.0 --port 8000``.
Thứ tự khởi động giống bản cũ: log -> API cấu hình -> ERP bridge -> các kênh -> OpenClaw.
"""
import os

os.environ["NODE_OPTIONS"] = "--no-deprecation"

import threading

from fastapi import FastAPI

from core import logging_tee

logging_tee.install()

from api.routes import router as bot_router
from channels import start_all
from communication_api import router as communication_router
from core import intake
from core.integrations import openclaw_worker

app = FastAPI()
app.include_router(communication_router)
app.include_router(communication_router, prefix="/api")

intake.start_erp_bridge(app)

# Opt-in Chatwoot relay; disabled unless PHUCTHANH_HUB_CONFIG is configured.
from chatwoot_relay import start_if_configured

start_if_configured()
start_all()
threading.Thread(target=openclaw_worker, daemon=True).start()

app.include_router(bot_router)
