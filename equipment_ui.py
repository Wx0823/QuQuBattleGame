# -*- coding: utf-8 -*-
"""蛐蛐属性 · 装备面板：属性总览 + 6 部位装备槽 + 方块格子背包 + 穿戴操作。

背包为统一格子视图（不按部位过滤），面板打开期间每秒自动刷新
（战斗中掉落 1 秒内进格子）。战斗中更换装备：当前战斗结束后生效。
"""

from __future__ import annotations

from PySide6.QtCore import QSize, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QGridLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

import equipment
from panel import CardPanel
from stats import StatsDB, fmt_num


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
        p.drawRoundedRect(QRectF(pt(9, 8), pt(22, 25)), 5 * s, 5 * s)
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
        p.drawEllipse(QRectF(pt(30, 4), pt(6, 6)))
    else:
        # 未知部位的兜底：圆盾 + 部位首字
        p.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 70)))
        p.drawEllipse(QRectF(pt(7, 7), pt(26, 26)))
        p.setPen(QPen(c, 2))
        p.drawText(QRectF(pt(0, 0), pt(40, 40)),
                   Qt.AlignmentFlag.AlignCenter, name[:1])

    if equipped:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#F2C14E")))
        p.drawPolygon([pt(40, 0), pt(40, 10 * s), pt(40 - 10 * s, 0)])

    p.end()
    _ICON_CACHE[key] = pix
    return pix


