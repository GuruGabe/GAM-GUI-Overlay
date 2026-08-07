# GAMGUI

A point-and-click desktop front-end for [GAM7](https://github.com/GAM-team/GAM),
the command-line tool for Google Workspace administration. GAMGUI turns common
GAM tasks into fill-in forms across 14 categories (Users, Groups, Aliases,
Org Units, Chromebooks, Gmail, Calendars, Drive, Classroom, Licenses, Reports,
Security, Email Cleanup, Diagnostics) plus a Custom-command mode for anything
else.

It is aimed at admins who want GAM's power without memorizing its syntax, and at
teams who want to hand routine Google Workspace tasks to less technical staff.

> **GAMGUI is a front-end only.** It runs your own `gam` executable with your
> existing authorization and holds **no credentials of its own**. GAM must be
> installed and authorized on the machine, or nothing will work.

## Features

- 75+ ready-made tasks; every one shows the exact `gam` command before it runs.
- Commands run **without a shell**, so `&`, `|`, `>` and quotes inside subjects
  and queries are handled safely.
- Destructive tasks (delete, powerwash, domain-wide mail delete, etc.) require
  an explicit confirmation.
- A built-in **phishing incident-response workflow**: search every mailbox,
  confirm, delete by Message-ID, then pull Gmail/Drive audit evidence.
- A read-only **mailbox takeover audit** (filters, forwarding, send-as,
  delegates) for compromised-account response.
- Per-session logging of every command and its output.

## Requirements

- **GAM7 installed and authorized** for your Google Workspace domain
  (this is the essential prerequisite): https://github.com/GAM-team/GAM
- **Windows** for the prebuilt app. macOS/Linux run from source or a native
  build (see below).
- No Python needed to run the prebuilt app; Python 3.10+ to run/build from
  source.

## Install & run (Windows)

1. Download/build the one-folder app (a `GAMGUI` folder containing `GAMGUI.exe`
   and an `_internal` folder). **Keep the folder together** - `GAMGUI.exe` will
   not run if separated from `_internal`.
2. Launch `GAMGUI\GAMGUI.exe`.
3. If the window shows `gam: (not found)`, click **Locate gam.exe...** and point
   it at your `gam` executable. GAMGUI auto-detects `gam` when it is on the PATH
   or next to the app.

New, non-technical users: see **HOW-TO-GUIDE.txt** for a full plain-English
walkthrough. Full reference: **README.txt**.

## Build from source

GAMGUI is a single Python file (`GAMGUI.py`) using only the standard library
(tkinter). To build the Windows app:

```bat
py -m pip install pyinstaller
Build-EXE.bat
```

`Build-EXE.bat` first runs `extract_tcl.py` and then PyInstaller in one-folder
mode. The extract step is **required on Python 3.14+**: Tcl/Tk 9 stores its
script library inside the DLL as a zip filesystem, which PyInstaller does not
bundle on its own - without it the app crashes at startup with
`Tcl data directory _tcl_data not found`. `extract_tcl.py` copies that library
to disk so it can be bundled via `--add-data`.

The result is `dist\GAMGUI\` - copy the whole folder to its destination.

For **macOS/Linux**, build on that OS: `pyinstaller --onedir --windowed
--name GAMGUI GAMGUI.py`. If you hit a missing-Tcl-data error there, apply the
same `extract_tcl.py` + `--add-data` approach shown in `Build-EXE.bat`.

## Files

| File | Purpose |
|------|---------|
| `GAMGUI.py` | The entire application (single file, stdlib only) |
| `extract_tcl.py` | Build helper: extracts Tcl/Tk data from the DLL (Python 3.14+) |
| `Build-EXE.bat` | One-command Windows build |
| `HOW-TO-GUIDE.txt` | Plain-English guide for non-technical users |
| `README.txt` | Full reference and troubleshooting |
| `CHANGELOG.txt` | Version history |

## Disclaimer

GAMGUI executes real administrative commands against a live Google Workspace
through GAM. Review the command preview before running, and test in a
non-production domain first. Provided as-is under the Apache License 2.0, with
no warranty (see `LICENSE`). Not affiliated with or endorsed by the GAM project
or Google.
