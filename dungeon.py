# -*- coding: utf-8 -*-
"""桌面副本：连战调度器（纯逻辑，不依赖 Qt）。

一个 DungeonRun 管理一次副本挑战的全流程：
  难度 / 层 / 层内敌人序号 → 生成敌人（品种池 + 线性等级 + 难度倍率）
  → 结算（经验 / 升层 / 退层重试 / 通关）

规则（已与策划确认）：
  · 同难度内 20 层线性变强；第 20 层为首领层（额外 1.35 倍）
  · 击败当前敌人 → 下一敌；清层 → 自动下一层
  · 失败 → 返回上一层重来（第 1 层失败则本层重来），玩家满血
  · 血量/耐力跨场保留由表现层负责（dungeon 只提供规则数值）
  · 全部数值来自「9-副本难度」表
"""

from __future__ import annotations

import json
import os
import random
from persistence import write_json

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE_PATH = os.path.join(HERE, "data", "dungeon.json")

BOSS_FLOOR = 20
BOSS_MULT = 1.35      # 首领层额外强度
FLOOR_XP_STEP = 0.05  # 每层单杀经验递增 5%
WIN_HP_HEAL = 0.50    # 每场胜利回复最大血量比例（层内连打有损耗，但不至于低血死循环）
WIN_STA_HEAL = 0.30   # 每场胜利回复最大耐力比例
LOSS_XP_RATE = 0.60   # 战败参与奖经验比例（卡关挂机刷级的成长来源）


