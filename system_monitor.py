# -*- coding: utf-8 -*-
import os
import sys
import time
import requests
import subprocess
from datetime import datetime

# Cấu hình danh sách các máy chủ quản lý (Manager APIs)
# 1. Zalo Bot Manager (Chạy cục bộ hoặc trên máy chủ Chat)
ZALO_MANAGER_URL = "http://localhost:9000"

# 2. Design Monitor Manager (Watchdog 'By-Hands', Port 9001 local)
DESIGN_MANAGER_URL = "http://localhost:9001"

# 3. RIP Bot Manager (Chạy trên máy RIP in ấn 192.168.1.96, Port 9000)
RIP_MANAGER_URL = "http://192.168.1.96:9000"

# Thư mục giám sát W:\ để kiểm tra hoạt động thiết kế
WATCH_DIR = "W:\\"

def check_system_idle():
    """
    Kiểm tra xem hệ thống có đang rảnh rỗi (idle) để reset hay không.
    Trả về True nếu rảnh, False nếu đang bận làm việc.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Đang kiểm tra trạng thái hoạt động của hệ thống...")
    
    # 1. Kiểm tra xem có file nào mới được tạo/ghi đè trong thư mục W:\ trong vòng 3 phút qua không
    if os.path.exists(WATCH_DIR):
        try:
            now = time.time()
            for root, dirs, files in os.walk(WATCH_DIR):
                for f in files:
                    fpath = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(fpath)
                        if now - mtime < 180: # Có file vừa chỉnh sửa/tạo mới dưới 3 phút
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Hệ thống đang bận: Phát hiện file thiết kế đang hoạt động: {f}")
                            return False
                    except:
                        pass
        except Exception as e:
            print(f"[QUẢN ĐỐC WARNING] Lỗi khi quét kiểm tra thư mục thiết kế: {e}")
            
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Hệ thống đang rảnh rỗi (Idle). Sẵn sàng reset.")
    return True

def reset_bot(manager_url, name):
    """Gửi yêu cầu stop và start tới Manager tương ứng"""
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Đang dừng {name}...")
        requests.post(f"{manager_url}/manager/stop", timeout=15)
        time.sleep(3)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Đang khởi động lại {name}...")
        res = requests.post(f"{manager_url}/manager/start", timeout=15)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Kết quả {name}: {res.json()}")
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC ERROR] Không thể reset {name} ({manager_url}): {e}")
        return False

def force_kill_local_zombies():
    """Tắt cưỡng bức các tiến trình kẹt ngầm trên máy cục bộ để làm sạch RAM"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Đang dọn dẹp các tiến trình bị kẹt ngầm (Chrome, Adobe)...")
    try:
        # Tìm và diệt các tiến trình Chrome chạy trên cổng debug 9222 và 9223
        for port in (9222, 9223):
            try:
                ns_out = subprocess.check_output("netstat -ano", shell=True).decode()
                for line in ns_out.splitlines():
                    if f":{port}" in line:
                        parts = line.strip().split()
                        if parts:
                            pid = parts[-1]
                            if pid.isdigit() and pid != '0':
                                os.system(f"taskkill /f /t /pid {pid} >nul 2>&1")
            except:
                pass
        
        os.system("taskkill /f /im Illustrator.exe >nul 2>&1")
        os.system("taskkill /f /im Photoshop.exe >nul 2>&1")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Đã dọn dẹp xong RAM và tiến trình.")
    except Exception as e:
        print(f"[QUẢN ĐỐC ERROR] Lỗi dọn dẹp tiến trình: {e}")

def get_last_reset_time():
    """Đọc thời gian reset cuối cùng từ file, trả về float. Nếu lỗi trả về 0.0"""
    filepath = os.path.join(os.path.dirname(__file__), "last_reset.txt")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return float(f.read().strip())
        except:
            pass
    return 0.0

def update_last_reset_time():
    """Cập nhật thời gian reset hiện tại vào file"""
    try:
        filepath = os.path.join(os.path.dirname(__file__), "last_reset.txt")
        with open(filepath, "w") as f:
            f.write(str(time.time()))
    except:
        pass

def main_loop():
    print("=================================================================")
    print(f"    [QUẢN ĐỐC HỆ THỐNG] KHỞI ĐỘNG DAEMON RESET MỖI 3 GIỜ")
    print(f"    Thời gian khởi chạy: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=================================================================")
    
    interval = 3 * 60 * 60 # 3 tiếng (10800 giây)
    
    # Khởi tạo mốc thời gian reset ban đầu nếu chưa có file
    if get_last_reset_time() == 0.0:
        update_last_reset_time()
        
    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Bắt đầu chu kỳ theo dõi 3 tiếng...")
        
        # Kiểm tra định kỳ mỗi 10 giây thay vì sleep liền 3 tiếng
        while True:
            last_reset = get_last_reset_time()
            now = time.time()
            elapsed = now - last_reset
            
            if elapsed >= interval:
                # Đã quá 3 tiếng kể từ lần reset cuối cùng
                break
                
            # Đợi thêm 10 giây rồi kiểm tra tiếp
            time.sleep(10)
        
        # Kiểm tra trạng thái rảnh rỗi trước khi reset
        while not check_system_idle():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Hệ thống đang bận thiết kế. Hoãn quy trình reset 10 phút...")
            time.sleep(600) # Đợi 10 phút rồi thử lại
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] >>> BẮT ĐẦU TIẾN TRÌNH TỰ ĐỘNG RESET TOÀN BỘ HỆ THỐNG <<<")
        
        # 1. Reset Design Monitor (Watchdog By-Hands)
        reset_bot(DESIGN_MANAGER_URL, "Design Monitor (Watchdog)")
        
        # 2. Reset RIP Bot (192.168.1.96)
        reset_bot(RIP_MANAGER_URL, "RIP Bot")
        
        # 3. Reset Zalo Bot và làm sạch tiến trình Chrome cục bộ
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Đang dừng Zalo Bot...")
            requests.post(f"{ZALO_MANAGER_URL}/manager/stop", timeout=15)
            time.sleep(3)
            
            # Làm sạch Chrome và Adobe bị kẹt
            force_kill_local_zombies()
            time.sleep(2)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Đang mở lại Zalo Bot...")
            res = requests.post(f"{ZALO_MANAGER_URL}/manager/start", timeout=15)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] Kết quả Zalo Bot: {res.json()}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC ERROR] Lỗi khi reset Zalo Bot: {e}")
            
        # Cập nhật mốc thời gian reset mới sau khi đã reset thành công
        update_last_reset_time()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [QUẢN ĐỐC] >>> QUY TRÌNH RESET TOÀN BỘ HỆ THỐNG HOÀN TẤT <<<")

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n[QUẢN ĐỐC] Đã tắt luồng quản đốc hệ thống.")
