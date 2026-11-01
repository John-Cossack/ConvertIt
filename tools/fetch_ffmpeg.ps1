$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$thirdParty = Join-Path $taskRoot 'third-party'
New-Item -ItemType Directory -Path $thirdParty -Force | Out-Null
$archive = Join-Path $thirdParty 'ffmpeg.zip'
Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip' -OutFile $archive
$expected = '60F467265B1E312373DBCD92200C2618A74850F98D3D078E94296BB3FA2047BA'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'Unexpected FFmpeg archive checksum.' }
Expand-Archive -LiteralPath $archive -DestinationPath $thirdParty -Force
