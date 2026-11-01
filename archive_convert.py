"""Lossless archive repacking in isolated directories; no extracted executables run."""
from localization import localize
from pathlib import Path, PurePosixPath
import bz2
import gzip
import hashlib
import lzma
import os
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile
import json

from capabilities import INPUTS, available, extension, input_extension
from external_tools import ROOT, run_tool

STREAMS = {'gzip', 'bzip2', 'xz', 'lzma', 'Z'}
TYPES = STREAMS | {'7z', 'zip', 'tar', 'Cpio', 'Arj', 'Cab', 'Ar', 'Dmg', 'APFS',
                   'APM', 'FAT', 'HFS', 'Iso', 'Udf', 'Rar', 'Rar5', 'Rpm', 'Lzh',
                   'MBR', 'GPT', 'NTFS', 'Ext', 'Sparse', 'LP'}
PASSWORD = '-pConvertIt-No-Password-Provided'
MAX_ENTRIES = 200_000


def extra_tool(name):
    folder='unar' if name in {'unar','lsar'} else 'cygwin/bin' if name in {'rzip','compress'} else 'posix/usr/bin'
    development='third-party/unar' if folder=='unar' else 'third-party/cygwin/bin' if folder=='cygwin/bin' else 'third-party/posix-runtime/usr/bin'
    for path in [ROOT/folder/(name+'.exe'),ROOT/development/(name+'.exe')]:
        if path.is_file():return path
    raise ValueError(localize('Не знайдено архіватор ')+name)


