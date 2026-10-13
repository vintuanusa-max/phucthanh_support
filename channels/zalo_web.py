"""Kênh Zalo cá nhân qua Zalo Web (Chrome CDP cổng 9222) + Playwright."""
import base64
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid

from playwright.sync_api import sync_playwright

import communication_policy
from core import runtime as rt
from core.downloads import background_download_drive, background_download_general_link
from erp_bridge import exact_group
from core.history import load_history, save_history
from core.messages import IncomingMessage, publish
from core.runtime import (_send_worker_busy, _tls, _zalo_scan_event, report_status_to_nas, send_queue,
                          telegram_alert, zalo_lock)
from core.settings import (_is_design_file, _is_zalo_internal, get_zalo_internal, get_zalo_skip_groups,
                           is_skip_group, load_config, zalo_allowed)
from core.text_rules import (_has_zalo_internal_mention, _is_order_relevant, build_search_keyword,
                             generate_stable_id, group_to_folder, name_match)

NAME = "zalo"


def _get_zalo_page():
    """Lấy Zalo page với kết nối bền vững theo từng thread."""
    try:
        if getattr(_tls, 'zalo_browser', None):
            ctx = _tls.zalo_browser.contexts[0]
            page = next((p for p in ctx.pages if "chat.zalo.me" in p.url), None)
            if page and not page.is_closed():
                return page
    except:
        _tls.zalo_browser = None
    if not getattr(_tls, 'pw', None):
        _tls.pw = sync_playwright().start()
    _tls.zalo_browser = _tls.pw.chromium.connect_over_cdp("http://localhost:9222", timeout=10000)
    return next((p for p in _tls.zalo_browser.contexts[0].pages if "chat.zalo.me" in p.url), None)


ZALO_ATTACHMENT_GUARD_JS = r"""(node, kind) => {
    const message = node.closest('[id^="bb_msg_id_"], [id^="msg-item-"], .msg-item, .chat-item')
        || (kind === 'image' && node.closest('.photo-message-v2, .card--group-photo'));
    if (node.closest('[class*="sticker"], [class*="emoji"], [class*="emoticon"], [class*="reaction"], [class*="avatar"], [data-type="sticker"], [data-z-element-type="sticker"]')) return false;
    if (!message || node.closest('.me, .card--me')) return false;
    for (let el = node; el; el = el.parentElement) {
        const marker = [el.className, el.id, el.getAttribute('data-z-element-type'),
            el.getAttribute('data-type'), el.getAttribute('src')].join(' ').toLowerCase();
        if (/sticker|emoji|emoticon|reaction|avatar/.test(marker)) return false;
        if (el === message) break;
    }
    if (kind === 'file') {
        if (node.closest('.file-message, .card--file, .msg-file')) return true;
        // Accept named file attachments in newer msg-item layouts, not generic labels.
        if (message.querySelector('[class*="sticker"], [data-z-element-type="sticker"], [data-type="sticker"]')) return false;
        const names = message.querySelectorAll('.file-name, .file-message__name, [data-z-element-type="file-name"]');
        return Array.from(names).some(el => {
            if (el.closest('.quote, .quote-content, .reply-preview, [class*="quote"]')) return false;
            const filename = (el.textContent || el.getAttribute('title') || '').trim();
            return /\.[a-z0-9]{1,10}$/i.test(filename);
        });
    }
    return node.tagName === 'IMG' && node.matches('img.zimg-el, img[data-z-element-type="image"], img[class*="picture"]')
        && node.clientWidth >= 80 && node.clientHeight >= 80;
}"""


def react_to_message_like(page, element_locator):
    """Thả tim/like tin nhắn bằng cách hover và click icon Thích."""
    # Vô hiệu hóa hoàn toàn để tránh lỗi chọn nhầm biểu cảm (như mặt khóc)
    return False


