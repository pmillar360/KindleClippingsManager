# KCM — Kindle Clippings Manager

A lightweight, browser-based app for reading, browsing, searching, editing, and saving your Kindle highlights and bookmarks from a `My Clippings.txt` file. No installation, no server, no backend — runs entirely in your browser.

---

## Features

- **Load & Save** — Open your `My Clippings.txt` via a file picker and download the modified file at any time. Unsaved-change warnings prevent accidental data loss.
- **Browse by Book or Author** — A sidebar lists all books alphabetically, sortable by title or author. Each entry shows the clipping count.
- **Search** — Filter books and authors in real time, or switch to full-text content search to find specific passages across all clippings.
- **Edit Clippings** — Inline editing of highlight text with Save / Cancel controls.
- **Delete Clippings or Entire Books** — Remove individual clippings or all clippings for a book, with confirmation prompts.
- **Duplicate Detection** — Clippings with identical location and text are flagged, and can be removed in bulk.
- **Clipping-level search** — Filter clippings within a selected book by text.

---

## Getting Started

No build step required.

1. Clone or download this repository.
2. Open `index.html` in any modern browser (Chrome or Edge recommended for broadest File System API support).
3. Click **Open File** and select your Kindle's `My Clippings.txt`.
4. Browse, search, and edit your clippings.
5. Click **Download updated clippings file** to save your changes.

> **Tip:** On Chrome/Edge, the app uses a standard `<input type="file">` picker. The downloaded file can be renamed back to `My Clippings.txt` and copied to your Kindle.

---

## Project Structure

```
KCM/
├── index.html          # Single-page app shell (Vue 3 via CDN)
├── css/
│   └── style.css       # App styles
├── js/
│   ├── app.js          # Vue 3 application logic & state
│   ├── parser.js       # Parses My Clippings.txt into a data model
│   └── serializer.js   # Reconstructs My Clippings.txt from the data model
├── package.json        # Minimal config (type: module)
├── tests.js            # Unit tests
└── MVP.md              # Product requirements
```

---

## Tech Stack

| Concern | Choice |
|---------|--------|
| Framework | Vue 3 (via CDN, no build step) |
| Styling | Custom CSS |
| File I/O | `<input type="file">` + `Blob` download |
| Storage | In-memory only — the file is the source of truth |

---

## Data Model

```
AppState
├── books: Book[]
├── clippingOrder: string[]   // preserves original file order
└── isDirty: boolean

Book
├── id: string                // derived from title + author
├── title: string
├── author: string
└── clippings: Clipping[]

Clipping
├── id: string
├── type: "Highlight" | "Bookmark" | "Note"
├── page: number | null
├── locationStart: number
├── locationEnd: number | null
├── addedOn: Date
└── text: string
```

---

## Input File Format

The app expects the standard Kindle clippings format:

```
{Book Title} ({Author Name})
- Your {Highlight|Bookmark|Note} [on page {N} |] at location {N}-{N} | Added on {Weekday}, {D Month YYYY HH:MM:SS}

{clipping text}
==========
```

Bookmarks have no clipping text. The parser handles BOM characters, variant title/author spellings, and duplicate entries.

---

## Serialization

When downloading, the app reconstructs the exact `My Clippings.txt` format, preserving original clipping order. Deleted entries are omitted and edited text replaces the original.

---

## Browser Compatibility

Tested on Chrome and Edge (Chromium). Firefox is supported for reading; file download works in all modern browsers.
