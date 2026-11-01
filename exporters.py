"""Full-resolution raster containers and lossless SVG export."""
from localization import localize
import base64
import io
from pathlib import Path
import struct
import zipfile
import zlib

from PIL import Image

EXTRA_FORMATS = {"pdf", "eps", "ps", "psd", "odd", "odg", "svg"}


def png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=9)
    return buffer.getvalue()


def white_rgb(image):
    rgba = image.convert("RGBA")
    result = Image.new("RGB", rgba.size, "white")
    result.paste(rgba, mask=rgba.getchannel("A"))
    rgba.close()
    return result


def save_pdf(frames, destination):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    canvas = Canvas(str(destination), pageCompression=1)
    canvas.setCreator("ConvertIt 0.3")
    for frame in frames:
        width, height = frame.size
        canvas.setPageSize((width, height))
        canvas.drawImage(ImageReader(io.BytesIO(png_bytes(frame))), 0, 0, width, height, mask="auto")
        canvas.showPage()
    canvas.save()


def save_postscript_data(pixels, size, destination, eps, depth=8):
    width, height = size
    encoded = base64.a85encode(zlib.compress(pixels, 9))
    header = "%!PS-Adobe-3.0" + (" EPSF-3.0" if eps else "")
    header += f"\n%%BoundingBox: 0 0 {width} {height}\n%%LanguageLevel: 3\n%%Pages: 1\n%%EndComments\n"
    if not eps:
        header += f"<< /PageSize [{width} {height}] >> setpagedevice\n"
    header += f"gsave\n{width} {height} scale\n/DeviceRGB setcolorspace\n"
    header += f"<< /ImageType 1 /Width {width} /Height {height} /BitsPerComponent {depth}\n"
    header += f"/Decode [0 1 0 1 0 1] /ImageMatrix [{width} 0 0 -{height} 0 {height}]\n"
    header += "/DataSource currentfile /ASCII85Decode filter /FlateDecode filter >> image\n"
    wrapped = b"\n".join(encoded[i:i + 80] for i in range(0, len(encoded), 80))
    Path(destination).write_bytes(header.encode("ascii") + wrapped + b"\n~>\ngrestore\nshowpage\n%%EOF\n")


def save_postscript(image, destination, eps):
    with white_rgb(image) as rgb:
        save_postscript_data(rgb.tobytes(), rgb.size, destination, eps)


def save_psd(image, destination):
    """PSD version 1, one editable raster layer and a lossless merged composite."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width > 30000 or height > 30000:
        raise ValueError(localize("PSD обмежений 30000 пікселями на сторону. Оберіть TIFF."))
    planes = [channel.tobytes() for channel in rgba.split()]
    rgba.close()
    save_psd_planes(planes, (width, height), destination, 8, image.info.get("icc_profile"))


def save_psd_planes(planes, size, destination, depth, profile=None):
    width, height = size
    if width > 30000 or height > 30000:
        raise ValueError(localize("PSD обмежений 30000 пікселями на сторону. Оберіть TIFF."))
    channels = len(planes)
    u32 = lambda value: struct.pack(">I", value)
    resources = b""
    if profile:
        resources = b"8BIM" + struct.pack(">H", 1039) + b"\0\0" + u32(len(profile)) + profile + b"\0" * (len(profile) % 2)
    name = b"\x05Image\0\0"  # Pascal string, padded to a multiple of four bytes.
    extra = u32(0) + u32(0) + name
    record = struct.pack(">iiiiH", 0, 0, height, width, channels)
    record += b"".join(struct.pack(">hI", channel_id, len(data) + 2) for channel_id, data in zip((0, 1, 2, -1), planes))
    record += b"8BIMnorm" + bytes((255, 0, 0, 0)) + u32(len(extra)) + extra
    layer_info = struct.pack(">h", -1 if channels == 4 else 1) + record + b"".join(b"\0\0" + plane for plane in planes)
    layer_info += b"\0" * (len(layer_info) % 2)
    layers = u32(len(layer_info)) + layer_info + u32(0)
    with open(destination, "wb") as file:
        file.write(b"8BPS" + struct.pack(">H6sHIIHH", 1, b"\0" * 6, channels, height, width, depth, 3))
        file.write(u32(0) + u32(len(resources)) + resources + u32(len(layers)) + layers)
        file.write(b"\0\0")
        for plane in planes:
            file.write(plane)


def save_svg(image, destination):
    # Keep the decoded source pixels; PDF uses its own native vector exporter.
    width, height = image.size
    data = base64.b64encode(png_bytes(image)).decode("ascii")
    Path(destination).write_text(f'''<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><image width="{width}" height="{height}" xlink:href="data:image/png;base64,{data}"/></svg>''', encoding="utf-8")


def save_opendocument(image, destination, *, encoded_png=None, size=None):
    mime = "application/vnd.oasis.opendocument.graphics"
    pixel_width, pixel_height = size if size is not None else image.size
    width, height = pixel_width / 96 * 2.54, pixel_height / 96 * 2.54
    namespaces = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                  'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
                  'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
                  'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
                  'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
                  'xmlns:xlink="http://www.w3.org/1999/xlink" office:version="1.3"')
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content {namespaces}><office:automatic-styles><style:style style:name="gr1" style:family="graphic"><style:graphic-properties draw:stroke="none" draw:fill="none"/></style:style></office:automatic-styles><office:body><office:drawing><draw:page draw:name="Page1" draw:master-page-name="Default"><draw:frame draw:style-name="gr1" draw:name="Image" svg:x="0cm" svg:y="0cm" svg:width="{width:.8f}cm" svg:height="{height:.8f}cm"><draw:image xlink:href="Pictures/image.png" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame></draw:page></office:drawing></office:body></office:document-content>'''
    styles = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles {namespaces}><office:styles/><office:automatic-styles><style:page-layout style:name="pm1"><style:page-layout-properties fo:page-width="{width:.8f}cm" fo:page-height="{height:.8f}cm" fo:margin="0cm"/></style:page-layout></office:automatic-styles><office:master-styles><style:master-page style:name="Default" style:page-layout-name="pm1"/></office:master-styles></office:document-styles>'''
    manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3"><manifest:file-entry manifest:full-path="/" manifest:media-type="{mime}" manifest:version="1.3"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/><manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/><manifest:file-entry manifest:full-path="Pictures/image.png" manifest:media-type="image/png"/></manifest:manifest>'''
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", mime, compress_type=zipfile.ZIP_STORED)
        archive.writestr("content.xml", content)
        archive.writestr("styles.xml", styles)
        archive.writestr("META-INF/manifest.xml", manifest)
        archive.writestr("Pictures/image.png", encoded_png if encoded_png is not None else png_bytes(image))


def save_extra(frames, destination, target):
    if target == "pdf":
        save_pdf(frames, destination)
    elif target in {"eps", "ps"}:
        save_postscript(frames[0], destination, target == "eps")
    elif target == "psd":
        save_psd(frames[0], destination)
    elif target in {"odd", "odg"}:
        save_opendocument(frames[0], destination)
    elif target == "svg":
        save_svg(frames[0], destination)
    else:
        raise ValueError(localize("Непідтримуваний контейнер."))
