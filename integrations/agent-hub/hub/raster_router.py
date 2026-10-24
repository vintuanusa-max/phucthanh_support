"""Cost-conscious routing; no generative reconstruction without explicit consent."""
import base64,io,json,math
from pathlib import Path
from PIL import Image
from hub.replicate_redraw import redraw

def route(pet,raw,consent,folder,side,face):
    folder=Path(folder);folder.mkdir(exist_ok=True)
    parts=[{'inline_data':{'mime_type':'image/png','data':base64.b64encode(raw).decode()}},{'text':json.dumps(face,ensure_ascii=False)}]
    props={'action':{'type':'string','enum':['keep','upscale','redraw','review']},'reason':{'type':'string'},'lines':{'type':'array','items':{'type':'string'}},'legible':{'type':'boolean'},'background':{'type':'string','enum':['white','alpha','complex']},'white_artwork':{'type':'boolean'},'blocking_issues':{'type':'array','items':{'type':'string'}}}
    plan=pet.ask('Chọn cách ít tốn phí nhất để xử lý LOGO RIÊNG đã đối chiếu maket. keep nếu đủ nét ở kích thước in; upscale chỉ khi ảnh sạch chỉ thiếu pixel; redraw cho logo/chữ/hình có nhiễu, xước, méo nét cần phục dựng, kể cả khi vẫn đọc được chữ; review nếu chữ/số không đọc chắc, mất nét hoặc lẫn sản phẩm. Không sáng tạo mới. Đọc nguyên văn từng dòng. Phân biệt chi tiết trắng thuộc artwork và nền. Tách nền không phải vẽ lại. Không cần gọi model nếu ảnh đủ nét. blocking_issues chỉ là vấn đề KHÔNG THỂ xử lý theo action đã chọn, ví dụ sai nguồn/chữ không rõ. Răng cưa/thiếu độ phân giải xử lý được bằng upscale không phải blocking_issues.',parts,{'type':'object','properties':props,'required':list(props)})
    (folder/(side+'.route.json')).write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
    if plan['blocking_issues'] or not plan['legible'] or plan['action']=='review':raise ValueError('Router cần nhân viên: '+plan['reason'])
    if plan['action'] in ('upscale','redraw') and not consent:raise ValueError('Cần nhân viên hỏi file và khách xác nhận không có trước phục dựng')
    # Segmentation is permitted without reconstruction consent, but uses same durable receipt mechanism.
    permission=consent or {'question_message_id':'segmentation-only','answer_message_id':'existing-artwork','method':'non-generative-background-removal'}
    def uri(data):return 'data:image/png;base64,'+base64.b64encode(data).decode()
    result=raw
    if plan['action']=='upscale':
        result=redraw(pet,result,permission,folder,side+'_upscale',model='nightmareai/real-esrgan',parameters={'image':uri(result),'scale':2,'face_enhance':False})
    elif plan['action']=='redraw':
        from hub.openai_redraw import redraw as openai_redraw
        result=openai_redraw(pet,result,consent,folder,side,plan['lines'])
        face['background']='alpha';face['white_artwork']=plan['white_artwork'];face['router']=plan
        face['redraw_provider']='openai/gpt-image-2.5-sunburst'
        face['openai_usage']=json.loads((folder/(side+'.openai.json')).read_text()).get('usage',{})
        return result
    if plan['background']=='complex' or (plan['background']=='white' and plan['white_artwork']):
        result=redraw(pet,result,permission,folder,side+'_background',model='men1scus/birefnet',parameters={'image':uri(result)})
        with Image.open(io.BytesIO(result)) as im:
            if 'A' not in im.getbands() or im.getchannel('A').getextrema()[0]==255:raise ValueError('BiRefNet chưa tạo nền trong suốt')
        face['background']='alpha'
    else:face['background']=plan['background']
    face['white_artwork']=plan['white_artwork'];face['router']=plan
    return result

