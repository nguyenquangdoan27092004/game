import os
import sys


def app_dir():
    """Thư mục chứa app: cạnh file .exe (khi đóng gói) hoặc cạnh script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def fix_console_encoding():
    """Ép stdout/stderr dùng UTF-8 để in tiếng Việt không bị lỗi trên Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
