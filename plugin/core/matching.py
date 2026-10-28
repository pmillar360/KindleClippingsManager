from dataclasses import replace
import re
from .models import normalize, stable_id


def author_key(author):
    if ',' in author:
        last, first = author.split(',', 1)
        author = first + ' ' + last
    return re.sub(r'[^\w\s]', '', normalize(author))


def canonical(book, library_id):
    return replace(book, id='calibre-' + stable_id(library_id, book.calibre_id), library_id=library_id)


class Matcher:
    def __init__(self, books=(), device_mappings=None):
        self.books = list(books)
        self.device_mappings = device_mappings or {}

    def match(self, source):
        if source.id in self.device_mappings:
            choices = [b for b in self.books if b.id == self.device_mappings[source.id]]
        else:
            def ids(book):
                return {k.casefold(): normalize(str(v)).replace('-', '') for k, v in book.identifiers.items() if v}
            source_ids = ids(source)
            choices = []
            for book in self.books:
                target_ids = ids(book)
                common = source_ids.keys() & target_ids.keys()
                if common and all(source_ids[k] == target_ids[k] for k in common):
                    choices.append(book)
            if not choices:
                choices = [b for b in self.books if normalize(b.title) == normalize(source.title)
                           and source.authors and {author_key(a) for a in b.authors} == {author_key(a) for a in source.authors}
                           and not any(source_ids[k] != ids(b)[k] for k in source_ids.keys() & ids(b).keys())]
        if len(choices) == 1:
            return choices[0], None
        if len(choices) > 1:
            return source, 'Ambiguous library match; select the edition in Manage highlights.'
        return source, None
