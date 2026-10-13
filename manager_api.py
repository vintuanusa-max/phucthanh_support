import os
import subprocess
from fastapi import FastAPI
import uvicorn
import signal

app = FastAPI(title="Zalo Bot Manager API")
from communication_api import router as communication_router
app.include_router(communication_router, prefix="/manager")

import sys
PYTHON_EXE = sys.executable
BOT_PY_FILE = "main.py"

current_process = None
chrome_processes = []

def get_running_process():
    global current_process
    if current_process is not None:
        if current_process.poll() is None:
            return current_process
    return None

@app.get("/manager/status")
def get_status():
    proc = get_running_process()
    if proc:
        return {"status": "running", "pid": proc.pid}
    return {"status": "stopped", "pid": None}

@app.post("/manager/start")
def start_bot():
    global current_process, chrome_processes
    proc = get_running_process()
    
    # Ghi nhận thời gian reset mới nhất
    try:
        import time
        with open(os.path.join(os.path.dirname(__file__), "last_reset.txt"), "w") as f:
            f.write(str(time.time()))
    except Exception as e:
        print("Loi khi ghi file last_reset.txt:", e)
        
    if proc:
        return {"status": "running", "message": "Bot is already running", "pid": proc.pid}
    
    # Tu dong mo 2 cua so Chrome cho Zalo va WA
    try:
        import time
        import os
        
        # Tat sach cac tien trinh Chrome cu truoc khi mo de chac chan bat duoc cong debug 9222/9223
        os.system("taskkill /f /im chrome.exe >nul 2>&1")
        time.sleep(1)
        
        def fix_chrome_crash_flag(user_data_dir):
            try:
                pref_path = os.path.join(user_data_dir, "Default", "Preferences")
                if os.path.exists(pref_path):
                    with open(pref_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if '"exit_type":"Crashed"' in content or '"exit_type":"crashed"' in content or 'Crashed' in content:
                        content = content.replace('"exit_type":"Crashed"', '"exit_type":"Normal"')
                        content = content.replace('"exit_type":"crashed"', '"exit_type":"Normal"')
                        content = content.replace('"session_exit_type":"Crashed"', '"session_exit_type":"Normal"')
                        content = content.replace('"session_exit_type":"crashed"', '"session_exit_type":"Normal"')
                        with open(pref_path, "w", encoding="utf-8") as f:
                            f.write(content)
            except Exception as e:
                pass
                
        fix_chrome_crash_flag(r"C:\WA_Session")
        fix_chrome_crash_flag(r"D:\Chrome_Zalo_Bot_Data")

        cmd_chrome_wa = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "--remote-debugging-port=9223",
            r"--user-data-dir=C:\WA_Session",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            "https://web.whatsapp.com/"
        ]
        cmd_chrome_zalo = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "--remote-debugging-port=9222",
            r"--user-data-dir=D:\Chrome_Zalo_Bot_Data",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            "https://chat.zalo.me/"
        ]
        
        p_wa = subprocess.Popen(cmd_chrome_wa)
        chrome_processes.append(p_wa)
        time.sleep(1)
        
        p_zalo = subprocess.Popen(cmd_chrome_zalo)
        chrome_processes.append(p_zalo)
        time.sleep(1)
    except Exception as e:
        print("Loi khi tu dong mo Chrome:", e)

    if os.path.exists(PYTHON_EXE):
        cmd = [PYTHON_EXE, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
    else:
        cmd = ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
    
    # CREATE_NEW_PROCESS_GROUP separates it from the manager's console signals
    current_process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return {"status": "started", "pid": current_process.pid}

@app.post("/manager/stop")
def stop_bot():
    global current_process, chrome_processes
    proc = get_running_process()
    
    # Tat sach cac cua so Chrome da mo qua PID cua session hien tai
    for cp in chrome_processes:
        try:
            os.system(f"taskkill /F /T /PID {cp.pid} >nul 2>&1")
        except:
            pass
    chrome_processes.clear()

    # Diet them qua netstat de dam bao tich hop Chrome tren cong 9222 (Zalo) va 9223 (WhatsApp) duoc dong
    for port in (9222, 9223):
        try:
            ns_out = subprocess.check_output("netstat -ano", shell=True).decode()
            for line in ns_out.splitlines():
                if f":{port}" in line:
                    parts = line.strip().split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit() and pid != '0':
                            os.system(f"taskkill /F /T /PID {pid} >nul 2>&1")
        except:
            pass

    if proc:
        try:
            proc.kill()
        except Exception as e:
            return {"status": "error", "message": str(e)}
        
        current_process = None
        return {"status": "stopped"}
    return {"status": "already_stopped"}

@app.post("/manager/shutdown_pc")
@app.post("/manager/shutdown")
def shutdown_pc():
    print("Received shutdown request. Shutting down PC in 5 seconds...")
    os.system("shutdown /s /t 5")
    return {"status": "shutdown_initiated"}

@app.post("/manager/restart_pc")
@app.post("/manager/restart")
def restart_pc():
    print("Received restart request. Restarting PC in 5 seconds...")
    os.system("shutdown /r /t 5")
    return {"status": "restart_initiated"}

import config_manager

@app.get("/manager/config")
def get_bot_config():
    return config_manager.load_config()

@app.post("/manager/config")
def update_bot_config(config_data: dict):
    success = config_manager.save_config(config_data)
    if success:
        return {"status": "success", "config": config_manager.load_config()}
    return {"status": "error", "message": "Failed to save config"}

@app.on_event("startup")
def startup_event():
    print("Auto-starting Zalo Bot on startup...")
    if os.environ.get("ZALO_REUSE_OPEN_BROWSERS") == "1":
        # Installer retains the authenticated browser sessions already open on MAY1.
        global current_process
        current_process = subprocess.Popen(
            [PYTHON_EXE, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        return
    start_bot()

if __name__ == "__main__":
    print("========================================")
    print("     ZALO BOT MANAGER (PORT 9000)")
    print("========================================")
    uvicorn.run(app, host="0.0.0.0", port=9000)

