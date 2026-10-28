"""Read-only YJR / KFX reconstruction using pinned GPL libraries.

Positions are inclusive KFX PID ranges, never EPUB character offsets.
"""
from bisect import bisect_right
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
import hashlib
import io
import logging

from ..core.models import Book, Highlight, ImportBatch, ImportSource, stable_id
from ..vendor.krds import KindleReaderDataStore


class RecoveryError(Exception):
    pass


def quiet_logger():
    logger = logging.Logger('kindle-recovery-private', level=logging.CRITICAL + 1)
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def decode_yjr(path):
    data = Path(path).read_bytes()
    try:
        result = KindleReaderDataStore(quiet_logger(), data).deserialize()
        cache = result.get('annotation.cache.object', {})
        if not isinstance(cache, dict):
            raise ValueError('Unknown annotation container')
        return cache
    except Exception as error:
        raise RecoveryError('Corrupt or unsupported YJR annotation data (' + type(error).__name__ + ').') from None


@dataclass
class TextSpan:
    position: int
    text: str


def extract_text(spans, start, end):
    if start < 0 or end < start:
        raise RecoveryError('Invalid KFX annotation range.')
    parts = []
    covered_start = covered_end = False
    previous = None
    for span in spans:
        stop = span.position + len(span.text)
        if span.position > end:
            break
        if stop <= start:
            continue
        a, b = max(start, span.position), min(end + 1, stop)
        if b <= a:
            continue
        covered_start |= span.position <= start < stop
        covered_end |= span.position <= end < stop
        if previous is not None and a > previous:
            # Structural gaps are paragraph boundaries, not invented characters.
            parts.append('\n\n')
        parts.append(span.text[a - span.position:b - span.position])
        previous = b
    if not covered_start or not covered_end:
        raise RecoveryError('KFX selection boundary is outside supported text content.')
    result = ''.join(parts).strip()
    if not result:
        raise RecoveryError('KFX selection contains no recoverable text.')
    return result


def navigation(book, chunks):
    """Handle inline IonAnnotation, referenced fragments, and nested entries."""
    from ..vendor.kfxlib.ion import IonSymbol, unannotated
    from ..vendor.kfxlib.yj_container import YJFragment

    def resolve(value, ftype):
        if isinstance(value, IonSymbol):
            value = book.fragments.get(ftype=ftype, fid=value)
            if value is None:
                raise RecoveryError('Navigation references a missing fragment.')
        if isinstance(value, YJFragment):
            value = value.value
        value = unannotated(value)
        if not isinstance(value, dict):
            raise RecoveryError('Unsupported navigation structure.')
        return value

    def position(value):
        value = unannotated(value)
        eid, offset = value.get('$155'), value.get('$143', 0)
        if eid is None:
            raise RecoveryError('Navigation target has no element ID.')
        pid = book.pid_for_eid(eid, offset, chunks)
        if pid is None:
            raise RecoveryError('Navigation target could not be mapped to KFX text.')
        return pid

    pages, toc = [], []
    nav = book.fragments.get('$389', first=True)
    if nav is None:
        return pages, toc

    def visit(value, kind, depth=0):
        if depth > 32:
            raise RecoveryError('Navigation nesting exceeds supported depth.')
        entry = resolve(value, '$393')
        representation = unannotated(entry.get('$241', {}))
        label = representation.get('$244')
        if label and '$246' in entry:
            row = (position(entry['$246']), str(label), depth)
            (pages if kind == '$237' else toc).append(row)
        for child in entry.get('$247', []):
            visit(child, kind, depth + 1)

    for root_value in nav.value:
        root = resolve(root_value, '$389')
        for value in root.get('$392', []):
            container = resolve(value, '$391')
            kind = str(container.get('$235'))
            if kind in ('$237', '$212'):
                for entry in container.get('$247', []):
                    visit(entry, kind)
    return sorted(pages), sorted(toc, key=lambda item: (item[0], item[2]))


def position(value):
    try:
        return int(str(value).rsplit(':', 1)[-1])
    except (ValueError, TypeError):
        raise RecoveryError('Unsupported annotation position encoding.') from None


