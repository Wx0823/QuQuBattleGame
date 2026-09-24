"""测试专用存档隔离：不读取/覆盖玩家进度，离开上下文恢复全部路径。"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import equipment
import dungeon
from persistence import write_json


@contextmanager
def isolated_game_data():
    with tempfile.TemporaryDirectory(prefix='ququ-test-') as temporary, ExitStack() as stack:
        root = Path(temporary)
        for module, attribute, filename, data in (
            (equipment, 'INV_PATH', 'inventory.json', {'items': {}, 'equipped': {}, 'next_uid': 1}),
            (dungeon, 'SAVE_PATH', 'dungeon.json', {}),
            (sys.modules.get('main'), 'SAVE_FILE', 'save.json', {}),
            (sys.modules.get('settings'), 'PATH', 'settings.json', {}),
        ):
            if module is None:
                continue
            path = root / filename
            write_json(path, data)
            stack.enter_context(patch.object(module, attribute, str(path)))
        yield root
