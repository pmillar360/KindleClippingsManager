# KCM — Kindle Clippings Manager

KCM is a lightweight browser app for reviewing, searching, editing, and organizing Kindle highlights, notes, and bookmarks exported from `My Clippings.txt`. It runs entirely in the browser and keeps the file as the source of truth.

---

## Overview

This project is built for Kindle readers who want a cleaner way to work with large annotation files without a backend or account setup. It lets you load a `My Clippings.txt` export, browse entries by book or author, search text, edit clipping content, remove duplicates, and download the updated file in Kindle-compatible format.

---

## Features

- **Open and review a Kindle export** — Load a `My Clippings.txt` file through the browser file picker.
- **Browse by book or author** — View the library sorted by title or author, with each book showing its clipping count.
- **Search across the library** — Filter books and authors in real time, or search inside clipping text across all entries.
- **Edit clipping text** — Update a highlight or note inline using the Edit, Save, and Cancel controls.
- **Delete entries or entire books** — Remove a single clipping or all clippings for a selected book after confirmation.
- **Detect duplicates** — Highlight repeated entries by location and text and remove them in bulk.
- **Download the updated file** — Rebuild the Kindle-compatible output and save it as a new `.txt` file.

---

## Who This Is For

This tool is designed for Kindle users who want a straightforward way to review annotations, clean up duplicates, and keep only the highlights and notes they still want to keep.

---

## Input File Format

The app expects the standard Kindle clippings format:

```
{Book Title} ({Author Name})
- Your {Highlight|Bookmark|Note} [on page {N} |] at location {N}-{N} | Added on {Weekday}, {D Month YYYY HH:MM:SS}

{clipping text}
==========
```

Notes:
- Bookmarks have no clipping text.
- A book may appear under slightly different title or author spellings across clippings.
- Duplicate clippings (same location and same text) may exist.

---

## Data Model

```text
AppState
├── filePath: string | null
├── isDirty: boolean
└── books: Book[]

Book
├── id: string
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

## Serialization

When the file is downloaded, the app rebuilds the `My Clippings.txt` structure in Kindle-compatible format:

```text
{title} ({author})
- Your {type} [on page {N} |] at location {N}[-{N}] | Added on {Weekday}, {D Month YYYY HH:MM:SS}

{text}
==========
```

- Deleted entries are omitted.
- Edited text replaces the original text.
- Clippings are preserved in the original file order as far as the app stores it.

---

## Getting Started

No build step is required.

1. Clone or download this repository.
2. Open `index.html` in a modern browser.
3. Click **Open File** and choose your Kindle export named `My Clippings.txt`.
4. Browse, search, edit, and remove clippings as needed.
5. Click **Download updated clippings file** to save the modified content as a new file.

> Tip: This app uses the browser file picker and download flow rather than writing directly back to the original source file. After downloading, you can rename the file back to `My Clippings.txt` and copy it to your Kindle if needed.

---

## Project Structure

```text
KCM/
├── index.html          # App shell
├── css/
│   └── style.css       # App styling
├── js/
│   ├── app.js          # UI logic and application state
│   ├── parser.js       # Parses My Clippings.txt into a data model
│   └── serializer.js   # Rebuilds My Clippings.txt from the data model
├── package.json        # Minimal project config
├── tests.js            # Unit tests
├── README.md           # Project documentation
├── testfiles/          # Sample clipping files for testing
└── .docs/              # Project docs directory
```

---

## Tech Stack

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Framework | Vanilla JS or Vue 3 via CDN | Lightweight and no build step |
| Styling | Custom CSS | Simple, focused UI |
| File I/O | File input and blob download | Runs fully in the browser |
| Storage | In-memory only | Keeps the file as the source of truth |

---

## Browser Compatibility

The app is designed for modern Chromium browsers such as Chrome and Edge. It uses standard browser APIs for file selection and downloads, so it works best in those environments.
