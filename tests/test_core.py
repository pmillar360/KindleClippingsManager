from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest
from unittest.mock import patch

from plugin.core.models import Book, Highlight, ImportBatch, SyncDestination
from plugin.core.matching import Matcher, canonical
from plugin.core.storage import Store
from plugin.core.markdown import MarkdownOptions, render
from plugin.core.sync import SyncEngine, safe_filename, validate_destination
from plugin.importers.clippings import parse, parse_date, serialize


def clipping(text='A synthetic passage.', location='10-12', kind='Highlight', title='Example', author='Author'):
    return f'{title} ({author})\n- Your {kind} on page 3 | location {location} | Added on Wednesday, 28 October 2026 12:30:00\n\n{text}\n==========\n'


class ParserTests(unittest.TestCase):
    def test_multilingual_dates_and_invalid_dates(self):
        for month, index in [('March', 3), ('März', 3), ('février', 2), ('ottobre', 10), ('outubro', 10), ('oktober', 10)]:
            self.assertEqual(parse_date(f'Wednesday, 1 {month} 2026 12:30:00'), f'2026-{index:02d}-01T12:30:00')
        self.assertIsNone(parse_date('Wednesday, 31 February 2026 12:30:00'))
        self.assertEqual(parse_date('October 28, 2026 12:30:00 AM'), '2026-10-28T00:30:00')

    def test_bom_crlf_paragraphs_and_stable_identity(self):
        text = clipping('First.\n\nSecond.')
        first = parse('\ufeff' + text.replace('\n', '\r\n'))
        second = parse(clipping('Earlier.', '1-2') + text)
        self.assertEqual(first.highlights[0].id, second.highlights[1].id)
        self.assertEqual(first.highlights[0].text, 'First.\n\nSecond.')

    def test_notes_bookmarks_unknowns_and_placeholders(self):
        result = parse(clipping('Personal thought', kind='Note') + clipping('', kind='Bookmark') + clipping('<You have reached the clipping limit for this item>') + 'broken\n==========')
        self.assertEqual([h.kind for h in result.highlights], ['note', 'bookmark', 'highlight'])
        self.assertTrue(result.highlights[2].needs_recovery)
        self.assertEqual(result.highlights[2].text, '')
        self.assertTrue(result.warnings)
        legitimate = parse(clipping('A real passage discussing the clipping limit of an audio signal.'))
        self.assertFalse(legitimate.highlights[0].needs_recovery)

    def test_page_only_has_no_fabricated_location(self):
        result = parse('Book\n- Your Highlight on page 12 | Added on Wednesday, 28 October 2026 12:30:00\n\nText\n==========')
        self.assertIsNone(result.highlights[0].location_start)
        self.assertEqual(result.highlights[0].page, '12')

    def test_roundtrip_order_and_german_raw_metadata(self):
        text = clipping('Later', '20-21') + clipping('Earlier', '1-2')
        result = parse(text)
        self.assertEqual(serialize(result.books, result.highlights), text)
        german = 'Book (Autor)\n- Deine Markierung bei Position 5-6 | Hinzugefügt am Montag, 2. März 2026 04:22:09\n\nText\n==========\n'
        result = parse(german)
        self.assertEqual(serialize(result.books, result.highlights), german)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.sqlite'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_repeated_imports_persistent_exclusions_and_edits(self):
        batch = parse(clipping())
        self.assertEqual(self.store.ingest(batch, Matcher())['new'], 1)
        h = self.store.highlights()[0]
        self.store.exclude('highlight', h.id)
        self.store.exclude('book', h.book_id)
        self.store.edit(h.id, 'Edited locally')
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.ingest(parse(clipping()), Matcher())['new'], 0)
        h = self.store.highlights()[0]
        self.assertTrue(h.excluded)
        self.assertEqual(h.text, 'Edited locally')
        self.assertTrue(self.store.excluded('book', h.book_id))

    def test_same_text_different_positions_is_not_duplicate(self):
        result = self.store.ingest(parse(clipping() + clipping(location='20-22')), Matcher())
        self.assertEqual(result['new'], 2)

    def test_cross_source_reconciliation_needs_corroboration(self):
        batch = parse(clipping())
        self.store.ingest(batch, Matcher())
        h = replace(batch.highlights[0], id='recovery', source='yjr', source_id='recovery-1', location_start=None, location_end=None,
                    position_start=100, position_end=120, position_system='kfx:one')
        stats = self.store.ingest(ImportBatch(batch.books, [h]), Matcher())
        self.assertEqual(stats['new'], 0)
        self.assertEqual(len(self.store.provenance(self.store.highlights()[0].id)), 2)
        h = replace(h, id='different', source_id='recovery-2', created_at=None, position_start=200)
        self.assertEqual(self.store.ingest(ImportBatch(batch.books, [h]), Matcher())['new'], 1)

    def test_late_calibre_matching_preserves_id_exclusion_and_note_path(self):
        batch = parse(clipping())
        self.store.ingest(batch, Matcher())
        before = self.store.highlights()[0]
        self.store.exclude('highlight', before.id)
        self.store.exclude('book', before.book_id)
        book = canonical(Book('Example', ['Author'], calibre_id=7), 'library-a')
        self.store.ingest(batch, Matcher([book]))
        after = self.store.highlights()[0]
        self.assertEqual(after.book_id, book.id)
        self.assertEqual(after.id, before.id)
        self.assertTrue(after.excluded)
        self.assertTrue(self.store.excluded('book', book.id))
        self.store.ingest(batch, Matcher())
        self.assertEqual(self.store.books()[0].id, book.id)

    def test_library_ids_and_editions_are_distinct(self):
        a = canonical(Book('Example', ['Author'], calibre_id=1), 'a')
        b = canonical(Book('Example', ['Author'], calibre_id=1), 'b')
        self.assertNotEqual(a.id, b.id)
        source = Book('Example', ['Author'])
        matched, warning = Matcher([a, b]).match(source)
        self.assertEqual(matched, source)
        self.assertTrue(warning)

    def test_epub_only_record_and_identifiers(self):
        library = canonical(Book('Other title', ['Author'], calibre_id=1, identifiers={'isbn': '123-456'}, formats=[{'format': 'EPUB'}]), 'library')
        matched, warning = Matcher([library]).match(Book('Example', ['Author'], identifiers={'isbn': '123456'}))
        self.assertEqual(matched.id, library.id)
        self.assertIsNone(warning)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state.sqlite')
        self.batch = parse(clipping())
        self.store.ingest(self.batch, Matcher())
        self.engine = SyncEngine(self.store, SyncDestination(str(self.root), 'Highlights'))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def initial(self):
        changes = self.engine.plan()
        self.assertEqual(self.engine.apply(changes)['created'], 1)
        return Path(changes[0].path)

    def test_incremental_preserves_commentary_exclusions_and_backups(self):
        path = self.initial()
        path.write_bytes(path.read_bytes() + b'\nMy own commentary.\n')
        self.store.ingest(parse(clipping('New passage', '20-22')), Matcher())
        plan = self.engine.plan()
        self.assertEqual(plan[0].action, 'update')
        self.assertEqual(self.engine.apply(plan)['updated'], 1)
        self.assertIn('My own commentary.', path.read_text(encoding='utf-8'))
        self.assertEqual(len(list((path.parent / '.kindle-highlights-backups').glob('*.md'))), 1)
        self.assertEqual(self.engine.plan()[0].action, 'unchanged')
        self.store.exclude('highlight', self.store.highlights()[0].id)
        self.engine.apply(self.engine.plan())
        self.assertNotIn('A synthetic passage.', path.read_text(encoding='utf-8'))
        self.store.exclude('book', self.batch.books[0].id)
        self.assertEqual(self.engine.plan(), [])
        self.assertTrue(path.exists())

    def test_user_edit_inside_markers_is_conflict(self):
        path = self.initial()
        path.write_text(path.read_text(encoding='utf-8').replace('A synthetic passage.', 'User revision.'), encoding='utf-8')
        before = path.read_bytes()
        self.assertEqual(self.engine.apply(self.engine.plan())['conflicts'], 1)
        self.assertEqual(path.read_bytes(), before)

    def test_unrelated_file_collision_and_filename_safety(self):
        folder = self.root / 'Highlights'
        folder.mkdir()
        unrelated = folder / 'Example.md'
        unrelated.write_text('User note', encoding='utf-8')
        plan = self.engine.plan()
        self.assertNotEqual(plan[0].path, str(unrelated))
        self.engine.apply(plan)
        self.assertEqual(unrelated.read_text(encoding='utf-8'), 'User note')
        self.assertEqual(safe_filename('CON'), '_CON')
        self.assertNotIn('/', safe_filename('../../evil'))
        for folder in ('../outside', 'C:\\outside', '/outside', 'invalid:folder'):
            with self.assertRaises(ValueError):
                validate_destination(SyncDestination(str(self.root), folder))

    def test_preview_race_does_not_overwrite(self):
        path = self.initial()
        self.store.ingest(parse(clipping('New', '30-31')), Matcher())
        plan = self.engine.plan()
        path.write_bytes(path.read_bytes() + b'User edit after preview')
        before = path.read_bytes()
        self.assertEqual(self.engine.apply(plan)['errors'], 1)
        self.assertEqual(path.read_bytes(), before)

    def test_failed_replace_keeps_note_and_retry_works(self):
        path = self.initial()
        before = path.read_bytes()
        self.store.ingest(parse(clipping('New', '30-31')), Matcher())
        with patch('plugin.core.sync.os.replace', side_effect=PermissionError):
            self.assertEqual(self.engine.apply(self.engine.plan())['errors'], 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.engine.apply(self.engine.plan())['updated'], 1)

    def test_journal_recovers_write_before_database_commit(self):
        plan = self.engine.plan()
        real_record = self.engine._record
        with patch.object(self.engine, '_record', side_effect=sqlite3.OperationalError):
            self.assertEqual(self.engine.apply(plan)['errors'], 1)
        self.assertTrue(Path(plan[0].path).exists())
        self.assertIsNone(self.engine.state(plan[0].book_id))
        self.engine._record = real_record
        self.assertEqual(self.engine.plan()[0].action, 'unchanged')
        self.assertIsNotNone(self.engine.state(plan[0].book_id))

    def test_cancel_before_writes(self):
        plan = self.engine.plan()
        self.assertTrue(self.engine.apply(plan, cancelled=lambda: True)['cancelled'])
        self.assertFalse(Path(plan[0].path).exists())

    def test_yaml_escaping_paragraphs_and_no_placeholder_export(self):
        book = Book('Title: "quoted"\nother', ['A: B'])
        h = Highlight(book.id, 'One\n\nTwo', id='one')
        a = render(book, [h])
        b = render(book, [replace(h, source='yjr')])
        self.assertEqual(a, b)
        self.assertIn('> One\n>\n> Two', a)
        from plugin.core.markdown import frontmatter
        fm = frontmatter(book, MarkdownOptions())
        self.assertEqual(json.loads(fm.splitlines()[1].split(': ', 1)[1]), book.title)
        self.assertNotIn('One', render(book, [replace(h, needs_recovery=True)]))
        note = replace(h, text='Personal thought', kind='note')
        self.assertIn('Personal thought', render(book, [note]))
        self.assertNotIn('Personal thought', render(book, [note], MarkdownOptions(notes=False)))


if __name__ == '__main__':
    unittest.main()
