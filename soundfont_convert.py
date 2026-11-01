"""sfArk v2 decompression, checked by the decoder's stored checksum."""
from localization import localize
from pathlib import Path
import shutil,struct,tempfile
from external_tools import ROOT,run_tool
from transactions import publish


def flags(source):
    with Path(source).open('rb') as stream:header=stream.read(32)
    if len(header)<32 or header[26:31]!=b'sfArk':raise ValueError(localize('Потрібен звичайний SFARK v2; SFX та інші файли не підтримуються.'))
    value=struct.unpack_from('<I',header)[0]
    if value&2:raise ValueError(localize('SFARK містить вбудовані ліцензійні умови. Відкрийте його в оригінальній sfArk-утиліті для ручного підтвердження.'))
    return value


def planned_outputs(source,target):
    source=Path(source)
    if target!='sf2':raise ValueError(localize('SFARK конвертується лише у SF2.'))
    values=[source.with_suffix('.sf2')]
    if flags(source)&1:values.append(source.with_suffix('.txt'))
    return values


def convert_soundfont(source,target,overwrite=False):
    source=Path(source).absolute();destinations=planned_outputs(source,target)
    binary=next((p for p in [ROOT/'sfark/sfarkxtc.exe',ROOT/'third-party/sfark-windows/sfarkxtc-windows-3.0b-win64/sfarkxtc.exe'] if p.is_file()),None)
    if not binary:raise ValueError(localize('Не знайдено SFARK-декодер.'))
    with tempfile.TemporaryDirectory(prefix='.convert-sfark-',dir=source.parent) as directory:
        work=Path(directory);shutil.copyfile(source,work/'input.sfark')
        run_tool([binary,'input.sfark','output.sf2','--quiet'],work,timeout=1800)
        staged=work/'output.sf2'
        data=staged.read_bytes()
        if data[:4]!=b'RIFF' or data[8:12]!=b'sfbk' or struct.unpack_from('<I',data,4)[0]!=len(data)-8:
            raise ValueError(localize('Декодер не створив повний SF2.'))
        files=[staged]+([work/'output.txt'] if len(destinations)>1 else [])
        return publish(list(zip(files,destinations)),overwrite)
