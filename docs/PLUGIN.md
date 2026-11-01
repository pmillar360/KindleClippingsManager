# Kindle Highlights Sync user guide

## Configuration

Settings persist in Calibre’s configuration directory. The vault must already
exist. The destination is a relative folder such as `Books/Highlights`; traversal,
absolute subdirectories, and links escaping the vault are rejected.

Filename fields are `{title}`, `{author}`, and `{id}`. Values are sanitized for
Windows and Linux. Choose a preset or enter, for example, `{author} - {title}`.
Enable **Create a folder for each author** for paths such as
`Books/Highlights/Author/Author - Title.md`. Multiple authors share one folder;
missing authors use `Unknown author`. An example path updates as you edit settings.
Unrelated filename collisions receive a book-ID suffix.
Saved filenames remain stable when metadata or naming settings change. Changing the destination
folder starts a separate export destination; old notes are left intact.

The default Markdown uses YAML properties, a book heading, author, numbered
blockquotes, available page/location/chapter metadata, highlight dates, and notes.
You can turn these formatting choices on or off and change the date format with
strftime directives, for example `%Y-%m-%d` or `%d %B %Y`.
Compact metadata puts positions and dates on one line. Chapter grouping adds
headings as the chapter changes in book order; repeated chapter names do not
reorder passages. Formatting changes apply during the next synchronization;
simultaneous edits to a passage may require review.

Backups, preservation of user edits, and keeping missing-book notes are mandatory
in this release. There is no destructive overwrite or automatic deletion mode.

### Preferences reference

Open the plugin toolbar menu → **Settings**, or customize the plugin through
Calibre’s **Preferences → Plugins**. Hover over an option for an explanation.
The defaults below apply to a fresh configuration; upgrades retain saved choices.
Save with **OK** to use changes on the next import/export.