def scan_zalo_loop():
    cycle = 0
    while True:
        _zalo_scan_event.wait(timeout=120)  # Tự wakeup mỗi 2 phút nếu không có ai trigger
        _zalo_scan_event.clear()
        while rt.SYSTEM_STATUS == "PAUSED" or _send_worker_busy.is_set() or rt.screenshot_active > 0:
            time.sleep(5)
        cycle += 1
        print(f"🔄 [Zalo #{cycle}] Bắt đầu quét...")
        cycle_deadline = time.time() + 90
        zalo_page = None
        with zalo_lock:
            try:
                zalo_page = _get_zalo_page()
            except Exception as e:
                _tls.zalo_browser = None
                print(f"⚠️ [Zalo] Lỗi kết nối: {e}")
        if not zalo_page:
            print(f"⚠️ [Zalo #{cycle}] Không tìm thấy tab Zalo Web — bỏ qua chu kỳ này.")
            continue
        print(f"✅ [Zalo #{cycle}] Đã kết nối tab Zalo Web.")
        report_status_to_nas(True, f"Quét tin nhắn Zalo #{cycle}...")
        try:
            # --- ĐẢM BẢO THOÁT KHỎI NHÓM NẾU BỊ KẸT TỪ TRƯỚC ---
            try:
                zalo_page.bring_to_front()
                # 1. Bấm Back nếu kẹt ở giao diện hẹp
                zalo_page.evaluate("""() => {

                    let backBtn = document.querySelector('.fa-chevron-left, i[class*="chevron-left"], [icon*="back"], [icon*="Back"], .header-back, [class*="btn-back"]');

                    if (backBtn) backBtn.click();

                }""")
                time.sleep(0.3)
                # 2. Bấm Alt+1 để focus danh sách hội thoại
                zalo_page.locator("body").press("Alt+1", timeout=2000)
                time.sleep(0.3)
                # 3. Đóng hộp thoại rác (nếu có)
                zalo_page.locator("body").press("Escape", timeout=2000)
                time.sleep(0.3)
                # 4. Xóa ô tìm kiếm nếu bị kẹt từ trước
                try:
                    s_box = zalo_page.locator("#contact-search-input")
                    if s_box.is_visible(timeout=1000):
                        s_box.fill("")
                        time.sleep(0.3)
                except: pass
            except: pass
            try:
                sidebar = zalo_page.locator("#contact-list-inner")
                if sidebar.is_visible(timeout=1000): sidebar.evaluate("node => node.scrollTop = 0")
            except: pass
            js_get_unread = r"""
                (skipNames) => {
                    let items = Array.from(document.querySelectorAll('div.msg-item')).filter(el => {
                        if (el.id && el.id.startsWith('msg-item-')) return false;
                        if (el.closest('.chat-content, #messageViewContainer')) return false;
                        
                        let titleText = (el.innerText || "").split('\n')[0].trim().replace(/\s+/g, ' ').normalize('NFC');
                        if (skipNames && skipNames.includes(titleText)) return false;
                        
                        const t = (el.innerText || '').toLowerCase().replace(/ /g,' ');
                        if (t.includes('cloud') || t.includes('documents') || t.includes('truyền file')) return false;
                        return el.querySelector('.v-badge__badge, .v-badge, [class*="unread"], [class*="badge"], .red-dot') !== null;
                    });
                    return items.length > 0 ? items[0] : null;
                }
            """
            print(f"📊 [Zalo #{cycle}] Đang quét sidebar (hỗ trợ cuộn)...")
            visited_groups = set()
            active_group_name = None
            with zalo_lock:
                try:
                    active_header_el = zalo_page.locator(".header-title").first
                    if active_header_el.is_visible(timeout=1000):
                        raw_h = active_header_el.inner_text(timeout=1000)
                        active_group_name = unicodedata.normalize('NFC', raw_h.strip().split('\n')[0].strip())
                        active_group_name = re.sub(r'\s+', ' ', active_group_name)
                except: pass
            for scan_step in range(30):
                    if time.time() > cycle_deadline:
                        print(f"⚠️ [WATCHDOG] Chu kỳ quét vượt 90s, bỏ qua các nhóm còn lại.")
                        break
                    while _send_worker_busy.is_set() or rt.screenshot_active > 0:
                        time.sleep(1)
                        cycle_deadline += 1
                    with zalo_lock:
                        try:
                            is_active_scan = False
                            if scan_step == 0 and active_group_name:
                                if not is_skip_group(active_group_name, get_zalo_skip_groups()):
                                    group_name = active_group_name
                                    is_active_scan = True
                                    print(f"🖥️ [Zalo] Tự động quét phòng chat đang mở (Active): {group_name}")
                            if not is_active_scan:
                                target_item = zalo_page.evaluate_handle(js_get_unread, list(visited_groups))
                                try:
                                    is_null = target_item.evaluate("node => node === null")
                                except: is_null = True
                                if is_null:
                                    try:
                                        zalo_page.locator("#contact-list-inner").evaluate("node => node.scrollTop += 600")
                                        time.sleep(0.8)
                                        target_item = zalo_page.evaluate_handle(js_get_unread, list(visited_groups))
                                        is_null = target_item.evaluate("node => node === null")
                                    except: is_null = True
                                if is_null:
                                    break # Đã cuộn mà vẫn không có -> hết nhóm chưa đọc
                                # Đảm bảo đóng mọi lightbox/dialog còn sót trước khi click nhóm mới
                                try:
                                    zalo_page.locator("body").press("Escape")
                                    time.sleep(0.2)
                                except: pass
                                target_item.click(force=True, timeout=3000)
                                time.sleep(0.8)
                            time.sleep(0.8)
                            header = zalo_page.locator(".header-title").first
                            try:
                                raw_header = header.inner_text(timeout=2000)
                                group_name = unicodedata.normalize('NFC', raw_header.strip().split('\n')[0].strip())
                                group_name = re.sub(r'\s+', ' ', group_name)
                            except:
                                print(f"⚠️ [SCAN] Timeout đọc header, bỏ qua nhóm này.")
                                continue
                            visited_groups.add(group_name)
                            rt.erp_bridge.observe(group_name)
                            if re.search(r"my documents|cloud|truyền file", group_name, re.IGNORECASE):
                                continue
                            if is_skip_group(group_name, get_zalo_skip_groups()) or communication_policy.is_internal(load_config(), group_name):
                                continue
                            print(f"👉 Đang vào đọc: {group_name}")
                            # Chờ message container load xong cho nhóm mới
                            # (header cập nhật nhanh hơn nội dung chat — đọc ngay sẽ đọc nhầm nhóm cũ)
                            time.sleep(1.5)
                            history = load_history()
                            save_dir = f"W:\\{group_to_folder(group_name)}"
                            os.makedirs(save_dir, exist_ok=True)
                            check_today_js = r"""node => {
                                let container = document.querySelector('#messageViewContainer') || document.querySelector('.chat-content');
                                if (!container) return false;
                                let dateBlocks = Array.from(container.querySelectorAll('.block-date, div.block-date'));
                                let todayBlock = dateBlocks.find(b => 
                                    b.querySelector('[data-translate-text-arguments*="STR_TODAY"]') || 
                                    b.innerText.includes("Hôm nay") || 
                                    b.innerText.includes("Today")
                                );
                                if (!todayBlock) return false;
                                let pos = todayBlock.compareDocumentPosition(node);
                                return (pos & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
                            }"""
                            new_data = False
                            has_liked_group = False
                            c_files, c_texts = [], []
                            internal_members = get_zalo_internal()
                            # Build senderMap dùng chung cho file, ảnh, text
                            try:
                                sender_map = zalo_page.evaluate(r"""() => {

                                    let container = document.querySelector('#messageViewContainer') || document.querySelector('.chat-content');

                                    if (!container) return {};

                                    let todayBlock = Array.from(container.querySelectorAll('div.block-date')).find(b =>

                                        b.querySelector('[data-translate-text-arguments*="STR_TODAY"]')

                                    );

                                    if (!todayBlock) return {};

                                    let senderMap = {}, lastSender = 'Khách';

                                    for (let item of todayBlock.querySelectorAll('div.chat-item.flx')) {

                                        if (item.classList.contains('me')) continue;

                                        let nameEl = item.querySelector('.message-sender-name-content .truncate:not(.quote-name)');

                                        if (nameEl) {

                                            let txt = nameEl.innerText.replace(/ /g, ' ').trim();

                                            if (txt) lastSender = txt;

                                        }

                                        // Map TẤT CẢ bb_msg_id_ trong chat-item (batch upload có nhiều ảnh)

                                        for (let msgEl of item.querySelectorAll('[id^="bb_msg_id_"]')) {

                                            senderMap[msgEl.id] = lastSender;

                                        }

                                    }

                                    return senderMap;

                                }""")
                            except:
                                sender_map = {}
                            # 1. Quét File
                            btns = zalo_page.locator("[title='Lưu về máy'], [title='Tải xuống'], [data-translate-title='STR_DOWNLOAD'], [data-translate-title='STR_SAVE_TO_PC'], [icon*='download'], [icon*='Download'], i.fa-download, i[class*='download']").all()
                            print(f"[FileScan] {group_name}: {len(btns)} nut tai; kiem tra toi da 20 nut cuoi")
                            for btn in reversed(btns[-20:]):
                                try:
                                    if not btn.evaluate(ZALO_ATTACHMENT_GUARD_JS, "file"):
                                        print(f"[FileScan] {group_name}: bo qua nut tai - khong xac nhan duoc file hoac sticker/emoji")
                                        continue
                                    if btn.evaluate("node => node.closest('.me, .card--me') !== null"): continue
                                    if not btn.evaluate(check_today_js): continue
                                    raw_id = btn.evaluate("node => { let m = node.closest('[id^=\"bb_msg_id_\"]'); let base = m ? m.id : ''; if(!base){let p = node.closest('[data-id], [id^=\"msg-item-\"], .msg-item'); base = p ? p.id || p.getAttribute('data-id') : '0';} let n = node.closest('.file-message, .msg-item, .card--file'); let nameNode = n ? n.querySelector('.file-name, .file-message__name, [class*=\"name\"]') : null; let name = nameNode ? nameNode.innerText.trim() : ''; return base + '_' + name; }")
                                    file_sender = btn.evaluate(r"""(node, sm) => {

                                        let m = node.closest('[id^="bb_msg_id_"]');

                                        if (m && sm[m.id]) return sm[m.id];

                                        let ci = node.closest('div.chat-item.flx');

                                        if (!ci || ci.classList.contains('me')) return 'Khách';

                                        let curr = ci;

                                        while (curr) {

                                            if (curr.classList && curr.classList.contains('chat-item') && !curr.classList.contains('me')) {

                                                let ne = curr.querySelector('.message-sender-name-content .truncate:not(.quote-name)');

                                                if (ne) { let t = ne.innerText.replace(/ /g,' ').trim(); if (t) return t; }

                                            }

                                            curr = curr.previousElementSibling;

                                        }

                                        return 'Khách';

                                    }""", sender_map)
                                    if internal_members and _is_zalo_internal(file_sender, internal_members):
                                        print(f"⏭️  [File] Bỏ qua nội bộ ({file_sender}): {group_name}")
                                        continue
                                    f_id = generate_stable_id(f"f_{group_name}_{raw_id}")
                                    if f_id not in history["messages"]:
                                        if not os.path.exists("W:\\"):
                                            print(f"⚠️ [CẢNH BÁO] Không thể kết nối hoặc truy cập ổ đĩa W:\\! Vui lòng kiểm tra ổ đĩa mạng.")
                                        saved_ok = False
                                        filename_log = "Unknown"
                                        for attempt in range(3):
                                            if attempt > 0:
                                                print(f"🔄 [File] Thử lại lần {attempt+1}/3 sau 3 giây...")
                                                time.sleep(3.0)
                                                cycle_deadline += 3.0
                                            t_start = time.time()
                                            try:
                                                # Ngăn Zalo revoke Blob URL quá nhanh để Playwright CDP hoặc JS Fetch kịp đọc
                                                try:
                                                    zalo_page.evaluate("""() => {

                                                        if (!window.__orig_revoke) {

                                                            window.__orig_revoke = URL.revokeObjectURL;

                                                            URL.revokeObjectURL = function(url) {

                                                                setTimeout(() => window.__orig_revoke(url), 300000);

                                                            };

                                                        }

                                                    }""")
                                                except: pass
                                                with zalo_page.expect_download(timeout=120000) as dl: 
                                                    try: btn.hover(timeout=2000)
                                                    except: pass
                                                    time.sleep(0.3)
                                                    # Dùng phím Alt khi click để ngăn Internet Download Manager (IDM) bắt link (nếu có)
                                                    btn.click(force=True, timeout=5000, modifiers=["Alt"])
                                                download = dl.value
                                                filename_log = download.suggested_filename
                                                path = os.path.join(save_dir, filename_log)
                                                print(f"📥 [File] Đang tải '{filename_log}' từ {file_sender} (Lần {attempt+1})...")
                                                print(f"🔗 [File] URL tải xuống: {download.url[:150]}")
                                                temp_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), f"dl_{uuid.uuid4().hex}_{download.suggested_filename}")
                                                try:
                                                    native_path = download.path()
                                                    if native_path and os.path.exists(native_path) and os.path.getsize(native_path) > 0:
                                                        print(f"💡 [File] Tải xong bằng Native Path: {native_path} ({os.path.getsize(native_path)} bytes)")
                                                        shutil.copy2(native_path, path)
                                                except Exception as e:
                                                    pass
                                                if not (os.path.exists(path) and os.path.getsize(path) > 0):
                                                    download.save_as(temp_path)
                                                    # Dùng JS Fetch nếu Playwright CDP bị lỗi trả về 0KB (Bug của Playwright CDP)
                                                    if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                                                        if download.url:
                                                            print(f"⚠️ [File] Tải qua CDP bị 0KB, đang dùng JS Fetch để lấy data...")
                                                            try:
                                                                b64 = zalo_page.evaluate("""async (url) => {

                                                                    let res = await fetch(url);

                                                                    let blob = await res.blob();

                                                                    return new Promise((resolve) => {

                                                                        let reader = new FileReader();

                                                                        reader.onloadend = () => resolve(reader.result);

                                                                        reader.readAsDataURL(blob);

                                                                    });

                                                                }""", download.url)
                                                                if b64 and "," in b64:
                                                                    import base64
                                                                    b64_data = b64.split(",", 1)[1]
                                                                    with open(temp_path, "wb") as f:
                                                                        f.write(base64.b64decode(b64_data))
                                                                    print(f"✅ [File] Tải qua JS Fetch thành công!")
                                                            except Exception as e:
                                                                print(f"❌ [File] JS Fetch lỗi: {e}")
                                                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                                                        shutil.copy2(temp_path, path)
                                                        try: os.remove(temp_path)
                                                        except: pass
                                                if os.path.exists(path) and os.path.getsize(path) > 0:
                                                    c_files.append(path)
                                                    history["messages"].add(f_id)
                                                    publish(IncomingMessage(channel=NAME, chat_id=group_name, chat_name=group_name, sender=file_sender,
                                                                            message_id=raw_id, attachments=(path,)))
                                                    new_data = True
                                                    saved_ok = True
                                                    if _is_design_file(path):
                                                        print(f"💾 [File/Design] Đã copy thành công file thiết kế sang ổ W: {path}")
                                                        if telegram_alert:
                                                            telegram_alert.send_alert(f"📥 <b>Zalo:</b> Khách hàng <b>{file_sender}</b> vừa gửi file thiết kế mới:\n<code>{filename_log}</code>")
                                                    else:
                                                        print(f"💾 [File] Đã copy thành công từ {file_sender}: {os.path.basename(path)} ({os.path.getsize(path)} bytes)")
                                                    if False:  # Bỏ like file tránh hiện popup biểu cảm
                                                        print(f"❤️ Đã thả Like cho file từ {file_sender}")
                                                        pass
                                                    break
                                                else:
                                                    reason = download.failure() or ("Bị phần mềm khác bắt link (như IDM)" if attempt == 2 else "Kích thước file = 0")
                                                    print(f"❌ [File] Lưu thất bại 0KB lần {attempt+1} từ {file_sender}: {reason}")
                                                    if os.path.exists(path):
                                                        try: os.remove(path)
                                                        except: pass
                                            except Exception as e:
                                                print(f"❌ [File] Lỗi download lần {attempt+1} từ {file_sender}: {e}")
                                            finally:
                                                # Gia hạn thời gian chờ của Watchdog thêm thời gian đã download thực tế
                                                download_duration = time.time() - t_start
                                                cycle_deadline += download_duration
                                        if not saved_ok:
                                            print(f"⛔ [File] Bỏ qua file '{filename_log}' từ {file_sender} sau 3 lần thử.")
                                            if telegram_alert:
                                                telegram_alert.send_alert(f"❌ <b>Zalo (Lỗi):</b> Không thể tải file <code>{filename_log}</code> từ <b>{file_sender}</b> sau 3 lần thử. Hãy kiểm tra lại.")
                                except Exception as e:
                                    print(f"❌ [File] Lỗi xử lý nút download file: {e}")
                            # 2. Quét Hình Ảnh
                            img_els = zalo_page.locator("img.zimg-el, img[data-z-element-type='image'], img[class*='picture'], img[src*='chat.zalo.me']").all()
                            for img in reversed(img_els[-20:]):
                                try:
                                    if not img.evaluate(ZALO_ATTACHMENT_GUARD_JS, "image"): continue
                                    if img.evaluate("node => node.closest('.me, .card--me') !== null"): continue
                                    if img.evaluate("node => node.closest('.file-message, .card--file, .msg-file') !== null"): continue
                                    if not img.evaluate(check_today_js): continue
                                    # Bỏ qua các ảnh kích thước nhỏ (emoji, icon, avatar, reactions...) để tránh click nhầm
                                    if img.evaluate("node => node.clientWidth < 80 || node.clientHeight < 80"):
                                        continue
                                    raw_id = img.evaluate("node => { let m = node.closest('[id^=\"bb_msg_id_\"]'); let base = m ? m.id : ''; if(!base){let p = node.closest('[data-id], [id^=\"msg-item-\"], .msg-item'); base = p ? p.id || p.getAttribute('data-id') : '0';} return base + '_' + (node.src || node.getAttribute('src') || ''); }")
                                    img_sender = img.evaluate(r"""(node, sm) => {

                                        let m = node.closest('[id^="bb_msg_id_"]');

                                        if (m && sm[m.id]) return sm[m.id];

                                        let ci = node.closest('div.chat-item.flx');

                                        if (!ci || ci.classList.contains('me')) return 'Khách';

                                        let curr = ci;

                                        while (curr) {

                                            if (curr.classList && curr.classList.contains('chat-item') && !curr.classList.contains('me')) {

                                                let ne = curr.querySelector('.message-sender-name-content .truncate:not(.quote-name)');

                                                if (ne) { let t = ne.innerText.replace(/ /g,' ').trim(); if (t) return t; }

                                            }

                                            curr = curr.previousElementSibling;

                                        }

                                        return 'Khách';

                                    }""", sender_map)
                                    if internal_members and _is_zalo_internal(img_sender, internal_members):
                                        print(f"⏭️  [Ảnh] Bỏ qua nội bộ ({img_sender}): {group_name}")
                                        continue
                                    img_id = generate_stable_id(f"img_{group_name}_{raw_id}")
                                    if img_id not in history["messages"]:
                                        if not os.path.exists("W:\\"):
                                            print(f"⚠️ [CẢNH BÁO] Không thể kết nối hoặc truy cập ổ đĩa W:\\! Vui lòng kiểm tra ổ đĩa mạng.")
                                        img.click(timeout=3000)
                                        # Chờ lightbox ảnh thực sự load xong (thay vì sleep cứng)
                                        # Poll naturalWidth của img trong viewer tối đa 12s
                                        lightbox_loaded = False
                                        for _w in range(24):
                                            try:
                                                nw = zalo_page.evaluate("""() => {

                                                    let v = document.querySelector('.photo-viewer img, .image-viewer img, .zviewer img, img.main-photo, [class*=\"viewer\"] img');

                                                    return v ? v.naturalWidth : 0;

                                                }""")
                                                if nw and nw > 0:
                                                    lightbox_loaded = True
                                                    break
                                            except: pass
                                            time.sleep(0.5)
                                            cycle_deadline += 0.5
                                        if not lightbox_loaded:
                                            # A sticker panel is not an image viewer; never click its buttons.
                                            zalo_page.locator("body").press("Escape")
                                            continue
                                        viewer = zalo_page.locator(".photo-viewer:visible, .image-viewer:visible, .zviewer:visible, [class*=\"viewer\"]:visible").first
                                        if not viewer.is_visible(timeout=2000):
                                            continue
                                        try:
                                            viewer.hover(timeout=2000)
                                        except Exception:
                                            pass
                                        dl_btn = viewer.locator("[title='Lưu về máy'], [title='Tải xuống'], [data-translate-title='STR_DOWNLOAD'], [data-translate-title='STR_SAVE_TO_PC'], [icon*='download'], [icon*='Download'], i.fa-download, i[class*='download']").first
                                        if not dl_btn.is_visible(timeout=1000):
                                            zalo_page.locator("body").press("Escape")
                                            continue
                                        saved_ok = False
                                        filename_log = "Unknown"
                                        for attempt in range(3):  # Retry tối đa 3 lần nếu 0KB
                                            if attempt > 0:
                                                print(f"🔄 [Ảnh] Thử lại lần {attempt+1}/3 sau 3 giây...")
                                                time.sleep(3.0)
                                                cycle_deadline += 3.0
                                            t_start = time.time()
                                            try:
                                                with zalo_page.expect_download(timeout=120000) as dl:
                                                    try: dl_btn.hover(timeout=2000)
                                                    except: pass
                                                    time.sleep(0.3)
                                                    dl_btn.click(force=True, timeout=5000)
                                                download = dl.value
                                                filename_log = download.suggested_filename
                                                path = os.path.join(save_dir, download.suggested_filename)
                                                temp_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), f"dl_{uuid.uuid4().hex}_{download.suggested_filename}")
                                                print(f"📥 [Ảnh] Đang tải '{filename_log}' từ {img_sender} (Lần {attempt+1})...")
                                                if not (os.path.exists(path) and os.path.getsize(path) > 0):
                                                    download.save_as(temp_path)
                                                    # Dùng JS Fetch nếu Playwright CDP bị lỗi trả về 0KB
                                                    if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                                                        if download.url:
                                                            print(f"⚠️ [Ảnh] Tải qua CDP bị 0KB, đang dùng JS Fetch để lấy data...")
                                                            try:
                                                                b64 = zalo_page.evaluate("""async (url) => {

                                                                    let res = await fetch(url);

                                                                    let blob = await res.blob();

                                                                    return new Promise((resolve) => {

                                                                        let reader = new FileReader();

                                                                        reader.onloadend = () => resolve(reader.result);

                                                                        reader.readAsDataURL(blob);

                                                                    });

                                                                }""", download.url)
                                                                if b64 and "," in b64:
                                                                    import base64
                                                                    b64_data = b64.split(",", 1)[1]
                                                                    with open(temp_path, "wb") as f:
                                                                        f.write(base64.b64decode(b64_data))
                                                                    print(f"✅ [Ảnh] Tải qua JS Fetch thành công!")
                                                            except Exception as e:
                                                                print(f"❌ [Ảnh] JS Fetch lỗi: {e}")
                                                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                                                        try:
                                                            from PIL import Image
                                                            with Image.open(temp_path) as im:
                                                                if im.mode in ("RGBA", "P"):
                                                                    im = im.convert("RGB")
                                                                im.save(path, "JPEG", quality=95)
                                                            print(f"🔄 [Ảnh] Đã chuyển đổi và lưu thành JPG: {path}")
                                                        except Exception as e_conv:
                                                            print(f"❌ [Ảnh] Lỗi chuyển đổi JPG: {e_conv}")
                                                            shutil.copy2(temp_path, path)
                                                        try: os.remove(temp_path)
                                                        except: pass
                                                if os.path.exists(path) and os.path.getsize(path) > 0:
                                                    c_files.append(path)
                                                    history["messages"].add(img_id)
                                                    new_data = True
                                                    saved_ok = True
                                                    print(f"💾 [Ảnh] Đã lưu thành công từ {img_sender}: {os.path.basename(path)} ({os.path.getsize(path)} bytes)")
                                                    break  # Thành công → thoát retry
                                                else:
                                                    reason = download.failure() or "CDN trả về rỗng / URL hết hạn"
                                                    print(f"❌ [Ảnh] Lỗi 0KB lần {attempt+1} từ {img_sender}: {reason}")
                                                    if os.path.exists(path):
                                                        try: os.remove(path)
                                                        except: pass
                                            except Exception as e:
                                                print(f"❌ [Ảnh] Lỗi download lần {attempt+1} từ {img_sender}: {e}")
                                            finally:
                                                # Gia hạn thời gian Watchdog
                                                download_duration = time.time() - t_start
                                                cycle_deadline += download_duration
                                        if not saved_ok:
                                            try:
                                                img_src = img.get_attribute("src")
                                                if img_src and img_src.startswith("blob:"):
                                                    b64 = zalo_page.evaluate("""async (url) => {
                                                        let res = await fetch(url);
                                                        let blob = await res.blob();
                                                        return new Promise((resolve) => {
                                                            let reader = new FileReader();
                                                            reader.onloadend = () => resolve(reader.result);
                                                            reader.readAsDataURL(blob);
                                                        });
                                                    }""", img_src)
                                                    if b64 and "," in b64:
                                                        import base64
                                                        b64_data = b64.split(",", 1)[1]
                                                        filename = f"img_{uuid.uuid4().hex[:8]}.jpg"
                                                        path = os.path.join(save_dir, filename)
                                                        temp_blob_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), f"temp_blob_{uuid.uuid4().hex[:8]}.png")
                                                        with open(temp_blob_path, "wb") as f_temp:
                                                            f_temp.write(base64.b64decode(b64_data))
                                                        try:
                                                            from PIL import Image
                                                            with Image.open(temp_blob_path) as im:
                                                                if im.mode in ("RGBA", "P"): 
                                                                    im = im.convert("RGB")
                                                                im.save(path, "JPEG", quality=95)
                                                        except Exception as e_conv:
                                                            with open(path, "wb") as f_out:
                                                                f_out.write(base64.b64decode(b64_data))
                                                        finally:
                                                            if os.path.exists(temp_blob_path):
                                                                try: os.remove(temp_blob_path)
                                                                except: pass
                                                        if os.path.exists(path) and os.path.getsize(path) > 0:
                                                            c_files.append(path)
                                                            history["messages"].add(img_id)
                                                            new_data = True
                                                            saved_ok = True
                                                            print(f"[Direct Blob] Tai thanh cong: {filename}")
                                            except Exception as direct_err:
                                                print(f"[Direct Blob] Loi: {direct_err}")
                                        if not saved_ok:
                                            print(f"⛔ [Ảnh] Bỏ qua ảnh '{filename_log}' từ {img_sender} sau 3 lần thử.")
                                        # Luôn đóng lightbox dù thành công hay lỗi
                                        try:
                                            time.sleep(0.5)
                                            cycle_deadline += 0.5
                                            zalo_page.locator("body").press("Escape", timeout=2000)
                                            time.sleep(0.5)
                                            cycle_deadline += 0.5
                                        except: pass
                                        if saved_ok:
                                            publish(IncomingMessage(channel=NAME, chat_id=group_name, chat_name=group_name, sender=img_sender,
                                                                    message_id=raw_id, attachments=(path,)))
                                            if False:  # Bỏ like ảnh tránh hiện popup biểu cảm
                                                print(f"❤️ Đã thả Like cho ảnh từ {img_sender}")
                                                pass
                                except Exception as e:
                                    print(f"❌ [Ảnh] Lỗi xử lý ảnh: {e}")
                                    # Đảm bảo đóng lightbox kể cả khi exception bên ngoài try-download
                                    try:
                                        zalo_page.locator("body").press("Escape", timeout=2000)
                                        time.sleep(0.3)
                                        cycle_deadline += 0.3
                                    except: pass
                            # 3. Quét Chữ và Link Drive
                            texts_info = zalo_page.evaluate(r"""() => {

                                let container = document.querySelector('#messageViewContainer') || document.querySelector('.chat-content');

                                if (!container) return [];

                                let todayBlock = Array.from(container.querySelectorAll('div.block-date')).find(b =>

                                    b.querySelector('[data-translate-text-arguments*="STR_TODAY"]')

                                );

                                if (!todayBlock) return [];

                                let senderMap = {};

                                let lastKnownSender = 'Khách';

                                for (let item of todayBlock.querySelectorAll('div.chat-item.flx')) {

                                    if (item.classList.contains('me')) continue;

                                                                    let nameEl = item.querySelector('.message-sender-name-content .truncate:not(.quote-name)');

                                    if (nameEl) {

                                        let txt = nameEl.innerText.replace(/ /g, ' ').trim();

                                        if (txt) lastKnownSender = txt;

                                    }

                                    item.querySelectorAll('[id^="bb_msg_id_"]').forEach(msgEl => {

                                        senderMap[msgEl.id] = lastKnownSender;

                                    });

                                }

                                let results = [];

                                todayBlock.querySelectorAll('span.text').forEach(n => {

                                    let chatItem = n.closest('div.chat-item');

                                    if (!chatItem || chatItem.classList.contains('me')) return;

                                    if (n.closest('.message-quote-fragment__content-container')) return;

                                    let content = n.innerText.trim();

                                    if (!content) return;

                                    let msgEl = n.closest('[id^="bb_msg_id_"]');

                                    if (!msgEl) return;

                                    let sender = senderMap[msgEl.id] || lastKnownSender;

                                    results.push({ content, raw_id: msgEl.id, sender });

                                });

                                return results;

                            }""")
                            # Duyệt qua các tin nhắn hôm nay theo chiều thuận (từ cũ đến mới) để xử lý tuần tự đúng thứ tự thời gian
                            for item in texts_info[-30:]:
                                content = item["content"]
                                sender = item["sender"]
                                # Bỏ qua tin nhắn từ nhân viên nội bộ trong luồng quét thường
                                is_internal = _is_zalo_internal(sender, internal_members) if internal_members else False
                                if is_internal or _has_zalo_internal_mention(content, internal_members):
                                    continue
                                msg_id = generate_stable_id(f"t_{group_name}_{sender}_{content}")
                                if msg_id not in history["messages"]:
                                    publish(IncomingMessage(channel=NAME, chat_id=group_name, chat_name=group_name, sender=sender,
                                                            message_id=item['raw_id'], text=content))
                                    c_texts.append(f"{sender}: {content}")
                                    # Tải file Drive hoặc link chia sẻ file khác nếu có trong tin nhắn
                                    drive_links = re.findall(r'(https?://drive\.google\.com/[^\s]+)', content)
                                    for link in drive_links:
                                        threading.Thread(target=background_download_drive, args=(group_name, link, save_dir), daemon=True).start()
                                    all_links = re.findall(r'(https?://[^\s]+)', content)
                                    for link in all_links:
                                        if "drive.google.com" in link or "viber.com" in link or ("zalo.me" in link and "/s/" not in link):
                                            continue
                                        threading.Thread(target=background_download_general_link, args=(group_name, link, save_dir), daemon=True).start()
                                    # Tự động lên đơn và thả tim/like dòng tin nhắn có số lượng/báo giá
                                    if _is_order_relevant(content) and zalo_allowed(group_name, "auto_order"):
                                        msg_el = zalo_page.locator(f"#{item['raw_id']}")
                                        # 1. Cuộn tin nhắn này vào giữa màn hình trước (lúc này CHƯA THẢ LIKE nên không bị popup che khuất)
                                        try:
                                            msg_el.scroll_into_view_if_needed(timeout=3000)
                                            time.sleep(1.5)  # Chờ giao diện cuộn ổn định
                                        except Exception as scroll_err:
                                            print(f"⚠️ Lỗi cuộn tin nhắn: {scroll_err}")
                                        # 2. Tiến hành chụp màn hình khung chat sạch (không bị popup che)
                                        f_path = f"zalo_order_{int(time.time())}_{item['raw_id']}.png"
                                        screenshot_ok = False
                                        try:
                                            area = zalo_page.locator("#messageViewContainer, .chat-message").first
                                            if area.is_visible(timeout=3000):
                                                area.screenshot(path=f_path)
                                                screenshot_ok = True
                                            else:
                                                zalo_page.screenshot(path=f_path)
                                                screenshot_ok = True
                                        except Exception as screenshot_err:
                                            print(f"❌ [Zalo] Lỗi chụp màn hình khi phát hiện đơn hàng tuần tự: {screenshot_err}")
                                        if screenshot_ok:
                                            # Persist before history: retry/restart cannot lose an observed order.
                                            try:
                                                rt.erp_bridge.capture(group_name, item['raw_id'], f_path, content)
                                            except Exception as capture_error:
                                                print(f"[ERP] Chưa lưu được đơn chờ: {type(capture_error).__name__}")
                                                continue
                                            history["messages"].add(msg_id)
                                            save_history(history)
                                            try:
                                                os.remove(f_path)
                                            except OSError:
                                                pass
                                            # 3. Thả like cho tin nhắn đặt hàng này SAU khi đã chụp ảnh màn hình xong
                                            try:
                                                react_to_message_like(zalo_page, msg_el)
                                                print(f"❤️ Đã thả Like cho dòng tin nhắn có số lượng của {sender}: '{content[:30]}...' (Sau khi chụp ảnh)")
                                            except Exception as like_err:
                                                print(f"⚠️ Không thể thả Like cho tin nhắn: {like_err}")
                                            # Đợi một chút để không bị chồng chéo
                                            time.sleep(1.0)
                                            new_data = True
                                    else:
                                        # Nếu là tin nhắn bình thường (không có SL) thì chỉ lưu vào lịch sử đã đọc
                                        history["messages"].add(msg_id)
                                        new_data = True
                        except Exception as e:
                            print(f"❌ [Zalo #{cycle}] Item {scan_step}: lỗi xử lý — {e}")
                        # 4. Trả về tổng quan và dọn dẹp badge
                        try:
                            # Nếu giao diện hẹp (ẩn sidebar), bấm nút Back để hiện lại sidebar
                            zalo_page.evaluate("""() => {

                                let backBtn = document.querySelector('.fa-chevron-left, i[class*="chevron-left"], [icon*="back"], [icon*="Back"], .header-back, [class*="btn-back"]');

                                if (backBtn) backBtn.click();

                            }""")
                            time.sleep(0.5)
                            # Phím tắt Zalo: Alt+1 để focus về danh sách hội thoại
                            zalo_page.locator("body").press("Alt+1")
                            time.sleep(0.3)
                            # Ép Zalo đánh dấu đã đọc (clear badge rác hoặc @mention)
                            elem = target_item.as_element()
                            if elem:
                                try:
                                    if elem.is_visible():
                                        elem.click(button="right", force=True, timeout=1500)
                                        time.sleep(0.3)
                                        mark_read = zalo_page.locator("div.menu-item").filter(has_text=re.compile(r"Đánh dấu đã đọc", re.IGNORECASE)).first
                                        if mark_read.is_visible(timeout=1000):
                                            mark_read.click(force=True, timeout=1000)
                                        else:
                                            zalo_page.locator("body").press("Escape")
                                        time.sleep(0.3)
                                except Exception as mark_err:
                                    print(f"⚠️ Lỗi ép đọc nhóm {group_name}: {mark_err}")
                            zalo_page.locator("body").press("Escape")
                        except: pass
            # Quay lại Cloud của tôi để thoát hoàn toàn khỏi nhóm cuối cùng
            try:
                zalo_page.locator("body").press("Escape")
                time.sleep(0.3)
                s_box = zalo_page.locator("#contact-search-input")
                if s_box.is_visible(timeout=1000):
                    s_box.fill("")
                    time.sleep(0.3)
                cloud_node = zalo_page.locator("div.msg-item").filter(
                    has_text=re.compile(r"Cloud của tôi|My Documents|Truyền File", re.IGNORECASE)
                ).first
                if cloud_node.is_visible(timeout=1500):
                    cloud_node.click(timeout=2000)
                    time.sleep(0.8)
            except: pass
            print(f"✅ [Zalo #{cycle}] Chu kỳ hoàn tất — chờ chu kỳ tiếp theo.")
        except Exception as e:
            print(f"❌ [Zalo #{cycle}] Lỗi nghiêm trọng trong chu kỳ quét: {e}")
            _tls.zalo_browser = None
        finally:
            report_status_to_nas(False)


