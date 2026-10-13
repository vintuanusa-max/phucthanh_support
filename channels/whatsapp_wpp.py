"""Kênh WhatsApp cá nhân qua WhatsApp Web (Chrome CDP cổng 9223) + WPPConnect."""
import base64
import os
import re
import threading
import time
import unicodedata

from playwright.sync_api import sync_playwright

from core import runtime as rt
from core.history import load_whatsapp_history, save_whatsapp_history
from core.intake import process_extracted_screenshot_async
from core.messages import IncomingMessage, publish
from core.paths import ROOT
from core.policy import whatsapp_reply_disabled
from core.runtime import WHATSAPP_CDP_PORT, _tls, _wa_scan_event, report_status_to_nas, wa_send_queue, whatsapp_lock
from core.settings import _is_design_file, get_wa_internal, get_wa_skip_groups, is_skip_group
from core.text_rules import (_has_internal_mention, _is_order_forwardable, _is_order_relevant, get_recent_files,
                             group_to_folder, name_match)

NAME = "whatsapp"


def _get_wa_page():
    """Lấy WhatsApp page với kết nối bền vững theo từng thread."""
    try:
        if getattr(_tls, 'wa_browser', None):
            ctx = _tls.wa_browser.contexts[0]
            page = next((p for p in ctx.pages if "web.whatsapp.com" in p.url), None)
            if page and not page.is_closed():
                _inject_wppconnect(page)
                return page
    except:
        _tls.wa_browser = None
    if not getattr(_tls, 'pw', None):
        _tls.pw = sync_playwright().start()
    _tls.wa_browser = _tls.pw.chromium.connect_over_cdp(f"http://localhost:{WHATSAPP_CDP_PORT}", timeout=10000)
    page = next((p for p in _tls.wa_browser.contexts[0].pages if "web.whatsapp.com" in p.url), None)
    if page:
        _inject_wppconnect(page)
    return page


def _inject_wppconnect(page):
    """Tiêm wppconnect-wa.js vào trang WhatsApp để dùng API Headless."""
    try:
        # Chờ WA UI load lên trước khi tiêm WPP
        page.wait_for_selector('#pane-side, [data-testid="chat-list"], canvas', timeout=5000)
    except: pass
    is_ready = page.evaluate("() => typeof WPP !== 'undefined' && WPP.isReady")
    if not is_ready:
        print("[WA] Đang tiêm wppconnect-wa.js (bỏ qua CSP)...")
        try:
            wa_js_path = os.path.join(str(ROOT), "wppconnect-wa.js")
            if os.path.exists(wa_js_path):
                with open(wa_js_path, "r", encoding="utf-8") as f:
                    js_code = f.read()
                # Evaluate trực tiếp mã nguồn thay vì dùng thẻ <script> để lách luật CSP
                page.evaluate(js_code)
            else:
                print("❌ [WA] Không tìm thấy file wppconnect-wa.js tại local. Đang cố thử tải script tag...")
                page.add_script_tag(url="https://github.com/wppconnect-team/wa-js/releases/latest/download/wppconnect-wa.js")
            # Khởi tạo WPP
            page.evaluate("""async () => {

                if (typeof WPP === 'undefined') return false;

                

                if (WPP.webpack && typeof WPP.webpack.inject === 'function') {

                    try { await WPP.webpack.inject(); } catch(e) {}

                }

                return true;

            }""")
            # Đợi chắc chắn isReady = true
            for _ in range(15):
                if page.evaluate("() => typeof WPP !== 'undefined' && WPP.isReady"):
                    print("[WA] Đã khởi tạo WPPConnect thành công.")
                    return
                time.sleep(1)
            print("⚠️ [WA] Tiêm WPPConnect xong nhưng isReady vẫn false.")
        except Exception as e:
            print(f"❌ [WA] Lỗi tiêm WPPConnect: {e}")


