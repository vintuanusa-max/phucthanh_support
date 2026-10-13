from playwright.sync_api import sync_playwright
import time

print("Đang khởi động trình duyệt...")
with sync_playwright() as p:
    # Khởi tạo context và chỉ định nơi lưu session
    context = p.chromium.launch_persistent_context(
        user_data_dir="./zalo_session_data",
        headless=False, # Mở giao diện để anh nhìn thấy mã QR
        args=["--disable-blink-features=AutomationControlled"] # Ẩn danh cơ bản
    )
    page = context.pages[0]
    
    page.goto("https://chat.zalo.me")
    print("Trình duyệt đã mở! Vui lòng dùng điện thoại quét mã QR Zalo...")
    
    # Cho anh 60 giây để thong thả quét mã QR và đợi Zalo load tin nhắn cũ
    time.sleep(60) 
    
    context.close()
    print("Đã tắt trình duyệt và lưu xong phiên đăng nhập!")