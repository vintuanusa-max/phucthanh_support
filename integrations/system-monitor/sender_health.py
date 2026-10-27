"""Read-only sender health. Never replay or expose message bodies."""
import json,sqlite3,time
from contextlib import closing

def sender_status(home,alive,now=None):
 now=time.time() if now is None else now
 out=dict(state='bad',label='Cần kiểm tra',detail='',action='',issues=[],updated_at=0)
 try:
  data=json.loads((home/'status.json').read_text(encoding='utf-8-sig'))
  out['updated_at']=float(data.get('updated_at',0));age=max(0,now-out['updated_at'])
  pre=data.get('last_preflight') or {};out['attempt']=pre.get('attempt',0)
  with closing(sqlite3.connect((home/'sender.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
   for key,raw in db.execute('SELECT id,result FROM attempts'):
    r=json.loads(raw)
    if r.get('state') in ('blocked','failed','uncertain'):
     out['issues'].append(dict(id=key,state=r['state'],detail=str(r.get('detail',''))[:300]))
  out['issue_count']=len(out['issues']);out['issues']=out['issues'][-10:]
  restart=home/'watchdog-last-start.txt'
  restarting=restart.exists() and 0 <= now-restart.stat().st_mtime < 90
  if (home/'halt.flag').exists() or data.get('phase')=='halted':
   out.update(label='Bị khóa — cần kiểm tra',detail='Bộ gửi đã khóa an toàn; không tự khởi động lại.',action='Đối chiếu kết quả gửi và Inspector trước khi mở khóa. Không gửi lại tin chưa rõ kết quả.')
  elif (home/'stop.flag').exists():
   out.update(state='warn',label='Đã dừng chủ động',detail='Có stop.flag; giám sát tôn trọng yêu cầu dừng.',action='Chỉ mở lại khi người vận hành cho phép; giữ nguyên nhật ký gửi.')
  elif not alive and restarting:
   out.update(state='retry',label='Đang tự phục hồi',detail='Giám sát vừa yêu cầu khởi động lại bộ gửi; đang chờ heartbeat.',action='Nếu quá 90 giây vẫn chưa chạy, kiểm tra stderr.log. Không tự gửi lại tin chưa rõ kết quả.')
  elif not alive or age>90:
   out.update(label='Cần kiểm tra',detail='Không thấy tiến trình hoặc heartbeat quá 90 giây.',action='Giám sát mỗi phút chỉ mở lại tiến trình đã dừng (giãn cách 3 phút). Tiến trình còn sống nhưng treo cần kiểm tra; không cưỡng bức gửi lại.')
  elif out['issue_count']:
   out.update(state='warn',detail=f"Có {out['issue_count']} tin bị chặn hoặc chưa rõ kết quả.",action='Đối chiếu lịch sử Zalo trước khi xử lý; không tự gửi lại các tin này.')
  elif data.get('error'):
   out.update(state='warn',detail='Lỗi kết nối: '+str(data['error'])[:150],action='Kiểm tra Hub/mạng; bộ gửi sẽ thử kết nối lại.')
  elif pre.get('state')=='blocked' and now-float(pre.get('at',0))<35 and pre.get('attempt',3)<3:
   out.update(state='retry',label='Đang tự phục hồi',detail=f"Đang kiểm tra trước gửi, lượt {pre.get('attempt')}/3: {pre.get('detail','')}",action='Chờ tối đa 3 lượt; chưa gọi gửi tin.')
  else:
   out.update(state='ok',label='Đang chạy',detail='Bộ gửi hoạt động; không có tin lỗi cần xử lý.',action='Tự nhận phiên bản/bundle mới. API không tương thích sẽ dừng để kiểm tra; không tự gửi lại tin chưa rõ kết quả.')
 except Exception:
  out.update(detail='Không đọc được trạng thái hoặc nhật ký bộ gửi.',action='Kiểm tra bộ gửi và quyền đọc nhật ký; không thao tác gửi lại.')
 return out
