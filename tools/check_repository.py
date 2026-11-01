"""Dependency-free checks for source, menu contracts and public documentation."""
import ast
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent

def require(condition, message):
    if not condition:
        raise ValueError(message)

def check():
    sources = [*ROOT.glob('*.py'), *ROOT.joinpath('tools').glob('*.py'), *ROOT.joinpath('tests').glob('*.py')]
    for path in sources:
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))

    registry = json.loads((ROOT/'routes.json').read_text(encoding='utf-8'))
    outputs = registry['outputs']
    ids = {row['id'] for row in outputs}
    groups = {row['id'] for row in registry['groups']}
    require(len(ids) == len(outputs) <= 256, 'Output IDs must be unique and fit the native menu mask.')
    require(not any(row['extension'].lower() in {'heic','heif'} for row in outputs), 'HEIC/HEIF must remain input-only.')
    require(sum(row['label'].upper() == 'SVG' for row in outputs) == 1, 'SVG must have one output entry.')
    for row in outputs:
        require(row['group'] in groups, f'Unknown group: {row["id"]}')
        require(bool(re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', row['id'])), f'Invalid output ID: {row["id"]}')
        require(bool(row['label']) and bool(row['extension']), 'Empty output label or extension.')
    extensions = []
    for row in registry['inputs']:
        require(bool(row['extensions']), 'An input rule has no extensions.')
        extensions.extend(row['extensions'])
        require(set(row.get('allow', [])) <= ids, f'Unknown output route in {row["format"]}.')
    require(len(extensions) == len(set(extensions)), 'Input extensions have conflicting rules.')

    catalog = json.loads((ROOT/'locales/messages.json').read_text(encoding='utf-8'))
    require(all(isinstance(k,str) and k and isinstance(v,str) and v for k,v in catalog.items()), 'Invalid localization entry.')
    for path in ROOT.glob('*.py'):
        if path.name == 'localization.py':
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id == 'localize':
                if node.args and isinstance(node.args[0],ast.Constant):
                    require(node.args[0].value in catalog, f'Missing translation in {path.name}.')

    manifest = ET.parse(ROOT/'package/AppxManifest.xml').getroot()
    namespace = {'app':'http://schemas.microsoft.com/appx/manifest/foundation/windows10'}
    identity = manifest.find('app:Identity',namespace)
    require(bool(re.fullmatch(r'\d+\.\d+\.\d+\.\d+', identity.get('Version',''))), 'Invalid MSIX version.')
    for name in ('LICENSE','README.md','CHANGELOG.md','FORMATS.md','licenses/THIRD_PARTY.md',
                 '.github/CONTRIBUTING.md','.github/CODE_OF_CONDUCT.md','.github/SECURITY.md'):
        require((ROOT/name).is_file(), f'Missing project document: {name}')
    readme = (ROOT/'README.md').read_text(encoding='utf-8')
    require('🇬🇧' in readme and '🇺🇦' in readme, 'README must contain both language sections.')
    for label,target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',readme):
        if target.startswith(('https://','http://','#','mailto:')):
            continue
        require((ROOT/target.split('#')[0]).exists(), f'Broken README link: {label} -> {target}')
    require(not (ROOT/'README.uk.md').exists(), 'Keep a single bilingual README.')
    print(f'Validated {len(sources)} Python sources, {len(outputs)} outputs, {len(extensions)} input extensions and public documentation.')

if __name__ == '__main__':
    check()