def send_zalo_worker():
    while True:
        task = send_queue.get()
        erp_event_id = task.get("erp_event_id")
        try:
            if erp_event_id and not rt.erp_bridge.store.claim(erp_event_id):
                send_queue.task_done()
                continue
        except Exception:
            send_queue.put(task)
            send_queue.task_done()
            time.sleep(5)
            continue
        while rt.SYSTEM_STATUS == "PAUSED" or rt.screenshot_active > 0:
            time.sleep(2)
        customer_name = task['customer_name']
        message = task['message']
        is_disabled = not zalo_allowed(customer_name, "receive_messages")
        if is_disabled or (erp_event_id and not rt.erp_bridge.settings().get("enabled")):
            rt.erp_bridge.store.mark(erp_event_id, "blocked", "Cấu hình tắt nhận tin hoặc tắt tích hợp")
            print(f"⏭️  [Zalo-Worker] Bỏ qua gửi tin nhắn vì nhóm nằm trong zalo_disable_reply_groups (Khách: {customer_name})")
            send_queue.task_done()
            time.sleep(1)
            continue
        _send_worker_busy.set()
        report_status_to_nas(True, f"Gửi tin Zalo -> {customer_name}")
        with zalo_lock:
            try:
                page = _get_zalo_page()
                if page:
                    page.bring_to_front()
                    found = False
                    try:
                        header_now = page.locator(".header-title").first.inner_text(timeout=1500).strip()
                        if re.search(r"my documents|cloud|truyền file", header_now, re.IGNORECASE):
                            page.locator("body").press("Escape")
                            time.sleep(0.5)
                    except: pass
                    # CÁCH 1: Tìm trực tiếp ở danh sách bên trái
                    try:
                        chat_items = page.locator("#contact-list-inner div.msg-item").all()
                        for item in chat_items[:20]:
                            try:
                                item_text = item.evaluate("node => node.innerText.split('\\n')[0]").strip()
                                if item_text and (exact_group(customer_name, item_text) if erp_event_id else name_match(customer_name, item_text)):
                                    item.click(force=True, timeout=2000)
                                    found = True
                                    print(f"🔍 [SEND] Cách 1 tìm thấy '{customer_name}' → '{item_text}'")
                                    break
                            except: continue
                    except Exception as e:
                        print(f"⚠️ [SEND] Cách 1 lỗi: {e}")
                    # CÁCH 2: Dùng ô tìm kiếm nếu cách 1 thất bại
                    if not found:
                        try:
                            s_box = page.locator("#contact-search-input")
                            try:
                                s_box.click(force=True, timeout=3000)
                            except: pass
                            s_box.focus()
                            s_box.fill("", timeout=3000)
                            keyword = build_search_keyword(customer_name)
                            print(f"🔍 [SEND] Cách 2 search với từ khóa: '{keyword}'")
                            s_box.fill(keyword, timeout=3000)
                            time.sleep(2.5)
                            search_results = page.locator(
                                "#contact-search-list-wrapper div.msg-item, .global-search-list div.msg-item"
                            ).all()
                            clicked_verified = False
                            for result in (search_results if erp_event_id else search_results[:5]):
                                try:
                                    result_text = result.evaluate("node => node.innerText.split('\\n')[0]").strip()
                                    if result_text and (exact_group(customer_name, result_text) if erp_event_id else name_match(customer_name, result_text)):
                                        result.click(timeout=2000)
                                        clicked_verified = True
                                        found = True
                                        print(f"🔍 [SEND] Search khớp (Python): '{result_text}'")
                                        break
                                except: continue
                            if not clicked_verified:
                                clicked_js = page.evaluate(r"""(params) => {

                                    const norm = s => s.normalize('NFC').toLowerCase().replace(/\s+/g,' ').trim();

                                    const kn = norm(params.kw);

                                    const req = norm(params.req);

                                    const items = document.querySelectorAll('.msg-item, [class*="ContactItem"], [data-id*="search_result"]');

                                    for (const item of items) {

                                        if (item.closest('header, .chat-content, #messageViewContainer, #contact-list-inner')) continue;

                                        const txt = norm(item.innerText.split('\n')[0]);

                                        if (!txt) continue;

                                        if (params.exact ? txt === req : (txt.includes(req) || req.includes(txt) || txt.includes(kn) || kn.includes(txt))) {

                                            item.click();

                                            return txt;

                                        }

                                    }

                                    return null;

                                }""", {"kw": keyword, "req": customer_name, "exact": bool(erp_event_id)})
                                if clicked_js:
                                    time.sleep(1.5)
                                    found = True
                                    clicked_verified = True
                                    print(f"🔍 [SEND] Search khớp (JS): '{clicked_js}'")
                            if not clicked_verified and not erp_event_id:
                                first_result = page.locator(
                                    "#contact-search-list-wrapper div.msg-item, .global-search-list div.msg-item"
                                ).first
                                if first_result.is_visible(timeout=2000):
                                    first_result.click(force=True, timeout=2000)
                                    found = True
                                    print(f"⚠️ [SEND] Search: click kết quả đầu (không verify tên)")
                                else:
                                    s_box.focus()
                                    s_box.press("ArrowDown")
                                    time.sleep(0.5)
                                    s_box.press("Enter")
                                    found = True
                        except Exception as e:
                            print(f"⚠️ [SEND] Cách 2 lỗi: {e}")
                    time.sleep(2.5)
                    header_name = ""
                    try:
                        header_name = page.locator(".header-title").first.inner_text(timeout=3000).strip()
                    except: pass
                    if re.search(r"my documents|cloud|truyền file", header_name, re.IGNORECASE):
                        print(f"⚠️ [SEND] Vẫn kẹt ở '{header_name}', thử navigate lại...")
                        found = False
                        try:
                            s_box = page.locator("#contact-search-input")
                            try:
                                s_box.click(force=True, timeout=3000)
                            except: pass
                            s_box.focus()
                            s_box.fill("", timeout=3000)
                            keyword = build_search_keyword(customer_name)
                            s_box.fill(keyword, timeout=3000)
                            time.sleep(2.5)
                            search_results = page.locator(
                                "#contact-search-list-wrapper div.msg-item, .global-search-list div.msg-item"
                            ).all()
                            clicked_verified = False
                            for result in (search_results if erp_event_id else search_results[:5]):
                                try:
                                    result_text = result.evaluate("node => node.innerText.split('\\n')[0]").strip()
                                    if result_text and (exact_group(customer_name, result_text) if erp_event_id else name_match(customer_name, result_text)):
                                        result.click(force=True, timeout=2000)
                                        clicked_verified = True
                                        found = True
                                        break
                                except: continue
                            if not clicked_verified:
                                clicked_js = page.evaluate(r"""(params) => {

                                    const norm = s => s.normalize('NFC').toLowerCase().replace(/\s+/g,' ').trim();

                                    const kn = norm(params.kw);

                                    const req = norm(params.req);

                                    const items = document.querySelectorAll('.msg-item, [class*="ContactItem"], [data-id*="search_result"]');

                                    for (const item of items) {

                                        if (item.closest('header, .chat-content, #messageViewContainer, #contact-list-inner')) continue;

                                        const txt = norm(item.innerText.split('\n')[0]);

                                        if (!txt) continue;

                                        if (params.exact ? txt === req : (txt.includes(req) || req.includes(txt) || txt.includes(kn) || kn.includes(txt))) {

                                            item.click();

                                            return txt;

                                        }

                                    }

                                    return null;

                                }""", {"kw": keyword, "req": customer_name, "exact": bool(erp_event_id)})
                                if clicked_js:
                                    time.sleep(1.5)
                                    found = True
                                    clicked_verified = True
                            if not clicked_verified and not erp_event_id:
                                first_result = page.locator(
                                    "#contact-search-list-wrapper div.msg-item, .global-search-list div.msg-item"
                                ).first
                                if first_result.is_visible(timeout=2000):
                                    first_result.click(timeout=2000)
                                    found = True
                        except Exception as e2:
                            print(f"⚠️ [SEND] Retry lỗi: {e2}")
                        time.sleep(2)
                        try:
                            header_name = page.locator(".header-title").first.inner_text(timeout=3000).strip()
                        except: pass
                    print(f"📋 [SEND] Header: '{header_name}' | Yêu cầu: '{customer_name}'")
                    if found and (exact_group(customer_name, header_name) if erp_event_id else name_match(customer_name, header_name)) and zalo_allowed(customer_name, "receive_messages") and zalo_allowed(header_name, "receive_messages"):
                        inp = page.locator("#richInput")
                        inp.click(timeout=3000)
                        inp.fill(message, timeout=3000)
                        time.sleep(0.5)
                        if zalo_allowed(customer_name, "receive_messages") and zalo_allowed(header_name, "receive_messages") and (not erp_event_id or rt.erp_bridge.settings().get("enabled")):
                            if erp_event_id and not exact_group(customer_name, page.locator(".header-title").first.inner_text(timeout=1500).strip()):
                                inp.fill("")
                                raise RuntimeError("Nhóm đang mở đã thay đổi trước khi gửi")
                            # Durable boundary immediately before the irreversible UI action.
                            rt.erp_bridge.store.mark(erp_event_id, "sending")
                            inp.press("Enter")
                            rt.erp_bridge.store.mark(erp_event_id, "submitted", "Đã thao tác gửi trên Zalo; không phải xác nhận người nhận đã đọc")
                        else:
                            inp.fill("")
                            raise RuntimeError("Khách đã tắt nhận tin trong lúc chuẩn bị gửi")
                        print(f"✅ [SEND] Đã gửi thành công cho: {customer_name}")
                    elif not found:
                        print(f"❌ [SEND] Không tìm thấy '{customer_name}' qua cả 2 cách. Hủy gửi.")
                    else:
                        print(f"❌ [CẢNH BÁO NGUY HIỂM] Yêu cầu: '{customer_name}' | Đang mở: '{header_name}'. Không khớp → Hủy!")
                    # Về lại Cloud
                    try:
                        page.locator("body").press("Escape")
                        time.sleep(0.3)
                        try:
                            s_box = page.locator("#contact-search-input")
                            if s_box.is_visible(timeout=1000):
                                s_box.fill("")
                                time.sleep(0.3)
                        except: pass
                        cloud_node = page.locator("div.msg-item").filter(
                            has_text=re.compile(r"Cloud của tôi|My Documents|Truyền File", re.IGNORECASE)
                        ).first
                        if cloud_node.is_visible(timeout=1500):
                            cloud_node.click(timeout=2000)
                            time.sleep(0.8)
                    except: pass
            except Exception as e:
                _tls.zalo_browser = None
                print(f"❌ [SEND] Lỗi kỹ thuật khi gửi tin cho {customer_name}: {e}")
            finally:
                try:
                    rt.erp_bridge.store.fail(erp_event_id)
                except Exception:
                    print("[ERP] Không ghi được kết quả; giữ hàng đợi để đối chiếu sau")
                _send_worker_busy.clear()
                report_status_to_nas(False)
        send_queue.task_done()
        time.sleep(1)


