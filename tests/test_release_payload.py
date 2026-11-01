import unittest
from tools.prune_runtime import reason

class ReleasePayloadTests(unittest.TestCase):
    def test_conversion_assets_and_languages_are_retained(self):
        for name in ('_internal/imagemagick/magick.exe',
                     '_internal/imagemagick/sRGB.icc',
                     '_internal/libreoffice/program/swlo.dll',
                     '_internal/libreoffice/program/resource/common/vcl.mo',
                     '_internal/libreoffice/program/resource/uk/vcl.mo',
                     '_internal/libreoffice/share/extensions/dict-de/hyph_de_DE.dic',
                     '_internal/libreoffice/share/uno_packages/cache/H2Orestart.jar',
                     '_internal/inkscape/share/locale/uk/LC_MESSAGES/inkscape.mo',
                     '_internal/inkscape/lib/libinkscape_base.dll',
                     '_internal/ghostscript/Resource/Font/NimbusRoman-Regular',
                     '_internal/ffmpeg/ffmpeg.exe',
                     'Licenses/THIRD_PARTY.md'):
            with self.subTest(name=name):self.assertIsNone(reason(name))
    def test_duplicate_programs_and_nonconversion_assets_are_removed(self):
        for name in ('_internal/imagemagick/identify.exe',
                     '_internal/libreoffice/program/resource/de/vcl.mo',
                     '_internal/libreoffice/share/extensions/dict-de/de_DE.dic',
                     '_internal/inkscape/share/inkscape/tutorials/lesson.svg',
                     '_internal/inkscape/bin/gdb.exe',
                     '_internal/inkscape/lib/libinkscape_base.dll.a',
                     '_internal/ghostscript/vcredist_x64.exe',
                     '_internal/pymupdf/layout/onnx/model.onnx'):
            with self.subTest(name=name):self.assertIsNotNone(reason(name))
