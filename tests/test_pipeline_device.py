from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import hashlib
import unittest

from plugin.calibre_adapter import copy_device_sources
from plugin.core.pipeline import Cancelled, scan_folder
from plugin.core.models import Book, Highlight
from plugin.core.storage import Store
from plugin.core.matching import Matcher

CLIPPING = 'Synthetic (Author)\n- Your Highlight at location 1-2 | Added on Wednesday, 28 October 2026 12:30:00\n\nSynthetic passage.\n==========\n'


class DeviceTests(unittest.TestCase):
    def test_mounted_copy_is_read_only_and_pipeline_reimports(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'device'
            documents = source / 'documents'
            documents.mkdir(parents=True)
            (documents / 'My Clippings.txt').write_text(CLIPPING, encoding='utf-8')
            stage = root / 'stage'
            device = SimpleNamespace(is_kindle=True, _main_prefix=str(source))
            before = (documents / 'My Clippings.txt').read_bytes()
            self.assertEqual(copy_device_sources(device, stage), [])
            result = scan_folder(stage)
            store = Store(root / 'state.sqlite')
            try:
                self.assertEqual(store.ingest(result, Matcher())['new'], 1)
                self.assertEqual(store.ingest(scan_folder(stage), Matcher())['new'], 0)
            finally:
                store.close()
            self.assertEqual((documents / 'My Clippings.txt').read_bytes(), before)
            self.assertEqual(len(list(source.rglob('*'))), 2)

    def test_mtp_explicit_sidecar_listing_bypasses_cache_and_uses_no_writes(self):
        class FakeKindle:
            is_kindle = True
            filesystem_cache = SimpleNamespace(entries=['storage'])
            calls = []
            def list_mtp_folder_by_name(self, storage, *parts):
                self.calls.append(('list', parts))
                if not parts:
                    return [{'name': 'documents', 'is_folder': True}]
                if parts == ('documents',):
                    return [{'name': 'My Clippings.txt', 'is_folder': False}, {'name': 'Synthetic.sdr', 'is_folder': True}]
                return [{'name': 'annotations.yjr', 'is_folder': False}]
            def get_mtp_file_by_name(self, storage, *parts, stream):
                self.calls.append(('read', parts))
                stream.write(CLIPPING.encode() if parts[-1].endswith('.txt') else b'synthetic-yjr')
        with TemporaryDirectory() as temporary:
            device = FakeKindle()
            self.assertEqual(copy_device_sources(device, temporary), [])
            self.assertTrue((Path(temporary) / '0/documents/Synthetic.sdr/annotations.yjr').exists())
            self.assertTrue(all(call[0] in ('list', 'read') for call in device.calls))

    def test_corrupted_yjr_does_not_discard_other_sources(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'My Clippings.txt').write_text(CLIPPING, encoding='utf-8')
            (root / 'bad.yjr').write_bytes(b'bad')
            result = scan_folder(root)
            self.assertEqual(len(result.highlights), 1)
            self.assertTrue(any('Corrupt' in w for w in result.warnings))

    def test_cancel_and_unknown_device(self):
        with TemporaryDirectory() as temporary:
            with self.assertRaises(Cancelled):
                scan_folder(temporary, cancelled=lambda: True)
            with self.assertRaises(ValueError):
                copy_device_sources(SimpleNamespace(), temporary)


if __name__ == '__main__':
    unittest.main()
