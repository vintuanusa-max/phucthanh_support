"""Scoped machine integration; admin-only mapping and delivery inspection."""


import base64


import binascii


import io


import uuid


import re


from pathlib import Path


from datetime import date


from decimal import Decimal


from typing import Literal





import json


import psycopg


import requests


from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile


from fastapi.responses import HTMLResponse


from pydantic import BaseModel, Field, TypeAdapter


from psycopg.types.json import Jsonb





from backend_v2 import phieu_lenh, uploads, zalo_integration as zi


from backend_v2.auth import get_current_user, require_admin


from backend_v2.db import transaction, fetch_all, fetch_one


from backend_v2.routers import orders_router as orders


from backend_v2.routers.pricing_router import tra_gia





router = APIRouter(tags=["Zalo ERP"])








@router.get("/manage", response_class=HTMLResponse, include_in_schema=False)


def management_page():


    # Only the shell is public. Every data/mutation endpoint below requires ERP admin auth.


    return Path(__file__).with_name("zalo_manage.html").read_text(encoding="utf-8")








@router.get("/status", dependencies=[Depends(get_current_user)])


def integration_status():


    return {"enabled": zi.settings()["enabled"], "protocol": 1}








def bot_request(method, path, payload=None):


    import requests


    cfg = zi.settings()


    if not cfg["enabled"]:


        raise HTTPException(503, "Kết nối Zalo chưa bật")


    bot = fetch_one("SELECT url FROM bot WHERE ma='zalo'")


    if not bot or not bot["url"]:


        raise HTTPException(503, "Chưa có địa chỉ bot Zalo")


    try:


        with requests.Session() as session:


            session.trust_env = False


            response = session.request(method, bot["url"].rstrip("/") + "/erp-integration" + path,


                json=payload, headers={"X-Zalo-Token": cfg["token"]}, timeout=(3,10), allow_redirects=False)


        if response.status_code == 409:


            raise HTTPException(409, "Trạng thái đơn đã thay đổi hoặc không cho phép thao tác này. Hãy tải lại danh sách.")


        if response.status_code in (401,403):


            raise HTTPException(503, "Mã kết nối ERP và bot Zalo chưa khớp. Kiểm tra token tích hợp trên hai bên.")


        if response.status_code == 404:


            raise HTTPException(503, "API tích hợp chưa có trên bot hoặc URL bot chưa đúng. Kiểm tra bản cập nhật bot và địa chỉ kết nối.")


        if response.status_code != 200:


            raise HTTPException(503, "Bot chưa sẵn sàng cho kết nối ERP (HTTP " + str(response.status_code) + ").")


        return response.json()


    except (requests.RequestException, ValueError):


        raise HTTPException(503, "ERP không kết nối được API máy Zalo. Kiểm tra bot đang mở, IP và mạng LAN.")








@router.get("/notification-status")


def notification_status(user: dict=Depends(get_current_user)):


    enabled=zi.settings()["enabled"]


    result={"erp_enabled":enabled,"bot_connected":False,"bot_enabled":False,


            "can_configure":bool(user.get('_admin_granted')),"counts":{},"oldest_pending":None,"last_submitted":None}


    if not enabled:


        return dict(result,detail="Tích hợp Zalo đang tắt trên ERP; chưa tạo/gửi thông báo mới.")


    result['counts']={r['state']:r['n'] for r in fetch_all("SELECT state,count(*) AS n FROM zalo_outbox WHERE detail<>'user_cancelled' GROUP BY state")}


    dates=fetch_one("SELECT min(created_at) FILTER (WHERE state IN ('pending','queued')) AS oldest_pending, max(updated_at) FILTER (WHERE state='submitted') AS last_submitted FROM zalo_outbox")


    if dates:result.update(dates)


    try:


        bot=bot_request('GET','/intake')


        result.update(bot_connected=True,bot_enabled=bool(bot.get('enabled')))


        detail=("API bot kết nối được, xử lý ERP đang bật. Tin chờ còn phụ thuộc bot chạy tiếp, đăng nhập Zalo và quyền nhận tin của nhóm."


                if result['bot_enabled'] else "API bot kết nối được nhưng xử lý ERP đang tắt. Bật xử lý đơn và thông báo bên dưới để tiếp tục.")


    except HTTPException as exc:detail=str(exc.detail)


    return dict(result,detail=detail)








