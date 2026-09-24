"""Shared screen-safe placement in Qt logical coordinates."""
from PySide6.QtCore import QRect, QPoint


def clamp_position(position, size, bounds):
    return QPoint(max(bounds.left(), min(position.x(), bounds.right()-size.width()+1)),
                  max(bounds.top(), min(position.y(), bounds.bottom()-size.height()+1)))


def beside(anchor, size, bounds, gap=12):
    candidates = [QPoint(anchor.left()-size.width()-gap, anchor.top()),
                  QPoint(anchor.right()+gap+1, anchor.top()),
                  QPoint(anchor.left(), anchor.bottom()+gap+1),
                  QPoint(anchor.left(), anchor.top()-size.height()-gap)]
    positions = [clamp_position(pos, size, bounds) for pos in candidates]
    def score(pos):
        overlap = QRect(pos, size).intersected(anchor)
        return max(0, overlap.width())*max(0, overlap.height())
    return min(positions, key=score)


def place_panel(panel, anchor):
    from PySide6.QtCore import QSize
    size = panel.size()
    drawer = getattr(panel, 'drawer', None)
    if drawer is not None and drawer.isVisible():
        size = QSize(size.width()+8+drawer.width(), size.height())
    panel.move(beside(anchor.frameGeometry(), size, anchor.screen().availableGeometry()))


def screen_for_point(point, fallback):
    from PySide6.QtWidgets import QApplication
    return next((screen for screen in QApplication.screens() if screen.geometry().contains(point)), fallback)
