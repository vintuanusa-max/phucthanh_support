"""Bag-print planning metadata only; no graphics execution."""
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import Field
from hub.models import StrictModel

FIELDS={'design_code','construction','has_bottom','print_faces','fabric_scope','split_axis','split_confirmed',
 'finished_height_cm','finished_width_cm','gusset_cm','bottom_cm','fabric_height_cm','fabric_width_cm',
 'mouth_allowance_cm','top_offset_finished_cm','top_offset_reference','right_offset_cm','left_offset_cm',
 'front_print','back_print','gusset_print','bottom_print','handle_print','handle_template_code','handle_roll_width_cm',
 'source_artwork','source_maket','source_slip','output_format','color_profile','mirror','bleed_cm','shrink_compensation','approval_version'}

class BagFact(StrictModel):
    field: str = Field(max_length=60)
    value: str = Field(max_length=1000)
    source_message_ids: list[str] = Field(min_length=1,max_length=10)
    evidence: str = Field(min_length=1,max_length=1000)
    basis: str = Field(pattern='^(text|image)$')

class BagPlacement(StrictModel):
    object_label: str = Field(max_length=160)
    edge: Literal['top','bottom','left','right']
    reference: Literal['finished_mouth','finished_edge','raw_fabric_edge','unknown']
    offset_cm: float | None = Field(default=None, ge=0, le=10000)
    mouth_allowance_cm: float | None = Field(default=None, ge=0, le=1000)
    source_message_ids: list[str] = Field(min_length=1,max_length=10)
    evidence: str = Field(min_length=1,max_length=1000)
    basis: Literal['text','image']

class BagPanel(StrictModel):
    part: Literal['front','back','gusset','bottom','handles','unknown']
    print_required: bool | None = None
    width_cm: float | None = Field(default=None,gt=0,le=10000)
    height_cm: float | None = Field(default=None,gt=0,le=10000)
    source_message_ids: list[str] = Field(min_length=1,max_length=10)
    artwork_source_message_ids: list[str] = Field(default_factory=list,max_length=10)
    placements: list[BagPlacement] = Field(default_factory=list,max_length=12)

BAG_PROMPT='''Nếu là in túi, thêm bag_facts, mỗi field/value có source_message_ids và evidence.
Các field được phép: '''+', '.join(sorted(FIELDS))+'''.
Đơn vị kích thước cm, value số thập phân khi rõ; boolean dùng true/false; chưa rõ bỏ field.
Đọc phiếu lệnh + maket + file như các nguồn khác nhau; source_artwork/maket/slip là mô tả nguồn, không bịa đường dẫn.
fabric_scope chỉ single_face hoặc two_faces hoặc unknown; split_axis height/width/unknown.
Không suy single_face từ print_faces=1: số mặt in không cho biết vải là 1 mảnh hay trải 2 mặt.
split_confirmed=true chỉ khi nguồn xác nhận chia đôi kích thước vải và biết trục chia.
Đáy/hông có tồn tại KHÔNG có nghĩa phải in đáy/hông. Tách front/back/gusset/bottom/handle_print.
Miệng túi +5cm: nếu cữ trên maket tính từ miệng thành phẩm thì cộng 5 vào cữ trên theo mép vải; không cộng lần nữa vào kích thước vải đã cho.
top_offset_reference dùng finished_mouth hoặc raw_fabric_edge hoặc unknown. Không cộng nếu cữ đã từ mép vải.
Quai cần mã mẫu quai khách cung cấp; chỉ đặt handle_roll_width_cm=160 theo quy tắc chủ xưởng khi xác định có in quai, giữ phần thiếu mã/quy cách để người kiểm tra.
File PDF/AI có sẵn không đồng nghĩa đã đúng artboard. Không tự sửa, chia đôi, co giãn, mirror hay suy phần cộng đường may/co vải.
bag_panels tách front/back/gusset/bottom/handles; mỗi panel có file nguồn và placements riêng cho từng logo/chữ/ảnh. source_message_ids của panel phải có nguồn thật. Kích thước chưa biết để null. Không tự quy đổi mép thành phẩm sang mép vải trừ cữ top finished_mouth + mouth_allowance đã rõ.
Thông tin đọc từ ảnh có basis=image và evidence mô tả ô/nhãn; luôn chờ nhân viên xác minh. Có mâu thuẫn thì ghi conflicts, không tự chọn.
'''

