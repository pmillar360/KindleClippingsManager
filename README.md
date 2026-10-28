# Kindle Highlights Sync — Calibre plugin

Native Qt plugin for importing Kindle clippings and DRM-free KFX/YJR annotations,
managing persistent exclusions, and safely synchronizing Markdown to Obsidian.
The original KCM browser app remains available below and through `index.html`.

Requires **Calibre 9.17 or newer**. Windows runtime and Ubuntu engine tests pass;
physical Kindle USB/MTP and Linux Calibre GUI validation remain outstanding. Version 0.1.0
is a preview build, not a claim of completed hardware/platform certification.

## Install

1. Build the ZIP with `calibre-debug tools/build_plugin.py`, or use the supplied
   `dist/Kindle-Highlights-Sync-0.1.0.zip`.
2. In Calibre, open **Preferences → Plugins → Load plugin from file** and select
   that ZIP. Restart Calibre when prompted.
3. Add **Sync Kindle Highlights** to the toolbar through **Preferences → Toolbars
   & menus** if it is not already visible.
4. Open its toolbar menu → **Settings**. Select an existing Obsidian vault,
   destination folder, and optionally a fallback import folder.
5. Connect and unlock the Kindle, then click **Sync Kindle Highlights**. Review
   the preview and synchronize. Without a device, the configured fallback folder
   or a folder picker supplies the input.

No pip installs, network access, Obsidian plugin, or retained library KFX duplicate
is required. Dependencies are included or provided by Calibre.

## Daily use

- Import sources are read only. For manual recovery, keep each book’s `.kfx`
  alongside its matching `.sdr` directory containing the `.yjr` sidecar.
- Use **Manage highlights** to search, edit, exclude/restore, choose the correct
  Calibre edition, export one book, or save a cleaned clippings copy elsewhere.
- Uncheck a book in the preview to skip it for that synchronization only.
- Write Obsidian commentary **outside** the marked managed section. Editing
  managed content creates a conflict and preserves the entire existing note.
- Backups are stored under the destination’s `.kindle-highlights-backups` folder.
  Missing or excluded books never delete existing notes.
- YAML properties are created initially and then treated as user-owned. Managed
  title/author/series text follows the selected metadata preference.
- KFX positions are labeled as KFX positions. They are never passed off as Kindle
  locations or EPUB offsets. An embedded location map must be corroborated by
  multiple existing clippings before it is used to reconcile clipping limits.

See [the plugin guide](docs/PLUGIN.md), [architecture](docs/ARCHITECTURE.md),
[validation and limitations](docs/VALIDATION.md), and
[dependency notices](THIRD_PARTY_NOTICES.md).

## Development checks

```powershell
$env:CALIBRE_CONFIG_DIRECTORY = Join-Path (Get-Location) '.calibre-test-profile'
calibre-debug tools/run_tests.py
node --test tests.js
calibre-debug tools/build_plugin.py
calibre-customize -a dist/Kindle-Highlights-Sync-0.1.0.zip
$env:QT_QPA_PLATFORM = 'offscreen'
calibre-debug tools/smoke_calibre.py
```

Private recovery test, only when the ignored original fixtures are present:

```powershell
$env:KHS_PRIVATE_TESTS = '1'
calibre-debug tools/run_tests.py
```

The ZIP includes an allowlist of plugin source and notices only. It never includes
`testfiles`, private highlights, local state, or test profiles. Do not commit those
inputs. The original browser application and its documentation follow.

---

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
