@ECHO OFF
:: =============================================================================
:: Script:   Build-EXE.bat
:: Author:   Gabe - FSISD IT Department
:: Created:  07-23-2026
:: Version:  1.0
::
:: Purpose:
::   Builds GAMGUI.exe from GAMGUI.py using PyInstaller. The result is a
::   single self-contained EXE in the dist folder that can be copied into
::   the GAM folder (C:\GAM7).
::
:: Requirements:
::   Python 3.10+ on PATH and PyInstaller (pip install pyinstaller).
:: =============================================================================
SETLOCAL ENABLEEXTENSIONS

:: Work from this script's folder so relative paths are predictable.
CD /D "%~dp0"

:: Verify PyInstaller is available before trying to build.
py -m PyInstaller --version >NUL 2>&1
IF ERRORLEVEL 1 (
    ECHO PyInstaller is not installed. Run:  py -m pip install pyinstaller
    EXIT /B 1
)

:: --onefile  = single EXE, no folder of DLLs
:: --windowed = no console window behind the GUI
:: --name     = output file name
py -m PyInstaller --onefile --windowed --name GAMGUI GAMGUI.py
IF ERRORLEVEL 1 (
    ECHO Build FAILED. Review the PyInstaller output above.
    EXIT /B 1
)

ECHO.
ECHO Build complete: dist\GAMGUI.exe
ECHO Copy it into your GAM folder (e.g. C:\GAM7) and double-click to run.
ENDLOCAL
