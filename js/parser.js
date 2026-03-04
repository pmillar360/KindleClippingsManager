/**
 * Parses a Kindle "My Clippings.txt" file into a structured data model.
 * Supports multiple Kindle languages (English, German, Spanish, French, Italian, Portuguese, Dutch).
 */

const SEPARATOR = '==========';

/**
 * Map of known clipping type keywords across Kindle languages to normalized English types.
 */
const TYPE_KEYWORDS = {
  // English
  highlight: 'Highlight', bookmark: 'Bookmark', note: 'Note',
  // German
  markierung: 'Highlight', lesezeichen: 'Bookmark', notiz: 'Note',
  // Spanish
  subrayado: 'Highlight', resaltado: 'Highlight', marcador: 'Bookmark', nota: 'Note',
  // French
  surlignement: 'Highlight', signet: 'Bookmark',
  // Italian
  evidenziazione: 'Highlight', segnalibro: 'Bookmark',
  // Portuguese
  destaque: 'Highlight',
  // Dutch
  markering: 'Highlight', bladwijzer: 'Bookmark', notitie: 'Note',
};

const TYPE_PATTERN = new RegExp(
  '\\b(' + Object.keys(TYPE_KEYWORDS).join('|') + ')\\b', 'i'
);

/**
 * Map of month names across Kindle languages to 0-based month index.
 */
const MONTH_MAP = {};
const MONTHS_BY_LANG = {
  en: ['january','february','march','april','may','june','july','august','september','october','november','december'],
  de: ['januar','februar','märz','april','mai','juni','juli','august','september','oktober','november','dezember'],
  es: ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'],
  fr: ['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'],
  it: ['gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre'],
  pt: ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'],
  nl: ['januari','februari','maart','april','mei','juni','juli','augustus','september','oktober','november','december'],
};
for (const months of Object.values(MONTHS_BY_LANG)) {
  months.forEach((name, idx) => { MONTH_MAP[name] = idx; });
}

/**
 * Parse the full text of a My Clippings.txt file.
 * Returns { books: Book[], clippingOrder: string[] }
 * where clippingOrder tracks original order by clipping id.
 */
export function parseClippings(text) {
  // Strip BOM if present
  if (text.charCodeAt(0) === 0xFEFF) {
    text = text.slice(1);
  }

  const rawEntries = text.split(SEPARATOR).map(s => s.trim()).filter(Boolean);
  const booksMap = new Map(); // key: bookId -> Book
  const clippingOrder = []; // track original order
  let clippingIndex = 0;

  for (const raw of rawEntries) {
    const parsed = parseEntry(raw, clippingIndex);
    if (!parsed) continue;

    const { bookTitle, bookAuthor, clipping } = parsed;
    const bookId = makeBookId(bookTitle, bookAuthor);

    if (!booksMap.has(bookId)) {
      booksMap.set(bookId, {
        id: bookId,
        title: bookTitle,
        author: bookAuthor,
        clippings: []
      });
    }

    booksMap.get(bookId).clippings.push(clipping);
    clippingOrder.push(clipping.id);
    clippingIndex++;
  }

  const books = Array.from(booksMap.values());

  // Sort clippings within each book by location
  for (const book of books) {
    book.clippings.sort((a, b) => a.locationStart - b.locationStart);
  }

  return { books, clippingOrder };
}

/**
 * Parse a single clipping entry (text between separators).
 */
function parseEntry(raw, index) {
  const lines = raw.split('\n');
  if (lines.length < 2) return null;

  const titleLine = lines[0].trim();
  const metaLine = lines[1].trim();

  // The clipping text is everything after the blank line (line index 2+)
  // Line 2 is typically blank, text starts at line 3
  const textLines = lines.slice(2);
  // Remove leading empty lines, keep trailing as-is
  const text = textLines.join('\n').trim();

  // Parse title and author from first line
  // Format: "Book Title (Author Name)"
  const titleAuthor = parseTitleAuthor(titleLine);
  if (!titleAuthor) return null;

  // Parse metadata line
  const meta = parseMetaLine(metaLine);
  if (!meta) return null;

  const clipping = {
    id: `clip-${index}`,
    type: meta.type,
    page: meta.page,
    locationStart: meta.locationStart,
    locationEnd: meta.locationEnd,
    addedOn: meta.addedOn,
    addedOnRaw: meta.addedOnRaw,
    metaLineRaw: metaLine,
    text: text
  };

  return {
    bookTitle: titleAuthor.title,
    bookAuthor: titleAuthor.author,
    clipping
  };
}

/**
 * Parse "Book Title (Author Name)" from the first line.
 * The author is in the last pair of parentheses.
 */
function parseTitleAuthor(line) {
  // Find the last '(' that has a matching ')'
  const lastParen = line.lastIndexOf('(');
  if (lastParen === -1 || !line.endsWith(')')) {
    // No author in parens — treat whole line as title
    return { title: line.trim(), author: '' };
  }

  const title = line.substring(0, lastParen).trim();
  const author = line.substring(lastParen + 1, line.length - 1).trim();

  return { title, author };
}

