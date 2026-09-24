"""品种持久化回归；全部使用临时存档，不启动输入钩子或托盘。"""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
import main
import settings


class SpeciesPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.save_path = Path(self.temp.name) / 'save.json'
        self.settings_path = Path(self.temp.name) / 'settings.json'
        self.patches = [patch.object(main, 'SAVE_FILE', str(self.save_path)),
                        patch.object(settings, 'PATH', str(self.settings_path)),
                        patch.object(main.Pet, '_init_hook'), patch.object(main.Pet, '_init_tray')]
        for p in self.patches:
            p.start()
        self.pets = []

    def tearDown(self):
        for pet in self.pets:
            pet.panel.close()
            pet.settings_panel.close()
            pet.close()
            pet.deleteLater()
        self.app.processEvents()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def write(self, path, data):
        path.write_text(json.dumps(data), encoding='utf-8')

    def pet(self):
        pet = main.Pet()
        pet.timer.stop()
        self.pets.append(pet)
        return pet

    def assert_species(self, pet, sid):
        self.assertEqual(pet.species_id, sid)
        self.assertEqual(pet.palette['species_id'], sid)
        self.assertEqual(pet.settings.species_id, sid)
        self.assertEqual(pet.settings_panel.combo.currentData(), sid)

    def test_saved_species_wins_over_stale_settings(self):
        self.write(self.save_path, {'species_id': 'c002', 'level': 3, 'xp': 108, 'total_xp': 238})
        self.write(self.settings_path, {'species_id': 'c003', 'zoom': 1.14})
        pet = self.pet()
        self.assert_species(pet, 'c002')
        self.assertEqual((pet.level, pet.xp, pet.total_xp), (3, 108, 238))
        self.assertAlmostEqual(pet.zoom, 1.14)
        self.assertEqual(json.loads(self.settings_path.read_text())['species_id'], 'c002')

    def test_ui_switch_is_saved_immediately_and_survives_restart(self):
        self.write(self.save_path, {'species_id': 'c003', 'level': 22, 'xp': 598})
        pet = self.pet()
        combo = pet.settings_panel.combo
        combo.setCurrentIndex(combo.findData('c002'))
        self.assert_species(pet, 'c002')
        for path in (self.save_path, self.settings_path):
            self.assertEqual(json.loads(path.read_text())['species_id'], 'c002')
        pet.close()
        restarted = self.pet()
        self.assert_species(restarted, 'c002')
        self.assertEqual((restarted.level, restarted.xp), (22, 598))

    def test_legacy_save_without_species_uses_settings(self):
        self.write(self.save_path, {'level': 8, 'xp': 17})
        self.write(self.settings_path, {'species_id': 'c005'})
        self.assert_species(self.pet(), 'c005')

    def test_programmatic_change_syncs_panel_without_recursive_writes(self):
        pet = self.pet()
        with patch.object(pet, 'save', wraps=pet.save) as save:
            pet.set_species('c004')
            save.assert_called_once()
        self.assert_species(pet, 'c004')
        pet.set_species('missing')
        self.assert_species(pet, 'c004')


if __name__ == '__main__':
    unittest.main(verbosity=2)
