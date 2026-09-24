# -*- coding: utf-8 -*-
"""蛐蛐设置：数据与设置面板。

设置项保存在 data/settings.json，与存档分开，避免重置蛐蛐时把偏好也清掉。
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QVBoxLayout)

from panel import CardPanel
from stats import StatsDB
from persistence import write_json

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "data", "settings.json")

ZOOM_MIN, ZOOM_MAX = 60, 200  # 百分比

SLIDER_CSS = """
QSlider::groove:horizontal{height:4px; background:rgba(255,255,255,0.12); border-radius:2px;}
QSlider::sub-page:horizontal{background:#C8A76B; border-radius:2px;}
QSlider::handle:horizontal{width:14px; margin:-5px 0; background:#C8A76B;
    border-radius:7px; border:none;}
QSlider::handle:horizontal:hover{background:#A5E063;}
"""

CHECK_CSS = """
QCheckBox{color:#EEE6D6; font-size:12px; spacing:8px;}
QCheckBox::indicator{width:16px; height:16px; border-radius:4px;
    border:1px solid rgba(255,255,255,0.28); background:transparent;}
QCheckBox::indicator:checked{background:#C8A76B; border-color:#C8A76B;}
"""

COMBO_CSS = """
QComboBox{color:#EEE6D6; background:rgba(255,255,255,0.06);
    border:1px solid rgba(255,255,255,0.12); border-radius:6px;
    padding:6px 10px; font-size:12px; min-width:120px;}
QComboBox::drop-down{border:none; width:18px;}
QComboBox QAbstractItemView{background:#1E2430; color:#EEE6D6;
    selection-background-color:#C8A76B; selection-color:#1E2430;
    border:1px solid rgba(255,255,255,0.12);}
"""


class Settings:
    """桌宠的外观与行为偏好。"""

    def __init__(self) -> None:
        self.zoom = 1.0
        self.show_bar = True
        self.always_top = True
        self.species_id = "c001"
        self.load()

    def load(self) -> None:
        if not os.path.exists(PATH):
            return
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.zoom = max(ZOOM_MIN/100, min(ZOOM_MAX/100, float(d.get("zoom", 1.0))))
            self.show_bar = bool(d.get("show_bar", True))
            self.always_top = bool(d.get("always_top", True))
            self.species_id = str(d.get("species_id", "c001"))
        except Exception:
            pass

    def save(self) -> None:
        write_json(PATH, {"zoom": self.zoom, "show_bar": self.show_bar,
                          "always_top": self.always_top, "species_id": self.species_id})


class SettingsPanel(CardPanel):
    W, H = 320, 396

    def __init__(self, pet):
        super().__init__("蛐蛐设置", self.W, self.H)
        self.pet = pet
        self.cfg = pet.settings
        self.db = StatsDB()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(8)
        self.build_header(root)

        # ---- 蛐蛐大小 ----
        row = QHBoxLayout()
        t = QLabel("蛐蛐大小")
        t.setStyleSheet("color:#EEE6D6; font-size:12px;")
        row.addWidget(t)
        row.addStretch()
        self.zoom_val = QLabel(f"{int(self.cfg.zoom * 100)}%")
        self.zoom_val.setStyleSheet("color:#C8A76B; font-size:12px; font-weight:600;")
        row.addWidget(self.zoom_val)
        root.addLayout(row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(ZOOM_MIN, ZOOM_MAX)
        self.slider.setValue(int(self.cfg.zoom * 100))
        self.slider.setStyleSheet(SLIDER_CSS)
        self.slider.valueChanged.connect(self._on_zoom)
        root.addWidget(self.slider)

        hint = QLabel("拖动即时预览，松手后自动记住")
        hint.setStyleSheet("color:#8A9085; font-size:11px;")
        root.addWidget(hint)

        root.addSpacing(6)
        root.addWidget(self.sep())
        root.addSpacing(6)

        # ---- 开关项 ----
        self.cb_bar = QCheckBox("显示经验条")
        self.cb_bar.setStyleSheet(CHECK_CSS)
        self.cb_bar.setChecked(self.cfg.show_bar)
        self.cb_bar.stateChanged.connect(self._on_bar)
        root.addWidget(self.cb_bar)

        self.cb_top = QCheckBox("始终显示在最前")
        self.cb_top.setStyleSheet(CHECK_CSS)
        self.cb_top.setChecked(self.cfg.always_top)
        self.cb_top.stateChanged.connect(self._on_top)
        root.addWidget(self.cb_top)

        root.addSpacing(6)
        root.addWidget(self.sep())
        root.addSpacing(6)

        # ---- 品种 ----
        row2 = QHBoxLayout()
        t2 = QLabel("蛐蛐品种")
        t2.setStyleSheet("color:#EEE6D6; font-size:12px;")
        row2.addWidget(t2)
        row2.addStretch()
        self.combo = QComboBox()
        self.combo.setStyleSheet(COMBO_CSS)
        for sid in self.db.species_ids():
            sp = self.db.species(sid) or {}
            self.combo.addItem(f"{sp.get('名称', sid)}（{sp.get('稀有度', '')}）", sid)
        idx = self.combo.findData(self.pet.species_id)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.currentIndexChanged.connect(self._on_species)
        row2.addWidget(self.combo)
        root.addLayout(row2)

        hint2 = QLabel("临时入口，后续改为孵化 / 捕捉获得")
        hint2.setStyleSheet("color:#8A9085; font-size:11px;")
        root.addWidget(hint2)

        root.addStretch()
        root.addWidget(self.sep())
        root.addSpacing(8)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        css = (
            "QPushButton{color:#AAA698; background:rgba(255,255,255,0.06);"
            "border:1px solid rgba(255,255,255,0.12); border-radius:6px; padding:7px; font-size:12px;}"
            "QPushButton:hover{color:#FFFFFF; background:rgba(255,255,255,0.12);}"
        )
        btn_def = QPushButton("恢复默认设置")
        btn_def.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_def.setStyleSheet(css)
        btn_def.clicked.connect(self._on_reset)
        btns.addWidget(btn_def)

        btn_pet = QPushButton("重置蛐蛐")
        btn_pet.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pet.setStyleSheet(css)
        btn_pet.clicked.connect(self._on_reset_pet)
        btns.addWidget(btn_pet)
        root.addLayout(btns)

        note = QLabel("重置会清空等级、经验及副本进度（含通关与解锁）\n品种、装备、位置与设置保留")
        note.setStyleSheet("color:#8A9085; font-size:11px;")
        root.addWidget(note)

    # ---------- 回调 ----------

    def sync_species(self) -> None:
        """展示角色当前品种；刷新选项不能触发换种或写档。"""
        blocked = self.combo.blockSignals(True)
        try:
            self.combo.setCurrentIndex(self.combo.findData(self.pet.species_id))
        finally:
            self.combo.blockSignals(blocked)

    def show_near(self, anchor) -> None:
        self.sync_species()
        super().show_near(anchor)

    def _on_zoom(self, v: int) -> None:
        self.zoom_val.setText(f"{v}%")
        self.cfg.zoom = v / 100.0
        # 必须走 set_zoom 同步 pet.zoom（apply_zoom 读的是 pet.zoom），
        # 之前只改 cfg 导致滑块动了蛐蛐没反应，改完也没保存
        self.pet.set_zoom(v / 100.0)
        self.cfg.save()

    def _on_bar(self, state: int) -> None:
        self.cfg.show_bar = bool(state)
        self.pet.apply_flags()
        self.cfg.save()

    def _on_top(self, state: int) -> None:
        self.cfg.always_top = bool(state)
        self.pet.apply_flags()
        self.cfg.save()

    def _on_species(self, idx: int) -> None:
        sid = self.combo.itemData(idx)
        if not sid:
            return
        self.pet.set_species(sid)
        if self.pet.panel.isVisible():
            self.pet.panel.refresh()

    def _on_reset_pet(self) -> None:
        self.pet._reset()
        if self.pet.panel.isVisible():
            self.pet.panel.refresh()

    def _on_reset(self) -> None:
        self.cfg.zoom = 1.0
        self.cfg.show_bar = True
        self.cfg.always_top = True
        self.cfg.save()
        self.slider.setValue(100)
        self.cb_bar.setChecked(True)
        self.cb_top.setChecked(True)
        self.pet.set_zoom(1.0)
        self.pet.apply_flags()
