# Releasing GAMGUI (per-OS installers)

GAMGUI ships a per-OS download for each release, the same way GAM7 does:

- `GAMGUI-<tag>-Windows.zip`
- `GAMGUI-<tag>-macOS.zip` (contains `GAMGUI.app`)
- `GAMGUI-<tag>-Linux.tar.gz`

Each is a self-contained one-folder app - no Python or installer needed; the
user unzips it and runs the `GAMGUI` executable inside. GAM7 itself must already
be set up on the machine.

## Cutting a release

1. Bump `APP_VERSION` in `GAMGUI.py`, update `CHANGELOG.txt`, and push to
   `main`.
2. Create the GitHub release for the version tag (bare number, e.g. `2.9`):
   ```
   gh release create 2.9 --title "GAMGUI 2.9" --notes-file notes.txt --latest
   ```
   (You can also attach the Windows zip here if you built it locally with
   `Build-EXE.bat`.)
3. Build the per-OS archives with GitHub Actions:
   - Open the repo's **Actions** tab -> **Build installers** -> **Run
     workflow**.
   - Enter the same tag (`2.9`) and run it.
   - The workflow builds on Windows, macOS, and Linux runners and uploads each
     archive to the `2.9` release.

That's it - the release then has all three downloads.

## How the build works

- Windows uses `Build-EXE.bat`; macOS/Linux use `build-app.sh`. The CI workflow
  (`.github/workflows/build-installers.yml`) runs the same PyInstaller commands
  those scripts use.
- `extract_tcl.py` pulls the Tcl/Tk script library out of the Python 3.14 Tcl 9
  DLL so PyInstaller can bundle it. It briefly opens a Tk interpreter, so the
  Linux CI job runs it under `xvfb` (a virtual display).
- The auto-updater `updategamgui.ps1` is copied into the app folder so every
  download can update itself.

## First-run note

The CI workflow is set to **manual trigger** (workflow_dispatch). The Windows
path matches the long-tested local build; the macOS and Linux paths are built
from `build-app.sh` and may need a small tweak the first time they run on the
GitHub runners (PyInstaller output layout and tkinter packaging differ slightly
per OS). Watch the first run's logs and adjust the `Package` steps if the
archive is missing an expected file.
