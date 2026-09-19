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
from dungeon import DungeonRun
from stats import StatsDB

db = StatsDB()
RESULTS: list[tuple[str, bool, str]] = []

# 各难度入场等级（对应副本规划的玩家成长节奏）
ENTRY_LV = {"d01": 1, "d02": 7, "d03": 12, "d04": 17, "d05": 23,
            "d06": 29, "d07": 36, "d08": 44, "d09": 53, "d10": 63}


def check(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, ok, note))
    print(("  PASS " if ok else "  FAIL ") + name + (f"  [{note}]" if note else ""))


def _random_fighter(side: int):
    """随机品种 + 随机等级，贴近真实对局的属性分布。"""
    sid = random.choice(db.species_ids())
    lv = random.randint(3, 14)
    sp = db.species(sid) or {}
    return {"name": f"{sp.get('名称', sid)}{side}", "side": side, "level": lv,
            "stats": db.compute(sid, lv)[0]}


def run_battle(seed, la=None, ra=None, max_ticks=2000):
    """构建一场战斗并跑完，返回 (battle, 全部事件)。"""
    la = la or _random_fighter(0)
    ra = ra or _random_fighter(1)
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

    # 2. 确定性：同种子+同蛐蛐，两次战斗事件流完全一致
    la, ra = _random_fighter(0), _random_fighter(1)
    _, e1 = run_battle(42, la=la, ra=ra)
    _, e2 = run_battle(42, la=la, ra=ra)
    check("引擎·同种子复现一致", e1 == e2, f"{len(e1)} 事件")

    # 3. 大样本：全部打完、结果合法、数值不越界；并统计力竭频率
    reasons, winners = set(), set()
    ok_bounds = True
    total_ex = 0
    for i in range(150):
        b, ev = run_battle(random.randrange(1 << 30))
        check_over = b.over and b.winner in (0, 1, None) and b.end_reason
        if not check_over:
            ok_bounds = False
        reasons.add(b.end_reason)
        winners.add(b.winner)
        total_ex += sum(1 for e in ev if e["type"] == "exhaust")
        for e in ev:
            if "dmg" in e and e["dmg"] < 0:
                ok_bounds = False
            if "hp" in e and (e["hp"] < 0 or e["hp"] > 999):
                ok_bounds = False
    check("引擎·150 场全部正常终局", ok_bounds, f"终局原因 {sorted(reasons)}")
    avg_ex = total_ex / 150.0
    check("节奏·力竭是点缀不是常态", avg_ex <= 2.5,
          f"场均力竭 {avg_ex:.1f} 次")

    # 4. 终局手段：击倒看统计；士气崩溃用定向构造（随机对局中它是小概率结局）
    check("玩法·击倒结局存在", "击倒" in reasons)
    scare = {"name": "胆气弱", "side": 1, "level": 8, "stats": {
        "hp": 160, "sta": 90, "atk": 20, "arm": 20, "spd": 20,
        "sta_regen": 6, "crit": 0, "guts": 5, "morale": 40, "pen": 0}}
    bully = {"name": "恶霸", "side": 0, "level": 8, "stats": {
        "hp": 300, "sta": 90, "atk": 38, "arm": 25, "spd": 24,
        "sta_regen": 7, "crit": 0, "guts": 60, "morale": 100, "pen": 0}}
    _, ev = run_battle(19, la=bully, ra=scare)
    check("玩法·士气崩溃可触发",
          any(e["type"] == "end" and e["reason"] == "士气崩溃" for e in ev))

    # 4.5 克制表：查表正确 + 实战中克制命中出现
    check("公式·克制查表", db.counter("摔投", "格挡") == 1.3
          and db.counter("轻咬", "格挡") == 0.45
          and db.counter("冲撞", "冲撞") == 1.1)
    n_counter = 0
    for i in range(150):
        _, ev = run_battle(random.randrange(1 << 30))
        n_counter += sum(1 for e in ev if e.get("counter"))
    check("玩法·克制命中出现", n_counter >= 5, f"150 场共 {n_counter} 次")

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

    # 10. 副本曲线：挂机模拟全部难度，校准通关时长
    rows = check_dungeon_curve()
    d01 = next((r for r in rows if r["id"] == "d01"), None)
    check("副本·新手 30 分钟档", d01 is not None and d01["done"]
          and 15 <= d01["time"] / 60 <= 50,
          f"{d01['time']/60:.1f}min" if d01 else "")
    check("副本·d01-d08 可通关", all(
        r["done"] for r in rows if r["id"] in ("d01", "d02", "d03", "d04",
                                               "d05", "d06", "d07", "d08")))
    d09r = next(r for r in rows if r["id"] == "d09")
    d10r = next(r for r in rows if r["id"] == "d10")
    check("副本·绝望为长线墙（可达 19 层，通关需场外成长）",
          d09r["max_floor"] >= 19, f"最远第 {d09r['max_floor']} 层")
    check("副本·真神为终极天花板（入场即硬墙，不崩即可）",
          d10r["max_floor"] >= 2, f"最远第 {d10r['max_floor']} 层")

    # 11. 桌面舞台：战败后玩家必须复活重建（鞭尸 bug 回归测试）
    check("副本·战败后玩家复活重建", _stage_retry_smoke())
    # 12. 桌面舞台：残血退出副本 → 续打 → 血量保留（不回满）
    check("副本·切换模式血量保留", _resume_hp_smoke())
    times = [r["time"] / 60 for r in rows]
    check("副本·难度耗时递增", all(a <= b * 1.6 for a, b in zip(times, times[1:])),
          "->".join(f"{t:.0f}" for t in times))

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
        ok = not pm.isNull() and win.stage.battle.over
        print(f"    [smoke] 战斗结束={win.stage.battle.over} "
              f"胜者={win.stage.battle.winner} 原因={win.stage.battle.end_reason} "
              f"XP={pet.xp_log}")
        win.close()
        return ok
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


