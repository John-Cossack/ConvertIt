param([string]$InstallDirectory = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ConvertIt'))
$ErrorActionPreference = 'Stop'
$msix = Join-Path $PSScriptRoot 'ConvertIt.msix'
if (!(Test-Path -LiteralPath $msix)) { $msix = Join-Path $PSScriptRoot 'dist\ConvertIt.msix' }
if (!(Test-Path -LiteralPath $msix)) { throw 'ConvertIt.msix was not found. Extract the release or build the project first.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($msix)
try {
    $manifestReader = [IO.StreamReader]::new($archive.GetEntry('AppxManifest.xml').Open())
    try { $expectedVersion = ([xml]$manifestReader.ReadToEnd()).Package.Identity.Version } finally { $manifestReader.Dispose() }
} finally { $archive.Dispose() }
$destination = [IO.Path]::GetFullPath($InstallDirectory)
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall.ps1') -Destination (Join-Path $destination 'uninstall.ps1') -Force

# Unsigned local test package. No certificates or developer-mode changes.
Add-AppxPackage -Path $msix -AllowUnsigned -ForceTargetApplicationShutdown -ErrorAction Stop
$package = Get-AppxPackage -Name 'Gruse.ConvertApp' -ErrorAction Stop
if (!$package) { throw 'Package registration could not be verified.' }
if ([string]$package.Version -ne [string]$expectedVersion) { throw "Expected package $expectedVersion, got $($package.Version)" }
$application = $package.InstallLocation

$clsid = '{5E925D56-17C4-4CB1-9C91-70B5C5B55E62}'
$server = "HKCU:\Software\Classes\CLSID\$clsid\InprocServer32"
New-Item -Path $server -Force | Out-Null
Set-Item -LiteralPath $server -Value (Join-Path $application 'ConvertShell.dll')
New-ItemProperty -LiteralPath $server -Name ThreadingModel -Value Apartment -PropertyType String -Force | Out-Null
$verb = 'HKCU:\Software\Classes\*\shell\ConvertIt'
$legacyVerb = 'HKCU:\Software\Classes\*\shell\ConvertApp'
if (Test-Path -LiteralPath $legacyVerb) { Remove-Item -LiteralPath $legacyVerb -Recurse -Force }
New-Item -Path $verb -Force | Out-Null
$menuLabel = if ([Globalization.CultureInfo]::CurrentUICulture.TwoLetterISOLanguageName -eq 'uk') { 'Конвертувати' } else { 'Convert' }
New-ItemProperty -LiteralPath $verb -Name MUIVerb -Value $menuLabel -PropertyType String -Force | Out-Null
New-ItemProperty -LiteralPath $verb -Name ExplorerCommandHandler -Value $clsid -PropertyType String -Force | Out-Null
New-ItemProperty -LiteralPath $verb -Name MultiSelectModel -Value Player -PropertyType String -Force | Out-Null
New-ItemProperty -LiteralPath $verb -Name Icon -Value ((Join-Path $application 'ConvertIt.exe') + ',0') -PropertyType String -Force | Out-Null

$programs = [Environment]::GetFolderPath('Programs')
$shortcutPath = Join-Path $programs 'Конвертувати.lnk'
if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath -Force }

Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class ConvertShellNotify { [DllImport("shell32.dll")] public static extern void SHChangeNotify(uint e, uint f, IntPtr a, IntPtr b); }'
[ConvertShellNotify]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
@{ version=[string]$expectedVersion; directory=$application; package=$package.PackageFullName; shortcut=$null; installedAt=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $destination 'install-receipt.json') -Encoding UTF8
Write-Output "Installed: $application"
Write-Output "Package: $($package.PackageFullName)"
