# -*- coding: utf-8 -*-
"""战斗系统自检清单。跑法：

    python battle_checklist.py

全部通过输出 ALL PASS 并返回 0；任何一项失败打印 FAIL 并返回 1。
不依赖桌宠主程序，可单独跑（引擎层）；竞技场冒烟测试用 offscreen 渲染。
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from battle import Battle, Fighter, make_fighter
from stats import StatsDB

db = StatsDB()
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, ok, note))
    print(("  PASS " if ok else "  FAIL ") + name + (f"  [{note}]" if note else ""))


def run_battle(seed, la=None, ra=None, max_ticks=2000):
    """构建一场战斗并跑完，返回 (battle, 全部事件)。"""
    la = la or {"name": "左军", "side": 0, "level": 10, "stats": {
        "hp": 175, "sta": 73, "atk": 29, "arm": 31, "spd": 25,
        "sta_regen": 7, "crit": 8, "guts": 70, "morale": 100, "pen": 0}}
    ra = ra or {"name": "右军", "side": 1, "level": 10, "stats": {
        "hp": 160, "sta": 80, "atk": 27, "arm": 25, "spd": 22,
        "sta_regen": 6, "crit": 5, "guts": 50, "morale": 100, "pen": 0}}
    b = Battle(db, Fighter(**la), Fighter(**ra), seed=seed)
    events = []
    for _ in range(max_ticks):
        events += b.step()
        if b.over:
            break
    return b, events


def main() -> int:
    print("== 战斗系统自检 ==")

    # 1. 公式核验：护甲减伤与保底
    d1 = db.damage_after_armor(100, 100, 0)     # ARM=K → 恰好减半
    d2 = db.damage_after_armor(100, 0, 0)       # 无护甲 → 全额
    d3 = db.damage_after_armor(0.01, 9999, 0)   # 保底 1 点
    check("公式·护甲减伤 ARM/(ARM+K)", abs(d1 - 50) < 0.01, f"100→{d1}")
    check("公式·零护甲全额", abs(d2 - 100) < 0.01, f"→{d2}")
    check("公式·保底伤害", abs(d3 - 1) < 0.01, f"→{d3}")

    # 2. 确定性：同种子两次战斗事件流完全一致
    _, e1 = run_battle(42)
    _, e2 = run_battle(42)
    check("引擎·同种子复现一致", e1 == e2, f"{len(e1)} 事件")

    # 3. 大样本：全部打完、结果合法、数值不越界
    reasons, winners = set(), set()
    ok_bounds = True
    for i in range(60):
        b, ev = run_battle(random.randrange(1 << 30))
        check_over = b.over and b.winner in (0, 1, None) and b.end_reason
        if not check_over:
            ok_bounds = False
        reasons.add(b.end_reason)
        winners.add(b.winner)
        for e in ev:
            if "dmg" in e and e["dmg"] < 0:
                ok_bounds = False
            if "hp" in e and (e["hp"] < 0 or e["hp"] > 999):
                ok_bounds = False
    check("引擎·60 场全部正常终局", ok_bounds, f"终局原因 {sorted(reasons)}")

    # 4. 终局手段覆盖：击倒与士气崩溃都出现过
    check("玩法·击倒结局存在", "击倒" in reasons)
    check("玩法·士气崩溃结局存在", "士气崩溃" in reasons)

    # 5. 定向触发·力竭：耐力耗尽必然出力竭事件
    low_sta = {"name": "没劲的", "side": 1, "level": 1, "stats": {
        "hp": 500, "sta": 12, "atk": 5, "arm": 10, "spd": 10,
        "sta_regen": 1, "crit": 0, "guts": 90, "morale": 100, "pen": 0}}
    _, ev = run_battle(7, ra=low_sta)
    check("玩法·力竭触发", any(e["type"] == "exhaust" for e in ev))

    # 6. 定向触发·败退：低士气被鸣叫/伤害一压就跑
    scared = {"name": "胆小的", "side": 1, "level": 1, "stats": {
        "hp": 500, "sta": 200, "atk": 5, "arm": 10, "spd": 10,
        "sta_regen": 30, "crit": 0, "guts": 0, "morale": 8, "pen": 0}}
    _, ev = run_battle(3, ra=scared)
    fled = any(e["type"] == "end" and e["reason"] == "士气崩溃" for e in ev)
    check("玩法·低士气迅速败退", fled)

    # 7. 格挡反弹：防御方摆格挡时出现反弹伤害事件
    seen_reflect = False
    for i in range(30):
        _, ev = run_battle(1000 + i)
        if any(e["type"] == "reflect" for e in ev):
            seen_reflect = True
            break
    check("玩法·格挡反弹出现过", seen_reflect)

    # 8. 突然死亡 + 平局判定：肉度拉满拖到超时，伤害倍率上涨且血量接近判平
    tank_l = {"name": "肉盾L", "side": 0, "level": 1, "stats": {
        "hp": 99999, "sta": 999, "atk": 1, "arm": 999, "spd": 5,
        "sta_regen": 50, "crit": 0, "guts": 99, "morale": 100, "pen": 0}}
    tank_r = dict(tank_l, name="肉盾R", side=1)
    b, _ = run_battle(5, la=tank_l, ra=tank_r, max_ticks=1200)
    check("玩法·突然死亡倍率生效", b.t > 45 and b.sudden_mult > 1.0,
          f"t={b.t:.0f}s mult={b.sudden_mult:.2f}")
    check("玩法·超时判定出平局", b.winner is None and b.end_reason == "势均力敌",
          f"winner={b.winner} reason={b.end_reason}")

    # 9. 竞技场冒烟：离屏渲染跑完整场，不崩、能出结算
    ok_smoke = _arena_smoke()
    check("表现·竞技场离屏跑完整场", ok_smoke)

    print()
    fails = [r for r in RESULTS if not r[1]]
    print(f"== {len(RESULTS) - len(fails)}/{len(RESULTS)} 通过 ==")
    return 0 if not fails else 1


def _arena_smoke() -> bool:
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPixmap

        app = QApplication.instance() or QApplication(sys.argv)

        class FakePet:
            species_id = "c001"
            level = 8
            talents: list = []
            palette = None
            xp_log: list = []

            def _add_xp(self, n):
                self.xp_log.append(n)

        from cricket import palette_from_hex
        pet = FakePet()
        pet.palette = palette_from_hex("#6FA83C")

        from arena import ArenaWindow
        win = ArenaWindow(pet)
        for _ in range(2600):          # ≈78 秒，足够打完整场
            win._frame()
            if not win.result_box.isHidden():
                break
        pm = QPixmap(win.size())
        win.render(pm)
        ok = not pm.isNull() and win.battle.over
        print(f"    [smoke] 战斗结束={win.battle.over} "
              f"胜者={win.battle.winner} 原因={win.battle.end_reason} "
              f"XP={pet.xp_log}")
        win.close()
        return ok
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    sys.exit(main())
