"""Conservative intent routing. Never infers quantities or creates orders."""
import json,re,unicodedata
HISTORY={'conversation','approval','design_change','quote'}
def norm(s):
 return ''.join(c for c in unicodedata.normalize('NFD',s.lower().replace('đ','d')) if not unicodedata.combining(c))
def classify(messages,payload=None,result=None):
 p=payload or {};r=result or {}
 if p.get('submitted_payload') or p.get('request_id') or p.get('orders') or r.get('orders'):
  return 'order','Đã có đề xuất/giao dịch đơn; giữ đối chiếu ERP'
 text='\n'.join(norm(m.get('text','')) for m in messages)
 media=any(m.get('images') or m.get('assets') for m in messages)
 # A positive request wins over delivery, revision or approval elsewhere in the same batch.
 quantity=bool(re.search(r'\b(?:sl|so luong)\s*[:=]?\s*\d|\b\d+(?:[.,]\d+)?\s*(?:cai|c\b|tam|mieng|non|tui|met|bo\b)',text))
 request=bool(re.search(r'\b(?:in (?:them|giup|dum|cho)|ra pet|dat (?:them|hang)|lam them|san xuat|sx lai)\b',text))
 if request and (quantity or re.search(r'\bra pet\s+\d',text)):
  return 'order','Có yêu cầu in/đặt thêm kèm số lượng; cần đối chiếu nguồn và ERP'
 if re.search(r'\b(?:sl|so luong)\s*[:=]?\s*\d',text) or (quantity and re.search(r'\bin\b',text) and not re.search(r'\b(?:xong chua|bao nhieu tien|nhan duoc chua)\b',text)):
  return 'order','Có số lượng và thông tin in; chưa được coi là trao đổi thông thường'
 if re.search(r'\b(?:in them|dat them|lam them|in bu)\b',text) and not re.search(r'\b(?:ky sau|lan sau|hom sau)\b',text):
  return 'order','Có yêu cầu đặt thêm/in bù nhưng cần làm rõ số lượng hoặc mẫu'
 if media and not (r.get('agent_state')=='completed'):
  return 'unknown','Nguồn ảnh/file chưa có kết luận; giữ lại để đọc, không tự ẩn'
 if re.search(r'\b(?:chinh|sua)\b.*\b(?:mau|cu|cao|ngang|sang)|\b(?:mau cam|mau den|mau xam|mau no|giong mau|cao\s+\d.*cm|cu in.*cm)\b',text):
  return 'design_change','Yêu cầu chỉnh màu/kích thước/mẫu; không phải đơn mới'
 if re.search(r'\b(?:ok in|cho in|chot|duyet|dung roi|chuan cu|cu in.*ok)\b',text) or re.fullmatch(r'[\s.!@\w]*\bok\b[\s.!]*',text.strip()) and len(text)<30:
  return 'approval','Trao đổi xác nhận/duyệt; cần ngữ cảnh ở luồng duyệt in, không tự tạo đơn'
 if re.search(r'\b(?:bao gia|gia bao nhieu|xhd|xuat hoa don)\b',text):
  return 'quote','Hỏi giá/hóa đơn; không phải đặt hàng mới'
 if re.search(r'\b(?:cam on|ra lay|xe lay|dat xe|book xe|phi xe|lalamove|giao thanh cong|nhan duoc chua|xong chua|co mat in|hang.*chua|ky sau in bu)\b',text) or re.fullmatch(r'(?:da|vang|a|em|anh|chi|nha|nhe|oi|\s|[.!])+',text.strip()):
  return 'conversation','Trao đổi tiến độ/giao nhận/xã giao; chưa có yêu cầu đơn mới'
 return 'unknown','Chưa đủ căn cứ phân loại; giữ lại để kiểm tra, không tự bỏ nguồn'
def evidence(db,row,p):
 out=[]
 for mid in p.get('messages',[]):
  r=db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND (message_id=? OR id=?) ORDER BY revision DESC LIMIT 1',(row['account'],row['thread_id'],str(mid),str(mid))).fetchone()
  if r:out.append(json.loads(r[0]))
 return out

def presentation(db,row,p,res):
 state=row['state']
 if state in ('created','duplicate','amended'):return 'done','Đã xử lý ERP'
 if state in ('superseded','archived'):return 'history','Hồ sơ đã thay thế/đóng'
 if state in ('sending','uncertain'):return 'review' if state=='uncertain' else 'waiting','Đang/chưa rõ kết quả ERP; không tự gửi lại'
 if db.execute('SELECT 1 FROM agent_proposals WHERE run_id=? LIMIT 1',(row['id'],)).fetchone():return ('review' if state in ('review','failed','error') else 'waiting'),'Có đề xuất đơn; cần đối chiếu trước khi kết luận'
 category,reason=classify(evidence(db,row,p),p,res)
 if category in HISTORY:return 'history',reason
 if state=='ignored':return 'history','Đã đọc; không tạo đơn'
 return ('review' if state in ('review','failed','error') else 'waiting'),reason
