"""Conservative file ownership, crash journal, and atomic note replacement."""
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from string import Formatter
import hashlib
import json
import os
import re
import tempfile
from uuid import uuid4

from .markdown import BEGIN, END, MarkdownOptions, frontmatter, render
from .models import now
from .models import normalize
from .matching import author_key
from .note_merge import merge, properties, region, split
from .markdown import inline, order_key


def digest(data):
    return hashlib.sha256(data).hexdigest()


def contained(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Destination escapes the selected vault.')
    return path


def safe_filename(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', value).strip(' .')
    value = re.sub(r'\s+', ' ', value)
    if not value:
        value = 'Untitled'
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', value, re.I):
        value = '_' + value
    # Bound Windows path component bytes as well as character count.
    while len(value.encode('utf-8')) > 160:
        value = value[:-1]
    return value.rstrip(' .') or 'Untitled'


def validate_destination(destination):
    vault = Path(destination.vault).expanduser().resolve()
    if not destination.vault.strip() or not vault.is_dir():
        raise ValueError('Select an existing Obsidian vault directory.')
    folder = destination.folder.replace('\\', '/')
    if Path(folder).is_absolute() or PureWindowsPath(folder).drive or '..' in Path(folder).parts:
        raise ValueError('Destination folder must be relative and cannot contain "..".')
    if any(part.rstrip(' .') != part or re.search(r'[<>:"|?*\x00-\x1f]', part) for part in Path(folder).parts):
        raise ValueError('Destination folder contains an invalid path component.')
    target = contained(vault, vault / folder)
    if target.exists() and not target.is_dir():
        raise ValueError('Destination folder is a file.')
    for _, field, spec, conversion in Formatter().parse(destination.filename):
        if field is not None and (field not in ('title', 'author', 'id') or spec or conversion):
            raise ValueError('Filename supports only {title}, {author}, and {id}.')
    return vault, target


@dataclass
class Change:
    book_id: str
    title: str
    path: str
    action: str
    expected_hash: str | None
    content: bytes = b''
    managed: str = ''
    reason: str = ''
    duplicates: list = field(default_factory=list)


class SyncEngine:
    def __init__(self, store, destination, options=None):
        self.store = store
        self.destination = destination
        self.options = options or MarkdownOptions()
        self.vault, self.target = validate_destination(destination)
        self.key = str(self.target)

    def state(self, book_id):
        return self.store.db.execute('SELECT * FROM sync_state WHERE destination=? AND book_id=?', (self.key, book_id)).fetchone()

    def _record(self, book_id, path, managed):
        self.store.db.execute('INSERT OR REPLACE INTO sync_state VALUES(?,?,?,?,?)',
                              (self.key, book_id, str(path), managed, now()))

    def _matches(self, book, text):
        values = properties(text)
        identity = values.get('khs_book_id')
        if not isinstance(identity, str):
            identity = None
        aliases = {book.id} | self._aliases.get(book.id, set())
        if identity and identity in aliases:
            return True
        # Explicitly different library editions must not be combined by title.
        if identity and identity.startswith('calibre-') and book.id.startswith('calibre-'):
            return False
        identifiers = values.get('identifiers', {})
        if isinstance(identifiers, dict):
            common = identifiers.keys() & book.identifiers.keys()
            if any(normalize(str(identifiers[k])).replace('-', '') != normalize(str(book.identifiers[k])).replace('-', '') for k in common):
                return False
            if common:
                choices = [b for b in self._books if any(k in b.identifiers and normalize(str(b.identifiers[k])).replace('-', '') == normalize(str(identifiers[k])).replace('-', '') for k in identifiers)]
                return len(choices) == 1 and choices[0].id == book.id
        peers = [b for b in self._books if normalize(b.title) == normalize(book.title)
                 and {author_key(a) for a in b.authors} == {author_key(a) for a in book.authors}]
        if len(peers) != 1:
            return False
        title = values.get('title')
        author = values.get('author')
        if title is None:
            title_match = re.search(r'^# (.+)$', text, re.M)
            author_match = re.search(r'^\*\*Author:\*\* (.+)$', text, re.M)
            title = title_match[1] if title_match else ''
            author = author_match[1] if author_match else ''
            return normalize(title) == normalize(inline(book.title)) and normalize(author or '') == normalize(inline(', '.join(book.authors)))
        return (isinstance(title, str) and isinstance(author or '', str)
                and normalize(title) == normalize(book.title)
                and author_key(author or '') == author_key(', '.join(book.authors)))

    def _notes(self):
        notes = {}
        if self.target.exists():
            for directory, folders, filenames in os.walk(self.target):
                folders[:] = [name for name in folders if not name.startswith('.')]
                for name in filenames:
                    if name.startswith('.') or not name.lower().endswith('.md'):
                        continue
                    try:
                        path = contained(self.target, Path(directory) / name)
                        raw = path.read_bytes()
                        notes[path] = (raw, raw.decode('utf-8'))
                    except (OSError, UnicodeDecodeError, ValueError):
                        continue
        return notes

    def recover(self):
        """Finalize a completed replacement or release an unperformed intent.

        A divergent destination is retained as a conflict. No replay overwrites.
        """
        conflicts = []
        for row in self.store.db.execute('SELECT * FROM sync_journal WHERE destination=?', (self.key,)).fetchall():
            try:
                path = contained(self.target, row['path'])
                current = digest(path.read_bytes()) if path.exists() else None
            except (OSError, ValueError):
                conflicts.append(row['book_id'])
                continue
            with self.store.db:
                if current == row['next_hash']:
                    self._record(row['book_id'], path, row['managed'])
                    self.store.db.execute('DELETE FROM sync_journal WHERE id=?', (row['id'],))
                elif current == row['previous_hash']:
                    self.store.db.execute('DELETE FROM sync_journal WHERE id=?', (row['id'],))
                else:
                    conflicts.append(row['book_id'])
        return conflicts

    def plan(self, only=None, skip=()):
        pending = self.recover()
        self._books = self.store.books()
        self._aliases = {}
        for row in self.store.db.execute('SELECT alias,book_id FROM book_aliases'):
            self._aliases.setdefault(row['book_id'], set()).add(row['alias'])
        changes, occupied = [], set()
        notes = self._notes()
        claimed = set()
        for row in self.store.db.execute('SELECT path FROM sync_state WHERE destination=?', (self.key,)):
            occupied.add(str(Path(row[0]).resolve()).casefold())
        for book in self._books:
            if only is not None and book.id not in only:
                continue
            if book.id in skip or self.store.excluded('book', book.id):
                continue
            highlights = self.store.highlights(book.id)
            eligible = [h for h in highlights if not h.excluded and not h.needs_recovery and h.kind in ('highlight', 'note')
                        and (h.kind != 'note' or self.options.notes) and h.text.strip()]
            state = self.state(book.id)
            if not eligible and not state:
                continue
            managed = render(book, highlights, self.options)
            baseline = managed
            candidates = [p for p, (_, text) in notes.items() if self._matches(book, text) and p not in claimed]
            if state:
                path = contained(self.target, state['path'])
            else:
                name = safe_filename(self.destination.filename.format(title=book.title, author=', '.join(book.authors), id=book.id))
                folder = self.target / safe_filename(', '.join(book.authors) or 'Unknown author') if self.destination.author_folders else self.target
                path = contained(self.target, folder / (name + '.md'))
                if candidates:
                    path = min(candidates, key=lambda p: (bool(re.search(r' \[[\w-]+\]$', p.stem)), len(p.parts), str(p)))
                elif str(path).casefold() in occupied or path.exists():
                    path = contained(self.target, folder / (name + ' [' + book.id[-8:] + '].md'))
                    counter = 2
                    while path.exists() or str(path).casefold() in occupied:
                        path = contained(self.target, folder / (name + ' [' + book.id[-8:] + ']-' + str(counter) + '.md'))
                        counter += 1
            claimed.update(candidates)
            claimed.add(path)
            occupied.add(str(path).casefold())
            try:
                raw = path.read_bytes() if path.exists() else None
            except OSError:
                changes.append(Change(book.id, book.title, str(path), 'conflict', None,
                                      reason='The destination note could not be read; check its permissions.'))
                continue
            expected = digest(raw) if raw is not None else None
            action, reason, duplicates = 'create', '', []
            content = (frontmatter(book, self.options) + managed).encode('utf-8')
            if book.id in pending:
                action, reason = 'conflict', 'An interrupted write has diverged from both recorded versions.'
            elif state and raw is None:
                action, reason = 'conflict', 'Previously synchronized note is missing; restore it or reset its destination mapping.'
            elif raw is not None:
                try:
                    text = raw.decode('utf-8')
                    match = region(text)
                    extras = [p for p in candidates if p != path]
                    managed = merge(match[0], state['managed'] if state else None, managed,
                                    [region(notes[p][1])[0] for p in extras],
                                    {h.id: order_key(h)[:3] for h in highlights})
                    newline = '\r\n' if '\r\n' in match[0] else '\n'
                    replacement = managed.replace('\n', newline)
                    merged_text = text[:match.start()] + replacement + text[match.end():]
                    for extra in extras:
                        extra_raw, extra_text = notes[extra]
                        extra_region = region(extra_text)
                        outside = extra_text[:extra_region.start()] + extra_text[extra_region.end():]
                        extra_header, _ = split(extra_region[0])
                        expected_header, _ = split(baseline)
                        if extra_header != expected_header:
                            outside += extra_header
                        # Preserve all duplicate-file properties and commentary.
                        section = newline + '## Merged note: ' + inline(extra.name) + newline + newline + outside
                        if outside.strip() and section not in merged_text:
                            merged_text += section
                        duplicates.append((str(extra), digest(extra_raw)))
                    content = merged_text.encode('utf-8')
                    action = 'unchanged' if content == raw and not duplicates else 'update'
                except (ValueError, UnicodeDecodeError) as error:
                    action, reason = 'conflict', str(error)
            changes.append(Change(book.id, book.title, str(path), action, expected, content, baseline, reason, duplicates))
        return changes

    def apply(self, changes, cancelled=lambda: False, progress=lambda value, message: None):
        summary = {'created': 0, 'updated': 0, 'unchanged': 0, 'merged': 0, 'conflicts': 0, 'errors': 0, 'cancelled': False, 'details': []}
        for i, change in enumerate(changes):
            if cancelled():
                summary['cancelled'] = True
                break
            progress(int(i * 100 / max(len(changes), 1)), 'Writing book ' + str(i + 1))
            if change.action in ('conflict', 'unchanged'):
                summary['conflicts' if change.action == 'conflict' else 'unchanged'] += 1
                if change.reason:
                    summary['details'].append(change.book_id + ': ' + change.reason)
                    self.store.event('conflict', change.reason, change.book_id)
                elif change.action == 'unchanged':
                    with self.store.db:
                        self._record(change.book_id, change.path, change.managed)
                continue
            temp_path = None
            try:
                # Revalidate after preview, including symlinks/junctions.
                if validate_destination(self.destination) != (self.vault, self.target):
                    raise ValueError('Destination directory changed since preview; synchronize again.')
                path = contained(self.target, change.path)
                path.parent.mkdir(parents=True, exist_ok=True)
                before = path.read_bytes() if path.exists() else None
                if (digest(before) if before is not None else None) != change.expected_hash:
                    raise ValueError('Note changed since preview; synchronize again.')
                for source, expected in change.duplicates:
                    source = contained(self.target, source)
                    if digest(source.read_bytes()) != expected:
                        raise ValueError('A duplicate note changed since preview; synchronize again.')
                if before is not None:
                    backup_dir = contained(self.vault, self.target / '.kindle-highlights-backups')
                    backup_dir.mkdir(exist_ok=True)
                    backup = contained(backup_dir, backup_dir / (change.book_id + '-' + uuid4().hex + '.md'))
                    with backup.open('xb') as stream:
                        stream.write(before)
                        stream.flush()
                        os.fsync(stream.fileno())
                journal_id = uuid4().hex
                with self.store.db:
                    self.store.db.execute('INSERT INTO sync_journal VALUES(?,?,?,?,?,?,?,?)',
                        (journal_id, self.key, change.book_id, str(path), change.expected_hash,
                         digest(change.content), change.managed, now()))
                fd, temp_path = tempfile.mkstemp(prefix='.khs-', suffix='.tmp', dir=str(path.parent))
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(change.content)
                    stream.flush()
                    os.fsync(stream.fileno())
                # A last check narrows races with external editors.
                current = path.read_bytes() if path.exists() else None
                if (digest(current) if current is not None else None) != change.expected_hash:
                    raise ValueError('Note changed during synchronization; your content was preserved.')
                if validate_destination(self.destination) != (self.vault, self.target):
                    raise ValueError('Destination directory changed during synchronization.')
                contained(self.vault, path)
                os.replace(temp_path, path)
                temp_path = None
                if os.name != 'nt':
                    directory_fd = os.open(str(path.parent), os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                with self.store.db:
                    self._record(change.book_id, path, change.managed)
                    self.store.db.execute('DELETE FROM sync_journal WHERE id=?', (journal_id,))
                for source, expected in change.duplicates:
                    source = contained(self.target, source)
                    if digest(source.read_bytes()) != expected:
                        raise ValueError('A duplicate note changed during synchronization; it was retained.')
                    archive_dir = contained(self.target, self.target / '.kindle-highlights-backups' / 'merged')
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    archive = contained(archive_dir, archive_dir / (source.stem[:50] + '-' + uuid4().hex + '.md'))
                    os.replace(source, archive)
                    summary['merged'] += 1
                    with self.store.db:
                        self.store.db.execute('UPDATE sync_state SET path=?,managed=? WHERE destination=? AND path=?',
                                              (str(path), change.managed, self.key, str(source)))
                summary['created' if change.action == 'create' else 'updated'] += 1
            except Exception as error:
                summary['errors'] += 1
                # Avoid logging arbitrary OS/library exception text with private content.
                message = str(error) if isinstance(error, ValueError) else 'Filesystem operation failed (' + type(error).__name__ + ').'
                summary['details'].append(change.book_id + ': ' + message)
                self.store.event('sync_error', message, change.book_id)
            finally:
                if temp_path:
                    try:
                        Path(temp_path).unlink(missing_ok=True)
                    except OSError:
                        pass
        progress(100, 'Synchronization finished')
        if not summary['errors'] and not summary['conflicts'] and not summary['cancelled']:
            self.store.event('sync_complete', json.dumps({k: v for k, v in summary.items() if k != 'details'}))
        return summary
