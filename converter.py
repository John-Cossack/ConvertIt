"""ConvertIt — format-aware local conversion for Windows Explorer."""
from __future__ import annotations

from localization import localize
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from audio import AUDIO_FORMATS, AUDIO_EXTENSIONS, convert_audio
from avif import save_avif
from precision import high_precision, convert_precision
from capabilities import INPUTS, OUTPUTS, available, extension as output_extension, selection_groups
from exporters import EXTRA_FORMATS, save_extra

register_heif_opener()
warnings.simplefilter("error", Image.DecompressionBombWarning)
VERSION = "0.8"
FORMATS = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "avif": "AVIF",
           "bmp": "BMP", "gif": "GIF", "tiff": "TIFF", "ico": "ICO", "tga":"TGA", "ppm":"PPM"}
ALL_FORMATS = OUTPUTS
ANIMATED = {"png", "gif", "webp", "avif", "tiff", "pdf"}


class ConversionError(Exception):
    pass


def convert(source: Path, target: str, overwrite=False, allow_flatten=False) -> Path:
    """Write atomically beside source. Never overwrite the source or an existing file silently."""
    source = Path(source).absolute()
    from expanded import handles,convert_expanded
    if handles(source,target):
        result=convert_expanded(source,target,overwrite)
        if sys.platform=='win32':
            for output in result if isinstance(result,list) else [result]:
                ctypes.windll.shell32.SHChangeNotify(0x00002000,0x0005,str(output),None)
        return result
    from archive_convert import is_archive, convert_archive
    if is_archive(source):
        output = convert_archive(source, target, overwrite)
        if sys.platform == 'win32':
            ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(output), None)
        return output
    from document_convert import is_document, convert_document
    if is_document(source):
        output = convert_document(source, target, overwrite)
        if sys.platform == 'win32':
            ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(output), None)
        return output
    if source.suffix.lower() == '.pdf':
        from pdf_convert import convert_pdf
        outputs = convert_pdf(source, target, overwrite)
        if sys.platform == 'win32':
            for output in outputs:
                ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(output), None)
        return outputs
    if target in AUDIO_FORMATS:
        output = convert_audio(source, target, overwrite=overwrite)
        if sys.platform == "win32":
            ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(output), None)
        return output
    if target not in FORMATS and target not in EXTRA_FORMATS:
        raise ConversionError(localize("Непідтримуваний формат: ") + target)
    destination = source.with_suffix("." + output_extension(target))
    if os.path.normcase(str(source)) == os.path.normcase(str(destination)):
        raise ConversionError(localize("Файл уже має цей формат."))
    if destination.exists() and not overwrite:
        raise FileExistsError(str(destination))
    temporary = None
    frames = []
    try:
        with Image.open(source) as image:
            if target not in {row["id"] for row in available(image.format)}:
                raise ConversionError(localize("Цей напрямок перетворення поки не підтримується."))
            count = getattr(image, "n_frames", 1)
            precise = high_precision(image, source)
            if precise and image.format == "HEIF" and target in {"pdf", "psd", "odd", "avif", "eps", "ps"}:
                from precision import convert_heic_precision
                if count != 1 or image.mode == "RGBA":
                    raise ConversionError(localize("Цей HDR HEIC містить кілька кадрів або прозорість. Оберіть PNG/TIFF."))
                result = convert_heic_precision(source, target, overwrite, image.info.get("icc_profile"))
                if sys.platform == "win32":
                    ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(result), None)
                return result
            if precise and target != "jpg" and not (image.format == "HEIF" and target not in {"png", "tiff"}):
                native = image.mode in {"I", "F", "I;16", "I;16L", "I;16B"}
                if target not in {"png", "tiff"}:
                    raise ConversionError(localize("Це зображення понад 8 біт. Щоб зберегти точність у версії 0.2, оберіть PNG або TIFF."))
                if not native:
                    if image.format == "TIFF" and max(image.tag_v2.get(258, (8,))) > 16:
                        raise ConversionError(localize("Багатоканальні TIFF понад 16 біт поки не підтримуються без зниження точності."))
                    if image.format == "HEIF" and image.mode == "RGBA":
                        raise ConversionError(localize("HDR HEIC із прозорістю поки не підтримується без втрати точності."))
                    if count != 1:
                        raise ConversionError(localize("Багатокадрові HDR-зображення поки не підтримуються без втрати розрядності."))
                    result = convert_precision(source, target, overwrite)
                    if sys.platform == "win32":
                        ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(result), None)
                    return result
                if target == "png" and image.mode in {"I", "F"}:
                    raise ConversionError(localize("Для цього 32-бітного зображення оберіть TIFF, щоб зберегти розрядність."))
            if count > 1 and target not in ANIMATED and not allow_flatten:
                raise ConversionError(localize("Цей формат збереже лише перший кадр. Потрібне підтвердження."))
            durations = []
            original_info = image.info.copy()
            exif = Image.Exif()
            exif.load(image.getexif().tobytes())
            exif.pop(274, None)  # Orientation is applied to the pixels below.
            for index in range(count if target in ANIMATED else 1):
                image.seek(getattr(image, "_min_frame", 0) + index)
                transposed = ImageOps.exif_transpose(image)
                # Preserve native precision for grayscale PNG and TIFF, including float TIFF.
                preserve_native = (target == "tiff" and image.mode in {"I", "F", "I;16", "I;16L", "I;16B", "CMYK", "L", "LA", "1"}) or (
                    target == "png" and image.mode in {"I;16", "I;16L", "I;16B", "L", "LA", "1"})
                frame = transposed.copy() if preserve_native else transposed.convert("RGBA")
                transposed.close()
                durations.append(image.info.get("duration", 100))
                if target in {"jpg", "bmp", "ppm"}:
                    background = Image.new("RGB", frame.size, "white")
                    background.paste(frame, mask=frame.getchannel("A"))
                    frame.close()
                    frame = background
                if target == "ico":
                    frame.thumbnail((256, 256), Image.Resampling.LANCZOS)
                    edge = max(frame.size)
                    square = Image.new("RGBA", (edge, edge), (0, 0, 0, 0))
                    square.paste(frame, ((edge - frame.width) // 2, (edge - frame.height) // 2))
                    frame.close()
                    frame = square
                frames.append(frame)
            options = {}
            if target == "jpg":
                options.update(quality=100, subsampling=0, optimize=True)
            elif target == "webp":
                options.update(lossless=True, quality=100, method=6, exact=True)
            elif target == "avif":
                options.update(quality=100, subsampling="4:4:4", speed=4)
            elif target == "tiff":
                options.update(compression="tiff_adobe_deflate")
            elif target == "png":
                options.update(compress_level=9)
            if target in {"png", "jpg", "webp", "avif", "tiff"}:
                for key in ("icc_profile", "dpi"):
                    if key in original_info:
                        options[key] = original_info[key]
                if exif and target != "tiff":
                    options["exif"] = exif.tobytes()
            if len(frames) > 1:
                options.update(save_all=True, append_images=frames[1:])
                if target != "tiff":
                    options.update(duration=durations)
                    if "loop" in original_info:
                        options["loop"] = original_info["loop"]
                if target == "gif":
                    options["disposal"] = 2
            fd, temporary = tempfile.mkstemp(prefix=".convert-", suffix=".tmp", dir=source.parent)
            os.close(fd)
            if target in EXTRA_FORMATS:
                save_extra(frames, temporary, target)
            elif target == "avif" and not original_info.get("icc_profile") and not exif:
                save_avif(frames, temporary, durations, original_info.get("loop", 0))
            else:
                frames[0].save(temporary, format=FORMATS[target], **options)
        # Windows rename fails if destination appeared in the meantime. Replace only on explicit consent.
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.rename(temporary, destination)
        temporary = None
        if sys.platform == "win32":
            ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, str(destination), None)
        return destination
    except (UnidentifiedImageError, OSError) as error:
        if isinstance(error, FileExistsError):
            raise
        raise ConversionError(localize("Не вдалося прочитати або зберегти зображення: ") + str(error)) from error
    finally:
        for frame in frames:
            frame.close()
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def shell_convert(files, target):
    """Explorer worker: no Tk, console, picker, progress, or success windows."""
    errors = []
    def confirm(text):
        return ctypes.windll.user32.MessageBoxW(None, text, 'ConvertIt', 0x134) == 6
    for name in files:
        source = Path(name)
        try:
            flatten = False
            from document_convert import is_document
            from archive_convert import is_archive
            from expanded import handles
            if source.suffix.lower() != '.pdf' and not handles(source,target) and not is_document(source) and not is_archive(source) and target not in AUDIO_FORMATS:
                with Image.open(source) as image:
                    flatten = getattr(image, 'n_frames', 1) > 1 and target not in ANIMATED
            if flatten and not confirm(f"{source.name}\n{target.upper()}{localize(' збереже лише перший кадр. Продовжити?')}"):
                continue
            if handles(source,target):
                from expanded import planned_outputs
                destinations=planned_outputs(source,target)
            elif is_archive(source):
                from archive_convert import planned_outputs
                destinations = planned_outputs(source, target)
            elif source.suffix.lower() == '.pdf':
                from pdf_convert import planned_outputs
                destinations = planned_outputs(source, target)
            else:
                destinations = [source.with_suffix('.' + output_extension(target))]
            conflicts = [p for p in destinations if p.exists() and p != source]
            replace = False
            if conflicts:
                names = '\n'.join(p.name for p in conflicts[:10])
                if not confirm(f"{localize('Замінити наявні файли (')}{len(conflicts)})?\n{names}\n{source.parent}"):
                    continue
                replace = True
            convert(source, target, overwrite=replace, allow_flatten=flatten)
        except Exception as error:
            errors.append(source.name + ' — ' + str(error))
    if errors:
        ctypes.windll.user32.MessageBoxW(None, '\n\n'.join(errors), localize('Конвертувати · помилка'), 0x10)
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description="ConvertIt " + VERSION)
    parser.add_argument("files", nargs="*")
    parser.add_argument("--format", choices=ALL_FORMATS)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    files = args.files
    if args.request:
        request = args.request.resolve()
        if request.parent != Path(tempfile.gettempdir()).resolve() or not request.name.lower().startswith("cvt") or request.suffix.lower() != ".tmp":
            raise ConversionError(localize("Неприпустимий файл запиту."))
        files += request.read_text(encoding="utf-16").splitlines()
        request.unlink()
    if args.quiet:
        if not args.format or not files:
            parser.error("--quiet requires --format and files")
        results = []
        for file in files:
            try:
                output = convert(Path(file), args.format)
                outputs = output if isinstance(output, list) else [output]
                results.append({"source": file, "output": str(outputs[0]), "outputs": [str(p) for p in outputs], "ok": True})
            except Exception as error:
                results.append({"source": file, "error": str(error), "ok": False})
        if args.report:
            args.report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if all(result["ok"] for result in results) else 1
    if args.format and files:
        return shell_convert(files, args.format)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if "--quiet" not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, str(exc), localize("Конвертувати · помилка"), 0x10)
        raise SystemExit(1)
