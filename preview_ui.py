"""离屏展示真实窗口与布局校验；不读取/修改玩家存档。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import random
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase, QColor, QPixmap, QPainter
import main
import equipment
from test_support import isolated_game_data
from ui_theme import dungeon_hud_rect

def main_preview():
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    app.setFont(QFont('Microsoft YaHei', 9))
    out = Path(__file__).parent / 'docs'
    with isolated_game_data(), patch.object(main.Pet, '_init_hook'), patch.object(main.Pet, '_init_tray'):
        pet = main.Pet()
        pet.timer.stop()
        pet.set_species('c002')
        pet.level = 12
        pet.recompute()
        pet.show()
        for zoom in (.6, 1., 1.14, 2.):
            pet.set_zoom(zoom)
            for button in (pet.btn_attr, pet.btn_dungeon):
                assert pet.rect().contains(button.geometry())
                assert pet.mask().contains(button.geometry().center())
            assert not pet.btn_attr.geometry().intersects(pet.btn_dungeon.geometry())
        pet.set_zoom(1.5)
        app.processEvents()
        def save(widget, name):
            pix = QPixmap(widget.size())
            pix.fill(QColor('#343D3A'))
            painter = QPainter(pix)
            painter.drawPixmap(0, 0, widget.grab())
            painter.end()
            pix.save(str(out/name))
        save(pet, 'ui_idle.png')
        pet.begin_desktop_battle(diff_id='d01')
        stage = pet._stage
        for _ in range(22): stage.update(.1)
        hud = dungeon_hud_rect(stage.cx)
        for button in (pet.btn_equip_b, pet.btn_desktop):
            assert hud.contains(button.geometry().toRectF())
        app.processEvents()
        save(pet, 'ui_battle.png')
        stage.discard()
        pet.end_desktop_battle()
        for _ in range(26):
            item = equipment.make_item(pet.db, random.Random(_), 'd05')
            if item: equipment.add_item(pet.db, item)
        pet._toggle_equipment_panel()
        app.processEvents()
        panel = pet.equip_panel
        items = panel.model.visible_items()
        if items: panel._on_item(items[0]['uid'])
        panel.grab().save(str(out/'ui_equipment.png'))
        panel.set_page(0)
        panel._show_attribute('hp')
        app.processEvents()
        panel.grab().save(str(out/'ui_attributes.png'))
        panel.set_page(1)
        sid = items[0]['slot'] if items else pet.db.data['_装备部位顺序'][0]
        panel._on_slot_click(sid)
        if items: panel._on_item(items[0]['uid'])
        app.processEvents()
        panel.drawer.grab().save(str(out/'ui_slot_bag.png'))
        combined = QPixmap(panel.width()+8+panel.drawer.width(), panel.height())
        combined.fill(QColor('#343D3A'))
        painter = QPainter(combined)
        painter.drawPixmap(0, 0, panel.grab())
        painter.drawPixmap(panel.width()+8, 0, panel.drawer.grab())
        painter.end()
        combined.save(str(out/'ui_equipment_drawer.png'))
        pet.settings_panel.show_near(pet)
        app.processEvents()
        pet.settings_panel.grab().save(str(out/'ui_settings.png'))
        pet._open_dungeon_select()
        app.processEvents()
        pet.dungeon_sel.grab().save(str(out/'ui_dungeon.png'))
        pet.close()
    print('UI previews and layout checks PASS')

if __name__ == '__main__':
    main_preview()
