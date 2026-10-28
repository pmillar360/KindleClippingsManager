"""Private fixture diagnostics: only counts and structural metadata are printed."""
from pathlib import Path
import sys
import logging

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plugin.vendor.krds import KindleReaderDataStore
from plugin.vendor.kfxlib import YJ_Book, set_logger
from plugin.vendor.kfxlib.ion import unannotated


def main():
    quiet = logging.getLogger('private-fixture')
    quiet.addHandler(logging.NullHandler())
    quiet.propagate = False
    set_logger(quiet)
    kfx = next((ROOT / 'testfiles').glob('*.kfx'))
    yjr = next((ROOT / 'testfiles').rglob('*.yjr'))
    data = KindleReaderDataStore(quiet, yjr.read_bytes()).deserialize()
    cache = data.get('annotation.cache.object', {})
    print('Annotation containers:', {k: len(v) for k, v in cache.items()})
    book = YJ_Book(str(kfx))
    book.decode_book()
    print('Metadata title available:', bool(book.get_yj_metadata_from_book().title))
    chunks = book.collect_content_position_info()
    print('Chunks:', len(chunks), 'text chunks:', sum(c.text is not None for c in chunks))
    print('Text length mismatches:', sum(c.text is not None and len(c.text) != c.length for c in chunks))
    nav = book.fragments.get('$389', first=True)
    print('Navigation root type:', type(nav.value).__name__ if nav else None)
    if nav:
        root = unannotated(nav.value[0])
        print('Navigation entries:', [(type(v).__name__, str(unannotated(v).get('$235')) if hasattr(unannotated(v), 'get') else 'reference') for v in root.get('$392', [])])
    print('Location map entries:', len(book.collect_location_map_info(chunks)))
    print('Annotation fields:', sorted(next(iter(cache.get('annotation.personal.highlight', [])), {}).keys()))


if __name__ == '__main__':
    main()