def _wa_get_chats(wa_page):
    """Lấy danh sách chat có tin nhắn chưa đọc thông qua WPPConnect."""
    return wa_page.evaluate(r"""async () => {
        for (let i = 0; i < 20; i++) {
            if (typeof WPP !== 'undefined' && WPP.isReady) break;
            await new Promise(r => setTimeout(r, 500));
        }

        if (typeof WPP === 'undefined' || !WPP.isReady) {
            let items = [];
            let pane = document.querySelector('#pane-side') 
                    || document.querySelector('[data-testid="chat-list"]')
                    || document.querySelector('[role="grid"]');
            if (pane) {
                let rows = pane.querySelectorAll('div[tabindex="-1"], div[role="listitem"], [data-testid^="list-item-"]');
                rows.forEach(r => {
                    let titleEl = r.querySelector('[data-testid="cell-frame-title"]') 
                               || r.querySelector('span[title]') 
                               || r.querySelector('span[dir="auto"]');
                    let unreadEl = r.querySelector('[data-testid="icon-unread-count"]')
                                || r.querySelector('span[aria-label*="unread"]')
                                || r.querySelector('span[aria-label*="chưa đọc"]');
                    if (titleEl) {
                        let rawName = titleEl.getAttribute('title') || titleEl.innerText || '';
                        let name = typeof rawName === 'string' ? rawName.trim() : '';
                        // Nếu là chuỗi toàn số (số điện thoại) mà có tên hiển thị khác thì bỏ qua số phone
                        if (name && name.length > 1 && !name.includes('\n')) {
                            items.push({ 
                                id: name, 
                                name: name, 
                                hasUnread: !!unreadEl, 
                                isPinned: true, 
                                unreadCount: unreadEl ? parseInt(unreadEl.innerText) || 1 : 1 
                            });
                        }
                    }
                });
            }
            if (items.length > 0) return { error: null, total: items.length, found: items.length, unread_count: items.length, items: items };
            return { error: "WPP not ready & DOM fallback empty" };
        }

        let chats = [];
        if (typeof WPP.chat.getChats === 'function') {
            chats = await WPP.chat.getChats();
        } else if (typeof WPP.chat.list === 'function') {
            chats = await WPP.chat.list();
        } else if (WPP.whatsapp && WPP.whatsapp.ChatStore) {
            chats = WPP.whatsapp.ChatStore.getModels();
        } else {
            return { error: "Chat list API not found in WPP" };
        }

        let results = [];
        for (let c of chats) {
            let isPinned = !!c.pin || !!c.isPinned || (typeof c.isPinned === 'function' && c.isPinned());
            let hasUnread = c.unreadCount > 0 || (c.unreadCount === undefined && c.unread);
            results.push({
                id: c.id._serialized,
                name: c.name || c.formattedTitle || c.id.user,
                hasUnread: hasUnread,
                isPinned: isPinned,
                unreadCount: c.unreadCount || 0
            });
        }
        return {
            error: null,
            total: chats.length,
            found: results.length,
            unread_count: results.filter(r => r.hasUnread).length,
            items: results
        };
    }""")


def _wa_read_messages(wa_page, chat_id, internal_members):
    """Đọc tin nhắn đến từ một chat cụ thể bằng WPPConnect API."""
    return wa_page.evaluate(r"""async (params) => {

        let internal = params.internal;

        let chatId = params.chatId;

        for (let i = 0; i < 20; i++) {

            if (typeof WPP !== 'undefined' && WPP.isReady) break;

            await new Promise(r => setTimeout(r, 500));

        }

        if (typeof WPP === 'undefined' || !WPP.isReady) return { msgs: [], debug: "WPP not ready" };

        

        // Lấy tin nhắn chưa đọc

        let msgs = await WPP.chat.getMessages(chatId, { count: 20 });

        let results = [];

        

        for (let msg of msgs) {

            if (msg.id.fromMe) continue; // Bỏ qua tin nhắn do mình gửi

            

            // Chỉ quét tin nhắn trong ngày hôm nay

            let msgDate = new Date(msg.t * 1000);

            let today = new Date();

            if (msgDate.getDate() !== today.getDate() || msgDate.getMonth() !== today.getMonth() || msgDate.getFullYear() !== today.getFullYear()) {

                continue;

            }

            

            let senderRaw = msg.sender ? (msg.sender.pushname || msg.sender.name || msg.sender.formattedName || msg.from) : msg.from;

            let sender = (typeof senderRaw === 'object' && senderRaw !== null) ? (senderRaw._serialized || senderRaw.user || '') : String(senderRaw || 'Khách');

            let sLow = sender.toLowerCase();

            // Do not filter out internal members in JS so we can scan them in python for trigger commands
            // if (internal.some(im => sLow.includes(im.toLowerCase()) || im.toLowerCase().includes(sLow))) continue;

            

            let content = msg.caption || msg.body || '';
            if (typeof content === 'string' && (content.startsWith('data:') || content.startsWith('/9j/') || (content.length > 100 && !content.includes(' ')))) {
                content = msg.caption || '';
            }

            results.push({

                content: content,

                sender: sender || 'Khách',

                msgId: msg.id._serialized,

                isMedia: msg.hasMedia || msg.isMedia,

                type: msg.type,

                rawMsg: {

                    filename: msg.filename || (msg.mediaData ? msg.mediaData.filename : '') || msg.clientUrl || (msg.mediaData ? msg.mediaData.clientUrl : '') || '',

                    clientUrl: msg.clientUrl || (msg.mediaData ? msg.mediaData.clientUrl : '') || ''

                }

            });

        }

        return { msgs: results, debug: "WPP API used" };

    }""", {"internal": internal_members, "chatId": chat_id})


