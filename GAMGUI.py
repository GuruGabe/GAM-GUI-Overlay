# =============================================================================
# Script:   GAMGUI.py
# Author:   Gabriel Clifton (built with Claude). Originally created for a K-12 Google
#           Workspace and generalized for public sharing.
# Created:  07-23-2026
# Modified: 08-07-2026
# Version:  1.12
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
import tkinter as tk           # The GUI toolkit that ships with Python
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog

APP_NAME = "GAMGUI"
APP_VERSION = "1.12"

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

INI_PATH = os.path.join(app_dir(), "gamgui.ini")
LOG_DIR = os.path.join(app_dir(), "Logs")

# =============================================================================
# SECTION: Task catalog
#
# Every task is a small dictionary:
#   name        - shown in the task list
#   desc        - plain-English explanation shown above the form
#   template    - the gam command with {placeholders}; parts wrapped in
#                 [square brackets] are optional and are dropped whenever
#                 every placeholder inside them is left blank
#   fields      - list of input fields: (label, key, required, choices)
#                 choices=None gives a text box; a list gives a dropdown
#   destructive - True adds an extra "are you sure" confirmation
#
# This data-driven design means adding a new task is 5 lines, no new code.
# =============================================================================

def T(name, desc, template, fields, destructive=False, external=False,
      workflow=False, audit=False):
    # Tiny helper so the catalog below stays readable.
    # external=True: launches a program in its own console window instead
    #   of running a gam command.
    # workflow=True: runs the built-in multi-phase incident-response
    #   workflow (special code path, not a single template).
    # audit=True: runs the read-only mailbox takeover audit (several
    #   read-only gam commands in sequence, no confirmation needed).
    return {"name": name, "desc": desc, "template": template,
            "fields": fields, "destructive": destructive,
            "external": external, "workflow": workflow, "audit": audit}

def F(label, key, required=True, choices=None, default=""):
    # Tiny helper for field definitions.
    return {"label": label, "key": key, "required": required,
            "choices": choices, "default": default}

