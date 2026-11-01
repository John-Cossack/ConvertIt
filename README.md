# ConvertIt

[🇬🇧 English](#english) · [🇺🇦 Українська](#ukrainian)

<a id="english"></a>
## 🇬🇧 English

Convert images, audio, video, documents, archives and more directly in the
Windows 11 Explorer menu: **right-click → Convert → format**.
Conversions run locally. No separate app window or Python console.
English is the default; Ukrainian is used when the Windows display language is Ukrainian.

### Install

Download and extract the Windows x64 release. Open **PowerShell 7 as administrator**
in the extracted folder and run:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

Keep `ConvertIt.msix` beside the script. The installer registers the Explorer
menu and upgrades previous versions. This local package is unsigned; the script
does not install certificates or enable Developer Mode.

### Uninstall

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

The app and menu registrations are removed. Your converted files remain.
A copy of the uninstaller is also saved in `%LOCALAPPDATA%/ConvertIt/`.

### Files and quality

Results are saved beside the original with the same name and a new extension.
Multiple pages become `name.png`, `name_2.png`, etc. Existing outputs require
confirmation. Errors and confirmations use standard Windows dialogs.

Lossless conversion is preferred where the output format supports it. JPEG,
MP3 and other lossy codecs have inherent limits. HEIC/HEIF are input only.
[Supported routes](FORMATS.md); support depends on the specific file variant.
Scanned documents require an existing text layer for text extraction; automatic OCR is not included.
Ebooks require an installed Calibre, HWPX requires Java, and RAR creation requires WinRAR.

The package includes LibreOffice, Inkscape, FFmpeg and Pandoc for local document,
vector and media conversions. Unused manuals, additional UI languages, developer
files and duplicate helper programs are excluded from the release.

<a id="ukrainian"></a>
## 🇺🇦 Українська

Перетворюйте зображення, аудіо, відео, документи, архіви та інші файли просто
в Провіднику Windows 11: **права кнопка → Конвертувати → формат**.
Усе працює локально, без окремого вікна програми чи консолі Python.
Для української мови інтерфейсу Windows використовується українська,
для всіх інших — англійська.

### Встановлення

Завантажте й розпакуйте реліз Windows x64. Відкрийте **PowerShell 7 від
адміністратора** в розпакованій папці та виконайте:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

Залиште `ConvertIt.msix` поруч зі скриптом. Інсталятор реєструє меню та оновлює
попередні версії. Цей локальний пакет не підписано; скрипт не встановлює
сертифікати й не вмикає Developer Mode.

### Видалення

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

Програма та реєстрація меню видаляються. Конвертовані файли залишаються.
Копія скрипта видалення також є в `%LOCALAPPDATA%/ConvertIt/`.

### Файли та якість

Результат зберігається поруч з оригіналом із тим самим ім’ям та новим
розширенням. Кілька сторінок — `назва.png`, `назва_2.png` тощо. Заміна наявних
файлів потребує підтвердження. Помилки й підтвердження — стандартні діалоги Windows.

Застосовуються профілі без втрат, якщо формат це дозволяє. JPEG, MP3 та інші
кодеки зі втратами мають власні обмеження. HEIC/HEIF — лише вхід.
[Доступні напрямки](FORMATS.md); підтримка залежить від різновиду файла.
Для витягування тексту зі сканів потрібен наявний текстовий шар; автоматичного OCR немає.
Для книг потрібен установлений Calibre, для HWPX — Java, для створення RAR — WinRAR.

Пакет містить LibreOffice, Inkscape, FFmpeg і Pandoc для локальної роботи з
документами, векторами та медіа. Зайві довідники, додаткові мови інтерфейсу,
файли розробника й дубльовані допоміжні програми до релізу не входять.

---

[Third-party notices / Ліцензійні відомості](licenses/THIRD_PARTY.md)

<details>
<summary>Developer build instructions / Збирання для розробників</summary>

The repository contains source code. Build dependencies and binary runtimes are
not committed. Use Windows 11 x64, PowerShell 7, Python 3.14 x64, Visual C++ Build
Tools 2019 and Windows SDK 10.0.19041.0. Install `requirements.txt` into `vendor/`
and `requirements-dev.txt` into `build-deps/`. Prepare native runtimes according
to `build.ps1`, `tools/package_expanded.py` and the third-party notices; full setup
is not yet automated. `tools/prune_runtime.py` removes unused release payloads.

```powershell
pwsh -File .\build.ps1
$env:PYTHONPATH = "vendor;build-deps;."
python -m unittest discover -s tests -v
pwsh -File .\tools\clean.ps1 -KeepRelease
```

</details>
