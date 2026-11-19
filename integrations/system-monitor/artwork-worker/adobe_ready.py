"""Retry only COM activation/readiness. Never retry an export after dispatch."""
def ready_command(progid, variable):
    if progid not in ('Photoshop.Application','Illustrator.Application') or variable not in ('$app','$ai','$a'):
        raise ValueError('Unsupported Adobe application')
    kill_ghost = "Get-Process Illustrator -ErrorAction SilentlyContinue | Where-Object { [string]::IsNullOrWhiteSpace($_.MainWindowTitle) } | Stop-Process -Force -ErrorAction SilentlyContinue; " if progid == 'Illustrator.Application' else ""
    return ("$ErrorActionPreference='Stop'; $adobeDeadline=[DateTime]::UtcNow.AddSeconds(120); "
            "$adobeReady=$false; " + variable + "=$null; "
            "while([DateTime]::UtcNow -lt $adobeDeadline){ try { "
            "if($null -eq " + variable + "){ " + variable + "=New-Object -ComObject " + progid + " }; "
            "$adobeVersion=" + variable + ".Version; "
            "if($adobeVersion){$adobeReady=$true;break} "
            "} catch { " + kill_ghost + "}; Start-Sleep -Seconds 2 }; "
            "if(-not $adobeReady){throw 'Adobe chưa sẵn sàng sau 120 giây; kiểm tra hộp thoại hoặc đăng nhập ứng dụng'}; ")
