# -*- coding: utf-8 -*-
"""战斗引擎：纯逻辑，不依赖 Qt。

设计原则：
  1. 固定步长推进（TICK，来自数值表「7-战斗常数」），同一 seed 必然复现同一场战斗
  2. 全部数值来自 stats.json（品种/成长/招式/克制/状态/战斗常数），代码里不写死数值
  3. 每步输出结构化事件流，表现层（arena.py）只是"播放器"
  4. 将来 Steam 联机：两端交换 seed + 双方蛐蛐数据，各自跑本引擎即可得到一致战况

胜负判定（对应真实斗蛐蛐）：
  - 击倒：一方 HP=0
  - 败退：一方士气（斗性）归零，掉头就跑
  - 判定：战斗超时按剩余血量比例判胜，接近则平局
"""

from __future__ import annotations

import random

# 引擎自有常数（不属于数值策划调参范围的东西）
HIT_BASE = 85          # 命中基数%，与招式「命中修正」相加
MORALE_CAP = 100.0     # 士气上限
GUTS_SOFT = 80.0       # 斗性减伤士气的软化常数：损失×80/(80+斗性)
STATUS_MAX_STACKS = 3  # 流血等可叠状态的最大层数（与状态表「最大层数」一致）
EXHAUST_MORALE = 6     # 力竭一次挫掉的士气（当众喘不上气很丢脸）
BIG_HIT_MORALE = 6     # 单发重伤额外挫掉的士气
BIG_HIT_RATIO = 0.12   # 单发伤害≥最大血量 12% 算重伤


class Fighter:
    """战斗中的单只蛐蛐：快照属性 + 运行时状态。"""

    def __init__(self, name: str, side: int, level: int,
                 stats: dict, species_id: str = ""):
        self.name = name
        self.side = side          # 0=左(玩家) 1=右(对手)
        self.level = level
        self.species_id = species_id

        self.hp_max = float(stats.get("hp", 100))
        self.hp = self.hp_max
        self.sta_max = float(stats.get("sta", 100))
        self.sta = self.sta_max
        self.sta_regen = float(stats.get("sta_regen", 5))
        self.atk = float(stats.get("atk", 10))
        self.arm = float(stats.get("arm", 0))
        self.spd = float(stats.get("spd", 20))
        self.crit = float(stats.get("crit", 5))
        self.pen = float(stats.get("pen", 0))
        self.guts = float(stats.get("guts", 50))
        self.morale = float(stats.get("morale", 100))

        self.cool = 0.0           # 出手冷却倒计时
        self.exhausted_until = -1.0
        self.statuses: dict[str, dict] = {}   # sid -> {'until': t, 'stacks': n}
        self._bleed_next = 0.0
        self.dealt = 0.0          # 累计输出
        self.taken = 0.0

    @property
    def alive(self) -> bool:
        return self.hp > 0 and self.morale > 0

    def has_status(self, sid: str, t: float) -> bool:
        s = self.statuses.get(sid)
        return bool(s and s["until"] > t)

    def apply_status(self, sid: str, t: float, duration: float,
                     stackable: bool = False) -> None:
        s = self.statuses.setdefault(sid, {"until": 0.0, "stacks": 0})
        if stackable:
            s["stacks"] = min(STATUS_MAX_STACKS, s["stacks"] + 1)
        else:
            s["stacks"] = 1
        s["until"] = t + duration


