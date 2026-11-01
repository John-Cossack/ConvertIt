$ErrorActionPreference = 'Stop'
Get-AppxPackage -Name 'Gruse.ConvertApp' | Remove-AppxPackage -ErrorAction Stop
foreach ($key in @('HKCU:\Software\Classes\*\shell\ConvertIt', 'HKCU:\Software\Classes\*\shell\ConvertApp', 'HKCU:\Software\Classes\CLSID\{5E925D56-17C4-4CB1-9C91-70B5C5B55E62}')) {
    if (Test-Path -LiteralPath $key) { Remove-Item -LiteralPath $key -Recurse -Force }
}
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Конвертувати.lnk'
if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut -Force }
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class ConvertShellRemoveNotify { [DllImport("shell32.dll")] public static extern void SHChangeNotify(uint e, uint f, IntPtr a, IntPtr b); }'
[ConvertShellRemoveNotify]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
Write-Output 'ConvertIt has been uninstalled and its Explorer integration removed.'
