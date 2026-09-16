# Releasing GAMGUI (per-OS installers)

Each release ships a real installer AND a portable archive for every OS:

| OS | Installer | Portable |
|----|-----------|----------|
| Windows | `GAMGUI-<tag>-Setup.exe` (Inno Setup; installs to Program Files, adds Start Menu/desktop shortcuts and an uninstaller, and registers an Add/Remove Programs entry + version under `HKLM\...\CurrentVersion\Uninstall` and `HKLM\SOFTWARE\GAMGUI`) | `GAMGUI-<tag>-Windows.zip` |
| macOS | `GAMGUI-<tag>.dmg` (drag `GAMGUI.app` to Applications; version in the app's Info.plist) | `GAMGUI-<tag>-macOS.zip` |
| Linux | `gamgui_<tag>_amd64.deb` and `gamgui-<tag>-1.x86_64.rpm` (register with dpkg/rpm) | `GAMGUI-<tag>-Linux.tar.gz` |

The installers register with the OS so it knows GAMGUI is installed and at what
version (Add/Remove Programs on Windows, `dpkg -l gamgui` / `rpm -q gamgui` on
Linux, the app bundle on macOS). The portable archives need no install - unzip
and run the `GAMGUI` app inside; the auto-updater also uses the Windows zip.
GAM7 itself must already be set up on the machine.

The installer definitions live in `installer/` (`gamgui.iss`,
`build-macos-dmg.sh`, `build-linux-packages.sh`) and are driven by the
`Build installers` workflow.

## Cutting a release

1. Bump `APP_VERSION` in `GAMGUI.py`, update `CHANGELOG.txt`, and push to
   `main`.
2. Create the GitHub release for the version tag (bare number, e.g. `2.9`).
   Write the notes WITHOUT a SHA line and do NOT attach any zip yourself - let
   CI build and attach all three, so the archive names stay consistent
   (`GAMGUI-<tag>-Windows.zip`, `-macOS.zip`, `-Linux.tar.gz`):
   ```
   gh release create 2.9 --title "GAMGUI 2.9" --notes-file notes.txt --latest
   ```
3. Build the per-OS archives with GitHub Actions:
   - Open the repo's **Actions** tab -> **Build installers** -> **Run
     workflow**.
   - Enter the same tag (`2.9`) and run it.
   - The workflow builds on Windows, macOS, and Linux runners and uploads each
     archive to the `2.9` release.
4. (Optional, recommended) Let the auto-updater verify downloads: add the
   Windows zip's checksum to the release notes so `updategamgui.ps1` can check
   it. After CI finishes:
   ```
   gh release download 2.9 -p "GAMGUI-2.9-Windows.zip"
   (Get-FileHash GAMGUI-2.9-Windows.zip -Algorithm SHA256).Hash
   ```
   Append a line like `SHA-256 (GAMGUI-2.9-Windows.zip):` followed by that hash
   to the notes (`gh release edit 2.9 --notes-file ...`). If no SHA is present,
   the updater simply skips verification and still installs.

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
