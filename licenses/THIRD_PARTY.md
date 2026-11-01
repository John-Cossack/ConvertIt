# Third-party notices for ConvertIt

The original application source for this release is available at
https://github.com/John-Cossack/ConvertIt/tree/v0.8.0.2 under AGPL-3.0-only.
The component versions, upstream source projects and build references below
identify the separate, unmodified native engines and Python dependencies.
Component license texts are retained in the packaged runtime and `Licenses/`.


- Pillow 13.0.0: https://python-pillow.github.io/ ; license included by PyInstaller in distribution metadata.
- pillow-heif 1.8.1 / libheif / x265: https://github.com/bigcat88/pillow_heif ; bundled wheel metadata and native library licenses apply.
- ReportLab 5.1.0: https://www.reportlab.com/ ; BSD license, used for lossless image embedding in PDF.
- VTracer 0.6.15: https://github.com/visioncortex/vtracer ; MIT/Apache-2.0 licenses, legacy component retained in this local runtime; SVG export no longer invokes tracing.
- PyMuPDF 2.0 / MuPDF: https://github.com/pymupdf/PyMuPDF ; dual AGPL-3.0 / Artifex commercial licensing, bundled package metadata and license files apply.
- python-pptx 1.0.2, openpyxl 3.1.5, xlwt 1.3.0, ezdxf 1.4.5 and lxml: their package license metadata accompanies the Python build. python-docx 1.2.0 is used for verification.
- Portable Inkscape 1.4.4: https://inkscape.org/release/inkscape-1.4.4/windows/64-bit/7z/ ; GPL-2.0-or-later, portable distribution includes its component licenses and COPYING files. Official archive SHA-256: `c4dbd64a92628abe7d7316c43f9325396e4d48417866027ee3d993d4f5b54c6a` (locally recorded download hash).
- Portable LibreOffice 26.8.1.1: https://download.documentfoundation.org/libreoffice/stable/26.8.1/win/x86_64/LibreOffice_26.8.1_Win_x86-64.msi ; MPL-2.0 / LGPL-3.0-or-later; files extracted without installing the MSI. Original MSI Authenticode verified as The Document Foundation. Bundled distribution includes license and notice files.
- Existing system Calibre 8.15.0: https://calibre-ebook.com/ ; GPL-3.0; invoked as a separate local process, not copied into this package. Uses isolated temporary profiles.
- FFmpeg 9.0.2 essentials Windows x64 build by Gyan Doshi: https://www.gyan.dev/ffmpeg/builds/ . FFmpeg download page links to this Windows build provider: https://ffmpeg.org/download.html .

Downloaded archive: `ffmpeg-9.0.2-essentials_build.zip`, SHA-256 `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba` (compared with the provider's published checksum).

This FFmpeg build is GPL v3 or later. The original LICENSE and README accompany the application in `Licenses/`; the exact source identified by the provider is https://github.com/FFmpeg/FFmpeg/commit/946fcce07b and build information/source instructions are on the provider's page. These binaries are invoked as separate local processes. No conversion uploads files to external services.

ConvertIt source code is licensed under AGPL-3.0-only. Third-party components
retain their own licenses. Their notices and source references accompany the release.
# Pandoc 3.13

Portable official Windows binary from https://github.com/jgm/pandoc/releases/tag/3.13.
GPL-2.0-or-later; upstream source and build instructions: https://github.com/jgm/pandoc.
COPYING.rtf and COPYRIGHT.txt are bundled beside pandoc.exe. Used as a separate hidden process for MD/RST/TEX conversion.

# 7-Zip 26.05

Official Windows x64 package: https://www.7-zip.org/a/7z2605-x64.exe.
Only 7z.exe, 7z.dll, License.txt and readme.txt are bundled; no file manager,
installer, shell extension, or 7-Zip menu is installed. License: LGPL with BSD
parts and the unRAR restriction; upstream source: https://www.7-zip.org/download.html.
Existing WinRAR Rar.exe is invoked separately for optional RAR creation and is not redistributed.

## Additional portable helpers in 0.7

- ImageMagick 7.1.2-35 Q16-HDRI: https://imagemagick.org/ ; ImageMagick license and bundled delegate notices accompany the portable runtime.
- Ghostscript 10.08.0: https://ghostscript.com/ ; AGPL-3.0, source at https://github.com/ArtifexSoftware/ghostpdl . Invoked separately in SAFER mode for PostScript inputs.
- FontForge 20251009: https://fontforge.org/ ; GPL-3.0 with component notices included in its portable tree.
- LibreDWG 0.14: https://www.gnu.org/software/libredwg/ ; GPL-3.0-or-later, upstream source https://git.savannah.gnu.org/cgit/libredwg.git/ . Only conversion executables and their DLL import closure are copied.
- UniConvertor 2.0rc5: https://sk1project.net/uc2/ ; AGPL-3.0 and bundled dependencies. No installer or shell registration is run. SK/SK1 command syntax is validated as literal data before invoking its legacy parser.
- dwf-viewer 0.6.7: https://github.com/flyfish-dev/dwf-viewer ; AGPL-3.0, LICENSE and NOTICE are included with the package. The first-party Node adapter serializes all decoded 2D primitives and pages into SVG without running a browser. Node.js 22.22 executable is copied from the existing system installation; MIT and bundled third-party notices: https://github.com/nodejs/node/blob/v22.22.0/LICENSE .
- DjVuLibre, rzip and ncompress from official Cygwin packages: https://cygwin.com/packages/ ; GPL/public-domain component licenses are copied from share/doc. Cygwin DLLs are used privately beside helpers; no system installation is performed. Cygwin source packages: https://cygwin.com/packages/src_package_list.html .
- lzip 1.26 and lzop 1.04 from MSYS2: https://packages.msys2.org/ ; GPL-2.0-or-later and component notices included from usr/share/licenses. Upstream sources: https://www.nongnu.org/lzip/ and https://www.lzop.org/ .
- The Unarchiver command-line unar/lsar: https://theunarchiver.com/command-line ; LGPL, upstream source https://github.com/MacPaw/XADMaster . Portable binaries only; no external context menu is registered.
- sfarkxtc-windows 3.0b: https://github.com/moltenform/sfarkxtc-windows ; GPL-3.0; readme accompanies the helper. Uses upstream checksum validation and rejects embedded licenses that require manual agreement.
- H2Orestart 0.8.0: https://github.com/ebandal/H2Orestart ; GPL-3.0, license text included; extension is registered only in the bundled portable LibreOffice shared package cache. Uses existing Java; no new OS-level menu is installed.
- rawpy 0.28.0, fonttools 4.68.0, Brotli 1.2.1, imagecodecs 2026.10.10 and pycdlib 1.22.0: respective wheel license metadata is collected in the application. Pure-Python acefile 0.6.14 is vendored from https://github.com/droe/acefile under BSD-2-Clause; no optional C extension is used.

Retain dependency source references and component license files when redistributing
the package. Native components are unmodified upstream binaries, staged and pruned
by the build scripts; no source changes to those native engines are made here.
