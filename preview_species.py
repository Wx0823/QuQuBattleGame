# -*- coding: utf-8 -*-
"""离屏渲染预览：品种配色 / 缩放对比 / 属性面板 / 设置面板。

用法: python preview_species.py
产物: docs/ 下的 preview_*.png
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

import main as M

# 所有角色/装备/设置写入临时目录，预览不触碰玩家进度。
import atexit
from test_support import isolated_game_data
_test_data = isolated_game_data()
_test_root = _test_data.__enter__()
atexit.register(_test_data.__exit__, None, None, None)

M.Pet._init_hook = lambda self: None
M.Pet._init_tray = lambda self: None

DOCS = os.path.join(HERE, "docs")
os.makedirs(DOCS, exist_ok=True)

app = QApplication(sys.argv)
pet = M.Pet()
pet.level = 12
pet.talents = ["t001", "t006"]
pet.recompute()


def grab_panel(panel, name: str) -> None:
    """面板必须先真正 show 一次，Qt 才会完成布局计算。"""
    panel.show()
    app.processEvents()
    if hasattr(panel, "refresh"):
        panel.refresh()
        app.processEvents()
    img = QImage(panel.width(), panel.height(), QImage.Format.Format_ARGB32)
    img.fill(QColor(30, 36, 46))
    panel.render(img)
    path = os.path.join(DOCS, name)
    img.save(path)
    panel.hide()
    print("saved", path)


# ---------- 1. 品种配色对比 ----------
ids = ["c001", "c002", "c003", "c004", "c005", "c006"]
cols, rows = 3, 2
img = QImage(M.WIN_W * cols, M.WIN_H * rows, QImage.Format.Format_ARGB32)
img.fill(QColor("#EDF2E4"))
p = QPainter(img)
for i, sid in enumerate(ids):
    sp = pet.db.species(sid)
    if not sp:
        continue
    pet.set_species(sid)
    pet.repaint()
    x = (i % cols) * M.WIN_W
    y = (i // cols) * M.WIN_H
    p.drawPixmap(x, y, pet.grab())
p.end()
img.save(os.path.join(DOCS, "preview_species.png"))
print("saved preview_species.png")

# ---------- 2. 缩放对比 ----------
pet.set_species("c001")
pet.repaint()
cell, h = 320, 360
img2 = QImage(cell * 3, h, QImage.Format.Format_ARGB32)
img2.fill(QColor("#EDF2E4"))
p = QPainter(img2)
for i, z in enumerate([0.7, 1.0, 1.5]):
    pet.set_zoom(z)
    pet.repaint()
    px = pet.grab()
    # grab() 返回的是物理像素（高分屏 dpr>1），居中排版要用逻辑尺寸
    dpr = px.devicePixelRatio() or 1.0
    lw, lh = int(px.width() / dpr), int(px.height() / dpr)
    p.drawPixmap(i * cell + (cell - lw) // 2, h - lh, px)
    p.setPen(QColor("#3A4A2A"))
    p.drawText(i * cell + 12, 24, f"{int(z * 100)}%   窗口 {lw} x {lh}")
p.end()
img2.save(os.path.join(DOCS, "preview_zoom.png"))
print("saved preview_zoom.png")

# ---------- 3. 面板 ----------
pet.set_zoom(1.0)
pet.set_species("c001")
pet.repaint()
grab_panel(pet.panel, "preview_panel.png")
grab_panel(pet.settings_panel, "preview_settings.png")
