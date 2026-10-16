# =============================================================================
# gam_install.py - how was GAM itself installed, and how to update it the
# SAME way (GAMGUI 2.88; Gabe 10-13-2026: "Find out how GAM7 was installed
# ... and prompt to update GAM7 when needed using the same method").
#
# GAM's own documented ways (GAM wiki: Downloads-Installs, How-to-Update-GAM7,
# Install-GAM-as-Python-Library; GAM repo src/gam.iss and src/gam-install.sh):
#
#   kind            how GAMGUI tells                   how GAMGUI updates it
#   --------------  ---------------------------------  ---------------------------
#   win-installer   Windows; GAM7's uninstall entry     download the installer
#                   (Inno Setup AppId {D86B52B2-...}    gam-<v>-windows-<arch>.exe,
#                   _is1, or the older GAM7 MSI with    check its SHA-256, run it
#                   the same code) points at gam.exe's  (UAC prompt; it removes an
#                   folder                              old MSI GAM itself)
#   win-zip         Windows; gam.exe with no such entry download the .zip, check its
#                                                       SHA-256, replace gam.exe and
#                                                       lib in the SAME folder
#   pip             'gam version' says pythonsource and pip install --upgrade gam7
#                   gam is in a Python Scripts folder
#   unix-archive    macOS / Linux build of GAM          GAM's own install script in
#                   (pyinstaller)                       update mode: -l (skip project
#                                                       and auth) -p false (leave the
#                                                       shell profile alone) -d <the
#                                                       same folder>
#   source          pythonsource, not from pip (a copy  manual - GAM's Releases page
#                   of GAM's source code)
#   unknown         anything else (e.g. Homebrew)       manual - GAM's Releases page
#
# GitHub publishes a SHA-256 'digest' for every release file; GAMGUI refuses a
# download whose hash does not match. GAM's install script (macOS / Linux)
# does its own download and checks no hash - that is GAM's documented way,
# so GAMGUI says so before running it.
#
# Pure functions except windows_uninstall_entries (reads the registry) and
# apply_zip_update (changes files) - GAMGUI.py does the downloading, asking
# and launching.
# =============================================================================

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile

GAM_RELEASES_URL = "https://github.com/GAM-team/GAM/releases/latest"
GAM_LATEST_API = "https://api.github.com/repos/GAM-team/GAM/releases/latest"
GAM_INSTALL_SCRIPT = "https://raw.githubusercontent.com/GAM-team/GAM/main/src/gam-install.sh"
# GAM's Inno Setup AppId (src/gam.iss) - also the upgrade code of the older
# GAM7 MSI installer, which the new installer removes before installing.
GAM_APP_ID = "{D86B52B2-EFE9-4F9D-8BA3-9D84B9B2D319}"

KIND_LABELS = {
    "win-installer": "the GAM7 Windows installer",
    "win-zip": "the GAM7 Windows zip (extracted into a folder)",
    "pip": "pip (GAM as a Python library)",
    "unix-archive": "GAM's macOS / Linux download (install script or archive)",
    "source": "a copy of GAM's source code",
    "unknown": "a way GAMGUI does not recognise",
}


def version_tuple(text):
    # "v7.48.26" / "GAM 7.48.26 - ..." -> (7, 48, 26); unreadable -> ().
    found = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(p or 0) for p in found.groups()) if found else ()


# A GAM version like 7.48.29 (a 1-2 digit first part, so a date-style tag
# such as 2026.10.15 is never taken for a version).
_GAM_VERSION_RE = re.compile(r"(?<!\d)(\d{1,2}\.\d+\.\d+)(?![\d.])")


def release_version(release):
    # GAM's version from a GitHub release (releases/latest JSON), "" if none.
    # 2.90: GAM 7.48.29 was tagged "20261015.233203" (name "GAM 7.48.29",
    # files gam-7.48.29-...); earlier releases were tagged "v7.48.28". So:
    # the tag when it IS a version, else the release name, else the files.
    tag = (release.get("tag_name") or "").strip().lstrip("v")
    if _GAM_VERSION_RE.fullmatch(tag):
        return tag
    found = _GAM_VERSION_RE.search(release.get("name") or "")
    if found:
        return found.group(1)
    for asset in release.get("assets") or []:
        found = re.match(r"gam-(\d{1,2}\.\d+\.\d+)-", asset.get("name") or "")
        if found:
            return found.group(1)
    return ""


