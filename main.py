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

from PySide6.QtCore import QObject, QRectF, QSharedMemory, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QFont, QIcon,
                           QPainter, QPen, QPixmap, QRegion)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from pynput import keyboard, mouse
from pynput.keyboard import Key

from cricket import Cricket, paint_cricket, palette_from_hex
from panel import StatsPanel
from settings import Settings, SettingsPanel
from stage import FIELD_W as FIELD_W_UI
from stats import StatsDB

# 基准尺寸，实际显示尺寸 = 基准 × 缩放（设置面板可调）
# 顶部多留 TOP_PAD：经验飘字往上升，没这块会被 setMask 裁掉上半截
WIN_W, WIN_H = 190, 224
TOP_PAD = 16
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


class Pet(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.cricket = Cricket()
        self.level = 1
        self.xp = 0
        self.total_xp = 0
        self._stage = None          # 桌面副本战斗舞台（非空 = 副本进行中）
        self._battle_pos = None     # 进入副本前的窗口位置

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
        self._right_down = False  # 右键已按下、尚未抬起
        self._menu_t = 0.0        # 上次弹菜单的时间，用于防重复弹出
        self._pending = 0          # 待汇总显示的经验
        self._pending_t = 0.0
        self.floats = []           # 飘字 [(text, x, y, life, max_life, color)]
        self.levelup_t = 0.0
        self._save_t = 0.0
        self._panel_dirty = False  # 面板数据有变化，待 _tick 节流刷新
        self._panel_t = 0.0

        self._load()
        self.recompute()  # 读档后按存档的品种/等级重算
        self._make_mode_buttons()
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

    # ---------- 模式切换按钮 ----------

    def _make_mode_buttons(self) -> None:
        """挂机：「属性」「副本」；副本战场：「装备」「桌面」。"""
        from PySide6.QtWidgets import QPushButton
        css = ("QPushButton{color:#E8EDF2; background:rgba(0,0,0,120);"
               "border:1px solid rgba(255,255,255,70); border-radius:8px;"
               "font-size:11px;}"
               "QPushButton:hover{background:rgba(143,209,79,150);"
               "border-color:rgba(143,209,79,200);}")
        css_gold = ("QPushButton{color:#1E2430; background:rgba(250,199,117,220);"
                    "border:none; border-radius:8px; font-size:11px;}"
                    "QPushButton:hover{background:rgba(250,199,117,255);}")

        self.btn_attr = QPushButton("属性", self)
        self.btn_attr.setStyleSheet(css)
        self.btn_attr.setFixedSize(40, 18)
        self.btn_attr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_attr.setToolTip("蛐蛐属性 · 装备")
        self.btn_attr.clicked.connect(self._toggle_equipment_panel)

        self.btn_dungeon = QPushButton("副本", self)
        self.btn_dungeon.setStyleSheet(css)
        self.btn_dungeon.setFixedSize(40, 18)
        self.btn_dungeon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dungeon.setToolTip("直进当前可挑战的副本（右键菜单可选难度）")
        self.btn_dungeon.clicked.connect(self._quick_enter_dungeon)

        self.btn_equip_b = QPushButton("装备", self)
        self.btn_equip_b.setStyleSheet(css)
        self.btn_equip_b.setFixedSize(40, 18)
        self.btn_equip_b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_equip_b.setToolTip("战斗中可更换装备，本场结束后生效")
        self.btn_equip_b.clicked.connect(self._toggle_equipment_panel)

        self.btn_desktop = QPushButton("桌面", self)
        self.btn_desktop.setStyleSheet(css_gold)
        self.btn_desktop.setFixedSize(40, 18)
        self.btn_desktop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_desktop.setToolTip("退回挂机模式（进度保存）")
        self.btn_desktop.clicked.connect(self.end_desktop_battle)

        for b in (self.btn_attr, self.btn_dungeon,
                  self.btn_equip_b, self.btn_desktop):
            b.hide()

    def _place_mode_buttons(self) -> None:
        if self._stage is not None:
            # 副本战场：「装备」「桌面」
            self.btn_attr.hide()
            self.btn_dungeon.hide()
            self.btn_equip_b.move(FIELD_W_UI - 98, 10)
            self.btn_equip_b.show()
            self.btn_desktop.move(FIELD_W_UI - 52, 10)
            self.btn_desktop.show()
        else:
            # 挂机模式：「属性」「副本」（随缩放走）
            self.btn_equip_b.hide()
            self.btn_desktop.hide()
            self.btn_attr.move(int((WIN_W - 92) * self.zoom), int(8 * self.zoom))
            self.btn_attr.show()
            self.btn_dungeon.move(int((WIN_W - 46) * self.zoom), int(8 * self.zoom))
            self.btn_dungeon.show()

    def _toggle_equipment_panel(self) -> None:
        from equipment_ui import EquipmentPanel
        panel = getattr(self, "equip_panel", None)
        if panel is not None and panel.isVisible():
            panel.hide()
            return
        if panel is None:
            panel = EquipmentPanel(self)
            self.equip_panel = panel
        panel.refresh()
        panel.show_near(self)

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
        """只在蛐蛐本体、飘字区与经验条的位置接收鼠标事件并渲染。

        mask 之外（窗口的透明区域）事件照旧穿透到桌面，不挡图标；
        mask 之内事件归窗口，右键不会再漏给系统菜单。
        """
        f = self.zoom
        # 飘字带：从窗口顶到蛐蛐头顶，保证 "+12" 这类数字完整显示
        region = QRegion(int(16 * f), 0, int(164 * f), int(70 * f))
        # 蛐蛐本体 + 升级光圈（y 已含 TOP_PAD 偏移；左界/底界给光圈留足空间）
        region = region.united(
            QRegion(int(16 * f), int((36 + TOP_PAD) * f),
                    int(168 * f), int(128 * f)))
        if self.settings.show_bar:
            region = region.united(
                QRegion(int(24 * f), int((162 + TOP_PAD) * f),
                        int(142 * f), int(46 * f)))
        # 模式按钮也要在 mask 内，否则不渲染不可点
        for name in ("btn_attr", "btn_dungeon"):
            b = getattr(self, name, None)
            if b is not None:
                region = region.united(QRegion(b.geometry()))
        self.setMask(region)

    def apply_zoom(self) -> None:
        """按缩放值调整窗口尺寸。"""
        f = self.zoom
        self.setFixedSize(max(60, int(WIN_W * f)), max(60, int(WIN_H * f)))
        self._update_mask()
        self._place_mode_buttons()
        self._clamp_into_screen()
        self.update()

    def set_zoom(self, z: float) -> None:
        self.zoom = max(0.6, min(2.0, float(z)))
        self.apply_zoom()

    def _init_tray(self) -> None:
        self.tray = QSystemTrayIcon(_make_icon(), self)
        menu = QMenu()
        menu.setFont(QFont("Microsoft YaHei", 9))
        act_fight = QAction("发起对战", self)
        act_fight.triggered.connect(self._open_arena)
        act_dungeon = QAction("挑战副本", self)
        act_dungeon.triggered.connect(self._open_dungeon_select)
        act_attr = QAction("蛐蛐属性", self)
        act_attr.triggered.connect(self._toggle_panel)
        act_cfg = QAction("蛐蛐设置", self)
        act_cfg.triggered.connect(self._toggle_settings)
        act_quit = QAction("退出游戏", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_dungeon)
        menu.addAction(act_fight)
        menu.addSeparator()
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
        # 注意：右键菜单不走全局钩子 —— 钩子在“按下”瞬间就弹菜单，
        # 随后的“抬起”会被菜单窗口当作外部点击，菜单一闪而过。
        # 右键统一由 Qt 的 mousePress/Release 事件对处理，抬起时再弹。
        # 左键拖动同理不走全局钩子（见 _on_press 注释），只保留加经验。

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

    # ---------- 桌面副本 ----------

    def _on_desktop_diff_clear(self, res: dict) -> None:
        """桌面副本通关：庆祝演出 → 自动撤回挂机模式。"""
        from PySide6.QtCore import QTimer
        stage = self._stage
        if stage is None:
            return
        first = res.get("first_clear", False)

        # 新解锁提示
        order = self.db.data.get("_副本难度顺序", [])
        did = stage.drun.diff_id
        idx = order.index(did) if did in order else -1
        unlock_txt = ""
        if 0 <= idx + 1 < len(order):
            nxt = order[idx + 1]
            nxt_name = self.db.data["副本难度"][nxt].get("名称", "")
            unlock_txt = nxt_name
            self._float_unlock = nxt_name

        stage._float("副本通关！", 0, "#FAC775", -80)
        stage._float("首通！" if first else "通关", 0, "#FAC775", -56)
        if unlock_txt:
            stage._float(f"已解锁「{unlock_txt}」", 0, "#97C459", -34)
        stage._log(f"「{stage.drun.diff_name()}」副本通关！"
                   + ("（首通）" if first else ""))
        # 庆祝 4.5 秒后自动撤回挂机模式
        QTimer.singleShot(4500, self._delayed_exit_battle)

    def _delayed_exit_battle(self) -> None:
        if self._stage is not None and self._stage.dungeon_result is not None:
            self.end_desktop_battle()
        elif self._stage is not None and self._stage.drun is not None:
            # 兜底：无论断点状态，通关演出结束后一律撤回挂机
            self.end_desktop_battle()

    def begin_desktop_battle(self, diff_id: str | None = None,
                             resume: bool = False) -> None:
        """副本直接在桌面上打：窗口临时扩为战场，蛐蛐原地迎战。"""
        from stage import BattleStage, FIELD_W, FIELD_H, FIELD_R
        old = getattr(self, "arena_win", None)
        if old is not None:
            old.close()
        self._battle_pos = (self.x(), self.y())
        self._stage = BattleStage(self, style="desktop", diff_id=diff_id,
                                  resume=resume, cx=FIELD_W / 2,
                                  cy=FIELD_H / 2 - 10, radius=FIELD_R)
        self._stage.on_diff_clear = self._on_desktop_diff_clear
        scr = QApplication.primaryScreen().availableGeometry()
        fx = max(scr.left(), min(int(self.x() + self.width() / 2 - FIELD_W / 2),
                                 scr.right() - FIELD_W))
        fy = max(scr.top(), min(int(self.y() + self.height() / 2 - FIELD_H / 2),
                                scr.bottom() - FIELD_H))
        self.setFixedSize(FIELD_W, FIELD_H)
        self.move(fx, fy)
        self.clearMask()          # 解除蛐蛐 mask，整个战场可绘
        self._place_mode_buttons()   # 藏「副本」、亮「桌面」
        self.raise_()

    def end_desktop_battle(self) -> None:
        if self._stage is not None:
            self._stage.on_exit()
            self._stage = None
        self.apply_zoom()         # 恢复蛐蛐尺寸与 mask
        if self._battle_pos:
            self.move(*self._battle_pos)
        self._place_mode_buttons()   # 藏「桌面」、亮「副本」

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
        # 只关心左键按下（加经验）；右键菜单与拖动都由 Qt 事件处理，见 _init_hook
        if button == mouse.Button.left and pressed:
            self.bridge.press.emit()

    # ---------- 主线程槽 ----------

    def _on_key(self) -> None:
        self._add_xp(XP_PER_KEY)

    def _on_press(self) -> None:
        # 全局钩子只负责加经验。拖动一律走 Qt 的 mousePressEvent（mask 内才算抓住蛐蛐）。
        # 以前这里按“光标在窗口矩形内”就开拖 —— 窗口大片透明区也会中招：
        # 看着点的是桌面/面板旁边，实际点在隐形窗口上，蛐蛐开始追着鼠标跑，
        # 面板也收不到点击。这就是“面板无法操作、鼠标靠近面板蛐蛐乱跑”的根因。
        self._add_xp(XP_PER_CLICK)

    def _add_xp(self, n: int) -> None:
        self.xp += n
        self.total_xp += n
        self._pending += n
        self._panel_dirty = True   # 属性面板若开着，由 _tick 节流刷新
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
            self._panel_dirty = True

    # ---------- 主循环 ----------

    def _tick(self) -> None:
        dt = 0.016
        # 桌面副本进行中：驱动战斗舞台，蛐蛐挂机绘制暂停
        if self._stage is not None:
            if self._dragging and self._offset is not None:
                self.move(QCursor.pos() - self._offset)
            self._stage.update(dt)
            self.update()
            self._save_t += dt
            if self._save_t >= 10.0:
                self._save_t = 0.0
                self.save()
            return

        self.cricket.update(dt)

        # 保险：拖动状态里左键已经物理松开（release 被弹窗吃掉等极端情况）
        # 就自动复位，避免蛐蛐永久追着鼠标跑
        if self._dragging and not (QApplication.mouseButtons()
                                   & Qt.MouseButton.LeftButton):
            self._dragging = False

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

        # 属性面板开着时同步经验/等级（0.3s 节流，避免打字时每键重刷整块面板）
        self._panel_t += dt
        if (self._panel_dirty and self._panel_t >= 0.3
                and self.panel is not None and self.panel.isVisible()):
            self.panel.refresh()
            self._panel_dirty = False
            self._panel_t = 0.0

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
        # 桌面副本进行中：整个窗口让位给战斗舞台
        if self._stage is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._stage.draw(p)
            p.end()
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 整体下移 TOP_PAD，给顶部飘字留出渲染空间（mask 同步扩过）
        p.translate(0, TOP_PAD * self.zoom)

        f = self.zoom

        if self.levelup_t > 0:
            k = self.levelup_t / 1.8
            # 光圈扩散最大 160*f，必须小于窗口宽 190*f，否则两端被窗口边缘裁出直边
            gw = 100 * f * (1.6 - k * 0.6)
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
        """只吞掉系统合成的右键菜单事件，不再在这里弹菜单。

        菜单统一在 mouseReleaseEvent（右键抬起）时弹出 —— 若在这里
        （按下阶段）弹，随后的抬起会被菜单当作外部点击，菜单一闪而过。
        """
        event.accept()

    def mousePressEvent(self, event) -> None:
        """左键按下：开始拖动。

        按下落在 mask（蛐蛐本体）内时窗口会拿到系统级鼠标捕获，
        拖动期间消息全归本窗口，桌面不会拉选区。
        右键只记录“已按下”，抬起时才弹菜单（Windows 惯例）。
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._right_down = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self._dragging):
            self._dragging = False
            self._clamp_into_screen()
            self.save()
            event.accept()
            return
        if (event.button() == Qt.MouseButton.RightButton
                and self._right_down):
            self._right_down = False
            event.accept()
            # 按下/抬起都已由本窗口消化，此刻弹菜单不会再被“抬起”关掉
            self._show_menu()
            return
        super().mouseReleaseEvent(event)

    def _show_menu(self) -> None:
        """右键菜单。副本进行中切换为副本菜单。"""
        if self._stage is not None:
            menu = QMenu()
            menu.setFont(QFont("Microsoft YaHei", 9))
            act_quit_d = QAction("撤出副本（进度保存）", self)
            act_quit_d.triggered.connect(self.end_desktop_battle)
            act_quit = QAction("退出游戏", self)
            act_quit.triggered.connect(self._quit)
            menu.addAction(act_quit_d)
            menu.addSeparator()
            menu.addAction(act_quit)
            menu.exec(QCursor.pos())
            return
        # 防重入：0.4 秒内只弹一次（连点右键不会疯狂闪菜单）
        now = time.monotonic()
        if now - self._menu_t < 0.4:
            return
        if not self.geometry().contains(QCursor.pos()):
            return
        self._menu_t = now
        menu = QMenu()
        menu.setFont(QFont("Microsoft YaHei", 9))
        act_fight = QAction("发起对战", self)
        act_fight.triggered.connect(self._open_arena)
        act_dungeon = QAction("挑战副本", self)
        act_dungeon.triggered.connect(self._open_dungeon_select)
        act_attr = QAction("蛐蛐属性", self)
        act_attr.triggered.connect(self._toggle_panel)
        act_cfg = QAction("蛐蛐设置", self)
        act_cfg.triggered.connect(self._toggle_settings)
        act_quit = QAction("退出游戏", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_dungeon)
        menu.addAction(act_fight)
        menu.addSeparator()
        menu.addAction(act_attr)
        menu.addAction(act_cfg)
        menu.addSeparator()
        menu.addAction(act_quit)
        menu.exec(QCursor.pos())

    def _open_arena(self) -> None:
        """打开竞技场：自动观战，赢了给蛐蛐加经验。"""
        from arena import ArenaWindow
        if getattr(self, "arena_win", None) is not None \
                and self.arena_win.isVisible():
            self.arena_win.raise_()
            return
        self.arena_win = ArenaWindow(self)

    def _quick_enter_dungeon(self) -> None:
        """副本按钮直进：断点优先，否则打已解锁的最前沿难度。"""
        from dungeon import DungeonRun
        if DungeonRun.load_run(self.db) is not None:
            self.begin_desktop_battle(resume=True)
            return
        cleared = DungeonRun.load_cleared()
        order = self.db.data.get("_副本难度顺序", [])
        target = order[-1] if order else "d01"
        for did in order:
            conf = self.db.data["副本难度"].get(did, {})
            pre = str(conf.get("解锁前置", "") or "")
            if (not pre or pre in cleared) and did not in cleared:
                target = did
                break
        self.begin_desktop_battle(diff_id=target)

    def _open_dungeon_select(self) -> None:
        """打开副本难度选择面板。"""
        from arena import DungeonSelect
        sel = getattr(self, "dungeon_sel", None)
        if sel is not None and sel.isVisible():
            sel.raise_()
            return

        def start(diff_id):
            old = getattr(self, "arena_win", None)
            if old is not None:
                old.close()
            if diff_id is None:
                self.begin_desktop_battle(resume=True)
            else:
                self.begin_desktop_battle(diff_id=diff_id)

        self.dungeon_sel = DungeonSelect(self, start)
        self.dungeon_sel.show_near(self)

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
        if self._stage is not None:
            self._stage.on_exit()   # 副本断点保存
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

    # 单实例锁：重复启动会出现好几只蛐蛐、右键也会弹出好几个菜单
    guard = QSharedMemory("QuQuBattleGame.SingleInstance")
    if not guard.create(1):
        print("电子斗蛐蛐已经在运行了")
        sys.exit(0)

    pet = Pet()
    pet.place_initial()
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
