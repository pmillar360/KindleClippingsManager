from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from plugin.core.markdown import MarkdownOptions, frontmatter, render
from plugin.core.matching import Matcher, canonical
from plugin.core.models import Book, Highlight, ImportBatch, SyncDestination
from plugin.core.storage import Store
from plugin.core.sync import SyncEngine


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state.sqlite')
        self.book = Book('Example', ['Author'])
        self.first = Highlight(self.book.id, 'First passage', location_start=10, location_end=12, chapter='One')
        self.last = Highlight(self.book.id, 'Last passage', location_start=90, location_end=92, chapter='Two')
        self.ingest(self.first, self.last)
        self.engine = SyncEngine(self.store, SyncDestination(str(self.root), 'notes'))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def ingest(self, *highlights):
        return self.store.ingest(ImportBatch([self.book], list(highlights)), Matcher())

    def initial(self):
        plan = self.engine.plan()
        self.assertEqual(self.engine.apply(plan)['created'], 1)
        return Path(plan[0].path)

    def test_middle_insertion_preserves_edit_and_noop_bytes_mtime_backups(self):
        path = self.initial()
        path.write_text(path.read_text(encoding='utf-8').replace('First passage', 'My edited passage'), encoding='utf-8')
        self.ingest(Highlight(self.book.id, 'Middle passage', location_start=50, location_end=52, chapter='One'))
        self.assertEqual(self.engine.apply(self.engine.plan())['updated'], 1)
        content = path.read_text(encoding='utf-8')
        self.assertLess(content.index('My edited passage'), content.index('Middle passage'))
        self.assertLess(content.index('Middle passage'), content.index('Last passage'))
        self.assertIn('### Highlight 3\n\n> Last passage', content)
        before, timestamp = path.read_bytes(), path.stat().st_mtime_ns
        backups = list((self.root / 'notes/.kindle-highlights-backups').glob('*.md'))
        for _ in range(2):
            self.assertEqual(self.engine.apply(self.engine.plan())['unchanged'], 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, timestamp)
        self.assertEqual(list((self.root / 'notes/.kindle-highlights-backups').glob('*.md')), backups)

    def test_hidden_positions_still_sort_by_book_location(self):
        self.engine.options = MarkdownOptions(positions=False)
        path = self.initial()
        self.ingest(Highlight(self.book.id, 'Middle', location_start=50))
        self.engine.apply(self.engine.plan())
        text = path.read_text(encoding='utf-8')
        self.assertLess(text.index('First passage'), text.index('Middle'))
        self.assertLess(text.index('Middle'), text.index('Last passage'))

    def test_concurrent_source_and_manual_change_is_conflict(self):
        path = self.initial()
        path.write_text(path.read_text(encoding='utf-8').replace('First passage', 'My edit'), encoding='utf-8')
        self.store.edit(self.first.id, 'Different plugin edit')
        before = path.read_bytes()
        self.assertEqual(self.engine.apply(self.engine.plan())['conflicts'], 1)
        self.assertEqual(path.read_bytes(), before)

    def test_user_deleted_block_stays_deleted_on_repeated_export(self):
        path = self.initial()
        text = path.read_text(encoding='utf-8')
        start, end = text.index('<!-- khs:' + self.first.id), text.index('<!-- khs:' + self.last.id)
        path.write_text(text[:start] + text[end:], encoding='utf-8')
        self.engine.apply(self.engine.plan())
        self.engine.apply(self.engine.plan())
        self.assertNotIn('First passage', path.read_text(encoding='utf-8'))

    def test_custom_filename_and_author_folder_sanitized(self):
        self.engine = SyncEngine(self.store, SyncDestination(str(self.root), 'notes', '{author} - {title}', True))
        path = self.initial()
        self.assertEqual(path.relative_to(self.root).as_posix(), 'notes/Author/Author - Example.md')
        self.engine = SyncEngine(self.store, SyncDestination(str(self.root), 'notes', '{title}', False))
        self.assertEqual(self.engine.plan()[0].path, str(path))

    def test_adopt_existing_note_without_state(self):
        folder = self.root / 'notes'
        folder.mkdir()
        path = folder / 'Example.md'
        path.write_text(frontmatter(self.book, MarkdownOptions()) + render(self.book, [self.first]) + '\nPersonal notes\n', encoding='utf-8')
        plan = self.engine.plan()
        self.assertEqual(plan[0].path, str(path))
        self.assertEqual(self.engine.apply(plan)['updated'], 1)
        self.assertIn('Personal notes', path.read_text(encoding='utf-8'))
        self.assertEqual(len(list(folder.glob('*.md'))), 1)
        self.assertEqual(self.engine.plan()[0].action, 'unchanged')

    def duplicate(self, highlights=None, comment='Personal duplicate commentary'):
        path = self.root / 'notes/Example [fh4b55f].md'
        path.write_text(frontmatter(self.book, MarkdownOptions()) + render(self.book, highlights or [self.first]) + '\n' + comment + '\n', encoding='utf-8')
        return path

    def test_duplicate_notes_merge_unique_highlights_and_archive_original(self):
        path = self.initial()
        historical = Highlight(self.book.id, 'Historical middle', location_start=40, location_end=42)
        duplicate = self.duplicate([replace(self.first, id='historic-first'), historical])
        original = duplicate.read_bytes()
        plan = self.engine.plan()
        self.assertEqual(len(plan[0].duplicates), 1)
        self.assertEqual(self.engine.apply(plan)['updated'], 1)
        text = path.read_text(encoding='utf-8')
        self.assertEqual(text.count('> First passage'), 1)
        self.assertIn('Personal duplicate commentary', text)
        self.assertLess(text.index('Historical middle'), text.index('Last passage'))
        self.assertFalse(duplicate.exists())
        archives = list((self.root / 'notes/.kindle-highlights-backups/merged').glob('*.md'))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), original)
        before = path.read_bytes()
        self.assertEqual(self.engine.apply(self.engine.plan())['unchanged'], 1)
        self.assertEqual(path.read_bytes(), before)

    def test_duplicate_changed_after_preview_preserves_all_files(self):
        path = self.initial()
        duplicate = self.duplicate()
        before = path.read_bytes()
        plan = self.engine.plan()
        duplicate.write_bytes(duplicate.read_bytes() + b'New edit')
        self.assertEqual(self.engine.apply(plan)['errors'], 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(duplicate.exists())

    def test_interrupted_duplicate_archival_retries_without_losing_commentary(self):
        path = self.initial()
        duplicate = self.duplicate([self.first, Highlight(self.book.id, 'Historical middle', location_start=40)])
        real_replace = __import__('os').replace
        def replace_file(source, target):
            if Path(source) == duplicate:
                raise PermissionError()
            return real_replace(source, target)
        with patch('plugin.core.sync.os.replace', side_effect=replace_file):
            self.assertEqual(self.engine.apply(self.engine.plan())['errors'], 1)
        self.assertTrue(duplicate.exists())
        self.assertIn('Historical middle', path.read_text(encoding='utf-8'))
        self.assertEqual(self.engine.apply(self.engine.plan())['updated'], 1)
        text = path.read_text(encoding='utf-8')
        self.assertEqual(text.count('Personal duplicate commentary'), 1)
        self.assertFalse(duplicate.exists())
        self.assertEqual(self.engine.plan()[0].action, 'unchanged')

    def test_historical_middle_order_survives_hidden_position_setting(self):
        path = self.initial()
        self.duplicate([Highlight(self.book.id, 'Historical middle', location_start=40)])
        self.engine.options = MarkdownOptions(positions=False)
        self.assertEqual(self.engine.apply(self.engine.plan())['updated'], 1)
        text = path.read_text(encoding='utf-8')
        self.assertLess(text.index('First passage'), text.index('Historical middle'))
        self.assertLess(text.index('Historical middle'), text.index('Last passage'))
        self.assertEqual(self.engine.plan()[0].action, 'unchanged')

    def test_compact_same_text_on_different_locations_not_collapsed(self):
        self.engine.options = MarkdownOptions(compact=True)
        first = replace(self.first, text='Same words', page='1')
        self.store.edit(self.first.id, 'Same words')
        path = self.initial()
        self.duplicate([replace(first, id='different', location_start=50, location_end=52)])
        self.engine.apply(self.engine.plan())
        self.assertEqual(path.read_text(encoding='utf-8').count('> Same words'), 2)

    def test_duplicate_conflicting_edit_preserves_both(self):
        path = self.initial()
        duplicate = self.duplicate([replace(self.first, text='Conflicting edit')])
        before = path.read_bytes(), duplicate.read_bytes()
        self.assertEqual(self.engine.apply(self.engine.plan())['conflicts'], 1)
        self.assertEqual((path.read_bytes(), duplicate.read_bytes()), before)

    def test_historical_duplicate_with_trailing_personal_comment_is_preserved(self):
        path = self.initial()
        duplicate = self.duplicate([replace(self.first, id='historical')])
        duplicate.write_text(duplicate.read_text(encoding='utf-8').replace('<!-- kindle-highlights-sync:end -->',
                             'My comment inside a historical block\n\n<!-- kindle-highlights-sync:end -->'), encoding='utf-8')
        self.assertEqual(self.engine.apply(self.engine.plan())['updated'], 1)
        self.assertIn('My comment inside a historical block', path.read_text(encoding='utf-8'))

    def test_orphaned_suffix_note_is_reused(self):
        folder = self.root / 'notes'
        folder.mkdir()
        duplicate = self.duplicate()
        plan = self.engine.plan()
        self.assertEqual(plan[0].path, str(duplicate))
        self.assertEqual(self.engine.apply(plan)['updated'], 1)
        self.assertEqual(len(list(folder.glob('*.md'))), 1)

    def test_chapter_grouping_and_compact_metadata_stable(self):
        self.engine.options = MarkdownOptions(compact=True, group_chapters=True)
        path = self.initial()
        self.ingest(Highlight(self.book.id, 'Middle', location_start=50, chapter='One'))
        self.engine.apply(self.engine.plan())
        text = path.read_text(encoding='utf-8')
        self.assertEqual(text.count('### One\n'), 1)
        self.assertEqual(text.count('### Two\n'), 1)
        self.assertIn('**Location:** 10–12 · **Chapter:** One', text)
        self.assertEqual(self.engine.plan()[0].action, 'unchanged')

    def test_chapters_without_positions_and_repeated_chapter_name(self):
        self.engine.options = MarkdownOptions(group_chapters=True, positions=False)
        self.ingest(Highlight(self.book.id, 'Middle', location_start=50, chapter='Two'))
        self.ingest(Highlight(self.book.id, 'Later', location_start=100, chapter='One'))
        path = self.initial()
        self.assertEqual(self.engine.plan()[0].action, 'unchanged')
        text = path.read_text(encoding='utf-8')
        self.assertLess(text.index('Last passage'), text.index('Later'))

    def test_two_editions_do_not_adopt_ambiguous_legacy_note(self):
        # Deliberately retain two distinct library editions of the same title.
        a = canonical(replace(self.book, calibre_id=1), 'library')
        b = canonical(replace(self.book, calibre_id=2), 'library')
        self.store.map_book(self.book.id, a)
        self.store.ingest(ImportBatch([b], [Highlight(b.id, 'Other edition', location_start=1)]), Matcher())
        folder = self.root / 'notes'
        folder.mkdir()
        legacy = frontmatter(self.book, MarkdownOptions()).replace('khs_book_id: "' + self.book.id + '"\n', '')
        path = folder / 'Example.md'
        path.write_text(legacy + render(self.book, [self.first]), encoding='utf-8')
        before = path.read_bytes()
        plan = self.engine.plan()
        self.assertTrue(all(c.path != str(path) for c in plan))
        self.engine.apply(plan)
        self.assertEqual(path.read_bytes(), before)

    def test_source_book_id_variation_reuses_identity(self):
        variant = replace(self.book, id='different-source-id', identifiers={'asin': 'example'})
        self.store.ingest(ImportBatch([variant], [Highlight(variant.id, 'New', location_start=50)]), Matcher())
        self.assertEqual(len(self.store.books()), 1)
        self.assertEqual(len(self.store.highlights(self.book.id)), 3)


if __name__ == '__main__':
    unittest.main()