@router.get("/bot-intake", dependencies=[Depends(get_current_user)])


def bot_intake():


    return bot_request("GET", "/intake")








class IntakeCleanup(BaseModel):


    kind: Literal["created", "valueerror"]








@router.post("/bot-intake/cleanup", dependencies=[Depends(require_admin)])


def cleanup_intake(req: IntakeCleanup):


    return bot_request("POST", "/intake/cleanup", req.model_dump())








@router.post("/bot-intake/{request_id}/retry", dependencies=[Depends(get_current_user)])


def retry_intake(request_id: str):


    if len(request_id) != 64 or any(c not in "0123456789abcdef" for c in request_id):


        raise HTTPException(422, "Mã yêu cầu không hợp lệ")


    return bot_request("POST", "/intake/" + request_id + "/retry")








@router.post("/bot-intake/{request_id}/discard", dependencies=[Depends(require_admin)])


def discard_intake(request_id: str):


    if len(request_id) != 64 or any(c not in "0123456789abcdef" for c in request_id):


        raise HTTPException(422, "Mã yêu cầu không hợp lệ")


    return bot_request("POST", "/intake/" + request_id + "/discard")








class ProductSelection(BaseModel):


    product_codes: list[str] = Field(min_length=1, max_length=30)








class BotControl(BaseModel):


    enabled: bool








@router.post("/bot-control", dependencies=[Depends(require_admin)])


def control_bot(req: BotControl):


    return bot_request("POST", "/control", req.model_dump())








@router.get("/products-for-intake", dependencies=[Depends(get_current_user)])


def intake_products():


    return {"items": fetch_all("SELECT ma_hang,ten_san_pham FROM loai_san_pham WHERE deleted_at IS NULL ORDER BY ma_hang")}








@router.post("/bot-intake/{request_id}/products", dependencies=[Depends(get_current_user)])


def select_intake_products(request_id: str, req: ProductSelection):


    if len(request_id) != 64 or any(c not in "0123456789abcdef" for c in request_id):


        raise HTTPException(422, "Mã yêu cầu không hợp lệ")


    available = {r["ma_hang"] for r in intake_products()["items"]}


    if any(code not in available for code in req.product_codes):


        raise HTTPException(422, "Chọn mã hàng ERP đang hoạt động cho từng dòng")


    return bot_request("POST", "/intake/" + request_id + "/products", req.model_dump())








def machine(x_zalo_token: str = Header(default="")):


    zi.authorize(x_zalo_token)








class Line(BaseModel):


    ma_san_pham: str | None = Field(default=None, max_length=200)


    ten_mau: str | None = Field(default=None, max_length=500)


    so_luong: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


    ghi_chu_mau_do: str = Field(default="", max_length=4000)


    ngay_giao_hang: date | None = None








class Intake(BaseModel):


    source: Literal["zalo", "whatsapp", "viber"] = "zalo"


    request_id: str = Field(min_length=1, max_length=200)


    group_name: str = Field(min_length=1, max_length=300)


    orders: list[Line] = Field(min_length=1, max_length=30)


    image_base64: str | None = Field(default=None, max_length=7_000_000)


    customer_id: uuid.UUID | None = None


    group_id: str | None = Field(default=None, pattern=r"^(?:g[0-9]+|[0-9]+(?:-[0-9]+)?@g\.us)$", max_length=100)


    source_account: str | None = Field(default=None, min_length=1, max_length=100)








class Group(BaseModel):


    group_name: str = Field(min_length=1, max_length=300)


    release_waiting: bool = False








