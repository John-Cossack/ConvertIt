"""Local FFmpeg audio conversion with explicit codec and precision choices."""
from __future__ import annotations

from localization import localize
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from capabilities import available

AUDIO_FORMATS = {
    "wav": "WAV", "flac": "FLAC", "m4a": "M4A · ALAC", "aiff": "AIFF",
    "mp3": "MP3", "aac": "AAC", "ogg": "OGG", "opus": "OPUS",
    "ac3": "AC3", "wma": "WMA", "au": "AU", "caf": "CAF", "weba": "WEBA",
    "m4b": "M4B · ALAC",
    "aif":"AIF", "aifc":"AIFC", "oga":"OGA", "amr":"AMR", "voc":"VOC",
}
AUDIO_EXTENSIONS = set(AUDIO_FORMATS) | {"aif", "aifc", "oga", "mp2", "amr", "ape", "wv", "dss", "voc"}
LOSSLESS_AUDIO = {"wav", "flac", "m4a", "m4b", "aiff", "au", "caf"}


def binary(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [base / "ffmpeg" / (name + ".exe")]
    if not getattr(sys, "frozen", False):
        candidates += list((base / "third-party").glob("ffmpeg-*/bin/" + name + ".exe"))
    for path in candidates:
        if path.is_file():
            return str(path)
    raise ValueError(localize("Не знайдено ") + name + localize(". Перевстановіть програму."))


def run(arguments, timeout=None):
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=timeout)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-2000:]
        raise ValueError(localize("Помилка аудіо: ") + detail)
    return result.stdout


