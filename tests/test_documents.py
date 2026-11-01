from pathlib import Path
import gzip
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from docx import Document
from docx.shared import Inches
from PIL import Image
import pymupdf

from converter import convert, shell_convert
from capabilities import available
from document_convert import planned_outputs


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent / 'test-results', prefix='document-test-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'Документ & тест.docx'
        image = self.root / 'photo.png'
        Image.new('RGB', (150, 100), 'red').save(image)
        doc = Document()
        doc.add_heading('Document quality test', 0)
        doc.add_paragraph('Український текст: ї є ґ. Content stays editable.')
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = 'Name'
        table.cell(1, 1).text = '42'
        doc.add_picture(str(image), width=Inches(1))
        doc.add_page_break()
        doc.add_paragraph('Second page marker')
        doc.save(self.source)
        self.original = self.source.read_bytes()

    def tearDown(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.temp.cleanup()

    def test_native_outputs_and_reimport(self):
        for target in 'doc docm dot dotx odt rtf'.split():
            with self.subTest(target=target):
                output = convert(self.source, target)
                self.assertEqual(output.stem, self.source.stem)
                if target in {'doc', 'dot'}:
                    self.assertTrue(output.read_bytes().startswith(bytes.fromhex('D0CF11E0A1B11AE1')))
                elif target == 'rtf':
                    self.assertTrue(output.read_bytes().startswith(b'{\\rtf'))
                else:
                    with zipfile.ZipFile(output) as archive:
                        self.assertIn('content.xml' if target == 'odt' else 'word/document.xml', archive.namelist())
                        if target in {'docm', 'dotx'}:
                            content = archive.read('[Content_Types].xml')
                            self.assertIn(b'macroEnabled' if target == 'docm' else b'template.main', content)
                # Actual decoding by Writer, rather than just checking file suffixes.
                pdf = convert(output, 'pdf', overwrite=True)
                with pymupdf.open(pdf) as document:
                    self.assertEqual(len(document), 2)
                    text = ''.join(p.get_text() for p in document)
                    self.assertIn('Second page marker', text)
                    self.assertIn('Український', text)
                    self.assertTrue(document[0].get_images())

    def test_text_outputs_resources_and_reimport(self):
        for target in 'html txt md rst tex'.split():
            with self.subTest(target=target):
                output = convert(self.source, target)
                text = output.read_text(encoding='utf-8-sig')
                self.assertIn('Second page marker', ' '.join(text.split()))
                self.assertIn('Український', text)
                if target == 'html':
                    self.assertIn('data:image/', text)
                if target in {'md', 'rst', 'tex'}:
                    assets = self.root / (self.source.stem+'_'+target+'_files')
                    self.assertTrue(any(p.is_file() for p in assets.rglob('*')))
                    self.assertNotIn('.convert-document-', text)
                converted = convert(output, 'docx', overwrite=True)
                document = Document(converted)
                self.assertIn('Second page marker', ' '.join(' '.join(p.text for p in document.paragraphs).split()))
                self.assertGreater(len(document.paragraphs), 0)
                if target != 'txt':
                    with zipfile.ZipFile(converted) as archive:
                        self.assertTrue(any(n.startswith('word/media/') for n in archive.namelist()), 'Images must survive a round trip')
                # The source in this test is the DOCX destination, restored for
                # further subtests after validating an explicit overwrite.
                self.source.write_bytes(self.original)

    def test_pdf_and_silent_shell_worker(self):
        with patch('converter.ctypes.windll.user32.MessageBoxW') as message:
            self.assertEqual(shell_convert([self.source], 'pdf'), 0)
            message.assert_not_called()
        with pymupdf.open(self.source.with_suffix('.pdf')) as document:
            self.assertEqual(len(document), 2)
            self.assertIn('Second page marker', document[1].get_text())

    def test_preflight_and_invalid_input(self):
        with self.assertRaises(ValueError):
            planned_outputs(self.source, 'docx')
        with self.assertRaises(ValueError):
            planned_outputs(self.source, 'mp3')
        destination = self.source.with_suffix('.pdf')
        destination.write_bytes(b'KEEP')
        with self.assertRaises(FileExistsError):
            convert(self.source, 'pdf')
        self.assertEqual(destination.read_bytes(), b'KEEP')
        bad = self.root / 'broken.docx'
        bad.write_bytes(b'This is not a Word archive')
        with self.assertRaises(ValueError):
            convert(bad, 'pdf')
        self.assertFalse(bad.with_suffix('.pdf').exists())

    def test_abw_zabw_and_unicode_plain_text(self):
        abw = b'''<?xml version="1.0" encoding="UTF-8"?><abiword xmlns="http://www.abisource.com/awml.dtd" version="1.0"><section><p>AbiWord sample marker</p></section></abiword>'''
        for ext in ['abw', 'zabw']:
            source = self.root / ('abi.'+ext)
            source.write_bytes(gzip.compress(abw) if ext == 'zabw' else abw)
            result = convert(source, 'docx', overwrite=True)
            self.assertIn('AbiWord sample marker', '\n'.join(p.text for p in Document(result).paragraphs))
        text = self.root / 'plain.txt'
        text.write_text('Український текст ї ґ є', encoding='utf-8')
        result = convert(text, 'docx')
        self.assertIn('Український', '\n'.join(p.text for p in Document(result).paragraphs))

    def test_registry(self):
        expected = set('doc docm docx dot dotx html md odt pdf rst rtf tex txt'.split())
        self.assertEqual({r['id'] for r in available('DOCX', 'document')}, expected)

    def test_attachment_collision_preserves_existing_document_and_folder(self):
        output = convert(self.source, 'md')
        original = output.read_bytes()
        assets = self.root / (self.source.stem+'_md_files')
        marker = assets / 'user-file.txt'
        marker.write_bytes(b'KEEP USER DATA')
        with self.assertRaises(FileExistsError):
            convert(self.source, 'md', overwrite=True)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(marker.read_bytes(), b'KEEP USER DATA')
        self.assertFalse(list(self.root.glob('.convert-document-*')))
