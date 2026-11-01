"""Exercise installed ZIP, real library API, and Qt widgets in an isolated profile."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qt.core import QApplication, QEventLoop, QFont, QFontDatabase, QMainWindow, QTimer
from calibre.db.legacy import LibraryDatabase
from calibre.ebooks.metadata.book.base import Metadata
from calibre.customize.ui import find_plugin
from calibre_plugins.kindle_highlights_sync.calibre_adapter import library_snapshot
from calibre_plugins.kindle_highlights_sync.config import SettingsWidget
from calibre_plugins.kindle_highlights_sync.config import preferences
from calibre_plugins.kindle_highlights_sync.core.models import ImportBatch, Highlight, SyncDestination
from calibre_plugins.kindle_highlights_sync.core.matching import Matcher
from calibre_plugins.kindle_highlights_sync.core.storage import Store
from calibre_plugins.kindle_highlights_sync.core.sync import SyncEngine
from calibre_plugins.kindle_highlights_sync.ui import ManagerDialog, PreviewDialog
from calibre_plugins.kindle_highlights_sync.action import KindleHighlightsAction


def main():
    app = QApplication.instance() or QApplication([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    if font_id >= 0:
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    output = ROOT / '.test-output'
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=output) as temporary:
        root = Path(temporary)
        library = root / 'library'
        library.mkdir()
        db = LibraryDatabase(str(library))
        metadata = Metadata('Synthetic EPUB', ['Example Author'])
        metadata.identifiers = {'isbn': '9780000000001'}
        epub = root / 'synthetic.epub'
        with zipfile.ZipFile(epub, 'w') as archive:
            archive.writestr('mimetype', 'application/epub+zip')
            archive.writestr('META-INF/container.xml', '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
            archive.writestr('content.opf', '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Synthetic EPUB</dc:title><dc:creator>Example Author</dc:creator><dc:identifier id="id">test-book</dc:identifier><dc:language>en</dc:language></metadata><manifest><item id="text" href="text.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="text"/></spine></package>')
            archive.writestr('text.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Synthetic EPUB</title></head><body><p>A synthetic passage.</p></body></html>')
        db.new_api.add_books([(metadata, {'EPUB': str(epub)})])
        gui = QMainWindow()
        gui.current_db = db
        snapshot = library_snapshot(gui)
        assert len(snapshot) == 1 and snapshot[0].formats == [{'format': 'EPUB'}]
        plugin = find_plugin('Kindle Highlights Sync')
        widget = plugin.config_widget()
        assert isinstance(widget, SettingsWidget)
        widget.resize(720, 850)
        widget.controls['filename'].setText('{author} - {title}')
        widget.controls['author_folders'].setChecked(True)
        assert widget.path_preview.toPlainText() == 'Books/Highlights/Example Author/Example Author - Example Book.md'
        assert 'compact' in widget.values() and 'group_chapters' in widget.values()
        widget.show()
        app.processEvents()
        widget.grab().save(str(output / 'settings.png'))
        widget.resize(520, 740)
        app.processEvents()
        widget.grab().save(str(output / 'settings-narrow.png'))
        widget.close()
        state = root / 'state.sqlite'
        store = Store(state)
        book = snapshot[0]
        store.ingest(ImportBatch([book], [Highlight(book.id, 'A synthetic passage.\n\nAnother paragraph.', location_start=10, location_end=12)]), Matcher(snapshot))
        vault = root / 'vault'
        vault.mkdir()
        engine = SyncEngine(store, SyncDestination(str(vault)))
        plan = engine.plan()
        assert len(plan) == 1
        preview = PreviewDialog(gui, plan, {'books': 1, 'imported': 1, 'new': 1})
        preview.show()
        app.processEvents()
        assert len(preview.selected()) == 1
        preview.grab().save(str(output / 'preview.png'))
        preview.close()
        manager = ManagerDialog(gui, state, snapshot, lambda only: None)
        manager.show()
        app.processEvents()
        assert manager.books.count() == 1
        assert manager.highlights.rowCount() == 1
        manager.highlights.selectRow(0)
        app.processEvents()
        assert manager.current_highlight is not None
        manager.grab().save(str(output / 'manager.png'))
        manager.close()
        assert engine.apply(plan)['created'] == 1
        assert engine.plan()[0].action == 'unchanged'
        action = KindleHighlightsAction(gui, '')
        gui.keyboard = SimpleNamespace(register_shortcut=lambda *a, **kw: None)
        action.do_genesis()
        assert action.qaction.text() == 'Sync Kindle Highlights'
        assert len(action.menu.actions()) == 5
        source = root / 'source'
        source.mkdir()
        (source / 'My Clippings.txt').write_text('Synthetic EPUB (Example Author)\n- Your Highlight at location 1-2 | Added on Wednesday, 28 October 2026 12:30:00\n\nA synthetic passage.\n==========\n', encoding='utf-8')
        prefs = preferences()
        with prefs:
            prefs['vault'] = str(vault)
            prefs['manual_folder'] = str(source)
            prefs['preview'] = False
        gui.device_manager = SimpleNamespace(is_device_connected=False, device=None)
        loop = QEventLoop()
        result = {}
        def summary(value):
            result.update(value)
            action._finish()
            loop.quit()
        def failure(message):
            result['failure'] = message
            action._finish()
            loop.quit()
        action._summary = summary
        action._failed = failure
        action.start_sync()
        QTimer.singleShot(15000, loop.quit)
        loop.exec()
        assert 'failure' not in result, result
        assert result.get('created') == 1, result
        # Wait for the final QThread return before destroying its parent.
        for worker in list(action.workers):
            worker.wait(5000)
        print('Installed ZIP imports, real EPUB-only library, Qt dialogs, toolbar, background import, and one-click sync passed.')
        store.close()
        db.close()
        gui.close()


if __name__ == '__main__':
    main()
