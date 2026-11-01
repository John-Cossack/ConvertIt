param([switch]$KeepRelease)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
function Remove-ProjectPath([string]$RelativePath) {
    $target = [IO.Path]::GetFullPath((Join-Path $root $RelativePath))
    if (!$target.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe cleanup target: $target" }
    if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Refusing a link: $target" }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
foreach ($path in @('build','test-results','.venv','__pycache__','tools\__pycache__','tests\__pycache__','.pytest_cache','.ruff_cache')) {
    Remove-ProjectPath $path
}
if ($KeepRelease) {
    if (Test-Path (Join-Path $root 'dist')) {
        Get-ChildItem -LiteralPath (Join-Path $root 'dist') -Force | Where-Object { $_.Name -ne 'ConvertIt.msix' -and !(!$_.PSIsContainer -and $_.Name -like 'ConvertIt*.zip') } | ForEach-Object { Remove-ProjectPath ('dist\'+$_.Name) }
    }
} else { Remove-ProjectPath 'dist' }
Get-ChildItem -LiteralPath $root -File | Where-Object { $_.Extension -in @('.obj','.lib','.exp','.spec','.log') -or $_.Name -eq 'install-status.txt' } | ForEach-Object { Remove-ProjectPath $_.Name }
Write-Output 'Removed generated files. Local build dependencies and optional integration fixtures were retained.'
