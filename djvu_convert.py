"""DjVuLibre native-resolution PDF rendering, plus its existing OCR text."""
from localization import localize
from pathlib import Path
import os
import tempfile
import pymupdf
from external_tools import ROOT,run_tool
from pdf_convert import convert_pdf,PAGE_FORMATS
from transactions import publish


def tool(name):
    for path in [ROOT/('cygwin/bin/'+name+'.exe'),ROOT/('third-party/cygwin/bin/'+name+'.exe')]:
        if path.is_file():return path
    raise ValueError(localize('Не знайдено DjVuLibre.'))


def native_path(path):
    path=Path(path).absolute()
    return '/cygdrive/'+path.drive[0].lower()+path.as_posix()[2:]


def render(source,pdf,work):
    run_tool([tool('ddjvu'),'-format=pdf',native_path(source),native_path(pdf)],work,timeout=1800)
    text=run_tool([tool('djvutxt'),native_path(source)],work).decode('utf-8')
    pages=text.split('\f')
    if text.strip():
        original=work/'rendered.pdf';pdf.rename(original)
        with pymupdf.open(original) as document:
            font=Path(os.environ['SystemRoot'])/'Fonts/arial.ttf'
            for index,page in enumerate(document):
                if index<len(pages) and pages[index].strip():
                    page.insert_text((2,3),pages[index],fontname='OCR',fontfile=str(font),fontsize=1,render_mode=3)
            document.save(pdf,deflate=True)
    return text


def planned_outputs(source,target):
    source=Path(source).absolute()
    if target not in PAGE_FORMATS:return [source.with_suffix('.'+target)]
    with tempfile.TemporaryDirectory(prefix='.convert-plan-',dir=source.parent) as directory:
        count=int(run_tool([tool('djvused'),native_path(source),'-e','n'],Path(directory)).decode().strip())
    return [source.with_name(source.stem+(f'_{i+1}' if i else '')+'.'+target) for i in range(count)]


def convert_djvu(source,target,overwrite=False):
    source=Path(source).absolute()
    with tempfile.TemporaryDirectory(prefix='.convert-djvu-',dir=source.parent) as directory:
        work=Path(directory);pdf=work/(source.stem+'.pdf')
        text=render(source,pdf,work)
        if target in {'txt','md'}:
            if not text.strip():raise ValueError(localize('DJVU не має OCR-тексту. Спочатку потрібне OCR; оберіть PDF або зображення.'))
            staged=work/(source.stem+'.'+target);staged.write_text(text,encoding='utf-8');outputs=[staged]
        else:outputs=[pdf] if target=='pdf' else convert_pdf(pdf,target)
        return publish([(p,source.parent/p.name) for p in outputs],overwrite)
