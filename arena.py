# -*- coding: utf-8 -*-
"""竞技场：俯视斗蛐蛐罐（表现层）。

battle.py 负责算，本文件负责演：
  引擎每 0.1 秒吐一批事件，这里把它们播放成盘内走位、冲锋、击退、
  对峙转头、力竭后撤、掉头逃出罐外等画面。
引擎依旧不知道画面的存在 —— 同一个 seed 永远是同一场战斗。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from battle import Battle, make_fighter
from cricket import Cricket, paint_cricket_top, palette_from_hex
from stats import StatsDB, fmt_num

WIN_W, WIN_H = 760, 540
DISH_CX, DISH_CY, DISH_R = 380, 306, 196
CRICKET_SCALE = 1.35

BAR_W = 230
ROW_NAME, ROW_HP, ROW_STA, ROW_MOR = 18, 42, 64, 80

STATUS_COLOR = {
    "s001": ("力竭", "#BA7517"), "s002": ("流血", "#A32D2D"),
    "s003": ("破防", "#712B13"), "s004": ("格挡", "#0F6E56"),
    "s005": ("高涨", "#3B6D11"), "s006": ("畏缩", "#993556"),
}

FLOOR = QColor("#D9C9A2")
FLOOR_RING = QColor(0, 0, 0, 34)
RIM = QColor("#7A6A50")
RIM_DK = QColor("#57492F")


class ArenaWindow(QWidget):
    """俯视斗蛐蛐罐。"""

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
        c.act_next = 9999
        return f, c, pal

    def _restart(self) -> None:
        self.f = [self._make_side(0), self._make_side(1)]
        self.seed = random.randrange(1 << 30)
        self.battle = Battle(self.db, self.f[0][0], self.f[1][0], seed=self.seed)
        self.acc = 0.0
        self.intro_t = 1.0
        self.end_t = -1.0
        self.shake_t = 0.0
        # 走位编排状态
        self.ch = []
        for side in (0, 1):
            x = DISH_CX + (-128 if side == 0 else 128)
            y = DISH_CY + (14 if side == 0 else -14)
            self.ch.append({
                "x": x, "y": y,
                "hd": 0.0 if side == 0 else 180.0,   # 当前朝向(度)
                "thd": 0.0 if side == 0 else 180.0,  # 目标朝向
                "wt": (x, y),                        # 游走目标点
                "wt_t": 0.0,
                "mode": "wander",                    # wander/approach/retreat/circle
                "mode_t": 0.0,
                "kn": [0.0, 0.0],                    # 受击退/后撤速度
                "dash": None,                        # {'t','dur','sx','sy','tx','ty'}
            })
        self.fx = {
            "flash": [0.0, 0.0], "guard": [0.0, 0.0],
            "floats": [],          # (text, side, dy, life, color)
            "flee": None,          # (side, )
            "ko": None,
        }
        self.log = [" waiting"]
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

        self.shake_t = max(0.0, self.shake_t - dt)
        for k in (0, 1):
            self.fx["flash"][k] = max(0.0, self.fx["flash"][k] - dt)
            self.fx["guard"][k] = max(0.0, self.fx["guard"][k] - dt)
        for fl in self.fx["floats"]:
            fl[2] += 42 * dt
            fl[3] -= dt
        self.fx["floats"] = [x for x in self.fx["floats"] if x[3] > 0]

        for i in (0, 1):
            frozen = (self.fx["ko"] == i or
                      (self.fx["flee"] and self.fx["flee"][0] == i
                       and self.fx["flee"][1] >= 1))
            if not frozen:
                self.f[i][1].update(dt)
            self._choreo(i, dt)
        self._separate()

        self.update()

    def _separate(self) -> None:
        """两只蛐蛐最小身体间距，防止叠成一团；冲锋/倒下/逃跑的一方不被推开。"""
        a, b = self.ch[0], self.ch[1]
        busy = [False, False]
        if self.fx["ko"] is not None:
            busy[self.fx["ko"]] = True
        if self.fx["flee"]:
            busy[self.fx["flee"][0]] = True
        for i in (0, 1):
            if self.ch[i]["dash"] is not None:
                busy[i] = True
        if all(busy):
            return
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        d = math.hypot(dx, dy)
        min_d = 68.0
        if d >= min_d or d < 0.01:
            return
        push = (min_d - d) / 2.0
        ux, uy = dx / d, dy / d
        if not busy[0]:
            a["x"] -= ux * push * (2 if busy[1] else 1)
            a["y"] -= uy * push * (2 if busy[1] else 1)
        if not busy[1]:
            b["x"] += ux * push * (2 if busy[0] else 1)
            b["y"] += uy * push * (2 if busy[0] else 1)

    # ---------- 走位编排 ----------

    def _foe_pos(self, i: int) -> tuple[float, float]:
        o = self.ch[1 - i]
        return o["x"], o["y"]

    def _choreo(self, i: int, dt: float) -> None:
        if self.fx["ko"] == i:
            return
        ch = self.ch[i]
        fleeing = self.fx["flee"] and self.fx["flee"][0] == i
        fx_, fy_ = self._foe_pos(i)

        if ch["dash"] is not None:
            # 冲锋：先向后一蹲蓄力（预备动作），再扑出、收回
            d = ch["dash"]
            d["t"] += dt
            k = min(1.0, d["t"] / d["dur"])
            if k < 0.22:
                off = -0.12 * math.sin(k / 0.22 * math.pi)
            else:
                off = math.sin((k - 0.22) / 0.78 * math.pi)
            ch["x"] = d["sx"] + (d["tx"] - d["sx"]) * off
            ch["y"] = d["sy"] + (d["ty"] - d["sy"]) * off
            ch["thd"] = math.degrees(math.atan2(fy_ - ch["y"], fx_ - ch["x"]))
            if k >= 1.0:
                ch["dash"] = None
                # 收势回弹一小步，避免"顶死"在对手身上
                n = math.hypot(fx_ - ch["x"], fy_ - ch["y"]) or 1.0
                ch["kn"][0] = (ch["x"] - fx_) / n * 95
                ch["kn"][1] = (ch["y"] - fy_) / n * 95
        elif fleeing:
            # 掉头往罐外冲
            dx, dy = ch["x"] - DISH_CX, ch["y"] - DISH_CY
            n = math.hypot(dx, dy) or 1.0
            ch["x"] += dx / n * 300 * dt
            ch["y"] += dy / n * 300 * dt
            self.fx["flee"] = (i, min(1.0, self.fx["flee"][1] + dt * 0.8))
        else:
            # 受击退/后撤惯性
            if abs(ch["kn"][0]) > 1 or abs(ch["kn"][1]) > 1:
                ch["x"] += ch["kn"][0] * dt
                ch["y"] += ch["kn"][1] * dt
                ch["kn"][0] *= max(0.0, 1.0 - 7.0 * dt)
                ch["kn"][1] *= max(0.0, 1.0 - 7.0 * dt)

            # ---- 行为模式机：逼近 / 倒退拉开 / 绕圈试探 / 随意游走 ----
            dist = math.hypot(fx_ - ch["x"], fy_ - ch["y"]) or 1.0
            ch["mode_t"] -= dt
            if ch["mode_t"] <= 0:
                if dist < 95:
                    ch["mode"] = random.choice(
                        ("retreat", "circle", "wander", "retreat"))
                elif dist > 175:
                    ch["mode"] = "approach"
                else:
                    ch["mode"] = random.choice(
                        ("wander", "circle", "approach", "retreat", "circle"))
                ch["mode_t"] = random.uniform(0.7, 1.7)

            ux, uy = (fx_ - ch["x"]) / dist, (fy_ - ch["y"]) / dist
            mvx, mvy, sp = 0.0, 0.0, 0.0
            face_foe = True
            if ch["mode"] == "approach":
                if dist > 108:
                    mvx, mvy, sp = ux, uy, 74.0
            elif ch["mode"] == "retreat":
                # 倒退着拉开距离（身子仍对着对手，真实斗蛐蛐的退让姿态）
                if dist < 168:
                    mvx, mvy, sp = -ux, -uy, 80.0
            elif ch["mode"] == "circle":
                # 绕对手弧线游走（两只绕行方向相反，形成盘旋感）
                sgn = 1.0 if i == 0 else -1.0
                mvx, mvy = -uy * sgn, ux * sgn
                sp = 64.0
                if dist > 150:
                    mvx += ux * 0.5
                    mvy += uy * 0.5
                elif dist < 95:
                    mvx -= ux * 0.5
                    mvy -= uy * 0.5
            else:  # wander
                ch["wt_t"] -= dt
                wx, wy = ch["wt"]
                if math.hypot(wx - ch["x"], wy - ch["y"]) < 10:
                    ang = random.uniform(0, math.tau)
                    rr = random.uniform(30, 100)
                    mx, my = (ch["x"] + fx_) / 2, (ch["y"] + fy_) / 2
                    ch["wt"] = (mx + math.cos(ang) * rr, my + math.sin(ang) * rr)
                wx, wy = ch["wt"]
                dwx, dwy = wx - ch["x"], wy - ch["y"]
                dwd = math.hypot(dwx, dwy)
                if dwd > 8:
                    mvx, mvy, sp = dwx / dwd, dwy / dwd, 46.0
                    face_foe = dist < 140

            if sp > 0:
                ch["x"] += mvx * sp * dt
                ch["y"] += mvy * sp * dt
                if face_foe:
                    ch["thd"] = math.degrees(math.atan2(fy_ - ch["y"], fx_ - ch["x"]))
                else:
                    ch["thd"] = math.degrees(math.atan2(mvy, mvx))

        # 盘内约束（逃跑除外）；退无可退就立刻换行为，避免贴墙发呆
        if not fleeing:
            px, py = ch["x"], ch["y"]
            dx, dy = ch["x"] - DISH_CX, ch["y"] - DISH_CY
            d = math.hypot(dx, dy)
            lim = DISH_R - 34
            if d > lim:
                ch["x"] = DISH_CX + dx / d * lim
                ch["y"] = DISH_CY + dy / d * lim
                if ch["mode"] == "retreat" \
                        and math.hypot(ch["x"] - px, ch["y"] - py) > 1.5:
                    ch["mode"] = random.choice(("circle", "wander"))
                    ch["mode_t"] = random.uniform(0.8, 1.4)

        # 朝向平滑
        diff = (ch["thd"] - ch["hd"] + 540) % 360 - 180
        ch["hd"] += diff * min(1.0, dt * 7.0)

    # ---------- 事件播放 ----------

    def _float(self, text: str, side: int, color: str, dy: float = 0.0) -> None:
        self.fx["floats"].append([text, side, dy, 1.1, QColor(color)])

    def _play(self, e: dict) -> None:
        t = e["type"]
        names = (self.f[0][0].name, self.f[1][0].name)
        if t == "start":
            self._log(f"开战！{names[0]} VS {names[1]}")
        elif t in ("hit", "miss"):
            side = e["side"]
            sx, sy = self.ch[side]["x"], self.ch[side]["y"]
            tx, ty = self._foe_pos(side)
            dist = math.hypot(tx - sx, ty - sy)
            reach = max(30.0, min(110.0, dist - 52))
            n = dist or 1.0
            ch = self.ch[side]
            ch["dash"] = {"t": 0.0, "dur": 0.24,
                          "sx": sx, "sy": sy,
                          "tx": sx + (tx - sx) / n * reach,
                          "ty": sy + (ty - sy) / n * reach}
            ch["thd"] = math.degrees(math.atan2(ty - sy, tx - sx))
            if t == "hit":
                self.fx["flash"][1 - side] = 0.22
                if e.get("crit"):
                    self.shake_t = 0.3
                # 受击退
                kn = self.ch[1 - side]["kn"]
                kn[0] = (tx - sx) / n * 230
                kn[1] = (ty - sy) / n * 230
                self._float(f"{'暴击 ' if e.get('crit') else ''}-{e['dmg']}",
                            1 - side, "#F09595" if side == 1 else "#E24B4A", -34)
                if e.get("guarded"):
                    self.fx["guard"][1 - side] = 0.5
                    self._float("格挡!", 1 - side, "#5DCAA5", -52)
                self._log(f"{names[side]} 使出「{e['move']}」"
                          f"{'暴击' if e.get('crit') else '命中'} {e['dmg']}"
                          f"{'（被格挡）' if e.get('guarded') else ''}")
            else:
                # 被躲开：守方顺势大步跳出距离
                dch = self.ch[1 - side]
                jx, jy = dch["x"] - sx, dch["y"] - sy
                jn = math.hypot(jx, jy) or 1.0
                dch["kn"][0] = jx / jn * 300
                dch["kn"][1] = jy / jn * 300
                self._float("闪避", 1 - side, "#B4B2A9", -34)
                self._log(f"{names[side]} 的「{e['move']}」被躲开了")
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
            # 力竭后大幅后撤喘口气
            ch = self.ch[e["side"]]
            fx_, fy_ = self._foe_pos(e["side"])
            n = math.hypot(ch["x"] - fx_, ch["y"] - fy_) or 1.0
            ch["kn"][0] = (ch["x"] - fx_) / n * 170
            ch["kn"][1] = (ch["y"] - fy_) / n * 170
            ch["mode"], ch["mode_t"] = "retreat", 1.2
            self._log(f"{names[e['side']]} 耐力见底，退开喘息")
        elif t == "recover":
            self._float("回气!", e["side"], "#97C459", -46)
            self.f[e["side"]][1].hop(95)
            self._log(f"{names[e['side']]} 缓过劲来，耐力回满！")
        elif t == "end":
            self.end_t = 1.3
            w = e["winner"]
            if e["reason"] == "击倒":
                self.fx["ko"] = 1 - w
                self._log(f"{names[w]} 将对手掀翻在地，胜！")
            elif e["reason"] == "士气崩溃":
                loser = 1 - w
                self.fx["flee"] = (loser, 0.0)
                self._log(f"{names[loser]} 斗性崩溃，掉头冲出罐外！")
            else:
                self._log(f"战至超时，{e['reason']}"
                          + (f"，{names[w]}胜" if w is not None else "，平局"))

    def _log(self, text: str) -> None:
        self.log.append(text)
        self.log = self.log[-4:]

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

        xp = {0: 30 + 6 * b.level, 1: 6}.get(w, 12)
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

        p.fillRect(self.rect(), QColor("#232733"))

        if self.shake_t > 0:
            p.translate(random.uniform(-3, 3), random.uniform(-3, 3))

        self._draw_dish(p)
        for i in (0, 1):
            self._draw_cricket(p, i)
        self._draw_bars(p)
        self._draw_floats(p)
        self._draw_log(p)
        if self.intro_t > 0:
            self._draw_vs(p)
        p.end()

    def _draw_dish(self, p: QPainter) -> None:
        # 罐底投影
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 110)))
        p.drawEllipse(QRectF(DISH_CX - DISH_R - 18, DISH_CY - DISH_R - 10,
                             (DISH_R + 18) * 2, (DISH_R + 10) * 2 + 26))
        # 陶罐外沿
        p.setBrush(QBrush(RIM_DK))
        p.drawEllipse(QRectF(DISH_CX - DISH_R - 14, DISH_CY - DISH_R - 14,
                             (DISH_R + 14) * 2, (DISH_R + 14) * 2))
        p.setBrush(QBrush(RIM))
        p.drawEllipse(QRectF(DISH_CX - DISH_R - 8, DISH_CY - DISH_R - 8,
                             (DISH_R + 8) * 2, (DISH_R + 8) * 2))
        # 沿口高光
        p.setPen(QPen(QColor(255, 255, 255, 46), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(DISH_CX - DISH_R - 4, DISH_CY - DISH_R - 4,
                             (DISH_R + 4) * 2, (DISH_R + 4) * 2))
        # 盘底（沙土色，微渐变制造凹陷感）
        g = QLinearGradient(DISH_CX, DISH_CY - DISH_R,
                            DISH_CX, DISH_CY + DISH_R)
        g.setColorAt(0.0, FLOOR.lighter(108))
        g.setColorAt(1.0, FLOOR.darker(112))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QRectF(DISH_CX - DISH_R, DISH_CY - DISH_R,
                             DISH_R * 2, DISH_R * 2))
        # 盘底同心圈（斗盆的中圈标线）
        p.setPen(QPen(FLOOR_RING, 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for rr in (DISH_R - 16, int(DISH_R * 0.55)):
            p.drawEllipse(QRectF(DISH_CX - rr, DISH_CY - rr, rr * 2, rr * 2))
        p.setPen(QPen(FLOOR_RING, 1.0))
        p.drawLine(QPointF(DISH_CX - DISH_R + 16, DISH_CY),
                   QPointF(DISH_CX + DISH_R - 16, DISH_CY))

    def _draw_cricket(self, p: QPainter, i: int) -> None:
        ch = self.ch[i]
        f, c, pal = self.f[i]
        opacity = 1.0
        if self.fx["flee"] and self.fx["flee"][0] == i:
            # 冲出罐沿后逐渐淡出
            d = math.hypot(ch["x"] - DISH_CX, ch["y"] - DISH_CY)
            opacity = max(0.0, 1.0 - max(0.0, d - DISH_R + 10) / 70.0)
            if opacity <= 0.0:
                return
        angle = ch["hd"] + (26 if self.fx["ko"] == i else 0)
        paint_cricket_top(p, ch["x"], ch["y"], angle, CRICKET_SCALE,
                          c, pal, opacity)

        # 受击闪白
        if self.fx["flash"][i] > 0:
            a = int(150 * self.fx["flash"][i] / 0.22)
            p.save()
            p.translate(ch["x"], ch["y"])
            p.rotate(ch["hd"])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, a)))
            p.drawEllipse(QRectF(-48, -26, 110, 52))
            p.restore()

        # 格挡护罩
        if self.fx["guard"][i] > 0:
            a = int(160 * min(1.0, self.fx["guard"][i] / 0.5))
            p.setPen(QPen(QColor(93, 202, 165, a), 3.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(ch["x"] - 46, ch["y"] - 46, 92, 92))

        # 倒下灰化
        if self.fx["ko"] == i:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(40, 44, 52, 150)))
            p.drawEllipse(QRectF(ch["x"] - 46, ch["y"] - 26, 96, 52))

    def _bar(self, p: QPainter, x: float, y: float, w: float, h: float,
             ratio: float, color: str, label: str | None,
             align_right: bool = False) -> None:
        ratio = max(0.0, min(1.0, ratio))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 110)))
        p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        if ratio > 0:
            p.setBrush(QBrush(QColor(color)))
            fw = max(h - 2, (w - 2) * ratio)
            fx = x + 1 if not align_right else x + w - 1 - fw
            p.drawRoundedRect(QRectF(fx, y + 1, fw, h - 2),
                              (h - 2) / 2, (h - 2) / 2)
        if label:
            p.setPen(QPen(QColor("white")))
            p.setFont(QFont("Microsoft YaHei", 8))
            p.drawText(QRectF(x, y - 1, w, h + 2),
                       Qt.AlignmentFlag.AlignCenter, label)

    def _draw_bars(self, p: QPainter) -> None:
        for i in (0, 1):
            f, _c, _pal = self.f[i]
            right = i == 1
            x = 36 if not right else WIN_W - 36 - BAR_W
            p.setPen(QPen(QColor("#E8EDF2")))
            p.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.DemiBold))
            p.drawText(QRectF(x, ROW_NAME, BAR_W, 20),
                       Qt.AlignmentFlag.AlignLeft if not right
                       else Qt.AlignmentFlag.AlignRight,
                       f"{f.name}  Lv.{f.level}")
            self._bar(p, x, ROW_HP, BAR_W, 13, f.hp / f.hp_max,
                      "#E24B4A", f"{fmt_num(f.hp)}/{fmt_num(f.hp_max)}", right)
            self._bar(p, x, ROW_STA, BAR_W, 8, f.sta / f.sta_max,
                      "#378ADD", None, right)
            self._bar(p, x, ROW_MOR, BAR_W, 6, f.morale / 100.0,
                      "#EF9F27", None, right)
            # 状态角标
            t = self.battle.t
            chips = [(STATUS_COLOR[sid][0], STATUS_COLOR[sid][1], st["stacks"])
                     for sid, st in f.statuses.items()
                     if st["until"] > t and sid in STATUS_COLOR]
            cx = x if not right else x + BAR_W - len(chips) * 36
            for name, color, stacks in chips:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(color)))
                p.drawRoundedRect(QRectF(cx, ROW_MOR + 12, 34, 18), 5, 5)
                p.setPen(QPen(QColor("white")))
                p.setFont(QFont("Microsoft YaHei", 8))
                txt = name if stacks <= 1 else f"{name}x{stacks}"
                p.drawText(QRectF(cx, ROW_MOR + 12, 34, 18),
                           Qt.AlignmentFlag.AlignCenter, txt)
                cx += 36

    def _draw_floats(self, p: QPainter) -> None:
        font = QFont("Microsoft YaHei", 13, QFont.Weight.DemiBold)
        p.setFont(font)
        for text, side, dy, life, color in self.fx["floats"]:
            alpha = min(1.0, life / 0.5)
            c = QColor(color)
            c.setAlphaF(alpha)
            ch = self.ch[side]
            r = QRectF(ch["x"] - 70, ch["y"] - 78 - dy, 140, 26)
            p.setPen(QPen(QColor(0, 0, 0, int(140 * alpha)), 3.0))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QPen(c, 1.0))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_log(self, p: QPainter) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 100)))
        p.drawRoundedRect(QRectF(30, WIN_H - 84, WIN_W - 60, 70), 10, 10)
        p.setPen(QPen(QColor("#C9D2DC")))
        p.setFont(QFont("Microsoft YaHei", 9))
        y = WIN_H - 68
        for line in self.log:
            p.drawText(QRectF(46, y, WIN_W - 92, 18),
                       Qt.AlignmentFlag.AlignLeft, line)
            y += 18

    def _draw_vs(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(255, 255, 255, int(220 * min(1, self.intro_t)))))
        p.setFont(QFont("Microsoft YaHei", 46, QFont.Weight.DemiBold))
        p.drawText(self.rect().adjusted(0, -60, 0, -60),
                   Qt.AlignmentFlag.AlignCenter, "VS")


def e_reason(r: str) -> str:
    return {"击倒": "一方被掀翻在地（HP 归零）",
            "士气崩溃": "一方斗性崩溃，掉头败退",
            "判定获胜": "战至超时，按剩余血量判定",
            "势均力敌": "战至超时，不分胜负"}.get(r, r)
