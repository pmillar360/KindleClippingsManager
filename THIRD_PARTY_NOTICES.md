# Third-party notices

Kindle Highlights Sync is distributed under GPL-3.0-or-later. See LICENSE.
All processing is local. The plugin never downloads code at runtime.

## KRDS

- Author: John Howell; copyright 2019 John Howell, with upstream contributions.
- License declaration: GPL v3, retained in `plugin/vendor/krds.py`.
- Source: https://github.com/K-R-D-S/KRDS
- Commit: `9c8a0b0ec9cb6af72fba900a6f9b09f92de477de`
- SHA-256: `921ea44e31e872afc38283b9cdfc3d167b11dbad1831379e8fa28ac822d835b2`
- Unmodified. The plugin calls the decoder in memory and supplies a quiet logger;
  it does not call the CLI that writes a JSON file alongside its input.

## kfxlib / KFX Input 2.25.0

- Author: John Howell; copyright 2016–2025 John Howell.
- License declaration: GPL v3, retained in the library source files.
- Project: https://www.mobileread.com/forums/showthread.php?t=291290
- Source archive mirror: https://github.com/aakar/KFX-Highlights/blob/716525d090f94db240c593fd4ea5d5771805e6d2/KFX%20Input.zip
- Archive SHA-256: `a4d95a13d987c9939b2755285663670987aac2afa10993f2ecf24e7526230877`
- Only the `kfxlib/*.py` source files are included. KFX Input GUI/plugin hooks and
  its bundled pypdf package are not included.
- Local modification: `resources.py` makes its unused PDF dependency optional.
  PDF/print-replica conversion is not supported by this plugin.
- Local modification: `yj_book.py` removes the upstream optional DeDRM adapter.
  Encrypted containers are rejected, even if another DRM plugin is installed.
- Runtime dependencies Pillow and lxml are supplied by Calibre. No additional
  installation is required inside Calibre.
- `plugin/vendor/manifest.json` records the hash of each redistributed source file.
  `tools/vendor_dependencies.py` reproduces the extraction and both patches.

## KFX-Highlights research reference

https://github.com/aakar/KFX-Highlights was consulted for annotation format research
and the existing recovery workflow. Its surrounding extraction, shell, Readwise,
and email scripts are not redistributed or imported. Their license could not be
established during review. Our navigation adapter, reconstruction wrapper, and
Calibre integration are implemented in this repository.

The plugin does not implement or bundle DRM circumvention.
