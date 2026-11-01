@echo off
setlocal
if not exist "dist" mkdir "dist"
call "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /MT /EHsc /utf-8 /DUNICODE /D_UNICODE shell\VerifyShell.cpp /link /OUT:dist\VerifyShell.exe shell32.lib ole32.lib uuid.lib user32.lib
exit /b %errorlevel%
