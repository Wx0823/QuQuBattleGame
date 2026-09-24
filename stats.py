# -*- coding: utf-8 -*-
"""数值表数据层。

读取 数值表/QuQu数值表.xlsx 导出的 data/stats.json，对外提供：
  - const / species / growth / move / counter / status / talent 查询
  - compute_stats() 按「品种 + 等级 + 天赋」算出蛐蛐最终属性

策划改 Excel → 重启桌宠 → 自动重新导出并生效。
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(HERE, "数值表", "QuQu数值表.xlsx")
JSON_PATH = os.path.join(HERE, "data", "stats.json")

# 属性 ID -> 品种表列名
SPECIES_COL = {
    "hp": "HP", "atk": "ATK", "arm": "ARM", "spd": "SPD", "sta": "STA",
    "sta_regen": "耐力回复", "crit": "暴击", "guts": "斗性", "weight": "体重",
}
# 属性 ID -> 成长表列名
GROWTH_COL = {
    "hp": "HP+", "atk": "攻击+", "arm": "护甲+", "spd": "速度+", "sta": "耐力+",
}
BASE_KEYS = ["hp", "sta", "atk", "arm", "spd", "sta_regen",
             "crit", "tough", "pen", "morale", "guts", "weight"]

# Excel 缺失时的兜底常数，保证程序不至于崩
FALLBACK_CONST = {
    "TICK": 0.1, "ARM_K": 100, "BASE_INTERVAL": 1.2,
    "EXHAUST_TIME": 1.5, "EXHAUST_VULN": 0.5, "CRIT_MULT": 1.5,
    "BLOCK_REDUCE": 0.6, "BLOCK_REFLECT": 0.3,
    "BATTLE_TIME": 60, "SUDDEN_DEATH": 45, "SUDDEN_DEATH_RATE": 0.05,
    "MORALE_FLEE": 30, "MORALE_LOSS_PER_DMG": 0.35, "MORALE_CRIT_LOSS": 3.0,
    "CHIRP_SELF_MORALE": 12, "CHIRP_FOE_MORALE": 8,
    "MIN_DAMAGE": 1, "BLEED_INTERVAL": 0.5, "BLEED_PER_TICK": 3,
}


class StatsDB:
    """单例，全局共享一份数值表。"""

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
            cls._inst._loaded = False
        return cls._inst

    def __init__(self):
        if getattr(self, "_loaded", False):
            return
        self.data = {}
        self.error = ""
        self._loaded = True
        self.reload()

    # ---------- 加载 ----------

    def reload(self) -> bool:
        try:
            self.error = ""
            self._maybe_export()
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                candidate = json.load(f)
            if not isinstance(candidate, dict):
                raise ValueError("数值表 JSON 必须是对象")
            self.data = candidate
            return True
        except Exception as e:
            self.error = f"{self.error}; {e}" if self.error else str(e)
            return False

    def _maybe_export(self) -> None:
        """Excel 比 JSON 新就重新导出（需要时才 import openpyxl，省启动时间）。"""
        if not os.path.exists(JSON_PATH) or (
            os.path.exists(XLSX)
            and os.path.getmtime(XLSX) > os.path.getmtime(JSON_PATH)
        ):
            try:
                import 导出数值表 as exporter
                exporter.export()
            except Exception as e:
                self.error = f"自动导出失败: {e}"

    # ---------- 查询 ----------

    def const(self, name: str, default=None):
        row = self.data.get("战斗常数", {}).get(name)
        if row is None:
            return FALLBACK_CONST.get(name, default)
        v = row.get("值", default)
        if v is None:
            return FALLBACK_CONST.get(name, default)
        return v

    def species(self, sid):
        return self.data.get("品种", {}).get(sid)

    def species_ids(self):
        return self.data.get("_品种顺序", [])

    def growth(self, level: int):
        # JSON 对象的 key 一律是字符串，必须转 str 再查
        return self.data.get("成长", {}).get(str(int(level)), {})

    @property
    def max_level(self) -> int:
        return max((int(key) for key in self.data.get('成长', {}) if str(key).isdigit()), default=1)

    def exp_need(self, level: int) -> int:
        g = self.growth(level)
        v = g.get("本级升级经验")
        return max(1, int(v) if v is not None else 40 + (level - 1) * 35)

    def move(self, mid):
        return self.data.get("招式", {}).get(mid)

    def move_by_name(self, name):
        mid = self.data.get("_招式ByName", {}).get(name)
        return self.move(mid) if mid else None

    def counter(self, atk_name: str, def_name: str) -> float:
        return float(self.data.get("克制", {}).get(f"{atk_name}>{def_name}", 1.0))

    def status(self, sid):
        return self.data.get("状态", {}).get(sid)

    def talent(self, tid):
        return self.data.get("天赋", {}).get(tid)

    def talents(self):
        return self.data.get("天赋", {})

    # ---------- 派生计算 ----------

    def compute(self, species_id: str, level: int = 1, talent_ids=None) -> dict:
        """算出一只蛐蛐的最终属性。返回 (属性dict, 条件天赋list)。"""
        sp = self.species(species_id) or {}
        stats = {}

        for key in BASE_KEYS:
            col = SPECIES_COL.get(key)
            base = sp.get(col) if col else None
            if base is None:
                base = {"morale": 100}.get(key, 0)
            stats[key] = float(base)

        # 等级成长：从第 2 级开始累加
        for lv in range(2, int(level) + 1):
            g = self.growth(lv)
            if not g:
                continue
            for key, col in GROWTH_COL.items():
                v = g.get(col)
                if v is not None:
                    stats[key] += float(v)

        conditional = []
        for tid in (talent_ids or []):
            t = self.talent(tid)
            if not t:
                continue
            self._apply_talent(stats, t, conditional)

        return stats, conditional

    @staticmethod
    def _apply_talent(stats: dict, talent: dict, conditional: list) -> None:
        raw = str(talent.get("参数", "") or "")
        for part in raw.split(";"):
            part = part.strip()
            if not part:
                continue
            # 条件触发型（如 hp<30%:atk*1.30）留给战斗系统判定
            if "<" in part or ">" in part:
                conditional.append(part)
                continue
            if "*" in part:
                k, v = part.split("*", 1)
                k = k.strip()
                if k in stats:
                    try:
                        stats[k] *= float(v)
                    except ValueError:
                        pass
            elif "+" in part:
                k, v = part.split("+", 1)
                k = k.strip()
                if k in stats:
                    try:
                        stats[k] += float(v)
                    except ValueError:
                        pass

    # ---------- 战斗公式（数值全部来自表） ----------

    def damage_after_armor(self, raw: float, arm: float, pen: float = 0.0) -> float:
        """护甲百分比减伤，破甲先扣护甲。带保底伤害。"""
        eff_arm = max(0.0, float(arm) - float(pen))
        k = float(self.const("ARM_K", 100))
        mult = k / (k + eff_arm) if k + eff_arm > 0 else 1.0
        return max(float(self.const("MIN_DAMAGE", 1)), raw * mult)

    def power(self, stats: dict) -> float:
        """战力评分：给玩家一个直观的强弱数字。"""
        return sum(float(stats.get(k, 0)) * w for k, w in POWER_WEIGHT.items())

    def attack_interval(self, spd: float) -> float:
        """出手间隔。速度走线性收益：速度翻倍则出手频率翻倍，
        这样速度与其他属性是同一量级的成长，不会出现后期完全没感觉的问题。
        """
        base = float(self.const("BASE_INTERVAL", 1.2))
        ref = float(self.const("REF_SPD", 20))
        floor = float(self.const("MIN_INTERVAL", 0.25))
        s = max(1.0, float(spd))
        return max(floor, base * ref / s)


# 战力权重（后续可移进数值表做成第 9 张表）
POWER_WEIGHT = {
    "hp": 0.4, "sta": 0.3, "atk": 3.0, "arm": 2.0, "spd": 2.0,
    "crit": 2.0, "tough": 1.5, "pen": 1.5, "guts": 0.5,
}


def fmt_num(v) -> str:
    """属性展示：整数就不带小数。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(round(f))) if abs(f - round(f)) < 1e-6 else f"{f:.1f}"
