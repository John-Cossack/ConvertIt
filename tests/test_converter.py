from pathlib import Path
import tempfile
import unittest
import random

from PIL import Image
from converter import convert, ConversionError, FORMATS


class ConversionTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parent.parent / "test-results"
        test_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="convert-tests-", dir=test_root)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "Фото з пробілами & тест.png"
        Image.new("RGBA", (320, 180), (255, 0, 0, 100)).save(self.source)
        self.original = self.source.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_all_output_formats(self):
        for target, encoding in FORMATS.items():
            with self.subTest(target=target):
                source = self.source
                if target == "png":
                    source = self.folder / "вхід.webp"
                    Image.new("RGBA", (320, 180), (255, 0, 0, 100)).save(source)
                output = convert(source, target)
                self.assertEqual(output.parent, source.parent)
                self.assertEqual(output.stem, source.stem)
                with Image.open(output) as result:
                    result.load()
                    self.assertEqual(result.format, encoding)
                    self.assertEqual(result.size, (320, 180) if target != "ico" else (256, 256))
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_collision_requires_consent(self):
        destination = self.source.with_suffix(".jpg")
        destination.write_bytes(b"existing content")
        with self.assertRaises(FileExistsError):
            convert(self.source, "jpg")
        self.assertEqual(destination.read_bytes(), b"existing content")
        convert(self.source, "jpg", overwrite=True)
        with Image.open(destination) as result:
            self.assertEqual(result.format, "JPEG")

    def test_never_overwrites_source(self):
        with self.assertRaises(ConversionError):
            convert(self.source, "png", overwrite=True)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_transparency_and_white_background(self):
        with Image.open(convert(self.source, "webp")) as result:
            self.assertEqual(result.convert("RGBA").getpixel((0, 0))[3], 100)
        with Image.open(convert(self.source, "bmp")) as result:
            self.assertEqual(result.getpixel((0, 0)), (255, 155, 155))

    def test_exif_rotation(self):
        source = self.folder / "rotated.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (80, 40), "red").save(source, exif=exif)
        with Image.open(convert(source, "png")) as result:
            self.assertEqual(result.size, (40, 80))

    def test_animation_preserved_and_flattening_requires_consent(self):
        source = self.folder / "animation.gif"
        frames = [Image.new("RGBA", (40, 40), color) for color in ("red", "green", "blue")]
        frames[0].save(source, save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=2)
        for target in ("png", "webp", "avif", "tiff"):
            with self.subTest(target=target), Image.open(convert(source, target)) as result:
                self.assertEqual(result.n_frames, 3)
                result.seek(2)
                self.assertGreater(result.convert("RGB").getpixel((0, 0))[2], 200)
        with self.assertRaises(ConversionError):
            convert(source, "jpg")
        self.assertFalse(source.with_suffix(".jpg").exists())
        convert(source, "jpg", allow_flatten=True)

    def test_detects_actual_content(self):
        source = self.folder / "really-png.jpg"
        source.write_bytes(self.original)
        with Image.open(convert(source, "webp")) as result:
            self.assertEqual(result.format, "WEBP")

    def test_corrupt_input_and_temporary_cleanup(self):
        source = self.folder / "broken.jpg"
        source.write_bytes(b"this is not an image")
        with self.assertRaises(ConversionError):
            convert(source, "png")
        self.assertFalse(source.with_suffix(".png").exists())
        self.assertEqual(list(self.folder.glob(".convert-*")), [])

    def test_heic_input(self):
        import pillow_heif
        source = self.folder / "photo.heic"
        pillow_heif.from_pillow(Image.new("RGB", (64, 32), "blue")).save(source)
        with Image.open(convert(source, "png")) as result:
            self.assertEqual(result.size, (64, 32))
        with Image.open(convert(source, "jpg")) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(result.size, (64, 32))
        self.assertNotIn("heic", FORMATS)
        with self.assertRaises(ConversionError):
            convert(self.source, "heic")

    def test_exact_pixels_in_lossless_outputs(self):
        source = self.folder / "noise.bmp"
        image = Image.frombytes("RGB", (64, 48), random.Random(42).randbytes(64 * 48 * 3))
        image.save(source)
        for target in ("png", "webp", "tiff", "avif"):
            with self.subTest(target=target), Image.open(convert(source, target)) as result:
                self.assertEqual(result.convert("RGB").tobytes(), image.tobytes())

    def test_avif_and_webp_exact_alpha(self):
        source = self.folder / "alpha.png"
        image = Image.frombytes("RGBA", (64, 48), random.Random(6).randbytes(64 * 48 * 4))
        image.save(source)
        for target in ("avif", "webp"):
            with self.subTest(target=target), Image.open(convert(source, target)) as result:
                self.assertEqual(result.convert("RGBA").tobytes(), image.tobytes())

    def test_16_bit_grayscale_preserved(self):
        source = self.folder / "16-bit.png"
        image = Image.frombytes("I;16", (64, 48), random.Random(7).randbytes(64 * 48 * 2))
        image.save(source)
        output = convert(source, "tiff")
        with Image.open(output) as result:
            self.assertEqual(list(result.getdata()), list(image.getdata()))

    def test_exif_metadata_preserved_without_double_rotation(self):
        source = self.folder / "metadata.jpg"
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = "Artist name"
        Image.new("RGB", (80, 40), "red").save(source, exif=exif)
        with Image.open(convert(source, "png")) as result:
            self.assertEqual(result.size, (40, 80))
            self.assertEqual(result.getexif().get(315), "Artist name")
            self.assertNotIn(274, result.getexif())

    def test_avif_preserves_color_profile(self):
        from PIL import ImageCms
        source = self.folder / "profile.png"
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("RGB", (48, 32), "red").save(source, icc_profile=profile)
        with Image.open(convert(source, "avif")) as result:
            self.assertEqual(result.info["icc_profile"], profile)

    def test_16_bit_rgb_preserved_and_not_silently_reduced(self):
        from audio import binary, run
        raw = self.folder / "rgb16.raw"
        pixels = random.Random(19).randbytes(48 * 32 * 6)
        raw.write_bytes(pixels)
        source = self.folder / "rgb16.png"
        run([binary("ffmpeg"), "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb48le", "-s", "48x32", "-i", str(raw),
             "-frames:v", "1", str(source)])
        output = convert(source, "tiff")
        decoded = run([binary("ffmpeg"), "-v", "error", "-i", str(output), "-f", "rawvideo", "-pix_fmt", "rgb48le", "pipe:1"])
        self.assertEqual(decoded, pixels)
        with self.assertRaisesRegex(ConversionError, "8"):
            convert(source, "webp")

    def test_hdr_heic_preserves_high_precision(self):
        import pillow_heif
        from audio import binary, run
        source = self.folder / "hdr.heic"
        pillow_heif.from_bytes("RGB;16", (32, 32), random.Random(23).randbytes(32 * 32 * 6)).save(
            source, quality=-1, chroma=444, matrix_coefficients=0, bit_depth=10)
        output = convert(source, "png")
        def decode(path):
            return run([binary("ffmpeg"), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb48le", "pipe:1"])
        self.assertEqual(decode(source), decode(output))
        with Image.open(convert(source, "jpg")) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(result.size, (32, 32))


if __name__ == "__main__":
    unittest.main()
