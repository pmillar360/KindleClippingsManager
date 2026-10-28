from pathlib import Path

from .models import ImportBatch
from ..importers.clippings import read
from ..importers.recovery import decode_yjr, recover


class Cancelled(Exception):
    pass


def scan_folder(folder, clippings=True, recovery=True, progress=lambda value, message: None, cancelled=lambda: False):
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('Import folder is missing or unavailable.')
    result = ImportBatch()
    files = []
    # Do not follow linked directories off the chosen source/device.
    import os
    def on_error(error):
        result.warnings.append('A source directory could not be read (' + type(error).__name__ + ').')
    for current, directories, names in os.walk(root, onerror=on_error, followlinks=False):
        directories[:] = [name for name in directories if (Path(current) / name).resolve().is_relative_to(root) and not (Path(current) / name).is_symlink()]
        for name in names:
            path = Path(current) / name
            if not path.is_symlink() and path.resolve().is_relative_to(root):
                files.append(path)
        if cancelled():
            raise Cancelled()
    clipping_files = [p for p in files if p.name.casefold() == 'my clippings.txt']
    if not clipping_files and clippings:
        # Manual copied exports often retain descriptive filenames.
        clipping_files = [p for p in files if p.suffix.lower() == '.txt' and p.name.casefold().startswith('my clippings')]
    tasks = [('clippings', p) for p in clipping_files] if clippings else []
    tasks += [('yjr', p) for p in files if p.suffix.lower() == '.yjr'] if recovery else []
    if clippings and not clipping_files:
        result.warnings.append('My Clippings.txt was not found in this source.')
    kfx_files = [p for p in files if p.suffix.lower() == '.kfx' and p.name.lower() != 'bookmanifest.kfx'
                 and not any(part.lower().endswith('.sdr') for part in p.relative_to(root).parts[:-1])]
    if recovery and not any(kind == 'yjr' for kind, _ in tasks):
        result.warnings.append('No YJR annotations were found. If recovery is needed, include the book’s .sdr folder.')
    if recovery and any(p.name == 'ksdk_annotation_v1.db' for p in files):
        result.warnings.append('A newer Kindle annotation database was detected. This release supports YJR recovery; empty sidecars need a compatible annotation export.')
    for index, (kind, path) in enumerate(tasks):
        if cancelled():
            raise Cancelled()
        progress(int(index * 90 / max(len(tasks), 1)), 'Reading annotation source ' + str(index + 1))
        try:
            if kind == 'clippings':
                batch = read(path)
            else:
                cache = decode_yjr(path)
                if not any(cache.get(key) for key in ('annotation.personal.highlight', 'annotation.personal.note', 'annotation.personal.bookmark')):
                    result.warnings.append('A YJR sidecar has no annotations; newer firmware may use the account annotation database.')
                    continue
                sidecar = next((parent for parent in path.parents if parent.name.lower().endswith('.sdr') and parent.is_relative_to(root)), None)
                choices = [k for k in kfx_files if sidecar and k.parent == sidecar.parent and k.stem == sidecar.name[:-4]]
                if len(choices) != 1:
                    result.recovery_failures += 1
                    result.warnings.append('YJR recovery skipped: the corresponding KFX and .sdr pair is missing or ambiguous.')
                    continue
                batch = recover(choices[0], cache, str(path))
            result.books.extend(batch.books)
            result.highlights.extend(batch.highlights)
            result.sources.extend(batch.sources)
            result.warnings.extend(batch.warnings)
            result.recovery_failures += batch.recovery_failures
        except Exception as error:
            if kind == 'yjr':
                result.recovery_failures += 1
            # RecoveryError messages are deliberately content-free.
            from ..importers.recovery import RecoveryError
            message = str(error) if isinstance(error, RecoveryError) else type(error).__name__
            result.warnings.append(kind.upper() + ' source could not be imported: ' + message)
    # Preserve the best source metadata for a shared provisional identity.
    books = {}
    for book in result.books:
        if book.id not in books or book.identifiers or book.formats:
            books[book.id] = book
    result.books = list(books.values())
    progress(95, 'Annotations read')
    return result
