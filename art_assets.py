"""美术资源入口：图集切片与透明边界裁切只做一次，绘制路径不读磁盘。"""
from functools import lru_cache
import json
import math
from pathlib import Path

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QBitmap, QImage, QPainter, QPixmap, QRegion

ART_ROOT = Path(__file__).resolve().parent / 'assets' / 'art'
_MIP_CACHE = {}


@lru_cache(maxsize=1)
def manifest():
    try:
        return json.loads((ART_ROOT / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=8)
def atlas(name):
    conf = manifest().get('atlases', {}).get(name, {})
    return QImage(str(ART_ROOT / conf.get('file', 'missing.png')))


@lru_cache(maxsize=64)
def sprite(name, index=0):
    """按透明遮罩找主体边界，保留原始 alpha；不修改原图。需 QApplication。"""
    conf = manifest().get('atlases', {}).get(name, {})
    source = atlas(name)
    cols, rows = conf.get('columns', 1), conf.get('rows', 1)
    if source.isNull() or index < 0 or index >= cols * rows:
        return QPixmap()
    w, h = source.width() // cols, source.height() // rows
    cell = source.copy((index % cols) * w, (index // cols) * h, w, h)
    mask = cell.createAlphaMask(Qt.ImageConversionFlag.ThresholdAlphaDither)
    bounds = QRegion(QBitmap.fromImage(mask)).boundingRect()
    if bounds.isEmpty():
        return QPixmap()
    bounds = bounds.adjusted(-3, -3, 3, 3).intersected(QRect(0, 0, w, h))
    return QPixmap.fromImage(cell.copy(bounds))


def species_sprite(view, palette):
    index = manifest().get('species', {}).get(palette.get('species_id'))
    return sprite(view, index) if index is not None else QPixmap()


def draw_sprite(painter, pixmap, rect, keep_aspect=False):
    if pixmap.isNull():
        return False
    target = QRectF(rect)
    if keep_aspect:
        ratio = min(target.width() / pixmap.width(), target.height() / pixmap.height())
        w, h = pixmap.width() * ratio, pixmap.height() * ratio
        target = QRectF(target.center().x() - w / 2, target.center().y() - h / 2, w, h)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    # Qt 直接把 400px 图缩到 40px 时只做双线性采样，细翅纹会闪烁。
    # 使用有限档位的预缩小缓存，避免每帧呼吸缩放反复创建新纹理。
    transform = painter.worldTransform()
    screen_scale = math.hypot(transform.m11(), transform.m12())
    sample_width = 2 ** math.ceil(math.log2(max(16, target.width()*screen_scale*1.5)))
    if sample_width < pixmap.width():
        key = (pixmap.cacheKey(), sample_width)
        if key not in _MIP_CACHE:
            if len(_MIP_CACHE) >= 256:
                _MIP_CACHE.clear()
            _MIP_CACHE[key] = pixmap.scaledToWidth(sample_width, Qt.TransformationMode.SmoothTransformation)
        pixmap = _MIP_CACHE[key]
    painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
    return True


def draw_effect(painter, index, x, y, size, opacity=1.0, angle=0):
    painter.save()
    painter.translate(x, y)
    painter.rotate(angle)
    painter.setOpacity(painter.opacity() * max(0.0, min(1.0, opacity)))
    drawn = draw_sprite(painter, sprite('effects', index), QRectF(-size/2, -size/2, size, size), True)
    painter.restore()
    return drawn
