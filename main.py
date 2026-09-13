# -*- coding: utf-8 -*-
"""电子斗蛐蛐 · 桌面宠物（第一阶段）

当前能力：
  1. 蛐蛐常驻桌面最上层挂机，会呼吸、眨眼、蹦跶、鸣叫、转身
  2. 可以把它拖到屏幕任意位置（窗口鼠标穿透，不挡正常操作）
  3. 打字 / 点击鼠标会给它加经验值，攒满升级

后续再规划：对战、喂食、burrow 等。
"""

from __future__ import annotations

import json
import os
import random
import sys
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(APP_DIR, "save.json")
LOG_FILE = os.path.join(APP_DIR, "error.log")

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QFont, QIcon,
                           QPainter, QPen, QPixmap)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from pynput import keyboard, mouse
from pynput.keyboard import Key

from cricket import Cricket, paint_cricket

WIN_W, WIN_H = 190, 208
CX = 98.0
FOOT_Y = 155.0
SCALE = 1.3

XP_PER_KEY = 1
XP_PER_CLICK = 2

MODIFIER_KEYS = {
    Key.shift, Key.shift_l, Key.shift_r,
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
    Key.cmd, Key.cmd_l, Key.cmd_r,
    Key.caps_lock, Key.num_lock, Key.scroll_lock,
}


def xp_need(level: int) -> int:
    """升到下一级所需经验。"""
    return 40 + (level - 1) * 35


class Bridge(QObject):
    """全局钩子线程 -> 主线程 的信号桥。"""

    key = Signal()
    press = Signal()
    release = Signal()
    right = Signal()


