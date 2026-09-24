# -*- coding: utf-8 -*-
"""启动桌宠并抓一张桌面截图，用于验收实际显示效果。"""

import os
import sys
import atexit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PIL import ImageGrab

import main as M
from test_support import isolated_game_data

_sandbox = isolated_game_data()
_sandbox.__enter__()
atexit.register(_sandbox.__exit__, None, None, None)

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
pet = M.Pet()
app.aboutToQuit.connect(pet._shutdown)
pet.place_initial()
pet.show()


def grab() -> None:
    img = ImageGrab.grab()
    img.save(os.path.join(HERE, "desktop_live.png"))
    w, h = img.size
    img.crop((w - 900, h - 700, w, h)).save(os.path.join(HERE, "desktop_live_crop.png"))
    print("grabbed", img.size)
    app.quit()


QTimer.singleShot(1200, grab)
app.exec()
print("done")
