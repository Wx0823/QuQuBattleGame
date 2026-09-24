# -*- coding: utf-8 -*-
"""装备基础组件：品质图标、深色滚动区和池化背包格子。"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QSize, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import QGridLayout, QPushButton, QScrollArea, QWidget

import equipment
from art_assets import draw_sprite, manifest, sprite


def _ui_color(color_hex: str) -> str:
    """暗色品质（如黑金）在深色面板上不可读 → 自动改用金色描边显示。"""
    c = QColor(color_hex)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#E8B23A" if lum < 90 else color_hex


# ---------- 部位图标（QPainter 手绘，品质色渲染） ----------

_ICON_CACHE: dict = {}


def slot_icon_pixmap(slot_name: str, color_hex: str,
                     equipped: bool = False, size: int = 40) -> QPixmap:
    """按部位画一枚装备图标。equipped=True 时右上角带金色角标。"""
    key = (slot_name, color_hex, equipped, size)
    pix = _ICON_CACHE.get(key)
    if pix is not None:
        return pix
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = QColor(color_hex)
    s = size / 40.0
    index = manifest().get('slots', {}).get(slot_name)
    if index is not None and draw_sprite(p, sprite('equipment', index),
                                         QRectF(2*s, 1*s, 36*s, 36*s), True):
        p.setPen(QPen(c, 2*s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(11*s, 38*s), QPointF(29*s, 38*s))
        if equipped:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#F2C14E'))
            p.drawPolygon([QPointF(40*s, 0), QPointF(40*s, 10*s), QPointF(30*s, 0)])
        p.end()
        _ICON_CACHE[key] = pix
        return pix

    def pt(x, y):
        return QPointF(x * s, y * s)

    pen = QPen(c, 3.0 * s)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    name = slot_name or ""
    if name.startswith("触须"):
        for sgn in (1, -1):
            path = QPainterPath()
            path.moveTo(pt(20, 33))
            path.quadTo(pt(20 + 12 * sgn, 22), pt(20 + 15 * sgn, 8))
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.drawEllipse(pt(20 + 15 * sgn, 8), 2.2 * s, 2.2 * s)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif name.startswith("牙齿"):
        p.setBrush(QBrush(c))
        p.setPen(Qt.PenStyle.NoPen)
        for x0 in (10, 21):
            fang = QPainterPath()
            fang.moveTo(pt(x0, 8))
            fang.quadTo(pt(x0 + 5, 20), pt(x0 + 4, 32))
            fang.quadTo(pt(x0 + 1, 22), pt(x0 - 2, 11))
            fang.closeSubpath()
            p.drawPath(fang)
    elif name.startswith("前躯"):
        p.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 70)))
        p.drawRoundedRect(QRectF(9 * s, 8 * s, 22 * s, 25 * s), 5 * s, 5 * s)
        p.drawLine(pt(9, 20), pt(31, 20))
    elif name.startswith("后躯"):
        path = QPainterPath()
        path.moveTo(pt(12, 7))
        path.quadTo(pt(26, 14), pt(24, 24))
        p.drawPath(path)
        pen2 = QPen(c, 2.0 * s)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen2)
        p.drawLine(pt(24, 24), pt(14, 33))
        p.drawLine(pt(24, 24), pt(30, 30))
    elif name.startswith("翅膀"):
        wing = QPainterPath()
        wing.moveTo(pt(20, 5))
        wing.quadTo(pt(34, 13), pt(31, 29))
        wing.quadTo(pt(18, 33), pt(10, 25))
        wing.quadTo(pt(11, 11), pt(20, 5))
        p.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 80)))
        p.drawPath(wing)
        p.drawLine(pt(20, 6), pt(17, 30))
        p.drawLine(pt(20, 6), pt(26, 28))
    elif name.startswith("尾巴"):
        path = QPainterPath()
        path.moveTo(pt(10, 32))
        path.quadTo(pt(16, 10), pt(32, 8))
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(c))
        p.drawEllipse(QRectF(30 * s, 4 * s, 6 * s, 6 * s))
    else:
        # 未知部位的兜底：圆盾 + 部位首字
        p.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 70)))
        p.drawEllipse(QRectF(7 * s, 7 * s, 26 * s, 26 * s))
        p.setPen(QPen(c, 2))
        p.drawText(QRectF(pt(0, 0), pt(40, 40)),
                   Qt.AlignmentFlag.AlignCenter, name[:1])

    if equipped:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#F2C14E")))
        p.drawPolygon([pt(40, 0), pt(40, 10), pt(30, 0)])

    p.end()
    _ICON_CACHE[key] = pix
    return pix


def scroll_area(content):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setStyleSheet(
        "QScrollArea{background:#202827; border:1px solid #575543; border-radius:8px;}"
        "QScrollArea>QWidget>QWidget{background:#202827;}"
        "QScrollBar:vertical{background:#202827;width:9px;}"
        "QScrollBar::handle:vertical{background:#8A9085;min-height:24px;border-radius:4px;}"
        "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;}")
    area.viewport().setStyleSheet("background:#202827;")
    area.setWidget(content)
    return area


class InventoryGrid(QWidget):
    """池化格子，增量扩容；过滤和刷新都不销毁部件。"""
    selected = Signal(str)
    COLS = 5

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.cells = []
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(10, 10, 10, 10)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    def render(self, items, equipped, selected_uid, upgrades=()):
        count = max(self.COLS * 4, ((len(items) + self.COLS - 1) // self.COLS) * self.COLS)
        while len(self.cells) < count:
            cell = QPushButton()
            cell.setFixedSize(54, 54)
            cell.setCheckable(True)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.clicked.connect(lambda checked=False, c=cell: self.selected.emit(c._uid))
            index = len(self.cells)
            self.grid.addWidget(cell, index // self.COLS, index % self.COLS)
            self.cells.append(cell)
        worn = set(equipped.values())
        for index, cell in enumerate(self.cells):
            cell.setVisible(index < count)
            item = items[index] if index < len(items) else None
            cell._uid = item["uid"] if item else ""
            cell._upgrade = cell._uid in upgrades
            cell.setEnabled(item is not None)
            cell.setChecked(bool(item) and selected_uid == cell._uid)
            if not item:
                cell.setIcon(QIcon())
                cell.setToolTip("")
                cell.setAccessibleName("空背包格")
                cell.setStyleSheet("QPushButton{background:#19211F;border:1px solid #39463C;border-radius:8px;}")
                continue
            color = _ui_color(equipment.quality_color(self.db, item))
            slot = self.db.data.get("装备部位", {}).get(item["slot"], {}).get("名称", item["slot"])
            icon = slot_icon_pixmap(slot, color, cell._uid in worn)
            if cell._upgrade:
                # 复制缓存图标再叠加，避免箭头污染其他格子与详情图。
                icon = icon.copy()
                painter = QPainter(icon)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor('#16291E'))
                painter.drawRoundedRect(QRectF(25, 0, 15, 20), 4, 4)
                painter.setPen(QPen(QColor('#A8ED79'), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(32.5, 16), QPointF(32.5, 5))
                painter.drawLine(QPointF(28.5, 9), QPointF(32.5, 5))
                painter.drawLine(QPointF(36.5, 9), QPointF(32.5, 5))
                painter.end()
            cell.setIcon(QIcon(icon))
            cell.setIconSize(QSize(40, 40))
            cell.setStyleSheet(
                f"QPushButton{{background:#2A3430;border:1px solid {color};border-radius:8px;}}"
                "QPushButton:hover{background:#424C3D;}"
                "QPushButton:checked{background:#514B35;border:2px solid #E3C581;}"
                "QPushButton:focus{border:2px solid #FFFFFF;}")
            title = item.get("名称", slot) + ("（已装备）" if cell._uid in worn else "")
            if cell._upgrade:
                title += "（可提升：相比同部位装备，属性有提升且无下降）"
            cell.setAccessibleName(title)
            affixes = equipment.item_affix_text(self.db, item)
            cell.setToolTip(escape(title) + "<br>" + "<br>".join(escape(t) for t, _ in affixes))