def probe(source):
    info = json.loads(run([binary("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
                           "-select_streams", "a", "-show_streams", "-show_format", "-of", "json",
                           str(Path(source).absolute())], timeout=60))
    if not info.get("streams"):
        raise ValueError(localize("У файлі немає аудіодоріжки."))
    if len(info["streams"]) != 1:
        raise ValueError(localize("Файл має кілька аудіодоріжок. Щоб не втратити інші, оберіть файл з однією доріжкою."))
    return info["streams"][0]


def encoding(target, stream):
    """Do not force sample rate/channel reductions to satisfy a legacy codec."""
    if target=='aif':return encoding('aiff',stream)
    if target=='oga':return encoding('ogg',stream)
    if target=='aifc':return ['-c:a','pcm_f64be','-f','aiff']
    if target=='amr':return ['-af','aresample=16000:filter_size=128:phase_shift=10:exact_rational=1:cutoff=0.995:filter_type=kaiser:kaiser_beta=16','-ac','1','-c:a','libvo_amrwbenc','-b:a','23850','-f','amr']
    if target=='voc':return ['-c:a','pcm_s16le','-f','voc']
    rate = int(stream["sample_rate"])
    channels = int(stream["channels"])
    sample = stream.get("sample_fmt", "s16")
    bits = int(stream.get("bits_per_raw_sample", 0) or stream.get("bits_per_sample", 0) or
               (64 if sample.startswith("dbl") else 32 if sample.startswith(("s32", "flt")) else 16))
    floating = sample.startswith(("flt", "dbl"))
    # Decoded lossy audio is float; 24-bit integer destinations retain a very wide dynamic range.
    integer_bits = 24 if floating else bits
    suffix = "be" if target in {"aiff", "au"} else "le"
    pcm = ("pcm_f64" if sample.startswith("dbl") else "pcm_f32") + suffix if floating else (
        "pcm_s64" if bits > 32 else "pcm_s32" if bits > 24 else "pcm_s24" if bits > 16 else "pcm_s16") + suffix
    if target in {"wav", "aiff", "au", "caf"}:
        if target == "aiff" and floating:
            if stream.get("codec_name", "").startswith("pcm_"):
                raise ValueError(localize("Для float-аудіо без втрати точності оберіть WAV або CAF."))
            pcm = "pcm_s24be"
        return ["-c:a", pcm, "-f", {"wav": "wav", "aiff": "aiff", "au": "au", "caf": "caf"}[target]]
    if floating and stream.get("codec_name", "").startswith("pcm_") and target in {"flac", "m4a", "m4b"}:
        raise ValueError(localize("Це float PCM. Для збереження точної розрядності оберіть WAV або CAF."))
    if target == "flac":
        if integer_bits > 32:
            raise ValueError(localize("Для аудіо понад 32 біти оберіть WAV або CAF."))
        return ["-c:a", "flac", "-strict", "experimental", "-compression_level", "12", "-sample_fmt", "s16" if integer_bits <= 16 else "s32",
                "-bits_per_raw_sample", str(16 if integer_bits <= 16 else 24 if integer_bits <= 24 else 32), "-f", "flac"]
    if target in {"m4a", "m4b"}:
        if integer_bits > 24:
            raise ValueError(localize("ALAC підтримує тут до 24 біт. Для збереження 32 біт оберіть WAV або FLAC."))
        return ["-c:a", "alac", "-sample_fmt", "s16p" if integer_bits <= 16 else "s32p",
                "-bits_per_raw_sample", str(16 if integer_bits <= 16 else 24), "-movflags", "+faststart", "-f", "ipod"]
    limits = {"mp3": ({8000,11025,12000,16000,22050,24000,32000,44100,48000}, 2),
              "aac": ({7350,8000,11025,12000,16000,22050,24000,32000,44100,48000,64000,88200,96000}, 8),
              "ac3": ({32000,44100,48000}, 6), "wma": ({22050,32000,44100,48000}, 2)}
    if target in limits and (rate not in limits[target][0] or channels > limits[target][1]):
        raise ValueError(f"{target.upper()}{localize(' не збереже ')}{rate}{localize(' Гц / ')}{channels}{localize(' каналів без зміни. Оберіть WAV, FLAC або ALAC.')}")
    if target == "mp3":
        # LAME's maximum CBR for MPEG-1; low sample rates are limited by MPEG-2/2.5.
        return ["-c:a", "libmp3lame", "-b:a", "320k" if rate >= 32000 else "160k", "-compression_level", "0", "-f", "mp3"]
    if target == "aac":
        return ["-c:a", "aac", "-b:a", str(256000 * channels), "-f", "adts"]
    if target == "ogg":
        return ["-c:a", "libvorbis", "-q:a", "10", "-f", "ogg"]
    if target in {"opus", "weba"}:
        if channels > 8:
            raise ValueError(localize("Для понад 8 каналів оберіть WAV, FLAC або CAF."))
        resample = ["-af", "aresample=filter_size=128:phase_shift=10:exact_rational=1:cutoff=0.995:filter_type=kaiser:kaiser_beta=16", "-ar", "48000"] if rate != 48000 else []
        return [*resample, "-c:a", "libopus", "-b:a", "256k" if channels==1 else "510k", "-vbr", "on", "-compression_level", "10", "-f", "ogg" if target == "opus" else "webm"]
    if target == "ac3":
        return ["-c:a", "ac3", "-b:a", "640k", "-f", "ac3"]
    if target == "wma":
        return ["-c:a", "wmav2", "-b:a", "320k", "-f", "asf"]
    raise ValueError(localize("Непідтримуваний аудіоформат."))


def convert_audio(source, target, overwrite=False, profile=None):
    source = Path(source).absolute()
    output = source.with_suffix("." + target)
    if os.path.normcase(str(source)) == os.path.normcase(str(output)):
        raise ValueError(localize("Файл уже має цей формат."))
    if output.exists() and not overwrite:
        raise FileExistsError(str(output))
    stream = probe(source)
    source_format = profile or ("MP3" if stream.get("codec_name") == "mp3" else "audio")
    if target not in {row["id"] for row in available(source_format, "audio")}:
        raise ValueError(localize("Цей напрямок перетворення для ") + source_format + localize(" не підтримується."))
    options = encoding(target, stream)
    # Remux compatible compressed streams to avoid another lossy generation.
    codec = stream.get("codec_name")
    if (target, codec) in {("aac", "aac"), ("mp3", "mp3"), ("ogg", "vorbis"), ("oga", "vorbis"),
                           ("opus", "opus"), ("weba", "opus"), ("ac3", "ac3"), ("wma", "wmav2")}:
        options = ["-c:a", "copy", "-f", {"aac":"adts", "mp3":"mp3", "ogg":"ogg", "oga":"ogg", "opus":"ogg", "weba":"webm", "ac3":"ac3", "wma":"asf"}[target]]
    fd, name = tempfile.mkstemp(prefix=".convert-", suffix=".tmp", dir=source.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        run([binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-xerror",
             "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:a:0", "-map_metadata", "0",
             "-map_chapters", "0", "-vn", "-sn", "-dn", *options, str(temporary)])
        result = probe(temporary)
        if int(result["channels"]) != (1 if target=='amr' else int(stream["channels"])):
            raise ValueError(localize("Кодек змінив кількість каналів; файл не збережено."))
        expected_rate = 16000 if target=='amr' else 48000 if target in {"opus", "weba"} else int(stream["sample_rate"])
        if int(result["sample_rate"]) != expected_rate:
            raise ValueError(localize("Кодек змінив частоту дискретизації; файл не збережено."))
        if overwrite:
            os.replace(temporary, output)
        else:
            os.rename(temporary, output)
        return output
    finally:
        temporary.unlink(missing_ok=True)
