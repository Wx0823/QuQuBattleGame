# -*- coding: utf-8 -*-
"""装备系统：生成 / 掉落 / 背包 / 属性加成（纯逻辑，不依赖 Qt）。

设计要点：
  - 部位、品质、词条全部来自数值表（10/11/12 三张表），可动态扩展
  - 词条数值 = 基础值 × 品质数值倍率 × 随机浮动(0.85~1.25)，3% 概率按高 1 档品质生成
  - 掉落：按难度表的掉落概率 + 品质权重掷骰
  - 背包/穿戴状态持久化在 data/inventory.json
"""

from __future__ import annotations

import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
INV_PATH = os.path.join(HERE, "data", "inventory.json")

UPGRADE_CHANCE = 0.03   # 词条按高 1 档品质生成的概率


# ---------- 背包持久化 ----------

def _read_inv() -> dict:
    try:
        with open(INV_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"items": {}, "equipped": {}, "next_uid": 1}


def _write_inv(data: dict) -> None:
    os.makedirs(os.path.dirname(INV_PATH), exist_ok=True)
    try:
        with open(INV_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_inventory() -> dict:
    return _read_inv()


def save_inventory(data: dict) -> None:
    _write_inv(data)


# ---------- 生成 ----------

def _weighted_choice(rng: random.Random, pairs: list) -> str:
    total = sum(w for _k, w in pairs)
    roll = rng.uniform(0, total)
    acc = 0.0
    for k, w in pairs:
        acc += w
        if roll <= acc:
            return k
    return pairs[-1][0]


def tier_mult(db, quality_id: str) -> float:
    q = db.data.get("装备品质", {}).get(quality_id, {})
    return float(q.get("数值倍率", 1.0))


def quality_order(db) -> list:
    return db.data.get("_装备品质顺序", [])


def make_item(db, rng: random.Random, diff_id: str) -> dict:
    """按难度掷一次装备掉落，返回装备实例 dict。"""
    conf = db.data["副本难度"].get(diff_id, {})
    if rng.uniform(0, 100) > float(conf.get("装备掉落概率", 20) or 20):
        return {}

    # 品质：按难度权重
    weight_str = str(conf.get("装备品质权重", "") or "")
    pairs = []
    for part in weight_str.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        qid, w = part.split(":", 1)
        pairs.append((qid.strip(), float(w)))
    if not pairs:
        return {}
    quality_id = _weighted_choice(rng, pairs)

    order = quality_order(db)
    slot_ids = db.data.get("_装备部位顺序", [])
    if not slot_ids:
        return {}
    slot_id = rng.choice(slot_ids)
    slot_conf = db.data.get("装备部位", {}).get(slot_id, {})
    quality_conf = db.data.get("装备品质", {}).get(quality_id, {})

    # 词条：按品质词条数，从适配该部位的词条池按权重抽（不重复）
    n_affix = int(quality_conf.get("词条数", 1))
    slot_name = slot_conf.get("名称", slot_id)
    eligible = []
    for aid, a in db.data.get("装备词条", {}).items():
        slots = str(a.get("部位", "") or "")
        if slots == "全部" or slot_name in [s.strip() for s in slots.split(",")]:
            eligible.append((aid, float(a.get("权重", 1) or 1)))
    if not eligible:
        return {}

    affixes = []
    for _ in range(n_affix):
        if not eligible:
            break
        aid = _weighted_choice(rng, eligible)
        eligible = [x for x in eligible if x[0] != aid]
        a = db.data["装备词条"][aid]
        # 数值：3% 概率按高 1 档品质生成
        t = quality_id
        upgrade = rng.uniform(0, 100) < UPGRADE_CHANCE * 100
        if upgrade:
            idx = order.index(quality_id) if quality_id in order else -1
            if 0 <= idx + 1 < len(order):
                t = order[idx + 1]
        val = float(a.get("基础值", 1)) * tier_mult(db, t) \
            * rng.uniform(0.85, 1.25)
        val = max(1.0, round(val, 1))
        affixes.append({"id": aid, "val": val, "up": upgrade})

    return {
        "slot": slot_id,
        "quality": quality_id,
        "affixes": affixes,
    }


def item_name(db, item: dict) -> str:
    slot = db.data.get("装备部位", {}).get(item["slot"], {})
    q = db.data.get("装备品质", {}).get(item["quality"], {})
    return f"{q.get('名称', '?')}·{slot.get('名称', '?')}"


def quality_color(db, item: dict) -> str:
    q = db.data.get("装备品质", {}).get(item["quality"], {})
    return str(q.get("颜色", "#D5D8DC"))


def item_affix_text(db, item: dict) -> list:
    """[(文本, 是否跨档)] —— UI 展示用。"""
    out = []
    for aff in item.get("affixes", []):
        a = db.data.get("装备词条", {}).get(aff["id"], {})
        attr = str(a.get("属性ID", ""))
        attr_name = db.data.get("属性定义", {}).get(attr, {}).get("属性名", attr)
        out.append((f"{attr_name} +{fmt_val(aff['val'])}", aff.get("up", False)))
    return out


def fmt_val(v: float) -> str:
    return str(int(round(v))) if abs(v - round(v)) < 1e-6 else f"{v:.1f}"


# ---------- 背包 / 穿戴 ----------

def add_item(db, item: dict) -> str | None:
    """入库。空掉落（未掷中）直接忽略，返回 None。"""
    if not item or "slot" not in item:
        return None
    data = _read_inv()
    uid = str(data.get("next_uid", 1))
    data["next_uid"] = int(uid) + 1
    item["uid"] = uid
    item["名称"] = item_name(db, item)
    data["items"][uid] = item
    _write_inv(data)
    return uid


def get_items() -> dict:
    return _read_inv().get("items", {})


def get_equipped() -> dict:
    return _read_inv().get("equipped", {})


def equip(uid: str) -> dict | None:
    """穿戴：同部位旧装备回背包。返回被替换下的装备（可能 None）。"""
    data = _read_inv()
    item = data["items"].get(uid)
    if not item:
        return None
    replaced = data["equipped"].get(item["slot"])
    data["equipped"][item["slot"]] = uid
    _write_inv(data)
    return data["items"].get(replaced) if replaced else None


def unequip(slot: str) -> dict | None:
    data = _read_inv()
    uid = data["equipped"].pop(slot, None)
    _write_inv(data)
    return data["items"].get(uid) if uid else None


def equipped_items() -> list:
    """当前穿戴中的装备实例列表。"""
    data = _read_inv()
    out = []
    for uid in data.get("equipped", {}).values():
        it = data["items"].get(uid)
        if it:
            out.append(it)
    return out


# ---------- 属性加成 ----------

def bonus_stats(equipped: list | None = None) -> dict:
    """穿戴中装备的词条合计。"""
    bonus: dict = {}
    for item in (equipped if equipped is not None else equipped_items()):
        for aff in item.get("affixes", []):
            a = _read_affix(aff["id"])
            if not a:
                continue
            attr = str(a.get("属性ID", ""))
            if not attr:
                continue
            bonus[attr] = bonus.get(attr, 0) + float(aff.get("val", 0))
    return bonus


def apply_bonus(base: dict, bonus: dict) -> dict:
    """基础属性 + 装备加成 → 最终属性（返回新 dict）。"""
    out = dict(base)
    for k, v in bonus.items():
        out[k] = float(out.get(k, 0)) + float(v)
    return out


def effective_stats(db, species_id: str, level: int,
                    talents=None, equipped: list | None = None) -> dict:
    """基础属性 + 装备加成。"""
    base, _cond = db.compute(species_id, level, talents or [])
    if equipped is None:
        equipped = equipped_items()
    return apply_bonus(base, bonus_stats(equipped))


def _read_affix(aid: str) -> dict:
    # 延迟加载，避免测试环境反复读文件
    global _AFFIX_CACHE
    if _AFFIX_CACHE is None:
        from stats import StatsDB
        _AFFIX_CACHE = StatsDB().data.get("装备词条", {})
    return _AFFIX_CACHE.get(aid, {})


_AFFIX_CACHE: dict | None = None


def invalidate_cache() -> None:
    global _AFFIX_CACHE
    _AFFIX_CACHE = None
