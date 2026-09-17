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
        self.intro_t = 1.6        # 入场仪式：从罐沿走到开战位
        INTRO_DUR = 1.6
        self.end_t = -1.0
        self.shake_t = 0.0
        # 走位编排状态
        self.ch = []
        self._rim = []
        self._start = []
        for side in (0, 1):
            x = DISH_CX + (-128 if side == 0 else 128)
            y = DISH_CY + (14 if side == 0 else -14)
            # 入场起点在罐沿（两侧对称的斜对角）
            ang = math.radians(200 if side == 0 else -20)
            rx = DISH_CX + math.cos(ang) * (DISH_R - 20)
            ry = DISH_CY + math.sin(ang) * (DISH_R - 20)
            self._rim.append((rx, ry))
            self._start.append((x, y))
            self.ch.append({
                "x": rx, "y": ry,
                "hd": 0.0 if side == 0 else 180.0,   # 当前朝向(度)
                "thd": 0.0 if side == 0 else 180.0,  # 目标朝向
                "wt": (x, y),                        # 游走目标点
                "wt_t": 0.0,
                "mode": "wander",                    # wander/approach/retreat/circle
                "mode_t": 0.0,
                "kn": [0.0, 0.0],                    # 受击退/后撤速度
                "dash": None,                        # {'t','dur','sx','sy','tx','ty'}
                "skew": 0.0,                         # 对峙朝向侧偏（防头对头摆拍）
                "skew_t": 0.0,
            })
        self.fx = {
            "flash": [0.0, 0.0], "guard": [0.0, 0.0],
            "floats": [],          # (text, side, dy, life, color)
            "flee": None,          # (side, )
            "ko": None,
            "ko_anim": None,       # {'side','t'} 掀翻动画
            "grapple": None,       # {'t','dur','mid','ux','uy','ph'} 角力僵持
        }
        self.dust = []             # 尘土粒子 [x, y, vx, vy, life, max]
        self._last_hit = None      # (anim_t, side) 用于角力判定
        self.log = [" waiting"]
        self._prev_pos = [(self.ch[0]["x"], self.ch[0]["y"]),
                          (self.ch[1]["x"], self.ch[1]["y"])]
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
        self._anim_t = getattr(self, "_anim_t", 0.0) + dt
        if self.intro_t > 0:
            # 入场仪式：从罐沿走到开战位（缓入缓出）
            INTRO_DUR = 1.6
            self.intro_t -= dt
            prog = max(0.0, min(1.0, 1.0 - self.intro_t / INTRO_DUR))
            ease = 1.0 - (1.0 - prog) ** 2
            for i in (0, 1):
                ch = self.ch[i]
                rx, ry = self._rim[i]
                sx, sy = self._start[i]
                ch["x"] = rx + (sx - rx) * ease
                ch["y"] = ry + (sy - ry) * ease
                ch["thd"] = math.degrees(math.atan2(sy - ry, sx - rx))
                c2 = self.f[i][1]
                c2.move_amp = 0.65
                c2.gait_phase += dt * 11.0
        elif not self.battle.over:
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

        # 掀翻动画推进
        if self.fx["ko_anim"] is not None:
            self.fx["ko_anim"]["t"] += dt

        # 尘土粒子
        for dpar in self.dust:
            dpar[0] += dpar[2] * dt
            dpar[1] += dpar[3] * dt
            dpar[2] *= 1.0 - 3.5 * dt
            dpar[3] *= 1.0 - 3.5 * dt
            dpar[4] -= dt
        self.dust = [d for d in self.dust if d[4] > 0]

        # 角力僵持：锁住中线对推，期间普通走位与冲刺全部冻结
        g = self.fx["grapple"]
        if g is not None:
            g["t"] += dt
            k = min(1.0, g["t"] / g["dur"])
            shove = math.sin(g["t"] * 17.0) * 13.0 * (1.0 - k * 0.4)
            mx, my = g["mid"]
            ux, uy = g["ux"], g["uy"]
            a, b = self.ch[0], self.ch[1]
            a["x"] = mx - ux * 40 - ux * shove
            a["y"] = my - uy * 40 - uy * shove
            b["x"] = mx + ux * 40 + ux * shove
            b["y"] = my + uy * 40 + uy * shove
            a["thd"] = b["thd"] = math.degrees(math.atan2(uy, ux))
            if k >= 1.0:
                self.fx["grapple"] = None
                # 角力结束：不分胜负，各自弹开
                for ch, sgn in ((a, -1.0), (b, 1.0)):
                    ch["kn"][0] = ux * 250 * sgn
                    ch["kn"][1] = uy * 250 * sgn
                self._dust((mx + ux * 30, my + uy * 30), 10, 70)

        for i in (0, 1):
            if self.fx["grapple"] is not None:
                self.f[i][1].gait_phase += dt * 16.0   # 角力时腿在乱蹬
                self.f[i][1].move_amp = 1.0
                continue
            fleeing_i = self.fx["flee"] and self.fx["flee"][0] == i
            frozen = (self.fx["ko"] == i
                      or (fleeing_i and self.fx["flee"][1] >= 1))
            # 战斗已分胜负：胜者原地立定（不再踩着尸体走位），由 end 分支安排庆祝
            if self.battle.over and not fleeing_i and self.fx["ko"] != i:
                frozen = True
            if not frozen:
                self.f[i][1].update(dt)

            # 步态驱动：按本帧实际位移算移动强度，冲刺时步频拉满
            ch = self.ch[i]
            c2 = self.f[i][1]
            if self.fx["ko"] != i:
                px, py = self._prev_pos[i]
                moved = math.hypot(ch["x"] - px, ch["y"] - py)
                self._prev_pos[i] = (ch["x"], ch["y"])
                target = max(0.0, min(1.0, moved / dt / 130.0))
                if ch["dash"] is not None:
                    target = 1.0
                c2.move_amp += (target - c2.move_amp) * min(1.0, dt * 9.0)
                c2.gait_phase += dt * (4.0 + 14.0 * c2.move_amp)
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
        min_d = 92.0   # 身体+触须的安全距离，防穿模绞绕
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
                prev = ch["mode"]
                if dist < 95:
                    pool = ("retreat", "circle", "wander", "retreat")
                elif dist > 175:
                    # 刚退完不马上贴回去，除非真离得很远
                    if prev == "retreat" and dist < 220:
                        pool = ("circle", "wander")
                    else:
                        pool = ("approach",)
                else:
                    pool = ("wander", "circle", "approach", "retreat", "circle")
                    if prev == "retreat":
                        # 退完先缓和一轮，杜绝"退了又立刻冲回"的乒乓感
                        pool = ("wander", "circle", "wander", "circle")
                ch["mode"] = random.choice(pool)
                ch["mode_t"] = (random.uniform(1.0, 2.0)
                                if ch["mode"] == "retreat"
                                else random.uniform(0.7, 1.7))

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
                    # 对峙侧偏 + 小幅虚晃：真实斗蟋蟀不会摆出完美头对头
                    ch["skew_t"] -= dt
                    if ch["skew_t"] <= 0:
                        ch["skew"] = random.uniform(-1.0, 1.0)
                        ch["skew_t"] = random.uniform(1.5, 3.5)
                    wob = (math.sin(self._anim_t * 1.7 + i * 2.1) * 6.0
                           if dist < 150 else 0.0)
                    base = math.atan2(fy_ - ch["y"], fx_ - ch["x"])
                    ch["thd"] = math.degrees(
                        base + math.radians(ch["skew"] * 20.0 + wob))
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

    def _dust(self, pos: tuple, count: int, spread: float) -> None:
        """扬起一撮沙尘（冲锋/受击/角力/倒地的地表反馈）。"""
        if len(self.dust) > 90:
            return
        for _ in range(count):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(0.2, 1.0) * spread
            self.dust.append([
                pos[0] + random.uniform(-8, 8),
                pos[1] + random.uniform(-5, 5),
                math.cos(ang) * sp, math.sin(ang) * sp * 0.6,
                random.uniform(0.35, 0.7), 0.7])

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
            n = dist or 1.0
            ch = self.ch[side]
            in_grapple = self.fx["grapple"] is not None

            if t == "hit":
                # ---- 角力判定：双方短间隔互中 → 锁颚角力 ----
                if (not in_grapple and self._last_hit is not None
                        and self._last_hit[1] != side
                        and self._anim_t - self._last_hit[0] < 0.55
                        and dist < 130
                        and self.fx["ko"] is None and self.fx["flee"] is None):
                    mx, my = (sx + tx) / 2, (sy + ty) / 2
                    self.fx["grapple"] = {
                        "t": 0.0, "dur": 0.85, "mid": (mx, my),
                        "ux": (tx - sx) / n, "uy": (ty - sy) / n}
                    for cch in (self.ch[0], self.ch[1]):
                        cch["dash"] = None
                        cch["kn"] = [0.0, 0.0]
                    self._dust((mx, my), 12, 80)
                    self.shake_t = 0.25
                    self._log("两虫锁颚角力，互不相让！")
                self._last_hit = (self._anim_t, side)

            if not in_grapple and self.fx["grapple"] is None:
                # 距离越远，扑击行程越长、耗时越久——远距离出招读作"反身扑击"，
                # 而不是原地被拽到对手脸上。终点停在颚对颚（约 76px），身体不叠
                reach = max(24.0, min(150.0, dist - 76))
                dur = 0.24 + min(0.28, dist * 0.0014)
                ch["dash"] = {"t": 0.0, "dur": dur,
                              "sx": sx, "sy": sy,
                              "tx": sx + (tx - sx) / n * reach,
                              "ty": sy + (ty - sy) / n * reach}
                ch["thd"] = math.degrees(math.atan2(ty - sy, tx - sx))
                ch["mode"], ch["mode_t"] = "wander", 0.5

            if t == "hit":
                self.fx["flash"][1 - side] = 0.22
                self._dust((tx, ty), 6, 55)
                if e.get("counter"):
                    # 克制命中：金色爆发
                    self.shake_t = 0.45
                    self._dust((tx, ty), 14, 90)
                    self._float("克制!", 1 - side, "#FAC775", -56)
                elif e.get("crit"):
                    self.shake_t = 0.3
                # 受击退（角力中被锁住不弹）
                if self.fx["grapple"] is None:
                    kn = self.ch[1 - side]["kn"]
                    kn[0] = (tx - sx) / n * 230
                    kn[1] = (ty - sy) / n * 230
                dmg_color = "#FAC775" if e.get("counter") else (
                    "#F09595" if side == 1 else "#E24B4A")
                self._float(f"{'暴击 ' if e.get('crit') else ''}-{e['dmg']}",
                            1 - side, dmg_color, -34)
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
                self._dust((dch["x"], dch["y"]), 5, 45)
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
            self.end_t = 1.6
            w = e["winner"]
            if e["reason"] == "击倒":
                loser = 1 - w
                self.fx["ko"] = loser
                self.fx["ko_anim"] = {"side": loser, "t": 0.0}
                self._dust((self.ch[loser]["x"], self.ch[loser]["y"]), 16, 90)
                # 胜者不踩尸体：退开半步、转身高歌庆祝
                wch = self.ch[w]
                lch = self.ch[1 - w]
                n = math.hypot(wch["x"] - lch["x"], wch["y"] - lch["y"]) or 1.0
                wch["kn"][0] = (wch["x"] - lch["x"]) / n * 150
                wch["kn"][1] = (wch["y"] - lch["y"]) / n * 150
                wch["mode"], wch["mode_t"] = "retreat", 2.0
                self.f[w][1].chirp = 2.2
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
        self._draw_dust(p)
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

    def _draw_dust(self, p: QPainter) -> None:
        """沙尘粒子：扑击/受击/角力/掀翻时扬起。"""
        for x, y, _vx, _vy, life, mx in self.dust:
            a = int(150 * (life / mx))
            r = 2.5 + 2.5 * (1.0 - life / mx)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(214, 199, 160, a)))
            p.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))

    def _draw_cricket(self, p: QPainter, i: int) -> None:
        ch = self.ch[i]
        f, c, pal = self.f[i]
        opacity = 1.0
        flip = 1.0
        spin = 0.0
        if self.fx["flee"] and self.fx["flee"][0] == i:
            # 冲出罐沿后逐渐淡出
            d = math.hypot(ch["x"] - DISH_CX, ch["y"] - DISH_CY)
            opacity = max(0.0, 1.0 - max(0.0, d - DISH_R + 10) / 70.0)
            if opacity <= 0.0:
                return
        # KO 掀翻动画：自转 540° + 翻面（肚皮朝上，用腹色）
        if (self.fx["ko"] == i and self.fx["ko_anim"] is not None
                and self.fx["ko_anim"]["side"] == i):
            k = min(1.0, self.fx["ko_anim"]["t"] / 0.6)
            spin = 540.0 * k
            flip = math.cos(k * math.pi)          # 1 → -1
            if flip < 0:
                pal = {"hi": pal["belly"], "body": pal["belly"],
                       "dk": pal["dk"], "belly": pal["hi"]}
        # 近身收须：两只贴近时触须上扬收短，防绞成麻花
        fx_, fy_ = self._foe_pos(i)
        dist = math.hypot(fx_ - ch["x"], fy_ - ch["y"])
        ant_lift = max(0.0, min(1.0, 1.0 - (dist - 95.0) / 90.0))
        angle = ch["hd"] + spin + (26 if self.fx["ko"] == i else 0)
        paint_cricket_top(p, ch["x"], ch["y"], angle, CRICKET_SCALE,
                          c, pal, opacity, ant_lift, flip)

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
