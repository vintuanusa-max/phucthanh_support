"""Machine-authenticated, idempotent production slip intake."""
import base64, io, re, uuid
from datetime import date
from decimal import Decimal
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from PIL import Image
from psycopg.types.json import Jsonb
from backend_v2 import uploads, zalo_integration as zi
from backend_v2.db import transaction
from backend_v2.routers import orders_router as orders

class Slip(BaseModel):
    request_id: str = Field(min_length=1,max_length=200)
    customer_id: uuid.UUID
    source: Literal['zalo','whatsapp']
    source_account: str = Field(min_length=1,max_length=200)
    group_id: str = Field(min_length=1,max_length=200)
    group_name: str = Field(min_length=1,max_length=300)
    source_message_id: str = Field(min_length=1,max_length=200)
    asset_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    design_code: str | None = Field(default=None,max_length=200)
    quantity: int = Field(gt=0,le=999999999,strict=True)
    delivery_date: date | None = None
    print_type: str = Field(default='',max_length=1500)
    product_codes: list[str] = Field(default_factory=list,max_length=1)
    nas_path: str = Field(default='',max_length=1500)
    image_base64: str = Field(max_length=7000000)

    @field_validator('design_code')
    @classmethod
    def clean_code(cls,value):
        return value.strip() or None if value is not None else None

    @field_validator('product_codes')
    @classmethod
    def codes(cls,value):
        if not all(re.fullmatch(r'TUI|PETA[2-5]|PET[0-9]+X[0-9]+',v) for v in value):
            raise ValueError('Mã hàng phiếu không hợp lệ')
        return value

def image_bytes(value):
    try:
        data=base64.b64decode(value,validate=True)
        if len(data)>5_000_000:raise ValueError()
        with Image.open(io.BytesIO(data)) as im:
            if im.format!='PNG' or im.width*im.height>24_000_000:raise ValueError()
            im.verify()
        return data
    except Exception:
        raise HTTPException(422,'Ảnh phiếu PNG không hợp lệ hoặc quá lớn')

def create(req: Slip):
    image=image_bytes(req.image_base64)
    digest=zi.payload_hash(req.model_dump(mode='json'));saved=None
    try:
        with transaction() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('zalo-intake:'+req.request_id,))
            old=conn.execute('SELECT payload_hash,response FROM zalo_intake WHERE request_id=%s',(req.request_id,)).fetchone()
            if old:
                if old['payload_hash']!=digest:raise HTTPException(409,'request_id đã dùng cho nội dung khác')
                return old['response']
            customer=zi.customer_by_id(conn,req.customer_id)
            # Serialise all slips for this customer, including cross-group duplicates.
            conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('production-slip:'+str(customer['id']),))
            day=conn.execute("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS day").fetchone()['day']
            existing=conn.execute("""SELECT response FROM zalo_intake WHERE response->>'customer_id'=%s
                AND response->>'slip_day'=%s AND response->>'asset_sha256'=%s
                AND response->>'status' IN ('created','duplicate') LIMIT 1""",
                (str(customer['id']),str(day),req.asset_sha256)).fetchone()
            duplicates=existing['response']['orders'] if existing else []
            if not duplicates and req.design_code:
                duplicates=conn.execute("""SELECT id,ma_don_hang FROM don_hang WHERE doi_tac_id=%s
                    AND deleted_at IS NULL AND (tao_luc AT TIME ZONE 'Asia/Ho_Chi_Minh')::date=%s
                    AND lower(regexp_replace(trim(ten_don_hang),'\\s+',' ','g'))=lower(regexp_replace(trim(%s),'\\s+',' ','g'))
                    ORDER BY tao_luc LIMIT 5""",(customer['id'],day,req.design_code)).fetchall()
            response={'status':'duplicate' if duplicates else 'created','orders':[],
                'customer_id':str(customer['id']),'group_id':req.group_id,'source_account':req.source_account,
                'slip_day':str(day),'asset_sha256':req.asset_sha256,'design_code':req.design_code,
                'auto_order_name':not bool(req.design_code)}
            conn.execute('INSERT INTO zalo_intake(request_id,payload_hash,response) VALUES (%s,%s,%s)',(req.request_id,digest,Jsonb({})))
            if duplicates:
                response['orders']=[{'id':str(r['id']),'ma_don_hang':r['ma_don_hang']} for r in duplicates]
            else:
                products=conn.execute('SELECT id,ma_hang FROM loai_san_pham WHERE deleted_at IS NULL').fetchall()
                matches=[p for p in products if req.product_codes and p['ma_hang'].strip().upper()==req.product_codes[0]]
                pid=matches[0]['id'] if len(matches)==1 else None
                price=conn.execute('''SELECT don_gia FROM bang_gia WHERE loai_san_pham_id=%s
                    AND (doi_tac_id=%s OR doi_tac_id IS NULL) AND so_luong_tu<=%s
                    ORDER BY (doi_tac_id IS NOT NULL) DESC,so_luong_tu DESC LIMIT 1''',(pid,customer['id'],req.quantity)).fetchone()
                amount=price['don_gia'] if price else Decimal(0)
                title=req.design_code
                note=' | '.join(x for x in [title,'CHỜ MÃ HÀNG: nhân viên bổ sung' if pid is None else '', 'Phiếu lệnh '+req.source+': '+req.group_name,
                    'Tin nguồn: '+req.source_message_id,req.nas_path,
                    'CHỜ GIÁ: nhân viên bổ sung' if not price else ''] if x)
                line=orders.DongIn(loai_san_pham_id=pid,so_luong=req.quantity,don_gia=amount,ghi_chu=title or ('Chờ bổ sung mã hàng' if pid is None else None))
                order=orders.DonHangCreate(doi_tac_id=customer['id'],ten_don_hang=title,
                    trang_thai='len_mau',ngay_giao_du_kien=req.delivery_date,yeu_cau=req.print_type,
                    ghi_chu=note,dong=[line])
                identity=orders.create_order_in_transaction(conn,order,None,[amount])
                conn.execute('INSERT INTO zalo_order_source(don_hang_id,doi_tac_id,group_name,request_id,source) VALUES (%s,%s,%s,%s,%s)',
                    (identity,customer['id'],req.group_name,req.request_id,req.source))
                saved=uploads.save(f'don_hang/{identity}','khach_dat','.png',image)
                conn.execute("INSERT INTO anh_don_hang(don_hang_id,loai,duong_dan) VALUES (%s,'khach_dat',%s)",(identity,saved))
                row=conn.execute('SELECT id,ma_don_hang FROM don_hang WHERE id=%s',(identity,)).fetchone()
                response['orders']=[{'id':str(row['id']),'ma_don_hang':row['ma_don_hang']}]
                response['waiting_product_code']=pid is None
            conn.execute('UPDATE zalo_intake SET response=%s WHERE request_id=%s',(Jsonb(response),req.request_id))
        return response
    except Exception:
        if saved:uploads.remove(saved)
        raise

def register_routes(router,machine):
    @router.get('/production-slip/capabilities',dependencies=[Depends(machine)])
    def capabilities():
        return {'production_slip_version':2,'auto_order_name':True,'waiting_product_code':True}
    router.add_api_route('/production-slip/orders',create,methods=['POST'],dependencies=[Depends(machine)])
