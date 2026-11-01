# Validation — 0.2.0 preview

Version 0.2.0 was validated on Windows on 2026-11-01 using **Calibre 9.17**
with an isolated configuration profile. All **53 Python tests pass**, including
the private recovery test, and all **23 JavaScript tests pass**. The earlier
0.1.0 engine passed 35 tests on Ubuntu Python 3.12.3; the expanded 0.2.0 suite has
not been rerun on Linux. The user's ordinary Calibre configuration and vault were not
modified by testing.

## Automated evidence

- Python suite covers multilingual parsing, malformed records, raw metadata,
  stable identities, cross-source reconciliation, different-position duplicates,
  ambiguous page-only entries, late library mappings, EPUB-only records,
  persistent exclusions and edits, SQLite migration/rejection behavior, YAML,
  multiline Markdown, path validation, filename collisions, and cancellation.
- Synthetic binary YJR fixture exercises the actual KRDS decoder.
- Synthetic text ranges exercise inclusive KFX boundaries and Unicode.
- Synthetic Ion navigation exercises inline annotations and referenced fragments.
- Encrypted ordinary and metadata KFX containers are rejected.
- Sync integration checks user commentary/frontmatter/CRLF preservation,
  managed-section conflicts, backup creation, concurrent preview edits,
  failed replacements, and a file replacement followed by a failed database
  update. Journal recovery makes the next identical sync unchanged.
- Incremental merge checks middle insertion, hidden position labels, numbering,
  chapter grouping, compact metadata, retained manual edits/deletions, simultaneous
  source/user conflicts, and unchanged bytes/mtime/backup count on repeat exports.
- Duplicate-note checks adoption without state, orphaned suffixes, historical
  highlight IDs, unique passage ordering, ambiguous editions, conflicting edits,
  duplicate-file changes after preview, and interrupted archival/retry without
  repeated personal commentary. Archived originals retain their exact bytes.
- The settings smoke check verifies author-folder and custom-filename preview
  values as well as the new formatting controls. Rendered Qt settings were reviewed.
- Mounted-storage and MTP doubles exercise read-only copying, uncached sidecar
  enumeration, corrupt-source isolation, repeated imports, and cancellation.
- The original 23 JavaScript tests use public synthetic fixtures and pass.
- The installed ZIP smoke test creates a real temporary Calibre library retaining
  only EPUB, reads metadata through Calibre’s API, constructs/renders settings,
  preview, and manager widgets, initializes the toolbar action, and completes
  its asynchronous one-click import and vault synchronization using a fallback
  folder. It does not simulate a physical USB connection.

## Private recovery

The ignored local Scattered Minds KFX/YJR fixture recovers **275 highlights**, all
nonempty, with chapter metadata for all 275 and no recovery warnings. Byte
comparisons confirm that KFX and YJR inputs are unchanged. A full local folder
import followed by a repeated import creates zero additional highlights.

The available clipping exports have no timestamp-matched reference passages
for these recovered annotations. Consequently this validation reproduces the
reported recovery count and verifies structural/boundary behavior, but does not
independently certify every passage against a human-reviewed reference selection.
`tools/validate_private.py` prints comparison counts without highlight contents.
Private files are never included in the ZIP or public test fixtures.

## Outstanding release checks

- Physical Kindle connection and disconnection on Windows 11, including MTP
  permissions and any model-specific annotation storage variations.
- Linux Calibre installation, Qt rendering, real device transport, and a native
  Linux vault. The Ubuntu engine run used WSL and the mounted workspace; it does
  not substitute for testing the Calibre GUI or actual hardware on Linux.
- Manual review of recovered selection boundaries against known Kindle selections
  on the actual device and additional books/layouts/firmware revisions.
- Larger-library performance and additional edition-matching cases.

## Intentional limitations

- `ksdk_annotation_v1.db` extraction is not implemented; empty YJR sidecars are
  reported instead of treated as successful recovery.
- Direct EPUB text reconstruction, AZW3/MOBI recovery, fixed-layout/PDF books,
  covers, custom templates, and automatic connection-triggered sync are deferred.
- Conflicts skip the whole affected book note. There is no destructive overwrite
  setting, interactive three-way merge, or note-destination reset UI.
- YAML frontmatter becomes user-owned after creation. Managed metadata in the
  body updates; arbitrary user properties are never rewritten.
- Mappings can be selected in the manager but currently cannot be undone there.
- Calibre 9.17 is the minimum supported version because it is the API/runtime
  version tested. Compatibility with older Calibre releases is not claimed.

## Reproduce

Use the commands in README.md. `KHS_PRIVATE_TESTS=1` enables the private fixture
check; otherwise it is skipped. `tools/smoke_calibre.py` loads the installed ZIP,
so rebuild and reinstall in the isolated profile after changing plugin code.
