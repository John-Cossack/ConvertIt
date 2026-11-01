"""Dispatch for new media families, shared by the CLI and native shell worker."""
from localization import localize
from pathlib import Path
from capabilities import INPUTS,input_extension,available,extension

KINDS={'video','font','ebook','spreadsheet','presentation','vector','graphics','raw','cad','djvu','soundfont'}


def handles(source,target):
    rule=INPUTS.get(input_extension(source),{})
    from video import is_video_ogg
    return is_video_ogg(source) or rule.get('kind') in KINDS or (rule.get('kind')=='image' and target in {'psb','icns'})


def check(source,target):
    rule=INPUTS.get(input_extension(source),{})
    from video import is_video_ogg
    if is_video_ogg(source):rule={'format':'VIDEO','kind':'video'}
    if target not in {r['id'] for r in available(rule.get('format'),rule.get('kind'))}:
        raise ValueError(localize('Цей напрямок конвертації не підтримується.'))
    return rule.get('kind')


def planned_outputs(source,target):
    family=check(source,target)
    if family in {'spreadsheet','presentation'}:
        from office_formats import planned_outputs as plan
        return plan(source,target)
    if family in {'vector','graphics','raw','cad'}:
        from graphics_convert import planned_outputs as plan
        return plan(source,target)
    if family=='djvu':
        from djvu_convert import planned_outputs as plan
        return plan(source,target)
    if family=='soundfont':
        from soundfont_convert import planned_outputs as plan
        return plan(source,target)
    return [Path(source).with_suffix('.'+extension(target))]


def convert_expanded(source,target,overwrite=False):
    family=check(source,target)
    if family=='video':
        from video import convert_video
        return convert_video(source,target,overwrite)
    if family=='font':
        from font_convert import convert_font
        return convert_font(source,target,overwrite)
    if family=='ebook':
        from ebook_convert import convert_ebook
        return convert_ebook(source,target,overwrite)
    if family in {'spreadsheet','presentation'}:
        from office_formats import convert_office
        return convert_office(source,target,overwrite)
    if family=='djvu':
        from djvu_convert import convert_djvu
        return convert_djvu(source,target,overwrite)
    if family=='soundfont':
        from soundfont_convert import convert_soundfont
        return convert_soundfont(source,target,overwrite)
    from graphics_convert import convert_graphics
    return convert_graphics(source,target,overwrite)
