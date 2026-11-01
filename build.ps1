param([switch]$ReuseRuntimes, [switch]$ReusePython)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONPATH = "$PSScriptRoot\vendor;$PSScriptRoot\build-deps"
python tools/prepare_assets.py
if ($LASTEXITCODE) { throw 'Asset generation failed' }
python tools/generate_routes.py
if ($LASTEXITCODE) { throw 'Route generation failed' }
$ffmpegRoot = Join-Path $PSScriptRoot 'third-party\ffmpeg-9.0.2-essentials_build'
if (!(Test-Path -LiteralPath (Join-Path $ffmpegRoot 'bin\ffmpeg.exe'))) { throw 'Run tools\fetch_ffmpeg.ps1 first.' }
$pythonDist = if ($ReuseRuntimes) { 'build\python-dist' } else { 'dist' }
if ($ReuseRuntimes -and (!(Test-Path 'dist\ConvertIt\_internal\inkscape\bin\inkscape.com') -or !(Test-Path 'dist\ConvertIt\_internal\libreoffice\program\soffice.com'))) { throw 'Build once without -ReuseRuntimes first.' }
if ($ReusePython) {
    if (!(Test-Path "$pythonDist\ConvertIt\ConvertIt.exe")) { throw 'No staged Python build to reuse.' }
} else {
    python -m PyInstaller --noconfirm --clean --onedir --windowed --distpath $pythonDist --name ConvertIt --icon package/ConvertIt.ico --paths vendor --collect-all pillow_heif --collect-all PIL --collect-all vtracer --collect-all reportlab --collect-all pymupdf --collect-all ezdxf --collect-all pptx --collect-all openpyxl --collect-all xlwt --collect-all rawpy --collect-all imagecodecs --collect-all fontTools --collect-all brotli --collect-all pycdlib --hidden-import acefile --hidden-import PIL._avif --add-data "routes.json;." --add-data "locales;locales" --add-binary "$ffmpegRoot\bin\ffmpeg.exe;ffmpeg" --add-binary "$ffmpegRoot\bin\ffprobe.exe;ffmpeg" converter.py
    if ($LASTEXITCODE) { throw 'Python build failed' }
}
if ($ReuseRuntimes) {
    Copy-Item -Path "$pythonDist\ConvertIt\*" -Destination dist\ConvertIt -Recurse -Force
}
foreach ($runtime in @(@('third-party\inkscape\inkscape','inkscape'), @('third-party\libreoffice-26.8.1','libreoffice'))) {
    if (!(Test-Path -LiteralPath $runtime[0])) { throw "Missing portable runtime: $($runtime[0])" }
    if (!$ReuseRuntimes) { Copy-Item -LiteralPath $runtime[0] -Destination (Join-Path 'dist\ConvertIt\_internal' $runtime[1]) -Recurse -Force }
}
New-Item -ItemType Directory -Path dist\ConvertIt\_internal\pandoc -Force | Out-Null
Copy-Item -Path third-party\pandoc\pandoc-3.13\pandoc.exe,third-party\pandoc\pandoc-3.13\COPYING.rtf,third-party\pandoc\pandoc-3.13\COPYRIGHT.txt -Destination dist\ConvertIt\_internal\pandoc -Force
New-Item -ItemType Directory -Path dist\ConvertIt\_internal\7zip -Force | Out-Null
Copy-Item -Path third-party\7zip\7z.exe,third-party\7zip\7z.dll,third-party\7zip\License.txt,third-party\7zip\readme.txt -Destination dist\ConvertIt\_internal\7zip -Force
python tools/package_expanded.py
if ($LASTEXITCODE) { throw 'Expanded runtime packaging failed' }
& cmd.exe /d /c build-shell.cmd
if ($LASTEXITCODE) { throw 'Shell extension build failed' }
New-Item -ItemType Directory -Path dist\ConvertIt\Assets -Force | Out-Null
Copy-Item -Path package\Assets\* -Destination dist\ConvertIt\Assets -Force
Copy-Item -LiteralPath package\AppxManifest.xml -Destination dist\ConvertIt\AppxManifest.xml -Force
New-Item -ItemType Directory -Path dist\ConvertIt\Licenses -Force | Out-Null
Copy-Item -LiteralPath "$ffmpegRoot\LICENSE" -Destination dist\ConvertIt\Licenses\FFmpeg-LICENSE.txt -Force
Copy-Item -LiteralPath "$ffmpegRoot\README.txt" -Destination dist\ConvertIt\Licenses\FFmpeg-README.txt -Force
Copy-Item -LiteralPath licenses\THIRD_PARTY.md -Destination dist\ConvertIt\Licenses\THIRD_PARTY.md -Force
python tools/prune_runtime.py dist/ConvertIt
if ($LASTEXITCODE) { throw 'Runtime pruning failed' }
& 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\makeappx.exe' pack /d dist\ConvertIt /p dist\ConvertIt.msix /o
if ($LASTEXITCODE) { throw 'MSIX build failed' }
Write-Host 'Built dist\ConvertIt and dist\ConvertIt.msix'
