"""美术接入回归与预览：不启动输入钩子、不改玩家存档。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication

from art_assets import atlas, manifest, sprite
from cricket import Cricket, paint_cricket, paint_cricket_top, palette_from_hex
from equipment_widgets import slot_icon_pixmap
from stats import StatsDB


def canvas(w, h, color=Qt.GlobalColor.transparent):
    image = QImage(w, h, QImage.Format.Format_ARGB32)
    image.fill(color)
    return image


def render_cricket(sid, top=False, time=0, flip=1, opacity=1):
    sp = StatsDB().species(sid)
    pal = palette_from_hex(sp['主色'], sid)
    c = Cricket()
    c.t = time
    c.move_amp = .9
    c.gait_phase = time*5
    c.wing = .5 if time else 0
    image = canvas(320, 220)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if top:
        paint_cricket_top(p, 130, 110, 0, 1.7, c, pal, opacity, .5, flip)
    else:
        paint_cricket(p, 150, 180, 2, c, pal)
    p.end()
    return image


class ArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = 'C:/Windows/Fonts/msyh.ttc'
        if Path(font).exists():
            QFontDatabase.addApplicationFont(font)
            cls.app.setFont(QFont('Microsoft YaHei', 9))

    def test_all_species_views_and_transparency(self):
        for sid in StatsDB().species_ids():
            self.assertIn(sid, manifest()['species'])
            for top in (False, True):
                image = render_cricket(sid, top)
                self.assertGreater(image.pixelColor(150, 110).alpha(), 0)
                self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        for name in manifest()['atlases']:
            self.assertFalse(atlas(name).isNull())
            self.assertTrue(atlas(name).hasAlphaChannel())

    def test_animation_and_knockout_change_pixels(self):
        for sid in StatsDB().species_ids():
            self.assertNotEqual(render_cricket(sid, True), render_cricket(sid, True, .4))
            self.assertNotEqual(render_cricket(sid, True), render_cricket(sid, True, flip=-1))
            self.assertNotEqual(render_cricket(sid), render_cricket(sid, time=.4))

    def test_painter_state_and_opacity(self):
        image = canvas(300, 240)
        p = QPainter(image)
        p.setOpacity(.7)
        paint_cricket_top(p, 130, 110, 30, 1, Cricket(),
                          palette_from_hex('#6FA83C', 'c001'), .25)
        self.assertAlmostEqual(p.opacity(), .7)
        self.assertTrue(p.transform().isIdentity())
        p.end()
        # 轮廓/关节/高光会重复叠加 alpha，但整体不得变成不透明色块。
        self.assertLess(max(image.pixelColor(x, y).alpha() for x in range(300) for y in range(240)), 200)

    def test_ko_preserves_painted_body(self):
        # 翻转后腹部仍应保留贴图细节，防止纯色条块再次盖住整个躯干。
        for sid in StatsDB().species_ids():
            alive = render_cricket(sid, True)
            dead = render_cricket(sid, True, flip=-1)
            matches = 0
            total = 0
            for x in range(102, 142):
                for y in range(101, 119):
                    a = alive.pixelColor(x, y)
                    b = dead.pixelColor(x, dead.height()-1-y)
                    matches += max(abs(a.red()-b.red()), abs(a.green()-b.green()),
                                   abs(a.blue()-b.blue())) < 16
                    total += 1
            self.assertGreater(matches/total, .85, sid)

    def test_antenna_roots_inside_each_species_head(self):
        from cricket_art import side_antenna_roots
        for sid in StatsDB().species_ids():
            pix = sprite('side', manifest()['species'][sid])
            image = pix.toImage()
            height = 72*pix.height()/pix.width()
            rect = QRectF(-35, 7-height, 72, height)
            for x, y in side_antenna_roots(pix, rect):
                px = int((x-rect.left())/rect.width()*image.width())
                py = int((y-rect.top())/rect.height()*image.height())
                self.assertGreaterEqual(image.pixelColor(px, py).alpha(), 192, sid)

    def test_icons_all_slots_qualities_and_unknown_fallback(self):
        db = StatsDB()
        for slot in db.data['装备部位'].values():
            self.assertIn(slot['名称'], manifest()['slots'])
            for quality in db.data['装备品质'].values():
                icon = slot_icon_pixmap(slot['名称'], quality['颜色'], True)
                self.assertFalse(icon.isNull())
        self.assertFalse(slot_icon_pixmap('新部位', '#E8B23A').isNull())
        self.assertFalse(render_cricket('c001').isNull())

    def test_cache_and_source_slices(self):
        for name, count in [('side', 6), ('top', 6), ('equipment', 6), ('effects', 4), ('arena', 1)]:
            for i in range(count):
                pix = sprite(name, i)
                self.assertGreater(pix.width(), 40)
                self.assertGreater(pix.height(), 40)
                self.assertEqual(pix.cacheKey(), sprite(name, i).cacheKey())


def previews():
    app = QApplication.instance() or QApplication([])
    font = 'C:/Windows/Fonts/msyh.ttc'
    if Path(font).exists():
        QFontDatabase.addApplicationFont(font)
        app.setFont(QFont('Microsoft YaHei', 9))
    db = StatsDB()
    sheet = canvas(1200, 800, QColor('#20262A'))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for index, sid in enumerate(db.species_ids()):
        col, row = index % 3, index // 3
        x, y = col*400, row*400
        p.setPen(QColor('#E1CAA0'))
        p.setFont(QFont('Microsoft YaHei', 14))
        p.drawText(QRectF(x+20, y+15, 360, 28), db.species(sid)['名称'])
        p.drawImage(QRectF(x+40, y+35, 320, 220), render_cricket(sid))
        p.drawImage(QRectF(x+60, y+210, 280, 180), render_cricket(sid, True, .4))
    p.end()
    sheet.save('docs/art_species_v3.png')
    icons = canvas(900, 220, QColor('#20262A'))
    p = QPainter(icons)
    for i, slot in enumerate(db.data['装备部位'].values()):
        p.drawPixmap(i*150+24, 25, slot_icon_pixmap(slot['名称'], '#E8B23A', size=108))
        p.setPen(QColor('#E1CAA0'))
        p.drawText(QRectF(i*150, 160, 150, 30), Qt.AlignmentFlag.AlignCenter, slot['名称'])
    p.end()
    icons.save('docs/art_equipment_v3.png')
    from stage import BattleStage
    pet = SimpleNamespace(species_id='c001', level=12, talents=[],
                          palette=palette_from_hex('#6FA83C', 'c001'))
    for style in ('desktop', 'arena'):
        stage = BattleStage(pet, style=style, cx=380 if style=='arena' else 330,
                            cy=290 if style=='arena' else 248, radius=195 if style=='arena' else 236)
        stage.intro_t = 0
        stage.f[1] = (stage.f[1][0], stage.f[1][1], palette_from_hex('#3A3A3A', 'c004'))
        stage.ch[0].update(x=stage.cx-70, y=stage.cy, hd=0)
        stage.ch[1].update(x=stage.cx+70, y=stage.cy, hd=180)
        stage.fx['flash'][1] = .14
        stage.fx['guard'][0] = .3
        scene = canvas(760 if style=='arena' else 660, 600 if style=='arena' else 440, QColor('#30383E'))
        p = QPainter(scene)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        stage.draw(p)
        p.end()
        scene.save(f'docs/art_battle_{style}_v3.png')


if __name__ == '__main__':
    import sys
    if '--preview' in sys.argv:
        previews()
    else:
        unittest.main(verbosity=2)
