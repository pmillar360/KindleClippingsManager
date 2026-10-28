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
    values = {'title': book.title, 'author': ', '.join(book.authors), 'tags': ['books', 'highlights']}
    if book.series:
        values['series'] = book.series
    if book.published:
        values['published'] = book.published
    if book.identifiers:
        values['identifiers'] = book.identifiers
    return '---\n' + '\n'.join(k + ': ' + json.dumps(v, ensure_ascii=False) for k, v in values.items()) + '\n---\n\n'


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
    active.sort(key=lambda h: (h.position_start if h.position_start is not None else h.location_start if h.location_start is not None else 2**63, h.created_at or '', h.id))
    for number, h in enumerate(active, 1):
        lines += [f'<!-- khs:{h.id} -->']
        label = 'Note' if h.kind == 'note' else 'Highlight'
        if options.numbering:
            lines += [f'### {label} {number}', '']
        lines += [passage(h.text, options.blockquotes), '']
        if options.notes and h.note:
            lines += ['**Note:**', passage(h.note, options.blockquotes), '']
        if options.positions:
            if h.page:
                lines.append('**Page:** ' + inline(h.page))
            if h.location_start is not None:
                location = str(h.location_start)
                if h.location_end is not None and h.location_end != h.location_start:
                    location += '–' + str(h.location_end)
                lines.append('**Location:** ' + location)
            elif h.position_start is not None:
                # Never mislabel a KFX PID as a Kindle location.
                lines.append('**KFX position:** ' + str(h.position_start) + ('–' + str(h.position_end) if h.position_end != h.position_start else ''))
            if h.chapter:
                lines.append('**Chapter:** ' + inline(h.chapter))
        if options.dates and h.created_at:
            try:
                date = datetime.fromisoformat(h.created_at).strftime(options.date_format)
                lines.append('**Highlighted:** ' + inline(date))
            except (ValueError, TypeError):
                pass
        lines.append('')
    lines += [END]
    return '\n'.join(lines) + '\n'
