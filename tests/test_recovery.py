from pathlib import Path
import os
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from plugin.importers.recovery import RecoveryError, TextSpan, decode_yjr, extract_text


class RecoveryTests(unittest.TestCase):
    def test_navigation_unwraps_inline_annotations_and_references(self):
        from plugin.importers.recovery import navigation
        from plugin.vendor.kfxlib.ion import IonAnnotation, IS
        entry = {'$246': {'$155': 1, '$143': 5}, '$241': {'$244': 'Synthetic chapter'}}
        container = IonAnnotation([IS('$391')], {'$235': IS('$212'), '$247': [IonAnnotation([IS('$393')], entry)]})
        nav = SimpleNamespace(value=[{'$392': [container]}])
        book = SimpleNamespace(fragments=SimpleNamespace(get=lambda *args, **kwargs: nav),
                               pid_for_eid=lambda eid, offset, chunks: 100 + offset)
        pages, toc = navigation(book, [])
        self.assertEqual(pages, [])
        self.assertEqual(toc, [(105, 'Synthetic chapter', 0)])
        referenced = SimpleNamespace(value={'$235': IS('$237'), '$247': [entry]})
        # A real fragment instance is required for reference unwrapping.
        from plugin.vendor.kfxlib.yj_container import YJFragment
        referenced = YJFragment(ftype='$391', fid=IS('pages'), value={'$235': IS('$237'), '$247': [entry]})
        nav.value = [{'$392': [IS('pages')]}]
        book.fragments.get = lambda *args, **kwargs: referenced if kwargs.get('fid') else nav
        self.assertEqual(navigation(book, [])[0], [(105, 'Synthetic chapter', 0)])

    def test_drm_is_rejected_even_for_metadata_container(self):
        from plugin.importers.recovery import recover
        with TemporaryDirectory() as temporary:
            for filename in ('book.kfx', 'metadata.kfx'):
                path = Path(temporary) / filename
                data = b'\xeaDRMION\xee' + b'private-synthetic-encrypted-data'
                path.write_bytes(data)
                with self.assertRaisesRegex(RecoveryError, 'DRM-protected'):
                    recover(path, {})
                self.assertEqual(path.read_bytes(), data)

    def test_inclusive_boundaries_single_character_and_unicode(self):
        spans = [TextSpan(0, 'Aé😀BC'), TextSpan(7, 'Second paragraph')]
        self.assertEqual(extract_text(spans, 2, 2), '😀')
        self.assertEqual(extract_text(spans, 1, 3), 'é😀B')
        self.assertEqual(extract_text(spans, 3, 9), 'BC\n\nSec')
        with self.assertRaises(RecoveryError):
            extract_text(spans, 6, 9)

    @unittest.skipUnless(os.environ.get('KHS_PRIVATE_TESTS') == '1', 'Opt-in private KFX/YJR fixture')
    def test_private_275_highlights_with_navigation(self):
        from plugin.importers.recovery import recover
        root = Path(__file__).resolve().parents[1] / 'testfiles'
        kfx = next(root.glob('*.kfx'))
        yjr = next(root.rglob('*.yjr'))
        before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
        result = recover(kfx, decode_yjr(yjr), str(yjr))
        highlights = [h for h in result.highlights if h.kind == 'highlight']
        self.assertEqual(len(highlights), 275)
        self.assertTrue(all(h.text.strip() for h in highlights))
        self.assertTrue(any(h.chapter for h in highlights))
        self.assertFalse(result.warnings, result.warnings)
        from plugin.core.pipeline import scan_folder
        from plugin.core.storage import Store
        from plugin.core.matching import Matcher
        with TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / 'state.sqlite')
            try:
                batch = scan_folder(root)
                first = store.ingest(batch, Matcher())
                self.assertGreaterEqual(first['new'], 275)
                self.assertEqual(store.ingest(batch, Matcher())['new'], 0)
            finally:
                store.close()
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual({p for p in root.rglob('*') if p.is_file()}, set(before))


if __name__ == '__main__':
    unittest.main()
