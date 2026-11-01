"""Local video remux first, then explicit high-quality codec profiles."""
from localization import localize
from pathlib import Path
import json
import tempfile
from audio import binary, run, AUDIO_FORMATS, convert_audio
from transactions import publish
from capabilities import extension

PROFILES = {
    'ogg-video': ('ogg', ['-c:v','libtheora','-q:v','10','-c:a','libvorbis','-q:a','10']),
    'mkv': ('matroska', ['-c:v','ffv1','-level','3','-c:a','copy','-c:s','copy']),
    'avi': ('avi', ['-c:v','ffv1','-c:a','copy']),
    'mp4': ('mp4', ['-c:v','libx264','-crf','0','-preset','medium','-c:a','alac']),
    'mov': ('mov', ['-c:v','libx264','-crf','0','-preset','medium','-c:a','copy']),
    'webm': ('webm', ['-c:v','libvpx-vp9','-lossless','1','-deadline','good','-cpu-used','2','-c:a','libopus','-b:a','510k']),
    'wmv': ('asf', ['-c:v','wmv2','-q:v','1','-c:a','wmav2','-b:a','320k']),
    'flv': ('flv', ['-c:v','libx264','-crf','0','-c:a','aac','-b:a','512k']),
    'mpeg': ('mpeg', ['-c:v','mpeg2video','-q:v','1','-c:a','mp2','-b:a','384k']),
    'mpg': ('mpeg', ['-c:v','mpeg2video','-q:v','1','-c:a','mp2','-b:a','384k']),
    'vob': ('vob', ['-c:v','mpeg2video','-q:v','1','-c:a','ac3','-b:a','640k']),
    'mod': ('mpeg', ['-c:v','mpeg2video','-q:v','1','-c:a','mp2','-b:a','384k']),
    'ts': ('mpegts', ['-c:v','libx264','-crf','0','-c:a','aac','-b:a','512k']),
    'mts': ('mpegts', ['-c:v','libx264','-crf','0','-c:a','aac','-b:a','512k']),
    'm2ts': ('mpegts', ['-c:v','libx264','-crf','0','-c:a','aac','-b:a','512k','-mpegts_m2ts_mode','1']),
    'm4v': ('ipod', ['-c:v','libx264','-crf','0','-c:a','aac','-b:a','512k']),
    '3gp': ('3gp', ['-c:v','libx264','-crf','0','-c:a','aac','-b:a','320k']),
    '3gpp': ('3gp', ['-c:v','libx264','-crf','0','-c:a','aac','-b:a','320k']),
    '3g2': ('3g2', ['-c:v','libx264','-crf','0','-c:a','aac','-b:a','320k']),
    'ogv': ('ogv', ['-c:v','libtheora','-q:v','10','-c:a','libvorbis','-q:a','10']),
    'swf': ('swf', ['-c:v','flv','-q:v','1','-c:a','libmp3lame','-b:a','320k','-ar','44100']),
    'rm': ('rm', ['-c:v','rv20','-q:v','1','-c:a','ac3','-b:a','640k']),
    'rmvb': ('rm', ['-c:v','rv20','-q:v','1','-c:a','ac3','-b:a','640k']),
    'mxf': ('mxf', ['-c:v','mpeg2video','-q:v','1','-pix_fmt','yuv422p','-c:a','pcm_s24le']),
    'dv': ('dv', ['-c:v','dvvideo','-pix_fmt','yuv420p','-c:a','pcm_s16le']),
}


def is_video_ogg(source):
    if Path(source).suffix.lower()!='.ogg':return False
    with Path(source).open('rb') as stream:data=stream.read(65536)
    return data.startswith(b'OggS') and (b'\x80theora' in data or b'BBCD' in data)


def probe(source):
    return json.loads(run([binary('ffprobe'),'-v','error','-protocol_whitelist','file,pipe',
                           '-show_streams','-show_format','-of','json',str(source)],timeout=60))


