# Kindle Highlights Sync user guide

## Configuration

Settings persist in Calibre’s configuration directory. The vault must already
exist. The destination is a relative folder such as `Books/Highlights`; traversal,
absolute subdirectories, and links escaping the vault are rejected.

Filename fields are `{title}`, `{author}`, and `{id}`. Values are sanitized for
Windows and Linux. Colliding filenames receive a deterministic book-ID suffix.
Saved filenames remain stable when metadata changes. Changing the destination
folder starts a separate export destination; old notes are left intact.

The default Markdown uses YAML properties, a book heading, author, numbered
blockquotes, available page/location/chapter metadata, highlight dates, and notes.
You can turn these formatting choices on or off and change the date format with
strftime directives, for example `%Y-%m-%d` or `%d %B %Y`.

Backups, preservation of user edits, and keeping missing-book notes are mandatory
in this release. There is no destructive overwrite or automatic deletion mode.

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

The plugin replaces only the region bounded by these markers:

```markdown
<!-- kindle-highlights-sync:begin -->
...generated book heading and highlights...
<!-- kindle-highlights-sync:end -->
```

Keep personal commentary before or after this region. YAML frontmatter is
initially generated above the region, then remains user-owned. User properties,
comments, and line endings outside the region are preserved.

If the managed region has changed since the previous successful write, the
plugin skips that note. Review the existing note and its recoverable backup.
To resume automated updates, move personal edits outside the managed region and
restore the managed region from the latest matching backup. For a missing note,
restore it at its saved path; the plugin deliberately does not silently recreate
or rename it. Backups and state can be inspected using ordinary local tools.

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
