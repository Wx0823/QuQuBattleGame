"""右键与托盘共用墨金菜单；每次打开读取当前角色及战斗状态。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget, QWidgetAction
from ui_theme import mode_icon

MENU_CSS = '''
QMenu{background:#1D2723;color:#EEE6D6;border:1px solid #87744E;
 border-radius:10px;padding:8px;}
QMenu::item{min-width:180px;padding:10px 18px 10px 32px;margin:2px 3px;
 border:1px solid transparent;border-radius:6px;font-size:13px;}
QMenu::item:selected{background:#394536;color:#F5DBA4;border-color:#7B7150;}
QMenu::item:disabled{color:#818A7C;}
QMenu::separator{height:1px;background:#414A3B;margin:7px 12px;}
QMenu::icon{left:12px;}
'''

def menu_icon(kind):
    if kind in ('equipment', 'dungeon'):
        return mode_icon(kind)
    pix = QPixmap(16,16)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor('#D6B778'), 1.4))
    if kind == 'settings':
        for y, x in ((4,6),(8,10),(12,5)):
            p.drawLine(2,y,14,y)
            p.drawLine(x,y-2,x,y+2)
    elif kind == 'fight':
        p.drawLine(3,3,13,13); p.drawLine(13,3,3,13)
        p.drawLine(2,10,6,14); p.drawLine(10,14,14,10)
    else:
        p.drawLine(3,2,3,14); p.drawLine(3,2,8,2); p.drawLine(3,14,8,14)
        p.drawLine(7,8,14,8); p.drawLine(11,5,14,8); p.drawLine(11,11,14,8)
    p.end()
    return QIcon(pix)

def populate_menu(menu, pet):
    menu.clear()
    header = QWidget(menu)
    layout = QVBoxLayout(header)
    layout.setContentsMargins(13,9,13,10)
    layout.setSpacing(5)
    species = (pet.db.species(pet.species_id) or {}).get('名称','蛐蛐')
    name = QLabel(f'{species}  ·  Lv.{pet.level}')
    name.setStyleSheet('color:#E2C58B;font-size:14px;font-weight:600;')
    stage = pet._stage
    status = (f'{stage.drun.diff_name()} · 第 {stage.drun.floor}/{stage.drun.floors} 层'
              if stage is not None and stage.drun is not None else '桌面挂机 · 养成与挑战')
    sub = QLabel(status)
    sub.setStyleSheet('color:#A5AE9F;font-size:11px;')
    layout.addWidget(name); layout.addWidget(sub)
    action = QWidgetAction(menu)
    action.setDefaultWidget(header)
    menu.addAction(action)
    menu.addSeparator()
    def add(text, icon, callback):
        action = menu.addAction(menu_icon(icon), text)
        action.triggered.connect(callback)
    if stage is not None:
        add('撤出副本 · 保存进度', 'exit', pet.end_desktop_battle)
    else:
        add('挑战副本', 'dungeon', pet._open_dungeon_select)
        add('发起对战', 'fight', pet._open_arena)
    menu.addSeparator()
    add('蛐蛐属性', 'dungeon', pet._toggle_attribute_panel)
    add('蛐蛐装备', 'equipment', pet._toggle_equipment_panel)
    add('蛐蛐设置', 'settings', pet._toggle_settings)
    menu.addSeparator()
    add('退出游戏', 'exit', pet._quit)

def create_menu(pet):
    menu = QMenu(pet)
    menu.setFont(QFont('Microsoft YaHei',9))
    menu.setStyleSheet(MENU_CSS)
    menu.aboutToShow.connect(lambda: populate_menu(menu, pet))
    return menu
