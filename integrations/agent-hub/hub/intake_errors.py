"""Bounded diagnostics without credentials, request bodies or image data."""
import re
import httpx
from pydantic import ValidationError

def detail(exc):
    if isinstance(exc,ValidationError):
        return 'Schema AI: '+ '; '.join('.'.join(map(str,e['loc']))+': '+e['type'] for e in exc.errors(include_input=False)[:6])
    if isinstance(exc,httpx.HTTPStatusError):return 'API HTTP '+str(exc.response.status_code)+'; kiểm tra dịch vụ/quota, chưa ghi ERP'
    if isinstance(exc,httpx.TimeoutException):return 'API hết thời gian chờ; giữ nguồn, kiểm tra kết nối trước khi chạy lại'
    if not isinstance(exc,ValueError):return type(exc).__name__+'; kiểm tra log nội bộ'
    text=str(exc)
    text=re.sub(r'(?i)(bearer\s+\S+|sk-[\w-]+|r8_[\w]+|AIza[\w-]+|https?://\S+)','[đã ẩn]',text)
    text=re.sub(r'(?i)(token|api.?key|password|secret)\s*[:=]\s*\S+',r'\1=[đã ẩn]',text)
    return 'ValueError: '+text[:400]
