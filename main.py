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
import time
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(APP_DIR, "save.json")
LOG_FILE = os.path.join(APP_DIR, "error.log")

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QFont, QIcon,
                           QPainter, QPen, QPixmap, QRegion)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from pynput import keyboard, mouse
from pynput.keyboard import Key

from cricket import Cricket, paint_cricket, palette_from_hex
from panel import StatsPanel
from settings import Settings, SettingsPanel
from stats import StatsDB

# 基准尺寸，实际显示尺寸 = 基准 × 缩放（设置面板可调）
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

        # 数值表驱动：品种 + 等级 + 天赋 -> 最终属性
        self.db = StatsDB()
        self.settings = Settings()
        self.zoom = self.settings.zoom
        self.species_id = self.settings.species_id
        self.talents = []
        self.stats = {}
        self.palette = None
        self.recompute()

        self._dragging = False
        self._offset = None
        self._menu_t = 0.0        # 上次弹菜单的时间，用于防重复弹出
        self._pending = 0          # 待汇总显示的经验
        self._pending_t = 0.0
        self.floats = []           # 飘字 [(text, x, y, life, max_life, color)]
        self.levelup_t = 0.0
        self._save_t = 0.0

        self._load()
        self.recompute()  # 读档后按存档的品种/等级重算
        self._init_window()
        # 必须在钩子启动前建好，否则首次按键可能访问到尚未创建的面板
        self.panel = StatsPanel(self)
        self.settings_panel = SettingsPanel(self)
        self._init_tray()
        self._init_hook()

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    # ---------- 初始化 ----------

    def _init_window(self) -> None:
        self.apply_flags()
        self.apply_zoom()

    def apply_flags(self) -> None:
        """置顶开关。改 flags 会隐藏窗口，所以要重新 show。"""
        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        if self.settings.always_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        # 注意：不能用 WA_TransparentForMouseEvents —— 那会让右键穿透到桌面，
        # 弹出系统的“刷新/查看”菜单。改用 setMask 只占住蛐蛐本体那一块。
        self.setWindowTitle("电子斗蛐蛐")
        if was_visible:
            self.show()
        self._update_mask()

    def _update_mask(self) -> None:
        """只在蛐蛐本体与经验条的位置接收鼠标事件。

        mask 之外（窗口的透明区域）事件照旧穿透到桌面，不挡图标；
        mask 之内事件归窗口，右键不会再漏给系统菜单。
        """
        f = self.zoom
        # 蛐蛐绘制范围：本地 x∈[-45,63]、y∈[-55,22]，再按 SCALE 与脚底位置换算
        region = QRegion(int(34 * f), int(36 * f), int(150 * f), int(126 * f))
        if self.settings.show_bar:
            region = region.united(
                QRegion(int(24 * f), int(162 * f), int(142 * f), int(46 * f)))
        self.setMask(region)

    def apply_zoom(self) -> None:
        """按缩放值调整窗口尺寸。"""
        f = self.zoom
        self.setFixedSize(max(60, int(WIN_W * f)), max(60, int(WIN_H * f)))
        self._update_mask()
        self._clamp_into_screen()
        self.update()

    def set_zoom(self, z: float) -> None:
        self.zoom = max(0.6, min(2.0, float(z)))
        self.apply_zoom()

    def _init_tray(self) -> None:
        self.tray = QSystemTrayIcon(_make_icon(), self)
        menu = QMenu()
        menu.setFont(QFont("Microsoft YaHei", 9))
        act_attr = QAction("蛐蛐属性", self)
        act_attr.triggered.connect(self._toggle_panel)
        act_cfg = QAction("蛐蛐设置", self)
        act_cfg.triggered.connect(self._toggle_settings)
        act_quit = QAction("退出游戏", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_attr)
        menu.addAction(act_cfg)
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

    # ---------- 属性 ----------

    def recompute(self) -> None:
        """按数值表重算属性与配色。等级或品种变化后都要调用。"""
        self.stats, self._cond = self.db.compute(
            self.species_id, self.level, self.talents)
        sp = self.db.species(self.species_id) or {}
        self.palette = palette_from_hex(str(sp.get("主色", "#6FA83C")))

    def set_species(self, sid: str) -> None:
        if self.db.species(sid):
            self.species_id = sid
            self.recompute()

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
            self.species_id = str(d.get("species_id", "c001"))
            self.talents = list(d.get("talents", []))
            if d.get("x") is not None and d.get("y") is not None:
                self._start_pos = (int(d["x"]), int(d["y"]))
        except Exception:
            self._start_pos = None

    def save(self) -> None:
        data = {
            "level": self.level,
            "xp": self.xp,
            "total_xp": self.total_xp,
            "species_id": self.species_id,
            "talents": self.talents,
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
        self.move(screen.right() - self.width() - 40,
                  screen.bottom() - self.height() - 60)

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
        leveled = False
        while self.xp >= self.db.exp_need(self.level):
            self.xp -= self.db.exp_need(self.level)
            self.level += 1
            leveled = True
            self.levelup_t = 1.8
            self.cricket.level_up()
            self.floats.append(["升级!", 0.0, 0.0, 1.8, 1.8, QColor("#F2B233")])
        if leveled:
            self.recompute()
            if self.panel is not None and self.panel.isVisible():
                self.panel.refresh()

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

        f = self.zoom

        if self.levelup_t > 0:
            k = self.levelup_t / 1.8
            gw = 124 * f * (1.6 - k * 0.6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(242, 178, 51, int(70 * k))))
            p.drawEllipse(QRectF(CX * f - gw / 2, (FOOT_Y - 96) * f, gw, 104 * f))

        paint_cricket(p, CX * f, FOOT_Y * f, SCALE * f, self.cricket, self.palette)

        self._draw_floats(p, f)
        if self.settings.show_bar:
            self._draw_bar(p, f)
        p.end()

    def _draw_floats(self, p: QPainter, f: float) -> None:
        size = max(8, min(17, int(10 * f)))
        font = QFont("Microsoft YaHei", size)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        for text, dx, dy, life, max_life, color in self.floats:
            alpha = min(1.0, life / (max_life * 0.5))
            c = QColor(color)
            c.setAlphaF(alpha)
            r = QRectF((CX + dx) * f - 60 * f, (FOOT_Y - 128) * f - dy * f,
                       120 * f, 22 * f)
            p.setPen(QPen(QColor(0, 0, 0, int(120 * alpha)), 3.0))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QPen(c, 1.0))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_bar(self, p: QPainter, f: float) -> None:
        need = self.db.exp_need(self.level)
        ratio = max(0.0, min(1.0, self.xp / need))
        x, y, w, h = 34.0 * f, 170.0 * f, 122.0 * f, 9.0 * f

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 95)))
        p.drawRoundedRect(QRectF(x, y, w, h), 4.5 * f, 4.5 * f)
        p.setBrush(QBrush(QColor("#8FD14F")))
        p.drawRoundedRect(QRectF(x, y, w * ratio, h), 4.5 * f, 4.5 * f)
        p.setBrush(QBrush(QColor(255, 255, 255, 70)))
        p.drawRoundedRect(QRectF(x + 1, y + 1, max(0.0, w * ratio - 2), 3 * f),
                          1.5 * f, 1.5 * f)

        # 文字底衬：桌面上背景不可控，加个深色胶囊保证任何壁纸下都能看清
        cap_w, cap_h = 108 * f, 19 * f
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 135)))
        p.drawRoundedRect(QRectF(x + w / 2 - cap_w / 2, y + 12 * f, cap_w, cap_h),
                          9.5 * f, 9.5 * f)

        font = QFont("Microsoft YaHei", max(8, min(14, int(9 * f))))
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        label = f"Lv.{self.level}  {self.xp} / {need}"
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.0))
        p.drawText(QRectF(x + w / 2 - cap_w / 2, y + 12 * f, cap_w, cap_h),
                   Qt.AlignmentFlag.AlignCenter, label)

    # ---------- 交互 ----------

    def contextMenuEvent(self, event) -> None:
        """右键落在 mask 内时走这里 —— 事件已被窗口吃掉，不会再漏给桌面。"""
        event.accept()
        self._show_menu()

    def _show_menu(self) -> None:
        # 防重入：Qt 事件与全局钩子都可能触发，0.4 秒内只弹一次
        now = time.monotonic()
        if now - self._menu_t < 0.4:
            return
        if not self.geometry().contains(QCursor.pos()):
            return
        self._menu_t = now
        menu = QMenu()
        menu.setFont(QFont("Microsoft YaHei", 9))
        act_attr = QAction("蛐蛐属性", self)
        act_attr.triggered.connect(self._toggle_panel)
        act_cfg = QAction("蛐蛐设置", self)
        act_cfg.triggered.connect(self._toggle_settings)
        act_quit = QAction("退出游戏", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_attr)
        menu.addAction(act_cfg)
        menu.addSeparator()
        menu.addAction(act_quit)
        menu.exec(QCursor.pos())

    def _toggle_panel(self) -> None:
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.panel.show_near(self)
            self.panel.portrait.timer.start()

    def _toggle_settings(self) -> None:
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
        else:
            self.settings_panel.show_near(self)

    def _clamp_into_screen(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        nx = min(max(self.x(), screen.left() - self.width() + 70), screen.right() - 70)
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