def exit_chat():
    with zalo_lock:
        browser = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=10000)
                page = next((pg for pg in browser.contexts[0].pages if "chat.zalo.me" in pg.url), None)
                if page:
                    page.bring_to_front()
                    page.locator("body").press("Escape")
                    time.sleep(0.5)
                    try:
                        s_box = page.locator("#contact-search-input")
                        if s_box.is_visible():
                            s_box.fill("")
                    except: pass
                    cloud_node = page.locator("div.msg-item").filter(has_text=re.compile(r"Cloud của tôi|My Documents|Truyền File", re.IGNORECASE)).first
                    if cloud_node.is_visible(timeout=1500):
                        cloud_node.click(timeout=2000)
                        time.sleep(0.8)
                    return {"status": "ok", "message": "Successfully exited chat and reset to Cloud"}
                else:
                    return {"status": "error", "message": "Zalo page not found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if browser:
                try: browser.close()
                except: pass


def broadcast(message, limit):
    prev_status = rt.SYSTEM_STATUS
    rt.SYSTEM_STATUS = "PAUSED"
    queued_names = []
    with zalo_lock:
        browser = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=10000)
                page = next((pg for pg in browser.contexts[0].pages if "chat.zalo.me" in pg.url), None)
                if page:
                    page.bring_to_front()
                    try:
                        sidebar = page.locator("#contact-list-inner")
                        if sidebar.is_visible(timeout=1000): sidebar.evaluate("node => node.scrollTop = 0")
                    except: pass
                    time.sleep(0.5)
                    js_get_names = """() => {

                        let items = Array.from(document.querySelectorAll('div.msg-item')).filter(el => {

                            if (el.id && el.id.startsWith('msg-item-')) return false;

                            if (el.closest('.chat-content, #messageViewContainer')) return false;

                            return true;

                        });

                        let results = [];

                        for(let el of items) {

                            let parts = el.innerText.trim().split('\\n');

                            if(parts.length > 0 && parts[0]) {

                                results.push(parts[0].trim());

                            }

                        }

                        return results;

                    }"""
                    names_list = page.evaluate(js_get_names)
                    count = 0
                    for name in names_list:
                        if count >= limit: break
                        if re.search(r"my documents|cloud|truyền file", name, re.IGNORECASE):
                            continue
                        send_queue.put({"customer_name": name, "message": message})
                        queued_names.append(name)
                        count += 1
        except Exception as e:
            print(f"❌ [BROADCAST] Lỗi: {e}")
            rt.SYSTEM_STATUS = prev_status
            return {"status": "error", "msg": str(e)}
        finally:
            if browser:
                try: browser.close()
                except: pass
    rt.SYSTEM_STATUS = prev_status
    return {
        "status": "success",
        "msg": f"Thành công! Đã lên danh sách và đưa {len(queued_names)} tin nhắn vào hàng đợi. Bot sẽ tự động gửi lần lượt.",
        "targets": queued_names
    }


