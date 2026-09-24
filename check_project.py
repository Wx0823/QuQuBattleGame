"""一键语法检查 + 全部自动回归。测试脚本各自隔离存档。"""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CHECKS = ('battle_checklist.py', 'gameplay_checklist.py', 'species_checklist.py',
          'equipment_ui_checklist.py', 'art_checklist.py')


def main():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sources = list(ROOT.glob('*.py'))
    for path in sources:
        compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec')
    results = [f'Syntax: {len(sources)} Python files PASS']
    failed = []
    for name in CHECKS:
        print(f'Running {name}', flush=True)
        result = subprocess.run([sys.executable, '-u', str(ROOT/name)], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8')
        output = result.stdout + result.stderr
        results.append(f'\n=== {name} (exit {result.returncode}) ===\n{output}')
        print(output, end='')
        if result.returncode:
            failed.append(name)
    (ROOT/'docs'/'validation_results.txt').write_text('\n'.join(results), encoding='utf-8')
    print('FAILED: '+', '.join(failed) if failed else 'ALL CHECKS PASS')
    return bool(failed)


if __name__ == '__main__':
    sys.exit(main())
