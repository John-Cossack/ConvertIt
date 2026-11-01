@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
if not exist "dist\ConvertIt" mkdir "dist\ConvertIt"
cl /nologo /std:c++17 /O2 /MT /EHsc /utf-8 /DUNICODE /D_UNICODE /LD shell\ConvertShell.cpp /link /DEF:shell\ConvertShell.def /OUT:dist\ConvertIt\ConvertShell.dll shlwapi.lib shell32.lib ole32.lib uuid.lib user32.lib
exit /b %errorlevel%