def scan_whatsapp_loop():
    cycle = 0
    while True:
        _wa_scan_event.wait(timeout=120)  # Tự wakeup mỗi 2 phút nếu không có ai trigger
        _wa_scan_event.clear()
        while rt.SYSTEM_STATUS == "PAUSED" or rt.screenshot_active > 0:
            time.sleep(5)
        cycle += 1
        wa_page = None
        with whatsapp_lock:
            try:
                wa_page = _get_wa_page()
            except Exception as e:
                _tls.wa_browser = None
                print(f"❌ [WA #{cycle}] Không kết nối được: {e}")
        if not wa_page:
            continue
        report_status_to_nas(True, f"Quét WhatsApp #{cycle}...")
        try:
            try:
                wa_page.bring_to_front()  # Đưa Chrome WA lên foreground để tương tác
            except: pass
            print(f"🔄 [WA #{cycle}] Bắt đầu quét...")
            history = load_whatsapp_history()
            try:
                wa_page.evaluate("""() => {

                    let p = document.querySelector('#pane-side')

                          || document.querySelector('[data-testid="chat-list"]');

                    if (p) p.scrollTop = 0;

                }""")
            except: pass
            chat_result = {}
            try:
                chat_result = _wa_get_chats(wa_page)
            except Exception as e:
                print(f"⚠️ [WA #{cycle}] Lỗi khi lấy danh sách chat DOM: {e}")
                chat_result = {"error": str(e)}
            if chat_result.get('error'):
                print(f"⚠️ [WA #{cycle}] Không tìm thấy sidebar chat. Lỗi: {chat_result['error']}")
                continue
            chats = chat_result.get('items', [])
            unread_chats = [c for c in chats if c['hasUnread']]
            if unread_chats:
                print(f"📋 [WA #{cycle}] Có {len(unread_chats)} chat chưa đọc: {[c['name'] for c in unread_chats]}")
            processed_in_cycle = set()
            for chat in chats:
                chat_name = chat['name']
                if chat_name in processed_in_cycle:
                    continue
                processed_in_cycle.add(chat_name)
                # Lọc badge text bị nhận nhầm là tên nhóm (VD: "1 tin nhắn chưa đọc", "unread messages")
                if re.search(r'tin\s*nh[aắ]n|unread\s*msg|unread\s*message', chat_name, re.IGNORECASE):
                    continue
                if re.search(r'broadcast|kênh|channel', chat_name, re.IGNORECASE):
                    continue
                wa_skip_groups = get_wa_skip_groups()
                if is_skip_group(chat_name, wa_skip_groups):
                    continue
                # Bỏ qua các chat cá nhân dạng số điện thoại (ví dụ: 84902789551, +84 96 300 16 68)
                clean_name_check = re.sub(r'[\s\+\-\(\)]', '', chat_name)
                if clean_name_check.isdigit() or (clean_name_check.startswith('84') and clean_name_check[2:].isdigit()):
                    continue
                with whatsapp_lock:
                    try:
                        header_name = chat_name
                        print(f"👉 [WA] Đang đọc: {header_name} (unread={chat['hasUnread']})")
                        folder_name = group_to_folder(header_name)
                        save_dir = f"W:\\{folder_name}"
                        wa_internal = get_wa_internal()
                        raw = _wa_read_messages(wa_page, chat['id'], wa_internal)
                        msgs = raw.get('msgs', []) if isinstance(raw, dict) else []
                        print(f"   → Tìm thấy {len(msgs)} tin nhắn đến bằng API")
                        new_data = False
                        c_texts, c_files, c_intake = [], [], []
                        # 2.5. Kiểm tra lệnh từ nhân viên nội bộ (WA)
                        has_force_command = False
                        command_msg_id = None
                        command_sender = ""
                        command_text = ""
                        for item in msgs:
                            sender = item["sender"]
                            c_content = item.get("content") or ""
                            is_internal = any(im.lower() in sender.lower() or sender.lower() in im.lower() for im in wa_internal) if wa_internal else False
                            if is_internal:
                                norm_content = unicodedata.normalize('NFC', c_content).strip().lower()
                                if norm_content in ["xem lên đơn", "lên đơn"]:
                                    if item['msgId'] not in history["messages"]:
                                        has_force_command = True
                                        command_msg_id = item['msgId']
                                        command_sender = sender
                                        command_text = c_content
                                        break
                        if has_force_command:
                            print(f"⚡ [WA] Nhận lệnh '{command_text}' từ nhân viên nội bộ: {command_sender}")
                            # Tìm tất cả tin nhắn của khách có chứa số lượng để lên đơn toàn bộ các lô
                            target_customer_msgs = []
                            for item in msgs:
                                c_sender = item["sender"]
                                c_content = item.get("content") or ""
                                c_is_internal = any(im.lower() in c_sender.lower() or c_sender.lower() in im.lower() for im in wa_internal) if wa_internal else False
                                if not c_is_internal and item["msgId"] not in history["messages"] and _is_order_relevant(c_content):
                                    target_customer_msgs.append(item)
                            if target_customer_msgs:
                                print(f"🎯 [WA] Tìm thấy {len(target_customer_msgs)} tin nhắn đặt hàng của khách để lên đơn.")
                                force_ok = True
                                for idx, target_msg in enumerate(target_customer_msgs):
                                    print(f"  👉 Đang lên đơn lô {idx+1}/{len(target_customer_msgs)}: {target_msg['sender']}: '{target_msg['content']}'")
                                    f_path = f"whatsapp_order_{int(time.time())}_{idx}.png"
                                    try:
                                        wa_page.evaluate(f"async () => {{ await WPP.chat.openChatBottom('{chat['id']}'); }}")
                                        time.sleep(2)
                                        area = wa_page.locator("#main").first
                                        if area.is_visible(timeout=3000):
                                            area.screenshot(path=f_path)
                                        else:
                                            wa_page.screenshot(path=f_path)
                                        process_extracted_screenshot_async(
                                            header_name, f_path, "whatsapp",
                                            str(chat['id']) + "\0" + str(target_msg['msgId']), target_msg['content'])
                                        history["messages"].add(target_msg['msgId'])
                                    except Exception as screenshot_err:
                                        force_ok = False
                                        print(f"❌ [WA] Lỗi chụp màn hình khi force lên đơn lô {idx+1}: {screenshot_err}")
                            else:
                                print(f"⚠️ [WA] Không tìm thấy tin nhắn nào có chứa số lượng của khách hôm nay để lên đơn.")
                            # Đánh dấu đã xử lý lệnh này
                            if not target_customer_msgs or force_ok:
                                history["messages"].add(command_msg_id)
                            save_whatsapp_history(history)
                        for item in msgs:
                            msg_id = item['msgId']
                            sender = item["sender"]
                            c_content = item.get("content") or ""
                            # Bỏ qua nhân viên nội bộ
                            is_internal = any(im.lower() in sender.lower() or sender.lower() in im.lower() for im in wa_internal) if wa_internal else False
                            if is_internal:
                                continue
                            if msg_id in history["messages"]:
                                continue
                            dl_success = True
                            media_paths = []
                            # Tải Media trực tiếp bằng API
                            if item.get('isMedia'):
                                dl_success = False
                                try:
                                    b64_data = wa_page.evaluate(f"async () => {{ return await WPP.chat.downloadMedia('{msg_id}').then(WPP.util.blobToBase64); }}")
                                    if b64_data and ',' in b64_data:
                                        header, encoded = b64_data.split(",", 1)
                                        ext = ".bin"
                                        if "jpeg" in header or "jpg" in header: ext = ".jpg"
                                        elif "png" in header: ext = ".png"
                                        elif "pdf" in header: ext = ".pdf"
                                        elif "mp4" in header: ext = ".mp4"
                                        # Lấy tên file gốc nếu có
                                        rawMsg = item.get('rawMsg', {})
                                        suggested_filename = rawMsg.get('filename') or rawMsg.get('clientUrl') or ''
                                        if suggested_filename:
                                            suggested_filename = os.path.basename(suggested_filename.split('?')[0])
                                        if not suggested_filename:
                                            suggested_filename = f"wa_{msg_id.replace('@', '_').replace('.', '_')}{ext}"
                                        import base64
                                        os.makedirs(save_dir, exist_ok=True)
                                        path = os.path.join(save_dir, suggested_filename)
                                        with open(path, "wb") as f:
                                            f.write(base64.b64decode(encoded))
                                        if os.path.exists(path) and os.path.getsize(path) > 0:
                                            c_files.append(path)
                                            media_paths.append(path)
                                            print(f"💾 [WA-Media] Đã tải API: {suggested_filename}")
                                            dl_success = True
                                        else:
                                            print(f"❌ [WA-Media] Tải file bị rỗng: {suggested_filename}")
                                except Exception as e:
                                    print(f"❌ [WA-Media] Lỗi tải qua API: {e}")
                            if item.get('content'):
                                c_texts.append(f"{item['sender']}: {item['content']}")
                            # Chỉ thêm vào lịch sử nếu tải file thành công (hoặc không có file)
                            if dl_success:
                                publish(IncomingMessage(channel=NAME, chat_id=str(chat['id']), chat_name=header_name, sender=sender,
                                                        message_id=str(msg_id), text=c_content, attachments=tuple(media_paths)))
                                if _is_order_relevant(c_content) or _is_order_forwardable(c_content):
                                    c_intake.append((msg_id, c_content))
                                else:
                                    history["messages"].add(msg_id)
                                new_data = True
                        # Đánh dấu đã đọc trên điện thoại
                        try:
                            wa_page.evaluate(f"async () => {{ await WPP.chat.markIsRead('{chat['id']}'); }}")
                        except: pass
                        if new_data:
                            combined_wa = "\n".join(c_texts)
                            recent_files = get_recent_files(save_dir, minutes=10)
                            all_files = list(set(c_files + recent_files))
                            send_files = [f for f in all_files if not _is_design_file(f)]
                            actual_f_type = "COMBO"
                            # Log kết quả tải file
                            if c_files:
                                print(f"💾 [WA] Đã lưu {len(c_files)} file: {[os.path.basename(f) for f in c_files]}")
                            # Logic forward tương tự Zalo: CHỈ forward khi có text chứa SL/báo giá
                            has_new_images = any(f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) for f in c_files)
                            if _has_internal_mention(combined_wa, wa_internal) and not _is_order_relevant(combined_wa):
                                print(f"⏭️  [WA] Bỏ qua (@nội bộ): {header_name} — {combined_wa[:60]}")
                                save_whatsapp_history(history)
                            elif c_intake:
                                # Tiến hành chụp màn hình và lên đơn
                                f_path = f"whatsapp_order_{int(time.time())}.png"
                                try:
                                    # Mở chat cụ thể trên màn hình để chụp ảnh
                                    wa_page.evaluate(f"async () => {{ await WPP.chat.openChatBottom('{chat['id']}'); }}")
                                    time.sleep(2) # Chờ 2 giây load tin nhắn trên UI
                                    area = wa_page.locator("#main").first
                                    if area.is_visible(timeout=3000):
                                        area.screenshot(path=f_path)
                                    else:
                                        wa_page.screenshot(path=f_path)
                                    # Persist to SQLite before saving scan history.
                                    for intake_msg_id, intake_text in c_intake:
                                        process_extracted_screenshot_async(
                                            header_name, f_path, "whatsapp",
                                            str(chat['id']) + "\0" + str(intake_msg_id), intake_text)
                                        history["messages"].add(intake_msg_id)
                                    save_whatsapp_history(history)
                                except Exception as screenshot_err:
                                    print(f"❌ [WA] Lỗi chụp/lưu đơn hàng: {screenshot_err}")
                                    for intake_msg_id, _ in c_intake:
                                        history["messages"].discard(intake_msg_id)
                                    save_whatsapp_history(history)
                            elif c_texts:
                                print(f"⏭️  [WA] Bỏ qua (lưu ý in ấn / không có SL/báo giá): {header_name} — {combined_wa[:60]}")
                                save_whatsapp_history(history)
                            else:
                                save_whatsapp_history(history)
                    except Exception as e:
                        print(f"⚠️ [WA] Lỗi xử lý '{chat_name}': {e}")
            print(f"✅ [WA #{cycle}] Chu kỳ hoàn tất — chờ chu kỳ tiếp theo.")
        except Exception as e:
            _tls.wa_browser = None
            print(f"❌ [WA #{cycle}] Lỗi nghiêm trọng: {e}")
        finally:
            report_status_to_nas(False)