def _level_from_xp(xp: int) -> int:
    lv = 1
    while xp >= db.exp_need(lv) and lv < 300:
        xp -= db.exp_need(lv)
        lv += 1
    return lv


def _cum_exp(lv: int) -> int:
    """累计经验：从 1 级升到 lv 所需总量。"""
    t = 0
    for k in range(1, lv):
        t += db.exp_need(k)
    return t


def sim_dungeon(diff_id: str, seed: int = 1) -> dict:
    """无动画快进模拟：玩家按入场等级自动挂完整个副本。

    返回 {time(秒), retries, lv(最终等级), done}。
    """
    dr = DungeonRun(db, diff_id, seed=seed)
    # 玩家带着入场等级的累计经验进入，副本内经验是增量
    xp_base = _cum_exp(ENTRY_LV.get(diff_id, 1))
    xp_total = 0
    t = 0.0
    retries = 0
    frac_hp = frac_sta = 1.0
    max_floor = 1
    guard = 0
    while guard < 15000:
        guard += 1
        lv = _level_from_xp(xp_base + xp_total)
        stats, _ = db.compute("c001", lv)
        pf = Fighter("模拟玩家", 0, lv, stats)
        pf.hp = max(1.0, pf.hp_max * frac_hp)
        pf.sta = max(1.0, pf.sta_max * frac_sta)
        ef = dr.make_enemy(dr.eidx)
        b = Battle(db, pf, ef, seed=dr.rng.randrange(1 << 30))
        for _ in range(2000):
            b.step()
            if b.over:
                break
        t += b.t + 2.0   # 战斗时长 + 敌人间休整
        win = b.winner == 0
        frac_hp = max(0.02, pf.hp / pf.hp_max)
        frac_sta = max(0.02, pf.sta / pf.sta_max)
        res = dr.on_fight_end(win)
        xp_total += res.get("xp", 0)
        if win:
            frac_hp = min(1.0, frac_hp + 0.50)
            frac_sta = min(1.0, frac_sta + 0.30)
        else:
            frac_hp = frac_sta = 1.0
            retries += 1
        if res["result"] == "floor_clear":
            frac_hp = frac_sta = 1.0   # 清层休整回满
        if dr.floor > max_floor:
            max_floor = dr.floor
        if res["result"] == "diff_clear":
            lv = _level_from_xp(xp_base + xp_total)
            return {"time": t, "retries": retries, "lv": lv,
                    "done": True, "max_floor": max_floor}
    lv = _level_from_xp(xp_base + xp_total)
    return {"time": t, "retries": retries, "lv": lv,
            "done": False, "max_floor": max_floor}


