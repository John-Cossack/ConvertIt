"""Windows display-language selection: Ukrainian only for a Ukrainian UI."""
import ctypes
import json
from pathlib import Path
import re
import sys

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
MESSAGES = json.loads((ROOT / 'locales/messages.json').read_text(encoding='utf-8'))
_pattern = re.compile('|'.join(re.escape(text) for text in sorted(MESSAGES, key=len, reverse=True)))

def language():
    if sys.platform == 'win32':
        try:
            if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff == 0x22:
                return 'uk'
        except OSError:
            pass
    return 'en'

def localize(message):
    text = str(message)
    if language() == 'uk':
        return text.replace('Конвертувати · помилка', 'ConvertIt — помилка')
    return _pattern.sub(lambda match: MESSAGES[match.group()], text)