def send_whatsapp_worker():
    while True:
        task = wa_send_queue.get()
        while rt.SYSTEM_STATUS == "PAUSED":
            time.sleep(2)
        customer_name = task['customer_name']
        message = task['message']
        # Kiểm tra chặn gửi tin nhắn WhatsApp (whatsapp_disable_reply_groups)
        is_disabled = whatsapp_reply_disabled(customer_name, "WA-Worker")
        if is_disabled:
            print(f"⏭️  [WA-Worker] Bỏ qua gửi tin nhắn vì nhóm nằm trong whatsapp_disable_reply_groups (Khách: {customer_name})")
            wa_send_queue.task_done()
            time.sleep(1)
            continue
        report_status_to_nas(True, f"Gửi WhatsApp -> {customer_name}")
        with whatsapp_lock:
            try:
                wa_page = _get_wa_page()
                if wa_page:
                    # 1. Fetch all chats to python
                    chats = wa_page.evaluate("""async () => {

                        for (let i = 0; i < 20; i++) {

                            if (typeof WPP !== 'undefined' && WPP.isReady) break;

                            await new Promise(r => setTimeout(r, 500));

                        }

                        if (typeof WPP === 'undefined' || !WPP.isReady) return [];

                        let cList = [];

                        if (typeof WPP.chat.getChats === 'function') {

                            cList = await WPP.chat.getChats();

                        } else if (typeof WPP.chat.list === 'function') {

                            cList = await WPP.chat.list();

                        } else if (WPP.whatsapp && WPP.whatsapp.ChatStore) {

                            cList = WPP.whatsapp.ChatStore.getModels();

                        }

                        return cList.map(c => ({

                            id: c.id._serialized,

                            name: c.name || c.formattedTitle || c.id.user

                        }));

                    }""")
                    if not chats:
                        print(f"❌ [WA-SEND] WPP chưa sẵn sàng hoặc không tải được chats.")
                    else:
                        # 2. Tìm match theo name_match của python
                        target_id = None
                        target_name = None
                        for c in chats:
                            if name_match(customer_name, c['name']):
                                target_id = c['id']
                                target_name = c['name']
                                break
                        # 3. Gửi tin nhắn
                        if target_id:
                            success = wa_page.evaluate(f"""async () => {{

                                try {{

                                    await WPP.chat.sendTextMessage('{target_id}', `{message}`);

                                    return true;

                                }} catch (e) {{ return false; }}

                            }}""")
                            if success:
                                print(f"✅ [WA-SEND] Đã gửi API cho: '{target_name}' (Yêu cầu: '{customer_name}')")
                                # Thoát khỏi nhóm sau khi gửi tin nhắn WhatsApp
                                try:
                                    wa_page.evaluate("""async () => {

                                        if (typeof WPP !== 'undefined' && WPP.chat && typeof WPP.chat.closeChat === 'function') {

                                            await WPP.chat.closeChat();

                                        }

                                    }""")
                                except: pass
                            else:
                                print(f"❌ [WA-SEND] API WPP lỗi khi gửi cho '{target_name}'")
                        else:
                            print(f"❌ [WA-SEND] Không tìm thấy '{customer_name}' trong danh sách chat WA.")
            except Exception as e:
                _tls.wa_browser = None
                print(f"❌ [WA-SEND] Lỗi kỹ thuật khi gửi tin: {e}")
            finally:
                report_status_to_nas(False)
        wa_send_queue.task_done()
        time.sleep(1)


