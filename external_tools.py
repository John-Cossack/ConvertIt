"""Isolated local command-line converters; no network or interactive shell commands."""
from localization import localize
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def locate(name):
    candidates = {
        "inkscape": [ROOT / "inkscape/bin/inkscape.com", ROOT / "third-party/inkscape/inkscape/bin/inkscape.com"],
        "soffice": [ROOT / "libreoffice/program/soffice.com", ROOT / "third-party/libreoffice-26.8.1/program/soffice.com"],
        "calibre": [Path("C:/Program Files/Calibre2/ebook-convert.exe"), Path("C:/Program Files (x86)/Calibre2/ebook-convert.exe")],
        "pandoc": [ROOT / "pandoc/pandoc.exe", ROOT / "third-party/pandoc/pandoc-3.13/pandoc.exe"],
        "magick": [ROOT / 'imagemagick/magick.exe',ROOT / 'third-party/imagemagick/magick.exe'],
        "fontforge": [ROOT / 'fontforge/bin/fontforge.exe',ROOT / 'third-party/fontforge/{app}/bin/fontforge.exe'],
    }[name]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    command = shutil.which({"inkscape":"inkscape.com", "soffice":"soffice.com", "calibre":"ebook-convert.exe", "pandoc":"pandoc.exe",'magick':'magick.exe','fontforge':'fontforge.exe'}[name])
    if command:
        return command
    raise ValueError(localize("Не знайдено локальний конвертер ") + name)


def run_tool(arguments, work, timeout=300, cwd=None):
    work = Path(work).resolve()
    for name in ("temp", "inkscape-profile", "calibre-config", "calibre-cache"):
        (work / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH"):
        env.pop(name, None)
    env.update(TEMP=str(work / "temp"), TMP=str(work / "temp"),
               INKSCAPE_PROFILE_DIR=str(work / "inkscape-profile"),
               CALIBRE_CONFIG_DIRECTORY=str(work / "calibre-config"), CALIBRE_CACHE_DIRECTORY=str(work / "calibre-cache"))
    frozen = getattr(sys, "frozen", False) and sys.platform == "win32"
    if frozen:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        process = subprocess.Popen([str(arg) for arg in arguments], cwd=cwd or work, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        if frozen:
            ctypes.windll.kernel32.SetDllDirectoryW(str(ROOT))
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if sys.platform == 'win32':
            subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/taskkill.exe'),
                            '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        process.kill()
        process.communicate()
        raise ValueError(localize("Конвертер не завершив роботу вчасно."))
    if process.returncode:
        message = (stderr or stdout).decode("utf-8", errors="replace")[-3000:]
        raise ValueError(localize("Помилка локального конвертера: ") + message)
    return stdout


def libreoffice(source, target, destination, work, input_filter=None, family='writer'):
    work = Path(work)
    output = work / "office-output"
    output.mkdir(parents=True)
    # Never execute document macros or refresh linked content in a worker profile.
    user = work / "office-profile/user"
    user.mkdir(parents=True)
    (user / "registrymodifications.xcu").write_text('''<?xml version="1.0"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Writer/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>0</value></prop></item>
</oor:items>''', encoding='utf-8')
    profile = (work / "office-profile").resolve().as_uri()
    formats = {"doc":"doc:MS Word 97", "docx":"docx:Office Open XML Text", "rtf":"rtf:Rich Text Format",
               "ppt":"ppt:MS PowerPoint 97", "xls":"xls:MS Excel 97",
               "docm":"docm:Office Open XML Text VBA", "dot":"dot:MS Word 97 Vorlage",
               "dotx":"dotx:Office Open XML Text Template", "odt":"odt:writer8",
               "txt":"txt:Text (encoded):UTF8", "html":"html:HTML (StarWriter):EmbedImages",
               "pdf":'pdf:writer_pdf_Export:{"UseLosslessCompression":{"type":"boolean","value":"true"},"ReduceImageResolution":{"type":"boolean","value":"false"}}'}
    formats.update({'ods':'ods:calc8','xlsx':'xlsx:Calc Office Open XML',
                    'xlsm':'xlsm:Calc Office Open XML VBA','odp':'odp:impress8',
                    'pptx':'pptx:Impress Office Open XML','pptm':'pptm:Impress MS PowerPoint 2007 XML VBA',
                    'pps':'pps:MS PowerPoint 97 AutoPlay','ppsx':'ppsx:Impress Office Open XML AutoPlay',
                    'pot':'pot:MS PowerPoint 97 Vorlage','potx':'potx:Impress Office Open XML Template',
                    'odg':'odg:draw8'})
    if family == 'calc':
        formats['xls']='xls:MS Excel 97'
        formats['html']='html:HTML (StarCalc)'
    if target == 'pdf' and family != 'writer':
        formats['pdf']=formats['pdf'].replace('writer_pdf_Export',family+'_pdf_Export')
    run_tool([locate("soffice"), "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
              "-env:UserInstallation=" + profile, *(['--infilter='+input_filter] if input_filter else []),
              "--convert-to", formats[target], "--outdir", output, Path(source).resolve()], work)
    generated = output / (Path(source).stem + "." + target)
    if not generated.is_file():
        raise ValueError(localize("LibreOffice не створив потрібний файл."))
    generated.replace(destination)
