"""Compare recovered passages against existing clippings without printing text."""
from pathlib import Path
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plugin.importers.recovery import decode_yjr, recover
from plugin.importers.clippings import read
from plugin.core.models import text_key


def main():
    root = ROOT / 'testfiles'
    kfx = next(root.glob('*.kfx'))
    yjr = next(root.rglob('*.yjr'))
    batch = recover(kfx, decode_yjr(yjr), str(yjr))
    clipped = [h for path in root.glob('*.txt') for h in read(path).highlights if h.kind == 'highlight' and h.text and not h.needs_recovery]
    exact, overlap, different = 0, 0, 0
    for h in batch.highlights:
        matches = [c for c in clipped if c.created_at and c.created_at == h.created_at]
        if matches:
            if any(text_key(c.text) == text_key(h.text) for c in matches):
                exact += 1
            elif any(text_key(c.text) in text_key(h.text) or text_key(h.text) in text_key(c.text) for c in matches):
                overlap += 1
            else:
                different += 1
    print({'recovered': len(batch.highlights), 'nonempty': sum(bool(h.text) for h in batch.highlights),
           'chapters': sum(bool(h.chapter) for h in batch.highlights),
           'timestamp_text_exact': exact, 'timestamp_text_overlap': overlap, 'timestamp_text_different': different})


if __name__ == '__main__':
    main()