def unpack_extra(source,work):
    suffix=input_extension(source)
    payload=Path(work)/'files';payload.mkdir(parents=True)
    if suffix=='ace':
        import acefile
        with acefile.open(str(source)) as archive:
            members=archive.getmembers();seen=set()
            if len(members)>MAX_ENTRIES:raise ValueError(localize('Забагато записів архіву.'))
            for member in members:
                raw=member.raw_filename
                name=raw.decode('cp850') if isinstance(raw,bytes) else raw
                key=safe_name(name)
                if key in seen or member.is_enc() or member.attribs&0x400:
                    raise ValueError(localize('ACE містить пароль, посилання або конфлікт імен.'))
                seen.add(key)
                destination=payload/Path(name.replace('\\','/'))
                if member.is_dir():destination.mkdir(parents=True,exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    with destination.open('wb') as stream:
                        for block in archive.readblocks(member):stream.write(block)
    elif suffix in {'alz','arc'}:
        data=json.loads(run_tool([extra_tool('lsar'),'-json','-p','ConvertIt-No-Password',source],Path(work)/'tools'))
        members=data.get('lsarContents',[]);seen=set()
        if len(members)>MAX_ENTRIES or data.get('lsarError'):raise ValueError(localize('Невірний архів.'))
        for member in members:
            key=safe_name(member['XADFileName'])
            if key in seen or any(member.get(k) for k in ['XADIsEncrypted','XADIsLink','XADIsResourceFork','XADIsCorrupted']):
                raise ValueError(localize('Архів містить пароль, посилання, ресурсні потоки або конфлікт імен.'))
            seen.add(key)
        run_tool([extra_tool('unar'),'-q','-D','-f','-nr','-p','ConvertIt-No-Password','-o',payload,source],Path(work)/'tools',timeout=1800)
    elif suffix=='eml':
        from email.parser import BytesParser
        from email import policy
        raw=source.read_bytes();(payload/'message.eml').write_bytes(raw)
        message=BytesParser(policy=policy.default).parsebytes(raw)
        for index,part in enumerate(message.iter_attachments(),1):
            name=part.get_filename() or ('attachment-'+str(index))
            safe_name(name)
            destination=payload/'attachments'/name
            if destination.exists():raise ValueError(localize('Повторне ім’я вкладення EML.'))
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(part.get_payload(decode=True) or b'')
    elif suffix in {'rz','tar.rz'}:
        from djvu_convert import native_path
        decoded=Path(work)/'decoded.tar'
        run_tool([extra_tool('rzip'),'-d','-k','-o',native_path(decoded),native_path(source)],Path(work)/'tools',timeout=1800)
        if tarfile.is_tarfile(decoded):return unpack(decoded,Path(work)/'tar')
        decoded.rename(payload/source.name[:-len(suffix)-1])
    else:
        codec='lzip' if suffix.endswith('lz') else 'lzop'
        decoded=Path(work)/'decoded.tar'
        run_tool([extra_tool(codec),'-d','-k','-o',decoded,source],Path(work)/'tools',timeout=1800)
        if tarfile.is_tarfile(decoded):return unpack(decoded,Path(work)/'tar')
        stem=source.name[:-len(suffix)-1]
        decoded.rename(payload/stem)
    inventory(payload)
    return payload


def binary():
    for candidate in [ROOT / '7zip/7z.exe', ROOT / 'third-party/7zip/7z.exe']:
        if candidate.is_file():
            return candidate
    raise ValueError(localize('Не знайдено портативний 7-Zip.'))


def rar_binary():
    for directory in ['ProgramFiles', 'ProgramFiles(x86)']:
        candidate = Path(os.environ.get(directory, 'C:/Program Files')) / 'WinRAR/Rar.exe'
        if candidate.is_file():
            return candidate
    raise ValueError(localize('Для створення RAR потрібен установлений WinRAR.'))


def is_archive(source):
    return INPUTS.get(input_extension(source), {}).get('kind') == 'archive'


def planned_outputs(source, target):
    source = Path(source).absolute()
    suffix = input_extension(source)
    if not is_archive(source) or target not in {r['id'] for r in available('ARCHIVE', 'archive')}:
        raise ValueError(localize('Цей напрямок перетворення архіву не підтримується.'))
    stem = source.name[:-len(suffix)-1]
    destination = source.with_name(stem + '.' + extension(target))
    if os.path.normcase(str(source)) == os.path.normcase(str(destination)):
        raise ValueError(localize('Файл уже має цей формат.'))
    return [destination]


def safe_name(name):
    name = name.replace('\\', '/')
    if any(ord(c) < 32 for c in name) or any(c in name for c in ':*?"<>|') or name.startswith('/'):
        raise ValueError(localize('Архів містить небезпечне або несумісне з Windows ім’я: ') + repr(name))
    parts = name.rstrip('/').split('/')
    if any(p == '..' or (p not in {'.', ''} and (p.endswith((' ', '.')) or
           re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p))) for p in parts):
        raise ValueError(localize('Архів містить небезпечний шлях: ') + repr(name))
    return str(PurePosixPath(name)).casefold()


def validate_members(source):
    """Use structured headers for ZIP/TAR, including names with newlines."""
    members = []
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for item in archive.infolist():
                mode = item.external_attr >> 16
                if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ValueError(localize('Архів містить посилання або спеціальні файли, які не можна безпечно перепакувати.'))
                if item.flag_bits & 1:
                    raise ValueError(localize('Архів захищено паролем. Спочатку розпакуйте його самостійно.'))
                members.append(item.filename)
    elif tarfile.is_tarfile(source):
        with tarfile.open(source) as archive:
            for item in archive:
                if not (item.isfile() or item.isdir()):
                    raise ValueError(localize('Архів містить посилання або спеціальні файли, які ця версія не перепаковує.'))
                members.append(item.name)
                if len(members) > MAX_ENTRIES:
                    raise ValueError(localize('Архів містить понад 200 000 записів.'))
    seen = set()
    for name in members:
        key = safe_name(name)
        if key in seen:
            raise ValueError(localize('Архів містить повторні або нечутливі до регістру однакові імена.'))
        seen.add(key)