def whatsapp_status():
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{WHATSAPP_CDP_PORT}", timeout=5000)
            context = browser.contexts[0]
            all_urls = [pg.url for pg in context.pages]
            wa_page = next((pg for pg in context.pages if "web.whatsapp.com" in pg.url), None)
            connected = wa_page is not None
            browser.close()
            return {"connected": connected, "port": WHATSAPP_CDP_PORT, "all_page_urls": all_urls}
    except Exception as e:
        return {"connected": False, "port": WHATSAPP_CDP_PORT, "error": str(e)}


def whatsapp_debug():
    """Chẩn đoán chi tiết: tìm kiếm TOÀN BỘ document để biết tin nhắn nằm ở đâu."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{WHATSAPP_CDP_PORT}", timeout=5000)
            context = browser.contexts[0]
            wa_page = next((pg for pg in context.pages if "web.whatsapp.com" in pg.url), None)
            if not wa_page:
                browser.close()
                return {"error": "Không thấy tab WhatsApp Web"}
            info = wa_page.evaluate("""() => {

                let main = document.querySelector('#main');

                let global = {

                    data_pre_plain_text:  document.querySelectorAll('[data-pre-plain-text]').length,

                    copyable_text_pre:    document.querySelectorAll('.copyable-text[data-pre-plain-text]').length,

                    data_id_any:          document.querySelectorAll('[data-id]').length,

                    message_in_any:       document.querySelectorAll('.message-in').length,

                    msg_container_any:    document.querySelectorAll('[data-testid="msg-container"]').length,

                    span_dir_ltr:         document.querySelectorAll('span[dir="ltr"]').length,

                    role_row_global:      document.querySelectorAll('[role="row"]').length,

                };

                let allTestids = Array.from(new Set(

                    Array.from(document.querySelectorAll('[data-testid]'))

                         .map(el => el.getAttribute('data-testid'))

                )).slice(0, 50);

                let mainInfo = null;

                if (main) {

                    mainInfo = {

                        exists: true,

                        innerHTML_length: main.innerHTML.length,

                        children_count: main.children.length,

                        role_row:    main.querySelectorAll('[role="row"]').length,

                        data_pre:    main.querySelectorAll('[data-pre-plain-text]').length,

                        data_id:     main.querySelectorAll('[data-id]').length,

                        span_ltr:    main.querySelectorAll('span[dir="ltr"]').length,

                        testids_inside: Array.from(new Set(

                            Array.from(main.querySelectorAll('[data-testid]'))

                                 .map(el => el.getAttribute('data-testid'))

                        )).slice(0, 30),

                        first_child_tag: main.firstElementChild ? main.firstElementChild.tagName : null,

                        first_child_html: main.firstElementChild

                            ? main.firstElementChild.outerHTML.substring(0, 800) : null,

                    };

                }

                let wppStatus = typeof WPP !== 'undefined' ? { isReady: WPP.isReady, hasChat: !!WPP.chat } : "WPP Undefined";
                let sampleChats = [];
                try {
                    let pane = document.querySelector('#pane-side') || document.querySelector('[data-testid="chat-list"]');
                    if (pane) {
                        let rows = pane.querySelectorAll('div[tabindex="-1"], div[role="listitem"], [data-testid^="list-item-"]');
                        rows.forEach(r => {
                            let titleEl = r.querySelector('[data-testid="cell-frame-title"]') || r.querySelector('span[title]') || r.querySelector('span[dir="auto"]');
                            let unreadEl = r.querySelector('[data-testid="icon-unread-count"]') || r.querySelector('span[aria-label*="unread"]') || r.querySelector('span[aria-label*="chưa đọc"]');
                            if (titleEl) {
                                sampleChats.push({
                                    title: titleEl.getAttribute('title') || titleEl.innerText,
                                    hasUnreadBadge: !!unreadEl,
                                    unreadText: unreadEl ? unreadEl.innerText : null
                                });
                            }
                        });
                    }
                } catch(e) {}

                return {
                    page_title: document.title,
                    wpp_status: wppStatus,
                    global_counts: global,
                    all_testids_in_doc: allTestids,
                    sample_chats_found: sampleChats.slice(0, 15),
                    main_info: mainInfo,
                    sample_message: sampleMsg
                };
            }""")
            browser.close()
            return info
    except Exception as e:
        return {"error": str(e)}


def wa_sidebar_diagnose():
    """

    Chẩn đoán sidebar WhatsApp: trả về HTML thô của pane, các item, và item có unread.

    Gọi từ bất kỳ máy nào qua: http://<IP_MAY_CHU>:8000/api/wa-sidebar

    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{WHATSAPP_CDP_PORT}", timeout=5000)
            context = browser.contexts[0]
            wa_page = next((pg for pg in context.pages if "web.whatsapp.com" in pg.url), None)
            if not wa_page:
                browser.close()
                return {"error": "Không thấy tab WhatsApp Web", "all_urls": [pg.url for pg in context.pages]}
            result = wa_page.evaluate("""() => {

                // 1. Tìm sidebar pane

                let pane = document.querySelector('#pane-side')

                    || document.querySelector('[data-testid="chat-list"]')

                    || document.querySelector('[aria-label="Chat list"]')

                    || document.querySelector('[aria-label="Danh s\\u00e1ch chat"]');

                // Thu thập tất cả aria-label trong trang để debug

                let allAriaLabels = Array.from(document.querySelectorAll('[aria-label]'))

                    .map(el => ({ tag: el.tagName, id: el.id, label: el.getAttribute('aria-label') }))

                    .filter(x => x.label)

                    .slice(0, 40);

                if (!pane) {

                    return {

                        pane_found: false,

                        all_aria_labels: allAriaLabels,

                        body_top_html: document.body.innerHTML.substring(0, 1000)

                    };

                }

                // 2. Thử từng selector để tìm list items

                let selectorResults = {};

                let selectors = [

                    '[role="listitem"]', '[role="row"]',

                    '[data-testid="cell-frame-container"]',

                    'div[tabindex="-1"]', 'div[tabindex="0"]', 'li'

                ];

                let bestItems = [];

                let bestSel = '';

                for (let sel of selectors) {

                    let found = pane.querySelectorAll(sel);

                    selectorResults[sel] = found.length;

                    if (found.length > bestItems.length) {

                        bestItems = Array.from(found);

                        bestSel = sel;

                    }

                }

                // 3. HTML của item đầu tiên (tối đa 3000 chars)

                let firstItemHtml = bestItems.length > 0

                    ? bestItems[0].outerHTML.substring(0, 3000)

                    : null;

                // 4. Tìm item có "Chưa đọc" hoặc unread badge

                let unreadItemHtml = null;

                let unreadMethod = null;

                for (let item of bestItems) {

                    // Text "Chưa đọc"

                    let hasText = Array.from(item.querySelectorAll('span')).some(s => {

                        let t = s.innerText.trim().toLowerCase();

                        return t === 'ch\\u01b0a \\u0111\\u1ecd c' || t === 'ch\\u01b0a\\u0111\\u1ecdc' || t.includes('ch\\u01b0a \\u0111\\u1ecd') || t === 'unread';

                    });

                    // Badge số

                    let hasNum = Array.from(item.querySelectorAll('span')).some(s =>

                        /^\\d+$/.test(s.innerText.trim()) && parseInt(s.innerText.trim()) > 0

                    );

                    // data-testid

                    let hasTestid = !!(item.querySelector('[data-testid*="unread"]') || item.querySelector('[data-testid="icon-unread-count"]'));

                    if (hasText || hasNum || hasTestid) {

                        unreadItemHtml = item.outerHTML.substring(0, 4000);

                        unreadMethod = hasText ? 'text' : hasNum ? 'number' : 'testid';

                        break;

                    }

                }

                // 5. Tất cả span text trong item đầu để xem tên được lấy thế nào

                let firstItemSpans = bestItems.length > 0

                    ? Array.from(bestItems[0].querySelectorAll('span'))

                        .map(s => ({

                            text: s.innerText.trim().substring(0, 60),

                            title: s.getAttribute('title'),

                            dir: s.getAttribute('dir'),

                            classes: s.className.substring(0, 80)

                        }))

                        .filter(s => s.text)

                    : [];

                return {

                    pane_found: true,

                    pane_id: pane.id,

                    pane_aria: pane.getAttribute('aria-label'),

                    selector_results: selectorResults,

                    best_selector: bestSel,

                    total_items: bestItems.length,

                    first_item_html: firstItemHtml,

                    first_item_spans: firstItemSpans,

                    unread_item_found: !!unreadItemHtml,

                    unread_detect_method: unreadMethod,

                    unread_item_html: unreadItemHtml

                };

            }""")
            browser.close()
            return result
    except Exception as e:
        return {"error": str(e)}


