"""Separate SQLite state, stable source aliases, and durable exclusion decisions."""
from dataclasses import replace
from pathlib import Path
import json
import sqlite3
from datetime import datetime
from uuid import uuid4

from .models import Book, Highlight, decode, encode, now, text_key

MIGRATIONS = [
    '''CREATE TABLE books(id TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE book_aliases(alias TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id));
    CREATE TABLE highlights(id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id), data TEXT NOT NULL);
    CREATE INDEX highlights_book ON highlights(book_id);
    CREATE TABLE provenance(backend TEXT NOT NULL, source_id TEXT NOT NULL, highlight_id TEXT NOT NULL REFERENCES highlights(id),
        source_path TEXT NOT NULL, PRIMARY KEY(backend, source_id));
    CREATE TABLE exclusions(kind TEXT NOT NULL, entity_id TEXT NOT NULL, PRIMARY KEY(kind, entity_id));
    CREATE TABLE edits(highlight_id TEXT PRIMARY KEY REFERENCES highlights(id), text TEXT NOT NULL);
    CREATE TABLE imports(id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, summary TEXT);
    CREATE TABLE sources(path TEXT NOT NULL, backend TEXT NOT NULL, fingerprint TEXT NOT NULL, batch_id TEXT NOT NULL,
        PRIMARY KEY(path, backend));
    CREATE TABLE sync_state(destination TEXT NOT NULL, book_id TEXT NOT NULL, path TEXT NOT NULL,
        managed TEXT NOT NULL, synced_at TEXT NOT NULL, PRIMARY KEY(destination, book_id));
    CREATE TABLE sync_journal(id TEXT PRIMARY KEY, destination TEXT NOT NULL, book_id TEXT NOT NULL,
        path TEXT NOT NULL, previous_hash TEXT, next_hash TEXT NOT NULL, managed TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE events(id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, book_id TEXT, message TEXT NOT NULL);
    CREATE TABLE mappings(source_id TEXT PRIMARY KEY, library_book_id TEXT NOT NULL);
    '''
]


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=20000')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > len(MIGRATIONS):
            self.db.close()
            raise ValueError('State database was created by a newer plugin version.')
        for index in range(version, len(MIGRATIONS)):
            try:
                self.db.executescript('BEGIN IMMEDIATE;\n' + MIGRATIONS[index] + f'\nPRAGMA user_version={index + 1};\nCOMMIT;')
            except Exception:
                self.db.close()
                raise

    def close(self):
        self.db.close()

    def event(self, kind, message, book_id=None):
        with self.db:
            self.db.execute('INSERT INTO events(created_at,kind,book_id,message) VALUES(?,?,?,?)',
                            (now(), kind, book_id, message))

    def excluded(self, kind, entity_id):
        return self.db.execute('SELECT 1 FROM exclusions WHERE kind=? AND entity_id=?', (kind, entity_id)).fetchone() is not None

    def exclude(self, kind, entity_id, value=True):
        if kind not in ('book', 'highlight'):
            raise ValueError('Invalid exclusion type')
        with self.db:
            if value:
                self.db.execute('INSERT OR IGNORE INTO exclusions VALUES(?,?)', (kind, entity_id))
            else:
                self.db.execute('DELETE FROM exclusions WHERE kind=? AND entity_id=?', (kind, entity_id))

    def books(self):
        return [decode(Book, r[0]) for r in self.db.execute('SELECT data FROM books ORDER BY id')]

    def highlights(self, book_id=None, edited=True):
        query = 'SELECT data FROM highlights' + (' WHERE book_id=?' if book_id else '') + ' ORDER BY rowid'
        result = [decode(Highlight, r[0]) for r in self.db.execute(query, (book_id,) if book_id else ())]
        for h in result:
            h.excluded = self.excluded('highlight', h.id)
            override = self.db.execute('SELECT text FROM edits WHERE highlight_id=?', (h.id,)).fetchone() if edited else None
            if override:
                h.text = override[0]
                if h.text.strip():
                    h.needs_recovery = False
        return result

    def edit(self, highlight_id, text):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO edits VALUES(?,?)', (highlight_id, text))

    def reset_edit(self, highlight_id):
        with self.db:
            self.db.execute('DELETE FROM edits WHERE highlight_id=?', (highlight_id,))

    def mappings(self):
        return dict(self.db.execute('SELECT source_id,library_book_id FROM mappings'))

    def map_book(self, source_id, target):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO mappings VALUES(?,?)', (source_id, target.id))
            self._save_book(target, source_id)

    def _save_book(self, book, source_id):
        alias = self.db.execute('SELECT book_id FROM book_aliases WHERE alias=?', (source_id,)).fetchone()
        old_id = alias[0] if alias else source_id
        # Once matched, a temporary missing library must not demote canonical metadata.
        if alias and old_id.startswith('calibre-') and not book.id.startswith('calibre-'):
            return old_id
        self.db.execute('INSERT INTO books VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (book.id, encode(book)))
        if old_id != book.id and self.db.execute('SELECT 1 FROM books WHERE id=?', (old_id,)).fetchone():
            for h in self.highlights(old_id, edited=False):
                h.book_id = book.id
                self.db.execute('UPDATE highlights SET book_id=?,data=? WHERE id=?', (book.id, encode(h), h.id))
            if self.excluded('book', old_id):
                self.db.execute('INSERT OR IGNORE INTO exclusions VALUES(?,?)', ('book', book.id))
            # Preserve existing note path/ownership during later library matching.
            self.db.execute('UPDATE OR IGNORE sync_state SET book_id=? WHERE book_id=?', (book.id, old_id))
            self.db.execute('UPDATE book_aliases SET book_id=? WHERE book_id=?', (book.id, old_id))
            self.db.execute('DELETE FROM books WHERE id=?', (old_id,))
        self.db.execute('INSERT OR REPLACE INTO book_aliases VALUES(?,?)', (source_id, book.id))
        return book.id

    @staticmethod
    def same_annotation(a, b):
        if a.kind != b.kind:
            return False
        if a.position_start is not None and b.position_start is not None and a.position_system == b.position_system:
            same_span = (a.position_start, a.position_end) == (b.position_start, b.position_end)
        elif a.location_start is not None and b.location_start is not None:
            same_span = (a.location_start, a.location_end) == (b.location_start, b.location_end)
        else:
            # Cross-coordinate evidence: exact text AND exact creation timestamp,
            # with a unique candidate checked by the caller. No fuzzy guessing.
            def timestamp(value):
                try:
                    return datetime.fromisoformat(value).isoformat(timespec='seconds')
                except (ValueError, TypeError):
                    return None
            stamp = timestamp(a.created_at)
            same_span = bool(a.source != b.source and stamp and stamp == timestamp(b.created_at) and a.text and b.text)
        text_equal = text_key(a.text) == text_key(b.text)
        return same_span and (text_equal or a.needs_recovery or b.needs_recovery)

    def ingest(self, batch, matcher):
        batch_id = str(uuid4())
        stats = {'imported': len(batch.highlights), 'new': 0, 'existing': 0, 'duplicates': 0, 'warnings': list(batch.warnings),
                 'recovery_failures': batch.recovery_failures}
        with self.db:
            self.db.execute('INSERT INTO imports VALUES(?,?,NULL,NULL)', (batch_id, now()))
            mapping = {}
            for source in batch.books:
                book, warning = matcher.match(source)
                if warning:
                    stats['warnings'].append(warning + ' Source book ID: ' + source.id)
                mapping[source.id] = self._save_book(book, source.id)
            cache = {}
            # Confirm an embedded KFX location map against at least two known
            # clippings in the same canonical book before using it for merging
            # clipping-limit placeholders. Unverified coordinates stay separate.
            all_incoming = [replace(h, book_id=mapping.get(h.book_id, h.book_id)) for h in batch.highlights]
            trusted_systems = set()
            for system in {h.position_system for h in all_incoming if h.position_system}:
                pairs = []
                for recovered in (h for h in all_incoming if h.position_system == system and h.mapped_location_start is not None):
                    known = [h for h in all_incoming if h.book_id == recovered.book_id and h.source == 'clippings'
                             and h.text and text_key(h.text) == text_key(recovered.text) and h.location_start is not None]
                    if len(known) == 1:
                        pairs.append(((known[0].location_start, known[0].location_end),
                                      (recovered.mapped_location_start, recovered.mapped_location_end)))
                if len(pairs) >= 2 and len({a for a, _ in pairs}) >= 2 and all(a == b for a, b in pairs):
                    trusted_systems.add(system)
            for original in batch.highlights:
                h = replace(original, book_id=mapping.get(original.book_id, original.book_id))
                if h.position_system in trusted_systems:
                    h.location_start, h.location_end = h.mapped_location_start, h.mapped_location_end
                if h.book_id not in cache:
                    cache[h.book_id] = self.highlights(h.book_id, edited=False)
                candidates = cache[h.book_id]
                alias = self.db.execute('SELECT highlight_id FROM provenance WHERE backend=? AND source_id=?',
                                        (h.source, h.source_id)).fetchone()
                match = next((x for x in candidates if alias and x.id == alias[0]), None)
                if match is None:
                    matches = [x for x in candidates if self.same_annotation(x, h)]
                    if len(matches) == 1:
                        match = matches[0]
                    elif len(matches) > 1:
                        stats['warnings'].append('Ambiguous duplicate retained for review. Book ID: ' + h.book_id)
                if match:
                    stats['existing'] += 1
                    stats['duplicates'] += 1
                    # Preserve the canonical ID, raw source, and every known coordinate.
                    for name in ('location_start', 'location_end', 'position_start', 'position_end', 'position_system',
                                 'page', 'chapter', 'created_at', 'note'):
                        if getattr(match, name) is None and getattr(h, name) is not None:
                            setattr(match, name, getattr(h, name))
                    if match.needs_recovery and not h.needs_recovery:
                        match.text = h.text
                        match.needs_recovery = False
                    self.db.execute('UPDATE highlights SET data=? WHERE id=?', (encode(match), match.id))
                    identity = match.id
                else:
                    self.db.execute('INSERT INTO highlights VALUES(?,?,?)', (h.id, h.book_id, encode(h)))
                    candidates.append(h)
                    identity = h.id
                    stats['new'] += 1
                self.db.execute('INSERT OR REPLACE INTO provenance VALUES(?,?,?,?)',
                                (h.source, h.source_id, identity, h.source_path))
            for source in batch.sources:
                self.db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?)',
                                (source.path, source.backend, source.fingerprint, batch_id))
            self.db.execute('UPDATE imports SET finished_at=?,summary=? WHERE id=?', (now(), json.dumps(stats), batch_id))
        return stats

    def provenance(self, highlight_id):
        return [dict(r) for r in self.db.execute('SELECT backend,source_id,source_path FROM provenance WHERE highlight_id=?', (highlight_id,))]
