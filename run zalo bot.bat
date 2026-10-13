@echo off
title ZALO_BOT_PHUC_THANH
:: Cấu hình UTF-8 để hiển thị emoji trên console Windows
chcp 65001 > nul
set PYTHONUTF8=1
:: Tự động diệt cổng 8000 trước khi chạy
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /f /pid %%a
:: Chạy bot
py -m uvicorn main:app --host 0.0.0.0 --port 8000
pause