/**
 * Parse the metadata line in any supported Kindle language.
 * Uses structural parsing based on pipe delimiters and number positions.
 *
 * Known formats (any language):
 *   - {Your} {Type} at {location} {N}-{N} | {Added on} {date}
 *   - {Your} {Type} on {page} {N} | {location} {N} | {Added on} {date}
 *   - {Your} {Type} on {page} {N} | {location} {N}-{N} | {Added on} {date}
 */
function parseMetaLine(line) {
  if (!line.startsWith('- ')) return null;

  const segments = line.split('|').map(s => s.trim());
  if (segments.length < 2) return null;

  // Type detection from first segment
  const type = detectType(segments[0]);

  // Date: always the last segment
  const dateSeg = segments[segments.length - 1];
  const addedOnRaw = extractDateRaw(dateSeg);
  const addedOn = parseKindleDate(addedOnRaw);

  let page = null;
  let locationStart = 0;
  let locationEnd = null;

  if (segments.length >= 3) {
    // [type + page] | [location] | ... | [date]
    page = extractLastNumber(segments[0]);
    const loc = extractLocationRange(segments[segments.length - 2]);
    locationStart = loc.start;
    locationEnd = loc.end;
  } else {
    // [type + location] | [date]
    const loc = extractLocationRange(segments[0]);
    locationStart = loc.start;
    locationEnd = loc.end;
  }

  return { type, page, locationStart, locationEnd, addedOn, addedOnRaw };
}

/**
 * Detect the clipping type from a metadata segment using known keywords.
 * Falls back to 'Highlight' if no keyword is recognized.
 */
function detectType(segment) {
  const match = segment.match(TYPE_PATTERN);
  if (match) {
    return TYPE_KEYWORDS[match[1].toLowerCase()];
  }
  return 'Highlight';
}

/**
 * Extract the last number from a segment (used for page numbers).
 */
function extractLastNumber(segment) {
  const matches = [...segment.matchAll(/\d+/g)];
  if (matches.length === 0) return null;
  return parseInt(matches[matches.length - 1][0], 10);
}

/**
 * Extract a location or location range from a segment.
 * Looks for N-N (range) first, then falls back to the last number.
 */
function extractLocationRange(segment) {
  const rangeMatch = segment.match(/(\d+)-(\d+)/);
  if (rangeMatch) {
    return {
      start: parseInt(rangeMatch[1], 10),
      end: parseInt(rangeMatch[2], 10)
    };
  }
  const matches = [...segment.matchAll(/\d+/g)];
  if (matches.length > 0) {
    return {
      start: parseInt(matches[matches.length - 1][0], 10),
      end: null
    };
  }
  return { start: 0, end: null };
}

/**
 * Extract the raw date string from a date segment.
 * Strips the language-specific prefix (e.g., "Added on", "Hinzugefugt am")
 * and returns from the weekday name onward.
 */
function extractDateRaw(segment) {
  const commaIdx = segment.indexOf(',');
  if (commaIdx === -1) return segment.trim();

  // Walk back from the comma to find the start of the weekday word
  let i = commaIdx - 1;
  while (i >= 0 && segment[i] !== ' ') i--;

  return segment.substring(i + 1).trim();
}

/**
 * Parse a Kindle date string in any supported language.
 * Input format: "Weekday, D[.] MonthName YYYY HH:MM:SS"
 */
function parseKindleDate(str) {
  if (!str) return null;

  // Remove weekday prefix (everything up to and including the comma)
  const commaIdx = str.indexOf(',');
  let datePart = commaIdx !== -1 ? str.substring(commaIdx + 1).trim() : str;

  // Extract and remove time
  const timeMatch = datePart.match(/(\d{1,2}):(\d{2}):(\d{2})/);
  if (!timeMatch) {
    const d = new Date(str);
    return isNaN(d.getTime()) ? null : d;
  }
  datePart = datePart.replace(timeMatch[0], '').trim();

  // Extract and remove year
  const yearMatch = datePart.match(/\b((?:19|20)\d{2})\b/);
  if (!yearMatch) return null;
  datePart = datePart.replace(yearMatch[0], '').trim();

  // Remaining tokens: day (with optional trailing dot) and month name
  const tokens = datePart.split(/\s+/).filter(Boolean);
  let day = null;
  let month = null;

  for (const token of tokens) {
    const cleaned = token.replace(/\.$/, '');
    if (day === null && /^\d{1,2}$/.test(cleaned)) {
      day = parseInt(cleaned, 10);
    } else if (month === null && MONTH_MAP[cleaned.toLowerCase()] !== undefined) {
      month = MONTH_MAP[cleaned.toLowerCase()];
    }
  }

  if (day === null || month === null) {
    // Fallback for unrecognized date formats
    const d = new Date(str);
    return isNaN(d.getTime()) ? null : d;
  }

  return new Date(
    parseInt(yearMatch[1], 10),
    month,
    day,
    parseInt(timeMatch[1], 10),
    parseInt(timeMatch[2], 10),
    parseInt(timeMatch[3], 10)
  );
}

/**
 * Generate a stable book ID from title + author.
 */
function makeBookId(title, author) {
  return `book:${title}|||${author}`;
}