@router.get("/health", dependencies=[Depends(machine)])


def health():


    return {"status": "ok", "protocol": 1, "intake_sources": ["zalo", "whatsapp", "viber"], "stable_customer_id": True, "stable_customer_id_sources": ["zalo", "whatsapp", "viber"]}








@router.get("/customers/{customer_id}", dependencies=[Depends(machine)])


def machine_customer(customer_id: uuid.UUID):


    with transaction() as conn:


        customer = zi.customer_by_id(conn, customer_id)


    return {"id": str(customer["id"]), "name": customer["ten_doi_tac"]}








@router.post("/groups/observe", dependencies=[Depends(machine)])


def observe(req: Group):


    with transaction() as conn:


        zi.register_group(conn, req.group_name)


    return {"status": "observed"}








@router.get("/groups", dependencies=[Depends(get_current_user)])


def groups():


    return {"items": fetch_all("SELECT g.*,c.ten_doi_tac FROM zalo_group g JOIN doi_tac c ON c.id=g.doi_tac_id ORDER BY group_name")}








@router.post("/groups/confirm", dependencies=[Depends(require_admin)])


def confirm(req: Group):


    with transaction() as conn:


        customer=zi.register_group(conn, req.group_name, confirmed=True)


        released=0


        if req.release_waiting:


            # Only never-dispatched messages lacking a recipient; do not replay failed/uncertain/sent events.


            events=conn.execute("""SELECT o.id AS event_id,d.id,d.doi_tac_id,c.ten_doi_tac


                FROM zalo_outbox o JOIN don_hang d ON d.id=o.don_hang_id


                JOIN doi_tac c ON c.id=d.doi_tac_id JOIN trang_thai_don_hang t ON t.id=d.trang_thai_id


                WHERE o.state='blocked' AND o.detail<>'user_cancelled' AND o.group_name IS NULL AND d.doi_tac_id=%s


                AND d.deleted_at IS NULL AND t.ma='xong_hang' ORDER BY o.id FOR UPDATE OF o""",(customer['id'],)).fetchall()


            for event in events:


                group=zi.choose_group(conn,event)


                if group:


                    conn.execute("UPDATE zalo_outbox SET group_name=%s,state='pending',detail='',updated_at=now() WHERE id=%s",(group,event['event_id']))


                    released+=1


    return {"status": "confirmed", "released":released}








@router.post("/orders", dependencies=[Depends(machine)])


