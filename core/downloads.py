"""Tải file từ link Google Drive / link chia sẻ khác về ổ W:."""
import os
import re

import gdown

from core.integrations import forward_to_n8n


def background_download_drive(customer_name, link, save_dir):
    try:
        os.makedirs(save_dir, exist_ok=True)
        if "/folders/" in link:
            folder_id = link.split("/folders/")[1].split("?")[0].split("/")[0]
            gdown.download_folder(id=folder_id, output=save_dir, quiet=True)
            msg_type = "DRIVE_FOLDER"
        elif "/file/d/" in link:
            file_id = link.split("/file/d/")[1].split("/")[0]
            output_path = os.path.join(save_dir, f"drive_{file_id}")
            gdown.download(id=file_id, output=output_path, quiet=True, fuzzy=True)
            msg_type = "DRIVE_FILE"
        else: return
        forward_to_n8n(customer_name, msg_type, link, [save_dir])
    except: pass


def download_link_via_playwright(link, save_dir):
    """Sử dụng Playwright kết nối vào Chrome qua CDP để tự động click nút tải trên trang QNAP, zCloud..."""
    from playwright.sync_api import sync_playwright
    import time
    print(f"🌐 [Playwright Downloader] Bắt đầu tải link: {link}")
    try:
        with sync_playwright() as p:
            # Kết nối vào Chrome đang mở sẵn qua CDP
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.new_page()
            try:
                # Đi tới link và đợi 5s cho trang load động hoàn tất
                page.goto(link, timeout=60000, wait_until="load")
                time.sleep(5)
                # Các bộ chọn thông minh cho nút download
                selectors = [
                    # QNAP specific
                    "#download-btn",
                    ".q-btn-download",
                    "button[title*='Download']",
                    "button[title*='Tải xuống']",
                    "a[title*='Download']",
                    "a[title*='Tải xuống']",
                    # zCloud / Zalo Cloud specific
                    "[class*='btn-download']",
                    "[class*='download-btn']",
                    # General selectors
                    "a[href*='download']",
                    "button[class*='download']",
                    "a[class*='download']",
                    "i[class*='download']",
                    "div[class*='download']",
                    "xpath=//button[contains(translate(., 'DOWNLOAD', 'download'), 'download')]",
                    "xpath=//a[contains(translate(., 'DOWNLOAD', 'download'), 'download')]",
                    "xpath=//button[contains(., 'Tải xuống') or contains(., 'Tải về')]",
                    "xpath=//a[contains(., 'Tải xuống') or contains(., 'Tải về')]"
                ]
                # Đợi sự kiện download
                download_promise = page.wait_for_event("download", timeout=25000)
                clicked = False
                for sel in selectors:
                    try:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=1000):
                            btn.click(timeout=3000)
                            clicked = True
                            break
                    except:
                        pass
                if not clicked:
                    try:
                        # Fallback: tìm theo văn bản hiển thị
                        page.get_by_role("button", name=re.compile("download|tải xuống|tải về", re.IGNORECASE)).first.click(timeout=3000)
                        clicked = True
                    except:
                        pass
                if clicked:
                    download = download_promise.value
                    filename = download.suggested_filename
                    dest_path = os.path.join(save_dir, filename)
                    download.save_as(dest_path)
                    print(f"✅ [Playwright Downloader] Tải thành công: {filename}")
                    return dest_path
                else:
                    print(f"❌ [Playwright Downloader] Không tìm thấy nút Download cho: {link}")
            finally:
                try: page.close()
                except: pass
    except Exception as e:
        print(f"❌ [Playwright Downloader] Lỗi: {e}")
    return None


def background_download_general_link(customer_name, link, save_dir):
    try:
        os.makedirs(save_dir, exist_ok=True)
        filepath = download_link_via_playwright(link, save_dir)
        if filepath and os.path.exists(filepath):
            forward_to_n8n(customer_name, "LINK_FILE", link, [filepath])
    except Exception as e:
        print(f"⚠️ [Link Thread] Lỗi: {e}")
