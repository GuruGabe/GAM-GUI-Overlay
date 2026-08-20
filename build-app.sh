#!/usr/bin/env bash
# =============================================================================
# build-app.sh - build GAMGUI as a one-folder app on macOS / Linux.
# The macOS/Linux counterpart to Build-EXE.bat. Result: dist/GAMGUI/
# (run the GAMGUI executable inside it; on macOS you also get dist/GAMGUI.app).
#
# Why the extract step:
#   Python 3.14 uses Tcl/Tk 9, which keeps its script library inside the Tcl
#   shared library as a virtual zip filesystem. PyInstaller does not bundle it,
#   so the app would crash at startup with "Tcl data directory _tcl_data not
#   found". extract_tcl.py pulls that library out to disk (and drops the .enc
#   encoding tables, which some endpoint security blocks) so it can be bundled
#   with --add-data. On Python 3.13 or earlier this step is harmless.
#
# Requirements:
#   - Python 3.10+ WITH tkinter
#       Debian/Ubuntu: sudo apt install python3 python3-tk
#       Fedora/RHEL:   sudo dnf install python3 python3-tkinter
#       Arch:          sudo pacman -S tk
#       macOS:         python.org Python includes tkinter; Homebrew Python needs
#                      'brew install python-tk'
#   - PyInstaller:  pip install pyinstaller
# =============================================================================
set -e

# Work from this script's own folder so relative paths are predictable.
cd "$(dirname "$0")"

# Pick an interpreter (prefer python3).
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
    echo "Python 3 was not found on PATH."
    exit 1
fi

# Verify PyInstaller is available.
if ! "$PY" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller is not installed. Run:  $PY -m pip install pyinstaller"
    exit 1
fi

# Step 1: extract the Tcl/Tk libraries so they can be bundled.
echo "Extracting Tcl/Tk libraries..."
"$PY" extract_tcl.py

# Step 2: build one-folder, bundling the extracted Tcl/Tk data.
#   (macOS/Linux use a ':' separator in --add-data; Windows uses ';'.)
"$PY" -m PyInstaller --onedir --windowed --name GAMGUI \
    --add-data "build_res/_tcl_data:_tcl_data" \
    --add-data "build_res/_tk_data:_tk_data" \
    GAMGUI.py

echo
echo "Build complete: dist/GAMGUI/"
echo "Run the GAMGUI executable inside that folder (keep the folder together)."
echo "On macOS you can also open dist/GAMGUI.app (right-click -> Open the first"
echo "time, since the app is not code-signed)."