def _norm(path):
    return os.path.normcase(os.path.normpath(path or "")).rstrip("\\/")


def windows_uninstall_entries():
    # The registry's uninstall entries that look like GAM7, as dicts
    # {key, name, version, location, msi}. Empty off Windows or on error.
    try:
        import winreg
    except ImportError:
        return []
    out = []
    roots = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE,
              r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")]
    for root, path in roots:
        try:
            with winreg.OpenKey(root, path) as parent:
                count = winreg.QueryInfoKey(parent)[0]
                for i in range(count):
                    try:
                        name = winreg.EnumKey(parent, i)
                        with winreg.OpenKey(parent, name) as key:
                            def value(field):
                                try:
                                    return str(winreg.QueryValueEx(key, field)[0] or "")
                                except OSError:
                                    return ""
                            entry = {"key": name, "name": value("DisplayName"),
                                     "version": value("DisplayVersion"),
                                     "location": value("InstallLocation"),
                                     "msi": value("WindowsInstaller") == "1"}
                    except OSError:
                        continue
                    if is_gam_entry(entry):
                        out.append(entry)
        except OSError:
            continue
    return out


def is_gam_entry(entry):
    # GAM7's own installer entry: its AppId (Inno: '<AppId>_is1'), or a
    # 'GAM7 ...' display name (the older MSI).
    key = (entry.get("key") or "").upper()
    return key.startswith(GAM_APP_ID.upper()) or \
        (entry.get("name") or "").strip().upper().startswith("GAM7")


def detect(gam_path, version_line, system, uninstall_entries=(), python_dirs=()):
    # How the GAM at gam_path was installed -> {"kind", "label", "folder"}.
    # version_line: the first line of 'gam version' ("GAM 7.48.26 - ... -
    # pyinstaller|pythonsource"); system: platform.system().
    folder = os.path.dirname(os.path.realpath(gam_path)) if gam_path else ""
    line = (version_line or "").lower()

    def result(kind):
        return {"kind": kind, "label": KIND_LABELS[kind], "folder": folder}
    if not gam_path:
        return result("unknown")
    if "pythonsource" in line or any(_norm(folder) == _norm(d) for d in python_dirs):
        return result("pip" if any(_norm(folder) == _norm(d) for d in python_dirs)
                      else "source")
    if system == "Windows":
        for entry in uninstall_entries:
            if is_gam_entry(entry) and _norm(entry.get("location")) == _norm(folder):
                return result("win-installer")
        return result("win-zip")
    if system in ("Darwin", "Linux"):
        # Homebrew and other package managers keep GAM under their own tree;
        # GAM's script would put a second copy beside it, so leave those alone.
        if re.search(r"/(cellar|homebrew|linuxbrew|nix/store)/", _norm(folder).replace("\\", "/") + "/"):
            return result("unknown")
        return result("unix-archive")
    return result("unknown")


def windows_arch(machine):
    # platform.machine() on Windows ("AMD64" / "ARM64") -> GAM's word.
    return "arm64" if (machine or "").upper() in ("ARM64", "AARCH64") else "x86_64"


def pick_asset(release, kind, machine):
    # The release file for a Windows kind -> (name, url, sha256) or None.
    # release: GitHub's releases/latest JSON.
    tag = release_version(release)
    ext = {"win-installer": ".exe", "win-zip": ".zip"}.get(kind)
    if not ext or not tag:
        return None
    want = "gam-%s-windows-%s%s" % (tag, windows_arch(machine), ext)
    for asset in release.get("assets") or []:
        if asset.get("name") == want:
            digest = asset.get("digest") or ""
            sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
            return want, asset.get("browser_download_url") or "", sha
    return None


def script_command(folder):
    # GAM's install script in update mode for the macOS / Linux copy in
    # 'folder'. The script makes '<-d>/gam7' unless -s is given, so a folder
    # called gam7 is updated with -d <its parent>, any other with -d <it> -s.
    folder = folder.rstrip("/") or "/"
    if os.path.basename(folder) == "gam7":
        where = ["-d", os.path.dirname(folder) or "/"]
    else:
        where = ["-d", folder, "-s"]
    inner = "bash <(curl -s -S -L %s) -l -p false %s" % (
        shlex.quote(GAM_INSTALL_SCRIPT), " ".join(shlex.quote(w) for w in where))
    return ["bash", "-c", inner]


