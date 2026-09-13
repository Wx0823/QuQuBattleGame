# -*- coding: utf-8 -*-
"""竞技场：战斗表现层。

battle.py 负责算，本文件负责演 —— 引擎每 0.1 秒吐一批事件，
这里把它们播放成冲刺、受击、飘字、倒下、逃跑等画面。
"""

from __future__ import annotations

import random

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from battle import Battle, make_fighter
from cricket import Cricket, paint_cricket, palette_from_hex
from stats import StatsDB, fmt_num

WIN_W, WIN_H = 720, 470
LEFT_X, RIGHT_X = 175, 545
FOOT_Y = 330
CRICKET_SCALE = 1.55

BAR_W = 210
BAR_HP_Y, BAR_STA_Y, BAR_MOR_Y = 58, 80, 96

STATUS_COLOR = {
    "s001": ("力竭", "#BA7517"), "s002": ("流血", "#A32D2D"),
    "s003": ("破防", "#712B13"), "s004": ("格挡", "#0F6E56"),
    "s005": ("高涨", "#3B6D11"), "s006": ("畏缩", "#993556"),
}

BG_TOP = QColor("#2B3140")
BG_BOT = QColor("#20242E")
SAND = QColor("#C8B78A")


class ArenaWindow(QWidget):
    """两只蛐蛐的自动战斗直播窗口。"""

    def __init__(self, pet):
        super().__init__()
        self.pet = pet
        self.db = StatsDB()
        self.setWindowTitle("蛐蛐竞技场")
        self.setFixedSize(WIN_W, WIN_H)

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._frame)

        self._build_result_overlay()
        self._restart()
        self.show_center()

    # ---------- 开局 ----------

    def _make_side(self, side: int):
        """side 0 = 玩家的蛐蛐；side 1 = 随机对手（同等级野蛐蛐）。"""
        if side == 0:
            sp = self.db.species(self.pet.species_id) or {}
            name = f"{sp.get('名称', '蛐蛐')}·我方"
            f = make_fighter(self.db, 0, name, self.pet.species_id,
                             self.pet.level, self.pet.talents)
            pal = self.pet.palette
        else:
            sid = random.choice(self.db.species_ids())
            sp = self.db.species(sid) or {}
            name = f"{sp.get('名称', '野蛐蛐')}·野"
            f = make_fighter(self.db, 1, name, sid, self.pet.level)
            pal = palette_from_hex(str(sp.get("主色", "#6FA83C")))
        c = Cricket()
        c.act_next = 9999          # 战斗中禁止随机蹦跶
        c.facing = c.facing_target = -1.0 if side == 1 else 1.0
        return f, c, pal

    def _restart(self) -> None:
        self.f = [self._make_side(0), self._make_side(1)]
        seed = random.randrange(1 << 30)
        self.battle = Battle(self.db, self.f[0][0], self.f[1][0], seed=seed)
        self.seed = seed
        self.acc = 0.0
        self.intro_t = 1.0         # VS 开场倒计时
        self.end_t = -1.0          # 结束后延迟出结算
        self.shake_t = 0.0
        self.fx = {
            "lunge": [0.0, 0.0], "flash": [0.0, 0.0], "guard": [0.0, 0.0],
            "floats": [],          # (text, side, dy, life, color)
            "flee": None,          # (side, dx)
            "ko": None,            # side
        }
        self.log: list[str] = [" waiting"]
        self.result_box.hide()
        self.timer.start()

    def show_center(self) -> None:
        scr = self.screen().availableGeometry()
        self.move(scr.center().x() - WIN_W // 2,
                  scr.center().y() - WIN_H // 2)
        self.show()
        self.raise_()

    # ---------- 主循环 ----------

    def _frame(self) -> None:
        dt = 0.03
        if self.intro_t > 0:
            self.intro_t -= dt
        else:
            # 引擎推进（固定 0.1s 步长）
            self.acc += dt
            tick = float(self.db.const("TICK", 0.1))
            while self.acc >= tick and not self.battle.over:
                self.acc -= tick
                for e in self.battle.step():
                    self._play(e)

        if self.end_t > 0:
            self.end_t -= dt
            if self.end_t <= 0:
                self._show_result()

        for k in (0, 1):
            self.fx["lunge"][k] = max(0.0, self.fx["lunge"][k] - dt)
            self.fx["flash"][k] = max(0.0, self.fx["flash"][k] - dt)
            self.fx["guard"][k] = max(0.0, self.fx["guard"][k] - dt)
        self.shake_t = max(0.0, self.shake_t - dt)

        for fl in self.fx["floats"]:
            fl[2] += 42 * dt
            fl[3] -= dt
        self.fx["floats"] = [x for x in self.fx["floats"] if x[3] > 0]

        # 蛐蛐待机动画
        for i in (0, 1):
            f, c, _pal = self.f[i]
            if (self.fx["ko"] == i or
                    (self.fx["flee"] and self.fx["flee"][0] == i)):
                continue
            c.update(dt)

        if self.fx["flee"]:
            side, dx = self.fx["flee"]
            self.fx["flee"] = (side, dx + 300 * dt)

        self.update()

    # ---------- 事件播放 ----------

    def _float(self, text: str, side: int, color: str, dy: float = 0.0) -> None:
        self.fx["floats"].append([text, side, dy, 1.1, QColor(color)])

    def _play(self, e: dict) -> None:
        t = e["type"]
        names = (self.f[0][0].name, self.f[1][0].name)
        if t == "start":
            self._log(f"开战！{names[0]} VS {names[1]}")
        elif t == "hit":
            side = e["side"]
            self.fx["lunge"][side] = 0.26
            self.fx["flash"][1 - side] = 0.22
            if e.get("crit"):
                self.shake_t = 0.3
            self._float(f"{'暴击 ' if e.get('crit') else ''}-{e['dmg']}",
                        1 - side, "#F09595" if side == 1 else "#E24B4A", -34)
            if e.get("guarded"):
                self.fx["guard"][1 - side] = 0.5
                self._float("格挡!", 1 - side, "#5DCAA5", -52)
            self._log(f"{names[side]} 使出「{e['move']}」"
                      f"{'暴击' if e.get('crit') else '命中'} {e['dmg']}"
                      f"{'（被格挡）' if e.get('guarded') else ''}")
        elif t == "miss":
            self.fx["lunge"][e["side"]] = 0.26
            self._float("闪避", 1 - e["side"], "#B4B2A9", -34)
            self._log(f"{names[e['side']]} 的「{e['move']}」被躲开了")
        elif t == "guard_up":
            self.fx["guard"][e["side"]] = 0.8
            self._log(f"{names[e['side']]} 摆出「{e['move']}」架势")
        elif t == "chirp":
            self._float("♪", e["side"], "#FAC775", -50)
            self._float("+士气", e["side"], "#97C459", -30)
            self._float("-士气", 1 - e["side"], "#F09595", -30)
            self.f[e["side"]][1].chirp = 0.8
            self._log(f"{names[e['side']]} 振翅鸣叫，气势大振！")
        elif t == "bleed":
            self.fx["flash"][e["side"]] = 0.15
            self._float(f"-{e['dmg']}", e["side"], "#ED93B1", -20)
        elif t == "reflect":
            self._float(f"-{e['dmg']}", e["side"], "#F0997B", -20)
        elif t == "exhaust":
            self._float("力竭!", e["side"], "#EF9F27", -46)
            self._log(f"{names[e['side']]} 耐力见底，暂时动弹不得")
        elif t == "end":
            self.end_t = 1.1
            w = e["winner"]
            if e["reason"] == "击倒":
                self.fx["ko"] = 1 - w
                self._log(f"{names[w]} 将对手掀翻在地，胜！")
            elif e["reason"] == "士气崩溃":
                loser = 1 - w
                self.fx["flee"] = (loser, 0.0)
                self.f[loser][1].facing_target = -1.0 if loser == 0 else 1.0
                self._log(f"{names[loser]} 斗性崩溃，掉头就跑！")
            else:
                self._log(f"战至超时，{e['reason']}"
                          + (f"，{names[w]}胜" if w is not None else "，平局"))

    def _log(self, text: str) -> None:
        self.log.append(text)
        self.log = self.log[-4:]

    # ---------- 结算 ----------

    def _build_result_overlay(self) -> None:
        box = QWidget(self)
        box.setGeometry(160, 120, 400, 230)
        box.setStyleSheet(
            "QWidget{background:#1A2028; border:1px solid rgba(255,255,255,0.16);"
            "border-radius:12px;}")
        self.result_box = box
        root = QVBoxLayout(box)
        root.setContentsMargins(20, 16, 20, 16)

        self.r_title = QLabel("战斗结束")
        self.r_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.r_title.setStyleSheet("border:none; color:#E8EDF2; font-size:22px; font-weight:600;")
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
        b_again.clicked.connect(self._restart)
        b_close = QPushButton("收兵")
        b_close.setObjectName("gray")
        b_close.setStyleSheet(css)
        b_close.clicked.connect(self.close)
        btns.addWidget(b_again)
        btns.addWidget(b_close)
        root.addLayout(btns)

    def _show_result(self) -> None:
        w = self.battle.winner
        a, b = self.battle.fighters
        title = "平局" if w is None else ("胜利！" if w == 0 else "战败…")
        color = "#8FD14F" if w == 0 else ("#F09595" if w == 1 else "#B4B2A9")
        self.r_title.setText(title)
        self.r_title.setStyleSheet(
            f"border:none; color:{color}; font-size:22px; font-weight:600;")

        xp = 0
        if w == 0:
            xp = 30 + 6 * b.level
        elif w == 1:
            xp = 6
        else:
            xp = 12
        if xp > 0:
            self.pet._add_xp(xp)

        self.r_detail.setText(
            f"{e_reason(self.battle.end_reason)}\n"
            f"{a.name}  输出 {fmt_num(a.dealt)} / 受创 {fmt_num(a.taken)}\n"
            f"{b.name}  输出 {fmt_num(b.dealt)} / 受创 {fmt_num(b.taken)}\n"
            f"共 {self.battle.rounds} 回合 · 种子 {self.seed}（可用于复盘）\n"
            f"你的蛐蛐获得经验 +{xp}")
        self.result_box.show()
        self.result_box.raise_()

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 背景 + 地面
        p.fillRect(self.rect(), BG_TOP)
        p.fillRect(QRectF(0, 0, WIN_W, 140), BG_BOT)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(SAND))
        p.drawEllipse(QRectF(-80, FOOT_Y - 6, WIN_W + 160, 130))

        # 震屏（暴击时）
        if self.shake_t > 0:
            import random as _r
            p.translate(_r.uniform(-3, 3), _r.uniform(-3, 3))

        for i in (0, 1):
            self._draw_fighter(p, i)

        self._draw_floats(p)
        self._draw_log(p)
        if self.intro_t > 0:
            self._draw_vs(p)
        p.end()

    def _fighter_x(self, i: int) -> float:
        x = LEFT_X if i == 0 else RIGHT_X
        lunge = self.fx["lunge"][i]
        if lunge > 0:
            prog = 1.0 - lunge / 0.26
            off = 70 * (1 if i == 0 else -1)
            import math
            x += math.sin(prog * 3.14159) * off
        if self.fx["flee"] and self.fx["flee"][0] == i:
            x -= self.fx["flee"][1] * (1 if i == 0 else -1)
        return x

    def _draw_fighter(self, p: QPainter, i: int) -> None:
        f, c, pal = self.f[i]
        x = self._fighter_x(i)

        paint_cricket(p, x, FOOT_Y, CRICKET_SCALE, c, pal)

        # 受击闪白
        if self.fx["flash"][i] > 0:
            a = int(150 * self.fx["flash"][i] / 0.22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, a)))
            p.drawEllipse(QRectF(x - 52, FOOT_Y - 96, 104, 100))

        # 格挡护罩
        if self.fx["guard"][i] > 0:
            a = int(160 * min(1.0, self.fx["guard"][i] / 0.5))
            p.setPen(QPen(QColor(93, 202, 165, a), 3.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(x - 46, FOOT_Y - 88, 92, 92), 60 * 16, 240 * 16)

        # 倒下灰化
        if self.fx["ko"] == i:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(40, 44, 52, 150)))
            p.drawEllipse(QRectF(x - 52, FOOT_Y - 70, 104, 74))

        # 状态角标
        t = self.battle.t
        chips = [(STATUS_COLOR[sid][0], STATUS_COLOR[sid][1],
                  st["stacks"]) for sid, st in f.statuses.items()
                 if st["until"] > t and sid in STATUS_COLOR]
        cx = x - len(chips) * 17 + 17
        for name, color, stacks in chips:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(color)))
            p.drawRoundedRect(QRectF(cx - 15, FOOT_Y + 12, 30, 18), 5, 5)
            p.setPen(QPen(QColor("white")))
            p.setFont(QFont("Microsoft YaHei", 8))
            txt = name if stacks <= 1 else f"{name}{stacks}"
            p.drawText(QRectF(cx - 15, FOOT_Y + 12, 30, 18),
                       Qt.AlignmentFlag.AlignCenter, txt)
            cx += 34

        # 名字 + 三条状态条
        name_x = 40 if i == 0 else WIN_W - 40 - BAR_W
        p.setPen(QPen(QColor("#E8EDF2")))
        p.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.DemiBold))
        p.drawText(QRectF(name_x, 26, BAR_W, 20),
                   Qt.AlignmentFlag.AlignLeft if i == 0 else Qt.AlignmentFlag.AlignRight,
                   f"{f.name}  Lv.{f.level}")
        self._bar(p, name_x, BAR_HP_Y, BAR_W, 12, f.hp / f.hp_max,
                  "#E24B4A", f"{fmt_num(f.hp)}/{fmt_num(f.hp_max)}")
        self._bar(p, name_x, BAR_STA_Y, BAR_W, 8, f.sta / f.sta_max,
                  "#378ADD", None)
        self._bar(p, name_x, BAR_MOR_Y, BAR_W, 5, f.morale / 100.0,
                  "#EF9F27", None)

    def _bar(self, p: QPainter, x: float, y: float, w: float, h: float,
             ratio: float, color: str, label: str | None) -> None:
        ratio = max(0.0, min(1.0, ratio))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 110)))
        p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        if ratio > 0:
            p.setBrush(QBrush(QColor(color)))
            p.drawRoundedRect(QRectF(x + 1, y + 1, max(h - 2, (w - 2) * ratio),
                                     h - 2), (h - 2) / 2, (h - 2) / 2)
        if label:
            p.setPen(QPen(QColor("white")))
            p.setFont(QFont("Microsoft YaHei", 8))
            p.drawText(QRectF(x, y - 1, w, h + 2),
                       Qt.AlignmentFlag.AlignCenter, label)

    def _draw_floats(self, p: QPainter) -> None:
        font = QFont("Microsoft YaHei", 13, QFont.Weight.DemiBold)
        p.setFont(font)
        for text, side, dy, life, color in self.fx["floats"]:
            alpha = min(1.0, life / 0.5)
            c = QColor(color)
            c.setAlphaF(alpha)
            x = self._fighter_x(side)
            r = QRectF(x - 70, FOOT_Y - 120 - dy, 140, 26)
            p.setPen(QPen(QColor(0, 0, 0, int(140 * alpha)), 3.0))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QPen(c, 1.0))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_log(self, p: QPainter) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 90)))
        p.drawRoundedRect(QRectF(30, WIN_H - 108, WIN_W - 60, 88), 10, 10)
        p.setPen(QPen(QColor("#C9D2DC")))
        p.setFont(QFont("Microsoft YaHei", 9))
        y = WIN_H - 90
        for line in self.log:
            p.drawText(QRectF(46, y, WIN_W - 92, 20),
                       Qt.AlignmentFlag.AlignLeft, line)
            y += 21

    def _draw_vs(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(255, 255, 255, int(200 * min(1, self.intro_t)))))
        p.setFont(QFont("Microsoft YaHei", 42, QFont.Weight.DemiBold))
        p.drawText(self.rect().adjusted(0, -90, 0, -90),
                   Qt.AlignmentFlag.AlignCenter, "VS")


def e_reason(r: str) -> str:
    return {"击倒": "一方被掀翻在地（HP 归零）",
            "士气崩溃": "一方斗性崩溃，掉头败退",
            "判定获胜": "战至超时，按剩余血量判定",
            "势均力敌": "战至超时，不分胜负"}.get(r, r)
