"""Strict data-only validation before the legacy Sketch command parser."""
from localization import localize
from pathlib import Path
import ast
import base64
import io
from PIL import Image
from external_tools import ROOT,run_tool

COMMANDS=set('gl pe ps pgl pgr pgc phs pit fp fe ft lp le lw lc lj ld la1 la2 Fs Fn dstyle style use_style document layout grid layer masterlayer guidelayer guide G G_ M M_ B Bi B_ PT pt PT_ PC PC_ r e b bs bc bn bC txt im eps page add_pages bm'.split())


def binary():
    for path in [ROOT/'uniconvertor/uniconvertor.exe',ROOT/'third-party/uniconvertor/PFiles/UniConvertor-2.0rc5/uniconvertor.exe']:
        if path.is_file():return path
    raise ValueError(localize('Не знайдено UniConvertor.'))


def validate(source):
    lines=Path(source).read_text(encoding='utf-8-sig').splitlines()
    image=[];in_image=False
    for line in lines:
        line=line.strip()
        if in_image:
            if line=='-':
                try:
                    data=base64.b64decode(''.join(image),validate=True)
                    with Image.open(io.BytesIO(data)) as decoded:decoded.verify()
                except Exception as e:raise ValueError(localize('Невірне вбудоване зображення SK/SK1.')) from e
                in_image=False;image=[]
            else:image.append(line)
            continue
        if not line or line.startswith('#'):continue
        try:
            node=ast.parse(line,mode='eval').body
            if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name) or node.func.id not in COMMANDS:
                raise ValueError()
            values=[ast.literal_eval(a) for a in node.args]
            for keyword in node.keywords:
                if keyword.arg is None:raise ValueError()
                ast.literal_eval(keyword.value)
            if node.func.id=='bm':
                if len(values)>1 and values[1] is not None:
                    raise ValueError(localize('Зовнішні зображення SK треба попередньо вбудувати у файл.'))
                in_image=True
        except (ValueError,SyntaxError,TypeError) as e:
            raise ValueError(localize('SK/SK1 містить неочікувану команду або зовнішнє посилання; виконання коду заборонене.')) from e
    if in_image:raise ValueError(localize('Незавершений блок зображення SK/SK1.'))


def convert(source,target,destination,work):
    if Path(source).suffix.lower() in {'.sk','.sk1'}:validate(source)
    run_tool([binary(),'--log=ERROR',source,destination],work)
    if not Path(destination).is_file() or not Path(destination).stat().st_size:
        raise ValueError(localize('UniConvertor не створив повний результат.'))
