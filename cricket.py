# -*- coding: utf-8 -*-
"""蛐蛐本体：动画状态机 + 手绘渲染。

坐标系约定：以蛐蛐脚底为基准，本地坐标 y 轴向下为正，
身体主体落在 y ∈ [-74, 0]，水平范围 x ∈ [-46, 60]（朝右）。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

BODY_HI = QColor("#A8D465")
BODY = QColor("#6FA83C")
BODY_DK = QColor("#3F5C2C")
BELLY = QColor("#CBE098")
LIMB = QColor("#4A3312")
LIMB_HI = QColor("#6E4C1F")
LIMB_FAR = QColor("#38260D")
EYE_W = QColor("#FDFBF3")
EYE_D = QColor("#22241C")
SHADOW = QColor(0, 0, 0, 48)


class Cricket:
    """蛐蛐的状态机，只管动画数值，不碰 Qt 窗口。"""

    def __init__(self) -> None:
        self.t = 0.0
        self.y = 0.0              # 离地高度(px)
        self.vy = 0.0             # 垂直速度
        self.facing = 1.0         # 当前朝向插值值
        self.facing_target = 1.0  # 目标朝向 ±1
        self.blink = 0.0          # 闭眼剩余时间
        self.blink_next = 2.5
        self.act_next = 3.0       # 下次随机挂机行为
        self.chirp = 0.0          # 鸣叫剩余时间
        self.wing = 0.0           # 翅膀张开 0~1
        self.happy = 0.0          # 兴奋度(刚吃到经验)

    def hop(self, power: float = 110.0) -> None:
        """起跳。落地前重复调用无效，避免叠加成火箭。"""
        if self.y <= 0.5:
            self.vy = power

    def cheer(self) -> None:
        """吃到经验时的反应：小概率蹦一下，多半叫两声。"""
        self.happy = 0.8
        if random.random() < 0.35:
            self.hop(random.uniform(95, 145))
        self.chirp = max(self.chirp, 0.45)

    def level_up(self) -> None:
        self.happy = 1.4
        self.hop(180.0)
        self.chirp = 1.1

    def update(self, dt: float) -> None:
        self.t += dt

        # 垂直运动：起跳后受重力回落
        self.vy -= 620.0 * dt
        self.y += self.vy * dt
        if self.y <= 0.0:
            self.y = 0.0
            self.vy = 0.0

        # 转身：朝目标值插值，中途会经过 0（压扁=转身效果）
        self.facing += (self.facing_target - self.facing) * min(1.0, dt * 6.0)

        # 眨眼
        self.blink_next -= dt
        if self.blink_next <= 0.0:
            self.blink = 0.13
            self.blink_next = random.uniform(2.2, 6.0)
        if self.blink > 0.0:
            self.blink -= dt

        # 鸣叫时翅膀高频抖动
        if self.chirp > 0.0:
            self.chirp -= dt
            self.wing = abs(math.sin(self.chirp * 26.0)) * 0.9
        else:
            self.wing += (0.0 - self.wing) * min(1.0, dt * 8.0)

        if self.happy > 0.0:
            self.happy -= dt

        # 随机挂机行为：蹦跶 / 鸣叫 / 转身
        self.act_next -= dt
        if self.act_next <= 0.0:
            self.act_next = random.uniform(4.5, 12.0)
            r = random.random()
            if r < 0.38:
                self.hop(random.uniform(70, 125))
            elif r < 0.70:
                self.chirp = 0.7
            else:
                self.facing_target = -1.0 if self.facing_target > 0 else 1.0


def _stroke(p: QPainter, path: QPainterPath, color: QColor, width: float) -> None:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def palette_from_hex(main_hex: str) -> dict:
    """由品种主色生成一套配色：亮部 / 本体 / 暗部 / 腹部亮面。

    主色来自数值表「2-品种」的 主色 列，所以换品种就换配色。
    """
    base = QColor(main_hex)
    if not base.isValid():
        base = QColor("#6FA83C")
    h, s, v, _a = base.getHsv()
    return {
        "hi": QColor.fromHsv(h, max(0, s - 40), min(255, v + 45)),
        "body": base,
        "dk": QColor.fromHsv(h, min(255, s + 30), max(0, int(v * 0.62))),
        "belly": QColor.fromHsv(h, max(0, s - 60), min(255, v + 70)),
    }


DEFAULT_PALETTE = palette_from_hex("#6FA83C")


def _draw_body(p: QPainter, c: Cricket, pal: dict) -> None:
    sway = math.sin(c.t * 1.8) * 4.0
    hi, body, dk, belly = pal["hi"], pal["body"], pal["dk"], pal["belly"]

    # 远侧后腿（先画，被身体挡住一半）
    far = QPainterPath()
    far.moveTo(0, 0)
    far.lineTo(-24, -20)
    far.lineTo(-13, 13)
    _stroke(p, far, LIMB_FAR, 5.5)

    # 尾须
    for y0, y1 in ((-2, -13), (3, 10)):
        tail = QPainterPath()
        tail.moveTo(-24, y0)
        tail.quadTo(-36, y0, -45, y1)
        _stroke(p, tail, LIMB, 2.2)

    # 躯干
    p.setPen(QPen(dk, 1.5))
    p.setBrush(QBrush(body))
    p.drawEllipse(QRectF(-26, -17, 52, 34))

    # 腹部亮面
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(belly))
    p.drawEllipse(QRectF(-21, -1, 38, 15))

    # 体节纹
    p.setPen(QPen(QColor(dk.red(), dk.green(), dk.blue(), 110), 1.2))
    for i in range(3):
        x = -13 + i * 9
        p.drawLine(int(x), -14, int(x - 2), 4)
    p.setPen(Qt.PenStyle.NoPen)

    # 翅膀：鸣叫时向上掀起
    p.save()
    p.translate(-4, -13)
    p.rotate(-c.wing * 13.0)
    p.setPen(QPen(dk, 1.2))
    p.setBrush(QBrush(hi))
    p.drawEllipse(QRectF(-18, -8, 45, 20))
    p.setPen(QPen(QColor(255, 255, 255, 95), 1.0))
    p.drawLine(-12, -3, 18, -6)
    p.drawLine(-10, 1, 16, -1)
    p.restore()
    p.setPen(Qt.PenStyle.NoPen)

    # 头
    p.setPen(QPen(dk, 1.5))
    p.setBrush(QBrush(body))
    p.drawEllipse(QRectF(14, -28, 32, 32))

    # 触角
    for bx, by, tx, ty in ((34, -26, 63, -45), (27, -28, 56, -55)):
        ant = QPainterPath()
        ant.moveTo(bx, by)
        ant.quadTo(bx + 15, by - 11 + sway, tx, ty + sway)
        _stroke(p, ant, LIMB_HI, 2.0)

    # 眼睛
    if c.blink > 0.0:
        p.setPen(QPen(EYE_D, 2.0))
        p.drawLine(31, -16, 41, -16)
    else:
        p.setBrush(QBrush(EYE_W))
        p.setPen(QPen(dk, 1.0))
        p.drawEllipse(QRectF(29.5, -22.5, 13, 13))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(EYE_D))
        p.drawEllipse(QRectF(35, -19, 6, 6))
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawEllipse(QRectF(35.8, -18.4, 2.2, 2.2))

    # 嘴
    p.setPen(QPen(dk, 1.4))
    p.drawArc(QRectF(38, -10, 9, 8), 200 * 16, 140 * 16)

    # 近侧后腿（蟋蟀的大腿，画在最上层）
    near = QPainterPath()
    near.moveTo(-4, 4)
    near.lineTo(-31, -21)
    near.lineTo(-18, 16)
    _stroke(p, near, LIMB, 6.5)
    p.setPen(QPen(LIMB_HI, 1.4))
    for i in range(3):
        p.drawLine(int(-26 + i * 3), int(-13 + i * 5), int(-33 + i * 3), int(-10 + i * 5))

    # 前腿
    for x0, x1 in ((17, 13), (9, 3)):
        leg = QPainterPath()
        leg.moveTo(x0, 6)
        leg.lineTo(x1, 20)
        _stroke(p, leg, LIMB, 3.4)


def paint_cricket(p: QPainter, cx: float, foot_y: float, scale: float,
                  c: Cricket, palette: dict | None = None) -> None:
    """在 (cx, foot_y) 处画一只蛐蛐，脚底对齐 foot_y。

    palette 来自数值表品种主色，不传则用默认绿色。
    """
    # 地面投影，跳得越高影子越小越淡
    k = max(0.35, 1.0 - c.y / 60.0)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(0, 0, 0, int(48 * k))))
    p.drawEllipse(QRectF(cx - 32 * scale * k, foot_y - 5, 64 * scale * k, 10 * k))

    breathe = 1.0 + 0.025 * math.sin(c.t * 2.2) + 0.05 * max(0.0, c.happy)
    f = c.facing if abs(c.facing) > 0.06 else (0.06 if c.facing_target >= 0 else -0.06)

    p.save()
    p.translate(cx, foot_y - c.y)
    p.scale(f * scale * breathe, scale / breathe)
    p.translate(0, -22)
    _draw_body(p, c, palette or DEFAULT_PALETTE)
    p.restore()
