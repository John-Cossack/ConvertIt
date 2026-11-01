"""Local PDF export with page-aware naming and transactional publication."""
from localization import localize
from pathlib import Path
import os
import shutil
import tempfile
import html
import zipfile
from lxml import etree as ET

import pymupdf
from capabilities import available, extension
from external_tools import locate, run_tool, libreoffice

PAGE_FORMATS = {'avif','bmp','eps','gif','ico','jpg','odd','png','ps','psd','tiff','webp','svg','emf','wmf','dxf','svgz','psb','icns','ppm','tga','sk','sk1','cdr','cgm'}
DPI = 600
MAX_PIXELS = 100_000_000


def open_pdf(source):
    document = pymupdf.open(source)
    if not document.is_pdf or document.needs_pass or not len(document):
        document.close()
        raise ValueError(localize('PDF пошкоджено, порожній або захищено паролем.'))
    return document


def planned_outputs(source, target):
    source = Path(source).absolute()
    if target not in {row['id'] for row in available('PDF', 'pdf')}:
        raise ValueError(localize('Цей напрямок перетворення PDF не підтримується.'))
    if target == 'pdf':
        raise ValueError(localize('Файл уже має формат PDF.'))
    with open_pdf(source) as document:
        count = len(document) if target in PAGE_FORMATS else 1
    return [source.with_name(source.stem + (f'_{i+1}' if i else '') + '.' + extension(target)) for i in range(count)]


def render(page, destination):
    scale = DPI / 72
    if page.rect.width * page.rect.height * scale * scale > MAX_PIXELS:
        raise ValueError(localize('Сторінка завелика для 600 dpi (понад 100 Мп). Розділіть або зменште сторінку PDF.'))
    pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csRGB, alpha=False)
    pix.save(destination)


def text_pages(document):
    pages = [page.get_text('text', sort=True).strip() for page in document]
    missing = [str(i+1) for i, text in enumerate(pages) if not text and document[i].get_images()]
    if missing:
        raise ValueError(localize('Потрібне OCR для сканованих сторінок: ') + ', '.join(missing) + localize('. Оберіть зображення або презентацію.'))
    return pages


def vector_page(page, source, target, destination, work):
    svg = work / 'page.svg'
    svg.write_text(page.get_svg_image(text_as_path=True), encoding='utf-8')
    if target=='svgz':
        import gzip
        destination.write_bytes(gzip.compress(svg.read_bytes(),compresslevel=9));return
    if target in {'sk','sk1','cdr','cgm'}:
        from sk_convert import convert
        convert(svg,target,destination,work/'uniconvertor');return
    if target == 'svg':
        shutil.copyfile(svg, destination)
        return
    command = [locate('inkscape'), svg, '--export-type=' + target, '--export-filename=' + str(destination)]
    if target == 'dxf':
        command.append('--export-extension=org.ekips.output.dxf_outlines')
    run_tool(command, work)
    if not destination.is_file() or not destination.stat().st_size:
        raise ValueError(localize('Не вдалося створити ') + target.upper())
    if target == 'dxf' and page.get_images():
        # DXF cannot contain arbitrary PDF raster graphics. Keep a real PDF underlay
        # referring to the adjacent original, rather than silently losing those images.
        import ezdxf
        drawing = ezdxf.readfile(destination)
        drawing.dxfversion = 'AC1024'
        definition = drawing.add_underlay_def(filename=source.name, fmt='pdf', name=str(page.number + 1))
        drawing.modelspace().add_underlay(definition, insert=(0, 0, 0), scale=25.4)
        drawing.saveas(destination)