def intake(req: Intake):


    data = req.model_dump(mode="json")


    # Omitted ID fields must not alter hashes of existing retries.


    for field in ("customer_id", "group_id", "source_account"):


        if data[field] is None:


            data.pop(field)


    if req.source == "viber" and (not req.customer_id or req.group_id != "viber:g1" or req.source_account != "viber-personal-1"):
        raise HTTPException(422, "Viber requires the verified CDG customer binding")
    if req.customer_id is not None:


        identity_pattern = {"zalo": r"g[0-9]+", "whatsapp": r"[0-9]+(?:-[0-9]+)?@g\.us", "viber": r"viber:g1"}[req.source]


        if not req.group_id or not re.fullmatch(identity_pattern, req.group_id) or not req.source_account or not req.request_id.startswith("chatwoot-id:"):


            raise HTTPException(422, "ID customer intake requires complete source identity")


    elif req.group_id is not None or req.source_account is not None:


        raise HTTPException(422, "Source identity requires customer_id")


    # Keep old Zalo request hashes compatible with retries.


    if req.source == "zalo":


        data.pop("source")


    digest = zi.payload_hash(data)


    saved_images = []


    try:


        with transaction() as conn:


            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("zalo-intake:" + req.request_id,))


            old = conn.execute("SELECT payload_hash,response FROM zalo_intake WHERE request_id=%s", (req.request_id,)).fetchone()


            if old:


                if old["payload_hash"] != digest:


                    raise HTTPException(409, "request_id đã dùng cho nội dung khác")


                return old["response"]


            positive_lines = [line for line in req.orders if line.so_luong > 0]


            if not positive_lines:


                response = {"status": "skipped", "orders": [], "reason": "quantity_zero"}


                conn.execute("INSERT INTO zalo_intake(request_id,payload_hash,response) VALUES (%s,%s,%s)",


                             (req.request_id, digest, Jsonb(response)))


                return response


            customer = (zi.customer_by_id(conn, req.customer_id) if req.customer_id is not None


                        else zi.intake_customer(conn, req.group_name, req.source))


            products = conn.execute("SELECT id,ma_hang FROM loai_san_pham WHERE deleted_at IS NULL").fetchall()


            prepared = []


            for line in positive_lines:


                matches = [p for p in products if zi.normalize(p["ma_hang"]) == zi.normalize(line.ma_san_pham or "")]


                product_id=matches[0]["id"] if len(matches)==1 else None


                price=None


                if product_id:


                    price=conn.execute("""SELECT don_gia FROM bang_gia WHERE loai_san_pham_id=%s


                      AND (doi_tac_id=%s OR doi_tac_id IS NULL) AND so_luong_tu<=%s


                      ORDER BY (doi_tac_id IS NOT NULL) DESC,so_luong_tu DESC LIMIT 1""",


                      (product_id,customer["id"],line.so_luong)).fetchone()


                note=" | ".join(x for x in (line.ten_mau,line.ma_san_pham if line.ma_san_pham != line.ten_mau else None,line.ghi_chu_mau_do,


                      "") if x)


                ln=orders.DongIn(loai_san_pham_id=product_id if price else None,


                    so_luong=line.so_luong,ghi_chu=note)


                prepared.append((line,ln,price["don_gia"] if price else Decimal(0)))


            image = None


            if req.image_base64:


                try:


                    image = base64.b64decode(req.image_base64, validate=True)


                    if len(image) > uploads.MAX_BYTES:


                        raise HTTPException(413, "Ảnh lớn hơn 5MB")


                    from PIL import Image


                    with Image.open(io.BytesIO(image)) as img:


                        if img.format != "PNG":


                            raise ValueError("PNG required")


                        img.verify()


                except (ValueError, binascii.Error, OSError):


                    raise HTTPException(422, "Ảnh chụp PNG không hợp lệ")


            conn.execute("INSERT INTO zalo_intake(request_id,payload_hash,response) VALUES (%s,%s,%s)",


                         (req.request_id, digest, Jsonb({})))


            result = []


            for line, ln, price in prepared:


                req_order = orders.DonHangCreate(doi_tac_id=customer["id"], dong=[ln],


                    ten_don_hang=None, trang_thai="len_mau",


                    ngay_giao_du_kien=line.ngay_giao_hang, ghi_chu={"zalo": "Nguồn Zalo: ", "whatsapp": "Nguồn WhatsApp: ", "viber": "Nguồn Viber: "}[req.source] + req.group_name)


                order_id = orders.create_order_in_transaction(conn, req_order, None, [price])


                conn.execute("INSERT INTO zalo_order_source(don_hang_id,doi_tac_id,group_name,request_id,source) VALUES (%s,%s,%s,%s,%s)",


                             (order_id, customer["id"], req.group_name.strip(), req.request_id, req.source))


                if image:


                    rel = uploads.save(f"don_hang/{order_id}", "khach_dat", ".png", image)


                    saved_images.append(rel)


                    conn.execute("INSERT INTO anh_don_hang(don_hang_id,loai,duong_dan) VALUES (%s,'khach_dat',%s)", (order_id, rel))


                row = conn.execute("SELECT id,ma_don_hang FROM don_hang WHERE id=%s", (order_id,)).fetchone()


                result.append({"id": str(row["id"]), "ma_don_hang": row["ma_don_hang"]})


            response = {"status": "created", "orders": result}


            if req.customer_id is not None:


                response.update(customer_id=str(customer["id"]), group_id=req.group_id, source_account=req.source_account)


            conn.execute("UPDATE zalo_intake SET response=%s WHERE request_id=%s", (Jsonb(response), req.request_id))


        return response


    except Exception:


        for rel in saved_images:


            uploads.remove(rel)


        raise








