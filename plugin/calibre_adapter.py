"""Calibre boundary. All device I/O runs on Calibre's device thread."""
from pathlib import Path
import os

from .core.models import Book
from .core.matching import canonical


def library_snapshot(gui):
    api = gui.current_db.new_api
    library_id = str(api.library_id)
    result = []
    for book_id in api.all_book_ids():
        mi = api.get_metadata(book_id, get_cover=False)
        published = mi.pubdate.isoformat() if mi.pubdate and mi.pubdate.year > 101 else None
        result.append(canonical(Book(mi.title, list(mi.authors or []), identifiers=dict(mi.identifiers or {}),
                                     calibre_id=book_id, series=mi.series, published=published,
                                     formats=[{'format': f} for f in (api.formats(book_id) or ())]), library_id))
    return result


def device_book_mappings(gui, library_books):
    """Use Calibre's established on-device application IDs where available."""
    from .core.models import Book
    lookup = {b.calibre_id: b.id for b in library_books}
    result = {}
    for name in ('memory_view', 'card_a_view', 'card_b_view'):
        view = getattr(gui, name, None)
        if view is None:
            continue
        model = view.model()
        for book in getattr(model, 'db', ()) or ():
            application_id = getattr(book, 'application_id', None)
            if application_id in lookup:
                source = Book(book.title, list(book.authors or []))
                result[source.id] = lookup[application_id]
    return result


def is_kindle(device):
    return bool(getattr(device, 'is_kindle', False) or 'kindle' in type(device).__name__.lower()
                or getattr(device, 'VENDOR_ID', None) == 0x1949)


def copy_device_sources(device, destination, cancelled=lambda: False):
    """Copy annotation/KFX inputs locally. No device mutation calls are used.

    Explicit MTP listing bypasses normal .sdr omission without changing global
    driver settings or its filesystem cache. Must be called by a DeviceJob.
    """
    from .core.pipeline import Cancelled
    destination = Path(destination)
    warnings = []
    if not is_kindle(device):
        raise ValueError('The connected device is not recognized as a Kindle. Use manual folder import if needed.')
    allowed = {'.yjr', '.yjf', '.kfx', '.res', '.azw', '.azw8', '.azw9', '.yj'}

    def relevant(name):
        return name.casefold() == 'my clippings.txt' or Path(name).suffix.casefold() in allowed

    def safe_target(parts):
        # Device names are untrusted; never allow a device object to escape staging.
        if any(p in ('.', '..', '') or '/' in p or '\\' in p or ':' in p for p in parts):
            raise ValueError('Device contains an unsafe filename.')
        target = destination.joinpath(*parts)
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError('Device filename escapes the import directory.')
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    if hasattr(device, 'list_mtp_folder_by_name'):
        storages = device.filesystem_cache.entries
        for index, storage in enumerate(storages):
            def visit(parts, depth=0):
                if cancelled():
                    raise Cancelled()
                if depth > 40:
                    warnings.append('Skipped a device directory with excessive nesting.')
                    return
                try:
                    entries = device.list_mtp_folder_by_name(storage, *parts)
                except Exception:
                    warnings.append('One device directory could not be listed; use manual import if annotations are missing.')
                    return
                for entry in entries:
                    name = entry['name']
                    child = (*parts, name)
                    if entry.get('is_folder'):
                        if not parts and name.casefold() not in ('documents',):
                            continue
                        visit(child, depth + 1)
                    elif relevant(name):
                        target = safe_target((str(index), *child))
                        try:
                            with target.open('wb') as stream:
                                device.get_mtp_file_by_name(storage, *child, stream=stream)
                        except Exception:
                            target.unlink(missing_ok=True)
                            warnings.append('One device file could not be read; it may have disconnected.')
            visit(())
    else:
        import shutil
        roots = [getattr(device, '_main_prefix', None), getattr(device, '_card_a_prefix', None), getattr(device, '_card_b_prefix', None)]
        for index, prefix in enumerate(p for p in roots if p):
            root = Path(prefix).resolve()
            documents = root / 'documents'
            if not documents.is_dir():
                continue
            def on_error(error):
                warnings.append('A Kindle directory is inaccessible (' + type(error).__name__ + ').')
            for current, directories, files in os.walk(documents, followlinks=False, onerror=on_error):
                directories[:] = [d for d in directories if not (Path(current) / d).is_symlink() and (Path(current) / d).resolve().is_relative_to(root)]
                if cancelled():
                    raise Cancelled()
                for name in files:
                    source = Path(current) / name
                    if relevant(name) and not source.is_symlink() and source.resolve().is_relative_to(root):
                        target = safe_target((str(index), *source.relative_to(root).parts))
                        try:
                            shutil.copyfile(source, target)
                        except OSError:
                            target.unlink(missing_ok=True)
                            warnings.append('One Kindle file could not be read; it may have disconnected.')
    return warnings