def slides(document, destination, work):
    from pptx import Presentation
    from pptx.util import Inches
    presentation = Presentation()
    presentation.slide_width = Inches(13.333333)
    presentation.slide_height = Inches(7.5)
    svgs = []
    for i, page in enumerate(document):
        png = work / f'slide-{i}.png'
        render(page, png)
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        factor = min(presentation.slide_width/page.rect.width, presentation.slide_height/page.rect.height)
        width, height = round(page.rect.width*factor), round(page.rect.height*factor)
        slide.shapes.add_picture(str(png), (presentation.slide_width-width)//2, (presentation.slide_height-height)//2, width, height)
        svgs.append(page.get_svg_image(text_as_path=True).encode('utf-8'))
    raw = work / 'slides.pptx'
    presentation.save(raw)
    # Office displays native scalable SVG, with a high-resolution PNG fallback.
    ns = {'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
          'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
          'asvg':'http://schemas.microsoft.com/office/drawing/2016/SVG/main'}
    relns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    with zipfile.ZipFile(raw) as src, zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as dst:
        updates = {}
        content = ET.fromstring(src.read('[Content_Types].xml'))
        ET.SubElement(content, '{http://schemas.openxmlformats.org/package/2006/content-types}Default', Extension='svg', ContentType='image/svg+xml')
        updates['[Content_Types].xml'] = ET.tostring(content, encoding='utf-8', xml_declaration=True)
        for i, svg in enumerate(svgs, 1):
            slidepath = f'ppt/slides/slide{i}.xml'
            root = ET.fromstring(src.read(slidepath))
            blip = root.find('.//a:blip', ns)
            extlist = ET.SubElement(blip, '{'+ns['a']+'}extLst')
            ext = ET.SubElement(extlist, '{'+ns['a']+'}ext', uri='{96DAC541-7B7A-43D3-8B79-37D633B846F1}')
            ET.SubElement(ext, '{'+ns['asvg']+'}svgBlip', {'{'+ns['r']+'}embed':'rIdPdfSvg'})
            updates[slidepath] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            relpath = f'ppt/slides/_rels/slide{i}.xml.rels'
            rel = ET.fromstring(src.read(relpath))
            ET.SubElement(rel, '{'+relns+'}Relationship', Id='rIdPdfSvg', Type=ns['r']+'/image', Target=f'../media/pdf-page-{i}.svg')
            updates[relpath] = ET.tostring(rel, encoding='utf-8', xml_declaration=True)
            dst.writestr(f'ppt/media/pdf-page-{i}.svg', svg)
        for item in src.infolist():
            dst.writestr(item, updates.get(item.filename, src.read(item.filename)))


def spreadsheet(document, target, destination):
    import openpyxl
    import xlwt
    book = openpyxl.Workbook() if target == 'xlsx' else xlwt.Workbook()
    if target == 'xlsx':
        book.remove(book.active)
    count = 0
    for index, page in enumerate(document):
        for number, table in enumerate(page.find_tables(use_layout=False).tables, 1):
            count += 1
            name = f"{localize('Сторінка ')}{index + 1}-{number}"
            sheet = book.create_sheet(name) if target == 'xlsx' else book.add_sheet(name)
            for rowid, row in enumerate(table.extract()):
                for colid, value in enumerate(row):
                    text = '' if value is None else str(value)
                    if target == 'xlsx':
                        cell = sheet.cell(rowid+1, colid+1, text)
                        cell.data_type = 's'  # PDF text must never become executable Excel formulas.
                    else:
                        sheet.write(rowid, colid, text)
    if not count:
        raise ValueError(localize('У PDF не знайдено таблиць. Для тексту оберіть DOCX, TXT або HTML; для сканів спочатку потрібне OCR.'))
    book.save(destination)


def produce(document, source, target, staged, work):
    if target in PAGE_FORMATS:
        for page, destination in zip(document, staged):
            pagework = work / f'page-{page.number}'
            pagework.mkdir()
            if target in {'svg','svgz','emf','wmf','eps','ps','dxf','sk','sk1','cdr','cgm'}:
                vector_page(page, source, target, destination, pagework)
            else:
                png = pagework / 'render.png'
                render(page, png)
                if target == 'png':
                    shutil.copyfile(png, destination)
                else:
                    from converter import convert
                    # A different basename avoids PNG -> PNG and collision cases.
                    converted = convert(png, target, allow_flatten=True)
                    if isinstance(converted, list):
                        if len(converted) != 1:
                            raise ValueError(localize('Конвертер сторінки повернув неочікувану кількість файлів.'))
                        converted = converted[0]
                    shutil.move(converted, destination)
        return
    destination = staged[0]
    if target in {'txt','md'}:
        pages = text_pages(document)
        if target == 'md':
            import re
            pages = [re.sub(r'([\\`*_{}\[\]<>#+.!|~>-])', r'\\\1', text) for text in pages]
        destination.write_text(('\n\n---\n\n' if target == 'md' else '\n\f\n').join(pages), encoding='utf-8')
    elif target == 'html':
        body = '\n'.join(f"""{localize('<section aria-label="Сторінка ')}{i + 1}">{page.get_text('html')}</section>""" for i,page in enumerate(document))
        destination.write_text('<!doctype html><html lang="uk"><meta charset="utf-8"><title>'+html.escape(source.stem)+'</title><style>section{position:relative;page-break-after:always}</style><body>'+body+'</body></html>', encoding='utf-8')
    elif target in {'ppt','pptx'}:
        deck = destination if target == 'pptx' else work / 'presentation.pptx'
        slides(document, deck, work)
        if target == 'ppt':
            libreoffice(deck, target, destination, work)
    elif target in {'xls','xlsx'}:
        spreadsheet(document, target, destination)
    else:
        text_pages(document)  # Fail clearly for image-only pages rather than produce empty text.
        # Feed all pages through extracted XHTML. Calibre's PDF reflow heuristics
        # can remove repeated headers or fail on small page sizes.
        extracted = work / 'book-input.html'
        sections = []
        for page in document:
            markup = page.get_text('xhtml')
            sections.append('<section style="page-break-before:always">' + markup + '</section>')
        extracted.write_text('<!doctype html><html><head><meta charset="utf-8"><title>' + html.escape(source.stem) + '</title></head><body>' + ''.join(sections) + '</body></html>', encoding='utf-8')
        intermediate = work / ('book.docx' if target == 'doc' else 'book' if target == 'oeb' else 'book.'+target)
        options = ['--input-encoding', 'utf-8', '--output-profile', 'tablet']
        if target == 'epub':
            options += ['--epub-max-image-size', 'none']
        if target == 'mobi':
            options += ['--mobi-keep-original-images']
        run_tool([locate('calibre'), extracted, intermediate, *options], work)
        if target == 'doc':
            libreoffice(intermediate, 'doc', destination, work)
        else:
            shutil.move(intermediate, destination)


def convert_pdf(source, target, overwrite=False):
    source = Path(source).absolute()
    destinations = planned_outputs(source, target)
    conflicts = [path for path in destinations if path.exists()]
    if conflicts and not overwrite:
        raise FileExistsError(str(conflicts[0]))
    # All pages are generated first. A failure never publishes only the first pages.
    with tempfile.TemporaryDirectory(prefix='.convert-pdf-', dir=source.parent) as folder:
        work = Path(folder)
        staged = [work / f'output-{i}.{extension(target)}' for i in range(len(destinations))]
        with open_pdf(source) as document:
            produce(document, source, target, staged, work)
        for path in staged:
            if not path.exists() or (path.is_file() and not path.stat().st_size):
                raise ValueError(localize('Конвертер не створив повний результат.'))
        backups, published = [], []
        try:
            for i, (temporary, destination) in enumerate(zip(staged, destinations)):
                if destination.exists():
                    if not overwrite:
                        raise FileExistsError(str(destination))
                    # Do not replace folders that could contain unrelated user files.
                    if destination.is_dir():
                        raise FileExistsError(localize('Каталог уже існує: ') + str(destination))
                    backup = work / f'backup-{i}'
                    destination.rename(backup)
                    backups.append((backup, destination))
                temporary.rename(destination)
                published.append(destination)
        except Exception:
            for path in reversed(published):
                shutil.rmtree(path) if path.is_dir() else path.unlink()
            for backup, destination in reversed(backups):
                backup.rename(destination)
            raise
    return destinations
