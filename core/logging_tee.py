"""Nhân bản stdout/stderr vào bộ đệm log và zalo_bot.log."""
import datetime
import re
import sys
import threading

from core.runtime import LOG_FILE, _log_buffer, _log_lock

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHF]')


class _TeeOutput:
    def __init__(self, original):
        self._orig = original
        self._local = threading.local()
    def write(self, text):
        try:
            self._orig.write(text)
        except:
            try:
                enc = getattr(self._orig, 'encoding', None) or 'utf-8'
                self._orig.write(text.encode(enc, errors='replace').decode(enc))
            except:
                pass
        if not hasattr(self._local, "buf"):
            self._local.buf = ""
        self._local.buf += text
        while "\n" in self._local.buf:
            line, self._local.buf = self._local.buf.split("\n", 1)
            clean = _ANSI_RE.sub("", line).strip()
            if clean and "HTTP/1." not in clean:
                log_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log_line = f"[{log_time}] {clean}"
                with _log_lock:
                    _log_buffer.append(log_line)
                try:
                    log_file_path = LOG_FILE
                    with open(log_file_path, "a", encoding="utf-8") as f:
                        f.write(log_line + "\n")
                except:
                    pass
    def flush(self):
        self._orig.flush()
    def __getattr__(self, name):
        return getattr(self._orig, name)


def install():
    sys.stdout = _TeeOutput(sys.stdout)
    sys.stderr = _TeeOutput(sys.stderr)
