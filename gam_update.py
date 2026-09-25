# =============================================================================
# Script:   gam_update.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  09-25-2026
# Modified: 09-25-2026
# Version:  1.0 (GAMGUI 2.63)
#
# Purpose:
#   In-app updates for macOS and Linux (Windows keeps updategamgui.ps1).
#   No PowerShell or anything else to install: GAMGUI downloads the release
#   asset, checks it against the SHA-256 published in the release notes,
#   unpacks it, and hands a small bash script the job of swapping the new
#   copy in after GAMGUI has closed, then reopening it.
#
#     macOS, GAMGUI.app       GAMGUI-<v>-macOS.zip -> ditto -> codesign
#                             --verify -> swap the .app (rolled back if the
#                             copy fails) -> open
#     Linux, portable folder  GAMGUI-<v>-Linux.tar.gz -> swap the files in
#                             the folder, keeping gamgui.ini,
#                             gamgui_tasklists.json and Logs -> relaunch
#     Linux, .deb / .rpm      (in /opt, needs root) -> download + verify the
#                             package, then show the one sudo command to run
#     From source             -> open the Releases page
#
# Notes:
#   - Pure functions + script text only; GAMGUI.py does the downloading and
#     launching. The bash scripts use only what macOS / Linux always have.
#   - Nothing is installed unless the download's SHA-256 matches the value
#     in the release notes. No published hash = no update.
# =============================================================================

import os
import re
import shlex
import tarfile

UPDATE_KINDS = ("mac-app", "linux-portable", "linux-package", "source",
                "unknown")


def mac_data_dir(home=None):
    # Where GAMGUI keeps gamgui.ini, favorites and Logs on macOS (2.63+):
    # the standard per-user folder, NOT inside GAMGUI.app - writing into a
    # signed app bundle can break its signature, and replacing the app
    # (update) would wipe the settings.
    return os.path.join(home or os.path.expanduser("~"), "Library",
                        "Application Support", "GAMGUI")


def mac_bundle_path(executable):
    # /Applications/GAMGUI.app/Contents/MacOS/GAMGUI -> /Applications/GAMGUI.app
    parts = os.path.abspath(executable).split(os.sep)
    for i in range(len(parts) - 1, 0, -1):
        if parts[i].endswith(".app") and parts[i + 1:i + 2] == ["Contents"]:
            return os.sep.join(parts[:i + 1]) or os.sep
    return None


def install_kind(system, executable, frozen, writable):
    # system: platform.system() ("Darwin" / "Linux"); executable: the running
    # program; frozen: running as the built app; writable(path) -> bool.
    # Returns (kind, target): target is the .app path (mac-app) or the app
    # folder (linux-portable / linux-package).
    if not frozen:
        return "source", None
    if system == "Darwin":
        app = mac_bundle_path(executable)
        if app and writable(os.path.dirname(app)) and writable(app):
            return "mac-app", app
        return "unknown", app
    if system == "Linux":
        folder = os.path.dirname(os.path.abspath(executable))
        if writable(folder):
            return "linux-portable", folder
        return "linux-package", folder
    return "unknown", None


def asset_name(kind, tag, package_tool=None):
    # The release asset each kind of install needs (names from the build
    # workflow). package_tool: "apt" or "dnf"/"yum"/"zypper" for packages.
    if kind == "mac-app":
        return "GAMGUI-%s-macOS.zip" % tag
    if kind == "linux-portable":
        return "GAMGUI-%s-Linux.tar.gz" % tag
    if kind == "linux-package":
        if package_tool == "apt":
            return "gamgui_%s_amd64.deb" % tag
        return "gamgui-%s-1.x86_64.rpm" % tag
    return None


def published_sha256(body, name):
    # The release notes carry "SHA-256 (<asset>):" then the hash on the next
    # line (added after every build). Returns the upper-case hex or None.
    found = re.search(r"SHA-256 \(" + re.escape(name) + r"\):\s*([0-9A-Fa-f]{64})",
                      body or "")
    return found.group(1).upper() if found else None


def package_command(tool, path):
    # The one command a Linux admin runs to install a downloaded package.
    quoted = shlex.quote(path)
    return {"apt": "sudo apt install " + quoted,
            "dnf": "sudo dnf install " + quoted,
            "yum": "sudo yum install " + quoted,
            "zypper": "sudo zypper install " + quoted}.get(tool, "sudo rpm -U " + quoted)


def safe_extract_tar(archive, dest):
    # Extracts the Linux tar.gz, refusing anything that would land outside
    # 'dest' (absolute paths, '..', or links pointing out) - a damaged or
    # tampered archive must not write elsewhere. Returns the member count.
    dest_real = os.path.realpath(dest)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for m in members:
            target = os.path.realpath(os.path.join(dest, m.name))
            if not (target == dest_real or target.startswith(dest_real + os.sep)):
                raise ValueError("unsafe path in archive: " + m.name)
            if m.issym() or m.islnk():
                link = os.path.realpath(os.path.join(os.path.dirname(target), m.linkname))
                if not link.startswith(dest_real + os.sep):
                    raise ValueError("unsafe link in archive: " + m.name)
            if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
                raise ValueError("unexpected item in archive: " + m.name)
        tar.extractall(dest, members=members)
    return len(members)


