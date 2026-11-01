"""Native Calibre action and cancellable background workflow."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from calibre.gui2 import Dispatcher, error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from qt.core import QDialog, QFileDialog, QMenu, QProgressDialog, QThread, Qt, pyqtSignal

from .calibre_adapter import copy_device_sources, device_book_mappings, library_snapshot
from .config import SettingsDialog, destination, markdown_options, settings, state_path
from .core.matching import Matcher
from .core.pipeline import Cancelled, scan_folder
from .core.storage import Store
from .core.sync import SyncEngine, validate_destination
from .ui import ManagerDialog, PreviewDialog


class Worker(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function(self.progress.emit))
        except Cancelled:
            self.failed.emit('Cancelled. No additional notes were written.')
        except Exception as error:
            message = str(error) if isinstance(error, ValueError) else 'Operation failed (' + type(error).__name__ + '). Check the source and destination permissions.'
            self.failed.emit(message)


class KindleHighlightsAction(InterfaceAction):
    name = 'Kindle Highlights Sync'
    action_spec = ('Sync Kindle Highlights', 'reader.png', 'Import Kindle annotations and sync to Obsidian', None)

    def genesis(self):
        self.busy = False
        self.worker = None
        self.workers = []
        self.cancel_event = Event()
        self.staging = None
        self.menu = QMenu(self.gui)
        for label, callback in [('Sync Kindle Highlights', self.start_sync), ('Import folder…', self.import_folder),
                                 ('Manage highlights…', self.manage), ('Sync saved highlights', self.sync_saved),
                                 ('Settings…', self.configure)]:
            self.menu.addAction(label).triggered.connect(callback)
        self.qaction.setMenu(self.menu)
        self.qaction.triggered.connect(self.start_sync)

    def configure(self):
        if not self.busy:
            return SettingsDialog(self.gui).exec() == QDialog.DialogCode.Accepted
        return False

    def _begin(self):
        if self.busy:
            return False
        values = settings()
        try:
            validate_destination(destination(values))
        except ValueError:
            if not self.configure():
                return False
            values = settings()
        self.values = values
        self.db_path = state_path(self.gui)
        try:
            self.library_books = library_snapshot(self.gui)
            self.device_mappings = device_book_mappings(self.gui, self.library_books)
        except Exception:
            error_dialog(self.gui, 'Could not read the library', 'Wait for the Calibre library to finish opening, then retry.', show=True)
            return False
        self.busy = True
        self.cancel_event.clear()
        self.progress_dialog = QProgressDialog('Preparing Kindle Highlights Sync…', 'Cancel', 0, 100, self.gui)
        self.progress_dialog.setWindowTitle('Kindle Highlights Sync')
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.canceled.connect(self.cancel_event.set)
        self.progress_dialog.show()
        return True

    def _progress(self, value, message):
        self.progress_dialog.setValue(value)
        self.progress_dialog.setLabelText(message)

    def _work(self, function, callback):
        worker = Worker(function, self.gui)
        self.worker = worker
        self.workers.append(worker)
        worker.progress.connect(self._progress)
        worker.result.connect(callback)
        worker.failed.connect(self._failed)
        def finished():
            self.workers.remove(worker)
            if self.worker is worker:
                self.worker = None
            worker.deleteLater()
        worker.finished.connect(finished)
        worker.start()

    def _finish(self):
        self.progress_dialog.close()
        self.busy = False
        # QThread can emit its result just before run() returns. Keep its parent
        # alive until the finished signal; never destroy a running thread.
        if self.staging:
            self.staging.cleanup()
            self.staging = None

    def _failed(self, message):
        self._finish()
        error_dialog(self.gui, 'Kindle Highlights Sync', message, show=True)

    def _guard_source(self, source):
        vault, target = validate_destination(destination(self.values))
        source = Path(source).expanduser().resolve()
        if target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError('The import source and Obsidian destination must be separate directories.')

    def start_sync(self, checked=False):
        if not self._begin():
            return
        manager = self.gui.device_manager
        device = manager.device if manager.is_device_connected else None
        if device is None:
            folder = self.values['manual_folder']
            if not folder:
                folder = QFileDialog.getExistingDirectory(self.gui, 'Select a Kindle or copied import folder')
            if not folder:
                self._finish()
                return
            self._scan(folder)
            return
        try:
            # Reject destinations located on a mounted Kindle.
            for prefix in (getattr(device, '_main_prefix', None), getattr(device, '_card_a_prefix', None), getattr(device, '_card_b_prefix', None)):
                if prefix:
                    self._guard_source(prefix)
            self.staging = TemporaryDirectory(prefix='kindle-highlights-')
            self.progress_dialog.setLabelText('Copying annotation sources from Kindle…')
            def copy():
                return copy_device_sources(device, self.staging.name, self.cancel_event.is_set)
            manager.create_job(copy, Dispatcher(self._device_copied), 'Read Kindle highlight sources')
        except Exception as error:
            self._failed(str(error) if isinstance(error, ValueError) else 'Could not read the connected Kindle.')

    def _device_copied(self, job):
        if job.failed or self.cancel_event.is_set():
            self._failed('Kindle import was cancelled or the device could not be read. Manual folder import is available from the toolbar menu.')
            return
        self._scan(self.staging.name, job.result)

    def import_folder(self, checked=False):
        if self.busy:
            return
        folder = QFileDialog.getExistingDirectory(self.gui, 'Import a Kindle or copied source folder', settings()['manual_folder'])
        if folder and self._begin():
            self._scan(folder)

    def _scan(self, folder, warnings=()):
        try:
            self._guard_source(folder)
        except ValueError as error:
            self._failed(str(error))
            return
        values, db_path, library_books = self.values.copy(), self.db_path, self.library_books
        device_mappings = self.device_mappings.copy()
        def work(progress):
            batch = scan_folder(folder, values['clippings'], values['recovery'], progress, self.cancel_event.is_set)
            batch.warnings.extend(warnings)
            if self.cancel_event.is_set():
                raise Cancelled()
            store = Store(db_path)
            try:
                mappings = device_mappings | store.mappings()
                matcher = Matcher(library_books, mappings)
                if not values['prefer_calibre']:
                    class SourceMetadataMatcher:
                        def match(self, source):
                            target, warning = matcher.match(source)
                            return replace(source, id=target.id, calibre_id=target.calibre_id, library_id=target.library_id), warning
                    matcher_used = SourceMetadataMatcher()
                else:
                    matcher_used = matcher
                stats = store.ingest(batch, matcher_used)
                stats['books'] = len(batch.books)
                stats['excluded_books'] = sum(store.excluded('book', b.id) for b in store.books())
                stats['excluded_highlights'] = sum(h.excluded for h in store.highlights())
                stats['unrecovered'] = sum(h.needs_recovery for h in store.highlights())
                engine = SyncEngine(store, destination(values), markdown_options(values))
                return engine.plan(), stats
            finally:
                store.close()
        self._work(work, self._preview)

    def _preview(self, result):
        changes, stats = result
        self.progress_dialog.hide()
        if self.cancel_event.is_set():
            self._finish()
            return
        if self.values['preview']:
            dialog = PreviewDialog(self.gui, changes, stats)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._finish()
                return
            changes = dialog.selected()
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        values, db_path = self.values.copy(), self.db_path
        def work(progress):
            store = Store(db_path)
            try:
                return SyncEngine(store, destination(values), markdown_options(values)).apply(changes, self.cancel_event.is_set, progress)
            finally:
                store.close()
        self.import_stats = stats
        self._work(work, self._summary)

    def _summary(self, summary):
        self._finish()
        stats = self.import_stats
        text = (f'Notes created: {summary["created"]}\nNotes updated: {summary["updated"]}\nUnchanged: {summary["unchanged"]}\n'
                f'Duplicate notes merged and archived: {summary["merged"]}\n'
                f'Conflicts preserved: {summary["conflicts"]}\nWrite errors: {summary["errors"]}\n'
                f'New highlights: {stats.get("new", 0)}\nExisting / duplicate records: {stats.get("existing", 0)}\n'
                f'Recovery failures: {stats.get("recovery_failures", 0)}\n'
                f'Import warnings: {len(stats.get("warnings", []))}' + ('\nSynchronization cancelled.' if summary['cancelled'] else ''))
        info_dialog(self.gui, 'Kindle Highlights Sync results', text,
                    det_msg='\n'.join(stats.get('warnings', []) + summary['details']), show=True)

    def manage(self, checked=False):
        if self.busy:
            return
        source_roots = [settings()['manual_folder']]
        manager = self.gui.device_manager
        device = manager.device if manager.is_device_connected else None
        if device:
            source_roots.extend(getattr(device, name, None) for name in ('_main_prefix', '_card_a_prefix', '_card_b_prefix'))
        dialog = ManagerDialog(self.gui, state_path(self.gui), library_snapshot(self.gui), self.sync_saved, source_roots)
        dialog.exec()

    def shutting_down(self):
        self.cancel_event.set()
        for worker in list(self.workers):
            # Let the current atomic file operation or KFX decode finish.
            # A running QThread cannot safely outlive Calibre's Qt application.
            worker.wait()

    def sync_saved(self, only=None):
        if isinstance(only, bool):
            only = None
        if not self._begin():
            return
        values, db_path = self.values.copy(), self.db_path
        def work(progress):
            store = Store(db_path)
            try:
                engine = SyncEngine(store, destination(values), markdown_options(values))
                return engine.plan(only=only), {
                    'books': len(only) if only else len(store.books()), 'warnings': [],
                    'excluded_books': sum(store.excluded('book', b.id) for b in store.books()),
                    'excluded_highlights': sum(h.excluded for h in store.highlights()),
                    'unrecovered': sum(h.needs_recovery for h in store.highlights()),
                }
            finally:
                store.close()
        self._work(work, self._preview)