def listing(source, work):
    validate_members(source)
    output = run_tool([binary(), 'l', '-slt', '-sccUTF-8', PASSWORD, '--', source], work).decode('utf-8-sig')
    header, separator, body = output.replace('\r\n', '\n').partition('----------\n')
    kind = re.search(r'^Type = (.+)$', header, re.M)
    if not separator or not kind or kind[1] not in TYPES:
        raise ValueError(localize('Вміст не є підтримуваним архівом.'))
    records, record = [], {}
    for line in (body+'\n').splitlines():
        if not line:
            if record:
                records.append(record)
                record = {}
        else:
            key, sep, value = line.partition(' = ')
            if not sep or key in record:
                raise ValueError(localize('Архів має неоднозначні або несумісні імена записів.'))
            record[key] = value
    if len(records) > MAX_ENTRIES:
        raise ValueError(localize('Архів містить понад 200 000 записів.'))
    seen, total = set(), 0
    for record in records:
        key = safe_name(record.get('Path', ''))
        if key in seen:
            raise ValueError(localize('Імена записів архіву конфліктують у Windows.'))
        seen.add(key)
        if record.get('Encrypted') == '+':
            raise ValueError(localize('Архів захищено паролем. Спочатку розпакуйте його самостійно.'))
        if any(record.get(k) for k in ['Symbolic Link', 'Hard Link']) or record.get('Alternate Stream') == '+':
            raise ValueError(localize('Архів містить посилання або додаткові потоки даних.'))
        attributes = record.get('Attributes', '')
        if re.search(r'(?:^|\s)[lbcps][rwx-]{9}', attributes):
            raise ValueError(localize('Архів містить спеціальні файли або посилання.'))
        size = record.get('Size', '')
        if size:
            total += int(size)
    if total * 2 + 32_000_000 > shutil.disk_usage(Path(work).anchor).free:
        raise ValueError(localize('Недостатньо вільного місця для розпакування та перевірки архіву.'))
    return kind[1]


def unpack(source, work, compound=False):
    if input_extension(source) in {'ace','alz','arc','eml','lz','lzo','tar.lz','tar.lzo','tzo','rz','tar.rz'}:
        return unpack_extra(source,work)
    current = source
    for depth in range(4):
        step = Path(work) / str(depth)
        step.mkdir(parents=True)
        kind = listing(current, step / 'tools')
        payload = step / 'files'
        run_tool([binary(), 'x', '-y', '-aoa', '-sccUTF-8', PASSWORD, '-o'+str(payload), '--', current], step / 'tools', timeout=1800)
        payload.mkdir(exist_ok=True)
        inventory(payload)  # Reject reparse points before any subsequent reading.
        children = list(payload.iterdir())
        if len(children) == 1 and children[0].is_file() and (kind in STREAMS or compound):
            nested = children[0]
            if tarfile.is_tarfile(nested):
                current, compound = nested, False
                continue
            if compound:
                raise ValueError(localize('Складений архів не містить очікуваного TAR.'))
        return payload
    raise ValueError(localize('Забагато вкладених шарів стиснення.'))


def inventory(folder):
    result = {}
    for path in sorted(Path(folder).rglob('*')):
        info = path.lstat()
        if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400 or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError(localize('Результат містить посилання або спеціальний файл.'))
        name = path.relative_to(folder).as_posix()
        safe_name(name)
        if path.is_dir():
            result[name] = None
        else:
            with path.open('rb') as stream:
                result[name] = (info.st_size, hashlib.file_digest(stream, 'sha256').hexdigest())
    return result


