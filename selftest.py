# -*- coding: utf-8 -*-
"""自检脚本：离屏渲染蛐蛐的几种状态并截图，用来肉眼验收形象。

用法: python selftest.py
产物: preview_idle.png / preview_chirp.png / preview_jump.png / preview_levelup.png
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

import main as M

# 所有角色/装备/设置写入临时目录，预览不触碰玩家进度。
import atexit
from test_support import isolated_game_data
_test_data = isolated_game_data()
_test_root = _test_data.__enter__()
atexit.register(_test_data.__exit__, None, None, None)

# 自检时不需要全局钩子和托盘
M.Pet._init_hook = lambda self: None
M.Pet._init_tray = lambda self: None

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
app = QApplication(sys.argv)
pet = M.Pet()
pet.show()


def shot(name: str) -> None:
    img = QImage(M.WIN_W, M.WIN_H, QImage.Format.Format_ARGB32)
    img.fill(QColor("#EDF2E4"))
    p = QPainter(img)
    p.drawPixmap(0, 0, pet.grab())
    p.end()
    path = os.path.join(OUT_DIR, name)
    img.save(path)
    print("saved", path)


def step_idle() -> None:
    shot("preview_idle.png")
    pet.cricket.chirp = 0.6
    QTimer.singleShot(120, step_chirp)


def step_chirp() -> None:
    shot("preview_chirp.png")
    pet.cricket.chirp = 0.0
    pet.cricket.hop(150)
    QTimer.singleShot(140, step_jump)


def step_jump() -> None:
    shot("preview_jump.png")
    pet.level = 5
    pet.xp = 96
    pet.levelup_t = 1.5
    pet.floats.append(["+12", 12.0, 0.0, 0.9, 1.0, QColor("#FFFFFF")])
    QTimer.singleShot(120, step_levelup)


def step_levelup() -> None:
    shot("preview_levelup.png")
    app.quit()


QTimer.singleShot(400, step_idle)
sys.exit(app.exec())
