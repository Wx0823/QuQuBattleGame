"""装备面板状态：一次读档、筛选排序和换装预览，不依赖 Qt。"""
from __future__ import annotations

import equipment


class EquipmentViewModel:
    def __init__(self, db, pet):
        self.db, self.pet = db, pet
        self.inventory = {"items": {}, "equipped": {}}
        self.selected_uid = None
        self.slot_filter = None
        self.quality_filter = None
        self.sort = "newest"
        self._snapshot = None

    @property
    def items(self):
        return self.inventory.get("items", {})

    @property
    def equipped(self):
        return self.inventory.get("equipped", {})

    @property
    def selected(self):
        return self.items.get(self.selected_uid)

    def reload(self):
        inventory = equipment.load_inventory()
        pet_state = (self.pet.species_id, self.pet.level, getattr(self.pet, "xp", 0),
                     tuple(self.pet.talents), bool(getattr(self.pet, "_stage", None)))
        snapshot = (inventory, pet_state)
        changed = snapshot != self._snapshot
        self.inventory = inventory
        self._snapshot = snapshot
        if self.selected_uid not in self.items:
            self.selected_uid = None
        return changed

    def visible_items(self):
        items = [item for item in self.items.values()
                 if (not self.slot_filter or item["slot"] == self.slot_filter)
                 and (not self.quality_filter or item["quality"] == self.quality_filter)]
        ranks = {qid: i for i, qid in enumerate(equipment.quality_order(self.db))}
        def uid_key(item):
            uid = str(item["uid"])
            return (int(uid) if uid.isdigit() else -1, uid)
        if self.sort == "quality":
            return sorted(items, key=lambda it: (ranks.get(it["quality"], -1), uid_key(it)), reverse=True)
        return sorted(items, key=uid_key, reverse=True)

    def worn_items(self):
        return [self.items[uid] for uid in self.equipped.values() if uid in self.items]

    def stats(self):
        return equipment.effective_stats(self.db, self.pet.species_id,
                                         self.pet.level, self.pet.talents, self.worn_items())

    def comparison(self, item=None):
        """选中装备相对当前同部位装备的属性差，包含替换后失去的词条。"""
        item = self.selected if item is None else item
        if not item or self.equipped.get(item["slot"]) == item["uid"]:
            return {}
        old = self.items.get(self.equipped.get(item["slot"]))
        def bonuses(it):
            result = {}
            for aff in (it or {}).get("affixes", []):
                attr = self.db.data.get("装备词条", {}).get(aff["id"], {}).get("属性ID")
                if attr:
                    result[attr] = result.get(attr, 0) + float(aff["val"])
            return result
        before, after = bonuses(old), bonuses(item)
        return {key: after.get(key, 0) - before.get(key, 0)
                for key in dict.fromkeys([*before, *after])
                if abs(after.get(key, 0) - before.get(key, 0)) > 1e-6}

    def upgrades(self):
        """全背包每部位仅推荐一件无损提升；按战力收益、属性收益、品质择优。"""
        best = {}
        ranks = {qid: i for i, qid in enumerate(equipment.quality_order(self.db))}
        # 并列时固定选择较早获得的 UID，不受背包排序和筛选影响。
        ordered = sorted(self.items.items(), key=lambda pair: (
            int(pair[0]) if str(pair[0]).isdigit() else float('inf'), str(pair[0])))
        for uid, item in ordered:
            delta = self.comparison(item)
            if delta and all(value > 0 for value in delta.values()):
                score = (round(self.db.power(delta), 6), round(sum(delta.values()), 6),
                         ranks.get(item['quality'], -1))
                slot = item['slot']
                if slot not in best or score > best[slot][0]:
                    best[slot] = (score, uid)
        return {uid for _, uid in best.values()}

    def toggle_selected(self):
        # 操作前重读，防止定时刷新间隙里装备已变动。
        self.reload()
        item = self.selected
        if item:
            if self.equipped.get(item["slot"]) == item["uid"]:
                equipment.unequip(item["slot"])
            else:
                equipment.equip(item["uid"])
