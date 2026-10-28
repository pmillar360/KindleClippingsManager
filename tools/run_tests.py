"""Run with Python 3.10+ or calibre-debug tools/run_tests.py."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT / 'tests')))
    raise SystemExit(not result.wasSuccessful())
