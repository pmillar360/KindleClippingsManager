"""Three-way highlight merging; user text stays outside generated layout changes."""
import json
import re

from .markdown import BEGIN, END

REGION = re.compile(r'^' + re.escape(BEGIN) + r'\r?\n.*?^' + re.escape(END) + r'(?:\r?\n|$)', re.M | re.S)
MARKER = re.compile(r'^<!-- khs:([\w-]+) -->\n', re.M)
LAYOUT = re.compile(r'^(?:(?:### [^\n]*|####? (?:Highlight|Note) \d+)\n\n)*')


def region(text):
    matches = list(REGION.finditer(text))
    if len(matches) != 1 or text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError('Managed markers are missing, duplicated, or malformed.')
    return matches[0]


def split(text):
    text = text.replace('\r\n', '\n')
    match = region(text)
    inner = match[0][len(BEGIN) + 1:]
    inner = inner[:inner.rfind(END)]
    markers = list(MARKER.finditer(inner))
    header = inner[:markers[0].start()] if markers else inner
    blocks = {}
    for index, marker in enumerate(markers):
        identity = marker[1]
        if identity in blocks:
            raise ValueError('A highlight marker occurs more than once; review this note.')
        blocks[identity] = inner[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(inner)]
    return header, blocks


def body(block):
    return LAYOUT.sub('', block, count=1)


def signature(block):
    # Only collapse exact passage/note AND coordinates. Same words at distinct
    # positions remain separate; unpositioned annotations require stable IDs.
    text = body(block)
    coordinate = re.findall(r'\*\*Location:\*\* [^\n·]+', text)
    kind = re.search(r'^####? (Highlight|Note) \d+$', block, re.M)
    if not coordinate or not kind:
        return None
    # Compare the entire body, including any commentary after metadata. Case,
    # whitespace, dates and personal edits must never disappear in deduplication.
    # Old Markdown does not identify KFX coordinate systems, so those blocks need
    # stable matching IDs rather than a coincidentally equal numeric PID.
    return kind[1], text


def block_order(block):
    text = body(block)
    for group, label in enumerate(('Location', 'KFX position', 'Page')):
        match = re.search(r'\*\*' + label + r':\*\* (\d+)', text)
        if match:
            return group, '', int(match[1])
    return 3, '', 0


def merge(current, previous, desired, extras=(), positions=None):
    header, actual = split(current)
    old_header, baseline = split(previous) if previous else (header, {})
    new_header, generated = split(desired)
    for extra in extras:
        _, additional = split(extra)
        for identity, block in additional.items():
            if identity in actual and body(actual[identity]) != body(block):
                raise ValueError('Duplicate notes contain conflicting edits to the same highlight.')
            actual.setdefault(identity, block)
    result = {}
    for identity in dict.fromkeys([*actual, *generated]):
        local, old, new = actual.get(identity), baseline.get(identity), generated.get(identity)
        if local is None:
            # A manually deleted exported block stays deleted.
            if old is None and new is not None:
                result[identity] = new
            continue
        if new is None:
            if old is None:
                result[identity] = local  # unknown historical highlight
            elif body(local) != body(old):
                raise ValueError('An edited highlight was excluded or removed; review before removing it.')
            continue
        if old is not None and body(local) != body(old) and body(new) != body(old) and body(local) != body(new):
            raise ValueError('A highlight changed both in the plugin and in Obsidian; your edits are preserved.')
        selected = local if old is None or body(local) != body(old) else new
        # Regenerate only numbering/chapter headings, retaining passage/commentary.
        layout = new[:len(new) - len(body(new))]
        result[identity] = layout + body(selected)
    # Different historic IDs can denote the same highlight after later matching.
    seen, unique = {}, {}
    for identity in sorted(result, key=lambda identity: identity not in generated):
        block = result[identity]
        key = signature(block)
        if key is not None and key in seen:
            continue
        if key is not None:
            seen[key] = identity
        unique[identity] = block
    # Current renderer order is authoritative for known blocks. Insert historical
    # blocks by their recorded coordinates without comparing KFX PIDs to locations.
    ranks = {identity: index for index, identity in enumerate(generated)}
    positions = positions or {}
    identities = sorted(unique, key=lambda identity: (*positions.get(identity, block_order(unique[identity])), ranks.get(identity, len(ranks))))
    parts = []
    chapter = None
    chapters, current_chapter = {}, 'Other highlights'
    for identity, block in generated.items():
        heading = re.match(r'^### (?!Highlight \d|Note \d)([^\n]+)\n', block)
        if heading:
            current_chapter = heading[1]
        chapters[identity] = current_chapter
    grouped = any(re.match(r'^### (?!Highlight \d|Note \d)', b) for b in generated.values())
    for number, identity in enumerate(identities, 1):
        block = unique[identity]
        # A new middle highlight renumbers headings without rewriting passages.
        block = re.sub(r'^(####? (?:Highlight|Note)) \d+$', lambda m: m[1] + ' ' + str(number), block, flags=re.M)
        if grouped:
            match = re.search(r'\*\*Chapter:\*\* ([^\n·]+)', block)
            label = chapters.get(identity, match[1].strip() if match else 'Other highlights')
            block = re.sub(r'^### (?!Highlight \d|Note \d)[^\n]*\n\n', '', block)
            if label != chapter:
                block = '### ' + label + '\n\n' + block
                chapter = label
        parts += [f'<!-- khs:{identity} -->\n' + block]
    return BEGIN + '\n' + (new_header if header == old_header else header) + ''.join(parts) + END + '\n'


def properties(text):
    values = {}
    if text.startswith('---\n') or text.startswith('---\r\n'):
        yaml = text.replace('\r\n', '\n').split('---\n', 2)
        if len(yaml) == 3:
            for line in yaml[1].splitlines():
                key, separator, value = line.partition(': ')
                if separator:
                    try:
                        values[key] = json.loads(value)
                    except ValueError:
                        values[key] = value.strip().strip('\'"')
    return values