def installer_command(exe_path):
    # Runs GAM's Windows installer elevated (it needs admin - src/gam.iss
    # PrivilegesRequired=admin) and WAITS for it, returning its exit code.
    # /SILENT = progress window only, it updates the folder it was
    # installed in; /SUPPRESSMSGBOXES /NORESTART = no questions, no reboot.
    ps = ("$p = Start-Process -FilePath '%s' -ArgumentList '/SILENT','/SUPPRESSMSGBOXES',"
          "'/NORESTART' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
          % exe_path.replace("'", "''"))
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps]


def update_steps(info, release, machine, python=""):
    # What 'Update GAM' will do, as plain-English lines (for the question
    # GAMGUI asks first) - or a reason it cannot. -> (lines, error)
    kind = info["kind"]
    tag = release_version(release)
    if kind in ("win-installer", "win-zip"):
        asset = pick_asset(release, kind, machine)
        if not asset:
            return [], "GAM %s has no %s file for this computer." % (tag, kind.split("-")[1])
        name, _url, sha = asset
        if not sha:
            return [], "GitHub gives no SHA-256 for %s, so GAMGUI will not install it." % name
        if kind == "win-installer":
            return ["Download %s from GAM's GitHub release" % name,
                    "Check its SHA-256 against GitHub's",
                    "Run it (Windows asks for administrator approval) - it updates "
                    "GAM in %s" % info["folder"]], ""
        return ["Download %s from GAM's GitHub release" % name,
                "Check its SHA-256 against GitHub's",
                "Replace gam.exe and its lib folder in %s (the old ones are kept "
                "until the new ones are in place)" % info["folder"]], ""
    if kind == "pip":
        if not python:
            return [], "No Python was found to run pip with."
        return ["Run: %s -m pip install --upgrade gam7" % python], ""
    if kind == "unix-archive":
        return ["Run GAM's own install script in update mode (it downloads GAM %s "
                "into %s; it checks no SHA-256 - that is GAM's documented way):"
                % (tag, info["folder"]),
                "  " + script_command(info["folder"])[2]], ""
    return [], "GAMGUI cannot update %s - update GAM the way you installed it." \
        % info["label"]


def pip_command(python):
    return [python, "-m", "pip", "install", "--upgrade", "gam7"]


def is_writable(folder):
    # A real create-and-delete test (os.access ignores Windows ACLs).
    try:
        probe = os.path.join(folder, ".gamgui-write-test")
        with open(probe, "w") as handle:
            handle.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


def download_verified(url, sha, out):
    # Downloads 'url' into a NEW temporary folder and returns (folder, file).
    # Refused - nothing kept - unless the file's SHA-256 matches 'sha' (the
    # digest GitHub publishes for the release file).
    if not sha:
        raise RuntimeError("no SHA-256 to check the download against")
    work = tempfile.mkdtemp(prefix="gamgui-gam-")
    path = os.path.join(work, url.rstrip("/").rsplit("/", 1)[-1] or "download")
    out("Downloading " + url + "\n")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "GAMGUI-GAM-Update"}), timeout=120) as resp, \
                open(path, "wb") as handle:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                digest.update(chunk)
                handle.write(chunk)
        if digest.hexdigest().lower() != sha.lower():
            raise RuntimeError("the download's SHA-256 does not match GitHub's - nothing "
                               "was installed")
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    out("SHA-256 checked - it matches GitHub's.\n")
    return work, path


def _stream(command, out, on_proc=None, creationflags=0):
    # Runs a command, passing every line to out() (terminal colours
    # removed); on_proc(proc) lets a Stop button end it. -> exit code.
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=creationflags,
                            start_new_session=(os.name != "nt"))
    if on_proc:
        on_proc(proc)
    for line in proc.stdout:
        out(re.sub(r"\x1b\[[0-9;]*m", "", line))
    return proc.wait()