class Battle:
    """一场自动战斗。反复调用 step() 推进，返回本步产生的事件。"""

    def __init__(self, db, left: Fighter, right: Fighter, seed=None):
        self.db = db
        self.fighters = [left, right]
        self.rng = random.Random(seed)
        self.t = 0.0
        self.over = False
        self.winner: int | None = None    # 0/1，None=平局
        self.end_reason = ""
        self.rounds = 0                   # 出招总数（≈战斗烈度）
        self.sudden_mult = 1.0
        self._started = False

    # ---------- 对外 ----------

    def step(self) -> list[dict]:
        """推进一个 TICK，返回本步事件列表。战斗结束后返回空列表。"""
        if self.over:
            return []
        ev: list[dict] = []
        if not self._started:
            self._started = True
            ev.append({"t": self.t, "type": "start"})
            for f in self.fighters:
                f.cool = self._interval(f) * self.rng.uniform(0.4, 0.7)

        dt = float(self.db.const("TICK", 0.1))
        self.t += dt

        # 突然死亡：超时后伤害逐渐放大，避免无限拖
        sd_start = float(self.db.const("SUDDEN_DEATH", 45))
        if self.t > sd_start:
            self.sudden_mult += float(self.db.const("SUDDEN_DEATH_RATE", 0.05)) * dt

        for f in self.fighters:
            if f.hp <= 0:
                continue
            self._tick_status(f, dt, ev)
            self._tick_regen(f, dt)
            f.cool -= dt

        # 谁冷却好了谁出手；同一步内按速度决定先后
        ready = [f for f in self.fighters
                 if f.hp > 0 and f.morale > 0
                 and f.cool <= 0 and f.exhausted_until <= self.t]
        ready.sort(key=lambda f: (-f.spd, f.side))
        for f in ready:
            if self.over:
                break
            if f.hp <= 0 or f.morale <= 0 or f.cool > 0:
                continue
            self._act(f, ev)

        # 时间到 → 判定
        if not self.over and self.t >= float(self.db.const("BATTLE_TIME", 60)):
            self._judge(ev)

        for e in ev:
            e.setdefault("t", self.t)
        return ev

    # ---------- 内部 ----------

    def _interval(self, f: Fighter) -> float:
        return self.db.attack_interval(f.spd)

    def _foe(self, f: Fighter) -> Fighter:
        return self.fighters[1 - f.side]

    def _morale_loss(self, dmg: float, guts: float) -> float:
        """每点伤害造成的士气损失，斗性高的蛐蛐更扛得住心理打击。"""
        return dmg * float(self.db.const("MORALE_LOSS_PER_DMG", 0.35)) \
            * GUTS_SOFT / (GUTS_SOFT + guts)

    def _drain_morale(self, f: Fighter, amount: float, ev: list) -> None:
        """扣士气并在归零时判败退。所有掉士气的路径都走这里。"""
        if amount <= 0 or f.morale <= 0:
            return
        f.morale = max(0.0, f.morale - amount)
        if f.morale <= 0 and not self.over:
            self._finish(1 - f.side, "士气崩溃", ev)

    def _tick_status(self, f: Fighter, dt: float, ev: list) -> None:
        # 流血：每 BLEED_INTERVAL 跳一次，每层 BLEED_PER_TICK 点，无视护甲；
        # 带着伤流血也会动摇斗志
        if f.has_status("s002", self.t):
            if self.t >= f._bleed_next:
                f._bleed_next = self.t + float(self.db.const("BLEED_INTERVAL", 0.5))
                dmg = float(self.db.const("BLEED_PER_TICK", 3)) * f.statuses["s002"]["stacks"]
                self._lose_hp(f, dmg, ev, kind="bleed")
                self._drain_morale(f, self._morale_loss(dmg, f.guts), ev)
        # 状态到期清理；力竭到期时按状态表语义「恢复后耐力回满」
        for sid in [k for k, v in f.statuses.items() if v["until"] <= self.t]:
            del f.statuses[sid]
            if sid == "s001" and f.exhausted_until <= self.t:
                f.exhausted_until = -1.0
                f.sta = f.sta_max
                ev.append({"t": self.t, "type": "recover", "side": f.side})

    def _tick_regen(self, f: Fighter, dt: float) -> None:
        if f.exhausted_until > self.t:
            return          # 力竭期间不回耐力，结束时一次性回满
        f.sta = min(f.sta_max, f.sta + f.sta_regen * dt)

    def _lose_hp(self, f: Fighter, dmg: float, ev: list,
                 kind: str = "damage") -> None:
        dmg = max(0.0, dmg)
        f.hp = max(0.0, f.hp - dmg)
        f.taken += dmg
        ev.append({"t": self.t, "type": kind, "side": f.side,
                   "dmg": round(dmg, 1), "hp": round(f.hp, 1)})
        if f.hp <= 0 and not self.over:
            self._finish(1 - f.side, "击倒", ev)

    def _act(self, f: Fighter, ev: list) -> None:
        foe = self._foe(f)
        moves = [(mid, m) for mid, m in self.db.data.get("招式", {}).items()
                 if m.get("类型") in ("攻击", "防御", "辅助")
                 and float(m.get("耐力消耗", 0)) <= f.sta]
        if not moves:
            # 一个招都放不起 → 力竭
            f.exhausted_until = self.t + float(self.db.const("EXHAUST_TIME", 1.5))
            f.sta = 0.0
            f.apply_status("s001", self.t, float(self.db.const("EXHAUST_TIME", 1.5)))
            ev.append({"t": self.t, "type": "exhaust", "side": f.side})
            self._drain_morale(f, EXHAUST_MORALE, ev)
            f.cool = self._interval(f)
            return

        total = 0.0
        weights = []
        low_sta = f.sta < f.sta_max * 0.45
        for m2, mv2 in moves:
            cost = float(mv2.get("耐力消耗", 0))
            w = float(mv2.get("选择权重", 1))
            if low_sta:
                # 耐力见底时本能偏向省力的招，避免无脑大招把自己打空
                w *= max(0.2, 18.0 / (4.0 + cost))
            weights.append(w)
            total += w
        roll = self.rng.uniform(0, total)
        acc = 0.0
        mid, mv = moves[0], moves[0][1]
        for (m2, mv2), w in zip(moves, weights):
            acc += w
            if roll <= acc:
                mid, mv = m2, mv2
                break

        self.rounds += 1
        cost = float(mv.get("耐力消耗", 0))
        f.sta = max(0.0, f.sta - cost)
        if f.sta <= 0.0:
            f.exhausted_until = self.t + float(self.db.const("EXHAUST_TIME", 1.5))
            f.apply_status("s001", self.t, float(self.db.const("EXHAUST_TIME", 1.5)))
            ev.append({"t": self.t, "type": "exhaust", "side": f.side})
        f.cool = self._interval(f)

        mtype = mv.get("类型")
        if mtype == "防御":
            f.apply_status("s004", self.t, 0.8)
            ev.append({"t": self.t, "type": "guard_up", "side": f.side,
                       "move": mv.get("名称", mid), "anim": mv.get("动画", "guard")})
            return
        if mtype == "辅助":      # 鸣叫：涨己方士气、挫对方士气
            f.morale = min(MORALE_CAP, f.morale + float(self.db.const("CHIRP_SELF_MORALE", 12)))
            foe.morale = max(0.0, foe.morale - float(self.db.const("CHIRP_FOE_MORALE", 8)))
            f.apply_status("s005", self.t, 6.0)
            foe.apply_status("s006", self.t, 4.0)
            ev.append({"t": self.t, "type": "chirp", "side": f.side,
                       "move": mv.get("名称", mid), "anim": mv.get("动画", "chirp")})
            if foe.morale <= 0 and not self.over:
                self._finish(f.side, "士气崩溃", ev)
            return

        # ---- 攻击招式 ----
        hit = max(40, min(100, HIT_BASE + float(mv.get("命中修正", 0))))
        if self.rng.uniform(0, 100) > hit:
            ev.append({"t": self.t, "type": "miss", "side": f.side,
                       "move": mv.get("名称", mid), "anim": mv.get("动画", "bite")})
            return

        atk_eff = f.atk
        if f.has_status("s005", self.t):
            atk_eff *= 1.15       # 士气高涨
        if f.has_status("s006", self.t):
            atk_eff *= 0.80       # 畏缩

        crit = (self.rng.uniform(0, 100)
                < f.crit + float(mv.get("暴击修正", 0)))
        raw = atk_eff * float(mv.get("伤害系数", 1)) * self.sudden_mult
        if crit:
            raw *= float(self.db.const("CRIT_MULT", 1.5))

        arm_eff = foe.arm
        if foe.has_status("s003", self.t):
            arm_eff *= 0.70       # 破防
        dmg = float(self.db.damage_after_armor(raw, arm_eff, f.pen))

        guarded = foe.has_status("s004", self.t)
        if guarded:
            reflect = dmg * float(self.db.const("BLOCK_REFLECT", 0.3))
            dmg *= (1.0 - float(self.db.const("BLOCK_REDUCE", 0.6)))
            self._lose_hp(f, reflect, ev, kind="reflect")

        self._lose_hp(foe, dmg, ev, kind="attack")
        f.dealt += dmg

        ev.append({"t": self.t, "type": "hit", "side": f.side,
                   "move": mv.get("名称", mid), "anim": mv.get("动画", "bite"),
                   "dmg": round(dmg, 1), "crit": crit, "guarded": guarded,
                   "hp": round(foe.hp, 1), "foe_morale": round(foe.morale, 1)})

        # 士气：受伤按比例掉；被暴击、被打出重伤都额外挫志
        loss = self._morale_loss(dmg, foe.guts)
        if crit:
            loss += float(self.db.const("MORALE_CRIT_LOSS", 3))
        if dmg >= foe.hp_max * BIG_HIT_RATIO:
            loss += BIG_HIT_MORALE
        self._drain_morale(foe, loss, ev)

        # 附带状态（流血/破防等）
        sid = mv.get("附带状态")
        if sid and foe.hp > 0:
            st = self.db.status(sid) or {}
            stackable = int(st.get("最大层数", 1)) > 1
            foe.apply_status(sid, self.t, float(st.get("持续(秒)", 3)), stackable)

    def _finish(self, winner: int | None, reason: str, ev: list) -> None:
        if self.over:
            return
        self.over = True
        self.winner = winner
        self.end_reason = reason
        ev.append({"t": self.t, "type": "end", "winner": winner, "reason": reason})

    def _judge(self, ev: list) -> None:
        a, b = self.fighters
        ra, rb = a.hp / a.hp_max, b.hp / b.hp_max
        if abs(ra - rb) < 0.05:
            self._finish(None, "势均力敌", ev)
        else:
            self._finish(0 if ra > rb else 1, "判定获胜", ev)

    # ---------- 战报 ----------

    def log_lines(self) -> list[str]:
        lines = [f"{self.fighters[0].name}  VS  {self.fighters[1].name}"]
        return lines


def make_fighter(db, side: int, name: str, species_id: str, level: int,
                 talents=None) -> Fighter:
    """从数值表构建一只战斗用蛐蛐。"""
    stats, _cond = db.compute(species_id, level, talents or [])
    return Fighter(name, side, level, stats, species_id)
