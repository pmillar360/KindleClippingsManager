"""Multilingual clippings parser, ported from KCM; never changes its source."""
from datetime import datetime
from pathlib import Path
import hashlib
import re

from ..core.models import Book, Highlight, ImportBatch, ImportSource, stable_id

LANGUAGES = [
    'january february march april may june july august september october november december',
    'januar februar märz april mai juni juli august september oktober november dezember',
    'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre',
    'janvier février mars avril mai juin juillet août septembre octobre novembre décembre',
    'gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre',
    'janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro',
    'januari februari maart april mei juni juli augustus september oktober november december',
]
MONTHS = {name: i + 1 for language in LANGUAGES for i, name in enumerate(language.split())}
TYPES = {
    'highlight': 'highlight', 'markierung': 'highlight', 'subrayado': 'highlight',
    'resaltado': 'highlight', 'surlignement': 'highlight', 'evidenziazione': 'highlight',
    'destaque': 'highlight', 'markering': 'highlight', 'bookmark': 'bookmark',
    'lesezeichen': 'bookmark', 'marcador': 'bookmark', 'signet': 'bookmark',
    'segnalibro': 'bookmark', 'bladwijzer': 'bookmark', 'note': 'note', 'notiz': 'note',
    'nota': 'note', 'notitie': 'note',
}
LIMIT = re.compile(
    r'^<?(?:You have reached (?:the )?(?:clipping|export) limit for this (?:item|book)[.!]?'
    r'|Sie haben die (?:zulässige )?(?:Ausschneidegrenze|Exportgrenze) für '
    r'(?:diesen Artikel|dieses Buch) erreicht[.!]?)>?$', re.I)
PAGE = re.compile(r'\b(page|seite|página|pagina|pag\.|bladzijde)\b', re.I)


def parse_date(raw):
    time = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?', raw, re.I)
    year = re.search(r'\b((?:19|20)\d{2})\b', raw)
    if not time or not year:
        return None
    rest = raw[:time.start()] + raw[time.end():]
    rest = re.sub(r'\b' + year[1] + r'\b', '', rest)
    month = next((MONTHS[token.casefold()] for token in re.findall(r'[^\W\d_]+', rest)
                  if token.casefold() in MONTHS), None)
    day = re.search(r'\b(\d{1,2})\b', rest)
    if not month or not day:
        return None
    hour = int(time[1])
    if time[4]:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if time[4].upper() == 'PM' else 0)
    try:
        return datetime(int(year[1]), month, int(day[1]), hour, int(time[2]), int(time[3] or 0)).isoformat()
    except ValueError:
        return None


def title_author(line):
    if line.endswith(')') and '(' in line:
        title, author = line.rsplit('(', 1)
        return title.strip(), [author[:-1].strip()] if author[:-1].strip() else []
    return line.strip(), []


def parse(text, source_path=''):
    result = ImportBatch()
    books = {}
    occurrences = {}
    entries = re.split(r'^\s*==========\s*$', text.lstrip('\ufeff').replace('\r\n', '\n'), flags=re.M)
    for ordinal, raw in enumerate(entries):
        if not raw.strip():
            continue
        lines = raw.strip().split('\n')
        if len(lines) < 2 or not lines[1].lstrip().startswith('- '):
            result.warnings.append(f'Clippings entry {ordinal + 1}: malformed header; skipped.')
            continue
        meta = lines[1].strip()
        segments = [s.strip() for s in meta.split('|')]
        if len(segments) < 2:
            result.warnings.append(f'Clippings entry {ordinal + 1}: missing metadata; skipped.')
            continue
        title, authors = title_author(lines[0])
        book = Book(title, authors)
        books[book.id] = book
        words = re.findall(r'[^\W\d_]+', segments[0].casefold())
        kind = next((TYPES[w] for w in words if w in TYPES), 'unknown')
        if kind == 'unknown':
            result.warnings.append(f'Clippings entry {ordinal + 1}: unknown annotation type; retained for review.')
        location_segment = segments[-2]
        # A page-only entry must never invent a Kindle location.
        page_only = len(segments) == 2 and bool(PAGE.search(location_segment))
        numbers = re.search(r'(\d+)\s*[-–]\s*(\d+)', location_segment)
        single = re.findall(r'\d+', location_segment)
        start = (int(numbers[1]) if numbers else int(single[-1]) if single else None) if not page_only else None
        end = (int(numbers[2]) if numbers else start) if start is not None else None
        page_numbers = re.findall(r'\d+', segments[0]) if len(segments) >= 3 or page_only else []
        raw_date = re.sub(r'^(Added on|Hinzugefügt am|Añadido el|Agregado el|Ajouté le|Aggiunto il|Adicionado em|Toegevoegd op)\s+', '', segments[-1], flags=re.I)
        content = '\n'.join(lines[2:]).strip()
        missing = bool(LIMIT.search(content))
        highlight = Highlight(
            book.id, '' if missing else content, kind=kind, location_start=start,
            location_end=end, page=page_numbers[-1] if page_numbers else None,
            created_at=parse_date(raw_date), created_raw=raw_date,
            source_path=source_path, ordinal=ordinal, meta_raw=meta, needs_recovery=missing)
        if start is None:
            # Identical text without reliable positions is ambiguous. Preserve
            # repeated occurrences, while keeping each occurrence idempotent.
            signature = highlight.source_id
            occurrence = occurrences.get(signature, 0)
            occurrences[signature] = occurrence + 1
            highlight.source_id = stable_id(signature, occurrence)
            highlight.id = 'hl-' + stable_id(highlight.source, highlight.source_id)
        result.highlights.append(highlight)
    result.books = list(books.values())
    return result


def read(path):
    path = Path(path)
    data = path.read_bytes()
    result = parse(data.decode('utf-8-sig'), str(path))
    result.sources.append(ImportSource(str(path), 'clippings', hashlib.sha256(data).hexdigest()))
    return result


def serialize(books, highlights):
    """Cleaned copy only; caller chooses a separate output path."""
    by_id = {b.id: b for b in books}
    entries = []
    for h in sorted(highlights, key=lambda h: (h.source_path, h.ordinal)):
        if h.excluded or h.needs_recovery:
            continue
        b = by_id[h.book_id]
        title = b.title + (' (' + ', '.join(b.authors) + ')' if b.authors else '')
        meta = h.meta_raw
        if not meta:
            # KFX PID coordinates cannot be serialized as Kindle locations.
            if h.location_start is None:
                continue
            loc = str(h.location_start)
            if h.location_end is not None and h.location_end != h.location_start:
                loc += '-' + str(h.location_end)
            meta = f'- Your {h.kind.title()} at location {loc} | Added on {h.created_raw or h.created_at or ""}'
        entries.append(f'{title}\n{meta}\n\n{h.text}\n==========')
    return '\n'.join(entries) + ('\n' if entries else '')
