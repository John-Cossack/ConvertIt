"""Editable spreadsheet/presentation conversion and full-page graphic exports."""
from localization import localize
from pathlib import Path
import csv
import tempfile
import zipfile
import openpyxl
import pymupdf

from capabilities import INPUTS, available, input_extension, extension
from external_tools import libreoffice
from transactions import publish
from pdf_convert import PAGE_FORMATS, convert_pdf


def kind(source):
    return INPUTS.get(input_extension(source), {}).get('kind')


def check(source, target):
    rule = INPUTS.get(input_extension(source), {})
    if target not in {r['id'] for r in available(rule.get('format'), rule.get('kind'))}:
        raise ValueError(localize('Цей напрямок конвертації не підтримується.'))
    if input_extension(source) == extension(target):
        raise ValueError(localize('Файл уже має цей формат.'))


def prepare(source, target, work):
    family = 'calc' if kind(source) == 'spreadsheet' else 'impress' if kind(source) == 'presentation' else 'draw'
    staged = work / (source.stem+'.'+extension(target))
    if target in PAGE_FORMATS or target == 'pdf':
        pdf = work / (source.stem+'.pdf')
        libreoffice(source, 'pdf', pdf, work/'office', family=family)
        if target == 'pdf':
            return [pdf]
        return convert_pdf(pdf, target)
    if target == 'csv':
        xlsx = work/'normalized.xlsx'
        libreoffice(source, 'xlsx', xlsx, work/'office', family=family)
        book = openpyxl.load_workbook(xlsx, data_only=False)
        result = []
        try:
            for index, sheet in enumerate(book.worksheets):
                path = work/(source.stem+(f'_{index+1}' if index else '')+'.csv')
                with path.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.writer(stream)
                    for row in sheet.iter_rows(values_only=True):
                        writer.writerow(['' if value is None else value for value in row])
                if not path.stat().st_size:
                    path.write_bytes(b'\xef\xbb\xbf')
                result.append(path)
        finally:
            book.close()
        return result
    libreoffice(source, target, staged, work/'office', family=family)
    if target in {'xlsx','xlsm','ods','pptx','pptm','ppsx','potx','odp','odg'}:
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip():
                raise ValueError(localize('Пошкоджений вихідний документ.'))
    return [staged]


def planned_outputs(source, target):
    source = Path(source).absolute()
    check(source, target)
    # Page/sheet counts are determined by the same engine that converts them.
    # This runs on invocation, never while Explorer is enumerating its menu.
    if target in PAGE_FORMATS or target == 'csv':
        with tempfile.TemporaryDirectory(prefix='.convert-plan-',dir=source.parent) as folder:
            work=Path(folder)
            if target=='csv':
                normalized=work/'normalized.xlsx'
                libreoffice(source,'xlsx',normalized,work/'office',family='calc')
                book=openpyxl.load_workbook(normalized,read_only=True)
                count=len(book.worksheets);book.close()
            else:
                pdf=prepare(source,'pdf',work)[0]
                with pymupdf.open(pdf) as document:count=len(document)
            return [source.with_name(source.stem+(f'_{i+1}' if i else '')+'.'+extension(target)) for i in range(count)]
    return [source.with_suffix('.'+extension(target))]


def convert_office(source, target, overwrite=False):
    source = Path(source).absolute()
    check(source, target)
    with tempfile.TemporaryDirectory(prefix='.convert-office-',dir=source.parent) as folder:
        staged = prepare(source, target, Path(folder))
        return publish([(p,source.parent/p.name) for p in staged],overwrite)
