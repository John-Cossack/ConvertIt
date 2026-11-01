import ast
from pathlib import Path
import unittest
from unittest.mock import patch
import localization
import converter

class LocalizationTests(unittest.TestCase):
    def test_windows_display_language(self):
        for code,expected in [(0x0422,'uk'),(0x0409,'en'),(0x0407,'en'),(0x0419,'en')]:
            with self.subTest(code=code),patch.object(localization.ctypes.windll.kernel32,'GetUserDefaultUILanguage',return_value=code):
                self.assertEqual(localization.language(),expected)
    def test_english_default_and_ukrainian(self):
        for language,expected in [('en','The file is already in this format.'),('uk','Файл уже має цей формат.')]:
            with patch('localization.language',return_value=language):
                self.assertEqual(localization.localize('Файл уже має цей формат.'),expected)
    def test_native_error_dialog_in_both_languages(self):
        for language,expected in [('en','Unsupported format: xyz'),('uk','Непідтримуваний формат: xyz')]:
            with patch('localization.language',return_value=language):
                with self.assertRaises(converter.ConversionError) as caught:
                    converter.convert(Path('unknown.png'),'xyz')
                self.assertEqual(str(caught.exception),expected)
    def test_catalog_covers_localized_source_literals(self):
        root=Path(__file__).resolve().parent.parent
        for path in root.glob('*.py'):
            if path.name=='localization.py':continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='localize':
                    if node.args and isinstance(node.args[0],ast.Constant):
                        self.assertIn(node.args[0].value,localization.MESSAGES,path.name)
