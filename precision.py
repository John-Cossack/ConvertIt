"""Preserve high bit depth instead of implicitly reducing RGB/HDR input to 8 bits."""
from localization import localize
import os
import json
from pathlib import Path
import tempfile
import struct
import zlib

from audio import binary, run


def high_precision(image, source):
    if image.format == "AVIF":
        info = json.loads(run([binary("ffprobe"), "-v", "error", "-select_streams", "v:0",
                               "-show_entries", "stream=pix_fmt", "-of", "json", str(source)]))
        pixel_format = info.get("streams", [{}])[0].get("pix_fmt", "")
        if any(token in pixel_format for token in ("10", "12", "16", "f32")):
            return True
    if int(image.info.get("bit_depth", 8)) > 8:
        return True
    if image.format == "PNG":
        with open(source, "rb") as file:
            header = file.read(26)
        return len(header) == 26 and header[24] > 8
    if image.format == "TIFF":
        bits = image.tag_v2.get(258, (8,))
        return max(bits if isinstance(bits, tuple) else (bits,)) > 8
    return image.mode in {"I", "F", "I;16", "I;16L", "I;16B"}


def convert_precision(source, target, overwrite):
    output = Path(source).with_suffix("." + target)
    fd, name = tempfile.mkstemp(prefix=".convert-", suffix=".tmp", dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        options = ["-c:v", "png", "-pix_fmt", "rgba64be", "-compression_level", "9", "-f", "image2"] if target == "png" else [
            "-c:v", "tiff", "-pix_fmt", "rgba64le", "-compression_algo", "deflate", "-f", "image2"]
        run([binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-protocol_whitelist", "file,pipe",
             "-i", str(source), "-map", "0:v:0", "-frames:v", "1", "-map_metadata", "0", *options, str(temporary)])
        if overwrite:
            os.replace(temporary, output)
        else:
            os.rename(temporary, output)
        return output
    finally:
        temporary.unlink(missing_ok=True)


def save_rgb16_pdf(raw, size, destination, profile=None):
    """PDF 1.7 image XObject with native 16-bit RGB samples and optional ICC."""
    width, height = size
    def stream(dictionary, payload):
        compressed = zlib.compress(payload, 9)
        return b"<< " + dictionary + f" /Filter /FlateDecode /Length {len(compressed)} >>\nstream\n".encode("ascii") + compressed + b"\nendstream"
    colorspace = b"[/ICCBased 6 0 R]" if profile else b"/DeviceRGB"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>".encode("ascii"),
        stream(b"", f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q".encode("ascii")),
        stream(f"/Type /XObject /Subtype /Image /Width {width} /Height {height} /BitsPerComponent 16 /ColorSpace ".encode("ascii") + colorspace, raw),
    ]
    if profile:
        objects.append(stream(b"/N 3 /Alternate /DeviceRGB", profile))
    with open(destination, "wb") as file:
        file.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        positions = [0]
        for index, obj in enumerate(objects, 1):
            positions.append(file.tell())
            file.write(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
        offset = file.tell()
        file.write(f"xref\n0 {len(positions)}\n0000000000 65535 f \n".encode("ascii"))
        for position in positions[1:]:
            file.write(f"{position:010} 00000 n \n".encode("ascii"))
        file.write(f"trailer\n<< /Size {len(positions)} /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n".encode("ascii"))


def convert_heic_precision(source, target, overwrite, profile=None):
    """Keep >8-bit HEIC samples in containers that support them."""
    from exporters import save_opendocument, save_psd_planes, save_postscript_data
    source = Path(source)
    output = source.with_suffix("." + target)
    with tempfile.TemporaryDirectory(prefix=".convert-heic-", dir=source.parent) as folder:
        folder = Path(folder)
        temporary = folder / ("output." + target)
        ffmpeg = binary("ffmpeg")
        if target == "avif":
            info = json.loads(run([binary("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt", "-of", "json", str(source)]))
            pixel = info["streams"][0]["pix_fmt"]
            supported = {"gbrp10le", "gbrp12le", "yuv420p10le", "yuv422p10le", "yuv444p10le", "yuv420p12le", "yuv422p12le", "yuv444p12le", "gray10le", "gray12le"}
            if pixel not in supported:
                raise ValueError(localize("AVIF не збереже цю розрядність без зниження. Оберіть PNG/TIFF."))
            run([ffmpeg, "-v", "error", "-nostdin", "-y", "-protocol_whitelist", "file,pipe", "-i", str(source),
                 "-map", "0:v:0", "-frames:v", "1", "-c:v", "libaom-av1", "-pix_fmt", pixel,
                 "-crf", "0", "-b:v", "0", "-cpu-used", "4", "-threads", "4", "-still-picture", "1", "-f", "avif", str(temporary)])
        else:
            png = folder / "source.png"
            run([ffmpeg, "-v", "error", "-nostdin", "-y", "-protocol_whitelist", "file,pipe", "-i", str(source),
                 "-map", "0:v:0", "-frames:v", "1", "-c:v", "png", "-pix_fmt", "rgb48be", str(png)])
            with png.open("rb") as file:
                file.seek(16)
                size = struct.unpack(">II", file.read(8))
            if target == "odd":
                save_opendocument(None, temporary, encoded_png=png.read_bytes(), size=size)
            else:
                raw = run([ffmpeg, "-v", "error", "-nostdin", "-i", str(png), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb48be", "pipe:1"])
                if len(raw) != size[0] * size[1] * 6:
                    raise ValueError(localize("Не вдалося зберегти повний кадр HEIC."))
                if target == "pdf":
                    save_rgb16_pdf(raw, size, temporary, profile)
                elif target == "psd":
                    planes = []
                    for channel in range(3):
                        plane = bytearray(size[0] * size[1] * 2)
                        plane[0::2] = raw[channel * 2::6]
                        plane[1::2] = raw[channel * 2 + 1::6]
                        planes.append(bytes(plane))
                    save_psd_planes(planes, size, temporary, 16, profile)
                else:
                    # Portable EPS/PS output uses 8-bit RGB without lossy compression.
                    save_postscript_data(raw[0::2], size, temporary, target == "eps")
        if overwrite:
            os.replace(temporary, output)
        else:
            os.rename(temporary, output)
    return output
