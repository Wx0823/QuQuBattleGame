# -*- coding: utf-8 -*-
"""冒烟测试：完整走一遍 main 的启动路径（钩子+托盘+窗口），1.2 秒后自动退出。

任何异常都会被 excepthook 写进 error.log。
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import main as M

APP_DIR = os.path.dirname(os.path.abspath(__file__))
M.LOG_FILE = os.path.join(APP_DIR, "smoke_error.log")
if os.path.exists(M.LOG_FILE):
    os.remove(M.LOG_FILE)

M.SAVE_FILE = os.path.join(APP_DIR, "smoke_save.json")

sys.excepthook = M._excepthook
app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

pet = M.Pet()
pet.place_initial()
pet.show()
print("shown at", pet.x(), pet.y(), "visible:", pet.isVisible())
print("tray available:", pet.tray.isSystemTrayAvailable() if hasattr(pet, "tray") else "N/A")
print("kb listener alive:", pet.kb.is_alive())
print("ms listener alive:", pet.ms.is_alive())

pet._add_xp(37)
print("level", pet.level, "xp", pet.xp)

QTimer.singleShot(1200, app.quit)
rc = app.exec()
try:
    pet.kb.stop()
    pet.ms.stop()
except Exception:
    pass
print("exit code", rc)
print("error log:", os.path.exists(M.LOG_FILE))
if os.path.exists(M.LOG_FILE):
    print(open(M.LOG_FILE, encoding="utf-8").read())
