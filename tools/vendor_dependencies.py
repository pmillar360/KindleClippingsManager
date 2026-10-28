"""Maintainer-only vendoring. Downloads are never performed by the plugin."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'KFX-Input.zip': 'a4d95a13d987c9939b2755285663670987aac2afa10993f2ecf24e7526230877',
    'krds.py': '921ea44e31e872afc38283b9cdfc3d167b11dbad1831379e8fa28ac822d835b2',
}


def main():
    target = ROOT / 'plugin' / 'vendor'
    target.mkdir(parents=True, exist_ok=True)
    for name, expected in PINS.items():
        data = (ROOT / '.deps' / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Dependency checksum mismatch: ' + name)
    with zipfile.ZipFile(ROOT / '.deps/KFX-Input.zip') as archive:
        for name in archive.namelist():
            # Only the GPL Python library, no plugin hooks or embedded PDF package.
            parts = Path(name).parts
            if len(parts) == 2 and parts[0] == 'kfxlib' and name.endswith('.py'):
                path = target / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(archive.read(name))
    resources = target / 'kfxlib/resources.py'
    content = resources.read_text(encoding='utf-8')
    original = '''if calibre_numeric_version is not None:
    add_plugin_path()
    import pypdf
    remove_plugin_path()
else:
    import pypdf'''
    replacement = '''# Kindle Highlights Sync: PDF conversion is outside our supported scope.
# Do not require a bundled PDF library just to read reflowable KFX text.
try:
    import pypdf
except ImportError:
    pypdf = None'''
    if original not in content:
        raise ValueError('Unexpected upstream PDF import block')
    resources.write_text(content.replace(original, replacement), encoding='utf-8', newline='\n')
    book_path = target / 'kfxlib/yj_book.py'
    content = book_path.read_text(encoding='utf-8')
    # Remove upstream's optional DeDRM integration, including the import itself.
    # No encrypted container is offered to an installed third-party DRM plugin.
    start = content.index('    def expand_compressed_container(self, data):')
    content = content[:start] + '''    def expand_compressed_container(self, data):
        # Kindle Highlights Sync: encrypted containers are always unsupported.
        return None
'''
    book_path.write_text(content, encoding='utf-8', newline='\n')
    shutil.copyfile(ROOT / '.deps/krds.py', target / 'krds.py')
    manifest = {
        'krds': {'commit': '9c8a0b0ec9cb6af72fba900a6f9b09f92de477de',
                 'url': 'https://github.com/K-R-D-S/KRDS', 'sha256': PINS['krds.py']},
        'kfxlib': {'version': '2.25.0', 'mirror_commit': '716525d090f94db240c593fd4ea5d5771805e6d2',
                   'url': 'https://github.com/aakar/KFX-Highlights', 'archive_sha256': PINS['KFX-Input.zip']},
        'files': {str(p.relative_to(target)).replace('\\', '/'): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                  for p in sorted(target.rglob('*.py')) if p.name != '__init__.py' or p.parent.name == 'kfxlib'},
    }
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
