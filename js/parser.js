/**
 * Parses a Kindle "My Clippings.txt" file into a structured data model.
 */

const SEPARATOR = '==========';

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
 * Parse the metadata line.
 * Formats:
 *   - Your Highlight at location 25-26 | Added on Sunday, 6 March 2022 13:23:35
 *   - Your Bookmark at location 92 | Added on ...
 *   - Your Bookmark on page 117 | location 1788 | Added on ...
 *   - Your Highlight on page 4 | location 61-61 | Added on ...
 *   - Your Note on page 10 | location 150-152 | Added on ...
 */
function parseMetaLine(line) {
  if (!line.startsWith('- Your ')) return null;

  // Extract type
  const typeMatch = line.match(/^- Your (Highlight|Bookmark|Note)\s/i);
  if (!typeMatch) return null;
  const type = typeMatch[1];

  // Extract page (optional)
  let page = null;
  const pageMatch = line.match(/on page (\d+)/);
  if (pageMatch) {
    page = parseInt(pageMatch[1], 10);
  }

  // Extract location
  let locationStart = 0;
  let locationEnd = null;
  const locMatch = line.match(/location (\d+)(?:-(\d+))?/);
  if (locMatch) {
    locationStart = parseInt(locMatch[1], 10);
    locationEnd = locMatch[2] ? parseInt(locMatch[2], 10) : null;
  }

  // Extract date - everything after "Added on "
  let addedOn = null;
  let addedOnRaw = '';
  const dateMatch = line.match(/Added on (.+)$/);
  if (dateMatch) {
    addedOnRaw = dateMatch[1].trim();
    addedOn = parseKindleDate(addedOnRaw);
  }

  return { type, page, locationStart, locationEnd, addedOn, addedOnRaw };
}

/**
 * Parse Kindle date format: "Sunday, 6 March 2022 13:23:35"
 */
function parseKindleDate(str) {
  // Remove the weekday prefix: "Sunday, "
  const commaIdx = str.indexOf(',');
  if (commaIdx === -1) return new Date(str);
  const datePart = str.substring(commaIdx + 1).trim();

  // datePart is like "6 March 2022 13:23:35"
  const d = new Date(datePart);
  if (!isNaN(d.getTime())) return d;

  // Fallback: try full string
  return new Date(str);
}

/**
 * Generate a stable book ID from title + author.
 */
function makeBookId(title, author) {
  return `book:${title}|||${author}`;
}
