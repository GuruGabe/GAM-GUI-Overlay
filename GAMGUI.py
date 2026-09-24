# =============================================================================
# Script:   GAMGUI.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google
#           Workspace and generalized for public sharing.
# Created:  07-23-2026
# Modified: 08-07-2026
# Version:  1.18
#
# Purpose:
#   A graphical front-end (GUI) for GAM7, the command line tool for Google
#   Workspace administration. GAMGUI presents common GAM tasks as fill-in
#   forms, builds the exact GAM command for you, shows it before running,
#   and displays live output. It is aimed at admins who want GAM's power
#   without memorizing its syntax.
#
# Usage:
#   python GAMGUI.py          (from source)
#   GAMGUI.exe                (PyInstaller build; place next to gam.exe)
#
# Requirements:
#   - Python 3.10+ with tkinter (included in the standard Windows installer)
#   - GAM7 installed and authorized (https://github.com/GAM-team/GAM)
#   - No third-party Python packages required (standard library only)
#
# Notes:
#   - GAMGUI never talks to Google directly. Every action is executed by
#     your own gam executable with your existing authorization. GAMGUI
#     holds no credentials.
#   - Commands are shown before they run and can be edited or copied.
#   - Actions marked DESTRUCTIVE require an extra confirmation.
#   - A session log is written to the Logs folder next to this program.
# =============================================================================

# --- Standard library imports only; this keeps the program dependency-free ---
import os                      # File paths, environment
import sys                     # Detect frozen (EXE) vs source execution
import shutil                  # shutil.which() finds gam on the PATH
import subprocess              # Runs the gam commands
import threading               # Runs gam without freezing the window
import queue                   # Thread-safe pipe from worker to the UI
import re                      # Optional-segment parsing in command templates
import signal                  # Process-group kill on macOS/Linux (Stop button)
import datetime                # Timestamps for the log (MM-DD-YYYY HH:MM:SS)
import configparser            # Saves settings (gam path) between sessions
import csv                     # Parses discovery results in the incident workflow
import io                       # In-memory CSV parsing for the bulk-license tools
import json                    # Parses the GitHub release API for update checks
import urllib.request          # Fetches the latest release info (update check)
import webbrowser              # Opens the Releases page when self-update cannot run
import tkinter as tk           # The GUI toolkit that ships with Python
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog

APP_NAME = "GAMGUI"
APP_VERSION = "2.51"

# GitHub repo that publishes GAMGUI releases, and the API endpoint used by the
# built-in update check. The check only READS this public endpoint (no token).
UPDATE_REPO = "GuruGabe/GAM-GUI-Overlay"
UPDATE_API_URL = "https://api.github.com/repos/" + UPDATE_REPO + "/releases/latest"
UPDATE_RELEASES_URL = "https://github.com/" + UPDATE_REPO + "/releases/latest"

# =============================================================================
# SECTION: Locating gam and application folders
# =============================================================================

def app_dir():
    # When packaged by PyInstaller, sys.frozen is set and the EXE location is
    # sys.executable. From source, use this .py file's folder instead.
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def find_gam(saved_path):
    # Search order (first hit wins):
    #   1. The path the user saved previously in gamgui.ini
    #   2. gam.exe / gam sitting in the SAME folder as GAMGUI
    #      (the recommended install: drop GAMGUI.exe into C:\GAM7)
    #   3. Anywhere on the system PATH
    if saved_path and os.path.isfile(saved_path):
        return saved_path
    for name in ("gam.exe", "gam"):
        candidate = os.path.join(app_dir(), name)
        if os.path.isfile(candidate):
            return candidate
    hit = shutil.which("gam")
    if hit:
        return hit
    return ""

def _is_writable(path):
    # True only if we can actually CREATE a file in 'path'. os.access(W_OK) is
    # unreliable on Windows (it ignores ACLs and reports Program Files as
    # writable), so do a real write-and-delete probe.
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".gamgui_write_test")
        with open(probe, "w") as handle:
            handle.write("")
        os.remove(probe)
        return True
    except Exception:
        return False


def data_dir():
    # Where GAMGUI keeps its writable data: gamgui.ini and the Logs folder.
    # PORTABLE use (unzipped into a writable folder like C:\GAM7\GAMGUI): keep
    # the data right next to the app so everything travels together and the
    # updater/robocopy deploy can preserve it. INSTALLED use (Program Files):
    # that folder is read-only for standard users, so fall back to a per-user
    # folder under LocalAppData. This is what prevents the "Access is denied:
    # ...\Program Files\GAMGUI\Logs" crash on an installed copy.
    base = app_dir()
    if _is_writable(base):
        return base
    fallback = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "GAMGUI")
    try:
        os.makedirs(fallback, exist_ok=True)
    except Exception:
        pass
    return fallback

def _same_path(a, b):
    # True if two filesystem paths point at the same folder, ignoring case and
    # a trailing slash (Windows paths). Used to tell whether THIS running copy
    # is the registered Setup.exe install.
    if not a or not b:
        return False
    try:
        na = os.path.normcase(os.path.normpath(a)).rstrip("\\/")
        nb = os.path.normcase(os.path.normpath(b)).rstrip("\\/")
        return na == nb
    except Exception:
        return False


# Matches the GAM keyword "password" (as a whole word, any case) plus the
# value that follows it, in any of the shapes it reaches the log in:
#   gam create user a@b.com password Secret1!      (a plain command line)
#   gam ... password "Two Words"                   (a quoted value)
#   ['...', 'password', 'Secret1!']                (the repr() of an argv list)
#   Password: Secret1!                             (GAM echoing a password)
# Group 1 is the keyword and separator (kept); group 2 is the value (masked).
# "changepassword" / "changepasswordurl" do NOT match because \b needs a word
# boundary right before "password".
_SECRET_RE = re.compile(
    r"(?i)(\bpassword\b['\"]?[,:]?\s+)(\"[^\"]*\"|'[^']*'|\S+)")


def redact_secrets(text):
    # Returns text with every password value replaced by ********. Used ONLY
    # for what is written to the session log file on disk - the command that
    # actually runs, and the preview on screen, are never changed. Why: the
    # log is a plain-text file in the Logs folder, and passwords (new-user
    # passwords, reset passwords, S/MIME certificate passwords) must never be
    # stored there.
    try:
        return _SECRET_RE.sub(lambda m: m.group(1) + "********", text)
    except Exception:
        return text                   # never let redaction break logging