def capture_chat_screenshot(customer_name, f_path):
    """Mở chat Zalo theo tên và chụp khung chat. Trả về (success, error_msg); endpoint lo tạm dừng quét."""
    success = False
    error_msg = "Lỗi không xác định"
    with zalo_lock:
        browser = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=10000)
                page = next((pg for pg in browser.contexts[0].pages if "chat.zalo.me" in pg.url), None)
                if page:
                    page.bring_to_front()
                    # Reset về Cloud của tôi để thoát hoàn toàn khỏi nhóm đang quét
                    try:
                        page.locator("body").press("Escape")
                        cloud_node = page.locator("div.msg-item").filter(has_text=re.compile(r"Cloud của tôi|My Documents|Truyền File", re.IGNORECASE)).first
                        if cloud_node.is_visible(timeout=1000): cloud_node.click(timeout=2000)
                        time.sleep(0.5)
                    except: pass
                    found = False
                    keyword = build_search_keyword(customer_name)
                    # Bước 1: Thử tìm trong danh sách bên trái (nếu chat đang hiển thị)
                    try:
                        chat_items = page.locator("#contact-list-inner div.msg-item").all()
                        for item in chat_items[:20]:
                            try:
                                item_text = item.evaluate("node => node.innerText.split('\\n')[0]").strip()
                                if item_text and name_match(customer_name, item_text):
                                    item.click(timeout=2000)
                                    time.sleep(1.5)
                                    found = True
                                    print(f"🔍 [SCREENSHOT] Cách 1 tìm thấy: '{item_text}'")
                                    break
                            except: continue
                    except: pass
                    # Bước 2: Dùng ô tìm kiếm + JavaScript để click kết quả
                    if not found:
                        print(f"🔍 [SCREENSHOT] Search: '{keyword}'")
                        try:
                            s_box = page.locator("#contact-search-input")
                            try:
                                s_box.click(force=True, timeout=3000)
                            except: pass
                            s_box.focus()
                            time.sleep(0.3)
                            s_box.fill("", timeout=2000)
                            s_box.fill(keyword, timeout=3000)
                            time.sleep(3)
                            # Dùng JS để tìm kết quả — không phụ thuộc selector cố định
                            clicked = page.evaluate(r"""(params) => {

                                const norm = s => s.normalize('NFC').toLowerCase().replace(/\s+/g,' ').trim();

                                const kn = norm(params.kw);

                                const req = norm(params.req);

                                const items = document.querySelectorAll('.msg-item, [class*="ContactItem"], [data-id*="search_result"]');

                                for (const item of items) {

                                    if (item.closest('header, .chat-content, #messageViewContainer, #contact-list-inner')) continue;

                                    const txt = norm(item.innerText.split('\n')[0]);

                                    if (!txt) continue;

                                    // Ưu tiên match tên đầy đủ trước, sau đó mới tới keyword

                                    if (txt.includes(req) || req.includes(txt) || txt.includes(kn) || kn.includes(txt)) {

                                        item.click();

                                        return txt;

                                    }

                                }

                                return null;

                            }""", {"kw": keyword, "req": customer_name})
                            if clicked:
                                time.sleep(1.5)
                                found = True
                                print(f"🔍 [SCREENSHOT] JS click: '{clicked}'")
                            else:
                                # Fallback: bấm ArrowDown + Enter để chọn kết quả đầu tiên
                                s_box.press("ArrowDown")
                                time.sleep(0.5)
                                s_box.press("Enter")
                                time.sleep(1.5)
                                found = True
                                print(f"⚠️ [SCREENSHOT] ArrowDown+Enter (không verify)")
                        except Exception as e:
                            print(f"⚠️ [SCREENSHOT] Search lỗi: {e}")
                    # Đọc header, retry 3 lần nếu vẫn là My Documents
                    header_name = ""
                    for _ in range(3):
                        try:
                            header_name = page.locator(".header-title").first.inner_text(timeout=2000).strip()
                        except: pass
                        if header_name and not re.search(r'my documents|cloud|truyền file', header_name, re.IGNORECASE):
                            break
                        time.sleep(1)
                    print(f"📋 [SCREENSHOT] Header: '{header_name}' | Yêu cầu: '{customer_name}'")
                    if name_match(customer_name, header_name):
                        time.sleep(1)
                        area = page.locator("#messageViewContainer, .chat-message").first
                        if area.is_visible(timeout=2000): area.screenshot(path=f_path)
                        else: page.screenshot(path=f_path)
                        success = True
                    else:
                        error_msg = f"Tên khung chat không khớp! Yêu cầu: '{customer_name}', Thực tế đang mở: '{header_name}'"
                        print(f"❌ [SCREENSHOT] {error_msg}")
                    try:
                        page.locator("body").press("Escape")
                        time.sleep(0.3)
                        s_box = page.locator("#contact-search-input")
                        if s_box.is_visible(timeout=1000):
                            s_box.fill("")
                            time.sleep(0.3)
                        cloud_node = page.locator("div.msg-item").filter(has_text=re.compile(r"Cloud của tôi|My Documents|Truyền File", re.IGNORECASE)).first
                        if cloud_node.is_visible(timeout=1000): cloud_node.click(timeout=2000)
                    except: pass
                else:
                    error_msg = "Không tìm thấy tab Zalo Web đang mở"
        except Exception as e:
            error_msg = str(e)
            print(f"❌ [SCREENSHOT] Lỗi: {e}")
        finally:
            if browser:
                try: browser.close()
                except: pass
    return success, error_msg


def trigger_scan():
    _zalo_scan_event.set()


def start():
    """Khởi động luồng quét + luồng gửi (thứ tự như main.py cũ)."""
    threading.Thread(target=scan_zalo_loop, daemon=True).start()
    _zalo_scan_event.set()  # Kick ngay lần đầu khi khởi động
    threading.Thread(target=send_zalo_worker, daemon=True).start()