class Pet(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.cricket = Cricket()
        self.level = 1
        self.xp = 0
        self.total_xp = 0

        self._dragging = False
        self._offset = None
        self._pending = 0          # 待汇总显示的经验
        self._pending_t = 0.0
        self.floats = []           # 飘字 [(text, x, y, life, max_life, color)]
        self.levelup_t = 0.0
        self._save_t = 0.0

        self._load()
        self._init_window()
        self._init_tray()
        self._init_hook()

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    # ---------- 初始化 ----------

    def _init_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFixedSize(WIN_W, WIN_H)
        self.setWindowTitle("电子斗蛐蛐")

    def _init_tray(self) -> None:
        self.tray = QSystemTrayIcon(_make_icon(), self)
        menu = QMenu()
        menu.setFont(QFont("Microsoft YaHei", 9))
        act_reset = QAction("重置蛐蛐", self)
        act_reset.triggered.connect(self._reset)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_reset)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("电子斗蛐蛐")
        self.tray.show()

    def _init_hook(self) -> None:
        self.bridge = Bridge()
        self.bridge.key.connect(self._on_key)
        self.bridge.press.connect(self._on_press)
        self.bridge.release.connect(self._on_release)
        self.bridge.right.connect(self._show_menu)

        self.kb = keyboard.Listener(on_press=self._hook_key)
        self.ms = mouse.Listener(on_click=self._hook_click)
        self.kb.daemon = True
        self.ms.daemon = True
        self.kb.start()
        self.ms.start()

    # ---------- 存档 ----------

    def _load(self) -> None:
        self._start_pos = None
        if not os.path.exists(SAVE_FILE):
            return
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.level = int(d.get("level", 1))
            self.xp = int(d.get("xp", 0))
            self.total_xp = int(d.get("total_xp", self.xp))
            if d.get("x") is not None and d.get("y") is not None:
                self._start_pos = (int(d["x"]), int(d["y"]))
        except Exception:
            self._start_pos = None

    def save(self) -> None:
        data = {
            "level": self.level,
            "xp": self.xp,
            "total_xp": self.total_xp,
            "x": self.x() if self.isVisible() else None,
            "y": self.y() if self.isVisible() else None,
        }
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def place_initial(self) -> None:
        if self._start_pos:
            self.move(*self._start_pos)
            return
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - WIN_W - 40, screen.bottom() - WIN_H - 60)

    # ---------- 全局钩子回调（子线程） ----------

    def _hook_key(self, key) -> None:
        if key in MODIFIER_KEYS:
            return
        self.bridge.key.emit()

    def _hook_click(self, x, y, button, pressed) -> None:
        if button == mouse.Button.left:
            self.bridge.press.emit() if pressed else self.bridge.release.emit()
        elif button == mouse.Button.right and pressed:
            self.bridge.right.emit()

    # ---------- 主线程槽 ----------

    def _on_key(self) -> None:
        self._add_xp(XP_PER_KEY)

    def _on_press(self) -> None:
        pos = QCursor.pos()
        if self.geometry().contains(pos):
            self._dragging = True
            self._offset = pos - self.pos()
        self._add_xp(XP_PER_CLICK)

    def _on_release(self) -> None:
        if self._dragging:
            self._dragging = False
            self._clamp_into_screen()
            self.save()

    def _add_xp(self, n: int) -> None:
        self.xp += n
        self.total_xp += n
        self._pending += n
        while self.xp >= xp_need(self.level):
            self.xp -= xp_need(self.level)
            self.level += 1
            self.levelup_t = 1.8
            self.cricket.level_up()
            self.floats.append(["升级!", 0.0, 0.0, 1.8, 1.8, QColor("#F2B233")])

    # ---------- 主循环 ----------

    def _tick(self) -> None:
        dt = 0.016
        self.cricket.update(dt)

        if self._dragging and self._offset is not None:
            self.move(QCursor.pos() - self._offset)

        # 经验飘字每 260ms 汇总冒一次，避免打字时刷屏
        self._pending_t += dt
        if self._pending > 0 and self._pending_t >= 0.26:
            self.cricket.cheer()
            self.floats.append([
                f"+{self._pending}",
                random.uniform(-16, 16), 0.0, 1.0, 1.0, QColor("#FFFFFF"),
            ])
            self._pending = 0
            self._pending_t = 0.0

        for f in self.floats:
            f[2] += 34 * dt
            f[3] -= dt
        self.floats = [f for f in self.floats if f[3] > 0]

        if self.levelup_t > 0:
            self.levelup_t -= dt

        self._save_t += dt
        if self._save_t >= 10.0:
            self._save_t = 0.0
            self.save()

        self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self.levelup_t > 0:
            k = self.levelup_t / 1.8
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(242, 178, 51, int(70 * k))))
            p.drawEllipse(QRectF(CX - 62 * (1.6 - k * 0.6), FOOT_Y - 96,
                                 124 * (1.6 - k * 0.6), 104))

        paint_cricket(p, CX, FOOT_Y, SCALE, self.cricket)

        self._draw_floats(p)
        self._draw_bar(p)
        p.end()

    def _draw_floats(self, p: QPainter) -> None:
        font = QFont("Microsoft YaHei", 10)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        for text, dx, dy, life, max_life, color in self.floats:
            alpha = min(1.0, life / (max_life * 0.5))
            c = QColor(color)
            c.setAlphaF(alpha)
            p.setPen(QPen(QColor(0, 0, 0, int(120 * alpha)), 3.0))
            p.drawText(QRectF(CX + dx - 60, FOOT_Y - 128 - dy, 120, 22),
                       Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QPen(c, 1.0))
            p.drawText(QRectF(CX + dx - 60, FOOT_Y - 128 - dy, 120, 22),
                       Qt.AlignmentFlag.AlignCenter, text)

    def _draw_bar(self, p: QPainter) -> None:
        need = xp_need(self.level)
        ratio = max(0.0, min(1.0, self.xp / need))
        x, y, w, h = 34.0, 170.0, 122.0, 9.0

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 95)))
        p.drawRoundedRect(QRectF(x, y, w, h), 4.5, 4.5)
        p.setBrush(QBrush(QColor("#8FD14F")))
        p.drawRoundedRect(QRectF(x, y, w * ratio, h), 4.5, 4.5)
        p.setBrush(QBrush(QColor(255, 255, 255, 70)))
        p.drawRoundedRect(QRectF(x + 1, y + 1, max(0.0, w * ratio - 2), 3), 1.5, 1.5)

        font = QFont("Microsoft YaHei", 9)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        label = f"Lv.{self.level}   {self.xp} / {need}"
        p.setPen(QPen(QColor(0, 0, 0, 140), 3.0))
        p.drawText(QRectF(x - 10, y + 11, w + 20, 18), Qt.AlignmentFlag.AlignCenter, label)
        p.setPen(QPen(QColor("#FFFFFF"), 1.0))
        p.drawText(QRectF(x - 10, y + 11, w + 20, 18), Qt.AlignmentFlag.AlignCenter, label)

    # ---------- 交互 ----------

    def _show_menu(self) -> None:
        if not self.geometry().contains(QCursor.pos()):
            return
        menu = QMenu()
        menu.setFont(QFont("Microsoft YaHei", 9))
        act_reset = QAction("重置蛐蛐", self)
        act_reset.triggered.connect(self._reset)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_reset)
        menu.addSeparator()
        menu.addAction(act_quit)
        menu.exec(QCursor.pos())

    def _clamp_into_screen(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        nx = min(max(self.x(), screen.left() - WIN_W + 70), screen.right() - 70)
        ny = min(max(self.y(), screen.top()), screen.bottom() - 70)
        self.move(nx, ny)

    def _reset(self) -> None:
        self.level, self.xp, self.total_xp = 1, 0, 0
        self.floats.clear()
        self.save()

    def _quit(self) -> None:
        self.save()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        self.save()
        super().closeEvent(event)


def _make_icon() -> QIcon:
    """代码生成一个托盘图标，免得额外带素材文件。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#6FA83C")))
    p.drawEllipse(QRectF(6, 12, 52, 40))
    p.setBrush(QBrush(QColor("#A8D465")))
    p.drawEllipse(QRectF(36, 6, 26, 26))
    p.setBrush(QBrush(QColor("#FDFBF3")))
    p.drawEllipse(QRectF(46, 12, 11, 11))
    p.setBrush(QBrush(QColor("#22241C")))
    p.drawEllipse(QRectF(50, 15, 5, 5))
    p.setPen(QPen(QColor("#4A3312"), 3))
    p.drawLine(52, 8, 62, 0)
    p.end()
    return QIcon(pm)


def _excepthook(exc_type, exc, tb) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(exc_type, exc, tb)))
        f.write("\n")


def main() -> None:
    sys.excepthook = _excepthook
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    pet = Pet()
    pet.place_initial()
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