def _stage_retry_smoke() -> bool:
    """桌面舞台副本：把敌人血量改到打不死逼出一场败局，
    验证战败后玩家 Fighter 被复活重建、尸体状态被清理。"""
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        class FP:
            species_id = "c001"
            level = 1
            talents: list = []
            palette = None

            def _add_xp(self, n):
                pass

        from cricket import palette_from_hex
        from stage import BattleStage
        pet = FP()
        pet.palette = palette_from_hex("#6FA83C")
        st = BattleStage(pet, style="desktop", diff_id="d01")
        phase = 0
        for _k in range(6000):
            st.update(0.03)
            if phase == 0 and st.battle is not None:
                st.f[1][0].hp = 10 ** 9      # 打不死的敌人 → 必败
                phase = 1
            if phase == 1 and any("战败" in line for line in st.log):
                # 战败已结算：等新敌人入场、新战斗开始
                if (st.battle is not None and st.f[0][0].hp > 1.0
                        and st.fx["ko"] is None):
                    return True
            if st.dungeon_result is not None:
                return False
        return False
    except Exception:
        import traceback
        traceback.print_exc()
        return False


def _resume_hp_smoke() -> bool:
    """残血退出副本（保存断点）→ 续打 → 血量必须按断点恢复，而不是满血。"""
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        class FP:
            species_id = "c001"
            level = 10
            talents: list = []
            palette = None

            def _add_xp(self, n):
                pass

        from cricket import palette_from_hex
        from stage import BattleStage
        DungeonRun._write_save({})       # 清历史记录
        pet = FP()
        pet.palette = palette_from_hex("#6FA83C")
        st = BattleStage(pet, style="desktop", diff_id="d01")
        st._frac = [0.5, 0.6]            # 模拟残血状态
        st.on_exit()                     # 保存断点
        st2 = BattleStage(pet, style="desktop", resume=True)
        ok = (abs(st2._frac[0] - 0.5) < 0.02
              and abs(st2._frac[1] - 0.6) < 0.02
              and st2.f[0][0].hp < st2.f[0][0].hp_max * 0.6)
        DungeonRun.clear_run()
        return ok
    except Exception:
        import traceback
        traceback.print_exc()
        return False


def check_dungeon_curve() -> list[dict]:
    """模拟全部 10 档难度，输出通关时长曲线。"""
    print("  -- 副本挂机模拟（4h/日生态校准） --")
    print("  难度   通关耗时   重试   最终等级")
    rows = []
    for did in ["d01", "d02", "d03", "d04", "d05",
                "d06", "d07", "d08", "d09", "d10"]:
        r = sim_dungeon(did, seed=42)
        name = db.data["副本难度"][did].get("名称", did)
        flag = "" if r["done"] else f"  [未通·最远第{r['max_floor']}层]"
        print(f"  {name:<4} {r['time']/60:7.1f}min  {r['retries']:4d}   Lv.{r['lv']}{flag}")
        rows.append({"id": did, "name": name, **r})
    return rows


if __name__ == "__main__":
    sys.exit(main())
