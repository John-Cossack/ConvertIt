"""Preserve SFNT tables for web-font wrapping; FontForge for outline conversion."""
from localization import localize
from pathlib import Path
import io
import struct
import tempfile
from fontTools.ttLib import TTFont
from external_tools import locate, run_tool
from transactions import publish


def read_font(source):
    data=Path(source).read_bytes()
    if Path(source).suffix.lower()=='.eot':
        if len(data)<82 or struct.unpack_from('<H',data,34)[0]!=0x504c:
            raise ValueError(localize('Невірний EOT.'))
        total,size,version,flags=struct.unpack_from('<4I',data)
        if total!=len(data) or size>total-82:
            raise ValueError(localize('Пошкоджений EOT.'))
        if flags&4:
            raise ValueError(localize('EOT зі стисненням MicroType Express не підтримується; потрібен вихідний TTF/OTF.'))
        data=data[-size:]
        if flags&0x10000000:
            data=bytes(x^0x50 for x in data)
    return TTFont(io.BytesIO(data),recalcTimestamp=False)


def eot_bytes(font):
    font.flavor=None
    buffer=io.BytesIO();font.save(buffer);data=buffer.getvalue()
    os2=font['OS/2'];head=font['head']
    panose=bytes(getattr(os2.panose,n) for n in ['bFamilyType','bSerifStyle','bWeight','bProportion','bContrast','bStrokeVariation','bArmStyle','bLetterForm','bMidline','bXHeight'])
    header=struct.pack('<4I10sBBIHH',0,len(data),0x10000,0,panose,1,int(bool(os2.fsSelection&1)),os2.usWeightClass,os2.fsType,0x504c)
    header+=struct.pack('<11I',*(getattr(os2,'ulUnicodeRange'+str(i),0) for i in range(1,5)),
                        getattr(os2,'ulCodePageRange1',0),getattr(os2,'ulCodePageRange2',0),head.checkSumAdjustment,0,0,0,0)
    for number in [1,2,5,4]:
        value=(font['name'].getDebugName(number) or '').encode('utf-16le')
        header+=struct.pack('<HH',0,len(value))+value
    result=header+data
    return struct.pack('<I',len(result))+result[4:]


def convert_font(source,target,overwrite=False):
    source=Path(source).absolute();destination=source.with_suffix('.'+target)
    if target not in {'ttf','otf','woff','woff2','eot'} or source==destination:
        raise ValueError(localize('Неприпустимий вихідний формат шрифту.'))
    if destination.exists() and not overwrite:
        raise FileExistsError(str(destination))
    with tempfile.TemporaryDirectory(prefix='.convert-font-',dir=source.parent) as folder:
        work=Path(folder);staged=work/('output.'+target)
        original=read_font(source)
        try:
            cmap=set(original.getBestCmap() or {})
            original.flavor=None
            actual='otf' if original.sfntVersion=='OTTO' else 'ttf'
            if target in {'ttf','otf'} and target!=actual:
                if 'fvar' in original or 'COLR' in original or 'CBDT' in original or 'sbix' in original:
                    raise ValueError(localize('Змінні/кольорові шрифти зберігайте у WOFF/WOFF2 або вихідному типі контурів.'))
                native=work/('input.'+actual);original.save(native)
                run_tool([locate('fontforge'),'-lang','ff','-c','Open($1); Generate($2); Close();',native,staged],work)
            elif target=='eot':
                staged.write_bytes(eot_bytes(original))
            else:
                original.flavor=target if target in {'woff','woff2'} else None
                original.save(staged)
            checked=read_font(staged)
            try:
                if set(checked.getBestCmap() or {})!=cmap or checked['maxp'].numGlyphs!=original['maxp'].numGlyphs:
                    raise ValueError(localize('Конвертер змінив набір символів/гліфів; результат не збережено.'))
            finally:
                checked.close()
            publish([(staged,destination)],overwrite)
        finally:
            original.close()
    return destination