| Preference | Default | Function |
| --- | --- | --- |
| **Filename presets** | Choose a filename preset… | Copies a common pattern into **Filename convention**. You can edit the pattern afterwards. The first entry makes no change. Selecting a preset does not rename existing notes. |
| **Obsidian vault** | Empty; required | Existing vault directory containing the exported notes and backups. **Browse…** selects a directory. Nothing is uploaded to Obsidian or another service. |
| **Destination folder** | `Books/Highlights` | Subfolder relative to the vault, created when needed. Absolute paths and `..` are rejected. Changing this starts a separate export destination; old notes stay intact. |
| **Filename convention** | `{title}` | Pattern for new notes, using `{title}`, `{author}` (comma-separated authors), or `{id}` (the plugin’s stable book ID). For example, `{author} - {title}`. `.md` is appended automatically, so omit it from the pattern. Unsafe characters are replaced and long names shortened. Confirmed existing notes keep their paths, even after the pattern changes. |
| **Fallback import folder** | Empty | Copied Kindle source folder used when no device is connected. If empty, you are prompted to choose one. Also supplies the starting directory for **Import folder**, which lets you choose a different source. Sources are read only. |
| **Date format (strftime)** | `%Y-%m-%d` | Formatting for available annotation creation dates when **Show highlight dates** is enabled. `%Y-%m-%d` gives `2026-11-01`; `%d %B %Y` gives `01 November 2026` in an English locale; `%H:%M` adds hours/minutes. Month names follow the runtime locale. Stored dates are unchanged. |
| **Create a folder for each author** | Off | Adds an author subfolder for new notes, for example `Books/Highlights/Author/Title.md`. Multiple authors share one folder with comma-separated names; missing authors use `Unknown author`. Existing notes are not moved. |
| **Import My Clippings.txt** | On | Enables the clippings importer for future imports, including supported renamed clippings exports. Turning it off does not remove previously imported annotations. At least one importer must remain enabled. |
| **Recover highlights from KFX/YJR** | On | Enables recovery from supported DRM-free KFX books with matching `.sdr`/YJR annotation sidecars. Both sources are needed. It does not recover directly from EPUB or `ksdk_annotation_v1.db`, and turning it off does not remove previously recovered annotations. |
| **Preview changes before writing** | On | Shows proposed changes, conflicts, and duplicate files to merge/archive. Uncheck books to skip them for this run. When off, eligible changes are applied immediately; conflict checks and backups still apply. Cancelling the preview prevents vault writes but does not undo annotations already imported into local state. |
| **Prefer Calibre metadata** | On | Uses matched Calibre title, authors, series and other book metadata during future imports. When off, source metadata is preferred while library matching still applies. It does not change highlight text or rewrite existing YAML. Unmatched books use source metadata. |
| **Use blockquotes** | On | Renders highlight and personal-note text with Markdown `>` blockquotes. When off, text uses ordinary paragraphs. Stored annotation text is unchanged. |
| **Number highlights** | On | Adds numbered **Highlight**/**Note** headings. Inserting a highlight in the middle adjusts numbering. Turning it off hides these headings while retaining book ordering and stable block identities. |
| **Show page, location, and chapter when available** | On | Shows known page/location/chapter information; unmapped KFX coordinates are explicitly labeled **KFX position**. Missing values are omitted. Turning it off hides labels without changing sorting. Chapter-group headings are controlled separately. |
| **Show highlight dates** | On | Shows available annotation creation dates using **Date format**. Missing or unparseable dates are omitted. These are annotation dates, not export timestamps; this setting does not change sorting. |
| **Add YAML properties to new notes** | On | Creates Obsidian properties above the managed section: title, author, stable book ID, tags, and available series/publication date/identifiers. Existing YAML remains user-owned: toggling this neither adds properties to existing notes nor removes them. |
| **Include personal notes** | On | Includes standalone notes and notes attached to highlights. When off, they are omitted from generated output but retained in local state. If removing a block would discard manual edits, the note is flagged for review. |
| **Compact highlight metadata onto one line** | Off | Places visible position/chapter/date fields on one line separated by `·`. It does not shorten passages or turn on hidden metadata. |
| **Group highlights by chapter (in book order)** | Off | Adds chapter headings as the chapter changes while retaining book order. Equal chapter names are not collected out of order. Missing chapter names use **Other highlights**. Works independently of position labels and numbering. |
| **Example path** | Read-only preview | Illustrates the relative output path using **Example Book** and **Example Author**, rather than a real library record. Updates when destination/naming options change. Wraps long paths and supports selecting/copying text. |

Import switches affect future source scans; they do not clear local state or stop
previously imported highlights from being exported. Presentation switches affect
generated output at the next export; they do not alter the original Kindle files.
Existing manual edits are preserved, and a change that conflicts with an edit may
require review. Unrecognized historical blocks retained from duplicate notes may
keep their original formatting because their source records are unavailable.

## Input sources

The main action uses the connected Calibre device, then the configured fallback
folder if no device is connected. The **Import folder** menu always permits
choosing a copied Kindle directory. Device I/O uses Calibre’s device job queue.
Mounted USB and MTP have separate read-only adapters. A private local staging
directory is removed after synchronization.

Standard discovery searches `documents` on a device, and recursively searches the
selected manual folder. It imports `My Clippings.txt`; manually renamed exports
beginning with `My Clippings` are also recognized when no standard file exists.
For YJR recovery, preserve the relationship:

```text
Import folder/
  Example.kfx
  Example.sdr/
    annotations.yjr
    assets/                  # retain when present
```

The actual sidecar filename may differ. The directory-to-book relationship must
be unique. File names help locate a physical KFX/sidecar pair; library identity
then comes from metadata, identifiers, established device mappings, or an explicit
user-selected Calibre record.

EPUB-only Calibre records are supported. KFX text is read from the device or the
manual import source, so an additional KFX format need not remain in the library.
EPUB recognition uses Calibre’s metadata/format API. Direct reconstruction from
EPUB offsets is intentionally not implemented.

Newer firmware may keep annotations in `ksdk_annotation_v1.db` and leave YJR
sidecars empty. The folder scanner reports this condition. Database extraction
is not supported by this release; copying an empty YJR file cannot recover those
annotations. Mounted-device import also reports empty sidecars, but does not
scan the account database. Firmware changes require a new backend.

## Exclusions, edits, and matching

The manager includes excluded records by default. Excluding a book skips its
exports without removing its note. Excluding a highlight removes it from the
next generated managed section; the original annotation and exclusion persist.
Use the same buttons to restore records. Text edits are stored as separate local
overrides. **Restore source text** removes that override.

Annotations with uncertain identities remain separate. Use individual exclusions
to remove unwanted copies. Identical passages at different positions remain
independent highlights. Standalone personal notes retain their own identities
and timestamps; bookmarks are retained for cleaned clippings export but omitted
from the default Markdown.

**Match library book** lets you choose an edition explicitly when automatic
matching is ambiguous. Exclusions and highlight identities survive a later
mapping to Calibre. There is currently no UI to undo an incorrect mapping; back
up state before changing mappings. Existing notes are retained during remapping.

## Obsidian ownership and conflicts

The plugin merges individual highlight blocks inside these markers:

```markdown
<!-- kindle-highlights-sync:begin -->
...generated book heading and highlights...
<!-- kindle-highlights-sync:end -->
```

New highlights are inserted in book order, including highlights added in the
middle. Known Kindle locations sort first; unmapped KFX positions are ordered
separately within their source coordinate system, then unpositioned highlights.
The plugin never estimates a conversion between Kindle locations and KFX PIDs.
Numbered headings adjust to the resulting order. Unchanged exports do not write
the note or create a backup.

Personal commentary may remain before or after this region. Edits within an
existing highlight block are also preserved. YAML frontmatter is
initially generated above the region, then remains user-owned. User properties,
comments, and line endings outside the region are preserved.

The last generated version is compared with both the note and incoming highlights.
If the same passage changes differently in both places, or an edited passage
would be removed by an exclusion, the plugin skips the note for review. Manually
deleted blocks stay deleted. Missing or malformed markers also require review.
For a missing note,
restore it at its saved path; the plugin deliberately does not silently recreate
or rename it. Backups and state can be inspected using ordinary local tools.

Existing generated notes are discovered recursively within the destination
folder, including author subfolders and ID-suffixed filenames. Book IDs, aliases,
identifiers, or unambiguous title/author metadata establish identity; a filename
alone is insufficient. Distinct or ambiguous editions remain separate. A matching
note without valid managed markers is flagged for review and left intact.

Confirmed duplicate notes merge their unique highlight blocks. Exact passages
with matching coordinates and annotation kind can collapse across historical
IDs; identical words at different locations remain separate. Conflicting edits
retain both original files for review. Duplicate properties and commentary are
preserved in a **Merged note** section. After the destination is safely written,
the original duplicate is moved into `.kindle-highlights-backups/merged`.
The preview lists files to merge and archive. Interrupted consolidation can be
retried; archived files are excluded from discovery.

Each changed existing note is backed up before replacement. Notes are written
to a temporary file in the same directory, flushed, and atomically replaced.
The local journal reconciles a completed file replacement if Calibre stopped
before its state update. A divergent interrupted write becomes a conflict.

Keep the vault on a local filesystem supporting atomic replacement. External
editors and filesystem changes are checked again after preview and immediately
before replacement, but no application can provide a cross-process transaction
with an arbitrary editor or sync client. Pause competing editors during a sync
if they are actively modifying the same managed note.

## Local data and diagnostics

Open **Preferences → Miscellaneous → Open calibre configuration directory**.

- Preferences: `plugins/kindle_highlights_sync.json`.
- State: `plugins/kindle_highlights_sync/<library-key>/state.sqlite`.
- Backups: inside the configured vault destination’s
  `.kindle-highlights-backups` directory.

The state database contains private highlight text, edit overrides, import
history, exclusions, source paths/fingerprints, saved managed content, journal
entries, and content-free error categories. Protect it as you protect the vault.
Each Calibre library has separate state. Stop synchronization and close Calibre
before copying or restoring the SQLite file.

Preview cancellation prevents vault writes, but already-imported annotations
remain in local state. Cancellation during writing stops between books; notes
already written remain valid and the summary identifies cancellation.

Routine recovery logging suppresses upstream book/annotation dumps. There is no
telemetry, network request, upload, mail integration, or DRM plugin delegation.
