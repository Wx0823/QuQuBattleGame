"""装备掉落表现：只保存视觉快照，不参与掉落概率或背包结算。"""
import math
from collections import deque
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPen, QRadialGradient
import equipment
from equipment_widgets import _ui_color, slot_icon_pixmap
from ui_theme import draw_card


class LootEffects:
    DURATION = 4.6

    def __init__(self):
        self.queue = deque()
        self.age = 0.

    def clear(self):
        self.queue.clear()
        self.age = 0.

    def add(self, db, item, x, y):
        slot = db.data.get('装备部位', {}).get(item['slot'], {}).get('名称', item['slot'])
        quality = db.data.get('装备品质', {}).get(item['quality'], {}).get('名称', '')
        color = _ui_color(equipment.quality_color(db, item))
        self.queue.append(dict(name=equipment.item_name(db, item), quality=quality,
                               color=color, icon=slot_icon_pixmap(slot, color, size=56),
                               x=x, y=y))

    def update(self, dt):
        if not self.queue:
            return
        self.age += max(0., dt)
        while self.queue and self.age >= self.DURATION:
            self.queue.popleft()
            self.age -= self.DURATION
        if not self.queue:
            self.age = 0.

    def draw(self, p, cx, top):
        if not self.queue:
            return
        drop = self.queue[0]
        t = self.age
        color = QColor(drop['color'])
        p.save()
        alpha = min(1., t/.15, (self.DURATION-t)/.5)
        p.setOpacity(p.opacity()*max(0., alpha))
        # 独立于敌人位置：下一只增援出现时，图标不会跟着跳走。
        start_x = max(40., min(2*cx-40., drop['x']))
        start_y = max(top+90., drop['y']-40.)
        fly = max(0., min(1., (t-.65)/.75))
        ease = fly*fly*(3-2*fly)
        end_x, end_y = cx-104, top+31
        x = start_x+(end_x-start_x)*ease
        y = start_y+(end_y-start_y)*ease-28*math.sin(min(1., t/.65)*math.pi)
        if t < 1.4:
            glow = QRadialGradient(QPointF(x,y), 54)
            inner = QColor(color); inner.setAlpha(145)
            outer = QColor(color); outer.setAlpha(0)
            glow.setColorAt(0, inner); glow.setColorAt(1, outer)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(glow)
            p.drawEllipse(QPointF(x,y), 54, 54)
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(color, 1.4))
            radius = 16+min(1., t/.65)*28
            p.drawEllipse(QPointF(x,y), radius, radius*.42)
            for i in range(8):
                angle = i*math.tau/8+t*.7
                distance = 23+min(t,.7)*30
                px, py = x+math.cos(angle)*distance, y+math.sin(angle)*distance
                p.drawLine(QPointF(px-2,py), QPointF(px+2,py))
                p.drawLine(QPointF(px,py-2), QPointF(px,py+2))
            p.drawPixmap(QRectF(x-28,y-28,56,56), drop['icon'], QRectF(drop['icon'].rect()))
        # 图标飞入顶部奖励卡，文字持续停留，支持连续掉落排队显示。
        if t >= .9:
            p.setOpacity(p.opacity()*min(1., (t-.9)/.3))
            rect = QRectF(cx-138, top, 276, 62)
            draw_card(p, rect, 9)
            p.setPen(QPen(color, 2)); p.drawLine(QPointF(rect.left()+1,top+12), QPointF(rect.left()+1,top+50))
            p.drawPixmap(QRectF(cx-128,top+7,48,48), drop['icon'], QRectF(drop['icon'].rect()))
            p.setFont(QFont('Microsoft YaHei', 10, QFont.Weight.DemiBold))
            p.setPen(color)
            title = p.fontMetrics().elidedText(drop['name'], Qt.TextElideMode.ElideRight, 194)
            p.drawText(QRectF(cx-70,top+10,198,22), Qt.AlignmentFlag.AlignLeft, title)
            p.setFont(QFont('Microsoft YaHei', 8))
            p.setPen(QColor('#EEE6D6'))
            pending = f' · 另有 {len(self.queue)-1} 件' if len(self.queue)>1 else ''
            p.drawText(QRectF(cx-70,top+36,198,18), Qt.AlignmentFlag.AlignLeft,
                       f"{drop['quality']} · 已收入背包{pending}")
        p.restore()
