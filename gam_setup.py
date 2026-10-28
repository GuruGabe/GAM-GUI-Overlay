# =============================================================================
# gam_setup.py - the facts behind GAMGUI's "Set up GAM" window (2.97; Gabe
# 10-27-2026: "be able to install GAM7 and run gam oauth create/update ...
# just a pop-up window if needed").
#
# GAM's own first-time order (GAM wiki How-to-Install-GAM7; src/gam-install.sh
# runs the same steps after installing):
#
#   step            GAM command                               what it makes
#   --------------  ----------------------------------------  -----------------------
#   1 install       Windows: gam-<v>-windows-<arch>.exe        gam (C:\GAM7 on Windows,
#                   (elevated, /SILENT); macOS / Linux: the    ~/bin/gam7 elsewhere)
#                   install script with -l (install only)
#   2 project       gam create project <admin>                 client_secrets.json and
#                                                              oauth2service.json in the
#                                                              GAM config folder
#   3 admin         gam oauth create <admin>                   oauth2.txt (the admin's
#                   (later: gam oauth update - more scopes)    sign-in)
#   4 users' data   gam user <REGULAR user> check              the service account's
#                   serviceaccount (prints the Admin console   access to users' data
#                   link a super admin approves)
#
# Steps 2-4 open a browser and ask questions, so GAMGUI runs them in their OWN
# terminal window (console_command), never in the output pane.
#
# Pure functions except project_files (looks for two files) - GAMGUI.py
# does the asking, downloading and launching.
# =============================================================================

import os
import re
import shlex
import shutil
import subprocess

import gam_install

# Files 'gam create project' leaves in the GAM config folder (GAM's default
# names; gam.cfg can point elsewhere - then the window says "not found here"
# but every button still works).
PROJECT_FILES = ("client_secrets.json", "oauth2service.json")

# 'gam oauth info' with no admin sign-in yet (checked live 10-27-2026 with an
# empty GAM config folder: exit 51, "Client OAuth2 File: ...oauth2.txt, Not
# Shown: Does not exist").
_NO_OAUTH = re.compile(r"Client OAuth2 File:.*(Does not exist|Not Found)|"
                       r"oauth2\.txt,? Not Found", re.I)
_ADMIN = re.compile(r"Google Workspace Admin:\s*(\S+@\S+)")

# A failed command that the "Set up GAM" window can fix: a missing, expired or
# too-narrow sign-in, or a missing project / service account key. Checked
# AFTER explain_gam_error's hint is shown; GAMGUI then offers the window.
# "invalid_grant: Invalid email or User ID" is a wrong user, not a sign-in.
_SETUP_ERRORS = re.compile(
    r"Reauthentication is needed|invalid_grant(?!: Invalid email)|"
    r"No Client Access allowed|There are no scopes authorized|"
    r"Client OAuth2 File:.*(Does not exist|Not Found)|"
    r"Service Account OAuth2 File:.*(Does not exist|Not Found)|"
    r"No Service Account Access allowed", re.I)


def oauth_state(returncode, output):
    # 'gam oauth info' -> ("ok", admin email) / ("missing", "") / ("error",
    # GAM's first message line).
    found = _ADMIN.search(output or "")
    if found:
        return "ok", found.group(1)
    if _NO_OAUTH.search(output or ""):
        return "missing", ""
    lines = [l.strip() for l in (output or "").splitlines() if l.strip()]
    first = next((l for l in lines if l.upper().startswith("ERROR")), lines[0] if lines else "")
    return "error", first[:200] or ("exit code %s" % returncode)


def project_files(cfg_dir):
    # {file name: True if it is in the GAM config folder}.
    return {name: os.path.isfile(os.path.join(cfg_dir or "", name)) for name in PROJECT_FILES}


def needed_steps(gam_found, oauth, files):
    # The steps still to do, in GAM's order ("install", "project", "admin").
    # oauth: the first item of oauth_state(). An "error" sign-in (e.g. no
    # network) is NOT reported as missing - the window shows the message.
    if not gam_found:
        return ["install", "project", "admin"]
    steps = []
    if not all(files.values()):
        steps.append("project")
    if oauth == "missing":
        steps.append("admin")
    return steps


def setup_can_fix(output):
    # True when a failed command's output is a sign-in / project problem.
    return bool(_SETUP_ERRORS.search(output or ""))


def windows_gam_path(environ=None):
    # Where GAM's Windows installer puts gam.exe: DefaultDirName={sd}\GAM7
    # (src/gam.iss; {sd} = the system drive).
    drive = (environ if environ is not None else os.environ).get("SystemDrive") or "C:"
    return drive.rstrip("\\/") + "\\GAM7\\gam.exe"


def unix_gam_path(home=None):
    # The install script's default: $HOME/bin/gam7/gam.
    return os.path.join(home or os.path.expanduser("~"), "bin", "gam7", "gam")


