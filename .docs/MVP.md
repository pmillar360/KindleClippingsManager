# Kindle Clippings Manager (KCM) — MVP Document

## Overview

A lightweight, browser-based web application for reading, browsing, searching, editing, and saving Kindle clippings from a `My Clippings.txt` file. No backend server required; the app runs entirely in the browser using the File System Access API.

---

## Target User

A Kindle reader who accumulates highlights and bookmarks in `My Clippings.txt` and wants a clean UI to review, organize, and curate that content.

---

## Input File Format

The `My Clippings.txt` file follows a consistent structure. Each clipping entry is separated by `==========` and contains:

```
{Book Title} ({Author Name})
- Your {Highlight|Bookmark|Note} [on page {N} |] at location {N}-{N} | Added on {Weekday}, {D Month YYYY HH:MM:SS}

{clipping text}
==========
```

**Notes:**
- Bookmarks have no clipping text.
- A book may appear under slightly different title/author spellings across clippings (e.g., `Surely You're Joking, Mr. Feynman!` vs `Surely You're Joking Mr Feynman`).
- Duplicate clippings (same location, same text) may exist.

---

## MVP Features

### F1 — File Load & Save

| ID | Requirement |
|----|-------------|
| F1.1 | User can open a `My Clippings.txt` file via a file picker button. |
| F1.2 | The app parses the file into a structured in-memory data model on load. |
| F1.3 | User can save all changes back to the original file (overwrite) or download a new copy. |
| F1.4 | The app warns the user if there are unsaved changes before loading a new file. |

---

### F2 — Browse by Book / Author

| ID | Requirement |
|----|-------------|
| F2.1 | A sidebar or panel lists all books, grouped or sorted alphabetically by **title**. |
| F2.2 | Switching to an **Author** view groups/sorts the same list alphabetically by **author name**. |
| F2.3 | Each book entry displays the title, author, and a count of its clippings. |
| F2.4 | Clicking a book displays all its clippings in the main content area, ordered by location. |
| F2.5 | Bookmarks are visually distinguished from highlights (e.g., different icon or label). |

---

### F3 — Search

| ID | Requirement |
|----|-------------|
| F3.1 | A search bar filters the book/author list in real time as the user types. |
| F3.2 | Search matches against both **book title** and **author name**. |
| F3.3 | A separate full-text search mode searches within **clipping content** across all books. |
| F3.4 | Search results highlight the matched term within the result. |
| F3.5 | Clearing the search restores the full list instantly. |

---

### F4 — Edit Clippings

| ID | Requirement |
|----|-------------|
| F4.1 | Each clipping has an **Edit** action that opens the clipping text in an inline editable field. |
| F4.2 | Changes to clipping text are confirmed with a **Save** button and cancelled with **Cancel**. |
| F4.3 | The clipping metadata (type, location, date) is displayed read-only and is not editable. |
| F4.4 | A **Delete** action removes a single clipping after a confirmation prompt. |
| F4.5 | Deleting a clipping removes it from the in-memory model and marks the file as unsaved. |

---

### F5 — Remove Books

| ID | Requirement |
|----|-------------|
| F5.1 | A **Delete Book** action is available from the book list or the book detail view. |
| F5.2 | Deleting a book removes all its clippings after a confirmation prompt (stating the clipping count). |
| F5.3 | The book is removed from the sidebar/list immediately after deletion. |

---

### F6 — Duplicate Detection (Stretch Goal for MVP)

| ID | Requirement |
|----|-------------|
| F6.1 | The app detects clippings with identical location and text within the same book. |
| F6.2 | Duplicates are visually flagged and can be removed in bulk with a single action. |

---

## Data Model

```
AppState
├── filePath: string | null          // path/handle to the loaded file
├── isDirty: boolean                 // unsaved changes exist
└── books: Book[]

Book
├── id: string                       // generated from title + author
├── title: string
├── author: string
└── clippings: Clipping[]

Clipping
├── id: string                       // generated (index or UUID)
├── type: "Highlight" | "Bookmark" | "Note"
├── page: number | null
├── locationStart: number
├── locationEnd: number | null
├── addedOn: Date
└── text: string                     // empty string for Bookmarks
```

---

## Serialization

When saving, the app reconstructs the `My Clippings.txt` format exactly:

```
{title} ({author})
- Your {type} [on page {N} |] at location {N}[-{N}] | Added on {Weekday}, {D Month YYYY HH:MM:SS}

{text}
==========
```

- All books and their clippings are written in the original file order (or sorted order if reordered by the user).
- Deleted entries are omitted.
- Edited text replaces the original text.

---

## UI Layout

```
┌──────────────────────────────────────────────────────────┐
│  [Open File]  KCM — Kindle Clippings Manager  [Save]     │
├───────────────────┬──────────────────────────────────────┤
│  [ Search... ]    │  Book Title (Author)                  │
│                   │  ─────────────────────────────────── │
│  [By Title ▼]     │  📍 Bookmark · page 117 · Mar 2022   │
│                   │                                       │
│  □ 2001: A Space… │  ✏ Highlight · loc 1357 · Mar 2022   │
│  □ Attached       │  "ants left some sort of trail..."    │
│  □ Building a 2nd │                        [Edit] [Delete]│
│  □ Determined     │                                       │
│  □ Dune Saga      │  ✏ Highlight · loc 2559 · Mar 2022   │
│  □ Eruption       │  "The elementary things are easy…"   │
│  □ Genius Makers  │                        [Edit] [Delete]│
│  □ Great Gatsby   │                                       │
│  □ Hobbit         │                                       │
│  □ Lord of Rings  │                                       │
│  □ Pragmatic Prog │                                       │
│  □ Rick Rubin…    │                                       │
│  □ Slaughterhouse │                                       │
│  □ Surely Joking  │                                       │
│  □ What If?       │                                       │
│                   │                                       │
│  [Delete Book]    │                                       │
└───────────────────┴──────────────────────────────────────┘
```

---

## Tech Stack (Recommended)

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Framework | Vanilla JS or Vue 3 (no build step via CDN) | Lightweight, no toolchain required |
| Styling | CSS (custom) or Pico CSS | Minimal, classless/lightweight |
| File I/O | [File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API) | Native browser read/write, no server needed |
| Storage | In-memory only | Simplicity; file is source of truth |

---

## Out of Scope for MVP

- User accounts or cloud sync
- Multiple file management
- Import/export to other formats (CSV, Markdown, Notion, etc.)
- Tagging or custom categories
- Mobile-native app
- Offline PWA support
- Kindle device integration

---

## Success Criteria

- [ ] User can load `My Clippings.txt` and see all books and authors listed.
- [ ] User can switch between title and author views.
- [ ] User can search and find clippings by book, author, or text.
- [ ] User can edit the text of a highlight and see the updated content.
- [ ] User can delete a single clipping or an entire book.
- [ ] User can save modified content back to the original file format with no data loss.