def perform_update(info, release, machine, out, python="", on_proc=None, creationflags=0):
    # Updates GAM the way it was installed (see the table at the top).
    # out(text) shows progress; raises RuntimeError / OSError when GAM was NOT
    # updated. Shared by the desktop app and the browser version.
    kind = info["kind"]
    folder = info["folder"]
    if kind in ("win-installer", "win-zip"):
        asset = pick_asset(release, kind, machine)
        if not asset:
            raise RuntimeError("GAM's release has no matching file for this computer")
        name, url, sha = asset
        if kind == "win-zip" and not is_writable(folder):
            raise RuntimeError("cannot write to " + folder + " - run this as administrator "
                               "once, or update GAM by hand")
        work, path = download_verified(url, sha, out)
        try:
            if kind == "win-installer":
                out("Running the GAM installer - approve the Windows administrator "
                    "prompt...\n")
                done = subprocess.run(installer_command(path), capture_output=True,
                                      text=True, creationflags=creationflags)
                if done.returncode != 0:
                    raise RuntimeError("the installer stopped (exit %d)%s" % (
                        done.returncode, " - was the administrator prompt declined?"
                        if "cancel" in (done.stderr or "").lower() else ""))
            else:
                apply_zip_update(path, folder, log=lambda t: out(t + "\n"))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return
    if kind == "unix-archive":
        command = script_command(folder)
    elif kind == "pip":
        if not python:
            raise RuntimeError("no Python was found to run pip with")
        command = pip_command(python)
    else:
        raise RuntimeError("GAMGUI cannot update " + info["label"] + " - update GAM the "
                           "way you installed it (" + GAM_RELEASES_URL + ")")
    out("> " + (command[2] if kind == "unix-archive" else " ".join(command)) + "\n")
    rc = _stream(command, out, on_proc, creationflags)
    if rc != 0:
        raise RuntimeError("%s stopped (exit %d)" % (
            "GAM's install script" if kind == "unix-archive" else "pip", rc))


def check_zip(zip_path):
    # The GAM zip's member names, after refusing anything unsafe (an
    # absolute path or '..' could write outside the folder). Every member
    # must sit under 'gam7/'. ValueError for a bad file.
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    for name in names:
        clean = name.replace("\\", "/")
        if clean.startswith("/") or re.match(r"^[A-Za-z]:", clean) or \
                ".." in clean.split("/") or not clean.startswith("gam7/"):
            raise ValueError("Unexpected file in the GAM zip: " + name)
    if "gam7/gam.exe" not in names:
        raise ValueError("The GAM zip has no gam7/gam.exe.")
    return names


def apply_zip_update(zip_path, folder, log=print):
    # Replaces the files of a zip-extracted GAM in 'folder' with the zip's
    # gam7/ contents. Files that are not in the zip (gam.cfg, oauth2.txt,
    # GAMGUI itself...) are never touched. gam.exe and lib are RENAMED first
    # (Windows allows renaming a running .exe) and put back if anything fails.
    check_zip(zip_path)
    stamp = time.strftime("%Y%m%d%H%M%S")
    staging = os.path.join(folder, ".gamgui-gam-update-" + stamp)
    moved = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging)
        new_root = os.path.join(staging, "gam7")
        for name in ("gam.exe", "lib"):
            old = os.path.join(folder, name)
            if os.path.exists(old):
                aside = old + ".old-" + stamp
                os.rename(old, aside)
                moved.append((old, aside))
        for entry in os.listdir(new_root):
            source = os.path.join(new_root, entry)
            target = os.path.join(folder, entry)
            if os.path.isdir(source):
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
        log("Copied the new GAM files into " + folder)
    except Exception:
        # Put the old gam.exe / lib back; the new copies (if any) go first.
        for old, aside in reversed(moved):
            if os.path.isdir(old):
                shutil.rmtree(old, ignore_errors=True)
            elif os.path.exists(old):
                try:
                    os.remove(old)
                except OSError:
                    pass
            os.rename(aside, old)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    # The old copies go last; a gam.exe still running stays until next time.
    for _old, aside in moved:
        try:
            if os.path.isdir(aside):
                shutil.rmtree(aside)
            else:
                os.remove(aside)
        except OSError:
            log("Could not remove " + aside + " yet (in use) - delete it later.")
