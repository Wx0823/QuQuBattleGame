"""装备 UI 回归：临时背包存档，不改玩家数据。运行 python equipment_ui_checklist.py。"""
import copy
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

import equipment
from equipment_ui import EquipmentPanel
from stats import StatsDB


class EquipmentUITests(unittest.TestCase):
    def test_separate_pages_and_clickable_attribute_help(self):
        size = self.panel.size()
        self.panel.btn_stats_page.click()
        self.assertEqual(self.panel.pages.currentWidget(), self.panel.stats_page)
        self.panel.stat_buttons['hp'].click()
        self.assertIn('生命值', self.panel.help_text.text())
        self.panel.stat_buttons['tough'].click()
        self.assertIn('暴击', self.panel.help_text.text())
        self.panel.btn_equipment_page.click()
        self.assertEqual(self.panel.pages.currentWidget(), self.panel.equipment_page)
        self.assertEqual(size, self.panel.size())

    def test_slot_drawer_docks_filters_equips_and_hides(self):
        first, second = self.db.data['_装备部位顺序'][:2]
        uid = self.item(first, value=14)
        self.item(second, value=20)
        self.panel.refresh()
        self.panel.slot_btns[first].click()
        self.app.processEvents()
        self.assertTrue(self.panel.drawer.isVisible())
        self.assertEqual([it['uid'] for it in self.panel.model.visible_items()], [uid])
        self.assertEqual(self.panel.drawer.x(), self.panel.x()+self.panel.width()+8)
        self.assertEqual(self.panel.drawer.y(), self.panel.y())
        self.panel._on_item(uid)
        self.panel.btn_action.click()
        self.assertEqual(equipment.get_equipped()[first], uid)
        screen = self.panel.screen().availableGeometry()
        self.panel.move(screen.right()-10, screen.top())
        self.app.processEvents()
        self.assertLessEqual(self.panel.drawer.frameGeometry().right(), screen.right())
        self.panel.btn_stats_page.click()
        self.assertFalse(self.panel.drawer.isVisible())
        self.panel.btn_equipment_page.click()
        self.panel.slot_btns[second].click()
        self.assertTrue(all(it['slot'] == second for it in self.panel.model.visible_items()))
        self.panel.hide()
        self.assertFalse(self.panel.drawer.isVisible())

    def test_only_best_upgrade_per_slot_independent_of_filters(self):
        old = self.item(value=9.4)
        weaker = self.item(value=10.3)
        best = self.item(value=11.4)
        other = self.item(slot=self.db.data['_装备部位顺序'][1], value=12)
        equipment.equip(old)
        self.panel.refresh()
        self.assertEqual(self.panel.model.upgrades(), {best, other})
        self.panel.model.sort = 'quality'
        self.panel.model.slot_filter = self.db.data['_装备部位顺序'][0]
        self.assertEqual(self.panel.model.upgrades(), {best, other})
        self.assertNotIn(weaker, self.panel.model.upgrades())
        equipment.equip(best)
        self.panel.refresh()
        self.assertEqual(self.panel.model.upgrades(), {other})

    def test_equal_upgrades_choose_quality_then_stable_uid(self):
        self.item(value=12)
        quality = self.db.data['_装备品质顺序'][1]
        first = self.item(quality=quality, value=12)
        self.item(quality=quality, value=12)
        self.panel.refresh()
        self.assertEqual(self.panel.model.upgrades(), {first})
        # 改变字典顺序仍指向同一件，刷新时不跳动。
        self.panel.model.inventory['items'] = dict(reversed(list(self.panel.model.items.items())))
        self.assertEqual(self.panel.model.upgrades(), {first})
        equipment.equip(first)
        self.panel.refresh()
        self.assertFalse(self.panel.model.upgrades())

    def test_upgrade_arrow_follows_equipment_changes(self):
        old = self.item(value=10)
        better = self.item(value=10.2)
        worse = self.item(quality=self.db.data['_装备品质顺序'][-1], value=9)
        equal = self.item(value=10)
        equipment.equip(old)
        self.panel.refresh()
        self.assertEqual(self.panel.model.upgrades(), {better})
        cells = {c._uid: c for c in self.panel.inventory_grid.cells if c._uid}
        self.assertTrue(cells[better]._upgrade)
        self.assertIn('可提升', cells[better].toolTip())
        self.assertFalse(cells[worse]._upgrade)
        self.assertFalse(cells[equal]._upgrade)
        self.panel._on_item(better)
        self.panel._on_action()
        self.assertFalse(self.panel.model.upgrades())
        self.assertTrue(all(not c._upgrade for c in self.panel.inventory_grid.cells))

    def test_upgrade_does_not_hide_lost_affix_and_supports_empty_slot(self):
        old = self.item(value=10)
        candidate = self.item(value=20)
        equipment.equip(old)
        inventory = equipment.load_inventory()
        first = next(iter(self.db.data['装备词条']))
        attr = self.db.data['装备词条'][first]['属性ID']
        other = next(key for key, row in self.db.data['装备词条'].items() if row['属性ID'] != attr)
        inventory['items'][old]['affixes'].append({'id': other, 'val': 3, 'up': False})
        equipment.save_inventory(inventory)
        self.panel.refresh()
        self.assertNotIn(candidate, self.panel.model.upgrades())
        equipment.unequip(inventory['items'][old]['slot'])
        self.panel.refresh()
        self.assertIn(candidate, self.panel.model.upgrades())

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = 'C:/Windows/Fonts/msyh.ttc'
        if os.path.exists(font):
            QFontDatabase.addApplicationFont(font)
            cls.app.setFont(QFont('Microsoft YaHei', 9))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(equipment, 'INV_PATH', os.path.join(self.temp.name, 'inventory.json'))
        self.path_patch.start()
        self.db = StatsDB()
        self.config = copy.deepcopy(self.db.data)
        self.pet = SimpleNamespace(species_id='c001', level=10, talents=[], _stage=None)
        self.panel = EquipmentPanel(self.pet)
        self.panel.show()
        self.app.processEvents()

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        self.app.processEvents()
        self.db.data = self.config
        self.path_patch.stop()
        self.temp.cleanup()

    def item(self, slot=None, quality=None, value=10):
        return equipment.add_item(self.db, {
            'slot': slot or self.db.data['_装备部位顺序'][0],
            'quality': quality or self.db.data['_装备品质顺序'][0],
            'affixes': [{'id': next(iter(self.db.data['装备词条'])), 'val': value, 'up': False}],
        })

    def test_empty_and_timer(self):
        self.assertFalse(self.panel.btn_action.isEnabled())
        self.assertTrue(all(not c.isEnabled() and not c.isChecked() for c in self.panel.inventory_grid.cells))
        self.assertTrue(self.panel._poll.isActive())
        self.panel.hide()
        self.assertFalse(self.panel._poll.isActive())

    def test_equipping_comparison_and_removal(self):
        first, second = self.item(value=20), self.item(value=7)
        self.panel.refresh()
        self.panel._on_item(first)
        self.panel.btn_action.click()
        self.assertIn(first, equipment.get_equipped().values())
        self.panel._on_item(second)
        self.assertEqual(list(self.panel.model.comparison().values()), [-13.0])
        self.panel.btn_action.click()
        self.assertIn(second, equipment.get_equipped().values())
        self.panel.btn_action.click()
        self.assertEqual(equipment.get_equipped(), {})

    def test_snapshot_content_and_pet_changes(self):
        uid = self.item()
        self.panel.refresh()
        self.panel._on_item(uid)
        cells = list(self.panel.inventory_grid.cells)
        inv = equipment.load_inventory()
        inv['items'][uid]['affixes'][0]['val'] = 123
        equipment.save_inventory(inv)
        self.panel._poll_refresh()
        self.assertIn('123', self.panel.lbl_detail.text())
        self.assertEqual(uid, self.panel.sel_uid)
        self.assertEqual(cells, self.panel.inventory_grid.cells)
        self.pet.level = 11
        self.panel._poll_refresh()
        self.assertIn('Lv.11', self.panel.lbl_power.text())
        inv['items'] = {}
        equipment.save_inventory(inv)
        self.panel._poll_refresh()
        self.assertIsNone(self.panel.sel_uid)
        self.assertFalse(self.panel.btn_action.isEnabled())

    def test_filters_and_config_extension(self):
        self.db.data['装备部位']['new_slot'] = {'名称': '新部位'}
        self.db.data['_装备部位顺序'].append('new_slot')
        self.db.data['装备品质']['new_quality'] = {'名称': '新品质', '颜色': '#101010'}
        self.db.data['_装备品质顺序'].append('new_quality')
        self.item()
        uid = self.item('new_slot', 'new_quality')
        self.panel.refresh()
        self.assertIn('new_slot', self.panel.slot_btns)
        self.panel.slot_filter.setCurrentIndex(self.panel.slot_filter.findData('new_slot'))
        self.panel.quality_filter.setCurrentIndex(self.panel.quality_filter.findData('new_quality'))
        self.assertEqual([it['uid'] for it in self.panel.model.visible_items()], [uid])
        self.panel._on_item(uid)
        self.assertIn('#E8B23A', self.panel.lbl_detail.text())
        self.panel.slot_filter.setCurrentIndex(0)
        self.panel.quality_filter.setCurrentIndex(0)
        self.panel.sort_filter.setCurrentIndex(1)
        self.assertEqual(self.panel.model.visible_items()[0]['uid'], uid)

    def test_pool_growth_and_pixel_render(self):
        for _ in range(51):
            self.item()
        self.panel.refresh()
        cells = list(self.panel.inventory_grid.cells)
        self.assertEqual(len(cells), 55)
        self.panel.slot_filter.setCurrentIndex(2)
        self.assertEqual(self.panel.inventory_grid.cells, cells)
        self.assertFalse(cells[-1].isVisible())
        self.panel.slot_filter.setCurrentIndex(0)
        self.panel._on_item(self.panel.model.visible_items()[0]['uid'])
        self.app.processEvents()
        self.panel._on_slot_click(self.db.data['_装备部位顺序'][0])
        self.app.processEvents()
        image = self.panel.drawer.grab().toImage()
        viewport = self.panel.inv_area.viewport()
        point = viewport.mapTo(self.panel.drawer, QPoint(viewport.width() - 3, 3))
        color = image.pixelColor(point)
        self.assertLess(max(color.red(), color.green(), color.blue()), 90)
        self.assertTrue(self.panel.drawer.rect().contains(self.panel.btn_action.mapTo(self.panel.drawer, QPoint(0, 0))))
        if os.environ.get('EQUIPMENT_UI_PREVIEW'):
            image.save(os.environ['EQUIPMENT_UI_PREVIEW'])

    def test_removed_selection_cannot_be_equipped(self):
        uid = self.item()
        self.panel.refresh()
        self.panel._on_item(uid)
        equipment.save_inventory({'items': {}, 'equipped': {}, 'next_uid': 2})
        self.panel.btn_action.click()
        self.assertEqual(equipment.get_equipped(), {})
        self.assertFalse(self.panel.btn_action.isEnabled())


if __name__ == '__main__':
    unittest.main(verbosity=2)
