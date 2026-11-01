"""Offline DWF 2D vector decoding; standard DWFx uses MuPDF's XPS importer."""
from localization import localize
from pathlib import Path
import json
import shutil
import zipfile
import pymupdf
from external_tools import ROOT,locate,run_tool


def render(source,destination,work):
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:opc='[Content_Types].xml' in archive.namelist()
        if opc:
            try:
                with pymupdf.open(stream=Path(source).read_bytes(),filetype='xps') as document:
                    destination.write_bytes(document.convert_to_pdf());return
            except RuntimeError:pass
    script=ROOT/'dwf/convert.mjs'
    node=ROOT/'dwf/node.exe'
    if not script.is_file():script=ROOT/'third-party/dwf-runtime/convert.mjs'
    if not node.is_file():node=shutil.which('node.exe')
    if not node:raise ValueError(localize('Не знайдено локальний DWF runtime.'))
    output=work/'dwf-sheets'
    run_tool([node,script,source,output],work/'decode',timeout=1800)
    paths=json.loads((output/'pages.json').read_text(encoding='utf-8'))
    combined=pymupdf.open()
    try:
        for index,path in enumerate(paths):
            svg=Path(path).resolve()
            if not svg.is_relative_to(output.resolve()):raise ValueError(localize('Некоректний шлях сторінки DWF.'))
            pdf=work/('page-'+str(index)+'.pdf')
            run_tool([locate('inkscape'),svg,'--export-type=pdf','--export-filename='+str(pdf)],work/('inkscape-'+str(index)))
            with pymupdf.open(pdf) as page:combined.insert_pdf(page)
        if not len(combined):raise ValueError(localize('DWF не містить сторінок.'))
        combined.save(destination,deflate=True)
    finally:combined.close()
