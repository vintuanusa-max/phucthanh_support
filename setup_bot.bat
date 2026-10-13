@echo off
title SETUP ZALO BOT
echo Dang cai dat thu vien Python...
py -m pip install -r requirements.txt
py -m pip install tf-playwright-stealth google-generativeai pydantic gspread oauth2client gdown requests
echo.
echo Dang cai dat trinh duyet cho Playwright...
py -m playwright install chromium
echo.
echo Dang tai wppconnect-wa.js...
py -c "import urllib.request; urllib.request.urlretrieve('https://github.com/wppconnect-team/wa-js/releases/latest/download/wppconnect-wa.js', 'wppconnect-wa.js')"
echo.
echo Cai dat hoan tat! Nhan phim bat ky de thoat.
pause
