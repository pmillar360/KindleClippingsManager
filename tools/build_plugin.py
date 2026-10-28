"""Build a deterministic plugin ZIP from an explicit source allowlist."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    vendor = ROOT / 'plugin/vendor'
    manifest = json.loads((vendor / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        if hashlib.sha256((vendor / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise ValueError('Vendored dependency changed: ' + name)
    target = ROOT / 'dist/Kindle-Highlights-Sync-0.1.0.zip'
    target.parent.mkdir(exist_ok=True)
    sources = [(p, p.relative_to(ROOT / 'plugin').as_posix()) for p in sorted((ROOT / 'plugin').rglob('*'))
               if p.is_file() and p.suffix in ('.py', '.json', '.txt') and '__pycache__' not in p.parts]
    sources += [(ROOT / 'LICENSE', 'LICENSE'), (ROOT / 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md')]
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in sources:
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 28, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            data = path.read_bytes().replace(b'\r\n', b'\n')
            archive.writestr(info, data)
    with zipfile.ZipFile(target) as archive:
        for name, expected in manifest['files'].items():
            assert hashlib.sha256(archive.read('vendor/' + name)).hexdigest() == expected
    print(str(target))
    print('SHA-256:', hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
