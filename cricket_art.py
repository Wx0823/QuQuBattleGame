"""手绘躯干 + 连续关节动画。只负责美术，不改变战斗或宠物状态。"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen

from art_assets import draw_sprite, species_sprite

_HEAD_ANCHORS = {}


def side_antenna_roots(pix, rect):
    """在头部两列的不透明轮廓内定位根部，随品种贴图的实际比例缩放。"""
    key = pix.cacheKey()
    if key not in _HEAD_ANCHORS:
        image = pix.toImage()
        roots = []
        for fraction in (.87, .91):
            x = round((image.width()-1)*fraction)
            solid = [y for y in range(image.height())
                     if image.pixelColor(x, y).alpha() >= 192]
            if solid:
                # 埋入头壳，贴图覆盖根端，避免抗锯齿边缘形成缝隙。
                y = solid[min(len(solid)-1, max(2, round(len(solid)*.18)))]
            else:
                y = image.height()//2
            roots.append(((x+.5)/image.width(), (y+.5)/image.height()))
        if len(_HEAD_ANCHORS) >= 64:
            _HEAD_ANCHORS.clear()
        _HEAD_ANCHORS[key] = roots
    return [(rect.left()+u*rect.width(), rect.top()+v*rect.height())
            for u, v in _HEAD_ANCHORS[key]]


def stroke(p, points, color, width):
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    pen = QPen(color, width, Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def limb_colors(pal):
    """腿部以低饱和甲褐色为底，仅保留少量品种色，避免荧光塑料感。"""
    base = pal['body']
    earth = QColor('#86704D')
    mid = QColor(*(round(a*.35+b*.65) for a, b in zip(
        (base.red(), base.green(), base.blue()),
        (earth.red(), earth.green(), earth.blue()))))
    return mid.darker(210), mid, mid.lighter(135)


def limb(p, points, pal, width=2.4, spines=False):
    """细长渐尖的胫节与跗节；棘刺沿胫节分布，不再长在脚底。"""
    dark, mid, light = limb_colors(pal)
    for index, ((x0, y0), (x1, y1)) in enumerate(zip(points, points[1:])):
        dx, dy = x1-x0, y1-y0
        length = max(1, math.hypot(dx, dy))
        nx, ny = -dy/length, dx/length
        radius = width*.35 * (.65**index)
        tip = max(.18, radius*.5)
        path = QPainterPath(QPointF(x0+nx*radius, y0+ny*radius))
        path.quadTo(x0+dx*.5+nx*radius*.65, y0+dy*.5+ny*radius*.65,
                    x1+nx*tip, y1+ny*tip)
        path.lineTo(x1-nx*tip, y1-ny*tip)
        path.quadTo(x0+dx*.5-nx*radius, y0+dy*.5-ny*radius,
                    x0-nx*radius, y0-ny*radius)
        path.closeSubpath()
        p.setPen(QPen(dark, .45))
        grad = QLinearGradient(x0+nx*radius, y0+ny*radius, x0-nx*radius, y0-ny*radius)
        grad.setColorAt(0, light)
        grad.setColorAt(.4, mid)
        grad.setColorAt(1, dark)
        p.setBrush(grad)
        p.drawPath(path)
        if spines and index == 0:
            for k in (.25, .43, .61, .78):
                x, y = x0+dx*k, y0+dy*k
                stroke(p, [(x, y), (x+nx*1.8-dx/length, y+ny*1.8-dy/length)], dark, .55)


def femur(p, root, knee, pal, thickness=4):
    x0, y0 = root
    x1, y1 = knee
    dx, dy = x1-x0, y1-y0
    length = max(1, math.hypot(dx, dy))
    nx, ny = -dy/length*thickness, dx/length*thickness
    path = QPainterPath(QPointF(x0, y0))
    path.cubicTo(x0+dx*.35+nx, y0+dy*.35+ny,
                 x1+nx, y1+ny, x1, y1)
    path.cubicTo(x1-nx, y1-ny, x0+dx*.3-nx, y0+dy*.3-ny, x0, y0)
    grad = QLinearGradient(x0, y0-thickness, x1, y1+thickness)
    dark, mid, light = limb_colors(pal)
    grad.setColorAt(0, dark)
    grad.setColorAt(.35, light)
    grad.setColorAt(.65, mid)
    grad.setColorAt(1, dark)
    p.setPen(QPen(dark, .6))
    p.setBrush(grad)
    p.drawPath(path)
    # 少量纵向肌理取代贯穿整条腿的亮色粗线。
    for fraction in (-.3, .15, .45):
        stroke(p, [(x0+dx*.2+nx*fraction, y0+dy*.2+ny*fraction),
                   (x0+dx*.8+nx*fraction*.4, y0+dy*.8+ny*fraction*.4)], mid.darker(125), .3)


def feeler(p, root, middle, tip, pal):
    path = QPainterPath(QPointF(*root))
    path.quadTo(QPointF(*middle), QPointF(*tip))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(pal['dk'].darker(140), 1.5))
    p.drawPath(path)
    p.setPen(QPen(QColor('#BEA774'), .55))
    p.drawPath(path)


def side_body(p, c, pal):
    pix = species_sprite('side', pal)
    if pix.isNull():
        return False
    p.save()
    sway = math.sin(c.t * 2) * 3
    # 远侧三足。
    p.setOpacity(p.opacity() * .72)
    femur(p, (-4, -8), (-26, -17), pal, 3.5)
    limb(p, [(-26, -17), (-32, 15), (-39, 18), (-42, 17)], pal, 2.1, True)
    for x, end in ((7, -2), (20, 37)):
        limb(p, [(x, -8), (x + 6, 5), (end, 16), (end + 3, 18)], pal, 1.7)
    p.restore()
    height = 72 * pix.height() / pix.width()
    body_rect = QRectF(-35, 7-height, 72, height)
    # 根部由头壳轮廓定位，与躯干共用呼吸/转向变换，摆动只影响须尖。
    for sign, root in zip((-1, 1), side_antenna_roots(pix, body_rect)):
        feeler(p, (-29, -8), (-41, -9 + sign*5), (-51, -10 + sign*8), pal)
        feeler(p, root, (37, -49 + sway + sign*8),
               (57, -52 + sway + sign*10), pal)
    draw_sprite(p, pix, body_rect)
    # 鸣叫时背翅抬升，贴图上层独立转动，主体保持稳定。
    if c.wing > .03:
        p.save()
        p.translate(12, -21)
        p.rotate(c.wing * 9)
        p.translate(-12, 21)
        p.setClipRect(QRectF(-35, -29, 46, 16))
        draw_sprite(p, pix, body_rect)
        p.restore()
    femur(p, (-3, 0), (-24, -19), pal, 4.8)
    limb(p, [(-24, -19), (-32, 16), (-40, 20), (-44, 19)], pal, 2.8, True)
    for x, end in ((9, 0), (23, 30)):
        limb(p, [(x, -3), (x+4, 7), (end, 18), (end+4, 20), (end+6, 19)], pal, 2.1)
    if c.blink > 0:
        # 自然复眼的小幅遮合，避免破坏手绘头部。
        p.setPen(QPen(pal['dk'], 2.4))
        p.drawLine(QPointF(29, -17), QPointF(33, -16))
    return True


def top_body(p, x, y, angle, scale, c, pal, opacity, lift, flip):
    pix = species_sprite('top', pal)
    if pix.isNull():
        return False
    p.save()
    p.setOpacity(p.opacity() * max(0, min(1, opacity)))
    p.translate(x, y)
    p.rotate(angle + math.sin(c.gait_phase)*1.5*c.move_amp)
    breathe = 1 + .018*math.sin(c.t*2.4)
    p.scale(scale*breathe, scale/breathe * flip)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 48))
    p.drawEllipse(QRectF(-39, -16, 83, 35))
    curl = max(0, -flip)
    amp = 7*c.move_amp * (1-curl)
    for sign in (-1, 1):
        phase = c.gait_phase + (math.pi if sign < 0 else 0)
        sw = math.sin(phase)*amp
        # 后腿从胸部向后折叠，股节宽、胫节细，三对腿各有独立相位。
        knee = (-21+sw*.4, sign*(26-12*curl))
        femur(p, (1, sign*9), knee, pal, 4.1)
        limb(p, [knee, (-39+sw+17*curl, sign*(19-12*curl)),
                 (-47+sw+26*curl, sign*(22-17*curl))], pal, 2.2, True)
        for root_x, knee_x, foot_x, phase_shift in ((10, 3, -7, math.pi), (24, 32, 43, 0)):
            stride = math.sin(phase+phase_shift)*amp
            limb(p, [(root_x, sign*9), (knee_x+stride*.4, sign*(21-6*curl)),
                     (foot_x+stride+(root_x-foot_x)*curl*.7, sign*(29-22*curl)),
                     (foot_x+stride+3+(root_x-foot_x)*curl*.7, sign*(30-25*curl))], pal, 1.7)
        feeler(p, (-33, sign*5), (-44, sign*8), (-55, sign*12), pal)
        length = 1 - .48 * max(0, min(1, lift))
        sway = math.sin(c.t*2)*4
        feeler(p, (33, sign*5), (46+length*12, sign*(16+sway)),
               (39+length*48, sign*(23+sway)), pal)
    height = 76 * pix.height() / pix.width()
    rect = QRectF(-37, -height/2, 76, height)
    draw_sprite(p, pix, rect)
    # KO 保留完整手绘甲壳，通过翻转与收腿表达，不叠加矩形腹甲。
    if flip >= 0 and c.wing > .03:
        for sign in (-1, 1):
            p.save()
            p.translate(14, 0)
            p.rotate(sign*c.wing*12)
            p.translate(-14, 0)
            p.setClipRect(QRectF(-37, -16 if sign < 0 else 0, 51, 16))
            draw_sprite(p, pix, rect)
            p.restore()
    p.restore()
    return True
