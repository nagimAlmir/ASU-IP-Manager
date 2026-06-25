@echo off
cls
title ASU Manager v7
echo.
echo  === ASU Manager v7.2 ===
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  Python not found!
    echo  Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo  Python OK
echo.

echo  Checking dependencies...
python -m pip install ping3 customtkinter -q
echo  OK
echo.

if not exist "%~dp0ASU_Manager_v7.2.py" (
    echo  ERROR: ASU_Manager_v7.2.py not found!
    echo  Put both files in same folder.
    pause
    exit /b 1
)

echo  Creating shortcut on Desktop...
set SCR=%~dp0ASU_Manager_v7.2.py
set LNK=%USERPROFILE%\Desktop\ASU_Manager.lnk
set WRK=%~dp0
powershell -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell;$s=$w.CreateShortcut('%LNK%');$s.TargetPath='pythonw.exe';$s.Arguments='\"%SCR%\"';$s.WorkingDirectory='%WRK%';$s.Save()"

if exist "%LNK%" (
    echo  Shortcut created!
) else (
    echo @echo off > "%WRK%run.bat"
    echo pythonw "%SCR%" >> "%WRK%run.bat"
    echo  Created run.bat
)

echo.
echo  Launch now? Y=yes N=no
set /p ANS=" > "
if /i "%ANS%"=="y" start pythonw "%SCR%"
if /i "%ANS%"=="Y" start pythonw "%SCR%"

pause
