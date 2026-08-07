# GAMGUI

**A friendly, point-and-click window for [GAM7](https://github.com/GAM-team/GAM) -
the free tool that lets you manage your whole Google Workspace faster than
clicking through the Admin console.**

GAMGUI turns common GAM tasks into simple fill-in-the-blank forms, shows you the
exact command it will run **before** it runs, and prints the results in the
window. You get GAM's power without memorizing any commands.

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20source%3A%20macOS%2FLinux-informational)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Dependencies](https://img.shields.io/badge/dependencies-none%20(standard%20library)-brightgreen)

![GAMGUI main window](screenshot.png)

---

## New here? Start with this

**What is Google Workspace administration?** If your school or organization uses
Gmail, Google Drive, Chromebooks, Classroom, or Google Groups, an administrator
manages all of it (accounts, passwords, sharing, devices) from the Google Admin
console in a web browser. That works, but doing the same thing for hundreds of
people - one click at a time - is slow and error-prone.

**What is GAM?** [GAM](https://github.com/GAM-team/GAM/wiki) (Google Apps
Manager) is a free, open-source tool that talks directly to Google and does
those admin jobs in seconds. Reset 500 passwords, move a graduating class's
Chromebooks, or delete a phishing email from every mailbox in the district -
things that take hours in the console take one command in GAM.

**So what's the catch?** GAM is a *command-line* tool. You type text commands
like `gam create user jsmith@school.org firstname John lastname Smith`. That
scares off a lot of people who would otherwise love what it can do.

**That's what GAMGUI fixes.** GAMGUI puts a normal windowed program on top of
GAM. You pick a task from a list, fill in a couple of boxes, and click **Run**.
GAMGUI writes the correct GAM command for you, shows it to you, runs it, and
displays the result. You learn GAM by *seeing* the commands it builds - or you
never have to look at them at all.

> [!IMPORTANT]
> **GAMGUI does not replace GAM - it drives it.** You still need GAM installed
> and connected to your Google Workspace on the computer (a one-time setup,
> linked below). GAMGUI stores no passwords of its own; it simply runs *your*
> GAM. If GAM isn't set up yet, GAMGUI will open but can't do anything.

---

## What can you actually do with it?

Here are real jobs GAMGUI makes easy. Each links to the matching GAM
documentation if you want to go deeper.

### Manage people (accounts)
- **Onboard a new employee or student:** create the account, set a password,
  put it in the right group/department.
- **Offboard someone who left:** suspend the account, reset the password, sign
  them out everywhere, and hand their email/files to a manager.
- **Everyday help-desk:** reset a password, un-suspend a locked account, look up
  everything about a user, move someone to a different department.
- **Do it in bulk:** the same actions across a whole department or a
  spreadsheet of hundreds of people at once.
- Learn more: [Users](https://github.com/GAM-team/GAM/wiki/Users) ·
  [Groups](https://github.com/GAM-team/GAM/wiki/Groups) ·
  [Organizational Units](https://github.com/GAM-team/GAM/wiki/Organizational-Units)

### Email (Gmail)
- **Set up forwarding** for someone who left, so their mail reaches a coworker.
- **Grant a delegate** so an assistant can read/answer a shared mailbox.
- **Turn on an out-of-office** reply for someone who forgot.
- **Fix a compromised account** after a phishing attack (see Security below).
- Learn more:
  [Forwarding](https://github.com/GAM-team/GAM/wiki/Users-Gmail-Forwarding) ·
  [Delegates](https://github.com/GAM-team/GAM/wiki/Users-Gmail-Delegates) ·
  [Send-As / Signature / Vacation](https://github.com/GAM-team/GAM/wiki/Users-Gmail-Send-As-Signature-Vacation)

### Stop a phishing attack across everyone at once
- **Search every mailbox** in the domain for a malicious email (read-only - it
  just finds it), then **delete that email from everyone** with one guided
  workflow.
- **Audit a hacked account** to find the traps an attacker leaves behind:
  hidden mail-forwarding, filters that auto-delete incoming mail, extra
  delegates, and "send-as" identities.
- Learn more:
  [Messages/Threads](https://github.com/GAM-team/GAM/wiki/Users-Gmail-Messages-Threads) ·
  [Filters](https://github.com/GAM-team/GAM/wiki/Users-Gmail-Filters) ·
  [Deprovision](https://github.com/GAM-team/GAM/wiki/Users-Deprovision)

### Chromebooks (great for schools)
- **Move devices** to the right group so the right policies apply.
- **Disable a lost/stolen Chromebook**, or re-enable a found one.
- **Powerwash or wipe** devices remotely (for example, an end-of-year reset of a
  cart or a whole grade level).
- **Find out** who last used a device, or export your whole fleet to a sheet.
- Learn more:
  [ChromeOS Devices](https://github.com/GAM-team/GAM/wiki/ChromeOS-Devices)

### Google Drive and file sharing
- **Transfer someone's files** to another person before you delete their
  account (so nothing is lost).
- **See what a user has shared** and fix over-shared files.
- **Manage Shared Drives** and who has access to them.
- Learn more:
  [Drive files](https://github.com/GAM-team/GAM/wiki/Users-Drive-Files-Display) ·
  [Drive permissions](https://github.com/GAM-team/GAM/wiki/Users-Drive-Permissions) ·
  [Transfer](https://github.com/GAM-team/GAM/wiki/Users-Drive-Transfer) ·
  [Shared Drives](https://github.com/GAM-team/GAM/wiki/Shared-Drives)

### Calendars, Classroom, Groups
- **Share a calendar** with a person or a group, or clean up events.
- **Manage Google Classroom** courses and rosters, or change a class's owner
  when a teacher leaves.
- **Build and sync Groups** (mailing lists / access lists) from a department.
- Learn more:
  [Calendars](https://github.com/GAM-team/GAM/wiki/Calendars-Access) ·
  [Classroom](https://github.com/GAM-team/GAM/wiki/Classroom-Courses) ·
  [Group membership](https://github.com/GAM-team/GAM/wiki/Groups-Membership)

### See what's going on (reports)
- **Who changed what** in the Admin console, recent **logins**, and per-user
  **usage** - useful for security reviews and audits.
- Learn more: [Reports](https://github.com/GAM-team/GAM/wiki/Reports)

Every category above is one click in GAMGUI. There's also a **Custom command**
box for anything not yet built into a form - so you're never limited to the
built-in tasks.

---

## Get it running (the whole path, from zero)

### Step 1 - Set up GAM (one time, required)
GAMGUI needs GAM installed and connected to your Google Workspace first.
Follow Google Apps Manager's own guide - it walks you through it:
**[How to install GAM7](https://github.com/GAM-team/GAM/wiki/How-to-Install-GAM7)**.
You'll need to be a Google Workspace **administrator** to authorize it.

> Not sure GAM is working yet? Open a terminal and run `gam version` and
> `gam info domain`. If those show your domain, you're ready for GAMGUI.

### Step 2 - Get GAMGUI (prebuilt - no building required)
Most people should just download the ready-to-run app:

1. Go to the **[Releases](https://github.com/GuruGabe/GAM-GUI-Overlay/releases)**
   page of this repository.
2. Download **`GAMGUI-vX.Y-Windows.zip`** from the latest release.
3. **Unzip it**, and keep the whole `GAMGUI` folder together (the `GAMGUI.exe`
   needs the `_internal` folder next to it). A good place is `C:\GAM7\GAMGUI\`.
4. Double-click **`GAMGUI.exe`**. (Windows may warn about an unrecognized app
   because it isn't code-signed; choose **More info -> Run anyway**.)

No Python, no installers, nothing else to download. If you'd rather build it
yourself, see [Build from source](#build-from-source) below.

### Step 3 - First launch
- If the top of the window says `gam: (not found)`, click **Locate gam.exe...**
  and point it at your `gam` program. (GAMGUI finds it automatically when GAM is
  installed the normal way.)
- **Try a safe one first:** open **Diagnostics -> Domain info** and click
  **Run**. It only *reads* information and changes nothing - a perfect way to
  confirm everything works.

New, non-technical users: open **HOW-TO-GUIDE.txt** (included in the download)
for a complete, plain-English walkthrough. **README.txt** is the full reference.

---

## The task list at a glance

| Category | What it's for | GAM docs |
|----------|---------------|----------|
| Users | Create, reset password, suspend, move, rename, delete, look up, export | [Users](https://github.com/GAM-team/GAM/wiki/Users) |
| Groups | Mailing / access lists: create, add-remove members, sync from a department | [Groups](https://github.com/GAM-team/GAM/wiki/Groups-Membership) |
| Aliases | Extra email addresses for a person or group | [Aliases](https://github.com/GAM-team/GAM/wiki/Aliases) |
| Org Units | The "folders" that decide policies; move users between them | [Org Units](https://github.com/GAM-team/GAM/wiki/Organizational-Units) |
| Chromebooks | Move, disable, powerwash, wipe, inventory your device fleet | [ChromeOS](https://github.com/GAM-team/GAM/wiki/ChromeOS-Devices) |
| Gmail | Forwarding, delegates, vacation, signature, find/remove messages | [Gmail](https://github.com/GAM-team/GAM/wiki/Users-Gmail-Settings) |
| Calendars | Share calendars, list events | [Calendars](https://github.com/GAM-team/GAM/wiki/Calendars-Access) |
| Drive | List, share, transfer files; Shared Drives | [Drive](https://github.com/GAM-team/GAM/wiki/Users-Drive-Permissions) |
| Classroom | Courses and rosters; change a class owner | [Classroom](https://github.com/GAM-team/GAM/wiki/Classroom-Courses) |
| Licenses | See and assign Google licenses | [Licenses](https://github.com/GAM-team/GAM/wiki/Licenses) |
| Reports | Admin activity, logins, usage | [Reports](https://github.com/GAM-team/GAM/wiki/Reports) |
| Security | Sign out, deprovision, mailbox takeover audit, tokens | [Deprovision](https://github.com/GAM-team/GAM/wiki/Users-Deprovision) |
| Email Cleanup | Domain-wide search / trash / delete + incident-response workflow | [Messages](https://github.com/GAM-team/GAM/wiki/Users-Gmail-Messages-Threads) |
| Diagnostics | Version, domain info, authorization check | [Version & Help](https://github.com/GAM-team/GAM/wiki/Version-and-Help) |

Plus a **Custom command** mode that accepts any GAM command
([full command reference](https://github.com/GAM-team/GAM/wiki)).

---

## Safety and security (please read)

GAMGUI runs real commands against your live Google Workspace. It's built to be
careful, but treat it with respect:

- **It can do whatever your GAM can do.** GAMGUI has no permissions of its own -
  give it to people you trust with that level of access, and think about who
  should have the destructive tasks (deleting, wiping, domain-wide mail delete).
- **You always see the command first,** and destructive tasks pop a
  confirmation showing exactly what will happen.
- **Search before you delete.** For mail cleanup, run the read-only search and
  check the count first; prefer **Trash** (recoverable ~30 days) over **Delete**
  (permanent) when unsure.
- **Test in a non-production/test domain first** when you're learning.
- **Logs can contain email addresses and message details** - store and share
  them with that in mind.

---

## Build from source

GAMGUI is a single Python file (`GAMGUI.py`) using only the standard library.

```bat
py -m pip install pyinstaller
Build-EXE.bat
```

`Build-EXE.bat` runs `extract_tcl.py` and then PyInstaller in one-folder mode.
The extract step is **required on Python 3.14+**: Tcl/Tk 9 stores its script
library inside the DLL as a virtual zip filesystem, which PyInstaller doesn't
bundle on its own - without it the app crashes at startup with
`Tcl data directory _tcl_data not found`. `extract_tcl.py` copies that library
to disk so it can be bundled. The result is `dist\GAMGUI\` - distribute the
whole folder.

**macOS/Linux:** build on that OS with
`pyinstaller --onedir --windowed --name GAMGUI GAMGUI.py` (Linux needs the
`python3-tk` package). On Python 3.14+ apply the same `extract_tcl.py` +
`--add-data` approach shown in `Build-EXE.bat`. To just run it without building:
`python GAMGUI.py`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Top bar shows `gam: (not found)` | Click **Locate gam.exe...**, or install GAM the standard way so it's on the PATH. |
| "Windows protected your PC" on launch | The app isn't code-signed. Click **More info -> Run anyway**. |
| Commands return authorization errors | GAM isn't fully set up. Run **Diagnostics -> OAuth info** and re-authorize GAM. |
| App won't start after unzipping | Keep `GAMGUI.exe` and its `_internal` folder together in one folder. |
| A domain-wide search shows `exit code 50` or `60` | Normal on big domains - some mailboxes are always skipped; the results are still valid. |
| `Tcl data directory _tcl_data not found` (building yourself) | Run `extract_tcl.py` before PyInstaller, or just use `Build-EXE.bat`. |

---

## Project files

| File | Purpose |
|------|---------|
| `GAMGUI.py` | The entire application (single file, standard library only) |
| `extract_tcl.py` | Build helper: bundles Tcl/Tk data for Python 3.14+ |
| `Build-EXE.bat` | One-command Windows build |
| `HOW-TO-GUIDE.txt` | Plain-English guide for non-technical users |
| `README.txt` | Full reference and troubleshooting |
| `CHANGELOG.txt` | Version history |
| `NOTES.md` | Development notes, roadmap, known limitations |

---

## Contributing

Issues and pull requests are welcome. `GAMGUI.py` uses a data-driven task
catalog (the `TASKS` dictionary), so adding a task is a few lines and needs no
new code. Please keep the app dependency-free (standard library only) so it
stays easy to build and audit.

## License and disclaimer

Created by Gabriel Clifton. Licensed under the
[Apache License 2.0](LICENSE).

GAMGUI runs real administrative commands against a live Google Workspace through
GAM. Review the command preview before running, and test in a non-production
domain first. Provided **as-is, without warranty**. This is an independent
project and is **not affiliated with or endorsed by** the GAM project or Google.
