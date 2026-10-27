Set shell = CreateObject("WScript.Shell")
result = shell.Run("""C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"" -NoProfile -NonInteractive -WindowStyle Hidden -File ""C:\Users\Admin\AppData\Local\PhucThanh\ZaloDesktopReader\Watchdog-Sender.ps1""", 0, True)
WScript.Quit result
