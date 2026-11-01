import json
from pathlib import Path

from calibre.gui2 import error_dialog, info_dialog
from qt.core import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, Qt, QVBoxLayout, QWidget,
)

from .core.storage import Store


class PreviewDialog(QDialog):
    def __init__(self, parent, changes, stats):
        super().__init__(parent)
        self.setWindowTitle('Preview Kindle Highlights Sync')
        self.resize(950, 650)
        self.changes = changes
        layout = QVBoxLayout(self)
        counts = {action: sum(c.action == action for c in changes) for action in ('create', 'update', 'unchanged', 'conflict')}
        label = QLabel(f'Books found: {stats.get("books", 0)} · Imported: {stats.get("imported", 0)} · New: {stats.get("new", 0)} · Existing: {stats.get("existing", 0)}\n'
                       f'Excluded books: {stats.get("excluded_books", 0)} · Excluded highlights: {stats.get("excluded_highlights", 0)} · Unrecovered placeholders: {stats.get("unrecovered", 0)}\n'
                       f'Recovery failures: {stats.get("recovery_failures", 0)}\n'
                       f'Create: {counts["create"]} · Update: {counts["update"]} · Unchanged: {counts["unchanged"]} · Conflicts: {counts["conflict"]}')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(len(changes), 4)
        self.table.setHorizontalHeaderLabels(['Sync', 'Book', 'Action', 'Destination / conflict'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for index, change in enumerate(changes):
            select = QTableWidgetItem()
            select.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            select.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(index, 0, select)
            detail = change.reason or change.path
            if change.duplicates:
                detail += '\nMerge and archive: ' + ', '.join(Path(p).name for p, _ in change.duplicates)
            for column, text in enumerate((change.title, change.action, detail), 1):
                self.table.setItem(index, column, QTableWidgetItem(text))
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(170)
        self.details.setPlainText('\n'.join(stats.get('warnings', [])) or 'No import warnings.')
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Synchronize selected books')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self):
        return [c for index, c in enumerate(self.changes) if self.table.item(index, 0).checkState() == Qt.CheckState.Checked]


class ManagerDialog(QDialog):
    def __init__(self, parent, db_path, library_books, export_callback, source_roots=()):
        super().__init__(parent)
        self.setWindowTitle('Manage Kindle highlights')
        self.resize(1100, 740)
        self.store = Store(db_path)
        self.library_books = library_books
        self.export_callback = export_callback
        self.source_roots = [Path(p).resolve() for p in source_roots if p]
        self.current_book = None
        self.current_highlight = None
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search books, authors, highlights, or notes…')
        self.search.textChanged.connect(self.refresh_books)
        layout.addWidget(self.search)
        self.show_excluded = QCheckBox('Show excluded books and highlights')
        self.show_excluded.setChecked(True)
        self.show_excluded.toggled.connect(self.refresh_books)
        layout.addWidget(self.show_excluded)
        splitter = QSplitter()
        self.books = QListWidget()
        self.books.currentItemChanged.connect(self.select_book)
        splitter.addWidget(self.books)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.highlights = QTableWidget(0, 3)
        self.highlights.setHorizontalHeaderLabels(['Status', 'Type / position', 'Text'])
        self.highlights.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.highlights.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.highlights.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.highlights.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.highlights.itemSelectionChanged.connect(self.select_highlight)
        right_layout.addWidget(self.highlights)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText('Select a highlight to view or edit its text.')
        right_layout.addWidget(self.text)
        self.source = QLabel()
        self.source.setWordWrap(True)
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        right_layout.addWidget(self.source)
        splitter.addWidget(right)
        splitter.setSizes([300, 800])
        layout.addWidget(splitter)
        buttons = QGridLayout()
        for index, (text, callback) in enumerate([('Exclude / restore book', self.toggle_book), ('Exclude / restore highlight', self.toggle_highlight),
                               ('Save text edit', self.save_edit), ('Restore source text', self.reset_edit),
                               ('Match library book…', self.match_book), ('Export this book', self.export_book),
                               ('Export cleaned clippings…', self.export_clippings)]):
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button, index // 4, index % 4)
        layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.finished.connect(lambda: self.store.close())
        self.refresh_books()

    def refresh_books(self, *args):
        previous = self.current_book.id if self.current_book else None
        self.books.clear()
        self.current_book = None
        query = self.search.text().casefold()
        for book in sorted(self.store.books(), key=lambda b: b.title.casefold()):
            excluded = self.store.excluded('book', book.id)
            if excluded and not self.show_excluded.isChecked():
                continue
            highlights = self.store.highlights(book.id)
            haystack = book.title + ' ' + ' '.join(book.authors) + ' ' + ' '.join(h.text + ' ' + (h.note or '') for h in highlights)
            if query and query not in haystack.casefold():
                continue
            item = QListWidgetItem(('[Excluded] ' if excluded else '') + book.title + f' ({len(highlights)})')
            item.setData(Qt.ItemDataRole.UserRole, book)
            self.books.addItem(item)
            if book.id == previous:
                self.books.setCurrentItem(item)
        if self.books.currentItem() is None and self.books.count():
            self.books.setCurrentRow(0)
        if not self.books.count():
            self.highlights.setRowCount(0)
            self.text.clear()
            self.source.clear()
            self.status.setText('No matching imported books.')

    def select_book(self, current, previous=None):
        self.current_book = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.current_highlight = None
        self.highlights.setRowCount(0)
        self.text.clear()
        self.source.clear()
        if not self.current_book:
            return
        query = self.search.text().casefold()
        for h in self.store.highlights(self.current_book.id):
            if h.excluded and not self.show_excluded.isChecked():
                continue
            if query and query not in (h.text + ' ' + (h.note or '')).casefold() and query not in (self.current_book.title + ' ' + ' '.join(self.current_book.authors)).casefold():
                continue
            row = self.highlights.rowCount()
            self.highlights.insertRow(row)
            status = 'Excluded' if h.excluded else 'Needs recovery' if h.needs_recovery else 'Included'
            position = h.location_start if h.location_start is not None else h.position_start if h.position_start is not None else '—'
            for col, value in enumerate((status, h.kind + ' / ' + str(position), h.text[:240])):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, h)
                self.highlights.setItem(row, col, item)
        state = self.store.db.execute('SELECT synced_at,path FROM sync_state WHERE book_id=? ORDER BY synced_at DESC LIMIT 1', (self.current_book.id,)).fetchone()
        self.status.setText(('Last synchronized: ' + state[0] + '\n' + state[1]) if state else 'Not yet synchronized')

    def select_highlight(self):
        row = self.highlights.currentRow()
        item = self.highlights.item(row, 0) if row >= 0 else None
        self.current_highlight = item.data(Qt.ItemDataRole.UserRole) if item else None
        if self.current_highlight:
            self.text.setPlainText(self.current_highlight.text)
            provenance = self.store.provenance(self.current_highlight.id)
            self.source.setText('Sources: ' + ', '.join(p['backend'] for p in provenance) + '\nID: ' + self.current_highlight.id +
                                ('\nPersonal note: ' + self.current_highlight.note if self.current_highlight.note else ''))

    def toggle_book(self):
        if self.current_book:
            self.store.exclude('book', self.current_book.id, not self.store.excluded('book', self.current_book.id))
            self.refresh_books()

    def toggle_highlight(self):
        if self.current_highlight:
            h = self.current_highlight
            self.store.exclude('highlight', h.id, not h.excluded)
            self.select_book(self.books.currentItem())

    def save_edit(self):
        if self.current_highlight:
            self.store.edit(self.current_highlight.id, self.text.toPlainText())
            self.select_book(self.books.currentItem())

    def reset_edit(self):
        if self.current_highlight:
            self.store.reset_edit(self.current_highlight.id)
            self.select_book(self.books.currentItem())

    def match_book(self):
        if not self.current_book:
            return
        choices = sorted(self.library_books, key=lambda b: b.title.casefold())
        labels = [f'{b.title} — {", ".join(b.authors)} [Calibre {b.calibre_id}]' for b in choices]
        selected, ok = QInputDialog.getItem(self, 'Choose the correct edition', 'Calibre book', labels, 0, False)
        if ok and selected:
            target = choices[labels.index(selected)]
            old_id = self.current_book.id
            aliases = [r[0] for r in self.store.db.execute('SELECT alias FROM book_aliases WHERE book_id=?', (old_id,))]
            for alias in aliases or [old_id]:
                self.store.map_book(alias, target)
            self.refresh_books()

    def export_book(self):
        if self.current_book:
            book_id = self.current_book.id
            self.accept()
            self.export_callback({book_id})

    def export_clippings(self):
        from .importers.clippings import serialize
        path, _ = QFileDialog.getSaveFileName(self, 'Save a cleaned copy', 'Cleaned Clippings.txt', 'Text files (*.txt)')
        if not path:
            return
        path = Path(path).resolve()
        source_paths = {Path(r[0]).resolve() for r in self.store.db.execute('SELECT path FROM sources')}
        roots = self.source_roots + [p.parent for p in source_paths]
        if path in source_paths or any(path.is_relative_to(root) for root in roots) or path.name.casefold() == 'my clippings.txt':
            error_dialog(self, 'Choose another filename', 'Save a cleaned copy with a different name, outside the Kindle.', show=True)
            return
        books = [b for b in self.store.books() if not self.store.excluded('book', b.id)]
        ids = {b.id for b in books}
        try:
            path.write_text(serialize(books, [h for h in self.store.highlights() if h.book_id in ids]), encoding='utf-8')
            info_dialog(self, 'Cleaned clippings saved', 'KFX-only records without verified Kindle locations are omitted from this text format. They remain available in Markdown.', show=True)
        except OSError:
            error_dialog(self, 'Could not save', 'The selected destination is not writable.', show=True)
