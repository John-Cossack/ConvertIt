"""Copy portable helpers, keeping POSIX DLLs limited to import closures."""
from pathlib import Path
import shutil
import pefile

ROOT=Path(__file__).resolve().parent.parent
DEST=ROOT/'dist/ConvertIt/_internal'
def copy(source,target):
    source=Path(source);target=DEST/target
    if source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True)
    else:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
def closure(folder,names,target):
    files={p.name.lower():p for p in folder.iterdir() if p.is_file()}
    queue=list(names);seen=set()
    while queue:
        name=queue.pop().lower()
        if name in seen:continue
        seen.add(name)
        path=files.get(name)
        if path is None:continue # Windows system imports remain system imports.
        copy(path,target+'/'+path.name)
        pe=pefile.PE(str(path),fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        queue.extend(entry.dll.decode() for entry in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]));pe.close()

for source,target in [('imagemagick','imagemagick'),('ghostscript','ghostscript'),
                      ('fontforge/{app}','fontforge'),('uniconvertor/PFiles/UniConvertor-2.0rc5','uniconvertor'),
                      ('unar','unar'),('sfark-windows/sfarkxtc-windows-3.0b-win64','sfark')]:
    copy(ROOT/'third-party'/source,target)
closure(ROOT/'third-party/libredwg',['dwg2dxf.exe','dxf2dwg.exe'],'libredwg')
closure(ROOT/'third-party/cygwin/bin',['ddjvu.exe','djvutxt.exe','djvused.exe','rzip.exe','compress.exe'],'cygwin/bin')
closure(ROOT/'third-party/posix-runtime/usr/bin',['lzip.exe','lzop.exe'],'posix/usr/bin')
copy(ROOT/'third-party/dwf-runtime/node_modules/dwf-viewer','dwf/node_modules/dwf-viewer')
copy(ROOT/'tools/dwf_render.mjs','dwf/convert.mjs')
copy(Path('C:/Program Files/nodejs/node.exe'),'dwf/node.exe')
copy(ROOT/'third-party/libreoffice-26.8.1/share/uno_packages','libreoffice/share/uno_packages')
copy(ROOT/'third-party/cygwin/share/doc','cygwin/share/doc')
copy(ROOT/'third-party/cygwin/share/djvu','cygwin/share/djvu')
copy(ROOT/'third-party/posix-runtime/usr/share/licenses','posix/usr/share/licenses')
print('Expanded portable runtimes copied.')
