import base64
import io
from pathlib import Path
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
import zlib

from PIL import Image
from pypdf import PdfReader
from capabilities import OUTPUTS, available, selection_groups
from converter import convert, ConversionError


class ExportTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent.parent / "test-results"
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="exports-", dir=root)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "Фото з пробілами & тест.jpg"
        pixels = random.Random(99).randbytes(48 * 32 * 3)
        Image.frombytes("RGB", (48, 32), pixels).save(self.source, quality=100, subsampling=0)
        self.original = self.source.read_bytes()
        with Image.open(self.source) as image:
            self.pixels = image.convert("RGB").tobytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_jpg_routes_include_screenshot_formats(self):
        targets = {row["id"] for row in available("JPEG")}
        self.assertEqual(targets, {"pdf", "avif", "bmp", "eps", "gif", "ico", "jpg", "odd", "odg", "png", "ps", "psd", "tiff", "webp", "svg", "psb", "icns", "ppm", "tga"})
        self.assertNotIn("heic", targets)
        self.assertNotIn("mp3", targets)
        self.assertEqual([name for name, _ in selection_groups([self.source])], ["Документ", "Зображення", "Вектор"])
        self.assertEqual(selection_groups([self.source, self.folder / "audio.wav"]), [])
        self.assertEqual(selection_groups([self.folder / "unsupported.xml"]), [])
        self.assertEqual(len(selection_groups([self.folder / "audio.wav"])[0][1]), 19)

    def test_heic_routes_match_screenshot(self):
        expected = {"pdf", "avif", "bmp", "eps", "gif", "ico", "jpg", "odd", "png", "ps", "psd", "tiff", "webp"}
        self.assertEqual({row["id"] for row in available("HEIF")}, expected)
        self.assertEqual([name for name, _ in selection_groups([self.folder / "photo.HEIC"])], ["Документ", "Зображення"])
        self.assertEqual([name for name, _ in selection_groups([self.source, self.folder / "photo.heif"])], ["Документ", "Зображення"])

    def test_heic_all_screenshot_outputs_8_and_10_bit(self):
        import pillow_heif
        from audio import binary, run
        for depth in (8, 10):
            source = self.folder / f"photo-{depth}.heic"
            if depth == 8:
                pillow_heif.from_pillow(Image.new("RGB", (33, 25), (24, 89, 172))).save(source, quality=-1, chroma=444, matrix_coefficients=0)
            else:
                pillow_heif.from_bytes("RGB;16", (33, 25), random.Random(10).randbytes(33 * 25 * 6)).save(source, quality=-1, chroma=444, matrix_coefficients=0, bit_depth=10)
            for row in available("HEIF"):
                with self.subTest(depth=depth, target=row["id"]):
                    result = convert(source, row["id"])
                    self.assertTrue(result.is_file())
                    self.assertGreater(result.stat().st_size, 0)
            if depth == 10:
                reference = run([binary("ffmpeg"), "-v", "error", "-i", str(source), "-f", "rawvideo", "-pix_fmt", "rgb48be", "pipe:1"])
                pdf = PdfReader(source.with_suffix(".pdf"))
                image = next(iter(pdf.pages[0]["/Resources"]["/XObject"].values())).get_object()
                self.assertEqual(image["/BitsPerComponent"], 16)
                self.assertEqual(image.get_data(), reference)
                for target in ("png", "tiff", "psd", "avif"):
                    decoded = run([binary("ffmpeg"), "-v", "error", "-i", str(source.with_suffix('.' + target)), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb48be", "pipe:1"])
                    self.assertEqual(decoded, reference, target)
                with zipfile.ZipFile(source.with_suffix(".odd")) as archive:
                    extracted = self.folder / "hdr-embedded.png"
                    extracted.write_bytes(archive.read("Pictures/image.png"))
                decoded = run([binary("ffmpeg"), "-v", "error", "-i", str(extracted), "-f", "rawvideo", "-pix_fmt", "rgb48be", "pipe:1"])
                self.assertEqual(decoded, reference)
            with self.assertRaises(ConversionError):
                convert(source, "svg")

    def test_pdf_contains_exact_source_pixels(self):
        path = convert(self.source, "pdf")
        pdf = PdfReader(path)
        self.assertEqual(len(pdf.pages), 1)
        self.assertEqual(tuple(pdf.pages[0].mediabox)[2:], (48, 32))
        self.assertEqual(pdf.pages[0].images[0].image.convert("RGB").tobytes(), self.pixels)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_pdf_preserves_transparency(self):
        source = self.folder / "alpha.png"
        Image.new("RGBA", (40, 30), (10, 20, 30, 123)).save(source)
        image = PdfReader(convert(source, "pdf")).pages[0].images[0].image.convert("RGBA")
        self.assertEqual(image.getpixel((0, 0)), (10, 20, 30, 123))

    def test_animation_to_pdf_pages(self):
        source = self.folder / "pages.gif"
        red = Image.new("RGB", (40, 30), "red")
        blue = Image.new("RGB", (40, 30), "blue")
        red.save(source, save_all=True, append_images=[blue], duration=[100, 200])
        pdf = PdfReader(convert(source, "pdf"))
        self.assertEqual(len(pdf.pages), 2)
        self.assertEqual(pdf.pages[1].images[0].image.convert("RGB").getpixel((0, 0)), (0, 0, 255))

    def test_psd_exact_pixels_layer_and_input(self):
        path = convert(self.source, "psd")
        with Image.open(path) as image:
            self.assertEqual(image.format, "PSD")
            self.assertEqual(image.n_frames, 1)
            self.assertEqual(image.convert("RGB").tobytes(), self.pixels)
        with Image.open(convert(path, "png")) as image:
            self.assertEqual(image.convert("RGB").tobytes(), self.pixels)

    def test_psd_exact_alpha(self):
        source = self.folder / "alpha.png"
        pixels = random.Random(8).randbytes(40 * 30 * 4)
        Image.frombytes("RGBA", (40, 30), pixels).save(source)
        with Image.open(convert(source, "psd")) as image:
            self.assertEqual(image.convert("RGBA").tobytes(), pixels)

    def test_postscript_image_data_is_lossless(self):
        for fmt in ("eps", "ps"):
            with self.subTest(fmt=fmt):
                path = convert(self.source, fmt)
                data = path.read_bytes()
                self.assertTrue(data.startswith(b"%!PS-Adobe-3.0"))
                self.assertIn(b"%%BoundingBox: 0 0 48 32", data)
                encoded = data.split(b">> image\n", 1)[1].split(b"~>", 1)[0]
                self.assertEqual(zlib.decompress(base64.a85decode(encoded)), self.pixels)
                if fmt == "ps":
                    self.assertIn(b"/PageSize [48 32]", data)

    def test_opendocument_package_is_self_contained(self):
        for fmt in ("odd", "odg"):
            with self.subTest(fmt=fmt), zipfile.ZipFile(convert(self.source, fmt)) as archive:
                first = archive.infolist()[0]
                self.assertEqual(first.filename, "mimetype")
                self.assertEqual(first.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(archive.read("mimetype"), b"application/vnd.oasis.opendocument.graphics")
                for xml in ("content.xml", "styles.xml", "META-INF/manifest.xml"):
                    ET.fromstring(archive.read(xml))
                with Image.open(io.BytesIO(archive.read("Pictures/image.png"))) as image:
                    self.assertEqual(image.convert("RGB").tobytes(), self.pixels)

    def test_menu_has_only_short_unique_format_names(self):
        from capabilities import INPUTS
        for row in OUTPUTS.values():
            self.assertEqual(row['label'], row['extension'].upper())
        for rule in INPUTS.values():
            choices = available(rule['format'], rule['kind'])
            extensions = [row['extension'] for row in choices]
            self.assertEqual(len(extensions), len(set(extensions)))
        self.assertEqual(sum(row['extension']=='svg' for row in available('JPEG')), 1)

    def test_svg_image_is_exact_and_uses_svg_extension(self):
        path = convert(self.source, "svg")
        self.assertEqual(path.suffix, ".svg")
        self.assertEqual(path.stem, self.source.stem)
        xml = ET.parse(path).getroot()
        image = xml.find("{http://www.w3.org/2000/svg}image")
        payload = image.attrib["{http://www.w3.org/1999/xlink}href"].split(",", 1)[1]
        with Image.open(io.BytesIO(base64.b64decode(payload))) as decoded:
            self.assertEqual(decoded.convert("RGB").tobytes(), self.pixels)
        with self.assertRaises(FileExistsError):
            convert(self.source, "svg")


if __name__ == "__main__":
    unittest.main()
