"""Calibre book conversion using an isolated profile and original images."""
from localization import localize
from pathlib import Path
import os
import tempfile
import zipfile
import re
import unicodedata
from external_tools import locate,run_tool
from transactions import publish


def convert_ebook(source,target,overwrite=False):
    source=Path(source).absolute();destination=source.with_suffix('.'+target)
    if source==destination:
        raise ValueError(localize('Файл уже має цей формат.'))
    if destination.exists() and (not overwrite or destination.is_dir()):
        raise FileExistsError(str(destination))
    with tempfile.TemporaryDirectory(prefix='.convert-book-',dir=source.parent) as folder:
        work=Path(folder);staged=work/('book' if target=='oeb' else 'book.'+target)
        options=['--output-profile','tablet']
        if target=='epub':options+=['--epub-max-image-size','none']
        if target=='mobi':options+=['--mobi-keep-original-images']
        if source.suffix.lower() in {'.cbz','.cbr','.cbc','.cb7'}:options+=['--no-process']
        run_tool([locate('calibre'),source,staged,*options],work,timeout=1800)
        if target in {'pdb','pmlz','snb','rb','tcr','lrf','lit'}:
            # Older book encodings can silently replace Cyrillic with question marks.
            reference=work/'reference.txt';roundtrip=work/'roundtrip.txt'
            for book,text in ((source,reference),(staged,roundtrip)):
                run_tool([locate('calibre'),book,text,'--txt-output-encoding','utf-8'],work,timeout=1800)
            def words(path):
                return set(re.findall(r'[^\W\d_]+',unicodedata.normalize('NFC',path.read_text(encoding='utf-8-sig')).casefold()))
            if not words(reference).issubset(words(roundtrip)):
                raise ValueError(localize('Цей старий формат не зберігає весь текст цієї книги. Виберіть EPUB, AZW3 або DOCX.'))
        if staged.is_dir():
            if destination.exists():raise FileExistsError(str(destination))
            staged.rename(destination)
        else:
            if zipfile.is_zipfile(staged):
                with zipfile.ZipFile(staged) as archive:
                    if archive.testzip():raise ValueError(localize('Пошкоджена вихідна книга.'))
            publish([(staged,destination)],overwrite)
    return destination
