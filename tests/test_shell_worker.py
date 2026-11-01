from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import converter


class ShellWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent/'test-results')
        self.source = Path(self.temp.name)/'sample.png'
        Image.new('RGB',(24,24),'red').save(self.source)
        self.original = self.source.read_bytes()

    def tearDown(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.temp.cleanup()

    def test_success_has_no_windows(self):
        with patch.object(converter.ctypes.windll.user32,'MessageBoxW') as dialog:
            self.assertEqual(converter.shell_convert([self.source],'jpg'),0)
            dialog.assert_not_called()
        self.assertTrue(self.source.with_suffix('.jpg').exists())

    def test_collision_can_be_declined_without_replacing(self):
        destination = self.source.with_suffix('.jpg')
        destination.write_bytes(b'KEEP')
        with patch.object(converter.ctypes.windll.user32,'MessageBoxW',return_value=7) as dialog:
            self.assertEqual(converter.shell_convert([self.source],'jpg'),0)
            self.assertEqual(dialog.call_count,1)
        self.assertEqual(destination.read_bytes(),b'KEEP')

    def test_error_is_not_hidden(self):
        with patch.object(converter.ctypes.windll.user32,'MessageBoxW') as dialog:
            self.assertEqual(converter.shell_convert([self.source.with_name('missing.png')],'jpg'),1)
            self.assertEqual(dialog.call_count,1)

    def test_no_arguments_open_no_picker(self):
        with patch('sys.argv',['ConvertIt.exe']):
            self.assertEqual(converter.main(),0)
