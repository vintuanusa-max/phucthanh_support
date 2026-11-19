"""Text quantity orders keep media as evidence, never infer items from pixels."""
import re
from hub.order_signals import normalized
POLICY="Khách đã ghi số lượng bằng chữ: không đọc ảnh để chia mẫu/màu hay nhân số lượng. Ảnh/file chỉ làm nguồn, giữ message IDs của ảnh/file cùng yêu cầu. Một câu tổng lượng không ghi mỗi loại/mỗi màu => một dòng duy nhất đúng tổng lượng. Chỉ tách dòng theo lời khách ghi rõ. Không thiếu tên mẫu/mã mà chặn; để mã null và tên mô tả trung tính."
def total_quantity_request(messages):
 # Routing only: AI must reconcile total/additional/delivery mentions.
 if not any(m.get('images') or m.get('assets') for m in messages):return False
 for m in messages:
  if m.get('origin')!='customer' or m.get('revision') or m.get('recalled'):continue
  t=normalized(m.get('text',''))
  if re.search(r'\b(?:khong|ko|chua|dung)\s+(?:in|lam|dat|ra)|\b(?:huy|bao gia|hoi gia)\b',t):continue
  if re.search(r'\b(?:tc|tong(?: cong)?)\s*[:：]?\s*[1-9][0-9]*\s*(?:cai|ao|tam|bo|met|m)\b',t) and re.search(r'\b(?:in|dat|ra pet|ra phim)\b',t):return True
 return False

def text_quantity(messages):
 if total_quantity_request(messages):return True
 for m in messages:
  if m.get('origin','customer')!='customer' or m.get('direction','incoming')!='incoming' or m.get('recalled'):continue
  t=normalized(m.get('text','')).replace('.','')
  if re.search(r'\b(?:khong|ko|chua|dung)\s+(?:in|lam|dat)|\b(?:huy|bao gia|hoi gia)\b',t):continue
  t=re.sub(r'\b(?:ngang|cao|rong|dai|kho)\s*[0-9]+(?:\s*(?:cm|mm|m))?','',t)
  if re.search(r'\b(?:in|lam|dat|sl|so luong)\b[^\n!?]{0,65}?\b[1-9][0-9]*(?:\s*(?:cai|pc|pcs|met|m|tam|chiec|bo))?\b',t):return True
 return False
