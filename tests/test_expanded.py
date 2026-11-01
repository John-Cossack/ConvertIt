from pathlib import Path
import hashlib
import shutil
import tempfile
import unittest
import pymupdf
from converter import convert
from font_convert import read_font
from sk_convert import validate
from video import is_video_ogg
from audio import binary,run

ROOT=Path(__file__).resolve().parent.parent

class ExpandedTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'test-results').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'test-results',prefix='expanded-')
        self.work=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def fixture(self,name):
        original=ROOT/'tests/fixtures'/name
        if not original.is_file():self.skipTest('Optional integration fixture: '+name)
        result=self.work/name;shutil.copy2(original,result);return result
    def test_font_wrappers_preserve_tables(self):
        source=self.work/'Шрифт.ttf';shutil.copy2('C:/Windows/Fonts/arial.ttf',source)
        with read_font(source) as original:
            for target in ('woff','woff2','eot'):
                result=convert(source,target)
                with read_font(result) as checked:
                    self.assertEqual(original.getBestCmap(),checked.getBestCmap())
                    self.assertEqual(original['glyf'].compile(original),checked['glyf'].compile(checked))
    def test_fontforge_outline_conversion(self):
        source=self.work/'font.ttf';shutil.copy2('C:/Windows/Fonts/arial.ttf',source)
        result=convert(source,'otf')
        with read_font(source) as original,read_font(result) as checked:
            self.assertEqual(checked.sfntVersion,'OTTO')
            self.assertEqual(set(original.getBestCmap()),set(checked.getBestCmap()))
        reverse=self.work/'roundtrip.otf';result.rename(reverse)
        original_bytes=reverse.read_bytes()
        try:
            output=convert(reverse,'ttf')
        except ValueError as error:
            # Some FontForge outline conversions add/drop unencoded glyphs.
            # The quality guard must reject those without publishing a file.
            self.assertTrue('glyph' in str(error) or 'гліф' in str(error),str(error))
            self.assertFalse(reverse.with_suffix('.ttf').exists())
        else:
            with read_font(reverse) as before,read_font(output) as after:
                self.assertEqual(set(before.getBestCmap()),set(after.getBestCmap()))
                self.assertEqual(before['maxp'].numGlyphs,after['maxp'].numGlyphs)
        self.assertEqual(reverse.read_bytes(),original_bytes)
    def test_inkscape_native_exports(self):
        source=self.work/'drawing.svg'
        source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect x="10" y="10" width="80" height="50" fill="blue"/><text x="12" y="35">Vector</text></svg>',encoding='utf-8')
        for target in ('pdf','emf','wmf','eps','ps'):
            with self.subTest(target=target):
                result=convert(source,target)
                self.assertTrue(all(p.is_file() and p.stat().st_size for p in result))
    def test_sk_commands_are_data_only(self):
        source=self.work/'bad.sk'
        for payload in ("document(); __import__('os').system('x')", "txt(__import__('os').getcwd())", "bm(1, 'C:/private.png')", "__class__()"):
            source.write_text(payload,encoding='utf-8')
            with self.assertRaises(ValueError):validate(source)
        source.write_text("##Sketch 1 2\ndocument()\nlayer('Layer',1,1,0,0)\nr(1,0,0,1,0,0)\n",encoding='utf-8');validate(source)
    def test_sfark_exact_original(self):
        source=self.fixture('bank.sfark');result=convert(source,'sf2')
        self.assertEqual(hashlib.sha256(result[0].read_bytes()).digest(),hashlib.sha256((ROOT/'tests/fixtures/bank-original.sf2').read_bytes()).digest())
    def test_dwf_keeps_both_vector_pages(self):
        source=self.fixture('drawing.dwf');result=convert(source,'pdf')
        with pymupdf.open(result[0]) as document:
            self.assertEqual(len(document),2)
            for page in document:self.assertGreater(len(page.get_drawings()),100)
    def test_video_remux_and_lossless_frames(self):
        source=self.fixture('source.mkv')
        def frames(path):return run([binary('ffmpeg'),'-v','error','-i',str(path),'-map','0:v:0','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        original=frames(source)
        for target in ('avi','mp4','webm'):
            with self.subTest(target=target):self.assertEqual(frames(convert(source,target)),original)
        ogg=convert(source,'ogg-video');self.assertTrue(is_video_ogg(ogg))
    def test_legacy_book_does_not_publish_lost_unicode(self):
        source=self.fixture('book.epub')
        for target in ('pdb','pmlz','snb'):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):convert(source,target)
                self.assertFalse(source.with_suffix('.'+target).exists())
    def test_office_sheets_and_csv_names(self):
        import openpyxl
        source=self.work/'Таблиця.xlsx';book=openpyxl.Workbook()
        book.active['A1']='Український';book.active['B1']='=1+2'
        book.create_sheet('Другий')['A1']='Другий аркуш';book.save(source)
        result=convert(source,'csv')
        self.assertEqual(len(result),2)
        self.assertIn('=1+2',result[0].read_text(encoding='utf-8-sig'))
        self.assertEqual(result[1].name,'Таблиця_2.csv')
        self.assertIn('Другий аркуш',result[1].read_text(encoding='utf-8-sig'))

if __name__=='__main__':unittest.main()
