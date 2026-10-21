"""Atomic, source-idempotent machine quantity additions; no price/status replacement."""
import hashlib
import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Line(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id: uuid.UUID
    expected: Decimal=Field(gt=0,max_digits=14,decimal_places=2)
    target: Decimal=Field(gt=0,max_digits=14,decimal_places=2)


class Addition(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: str=Field(min_length=16,max_length=200)
    customer_id: uuid.UUID
    order_id: uuid.UUID
    source_account: str=Field(min_length=1,max_length=100)
    group_id: str=Field(min_length=1,max_length=300)
    source_message_id: str=Field(min_length=1,max_length=300)
    delta: Decimal=Field(gt=0,max_digits=14,decimal_places=2)
    lines: list[Line]=Field(min_length=1,max_length=20)

    @model_validator(mode='after')
    def quantities(self):
        if len({l.id for l in self.lines})!=len(self.lines) or any(l.expected+self.delta!=l.target for l in self.lines):
            raise ValueError('Quantity delta mismatch or repeated lines')
        return self


def validate_lines(current,requested):
    actual={str(l['id']):Decimal(str(l['so_luong'])) for l in current}
    if set(actual)!={str(l.id) for l in requested}:
        raise HTTPException(409,'Order lines changed; review required')
    if any(actual[str(l.id)]!=l.expected for l in requested):
        raise HTTPException(409,'Quantity changed; do not add again')


def recent_order(value, now=None):
    """Today plus two preceding calendar days in Vietnam."""
    zone=timezone(timedelta(hours=7))
    today=(now or datetime.now(zone)).astimezone(zone).date()
    if value is None:return False
    if isinstance(value,str):value=datetime.fromisoformat(value)
    if isinstance(value,datetime):
        value=(value.astimezone(zone) if value.tzinfo else value).date()
    return today-timedelta(days=2)<=value<=today


def register_routes(router,machine):
    from backend_v2.db import transaction
    from backend_v2 import kho_tu_dong
    from psycopg.types.json import Jsonb

    def read(conn,customer_id,order_id,lock=False):
        row=conn.execute('''SELECT d.id,d.ma_don_hang,d.doi_tac_id,d.ngay_dat_hang,t.ma AS status
            FROM don_hang d JOIN trang_thai_don_hang t ON t.id=d.trang_thai_id
            WHERE d.id=%s AND d.doi_tac_id=%s AND d.deleted_at IS NULL'''+(' FOR UPDATE OF d' if lock else ''),(order_id,customer_id)).fetchone()
        if not row:raise HTTPException(404,'Order not found for customer')
        return row

    @router.get('/agent/order-quantity',dependencies=[Depends(machine)])
    def snapshot(customer_id:uuid.UUID,order_id:uuid.UUID):
        with transaction() as conn:
            row=read(conn,customer_id,order_id)
            lines=conn.execute('SELECT id,so_luong,duong_dan_file_in FROM don_hang_dong WHERE don_hang_id=%s ORDER BY id',(order_id,)).fetchall()
        return {'customer_id':str(customer_id),'order_id':str(order_id),'order_ref':row['ma_don_hang'],'status':row['status'],'recent':recent_order(row['ngay_dat_hang']),
                'lines':[{'id':str(l['id']),'quantity':str(l['so_luong']),'file':l['duong_dan_file_in']} for l in lines]}

    @router.get('/agent/order-match',dependencies=[Depends(machine)])
    def match(customer_id:uuid.UUID,term:str):
        term=term.strip()
        if not 5<=len(term)<=180:raise HTTPException(422,'Specific file name or design phrase required')
        with transaction() as conn:
            rows=conn.execute("""SELECT h.id,h.ma_don_hang,l.id AS line_id,l.duong_dan_file_in,l.ghi_chu,
                h.ghi_chu AS order_note FROM don_hang h JOIN don_hang_dong l ON l.don_hang_id=h.id
                WHERE h.doi_tac_id=%s AND h.deleted_at IS NULL
                AND h.ngay_dat_hang::date BETWEEN (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date-2 AND (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                AND (strpos(khong_dau(COALESCE(l.duong_dan_file_in,'')),khong_dau(%s))>0
                  OR strpos(khong_dau(COALESCE(l.ghi_chu,'')),khong_dau(%s))>0
                  OR strpos(khong_dau(COALESCE(h.ghi_chu,'')),khong_dau(%s))>0)
                ORDER BY h.id,l.id LIMIT 51""",(customer_id,term,term,term)).fetchall()
        return {'customer_id':str(customer_id),'truncated':len(rows)>50,'matches':[
            {'order_id':str(r['id']),'order_ref':r['ma_don_hang'],'line_id':str(r['line_id']),
             'file':r['duong_dan_file_in'],'note':r['ghi_chu'],'order_note':r['order_note']} for r in rows[:50]]}

    @router.post('/agent/order-quantity',dependencies=[Depends(machine)])
    def amend(req:Addition):
        digest=hashlib.sha256(req.model_dump_json().encode()).hexdigest()
        with transaction() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS chat_order_quantity_receipts(
                source_account text,group_id text,source_message_id text,request_id text UNIQUE NOT NULL,
                digest text NOT NULL,result jsonb NOT NULL,created timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(source_account,group_id,source_message_id))''')
            # Serialize duplicate source events even when a conflicting retry changes the target order.
            source='|'.join([req.source_account,req.group_id,req.source_message_id])
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(source,))
            old=conn.execute('SELECT digest,result FROM chat_order_quantity_receipts WHERE source_account=%s AND group_id=%s AND source_message_id=%s',
                (req.source_account,req.group_id,req.source_message_id)).fetchone()
            if old:
                if old['digest']!=digest:raise HTTPException(409,'Source event already applied with different content')
                return old['result']
            row=read(conn,req.customer_id,req.order_id,True)
            if not recent_order(row['ngay_dat_hang']):raise HTTPException(409,'Order outside three-day window')
            if row['status'] in ('xong_hang','huy') or conn.execute('SELECT 1 FROM phieu_thu_chi WHERE don_hang_id=%s AND deleted_at IS NULL LIMIT 1',(req.order_id,)).fetchone():
                raise HTTPException(409,'Completed/paid order requires staff review')
            current=conn.execute('SELECT id,so_luong FROM don_hang_dong WHERE don_hang_id=%s FOR UPDATE',(req.order_id,)).fetchall()
            validate_lines(current,req.lines)
            for line in req.lines:
                conn.execute('UPDATE don_hang_dong SET so_luong=%s WHERE id=%s AND don_hang_id=%s',(line.target,line.id,req.order_id))
            kho_tu_dong.dong_bo_don(conn,req.order_id)
            result={'status':'updated','request_id':req.request_id,'order_id':str(req.order_id),'customer_id':str(req.customer_id),'order_ref':row['ma_don_hang'],
                    'delta':str(req.delta),'lines':[{'id':str(l.id),'before':str(l.expected),'after':str(l.target)} for l in req.lines]}
            conn.execute('INSERT INTO chat_order_quantity_receipts(source_account,group_id,source_message_id,request_id,digest,result) VALUES(%s,%s,%s,%s,%s,%s)',
                (req.source_account,req.group_id,req.source_message_id,req.request_id,digest,Jsonb(result)))
            return result