@router.get("/outbox", dependencies=[Depends(machine)])


def pending():


    with transaction() as conn:


        zi.release_missing_recipients(conn)


    # Bot keeps a durable local inbox. Repeated reads are intentional and deduplicated there.


    return {"items": fetch_all("SELECT id,group_name,message,state FROM zalo_outbox WHERE state IN ('pending','queued') ORDER BY created_at LIMIT 50")}








class Result(BaseModel):


    state: Literal["queued", "submitted", "failed", "blocked", "uncertain"]


    detail: str = Field(default="", max_length=500)








@router.post("/outbox/{event_id}/result", dependencies=[Depends(machine)])


def report(event_id: uuid.UUID, req: Result):


    with transaction() as conn:


        row = conn.execute("SELECT state FROM zalo_outbox WHERE id=%s FOR UPDATE", (event_id,)).fetchone()


        if not row:


            raise HTTPException(404, "Không có thông báo")


        if row["state"] in ("pending", "queued"):


            conn.execute("UPDATE zalo_outbox SET state=%s,detail=%s,updated_at=now() WHERE id=%s",


                         (req.state, req.detail, event_id))


    return {"status": "ok"}








@router.get("/deliveries", dependencies=[Depends(get_current_user)])


def deliveries():


    return {"items": fetch_all("""SELECT o.*,d.doi_tac_id,d.ma_don_hang,c.ten_doi_tac,


        (d.deleted_at IS NULL AND t.ma='xong_hang' AND


         NOT EXISTS (SELECT 1 FROM zalo_order_source src WHERE src.don_hang_id=d.id AND src.source<>'zalo')) AS can_resolve


        FROM zalo_outbox o JOIN don_hang d ON d.id=o.don_hang_id


        JOIN doi_tac c ON c.id=d.doi_tac_id JOIN trang_thai_don_hang t ON t.id=d.trang_thai_id


        WHERE o.detail<>'user_cancelled' ORDER BY o.created_at DESC LIMIT 200""")}











@router.post('/outbox/clear-waiting', dependencies=[Depends(require_admin)])


def clear_waiting():


    # Snapshot IDs then cancel on bot without holding PostgreSQL locks across network.


    rows=fetch_all("SELECT id FROM zalo_outbox WHERE state IN ('pending','queued','blocked') AND detail<>'user_cancelled' ORDER BY created_at LIMIT 500")


    if not rows:return {'cleared':0,'kept':0,'more':False}


    ids=[str(row['id']) for row in rows]


    result=bot_request('POST','/deliveries/cancel',{'ids':ids})


    cancelled=set(result.get('cancelled',[])).intersection(ids)


    count=0


    with transaction() as conn:


        for event_id in cancelled:


            count+=conn.execute("UPDATE zalo_outbox SET state='blocked',detail='user_cancelled',message='',group_name=NULL,updated_at=now() WHERE id=%s AND state IN ('pending','queued','blocked') AND detail<>'user_cancelled'",(event_id,)).rowcount


    return {'cleared':count,'kept':len(ids)-count,'more':len(rows)==500}





@router.post("/outbox/{event_id}/resolve", dependencies=[Depends(require_admin)])