def write_tar(payload, destination):
    with tarfile.open(destination, 'w', format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(payload.rglob('*')):
            archive.add(path, arcname=path.relative_to(payload).as_posix(), recursive=False)


def pack(payload, target, staged, work):
    if target in {'rz','tar.rz'}:
        from djvu_convert import native_path
        tar=work/'content.tar';write_tar(payload,tar)
        run_tool([extra_tool('rzip'),'-9','-k','-o',native_path(staged),native_path(tar)],work/'pack-tools',timeout=1800)
    elif target in {'z','tar.z','tz'}:
        from djvu_convert import native_path
        tar=work/'content.tar';write_tar(payload,tar)
        run_tool([extra_tool('compress'),'-f',native_path(tar)],work/'pack-tools',timeout=1800)
        tar.with_name(tar.name+'.Z').rename(staged)
    elif target in {'lz','lzo','tar.lz','tar.lzo','tzo'}:
        tar=work/'content.tar';write_tar(payload,tar)
        codec='lzip' if target.endswith('lz') else 'lzop'
        run_tool([extra_tool(codec),'-9','-k','-o',staged,tar],work/'pack-tools',timeout=1800)
    elif target=='iso':
        import pycdlib
        image=pycdlib.PyCdlib();image.new(interchange_level=3,joliet=3,rock_ridge='1.09',vol_ident='CONVERTAPP')
        mapping={Path('.'):''}
        try:
            for index,path in enumerate(sorted(payload.rglob('*')),1):
                relative=path.relative_to(payload);parent=mapping[relative.parent]
                if path.is_dir():
                    iso=parent+'/D'+str(index)
                    image.add_directory(iso_path=iso,rr_name=path.name,joliet_path='/'+relative.as_posix())
                    mapping[relative]=iso
                else:
                    image.add_file(str(path),iso_path=parent+'/F'+str(index)+'.DAT;1',rr_name=path.name,joliet_path='/'+relative.as_posix())
            image.write(str(staged))
        finally:image.close()
    elif target == 'rar':
        run_tool([rar_binary(), 'a', '-ma5', '-m5', '-mt2', '-r', '-idq', '-y', '-cfg-', staged, '.'],
                 work / 'pack-tools', timeout=1800, cwd=payload)
    elif target in {'7z', 'zip', 'jar'}:
        run_tool([binary(), 'a', '-t'+('zip' if target == 'jar' else target), '-mx=9', '-mmt=2', staged, '.'], work / 'pack-tools', timeout=1800, cwd=payload)
    elif target == 'tar':
        write_tar(payload, staged)
    elif target == 'cpio':
        tar = Path(os.environ['SystemRoot']) / 'System32/tar.exe'
        run_tool([tar, '--format=newc', '--options=hdrcharset=UTF-8', '-cf', staged, '-C', payload, '.'], work)
    else:
        tar = work / 'content.tar'
        write_tar(payload, tar)
        codec = {'bz':'bz2', 'tbz':'bz2', 'tbz2':'bz2', 'tgz':'gz'}.get(target, target.removeprefix('tar.'))
        if codec == 'bz':
            codec = 'bz2'
        if codec == '7z':
            run_tool([binary(), 'a', '-t7z', '-mx=9', '-mmt=2', staged, tar], work, timeout=1800)
        else:
            opener = {'gz':gzip.open, 'bz2':bz2.open, 'xz':lzma.open, 'lzma':lzma.open}[codec]
            options = {'format':lzma.FORMAT_ALONE} if codec == 'lzma' else {}
            with tar.open('rb') as source, opener(staged, 'wb', **options) as destination:
                shutil.copyfileobj(source, destination, 1024*1024)


def convert_archive(source, target, overwrite=False):
    source = Path(source).absolute()
    destination = planned_outputs(source, target)[0]
    if destination.exists() and (not overwrite or destination.is_dir()):
        raise FileExistsError(str(destination))
    with tempfile.TemporaryDirectory(prefix='.convert-archive-', dir=source.parent) as directory:
        work = Path(directory)
        payload = unpack(source, work / 'input', input_extension(source).startswith('tar.'))
        original = inventory(payload)
        staged = work / destination.name
        pack(payload, target, staged, work)
        # Reopen the actual generated format and compare every filename, empty
        # directory and SHA-256, before publishing any result beside the source.
        checked = unpack(staged, work / 'verify', target.startswith('tar.'))
        if original != inventory(checked):
            raise ValueError(localize('Перевірка архіву не пройдена: імена або вміст файлів змінилися.'))
        if overwrite:
            os.replace(staged, destination)
        else:
            os.link(staged, destination)
    return destination
