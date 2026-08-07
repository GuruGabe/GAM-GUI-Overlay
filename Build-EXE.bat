@ECHO OFF
:: =============================================================================
:: Script:   Build-EXE.bat
:: Author:   Gabe (built with Claude)
:: Created:  07-23-2026
:: Modified: 08-06-2026
:: Version:  2.0
::
:: Purpose:
::   Builds GAMGUI as a ONE-FOLDER app (dist\GAMGUI\) using PyInstaller.
::   Copy the whole dist\GAMGUI folder to its destination (e.g. C:\GAM7\GAMGUI)
::   and launch GAMGUI.exe inside it.
::
:: IMPORTANT - why one-folder and why the extract step:
::   Python 3.14 uses Tcl/Tk 9, which stores its script library INSIDE the DLL
::   as a virtual zip filesystem (//zipfs:/...). PyInstaller 6.21 does not copy
::   that library into the build, so the app crashes at startup with
::   "Tcl data directory _tcl_data not found". extract_tcl.py pulls the Tcl and
::   Tk libraries out of the zipfs into build_res\, and this script bundles them
::   with --add-data. One-folder (not one-file) also avoids the fragile
::   extract-to-%TEMP% behavior that failed intermittently.
::
:: Requirements:
::   Python 3.10+ on PATH and PyInstaller (py -m pip install pyinstaller).
:: =============================================================================
SETLOCAL ENABLEEXTENSIONS
CD /D "%~dp0"

:: Verify PyInstaller is available.
py -m PyInstaller --version >NUL 2>&1
IF ERRORLEVEL 1 (
    ECHO PyInstaller is not installed. Run:  py -m pip install pyinstaller
    EXIT /B 1
)

:: Step 1: extract the Tcl/Tk libraries out of the Tcl 9 zipfs into build_res\.
ECHO Extracting Tcl/Tk libraries from zipfs...
py extract_tcl.py
IF ERRORLEVEL 1 (
    ECHO Failed to extract Tcl/Tk data. Build aborted.
    EXIT /B 1
)

:: Step 2: build one-folder, bundling the extracted Tcl/Tk data.
::   --onedir   = folder of files (no fragile %TEMP% extraction at runtime)
::   --windowed = no console window behind the GUI
::   --add-data = ship the Tcl/Tk libraries as _tcl_data / _tk_data
py -m PyInstaller --onedir --windowed --name GAMGUI ^
    --add-data "build_res\_tcl_data;_tcl_data" ^
    --add-data "build_res\_tk_data;_tk_data" ^
    GAMGUI.py
IF ERRORLEVEL 1 (
    ECHO Build FAILED. Review the PyInstaller output above.
    EXIT /B 1
)

ECHO.
ECHO Build complete: dist\GAMGUI\  (run GAMGUI.exe inside it)
ECHO Copy the whole dist\GAMGUI folder to C:\GAM7\GAMGUI and launch
ECHO C:\GAM7\GAMGUI\GAMGUI.exe (or use the "Launch GAMGUI" shortcut).
ENDLOCAL