def resolve(event_id: uuid.UUID):


    # Only a missing ERP-side mapping can be released here; never resend an uncertain UI action.


    with transaction() as conn:


        event = conn.execute("SELECT * FROM zalo_outbox WHERE id=%s FOR UPDATE", (event_id,)).fetchone()


        if not event or event["state"] != "blocked" or event["group_name"] or event["detail"] == "user_cancelled":


            raise HTTPException(409, "Chỉ xử lý thông báo đang thiếu nhóm nhận")


        order = conn.execute("""SELECT d.id,d.doi_tac_id,c.ten_doi_tac FROM don_hang d JOIN doi_tac c ON c.id=d.doi_tac_id


            JOIN trang_thai_don_hang t ON t.id=d.trang_thai_id WHERE d.id=%s AND d.deleted_at IS NULL AND t.ma='xong_hang'""",


                             (event["don_hang_id"],)).fetchone()


        group = zi.choose_group(conn, order) if order else None


        if not group:


            raise HTTPException(409, "Chưa có nhóm duy nhất đã xác nhận hoặc đơn không còn Xong hàng")


        conn.execute("UPDATE zalo_outbox SET group_name=%s,state='pending',detail='',updated_at=now() WHERE id=%s", (group, event_id))


    return {"status": "pending"}








# ---- Lên đơn từ ảnh: phiếu lệnh hoặc ảnh chụp phòng chat Zalo (người dùng ERP đăng nhập; không dùng mã máy,


# không cần bật kết nối Zalo) ----





@router.get("/phieu-lenh/danh-muc", dependencies=[Depends(get_current_user)])


def phieu_catalog():


    """Khách và mã hàng cho các ô chọn của mục này (riêng, để không phụ thuộc quyền của /products-for-intake)."""


    return {"khach_hang": fetch_all("SELECT id,ten_doi_tac FROM doi_tac WHERE deleted_at IS NULL ORDER BY ten_doi_tac"),


            "ma_hang": intake_products()["items"]}








@router.post("/phieu-lenh/doc", dependencies=[Depends(get_current_user)])


def read_phieu(file: UploadFile = File(...), loai: str = Form("")):


    """Đọc ảnh bằng Gemini, trả bản nháp để người dùng kiểm tra. Chưa tạo gì.


    loai='phieu_lenh': một dòng hàng. loai='tin_nhan_chat': nhiều dòng, khách khớp theo tên nhóm ở đầu ảnh.


    Người dùng đã biết loại (chọn tệp = phiếu lệnh, dán ảnh chụp = chat Zalo) thì gửi luôn để khỏi tốn thêm một


    lượt gọi Gemini nhận diện; để trống thì ERP tự nhận ra."""


    if loai not in ("", "phieu_lenh", "tin_nhan_chat"):


        raise HTTPException(422, "Loại ảnh không hợp lệ")


    _, content = uploads.read_image(file)


    if not phieu_lenh.san_sang():


        raise HTTPException(503, "ERP chưa cấu hình khóa Gemini (ERP_GEMINI_API_KEY).")


    try:


        loai = loai or phieu_lenh.phan_loai(content)


        data = phieu_lenh.doc_chat(content) if loai == "tin_nhan_chat" else phieu_lenh.doc_phieu(content)


    except (requests.RequestException, RuntimeError):


        raise HTTPException(502, "Không đọc được ảnh (lỗi Gemini). Thử lại hoặc nhập tay.")


    codes = [r["ma_hang"] for r in intake_products()["items"]]


    if loai != "tin_nhan_chat":


        data["ma_hang"] = phieu_lenh.goi_y_ma_hang(data["loai_in"], codes)


        return {"loai": loai, **data}


    try:      # nhóm chủ xưởng đã xác nhận với khách; bảng chỉ có khi đã bật kết nối Zalo


        nhom_biet = fetch_all("SELECT group_name,doi_tac_id FROM zalo_group")


    except Exception:


        nhom_biet = []


    kq = phieu_lenh.tim_khach(data["ten_nhom"], fetch_all("SELECT id,ten_doi_tac FROM doi_tac WHERE deleted_at IS NULL"), nhom_biet)


    khach = kq["khach"]


    for d in data["dong"]:


        d["ma_hang"] = phieu_lenh.goi_y_ma_hang_chat(d["don_vi"], " ".join(x for x in (d["ten_mau"], d["ghi_chu"]) if x), codes)


    return {"loai": loai, **data, "khach_id": str(khach["id"]) if khach else None,


            "ten_khach": khach["ten_doi_tac"] if khach else None, "cach_khop": kq["cach"],


            "goi_y_khach": [{"id": str(k["id"]), "ten_doi_tac": k["ten_doi_tac"]} for k in kq["goi_y"]]}