def bag_plan(facts, panels=None):
    panels=panels or []
    values={};conflicts=[]
    for fact in facts:
        if fact.field not in FIELDS:raise ValueError('Unknown bag field')
        if fact.field in values and values[fact.field]!=fact.value:conflicts.append('Mâu thuẫn '+fact.field)
        values[fact.field]=fact.value
    derived={};missing=[]
    def num(field):
        try:
            n=Decimal(values[field])
            return n if n.is_finite() and n>=0 else None
        except (KeyError,InvalidOperation):return None
    if not facts and not panels:return None
    for f in ['fabric_height_cm','fabric_width_cm','fabric_scope','has_bottom','print_faces','source_artwork','source_maket','source_slip']:
        if not values.get(f) or values[f]=='unknown':missing.append(f)
    h,w=num('fabric_height_cm'),num('fabric_width_cm')
    if h and w and not conflicts:
        if values.get('fabric_scope')=='single_face':derived['artboard_candidate_cm']={'height':float(h),'width':float(w),'rule':'keep_explicit_single_face_fabric_size'}
        elif values.get('fabric_scope')=='two_faces':
            if values.get('split_confirmed')=='true' and values.get('split_axis') in ('height','width'):
                axis=values['split_axis'];derived['artboard_candidate_cm']={'height':float(h/2 if axis=='height' else h),'width':float(w/2 if axis=='width' else w),'rule':'explicit_two_faces_split_'+axis}
            else:missing.append('Xác nhận có chia đôi vải và chia theo chiều nào; không suy từ số mặt in')
    offset,allowance=num('top_offset_finished_cm'),num('mouth_allowance_cm')
    if offset is not None and not conflicts:
        if values.get('top_offset_reference')=='finished_mouth' and allowance is not None:
            derived['top_offset_raw_cm']=float(offset+allowance)
            derived['top_offset_formula']=f'{offset} + {allowance} (miệng túi)'
        elif values.get('top_offset_reference')=='raw_fabric_edge':derived['top_offset_raw_cm']=float(offset)
        else:missing.append('Mốc đo cữ trên và phần cộng miệng túi')
    if values.get('handle_print')=='true':
        derived['handle_artboard_width_cm']=160
        if not values.get('handle_template_code'):missing.append('Mã mẫu quai khách chỉ định và file tương ứng')
        missing.append('Xác nhận số quai, chiều dài/rộng, hướng xoay và cách lặp theo mẫu quai')
    for part in ['front','back','gusset','bottom']:
        if values.get(part+'_print')=='true':missing.append('Kiểm tra file, kích thước và cữ riêng cho '+part)
    panel_data=[]
    for panel in panels:
        data=panel.model_dump()
        for place in data['placements']:
            place['proposed_raw_offset_cm']=None
            if place['reference']=='raw_fabric_edge':place['proposed_raw_offset_cm']=place['offset_cm']
            elif place['edge']=='top' and place['reference']=='finished_mouth' and place['offset_cm'] is not None and place['mouth_allowance_cm'] is not None:
                place['proposed_raw_offset_cm']=float(Decimal(str(place['offset_cm']))+Decimal(str(place['mouth_allowance_cm'])))
            place['verified']=False
        data['ready_for_execution']=False
        panel_data.append(data)
    return {'profile':'bag-print-v1','panels':panel_data,'facts':[f.model_dump() for f in facts],'proposed_geometry':derived,
            'missing_or_review':list(dict.fromkeys(missing+conflicts)), 'ready_for_execution':False,
            'warning':'Hình học đề xuất từ dữ liệu chưa duyệt; không phải file in đã tạo.'}
