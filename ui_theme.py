"""墨金 UI：共享色板、控件样式与可缩放的矢量装饰。"""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QPen, QIcon, QPixmap, QPainter

TEXT = '#EEE6D6'
MUTED = '#AAA698'
GOLD = '#D6B778'
SURFACE = '#202827'

def button_css(primary=False, compact=False):
    bg, fg = ('#C8A76B', '#191F1E') if primary else ('#283230', TEXT)
    hover = '#E0C48F' if primary else '#39443D'
    padding = '0px' if compact else '7px 12px'
    return (f'QPushButton{{background:{bg};color:{fg};border:1px solid #776A4E;'
            f'border-radius:7px;padding:{padding};font-size:12px;font-weight:600;}}'
            f'QPushButton:hover{{background:{hover};border-color:#D6B778;}}'
            'QPushButton:pressed{background:#756447;color:#FFF4DB;}'
            'QPushButton:focus{border:1px solid #F3D99F;}'
            'QPushButton:disabled{background:#252C2A;color:#777F78;border-color:#414940;}')

PANEL_CSS = (
    'QLabel{color:#EEE6D6;font-size:12px;background:transparent;}'
    'QComboBox{color:#EEE6D6;background:#283230;border:1px solid #665F4D;'
    'border-radius:7px;padding:7px;font-size:12px;}'
    'QComboBox:hover{border-color:#D6B778;}'
    'QComboBox QAbstractItemView{color:#EEE6D6;background:#202827;selection-background-color:#526044;}'
    'QToolTip{color:#EEE6D6;background:#202827;border:1px solid #776A4E;padding:6px;}'
) + button_css()

def draw_card(p, rect, radius=14, ornaments=False):
    p.save()
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, QColor('#29322F'))
    gradient.setColorAt(1, QColor('#161D1D'))
    p.setBrush(gradient)
    p.setPen(QPen(QColor('#726448'), 1))
    p.drawRoundedRect(rect, radius, radius)
    if ornaments:
        inner = rect.adjusted(5, 5, -5, -5)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(214, 183, 120, 24), 1))
        p.drawRoundedRect(inner, radius-3, radius-3)
        p.setPen(QPen(QColor('#C7A96E'), 1))
        for x, direction in ((rect.left()+14, 1), (rect.right()-14, -1)):
            y = rect.top()+9
            p.drawLine(QPointF(x, y+9), QPointF(x, y))
            p.drawLine(QPointF(x, y), QPointF(x+direction*18, y))
    p.restore()

def mode_icon(kind):
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(GOLD), 1.3))
    if kind == 'equipment':
        points = [QPointF(3,3), QPointF(8,1), QPointF(13,3), QPointF(12,10), QPointF(8,14), QPointF(4,10), QPointF(3,3)]
        for a,b in zip(points,points[1:]): p.drawLine(a,b)
        p.drawLine(8,4,8,10)
    else:
        p.drawRoundedRect(QRectF(2,2,12,12), 2, 2)
        p.drawLine(5,5,11,5)
        p.drawLine(5,8,11,8)
        p.drawLine(5,11,8,11)
    p.end()
    return QIcon(pix)

# 桌面副本徽章与按钮共用几何，避免两处布局漂移。
BADGE_W = 208
TOOL_W = 58
TOOL_GAP = 6
HUD_W = BADGE_W + 12 + 2 * TOOL_W + TOOL_GAP + 10

def dungeon_hud_rect(cx):
    return QRectF(cx-HUD_W/2, 8, HUD_W, 46)
