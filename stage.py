# -*- coding: utf-8 -*-
"""战斗舞台：战场逻辑 + 编排 + 绘制，不依赖具体窗口。

两个宿主共用同一套舞台：
  - ArenaWindow（竞技场窗口，带陶罐/大 HUD）—— 好友对战
  - 桌宠本体窗口（桌面模式，无罐无底、蛐蛐直接在桌面打）—— 副本

引擎（battle.py）照旧不知道舞台的存在；同一种子仍复现同一场战斗。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen

from battle import Battle, make_fighter
from cricket import Cricket, paint_cricket_top, palette_from_hex
from dungeon import DungeonRun
from stats import StatsDB, fmt_num

# 桌面模式的战场几何
FIELD_W, FIELD_H = 660, 440
FIELD_CX, FIELD_CY = 330, 248
FIELD_R = 236

STATUS_COLOR = {
    "s001": ("力竭", "#BA7517"), "s002": ("流血", "#A32D2D"),
    "s003": ("破防", "#712B13"), "s004": ("格挡", "#0F6E56"),
    "s005": ("高涨", "#3B6D11"), "s006": ("畏缩", "#993556"),
}


def e_reason(r: str) -> str:
    return {"击倒": "一方被掀翻在地（HP 归零）",
            "士气崩溃": "一方斗性崩溃，掉头败退",
            "判定获胜": "战至超时，按剩余血量判定",
            "势均力敌": "战至超时，不分胜负"}.get(r, r)


class BattleStage:
    """一场可渲染的战斗。宿主每帧调用 update(dt) + draw(painter)。"""

    def __init__(self, pet, style: str = "arena",
                 diff_id: str | None = None, resume: bool = False,
                 cx: float = 0, cy: float = 0, radius: float = 0):
        self.pet = pet
        self.db = StatsDB()
        self.style = style                 # 'arena'（窗口+陶罐）| 'desktop'（桌面）
        self.cx, self.cy, self.radius = cx, cy, radius
        self.drun: DungeonRun | None = None
        self._frac = [1.0, 1.0]
        if diff_id:
            self.drun = DungeonRun(self.db, diff_id)
        elif resume:
            loaded = DungeonRun.load_run(self.db)
            if loaded:
                self.drun, hp, sta = loaded
                # 断点里的血/耐写回结转比例（否则来回切换血量总变满血）
                probe = self._make_player_fighter()
                self._frac = [
                    max(0.05, min(1.0, hp / max(1.0, probe.hp_max))),
                    max(0.05, min(1.0, sta / max(1.0, probe.sta_max)))]
        self._rest_t = 0.0
        self._rest_msg = ""
        self._enter = None
        self._pending_end = None
        self.dungeon_result = None
        self.on_diff_clear = None          # 宿主回调（弹结算）
        self.on_pvp_end = None
        self._anim_t = 0.0
        self._reset_field(intro=1.6 if self.drun is None else 0.0)
        if self.drun is not None:
            self._start_dungeon()
        else:
            self._restart()

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

    def _make_player_fighter(self):
        sp = self.db.species(self.pet.species_id) or {}
        return make_fighter(self.db, 0, f"{sp.get('名称', '蛐蛐')}·我方",
                            self.pet.species_id, self.pet.level,
                            self.pet.talents)

    def _reset_field(self, intro: float = 1.6) -> None:
        cx, cy = self.cx, self.cy
        r = self.radius
        self.seed = random.randrange(1 << 30)
        self.acc = 0.0
        self.intro_t = intro
        self.end_t = -1.0
        self.shake_t = 0.0
        self.ch = []
        self._rim = []
        self._start = []
        for side in (0, 1):
            x = cx + (-128 if side == 0 else 128)
            y = cy + (14 if side == 0 else -14)
            ang = math.radians(200 if side == 0 else -20)
            rx = cx + math.cos(ang) * (r - 20)
            ry = cy + math.sin(ang) * (r - 20)
            self._rim.append((rx, ry))
            self._start.append((x, y))
            self.ch.append({
                "x": rx, "y": ry,
                "hd": 0.0 if side == 0 else 180.0,
                "thd": 0.0 if side == 0 else 180.0,
                "wt": (x, y), "wt_t": 0.0,
                "mode": "wander", "mode_t": 0.0,
                "kn": [0.0, 0.0], "dash": None,
                "skew": 0.0, "skew_t": 0.0,
            })
        self.fx = {
            "flash": [0.0, 0.0], "guard": [0.0, 0.0],
            "floats": [], "flee": None, "ko": None,
            "ko_anim": None, "grapple": None,
        }
        self.dust = []
        self._last_hit = None
        self._pending_end = None
        self.log = [" waiting"]
        self._prev_pos = [(self.ch[0]["x"], self.ch[0]["y"]),
                          (self.ch[1]["x"], self.ch[1]["y"])]

    def _restart(self) -> None:
        """普通对战（竞技场）。"""
        self.drun = None
        self.dungeon_result = None
        self._frac = [1.0, 1.0]
        self._rest_t = 0.0
        self._enter = None
        self._reset_field(intro=1.6)
        self.f = [self._make_side(0), self._make_side(1)]
        self.battle = Battle(self.db, self.f[0][0], self.f[1][0],
                             seed=self.seed)

    # ---------- 副本 ----------

    def _start_dungeon(self) -> None:
        self._reset_field(intro=0.0)
        self.ch[0]["x"], self.ch[0]["y"] = self._start[0]
        self.ch[0]["hd"] = self.ch[0]["thd"] = 0.0
        player = self._make_player_fighter()
        player.hp = max(1.0, player.hp_max * self._frac[0])
        player.sta = max(1.0, player.sta_max * self._frac[1])
        pc = Cricket()
        pc.act_next = 9999
        self.f = [(player, pc, self.pet.palette), None]
        self.battle = None
        self._prev_pos[0] = self._start[0]
        self.log = [f"进入「{self.drun.diff_name()}」副本"]
        self._spawn_enemy()

    def _spawn_enemy(self) -> None:
        enemy = self.drun.make_enemy(self.drun.eidx)
        sp = self.db.species(enemy.species_id) or {}
        c = Cricket()
        c.act_next = 9999
        c.facing = c.facing_target = -1.0
        self.f[1] = (enemy, c, palette_from_hex(str(sp.get("主色", "#6FA83C"))))
        self.ch[1]["x"], self.ch[1]["y"] = self._rim[1]
        self.ch[1]["thd"] = self.ch[1]["hd"] = math.degrees(
            math.atan2(self._start[1][1] - self._rim[1][1],
                       self._start[1][0] - self._rim[1][0]))
        self._prev_pos[1] = (self.ch[1]["x"], self.ch[1]["y"])
        self._enter = {"side": 1, "t": 0.0, "dur": 1.0}

    def _begin_battle(self) -> None:
        if self.drun is not None:
            # 玩家复活/重建：按结转比例满状态进场。
            # 之前只重置血量比例和敌人，玩家本体还是上一场 hp=0 的尸体，
            # 新战斗开局即败，永远躺地上被鞭尸。
            player = self._make_player_fighter()
            player.hp = max(1.0, player.hp_max * self._frac[0])
            player.sta = max(1.0, player.sta_max * self._frac[1])
            pc = Cricket()
            pc.act_next = 9999
            self.f[0] = (player, pc, self.pet.palette)
            self.ch[0]["x"], self.ch[0]["y"] = self._start[0]
            self.ch[0]["hd"] = self.ch[0]["thd"] = 0.0
            self._prev_pos[0] = self._start[0]
            # 清掉上一场的尸体/逃跑/角力/护罩残留
            self.fx["ko"] = None
            self.fx["ko_anim"] = None
            self.fx["flee"] = None
            self.fx["grapple"] = None
            self.fx["guard"] = [0.0, 0.0]
            self.fx["flash"] = [0.0, 0.0]
            self._last_hit = None
        self.battle = Battle(self.db, self.f[0][0], self.f[1][0],
                             seed=self.seed)
        self.acc = 0.0

    def _rest(self, seconds: float, msg: str) -> None:
        self._rest_t = seconds
        self._rest_msg = msg
        self._log(msg)

    def _dungeon_advance(self) -> None:
        e = self._pending_end or {}
        win = e.get("winner") == 0
        player = self.f[0][0]
        self._frac = [max(0.05, min(1.0, player.hp / player.hp_max)),
                      max(0.05, min(1.0, player.sta / player.sta_max))]
        res = self.drun.on_fight_end(win)
        if win:
            self._frac[0] = min(1.0, self._frac[0] + 0.50)
            self._frac[1] = min(1.0, self._frac[1] + 0.30)
            self.pet._add_xp(res.get("xp", 0))
            self._float(f"+{res.get('xp', 0)} 经验", 0, "#97C459", -30)
        else:
            self._frac = [1.0, 1.0]
            self.pet._add_xp(res.get("xp", 0))
            self._float(f"+{res.get('xp', 0)} 经验", 0, "#8B97A6", -30)
        r = res["result"]
        if r == "next":
            self._rest(1.6, "敌方增援来袭！")
        elif r == "floor_clear":
            self._frac = [1.0, 1.0]
            self._rest(2.4, f"第 {res.get('floor', '?')} 层攻克！休整完毕")
        elif r == "retry":
            self._rest(2.4, f"战败…退回第 {res.get('floor', 1)} 层，整备再战")
        elif r == "diff_clear":
            DungeonRun.clear_run()
            self.dungeon_result = res
            if self.on_diff_clear:
                self.on_diff_clear(res)
            return
        probe = self._make_player_fighter()
        self.drun.save(self._frac[0] * probe.hp_max,
                       self._frac[1] * probe.sta_max)

    def on_exit(self) -> None:
        """宿主关闭时保存断点。"""
        if self.drun is None:
            return
        if self.battle is not None and not self.battle.over:
            player = self.f[0][0]
            self.drun.save(player.hp, player.sta)
        elif self.dungeon_result is None:
            probe = self._make_player_fighter()
            self.drun.save(self._frac[0] * probe.hp_max,
                           self._frac[1] * probe.sta_max)

    # ---------- 主循环 ----------

    def update(self, dt: float = 0.03) -> None:
        self._anim_t += dt
        if self.drun is not None:
            if self._rest_t > 0:
                self._rest_t -= dt
                if self._rest_t <= 0:
                    self._spawn_enemy()
            elif self._enter is not None:
                e = self._enter
                e["t"] += dt
                k = min(1.0, e["t"] / e["dur"])
                ease = 1.0 - (1.0 - k) ** 2
                ch = self.ch[e["side"]]
                ch["x"] = self._rim[e["side"]][0] + \
                    (self._start[e["side"]][0] - self._rim[e["side"]][0]) * ease
                ch["y"] = self._rim[e["side"]][1] + \
                    (self._start[e["side"]][1] - self._rim[e["side"]][1]) * ease
                ch["thd"] = 180.0
                c2 = self.f[e["side"]][1]
                c2.move_amp = 0.7
                c2.gait_phase += dt * 11.0
                if k >= 1.0:
                    self._enter = None
                    self._begin_battle()
            elif self.battle is not None and not self.battle.over:
                self.acc += dt
                tick = float(self.db.const("TICK", 0.1))
                while self.acc >= tick and not self.battle.over:
                    self.acc -= tick
                    for e in self.battle.step():
                        self._play(e)
        elif self.intro_t > 0:
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
        elif self.battle is not None and not self.battle.over:
            self.acc += dt
            tick = float(self.db.const("TICK", 0.1))
            while self.acc >= tick and not self.battle.over:
                self.acc -= tick
                for e in self.battle.step():
                    self._play(e)

        if self.end_t > 0:
            self.end_t -= dt
            if self.end_t <= 0:
                if self.drun is not None:
                    self._dungeon_advance()
                elif self.on_pvp_end:
                    self.on_pvp_end()

        self.shake_t = max(0.0, self.shake_t - dt)
        for k in (0, 1):
            self.fx["flash"][k] = max(0.0, self.fx["flash"][k] - dt)
            self.fx["guard"][k] = max(0.0, self.fx["guard"][k] - dt)
        for fl in self.fx["floats"]:
            fl[2] += 42 * dt
            fl[3] -= dt
        self.fx["floats"] = [x for x in self.fx["floats"] if x[3] > 0]

        if self.fx["ko_anim"] is not None:
            self.fx["ko_anim"]["t"] += dt

        for dpar in self.dust:
            dpar[0] += dpar[2] * dt
            dpar[1] += dpar[3] * dt
            dpar[2] *= 1.0 - 3.5 * dt
            dpar[3] *= 1.0 - 3.5 * dt
            dpar[4] -= dt
        self.dust = [d for d in self.dust if d[4] > 0]

        g = self.fx["grapple"]
        if g is not None:
            g["t"] += dt
            for i in (0, 1):
                self.f[i][1].chirp = max(self.f[i][1].chirp, 0.2)
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
                for ch, sgn in ((a, -1.0), (b, 1.0)):
                    ch["kn"][0] = ux * 250 * sgn
                    ch["kn"][1] = uy * 250 * sgn
                self._dust((mx + ux * 30, my + uy * 30), 10, 70)

        for i in (0, 1):
            if self.fx["grapple"] is not None:
                self.f[i][1].gait_phase += dt * 16.0
                self.f[i][1].move_amp = 1.0
                continue
            fleeing_i = self.fx["flee"] and self.fx["flee"][0] == i
            frozen = (self.fx["ko"] == i
                      or (fleeing_i and self.fx["flee"][1] >= 1))
            if self.battle is not None and self.battle.over \
                    and not fleeing_i and self.fx["ko"] != i:
                frozen = True
            if not frozen:
                self.f[i][1].update(dt)

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
                n = math.hypot(fx_ - ch["x"], fy_ - ch["y"]) or 1.0
                ch["kn"][0] = (ch["x"] - fx_) / n * 95
                ch["kn"][1] = (ch["y"] - fy_) / n * 95
        elif fleeing:
            dx, dy = ch["x"] - self.cx, ch["y"] - self.cy
            n = math.hypot(dx, dy) or 1.0
            ch["x"] += dx / n * 300 * dt
            ch["y"] += dy / n * 300 * dt
            self.fx["flee"] = (i, min(1.0, self.fx["flee"][1] + dt * 0.8))
        else:
            if abs(ch["kn"][0]) > 1 or abs(ch["kn"][1]) > 1:
                ch["x"] += ch["kn"][0] * dt
                ch["y"] += ch["kn"][1] * dt
                ch["kn"][0] *= max(0.0, 1.0 - 7.0 * dt)
                ch["kn"][1] *= max(0.0, 1.0 - 7.0 * dt)

            dist = math.hypot(fx_ - ch["x"], fy_ - ch["y"]) or 1.0
            ch["mode_t"] -= dt
            if ch["mode_t"] <= 0:
                prev = ch["mode"]
                if dist < 95:
                    pool = ("retreat", "circle", "wander", "retreat")
                elif dist > 175:
                    if prev == "retreat" and dist < 220:
                        pool = ("circle", "wander")
                    else:
                        pool = ("approach",)
                else:
                    pool = ("wander", "circle", "approach", "retreat", "circle")
                    if prev == "retreat":
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
                if dist < 168:
                    mvx, mvy, sp = -ux, -uy, 80.0
            elif ch["mode"] == "circle":
                sgn = 1.0 if i == 0 else -1.0
                mvx, mvy = -uy * sgn, ux * sgn
                sp = 64.0
                if dist > 150:
                    mvx += ux * 0.5
                    mvy += uy * 0.5
                elif dist < 95:
                    mvx -= ux * 0.5
                    mvy -= uy * 0.5
            else:
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

        if not fleeing:
            px, py = ch["x"], ch["y"]
            dx, dy = ch["x"] - self.cx, ch["y"] - self.cy
            d = math.hypot(dx, dy)
            lim = self.radius - 34
            if d > lim:
                ch["x"] = self.cx + dx / d * lim
                ch["y"] = self.cy + dy / d * lim
                if ch["mode"] == "retreat" \
                        and math.hypot(ch["x"] - px, ch["y"] - py) > 1.5:
                    ch["mode"] = random.choice(("circle", "wander"))
                    ch["mode_t"] = random.uniform(0.8, 1.4)

        diff = (ch["thd"] - ch["hd"] + 540) % 360 - 180
        ch["hd"] += diff * min(1.0, dt * 7.0)

    def _separate(self) -> None:
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
        min_d = 92.0
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

    # ---------- 事件播放 ----------

    def _float(self, text: str, side: int, color: str, dy: float = 0.0) -> None:
        self.fx["floats"].append([text, side, dy, 1.1, QColor(color)])

    def _dust(self, pos: tuple, count: int, spread: float) -> None:
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

    def _log(self, text: str) -> None:
        self.log.append(text)
        self.log = self.log[-4:]

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
                reach = max(24.0, min(150.0, dist - 76))
                dur = 0.24 + min(0.28, dist * 0.0014)
                ch["dash"] = {"t": 0.0, "dur": dur,
                              "sx": sx, "sy": sy,
                              "tx": sx + (tx - sx) / n * reach,
                              "ty": sy + (ty - sy) / n * reach}
                ch["thd"] = math.degrees(math.atan2(ty - sy, tx - sx))
                ch["mode"], ch["mode_t"] = "wander", 0.5
                self.f[side][1].chirp = max(self.f[side][1].chirp, 0.3)

            if t == "hit":
                self.fx["flash"][1 - side] = 0.22
                self._dust((tx, ty), 6, 55)
                if e.get("counter"):
                    self.shake_t = 0.45
                    self._dust((tx, ty), 14, 90)
                    self._float("克制!", 1 - side, "#FAC775", -56)
                elif e.get("crit"):
                    self.shake_t = 0.3
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
            self._pending_end = e
            self.end_t = 1.6
            w = e["winner"]
            if e["reason"] == "击倒":
                loser = 1 - w
                self.fx["ko"] = loser
                self.fx["ko_anim"] = {"side": loser, "t": 0.0}
                self._dust((self.ch[loser]["x"], self.ch[loser]["y"]), 16, 90)
                wch = self.ch[w]
                lch = self.ch[loser]
                n = math.hypot(wch["x"] - lch["x"], wch["y"] - lch["y"]) or 1.0
                wch["kn"][0] = (wch["x"] - lch["x"]) / n * 150
                wch["kn"][1] = (wch["y"] - lch["y"]) / n * 150
                wch["mode"], wch["mode_t"] = "retreat", 2.0
                self.f[w][1].chirp = 2.2
                self._log(f"{names[w]} 将对手掀翻在地，胜！")
            elif e["reason"] == "士气崩溃":
                loser = 1 - w
                self.fx["flee"] = (loser, 0.0)
                self.f[loser][1].chirp = 0.6
                self._log(f"{names[loser]} 斗性崩溃，掉头就跑！")
            else:
                self._log(f"战至超时，{e['reason']}"
                          + (f"，{names[w]}胜" if w is not None else "，平局"))

    # ---------- 绘制 ----------

    def draw(self, p: QPainter) -> None:
        if self.style == "arena":
            self._draw_dish(p)
        else:
            self._draw_field_hint(p)
        self._draw_dust(p)
        for i in (0, 1):
            self._draw_cricket(p, i)
        if self.style == "arena":
            self._draw_bars(p)
            if self.drun is not None:
                self._draw_dungeon_hud(p)
        else:
            self._draw_floating_bars(p)
            if self.drun is not None:
                self._draw_dungeon_badge(p)
        self._draw_floats(p)
        if self.style == "arena":
            self._draw_log(p)
        if self.intro_t > 0 or (self.drun is None and self.intro_t > 0):
            self._draw_vs(p)

    def _draw_field_hint(self, p: QPainter) -> None:
        """桌面模式：只画一个极淡的虚线活动范围圈。"""
        p.setPen(QPen(QColor(255, 255, 255, 26), 1.2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(self.cx - self.radius, self.cy - self.radius,
                             self.radius * 2, self.radius * 2))

    def _draw_dish(self, p: QPainter) -> None:
        cx, cy, r = self.cx, self.cy, self.radius
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 110)))
        p.drawEllipse(QRectF(cx - r - 18, cy - r - 10,
                             (r + 18) * 2, (r + 10) * 2 + 26))
        p.setBrush(QBrush(QColor("#57492F")))
        p.drawEllipse(QRectF(cx - r - 14, cy - r - 14,
                             (r + 14) * 2, (r + 14) * 2))
        p.setBrush(QBrush(QColor("#7A6A50")))
        p.drawEllipse(QRectF(cx - r - 8, cy - r - 8,
                             (r + 8) * 2, (r + 8) * 2))
        p.setPen(QPen(QColor(255, 255, 255, 46), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - r - 4, cy - r - 4,
                             (r + 4) * 2, (r + 4) * 2))
        floor = QColor("#D9C9A2")
        g = QLinearGradient(cx, cy - r, cx, cy + r)
        g.setColorAt(0.0, floor.lighter(108))
        g.setColorAt(1.0, floor.darker(112))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.setPen(QPen(QColor(0, 0, 0, 34), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for rr in (r - 16, int(r * 0.55)):
            p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))
        p.setPen(QPen(QColor(0, 0, 0, 34), 1.0))
        p.drawLine(QPointF(cx - r + 16, cy), QPointF(cx + r - 16, cy))

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
            d = math.hypot(ch["x"] - self.cx, ch["y"] - self.cy)
            opacity = max(0.0, 1.0 - max(0.0, d - self.radius + 10) / 70.0)
            if opacity <= 0.0:
                return
        if (self.fx["ko"] == i and self.fx["ko_anim"] is not None
                and self.fx["ko_anim"]["side"] == i):
            k = min(1.0, self.fx["ko_anim"]["t"] / 0.6)
            spin = 540.0 * k
            flip = math.cos(k * math.pi)
            if flip < 0:
                pal = {"hi": pal["belly"], "body": pal["belly"],
                       "dk": pal["dk"], "belly": pal["hi"]}
        fx_, fy_ = self._foe_pos(i)
        dist = math.hypot(fx_ - ch["x"], fy_ - ch["y"])
        ant_lift = max(0.0, min(1.0, 1.0 - (dist - 95.0) / 90.0))
        angle = ch["hd"] + spin + (26 if self.fx["ko"] == i else 0)
        paint_cricket_top(p, ch["x"], ch["y"], angle, 1.35,
                          c, pal, opacity, ant_lift, flip)

        if self.fx["flash"][i] > 0:
            a = int(150 * self.fx["flash"][i] / 0.22)
            p.save()
            p.translate(ch["x"], ch["y"])
            p.rotate(ch["hd"])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, a)))
            p.drawEllipse(QRectF(-48, -26, 110, 52))
            p.restore()

        if self.fx["guard"][i] > 0:
            k = min(1.0, self.fx["guard"][i] / 0.5)
            a = int(170 * k)
            pulse = 1.0 + 0.07 * math.sin(self._anim_t * 13.0)
            r = 46.0 * pulse
            p.setPen(QPen(QColor(93, 202, 165, a), 3.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(ch["x"] - r, ch["y"] - r, r * 2, r * 2))
            if self.style == "desktop":
                p.setPen(QPen(QColor(93, 202, 165, min(255, a + 70))))
                p.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.DemiBold))
                p.drawText(QRectF(ch["x"] - 52, ch["y"] - r - 20, 104, 16),
                           Qt.AlignmentFlag.AlignCenter, "格挡中")

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
        BAR_W = 230
        for i in (0, 1):
            f, _c, _pal = self.f[i]
            right = i == 1
            x = 36 if not right else WIN_ARENA_W - 36 - BAR_W
            p.setPen(QPen(QColor("#E8EDF2")))
            p.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.DemiBold))
            p.drawText(QRectF(x, 18, BAR_W, 20),
                       Qt.AlignmentFlag.AlignLeft if not right
                       else Qt.AlignmentFlag.AlignRight,
                       f"{f.name}  Lv.{f.level}")
            self._bar(p, x, 42, BAR_W, 13, f.hp / f.hp_max,
                      "#E24B4A", f"{fmt_num(f.hp)}/{fmt_num(f.hp_max)}", right)
            self._bar(p, x, 64, BAR_W, 8, f.sta / f.sta_max,
                      "#378ADD", None, right)
            self._bar(p, x, 80, BAR_W, 6, f.morale / 100.0,
                      "#EF9F27", None, right)
            t = self.battle.t if self.battle is not None else 0.0
            chips = [(STATUS_COLOR[sid][0], STATUS_COLOR[sid][1],
                      st["stacks"]) for sid, st in f.statuses.items()
                     if st["until"] > t and sid in STATUS_COLOR]
            cx = x if not right else x + BAR_W - len(chips) * 36
            for name, color, stacks in chips:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(color)))
                p.drawRoundedRect(QRectF(cx, 92, 34, 18), 5, 5)
                p.setPen(QPen(QColor("white")))
                p.setFont(QFont("Microsoft YaHei", 8))
                txt = name if stacks <= 1 else f"{name}x{stacks}"
                p.drawText(QRectF(cx, 92, 34, 18),
                           Qt.AlignmentFlag.AlignCenter, txt)
                cx += 36

    def _draw_floating_bars(self, p: QPainter) -> None:
        """桌面模式：血条悬浮在每只蛐蛐头顶。"""
        for i in (0, 1):
            f, _c, _pal = self.f[i]
            ch = self.ch[i]
            bw = 130
            x = ch["x"] - bw / 2
            y = ch["y"] - 96
            p.setPen(QPen(QColor("#E8EDF2")))
            p.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.DemiBold))
            p.drawText(QRectF(x, y - 15, bw, 14),
                       Qt.AlignmentFlag.AlignCenter,
                       f"{f.name} Lv.{f.level}")
            self._bar(p, x, y, bw, 8, f.hp / f.hp_max, "#E24B4A",
                      f"{fmt_num(f.hp)}/{fmt_num(f.hp_max)}")
            self._bar(p, x, y + 10, bw, 4, f.sta / f.sta_max,
                      "#378ADD", None)
            t = self.battle.t if self.battle is not None else 0.0
            n_active = sum(1 for sid, st in f.statuses.items()
                           if st["until"] > t and sid in STATUS_COLOR)
            if n_active:
                p.setPen(QPen(QColor("#FAC775")))
                p.setFont(QFont("Microsoft YaHei", 7))
                names = "·".join(STATUS_COLOR[sid][0]
                                 for sid, st in f.statuses.items()
                                 if st["until"] > t and sid in STATUS_COLOR)
                p.drawText(QRectF(x, y + 16, bw, 12),
                           Qt.AlignmentFlag.AlignCenter, names)

    def _draw_dungeon_hud(self, p: QPainter) -> None:
        n = self.drun.n_enemies
        eidx = min(self.drun.eidx + 1, n)
        prog = ((self.drun.floor - 1) * n + self.drun.eidx) / (20.0 * n)
        cx = WIN_ARENA_W / 2
        p.setPen(QPen(QColor("#E8EDF2")))
        p.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - 160, 14, 320, 20),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{self.drun.diff_name()}  ·  第 {self.drun.floor}/20 层"
                   f"  ·  敌人 {eidx}/{n}")
        bw = 260
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 110)))
        p.drawRoundedRect(QRectF(cx - bw / 2, 38, bw, 9), 4.5, 4.5)
        p.setBrush(QBrush(QColor("#FAC775")))
        p.drawRoundedRect(QRectF(cx - bw / 2 + 1, 39,
                                 max(7.0, (bw - 2) * max(0.0, min(1.0, prog))),
                                 7), 3.5, 3.5)
        if self._rest_t > 0:
            p.setPen(QPen(QColor("#FAC775")))
            p.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.DemiBold))
            p.drawText(QRectF(cx - 160, self.cy - 140, 320, 24),
                       Qt.AlignmentFlag.AlignCenter, self._rest_msg)

    def _draw_dungeon_badge(self, p: QPainter) -> None:
        """桌面模式：蛐蛐头顶的副本进度小徽章。"""
        n = self.drun.n_enemies
        eidx = min(self.drun.eidx + 1, n)
        prog = ((self.drun.floor - 1) * n + self.drun.eidx) / (20.0 * n)
        bw = 190
        cx = FIELD_CX
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 130)))
        p.drawRoundedRect(QRectF(cx - bw / 2, 8, bw, 34), 9, 9)
        p.setPen(QPen(QColor("#E8EDF2")))
        p.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - bw / 2, 11, bw, 16),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{self.drun.diff_name()}  第 {self.drun.floor}/20 层 · 敌 {eidx}/{n}")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 40)))
        p.drawRoundedRect(QRectF(cx - bw / 2 + 8, 30, bw - 16, 6), 3, 3)
        p.setBrush(QBrush(QColor("#FAC775")))
        p.drawRoundedRect(QRectF(cx - bw / 2 + 8, 30,
                                 max(6.0, (bw - 16) * max(0.0, min(1.0, prog))),
                                 6), 3, 3)
        if self._rest_t > 0:
            p.setPen(QPen(QColor("#FAC775")))
            p.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.DemiBold))
            p.drawText(QRectF(cx - 140, FIELD_CY - self.radius - 34, 280, 22),
                       Qt.AlignmentFlag.AlignCenter, self._rest_msg)

    def _draw_floats(self, p: QPainter) -> None:
        font = QFont("Microsoft YaHei", 12, QFont.Weight.DemiBold)
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
        p.drawRoundedRect(QRectF(30, WIN_ARENA_H - 84, WIN_ARENA_W - 60, 70),
                          10, 10)
        p.setPen(QPen(QColor("#C9D2DC")))
        p.setFont(QFont("Microsoft YaHei", 9))
        y = WIN_ARENA_H - 68
        for line in self.log:
            p.drawText(QRectF(46, y, WIN_ARENA_W - 92, 18),
                       Qt.AlignmentFlag.AlignLeft, line)
            y += 18

    def _draw_vs(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(255, 255, 255, int(220 * min(1, self.intro_t)))))
        p.setFont(QFont("Microsoft YaHei", 46, QFont.Weight.DemiBold))
        p.drawText(QRectF(self.cx - 200, self.cy - 150, 400, 300),
                   Qt.AlignmentFlag.AlignCenter, "VS")


# 竞技场窗口尺寸（arena 宿主用）
WIN_ARENA_W, WIN_ARENA_H = 760, 540
