from dataclasses import dataclass
from datetime import datetime
import html
import json
import re

BEGIN = '<!-- kindle-highlights-sync:begin -->'
END = '<!-- kindle-highlights-sync:end -->'


@dataclass
class MarkdownOptions:
    blockquotes: bool = True
    numbering: bool = True
    positions: bool = True
    dates: bool = True
    date_format: str = '%Y-%m-%d'
    yaml: bool = True
    notes: bool = True
    compact: bool = False
    group_chapters: bool = False


def inline(value):
    return re.sub(r'([\\`*_\[\]#])', r'\\\1', html.escape(str(value), quote=False).replace('\n', ' '))


def passage(text, quoted):
    # Escape our control markers even in non-blockquote output.
    # Escape HTML and control markers, preserving literal entity text as well.
    text = html.escape(text, quote=False)
    if quoted:
        return '\n'.join('> ' + line if line else '>' for line in text.split('\n'))
    return text


def frontmatter(book, options):
    if not options.yaml:
        return ''
    values = {'title': book.title, 'author': ', '.join(book.authors), 'khs_book_id': book.id,
              'tags': ['books', 'highlights']}
    if book.series:
        values['series'] = book.series
    if book.published:
        values['published'] = book.published
    if book.identifiers:
        values['identifiers'] = book.identifiers
    return '---\n' + '\n'.join(k + ': ' + json.dumps(v, ensure_ascii=False) for k, v in values.items()) + '\n---\n\n'


def order_key(h):
    # Keep coordinate systems distinct; mapped Kindle locations take precedence.
    # Unmapped KFX coordinates form their own ordered group after locations.
    if h.location_start is not None:
        coordinate = (0, '', h.location_start)
    elif h.position_start is not None:
        coordinate = (1, h.position_system or '', h.position_start)
    else:
        coordinate = (3, '', 0)
    return (*coordinate, h.created_at or '', h.id)


def ordered(highlights):
    return sorted(highlights, key=order_key)


def render(book, highlights, options=None):
    options = options or MarkdownOptions()
    lines = [BEGIN, '# ' + inline(book.title), '']
    if book.authors:
        lines += ['**Author:** ' + inline(', '.join(book.authors)), '']
    if book.series:
        lines += ['**Series:** ' + inline(book.series), '']
    lines += ['## Highlights', '']
    active = [h for h in highlights if not h.excluded and not h.needs_recovery and h.kind in ('highlight', 'note')
              and (h.kind != 'note' or options.notes) and h.text.strip()]
    active = ordered(active)
    chapter = object()
    for number, h in enumerate(active, 1):
        lines += [f'<!-- khs:{h.id} -->']
        if options.group_chapters and h.chapter != chapter:
            chapter = h.chapter
            lines += ['### ' + inline(chapter or 'Other highlights'), '']
        label = 'Note' if h.kind == 'note' else 'Highlight'
        if options.numbering:
            lines += [('####' if options.group_chapters else '###') + f' {label} {number}', '']
        lines += [passage(h.text, options.blockquotes), '']
        if options.notes and h.note:
            lines += ['**Note:**', passage(h.note, options.blockquotes), '']
        metadata = []
        if options.positions:
            if h.page:
                metadata.append('**Page:** ' + inline(h.page))
            if h.location_start is not None:
                location = str(h.location_start)
                if h.location_end is not None and h.location_end != h.location_start:
                    location += '–' + str(h.location_end)
                metadata.append('**Location:** ' + location)
            elif h.position_start is not None:
                # Never mislabel a KFX PID as a Kindle location.
                metadata.append('**KFX position:** ' + str(h.position_start) + ('–' + str(h.position_end) if h.position_end is not None and h.position_end != h.position_start else ''))
            if h.chapter:
                metadata.append('**Chapter:** ' + inline(h.chapter))
        if options.dates and h.created_at:
            try:
                date = datetime.fromisoformat(h.created_at).strftime(options.date_format)
                metadata.append('**Highlighted:** ' + inline(date))
            except (ValueError, TypeError):
                pass
        lines += ([' · '.join(metadata)] if options.compact and metadata else metadata)
        lines.append('')
    lines += [END]
    return '\n'.join(lines) + '\n'