def convert_video(source,target,overwrite=False):
    source=Path(source).absolute()
    if target in AUDIO_FORMATS:
        return convert_audio(source,target,overwrite,profile='audio')
    if target not in PROFILES:
        raise ValueError(localize('Цей вихідний відеоформат не підтримується.'))
    destination=source.with_suffix('.'+extension(target))
    if destination==source:
        raise ValueError(localize('Файл уже має цей формат.'))
    if destination.exists() and not overwrite:
        raise FileExistsError(str(destination))
    original=probe(source)
    videos=[s for s in original.get('streams',[]) if s['codec_type']=='video' and not s.get('disposition',{}).get('attached_pic')]
    if not videos:
        raise ValueError(localize('У файлі немає відеодоріжки.'))
    mux,options=PROFILES[target]
    with tempfile.TemporaryDirectory(prefix='.convert-video-',dir=source.parent) as directory:
        staged=Path(directory)/('result.'+target)
        common=[binary('ffmpeg'),'-hide_banner','-loglevel','error','-nostdin','-y','-xerror',
                '-protocol_whitelist','file,pipe','-i',str(source),'-map','0','-map_metadata','0','-map_chapters','0']
        try:
            run(common+['-c','copy','-f',mux,str(staged)])
            remuxed=probe(staged)
            if sorted(s['codec_type'] for s in remuxed['streams'])!=sorted(s['codec_type'] for s in original['streams']):
                raise ValueError('Remux changed a stream type.')
        except ValueError:
            staged.unlink(missing_ok=True)
            extra=[s for s in original['streams'] if s['codec_type'] not in {'video','audio'}]
            if extra and target not in {'mkv','mov','mp4'}:
                raise ValueError(localize('Цей контейнер не збереже всі субтитри/вкладення. Оберіть MKV.'))
            if any(int(s.get('bits_per_raw_sample') or 0)>10 or s.get('color_transfer') in {'smpte2084','arib-std-b67'} for s in videos) and target not in {'mkv','avi'}:
                raise ValueError(localize('Для цього HDR/високоточного відео оберіть MKV, щоб не втратити точність.'))
            if target=='dv' and any((s.get('width'),s.get('height'),s.get('r_frame_rate')) not in {(720,576,'25/1'),(720,480,'30000/1001')} for s in videos):
                raise ValueError(localize('DV потребує вихідного відео 720×576/25 або 720×480/29.97. Масштабування не застосовується.'))
            options=list(options)
            if target=='webm' and all(int(s.get('channels',2))==1 for s in original['streams'] if s['codec_type']=='audio'):
                options=[('256k' if x=='510k' else x) for x in options]
            if target in {'mp4','mov','flv','m4v','ts','mts','m2ts','3gp','3gpp','3g2'}:
                if any(s.get('pix_fmt','').startswith(('rgb','bgr','gbr')) for s in videos):
                    options=[('libx264rgb' if x=='libx264' else x) for x in options]
            run(common+options+['-f',mux,str(staged)])
        result=probe(staged)
        before=[s['codec_type'] for s in original['streams']]
        after=[s['codec_type'] for s in result['streams']]
        if sorted(before)!=sorted(after):
            raise ValueError(localize('Контейнер втратив доріжку; результат не збережено. Оберіть MKV.'))
        if [s.get('channels') for s in original['streams'] if s['codec_type']=='audio']!=[s.get('channels') for s in result['streams'] if s['codec_type']=='audio']:
            raise ValueError(localize('Кодек змінив кількість звукових каналів; оберіть MKV.'))
        decoded=[s for s in result['streams'] if s['codec_type']=='video' and not s.get('disposition',{}).get('attached_pic')]
        if [(s.get('width'),s.get('height')) for s in decoded]!=[(s.get('width'),s.get('height')) for s in videos]:
            raise ValueError(localize('Кодек змінив роздільність; результат не збережено.'))
        publish([(staged,destination)],overwrite)
    return destination
