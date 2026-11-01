"""Portable official MSYS CLI runtime, without installing MSYS on Windows."""
from pathlib import Path
import hashlib,re,tarfile,urllib.request,sys
root=Path(__file__).resolve().parent.parent
cache=root/'third-party/msys-cache';cache.mkdir(exist_ok=True)
output=root/'third-party/posix-runtime';output.mkdir(exist_ok=True)
seen=set()
def fetch(name):
    if name in seen:return
    seen.add(name)
    html=urllib.request.urlopen('https://packages.msys2.org/packages/'+name).read().decode()
    urls=re.findall(r'https://mirror\.msys2\.org/msys/[^"<>\s]+\.pkg\.tar\.(?:zst|xz)',html)
    if not urls:raise RuntimeError('No binary package: '+name)
    url=urls[0];file=cache/url.rsplit('/',1)[1]
    if not file.exists():urllib.request.urlretrieve(url,file)
    checksum=re.search(r'SHA256:.*?([0-9a-f]{64})',html,re.S)
    if checksum and hashlib.sha256(file.read_bytes()).hexdigest()!=checksum[1]:raise RuntimeError('Checksum mismatch')
    with tarfile.open(file,'r:*') as archive:
        info=archive.extractfile('.PKGINFO').read().decode()
        for item in archive:
            if item.isfile() and '..' not in Path(item.name).parts and item.name.startswith(('usr/','etc/')):
                destination=output/item.name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(archive.extractfile(item).read())
    print(name,flush=True)
    for dependency in re.findall(r'^depend = ([^\n]+)',info,re.M):fetch(re.split(r'[<>=]',dependency)[0])
for name in sys.argv[1:]:
    try:fetch(name)
    except Exception as e:print('MISSING',name,str(e),flush=True)
