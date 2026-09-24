"""装备面板宿主：布局与交互编排；数据状态、池化格子各自独立。"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QGridLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

import equipment
from equipment_viewmodel import EquipmentViewModel
from equipment_widgets import InventoryGrid, _ui_color, scroll_area, slot_icon_pixmap
from panel import CardPanel
from ui_theme import PANEL_CSS, button_css
from stats import StatsDB, fmt_num
from attribute_help import describe_attribute


class EquipmentPanel(CardPanel):
    W, H = 380, 620

    def __init__(self, pet):
        super().__init__("蛐蛐档案", self.W, self.H)
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
        navigation = QHBoxLayout()
        self.btn_stats_page = QPushButton("属性")
        self.btn_equipment_page = QPushButton("装备")
        for button in (self.btn_stats_page, self.btn_equipment_page):
            button.setCheckable(True)
            button.setMinimumHeight(36)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            navigation.addWidget(button)
        root.addLayout(navigation)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.stats_page = QWidget()
        stats_layout = QVBoxLayout(self.stats_page)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_exp = self._label("")
        stats_layout.addWidget(self.lbl_exp)
        stats_layout.addWidget(self._label("点击属性，了解它的作用"))
        self.stat_content = QWidget()
        self.stat_grid = QGridLayout(self.stat_content)
        self.stat_grid.setContentsMargins(8, 8, 8, 8)
        self.stat_grid.setSpacing(8)
        self.stat_buttons = {}
        self.stats_area = scroll_area(self.stat_content)
        stats_layout.addWidget(self.stats_area, 1)
        self.help_title = self._label("血量", heading=True)
        self.help_text = self._label("")
        self.help_text.setMinimumHeight(90)
        stats_layout.addWidget(self.help_title)
        stats_layout.addWidget(self.help_text)
        self.selected_attribute = 'hp'
        self.pages.addWidget(self.stats_page)

        self.equipment_page = QWidget()
        loadout_root = QVBoxLayout(self.equipment_page)
        loadout_root.setContentsMargins(0, 0, 0, 0)
        loadout_root.addWidget(self._label("当前穿戴", heading=True))
        loadout_root.addWidget(self._label("点击部位，在右侧背包挑选与更换装备"))
        loadout = QWidget()
        self.slot_layout = QGridLayout(loadout)
        self.slot_layout.setContentsMargins(8, 8, 8, 8)
        self.slot_layout.setSpacing(10)
        self.slot_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.slot_btns = {}
        self.loadout_area = scroll_area(loadout)
        loadout_root.addWidget(self.loadout_area, 1)
        loadout_root.addWidget(self._label("战斗中更换装备，下场战斗生效"))
        self.pages.addWidget(self.equipment_page)
        self.btn_stats_page.clicked.connect(lambda: self.set_page(0))
        self.btn_equipment_page.clicked.connect(lambda: self.set_page(1))

        self.drawer = CardPanel("部位背包", 400, self.H)
        self.drawer.setParent(self, self.drawer.windowFlags())
        self.drawer.setStyleSheet(PANEL_CSS)
        bag = QVBoxLayout(self.drawer)
        bag.setContentsMargins(16, 14, 16, 14)
        bag.setSpacing(8)
        self.drawer.build_header(bag)
        self.drawer_title = self._label("选择部位", heading=True)
        bag.addWidget(self.drawer_title)
        filters = QHBoxLayout()
        self.slot_filter = QComboBox(self.drawer)
        self.slot_filter.hide()  # 部位由装备页入口决定。
        self.quality_filter = QComboBox()
        self.sort_filter = QComboBox()
        self.quality_filter.setAccessibleName("按品质筛选")
        self.sort_filter.setAccessibleName("背包排序")
        self.sort_filter.addItem("最新获得", "newest")
        self.sort_filter.addItem("品质优先", "quality")
        for combo in (self.quality_filter, self.sort_filter):
            filters.addWidget(combo)
            combo.currentIndexChanged.connect(self._on_filter)
        self.slot_filter.currentIndexChanged.connect(self._on_filter)
        bag.addLayout(filters)
        self.lbl_inv = self._label("")
        bag.addWidget(self.lbl_inv)
        self.inventory_grid = InventoryGrid(self.db)
        self.inventory_grid.selected.connect(self._on_item)
        self.inv_area = scroll_area(self.inventory_grid)
        self.inv_area.setMinimumHeight(150)
        bag.addWidget(self.inv_area, 3)
        detail = QWidget()
        detail_layout = QHBoxLayout(detail)
        detail_layout.setContentsMargins(10, 10, 10, 10)
        self.detail_icon = QLabel()
        self.detail_icon.setFixedSize(70, 80)
        self.detail_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_layout.addWidget(self.detail_icon)
        self.lbl_detail = self._label("")
        self.lbl_detail.setTextFormat(Qt.TextFormat.RichText)
        detail_layout.addWidget(self.lbl_detail, 1)
        self.detail_area = scroll_area(detail)
        self.detail_area.setMinimumHeight(130)
        bag.addWidget(self.detail_area, 2)
        self.btn_action = QPushButton("选择一件装备")
        self.btn_action.setMinimumHeight(38)
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setStyleSheet(button_css(primary=True))
        self.btn_action.clicked.connect(self._on_action)
        bag.addWidget(self.btn_action)
        bag.addWidget(self._label("绿箭头：每部位最佳无损提升 · 金角标：已穿戴"))
        self.drawer.hide()
        self.set_page(1)
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
        for index, sid in enumerate(order):
            if sid not in self.slot_btns:
                btn = QPushButton()
                btn.setMinimumHeight(100)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda checked=False, s=sid: self._on_slot_click(s))
                self.slot_btns[sid] = btn
            self.slot_layout.addWidget(self.slot_btns[sid], index // 2, index % 2)
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
        for index, (attr, conf) in enumerate((a, c) for a, c in definitions.items() if a in eff):
            if attr not in self.stat_buttons:
                button = QPushButton()
                button.setMinimumHeight(40)
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(lambda checked=False, key=attr: self._show_attribute(key))
                self.stat_buttons[attr] = button
                self.stat_grid.addWidget(button, index // 2, index % 2)
            self.stat_buttons[attr].setText(f"{conf.get('属性名', attr)}   {fmt_num(eff[attr])}")
            self.stat_buttons[attr].setToolTip("点击查看属性用途")
        self._show_attribute(self.selected_attribute)
        for sid in self.db.data.get('_装备部位顺序', []):
            btn = self.slot_btns[sid]
            name = self.db.data.get('装备部位', {}).get(sid, {}).get('名称', sid)
            item = self.model.items.get(self.model.equipped.get(sid))
            color = _ui_color(equipment.quality_color(self.db, item)) if item else '#8B97A6'
            btn.setText(name + '\n' + (item.get('名称', '') if item else '未穿戴 · 打开背包'))
            btn.setToolTip(btn.text())
            btn.setIcon(QIcon(slot_icon_pixmap(name, color)))
            btn.setIconSize(QSize(32, 32))
            btn.setStyleSheet(f'QPushButton{{text-align:left;color:{color};}}')
        visible = self.model.visible_items()
        self.lbl_inv.setText(f"显示 {len(visible)} / {len(self.model.items)} 件" if visible
                             else ('暂无匹配装备，请调整筛选' if self.model.items else '背包为空，挑战副本获得装备'))
        self.inventory_grid.render(visible, self.model.equipped, self.sel_uid, self.model.upgrades())
        self._refresh_detail()

    def _refresh_detail(self):
        item = self.model.selected
        self.btn_action.setEnabled(bool(item))
        if not item:
            self.detail_icon.clear()
            self.lbl_detail.setText('选择背包装备查看词条与换装变化。<br><br>选择上方装备，查看属性变化后确认穿戴。')
            self.btn_action.setText('选择一件装备')
            return
        color = _ui_color(equipment.quality_color(self.db, item))
        slot_name = self.db.data.get('装备部位', {}).get(item['slot'], {}).get('名称', item['slot'])
        self.detail_icon.setPixmap(slot_icon_pixmap(slot_name, color, size=64))
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
        self.drawer_title.setText(self.db.data['装备部位'][sid].get('名称', sid) + ' · 背包')
        self.set_page(1)
        self._place_drawer()
        self.drawer.show()
        self.drawer.raise_()

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
        self.drawer.hide()
        super().hideEvent(event)

    def show_near(self, anchor):
        # 使用所在屏幕的可用区域，避免宽面板越过屏幕边缘或任务栏。
        screen = anchor.screen().availableGeometry()
        self.setFixedSize(min(self.W, screen.width()), min(self.H, screen.height()))
        from window_layout import place_panel
        place_panel(self, anchor)
        self.show()
        self.raise_()

    def set_page(self, index):
        self.pages.setCurrentIndex(index)
        self.btn_stats_page.setChecked(index == 0)
        self.btn_equipment_page.setChecked(index == 1)
        self.btn_stats_page.setStyleSheet(button_css(primary=index == 0))
        self.btn_equipment_page.setStyleSheet(button_css(primary=index == 1))
        if index == 0:
            self.drawer.hide()

    def _show_attribute(self, key):
        self.selected_attribute = key
        conf = self.db.data.get('属性定义', {}).get(key, {})
        self.help_title.setText(conf.get('属性名', key) + ' · 属性说明')
        self.help_text.setText(describe_attribute(self.db, key))
        for attr, button in self.stat_buttons.items():
            button.setChecked(attr == key)
            button.setStyleSheet(button_css(primary=attr == key))

    def _place_drawer(self):
        if getattr(self, '_placing_drawer', False):
            return
        self._placing_drawer = True
        try:
            screen = self.screen().availableGeometry()
            # 屏幕右侧不足时整组左移，保持背包紧邻装备页右侧。
            dw = min(400, max(320, screen.width()-self.width()-8))
            self.drawer.setFixedSize(dw, self.height())
            total = self.width()+8+dw
            x = max(screen.left(), min(self.x(), screen.right()-total+1))
            y = max(screen.top(), min(self.y(), screen.bottom()-self.height()+1))
            self.move(x, y)
            self.drawer.move(x+self.width()+8, y)
        finally:
            self._placing_drawer = False

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'drawer') and self.drawer.isVisible():
            self._place_drawer()
