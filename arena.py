# -*- coding: utf-8 -*-
"""蛐蛐竞技场窗口：战斗舞台（stage.py）的窗口宿主。

现在只负责窗口壳子 —— 战场逻辑、走位编排、绘制全在 stage.BattleStage。
好友对战在这里打；副本已移到桌面直接进行（main.py → pet 桌面模式）。
"""

from __future__ import annotations

import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from battle import make_fighter
from cricket import Cricket, paint_cricket_top, palette_from_hex
from dungeon import DungeonRun
from panel import CardPanel
from stage import BattleStage, WIN_ARENA_W, WIN_ARENA_H, e_reason
from stats import StatsDB, fmt_num


class ArenaWindow(QWidget):
    """好友对战窗口（陶罐竞技场）。"""

    def __init__(self, pet, diff_id: str | None = None, resume: bool = False):
        super().__init__()
        self.pet = pet
        self.setWindowTitle("蛐蛐竞技场")
        self.setFixedSize(WIN_ARENA_W, WIN_ARENA_H)

        self.stage = BattleStage(pet, style="arena", diff_id=diff_id,
                                 resume=resume, cx=380, cy=306, radius=196)
        self.stage.on_diff_clear = self._show_dungeon_result
        self.stage.on_pvp_end = self._show_pvp_result
        self._next_diff = None

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._frame)

        self._build_result_overlay()
        self.timer.start()
        self.show_center()

    def show_center(self) -> None:
        scr = self.screen().availableGeometry()
        self.move(scr.center().x() - WIN_ARENA_W // 2,
                  scr.center().y() - WIN_ARENA_H // 2)
        self.show()
        self.raise_()

    def _frame(self) -> None:
        self.stage.update()
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#232733"))
        if self.stage.shake_t > 0:
            p.translate(random.uniform(-3, 3), random.uniform(-3, 3))
        self.stage.draw(p)
        p.end()

    def closeEvent(self, event) -> None:
        self.stage.on_exit()
        super().closeEvent(event)

    # ---------- 结算 ----------

    def _build_result_overlay(self) -> None:
        box = QWidget(self)
        box.setGeometry(180, 150, 400, 230)
        box.setStyleSheet(
            "QWidget{background:#1A2028; border:1px solid rgba(255,255,255,0.16);"
            "border-radius:12px;}")
        self.result_box = box
        root = QVBoxLayout(box)
        root.setContentsMargins(20, 16, 20, 16)

        self.r_title = QLabel("战斗结束")
        self.r_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.r_title.setStyleSheet(
            "border:none; color:#E8EDF2; font-size:22px; font-weight:600;")
        root.addWidget(self.r_title)

        self.r_detail = QLabel("")
        self.r_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.r_detail.setStyleSheet("border:none; color:#8B97A6; font-size:12px;")
        self.r_detail.setWordWrap(True)
        root.addWidget(self.r_detail)

        root.addSpacing(8)
        btns = QHBoxLayout()
        css = ("QPushButton{color:#E8EDF2; background:rgba(143,209,79,0.85);"
               "border:none; border-radius:6px; padding:8px; font-size:13px;}"
               "QPushButton:hover{background:rgba(143,209,79,1.0);}"
               "QPushButton#gray{color:#8B97A6; background:rgba(255,255,255,0.08);}"
               "QPushButton#gray:hover{background:rgba(255,255,255,0.14);}")
        b_again = QPushButton("再来一场")
        b_again.setStyleSheet(css)
        b_again.clicked.connect(self._on_again)
        self.r_again_btn = b_again
        btns.addWidget(b_again)

        b_close = QPushButton("收兵")
        b_close.setObjectName("gray")
        b_close.setStyleSheet(css)
        b_close.clicked.connect(self.close)
        btns.addWidget(b_close)
        root.addLayout(btns)
        box.hide()   # show_center 的 show() 会连带显示子部件，必须显式藏起

    def _show_pvp_result(self) -> None:
        w = self.stage.battle.winner
        a, b = self.stage.battle.fighters
        title = "平局" if w is None else ("胜利！" if w == 0 else "战败…")
        color = "#8FD14F" if w == 0 else ("#F09595" if w == 1 else "#B4B2A9")
        self.r_title.setText(title)
        self.r_title.setStyleSheet(
            f"border:none; color:{color}; font-size:22px; font-weight:600;")

        xp = {0: 30 + 6 * b.level, 1: 6}.get(w, 12)
        self.pet._add_xp(xp)

        self.r_detail.setText(
            f"{e_reason(self.stage.battle.end_reason)}\n"
            f"{a.name}  输出 {fmt_num(a.dealt)} / 受创 {fmt_num(a.taken)}\n"
            f"{b.name}  输出 {fmt_num(b.dealt)} / 受创 {fmt_num(b.taken)}\n"
            f"共 {self.stage.battle.rounds} 回合 · 种子 {self.stage.seed}（可用于复盘）\n"
            f"你的蛐蛐获得经验 +{xp}")
        self.r_again_btn.setText("再来一场")
        self.result_box.show()
        self.result_box.raise_()

    def _show_dungeon_result(self) -> None:
        res = self.stage.dungeon_result or {}
        first = res.get("first_clear", False)
        self.r_title.setText("首通！" if first else "通关！")
        self.r_title.setStyleSheet(
            "border:none; color:#FAC775; font-size:22px; font-weight:600;")

        order = self.stage.db.data.get("_副本难度顺序", [])
        did = self.stage.drun.diff_id
        idx = order.index(did) if did in order else -1
        self._next_diff = order[idx + 1] if 0 <= idx + 1 < len(order) else None
        if self._next_diff:
            nxt = self.stage.db.data["副本难度"][self._next_diff].get("名称", "")
            self.r_again_label = f"挑战「{nxt}」"
        else:
            self.r_again_label = "再战本难度"

        a, b = self.stage.battle.fighters
        self.r_detail.setText(
            f"「{self.stage.drun.diff_name()}」副本攻略完成\n"
            f"总击杀 {self.stage.drun.kills} 只 · "
            f"累计经验 {fmt_num(self.stage.drun.total_xp)}\n"
            f"当前等级 Lv.{self.pet.level}"
            + ("（首通记录已保存）" if first else ""))
        self.r_again_btn.setText(self.r_again_label)
        self.result_box.show()
        self.result_box.raise_()

    def _on_again(self) -> None:
        if self.stage.drun is not None and self._next_diff:
            self.result_box.hide()
            self.stage = BattleStage(
                self.pet, style="arena", diff_id=self._next_diff,
                cx=380, cy=306, radius=196)
            self.stage.on_diff_clear = self._show_dungeon_result
            self.stage.on_pvp_end = self._show_pvp_result
            self._next_diff = None
        else:
            self.result_box.hide()
            self.stage._restart()


class DungeonSelect(CardPanel):
    """副本难度选择面板（副本以桌面模式进行，宿主是桌宠本体）。"""

    def __init__(self, pet, on_start):
        CardPanel.__init__(self, "挑战副本（桌面开战）", 400, 560)
        self.on_start = on_start
        self.db = StatsDB()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(6)
        self.build_header(root)

        css = ("QPushButton{text-align:left; color:#E8EDF2;"
               "background:rgba(255,255,255,0.06);"
               "border:1px solid rgba(255,255,255,0.12); border-radius:6px;"
               "padding:7px 10px; font-size:12px;}"
               "QPushButton:hover{background:rgba(143,209,79,0.28);}"
               "QPushButton:disabled{color:#55606E; background:rgba(255,255,255,0.03);}")

        loaded = DungeonRun.load_run(self.db)
        if loaded:
            dr, _hp, _sta = loaded
            b = QPushButton(f"▶ 继续进度：{dr.diff_name()} 第 {dr.floor} 层")
            b.setStyleSheet(css + "QPushButton{color:#8FD14F;}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: self._go(None))
            root.addWidget(b)

        cleared = DungeonRun.load_cleared()
        order = self.db.data.get("_副本难度顺序", [])
        for did in order:
            conf = self.db.data["副本难度"].get(did, {})
            if not conf:
                continue
            pre = str(conf.get("解锁前置", "") or "")
            unlocked = (not pre) or (pre in cleared)
            done = did in cleared
            label = (f"{conf.get('名称', did)}    "
                     f"{conf.get('每层敌人数', 3)} 敌/层 · "
                     f"Lv{conf.get('等级下限', 1)}-{conf.get('等级上限', 10)}"
                     + ("   ✓已通关" if done else ""))
            b = QPushButton(label)
            b.setStyleSheet(css)
            b.setEnabled(unlocked)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if not unlocked:
                b.setText(label + "（通关上一难度解锁）")
            b.clicked.connect(lambda _=False, d=did: self._go(d))
            root.addWidget(b)

        root.addStretch()
        hint = QLabel("副本在桌面上直接进行：敌人会走到你的蛐蛐身边开战，"
                      "击败后自动增援下一只，清层自动推进。"
                      "战败退回上一层重来（新手第 1 层除外）。"
                      "右键蛐蛐可随时撤出副本，进度自动保存。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#55606E; font-size:11px;")
        root.addWidget(hint)

    def _go(self, diff_id: str | None) -> None:
        self.hide()
        self.on_start(diff_id)