class EquipmentPanel(CardPanel):
    """属性 + 装备槽 + 格子背包。"""

    W, H = 430, 620
    GRID_COLS = 6

    def __init__(self, pet):
        CardPanel.__init__(self, "蛐蛐属性 · 装备", self.W, self.H)
        self.pet = pet
        self.db = StatsDB()
        self.sel_uid = None
        self._inv_snapshot = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(6)
        self.build_header(root)

        # ---- 属性总览 ----
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color:#E8EDF2; font-size:12px;")
        root.addWidget(self.lbl_stats)
        self.lbl_power = QLabel("")
        self.lbl_power.setStyleSheet("color:#8FD14F; font-size:11px;")
        root.addWidget(self.lbl_power)

        root.addSpacing(4)
        root.addWidget(self.sep())

        # ---- 装备槽（2 列 × 3 行）----
        grid = QGridLayout()
        grid.setSpacing(5)
        self.slot_btns = {}
        order = self.db.data.get("_装备部位顺序", [])
        for k, sid in enumerate(order):
            conf = self.db.data.get("装备部位", {}).get(sid, {})
            b = QPushButton()
            b.setStyleSheet(
                "QPushButton{text-align:left; padding:5px 8px; font-size:11px;"
                "color:#E8EDF2; background:rgba(255,255,255,0.06);"
                "border:1px solid rgba(255,255,255,0.14); border-radius:6px;}"
                "QPushButton:hover{background:rgba(143,209,79,0.22);}")
            b.clicked.connect(lambda _=False, s=sid: self._on_slot_click(s))
            grid.addWidget(b, k // 2, k % 2)
            self.slot_btns[sid] = b
        root.addLayout(grid)

        # ---- 格子背包 ----
        self.lbl_inv = QLabel("背包（点击格子查看 / 穿戴）")
        self.lbl_inv.setStyleSheet("color:#8B97A6; font-size:11px;")
        root.addWidget(self.lbl_inv)
        self.inv_area = QScrollArea()
        self.inv_area.setWidgetResizable(True)
        self.inv_area.setStyleSheet(
            "QScrollArea{border:1px solid rgba(255,255,255,0.10);"
            "border-radius:6px; background:#232733;}"
            "QScrollArea>QWidget>QWidget{background:#232733;}")
        self.inv_inner = QWidget()
        self.inv_grid = QGridLayout(self.inv_inner)
        self.inv_grid.setContentsMargins(6, 6, 6, 6)
        self.inv_grid.setSpacing(5)
        self._cells: list = []   # 格子池：只建一次，之后复用（避免重建渲染时序坑）
        self.inv_area.setWidget(self.inv_inner)
        self.inv_area.setFixedHeight(230)
        root.addWidget(self.inv_area)

        # ---- 词条详情 + 操作 ----
        self.lbl_detail = QLabel("选中格子查看装备词条")
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setStyleSheet("color:#C9D2DC; font-size:12px;")
        root.addWidget(self.lbl_detail)

        self.btn_action = QPushButton("装备")
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setStyleSheet(
            "QPushButton{color:#1E2430; background:rgba(143,209,79,0.9);"
            "border:none; border-radius:6px; padding:7px; font-size:12px;}"
            "QPushButton:hover{background:rgba(143,209,79,1.0);}"
            "QPushButton:disabled{color:#55606E; background:rgba(255,255,255,0.08);}")
        self.btn_action.clicked.connect(self._on_action)
        self.btn_action.setEnabled(False)
        root.addWidget(self.btn_action)

        note = QLabel("战斗中掉落 1 秒内自动进包；战斗中更换装备，本场结束后生效")
        note.setWordWrap(True)
        note.setStyleSheet("color:#55606E; font-size:10px;")
        root.addWidget(note)

        # 打开期间自动轮询（战斗中掉落自动进格子）
        self._poll = QTimer(self)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._poll_refresh)

    def showEvent(self, e) -> None:
        self._poll.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:
        self._poll.stop()
        super().hideEvent(e)

    def _poll_refresh(self) -> None:
        """战斗中掉落 → 背包自动刷新（数据无变化时跳过，避免打断选中）。"""
        snap = self._inventory_snapshot()
        if snap != self._inv_snapshot:
            self.refresh()

    def _inventory_snapshot(self) -> str:
        inv = equipment._read_inv()
        return f"{len(inv.get('items', {}))}:{sorted(inv.get('equipped', {}).values())}"

    # ---------- 刷新 ----------

    def refresh(self) -> None:
        pet = self.pet
        eff = equipment.effective_stats(
            self.db, pet.species_id, pet.level, pet.talents)
        self.lbl_stats.setText(
            f"血量 {fmt_num(eff.get('hp', 0))}   攻击 {fmt_num(eff.get('atk', 0))}   "
            f"护甲 {fmt_num(eff.get('arm', 0))}   速度 {fmt_num(eff.get('spd', 0))}   "
            f"耐力 {fmt_num(eff.get('sta', 0))}")
        power = (0.4 * eff.get("hp", 0) + 3.0 * eff.get("atk", 0)
                 + 2.0 * eff.get("arm", 0) + 2.0 * eff.get("spd", 0)
                 + 2.0 * eff.get("crit", 0) + 1.5 * eff.get("pen", 0)
                 + 0.5 * eff.get("guts", 0))
        equipped = equipment.get_equipped()
        self.lbl_power.setText(
            f"战力 {fmt_num(round(power))}   ·   已装备 "
            f"{len(equipped)}/{len(self.db.data.get('_装备部位顺序', []))} 件"
            + ("   （战斗中：下场生效）" if getattr(pet, "_stage", None) else ""))

        equipped_items = {it["slot"]: it for it in equipment.equipped_items()}
        for sid, btn in self.slot_btns.items():
            conf = self.db.data.get("装备部位", {}).get(sid, {})
            slot_name = conf.get("名称", sid)
            it = equipped_items.get(sid)
            if it:
                color = _ui_color(equipment.quality_color(self.db, it))
                btn.setText(f"{slot_name}｜{it.get('名称', '')}")
                btn.setStyleSheet(
                    f"QPushButton{{text-align:left; padding:5px 8px; font-size:11px;"
                    f"color:{color}; background:rgba(255,255,255,0.06);"
                    f"border:1px solid {color}; border-radius:6px;}}"
                    f"QPushButton:hover{{background:rgba(143,209,79,0.22);}}")
            else:
                btn.setText(f"{slot_name}｜空")
                btn.setStyleSheet(
                    "QPushButton{text-align:left; padding:5px 8px; font-size:11px;"
                    "color:#55606E; background:rgba(255,255,255,0.06);"
                    "border:1px solid rgba(255,255,255,0.14); border-radius:6px;}"
                    "QPushButton:hover{background:rgba(143,209,79,0.22);}")

        self._refresh_inventory_grid(equipped)
        self._refresh_detail()
        self._inv_snapshot = self._inventory_snapshot()

    def _refresh_inventory_grid(self, equipped_items: dict) -> None:
        """统一格子背包：固定 6 列网格（不足补深色空槽），装备格显示部位图标。"""
        items = sorted(equipment.get_items().values(),
                       key=lambda x: -int(x.get("uid", 0)))
        if self.sel_uid and not any(it["uid"] == self.sel_uid for it in items):
            self.sel_uid = None
        equipped_uids = set(equipment.get_equipped().values())

        total_slots = max(36, -(-len(items) // self.GRID_COLS) * self.GRID_COLS)

        # 格子池扩容（只建一次，之后复用）
        while len(self._cells) < total_slots:
            cell = QPushButton()
            cell.setFixedSize(48, 48)
            cell.setCheckable(True)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            idx = len(self._cells)
            self.inv_grid.addWidget(cell, idx // self.GRID_COLS,
                                    idx % self.GRID_COLS)
            cell.clicked.connect(
                lambda _=False, c=cell: self._on_item(getattr(c, "_uid", None)))
            self._cells.append(cell)

        EMPTY_CSS = ("QPushButton{background:#1B2129;"
                     "border:1px solid rgba(255,255,255,26); border-radius:7px;}"
                     "QPushButton:hover{background:#232A34;}")

        for k, cell in enumerate(self._cells):
            if k >= total_slots:
                cell.setVisible(False)
                continue
            cell.setVisible(True)
            if k < len(items):
                it = items[k]
                uid = it["uid"]
                cell._uid = uid
                is_eq = uid in equipped_uids
                color = _ui_color(equipment.quality_color(self.db, it))
                slot_conf = self.db.data.get("装备部位", {}).get(it["slot"], {})
                pix = slot_icon_pixmap(slot_conf.get("名称", it["slot"]),
                                       color, is_eq, 40)
                cell.setIcon(QIcon(pix))
                cell.setIconSize(QSize(36, 36))
                dark = color == "#E8B23A" and it["quality"] == "q07"
                bg = "#15161C" if dark else "#2A3040"
                border = f"2px solid {color}" if is_eq else f"1px solid {color}60"
                cell.setStyleSheet(
                    f"QPushButton{{background:{bg};"
                    f"border:{border}; border-radius:7px;}}"
                    f"QPushButton:hover{{background:#333B4A;}}"
                    f"QPushButton:checked{{background:#3A4A33;}}")
                aff = equipment.item_affix_text(self.db, it)
                cell.setToolTip(
                    f"<b><font color='{color}'>{it.get('名称', '')}</font></b>"
                    + ("（装备中）" if is_eq else "")
                    + "<br>" + "<br>".join(t for t, _u in aff))
            else:
                cell._uid = None
                cell.setIcon(QIcon())
                cell.setToolTip("")
                cell.setStyleSheet(EMPTY_CSS)
            cell.setChecked(self.sel_uid == cell._uid)

    def _refresh_detail(self) -> None:
        it = equipment.get_items().get(self.sel_uid) if self.sel_uid else None
        if not it:
            self.lbl_detail.setText("选中格子查看装备词条")
            self.btn_action.setEnabled(False)
            self.btn_action.setText("装备")
            return
        color = _ui_color(equipment.quality_color(self.db, it))
        aff = equipment.item_affix_text(self.db, it)
        slot_conf = self.db.data.get("装备部位", {}).get(it["slot"], {})
        equipped_now = equipment.get_equipped().get(it["slot"]) == it["uid"]
        lines = []
        for txt, up in aff:
            mark = "✦" if up else "·"
            lines.append(f"{mark} {txt}" + ("（稀有词条）" if up else ""))
        self.lbl_detail.setText(
            f"<b><font color='{color}'>{it.get('名称', '')}</font></b>"
            f"&nbsp;·&nbsp;{slot_conf.get('名称', '')}部位<br>"
            + "<br>".join(lines))
        self.btn_action.setEnabled(True)
        self.btn_action.setText("卸下" if equipped_now else "装备")

    # ---------- 操作 ----------

    def _on_slot_click(self, sid: str) -> None:
        """点击装备槽：查看该槽位已穿戴的装备（可卸下）。"""
        uid = equipment.get_equipped().get(sid)
        if uid:
            self.sel_uid = uid
            self.refresh()

    def _on_item(self, uid: str) -> None:
        self.sel_uid = uid
        self.refresh()

    def _on_action(self) -> None:
        it = equipment.get_items().get(self.sel_uid) if self.sel_uid else None
        if not it:
            return
        slot = it["slot"]
        if equipment.get_equipped().get(slot) == self.sel_uid:
            equipment.unequip(slot)
        else:
            equipment.equip(self.sel_uid)
        self.refresh()
