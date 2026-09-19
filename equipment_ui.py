# -*- coding: utf-8 -*-
"""蛐蛐属性 · 装备面板：属性总览 + 6 部位装备槽 + 背包 + 穿戴操作。

支持战斗中打开更换 —— 属性在当前战斗结束后生效（战斗体开打时快照）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt

import equipment
from panel import CardPanel
from stats import StatsDB, fmt_num


class EquipmentPanel(CardPanel):
    """属性 + 装备槽 + 背包。"""

    W, H = 430, 620

    def __init__(self, pet):
        CardPanel.__init__(self, "蛐蛐属性 · 装备", self.W, self.H)
        self.pet = pet
        self.db = StatsDB()
        self.sel_slot = (self.db.data.get("_装备部位顺序") or ["p01"])[0]
        self.sel_uid = None

        from PySide6.QtWidgets import (QGridLayout, QLabel, QPushButton,
                                       QScrollArea, QVBoxLayout)
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
                "QPushButton:hover{background:rgba(143,209,79,0.22);}"
                "QPushButton:checked{border-color:rgba(143,209,79,220);}")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, s=sid: self._on_slot(s))
            grid.addWidget(b, k // 2, k % 2)
            self.slot_btns[sid] = b
        root.addLayout(grid)

        # ---- 背包列表 ----
        self.lbl_inv = QLabel("背包")
        self.lbl_inv.setStyleSheet("color:#8B97A6; font-size:11px;")
        root.addWidget(self.lbl_inv)
        self.inv_area = QScrollArea()
        self.inv_area.setWidgetResizable(True)
        self.inv_area.setStyleSheet(
            "QScrollArea{border:1px solid rgba(255,255,255,0.10);"
            "border-radius:6px; background:rgba(0,0,0,0.25);}")
        self.inv_inner = QWidget()
        self.inv_layout = QVBoxLayout(self.inv_inner)
        self.inv_layout.setContentsMargins(6, 6, 6, 6)
        self.inv_layout.setSpacing(4)
        self.inv_layout.addStretch()
        self.inv_area.setWidget(self.inv_inner)
        root.addWidget(self.inv_area, 1)

        # ---- 词条详情 + 操作 ----
        self.lbl_detail = QLabel("选中装备查看词条")
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
        root.addWidget(self.btn_action)

        note = QLabel("战斗中更换装备：当前战斗结束后生效")
        note.setStyleSheet("color:#55606E; font-size:10px;")
        root.addWidget(note)

        self.refresh()

    # ---------- 刷新 ----------

    def refresh(self) -> None:
        import math
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
        equip_bonus_n = len(equipment.get_equipped())
        self.lbl_power.setText(
            f"战力 {fmt_num(round(power))}   ·   已装备 {equip_bonus_n}/"
            f"{len(self.db.data.get('_装备部位顺序', []))} 件"
            + ("   （战斗中：下场生效）" if getattr(pet, "_stage", None) else ""))

        equipped = {it["slot"]: it for it in equipment.equipped_items()}
        for sid, btn in self.slot_btns.items():
            conf = self.db.data.get("装备部位", {}).get(sid, {})
            slot_name = conf.get("名称", sid)
            it = equipped.get(sid)
            if it:
                color = equipment.quality_color(self.db, it)
                btn.setText(f"{slot_name}｜{it.get('名称', '')}")
                btn.setStyleSheet(
                    f"QPushButton{{text-align:left; padding:5px 8px; font-size:11px;"
                    f"color:{color}; background:rgba(255,255,255,0.06);"
                    f"border:1px solid {color}; border-radius:6px;}}"
                    f"QPushButton:hover{{background:rgba(143,209,79,0.22);}}"
                    f"QPushButton:checked{{border-color:rgba(143,209,79,220);}}")
            else:
                btn.setText(f"{slot_name}｜空")
                btn.setStyleSheet(
                    "QPushButton{text-align:left; padding:5px 8px; font-size:11px;"
                    "color:#55606E; background:rgba(255,255,255,0.06);"
                    "border:1px solid rgba(255,255,255,0.14); border-radius:6px;}"
                    "QPushButton:hover{background:rgba(143,209,79,0.22);}"
                    "QPushButton:checked{border-color:rgba(143,209,79,220);}")
            btn.setChecked(sid == self.sel_slot)

        self._refresh_inventory()
        self._refresh_detail()

    def _refresh_inventory(self) -> None:
        """重建背包列表（仅显示当前选中部位的物品）。"""
        from PySide6.QtWidgets import QPushButton
        # 清空旧列表
        while self.inv_layout.count() > 1:   # 最后一个是 stretch
            item = self.inv_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        items = [it for it in equipment.get_items().values()
                 if it["slot"] == self.sel_slot]
        items.sort(key=lambda x: -x["uid"])
        if self.sel_uid and not any(it["uid"] == self.sel_uid for it in items):
            self.sel_uid = None
        if not items:
            empty = QLabel("（空）· 击败副本怪物有概率掉落")
            empty.setStyleSheet("color:#55606E; font-size:11px;")
            self.inv_layout.insertWidget(0, empty)
            return
        for it in items:
            color = equipment.quality_color(self.db, it)
            equipped = equipment.get_equipped().get(self.sel_slot) == it["uid"]
            mark = "〔装备中〕" if equipped else ""
            txt = f"{mark}{it.get('名称', '')}"
            b = QPushButton(txt)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{text-align:left; color:{color};"
                f"background:rgba(255,255,255,0.05); border:none;"
                f"border-radius:4px; padding:5px 8px; font-size:11px;}}"
                f"QPushButton:hover{{background:rgba(143,209,79,0.20);}}")
            b.clicked.connect(lambda _=False, uid=it["uid"]: self._on_item(uid))
            self.inv_layout.insertWidget(self.inv_layout.count() - 1, b)

    def _refresh_detail(self) -> None:
        it = equipment.get_items().get(self.sel_uid) if self.sel_uid else None
        if not it:
            self.lbl_detail.setText("选中背包中的装备查看词条")
            self.btn_action.setEnabled(False)
            self.btn_action.setText("装备")
            return
        color = equipment.quality_color(self.db, it)
        aff = equipment.item_affix_text(self.db, it)
        lines = []
        for txt, up in aff:
            mark = "✦" if up else "·"
            lines.append(f"{mark} {txt}" + ("（稀有词条）" if up else ""))
        equipped_now = equipment.get_equipped().get(self.sel_slot) == it["uid"]
        self.lbl_detail.setText(
            f"<b><font color='{color}'>{it.get('名称', '')}</font></b><br>"
            + "<br>".join(lines))
        self.btn_action.setEnabled(True)
        self.btn_action.setText("卸下" if equipped_now else "装备")

    # ---------- 操作 ----------

    def _on_slot(self, sid: str) -> None:
        self.sel_slot = sid
        self.sel_uid = None
        self.refresh()

    def _on_item(self, uid: str) -> None:
        self.sel_uid = uid
        self.refresh()

    def _on_action(self) -> None:
        if not self.sel_uid:
            return
        it = equipment.get_items().get(self.sel_uid)
        if not it:
            return
        if equipment.get_equipped().get(self.sel_slot) == self.sel_uid:
            equipment.unequip(self.sel_slot)
        else:
            equipment.equip(self.sel_uid)
        self.refresh()
