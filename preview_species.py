# -*- coding: utf-8 -*-
"""离屏渲染：不同品种的配色对比 + 属性面板，用于验收数值表驱动效果。

用法: python preview_species.py
产物: docs/preview_species.png, docs/preview_panel.png
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

import main as M

M.Pet._init_hook = lambda self: None
M.Pet._init_tray = lambda self: None

app = QApplication(sys.argv)

pet = M.Pet()
pet.level = 12
pet.talents = ["t001", "t006"]
pet.recompute()

ids = ["c001", "c002", "c003", "c004", "c005", "c006"]
cols, rows = 3, 2
img = QImage(M.WIN_W * cols, M.WIN_H * rows, QImage.Format.Format_ARGB32)
img.fill(QColor("#EDF2E4"))
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

for i, sid in enumerate(ids):
    sp = pet.db.species(sid)
    if not sp:
        continue
    pet.set_species(sid)
    pet.repaint()
    x = (i % cols) * M.WIN_W
    y = (i // cols) * M.WIN_H
    p.drawPixmap(x, y, pet.grab())
    p.setPen(QColor("#3A4A2A"))
    p.drawText(x + 10, y + 18, f"{sp['名称']} {sp['主色']}")
p.end()

out1 = os.path.join(HERE, "docs", "preview_species.png")
img.save(out1)
print("saved", out1)

# 属性面板
pet.set_species("c001")
pet.talents = ["t001", "t006"]
pet.recompute()
panel = pet.panel
# 必须先真正 show 一次，Qt 才会完成布局计算，否则抓图会出现文字重叠
panel.show()
app.processEvents()
panel.refresh()
app.processEvents()
pimg = QImage(panel.W, panel.H, QImage.Format.Format_ARGB32)
pimg.fill(QColor(30, 36, 46))
panel.render(pimg)
out2 = os.path.join(HERE, "docs", "preview_panel.png")
pimg.save(out2)
panel.hide()
print("saved", out2)