class DungeonRun:
    """一次副本挑战。生成敌人 / 结算进度 / 存读档。"""

    def __init__(self, db, diff_id: str, seed: int | None = None):
        self.db = db
        self.diff_id = diff_id
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.floor = 1
        self.eidx = 0
        self.kills = 0
        self.total_xp = 0
        self._floor_enemies: list[dict] = []
        self._gen_floor()

    # ---------- 配置 ----------

    def conf(self) -> dict:
        return self.db.data["副本难度"][self.diff_id]

    @property
    def n_enemies(self) -> int:
        return int(self.conf().get("每层敌人数", 3))

    @property
    def floors(self) -> int:
        return BOSS_FLOOR

    def diff_name(self) -> str:
        return str(self.conf().get("名称", self.diff_id))

    def unlocked(self) -> bool:
        """本难度是否已解锁（前置难度在存档 cleared 里）。"""
        pre = str(self.conf().get("解锁前置", "") or "")
        if not pre:
            return True
        cleared = self.load_cleared()
        return pre in cleared

    # ---------- 敌人生成 ----------

    def _enemy_level(self, slot: int) -> int:
        """20 层 × 每层 N 敌全程线性插值 lo→hi。"""
        lo = float(self.conf().get("等级下限", 1))
        hi = float(self.conf().get("等级上限", 10))
        idx = (self.floor - 1) * self.n_enemies + slot
        total = max(1, self.floors * self.n_enemies - 1)
        return int(round(lo + (hi - lo) * idx / total))

    def _pick_species(self, slot: int) -> str:
        pool = str(self.conf().get("品种池", "") or "全部")
        ids = self.db.species_ids()
        if pool.strip() and pool.strip() != "全部":
            cand = [s.strip() for s in pool.split(",") if s.strip() in ids]
            if cand:
                ids = cand
        return self.rng.choice(ids)

    def _gen_floor(self) -> None:
        """生成本层敌人名单（不带战斗状态，进场时再实例化）。"""
        self._floor_enemies = []
        for slot in range(self.n_enemies):
            self._floor_enemies.append({
                "species_id": self._pick_species(slot),
                "level": self._enemy_level(slot),
            })

    def make_enemy(self, slot: int):
        """把名单里的敌人实例化成战斗用 Fighter。"""
        from battle import Fighter
        info = self._floor_enemies[slot]
        sp = self.db.species(info["species_id"]) or {}
        stats, _ = self.db.compute(info["species_id"], info["level"])
        mult_map = {"hp": "HP倍率", "atk": "攻击倍率", "arm": "护甲倍率",
                    "spd": "速度倍率", "sta": "耐力倍率"}
        for key, col in mult_map.items():
            mult = float(self.conf().get(col, 1.0) or 1.0)
            stats[key] = float(stats.get(key, 0)) * mult
        if self.floor == BOSS_FLOOR:
            stats["hp"] *= BOSS_MULT
            stats["atk"] *= BOSS_MULT
        return Fighter(f"{self.diff_name()}·{sp.get('名称', '?')}", 1,
                       info["level"], stats, info["species_id"])

    # ---------- 结算 ----------

    def on_fight_end(self, win: bool) -> dict:
        """一场战斗结束。返回 {'result', 'xp', ...}；xp 由表现层加给玩家。"""
        if win:
            base = float(self.conf().get("单杀经验", 10))
            xp = round(base * (1.0 + FLOOR_XP_STEP * (self.floor - 1)))
            self.kills += 1
            self.total_xp += xp
            if self.eidx + 1 < self.n_enemies:
                self.eidx += 1
                return {"result": "next", "xp": xp}
            fb = int(self.conf().get("层通关经验", 0))
            xp += fb
            self.total_xp += fb
            if self.floor < self.floors:
                self.floor += 1
                self.eidx = 0
                self._gen_floor()
                return {"result": "floor_clear", "xp": xp, "bonus": fb,
                        "cleared_floor": self.floor - 1, "floor": self.floor}
            return {"result": "diff_clear", "xp": xp, "bonus": fb,
                    "first_clear": self.mark_cleared()}
        # 失败：退上一层重来（第 1 层失败本层重来）。
        # 参与也有经验（60%）——卡关挂机刷级、变强后过关的生态核心
        base = float(self.conf().get("单杀经验", 10))
        xp = round(base * LOSS_XP_RATE * (1.0 + FLOOR_XP_STEP * (self.floor - 1)))
        self.total_xp += xp
        prev = self.floor
        if self.floor > 1:
            self.floor -= 1
        self.eidx = 0
        self._gen_floor()
        return {"result": "retry", "from_floor": prev, "floor": self.floor,
                "xp": xp}

    def cleared_before(self) -> bool:
        """进本难度前是否已通关过（用于判断本次是否算首通）。"""
        return self.diff_id in self.load_cleared()

    def mark_cleared(self) -> bool:
        """标记通关。返回 True 表示这是首次通关。"""
        cleared = self.load_cleared()
        if self.diff_id in cleared:
            return False
        cleared.append(self.diff_id)
        self._save_cleared(cleared)
        return True

    # ---------- 存读档 ----------

    @staticmethod
    def _save_cleared(cleared: list) -> None:
        data = DungeonRun._read_save()
        data["cleared"] = cleared
        DungeonRun._write_save(data)

    @staticmethod
    def load_cleared() -> list:
        return DungeonRun._read_save().get("cleared", [])

    @staticmethod
    def _read_save() -> dict:
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _write_save(data: dict) -> None:
        write_json(SAVE_PATH, data)

    def save(self, player_hp: float, player_sta: float) -> None:
        """保存断点：难度/层/敌序/玩家血耐。"""
        data = self._read_save()
        data["run"] = {
            "diff_id": self.diff_id, "floor": self.floor, "eidx": self.eidx,
            "seed": self.seed, "kills": self.kills, "total_xp": self.total_xp,
            "player_hp": player_hp, "player_sta": player_sta,
            "enemies": self._floor_enemies, "rng_state": self.rng.getstate(),
        }
        self._write_save(data)

    @classmethod
    def load_run(cls, db):
        """恢复断点，返回 (DungeonRun, player_hp, player_sta) 或 None。"""
        data = cls._read_save()
        run = data.get("run")
        if not run:
            return None
        try:
            dr = cls(db, run["diff_id"], seed=run.get("seed"))
            dr.floor = int(run["floor"])
            dr.eidx = int(run["eidx"])
            dr.kills = int(run.get("kills", 0))
            dr.total_xp = int(run.get("total_xp", 0))
            if not 1 <= dr.floor <= dr.floors or not 0 <= dr.eidx < dr.n_enemies:
                return None
            if 'enemies' in run and 'rng_state' in run:
                enemies = run['enemies']
                if (len(enemies) != dr.n_enemies or any(
                        not db.species(it['species_id']) or int(it['level']) < 1 for it in enemies)):
                    return None
                dr._floor_enemies = enemies
                def as_tuple(value):
                    return tuple(as_tuple(v) for v in value) if isinstance(value, list) else value
                dr.rng.setstate(as_tuple(run['rng_state']))
            else:
                dr._gen_floor()  # 旧版存档不包含名单，保持兼容。
            return dr, float(run.get("player_hp", 0)), float(run.get("player_sta", 0))
        except Exception:
            return None

    @staticmethod
    def reset_progress() -> None:
        """重置角色时同时清空断点、通关记录及由此派生的解锁。"""
        DungeonRun._write_save({})

    @staticmethod
    def clear_run() -> None:
        data = DungeonRun._read_save()
        data.pop("run", None)
        DungeonRun._write_save(data)
