from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
import unicodedata


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageInput(StrictModel):
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    data: str = Field(min_length=4, max_length=5592408)


class Asset(StrictModel):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    name: str = Field(max_length=200)
    kind: Literal["image", "file", "link"]
    state: Literal["ready", "failed"]
    relative_path: str = Field(default="", max_length=1000)
    sha256: str = Field(default="", max_length=64)
    size: int = Field(default=0, ge=0)
    mime_type: str = Field(default="", max_length=120)
    error: str = Field(default="", max_length=200)


class QuotedImage(StrictModel):
    message_id: str = Field(max_length=100)
    client_message_id: str = Field(max_length=100)
    sender_id: str = Field(max_length=100)
    sender: str = Field(max_length=300)
    timestamp: float = Field(ge=0)
    resolved: bool


class Capture(StrictModel):
    account: str = Field(min_length=1, max_length=100)
    thread_id: str = Field(min_length=1, max_length=300)
    message_id: str = Field(min_length=1, max_length=300)
    client_message_id: str = Field(default="", max_length=100)
    display_name: str = Field(min_length=1, max_length=300)
    sender: str = Field(default="", max_length=300)
    sender_id: str = Field(default="", max_length=100)
    direction: Literal["incoming", "outgoing"] = "incoming"
    origin: Literal["customer", "staff", "legacy_bot", "erp"] = "customer"
    text: str = Field(default="", max_length=20000)
    attachments: list[str] = Field(default_factory=list, max_length=30)
    images: list[ImageInput] = Field(default_factory=list, max_length=1)
    assets: list[Asset] = Field(default_factory=list, max_length=10)
    timestamp: float = Field(gt=0)
    revision: int = Field(default=0, ge=0)
    recalled: bool = False
    quoted_image: QuotedImage | None = None


class OrderLine(StrictModel):
    ma_san_pham: str = Field(min_length=1, max_length=200)
    ten_mau: str | None = Field(default=None, max_length=500)
    so_luong: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    ghi_chu_mau_do: str = Field(default="", max_length=4000)
    ngay_giao_hang: date | None = None


class Decision(StrictModel):
    action: Literal["reply", "handoff", "draft_order"]
    reply: str = Field(default="", max_length=8000)
    reason: str = Field(default="", max_length=2000)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    orders: list[OrderLine] = Field(default_factory=list, max_length=30)
    source_message_ids: list[int] = Field(default_factory=list, max_length=30)


class IntakeOrderLine(OrderLine):
    print_position_group: str | None = Field(default=None, min_length=1, max_length=100)
    ma_san_pham: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("ma_san_pham", mode="before")
    @classmethod
    def normalize_pending_product(cls, value):
        # These are missing-code labels, never actual ERP product codes.
        if isinstance(value, str):
            normalized = " ".join(unicodedata.normalize("NFC", value).casefold().split())
            if normalized in {"chờ mã", "erp chờ mã", "cho ma", "erp cho ma", "null", "none", ""}:
                return None
        return value


class IntakeDecision(Decision):
    orders: list[IntakeOrderLine] = Field(default_factory=list, max_length=30)


class Control(StrictModel):
    owner: Literal["ai", "human"]


class Mapping(StrictModel):
    group_name: str = Field(min_length=1, max_length=300)


class CustomerBinding(StrictModel):
    customer_id: UUID
    customer_name: str = Field(min_length=1, max_length=300)
    expected_version: int = Field(default=0, ge=0)


class DeliveryResult(StrictModel):
    state: Literal["submitted", "confirmed", "blocked", "failed", "uncertain"]
    platform_message_id: str = Field(default="", max_length=300)
    detail: str = Field(default="", max_length=500)


class DeliveryPrepare(StrictModel):
    client_id: str = Field(pattern=r"^[0-9]{10,20}$")


class ThreadNames(StrictModel):
    names: dict[
        Annotated[str, Field(pattern=r"^g[0-9]+$", max_length=100)],
        Annotated[str, Field(min_length=1, max_length=300)],
    ] = Field(max_length=5000)
