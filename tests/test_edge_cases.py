from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import struct
import unittest
from unittest.mock import patch

from plugin.core.models import Book, Highlight, ImportBatch, SyncDestination
from plugin.core.matching import Matcher
from plugin.core.storage import Store
from plugin.core.sync import SyncEngine, validate_destination
from plugin.importers.clippings import parse
from plugin.importers.recovery import decode_yjr, RecoveryError


def integer(value):
    return b'\x01' + struct.pack('>i', value)


def long(value):
    return b'\x02' + struct.pack('>q', value)


def string(value, typed=True):
    value = value.encode('utf-8')
    return (b'\x03' if typed else b'') + b'\x00' + struct.pack('>H', len(value)) + value


def obj(name, values):
    return b'\xfe' + string(name, typed=False) + b''.join(values) + b'\xff'


class EdgeTests(unittest.TestCase):
    def test_missing_positions_preserve_ambiguous_occurrences(self):
        text = 'Synthetic (Author)\n- Your Highlight on page 12 | Added on October 28, 2026 12:30:00 PM\n\nSame text\n==========\n'
        batch = parse(text + text)
        self.assertEqual(batch.highlights[0].created_at, '2026-10-28T12:30:00')
        self.assertNotEqual(batch.highlights[0].id, batch.highlights[1].id)
        with TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / 'state.sqlite')
            try:
                self.assertEqual(store.ingest(batch, Matcher())['new'], 2)
                self.assertEqual(store.ingest(batch, Matcher())['new'], 0)
            finally:
                store.close()

    def test_synthetic_yjr_decoding(self):
        annotation = obj('annotation.personal.highlight', [string('start:0'), string('end:5'), long(1_700_000_000_000), long(1_700_000_000_000), string('synthetic')])
        tree = obj('saved.avl.interval.tree', [integer(1), annotation])
        cache = obj('annotation.cache.object', [integer(1), integer(1), tree])
        binary = b'\x00\x00\x00\x00\x00\x1a\xb1\x26' + integer(1) + integer(1) + cache
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'synthetic.yjr'
            path.write_bytes(binary)
            result = decode_yjr(path)
            self.assertEqual(result['annotation.personal.highlight'][0]['endPosition'], 'end:5')
            self.assertEqual(path.read_bytes(), binary)
            path.write_bytes(binary[:20])
            with self.assertRaises(RecoveryError):
                decode_yjr(path)

    def test_clipping_limit_recovery_requires_validated_location_map(self):
        book = Book('Synthetic', ['Author'])
        clipping = [Highlight(book.id, 'One', location_start=10, location_end=11),
                    Highlight(book.id, 'Two', location_start=20, location_end=21),
                    Highlight(book.id, '', location_start=30, location_end=31, needs_recovery=True)]
        recovered = [Highlight(book.id, text, id=f'kfx-{i}', source='yjr', source_id=str(i),
                               position_start=i * 100, position_end=i * 100 + 5, position_system='kfx:synthetic',
                               mapped_location_start=i * 10, mapped_location_end=i * 10 + 1)
                     for i, text in enumerate(['One', 'Two', 'Recovered'], 1)]
        with TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / 'state.sqlite')
            try:
                stats = store.ingest(ImportBatch([book], clipping + recovered), Matcher())
                self.assertEqual(stats['new'], 3)
                self.assertEqual(len(store.highlights()), 3)
                self.assertTrue(all(not h.needs_recovery for h in store.highlights()))
                self.assertEqual(store.ingest(ImportBatch([book], clipping + recovered), Matcher())['new'], 0)
            finally:
                store.close()

    def test_unverified_location_map_does_not_merge_placeholder(self):
        book = Book('Synthetic')
        a = Highlight(book.id, '', location_start=30, needs_recovery=True)
        b = Highlight(book.id, 'Recovered', position_start=500, position_end=510, position_system='kfx:one',
                      mapped_location_start=30, source='yjr')
        self.assertFalse(Store.same_annotation(a, b))

    def test_timestamp_precision_does_not_duplicate_cross_source(self):
        a = Highlight('book', 'Same passage', location_start=1, created_at='2026-10-28T12:00:00')
        b = Highlight('book', 'Same passage', position_start=500, position_system='kfx:one', source='yjr', created_at='2026-10-28T12:00:00.123000')
        self.assertTrue(Store.same_annotation(a, b))

    def test_future_schema_is_rejected(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'state.sqlite'
            connection = sqlite3.connect(path)
            connection.execute('PRAGMA user_version=99')
            connection.close()
            with self.assertRaises(ValueError):
                Store(path)

    def test_crlf_commentary_and_user_frontmatter_stay_intact(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = Store(root / 'state.sqlite')
            try:
                book = Book('Synthetic')
                h = Highlight(book.id, 'First', location_start=1)
                store.ingest(ImportBatch([book], [h]), Matcher())
                engine = SyncEngine(store, SyncDestination(str(root), 'notes'))
                plan = engine.plan()
                engine.apply(plan)
                path = Path(plan[0].path)
                text = path.read_bytes().decode('utf-8').replace('tags: ', 'my_property: "personal"\ntags: ') + '\nPersonal commentary\n'
                path.write_bytes(text.replace('\n', '\r\n').encode('utf-8'))
                store.ingest(ImportBatch([book], [Highlight(book.id, 'Second', location_start=10)]), Matcher())
                self.assertEqual(engine.apply(engine.plan())['updated'], 1)
                content = path.read_bytes()
                self.assertIn(b'my_property: "personal"\r\n', content)
                self.assertIn(b'\r\nPersonal commentary\r\n', content)
                self.assertNotIn(b'\n', content.replace(b'\r\n', b''))
            finally:
                store.close()

    def test_unreadable_book_does_not_stop_other_books(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = Store(root / 'state.sqlite')
            try:
                books = [Book('One'), Book('Two')]
                store.ingest(ImportBatch(books, [Highlight(b.id, 'Text', location_start=1) for b in books]), Matcher())
                engine = SyncEngine(store, SyncDestination(str(root), 'notes'))
                engine.apply(engine.plan())
                target = Path(engine.plan()[0].path)
                original = Path.read_bytes
                def read(path):
                    if path == target:
                        raise PermissionError()
                    return original(path)
                with patch.object(Path, 'read_bytes', read):
                    actions = [c.action for c in engine.plan()]
                self.assertEqual(sorted(actions), ['conflict', 'unchanged'])
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
