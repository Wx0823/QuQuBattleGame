# -*- coding: utf-8 -*-
"""启动桌宠并抓一张桌面截图，用于验收实际显示效果。"""

import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtWidgets import QApplication
from PIL import ImageGrab

import main as M

M.SAVE_FILE = os.path.join(HERE, "smoke_save.json")

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
pet = M.Pet()
pet.place_initial()
pet.show()


def grab() -> None:
    time.sleep(1.2)
    img = ImageGrab.grab()
    img.save(os.path.join(HERE, "desktop_live.png"))
    w, h = img.size
    img.crop((w - 900, h - 700, w, h)).save(os.path.join(HERE, "desktop_live_crop.png"))
    print("grabbed", img.size)
    app.quit()


threading.Thread(target=grab, daemon=True).start()
app.exec()
print("done")
