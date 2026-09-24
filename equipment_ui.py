"""装备面板宿主：布局与交互编排；数据状态、池化格子各自独立。"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import equipment
from equipment_viewmodel import EquipmentViewModel
from equipment_widgets import InventoryGrid, _ui_color, scroll_area, slot_icon_pixmap
from panel import CardPanel
from ui_theme import PANEL_CSS, button_css
from stats import StatsDB, fmt_num


class EquipmentPanel(CardPanel):
    W, H = 960, 640

    def __init__(self, pet):
        super().__init__("蛐蛐装备", self.W, self.H)
        self.pet = pet
        self.db = StatsDB()
        self.model = EquipmentViewModel(self.db, pet)
        self.setStyleSheet(PANEL_CSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)
        self.build_header(root)
        self.lbl_power = self._label("", accent=True)
        root.addWidget(self.lbl_power)
        self.lbl_exp = self._label("")
        root.addWidget(self.lbl_exp)
        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # 左栏独立滚动，配置表新增部位不会挤压背包或操作区。
        loadout = QWidget()
        left = QVBoxLayout(loadout)
        left.setContentsMargins(12, 12, 12, 12)
        left.addWidget(self._label("属性总览", heading=True))
        self.lbl_stats = self._label("")
        left.addWidget(self.lbl_stats)
        left.addWidget(self.sep())
        left.addWidget(self._label("当前穿戴", heading=True))
        self.slot_layout = QVBoxLayout()
        left.addLayout(self.slot_layout)
        self.slot_btns = {}
        left.addStretch()
        self.loadout_area = scroll_area(loadout)
        body.addWidget(self.loadout_area, 3)

        center = QVBoxLayout()
        center.addWidget(self._label("装备背包", heading=True))
        filters = QHBoxLayout()
        self.slot_filter = QComboBox()
        self.quality_filter = QComboBox()
        self.sort_filter = QComboBox()
        self.slot_filter.setAccessibleName("按部位筛选")
        self.quality_filter.setAccessibleName("按品质筛选")
        self.sort_filter.setAccessibleName("背包排序")
        self.sort_filter.addItem("最新获得", "newest")
        self.sort_filter.addItem("品质优先", "quality")
        for combo in (self.slot_filter, self.quality_filter, self.sort_filter):
            filters.addWidget(combo)
            combo.currentIndexChanged.connect(self._on_filter)
        center.addLayout(filters)
        self.lbl_inv = self._label("")
        center.addWidget(self.lbl_inv)
        self.inventory_grid = InventoryGrid(self.db)
        self.inventory_grid.selected.connect(self._on_item)
        self.inv_area = scroll_area(self.inventory_grid)
        self.inv_area.setMinimumWidth(338)
        center.addWidget(self.inv_area, 1)
        body.addLayout(center, 4)

        right = QVBoxLayout()
        right.addWidget(self._label("装备详情", heading=True))
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        self.detail_icon = QLabel()
        self.detail_icon.setFixedHeight(100)
        self.detail_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_layout.addWidget(self.detail_icon)
        self.lbl_detail = self._label("")
        self.lbl_detail.setTextFormat(Qt.TextFormat.RichText)
        detail_layout.addWidget(self.lbl_detail)
        detail_layout.addStretch()
        self.detail_area = scroll_area(detail)
        right.addWidget(self.detail_area, 1)
        self.btn_action = QPushButton("选择一件装备")
        self.btn_action.setMinimumHeight(40)
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setStyleSheet(button_css(primary=True))
        self.btn_action.clicked.connect(self._on_action)
        right.addWidget(self.btn_action)
        body.addLayout(right, 3)
        root.addWidget(self._label("金色角标表示已穿戴 · 掉落每秒自动刷新 · 战斗中换装，下场战斗生效"))
        self._poll = QTimer(self)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._poll_refresh)
        self._config_snapshot = None
        self.refresh()

    @staticmethod
    def _label(text, heading=False, accent=False):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        if heading:
            label.setStyleSheet("font-size:14px;font-weight:600;color:#EEE6D6;")
        elif accent:
            label.setStyleSheet("font-size:15px;color:#D6B778;")
        return label

    @property
    def sel_uid(self):
        return self.model.selected_uid

    def _sync_config(self):
        data = self.db.data
        snapshot = repr((data.get('_装备部位顺序'), data.get('装备部位'),
                         data.get('_装备品质顺序'), data.get('装备品质')))
        if snapshot == self._config_snapshot:
            return
        self._config_snapshot = snapshot
        order = data.get('_装备部位顺序', [])
        for sid, btn in self.slot_btns.items():
            btn.hide()
            self.slot_layout.removeWidget(btn)
        for sid in order:
            if sid not in self.slot_btns:
                btn = QPushButton()
                btn.setMinimumHeight(46)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda checked=False, s=sid: self._on_slot_click(s))
                self.slot_btns[sid] = btn
            self.slot_layout.addWidget(self.slot_btns[sid])
            self.slot_btns[sid].show()
        for combo, title, ids, configs in (
            (self.slot_filter, '全部部位', order, data.get('装备部位', {})),
            (self.quality_filter, '全部品质', data.get('_装备品质顺序', []), data.get('装备品质', {})),
        ):
            selected = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(title, None)
            for key in ids:
                combo.addItem(str(configs.get(key, {}).get('名称', key)), key)
            combo.setCurrentIndex(max(0, combo.findData(selected)))
            combo.blockSignals(False)
        self.model.slot_filter = self.slot_filter.currentData()
        self.model.quality_filter = self.quality_filter.currentData()

    def refresh(self):
        self.model.reload()
        self._render()

    def _render(self):
        self._sync_config()
        eff = self.model.stats()
        species = self.db.species(self.pet.species_id) or {}
        self.lbl_power.setText(
            f"{species.get('名称', '蛐蛐')}  Lv.{self.pet.level}    ·    战力 {fmt_num(round(self.db.power(eff)))}"
            f"    ·    已穿戴 {len(self.model.worn_items())}/{len(self.db.data.get('_装备部位顺序', []))}"
            + ('    ·    下场战斗生效' if getattr(self.pet, '_stage', None) else ''))
        self.lbl_exp.setText(f"升级经验  {getattr(self.pet, 'xp', 0)} / {self.db.exp_need(self.pet.level)}")
        definitions = self.db.data.get('属性定义', {})
        self.lbl_stats.setText('\n'.join(
            f"{conf.get('属性名', attr)}   {fmt_num(eff.get(attr, 0))}"
            for attr, conf in definitions.items() if attr in eff))
        for sid in self.db.data.get('_装备部位顺序', []):
            btn = self.slot_btns[sid]
            name = self.db.data.get('装备部位', {}).get(sid, {}).get('名称', sid)
            item = self.model.items.get(self.model.equipped.get(sid))
            color = _ui_color(equipment.quality_color(self.db, item)) if item else '#8B97A6'
            btn.setText(name + '\n' + (item.get('名称', '') if item else '空槽 · 点击筛选'))
            btn.setToolTip(btn.text())
            btn.setIcon(QIcon(slot_icon_pixmap(name, color)))
            btn.setIconSize(QSize(32, 32))
            btn.setStyleSheet(f'QPushButton{{text-align:left;color:{color};}}')
        visible = self.model.visible_items()
        self.lbl_inv.setText(f"显示 {len(visible)} / {len(self.model.items)} 件" if visible
                             else ('暂无匹配装备，请调整筛选' if self.model.items else '背包为空，挑战副本获得装备'))
        self.inventory_grid.render(visible, self.model.equipped, self.sel_uid)
        self._refresh_detail()

    def _refresh_detail(self):
        item = self.model.selected
        self.btn_action.setEnabled(bool(item))
        if not item:
            self.detail_icon.clear()
            self.lbl_detail.setText('选择背包装备查看词条与换装变化。<br><br>点击左侧穿戴槽可查看当前装备。')
            self.btn_action.setText('选择一件装备')
            return
        color = _ui_color(equipment.quality_color(self.db, item))
        slot_name = self.db.data.get('装备部位', {}).get(item['slot'], {}).get('名称', item['slot'])
        self.detail_icon.setPixmap(slot_icon_pixmap(slot_name, color, size=96))
        worn = self.model.equipped.get(item['slot']) == item['uid']
        lines = [f"<b><font color='{color}'>{escape(item.get('名称', '装备'))}</font></b>",
                 '已穿戴' if worn else '背包中', '<br><b>装备词条</b>']
        lines += [escape(('✦ ' if up else '· ') + text + ('（稀有词条）' if up else ''))
                  for text, up in equipment.item_affix_text(self.db, item)]
        if not worn:
            lines.append('<br><b>替换后属性变化</b>')
            delta = self.model.comparison()
            for attr, value in delta.items():
                name = self.db.data.get('属性定义', {}).get(attr, {}).get('属性名', attr)
                tint = '#D6B778' if value > 0 else '#FF9D91'
                lines.append(f"<font color='{tint}'>{escape(str(name))} {value:+.1f}</font>")
            if not delta:
                lines.append('属性无变化')
        self.lbl_detail.setText('<br>'.join(lines))
        self.btn_action.setText('卸下装备' if worn else '替换装备' if self.model.equipped.get(item['slot']) else '穿戴装备')

    def _on_filter(self):
        self.model.slot_filter = self.slot_filter.currentData()
        self.model.quality_filter = self.quality_filter.currentData()
        self.model.sort = self.sort_filter.currentData()
        self._render()
        self.inv_area.verticalScrollBar().setValue(0)

    def _on_item(self, uid):
        self.model.selected_uid = uid
        self._render()

    def _on_slot_click(self, sid):
        self.model.selected_uid = self.model.equipped.get(sid)
        self.quality_filter.setCurrentIndex(0)
        self.slot_filter.setCurrentIndex(self.slot_filter.findData(sid))
        self.refresh()

    def _on_action(self):
        self.model.toggle_selected()
        self.refresh()

    def _poll_refresh(self):
        if self.model.reload():
            self._render()

    def showEvent(self, event):
        self.refresh()
        self._poll.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._poll.stop()
        super().hideEvent(event)

    def show_near(self, anchor):
        # 使用所在屏幕的可用区域，避免宽面板越过屏幕边缘或任务栏。
        screen = anchor.screen().availableGeometry()
        self.setFixedSize(min(self.W, screen.width()), min(self.H, screen.height()))
        g = anchor.frameGeometry()
        x = g.left() - self.width() - 12
        if x < screen.left():
            x = g.right() + 12
        x = max(screen.left(), min(x, screen.right() - self.width() + 1))
        y = max(screen.top(), min(g.top(), screen.bottom() - self.height() + 1))
        self.move(x, y)
        self.show()
        self.raise_()
