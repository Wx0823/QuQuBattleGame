"""整项目玩法回归；实际 Pet/BattleStage，临时存档、离屏 Qt。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import math
import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter
import main
import settings
import equipment
import dungeon
from arena import ArenaWindow
from battle import Battle, Fighter, make_fighter
from stage import BattleStage
from stats import StatsDB
from persistence import write_json
from test_support import isolated_game_data


class GameplayTests(unittest.TestCase):
    def test_idle_grass_buttons_and_header_at_all_zooms(self):
        from art_assets import sprite
        self.assertFalse(sprite('grass').isNull())
        for zoom in (.6, 1., 2.):
            self.pet.set_zoom(zoom)
            for button in (self.pet.btn_attr, self.pet.btn_dungeon):
                self.assertGreater(button.x(), (main.CX+75)*zoom)
                self.assertLess(button.geometry().bottom(), (main.TOP_PAD+main.FOOT_Y)*zoom)
                self.assertTrue(self.pet.rect().contains(button.geometry()))
                self.assertTrue(self.pet.mask().contains(button.geometry().center()))
            self.assertFalse(self.pet.btn_attr.geometry().intersects(self.pet.btn_dungeon.geometry()))
            ground = self.pet._grass_rect(zoom)
            pix = sprite('grass')
            self.assertAlmostEqual(ground.width()/ground.height(), pix.width()/pix.height())
            self.assertEqual(self.pet.btn_attr.x(), self.pet.btn_dungeon.x())
            self.assertEqual(self.pet.btn_dungeon.y(), self.pet.btn_attr.y()+self.pet.btn_attr.height()+6)
            self.assertEqual(self.pet.btn_attr.width(), max(44, min(116, int(58*zoom))))
            self.assertEqual(self.pet.btn_attr.height(), max(24, min(48, int(24*zoom))))
            self.assertFalse(self.pet.btn_dungeon.icon().isNull())
        self.pet.settings.show_bar = False
        self.pet._update_mask()
        self.assertTrue(self.pet.mask().contains(self.pet.btn_attr.geometry().center()))

    def test_open_windows_follow_pet_movement(self):
        from PySide6.QtCore import QPoint
        self.pet.show()
        self.pet.move(10, 10)
        self.pet._toggle_equipment_panel()
        equipment_panel = self.pet.equip_panel
        self.pet.settings_panel.show()
        self.pet._place_open_panels()
        self.app.processEvents()
        before = [p.pos() for p in (equipment_panel, self.pet.settings_panel)]
        self.pet.move(self.pet.pos()+QPoint(12, 9))
        self.app.processEvents()
        for panel, old in zip((equipment_panel, self.pet.settings_panel), before):
            self.assertEqual(panel.pos(), old+QPoint(12, 9))
        self.pet.settings_panel.hide()
        hidden_pos = self.pet.settings_panel.pos()
        self.pet.move(self.pet.pos()+QPoint(12, 9))
        self.app.processEvents()
        self.assertEqual(self.pet.settings_panel.pos(), hidden_pos)

    def test_corner_layout_at_all_zooms_and_offset_screens(self):
        from PySide6.QtCore import QRect, QSize, QPoint
        from window_layout import beside, clamp_position
        for bounds in (QRect(0, 0, 1920, 1040), QRect(-1920, 80, 1920, 1040)):
            for zoom in (.6, .79, 1., 2.):
                size = QSize(int(main.WIN_W*zoom), int(main.WIN_H*zoom))
                for corner in (bounds.topLeft(), bounds.topRight(), bounds.bottomLeft(), bounds.bottomRight()):
                    pos = clamp_position(corner, size, bounds)
                    pet = QRect(pos, size)
                    self.assertTrue(bounds.contains(pet))
                    for panel_size in (QSize(320, 400), QSize(380, 620), QSize(788, 620)):
                        panel = QRect(beside(pet, panel_size, bounds), panel_size)
                        self.assertTrue(bounds.contains(panel))
                        self.assertFalse(panel.intersects(pet))
        self.pet.show()
        self.pet.move(-500, -500)
        self.pet._clamp_into_screen()
        self.assertTrue(self.pet.screen().availableGeometry().contains(self.pet.frameGeometry()))

    def test_context_menu_refreshes_state_and_routes_actions(self):
        from menu_ui import create_menu
        menu = create_menu(self.pet)
        try:
            with patch.object(self.pet, '_toggle_settings') as settings_action:
                menu.aboutToShow.emit()
                actions = {a.text(): a for a in menu.actions()}
                self.assertIn('挑战副本', actions)
                actions['蛐蛐设置'].trigger()
                settings_action.assert_called_once()
            self.pet.begin_desktop_battle('d01')
            menu.aboutToShow.emit()
            actions = {a.text(): a for a in menu.actions()}
            self.assertNotIn('挑战副本', actions)
            self.assertIn('蛐蛐装备', actions)
            actions['撤出副本 · 保存进度'].trigger()
            self.assertIsNone(self.pet._stage)
            menu.aboutToShow.emit()
            self.assertEqual(sum(a.text() == '蛐蛐设置' for a in menu.actions()), 1)
        finally:
            menu.deleteLater()

    def test_desktop_clear_auto_enters_next_difficulty_and_stops_at_last(self):
        self.pet.begin_desktop_battle('d01')
        stage = self.pet._stage
        self.ready(stage)
        stage.drun.floor = stage.drun.floors
        stage.drun.eidx = stage.drun.n_enemies - 1
        with patch('main.QTimer.singleShot') as timer:
            self.kill(stage, 1)
            stage._dungeon_advance()
            callback = timer.call_args.args[1]
        callback()
        self.assertEqual(self.pet._stage.drun.diff_id, 'd02')
        self.assertEqual(self.pet._stage.drun.floor, 1)
        next_stage = self.pet._stage
        callback()
        self.assertIs(self.pet._stage, next_stage)
        self.pet.begin_desktop_battle(self.db.data['_副本难度顺序'][-1])
        last = self.pet._stage
        last.dungeon_result = {'result': 'diff_clear'}
        self.pet._delayed_exit_battle(last)
        self.assertIsNone(self.pet._stage)

    def test_idle_level_only_and_equipment_live_experience(self):
        from unittest.mock import MagicMock
        from PySide6.QtGui import QFontMetricsF
        self.pet.level = 80
        self.pet.xp = 123
        for zoom in (.6, 1., 2.):
            painter = MagicMock()
            self.pet._draw_bar(painter, zoom)
            rect, _, label = painter.drawText.call_args.args
            font = painter.setFont.call_args.args[0]
            metrics = QFontMetricsF(font)
            self.assertEqual(label, 'Lv.80')
            self.assertLessEqual(metrics.horizontalAdvance(label), rect.width())
            self.assertLessEqual(metrics.height(), rect.height())
        self.pet._toggle_equipment_panel()
        panel = self.pet.equip_panel
        self.assertIn('123 /', panel.lbl_exp.text())
        self.pet.xp = 124
        panel._poll_refresh()
        self.assertIn('124 /', panel.lbl_exp.text())

    def test_floor_clear_message_reports_completed_and_next_floor(self):
        stage = self.stage()
        self.ready(stage)
        stage.drun.floor = 6
        stage.drun.eidx = stage.drun.n_enemies - 1
        self.kill(stage, 1)
        stage._dungeon_advance()
        self.assertEqual(stage.drun.floor, 7)
        self.assertEqual(stage._rest_msg, '第 6 层攻克！休整后进入第 7 层')

    def test_loot_visuals_queue_render_and_expire_without_duplicate_rewards(self):
        stage = self.stage()
        self.ready(stage)
        with patch('equipment.make_item', return_value=self.loot()):
            self.kill(stage, 1)
            stage._dungeon_advance()
            stage._dungeon_advance()
        self.assertEqual(len(stage.loot_effects.queue), 1)
        self.assertEqual(len(equipment.get_items()), 1)
        fx = stage.loot_effects
        first = fx.queue[0]
        stage.ch[1]['x'] += 80
        self.assertNotEqual(first['x'], stage.ch[1]['x'])
        fx.add(self.db, self.loot(), 300, 240)
        image = QImage(660, 440, QImage.Format.Format_ARGB32)
        for t in (.1, .4, 1.1, 2., 4.4):
            fx.age = t
            image.fill(0)
            painter = QPainter(image)
            try:
                fx.draw(painter, 330, 88)
            finally:
                painter.end()
            self.assertTrue(any(image.pixelColor(x,y).alpha() for x in range(180,480,10) for y in range(80,350,10)))
        fx.update(.3)
        self.assertEqual(len(fx.queue), 1)
        fx.update(5)
        self.assertFalse(fx.queue)
        self.assertEqual(len(equipment.get_items()), 1)

    def test_entry_heading_matches_motion_for_both_hosts(self):
        for style, diff in (('arena', None), ('desktop', 'd01')):
            stage = BattleStage(self.pet, style=style, diff_id=diff)
            for _ in range(20):
                previous = [(ch['x'], ch['y']) for ch in stage.ch]
                stage.update(.03)
                for i in ((0, 1) if diff is None else (1,)):
                    ch = stage.ch[i]
                    dx, dy = ch['x']-previous[i][0], ch['y']-previous[i][1]
                    length = math.hypot(dx, dy)
                    self.assertGreater(length, 0)
                    heading = math.radians(ch['hd'])
                    alignment = (dx*math.cos(heading)+dy*math.sin(heading))/length
                    self.assertGreater(alignment, .999)

    def test_reinforcement_does_not_inherit_ko_or_dash(self):
        stage = self.stage()
        self.ready(stage)
        self.kill(stage, 1)
        stage.ch[1]['dash'] = {'stale': True}
        stage.ch[1]['kn'] = [300., 20.]
        stage._spawn_enemy()
        self.assertIsNone(stage.fx['ko'])
        self.assertIsNone(stage.fx['ko_anim'])
        self.assertIsNone(stage.ch[1]['dash'])
        self.assertEqual(stage.ch[1]['kn'], [0., 0.])
        for _ in range(20):
            ch = stage.ch[1]
            x, y = ch['x'], ch['y']
            stage.update(.03)
            angle = math.radians(ch['hd'])
            self.assertGreater((ch['x']-x)*math.cos(angle)+(ch['y']-y)*math.sin(angle), 0)

    def test_failed_stats_reload_keeps_previous_data(self):
        target = self.root / 'broken_stats.json'
        for content in ('{', '[]'):
            target.write_text(content, encoding='utf-8')
            with patch('stats.JSON_PATH', str(target)), patch.object(self.db, '_maybe_export'):
                self.assertFalse(self.db.reload())
            self.assertEqual(self.db.data, self.original_data)
            self.assertTrue(self.db.error)
        self.db.error = ''

    def test_stats_fallback_retains_export_warning(self):
        target = self.root / 'stats.json'
        write_json(target, self.original_data)
        def fail_export():
            self.db.error = '自动导出失败: 测试'
        with patch('stats.JSON_PATH', str(target)), patch.object(self.db, '_maybe_export', side_effect=fail_export):
            self.assertTrue(self.db.reload())
        self.assertIn('自动导出失败', self.db.error)
        self.assertEqual(self.db.data, self.original_data)
        self.db.error = ''

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.sandbox = isolated_game_data()
        self.root = self.sandbox.__enter__()
        self.hooks = [patch.object(main.Pet, '_init_hook'), patch.object(main.Pet, '_init_tray')]
        for hook in self.hooks: hook.start()
        self.pet = main.Pet()
        self.pet.timer.stop()
        self.db = self.pet.db
        self.original_data = copy.deepcopy(self.db.data)
        self.windows = []

    def tearDown(self):
        for window in self.windows: window.close()
        self.pet.close()
        self.pet.deleteLater()
        self.app.processEvents()
        self.db.data = self.original_data
        for hook in reversed(self.hooks): hook.stop()
        self.sandbox.__exit__(None, None, None)

    def stage(self, diff='d01'):
        return BattleStage(self.pet, style='desktop', diff_id=diff, cx=330, cy=248, radius=236)

    def ready(self, stage):
        old = stage.battle
        for _ in range(100):
            stage.update(.1)
            if stage.battle is not None and not stage.battle.over:
                return
        self.fail('未能开始新一场战斗')

    def kill(self, stage, side):
        events = []
        fighter = stage.f[side][0]
        stage.battle._lose_hp(fighter, fighter.hp, events)
        for event in events: stage._play(event)

    def loot(self):
        return {'slot': self.db.data['_装备部位顺序'][0],
                'quality': self.db.data['_装备品质顺序'][0],
                'affixes': [{'id': next(iter(self.db.data['装备词条'])), 'val': 15, 'up': False}]}

    def test_quit_saves_active_battle_and_stops_timer(self):
        self.pet.begin_desktop_battle('d01')
        stage = self.pet._stage
        self.ready(stage)
        fighter = stage.f[0][0]
        fighter.hp *= .37
        fighter.sta *= .42
        self.pet.timer.start()
        with patch.object(QApplication, 'quit'):
            self.pet._quit()
        self.assertFalse(self.pet.timer.isActive())
        loaded = dungeon.DungeonRun.load_run(self.db)
        self.assertAlmostEqual(loaded[1], fighter.hp)
        self.assertAlmostEqual(loaded[2], fighter.sta)
        restored = BattleStage(self.pet, style='desktop', resume=True)
        self.assertAlmostEqual(restored.f[0][0].hp, fighter.hp)

    def test_arena_close_stops_simulation(self):
        window = ArenaWindow(self.pet)
        self.windows.append(window)
        self.assertTrue(window.timer.isActive())
        window.close()
        self.assertFalse(window.timer.isActive())

    def test_completed_callback_cannot_close_new_dungeon(self):
        old = self.stage()
        old.dungeon_result = {'result': 'diff_clear'}
        self.pet.begin_desktop_battle('d01')
        current = self.pet._stage
        self.pet._delayed_exit_battle(old)
        self.assertIs(self.pet._stage, current)

    def test_battle_settings_do_not_resize_or_mask_field(self):
        self.pet.begin_desktop_battle('d01')
        size = self.pet.size()
        self.pet.set_zoom(1.8)
        self.pet._update_mask()
        self.assertEqual(self.pet.size(), size)
        self.assertTrue(self.pet.mask().isEmpty())
        self.pet.end_desktop_battle()
        self.assertEqual(self.pet.width(), int(main.WIN_W*1.8))

    def test_dungeon_resume_keeps_roster_and_rng(self):
        run = dungeon.DungeonRun(self.db, 'd01', seed=123)
        run.floor = 7
        run._gen_floor()
        run.eidx = 2
        run.save(56, 31)
        resumed, hp, sta = dungeon.DungeonRun.load_run(self.db)
        self.assertEqual(run._floor_enemies, resumed._floor_enemies)
        self.assertEqual(run.rng.getstate(), resumed.rng.getstate())
        run._gen_floor(); resumed._gen_floor()
        self.assertEqual(run._floor_enemies, resumed._floor_enemies)
        self.assertEqual((hp, sta), (56, 31))

    def test_invalid_checkpoint_is_rejected(self):
        run = dungeon.DungeonRun(self.db, 'd01', seed=1)
        run.save(50, 20)
        data = run._read_save(); data['run']['eidx'] = 999
        run._write_save(data)
        self.assertIsNone(run.load_run(self.db))

    def test_final_boss_loot_callback_and_replay(self):
        window = ArenaWindow(self.pet, diff_id='d10')
        window.timer.stop(); self.windows.append(window)
        stage = window.stage
        stage.drun.floor = stage.drun.floors
        stage.drun.eidx = stage.drun.n_enemies-1
        self.ready(stage)
        self.kill(stage, 1)
        with patch.object(equipment, 'make_item', return_value=self.loot()):
            stage.on_exit()
        self.assertEqual(len(equipment.get_items()), 1)
        self.assertFalse(window.result_box.isHidden())
        self.assertIn('d10', dungeon.DungeonRun.load_cleared())
        window._on_again()
        self.assertEqual(window.stage.drun.diff_id, 'd10')
        self.assertEqual(window.stage.drun.floor, 1)

    def test_exit_during_win_settles_once(self):
        stage = self.stage(); self.ready(stage)
        xp = self.pet.total_xp
        self.kill(stage, 1)
        with patch.object(equipment, 'make_item', return_value=self.loot()):
            stage.on_exit()
            awarded = self.pet.total_xp
            stage.on_exit()
        self.assertGreater(awarded, xp)
        self.assertEqual(self.pet.total_xp, awarded)
        self.assertEqual(len(equipment.get_items()), 1)
        loaded = dungeon.DungeonRun.load_run(self.db)[0]
        self.assertEqual(loaded.eidx, 1)

    def test_loss_retreat_revive_and_checkpoint(self):
        stage = self.stage()
        stage.drun.floor = 3
        self.ready(stage)
        self.kill(stage, 0)
        stage.on_exit()
        self.assertEqual(stage.drun.floor, 2)
        self.assertEqual(stage._frac, [1, 1])
        self.ready(stage)
        self.assertEqual(stage.f[0][0].hp, stage.f[0][0].hp_max)
        self.assertIsNone(stage.fx['ko'])

    def test_equipment_snapshot_updates_next_fight(self):
        stage = self.stage(); self.ready(stage)
        before = stage.f[0][0].atk
        aid = next(k for k,v in self.db.data['装备词条'].items() if v['属性ID']=='atk')
        item = self.loot(); item['affixes'] = [{'id': aid, 'val': 50, 'up': False}]
        equipment.equip(equipment.add_item(self.db, item))
        self.assertEqual(stage.f[0][0].atk, before)
        self.kill(stage, 0); stage.on_exit(); self.ready(stage)
        self.assertEqual(stage.f[0][0].atk, before+50)

    def test_growth_caps_at_configured_level(self):
        self.pet.level = self.db.max_level-1
        self.pet.xp = 0
        self.pet._add_xp(10**8)
        self.assertEqual(self.pet.level, self.db.max_level)
        self.assertLessEqual(self.pet.xp, self.db.exp_need(self.pet.level))
        stats = dict(self.pet.stats)
        self.pet._add_xp(10**8)
        self.assertEqual(self.pet.stats, stats)

    def test_reset_recomputes_level_one_attributes(self):
        self.pet.set_species('c002')
        self.pet.level = 30; self.pet.recompute()
        self.pet._reset()
        self.assertEqual(self.pet.level, 1)
        self.assertEqual(self.pet.species_id, 'c002')
        self.assertEqual(self.pet.stats, self.db.compute('c002', 1, self.pet.talents)[0])

    def test_reset_clears_dungeon_unlocks_and_selection(self):
        from PySide6.QtWidgets import QPushButton
        dungeon.DungeonRun._save_cleared(['d01'])
        run = dungeon.DungeonRun(self.db, 'd02')
        run.floor = 4
        run.save(12, 8)
        self.pet._open_dungeon_select()
        self.pet._reset()
        self.assertIsNone(dungeon.DungeonRun.load_run(self.db))
        self.assertEqual(dungeon.DungeonRun.load_cleared(), [])
        self.assertIsNone(self.pet.dungeon_sel)
        self.pet._open_dungeon_select()
        buttons = self.pet.dungeon_sel.findChildren(QPushButton)
        self.assertFalse(any('继续进度' in b.text() or '已通关' in b.text() for b in buttons))
        difficulties = [b for b in buttons if '敌/层' in b.text()]
        self.assertTrue(difficulties[0].isEnabled())
        self.assertTrue(all(not b.isEnabled() for b in difficulties[1:]))
        self.pet._quick_enter_dungeon()
        self.assertEqual(self.pet._stage.drun.diff_id, 'd01')
        self.assertEqual(self.pet._stage.drun.floor, 1)

    def test_reset_discards_active_and_pending_battles(self):
        self.pet.begin_desktop_battle(diff_id='d01')
        desktop = self.pet._stage
        self.ready(desktop)
        self.kill(desktop, 1)
        self.assertIsNotNone(desktop._pending_end)
        arena = ArenaWindow(self.pet, diff_id='d02')
        self.windows.append(arena)
        self.pet.arena_win = arena
        before_items = equipment.get_items()
        self.pet._reset()
        self.assertIsNone(self.pet._stage)
        self.assertIsNone(self.pet.arena_win)
        self.assertFalse(arena.timer.isActive())
        for stage in (desktop, arena.stage):
            stage.update(100)
            stage.on_exit()
        arena.close()
        self.pet._delayed_exit_battle(desktop)
        self.assertEqual(dungeon.DungeonRun._read_save(), {})
        self.assertEqual((self.pet.level, self.pet.xp, self.pet.total_xp), (1, 0, 0))
        self.assertEqual(equipment.get_items(), before_items)

    def test_atomic_write_failures_are_not_swallowed(self):
        for action in (self.pet.save, self.pet.settings.save,
                       lambda: equipment.save_inventory({'items': {}, 'equipped': {}}),
                       lambda: dungeon.DungeonRun._write_save({})):
            with patch('persistence.os.replace', side_effect=OSError('cannot save')):
                with self.assertRaises(OSError): action()

    def test_zero_drop_and_highest_quality_do_not_lie(self):
        conf = self.db.data['副本难度']['d01']
        conf['装备掉落概率'] = 0
        self.assertEqual(equipment.make_item(self.db, random.Random(1), 'd01'), {})
        conf['装备掉落概率'] = 100
        conf['装备品质权重'] = self.db.data['_装备品质顺序'][-1]+':1'
        with patch.object(equipment, 'UPGRADE_CHANCE', 1):
            item = equipment.make_item(self.db, random.Random(1), 'd01')
        self.assertTrue(item['affixes'])
        self.assertTrue(all(not a['up'] for a in item['affixes']))

    def test_failed_atomic_save_keeps_old_file(self):
        path = self.root/'atomic.json'; write_json(path, {'xp': 42})
        with patch('persistence.os.replace', side_effect=OSError('test failure')):
            with self.assertRaises(OSError): write_json(path, {'xp': 99})
        self.assertEqual(json.loads(path.read_text()), {'xp': 42})
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_conditional_talent_reacts_to_current_hp(self):
        fighter = make_fighter(self.db, 0, 'test', 'c001', 10, ['t007'])
        base = fighter.atk
        self.assertEqual(fighter.effective('atk'), base)
        fighter.hp = fighter.hp_max*.29
        self.assertAlmostEqual(fighter.effective('atk'), base*1.3)
        fighter.hp = fighter.hp_max
        self.assertEqual(fighter.effective('atk'), base)

    def attack_pair(self, toughness=0):
        move = next(copy.deepcopy(v) for v in self.db.data['招式'].values() if v['类型']=='攻击')
        move.update({'命中修正': 100, '暴击修正': 0, '附带状态': None})
        self.db.data['招式'] = {'test': move}
        a = Fighter('a', 0, 1, {'hp': 500, 'atk': 30, 'crit': 100, 'sta': 100})
        b = Fighter('b', 1, 1, {'hp': 500, 'tough': toughness, 'sta': 100})
        return Battle(self.db, a, b, seed=42), a, b

    def test_toughness_reduces_incoming_crit(self):
        battle, a, b = self.attack_pair(100)
        events = []; battle._act(a, events)
        self.assertFalse(next(e for e in events if e['type']=='hit')['crit'])

    def test_lethal_reflection_stops_dead_attacker(self):
        battle, a, b = self.attack_pair()
        a.hp = 1
        b.apply_status('s004', 0, 10)
        events = []; battle._act(a, events)
        self.assertTrue(battle.over)
        self.assertEqual(battle.winner, 1)
        self.assertEqual(b.hp, b.hp_max)
        self.assertEqual(events[-1]['type'], 'end')

    def test_battle_end_is_last_event(self):
        battle, a, b = self.attack_pair()
        b.hp = 1
        for _ in range(100):
            events = battle.step()
            if battle.over:
                self.assertEqual(events[-1]['type'], 'end')
                self.assertEqual(sum(e['type']=='end' for e in events), 1)
                return
        self.fail('No end event')

    def test_full_dungeon_progression_and_exactly_once_rewards(self):
        stage = self.stage()
        callbacks = []
        stage.on_diff_clear = callbacks.append
        fights = 0
        with patch.object(equipment, 'make_item', side_effect=lambda *args: self.loot()):
            while stage.dungeon_result is None and fights < 100:
                self.ready(stage)
                self.kill(stage, 1)
                stage.on_exit()
                fights += 1
        self.assertEqual(fights, stage.drun.floors*stage.drun.n_enemies)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(equipment.get_items()), fights)
        self.assertEqual(stage.drun.total_xp, self.pet.total_xp)
        self.assertIsNone(dungeon.DungeonRun.load_run(self.db))
        self.assertIn('d01', dungeon.DungeonRun.load_cleared())

    def test_real_desktop_battles_render_and_reward(self):
        self.pet.level = 10; self.pet.recompute()
        stage = self.stage()
        random.seed(29)
        image = QImage(660, 440, QImage.Format.Format_ARGB32)
        for i in range(15000):
            stage.update(.1)
            if i % 100 == 0:
                image.fill(0)
                painter = QPainter(image); stage.draw(painter); painter.end()
            if self.pet.total_xp > 0 and stage.drun.kills >= 3:
                break
        self.assertGreaterEqual(stage.drun.kills, 3)
        self.assertGreater(self.pet.total_xp, 0)
        self.assertFalse(image.isNull())


if __name__ == '__main__':
    unittest.main(verbosity=2)
