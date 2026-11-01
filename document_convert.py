"""Local Writer/Pandoc conversion with atomic, same-directory publication."""
from localization import localize
from pathlib import Path
import gzip
import os
import shutil
import tempfile
import zipfile

from capabilities import INPUTS, available, extension
from external_tools import libreoffice, locate, run_tool

WRITER_INPUTS = {
    'abw': 'AbiWord', 'doc': 'MS Word 97', 'docm': 'Office Open XML Text VBA',
    'docx': 'Office Open XML Text', 'dot': 'MS Word 97 Vorlage',
    'dotx': 'Office Open XML Text Template', 'html': 'HTML (StarWriter)',
    'htm': 'HTML (StarWriter)', 'hwp': None, 'hwpx':None,
    'lwp': 'LotusWordPro', 'odt': 'writer8', 'pages': 'Apple Pages',
    'rtf': 'Rich Text Format', 'txt': 'Text (encoded):UTF8',
    'wpd': 'WordPerfect', 'wps': 'MS_Works', 'sdw':'StarOffice_Writer',
}
PANDOC_INPUTS = {'md': 'markdown', 'markdown': 'markdown', 'rst': 'rst', 'tex': 'latex'}
TEXT_OUTPUTS = {'md': 'markdown', 'rst': 'rst', 'tex': 'latex'}


def is_document(source):
    return INPUTS.get(Path(source).suffix.lower().lstrip('.'), {}).get('kind') == 'document'


def planned_outputs(source, target):
    source = Path(source).absolute()
    rule = INPUTS.get(source.suffix.lower().lstrip('.'))
    if not rule or rule['kind'] != 'document' or target not in {r['id'] for r in available(rule['format'], 'document')}:
        raise ValueError(localize('Цей напрямок перетворення документа не підтримується.'))
    destination = source.with_suffix('.' + extension(target))
    if os.path.normcase(str(source)) == os.path.normcase(str(destination)):
        raise ValueError(localize('Файл уже має цей формат.'))
    return [destination]


def validate_source(source):
    if not source.is_file() or not source.stat().st_size:
        raise ValueError(localize('Документ порожній або недоступний.'))
    ext = source.suffix.lower().lstrip('.')
    if ext in {'docx', 'docm', 'dotx', 'odt', 'pages'}:
        try:
            with zipfile.ZipFile(source) as archive:
                names = set(archive.namelist())
                if ext in {'docx', 'docm', 'dotx'} and not {'[Content_Types].xml', 'word/document.xml'} <= names:
                    raise ValueError(localize('Невірний документ Word.'))
                if ext == 'odt' and (archive.read('mimetype').strip() != b'application/vnd.oasis.opendocument.text' or 'content.xml' not in names):
                    raise ValueError(localize('Невірний документ ODT.'))
                if ext == 'pages' and not any(n.endswith('.iwa') or n in {'index.xml', 'index.xml.gz'} for n in names):
                    raise ValueError(localize('Невірний документ Pages.'))
        except (zipfile.BadZipFile, KeyError) as error:
            raise ValueError(localize('Архів документа пошкоджено або захищено паролем.')) from error


def produce(source, target, destination, work):
    ext = source.suffix.lower().lstrip('.')
    native = source
    if ext == 'txt':
        data = source.read_bytes()
        try:
            text = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
        except UnicodeDecodeError as error:
            raise ValueError(localize('TXT має бути у кодуванні UTF-8 або UTF-16 з BOM. Збережіть його в Unicode.')) from error
        native = work / 'input.txt'
        native.write_text(text, encoding='utf-8')
    if ext == 'zabw':
        native = work / 'input.abw'
        with gzip.open(source, 'rb') as compressed:
            data = compressed.read(100_000_001)
        if len(data) > 100_000_000:
            raise ValueError(localize('Розпакований ABW перевищує 100 МБ.'))
        native.write_bytes(data)
        ext = 'abw'
    if ext in PANDOC_INPUTS:
        native = work / 'input.docx'
        run_tool([locate('pandoc'), source, '--from='+PANDOC_INPUTS[ext], '--to=docx', '--standalone',
                  '--resource-path='+str(source.parent), '--output', native], work)
        ext = 'docx'
    if target in TEXT_OUTPUTS:
        if ext != 'docx':
            intermediate = work / 'input.docx'
            libreoffice(native, 'docx', intermediate, work / 'to-docx', WRITER_INPUTS[ext])
            native = intermediate
        # Text formats cannot contain bitmap attachments. Keep relative resources
        # beside the output, and publish them only after the entire conversion.
        assets = destination.stem + '_' + target + '_files'
        run_tool([locate('pandoc'), native, '--from=docx', '--to='+TEXT_OUTPUTS[target],
                  '--standalone', '--wrap=none', '--extract-media='+assets, '--output', destination], work)
        return work / assets
    libreoffice(native, target, destination, work / 'writer', WRITER_INPUTS[ext])
    return None


def convert_document(source, target, overwrite=False):
    source = Path(source).absolute()
    destination = planned_outputs(source, target)[0]
    validate_source(source)
    if destination.exists() and (not overwrite or destination.is_dir()):
        raise FileExistsError(str(destination))
    with tempfile.TemporaryDirectory(prefix='.convert-document-', dir=source.parent) as folder:
        work = Path(folder)
        staged = work / destination.name
        assets = produce(source, target, staged, work)
        if not staged.is_file() or not staged.stat().st_size:
            raise ValueError(localize('Конвертер не створив документ.'))
        published_assets = None
        try:
            if assets and assets.is_dir():
                published_assets = destination.parent / assets.name
                if published_assets.exists():
                    raise FileExistsError(localize('Каталог вкладень уже існує: ') + str(published_assets))
                assets.rename(published_assets)
            if overwrite:
                os.replace(staged, destination)
            else:
                # An atomic create also protects against a file arriving after preflight.
                os.link(staged, destination)
        except Exception:
            if published_assets and published_assets.exists() and not assets.exists():
                shutil.rmtree(published_assets)
            raise
    return destination