def recover(kfx_path, cache, annotation_path='', backend='yjr'):
    # Libraries may log book text during error handling. Suppress their output;
    # expose only our content-free diagnostic categories.
    from ..vendor.kfxlib import YJ_Book, KFXDRMError, set_logger
    from ..vendor.kfxlib.message_logging import get_current_logger

    result = ImportBatch()
    kfx_path = Path(kfx_path)
    content_hash = hashlib.sha256(kfx_path.read_bytes()).hexdigest()
    previous_logger = get_current_logger()
    set_logger(quiet_logger())
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            book = YJ_Book(str(kfx_path))
            # Normalization resolves duplicate metadata fragments in memory.
            # decode_book reads containers; it does not rewrite the source.
            book.decode_book()
            if book.is_fixed_layout or book.is_print_replica:
                raise RecoveryError('Fixed-layout or print-replica KFX is not supported.')
            meta = book.get_yj_metadata_from_book()
            chunks = book.collect_content_position_info(keep_footnote_refs=True)
            spans = [TextSpan(c.pid, c.text) for c in chunks if c.text is not None]
            if any(len(c.text) != c.length for c in chunks if c.text is not None):
                raise RecoveryError('KFX text lengths do not agree with the position map.')
            try:
                pages, toc = navigation(book, chunks)
            except Exception:
                pages, toc = [], []
                result.warnings.append('Navigation metadata is unsupported; recovered passages remain available.')
            # Only embedded maps; never generate approximate Kindle locations.
            locations = book.collect_location_map_info(chunks) if (book.fragments.get('$550', first=True) or book.fragments.get('$621', first=True)) else []
    except KFXDRMError:
        raise RecoveryError('DRM-protected KFX cannot be recovered.') from None
    except RecoveryError:
        raise
    except Exception as error:
        raise RecoveryError('Unsupported or corrupt KFX (' + type(error).__name__ + ').') from None
    finally:
        set_logger(previous_logger)

    identifiers = {}
    for name in ('asin', 'isbn'):
        value = getattr(meta, name, None)
        if value:
            identifiers[name] = str(value)
    model = Book(meta.title or kfx_path.stem, list(meta.authors or []), identifiers=identifiers,
                 formats=[{'format': 'KFX', 'path': str(kfx_path), 'source': 'device'}])
    result.books.append(model)
    location_pids = [c.pid for c in locations]
    page_pids, toc_pids = [p[0] for p in pages], [t[0] for t in toc]
    for kind, key in [('highlight', 'annotation.personal.highlight'), ('note', 'annotation.personal.note'), ('bookmark', 'annotation.personal.bookmark')]:
        entries = cache.get(key, [])
        if not isinstance(entries, list):
            result.warnings.append('Unsupported annotation list; skipped one annotation category.')
            continue
        for ordinal, annotation in enumerate(entries):
            try:
                start = position(annotation['startPosition'])
                end = position(annotation.get('endPosition', annotation['startPosition']))
                text = extract_text(spans, start, end) if kind == 'highlight' else str(annotation.get('note', ''))
                page_index = bisect_right(page_pids, start) - 1
                chapter_index = bisect_right(toc_pids, start) - 1
                # Retain PID coordinates separately. Embedded locations are used
                # only after clippings corroborate the map in the orchestrator.
                h = Highlight(model.id, text, kind=kind, position_start=start, position_end=end,
                              position_system='kfx:' + content_hash,
                              mapped_location_start=bisect_right(location_pids, start) if location_pids and start >= location_pids[0] else None,
                              mapped_location_end=bisect_right(location_pids, end) if location_pids and end >= location_pids[0] else None,
                              page=pages[page_index][1] if page_index >= 0 else None,
                              chapter=toc[chapter_index][1] if chapter_index >= 0 else None,
                              created_at=annotation.get('creationTime'), source=backend,
                              source_id=stable_id(content_hash, annotation.get('annotationId'), kind, start, end, annotation.get('creationTime')),
                              source_path=str(annotation_path), ordinal=ordinal)
                result.highlights.append(h)
            except (KeyError, ValueError, TypeError, RecoveryError):
                result.recovery_failures += 1
                result.warnings.append(f'Annotation {ordinal + 1} ({kind}): invalid or unsupported selection; skipped.')
    # Notes remain independent annotations so their own identity, exclusion,
    # creation timestamp, and cross-source provenance are never discarded.
    result.sources.append(ImportSource(str(kfx_path), 'kfx', content_hash))
    if annotation_path:
        result.sources.append(ImportSource(str(annotation_path), backend, hashlib.sha256(Path(annotation_path).read_bytes()).hexdigest()))
    return result
