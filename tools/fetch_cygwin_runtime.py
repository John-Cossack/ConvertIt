"""Read official Cygwin package metadata; extract runtime files, never install."""
from pathlib import Path
import urllib.request,hashlib,re,tarfile,sys
root=Path(__file__).resolve().parent.parent
base='https://www.mirrorservice.org/sites/sourceware.org/pub/cygwin/'
cache=root/'third-party/cygwin-cache';cache.mkdir(exist_ok=True)
out=root/'third-party/cygwin';out.mkdir(exist_ok=True)
metadata=urllib.request.urlopen(base+'x86_64/setup.ini').read().decode()
packages={}
for block in metadata.split('\n@ ')[1:]:
    name,body=block.split('\n',1);body=re.split(r'\n\[(?:prev|test)\]',body)[0]
    install=re.search(r'^install: (\S+) \d+ ([0-9a-f]+)',body,re.M)
    requires=re.search(r'^(?:requires|depends2): (.*)$',body,re.M)
    dependencies=[]
    if requires:
        values=re.sub(r'\([^)]*\)','',requires[1]).replace(',',' ')
        dependencies=values.split()
    if install:packages[name]=(install[1],install[2],dependencies)
seen=set()
def fetch(name):
    if name in seen:return
    seen.add(name)
    if name.startswith('_'):return
    if name not in packages:raise RuntimeError('Missing package: '+name)
    url,sha,deps=packages[name];file=cache/Path(url).name
    if not file.exists():urllib.request.urlretrieve(base+url,file)
    if hashlib.sha512(file.read_bytes()).hexdigest()!=sha:raise RuntimeError('SHA512 mismatch')
    with tarfile.open(file,'r:*') as archive:
        for entry in archive:
            if not entry.isfile() or '..' in Path(entry.name).parts:continue
            if entry.name.startswith('usr/bin/'):
                destination=out/'bin'/Path(entry.name).name
            elif entry.name.startswith(('usr/share/djvu/','usr/share/doc/')):
                destination=out/Path(entry.name).relative_to('usr')
            else:continue
            if any(':' in part for part in destination.parts[1:]):continue
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(archive.extractfile(entry).read())
    print(name,flush=True)
    for dependency in deps:fetch(dependency)
for name in sys.argv[1:]:
    try:fetch(name)
    except Exception as e:print('MISSING',name,str(e),flush=True)
