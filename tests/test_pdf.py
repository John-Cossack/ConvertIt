import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

import pymupdf
from PIL import Image
from capabilities import available, selection_groups
from converter import convert
from pdf_convert import planned_outputs


class PdfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent / 'test-results', prefix='pdf-test-')
        self.folder = Path(self.temp.name)
        self.source = self.folder / 'Книга & тест.pdf'
        doc = pymupdf.open()
        for i in range(2):
            page = doc.new_page(width=144, height=144)
            page.insert_text((10,20), f'Page {i+1}', fontsize=10)
            for x in [10,70,130]:
                page.draw_line((x,40),(x,100))
            for y in [40,70,100]:
                page.draw_line((10,y),(130,y))
            for x,y,t in [(15,55,'Name'),(75,55,'Value'),(15,85,'Test'),(75,85,'=1+1')]:
                page.insert_text((x,y),t,fontsize=8)
        doc.save(self.source)
        self.original = self.source.read_bytes()

    def tearDown(self):
        self.assertEqual(self.original, self.source.read_bytes())
        self.temp.cleanup()

    def test_exact_pdf_profile_and_groups(self):
        expected = 'dxf doc docx html md pdf rtf txt azw3 epub lrf mobi oeb pdb avif bmp eps gif ico jpg odd png ps psd tiff webp ppt pptx xls xlsx emf svg wmf'.split()
        self.assertEqual({r['id'] for r in available('PDF','pdf')}, set(expected + 'svgz psb icns ppm tga sk sk1 cdr cgm'.split()))
        self.assertEqual(len(selection_groups([self.source])), 7)
        with self.assertRaises(ValueError):
            planned_outputs(self.source,'svg-image')
        with self.assertRaises(ValueError):
            convert(self.source,'pdf')

    def test_all_pages_and_resolution(self):
        output = convert(self.source,'png')
        self.assertEqual([p.name for p in output], ['Книга & тест.png','Книга & тест_2.png'])
        with Image.open(output[0]) as first, Image.open(output[1]) as second:
            self.assertEqual(first.size,(1200,1200))
            self.assertNotEqual(first.tobytes(),second.tobytes())
            self.assertAlmostEqual(first.info['dpi'][0],600,delta=1)

    def test_later_collision_preflight(self):
        second = self.source.with_name(self.source.stem+'_2.png')
        second.write_bytes(b'KEEP')
        with self.assertRaises(FileExistsError):
            convert(self.source,'png')
        self.assertEqual(second.read_bytes(),b'KEEP')
        self.assertFalse(self.source.with_suffix('.png').exists())

    def test_new_page_formats_keep_all_pages(self):
        for target in 'svgz psb icns ppm tga sk sk1 cdr cgm'.split():
            with self.subTest(target=target):
                outputs = convert(self.source, target)
                self.assertEqual(len(outputs), 2)
                self.assertEqual(outputs[1].stem, self.source.stem+'_2')
                self.assertTrue(all(p.is_file() and p.stat().st_size for p in outputs))

    def test_export_failure_publishes_nothing(self):
        import pdf_convert
        real = pdf_convert.render
        def fail_second(page, destination):
            if page.number == 1:
                raise ValueError('test failure')
            real(page,destination)
        first = self.source.with_suffix('.png')
        first.write_bytes(b'KEEP')
        with patch('pdf_convert.render', side_effect=fail_second), self.assertRaises(ValueError):
            convert(self.source,'png',overwrite=True)
        self.assertEqual(first.read_bytes(),b'KEEP')
        self.assertFalse(self.source.with_name(self.source.stem+'_2.png').exists())
        self.assertFalse(list(self.folder.glob('.convert-pdf-*')))

    def test_native_svg_text_and_sheets(self):
        outputs = convert(self.source,'svg')
        self.assertEqual(len(outputs),2)
        self.assertIn('path',outputs[0].read_text())
        self.assertNotIn('<image',outputs[0].read_text())
        txt = convert(self.source,'txt')[0].read_text(encoding='utf-8')
        self.assertIn('Page 1',txt)
        self.assertIn('Page 2',txt)
        import openpyxl
        book = openpyxl.load_workbook(convert(self.source,'xlsx')[0])
        self.assertEqual(len(book.worksheets),2)
        self.assertEqual(book.worksheets[0]['B2'].value,'=1+1')
        self.assertEqual(book.worksheets[0]['B2'].data_type,'s')

    def test_scanned_text_is_not_silently_empty(self):
        scan = self.folder / 'scan.pdf'
        doc = pymupdf.open()
        page = doc.new_page(width=72,height=72)
        image = io.BytesIO()
        Image.new('RGB',(20,20),'red').save(image,format='PNG')
        page.insert_image(page.rect,stream=image.getvalue())
        doc.save(scan)
        with self.assertRaisesRegex(ValueError,'OCR'):
            convert(scan,'txt')
        self.assertFalse(scan.with_suffix('.txt').exists())
        self.assertTrue(convert(scan,'png')[0].exists())

    def test_presentation_preserves_pages_and_svg(self):
        output = convert(self.source,'pptx')[0]
        from pptx import Presentation
        self.assertEqual(len(Presentation(output).slides),2)
        with zipfile.ZipFile(output) as archive:
            for i in (1,2):
                ET.fromstring(archive.read(f'ppt/media/pdf-page-{i}.svg'))
                self.assertIn(b'svgBlip',archive.read(f'ppt/slides/slide{i}.xml'))

    def test_epub_retains_large_embedded_image(self):
        source = self.folder / 'large-image.pdf'
        document = pymupdf.open()
        page = document.new_page(width=144,height=144)
        page.insert_text((10,20),'Image quality test')
        data = io.BytesIO()
        Image.new('RGB',(3200,32),'red').save(data,format='PNG')
        page.insert_image(pymupdf.Rect(10,30,134,60),stream=data.getvalue())
        document.save(source)
        output = convert(source,'epub')[0]
        with zipfile.ZipFile(output) as archive:
            sizes = []
            for name in archive.namelist():
                if name.lower().endswith(('.png','.jpg','.jpeg')):
                    with Image.open(io.BytesIO(archive.read(name))) as image:
                        sizes.append(image.size)
            self.assertIn((3200,32),sizes)


if __name__ == '__main__':
    unittest.main()
