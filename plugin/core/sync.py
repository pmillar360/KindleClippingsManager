"""Conservative file ownership, crash journal, and atomic note replacement."""
from dataclasses import dataclass
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
        changes, occupied = [], set()
        for row in self.store.db.execute('SELECT path FROM sync_state WHERE destination=?', (self.key,)):
            occupied.add(str(Path(row[0]).resolve()).casefold())
        for book in self.store.books():
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
            if state:
                path = contained(self.target, state['path'])
            else:
                name = safe_filename(self.destination.filename.format(title=book.title, author=', '.join(book.authors), id=book.id))
                path = contained(self.target, self.target / (name + '.md'))
                if str(path).casefold() in occupied or path.exists():
                    path = contained(self.target, self.target / (name + ' [' + book.id[-8:] + '].md'))
            occupied.add(str(path).casefold())
            try:
                raw = path.read_bytes() if path.exists() else None
            except OSError:
                changes.append(Change(book.id, book.title, str(path), 'conflict', None,
                                      reason='The destination note could not be read; check its permissions.'))
                continue
            expected = digest(raw) if raw is not None else None
            action, reason = 'create', ''
            content = (frontmatter(book, self.options) + managed).encode('utf-8')
            if book.id in pending:
                action, reason = 'conflict', 'An interrupted write has diverged from both recorded versions.'
            elif state and raw is None:
                action, reason = 'conflict', 'Previously synchronized note is missing; restore it or reset its destination mapping.'
            elif raw is not None:
                if not state:
                    action, reason = 'conflict', 'Destination exists and is not owned by this plugin.'
                else:
                    try:
                        text = raw.decode('utf-8')
                    except UnicodeDecodeError:
                        text = ''
                    pattern = re.compile(r'^' + re.escape(BEGIN) + r'\r?\n.*?^' + re.escape(END) + r'(?:\r?\n|$)', re.M | re.S)
                    regions = list(pattern.finditer(text))
                    if len(regions) != 1 or text.count(BEGIN) != 1 or text.count(END) != 1:
                        action, reason = 'conflict', 'Managed markers are missing, duplicated, or malformed.'
                    elif regions[0][0].replace('\r\n', '\n') != state['managed'].replace('\r\n', '\n'):
                        action, reason = 'conflict', 'Managed highlights were edited in Obsidian; your edits are preserved.'
                    else:
                        match = regions[0]
                        newline_managed = managed.replace('\n', '\r\n') if '\r\n' in match[0] else managed
                        content = (text[:match.start()] + newline_managed + text[match.end():]).encode('utf-8')
                        action = 'unchanged' if content == raw else 'update'
            changes.append(Change(book.id, book.title, str(path), action, expected, content, managed, reason))
        return changes

    def apply(self, changes, cancelled=lambda: False, progress=lambda value, message: None):
        summary = {'created': 0, 'updated': 0, 'unchanged': 0, 'conflicts': 0, 'errors': 0, 'cancelled': False, 'details': []}
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