def _create_order_from_image(current_user, content, ext, doi_tac_id, ten, yeu_cau, ghi_chu_don, ngay, dong, chap_nhan_trung):


    """Tạo đơn + lưu ảnh làm ảnh khách đặt. dong: [(ma_hang, so_luong, ghi_chu_dong)]; giá theo bảng giá."""


    ten = ten.strip()


    if not fetch_one("SELECT 1 AS ok FROM doi_tac WHERE id=%s AND deleted_at IS NULL", (doi_tac_id,)):


        raise HTTPException(422, "Khách hàng không tồn tại hoặc đã bị xóa")


    lines, gia_thieu = [], []


    for ma_hang, so_luong, ghi_chu_dong in dong:


        sp = fetch_one("SELECT id FROM loai_san_pham WHERE ma_hang=%s AND deleted_at IS NULL", (ma_hang,))


        if ma_hang and not sp:


            raise HTTPException(422, f"Mã hàng không hợp lệ hoặc đã ngừng dùng: {ma_hang}")


        gia = tra_gia(sp["id"], so_luong, doi_tac_id) if sp else None


        if not gia:


            gia_thieu.append(f"{ma_hang} (SL {so_luong:f})")


        don_gia = gia["don_gia"] if gia else Decimal(0)


        lines.append((orders.DongIn(loai_san_pham_id=sp["id"] if sp else None, so_luong=so_luong, don_gia=don_gia,


                                    ghi_chu=(ghi_chu_dong or "").strip() or None), don_gia))


    trung = fetch_all("SELECT ma_don_hang FROM don_hang WHERE doi_tac_id=%s AND ten_don_hang=%s AND deleted_at IS NULL "


                      "ORDER BY tao_luc DESC LIMIT 5", (doi_tac_id, ten))


    if trung and not chap_nhan_trung:


        raise HTTPException(409, "Khách này đã có đơn cùng tên: " + ", ".join(r["ma_don_hang"] for r in trung))


    ghi_chu = " | ".join(x for x in (ghi_chu_don.strip(), "Chưa có giá cho " + ", ".join(gia_thieu) + ", cần nhập đơn giá"


                                     if gia_thieu else "") if x)


    req = orders.DonHangCreate(doi_tac_id=doi_tac_id, ten_don_hang=ten, yeu_cau=(yeu_cau or "").strip() or None,


                               ghi_chu=ghi_chu or None, ngay_giao_du_kien=ngay, dong=[ln for ln, _ in lines])


    saved = None


    try:


        with transaction() as conn:


            order_id = orders.create_order_in_transaction(conn, req, current_user["id"], [g for _, g in lines])


            saved = uploads.save(f"don_hang/{order_id}", "khach_dat", ext, content)


            conn.execute("INSERT INTO anh_don_hang(don_hang_id,loai,duong_dan,tai_len_boi) VALUES (%s,'khach_dat',%s,%s)",


                         (order_id, saved, current_user["id"]))


            row = conn.execute("SELECT id,ma_don_hang FROM don_hang WHERE id=%s", (order_id,)).fetchone()


    except psycopg.IntegrityError:


        uploads.remove(saved)


        raise HTTPException(400, "Dữ liệu không hợp lệ.")


    except Exception:


        uploads.remove(saved)


        raise


    return {"id": str(row["id"]), "ma_don_hang": row["ma_don_hang"], "don_gia": lines[0][1],


            "co_gia": not gia_thieu, "so_dong": len(lines)}








@router.post("/phieu-lenh/tao", status_code=201)


