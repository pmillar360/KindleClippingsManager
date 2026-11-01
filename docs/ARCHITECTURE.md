# Architecture and maintenance

The legacy Vue app stays available as `index.html`, `js/`, and `css/`.
Its multilingual parsing rules, raw metadata round-trip behavior, and original
ordering were ported to Python. Its transient sequential IDs and destructive
deletion model were replaced with stable identities and persistent decisions.

## Boundaries

- `plugin/core/models.py`: normalized books, formats, annotations, sources,
  batches, destination, and state models.
- `plugin/importers/clippings.py`: seven-language parser and cleaned serialization.
- `plugin/importers/recovery.py`: KRDS decode, KFX text positions, Ion navigation.
- `plugin/core/pipeline.py`: read-only discovery and per-source failure isolation.
- `plugin/core/matching.py`: scoped Calibre identity, identifiers, conservative
  title/author matching, and explicit device/user mappings.
- `plugin/core/storage.py`: SQLite migration, provenance aliases, import history,
  reconciliation, edit overrides, and independent exclusions.
- `plugin/core/markdown.py`: the single source-independent renderer.
- `plugin/core/note_merge.py`: stable-block three-way merging, book-order
  insertion, retained local edits, historical duplicate reconciliation.
- `plugin/core/sync.py`: validation, preview plans, ownership checks, recoverable
  backups, journal, replacement, and successful synchronization events.
- `plugin/calibre_adapter.py`: library snapshots and read-only device adapters.
- `plugin/config.py`, `ui.py`, `action.py`: native Qt configuration, management,
  preview, progress, workers, and toolbar action.

The plugin opens SQLite in the thread that owns its work. Workers receive plain
metadata snapshots and never operate Qt widgets directly. MTP calls execute on
Calibre’s device thread, not the extraction worker. The device adapter explicitly
lists `.sdr` content without changing Calibre’s normal ignore policy or cache.

## Identity and deduplication

Calibre book identity hashes the library UUID and local book ID. Provisional
source identities hash normalized title/author metadata. Established aliases
survive later matching; source provenance is independent of the canonical ID.
Provisional source books also reconcile against unambiguous stored metadata and
identifiers. Distinct canonical Calibre records are never coalesced this way.

Sync discovery reads only Markdown within the selected destination, excluding
hidden backup folders. Notes are recognized by identity or unambiguous metadata,
not filename suffixes. Sync state stores the generated baseline, separately from
the actual merged note, so personal edits remain distinguishable on later runs.
Highlight bodies merge independently; numbering and chapter headings may update.
Changed notes still use a backed-up atomic file replacement for crash safety.
Duplicate sources are hash-checked and archived only after the canonical note
and state commit. An interrupted archival operation is rediscovered on retry.

Import identity includes annotation kind, source book, positional coordinate
system, selected text, and available creation metadata. KFX content fingerprints
scope PID coordinates to the actual source book data. Page-only records retain
ambiguous repeated occurrences with deterministic occurrence identities.

Repeated identical imports resolve their source aliases first. Other records
merge on compatible positions and text, or across sources with unique matching
text and creation time corroboration. Timestamp comparisons tolerate stored
subsecond precision differences, without assuming a timezone for naive dates.
Ambiguous candidates are retained and reported.

Kindle locations and KFX PIDs are separate fields. Embedded location maps are not
trusted merely because they exist: multiple distinct known clippings must agree
on start/end locations before the map is used for clipping-limit reconciliation.
Otherwise placeholders remain pending and recovered highlights are separately
available. No estimated ratio or EPUB character-offset mapping is used.

## Recovery compatibility fixes

Navigation supports inline `IonAnnotation` values, `YJFragment` wrappers, and
`IonSymbol` references. It resolves target element IDs through the library’s
position map and traverses nested navigation entries. Unresolved targets do not
default to position zero. Unsupported navigation drops optional navigation
metadata and records a warning without disabling text extraction.

The decoded KFX object provides metadata directly. Calling `get_metadata()` on
an already decoded object would reload fragments and introduce duplicate metadata
keys, so the wrapper uses `get_yj_metadata_from_book()` instead.

Reconstruction checks actual text-chunk lengths, slices inclusive annotation
ranges, supports single-character selections, and refuses boundaries outside
supported text. It retains paragraph gaps rather than inferring text lengths
from the next section. Unsupported fixed-layout/print-replica books are rejected.

See THIRD_PARTY_NOTICES.md and `plugin/vendor/manifest.json` for source pins,
checksums, GPL notices, and the two local dependency patches.

## Build and dependency updates

`calibre-debug tools/build_plugin.py` creates a deterministic ZIP with a fixed
timestamp and normalized line endings. It verifies the dependency manifest and
then verifies the packaged dependency bytes. Source fixtures and local state are
excluded by an explicit source allowlist.

Maintainer-only dependency refresh:

1. Download the reviewed KRDS file and KFX Input archive into ignored `.deps/`.
2. Review license declarations, source changes, and any transitive dependencies.
3. Deliberately update pins and archive checksums in `tools/vendor_dependencies.py`.
4. Run `calibre-debug tools/vendor_dependencies.py` to reproduce extraction and
   the PDF-import and optional DRM-adapter patches.
5. Run public and private tests, build, install in an isolated profile, and smoke
   test the installed ZIP. Commit the source and updated manifest together.

Nothing is fetched during normal plugin execution. New annotation storage
formats should implement another importer producing the same normalized models.