_HEADER = """#!/bin/bash
# GAMGUI updater ({what}) - written by GAMGUI {version}. It waits for GAMGUI
# (process {pid}) to close, installs the new version, and reopens it. Safe
# to delete afterwards. Log: {log}
LOG={log_q}
log() {{ echo "[$(date '+%m-%d-%Y %H:%M:%S')] $*" >> "$LOG"; }}
PID={pid}
# Wait up to 60 seconds for GAMGUI to close (its files must not be in use).
for i in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
if kill -0 "$PID" 2>/dev/null; then
    log "GAMGUI is still running - update cancelled"; exit 1
fi
"""


def mac_update_script(pid, app, new_app, old_data, new_data, work, log,
                      version):
    # Swaps /Applications/GAMGUI.app for the verified new copy. Settings that
    # older versions kept INSIDE the app are copied to Application Support
    # first. If the signature check or the copy fails, the old app stays.
    q = shlex.quote
    return _HEADER.format(what="macOS", version=version, pid=int(pid),
                          log=log, log_q=q(log)) + """APP={app}
NEW={new}
OLDDATA={old}
DATA={data}
WORK={work}
log "updating $APP"
# Keep settings/favorites/logs that older versions stored inside the app.
mkdir -p "$DATA"
for f in gamgui.ini gamgui_tasklists.json; do
    if [ -f "$OLDDATA/$f" ] && [ ! -f "$DATA/$f" ]; then cp -p "$OLDDATA/$f" "$DATA/$f"; fi
done
if [ -d "$OLDDATA/Logs" ]; then mkdir -p "$DATA/Logs"; cp -Rp "$OLDDATA/Logs/." "$DATA/Logs/"; fi
# The new app must pass Apple's signature check before it replaces anything.
if ! codesign --verify --deep --strict "$NEW" >> "$LOG" 2>&1; then
    log "new app failed the signature check - nothing changed"; open "$APP"; exit 1
fi
rm -rf "$APP.old"
if ! mv "$APP" "$APP.old"; then log "could not move the old app aside"; open "$APP"; exit 1; fi
if ditto "$NEW" "$APP"; then
    rm -rf "$APP.old"; log "updated to the new version"
else
    rm -rf "$APP"; mv "$APP.old" "$APP"; log "copy failed - old version restored"
fi
rm -rf "$WORK"
open "$APP"
""".format(app=q(app), new=q(new_app), old=q(old_data), data=q(new_data),
           work=q(work))


KEEP_ON_UPDATE = ("gamgui.ini", "gamgui_tasklists.json", "Logs")


def linux_update_script(pid, folder, new_folder, work, log, version):
    # Replaces the files of a portable Linux copy with the verified new ones,
    # keeping the user's settings, favorites and logs. The old files are
    # moved aside first and put back if anything fails.
    q = shlex.quote
    keep = " ".join(KEEP_ON_UPDATE)
    return _HEADER.format(what="Linux", version=version, pid=int(pid),
                          log=log, log_q=q(log)) + """DIR={folder}
NEW={new}
WORK={work}
OLD="$WORK/old"
log "updating $DIR"
mkdir -p "$OLD" || {{ log "cannot create $OLD"; exit 1; }}
# Move the old files aside - except the user's settings, favorites and logs.
for item in "$DIR"/* "$DIR"/.[!.]*; do
    [ -e "$item" ] || continue
    case "$(basename "$item")" in {keep_case}) continue ;; esac
    mv "$item" "$OLD/" || {{ log "could not move $item"; FAIL=1; break; }}
done
if [ -z "$FAIL" ]; then
    for item in "$NEW"/* "$NEW"/.[!.]*; do
        [ -e "$item" ] || continue
        case "$(basename "$item")" in {keep_case}) continue ;; esac
        cp -Rp "$item" "$DIR/" || {{ log "could not copy $item"; FAIL=1; break; }}
    done
fi
if [ -n "$FAIL" ]; then
    log "update failed - putting the old version back"
    for item in "$OLD"/* "$OLD"/.[!.]*; do
        [ -e "$item" ] || continue
        rm -rf "$DIR/$(basename "$item")"; mv "$item" "$DIR/"
    done
else
    log "updated to the new version (kept: {keep})"
fi
rm -rf "$WORK"
nohup "$DIR/GAMGUI" > /dev/null 2>&1 &
""".format(folder=q(folder), new=q(new_folder), work=q(work), keep=keep,
           keep_case="|".join(KEEP_ON_UPDATE))