def unix_install_command():
    # GAM's install script, install only (-l: no project / sign-in questions -
    # the window does those next). It adds 'gam' to the shell profile (its
    # default) so Terminal finds it too.
    inner = "bash <(curl -s -S -L %s) -l" % shlex.quote(gam_install.GAM_INSTALL_SCRIPT)
    return ["bash", "-c", inner]


def install_plan(release, system, machine):
    # (lines, problem) - what 'Install GAM7' will do, for the question asked
    # first; problem is set when it cannot (then nothing is done).
    tag = gam_install.release_version(release)
    if system == "Windows":
        asset = gam_install.pick_asset(release, "win-installer", machine)
        if not asset:
            return [], "GAM %s has no Windows installer for this computer." % (tag or "?")
        name, _url, sha = asset
        if not sha:
            return [], "GitHub gives no SHA-256 for %s, so GAMGUI will not install it." % name
        return ["Download %s from GAM's GitHub release" % name,
                "Check its SHA-256 against GitHub's",
                "Run it (Windows asks for administrator approval) - it installs GAM "
                "in %s" % os.path.dirname(windows_gam_path())], ""
    if system in ("Darwin", "Linux"):
        return ["Run GAM's own install script (it downloads GAM %s into %s and adds "
                "'gam' to your shell profile; it checks no SHA-256 - that is GAM's "
                "documented way):" % (tag or "(latest)", os.path.dirname(unix_gam_path())),
                "  " + unix_install_command()[2]], ""
    return [], "GAMGUI cannot install GAM on this system - see " + gam_install.GAM_RELEASES_URL


def perform_install(release, system, machine, out, on_proc=None, creationflags=0):
    # Installs GAM; returns the path of the new gam. Raises RuntimeError /
    # OSError when GAM was NOT installed. out(text) shows progress.
    if system == "Windows":
        asset = gam_install.pick_asset(release, "win-installer", machine)
        if not asset:
            raise RuntimeError("GAM's release has no Windows installer for this computer")
        _name, url, sha = asset
        work, path = gam_install.download_verified(url, sha, out)
        try:
            out("Running the GAM installer - approve the Windows administrator prompt...\n")
            done = subprocess.run(gam_install.installer_command(path), capture_output=True,
                                  text=True, creationflags=creationflags)
            if done.returncode != 0:
                raise RuntimeError("the installer stopped (exit %d)%s" % (
                    done.returncode, " - was the administrator prompt declined?"
                    if "cancel" in (done.stderr or "").lower() else ""))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        gam = windows_gam_path()
    elif system in ("Darwin", "Linux"):
        command = unix_install_command()
        out("> " + command[2] + "\n")
        rc = gam_install._stream(command, out, on_proc, creationflags)
        if rc != 0:
            raise RuntimeError("GAM's install script stopped (exit %d)" % rc)
        gam = unix_gam_path()
    else:
        raise RuntimeError("GAMGUI cannot install GAM on this system")
    if not os.path.isfile(gam):
        raise RuntimeError("the install finished but %s is not there" % gam)
    return gam


# ---- the setup commands (steps 2-4) ------------------------------------------
def step_argv(step, admin="", user=""):
    # The gam words for a setup button (without gam itself / 'select').
    if step == "project":
        return ["create", "project"] + ([admin] if admin else [])
    if step == "admin":
        return ["oauth", "create"] + ([admin] if admin else [])
    if step == "scopes":
        return ["oauth", "update"]
    if step == "serviceaccount":
        if not user:
            raise ValueError("a regular user's email address is needed")
        return ["user", user, "check", "serviceaccount"]
    raise ValueError("unknown step: " + step)


def _applescript_text(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def console_command(argv, title, system, cfg_dir="", which=None):
    # The command that opens a NEW terminal window running argv (gam and its
    # words) and keeps it open afterwards - or None when this system has no
    # terminal GAMGUI knows. cfg_dir: the GAM config folder GAMGUI uses (a
    # macOS Terminal window does NOT inherit GAMGUI's environment).
    if system == "Windows":
        # 'start' opens the console; 'cmd /k' keeps it open after gam exits.
        return ["cmd", "/c", "start", title, "cmd", "/k"] + list(argv)
    shell = " ".join(shlex.quote(a) for a in argv)
    if cfg_dir:
        shell = "export GAMCFGDIR=%s; %s" % (shlex.quote(cfg_dir), shell)
    shell += "; echo; read -r -p 'Press Enter to close this window...' _"
    if system == "Darwin":
        return ["osascript",
                "-e", 'tell application "Terminal" to do script %s' % _applescript_text(
                    "bash -c " + shlex.quote(shell)),
                "-e", 'tell application "Terminal" to activate']
    if system == "Linux":
        if which is None:
            which = shutil.which
        for name, form in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]),
                           ("konsole", ["-e"]), ("xfce4-terminal", ["-x"]), ("xterm", ["-e"])):
            if which(name):
                return [name] + form + ["bash", "-c", shell]
    return None
