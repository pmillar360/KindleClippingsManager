/**
 * Serializes the in-memory data model back to My Clippings.txt format.
 */

const SEPARATOR = '==========';

/**
 * Serialize all books and their clippings back to the My Clippings.txt format.
 * Respects original clipping order when available.
 * @param {Array} books - Array of Book objects
 * @param {Array} clippingOrder - Original order of clipping IDs
 * @returns {string} The serialized file content
 */
export function serializeClippings(books, clippingOrder) {
  // Build a map of clipping id -> { book, clipping }
  const clipMap = new Map();
  for (const book of books) {
    for (const clip of book.clippings) {
      clipMap.set(clip.id, { book, clipping: clip });
    }
  }

  // Collect clippings in original order, then append any new ones
  const ordered = [];
  const seen = new Set();

  for (const id of clippingOrder) {
    if (clipMap.has(id)) {
      ordered.push(clipMap.get(id));
      seen.add(id);
    }
  }

  // Append any clippings not in the original order (shouldn't happen in MVP)
  for (const [id, entry] of clipMap) {
    if (!seen.has(id)) {
      ordered.push(entry);
    }
  }

  const entries = ordered.map(({ book, clipping }) => {
    return serializeEntry(book, clipping);
  });

  return entries.join('\n') + '\n';
}

/**
 * Serialize a single clipping entry.
 */
function serializeEntry(book, clipping) {
  const titleLine = book.author
    ? `${book.title} (${book.author})`
    : book.title;

  const metaLine = clipping.metaLineRaw || buildMetaLine(clipping);
  const text = clipping.text || '';

  return `${titleLine}\n${metaLine}\n\n${text}\n${SEPARATOR}`;
}

/**
 * Build the metadata line for a clipping.
 */
function buildMetaLine(clip) {
  let parts = `- Your ${clip.type}`;

  if (clip.page != null) {
    parts += ` on page ${clip.page} |`;
    parts += ` location ${clip.locationStart}`;
  } else {
    parts += ` at location ${clip.locationStart}`;
  }

  if (clip.locationEnd != null) {
    parts += `-${clip.locationEnd}`;
  }

  parts += ` | Added on ${clip.addedOnRaw}`;

  return parts;
}