def capture_chat_screenshot(customer_name, f_path):
    """Mở chat WhatsApp theo tên và chụp khung chat. Trả về (success, error_msg); endpoint lo tạm dừng quét."""
    success = False
    error_msg = "Lỗi không xác định"
    with whatsapp_lock:
        browser = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://localhost:{WHATSAPP_CDP_PORT}", timeout=10000)
                page = next((pg for pg in browser.contexts[0].pages if "web.whatsapp.com" in pg.url), None)
                if page:
                    page.bring_to_front()
                    _inject_wppconnect(page)
                    chats = page.evaluate("""async () => {

                        if (typeof WPP === 'undefined' || !WPP.isReady) return [];

                        let cList = [];

                        if (typeof WPP.chat.getChats === 'function') {

                            cList = await WPP.chat.getChats();

                        } else if (typeof WPP.chat.list === 'function') {

                            cList = await WPP.chat.list();

                        }

                        return cList.map(c => ({

                            id: c.id._serialized,

                            name: c.name || c.formattedTitle || c.id.user

                        }));

                    }""")
                    target_id = None
                    target_name = None
                    for c in chats:
                        if name_match(customer_name, c['name']):
                            target_id = c['id']
                            target_name = c['name']
                            break
                    if target_id:
                        # Mở chat bằng WPPConnect
                        page.evaluate(f"async () => {{ await WPP.chat.openChatBottom('{target_id}'); }}")
                        time.sleep(2) # Chờ load tin nhắn
                        area = page.locator("#main").first
                        if area.is_visible(timeout=2000):
                            area.screenshot(path=f_path)
                        else:
                            page.screenshot(path=f_path)
                        success = True
                    else:
                        error_msg = f"Không tìm thấy khách hàng '{customer_name}' trên WhatsApp"
                else:
                    error_msg = "Không tìm thấy tab WhatsApp Web đang mở"
        except Exception as e:
            error_msg = str(e)
            print(f"❌ [SCREENSHOT-WA] Lỗi: {e}")
        finally:
            if browser:
                try: browser.close()
                except: pass
    return success, error_msg


def trigger_scan():
    _wa_scan_event.set()


def start():
    threading.Thread(target=scan_whatsapp_loop, daemon=True).start()
    _wa_scan_event.set()  # Kick ngay lần đầu khi khởi động
    threading.Thread(target=send_whatsapp_worker, daemon=True).start()
