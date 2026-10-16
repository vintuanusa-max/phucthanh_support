"""Versioned workbook references and conservative deterministic quote calculation."""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

APPROVED_SOURCE_SHA256='3db3bb0bc3133f6b4291aedc62d5dd089d16f9a59ddf09e1829387ab6e068dc7'

RULE_ROWS={'pet_meter':5,'transfer_meter':6,'pet_area':25,'transfer_hat_child':19,'transfer_hat_adult':19,'pet_finished_hat':28,'transfer_bag':26,'cut_pet_meter':36,'laser_panel':30,'laser_perimeter':32,'canavi':37}

def catalog():
    return json.loads(Path(__file__).with_name('pricebook.json').read_text(encoding='utf-8'))

def lookup(service):
    book=catalog()
    selected=[{'row':int(k),**v} for k,v in book['rows'].items() if int(k) in set(RULE_ROWS.values())|{4,17,18,21,27,29,31,35} and (not service or service.casefold() in v['service'].casefold())]
    return {'source':book['source'],'sha256':book['sha256'],'sheet':'BAOGIA','rows':selected,'rules':RULE_ROWS,'constraints':['Hỏi kích thước thực tế, số lượng, kỹ thuật và vị trí in; không suy kích thước từ pixel.','PET mét: 5-10m và ranh giới 100/500m chưa rõ, nhân viên xác nhận. PET diện tích theo xác nhận chủ 15/10: 1000 × ngang × cao / 49, ít nhất một chiều <=29cm.','C32 được chủ xác nhận sửa ngày 15/10: hình chữ nhật dùng 2 × (dài + rộng); hình khác cần đường cắt thực tế.','CANAVI dùng giá riêng theo khách ánh xạ, không dùng bảng chung.','Chưa có quy định VAT, làm tròn, phí ép/giao: không tự cộng hoặc cam kết đã bao gồm.']}

def quote(args, customer_name=''):
    book=catalog();rule=args.get('rule')
    if rule not in RULE_ROWS:raise ValueError('Unknown price rule')
    row=RULE_ROWS[rule];ref={'source':book['source'],'sha256':book['sha256'],'sheet':'BAOGIA','range':f'C{row}','rule':rule}
    def review(reason):return {'state':'human_review','reason':reason,**ref}
    if book['sha256']!=APPROVED_SOURCE_SHA256:return review('Bảng giá đã đổi phiên bản; cần kiểm tra lại quy tắc trước khi tính')
    fields=['width_cm','height_cm','quantity']
    missing=[f for f in fields if args.get(f) is None]
    if missing:return {'state':'missing_fields','missing_fields':missing,**ref}
    w,h,q=(Decimal(str(args[f])) for f in fields)
    if any(not x.is_finite() or x<=0 for x in (w,h,q)):raise ValueError('Invalid quote dimensions or quantity')
    unit=args.get('quantity_unit');price=None
    if 'canavi' in customer_name.casefold() or rule=='canavi':return review('Giá CANAVI riêng theo A5/A4/A3, cần xác nhận ranh giới và mẫu; không áp giá chung.')
    if rule in ('pet_meter','transfer_meter','cut_pet_meter'):
        if unit!='meter':return review('Bảng này tính mét dài; chưa có sơ đồ xếp mẫu để đổi số cái sang mét.')
        if rule=='pet_meter':
            if w>58:return review('Vượt khổ PET 58cm')
            if q<5:price=70000
            elif 10<=q<100:price=65000
            elif 100<q<500:price=60000
            elif 500<q<=1000:price=50000
            elif q>1000:price=45000
        elif rule=='transfer_meter':
            if w>160:return review('Vượt khổ chuyển nhiệt 160cm')
            if 100<=q<=500:price=18000
            elif 500<q<=2000:price=15000
            elif q>2000:price=14000
        else:price=10000
    else:
        if unit!='piece' or q!=q.to_integral_value():return review('Cần số lượng cái nguyên, đúng đơn vị áp dụng')
        if rule=='pet_area':
            if w>29 and h>29:return review('Cả ngang và cao đều lớn hơn 29cm; nhân viên tính giá riêng và nhắn sau.')
            price=(Decimal(1000)*w*h/Decimal(49)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
            ref.update(owner_override='15/10/2026: dùng mốc 7x7=1000 cho tất cả, ít nhất một chiều <=29cm',formula='1000 * width_cm * height_cm / 49',rounding='Đơn giá tham khảo làm tròn tới 1 đồng')
        elif rule=='transfer_hat_child':price=1000
        elif rule=='transfer_hat_adult':price=1200
        elif rule=='pet_finished_hat':return review('C28 ghi giá thường 2500/vị trí mạc nón; cần xác nhận kích thước/vị trí, chưa phải giá cố định')
        elif rule=='transfer_bag':return review('C26 có giá theo số lượng nhưng chưa quy định kích thước/số mặt; nhân viên xác nhận')
        elif rule=='laser_panel':price=100
        elif rule=='laser_perimeter':
            if args.get('shape')!='rectangle':return review('Cần chu vi đường cắt thực tế; không dùng khung bao chữ nhật cho hình bất kỳ')
            price=(Decimal(100)*2*(w+h)/Decimal(50)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
            ref.update(owner_override='15/10/2026: sửa chu vi thành 2*(dài+rộng)',formula='100 * 2 * (width_cm + height_cm) / 50',rounding='Đơn giá tham khảo làm tròn tới 1 đồng')
    if price is None:return review('Số lượng thuộc khoảng trống hoặc ranh giới chưa rõ trong bảng giá')
    return {'state':'quoted','unit_price_vnd':int(price),'quantity':str(q),'quantity_unit':unit,'total_vnd':str(Decimal(price)*q),'width_cm':str(w),'height_cm':str(h),'terms':'Giá tham khảo theo bảng; chưa xác nhận VAT và phí khác, chưa phải đơn đặt hàng.',**ref}