TASKS = {
 "Users": [
  T("Create user",
    "Creates a new user account. If OU is given the account is created "
    "directly in that OU so campus policies apply immediately.",
    "create user {email} firstname {first} lastname {last} password {password} [ou {ou}] [notify {notify}]",
    [F("New email address", "email"), F("First name", "first"),
     F("Last name", "last"), F("Password", "password"),
     F("OU path e.g. /Staff/Building1 (optional)", "ou", False),
     F("Email credentials to (optional)", "notify", False)]),
  T("Reset password",
    "Sets a new password for a user. Leave the password blank to have GAM "
    "generate a random one and email it to the notify address.",
    "update user {email} password {password|uniquerandom} [notify {notify}]",
    [F("User email", "email"), F("New password (blank = random)", "password", False),
     F("Email new password to (optional)", "notify", False)]),
  T("Suspend / unsuspend user",
    "Suspending blocks sign-in but keeps all data and licenses. "
    "Unsuspending restores access.",
    "update user {email} suspended {state}",
    [F("User email", "email"), F("Action", "state", choices=["on", "off"])]),
  T("Move user to OU",
    "Moves the account to a different OU. Policies of the new OU apply.",
    "update user {email} org {ou}",
    [F("User email", "email"), F("New OU path e.g. /Students/Building1", "ou")]),
  T("Rename user (display name)",
    "Changes first/last name only. The email address does not change.",
    "update user {email} [firstname {first}] [lastname {last}]",
    [F("User email", "email"), F("New first name (optional)", "first", False),
     F("New last name (optional)", "last", False)]),
  T("Change primary email",
    "Changes the sign-in address. The old address automatically becomes an "
    "alias so mail to it still arrives.",
    "update user {email} username {newemail}",
    [F("Current email", "email"), F("New email", "newemail")]),
  T("Hide/show in Global Address List",
    "Hidden users do not appear in the directory when people compose mail.",
    "update user {email} gal {state}",
    [F("User email", "email"), F("Show in GAL?", "state", choices=["off", "on"])]),
  T("User info",
    "Shows everything about one account: OU, aliases, groups, licenses, "
    "and the unique Google user ID.",
    "info user {email}",
    [F("User email", "email")]),
  T("Export users to CSV/Sheet",
    "Prints users with common fields. Output target 'todrive' creates a "
    "Google Sheet; 'screen' shows results below.",
    "print users fields primaryemail,firstname,lastname,orgunitpath,lastlogintime,suspended [todrive {todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"])]),
  T("Delete user (DESTRUCTIVE)",
    "Deletes the account. Recoverable with Undelete for about 20 days, "
    "after that everything is gone. Transfer Drive/Calendar data first!",
    "delete user {email}",
    [F("User email", "email")], destructive=True),
  T("Undelete user",
    "Restores a user deleted within the last ~20 days.",
    "undelete user {email} [ou {ou}]",
    [F("User email", "email"), F("Restore to OU (optional)", "ou", False)]),
 ],
 "Groups": [
  T("Create group",
    "Creates a Google Group (mailing list / access list).",
    "create group {group} [name {name}] [description {desc}]",
    [F("Group email", "group"), F("Display name (optional)", "name", False),
     F("Description (optional)", "desc", False)]),
  T("Add member",
    "Adds one address to a group with the chosen role.",
    "update group {group} add {role} {member}",
    [F("Group email", "group"),
     F("Role", "role", choices=["member", "manager", "owner"]),
     F("Member email", "member")]),
  T("Remove member",
    "Removes one address from a group.",
    "update group {group} delete member {member}",
    [F("Group email", "group"), F("Member email", "member")]),
  T("Sync group from OU (DESTRUCTIVE)",
    "Makes group membership EXACTLY match the users in an OU tree: missing "
    "users are added and anyone else is REMOVED from the group.",
    "update group {group} sync member notsuspended ous_and_children {ou}",
    [F("Group email", "group"), F("OU path e.g. /Staff/Building1", "ou")], destructive=True),
  T("List members",
    "Shows the full roster of a group.",
    "print group-members group {group}",
    [F("Group email", "group")]),
  T("Export all groups",
    "Prints every group in the domain.",
    "print groups [todrive {todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"])]),
  T("Delete group (DESTRUCTIVE)",
    "Deletes the group itself. Member accounts are not affected.",
    "delete group {group}",
    [F("Group email", "group")], destructive=True),
 ],
 "Aliases": [
  T("Create alias",
    "Adds an extra receive-address to a user or group.",
    "create alias {alias} {kind} {target}",
    [F("Alias address", "alias"),
     F("Target type", "kind", choices=["user", "group"]),
     F("Target email", "target")]),
  T("Delete alias",
    "Removes an alias. The target keeps its primary address.",
    "delete alias {alias}",
    [F("Alias address", "alias")], destructive=True),
  T("What is this address?",
    "Tells you whether an address is a user, a group, or an alias.",
    "whatis {email}",
    [F("Email address", "email")]),
 ],
 "Org Units": [
  T("Create OU", "Creates an organizational unit under the given path.",
    "create org {path} [description {desc}]",
    [F("Full OU path e.g. /Students/Building1", "path"),
     F("Description (optional)", "desc", False)]),
  T("Show OU tree", "Displays the whole OU hierarchy.",
    "show orgtree", []),
  T("Move users into OU",
    "Moves the listed users (space separated) into the target OU.",
    "update org {path} add user {users}",
    [F("Target OU path e.g. /Students/Building1", "path"), F("User email(s), space separated", "users")]),
  T("Delete OU (DESTRUCTIVE)",
    "Deletes an OU. It must be empty (no users/devices) first.",
    "delete org {path}",
    [F("OU path", "path")], destructive=True),
 ],
 "Chromebooks": [
  T("Device info by serial",
    "Full detail for one Chromebook found by its serial number.",
    "cros_sn {serial} info",
    [F("Serial number", "serial")]),
  T("Move device to OU",
    "Moves a Chromebook to another OU so different policies apply.",
    "cros_sn {serial} update ou {ou}",
    [F("Serial number", "serial"), F("New OU path e.g. /Students/Building1", "ou")]),
  T("Disable / re-enable device",
    "Disable locks a lost or stolen Chromebook; re-enable releases it.",
    "cros_sn {serial} update action {action}",
    [F("Serial number", "serial"),
     F("Action", "action", choices=["disable", "reenable"])], destructive=True),
  T("Powerwash device (DESTRUCTIVE)",
    "Factory-resets the Chromebook remotely. All local data is wiped. "
    "The device stays enrolled.",
    "issuecommand cros query:id:{serial} command remote_powerwash times_to_check_status 10 doit",
    [F("Serial number", "serial")], destructive=True),
  T("Wipe users from device (DESTRUCTIVE)",
    "Removes all user profiles from the device but keeps enrollment.",
    "issuecommand cros query:id:{serial} command wipe_users doit",
    [F("Serial number", "serial")], destructive=True),
  T("Export devices to CSV/Sheet",
    "Prints the fleet with the most useful fields.",
    "print cros fields serialnumber,ou,status,lastsync,annotateduser,annotatedassetid [todrive {todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"])]),
  T("Who used this Chromebook last?",
    "Shows recent users and networks for a device.",
    "cros_sn {serial} info recentusers lastknownnetwork",
    [F("Serial number", "serial")]),
 ],
 "Gmail": [
  T("Show delegates", "Lists who can open this mailbox as a delegate.",
    "user {email} show delegates", [F("Mailbox", "email")]),
  T("Add delegate",
    "Gives another user full mailbox access without sharing the password.",
    "user {email} add delegate {delegate}",
    [F("Mailbox", "email"), F("Delegate email", "delegate")]),
  T("Remove delegate", "Revokes delegate access.",
    "user {email} delete delegate {delegate}",
    [F("Mailbox", "email"), F("Delegate email", "delegate")]),
  T("Enable forwarding",
    "Registers the destination and turns forwarding on; a copy stays in "
    "the mailbox (keep).",
    "user {email} add forwardingaddress {dest}",
    [F("Mailbox", "email"), F("Forward to", "dest")]),
  T("Turn forwarding on (after registering)",
    "Second step: activates forwarding to an already-registered address.",
    "user {email} forward on keep {dest}",
    [F("Mailbox", "email"), F("Forward to", "dest")]),
  T("Turn forwarding off", "Stops forwarding for the mailbox.",
    "user {email} forward off", [F("Mailbox", "email")]),
  T("Set vacation responder",
    "Turns on an automatic reply. Dates are YYYY-MM-DD (Google's format).",
    "user {email} vacation on subject {subject} message {message} [startdate {start}] [enddate {end}]",
    [F("Mailbox", "email"), F("Subject", "subject"), F("Message", "message"),
     F("Start date YYYY-MM-DD (optional)", "start", False),
     F("End date YYYY-MM-DD (optional)", "end", False)]),
  T("Vacation responder off", "Turns the automatic reply off.",
    "user {email} vacation off", [F("Mailbox", "email")]),
  T("Set signature", "Replaces the mailbox signature (plain text or HTML).",
    "user {email} signature {signature}",
    [F("Mailbox", "email"), F("Signature text", "signature")]),
  T("Search messages (preview)",
    "Shows matching messages WITHOUT touching them. Always run this "
    "before any delete. Query syntax = Gmail search box.",
    "user {email} show messages query {query}",
    [F("Mailbox", "email"), F("Gmail query e.g. from:x subject:y", "query")]),
  T("Trash messages (DESTRUCTIVE)",
    "Moves matching messages to Trash (recoverable ~30 days). The max "
    "limit is a seatbelt against a bad query.",
    "user {email} trash messages query {query} max_to_trash {max} doit",
    [F("Mailbox", "email"), F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"),
     F("Max messages to trash", "max", default="25")], destructive=True),
 ],
 "Calendars": [
  T("Who can access a calendar?",
    "Lists the sharing (ACL) entries. Calendar ID is usually an email.",
    "calendar {cal} showacl", [F("Calendar ID (usually an email address)", "cal")]),
  T("Grant calendar access",
    "Gives a user or group access at the chosen level.",
    "calendar {cal} add {role} {who} sendnotifications false",
    [F("Calendar ID (usually an email address)", "cal"),
     F("Role", "role", choices=["freebusy", "reader", "editor", "owner"]),
     F("User email (or group:address)", "who")]),
  T("Remove calendar access", "Revokes a person's access to the calendar.",
    "calendar {cal} delete {who}",
    [F("Calendar ID (usually an email address)", "cal"), F("User email", "who")], destructive=True),
  T("List events",
    "Prints events; use dates to narrow the window (YYYY-MM-DD).",
    "calendar {cal} print events [after {after}] [before {before}] fields summary,start,end",
    [F("Calendar ID (usually an email address)", "cal"), F("After date (optional)", "after", False),
     F("Before date (optional)", "before", False)]),
 ],
 "Drive": [
  T("List a user's files",
    "Prints the files a user owns. Warning: can be large; a query like "
    "mimeType contains 'video/' narrows it.",
    "user {email} print filelist fields id,name,mimetype [query {query}]",
    [F("User email", "email"), F("Drive query (optional) e.g. mimeType contains 'video/'", "query", False)]),
  T("Transfer My Drive to another user",
    "Moves ownership of EVERYTHING the old user owns to the new user. "
    "Handles a SUSPENDED or ARCHIVED old account automatically: GAM cannot "
    "transfer files out of a disabled account, so this temporarily enables "
    "it, transfers, then restores it to EXACTLY the state it was in. GAM "
    "lands the files in a subfolder named '<old user> old files' (NOT the "
    "root); leave the folder name blank for that default or set your own "
    "(tags: #user# = old email, #username# = name before the @).",
    "", [F("Old user", "old"), F("New user", "new"),
         F("Folder name in new user's Drive (optional)", "folder", False)],
    destructive=True, workflow="transferdrive"),
  T("Share a file/folder",
    "Adds a permission on one file or folder (find the ID in the URL "
    "or a filelist export).",
    "user {owner} add drivefileacl {fileid} user {who} role {role}",
    [F("File owner", "owner"), F("File/folder ID (from the file's URL)", "fileid"),
     F("Share with", "who"),
     F("Role", "role", choices=["reader", "commenter", "writer"])]),
  T("List Shared Drives",
    "Prints all Shared Drives visible to the admin.",
    "print shareddrives fields id,name [todrive {todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"])]),
  T("Create Shared Drive", "Creates a new Shared Drive with the given name.",
    "create shareddrive {name}", [F("Shared Drive name", "name")]),
  T("Add member to Shared Drive",
    "Grants a role on a Shared Drive (organizer = full control).",
    "add drivefileacl shareddrive {driveid} user {who} role {role}",
    [F("Shared Drive ID (find it with List Shared Drives)", "driveid"), F("User email", "who"),
     F("Role", "role", choices=["reader", "commenter", "writer", "contentmanager", "organizer"])]),
  T("Move a user's Drive INTO a NEW Shared Drive (workflow)",
    "Offboarding helper: creates a NEW Shared Drive, moves the old user's "
    "My Drive contents into it, hands management to the new user, then "
    "removes the temporary access. Designed for a SUSPENDED user - it "
    "unsuspends them for the move and re-suspends them at the end. Needs an "
    "admin account. (Ported from the Move-UserDrive-to-SharedDrive batch.)",
    "", [F("Old user (unsuspended for the move, then re-suspended)", "old"),
         F("New user (becomes the Shared Drive manager)", "new"),
         F("Name for the new Shared Drive", "drivename"),
         F("Admin account (runs the ACL changes)", "admin")],
    destructive=True, workflow="shareddrive"),
 ],
 "Classroom": [
  T("List courses (by teacher)",
    "Prints courses; give a teacher email to see just theirs.",
    "print courses [teacher {teacher}] [todrive {todrive}]",
    [F("Teacher email (optional)", "teacher", False),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"])]),
  T("Add teacher to course", "Adds a co-teacher to a course by course ID.",
    "course {courseid} add teacher {teacher}",
    [F("Course ID (find it with List courses)", "courseid"), F("Teacher email", "teacher")]),
  T("Change course owner",
    "New owner must already be a teacher in the course (use Add teacher "
    "first). Old owner remains a teacher.",
    "update course {courseid} owner {newowner}",
    [F("Course ID (find it with List courses)", "courseid"), F("New owner email", "newowner")]),
  T("Archive course", "Archives a course (required before deleting).",
    "update course {courseid} status archived",
    [F("Course ID (find it with List courses)", "courseid")]),
  T("Archive ALL active Classrooms (end of year) (DESTRUCTIVE)",
    "End-of-year cleanup: finds EVERY active Google Classroom, shows you the "
    "count and a sample, asks you to type ARCHIVE, then archives them all. "
    "Archived classes are hidden but NOT deleted (teachers and students can "
    "still open them). Run AFTER the school year ends and BEFORE new classes "
    "are created, so you do not archive next year's courses. The full list "
    "is saved to the Logs folder as a record.",
    "", [], destructive=True, workflow="archivecourses"),
  T("Delete course (DESTRUCTIVE)", "Deletes an archived course.",
    "delete course {courseid}",
    [F("Course ID (find it with List courses)", "courseid")], destructive=True),
 ],
 "Licenses": [
  T("Show license counts", "Domain totals by SKU.", "show licenses", []),
  T("Add license to user", "Assigns a license SKU to a user.",
    "user {email} add license {sku}",
    [F("User email", "email"), F("SKU ID e.g. 1010310008", "sku")]),
  T("Remove license from user", "Removes a license SKU from a user.",
    "user {email} delete license {sku}",
    [F("User email", "email"), F("SKU ID e.g. 1010310008", "sku")], destructive=True),
 ],
 "Reports": [
  T("Admin activity (7 days)",
    "Who changed what in the Admin console over the last week.",
    "report admin start -7d", []),
  T("Login activity (3 days)", "Recent login events across the domain.",
    "report login start -3d", []),
  T("User usage snapshot", "Storage and Gmail statistics for one user.",
    "report user user {email}", [F("User email", "email")]),
 ],
 "Security": [
  T("Sign user out everywhere",
    "Kills all web and device sessions. First move for a compromised "
    "account.",
    "user {email} signout", [F("User email", "email")]),
  T("Deprovision (offboarding)",
    "Deletes app passwords, backup codes, and OAuth tokens; optionally "
    "also signs out and disables 2SV.",
    "user {email} deprovision popimap signout turnoff2sv",
    [F("User email", "email")], destructive=True),
  T("Show mailbox rules (Gmail filters)",
    "Lists every Gmail filter (rule) on a mailbox with its conditions and "
    "actions. Attackers who phish an account often add a rule that auto-"
    "deletes or forwards incoming mail to hide their tracks. Watch for "
    "actions like trash/delete, forward to an OUTSIDE address, or "
    "skip-inbox combined with mark-as-read.",
    "user {email} show filters", [F("Mailbox e.g. user@example.com", "email")]),
  T("Mailbox takeover audit (one user)",
    "One-click READ-ONLY check of the four places an email attacker hides "
    "after phishing an account: Gmail filters/rules, forwarding "
    "addresses, send-as identities, and mailbox delegates. Nothing is "
    "changed - it just shows you all four so you can spot anything the "
    "user did not set up themselves. Run this first on any suspected "
    "compromised account.",
    "", [F("Mailbox e.g. user@example.com", "email")], audit=True),
  T("Show OAuth tokens",
    "Lists third-party apps this user has granted access to. A malicious "
    "OAuth app is another common attacker foothold.",
    "user {email} print tokens", [F("User email", "email")]),
  T("Revoke one app's access",
    "Deletes the OAuth grant for a specific client ID (from Show tokens).",
    "user {email} delete tokens clientid {clientid}",
    [F("User email", "email"), F("Client ID (copy from Show OAuth tokens)", "clientid")], destructive=True),
 ],
 "Email Cleanup": [
  T("Search ALL mailboxes (preview)",
    "Searches EVERY mailbox in the domain for matching messages and lists "
    "from/to/subject/message-id/date. Read-only. Query uses Gmail search "
    "syntax, e.g.: from:bad@evil.com subject:\"Gift Card\". Note: a "
    "domain-wide search takes a while on a large domain.",
    "all users print messages query {query} headers from,to,subject,message-id,date",
    [F("Gmail query e.g. from:x subject:\"y\"", "query")]),
  T("Trash from ALL mailboxes (DESTRUCTIVE)",
    "Moves matching messages to Trash in EVERY mailbox (recoverable for "
    "~30 days). Run the search preview first and check the hit count. "
    "The max limit stops a bad query from running away.",
    "all users trash messages query {query} max_to_trash {max} doit",
    [F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"), F("Max per mailbox", "max", default="5000")],
    destructive=True),
  T("Delete from ALL mailboxes (DESTRUCTIVE)",
    "Permanently deletes matching messages from EVERY mailbox - no trash, "
    "no recovery. For phishing incident response. ALWAYS run the search "
    "preview first. Prefer an exact Message-ID query when you have one: "
    "rfc822msgid:<the-message-id> - it is far more precise than "
    "from+subject matching.",
    "all users delete messages query {query} max_to_delete {max} doit",
    [F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"), F("Max per mailbox", "max", default="5000")],
    destructive=True),
  T("Delete from ONE mailbox (DESTRUCTIVE)",
    "Permanently deletes matching messages from a single mailbox.",
    "user {email} delete messages query {query} max_to_delete {max} doit",
    [F("Mailbox", "email"), F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"),
     F("Max to delete", "max", default="100")], destructive=True),
  T("Full incident-response workflow",
    "Runs the complete phishing cleanup in four phases: 1) searches EVERY "
    "mailbox for messages matching From + Subject and saves the evidence "
    "CSV, 2) shows you the hit count and requires typing DELETE to "
    "continue, 3) deletes matches - by exact Message-ID when available "
    "(precise), otherwise by the From+Subject query, 4) pulls Gmail and "
    "Drive audit reports for the lookback window so you can see who "
    "opened, clicked, or downloaded. All evidence lands in a timestamped "
    "Incident folder under Logs. Canceling at the DELETE prompt keeps "
    "the evidence and deletes nothing.",
    "",
    [F("From address e.g. attacker@evil.com", "from"),
     F("Subject text e.g. Compensation Review & Bonus (no quotes needed)",
       "subject"),
     F("Audit lookback days", "days", default="30"),
     F("Max delete per mailbox (seatbelt)", "max", default="5000")],
    destructive=True, workflow=True),
 ],
 "Diagnostics": [
  T("GAM version", "Version, config file, and customer info.", "version", []),
  T("Domain info", "Read-only summary of the Workspace domain.", "info domain", []),
  T("OAuth info", "Which admin GAM runs as and the granted scopes.", "oauth info", []),
 ],
}

# =============================================================================
# SECTION: Command building
# =============================================================================

def quote_if_needed(value):
    # Wrap a value in double quotes when it contains spaces so the command
    # line stays intact. Values already fully quoted are left alone.
    # Embedded quotes are escaped as \" (NOT stripped) so Gmail queries like
    #   from:bad@evil.com subject:"Gift Card"
    # keep their inner quotes when the whole query gets wrapped - the same
    # form GAM expects on the command line.
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        return value
    if " " in value or '"' in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value

def build_command(task, values):
    # Renders the task template into TWO things:
    #   display - a readable command string for the preview box
    #   argv    - the argument LIST actually handed to gam, one element per
    #             argument with NO quoting or escaping (subprocess passes
    #             each element to gam intact)
    # Why argv matters: through v1.3 commands ran through cmd.exe as one
    # string, and cmd treats & | > < ^ as special - an "&" inside a subject
    # line silently CUT THE COMMAND IN HALF at that character. Passing an
    # argument list bypasses the shell so those characters are just text.
    # Template rules:
    #   1. Optional [bracketed] segments are dropped if every {placeholder}
    #      inside them is blank.
    #   2. {a|b} means: use value of 'a' if given, else the literal text
    #      'b' (used for blank password -> uniquerandom).
    # Returns (display, argv, error) - error is a message or empty string.
    template = task["template"]

    def seg_sub(match):
        segment = match.group(0)[1:-1]           # strip the [ ]
        keys = re.findall(r"{(\w+)[^}]*}", segment)
        if any(values.get(k, "").strip() for k in keys):
            return segment                        # keep, will fill below
        return ""                                 # all blank -> drop segment
    rendered = re.sub(r"\[[^\]]*\]", seg_sub, template)

    display_parts = []
    argv = []
    problem = [""]                                # mutable so fill() can set it

    def fill(match):
        # Replaces one {placeholder} inside a token with the form value.
        key, fallback = match.group(1), match.group(2) or ""
        value = values.get(key, "").strip()
        if not value:
            if fallback:
                value = fallback
            else:
                problem[0] = "Missing required value: " + key
        return value

    for token in rendered.split():
        filled = re.sub(r"{(\w+)(?:\|([^}]*))?}", fill, token)
        if problem[0]:
            return "", [], problem[0]
        argv.append(filled)                       # raw - no escaping needed
        display_parts.append(quote_if_needed(filled))

    return " ".join(display_parts), argv, ""


def incident_query(sender, subject):
    # Builds the Gmail search query for the incident workflow.
    # IMPORTANT: subject words are grouped with subject:(...) rather than
    # wrapped in quotes as an exact phrase. Gmail's quoted-phrase matching
    # is strict about exact wording and punctuation, so a subject like
    #   Compensation Review & Bonus
    # quoted often matches NOTHING while the words clearly exist. The
    # parenthesized form makes Gmail require each word (ANDed) and ignore
    # punctuation such as &, which is far more reliable. Discovery stays a
    # little broad on purpose - the workflow then deletes by exact
    # Message-ID, so broad discovery does not mean broad deletion.
    sender = sender.strip()
    subject = subject.strip()
    parts = []
    if sender:
        parts.append("from:" + sender)
    if subject:
        parts.append("subject:(" + subject + ")")
    return " ".join(parts)


def win_split(command_line):
    # Splits a hand-edited command string into an argument list using
    # Windows-style rules: whitespace separates arguments, double quotes
    # group words, \" is a literal quote. Backslashes are otherwise left
    # alone so file paths like C:\Temp\x.png survive intact (which is why
    # shlex in POSIX mode cannot be used here).
    args = []
    current = ""
    in_quotes = False
    index = 0
    while index < len(command_line):
        char = command_line[index]
        if char == "\\" and index + 1 < len(command_line) \
                and command_line[index + 1] == '"':
            current += '"'                        # \" -> literal quote
            index += 2
            continue
        if char == '"':
            in_quotes = not in_quotes             # quotes group, not literal
            index += 1
            continue
        if char in " \t" and not in_quotes:
            if current:
                args.append(current)
                current = ""
            index += 1
            continue
        current += char
        index += 1
    if current:
        args.append(current)
    return args

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

        # ---- session log ----------------------------------------------------
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        self.log_path = os.path.join(LOG_DIR, "GAMGUI_" + stamp + ".log")

        self.output_queue = queue.Queue()   # worker thread -> UI text box
        self.running_proc = None            # currently running gam process
        self.workflow_cancel = False        # set by Stop during the workflow
        self.field_vars = []                # (key, tk variable) of current form
        self.current_task = None

        self._build_layout()
        self._populate_tree()
        self.after(100, self._poll_output)
        self._log("Session start. gam path: " + (self.gam_path or "NOT FOUND"))
        if not self.gam_path:
            self._append_output("WARNING: gam.exe was not found. Use "
                                "Settings > Locate gam.exe.\n")

    # ---- layout -------------------------------------------------------------
    def _build_layout(self):
        # Top bar: gam path display + settings buttons.
        top = ttk.Frame(self, padding=4)
        top.pack(side="top", fill="x")
        self.path_label = ttk.Label(top, text="gam: " + (self.gam_path or "(not found)"))
        self.path_label.pack(side="left")
        ttk.Button(top, text="Locate gam.exe...", command=self._locate_gam).pack(side="right")

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)

        # Left: category/task tree.
        self.tree = ttk.Treeview(main, show="tree", selectmode="browse")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        main.add(self.tree, weight=1)

        # Right: form on top, command preview, output below.
        right = ttk.Frame(main, padding=6)
        main.add(right, weight=3)

        self.desc_label = ttk.Label(right, text="Select a task on the left.",
                                    wraplength=700, justify="left")
        self.desc_label.pack(anchor="w")

        self.form_frame = ttk.Frame(right)
        self.form_frame.pack(fill="x", pady=6)

        preview_bar = ttk.Frame(right)
        preview_bar.pack(fill="x")
        ttk.Label(preview_bar, text="Command preview (editable):").pack(side="left")
        ttk.Button(preview_bar, text="Build", command=self._preview).pack(side="right")
        ttk.Button(preview_bar, text="Copy", command=self._copy).pack(side="right")

        self.preview_box = tk.Text(right, height=3, wrap="word")
        self.preview_box.pack(fill="x", pady=4)

        run_bar = ttk.Frame(right)
        run_bar.pack(fill="x")
        self.run_button = ttk.Button(run_bar, text="Run", command=self._run)
        self.run_button.pack(side="left")
        ttk.Button(run_bar, text="Stop", command=self._stop).pack(side="left", padx=4)
        ttk.Button(run_bar, text="Clear output", command=lambda:
                   self.output_box.delete("1.0", "end")).pack(side="right")

        self.output_box = scrolledtext.ScrolledText(right, height=18, wrap="word",
                                                    state="normal")
        self.output_box.pack(fill="both", expand=True, pady=4)

        # Custom command entry lives as a synthetic tree item (see below).

    def _populate_tree(self):
        for category, tasks in TASKS.items():
            parent = self.tree.insert("", "end", text=category, open=False)
            for index, task in enumerate(tasks):
                self.tree.insert(parent, "end",
                                 text=task["name"],
                                 values=(category, index))
        self.tree.insert("", "end", text="Custom command", values=("__custom__", 0))

    # ---- task selection and form building -----------------------------------
    def _on_select(self, _event):
        item = self.tree.selection()
        if not item:
            return
        vals = self.tree.item(item[0], "values")
        if not vals:                      # category header clicked
            return
        if vals[0] == "__custom__":
            self._show_custom()
            return
        self.current_task = TASKS[vals[0]][int(vals[1])]
        self._show_form(self.current_task)

    def _clear_form(self):
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.field_vars = []

    def _show_form(self, task):
        self._clear_form()
        self.desc_label.config(text=task["name"] + ": " + task["desc"])
        for row, field in enumerate(task["fields"]):
            label = field["label"] + (" *" if field["required"] else "")
            ttk.Label(self.form_frame, text=label).grid(row=row, column=0,
                                                        sticky="w", pady=2)
            var = tk.StringVar(value=field["default"])
            if field["choices"] is not None:
                widget = ttk.Combobox(self.form_frame, textvariable=var,
                                      values=field["choices"], state="readonly",
                                      width=40)
                if field["choices"]:
                    var.set(field["choices"][0] if field["required"] else field["default"])
            else:
                widget = ttk.Entry(self.form_frame, textvariable=var, width=60)
            widget.grid(row=row, column=1, sticky="we", pady=2, padx=6)
            self.field_vars.append((field["key"], var))
        self.form_frame.columnconfigure(1, weight=1)
        self._preview()

    def _show_custom(self):
        self._clear_form()
        self.current_task = None
        self.desc_label.config(
            text="Custom command: type ANY gam command below (without the "
                 "leading 'gam') and press Run. Full syntax reference: "
                 "https://github.com/GAM-team/GAM/wiki  Note: commands run "
                 "without a shell, so pipes (|) and > redirection are not "
                 "available - use GAM's own 'redirect csv ./file.csv' or "
                 "'todrive' instead.")
        self.preview_box.delete("1.0", "end")

    # ---- preview / copy -----------------------------------------------------
    def _collect_values(self):
        return {key: var.get() for key, var in self.field_vars}

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
        # The incident workflow previews its Phase 1 discovery command.
        if self.current_task.get("workflow"):
            v = self._collect_values()
            sender = v.get("from", "").strip()
            subject = v.get("subject", "").strip()
            self.preview_box.delete("1.0", "end")
            if sender and subject:
                query = incident_query(sender, subject)
                self.preview_box.insert(
                    "1.0", "Phase 1: gam redirect csv <Incident folder>\\"
                    "MatchedMessages.csv all users print messages query "
                    + quote_if_needed(query)
                    + "  (then: confirm, delete, audit reports)")
            else:
                self.preview_box.insert(
                    "1.0", "(Missing required value: from/subject)")
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
            self._run_external()
            return
        if not self.gam_path:
            messagebox.showerror(APP_NAME, "gam.exe not found. Use Locate gam.exe.")
            return
        # Workflows run their own multi-step code paths.
        if self.current_task and self.current_task.get("workflow"):
            wf = self.current_task.get("workflow")
            if wf == "shareddrive":
                self._run_move_to_shareddrive()
            elif wf == "transferdrive":
                self._run_transfer_drive()
            elif wf == "archivecourses":
                self._run_archive_courses()
            else:
                self._run_incident_workflow()
            return
        # The mailbox takeover audit runs its own read-only sequence.
        if self.current_task and self.current_task.get("audit"):
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

        self._append_output("\n> " + command_text + "\n")
        self._log("RUN: " + command_text)
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
                    [self.gam_path] + argv,
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
        proc = subprocess.Popen([self.gam_path] + argv,
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
        proc = subprocess.Popen([self.gam_path] + argv, stdout=subprocess.PIPE,
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

    def _run_incident_workflow(self):
        # Native implementation of the email incident-response
        # workflow (originally GAM7-Workspace-Email-Cleanup.bat), built in
        # so it works on any machine GAMGUI is installed on.
        values = self._collect_values()
        sender = values.get("from", "").strip()
        subject = values.get("subject", "").strip()
        days = values.get("days", "30").strip() or "30"
        max_del = values.get("max", "5000").strip() or "5000"
        if not sender or not subject:
            messagebox.showerror(APP_NAME, "From address and Subject are required.")
            return
        if not days.isdigit() or not max_del.isdigit():
            messagebox.showerror(APP_NAME, "Lookback days and max delete must be whole numbers.")
            return

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
                             "Query: " + query]
            try:
                # ---- Phase 1: domain-wide discovery (read-only) ---------
                self.output_queue.put("\n===== PHASE 1: SEARCH ALL MAILBOXES =====\n")
                rc = self._stream_gam(
                    ["redirect", "csv", match_csv, "all", "users",
                     "print", "messages", "query", query,
                     "headers", "from,to,subject,message-id,date"],
                    "discovery")
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

                # ---- Phase 2: typed-DELETE confirmation -----------------
                ok = self._ask_delete_confirm(
                    str(len(hits)) + " message(s) in " + str(len(users))
                    + " mailbox(es) matched:\n\n" + query
                    + "\n\nReview " + match_csv + " first if unsure.")
                if not ok:
                    summary_lines.append("Operator canceled - NO deletions.")
                    self.output_queue.put("\n[canceled at confirmation - "
                                          "evidence kept, nothing deleted]\n")
                    return

                # ---- Phase 3: delete (Message-ID first, query fallback) -
                self.output_queue.put("\n===== PHASE 3: DELETE =====\n")
                if msgids:
                    for mid in sorted(msgids):
                        rc = self._stream_gam(
                            ["all", "users", "delete", "messages", "query",
                             "rfc822msgid:" + mid,
                             "max_to_delete", max_del, "doit"],
                            "delete " + mid)
                        if rc == -1:
                            return
                    summary_lines.append("Deleted by Message-ID: "
                                         + str(len(msgids)) + " id(s).")
                else:
                    rc = self._stream_gam(
                        ["all", "users", "delete", "messages", "query",
                         query, "max_to_delete", max_del, "doit"],
                        "delete by query")
                    if rc == -1:
                        return
                    summary_lines.append("Deleted by From+Subject query "
                                         "(no Message-IDs available).")

                # ---- Phase 4: audit evidence (read-only reports) --------
                self.output_queue.put("\n===== PHASE 4: AUDIT REPORTS =====\n")
                rc = self._stream_gam(
                    ["redirect", "csv", gmail_csv, "report", "gmail",
                     "user", "all", "start", "-" + days + "d",
                     "event", "delivery",
                     "gmaileventtypes", "7,15-19,28,31,32"],
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

    def _stop(self):
        # Tell a running incident workflow not to start its next phase.
        self.workflow_cancel = True
        proc = self.running_proc
        if proc is None:
            return
        self._log("STOP requested by user")
        try:
            if os.name == "nt":
                # IMPORTANT: proc.kill() would only kill the cmd.exe shell
                # wrapper that shell=True creates; gam.exe would keep
                # running underneath it. taskkill with /T kills the whole
                # process TREE (shell + gam + any children); /F forces it.
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
        # Mirror everything into the session log for troubleshooting.
        try:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            pass                      # never let logging crash the UI

    def _log(self, message):
        stamp = datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
        try:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write("[" + stamp + "] " + message + "\n")
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


# =============================================================================
# SECTION: Entry point
# =============================================================================

if __name__ == "__main__":
    app = GamGui()
    app.mainloop()
