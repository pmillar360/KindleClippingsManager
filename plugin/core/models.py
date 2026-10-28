from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
import hashlib
import json
import re
import unicodedata


def normalize(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value or '').casefold()).strip()


def text_key(value):
    return normalize(value)


def stable_id(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:32]


@dataclass
class BookFormat:
    format: str
    path: str
    source: str = 'device'


@dataclass
class Book:
    title: str
    authors: list[str] = field(default_factory=list)
    id: str = ''
    identifiers: dict = field(default_factory=dict)
    calibre_id: int | None = None
    library_id: str | None = None
    series: str | None = None
    published: str | None = None
    formats: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = 'book-' + stable_id(normalize(self.title), [normalize(a) for a in self.authors])


@dataclass
class Highlight:
    book_id: str
    text: str
    id: str = ''
    kind: str = 'highlight'
    note: str | None = None
    location_start: int | None = None
    location_end: int | None = None
    position_start: int | None = None
    position_end: int | None = None
    position_system: str | None = None
    mapped_location_start: int | None = None
    mapped_location_end: int | None = None
    page: str | None = None
    chapter: str | None = None
    created_at: str | None = None
    created_raw: str | None = None
    source: str = 'clippings'
    source_id: str = ''
    source_book_id: str = ''
    source_path: str = ''
    ordinal: int = 0
    meta_raw: str | None = None
    needs_recovery: bool = False
    excluded: bool = False

    def __post_init__(self):
        if not self.source_book_id:
            self.source_book_id = self.book_id
        if not self.source_id:
            self.source_id = stable_id(self.source_book_id, self.kind, self.location_start, self.location_end,
                                       self.position_start, self.position_end, self.position_system,
                                       self.page if self.location_start is None and self.position_start is None else None,
                                       text_key(self.text), self.created_at or self.created_raw)
        if not self.id:
            self.id = 'hl-' + stable_id(self.source, self.source_id)


@dataclass
class ImportSource:
    path: str
    backend: str
    fingerprint: str


@dataclass
class ImportBatch:
    books: list[Book] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)
    sources: list[ImportSource] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recovery_failures: int = 0


@dataclass
class SyncDestination:
    vault: str
    folder: str = 'Books/Highlights'
    filename: str = '{title}'


@dataclass
class SyncState:
    book_id: str
    path: str
    managed: str
    synced_at: str


def encode(obj):
    return json.dumps(asdict(obj), ensure_ascii=False, sort_keys=True)


def decode(cls, data):
    obj = json.loads(data)
    return cls(**{f.name: obj[f.name] for f in fields(cls) if f.name in obj})


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')
