"""Remove development/UI-only payloads from a staged ConvertIt distribution.

Keep all conversion filters, codecs, fonts, hyphenation dictionaries and notices.
The same rules are used when repacking an existing release and in fresh builds.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import re

LANGUAGES = {'common', 'en', 'en_US', 'en-US', 'en_GB', 'en-GB', 'en_ZA', 'en-ZA', 'uk', 'uk-UA'}

def reason(name):
    path = PurePosixPath(name.replace('\\', '/'))
    parts = path.parts
    if not parts or parts[0] != '_internal':
        return None
    if '__pycache__' in parts:
        return 'Interpreter caches'
    p = '/'.join(parts[1:])
    if p.startswith('imagemagick/') and path.suffix.lower() == '.exe' and path.name.lower() != 'magick.exe':
        return 'Duplicate ImageMagick commands'
    if p.startswith('libreoffice/program/resource/') and len(parts) > 4 and parts[4] not in LANGUAGES:
        return 'Unused LibreOffice UI languages'
    if p.startswith('libreoffice/share/registry/res/'):
        match = re.match(r'(?:fcfg_langpack|registry)_(.+)\.xcd$', path.name)
        if match and match[1] not in LANGUAGES:
            return 'Unused LibreOffice UI languages'
    if p.startswith('libreoffice/share/extensions/dict-'):
        if path.suffix.lower() in {'.dic', '.dat', '.idx'} and not path.name.startswith('hyph_'):
            return 'Spellcheck and thesaurus word lists'
    if p.startswith('libreoffice/help/'):
        return 'LibreOffice help'
    if p.startswith('libreoffice/share/config/images_') and path.suffix == '.zip' and path.name not in {'images_colibre.zip', 'images_helpimg.zip'}:
        return 'Alternate LibreOffice toolbar themes'
    if p.startswith(('inkscape/share/inkscape/tutorials/', 'inkscape/share/inkscape/examples/',
                     'inkscape/share/inkscape/extensions/', 'inkscape/include/',
                     'inkscape/lib/python3.12/', 'inkscape/share/gdb/')):
        return 'Inkscape tutorials, script extensions and SDK'
    if p.startswith('inkscape/share/locale/') and len(parts) > 4 and parts[4] not in LANGUAGES:
        return 'Unused Inkscape UI languages'
    if p in {'inkscape/bin/gdb.exe', 'inkscape/bin/inkview.exe', 'inkscape/bin/python.exe', 'inkscape/bin/pythonw.exe', 'inkscape/lib/lib2geom.dll.a'}:
        return 'Unused Inkscape helper programs'
    if p.startswith('inkscape/lib/') and path.suffix in {'.a', '.la'}:
        return 'Inkscape development link libraries'
    if p.startswith(('ghostscript/doc/', 'ghostscript/examples/', 'ghostscript/man/')) or p == 'ghostscript/vcredist_x64.exe':
        return 'Ghostscript manuals and unused installer'
    if p.startswith(('pymupdf/layout/', 'pymupdf/mupdf-devel/', 'onnxruntime/')):
        return 'Unused PDF layout AI and SDK'
    if p.startswith('fontforge/lib/python3.12/site-packages/') and any(part.startswith(('pip', 'setuptools')) for part in parts[5:]):
        return 'FontForge package managers'
    return None

def prune(root):
    root = Path(root).resolve()
    if not (root / 'ConvertIt.exe').is_file() or 'WindowsApps' in root.parts:
        raise ValueError('Only a staged ConvertIt distribution can be pruned.')
    removed = 0
    for path in root.rglob('*'):
        if path.is_file() and reason(path.relative_to(root).as_posix()):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Refusing a linked file outside the staging directory.')
            removed += path.stat().st_size
            path.unlink()
    duplicate=root/'_internal/pymupdf/mupdfcpp64.dll'
    shared=root/'_internal/mupdfcpp64.dll'
    if duplicate.is_file() and shared.is_file():
        with duplicate.open('rb') as a,shared.open('rb') as b:
            same=hashlib.file_digest(a,'sha256').digest()==hashlib.file_digest(b,'sha256').digest()
        if same:
            # PyInstaller adds _internal to the DLL search path at startup.
            removed+=duplicate.stat().st_size
            duplicate.unlink()
    print(f'Removed {removed / 1024**2:.1f} MiB of unused payload.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    prune(args.directory)