def registry_exe_install():
    # Reads the Setup.exe (Inno) install record that gamgui.iss writes to
    # HKLM\SOFTWARE\GAMGUI (Version + InstallLocation). Returns a dict
    # {"version", "location"} or None. Windows-only; winreg does not exist on
    # macOS/Linux (where gam_web imports this module), so it is imported lazily
    # and any failure just means "no installed copy found".
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except Exception:
        return None
    for subkey in (r"SOFTWARE\GAMGUI", r"SOFTWARE\WOW6432Node\GAMGUI"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                try:
                    location = winreg.QueryValueEx(key, "InstallLocation")[0]
                except OSError:
                    location = ""
                try:
                    version = winreg.QueryValueEx(key, "Version")[0]
                except OSError:
                    version = ""
                if location or version:
                    return {"version": str(version), "location": str(location)}
        except OSError:
            continue          # this view has no key; try the next
        except Exception:
            continue
    return None


DATA_DIR = data_dir()
INI_PATH = os.path.join(DATA_DIR, "gamgui.ini")
LOG_DIR = os.path.join(DATA_DIR, "Logs")
# Favorites and Recent tasks are kept in their own small JSON file (not the
# .ini) because task names can contain characters such as % that the .ini
# reader treats specially.
TASKLISTS_PATH = os.path.join(DATA_DIR, "gamgui_tasklists.json")
RECENT_MAX = 10                  # how many recently run tasks to remember

# Text-size steps offered by View > Larger / Smaller text. 1.0 is the normal
# size; index 1 is the default. Larger steps help on projectors and high-DPI
# screens.
TEXT_SCALES = [0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0]
TEXT_SCALE_DEFAULT = 1

# The command catalog and builder now live in gam_catalog.py so the desktop
# and web front-ends share one source. Re-exported here so gam_web.py's
# "import GAMGUI as gg" keeps finding gg.TASKS, gg.build_command, etc.
from gam_catalog import (
    T, F, quote_if_needed, build_command, incident_query, win_split,
    translate_license, TASKS, task_doc_url, bulk_field_modes,
    build_bulk_command, uses_local_time, contains_password, make_bat_script,
    make_sh_script,
)

# =============================================================================
# SECTION: Color themes (light / dark)
#
# Dark mode is a SOFT, low-contrast dark gray - easy on the eyes for long
# sessions and deliberately NOT pure black on white, which is the "blinding"
# look we are avoiding. It is applied through ttk's "clam" theme because that
# is the one ttk theme that actually honors custom colors on Windows (the
# native "vista" theme ignores most color settings), plus direct coloring of
# the two classic Tk Text widgets (the command preview and the output pane),
# which do not follow ttk styles at all.
# =============================================================================
DARK_PALETTE = {
    "bg":            "#2b2b2b",   # window and frame background
    "fg":            "#e0e0e0",   # normal text: soft off-white, not pure white
    "entry_bg":      "#3c3f41",   # entries, dropdowns, tree, output background
    "select_bg":     "#4a6785",   # selection highlight: a muted blue
    "select_fg":     "#ffffff",   # text on a selection
    "button_bg":     "#3c3f41",   # button face
    "button_active": "#4a4f52",   # button face while hovered/pressed
    "disabled":      "#808080",   # disabled text
    "trough":        "#3c3f41",   # scrollbar / progress troughs
}
# Light mode restores the platform-native ttk theme, so these values only need
# to cover the root window and the classic Text widgets.
LIGHT_PALETTE = {
    "bg":            "#f0f0f0",
    "fg":            "#000000",
    "entry_bg":      "#ffffff",
    "select_bg":     "#0a64c8",
    "select_fg":     "#ffffff",
    "button_bg":     "#f0f0f0",
    "button_active": "#e0e0e0",
    "disabled":      "#a0a0a0",
    "trough":        "#e0e0e0",
}

# =============================================================================
# SECTION: Main application window
# =============================================================================

class GamGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME + " " + APP_VERSION + " - GAM7 Graphical Front-End")
        self.geometry("1100x720")
        self.minsize(900, 600)

        # ---- settings (gam path persisted in gamgui.ini) --------------------
        self.config_parser = configparser.ConfigParser()
        self.config_parser.read(INI_PATH)
        saved = self.config_parser.get("gamgui", "gam_path", fallback="")
        self.gam_path = find_gam(saved)

        # ---- theme (light default; dark remembered in gamgui.ini) -----------
        # A single ttk.Style drives every ttk widget. Remember the platform
        # default theme so light mode can restore the native look exactly.
        self.style = ttk.Style(self)
        self._default_theme = self.style.theme_use()
        self.dark_mode = self.config_parser.getboolean(
            "gamgui", "dark_mode", fallback=False)

        # ---- automatic update check (remembered in gamgui.ini) --------------
        # When on, GAMGUI quietly asks GitHub once at startup whether a newer
        # release exists and, if so, offers to update itself. It NEVER updates
        # without the user saying yes, and any network failure is ignored so an
        # offline machine still starts normally.
        self.check_updates = self.config_parser.getboolean(
            "gamgui", "check_updates", fallback=True)
        self._update_in_progress = False     # guards against double-launching

        # ---- session log ----------------------------------------------------
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        self.log_path = os.path.join(LOG_DIR, "GAMGUI_" + stamp + ".log")

        self.output_queue = queue.Queue()   # worker thread -> UI text box
        self.running_proc = None            # currently running gam process
        self.workflow_cancel = False        # set by Stop during the workflow
        self.field_vars = []                # (key, tk variable) of current form
        self.field_maps = {}                # key -> valuemap (friendly->gam value)
        self.current_task = None
        self.current_key = None             # (category, task name) of current_task
        self.domain_section = ""            # "" = run against the saved default
        self._preview_after_id = None       # pending live-preview refresh

        # ---- text size (remembered in gamgui.ini) ---------------------------
        # An index into TEXT_SCALES. Out-of-range or bad values fall back to
        # the normal size so a hand-edited .ini can never break the window.
        try:
            idx = self.config_parser.getint("gamgui", "text_size",
                                            fallback=TEXT_SCALE_DEFAULT)
        except ValueError:
            idx = TEXT_SCALE_DEFAULT
        self.text_scale_index = (idx if 0 <= idx < len(TEXT_SCALES)
                                 else TEXT_SCALE_DEFAULT)
        self._base_font_sizes = {}          # named font -> its original size

        # ---- Favorites and Recent tasks (gamgui_tasklists.json) -------------
        # Each entry is [category, task name]. Names (not positions) are
        # stored so the lists survive catalog updates that reorder tasks.
        self.favorites, self.recent = self._load_tasklists()

        self._build_layout()
        self._populate_tree()
        self._apply_theme()                  # paint light or dark on first show
        self._apply_text_scale()             # apply the remembered text size
        self.after(100, self._poll_output)
        self._log("Session start. gam path: " + (self.gam_path or "NOT FOUND"))
        if not self.gam_path:
            self._append_output("WARNING: gam.exe was not found. Use "
                                "Settings > Locate gam.exe.\n")

        # Kick off the silent startup update check a moment after the window is
        # up, so it never delays the app appearing. Runs in a background thread.
        if self.check_updates:
            self.after(1500, lambda: self._check_updates_async(auto=True))

    # ---- layout -------------------------------------------------------------
    def _build_layout(self):
        # Menu bar: a "View" menu with a Dark mode toggle. Kept minimal so it
        # does not crowd the window; the checkbutton reflects the saved state.
        menubar = tk.Menu(self)
        view_menu = tk.Menu(menubar, tearoff=0)
        self.dark_var = tk.BooleanVar(value=self.dark_mode)
        view_menu.add_checkbutton(label="Dark mode", variable=self.dark_var,
                                  command=self._toggle_dark)
        # Text size: bigger text for projectors / demos and high-DPI screens.
        # The accelerator text is only a label; the real key bindings are
        # set just below with bind_all so they work from any widget.
        view_menu.add_separator()
        view_menu.add_command(label="Larger text", accelerator="Ctrl++",
                              command=lambda: self._change_text_scale(+1))
        view_menu.add_command(label="Smaller text", accelerator="Ctrl+-",
                              command=lambda: self._change_text_scale(-1))
        view_menu.add_command(label="Normal text size", accelerator="Ctrl+0",
                              command=lambda: self._change_text_scale(0))
        menubar.add_cascade(label="View", menu=view_menu)
        # Ctrl+= is the unshifted "+" key on US keyboards; the keypad keys are
        # bound too. Returning "break" stops the key reaching the focused box.
        for seq, step in (("<Control-plus>", 1), ("<Control-equal>", 1),
                          ("<Control-KP_Add>", 1), ("<Control-minus>", -1),
                          ("<Control-KP_Subtract>", -1),
                          # "Key-0": a bare digit in a Tk event pattern means a
                          # MOUSE button, so the 0 key must be spelled Key-0.
                          ("<Control-Key-0>", 0), ("<Control-KP_0>", 0)):
            self.bind_all(seq, lambda _e, s=step: (self._change_text_scale(s),
                                                   "break")[1])

        # "Help" menu: manual update check, a toggle for the startup check, and
        # an About box. The checkbutton reflects/stores the saved preference.
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Check for updates now...",
                              command=lambda: self._check_updates_async(auto=False))
        self.check_updates_var = tk.BooleanVar(value=self.check_updates)
        help_menu.add_checkbutton(label="Check for updates at startup",
                                  variable=self.check_updates_var,
                                  command=self._toggle_check_updates)
        help_menu.add_separator()
        help_menu.add_command(label="About " + APP_NAME, command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

        # Top bar: gam path display + settings buttons.
        top = ttk.Frame(self, padding=4)
        top.pack(side="top", fill="x")
        self.path_label = ttk.Label(top, text="gam: " + (self.gam_path or "(not found)"))
        self.path_label.pack(side="left")
        ttk.Button(top, text="Locate gam.exe...", command=self._locate_gam).pack(side="right")

        # Domain selector: multi-tenant admins (e.g. MSPs) pick which gam.cfg
        # section a command runs against. "(default)" injects nothing and runs
        # against the saved default. A section is applied per-command via a
        # leading "select <section>" that GAM treats as a one-shot (verified
        # non-persistent), so the user's saved default is never disturbed.
        ttk.Button(top, text="+", width=2, command=self._add_domain).pack(side="right", padx=(0, 4))
        self.domain_var = tk.StringVar(value="(default)")
        self.domain_combo = ttk.Combobox(top, textvariable=self.domain_var,
                                          state="readonly", width=18,
                                          values=self._domain_choices())
        self.domain_combo.pack(side="right")
        self.domain_combo.bind("<<ComboboxSelected>>", self._on_domain_change)
        ttk.Label(top, text="Domain:").pack(side="right", padx=(8, 2))

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)

        # Left: a search box above the category/task tree. The search filters
        # the tree live so a large command catalog stays navigable.
        left = ttk.Frame(main)
        main.add(left, weight=1)
        search_row = ttk.Frame(left, padding=(0, 0, 0, 4))
        search_row.pack(side="top", fill="x")
        ttk.Label(search_row, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True)
        # Enter opens the first match; Esc clears the search.
        self.search_entry.bind("<Return>", self._search_enter)
        self.search_entry.bind("<Escape>", lambda _e: self.search_var.set(""))
        # Rebuild the (filtered) tree whenever the search text changes.
        self.search_var.trace_add("write", lambda *_: self._populate_tree())
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.pack(side="top", fill="both", expand=True)
        # Right-click a task to add it to (or remove it from) Favorites.
        # Button-3 is the right button on Windows/Linux; macOS Tk reports the
        # right button as Button-2, so both are bound.
        self.tree_menu = tk.Menu(self, tearoff=0)
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<Button-2>", self._on_tree_right_click)

        # Right: form on top, command preview, output below.
        right = ttk.Frame(main, padding=6)
        main.add(right, weight=3)

        self.desc_label = ttk.Label(right, text="Select a task on the left.",
                                    wraplength=700, justify="left")
        self.desc_label.pack(anchor="w", fill="x")
        # Re-wrap the description to the panel's real width whenever it is
        # resized (or the text size changes), instead of a fixed 700 pixels.
        self.desc_label.bind(
            "<Configure>",
            lambda e: self.desc_label.config(wraplength=max(200, e.width - 8)))

        self.form_frame = ttk.Frame(right)
        self.form_frame.pack(fill="x", pady=6)

        preview_bar = ttk.Frame(right)
        preview_bar.pack(fill="x")
        ttk.Label(preview_bar, text="Command preview (editable):").pack(side="left")
        ttk.Button(preview_bar, text="Build", command=self._preview).pack(side="right")
        ttk.Button(preview_bar, text="Copy", command=self._copy).pack(side="right")
        # Saves the command as a .bat (Windows) / .sh (macOS, Linux) script
        # with logging - to double-click later or schedule (Task Scheduler).
        ttk.Button(preview_bar, text="Save as script...",
                   command=self._save_script).pack(side="right", padx=(0, 4))
        # "GAM docs" opens the GAM wiki page for the selected task in the web
        # browser (the right page is chosen by gam_catalog.task_doc_url).
        ttk.Button(preview_bar, text="GAM docs",
                   command=self._open_task_docs).pack(side="right", padx=(0, 4))
        # Adds / removes the selected task from Favorites. Its label flips
        # between "+ Favorite" and "- Favorite" (see _refresh_fav_button).
        self.fav_button = ttk.Button(preview_bar, text="+ Favorite",
                                     command=self._toggle_favorite_current)
        self.fav_button.pack(side="right", padx=(0, 4))

        self.preview_box = tk.Text(right, height=6, wrap="word")
        self.preview_box.pack(fill="x", pady=4)

        run_bar = ttk.Frame(right)
        run_bar.pack(fill="x")
        self.run_button = ttk.Button(run_bar, text="Run", command=self._run)
        self.run_button.pack(side="left")
        ttk.Button(run_bar, text="Stop", command=self._stop).pack(side="left", padx=4)
        # Turns the open task into a bulk job: pick a CSV, map fields to its
        # columns, and GAM runs the task once per row (gam csv ... gam ...).
        ttk.Button(run_bar, text="Run for each CSV row...",
                   command=self._open_bulk_dialog).pack(side="left", padx=4)
        ttk.Button(run_bar, text="Clear output", command=lambda:
                   self.output_box.delete("1.0", "end")).pack(side="right")
        ttk.Button(run_bar, text="Save output...",
                   command=self._save_output).pack(side="right", padx=(0, 4))
        # Keyboard shortcuts (work from anywhere in the window):
        #   Ctrl+F      jump to the task search box
        #   Ctrl+Enter  Run (exactly like the Run button - same confirmations)
        #   F1          open the GAM docs for the open task
        self.bind_all("<Control-f>", self._focus_search)
        self.bind_all("<Control-F>", self._focus_search)
        self.bind_all("<Control-Return>", lambda _e: (self._run(), "break")[1])
        self.bind_all("<F1>", lambda _e: (self._open_task_docs(), "break")[1])

        self.output_box = scrolledtext.ScrolledText(right, height=18, wrap="word",
                                                    state="normal")
        self.output_box.pack(fill="both", expand=True, pady=4)

        # Custom command entry lives as a synthetic tree item (see below).

    def _populate_tree(self):
        # Rebuild the whole tree from scratch (search filters it live). The
        # task's ORIGINAL index within its category is preserved in the item
        # values so _on_select still resolves TASKS[category][index] correctly.
        for item in self.tree.get_children():
            self.tree.delete(item)
        needle = ""
        if getattr(self, "search_var", None) is not None:
            needle = self.search_var.get().strip().lower()
        # Favorites and Recent sit at the very top (see _insert_special_nodes).
        self._insert_special_nodes(needle)
        for category, tasks in TASKS.items():
            matches = [(index, task) for index, task in enumerate(tasks)
                       if not needle or self._task_matches(needle, category, task)]
            if not matches:
                continue                    # hide categories with no match
            parent = self.tree.insert("", "end", text=category,
                                      open=bool(needle))
            for index, task in matches:
                self.tree.insert(parent, "end", text=task["name"],
                                 values=(category, index))
        # The raw console is always available when not filtering.
        if not needle:
            self.tree.insert("", "end", text="Run ANY GAM command (advanced)",
                             values=("__custom__", 0))

    def _insert_special_nodes(self, needle=""):
        # Inserts the "Favorites" and "Recent" groups at the TOP of the tree.
        # Hidden while searching so search results are not shown twice. Each
        # entry shows "Category > Task" so e.g. "Create user" is unambiguous.
        # Entries whose task no longer exists (renamed in a newer version) are
        # skipped quietly. The groups are tagged "special" so they can be
        # refreshed later without rebuilding (and deselecting) the whole tree.
        if needle:
            return
        position = 0
        for title, entries in (("Favorites", self.favorites),
                               ("Recent", self.recent)):
            found = [(cat, name, self._task_index(cat, name))
                     for cat, name in entries]
            found = [f for f in found if f[2] is not None]
            if not found:
                continue
            parent = self.tree.insert("", position, text=title, open=True,
                                      tags=("special",))
            position += 1
            for cat, name, index in found:
                self.tree.insert(parent, "end", text=cat + " > " + name,
                                 values=(cat, index), tags=("special",))

    @staticmethod
    def _task_matches(needle, category, task):
        # Search rule: every WORD typed must appear somewhere in the task's
        # name, category, description, or GAM command template - so
        # "vacation", "cigroup", or "reset password" all find the right
        # tasks even when the exact words are not in the task's name.
        haystack = " ".join((task["name"], category, task.get("desc", ""),
                             task.get("template", "") or "")).lower()
        return all(word in haystack for word in needle.split())

    def _search_enter(self, _event=None):
        # Enter in the search box opens the FIRST matching task.
        for top in self.tree.get_children(""):
            children = self.tree.get_children(top)
            if children:
                self.tree.selection_set(children[0])
                self.tree.see(children[0])
                self.tree.focus(children[0])
                return "break"
        return "break"

    def _focus_search(self, _event=None):
        # Ctrl+F: jump to the search box with its text selected.
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")
        return "break"

    def _save_output(self):
        # Saves everything in the output pane to a text file the user picks.
        # The output can contain names, email addresses, or a generated
        # password GAM printed - the file is saved exactly as shown, so store
        # it with care (see README "Safety and security").
        text = self.output_box.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showinfo(APP_NAME, "The output pane is empty.")
            return
        path = filedialog.asksaveasfilename(
            title="Save output as", defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            self._log("Output saved to " + path)
        except OSError as exc:
            messagebox.showerror(APP_NAME, "Could not save the output:\n" + str(exc))

    def _save_script(self):
        # Writes the command in the preview to a script file: a .bat on
        # Windows (house-style header, Logs\ file with MM-DD-YYYY timestamps,
        # GAM's exit code, CRLF line endings) or a .sh on macOS/Linux. The
        # script runs EXACTLY the argument list GAMGUI would run - the
        # escaping is proven against the real cmd.exe in
        # tests/test_script_export.py.
        task = self.current_task
        if task and (task.get("workflow") or task.get("audit")
                     or task.get("external") or task.get("interactive")):
            messagebox.showinfo(APP_NAME, "This is a multi-step workflow run "
                                "by GAMGUI itself, so it cannot be saved as a "
                                "single script.")
            return
        command_text = self.preview_box.get("1.0", "end").strip()
        if not command_text or command_text.startswith("("):
            messagebox.showerror(APP_NAME, "Build a command first (fill in the "
                                 "required boxes).")
            return
        if command_text == getattr(self, "generated_display", None):
            argv = list(self.generated_argv)
        else:
            stripped = command_text[4:] if command_text.lower().startswith("gam ") \
                else command_text
            argv = win_split(stripped)
        argv = self._domain_prefix() + argv
        if not argv:
            return
        if not self.gam_path:
            messagebox.showerror(APP_NAME, "gam.exe not found. Use Locate gam.exe.")
            return
        warnings = []
        if contains_password(argv):
            warnings.append("This command contains a PASSWORD. The script would "
                            "store it in plain text - anyone who can read the "
                            "file can see it.")
        if task and task.get("destructive"):
            warnings.append("This task is marked DESTRUCTIVE. A script runs "
                            "WITHOUT asking for confirmation.")
        if warnings and not messagebox.askyesno(
                APP_NAME + " - Save as script",
                "\n\n".join(warnings) + "\n\nSave the script anyway?",
                default="no"):
            return
        windows = os.name == "nt"
        ext = ".bat" if windows else ".sh"
        base = re.sub(r"[^A-Za-z0-9]+", "-", (task or {}).get(
            "name", "gam-command")).strip("-")[:60] or "gam-command"
        path = filedialog.asksaveasfilename(
            title="Save as script", defaultextension=ext,
            initialfile=base + ext,
            filetypes=[("Batch files" if windows else "Shell scripts", "*" + ext),
                       ("All files", "*.*")])
        if not path:
            return
        name = os.path.splitext(os.path.basename(path))[0]
        title = (task or {}).get("name", "Custom GAM command")
        today = datetime.datetime.now().strftime("%m-%d-%Y")
        try:
            maker = make_bat_script if windows else make_sh_script
            text = maker(argv, self.gam_path, name, title, APP_VERSION, today)
            with open(path, "w", encoding="ascii", errors="replace",
                      newline="") as handle:
                handle.write(text)
            if not windows:
                os.chmod(path, 0o755)         # make the .sh executable
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_NAME, "Could not save the script:\n" + str(exc))
            return
        self._log("Saved script " + path + " for: " + title)
        messagebox.showinfo(
            APP_NAME, "Saved " + path + "\n\nRun it by double-clicking it, or "
            "schedule it (Windows Task Scheduler / cron). Its output and exit "
            "code are logged in a Logs folder next to the script.")

    def _refresh_special_nodes(self):
        # Re-draws only the Favorites / Recent groups. The rest of the tree -
        # and the task currently open in the form - are left alone, so adding
        # a favorite or running a task never wipes what the user typed.
        for iid in self.tree.get_children(""):
            if self.tree.tag_has("special", iid):
                self.tree.delete(iid)
        self._insert_special_nodes(self.search_var.get().strip().lower())

    def _task_index(self, category, name):
        # Position of a task (by name) within its category, or None if that
        # category or task no longer exists.
        for index, task in enumerate(TASKS.get(category, [])):
            if task["name"] == name:
                return index
        return None

    # ---- Favorites / Recent persistence -------------------------------------
    def _load_tasklists(self):
        # Reads gamgui_tasklists.json. Anything missing or malformed simply
        # yields empty lists - a damaged file must never stop GAMGUI starting.
        def clean(value):
            out = []
            if isinstance(value, list):
                for item in value:
                    if (isinstance(item, list) and len(item) == 2
                            and all(isinstance(x, str) for x in item)
                            and item not in out):
                        out.append(item)
            return out
        try:
            with open(TASKLISTS_PATH, encoding="utf-8") as handle:
                data = json.load(handle)
            return clean(data.get("favorites")), clean(data.get("recent"))[:RECENT_MAX]
        except Exception:
            return [], []

    def _save_tasklists(self):
        # Writes Favorites and Recent back to disk. A failure (read-only
        # folder, disk full) is logged but never interrupts the user.
        try:
            with open(TASKLISTS_PATH, "w", encoding="utf-8") as handle:
                json.dump({"favorites": self.favorites, "recent": self.recent},
                          handle, indent=1)
        except Exception as exc:
            self._log("Could not save Favorites/Recent: " + str(exc))

    def _remember_recent(self):
        # Moves the current task to the front of the Recent list (keeping the
        # newest RECENT_MAX), saves, and refreshes that part of the tree.
        if not self.current_key:
            return
        entry = list(self.current_key)
        self.recent = [entry] + [e for e in self.recent if e != entry]
        self.recent = self.recent[:RECENT_MAX]
        self._save_tasklists()
        self._refresh_special_nodes()

    def _is_favorite(self, key):
        return key is not None and list(key) in self.favorites

    def _toggle_favorite(self, key):
        # Adds the task to Favorites, or removes it if it is already there.
        if key is None:
            return
        entry = list(key)
        if entry in self.favorites:
            self.favorites.remove(entry)
        else:
            self.favorites.append(entry)
        self._save_tasklists()
        self._refresh_special_nodes()
        self._refresh_fav_button()

    def _toggle_favorite_current(self):
        # The "+ Favorite / - Favorite" button acts on the open task.
        if self.current_key is None:
            messagebox.showinfo(APP_NAME, "Select a task first.")
            return
        self._toggle_favorite(self.current_key)

    def _refresh_fav_button(self):
        # Keeps the button's label in step with the open task's state.
        if getattr(self, "fav_button", None) is None:
            return
        self.fav_button.config(
            text="- Favorite" if self._is_favorite(self.current_key)
            else "+ Favorite")

    def _on_tree_right_click(self, event):
        # Right-click menu for the task tree: add/remove a favorite and open
        # the task's GAM docs; on the Recent header, clear the Recent list.
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        menu = self.tree_menu
        menu.delete(0, "end")
        vals = self.tree.item(iid, "values")
        if not vals:
            if (self.tree.item(iid, "text") == "Recent"
                    and self.tree.tag_has("special", iid)):
                menu.add_command(label="Clear the Recent list",
                                 command=self._clear_recent)
            else:
                return                    # a category header: nothing to offer
        elif vals[0] == "__custom__":
            return
        else:
            category, index = vals[0], int(vals[1])
            task = TASKS[category][index]
            key = (category, task["name"])
            menu.add_command(
                label=("Remove from Favorites" if self._is_favorite(key)
                       else "Add to Favorites"),
                command=lambda k=key: self._toggle_favorite(k))
            menu.add_command(
                label="Open GAM docs for this task",
                command=lambda c=category, t=task: self._open_docs_url(
                    task_doc_url(c, t)))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _clear_recent(self):
        self.recent = []
        self._save_tasklists()
        self._refresh_special_nodes()

    # ---- CSV bulk runs ("Run for each CSV row...") ---------------------------
    def _open_bulk_dialog(self):
        # Lets ANY ordinary task run once per row of a CSV file. The user
        # picks the CSV, then chooses, field by field, whether each value
        # comes from a CSV column or from the form. The finished command (gam
        # csv <file> gam <task>) is put in the preview; the user still clicks
        # Run, so the normal destructive confirmation still applies.
        task = self.current_task
        if task is None or task.get("workflow") or task.get("audit") \
                or task.get("external") or task.get("interactive"):
            messagebox.showinfo(
                APP_NAME, "Select an ordinary task first. Guided workflows, "
                "the mailbox audit, and the Run ANY GAM command console cannot "
                "be run per CSV row.")
            return
        if task["template"].lstrip().startswith("csv "):
            messagebox.showinfo(APP_NAME, "This task already reads a CSV file "
                                "itself - just fill in its form.")
            return
        modes = bulk_field_modes(task)
        if not any(modes.values()):
            messagebox.showinfo(
                APP_NAME, "None of this task's boxes can change from row to "
                "row (its values are dropdowns or are translated by GAMGUI), so "
                "it cannot run per CSV row.")
            return
        path = filedialog.askopenfilename(
            title="Select the CSV file to run this task for each row",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        # Read ONLY the header row - the data rows are read by GAM itself.
        # utf-8-sig drops the byte-order mark Excel adds to "CSV UTF-8" files.
        try:
            with open(path, newline="", encoding="utf-8-sig") as handle:
                header = next(csv.reader(handle), [])
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Could not read the CSV file:\n"
                                 + str(exc))
            return
        columns = [col.strip() for col in header if col and col.strip()]
        if not columns:
            messagebox.showerror(APP_NAME, "The CSV file has no header row. "
                                 "The first row must hold the column names.")
            return
        self._build_bulk_dialog(task, modes, path, columns)

    def _build_bulk_dialog(self, task, modes, path, columns):
        form_choice = "(use the value in the form)"
        palette = DARK_PALETTE if self.dark_mode else LIGHT_PALETTE
        dlg = tk.Toplevel(self)
        dlg.title(APP_NAME + " - Run for each CSV row")
        dlg.configure(bg=palette["bg"])
        dlg.transient(self)
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, wraplength=620, justify="left", text=(
            "Task: " + task["name"] + "\nCSV: " + path + "\nColumns: "
            + ", ".join(columns) + "\n\nFor each box, choose the CSV column "
            "that holds its value (it changes every row), or leave it on the "
            "form value (the same for every row). Boxes shown as 'form value "
            "only' cannot change per row.")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        def norm(text):
            return re.sub(r"[^a-z0-9]", "", text.lower())

        combos = {}
        row = 1
        for field in task["fields"]:
            key = field["key"]
            if key in ("todrive", "csvout"):
                continue                      # output is set in the main form
            ttk.Label(body, text=field["label"]).grid(row=row, column=0,
                                                      sticky="w", pady=2)
            if modes.get(key):
                combo = ttk.Combobox(body, state="readonly", width=34,
                                     values=[form_choice] + columns)
                # Pre-select a column whose name matches the field, e.g.
                # "Email" for an email box - the user can change it.
                guess = form_choice
                for col in columns:
                    if norm(col) in (norm(key), norm(field["label"])) or (
                            len(key) >= 4 and norm(key) in norm(col)):
                        guess = col
                        break
                combo.set(guess)
                combo.grid(row=row, column=1, sticky="we", pady=2, padx=6)
                combos[key] = combo
            else:
                ttk.Label(body, text="(form value only)").grid(
                    row=row, column=1, sticky="w", pady=2, padx=6)
            row += 1
        ttk.Label(body, text="Test run: only the first N rows (optional)").grid(
            row=row, column=0, sticky="w", pady=(8, 2))
        rows_var = tk.StringVar()
        ttk.Entry(body, textvariable=rows_var, width=8).grid(
            row=row, column=1, sticky="w", pady=(8, 2), padx=6)
        row += 1

        def build():
            mapping = {k: c.get() for k, c in combos.items()
                       if c.get() and c.get() != form_choice}
            display, argv, err = build_bulk_command(
                task, self._collect_values(), path, mapping,
                maxrows=rows_var.get(), domain_prefix=self._domain_prefix())
            if err:
                messagebox.showerror(APP_NAME, err, parent=dlg)
                return
            # Show the bulk command as the "generated" command so Run uses
            # this exact argument list (no re-parsing of the text).
            self.generated_display = "gam " + display
            self.generated_argv = argv
            self.preview_box.delete("1.0", "end")
            self.preview_box.insert("1.0", self.generated_display)
            self._append_output(
                "\n[Bulk command built: this task will run once per CSV row"
                + (" (first " + rows_var.get().strip() + " rows only)"
                   if rows_var.get().strip() else "")
                + ". Click Run. Changing a box in the form rebuilds the "
                "single-run command.]\n")
            dlg.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Build command", command=build).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=dlg.destroy).pack(
            side="left", padx=(6, 0))
        body.columnconfigure(1, weight=1)
        dlg.grab_set()                        # modal: finish or cancel first

    # ---- GAM documentation --------------------------------------------------
    def _open_task_docs(self):
        # Opens the GAM wiki page for the open task, or the wiki home page
        # when no task (or the "Run ANY GAM command" console) is selected.
        if self.current_key and self.current_task:
            url = task_doc_url(self.current_key[0], self.current_task)
        else:
            url = "https://github.com/GAM-team/GAM/wiki"
        self._open_docs_url(url)

    def _open_docs_url(self, url):
        # Opens a URL in the default browser. The URL always comes from the
        # built-in catalog (never from user input), so nothing untrusted is
        # ever opened.
        self._log("Open docs: " + url)
        try:
            webbrowser.open(url)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Could not open the browser:\n"
                                 + str(exc) + "\n\n" + url)

    # ---- text size -----------------------------------------------------------
    def _change_text_scale(self, step):
        # step +1 = larger, -1 = smaller, 0 = back to normal. Remembered in
        # gamgui.ini so the next launch opens at the same size.
        if step == 0:
            new = TEXT_SCALE_DEFAULT
        else:
            new = min(max(self.text_scale_index + step, 0), len(TEXT_SCALES) - 1)
        if new == self.text_scale_index and step != 0:
            return                            # already at the smallest/largest
        self.text_scale_index = new
        self._apply_text_scale()
        try:
            if not self.config_parser.has_section("gamgui"):
                self.config_parser.add_section("gamgui")
            self.config_parser.set("gamgui", "text_size", str(new))
            with open(INI_PATH, "w", encoding="utf-8") as handle:
                self.config_parser.write(handle)
        except Exception:
            pass                              # a settings-save failure is not fatal

    def _apply_text_scale(self):
        # Scales Tk's NAMED fonts, which every widget uses unless told
        # otherwise: TkDefaultFont (labels, buttons, tree), TkTextFont
        # (entries), TkFixedFont (command preview and output), and the rest.
        # Each font's ORIGINAL size is remembered the first time, so repeated
        # changes never drift. Tk sizes can be negative (meaning pixels
        # instead of points); the sign is kept.
        import tkinter.font as tkfont         # imported here: gam_web stubs tkinter
        factor = TEXT_SCALES[self.text_scale_index]
        for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont",
                     "TkMenuFont", "TkHeadingFont", "TkCaptionFont",
                     "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            try:
                font = tkfont.nametofont(name)
            except tk.TclError:
                continue                      # this font does not exist here
            if name not in self._base_font_sizes:
                self._base_font_sizes[name] = int(font.cget("size")) or 9
            base = self._base_font_sizes[name]
            size = max(1, int(round(abs(base) * factor)))
            font.configure(size=size if base > 0 else -size)
        self._apply_rowheight()

    def _apply_rowheight(self):
        # The task tree does not grow its rows with the font by itself, so
        # set the row height from the current font's line spacing (+ padding).
        try:
            import tkinter.font as tkfont
            line = tkfont.nametofont("TkDefaultFont").metrics("linespace")
            self.style.configure("Treeview", rowheight=line + 6)
        except Exception:
            pass

    # ---- task selection and form building -----------------------------------
    def _on_select(self, _event):
        item = self.tree.selection()
        if not item:
            return
        vals = self.tree.item(item[0], "values")
        if not vals:                      # category header clicked
            return
        if vals[0] == "__custom__":
            self.current_key = None
            self._show_custom()
            self._refresh_fav_button()
            return
        self.current_task = TASKS[vals[0]][int(vals[1])]
        self.current_key = (vals[0], self.current_task["name"])
        self._show_form(self.current_task)
        self._refresh_fav_button()

    def _clear_form(self):
        # Cancel a pending live-preview refresh from the previous form so it
        # cannot fire against the new, half-built one.
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id = None
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.field_vars = []
        self.field_maps = {}

    def _schedule_preview(self, *_args):
        # Live preview: called on every keystroke / dropdown change in the
        # form. Waits 200 ms after the LAST change before rebuilding the
        # command, so typing stays smooth instead of rebuilding per letter.
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
        self._preview_after_id = self.after(200, self._run_scheduled_preview)

    def _run_scheduled_preview(self):
        self._preview_after_id = None
        self._preview()

    def _show_form(self, task):
        self._clear_form()
        desc = task["name"] + ": " + task["desc"]
        # Tasks that take a local date/time (the {zulu:...} token, e.g. a
        # temporary admin role expiration) name this computer's time zone so
        # it is clear what "your local time" means before it becomes UTC.
        # The zone NAME is shown (not today's offset) because the conversion
        # uses the offset in effect ON THE DATE ENTERED - e.g. a November date
        # after the daylight-saving change converts at the standard offset.
        if uses_local_time(task):
            zone = datetime.datetime.now().astimezone().tzname()
            desc += ("  [Times are in this computer's time zone (" + zone
                     + " right now); daylight saving time is applied for the "
                     "date you enter.]")
        self.desc_label.config(text=desc)
        for row, field in enumerate(task["fields"]):
            label = field["label"] + (" *" if field["required"] else "")
            ttk.Label(self.form_frame, text=label).grid(row=row, column=0,
                                                        sticky="w", pady=2)
            var = tk.StringVar(value=field["default"])
            # A valuemap makes the dropdown show friendly names; plain choices
            # show their values directly.
            vmap = field.get("valuemap")
            choices = list(vmap.keys()) if vmap else field["choices"]
            if field.get("filepicker"):
                # "save" opens a Save-As dialog (for a CSV we are WRITING);
                # any other truthy value opens an Open dialog (a file we READ).
                mode = "save" if field.get("filepicker") == "save" else "open"
                widget = ttk.Frame(self.form_frame)
                ttk.Entry(widget, textvariable=var, width=48).pack(
                    side="left", fill="x", expand=True)
                # Only fields that ask for a CSV get the CSV-first file
                # filter; others (.eml, .pem, .p12, images, JSON) default to
                # "All files" so the right file is visible straight away.
                is_csv = "csv" in field["label"].lower()
                ttk.Button(widget, text="Browse...",
                           command=lambda v=var, m=mode, c=is_csv:
                           self._browse_file(v, m, c)).pack(
                    side="left", padx=(4, 0))
            elif choices is not None:
                widget = ttk.Combobox(self.form_frame, textvariable=var,
                                      values=choices, state="readonly", width=40)
                if choices:
                    var.set(choices[0] if field["required"] else field["default"])
            else:
                widget = ttk.Entry(self.form_frame, textvariable=var, width=60)
            widget.grid(row=row, column=1, sticky="we", pady=2, padx=6)
            if vmap:
                self.field_maps[field["key"]] = vmap
            self.field_vars.append((field["key"], var))
            # Live preview: rebuild the command shortly after this field
            # changes (typing, a dropdown pick, or a Browse... selection).
            # Added AFTER the default is set above so building the form does
            # not queue a pointless refresh for every field.
            var.trace_add("write", self._schedule_preview)
        self.form_frame.columnconfigure(1, weight=1)
        self._preview()

    def _show_custom(self):
        self._clear_form()
        self.current_task = None
        self.desc_label.config(
            text="Run ANY GAM command: type any gam command below (without the "
                 "leading 'gam') and press Run. The selected Domain applies to "
                 "it too. Full syntax reference: "
                 "https://github.com/GAM-team/GAM/wiki  Note: commands run "
                 "without a shell, so pipes (|) and > redirection are not "
                 "available - use GAM's own 'redirect csv ./file.csv' or "
                 "'todrive' instead.")
        self.preview_box.delete("1.0", "end")

    # ---- preview / copy -----------------------------------------------------
    def _browse_file(self, var, mode="open", csv_file=True):
        # Opens a file picker for a filepicker field and stores the chosen path.
        # mode "save" is used for a CSV we are about to WRITE (so it offers a
        # filename and warns before overwriting); "open" picks an existing file.
        # csv_file=False (any non-CSV field) lists "All files" first and uses a
        # neutral title, e.g. for .eml, .pem, .p12, image, or JSON files.
        types = [("CSV files", "*.csv"), ("All files", "*.*")]
        if mode == "save":
            path = filedialog.asksaveasfilename(
                title="Save results as CSV", defaultextension=".csv",
                filetypes=types)
        elif csv_file:
            path = filedialog.askopenfilename(
                title="Select CSV file", filetypes=types)
        else:
            path = filedialog.askopenfilename(
                title="Select file", filetypes=[("All files", "*.*")])
        if path:
            var.set(path)               # the live preview refreshes by itself
            self._preview()

    def _collect_values(self):
        # Translate any friendly dropdown selection back to the gam value.
        out = {}
        for key, var in self.field_vars:
            val = var.get()
            vmap = self.field_maps.get(key)
            if vmap and val in vmap:
                val = vmap[val]
            out[key] = val
        return out

    def _preview(self):
        if not self.current_task:
            return
        # The mailbox takeover audit previews the read-only checks it runs.
        if self.current_task.get("audit"):
            email = self._collect_values().get("email", "").strip()
            self.preview_box.delete("1.0", "end")
            if email:
                self.preview_box.insert(
                    "1.0", "READ-ONLY audit of " + email + ": show filters, "
                    "forwardingaddresses, sendas, delegates.")
            else:
                self.preview_box.insert("1.0", "(Missing required value: email)")
            return
        # Workflows preview a short description instead of one command.
        if self.current_task.get("workflow") == "archivecourses":
            self.preview_box.delete("1.0", "end")
            self.preview_box.insert("1.0", "Workflow: find all ACTIVE Classrooms "
                                    "-> confirm (type ARCHIVE) -> archive them all. "
                                    "Click Run.")
            return
        if self.current_task.get("workflow") in ("bulklicense_csv", "bulklicense_sheet"):
            v = self._collect_values()
            self.preview_box.delete("1.0", "end")
            act = "add" if v.get("action") == "add" else "remove"
            self.preview_box.insert("1.0",
                "Workflow: read Email/License rows -> translate names to SKUs "
                "-> confirm -> " + act + " each license via gam csv. Click Run.")
            return
        if self.current_task.get("workflow") == "transferdrive":
            v = self._collect_values()
            self.preview_box.delete("1.0", "end")
            if v.get("old", "").strip() and v.get("new", "").strip():
                folder = v.get("folder", "").strip()
                self.preview_box.insert("1.0",
                    "Workflow: check " + v["old"].strip() + "'s state -> enable "
                    "if suspended/archived -> transfer drive to " + v["new"].strip()
                    + (" (folder '" + folder + "')" if folder else "")
                    + " -> restore original state. Click Run.")
            else:
                self.preview_box.insert("1.0", "(Fill in old user and new user)")
            return
        if self.current_task.get("workflow") == "shareddrive":
            v = self._collect_values()
            self.preview_box.delete("1.0", "end")
            if v.get("old", "").strip() and v.get("new", "").strip() \
                    and v.get("drivename", "").strip() and v.get("admin", "").strip():
                self.preview_box.insert("1.0",
                    "Workflow: unsuspend " + v["old"].strip() + " -> create Shared "
                    "Drive '" + v["drivename"].strip() + "' -> move their My Drive into "
                    "it -> make " + v["new"].strip() + " manager -> clean up -> "
                    "re-suspend. Click Run.")
            else:
                self.preview_box.insert("1.0",
                    "(Fill in old user, new user, Shared Drive name, and admin)")
            return
        if self.current_task.get("workflow") == "targetedcleanup":
            v = self._collect_values()
            self.preview_box.delete("1.0", "end")
            q = v.get("query", "").strip()
            if not q:
                self.preview_box.insert("1.0", "(Enter a Gmail search query)")
                return
            thr = v.get("threads", "").strip()
            tp = ("config num_threads " + thr + " ") if thr else ""
            st = v.get("scopetype", "all") or "all"
            sv = v.get("scopeval", "").strip()
            scope = "all users" if st == "all" else (st + " " + sv)
            mx = v.get("max", "5000").strip() or "5000"
            self.preview_box.insert("1.0",
                "This runs two gam commands (search first, then delete only the "
                "matches):\n\n"
                "1) FIND (read-only):\ngam " + tp
                + "redirect csv <folder>\\MatchedMessages.csv " + scope
                + " print messages query " + quote_if_needed(q)
                + " headers from,to,subject,message-id,date\n\n"
                "2) After you type DELETE (matched mailboxes only):\ngam " + tp
                + "csv <folder>\\DeleteTargets.csv gam user ~user delete "
                "messages query rfc822msgid:~~msgid~~ max_to_delete " + mx
                + " doit")
            return
        if self.current_task.get("workflow") == "removeextaccess":
            v = self._collect_values()
            self.preview_box.delete("1.0", "end")
            ref = v.get("fileref", "").strip()
            if not ref:
                self.preview_box.insert("1.0", "(Enter a file name or ID)")
                return
            byid = v.get("findby") == "id"
            thr = v.get("threads", "").strip()
            tp = ("config num_threads " + thr + " ") if thr else ""
            st = v.get("scopetype", "user") or "user"
            sv = v.get("scopeval", "").strip()
            scope = "all users" if st == "all" else (st + " " + sv)
            finder = ("select id:" + ref if byid
                      else "query " + quote_if_needed("name = '" + ref + "'"))
            self.preview_box.insert("1.0",
                "This runs two gam commands (find who has it, then remove "
                "access):\n\n"
                "1) FIND (read-only):\ngam " + tp
                + "redirect csv <folder>\\WhoHasTheFile.csv " + scope
                + " print filelist " + finder
                + " showownedby others fields id,name,owners\n\n"
                "2) After you type DELETE (per matched user):\ngam " + tp
                + "csv <folder>\\RemoveTargets.csv gam user ~user delete "
                "drivefileacl id:~~fileid~~ ~user\n\n"
                "(view-only external shares cannot be removed this way - use "
                "the Admin Security Investigation Tool for those)")
            return
        if self.current_task.get("workflow") == "drivewipe":
            v = self._collect_values()
            self.preview_box.delete("1.0", "end")
            ref = v.get("fileref", "").strip()
            if not ref:
                self.preview_box.insert("1.0", "(Enter a file name or ID)")
                return
            byid = v.get("findby") == "id"
            thr = v.get("threads", "").strip()
            tp = ("config num_threads " + thr + " ") if thr else ""
            st = v.get("scopetype", "all") or "all"
            sv = v.get("scopeval", "").strip()
            scope = "all users" if st == "all" else (st + " " + sv)
            finder = ("select id:" + ref if byid
                      else "query " + quote_if_needed("name = '" + ref + "'")
                      + " excludetrashed")
            self.preview_box.insert("1.0",
                "This runs two gam commands (find owned copies, then delete):"
                "\n\n1) FIND (read-only):\ngam " + tp
                + "redirect csv <folder>\\MatchedFiles.csv " + scope
                + " print filelist " + finder
                + " showownedby me fields id,name,mimetype,owners\n\n"
                "2) After you type DELETE (each owned copy, permanent):\ngam "
                + tp + "csv <folder>\\DeleteTargets.csv gam user ~owner delete "
                "drivefile id:~~fileid~~ purge")
            return
        # The incident workflow previews the actual gam commands it will run.
        if self.current_task.get("workflow"):
            v = self._collect_values()
            sender = v.get("from", "").strip()
            subject = v.get("subject", "").strip()
            self.preview_box.delete("1.0", "end")
            if not (sender and subject):
                self.preview_box.insert(
                    "1.0", "(Missing required value: from/subject)")
                return
            stype = v.get("scopetype", "all").strip() or "all"
            sval = v.get("scopeval", "").strip()
            thr = v.get("threads", "").strip()
            days = v.get("days", "30").strip() or "30"
            mx = v.get("max", "5000").strip() or "5000"
            scope_txt = "all users" if stype == "all" else (stype + " " + sval)
            tp = ("config num_threads " + thr + " ") if thr else ""
            query = incident_query(sender, subject)
            self.preview_box.insert("1.0",
                "This workflow runs these gam commands in order:\n\n"
                "1) FIND (read-only):\ngam " + tp
                + "redirect csv <Incident folder>\\MatchedMessages.csv "
                + scope_txt + " print messages query " + quote_if_needed(query)
                + " headers from,to,subject,message-id,date\n\n"
                "2) After you type DELETE (matched mailboxes only):\ngam " + tp
                + "csv <folder>\\DeleteTargets.csv gam user ~user delete "
                "messages query rfc822msgid:~~msgid~~ max_to_delete " + mx
                + " doit\n\n"
                "3) Optional Drive sweep (searches ONLY the matched mailboxes) "
                "+ Gmail/Drive audit reports for the last " + days + " days.")
            return
        # External tasks preview the script path, not a gam command.
        if self.current_task.get("external"):
            path = self._collect_values().get("path", "").strip()
            self.preview_box.delete("1.0", "end")
            self.preview_box.insert("1.0", path if path
                                    else "(Missing required value: path)")
            return
        display, argv, error = build_command(self.current_task,
                                             self._collect_values())
        self.preview_box.delete("1.0", "end")
        if error:
            self.generated_display = None
            self.generated_argv = None
            self.preview_box.insert("1.0", "(" + error + ")")
        else:
            # Remember the generated form of this command. If the user runs
            # it unedited we use this exact argv (no re-parsing); if they
            # edit the preview we fall back to win_split() on their text.
            self.generated_display = "gam " + display
            self.generated_argv = argv
            self.preview_box.insert("1.0", self.generated_display)

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.preview_box.get("1.0", "end").strip())

    # ---- execution ----------------------------------------------------------
    def _run(self):
        if self.running_proc is not None:
            messagebox.showinfo(APP_NAME, "A command is already running.")
            return
        # External tasks (interactive scripts) open their own console
        # window and do not go through gam at all.
        if self.current_task and self.current_task.get("external"):
            self._remember_recent()
            self._run_external()
            return
        if not self.gam_path:
            messagebox.showerror(APP_NAME, "gam.exe not found. Use Locate gam.exe.")
            return
        # Interactive tasks (oauth create/update) need a browser and GAM's
        # scope menu, so they launch in their own console window.
        if self.current_task and self.current_task.get("interactive"):
            self._remember_recent()
            self._run_interactive()
            return
        # Workflows run their own multi-step code paths.
        if self.current_task and self.current_task.get("workflow"):
            self._remember_recent()
            wf = self.current_task.get("workflow")
            if wf == "shareddrive":
                self._run_move_to_shareddrive()
            elif wf == "transferdrive":
                self._run_transfer_drive()
            elif wf == "archivecourses":
                self._run_archive_courses()
            elif wf == "bulklicense_csv":
                self._run_bulk_license_csv()
            elif wf == "bulklicense_sheet":
                self._run_bulk_license_sheet()
            elif wf == "targetedcleanup":
                self._run_targeted_cleanup()
            elif wf == "drivewipe":
                self._run_drive_wipe()
            elif wf == "removeextaccess":
                self._run_remove_ext_access()
            else:
                self._run_incident_workflow()
            return
        # The mailbox takeover audit runs its own read-only sequence.
        if self.current_task and self.current_task.get("audit"):
            self._remember_recent()
            self._run_mailbox_audit()
            return
        # Rebuild from the form when a form task is active and the preview
        # still shows an error placeholder.
        command_text = self.preview_box.get("1.0", "end").strip()
        if command_text.startswith("("):
            self._preview()
            command_text = self.preview_box.get("1.0", "end").strip()
        if not command_text or command_text.startswith("("):
            messagebox.showerror(APP_NAME, "Fill in the required fields first.")
            return

        # Decide the argument list. Unedited form output uses the exact
        # argv built from the form. Edited previews and Custom commands
        # are split with Windows rules (win_split). Either way gam runs
        # WITHOUT a shell, so & | > < ^ in values are plain text.
        if command_text == getattr(self, "generated_display", None):
            argv = list(self.generated_argv)
        else:
            stripped = command_text
            if stripped.lower().startswith("gam "):
                stripped = stripped[4:]
            argv = win_split(stripped)
        if not argv:
            messagebox.showerror(APP_NAME, "Nothing to run.")
            return

        # Extra confirmation for destructive tasks - shows the exact command.
        if self.current_task and self.current_task["destructive"]:
            ok = messagebox.askyesno(
                APP_NAME + " - CONFIRM DESTRUCTIVE ACTION",
                "This action deletes data or changes device state:\n\n"
                + command_text + "\n\nAre you sure?")
            if not ok:
                return

        self._remember_recent()             # confirmed and about to run
        self._append_output("\n> " + command_text + "\n")
        self._log("RUN [" + (self.domain_section or "default") + "]: " + command_text)
        self._log("ARGV: " + repr(argv))
        self.run_button.config(state="disabled")

        def worker():
            # Runs in a background thread so the window stays responsive.
            try:
                # On macOS/Linux, start_new_session puts the shell AND gam
                # into their own process group so Stop can kill both at
                # once. Windows uses taskkill /T instead (see _stop).
                popen_kwargs = {}
                if os.name != "nt":
                    popen_kwargs["start_new_session"] = True
                # No shell: gam is the direct child and every argv element
                # reaches it exactly as typed. This is what makes & and
                # quotes inside subjects/queries safe.
                proc = subprocess.Popen(
                    [self.gam_path] + self._domain_prefix() + argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, # merge errors into one stream
                    text=True, encoding="utf-8", errors="replace",
                    **popen_kwargs)
                self.running_proc = proc
                for line in proc.stdout:
                    self.output_queue.put(line)
                proc.wait()
                self.output_queue.put("\n[exit code " + str(proc.returncode) + "]\n")
                self._log("EXIT: " + str(proc.returncode))
            except Exception as exc:
                self.output_queue.put("ERROR: " + str(exc) + "\n")
                self._log("ERROR: " + str(exc))
            finally:
                self.running_proc = None
                self.output_queue.put(None)   # sentinel: re-enable Run button

        threading.Thread(target=worker, daemon=True).start()

    def _stream_gam(self, argv, label):
        # Runs one gam command (argument list, no shell) from a WORKER
        # thread, streaming its output into the UI queue. Returns the exit
        # code, or -1 if the workflow was canceled. Used by the incident
        # workflow; the Stop button kills whichever step is running.
        if self.workflow_cancel:
            return -1
        self.output_queue.put("\n> gam " + " ".join(
            quote_if_needed(a) for a in argv) + "\n")
        self._log("WORKFLOW RUN: " + repr(argv))
        proc = subprocess.Popen([self.gam_path] + self._domain_prefix() + argv,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        self.running_proc = proc
        for line in proc.stdout:
            self.output_queue.put(line)
        proc.wait()
        self.running_proc = None
        self._log("WORKFLOW EXIT: " + str(proc.returncode))
        if self.workflow_cancel:
            return -1
        return proc.returncode

    def _capture_gam(self, argv):
        # Like _stream_gam but returns (returncode, full_output_text) so a
        # workflow can parse the result - e.g. read the new Shared Drive id
        # out of the "create teamdrive" output.
        if self.workflow_cancel:
            return -1, ""
        self.output_queue.put("\n> gam " + " ".join(
            quote_if_needed(a) for a in argv) + "\n")
        self._log("WORKFLOW RUN(capture): " + repr(argv))
        proc = subprocess.Popen([self.gam_path] + self._domain_prefix() + argv, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        self.running_proc = proc
        out = proc.stdout.read()
        proc.wait()
        self.running_proc = None
        self.output_queue.put(out)
        return proc.returncode, out

    def _user_state(self, user):
        # Reads a user's suspended/archived state (GAM cannot transfer Drive
        # files out of a suspended or archived account). Returns
        # (suspended, archived) as booleans, or None if the lookup failed.
        rc, out = self._capture_gam(["info", "user", user, "quick"])
        if rc != 0:
            return None
        suspended = bool(re.search(r"Account Suspended:\s*True", out))
        archived = bool(re.search(r"Is Archived:\s*True", out))
        return (suspended, archived)

    def _restore_state(self, user, changed_suspend, changed_archive):
        # Puts the account back exactly as it was. Runs even if the user hit
        # Stop, so we never leave an account enabled that started disabled.
        self.workflow_cancel = False
        if changed_suspend:
            self.output_queue.put("\n----- restoring suspended state -----\n")
            self._stream_gam(["update", "user", user, "suspended", "on"], "re-suspend")
        if changed_archive:
            self.output_queue.put("\n----- restoring archived state -----\n")
            self._stream_gam(["update", "user", user, "archived", "on"], "re-archive")

    def _run_transfer_drive(self):
        # State-aware Drive transfer: GAM cannot pull files from a suspended
        # or archived account, so temporarily enable it, transfer, then
        # restore the exact original state (active stays active).
        v = self._collect_values()
        old = v.get("old", "").strip(); new = v.get("new", "").strip()
        folder = v.get("folder", "").strip()
        if not (old and new):
            messagebox.showerror(APP_NAME, "Old user and new user are required.")
            return
        if not messagebox.askyesno(APP_NAME + " - CONFIRM",
                "Transfer ALL of " + old + "'s Drive files to " + new + "?\n\n"
                "If " + old + " is suspended or archived it will be temporarily "
                "enabled for the transfer, then set back to how it was."):
            return
        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            changed_suspend = False; changed_archive = False
            try:
                self.output_queue.put("\n===== TRANSFER DRIVE: " + old
                                      + " -> " + new + " =====\n")
                state = self._user_state(old)
                if state is None:
                    self.output_queue.put("Could not read " + old + "'s account "
                                          "state (does it exist?). Stopping.\n")
                    return
                was_suspended, was_archived = state
                self.output_queue.put("Original state: suspended=%s archived=%s\n"
                                      % (was_suspended, was_archived))
                # GAM cannot transfer from a disabled account - enable first.
                if was_archived:
                    self.output_queue.put("\n----- unarchiving (required to transfer) -----\n")
                    if self._stream_gam(["update", "user", old, "archived", "off"],
                                        "unarchive") == 0:
                        changed_archive = True
                    else:
                        self.output_queue.put("Could not unarchive - cannot "
                                              "transfer. Stopping.\n")
                        return
                if was_suspended:
                    self.output_queue.put("\n----- unsuspending (required to transfer) -----\n")
                    if self._stream_gam(["update", "user", old, "suspended", "off"],
                                        "unsuspend") == 0:
                        changed_suspend = True
                    else:
                        self.output_queue.put("Could not unsuspend - cannot "
                                              "transfer. Stopping.\n")
                        return
                # Transfer (with optional custom folder name).
                self.output_queue.put("\n----- transferring drive -----\n")
                argv = ["user", old, "transfer", "drive", new]
                if folder:
                    argv += ["targetuserfoldername", folder]
                rc = self._stream_gam(argv, "transfer")
                if rc not in (0,):
                    self.output_queue.put("\n[note] transfer finished with a "
                                          "nonzero code (rc=%s). A 'Permission ... "
                                          "Does not exist' warning is normal and "
                                          "does not mean files were missed - check "
                                          "the new user's '" + old + " old files' "
                                          "folder to confirm.\n" % rc)
            except Exception as exc:
                self.output_queue.put("\nWORKFLOW ERROR: " + str(exc) + "\n")
                self._log("TRANSFER WORKFLOW ERROR: " + str(exc))
            finally:
                # Always put the account back the way we found it.
                self._restore_state(old, changed_suspend, changed_archive)
                self.output_queue.put("\n===== TRANSFER COMPLETE (account restored "
                                      "to original state) =====\n")
                self.running_proc = None
                self.output_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _run_move_to_shareddrive(self):
        # Offboarding workflow ported from Move-UserDrive-to-SharedDrive.bat:
        # create a Shared Drive, move the old user's My Drive into it, hand it
        # to the new user, remove temporary access, re-suspend the old user.
        v = self._collect_values()
        old = v.get("old", "").strip(); new = v.get("new", "").strip()
        name = v.get("drivename", "").strip(); admin = v.get("admin", "").strip()
        if not (old and new and name and admin):
            messagebox.showerror(APP_NAME, "Old user, new user, Shared Drive "
                                 "name, and admin are all required.")
            return
        if not messagebox.askyesno(APP_NAME + " - CONFIRM WORKFLOW",
                "This offboarding workflow will:\n\n"
                "  1. Enable " + old + " if it is suspended/archived\n"
                "  2. Create a NEW Shared Drive named '" + name + "'\n"
                "  3. Move " + old + "'s My Drive contents into it\n"
                "  4. Make " + new + " a manager of it\n"
                "  5. Remove the temporary admin/old-user access\n"
                "  6. Restore " + old + " to its original state\n\nProceed?"):
            return
        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            changed_suspend = False; changed_archive = False
            try:
                self.output_queue.put("\n===== MOVE DRIVE -> NEW SHARED DRIVE =====\n")
                state = self._user_state(old)
                if state is None:
                    self.output_queue.put("Could not read " + old + "'s account "
                                          "state (does it exist?). Stopping.\n")
                    return
                was_suspended, was_archived = state
                self.output_queue.put("Original state: suspended=%s archived=%s\n"
                                      % (was_suspended, was_archived))
                if was_archived:
                    self.output_queue.put("\n----- unarchiving -----\n")
                    if self._stream_gam(["update", "user", old, "archived", "off"],
                                        "unarchive") == 0:
                        changed_archive = True
                    else:
                        self.output_queue.put("Could not unarchive. Stopping.\n")
                        return
                if was_suspended:
                    self.output_queue.put("\n----- unsuspending -----\n")
                    if self._stream_gam(["update", "user", old, "suspended", "off"],
                                        "unsuspend") == 0:
                        changed_suspend = True
                    else:
                        self.output_queue.put("Could not unsuspend. Stopping.\n")
                        return
                if self.workflow_cancel:
                    return
                rc, out = self._capture_gam(["user", old, "create", "teamdrive", name])
                if self.workflow_cancel:
                    return
                match = re.search(r"id:\s*([A-Za-z0-9_\-]{10,})", out)
                if rc != 0 or not match:
                    self.output_queue.put(
                        "\n[stopped: could not create the Shared Drive or read its "
                        "id, so NOTHING was moved.]\n")
                    return
                drive_id = match.group(1)
                self.output_queue.put("\nNew Shared Drive id: " + drive_id + "\n")
                steps = [
                    ("grant old user temporary manager access",
                     ["user", admin, "add", "drivefileacl", drive_id, "user", old,
                      "role", "manager", "asadmin"]),
                    ("move the old user's My Drive into the Shared Drive",
                     ["user", old, "move", "drivefile", "root", "teamdriveparentid",
                      drive_id, "mergewithparent"]),
                    ("make the new user a manager",
                     ["user", admin, "add", "drivefileacl", drive_id, "user", new,
                      "role", "manager", "asadmin"]),
                    ("remove old user's manager access",
                     ["user", admin, "delete", "drivefileacl", drive_id, "user", old,
                      "manager", "asadmin"]),
                    ("remove admin's manager access",
                     ["user", admin, "delete", "drivefileacl", drive_id, "user", admin,
                      "manager", "asadmin"]),
                ]
                for label, argv in steps:
                    if self.workflow_cancel:
                        self.output_queue.put("[stopped by user - remaining steps "
                                              "skipped]\n")
                        break
                    self.output_queue.put("\n----- " + label + " -----\n")
                    self._stream_gam(argv, label)
                self.output_queue.put("\n===== DONE: Shared Drive '" + name
                                      + "' is now managed by " + new + " =====\n")
            except Exception as exc:
                self.output_queue.put("\nWORKFLOW ERROR: " + str(exc) + "\n")
                self._log("SHAREDDRIVE WORKFLOW ERROR: " + str(exc))
            finally:
                self._restore_state(old, changed_suspend, changed_archive)
                self.running_proc = None
                self.output_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _ask_typed_confirm(self, summary, keyword):
        # Posts a typed-confirmation request to the UI thread and waits for
        # the poller to show the dialog and report the answer back. The user
        # must type <keyword> exactly (e.g. DELETE or ARCHIVE).
        event = threading.Event()
        result = {"ok": False}
        self.output_queue.put(("confirm", summary, event, result, keyword))
        event.wait()
        return result["ok"]

    def _ask_delete_confirm(self, summary):
        return self._ask_typed_confirm(summary, "DELETE")

    def _run_targeted_cleanup(self):
        # Two-phase targeted email cleanup: search ONCE, then trash/delete from
        # ONLY the mailboxes that matched (a small targets CSV run in one
        # parallel pass). No Drive sweep, no audit - the lightweight version of
        # the incident workflow.
        v = self._collect_values()
        query = v.get("query", "").strip()
        scopetype = v.get("scopetype", "all").strip() or "all"
        scopeval = v.get("scopeval", "").strip()
        threads = v.get("threads", "").strip()
        max_n = v.get("max", "5000").strip() or "5000"
        if not query:
            messagebox.showerror(APP_NAME, "Enter a Gmail search query.")
            return
        if scopetype != "all" and not scopeval:
            messagebox.showerror(APP_NAME, "The chosen search scope needs a "
                                 "value (domain, OU path, or group email).")
            return
        if (threads and not threads.isdigit()) or not max_n.isdigit():
            messagebox.showerror(APP_NAME, "Threads and Max per mailbox must be "
                                 "whole numbers (threads may be blank).")
            return
        scope_entity = (["all", "users"] if scopetype == "all"
                        else [scopetype, scopeval])
        thread_prefix = ["config", "num_threads", threads] if threads else []
        scope_label = ("all mailboxes" if scopetype == "all"
                       else scopetype + " " + scopeval)
        # These workflows are for malicious mail: PERMANENTLY delete (gam's
        # "delete messages" removes the message; it does NOT go to Trash).
        verb = "delete"
        max_flag = "max_to_delete"

        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        work_dir = os.path.join(LOG_DIR, "Cleanup_" + stamp)
        os.makedirs(work_dir, exist_ok=True)
        match_csv = os.path.join(work_dir, "MatchedMessages.csv")
        targets_csv = os.path.join(work_dir, "DeleteTargets.csv")

        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            try:
                self.output_queue.put("\n===== PHASE 1: SEARCH MAILBOXES ("
                                      + scope_label + ") =====\n")
                rc = self._stream_gam(
                    thread_prefix + ["redirect", "csv", match_csv]
                    + scope_entity
                    + ["print", "messages", "query", query,
                       "headers", "from,to,subject,message-id,date"],
                    "search")
                if rc == -1:
                    self.output_queue.put("\n[canceled - nothing changed]\n")
                    return
                if not os.path.isfile(match_csv):
                    self.output_queue.put("\n[stopped: search produced no "
                        "results file - check authorization and the query]\n")
                    return
                pairs, seen, box = [], set(), set()
                with open(match_csv, newline="", encoding="utf-8") as fh:
                    for row in csv.DictReader(fh):
                        u = (row.get("User") or "").strip()
                        mid = (row.get("Message-ID") or "").strip()
                        if u:
                            box.add(u)
                        if u and mid and (u, mid) not in seen:
                            seen.add((u, mid))
                            pairs.append((u, mid))
                self.output_queue.put("\nFound " + str(len(pairs))
                    + " message(s) in " + str(len(box)) + " mailbox(es). "
                    "Evidence: " + match_csv + "\n")
                if not pairs:
                    self.output_queue.put("\nNothing matched - nothing to "
                                          + verb + ". Done.\n")
                    return
                ok = self._ask_delete_confirm(
                    str(len(pairs)) + " message(s) in " + str(len(box))
                    + " mailbox(es) matched:\n\n" + query
                    + "\n\nThey will be PERMANENTLY DELETED (NOT recoverable - "
                    "they do NOT go to Trash) from those mailboxes ONLY.")
                if not ok:
                    self.output_queue.put("\n[canceled at confirmation - "
                                          "nothing changed]\n")
                    return
                with open(targets_csv, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["user", "msgid"])
                    for u, mid in pairs:
                        writer.writerow([u, mid])
                self.output_queue.put("\n===== PHASE 2: " + verb.upper()
                    + " (matched mailboxes only) =====\n")
                # user is a whole argument (~user); the message-id is embedded
                # in a larger string so it needs DOUBLE tildes (~~msgid~~).
                rc = self._stream_gam(
                    thread_prefix + ["csv", targets_csv, "gam", "user", "~user",
                        verb, "messages", "query", "rfc822msgid:~~msgid~~",
                        max_flag, max_n, "doit"],
                    verb + " from matched mailboxes")
                if rc == -1:
                    return
                self.output_queue.put("\n===== DONE ===== " + verb.capitalize()
                    + "d " + str(len(pairs)) + " message(s) from "
                    + str(len(box)) + " matched mailbox(es); all other "
                    "mailboxes skipped.\nEvidence: " + work_dir + "\n")
            except Exception as exc:
                self.output_queue.put("\nWORKFLOW ERROR: " + str(exc) + "\n")
                self._log("targetedcleanup ERROR: " + str(exc))
            finally:
                self.output_queue.put(None)      # re-enable the Run button

        threading.Thread(target=worker, daemon=True).start()

    def _run_drive_wipe(self):
        # Two-phase Drive cleanup: search Drives across the domain for a file by
        # NAME or ID, then trash/permanently-delete every OWNED copy that
        # matched (one parallel pass over just those owners).
        v = self._collect_values()
        findby = v.get("findby", "name").strip() or "name"
        fileref = v.get("fileref", "").strip()
        scopetype = v.get("scopetype", "all").strip() or "all"
        scopeval = v.get("scopeval", "").strip()
        threads = v.get("threads", "").strip()
        if not fileref:
            messagebox.showerror(APP_NAME, "Enter a file name or file ID.")
            return
        if scopetype != "all" and not scopeval:
            messagebox.showerror(APP_NAME, "The chosen search scope needs a "
                                 "value (domain, OU path, or group email).")
            return
        if threads and not threads.isdigit():
            messagebox.showerror(APP_NAME, "Threads must be a whole number, or "
                                 "blank.")
            return
        scope_entity = (["all", "users"] if scopetype == "all"
                        else [scopetype, scopeval])
        thread_prefix = ["config", "num_threads", threads] if threads else []
        scope_label = ("all users" if scopetype == "all"
                       else scopetype + " " + scopeval)

        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        work_dir = os.path.join(LOG_DIR, "DriveWipe_" + stamp)
        os.makedirs(work_dir, exist_ok=True)
        match_csv = os.path.join(work_dir, "MatchedFiles.csv")
        targets_csv = os.path.join(work_dir, "DeleteTargets.csv")

        if findby == "id":
            search = ["print", "filelist", "select", "id:" + fileref,
                      "showownedby", "me", "fields", "id,name,mimetype,owners"]
            what = "file ID " + fileref
        else:
            escaped = fileref.replace("\\", "\\\\").replace("'", "\\'")
            search = ["print", "filelist", "query", "name = '" + escaped + "'",
                      "showownedby", "me", "excludetrashed",
                      "fields", "id,name,mimetype,owners"]
            what = "files named '" + fileref + "'"

        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            try:
                self.output_queue.put("\n===== PHASE 1: SEARCH DRIVES ("
                    + scope_label + ") =====\nLooking for " + what + "\n")
                rc = self._stream_gam(
                    thread_prefix + ["redirect", "csv", match_csv]
                    + scope_entity + search,
                    "drive search")
                if rc == -1:
                    self.output_queue.put("\n[canceled - nothing changed]\n")
                    return
                if not os.path.isfile(match_csv):
                    self.output_queue.put("\n[stopped: search produced no "
                        "results file - check authorization and the value]\n")
                    return
                targets, seen, sample = [], set(), []
                with open(match_csv, newline="", encoding="utf-8") as fh:
                    for row in csv.DictReader(fh):
                        owner = (row.get("Owner") or row.get("User")
                                 or row.get("owners.0.emailAddress") or "").strip()
                        fid = (row.get("id") or "").strip()
                        name = (row.get("name") or "").strip()
                        if owner and fid and (owner, fid) not in seen:
                            seen.add((owner, fid))
                            targets.append((owner, fid))
                            if len(sample) < 8:
                                sample.append(name + "  (" + owner + ")")
                self.output_queue.put("\nFound " + str(len(targets))
                    + " owned copy/copies. Evidence: " + match_csv + "\n")
                if not targets:
                    self.output_queue.put("\nNo owned copies matched - nothing "
                                          "to remove. Done.\n")
                    return
                ok = self._ask_delete_confirm(
                    str(len(targets)) + " owned Drive file(s) matched "
                    + what + ".\n\nExamples:\n  " + "\n  ".join(sample)
                    + ("\n  ..." if len(targets) > len(sample) else "")
                    + "\n\nThey will be PERMANENTLY DELETED (NOT recoverable - "
                    "they do NOT go to Trash).")
                if not ok:
                    self.output_queue.put("\n[canceled at confirmation - "
                                          "nothing changed]\n")
                    return
                with open(targets_csv, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["owner", "fileid"])
                    for owner, fid in targets:
                        writer.writerow([owner, fid])
                self.output_queue.put("\n===== PHASE 2: PERMANENTLY DELETE "
                                      "matched copies =====\n")
                # owner is a whole arg (~owner); the id is embedded, so ~~fileid~~.
                # 'purge' permanently deletes (verified: it does not go to Trash).
                rc = self._stream_gam(
                    thread_prefix + ["csv", targets_csv, "gam", "user", "~owner",
                        "delete", "drivefile", "id:~~fileid~~", "purge"],
                    "permanently delete matched files")
                if rc == -1:
                    return
                self.output_queue.put("\n===== DONE ===== Permanently deleted "
                    + str(len(targets)) + " file(s). Evidence: "
                    + work_dir + "\n")
            except Exception as exc:
                self.output_queue.put("\nWORKFLOW ERROR: " + str(exc) + "\n")
                self._log("drivewipe ERROR: " + str(exc))
            finally:
                self.output_queue.put(None)      # re-enable the Run button

        threading.Thread(target=worker, daemon=True).start()

    def _run_remove_ext_access(self):
        # Two-phase: find every internal user (in scope) who can see an
        # EXTERNALLY owned file (by name or id), then remove each user's OWN
        # access. Google only lets a user drop their own access when they had
        # EDIT rights, so view-only external shares report an error (use the
        # Admin console Security Investigation Tool for those). The evidence CSV
        # lists everyone who has the file either way.
        v = self._collect_values()
        findby = v.get("findby", "name").strip() or "name"
        fileref = v.get("fileref", "").strip()
        scopetype = v.get("scopetype", "user").strip() or "user"
        scopeval = v.get("scopeval", "").strip()
        threads = v.get("threads", "").strip()
        if not fileref:
            messagebox.showerror(APP_NAME, "Enter a file name or file ID.")
            return
        if scopetype != "all" and not scopeval:
            messagebox.showerror(APP_NAME, "Enter the user(s), domain, OU, or "
                                 "group (only 'Everyone' may be left blank).")
            return
        if threads and not threads.isdigit():
            messagebox.showerror(APP_NAME, "Threads must be a whole number, or "
                                 "blank.")
            return
        scope_entity = (["all", "users"] if scopetype == "all"
                        else [scopetype, scopeval])
        thread_prefix = ["config", "num_threads", threads] if threads else []
        scope_label = ("all users" if scopetype == "all"
                       else scopetype + " " + scopeval)

        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        work_dir = os.path.join(LOG_DIR, "RemoveAccess_" + stamp)
        os.makedirs(work_dir, exist_ok=True)
        match_csv = os.path.join(work_dir, "WhoHasTheFile.csv")
        targets_csv = os.path.join(work_dir, "RemoveTargets.csv")

        if findby == "id":
            search = ["print", "filelist", "select", "id:" + fileref,
                      "showownedby", "others", "fields", "id,name,owners"]
            what = "file ID " + fileref
        else:
            escaped = fileref.replace("\\", "\\\\").replace("'", "\\'")
            search = ["print", "filelist", "query", "name = '" + escaped + "'",
                      "showownedby", "others", "fields", "id,name,owners"]
            what = "files named '" + fileref + "'"

        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            try:
                self.output_queue.put("\n===== PHASE 1: FIND WHO HAS IT ("
                    + scope_label + ") =====\nLooking for " + what
                    + " that your users can see but do NOT own\n")
                rc = self._stream_gam(
                    thread_prefix + ["redirect", "csv", match_csv]
                    + scope_entity + search,
                    "find access")
                if rc == -1:
                    self.output_queue.put("\n[canceled - nothing changed]\n")
                    return
                if not os.path.isfile(match_csv):
                    self.output_queue.put("\n[stopped: search produced no "
                        "results file - check authorization and the value]\n")
                    return
                pairs, seen, sample, extowner = [], set(), [], ""
                with open(match_csv, newline="", encoding="utf-8") as fh:
                    for row in csv.DictReader(fh):
                        user = (row.get("Owner") or row.get("User") or "").strip()
                        fid = (row.get("id") or "").strip()
                        name = (row.get("name") or "").strip()
                        ext = (row.get("owners.0.emailAddress") or "").strip()
                        if ext and not extowner:
                            extowner = ext
                        if user and fid and (user, fid) not in seen:
                            seen.add((user, fid))
                            pairs.append((user, fid))
                            if len(sample) < 10:
                                sample.append(user + "  (" + name + ")")
                self.output_queue.put("\nFound " + str(len(pairs))
                    + " internal user(s) with the file"
                    + ((" - external owner: " + extowner) if extowner else "")
                    + ".\nEvidence (who has it): " + match_csv + "\n")
                if not pairs:
                    self.output_queue.put("\nNo internal users in that scope "
                        "have this file. Nothing to remove. Done.\n")
                    return
                ok = self._ask_delete_confirm(
                    str(len(pairs)) + " internal user(s) can see "
                    + what + ".\n\nExamples:\n  " + "\n  ".join(sample)
                    + ("\n  ..." if len(pairs) > len(sample) else "")
                    + "\n\nThis will remove each user's access. NOTE: only "
                    "EDIT-shared copies can be removed this way; VIEW-ONLY "
                    "external shares will report an error - use the Admin "
                    "console Security Investigation Tool for those.")
                if not ok:
                    self.output_queue.put("\n[canceled at confirmation - "
                                          "nothing changed]\n")
                    return
                with open(targets_csv, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["user", "fileid"])
                    for user, fid in pairs:
                        writer.writerow([user, fid])
                self.output_queue.put("\n===== PHASE 2: REMOVE ACCESS =====\n"
                    "(a 'Does not exist' error for a user just means it was a "
                    "view-only external share GAM cannot remove - handle those "
                    "in the Admin investigation tool.)\n")
                # ~user is a whole argument (both the acting user AND the ACL
                # scope, i.e. the user removes their own permission); the file id
                # is embedded in id:... so it uses DOUBLE tildes.
                rc = self._stream_gam(
                    thread_prefix + ["csv", targets_csv, "gam", "user", "~user",
                        "delete", "drivefileacl", "id:~~fileid~~", "~user"],
                    "remove access")
                if rc == -1:
                    return
                self.output_queue.put("\n===== DONE ===== Attempted access "
                    "removal for " + str(len(pairs)) + " user(s). Any that "
                    "errored were view-only external shares (use the "
                    "investigation tool). Evidence: " + work_dir + "\n")
            except Exception as exc:
                self.output_queue.put("\nWORKFLOW ERROR: " + str(exc) + "\n")
                self._log("removeextaccess ERROR: " + str(exc))
            finally:
                self.output_queue.put(None)      # re-enable the Run button

        threading.Thread(target=worker, daemon=True).start()

    def _run_archive_courses(self):
        # End-of-year: archive every ACTIVE Google Classroom. Discovers the
        # list first (read-only), requires a typed ARCHIVE confirmation, then
        # archives via 'gam csv' so gam parallelizes the many updates.
        self.workflow_cancel = False
        self.run_button.config(state="disabled")
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        csv_path = os.path.join(LOG_DIR, "ActiveCourses_" + stamp + ".csv")

        def worker():
            try:
                self.output_queue.put("\n===== ARCHIVE ALL ACTIVE CLASSROOMS =====\n"
                                      "Step 1: finding active courses...\n")
                rc = self._stream_gam(["redirect", "csv", csv_path, "print",
                                       "courses", "states", "active",
                                       "fields", "id,name,ownerEmail"],
                                      "list active courses")
                if rc == -1:
                    return
                if not os.path.isfile(csv_path):
                    self.output_queue.put("\n[stopped: could not produce the course "
                                          "list. Nothing was archived.]\n")
                    return
                rows = []
                with open(csv_path, newline="", encoding="utf-8") as fh:
                    for row in csv.DictReader(fh):
                        if row.get("id"):
                            rows.append(row)
                if not rows:
                    self.output_queue.put("\nNo active courses found. Nothing to "
                                          "archive.\n")
                    return
                self.output_queue.put("\nFound " + str(len(rows)) + " active "
                                      "course(s). Sample:\n")
                for row in rows[:10]:
                    self.output_queue.put("  - " + row.get("name", "?") + "  ("
                                          + row.get("ownerEmail", "?") + ")\n")
                if len(rows) > 10:
                    self.output_queue.put("  ...and " + str(len(rows) - 10) + " more\n")
                if not self._ask_typed_confirm(
                        str(len(rows)) + " active Classroom(s) will be ARCHIVED "
                        "(hidden, not deleted).", "ARCHIVE"):
                    self.output_queue.put("\n[canceled - nothing archived. The list "
                                          "is saved at " + csv_path + "]\n")
                    return
                self.output_queue.put("\nStep 2: archiving " + str(len(rows))
                                      + " course(s) (this can take a while)...\n")
                self._stream_gam(["csv", csv_path, "gam", "update", "course",
                                  "~id", "status", "archived"], "archive courses")
                self.output_queue.put("\n===== DONE. The archived-course list is "
                                      "saved at " + csv_path + " =====\n")
            except Exception as exc:
                self.output_queue.put("\nWORKFLOW ERROR: " + str(exc) + "\n")
                self._log("ARCHIVE COURSES ERROR: " + str(exc))
            finally:
                self.running_proc = None
                self.output_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _run_mailbox_audit(self):
        # Read-only sweep of the four common email-attacker footholds on a
        # single mailbox. No changes, so no confirmation is required.
        email = self._collect_values().get("email", "").strip()
        if not email:
            messagebox.showerror(APP_NAME, "Mailbox address is required.")
            return
        checks = [
            ("Gmail filters / rules", ["user", email, "show", "filters"]),
            ("Forwarding addresses",
             ["user", email, "show", "forwardingaddresses"]),
            ("Send-as identities", ["user", email, "show", "sendas"]),
            ("Mailbox delegates", ["user", email, "show", "delegates"]),
        ]
        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            try:
                self.output_queue.put(
                    "\n===== MAILBOX TAKEOVER AUDIT: " + email + " =====\n"
                    "Review each section for anything the user did not set "
                    "up themselves - especially forwarding to an outside "
                    "address or a filter that deletes incoming mail.\n")
                for label, argv in checks:
                    if self.workflow_cancel:
                        break
                    self.output_queue.put("\n----- " + label + " -----\n")
                    self._stream_gam(argv, label)
                self.output_queue.put("\n===== AUDIT COMPLETE =====\n")
            except Exception as exc:
                self.output_queue.put("\nAUDIT ERROR: " + str(exc) + "\n")
                self._log("AUDIT ERROR: " + str(exc))
            finally:
                self.output_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _run_bulk_license_csv(self):
        # Bulk add/remove licenses from a local CSV (Email, License columns).
        values = self._collect_values()
        path = values.get("file", "").strip()
        action = values.get("action", "").strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror(APP_NAME, "Pick a CSV file that exists.")
            return
        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            try:
                with open(path, newline="", encoding="utf-8-sig") as fh:
                    text = fh.read()
                self._bulk_license_core(text, action,
                                        "CSV file " + os.path.basename(path))
            except Exception as exc:
                self.output_queue.put("\nERROR: " + str(exc) + "\n")
                self._log("BULK LICENSE ERROR: " + str(exc))
            finally:
                self.running_proc = None
                self.output_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _run_bulk_license_sheet(self):
        # Bulk add/remove licenses from a Google Sheet. Exports the tab to a
        # local CSV via gam, then runs the same core logic.
        values = self._collect_values()
        user = values.get("user", "").strip()
        fileid = values.get("fileid", "").strip()
        sheet = values.get("sheet", "").strip()
        action = values.get("action", "").strip()
        if not (user and fileid and sheet):
            messagebox.showerror(APP_NAME, "Admin, sheet file ID, and tab name "
                                 "are all required.")
            return
        self.workflow_cancel = False
        self.run_button.config(state="disabled")
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        out_name = "BulkLicSheet_" + stamp + ".csv"
        out_path = os.path.join(LOG_DIR, out_name)

        def worker():
            try:
                self.output_queue.put("\n===== BULK LICENSES FROM GOOGLE SHEET =====\n"
                                      "Exporting the sheet tab to CSV...\n")
                rc, _ = self._capture_gam(
                    ["user", user, "get", "drivefile", "id:" + fileid,
                     "csvsheet", sheet, "targetfolder", LOG_DIR,
                     "targetname", out_name, "overwrite", "true"])
                if rc != 0 or not os.path.isfile(out_path):
                    self.output_queue.put("\n[stopped: could not export the sheet. "
                                          "Check the admin, file ID, and tab name.]\n")
                    return
                with open(out_path, newline="", encoding="utf-8-sig") as fh:
                    text = fh.read()
                self._bulk_license_core(text, action, "Google Sheet")
            except Exception as exc:
                self.output_queue.put("\nERROR: " + str(exc) + "\n")
                self._log("BULK LICENSE SHEET ERROR: " + str(exc))
            finally:
                self.running_proc = None
                self.output_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _bulk_license_core(self, csv_text, action, source):
        # Shared logic for the bulk-license workflows: parse Email/License,
        # translate license names to SKUs, preview, confirm, and apply via
        # 'gam csv' (gam parallelizes the per-user updates).
        self.output_queue.put("\nReading rows from " + source + "...\n")
        reader = csv.DictReader(io.StringIO(csv_text))
        headers = reader.fieldnames or []
        email_col = next((h for h in headers if h.strip().lower() == "email"), None)
        lic_col = next((h for h in headers if h.strip().lower() == "license"), None)
        if not email_col or not lic_col:
            self.output_queue.put("\n[stopped: the data needs 'Email' and "
                                  "'License' column headers. Found: "
                                  + (", ".join(headers) or "none") + "]\n")
            return
        pairs = []
        unknown = []
        for row in reader:
            email = (row.get(email_col) or "").strip()
            lic_raw = (row.get(lic_col) or "").strip()
            if not email and not lic_raw:
                continue
            sku = translate_license(lic_raw)
            if not email or not sku:
                unknown.append((email or "(blank)", lic_raw or "(blank)"))
            else:
                pairs.append((email, sku))
        if unknown:
            self.output_queue.put("\nThese rows could not be understood:\n")
            for email, lic in unknown[:20]:
                self.output_queue.put("  - " + email + " : license '" + lic + "'\n")
            if len(unknown) > 20:
                self.output_queue.put("  ...and " + str(len(unknown) - 20) + " more\n")
            self.output_queue.put("\n[stopped: " + str(len(unknown)) + " unrecognized "
                                  "row(s). Nothing was changed. Use a friendly "
                                  "license name or a SKU id in the License column.]\n")
            return
        if not pairs:
            self.output_queue.put("\nNo usable rows found. Nothing to do.\n")
            return
        verb = "ADD" if action == "add" else "REMOVE"
        self.output_queue.put("\n" + str(len(pairs)) + " change(s) to " + verb
                              + ". Sample:\n")
        for email, sku in pairs[:10]:
            self.output_queue.put("  - " + email + "  "
                                  + ("gets" if action == "add" else "loses")
                                  + " SKU " + sku + "\n")
        if len(pairs) > 10:
            self.output_queue.put("  ...and " + str(len(pairs) - 10) + " more\n")
        if not self._ask_typed_confirm(str(len(pairs)) + " user(s) will "
                                       + verb.lower() + " the listed license.", verb):
            self.output_queue.put("\n[canceled - nothing changed]\n")
            return
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        run_csv = os.path.join(LOG_DIR, "BulkLicRun_" + stamp + ".csv")
        with open(run_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Email", "SKU"])
            for email, sku in pairs:
                writer.writerow([email, sku])
        self.output_queue.put("\nApplying " + str(len(pairs)) + " change(s)...\n")
        self._stream_gam(["csv", run_csv, "gam", "user", "~Email", action,
                          "license", "~SKU"], "bulk license " + action)
        self.output_queue.put("\n===== DONE (list saved at " + run_csv + ") =====\n")

    def _run_incident_workflow(self):
        # Native implementation of the email incident-response
        # workflow (originally GAM7-Workspace-Email-Cleanup.bat), built in
        # so it works on any machine GAMGUI is installed on.
        values = self._collect_values()
        sender = values.get("from", "").strip()
        subject = values.get("subject", "").strip()
        days = values.get("days", "30").strip() or "30"
        max_del = values.get("max", "5000").strip() or "5000"
        # Search scope: "all" (all mailboxes) or a keyword + value pair
        # (domains/ou_and_children/group). _collect_values has already turned
        # the friendly dropdown choice into the gam keyword.
        scopetype = values.get("scopetype", "all").strip() or "all"
        scopeval = values.get("scopeval", "").strip()
        threads = values.get("threads", "").strip()
        # Drive attachment sweep: off | auto (read the name from the caught
        # emails) | manual (use the filename(s) the operator typed).
        drivesweep = values.get("drivesweep", "off").strip() or "off"
        attachname = values.get("attachname", "").strip()
        if not sender or not subject:
            messagebox.showerror(APP_NAME, "From address and Subject are required.")
            return
        if not days.isdigit() or not max_del.isdigit():
            messagebox.showerror(APP_NAME, "Lookback days and max delete must be whole numbers.")
            return
        if scopetype != "all" and not scopeval:
            messagebox.showerror(APP_NAME, "The chosen search scope needs a value "
                                 "(domain, OU path, or group email).")
            return
        if threads and not threads.isdigit():
            messagebox.showerror(APP_NAME, "Speed (threads) must be a whole number, or blank.")
            return
        # Reusable command pieces. scope_entity is the GAM user selector; it is
        # "all users" for the whole domain, else "<keyword> <value>". Scoping to
        # fewer mailboxes is the main speedup. thread_prefix optionally raises
        # the parallel mailbox count for this run (config MUST precede redirect,
        # verified against gam). Both are injected into the phase 1/3 commands.
        scope_entity = ["all", "users"] if scopetype == "all" else [scopetype, scopeval]
        thread_prefix = ["config", "num_threads", threads] if threads else []
        scope_label = "all mailboxes" if scopetype == "all" else (scopetype + " " + scopeval)

        # Per-incident evidence folder, timestamped like the batch original.
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        incident_dir = os.path.join(LOG_DIR, "Incident_" + stamp)
        os.makedirs(incident_dir, exist_ok=True)
        match_csv = os.path.join(incident_dir, "MatchedMessages.csv")
        gmail_csv = os.path.join(incident_dir, "GmailAuditRaw.csv")
        drive_csv = os.path.join(incident_dir, "DriveDownloadRaw.csv")
        summary_txt = os.path.join(incident_dir, "Summary.txt")
        query = incident_query(sender, subject)

        self.workflow_cancel = False
        self.run_button.config(state="disabled")

        def worker():
            summary_lines = ["Incident run " + stamp,
                             "From: " + sender, "Subject: " + subject,
                             "Query: " + query, "Scope: " + scope_label,
                             "Threads: " + (threads or "config default")]
            try:
                # ---- Phase 1: scoped discovery (read-only) --------------
                self.output_queue.put("\n===== PHASE 1: SEARCH MAILBOXES ("
                                      + scope_label + ") =====\n")
                discovery_argv = (thread_prefix + ["redirect", "csv", match_csv]
                    + scope_entity
                    + ["print", "messages", "query", query,
                       "headers", "from,to,subject,message-id,date"])
                # When a Drive sweep is requested, also capture the attachment
                # file names in the evidence CSV so we can auto-detect them and
                # so the operator can read exactly what was attached.
                if drivesweep != "off":
                    discovery_argv += ["attachmentnamepattern", ".*",
                                       "showattachments"]
                rc = self._stream_gam(discovery_argv, "discovery")
                # A domain-wide "all users" operation returns a NONZERO exit
                # code whenever ANY single mailbox fails the query - and on a
                # large domain some always do (suspended, unlicensed, or
                # unprovisioned mailboxes). That is NORMAL and does not mean
                # discovery failed: GAM still wrote the results CSV with every
                # mailbox that matched. So we must NOT treat a nonzero exit as
                # fatal. Abort only on a real user cancel, or if no results
                # file was produced at all (a genuine auth/query failure).
                if rc == -1:
                    self.output_queue.put("\n[workflow canceled during "
                                          "discovery - nothing was deleted]\n")
                    return
                if not os.path.isfile(match_csv):
                    self.output_queue.put("\n[workflow stopped: discovery "
                                          "produced no results file - check "
                                          "authorization and the query]\n")
                    return
                if rc != 0:
                    self.output_queue.put(
                        "\n[note] discovery finished with some per-mailbox "
                        "errors (rc=%d). This is normal on a large domain - "
                        "suspended/unlicensed/unprovisioned mailboxes are "
                        "skipped. Continuing with the messages that were "
                        "found.\n" % rc)
                # Parse the evidence CSV. Verified gam headers:
                # User,threadId,id,From,To,Subject,Message-ID,Date
                hits = []
                users = set()
                msgids = set()
                if os.path.isfile(match_csv):
                    with open(match_csv, newline="", encoding="utf-8") as fh:
                        for row in csv.DictReader(fh):
                            hits.append(row)
                            if row.get("User"):
                                users.add(row["User"])
                            if row.get("Message-ID"):
                                msgids.add(row["Message-ID"])
                summary_lines.append("Messages found: " + str(len(hits)))
                summary_lines.append("Mailboxes affected: " + str(len(users)))
                summary_lines.append("Unique Message-IDs: " + str(len(msgids)))
                self.output_queue.put(
                    "\nFound " + str(len(hits)) + " message(s) in "
                    + str(len(users)) + " mailbox(es); "
                    + str(len(msgids)) + " unique Message-ID(s).\n"
                    "Evidence: " + match_csv + "\n")
                if not hits:
                    self.output_queue.put("\nNothing matched - no deletion "
                                          "needed. Workflow complete.\n")
                    return

                # ---- Drive attachment search (read-only, before confirm) ----
                # Find the attachment name(s), then look for OWNED copies of a
                # file with that exact name across the same scope. Matches are
                # shown at the confirmation step; nothing is removed until the
                # operator types DELETE.
                drive_matches = []          # list of (owner_email, fileid, name)
                attach_names = []
                drive_match_csv = os.path.join(incident_dir,
                                               "DriveAttachmentMatches.csv")
                if drivesweep == "manual" and attachname:
                    attach_names = [a.strip() for a in attachname.split(",")
                                    if a.strip()]
                elif drivesweep == "auto":
                    # Best-effort: pull file names from any evidence-CSV column
                    # whose header mentions "attachment".
                    seen = set()
                    for row in hits:
                        for col, val in row.items():
                            if col and "attachment" in col.lower() and val \
                                    and val.strip():
                                for nm in val.replace("\n", ",").split(","):
                                    nm = nm.strip()
                                    if nm and nm.lower() not in seen:
                                        seen.add(nm.lower())
                                        attach_names.append(nm)
                if drivesweep != "off":
                    if not attach_names:
                        self.output_queue.put("\n[Drive sweep] No attachment "
                            "filename to search for (none entered, and none "
                            "could be auto-detected). Skipping the Drive part.\n")
                    else:
                        # Scope the Drive search to ONLY the mailboxes that
                        # matched the email. The attachment would only be in the
                        # Drive of someone who actually received it, so searching
                        # every mailbox by filename is both slow AND dangerous -
                        # it matches unrelated files that merely share the name,
                        # owned by people (including long-disabled accounts) who
                        # never got the message. Write the affected users to a
                        # CSV and search just those.
                        affected_csv = os.path.join(incident_dir,
                                                    "AffectedUsers.csv")
                        with open(affected_csv, "w", newline="",
                                  encoding="utf-8") as fh:
                            aw = csv.writer(fh)
                            aw.writerow(["user"])
                            for u in sorted(users):
                                aw.writerow([u])
                        drive_scope = ["csvfile", affected_csv + ":user"]
                        self.output_queue.put("\n===== DRIVE SWEEP: SEARCH "
                            "(read-only, only the " + str(len(users))
                            + " mailbox(es) that got the email) =====\nLooking "
                            "for owned Drive copies of: "
                            + ", ".join(attach_names) + "\n")
                        # Escape single quotes for the Drive query, then OR the
                        # names into one filelist query.
                        clauses = ["name = '" + n.replace("'", "\\'") + "'"
                                   for n in attach_names]
                        dquery = " or ".join(clauses)
                        rcd = self._stream_gam(
                            thread_prefix + ["redirect", "csv", drive_match_csv]
                            + drive_scope
                            + ["print", "filelist", "query", dquery,
                               "showownedby", "me", "excludetrashed",
                               "fields", "id,name,owners,size"],
                            "drive attachment search")
                        if rcd == -1:
                            return
                        if os.path.isfile(drive_match_csv):
                            with open(drive_match_csv, newline="",
                                      encoding="utf-8") as fh:
                                for row in csv.DictReader(fh):
                                    owner = (row.get("Owner")
                                             or row.get("User")
                                             or row.get("owners.0.emailAddress")
                                             or "").strip()
                                    fid = (row.get("id") or "").strip()
                                    fname = (row.get("name") or "").strip()
                                    if owner and fid:
                                        drive_matches.append((owner, fid, fname))
                        self.output_queue.put("\nDrive matches: "
                            + str(len(drive_matches)) + " owned file(s). "
                            "Evidence: " + drive_match_csv + "\n")
                        summary_lines.append("Drive attachment matches: "
                            + str(len(drive_matches)))

                # ---- Phase 2: typed-DELETE confirmation -----------------
                confirm_msg = (str(len(hits)) + " message(s) in "
                    + str(len(users)) + " mailbox(es) matched:\n\n" + query)
                if drivesweep != "off":
                    confirm_msg += ("\n\nPLUS " + str(len(drive_matches))
                        + " matching Drive file(s) will be moved to their "
                        "owner's Trash (recoverable).")
                confirm_msg += ("\n\nReview the CSVs in the Incident folder "
                                "first if unsure.")
                ok = self._ask_delete_confirm(confirm_msg)
                if not ok:
                    summary_lines.append("Operator canceled - NO deletions.")
                    self.output_queue.put("\n[canceled at confirmation - "
                                          "evidence kept, nothing deleted]\n")
                    return

                # ---- Phase 3: delete from ONLY the matched mailboxes -----
                # THE SPEEDUP: discovery already recorded which user held which
                # Message-ID (in 'hits'). So write a tiny targets CSV and delete
                # straight from those mailboxes in ONE parallelized pass, instead
                # of re-scanning EVERY mailbox with "all users" for each id. On a
                # large domain this touches only the handful of mailboxes that
                # actually got the message and skips all the rest.
                self.output_queue.put("\n===== PHASE 3: DELETE =====\n")
                pairs = []                       # (user, message-id), de-duped
                seen_pairs = set()
                for row in hits:
                    u = (row.get("User") or "").strip()
                    mid = (row.get("Message-ID") or "").strip()
                    if u and mid and (u, mid) not in seen_pairs:
                        seen_pairs.add((u, mid))
                        pairs.append((u, mid))

                if pairs:
                    # A clean CSV with simple headers (user, msgid) so gam's
                    # ~header substitution is unambiguous (the raw evidence
                    # header 'Message-ID' has a hyphen that ~ref could misread).
                    targets_csv = os.path.join(incident_dir, "DeleteTargets.csv")
                    with open(targets_csv, "w", newline="",
                              encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(["user", "msgid"])
                        for u, mid in pairs:
                            writer.writerow([u, mid])
                    matched_boxes = len(set(u for u, _ in pairs))
                    self.output_queue.put(
                        "Deleting " + str(len(pairs)) + " message(s) from the "
                        + str(matched_boxes) + " matched mailbox(es) ONLY - "
                        "every mailbox that did not contain the message is "
                        "skipped.\n")
                    # NOTE: gam uses a SINGLE ~field only for a whole argument
                    # (~user), but DOUBLE ~~field~~ to substitute INSIDE a larger
                    # string, so the message-id must be rfc822msgid:~~msgid~~
                    # (single-tilde here would stay literal and delete nothing).
                    rc = self._stream_gam(
                        thread_prefix + ["csv", targets_csv, "gam", "user",
                            "~user", "delete", "messages", "query",
                            "rfc822msgid:~~msgid~~", "max_to_delete", max_del,
                            "doit"],
                        "delete from matched mailboxes")
                    if rc == -1:
                        return
                    summary_lines.append("Deleted " + str(len(pairs))
                        + " message(s) from " + str(matched_boxes)
                        + " matched mailbox(es); all other mailboxes skipped.")
                    summary_lines.append("Delete targets: " + targets_csv)
                elif msgids:
                    # Have Message-IDs but no per-mailbox mapping: one scoped
                    # delete covering every id at once (still a single pass).
                    q = " OR ".join("rfc822msgid:" + m for m in sorted(msgids))
                    rc = self._stream_gam(
                        thread_prefix + scope_entity
                        + ["delete", "messages", "query", q,
                           "max_to_delete", max_del, "doit"],
                        "delete by message-id")
                    if rc == -1:
                        return
                    summary_lines.append("Deleted by Message-ID: "
                                         + str(len(msgids)) + " id(s).")
                else:
                    rc = self._stream_gam(
                        thread_prefix + scope_entity
                        + ["delete", "messages", "query",
                           query, "max_to_delete", max_del, "doit"],
                        "delete by query")
                    if rc == -1:
                        return
                    summary_lines.append("Deleted by From+Subject query "
                                         "(no Message-IDs available).")

                # ---- Phase 4: Drive attachment removal (trash, recoverable) --
                if drive_matches:
                    self.output_queue.put("\n===== PHASE 4: TRASH DRIVE "
                        "ATTACHMENT COPIES =====\n")
                    trashed = 0
                    for owner, fid, fname in drive_matches:
                        self.output_queue.put("  trashing \"" + fname
                            + "\" (" + fid + ") owned by " + owner + "\n")
                        rct = self._stream_gam(
                            ["user", owner, "trash", "drivefile", "id:" + fid],
                            "trash drive " + fid)
                        if rct == -1:
                            return
                        if rct == 0:
                            trashed += 1
                    summary_lines.append("Drive files trashed: " + str(trashed)
                        + " of " + str(len(drive_matches)))
                    self.output_queue.put("\nTrashed " + str(trashed) + " of "
                        + str(len(drive_matches)) + " Drive file(s) (in each "
                        "owner's Drive Trash, recoverable ~30 days).\n")

                # ---- Phase 5: audit evidence (read-only reports) --------
                self.output_queue.put("\n===== PHASE 5: AUDIT REPORTS =====\n")
                rc = self._stream_gam(
                    ["redirect", "csv", gmail_csv, "report", "gmail",
                     "user", "all", "start", "-" + days + "d",
                     "event", "delivery",
                     "gmaileventtypes", "7,15/19,28,31,32"],
                    "gmail audit")
                if rc not in (0, -1):
                    # Some editions reject gmaileventtypes; retry plain.
                    rc = self._stream_gam(
                        ["redirect", "csv", gmail_csv, "report", "gmail",
                         "user", "all", "start", "-" + days + "d",
                         "event", "delivery"],
                        "gmail audit fallback")
                if rc == -1:
                    return
                rc = self._stream_gam(
                    ["redirect", "csv", drive_csv, "report", "drive",
                     "user", "all", "start", "-" + days + "d",
                     "event", "download"],
                    "drive audit")
                if rc == -1:
                    return
                summary_lines.append("Audit CSVs: " + gmail_csv
                                     + " and " + drive_csv)
                self.output_queue.put("\n===== WORKFLOW COMPLETE =====\n"
                                      "All evidence in: " + incident_dir + "\n")
            except Exception as exc:
                self.output_queue.put("\nWORKFLOW ERROR: " + str(exc) + "\n")
                self._log("WORKFLOW ERROR: " + str(exc))
                summary_lines.append("ERROR: " + str(exc))
            finally:
                try:
                    with open(summary_txt, "w", encoding="utf-8") as fh:
                        fh.write("\n".join(summary_lines) + "\n")
                except OSError:
                    pass
                self.output_queue.put(None)   # re-enable the Run button

        threading.Thread(target=worker, daemon=True).start()

    def _run_external(self):
        # Launches an interactive script in its OWN console window. Needed
        # because scripts like the Email Cleanup workflow use SET /P
        # prompts and a typed DELETE confirmation - those require a real
        # console with a keyboard, which the GUI output pane is not.
        path = self._collect_values().get("path", "").strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror(APP_NAME, "Workflow script not found:\n" + path)
            return
        if os.name != "nt":
            messagebox.showerror(APP_NAME,
                                 "This workflow launcher is Windows-only.")
            return
        # 'start' opens a new console; 'cmd /k' keeps it open after the
        # script ends so the operator can read the results. The working
        # directory is the script's folder so its Logs\ and Temp\ output
        # lands next to the script as designed.
        subprocess.Popen(["cmd", "/c", "start", "GAM Email Cleanup",
                          "cmd", "/k", path],
                         cwd=os.path.dirname(path))
        self._append_output("\n[launched in new console: " + path + "]\n")
        self._log("LAUNCH EXTERNAL: " + path)

    def _run_interactive(self):
        # Launches an interactive gam command (oauth create/update) in its OWN
        # console window, because it opens a browser for sign-in and shows
        # GAM's scope menu - both need a real console/keyboard, not the
        # captured output pane. The selected Domain (config section) is applied
        # so you can authorize a specific account.
        if os.name != "nt":
            messagebox.showerror(APP_NAME,
                                 "The interactive OAuth launch is Windows-only. "
                                 "Copy the previewed command and run it in a "
                                 "terminal instead.")
            return
        display, argv, error = build_command(self.current_task,
                                             self._collect_values())
        if error:
            messagebox.showerror(APP_NAME, error)
            return
        section = self.domain_section or "default"
        # 'start' opens a new console; 'cmd /k' keeps it open after gam exits so
        # the operator can read the result and complete any prompts. Same
        # pattern the external-script launcher uses.
        subprocess.Popen(["cmd", "/c", "start", "GAM OAuth (" + section + ")",
                          "cmd", "/k", self.gam_path]
                         + self._domain_prefix() + argv)
        prefix = " ".join(self._domain_prefix())
        self._append_output("\n[launched in a new console: gam "
                            + (prefix + " " if prefix else "") + display
                            + "]\nComplete the browser sign-in and GAM's scope "
                            "menu in that window.\n")
        self._log("LAUNCH INTERACTIVE [" + section + "]: " + display)

    def _stop(self):
        # Tell a running incident workflow not to start its next phase.
        self.workflow_cancel = True
        proc = self.running_proc
        if proc is None:
            return
        self._log("STOP requested by user")
        try:
            if os.name == "nt":
                # gam runs WITHOUT a shell, but gam can start child
                # processes of its own (e.g. multiprocess CSV runs), and
                # proc.kill() would only end the top process. taskkill with
                # /T kills the whole process TREE (gam + any children); /F
                # forces it.
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True)
            else:
                # macOS/Linux: kill the whole process group created by
                # start_new_session=True in _run().
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            self._append_output("\n[stopped by user]\n")
            self._log("STOPPED by user (process tree killed)")
        except Exception as exc:
            # If the process finished in the meantime the kill can fail;
            # report it instead of pretending the stop worked.
            self._append_output("\n[stop failed: " + str(exc) + "]\n")
            self._log("STOP FAILED: " + str(exc))

    def _poll_output(self):
        # Runs every 100 ms on the UI thread; drains the worker queue.
        # HARDENED: this method must never let an exception escape, because
        #   (1) escaping would skip the reschedule at the bottom and kill the
        #       poll loop for good (output pane goes dead, app looks frozen),
        #       and (2) a confirm dialog that failed WITHOUT releasing its
        #       event would deadlock the waiting worker thread. So the confirm
        #       branch always sets its event (finally), and the whole body is
        #       wrapped so the reschedule always happens (finally).
        try:
            while True:
                try:
                    line = self.output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    self.run_button.config(state="normal")
                elif isinstance(line, tuple) and line[0] == "confirm":
                    # Workflow worker is blocked waiting for this answer;
                    # dialogs must run here on the UI thread. A 5th tuple
                    # element (keyword) sets which word must be typed;
                    # older 4-element requests default to DELETE.
                    _tag, summary, event, result = line[0], line[1], line[2], line[3]
                    keyword = line[4] if len(line) > 4 else "DELETE"
                    try:
                        answer = simpledialog.askstring(
                            APP_NAME + " - CONFIRM " + keyword,
                            summary + "\n\nType " + keyword + " to proceed "
                            "(anything else cancels):",
                            parent=self)
                        result["ok"] = (answer == keyword)
                    finally:
                        event.set()   # ALWAYS release the worker thread
                else:
                    self._append_output(line)
        except Exception as exc:
            # Never let a UI-thread error kill the poll loop.
            try:
                self._log("POLL ERROR: " + str(exc))
            except Exception:
                pass
        finally:
            self.after(100, self._poll_output)   # always reschedule

    def _append_output(self, text):
        self.output_box.insert("end", text)
        self.output_box.see("end")
        # Mirror everything into the session log for troubleshooting, with
        # any password value masked (see redact_secrets).
        try:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(redact_secrets(text))
        except OSError:
            pass                      # never let logging crash the UI

    def _log(self, message):
        stamp = datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
        try:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                # redact_secrets masks any password value before it hits disk.
                handle.write("[" + stamp + "] " + redact_secrets(message) + "\n")
        except OSError:
            pass

    # ---- settings -----------------------------------------------------------
    def _locate_gam(self):
        path = filedialog.askopenfilename(
            title="Locate gam.exe",
            filetypes=[("gam executable", "gam.exe;gam"), ("All files", "*.*")])
        if path:
            self.gam_path = path
            self.path_label.config(text="gam: " + path)
            if not self.config_parser.has_section("gamgui"):
                self.config_parser.add_section("gamgui")
            self.config_parser.set("gamgui", "gam_path", path)
            with open(INI_PATH, "w", encoding="utf-8") as handle:
                self.config_parser.write(handle)
            self._log("gam path set to " + path)

    # ---- theme (light / dark) ----------------------------------------------
    def _apply_theme(self):
        # Repaint the whole window in the current mode. ttk widgets are styled
        # by class (so widgets created later automatically match), and the two
        # classic Tk Text widgets are colored directly because they ignore ttk.
        dark = self.dark_mode
        p = DARK_PALETTE if dark else LIGHT_PALETTE
        style = self.style
        if dark:
            # "clam" is the ttk theme that honors custom colors on Windows.
            style.theme_use("clam")
            style.configure(".", background=p["bg"], foreground=p["fg"],
                            fieldbackground=p["entry_bg"], bordercolor=p["entry_bg"],
                            lightcolor=p["bg"], darkcolor=p["bg"],
                            troughcolor=p["trough"], insertcolor=p["fg"],
                            arrowcolor=p["fg"])
            style.configure("TFrame", background=p["bg"])
            style.configure("TLabel", background=p["bg"], foreground=p["fg"])
            style.configure("TPanedwindow", background=p["bg"])
            style.configure("TButton", background=p["button_bg"], foreground=p["fg"])
            style.map("TButton",
                      background=[("active", p["button_active"]),
                                  ("disabled", p["bg"])],
                      foreground=[("disabled", p["disabled"])])
            style.configure("TEntry", fieldbackground=p["entry_bg"],
                            foreground=p["fg"], insertcolor=p["fg"])
            style.configure("TCombobox", fieldbackground=p["entry_bg"],
                            foreground=p["fg"], background=p["button_bg"],
                            arrowcolor=p["fg"])
            style.map("TCombobox",
                      fieldbackground=[("readonly", p["entry_bg"])],
                      foreground=[("readonly", p["fg"])],
                      selectbackground=[("readonly", p["entry_bg"])],
                      selectforeground=[("readonly", p["fg"])])
            style.configure("Treeview", background=p["entry_bg"],
                            fieldbackground=p["entry_bg"], foreground=p["fg"])
            style.map("Treeview", background=[("selected", p["select_bg"])],
                      foreground=[("selected", p["select_fg"])])
        else:
            # Light mode: hand every ttk widget back to the native theme.
            style.theme_use(self._default_theme)
        # The Combobox dropdown list is a classic Tk Listbox created on demand;
        # option_add settings applied now take effect the next time it opens.
        self.option_add("*TCombobox*Listbox.background", p["entry_bg"])
        self.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", p["select_bg"])
        self.option_add("*TCombobox*Listbox.selectForeground", p["select_fg"])
        # Root window plus the two classic Text widgets (preview + output).
        self.configure(bg=p["bg"])
        for txt in (getattr(self, "preview_box", None),
                    getattr(self, "output_box", None)):
            if txt is not None:
                txt.configure(bg=p["entry_bg"], fg=p["fg"],
                              insertbackground=p["fg"],
                              selectbackground=p["select_bg"],
                              selectforeground=p["select_fg"])
        # Switching the ttk theme resets per-theme settings such as the task
        # tree's row height, so re-apply it for the current text size.
        if getattr(self, "_base_font_sizes", None) is not None:
            self._apply_rowheight()

    def _toggle_dark(self):
        # Flip the mode, repaint, and remember the choice in gamgui.ini so the
        # window opens the same way next time.
        self.dark_mode = bool(self.dark_var.get())
        self._apply_theme()
        try:
            if not self.config_parser.has_section("gamgui"):
                self.config_parser.add_section("gamgui")
            self.config_parser.set("gamgui", "dark_mode",
                                   "true" if self.dark_mode else "false")
            with open(INI_PATH, "w", encoding="utf-8") as handle:
                self.config_parser.write(handle)
        except Exception:
            pass                              # a settings-save failure is not fatal

    # ---- built-in update check / self-update -------------------------------
    def _version_tuple(self, text):
        # Turns a version/tag string like "2.26" or "v2.26" into a tuple of ints
        # (2, 26) so versions compare NUMERICALLY - otherwise "2.9" would look
        # newer than "2.26" as a string. Non-digit junk in a part becomes 0.
        cleaned = (text or "").strip().lstrip("vV")
        parts = []
        for piece in cleaned.split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts) if parts else (0,)

    def _toggle_check_updates(self):
        # Persist the "check at startup" preference to gamgui.ini.
        self.check_updates = bool(self.check_updates_var.get())
        try:
            if not self.config_parser.has_section("gamgui"):
                self.config_parser.add_section("gamgui")
            self.config_parser.set("gamgui", "check_updates",
                                   "true" if self.check_updates else "false")
            with open(INI_PATH, "w", encoding="utf-8") as handle:
                self.config_parser.write(handle)
        except Exception:
            pass

    def _show_about(self):
        # Simple About box with the version and repo.
        messagebox.showinfo(
            "About " + APP_NAME,
            APP_NAME + " " + APP_VERSION + "\n\n"
            "A graphical front-end for GAM7.\n"
            + UPDATE_RELEASES_URL)

    def _check_updates_async(self, auto):
        # Starts the update check on a background thread so the UI never freezes
        # (a slow or unreachable network would otherwise hang the window).
        # 'auto' True = the silent startup check (say nothing unless an update
        # exists); False = the user clicked "Check for updates now" (always give
        # feedback, including "you are up to date" and errors).
        if self._update_in_progress:
            return
        worker = threading.Thread(target=self._check_updates_worker,
                                  args=(auto,), daemon=True)
        worker.start()

    def _check_updates_worker(self, auto):
        # Runs OFF the UI thread. Asks GitHub for the latest release tag, then
        # hands the result back to the UI thread with self.after (tkinter is not
        # thread-safe, so all UI work must happen there).
        tag = ""
        err = ""
        try:
            request = urllib.request.Request(
                UPDATE_API_URL,
                headers={"User-Agent": "GAMGUI-Updater",
                         "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(request, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
            tag = str(data.get("tag_name", "")).strip()
            if not tag:
                err = "GitHub did not return a release tag."
        except Exception as exc:
            err = str(exc)
        # Marshal back onto the UI thread.
        self.after(0, lambda: self._on_update_check_result(tag, err, auto))

    def _on_update_check_result(self, tag, err, auto):
        # Runs ON the UI thread with the check's outcome.
        if err or not tag:
            # A silent startup check stays silent on failure (e.g. offline); a
            # manual check tells the user what went wrong.
            if not auto:
                messagebox.showwarning(
                    APP_NAME + " - Update check",
                    "Could not check for updates:\n" + (err or "unknown error"))
            self._log("Update check failed: " + (err or "no tag"))
            return
        if self._version_tuple(tag) > self._version_tuple(APP_VERSION):
            self._prompt_update(tag)
        else:
            self._log("Update check: up to date (" + APP_VERSION + ").")
            if not auto:
                messagebox.showinfo(
                    APP_NAME + " - Update check",
                    "You are on the latest version (" + APP_VERSION + ").")

    def _prompt_update(self, tag):
        # Offers the update. GAMGUI never updates without this explicit yes.
        self._log("Update available: " + APP_VERSION + " -> " + tag)
        answer = messagebox.askyesno(
            APP_NAME + " - Update available",
            "A newer version of " + APP_NAME + " is available.\n\n"
            "    Installed: " + APP_VERSION + "\n"
            "    Latest:    " + tag + "\n\n"
            "Update now? " + APP_NAME + " will close, update itself, and "
            "reopen when it is done.")
        if answer:
            self._do_self_update(tag)

    def _do_self_update(self, tag):
        # Launches the bundled updater in a DETACHED process, then closes this
        # app so its files unlock and can be replaced. The updater waits a few
        # seconds first (so we are fully gone), updates, and relaunches GAMGUI.
        if self._update_in_progress:
            return

        # Self-update via the PowerShell updater is Windows-only. On mac/Linux
        # just open the Releases page so the user can grab the new build.
        if sys.platform != "win32":
            webbrowser.open(UPDATE_RELEASES_URL)
            messagebox.showinfo(
                APP_NAME,
                "Opening the Releases page in your browser so you can download "
                "the new version.")
            return

        appdir = app_dir()
        updater = os.path.join(appdir, "updategamgui.ps1")
        if not os.path.isfile(updater):
            # No bundled updater (e.g. running from source): fall back to the
            # Releases page rather than failing.
            webbrowser.open(UPDATE_RELEASES_URL)
            messagebox.showinfo(
                APP_NAME,
                "The updater script was not found next to the app, so the "
                "Releases page has been opened in your browser instead.")
            return

        # Is THIS running copy the registered Setup.exe (Program Files) install,
        # or a portable one? Decide from the REGISTRY, not from whether the
        # folder is writable - an admin can often write to Program Files, which
        # made the old write-probe wrongly treat the installed copy as portable
        # (so it updated files but never the installer/registry entry). If our
        # folder matches the recorded InstallLocation, it is the exe install and
        # must be updated by re-running Setup.exe (which needs admin).
        reg = registry_exe_install()
        installed = bool(reg and _same_path(appdir, reg.get("location", "")))

        ps_updater = updater.replace("'", "''")
        ps_appdir = appdir.replace("'", "''")
        try:
            if installed:
                # Launch the updater ELEVATED (UAC) so it can re-run Setup.exe.
                # The installer's /CLOSEAPPLICATIONS closes this app itself, so
                # we do not pre-sleep. ShellExecuteW with the "runas" verb is the
                # reliable way for a non-elevated app to request elevation - the
                # previous nested "Start-Process -Verb RunAs" inside a detached
                # PowerShell was fragile and could silently do nothing.
                import ctypes
                params = ('-ExecutionPolicy Bypass -NoProfile -File "'
                          + updater + '" -InstallType exe -Launch')
                rc = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "powershell.exe", params, None, 1)
                if int(rc) <= 32:
                    # <=32 means ShellExecute failed (e.g. the UAC prompt was
                    # declined). Do not close the app; tell the user.
                    messagebox.showwarning(
                        APP_NAME,
                        "The update needs administrator approval and it was not "
                        "granted, so nothing was changed. Try again and choose "
                        "Yes at the Windows prompt, or update manually from:\n"
                        + UPDATE_RELEASES_URL)
                    return
            else:
                # Portable copy: robocopy needs this app closed first, so the
                # updater sleeps briefly. Its own console window shows progress.
                inner = ("Start-Sleep -Seconds 3; & '" + ps_updater + "' "
                         "-InstallType zip -InstallRoot '" + ps_appdir
                         + "' -Launch")
                cre  = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                creT = cre | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                subprocess.Popen(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile",
                     "-Command", inner],
                    creationflags=creT)
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                "Could not start the updater:\n" + str(exc)
                + "\n\nYou can update manually from:\n" + UPDATE_RELEASES_URL)
            return

        self._update_in_progress = True
        self._log("Self-update launched (" + APP_VERSION + " -> " + tag
                  + (installed and ", installer" or ", portable") + ").")
        # Close the app so the updater can replace its files. destroy() ends the
        # mainloop; the process then exits and its file locks release.
        self.destroy()

    # ---- domain (gam.cfg section) selection --------------------------------
    def _domain_prefix(self):
        # Leading gam args that scope THIS command to the chosen gam.cfg
        # section. Empty list when running as the saved default. Verified to
        # be a one-shot that does not persist the selection.
        if getattr(self, "domain_section", ""):
            return ["select", self.domain_section]
        return []

    def _gam_cfg_path(self):
        # Locate gam.cfg: GAMCFGDIR wins (that is how this environment is set
        # up), else next to the gam executable, else the user ~/.gam default.
        # Best-effort - returns "" if none found so the selector still works
        # with only manual entries.
        candidates = []
        env_dir = os.environ.get("GAMCFGDIR", "")
        if env_dir:
            candidates.append(os.path.join(env_dir, "gam.cfg"))
        if self.gam_path:
            candidates.append(os.path.join(os.path.dirname(self.gam_path), "gam.cfg"))
        candidates.append(os.path.join(os.path.expanduser("~"), ".gam", "gam.cfg"))
        for candidate in candidates:
            try:
                if os.path.isfile(candidate):
                    return candidate
            except OSError:
                continue                    # unreachable share must not crash us
        return ""

    def _domain_choices(self):
        # "(default)" + only the gam.cfg sections that are GENUINELY separate
        # tenants (they define their OWN config_dir, i.e. their own credentials
        # folder - the way an MSP keeps client domains apart). Sections that
        # merely preset other variables and inherit config_dir from [DEFAULT]
        # (for example cros-reporting shortcuts) are NOT different domains, so
        # they are intentionally hidden here to keep the Domain list meaningful.
        # Manually added entries (the + button) are always shown.
        # interpolation=None so a value containing '%' cannot raise.
        choices = ["(default)"]
        cfg_path = self._gam_cfg_path()
        if cfg_path:
            parser = configparser.ConfigParser(interpolation=None)
            try:
                parser.read(cfg_path)
                default_cfgdir = parser.get("DEFAULT", "config_dir", fallback="")
                for section in parser.sections():
                    if section.lower() == "default":
                        continue
                    sec_cfgdir = parser.get(section, "config_dir", fallback="")
                    # A real separate tenant overrides config_dir to its own,
                    # different credentials folder. Same/inherited = not a domain.
                    if sec_cfgdir and sec_cfgdir != default_cfgdir \
                            and section not in choices:
                        choices.append(section)
            except Exception:
                pass                        # a malformed/unreachable cfg is non-fatal
        manual = self.config_parser.get("gamgui", "domains", fallback="")
        for name in [m.strip() for m in manual.split(";") if m.strip()]:
            if name not in choices:
                choices.append(name)
        return choices

    def _on_domain_change(self, _event):
        # Translate the dropdown choice into the section token used per command.
        selection = self.domain_var.get()
        self.domain_section = "" if selection == "(default)" else selection
        self._log("Domain set to: " + (self.domain_section or "(default)"))

    def _add_domain(self):
        # Let the user add a section name by hand (for tenants not present in
        # gam.cfg). Stored in gamgui.ini so it persists across sessions.
        name = simpledialog.askstring(
            APP_NAME, "gam.cfg section name to add to the Domain list:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if not self.config_parser.has_section("gamgui"):
            self.config_parser.add_section("gamgui")
        existing = self.config_parser.get("gamgui", "domains", fallback="")
        names = [m.strip() for m in existing.split(";") if m.strip()]
        if name not in names:
            names.append(name)
            self.config_parser.set("gamgui", "domains", ";".join(names))
            with open(INI_PATH, "w", encoding="utf-8") as handle:
                self.config_parser.write(handle)
        self.domain_combo.config(values=self._domain_choices())
        self.domain_var.set(name)
        self._on_domain_change(None)


# =============================================================================
# SECTION: Entry point
# =============================================================================

if __name__ == "__main__":
    app = GamGui()
    app.mainloop()