def create_from_phieu(


    file: UploadFile = File(...),


    doi_tac_id: uuid.UUID = Form(...),


    ten_don_hang: str = Form("", max_length=300),


    so_luong: Decimal = Form(..., gt=0, max_digits=14, decimal_places=2),


    ma_hang: str = Form("", max_length=200),


    loai_in: str = Form("", max_length=500),


    ngay_giao_du_kien: date | None = Form(None),


    chap_nhan_trung: bool = Form(False),


    current_user: dict = Depends(get_current_user),


):


    """Tạo đơn từ phiếu lệnh đã kiểm tra: một dòng hàng, ảnh phiếu lưu làm ảnh khách đặt."""


    ext, content = uploads.read_image(file)


    ghi_chu = (f"Loại in: {loai_in.strip()} | " if loai_in.strip() else "") + "Lên đơn từ ảnh phiếu lệnh (trang Kết nối Zalo)"


    return _create_order_from_image(current_user, content, ext, doi_tac_id, ten_don_hang, loai_in, ghi_chu,


                                    ngay_giao_du_kien, [(ma_hang, so_luong, "")], chap_nhan_trung)








class DongChat(BaseModel):


    ma_hang: str = Field(default="", max_length=200)


    so_luong: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


    ghi_chu: str = Field(default="", max_length=1000)








@router.post("/phieu-lenh/tao-chat", status_code=201)


def create_from_chat(


    file: UploadFile = File(...),


    doi_tac_id: uuid.UUID = Form(...),


    ten_don_hang: str = Form("", max_length=300),


    dong: str = Form(..., max_length=60000),


    ghi_chu: str = Form("", max_length=2000),


    ngay_giao_du_kien: date | None = Form(None),


    chap_nhan_trung: bool = Form(False),


    current_user: dict = Depends(get_current_user),


):


    """Tạo MỘT đơn nhiều dòng từ ảnh chụp phòng chat đã kiểm tra. `dong` là JSON [{ma_hang, so_luong, ghi_chu}]."""


    ext, content = uploads.read_image(file)


    try:


        ds = TypeAdapter(list[DongChat]).validate_python(json.loads(dong))


    except ValueError:


        raise HTTPException(422, "Danh sách dòng hàng không hợp lệ (mỗi dòng cần mã hàng và số lượng lớn hơn 0)")


    if not 1 <= len(ds) <= phieu_lenh.MAX_DONG:


        raise HTTPException(422, f"Đơn cần từ 1 đến {phieu_lenh.MAX_DONG} dòng hàng")


    return _create_order_from_image(current_user, content, ext, doi_tac_id, ten_don_hang, None,


                                    (ghi_chu.strip() + " | " if ghi_chu.strip() else "") + "Lên đơn từ ảnh chụp tin nhắn Zalo (trang Kết nối Zalo)",


                                    ngay_giao_du_kien, [(d.ma_hang, d.so_luong, d.ghi_chu) for d in ds], chap_nhan_trung)








@router.get("/agent/order-status", dependencies=[Depends(machine)])


def agent_order_status(customer_id: uuid.UUID, order_ref: str):


    if not re.fullmatch(r"[A-Za-z0-9-]{5,64}", order_ref):


        raise HTTPException(422, "Invalid order reference")


    with transaction() as conn:


        row = conn.execute(


            "SELECT dh.id,dh.ma_don_hang,dh.doi_tac_id,tt.ten_hien_thi "


            "FROM don_hang dh JOIN trang_thai_don_hang tt ON tt.id=dh.trang_thai_id "


            "WHERE dh.doi_tac_id=%s AND dh.deleted_at IS NULL "


            "AND (dh.ma_don_hang=%s OR dh.id::text=%s)",


            (customer_id, order_ref, order_ref),


        ).fetchone()


    if not row:


        raise HTTPException(404, "Order not found for mapped customer")


    return {"customer_id": str(row["doi_tac_id"]), "order_id": str(row["id"]),


            "order_ref": row["ma_don_hang"], "status": row["ten_hien_thi"]}






from backend_v2.slip_intake import register_routes as register_slip_routes

register_slip_routes(router, machine)

