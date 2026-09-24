# =============================================================================
# Script:   gam_catalog.py
# Author:   Gabriel Clifton (built with Claude).
# Created:  09-03-2026
# Modified: 09-03-2026
# Version:  1.0
#
# Purpose:
#   Holds the GAM task catalog (TASKS) and the pure, UI-free command-building
#   helpers (build_command, quote_if_needed, incident_query, win_split,
#   translate_license, and the T/F catalog-entry helpers). This module has
#   no tkinter dependency, so both front-ends can share one source of truth:
#     - GAMGUI.py (desktop) imports these names and re-exports them so its
#       GamGui class keeps working unchanged.
#     - gam_web.py (browser front-end) does "import GAMGUI as gg" and reads
#       gg.TASKS, gg.build_command, gg.win_split, gg.incident_query, and
#       gg.translate_license through that re-export.
#
# Notes:
#   - This module performs no I/O and holds no credentials. It only builds
#     command strings/argument lists from the TASKS templates and the values
#     a caller supplies.
# =============================================================================

import re                      # Optional-segment parsing in command templates

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
      workflow=False, audit=False, interactive=False):
    # Tiny helper so the catalog below stays readable.
    # external=True: launches a program in its own console window instead
    #   of running a gam command.
    # workflow=True: runs the built-in multi-phase incident-response
    #   workflow (special code path, not a single template).
    # audit=True: runs the read-only mailbox takeover audit (several
    #   read-only gam commands in sequence, no confirmation needed).
    # interactive=True: the gam command needs a real keyboard and/or a browser
    #   (e.g. oauth create/update), so it is launched in its OWN console window
    #   instead of the captured output pane. Still a normal template, so it
    #   previews and validates like any other task.
    return {"name": name, "desc": desc, "template": template,
            "fields": fields, "destructive": destructive,
            "external": external, "workflow": workflow, "audit": audit,
            "interactive": interactive}

def F(label, key, required=True, choices=None, default="", valuemap=None,
      filepicker=False, rawappend=False):
    # Tiny helper for field definitions.
    # valuemap (optional) maps a friendly DISPLAY name to the value gam wants,
    # e.g. {"Manager": "organizer"}. When set, the dropdown shows the friendly
    # names and the built command uses the mapped gam value.
    # filepicker=True adds a "Browse..." button to pick a local file.
    # rawappend=True marks this as an "Extra arguments (advanced)" free-text
    # box: build_command splits its contents with the same Windows quoting
    # rules used for edited previews (win_split) and appends each token
    # verbatim to the end of the command, letting rare gam flags through
    # without a dedicated widget for every one of them.
    return {"label": label, "key": key, "required": required,
            "choices": choices, "default": default, "valuemap": valuemap,
            "filepicker": filepicker, "rawappend": rawappend}


def _out():
    # The output-destination fields shared by EVERY task that can send its
    # results somewhere (the ones that used to offer only "Send to Google
    # Sheet?"). Splat this into a task's field list with *_out() and put the
    # {todrive} token in the template where the output option belongs.
    #
    # The "todrive" dropdown value (after the GUI/web translate the friendly
    # label) is one of:
    #   ""      -> Screen: print in the window (default, nothing added)
    #   "todrive" -> Google Sheet: gam uploads the results to a Sheet
    #   "csv"   -> CSV file: build_command turns the "csvout" path into a
    #              leading 'redirect csv <path>' so gam writes a local .csv
    # The second field is the CSV path, shown as a Save-As file picker; it is
    # only used when "CSV file on this PC" is chosen.
    return [
        F("Save results to", "todrive", False,
          valuemap={"Screen": "", "Google Sheet": "todrive",
                    "CSV file on this PC": "csv"}),
        F("CSV file to write (only for 'CSV file on this PC')", "csvout",
          False, filepicker="save"),
    ]


def _cros_scope():
    # The device-target fields shared by every BULK Chromebook action. Splat
    # this into a task's field list with *_cros_scope() and put the
    # {crosscope:crostype:crosval} token in the template where the device
    # selector belongs (build_command expands it into the right gam
    # <CrOSTypeEntity>). The dropdown value (after friendly-label translation)
    # is one of: sn / ou / ou_children / query / all. The second field holds
    # the serial list, OU path, or query (blank only when "ALL" is chosen).
    return [
        F("Target devices by", "crostype",
          valuemap={"Serial numbers (comma separated)": "sn",
                    "An OU (devices directly in it)": "ou",
                    "An OU and all its sub-OUs": "ou_children",
                    "A device query (e.g. location:Cart5)": "query",
                    "ALL managed devices": "all"}),
        F("Scope value - serials / OU path / query (blank only for ALL)",
          "crosval", False),
    ]


def _user_scope():
    # The user-target fields shared by every scope-based BULK user action. Splat
    # with *_user_scope() and put the {userscope:usertype:userval} token in the
    # template. The dropdown value (after friendly-label translation) is one of:
    # user / all / ou / ou_children / group / query / csv. The second field holds
    # the user email, OU path, group email, query, or a CSV file:column (blank
    # only for ALL). "A single user" lets the same BULK form serve one person.
    return [
        F("Target users by", "usertype",
          valuemap={"An OU (users directly in it)": "ou",
                    "An OU and all its sub-OUs": "ou_children",
                    "A group's members": "group",
                    "A user query (e.g. orgUnitPath=/Students)": "query",
                    "A CSV column of emails (file:column)": "csv",
                    "A single user (email)": "user",
                    "ALL users in the domain": "all"}),
        F("Scope value - email / OU path / group / query / file:column "
          "(blank only for ALL)", "userval", False),
    ]

TASKS = {
 "OAuth Setup": [
  # Set up or refresh the account GAM runs as. These open a real console
  # window because oauth create/update need a browser sign-in (and GAM's
  # scope menu). Pick a DOMAIN (config section) at the top first to target a
  # separate account; leave it "(default)" for the main one.
  T("Create / authorize a GAM admin account",
    "Authorizes the account GAM runs as - use it to set up GAM for a new "
    "admin, or to re-authorize. Opens a browser: sign in as the account GAM "
    "should act as, then choose the scopes it needs. To set up a SEPARATE "
    "account, first pick its config section in the Domain dropdown at the "
    "top. Runs in its own console window. TIP: on the scope menu, select only "
    "what the account's admin role actually needs, then press c.",
    "oauth create [admin {admin}]",
    [F("Admin email to authorize (optional)", "admin", False),
     F("Extra arguments (advanced, e.g. scopes ...)", "extra", False, rawappend=True)],
    interactive=True),
  T("Update / add scopes to a GAM account",
    "Re-runs authorization to ADD or refresh OAuth scopes for the current "
    "account - for example after a role gained Vault or Chrome rights and "
    "GAM started getting permission errors. Opens a browser; sign in as the "
    "same account. Runs in its own console window.",
    "oauth update [admin {admin}]",
    [F("Admin email (optional)", "admin", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    interactive=True),
  T("Who is GAM authorized as? (oauth info)",
    "Shows which account GAM is currently authorized as, and its scopes. "
    "Read-only.",
    "oauth info [showdetails]",
    [F("Show scope details?", "showdetails", False, choices=["", "showdetails"])]),
  T("Check service account (domain-wide delegation)",
    "Verifies the service account can act as users for the scopes GAM needs - "
    "the check to run after setting up domain-wide delegation.",
    "user {email} check serviceaccount",
    [F("Any user email to test as", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show GAM's service-account keys",
    "Lists the private keys on GAM's service account. The key this PC uses is "
    "marked usedToAuthenticateThisRequest: True. User keys are GAM's; system "
    "keys belong to Google Cloud.",
    "show sakeys {which}",
    [F("Which keys", "which", valuemap={"User keys (GAM's)": "user",
       "All keys": "all", "System keys": "system"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rotate GAM's service-account key (DESTRUCTIVE)",
    "Creates a new private key for GAM's service account and writes it into "
    "oauth2service.json. Choose what happens to the OLD keys: keep them "
    "(safest - other admins or PCs that share this service account keep "
    "working), replace only this PC's key, or delete every other key (anyone "
    "else using a copy of the old file is locked out). If your "
    "oauth2service.json lives on a shared folder, everyone using that folder "
    "gets the new key automatically.",
    "rotate sakey {retain} localkeysize {keysize}",
    [F("Old keys", "retain", valuemap={
       "Keep all existing keys": "retain_existing",
       "Replace only the key this PC uses": "replace_current",
       "Delete every other key": "retain_none"}),
     F("Key size", "keysize", valuemap={"2048 bit (GAM default)": "2048",
       "4096 bit": "4096"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Common Tasks": [
  # A small curated set of the most frequent actions, pinned at the top for
  # quick access and for live demos. These mirror commands that also live in
  # their full categories below; they are duplicated here on purpose for
  # convenience. Each carries an "Extra arguments (advanced)" box (rawappend)
  # so any extra gam flag can be tacked on.
  T("Create user",
    "Creates a new user account. If OU is given the account is created "
    "directly in that OU so campus policies apply immediately.",
    "create user {email} firstname {first} lastname {last} password {password} [ou {ou}] [notify {notify}]",
    [F("New email address", "email"), F("First name", "first"),
     F("Last name", "last"), F("Password", "password"),
     F("OU path e.g. /Staff/Building1 (optional)", "ou", False),
     F("Email credentials to (optional)", "notify", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Reset password",
    "Sets a new password for a user. Leave the password blank to have GAM "
    "generate a random one and email it to the notify address.",
    "update user {email} password {password|uniquerandom} [notify {notify}]",
    [F("User email", "email"), F("New password (blank = random)", "password", False),
     F("Email new password to (optional)", "notify", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Suspend / unsuspend user",
    "Suspending blocks sign-in but keeps all data and licenses. "
    "Unsuspending restores access.",
    "update user {email} suspended {state}",
    [F("User email", "email"), F("Action", "state", choices=["on", "off"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move user to OU",
    "Moves the account to a different OU. Policies of the new OU apply.",
    "update user {email} org {ou}",
    [F("User email", "email"), F("New OU path e.g. /Students/Building1", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("User info",
    "Shows everything about one account: OU, aliases, groups, licenses, "
    "and the unique Google user ID.",
    "info user {email}",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add group member",
    "Adds one address to a group with the chosen role.",
    "update group {group} add {role} {member}",
    [F("Group email", "group"),
     F("Role", "role", choices=["member", "manager", "owner"]),
     F("Member email", "member"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List group members",
    "Shows the full roster of a group.",
    "print group-members group {group}",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export users to CSV/Sheet",
    "Prints users with common fields. Output target 'todrive' creates a "
    "Google Sheet; 'screen' shows results below.",
    "print users fields primaryemail,firstname,lastname,orgunitpath,lastlogintime,suspended {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Users": [
  T("Create user",
    "Creates a new user account. If OU is given the account is created "
    "directly in that OU so campus policies apply immediately.",
    "create user {email} firstname {first} lastname {last} password {password} [ou {ou}] [notify {notify}]",
    [F("New email address", "email"), F("First name", "first"),
     F("Last name", "last"), F("Password", "password"),
     F("OU path e.g. /Staff/Building1 (optional)", "ou", False),
     F("Email credentials to (optional)", "notify", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update user - any attribute (advanced)",
    "The catch-all editor: type any user attribute in the box below. "
    "Examples:  organization title Teacher department Math primary  |  "
    "phone type work value 432-555-0100 primary  |  employeeid 12345  |  "
    "gender female  |  location clear. See the GAM wiki 'Users - Attributes' "
    "page for every attribute. This just runs 'gam update user <email> ...'.",
    "update user {email}",
    [F("User email", "email"),
     F("Attributes to set", "extra", False, rawappend=True)]),
  T("Reset password",
    "Sets a new password for a user. Leave the password blank to have GAM "
    "generate a random one and email it to the notify address.",
    "update user {email} password {password|uniquerandom} [notify {notify}]",
    [F("User email", "email"), F("New password (blank = random)", "password", False),
     F("Email new password to (optional)", "notify", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Suspend / unsuspend user",
    "Suspending blocks sign-in but keeps all data and licenses. "
    "Unsuspending restores access.",
    "update user {email} suspended {state}",
    [F("User email", "email"), F("Action", "state", choices=["on", "off"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move user to OU",
    "Moves the account to a different OU. Policies of the new OU apply.",
    "update user {email} org {ou}",
    [F("User email", "email"), F("New OU path e.g. /Students/Building1", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rename user (display name)",
    "Changes first/last name only. The email address does not change.",
    "update user {email} [firstname {first}] [lastname {last}]",
    [F("User email", "email"), F("New first name (optional)", "first", False),
     F("New last name (optional)", "last", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change primary email",
    "Changes the sign-in address. The old address automatically becomes an "
    "alias so mail to it still arrives.",
    "update user {email} username {newemail}",
    [F("Current email", "email"), F("New email", "newemail"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update job info (title + department)",
    "Sets the primary organization's job title and department together. "
    "NOTE: updating the organization REPLACES the primary organization "
    "record, so provide both fields (blank ones are cleared).",
    "update user {email} organization title {title} department {dept} primary",
    [F("User email", "email"), F("Job title", "title"),
     F("Department", "dept"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set recovery email",
    "Sets the account recovery email address.",
    "update user {email} recoveryemail {recoveryemail}",
    [F("User email", "email"), F("Recovery email address", "recoveryemail"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set recovery phone",
    "Sets the account recovery phone. Must be in E.164 format, e.g. "
    "+14325550100 (plus sign, country code, no spaces or dashes).",
    "update user {email} recoveryphone {recoveryphone}",
    [F("User email", "email"), F("Recovery phone (E.164, e.g. +14325550100)", "recoveryphone"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Hide/show in Global Address List",
    "Hidden users do not appear in the directory when people compose mail.",
    "update user {email} gal {state}",
    [F("User email", "email"), F("Show in GAL?", "state", choices=["off", "on"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Deprovision user (offboarding) (DESTRUCTIVE)",
    "Offboarding cleanup for a leaving user: removes POP/IMAP access, signs "
    "the user out of all sessions, revokes application-specific passwords, "
    "OAuth tokens and backup codes, and turns off 2-Step Verification. Does "
    "NOT delete the account or its data.",
    "user {email} deprovision popimap signout turnoff2sv",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Sign out user (revoke sessions)",
    "Signs the user out of all active web and device sessions. They must "
    "sign in again. Useful after a password reset or suspected compromise.",
    "user {email} signout",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("User info",
    "Shows everything about one account: OU, aliases, groups, licenses, "
    "and the unique Google user ID.",
    "info user {email}",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export users to CSV/Sheet",
    "Prints users with common fields. Output target 'todrive' creates a "
    "Google Sheet; 'screen' shows results below.",
    "print users fields primaryemail,firstname,lastname,orgunitpath,lastlogintime,suspended {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export users - advanced (query / fields / OU)",
    "Prints users you choose. Query examples: orgUnitPath=/Students  |  "
    "isSuspended=True  |  email:jsmith*. Fields is a comma list, e.g. "
    "primaryemail,name,orgunitpath,lastlogintime. Leave fields blank for "
    "the defaults.",
    "print users [query {query}] [fields {fields}] {todrive}",
    [F("Query (optional)", "query", False),
     F("Fields, comma separated (optional)", "fields", False),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Count users by OU",
    "Reports how many users are in each organizational unit.",
    "print usercountsbyorgunit {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Suspended users report - CSV/Sheet",
    "Lists every suspended (locked) account with its OU and last login - useful "
    "for periodic cleanup or deciding which accounts to delete.",
    "print users query isSuspended=True fields primaryemail,name,orgunitpath,lastlogintime {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Dormant / never-signed-in users report - CSV/Sheet",
    "Lists accounts that have NOT signed in since a date you choose (never-used "
    "accounts show a very old last-login) - useful for reclaiming licenses and "
    "security cleanup. Enter the cutoff date as YYYY-MM-DD; accounts last active "
    "before it are listed.",
    "print users query lastLoginTime<{date}T00:00:00Z fields primaryemail,orgunitpath,lastlogintime,suspended {todrive}",
    [F("Not signed in since (YYYY-MM-DD)", "date", default="2025-01-01"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export EVERY address in the domain (users+groups+aliases) - CSV/Sheet",
    "Prints every email address in the domain in one list - user accounts, "
    "groups, and their aliases, each tagged by type. Useful as a complete "
    "address inventory or to check whether a given address exists anywhere.",
    "print addresses {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List pending user invitations - CSV/Sheet",
    "Prints outstanding invitations sent to unmanaged / external accounts to "
    "join the organization that have not been accepted yet - useful for "
    "tracking who still needs to accept, or spotting invitations you did not "
    "expect.",
    "print userinvitations {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete user (DESTRUCTIVE)",
    "Deletes the account. Recoverable with Undelete for about 20 days, "
    "after that everything is gone. Transfer Drive/Calendar data first!",
    "delete user {email}",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Bulk delete users from a CSV (DESTRUCTIVE)",
    "Deletes EVERY user listed in a CSV, one per row. The CSV needs a column of "
    "user email addresses (the column name defaults to 'email'). Accounts are "
    "recoverable with Undelete for about 20 days, then gone - TRANSFER "
    "Drive/Calendar data first, and TEST on a one-row CSV before the whole "
    "list.",
    "csv {file} gam delete user ~{emailcol}",
    [F("CSV file of user emails", "file", filepicker=True),
     F("Column name holding the email", "emailcol", default="email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Undelete user",
    "Restores a user deleted within the last ~20 days.",
    "undelete user {email} [ou {ou}]",
    [F("User email", "email"), F("Restore to OU (optional)", "ou", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # BULK user actions. The scope-based ones apply the SAME change to a whole set
  # of users chosen with the user-scope picker (an OU / OU+children / a group /
  # a query / a CSV column / ALL). The CSV-row ones read a spreadsheet and run a
  # per-user command with PER-ROW values (a different value for each person).
  # ---------------------------------------------------------------------------
  T("BULK: suspend users (by OU / group / query / CSV) (DESTRUCTIVE)",
    "Suspends MANY accounts at once - a fast offboarding / lockout step (e.g. "
    "suspend a whole graduating class OU). Suspended users cannot sign in but "
    "their data is kept. Pick the target set with the scope dropdown.",
    "update users {userscope:usertype:userval} suspended on",
    [*_user_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: unsuspend users (by OU / group / query / CSV)",
    "Re-enables MANY suspended accounts at once (e.g. the returning students in "
    "an OU). Pick the target set with the scope dropdown.",
    "update users {userscope:usertype:userval} suspended off",
    [*_user_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: move users to an OU (by OU / group / query / CSV)",
    "Moves MANY users into a different OU at once - e.g. promoting a grade of "
    "students to next year's OU. Pick the target set, then the destination OU.",
    "update users {userscope:usertype:userval} org {neworg}",
    [*_user_scope(),
     F("Destination OU path e.g. /Students/Grade10", "neworg"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: change users (any attribute) (by OU / group / query / CSV)",
    "Applies the SAME change to MANY users at once. Pick the target set, then "
    "put the change in the advanced box, e.g.  changepasswordatnextlogin on  |  "
    "org /Students/Grade10  |  title Student. This is the power tool - it can "
    "make big changes, so TEST on a small scope first.",
    "update users {userscope:usertype:userval}",
    [*_user_scope(),
     F("Change to apply (advanced) e.g. changepasswordatnextlogin on", "extra",
       rawappend=True)],
    destructive=True),
  T("BULK: create users from a CSV",
    "Creates many accounts in ONE pass from a CSV - the start-of-year way to "
    "stand up a class or a staff list. The CSV needs columns for the email, "
    "first name, last name, and password; column names are case-sensitive. "
    "SECURITY: the CSV holds plaintext passwords - store it somewhere safe and "
    "delete it afterward. Add  changepasswordatnextlogin on  and  org ~OrgUnit  "
    "in the advanced box to force a reset and place accounts in an OU.",
    "csv {file} gam create user ~{emailcol} firstname ~{firstcol} lastname ~{lastcol} password ~{passcol}",
    [F("CSV file", "file", filepicker=True),
     F("Email column header", "emailcol", default="Email"),
     F("First-name column header", "firstcol", default="First"),
     F("Last-name column header", "lastcol", default="Last"),
     F("Password column header", "passcol", default="Password"),
     F("Extra arguments (advanced, e.g. org ~OrgUnit changepasswordatnextlogin on)",
       "extra", False, rawappend=True)]),
  T("BULK: update users from a CSV (per-row values)",
    "Updates many users from a CSV, using a DIFFERENT value per row (unlike the "
    "scope change above, which applies one value to everyone). Reference any "
    "column in the advanced box with a tilde, e.g.  title ~Title  department "
    "~Dept  org ~OrgUnit. The CSV needs an email column to identify each user.",
    "csv {file} gam update user ~{emailcol}",
    [F("CSV file", "file", filepicker=True),
     F("Email column header", "emailcol", default="Email"),
     F("Changes (advanced) e.g. title ~Title org ~OrgUnit", "extra",
       rawappend=True)]),
  # ---------------------------------------------------------------------------
  # Profile photos and invitations to unmanaged (personal) accounts.
  # ---------------------------------------------------------------------------
  T("Download a user's profile photo",
    "Saves a user's profile photo into a folder on this PC.",
    "user {email} get photo targetfolder {folder}",
    [F("User email", "email"),
     F("Folder on this PC", "folder", default="C:\\GAMPhotos"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set a user's profile photo from a file",
    "Uploads an image file (JPG or PNG) as a user's profile photo.",
    "user {email} update photo {file}",
    [F("User email", "email"), F("Photo file", "file", filepicker=True),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a user's profile photo (DESTRUCTIVE)",
    "Removes a user's profile photo.",
    "user {email} delete photo",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: set profile photos from a folder",
    "Sets profile photos for many users at once from a folder of images named "
    "after each user - by default  <email>.jpg  (e.g. jsmith@example.com.jpg). "
    "Change the file-name pattern to match yours; tokens: #email#, #user#, "
    "#username#.",
    "{userscope:usertype:userval} update photo sourcefolder {folder} filename {pattern}",
    [*_user_scope(),
     F("Folder of photos", "folder", default="C:\\GAMPhotos"),
     F("File-name pattern", "pattern", default="#email#.jpg"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Can this address be invited? (unmanaged account check)",
    "Checks whether an email address belongs to an UNMANAGED (personal) Google "
    "account that uses your domain. Such accounts can be invited to join your "
    "organization.",
    "check isinvitable {email}",
    [F("Email address", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Invite an unmanaged account to join the organization",
    "Sends an invitation to an unmanaged (personal) Google account that uses "
    "your domain, so its owner can move it into your organization.",
    "send userinvitation {email}",
    [F("Email address", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Invitation status for an address",
    "Shows the status of an invitation sent to an unmanaged account.",
    "info userinvitation {email}",
    [F("Email address", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Cancel an invitation",
    "Cancels a pending invitation to an unmanaged account.",
    "cancel userinvitation {email}",
    [F("Email address", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show or hide a user in the directory",
    "Controls whether a user appears in the organization's shared directory "
    "(Gmail / Contacts auto-complete and people search) - e.g. hide a "
    "service account or a protected staff member.",
    "user {email} profile {state}",
    [F("User email", "email"),
     F("Directory", "state", valuemap={"Hide from the directory": "unshare",
       "Show in the directory": "share"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Is a user shown in the directory?",
    "Shows whether a user's profile is shared in the organization's "
    "directory.",
    "user {email} show profile",
    [F("User email", "email"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List directory profiles (People API) - CSV/Sheet",
    "Prints the organization's directory profiles as other users see them "
    "(names, emails, phones, titles). Optional query, e.g. a last name.",
    "print people [query {query}] {todrive}",
    [F("Query (optional)", "query", False), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Is a user suspended?",
    "Quick check of whether one account is suspended.",
    "check suspended {email}",
    [F("User email", "email"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Groups": [
  T("Create group",
    "Creates a Google Group (mailing list / access list).",
    "create group {group} [name {name}] [description {desc}]",
    [F("Group email", "group"), F("Display name (optional)", "name", False),
     F("Description (optional)", "desc", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update group name / description / email",
    "Renames a group, changes its description, or changes its email address. "
    "Leave a field blank to leave it unchanged.",
    "update group {group} [name {name}] [description {desc}] [email {newemail}]",
    [F("Group email", "group"), F("New display name (optional)", "name", False),
     F("New description (optional)", "desc", False),
     F("New group email (optional)", "newemail", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update group settings (advanced)",
    "Changes access/posting settings. Type settings in the box, e.g.  "
    "whocanpostmessage ALL_MEMBERS_CAN_POST  |  whocanjoin INVITED_CAN_JOIN  "
    "|  whocanviewgroup ALL_MEMBERS_CAN_VIEW  |  allowexternalmembers true. "
    "See the GAM wiki 'Group Settings' page for all settings.",
    "update group {group}",
    [F("Group email", "group"),
     F("Settings to change", "extra", False, rawappend=True)]),
  T("Add member",
    "Adds one address to a group with the chosen role.",
    "update group {group} add {role} {member}",
    [F("Group email", "group"),
     F("Role", "role", choices=["member", "manager", "owner"]),
     F("Member email", "member"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change member role",
    "Changes an existing member's role (member / manager / owner).",
    "update group {group} update {role} {member}",
    [F("Group email", "group"),
     F("New role", "role", choices=["member", "manager", "owner"]),
     F("Member email", "member"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove member",
    "Removes one address from a group.",
    "update group {group} delete member {member}",
    [F("Group email", "group"), F("Member email", "member"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Sync group from OU (DESTRUCTIVE)",
    "Makes group membership EXACTLY match the users in an OU tree: missing "
    "users are added and anyone else is REMOVED from the group.",
    "update group {group} sync member notsuspended ous_and_children {ou}",
    [F("Group email", "group"), F("OU path e.g. /Staff/Building1", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Sync group members from a CSV (DESTRUCTIVE)",
    "Makes a group's membership EXACTLY match a CSV list of email addresses: "
    "anyone in the CSV who is missing is ADDED, and anyone in the group who is "
    "NOT in the CSV is REMOVED. The CSV needs an email column. TEST first - it "
    "removes members who are not in your list.",
    "update group {group} sync member csvfile {file}:{emailcol}",
    [F("Group email", "group"),
     F("CSV file of member emails", "file", filepicker=True),
     F("Column name holding the email", "emailcol", default="email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Remove ALL members (DESTRUCTIVE)",
    "Empties the group: removes every member, manager, and owner. The group "
    "itself remains.",
    "update group {group} clear member manager owner",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # ---------------------------------------------------------------------------
  # BULK group actions - add/remove many members at once, act on many groups
  # from a CSV, and create/delete groups in bulk. GAM's <UserTypeEntity> lets
  # the member source be a single email, a whole group, an OU, or a CSV column,
  # so those source fields are free-text (tokenized) - type, for example:
  #   jsmith@fsisd.net        (one person)
  #   group staff@fsisd.net   (everyone in a group)
  #   ou /Students/Grade9     (everyone in an OU)
  #   csvfile C:\list.csv:email   (a CSV column)
  # ---------------------------------------------------------------------------
  T("BULK: add members to a group (from a group / OU / CSV) - adds only",
    "Adds many members to ONE group in a single pass, WITHOUT removing anyone "
    "already in it (unlike Sync). Pick the role, then enter the source of "
    "members. Good for topping up a distribution list from a class OU or group.",
    "update group {group} add {role}",
    [F("Group email", "group"),
     F("Add them as", "role", valuemap={"Members": "member",
       "Managers": "manager", "Owners": "owner"}),
     F("Source - email / group <email> / ou <path> / csvfile <file>:<col>",
       "source", rawappend=True)]),
  T("BULK: remove members from a group (from a group / OU / CSV) (DESTRUCTIVE)",
    "Removes many members from ONE group in a single pass. Enter the source of "
    "members to remove (an email, a group, an OU, or a CSV column). Leave the "
    "role as 'Any role' to remove them no matter what role they hold.",
    "update group {group} remove [{role}]",
    [F("Group email", "group"),
     F("Remove from role", "role", required=False, valuemap={"Any role": "",
       "Members": "member", "Managers": "manager", "Owners": "owner"}),
     F("Source - email / group <email> / ou <path> / csvfile <file>:<col>",
       "source", rawappend=True)],
    destructive=True),
  T("BULK: add ONE user to MANY groups (from a CSV of groups)",
    "Adds a single person to every group listed in a CSV column - e.g. dropping "
    "a new staff member into all their distribution lists at once.",
    "update groups csvfile {file}:{groupcol} add {role} {user}",
    [F("CSV file of group emails", "file", filepicker=True),
     F("Column name holding the group emails", "groupcol", default="group"),
     F("Add them as", "role", valuemap={"Members": "member",
       "Managers": "manager", "Owners": "owner"}),
     F("User to add", "user"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: remove ONE user from MANY groups (from a CSV of groups) (DESTRUCTIVE)",
    "Removes a single person from every group listed in a CSV column - e.g. "
    "pulling a departing staff member out of all their lists at once. Leave the "
    "role as 'Any role' to remove them regardless of the role they hold.",
    "update groups csvfile {file}:{groupcol} remove [{role}] {user}",
    [F("CSV file of group emails", "file", filepicker=True),
     F("Column name holding the group emails", "groupcol", default="group"),
     F("Remove from role", "role", required=False, valuemap={"Any role": "",
       "Members": "member", "Managers": "manager", "Owners": "owner"}),
     F("User to remove", "user"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: create groups from a CSV",
    "Creates many groups in ONE pass from a CSV - e.g. a distribution list per "
    "grade or class at the start of the year. The CSV needs a group-email "
    "column and (optionally) a name column; column names are case-sensitive.",
    "csv {file} gam create group ~{emailcol} name ~{namecol}",
    [F("CSV file", "file", filepicker=True),
     F("Group-email column header", "emailcol", default="Email"),
     F("Group-name column header", "namecol", default="Name"),
     F("Extra arguments (advanced, e.g. description ~Description)", "extra",
       False, rawappend=True)]),
  T("BULK: delete groups from a CSV (DESTRUCTIVE)",
    "Deletes every group listed in a CSV column in ONE pass. This cannot be "
    "undone - the groups and their membership lists are gone. TEST your CSV "
    "first.",
    "delete groups csvfile {file}:{groupcol}",
    [F("CSV file of group emails", "file", filepicker=True),
     F("Column name holding the group emails", "groupcol", default="group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List members",
    "Shows the full roster of a group (all roles). Choose Screen, a Google "
    "Sheet, or a CSV file to export it.",
    "print group-members group {group} {todrive}",
    [F("Group email", "group"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List members by ROLE (one or more groups) - CSV/Sheet",
    "Lists the members of ONE group or SEVERAL groups (comma separated), "
    "filtered to the role(s) you pick: just Members, just Managers, just "
    "Owners, or a combination. The output has a 'group' column and a 'role' "
    "column so you can tell which group each person is in and what they are. "
    "Send it to the screen, a Google Sheet, or a CSV file.",
    "print group-members select {groups} roles {role} {todrive}",
    [F("Group(s) - one email, or several comma separated", "groups"),
     F("Which role(s)", "role", valuemap={
       "Members only": "member",
       "Managers only": "manager",
       "Owners only": "owner",
       "Members + Managers": "member,manager",
       "Managers + Owners": "manager,owner",
       "Everyone (all roles)": "member,manager,owner"}),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Group info",
    "Shows a group's settings, aliases, and member counts.",
    "info group {group}",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export all groups",
    "Prints every group in the domain.",
    "print groups {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export all groups + members",
    "Prints every group WITH its members, managers, and owners.",
    "print groups roles members,managers,owners {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("What groups is a user in? (their memberships) - CSV/Sheet",
    "Lists every group ONE user belongs to (and their role in each) - the "
    "everyday help-desk lookup of a person's group memberships. Send it to the "
    "screen, a Google Sheet, or a CSV.",
    "user {email} print groups {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a group's nested tree (sub-groups) - CSV/Sheet",
    "Shows a group's full tree: the groups nested inside it (and inside those), "
    "so you can see the whole membership hierarchy. Give one group or several "
    "(comma separated).",
    "print grouptree {groups} {todrive}",
    [F("Group(s) - one email, or several comma separated", "groups"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete group (DESTRUCTIVE)",
    "Deletes the group itself. Member accounts are not affected.",
    "delete group {group}",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Is a user in a group? (check membership)",
    "Checks whether a user belongs to one or more groups (comma separated), "
    "optionally counting membership through nested groups.",
    "user {email} check groups [{derived}] {groups}",
    [F("User email", "email"), F("Group(s), comma separated", "groups"),
     F("Count membership through nested groups?", "derived", False,
       valuemap={"No": "", "Yes": "includederivedmembership"})]),
  T("A user's membership details in a group",
    "Shows a user's role and email-delivery setting in a group.",
    "user {email} info member {group}",
    [F("User email", "email"), F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # Cloud Identity groups: security groups, dynamic groups (membership by
  # query), locked groups, and memberships that EXPIRE on a date.
  # ---------------------------------------------------------------------------
  T("List groups with Cloud Identity details - CSV/Sheet",
    "Prints groups with Cloud Identity details - security / dynamic / locked "
    "labels and dynamic-group queries. To list only security groups, put in "
    "the advanced box:  query \"'cloudidentity.googleapis.com/groups.security' "
    "in labels\"",
    "print cigroups {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. a query)", "extra", False,
       rawappend=True)]),
  T("Create a security group",
    "Creates a group labeled as a SECURITY group - usable to grant access in "
    "Google Cloud and some apps. Note: a security group can never be changed "
    "back to a plain group.",
    "create cigroup {email} name {name} [description {desc}] makesecuritygroup",
    [F("Group email", "email"), F("Group name", "name"),
     F("Description (optional)", "desc", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a dynamic group (members by query)",
    "Creates a group whose members are kept up to date automatically from a "
    "query on user attributes. Example query:  user.organizations.exists(org, "
    "org.department=='Sales')",
    "create cigroup {email} name {name} dynamic {query}",
    [F("Group email", "email"), F("Group name", "name"),
     F("Membership query", "query"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Make an existing group a security group (DESTRUCTIVE)",
    "Adds the SECURITY label to an existing plain group. This cannot be undone "
    "- a security group cannot go back to a plain group.",
    "update cigroup {group} makesecuritygroup",
    [F("Group email", "group"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Lock or unlock a group",
    "A LOCKED group's membership can only be changed by admins (owners and "
    "managers cannot add or remove people).",
    "update cigroup {group} {lock}",
    [F("Group email", "group"),
     F("Action", "lock", valuemap={"Lock": "locked", "Unlock": "unlocked"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add a member who expires on a date",
    "Adds a user to a group with an expiration - they are removed "
    "automatically at that time (e.g. a contractor or a substitute). Use a "
    "relative time like +90d, or a full time like 2027-06-30T00:00:00Z.",
    "update cigroups {group} add member expire {expire} user {email}",
    [F("Group email", "group"), F("User email", "email"),
     F("Remove them at e.g. +90d or 2027-06-30T00:00:00Z", "expire"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Group info (Cloud Identity view)",
    "Shows a group through the Cloud Identity API - including security / "
    "dynamic / locked labels, the dynamic query, and member expirations.",
    "info cigroups {group}",
    [F("Group email", "group"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List group members with expirations - CSV/Sheet",
    "Prints a group's members through the Cloud Identity API, including when "
    "each membership expires.",
    "print cigroup-members cigroup {group} {todrive}",
    [F("Group email", "group"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Sync a user's groups - exact list (DESTRUCTIVE)",
    "Makes a user's group memberships EXACTLY match the groups you list "
    "(comma separated), with the role you pick: missing groups are joined "
    "and the user is REMOVED from every other group. Limit it to one domain's "
    "groups with the optional domain box.",
    "user {email} sync groups [domain {domain}] {role} {groups}",
    [F("User email", "email"),
     F("Role in these groups", "role", valuemap={"Member": "member",
       "Manager": "manager", "Owner": "owner"}),
     F("Groups, comma separated", "groups"),
     F("Only touch groups in this domain (optional)", "domain", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Aliases": [
  T("Create alias",
    "Adds an extra receive-address to a user or group.",
    "create alias {alias} {kind} {target}",
    [F("Alias address", "alias"),
     F("Target type", "kind", choices=["user", "group", "target"]),
     F("Target email", "target"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete alias",
    "Removes an alias. The target keeps its primary address.",
    "delete alias {alias}",
    [F("Alias address", "alias"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Bulk delete aliases from a CSV (DESTRUCTIVE)",
    "Deletes EVERY alias listed in a CSV, one per row. GAM figures out on its "
    "own whether each is a user or group alias. Point the column name at the "
    "column holding the alias addresses (the 'Alias' column from 'Export all "
    "aliases' works; change it to match your file). The target accounts keep "
    "their primary addresses. TEST on a one-row CSV first.",
    "csv {file} gam delete alias ~{aliascol}",
    [F("CSV file of aliases to delete", "file", filepicker=True),
     F("Column name holding the alias address", "aliascol", default="Alias"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: create aliases from a CSV",
    "Adds many aliases in ONE pass from a CSV - e.g. give everyone a "
    "firstname.lastname@ alias. The CSV needs an alias column and a target "
    "(user email) column; column names are case-sensitive. (For group aliases, "
    "add  target  in place of  user  in the advanced box.)",
    "csv {file} gam create alias ~{aliascol} user ~{usercol}",
    [F("CSV file", "file", filepicker=True),
     F("Alias-address column header", "aliascol", default="Alias"),
     F("Target-user-email column header", "usercol", default="Email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Alias info",
    "Shows what an alias points to.",
    "info alias {alias}",
    [F("Alias address", "alias"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export all aliases",
    "Prints every user and group alias in the domain.",
    "print aliases {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("What is this address?",
    "Tells you whether an address is a user, a group, or an alias.",
    "whatis {email}",
    [F("Email address", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move an alias to another user or group",
    "Moves an existing alias from whoever has it now to a different user or "
    "group in one step (e.g. hand info@ to a new person).",
    "update alias {alias} {ttype} {target}",
    [F("Alias email", "alias"),
     F("Move to", "ttype", valuemap={"A user": "user", "A group": "group"}),
     F("New owner (user or group email)", "target"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Org Units": [
  T("Create OU", "Creates an organizational unit. Use 'buildpath' in the "
    "advanced box to auto-create missing parent OUs.",
    "create org {path} [description {desc}] [parent {parent}]",
    [F("Full OU path e.g. /Students/Building1", "path"),
     F("Description (optional)", "desc", False),
     F("Parent OU (optional)", "parent", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update / rename OU",
    "Renames an OU, changes its description, or moves it under a new parent. "
    "Leave a field blank to leave it unchanged.",
    "update org {path} [name {name}] [description {desc}] [parent {parent}]",
    [F("OU path", "path"), F("New name (optional)", "name", False),
     F("New description (optional)", "desc", False),
     F("New parent OU (optional)", "parent", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show OU tree", "Displays the whole OU hierarchy.",
    "show orgtree",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List OUs (CSV/Sheet)",
    "Prints every organizational unit.",
    "print ous {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move users into OU",
    "Moves the listed users into the target OU. For more than one user, "
    "separate with commas and NO spaces.",
    "update org {path} move users {users}",
    [F("Target OU path e.g. /Students/Building1", "path"),
     F("User email(s), comma separated no spaces", "users"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete OU (DESTRUCTIVE)",
    "Deletes an OU. It must be empty (no users/devices) first.",
    "delete org {path}",
    [F("OU path", "path"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: create OUs from a CSV",
    "Creates many organizational units in ONE pass from a CSV - e.g. one per "
    "grade, campus, or department at the start of the year. The CSV needs a "
    "column of full OU paths (like /Students/Grade9). Add 'buildpath' in the "
    "advanced box to auto-create any missing parent OUs.",
    "csv {file} gam create org ~{pathcol}",
    [F("CSV file", "file", filepicker=True),
     F("OU-path column header", "pathcol", default="OrgUnit"),
     F("Extra arguments (advanced, e.g. buildpath)", "extra", False,
       rawappend=True)]),
  T("BULK: delete OUs from a CSV (DESTRUCTIVE)",
    "Deletes every OU whose path is listed in a CSV column. Each OU must be "
    "empty (no users or devices) first. This cannot be undone - TEST your CSV.",
    "csv {file} gam delete org ~{pathcol}",
    [F("CSV file", "file", filepicker=True),
     F("OU-path column header", "pathcol", default="OrgUnit"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("OU info (details and users)",
    "Shows an OU's details and the users in it. Add  children  in the advanced "
    "box to include sub-OUs, or  nousers  to skip the user list.",
    "info org {path}",
    [F("OU path e.g. /Sales", "path"),
     F("Extra arguments (advanced, e.g. children)", "extra", False,
       rawappend=True)]),
  T("Is this OU empty? (check before deleting)",
    "Checks an OU for users, Chromebooks, browsers, Shared Drives, and sub-OUs "
    "and reports whether it is empty - run it before deleting an OU.",
    "check ou {path} {todrive}",
    [F("OU path e.g. /Old/Unused", "path"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Domains & Domain Aliases": [
  T("Domain info",
    "Shows details for a domain. Leave blank to show the primary domain.",
    "info domain [{domain}]",
    [F("Domain name (optional)", "domain", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List domains",
    "Prints all domains in the account.",
    "print domains {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add secondary domain",
    "Adds a secondary domain. You must still verify ownership (DNS) in the "
    "Admin console before it can be used.",
    "create domain {domain}",
    [F("Domain name to add", "domain"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete domain (DESTRUCTIVE)",
    "Removes a secondary domain from the account.",
    "delete domain {domain}",
    [F("Domain name", "domain"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Add domain alias",
    "Adds a domain alias that mirrors addresses of an existing domain.",
    "create domainalias {alias} {domain}",
    [F("New domain alias", "alias"), F("Existing (target) domain", "domain"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete domain alias (DESTRUCTIVE)",
    "Removes a domain alias.",
    "delete domainalias {alias}",
    [F("Domain alias", "alias"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List domain aliases",
    "Prints all domain aliases.",
    "print domainaliases {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Get a domain verification token",
    "Gets the DNS record (or file) Google needs to prove you own a domain - "
    "the first step after 'Add a domain'. Put the record it prints in your "
    "DNS, then run 'Verify a domain'.",
    "create verify {domain}",
    [F("Domain", "domain"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Verify a domain",
    "Asks Google to check the verification record you added. Pick the method "
    "you used.",
    "update verify {domain} {method}",
    [F("Domain", "domain"),
     F("Verification method", "method", valuemap={"DNS TXT record": "txt",
       "DNS CNAME record": "cname", "HTML file on the website": "file",
       "Meta tag on the website": "site"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List verified sites and domains",
    "Shows the sites and domains GAM's admin has verified with Google Site "
    "Verification.",
    "info verify",
    [     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Domain alias info",
    "Shows a domain alias's details and verification status.",
    "info domainalias {alias}",
    [F("Domain alias", "alias"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Make a domain the primary domain (DESTRUCTIVE)",
    "Changes the organization's PRIMARY domain to another verified domain - "
    "a major change (it affects the admin console, new accounts, and more). "
    "Read Google's guidance on changing the primary domain first.",
    "update domain {domain} primary",
    [F("Domain (must already be verified)", "domain"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Chromebooks": [
  T("Device info by serial",
    "Full detail for one Chromebook found by its serial number.",
    "cros_sn {serial} info",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move device to OU",
    "Moves a Chromebook to another OU so different policies apply.",
    "cros_sn {serial} update ou {ou}",
    [F("Serial number", "serial"), F("New OU path e.g. /Students/Building1", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update device (asset tag / user / location / notes)",
    "Sets the device's annotated fields. Leave a field blank to leave it "
    "unchanged.",
    "cros_sn {serial} update [asset {assetid}] [user {user}] [location {location}] [notes {notes}]",
    [F("Serial number", "serial"),
     F("Asset tag (optional)", "assetid", False),
     F("Assigned user (optional)", "user", False),
     F("Location (optional)", "location", False),
     F("Notes (optional)", "notes", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Disable / re-enable device",
    "Disable locks a lost or stolen Chromebook; re-enable releases it.",
    "cros_sn {serial} update action {action}",
    [F("Serial number", "serial"),
     F("Action", "action", choices=["disable", "reenable"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Deprovision device (retire) (DESTRUCTIVE)",
    "Removes the Chromebook from management (retiring it / disposal). This "
    "frees the license. It cannot be undone without re-enrolling.",
    "cros_sn {serial} update action deprovision_retiring_device acknowledge_device_touch_requirement",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Reboot device",
    "Remotely reboots an enrolled, online Chromebook.",
    "cros_sn {serial} issuecommand command reboot doit",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Take a screenshot",
    "Captures a screenshot from an enrolled, online Chromebook.",
    "cros_sn {serial} issuecommand command take_a_screenshot doit",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set device volume",
    "Sets the speaker volume (0-100) on an enrolled, online Chromebook.",
    "cros_sn {serial} issuecommand command set_volume {volume} doit",
    [F("Serial number", "serial"), F("Volume 0-100", "volume", default="50"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Powerwash device (DESTRUCTIVE)",
    "Factory-resets the Chromebook remotely. All local data is wiped. "
    "The device stays enrolled.",
    "cros_sn {serial} issuecommand command remote_powerwash times_to_check_status 10 doit",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Wipe users from device (DESTRUCTIVE)",
    "Removes all user profiles from the device but keeps enrollment.",
    "cros_sn {serial} issuecommand command wipe_users doit",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Export devices to CSV/Sheet",
    "Prints the fleet with the most useful fields.",
    "print cros fields serialnumber,ou,status,lastsync,annotateduser,annotatedassetid {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Find devices (query)",
    "Prints devices matching a query, e.g.  sync:..  |  status:provisioned  "
    "|  asset_id:12345  |  user:jsmith. See the CrOS query help.",
    "print cros query {query} {todrive}",
    [F("Query e.g. status:deprovisioned", "query"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Device activity report",
    "Prints recent-user and network activity for the fleet.",
    "print crosactivity {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Telemetry report (battery/CPU/network/storage) - CSV/Sheet",
    "Prints hardware telemetry for the fleet: battery health, CPU/memory use, "
    "network signal, storage, and more. Great for spotting devices with dying "
    "batteries or low disk space. Send it to the screen, a Google Sheet, or a "
    "CSV.",
    "print crostelemetry {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Devices needing attention - CSV/Sheet",
    "Prints the Chromebooks Google flags as needing attention (for example not "
    "syncing or with an unsupported OS) - a quick daily/weekly health check for "
    "the fleet.",
    "print chromeneedsattn {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("ChromeOS version report (patch compliance) - CSV/Sheet",
    "Prints how many devices are on each ChromeOS version - useful for checking "
    "the fleet is up to date and spotting devices stuck on an old build.",
    "print chromeversions {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Device counts (by OU / model / version) - CSV/Sheet",
    "Prints a summary count of Chromebooks broken down by organizational unit, "
    "model, and ChromeOS version - a quick way to size the fleet per campus or "
    "see how many of each model you have.",
    "print chromedevicecounts {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List enrolled Chrome BROWSERS (not Chromebooks) - CSV/Sheet",
    "Prints Chrome browsers enrolled in Chrome Browser Cloud Management - the "
    "managed Chrome on Windows/Mac PCs, which is separate from the Chromebook "
    "devices above. Only returns rows if your organization enrolls browsers in "
    "CBCM.",
    "print browsers {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Auto-Update Expiration (AUE) dates - CSV/Sheet",
    "Prints the Auto-Update Expiration date for each Chromebook model in the "
    "fleet - the date after which Google stops shipping ChromeOS updates for "
    "that model. Essential for planning device retirement and budgeting "
    "replacements before models go end-of-life.",
    "print chromeaues {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Check serial number validity (enrollable?) - CSV/Sheet",
    "Checks Chromebook serial numbers and reports whether Google recognizes "
    "each one as a valid, enrollable device - handy when receiving new devices "
    "or chasing down a serial that will not enroll. Enter one serial or several "
    "separated by commas.",
    "print chromesnvalidity cros_sn {serials} {todrive}",
    [F("Serial number(s), comma separated", "serials"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Who used this Chromebook last?",
    "Shows recent users and networks for a device.",
    "cros_sn {serial} info recentusers lastknownnetwork",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # BULK device actions. Each targets MANY Chromebooks at once via the device
  # scope selector (serials / an OU / an OU + children / a query / ALL). The
  # single-device tasks above use cros_sn <one serial>; these use the same
  # underlying gam commands but let you pick a whole cart, OU, or query.
  # ---------------------------------------------------------------------------
  T("BULK: move devices to an OU",
    "Moves MANY Chromebooks into a different OU at once - e.g. re-homing a "
    "whole cart or a campus of devices at the start of the year. Choose which "
    "devices with the scope dropdown, then the destination OU.",
    "{crosscope:crostype:crosval} update ou {newou}",
    [*_cros_scope(),
     F("Destination OU path e.g. /Chromebooks/FSHS/Library", "newou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: set device fields (asset tag / user / location / notes)",
    "Sets the annotated fields on MANY Chromebooks at once - e.g. stamp a whole "
    "cart with the same location. Leave a field blank to leave it unchanged. "
    "(To set a DIFFERENT asset tag per device, use the CSV task below instead.)",
    "{crosscope:crostype:crosval} update [asset {assetid}] [user {user}] [location {location}] [notes {notes}]",
    [*_cros_scope(),
     F("Asset tag (optional)", "assetid", False),
     F("Assigned user (optional)", "user", False),
     F("Location (optional)", "location", False),
     F("Notes (optional)", "notes", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: update asset tags from a CSV",
    "Reads a CSV with a serial-number column and an asset-tag column and stamps "
    "each device with its tag in ONE pass - the fast way to import an inventory "
    "spreadsheet. Column names are case-sensitive; defaults are 'SerialNumber' "
    "and 'AssetTag'.",
    "csv {file} gam update cros cros_sn ~{serialcol} asset ~{assetcol}",
    [F("CSV file", "file", filepicker=True),
     F("Serial-number column header", "serialcol", default="SerialNumber"),
     F("Asset-tag column header", "assetcol", default="AssetTag"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: disable / re-enable devices",
    "Disable locks MANY lost or stolen Chromebooks at once (e.g. a whole cart "
    "or query); re-enable releases them. Choose the devices with the scope "
    "dropdown.",
    "{crosscope:crostype:crosval} update action {action}",
    [*_cros_scope(),
     F("Action", "action", choices=["disable", "reenable"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: deprovision devices (retire) (DESTRUCTIVE)",
    "Removes MANY Chromebooks from management at once (retiring / disposal), "
    "freeing their licenses - e.g. deprovisioning an end-of-life model. This "
    "CANNOT be undone without re-enrolling each device. Add 'maxtodeprov "
    "<number>' in the advanced box to cap how many it will touch as a safety "
    "limit.",
    "{crosscope:crostype:crosval} update action deprovision_retiring_device acknowledge_device_touch_requirement",
    [*_cros_scope(),
     F("Extra arguments (advanced, e.g. maxtodeprov 50)", "extra", False,
       rawappend=True)],
    destructive=True),
  T("BULK: reboot devices",
    "Remotely reboots MANY enrolled, online Chromebooks at once - e.g. a whole "
    "cart. Offline devices are skipped.",
    "{crosscope:crostype:crosval} issuecommand command reboot doit",
    [*_cros_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: powerwash devices (DESTRUCTIVE)",
    "Factory-resets MANY enrolled Chromebooks at once. All local data on each "
    "device is wiped; the devices stay enrolled. Use the scope dropdown to pick "
    "which devices.",
    "{crosscope:crostype:crosval} issuecommand command remote_powerwash times_to_check_status 10 doit",
    [*_cros_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: wipe users from devices (DESTRUCTIVE)",
    "Removes all user profiles from MANY devices at once but keeps them "
    "enrolled - e.g. clearing a cart between users. Local user data on each "
    "device is lost.",
    "{crosscope:crostype:crosval} issuecommand command wipe_users doit",
    [*_cros_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Download device files (logs / screenshots)",
    "Downloads the files a Chromebook has uploaded (support logs, "
    "screenshots) into a folder on this PC - the newest one per device by "
    "default. Works on one device or a whole scope.",
    "{crosscope:crostype:crosval} get devicefile select last {count} targetfolder {folder}",
    [*_cros_scope(),
     F("How many of the newest files per device", "count", default="1"),
     F("Folder on this PC", "folder", default="C:\\GAMExports"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Device telemetry (battery, storage, CPU, memory)",
    "Shows a Chromebook's telemetry - battery health, storage, CPU, memory, "
    "network, and more. Limit it with field names in the advanced box, e.g. "
    " batteryinfo batterystatusreport",
    "info crostelemetry {serial}",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, e.g. batteryinfo)", "extra", False,
       rawappend=True)]),
  T("Get the result of a device command",
    "Shows the status and result of a remote command (reboot, screenshot, "
    "powerwash...) sent to a Chromebook. The command ID is printed when the "
    "command is sent.",
    "cros_sn {serial} getcommand commandid {commandid}",
    [F("Serial number", "serial"), F("Command ID", "commandid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Count devices in a scope",
    "Shows how many Chromebooks match - an OU, a query, or serial numbers.",
    "{crosscope:crostype:crosval} show count",
    [*_cros_scope(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Chrome Browsers & Policies": [
  # ---------------------------------------------------------------------------
  # Chrome Browser Cloud Management (managed Chrome browsers on Windows / Mac /
  # Linux), managed Chrome profiles, installed apps/extensions, and Chrome
  # policies (the settings under Devices > Chrome in the Admin console).
  # 'List Chrome browsers' lives under Chromebooks.
  # ---------------------------------------------------------------------------
  T("Chrome browser info",
    "Shows one managed Chrome browser (machine name, OS, Chrome version, last "
    "user, policies). Get the device ID from 'List Chrome browsers' under "
    "Chromebooks.",
    "info browser {deviceid} {detail}",
    [F("Browser device ID", "deviceid"),
     F("Detail", "detail", valuemap={"Basic": "basic", "Full": "full",
       "Annotated fields only (asset ID, location, notes, user)": "annotated"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move Chrome browsers to an OU",
    "Moves managed Chrome browsers to another OU so different policies apply. "
    "Pick them by device IDs (comma separated), a browser query, or the OU "
    "they are in now.",
    "move browsers ou {ou} {seltype} {selval}",
    [F("Move TO this OU", "ou"),
     F("Pick browsers by", "seltype", valuemap={
       "Device IDs (comma separated)": "ids",
       "A browser query (e.g. machine_name:LAB-*)": "queries",
       "The OU they are in now": "browserou"}),
     F("Device IDs / query / current OU", "selval"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update a Chrome browser's asset ID / location / notes / user",
    "Sets the annotated fields on a managed Chrome browser (the same fields as "
    "a Chromebook's asset tag and location). Fill in only what you want to "
    "change.",
    "update browser {deviceid} [assetid {assetid}] [location {location}] [notes {notes}] [user {user}]",
    [F("Browser device ID", "deviceid"),
     F("Asset ID (optional)", "assetid", False),
     F("Location (optional)", "location", False),
     F("Notes (optional)", "notes", False),
     F("User (optional)", "user", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a Chrome browser (DESTRUCTIVE)",
    "Removes a browser from Chrome Browser Cloud Management. It stops "
    "receiving your policies until it is enrolled again.",
    "delete browser {deviceid}",
    [F("Browser device ID", "deviceid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create a browser enrollment token",
    "Creates a token used to enroll Chrome browsers into management (deployed "
    "to machines by GPO/registry or MDM). Browsers enrolled with it land in "
    "the OU you choose. Treat the token like a password.",
    "create browsertoken [ou {ou}] [expire {expire}]",
    [F("OU for enrolled browsers (optional, blank = top level)", "ou", False),
     F("Expires (optional) e.g. +90d or 2027-06-30T00:00:00Z", "expire",
       False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List browser enrollment tokens - CSV/Sheet",
    "Prints your Chrome browser enrollment tokens with their OU, state, and "
    "expiration.",
    "print browsertokens {todrive}",
    [*_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Revoke a browser enrollment token (DESTRUCTIVE)",
    "Revokes an enrollment token so it can no longer enroll browsers "
    "(already-enrolled browsers stay enrolled). Use the token's permanent ID "
    "from 'List browser enrollment tokens'.",
    "revoke browsertoken {tokenid}",
    [F("Token permanent ID", "tokenid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List managed Chrome profiles - CSV/Sheet",
    "Prints managed Chrome profiles (a signed-in work profile in Chrome on any "
    "computer) with user, OS, Chrome version, and last activity. Optional "
    "filter e.g. osPlatformType=WINDOWS",
    "print chromeprofiles [filter {filter}] {todrive}",
    [F("Filter (optional)", "filter", False), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Chrome profile info",
    "Shows one managed Chrome profile. Use the profile ID from 'List managed "
    "Chrome profiles'.",
    "info chromeprofile {profile}",
    [F("Profile ID", "profile"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a managed Chrome profile (DESTRUCTIVE)",
    "Deletes a managed Chrome profile record.",
    "delete chromeprofile {profile}",
    [F("Profile ID", "profile"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Send a command to a Chrome profile (clear cache / cookies)",
    "Sends a remote command to a managed Chrome profile: clear its cache, "
    "clear its cookies, or check for extension updates.",
    "create chromeprofilecommand {profile} {command}",
    [F("Profile ID", "profile"),
     F("Command", "command", valuemap={"Clear cache": "clearcache",
       "Clear cookies": "clearcookies",
       "Check for extension updates": "extensionupdatecheck"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a Chrome profile's command results",
    "Shows the remote commands sent to a Chrome profile and their results.",
    "show chromeprofilecommands {profile}",
    [F("Profile ID", "profile"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List installed Chrome apps & extensions - CSV/Sheet",
    "Prints every Chrome app and extension installed on managed devices and "
    "browsers, with install counts and permissions - a quick extension audit. "
    "Optionally limit it to an OU and its sub-OUs.",
    "print chromeapps [ou_and_children {ou}] {todrive}",
    [F("OU (optional, includes sub-OUs)", "ou", False), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Which devices have an app / extension installed - CSV/Sheet",
    "Prints the devices and browsers that have one app or extension "
    "installed - e.g. find every machine with a risky extension.",
    "print chromeappdevices appid {appid} apptype {apptype} [ou_and_children {ou}] {todrive}",
    [F("App / extension ID", "appid"),
     F("Type", "apptype", valuemap={"Extension": "extension",
       "Chrome app": "app", "Theme": "theme", "Hosted app": "hostedapp",
       "Android app": "androidapp"}),
     F("OU (optional, includes sub-OUs)", "ou", False), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Chrome app / extension info",
    "Shows details about an app or extension from the Chrome Web Store, "
    "Google Play, or a web app (name, permissions, publisher).",
    "info chromeapp {apptype} {appid}",
    [F("Where it comes from", "apptype", valuemap={
       "Chrome Web Store (extension / app)": "chrome",
       "Google Play (Android app)": "android", "Web app": "web"}),
     F("App / extension ID", "appid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show Chrome policies for an OU - CSV/Sheet",
    "Prints the Chrome policies that apply to an OU (the settings under "
    "Devices > Chrome). Optional filter narrows it, e.g. chrome.users.* or "
    "chrome.devices.*",
    "print chromepolicies ou {ou} [filter {filter}] {todrive}",
    [F("OU path", "ou"), F("Filter (optional) e.g. chrome.users.*", "filter",
       False), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set a Chrome policy for an OU",
    "Sets one Chrome policy setting for an OU. Find the schema and field names "
    "with 'Look up Chrome policy schemas'. Example: schema "
    "chrome.users.UserPrintersAllowed  field userPrintersAllowed  value false. "
    "Add more  field value  pairs in the advanced box.",
    "update chromepolicy {schema} {field} {value} ou {ou}",
    [F("Policy schema e.g. chrome.users.UserPrintersAllowed", "schema"),
     F("Field e.g. userPrintersAllowed", "field"),
     F("Value e.g. false", "value"),
     F("OU path", "ou"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove a Chrome policy from an OU (inherit again) (DESTRUCTIVE)",
    "Deletes an OU's own setting for a Chrome policy so it inherits the "
    "parent OU's value again.",
    "delete chromepolicy {schema} ou {ou}",
    [F("Policy schema e.g. chrome.users.UserPrintersAllowed", "schema"),
     F("OU path", "ou"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Look up Chrome policy schemas",
    "Lists the Chrome policy schemas (the names used by 'Set a Chrome policy'). "
    "Optional filter e.g. chrome.users.* or chrome.devices.*",
    "show chromeschemas [filter {filter}]",
    [F("Filter (optional) e.g. chrome.users.*", "filter", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Chrome policy schema details",
    "Shows one Chrome policy schema: its fields, allowed values, and "
    "description.",
    "info chromeschema {schema}",
    [F("Policy schema e.g. chrome.users.UserPrintersAllowed", "schema"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Upload a wallpaper / avatar image for Chrome policy",
    "Uploads an image for a Chrome wallpaper or avatar policy. GAM prints a "
    "value to use when you set the matching policy.",
    "create chromepolicyimage {schema} {file}",
    [F("Image for", "schema", valuemap={
       "User wallpaper": "chrome.users.wallpaper",
       "User avatar": "chrome.users.avatar",
       "Sign-in screen wallpaper": "chrome.devices.signinwallpaperimage",
       "Managed guest wallpaper": "chrome.devices.managedguest.wallpaper",
       "Managed guest avatar": "chrome.devices.managedguest.avatar"}),
     F("Image file", "file", filepicker=True),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a Chrome network (Wi-Fi / Ethernet / VPN) from JSON",
    "Creates a managed network for an OU from a JSON file that describes it "
    "(the same settings as Devices > Networks in the Admin console).",
    "create chromenetwork {ou} {name} json file {file}",
    [F("OU path", "ou"), F("Network name", "name"),
     F("JSON file", "file", filepicker=True),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a Chrome network (DESTRUCTIVE)",
    "Deletes a managed network from an OU.",
    "delete chromenetwork {ou} {networkid}",
    [F("OU path", "ou"), F("Network ID", "networkid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Chrome version history - CSV/Sheet",
    "Prints Google's Chrome version history for a platform and channel - "
    "useful when planning updates or checking what is current.",
    "print chromehistory versions platform {platform} channel {channel} {todrive}",
    [F("Platform", "platform", valuemap={"Windows 64-bit": "win64",
       "Windows 32-bit": "win", "Mac": "mac", "Mac (Apple silicon)": "macarm64",
       "Linux": "linux", "Android": "android", "iOS": "ios", "All": "all"}),
     F("Channel", "channel", valuemap={"Stable": "stable", "Beta": "beta",
       "Dev": "dev", "Canary": "canary"}),
     *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Gmail": [
  T("Show delegates", "Lists who can open this mailbox as a delegate.",
    "user {email} show delegates",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export delegates (whole domain)",
    "Prints every mailbox's delegates across the domain to CSV/Sheet.",
    "all users print delegates {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add delegate",
    "Gives another user full mailbox access without sharing the password.",
    "user {email} add delegate {delegate}",
    [F("Mailbox", "email"), F("Delegate email", "delegate"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove delegate", "Revokes delegate access.",
    "user {email} delete delegate {delegate}",
    [F("Mailbox", "email"), F("Delegate email", "delegate"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Enable forwarding",
    "Registers the destination and turns forwarding on; a copy stays in "
    "the mailbox (keep).",
    "user {email} add forwardingaddress {dest}",
    [F("Mailbox", "email"), F("Forward to", "dest"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Turn forwarding on (after registering)",
    "Second step: activates forwarding to an already-registered address.",
    "user {email} forward on keep {dest}",
    [F("Mailbox", "email"), F("Forward to", "dest"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Turn forwarding off", "Stops forwarding for the mailbox.",
    "user {email} forward off",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show forwarding addresses",
    "Lists the forwarding addresses registered on a mailbox.",
    "user {email} show forwardingaddresses",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Forwarding address info",
    "Shows the status (pending/accepted) of one registered forwarding address.",
    "user {email} info forwardingaddress {dest}",
    [F("Mailbox", "email"), F("Forwarding address", "dest"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a forwarding address (DESTRUCTIVE)",
    "Removes a registered forwarding address from a mailbox. If it was the "
    "active forwarding target, forwarding stops.",
    "user {email} delete forwardingaddress {dest}",
    [F("Mailbox", "email"), F("Forwarding address", "dest"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Export forwarding addresses (whole domain)",
    "Prints every mailbox's registered forwarding addresses across the domain "
    "to CSV/Sheet - useful for spotting unexpected auto-forwarding.",
    "all users print forwardingaddresses {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Is mail being auto-forwarded out? (security check)",
    "Shows whether a mailbox has automatic forwarding turned ON and, if so, "
    "where it sends copies. Compromised accounts are often set to quietly "
    "forward a copy of every email to an outside address - this is the fastest "
    "way to check one mailbox.",
    "user {email} show forward",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Check auto-forwarding for EVERYONE (security sweep) - CSV/Sheet",
    "Prints the auto-forwarding setting for every mailbox in the domain - who "
    "has forwarding ON and the destination. Run this after a phishing incident "
    "to catch any account quietly forwarding mail to an outsider.",
    "all users print forward {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a mailbox's vacation / auto-reply",
    "Shows whether a mailbox has an out-of-office / vacation auto-reply turned "
    "on and its message - handy when someone reports odd auto-replies or you "
    "are cleaning up after an account issue.",
    "user {email} show vacation",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Who has auto-reply ON? (whole domain) - CSV/Sheet",
    "Prints every mailbox that currently has a vacation / out-of-office "
    "auto-reply turned ON, with the reply message - useful for catching stale "
    "auto-replies or an auto-reply an attacker set on a compromised account.",
    "all users print vacation enabledonly {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add send-as address",
    "Adds a 'send mail as' identity to the mailbox.",
    "user {email} add sendas {sendas} name {name}",
    [F("Mailbox", "email"), F("Send-as address", "sendas"),
     F("Display name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete send-as address",
    "Removes a 'send mail as' identity.",
    "user {email} delete sendas {sendas}",
    [F("Mailbox", "email"), F("Send-as address", "sendas"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show send-as addresses",
    "Lists the mailbox's send-as identities.",
    "user {email} show sendas",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update send-as (name / signature) (advanced)",
    "Changes an existing send-as identity: its display name, and (in the "
    "advanced box) its signature or default flag, e.g.  signature \"...\"  or  "
    "default  or  replyto boss@ex.com.",
    "user {email} update sendas {sendas} name {name}",
    [F("Mailbox", "email"), F("Send-as address", "sendas"),
     F("Display name", "name"),
     F("Extra arguments (advanced, e.g. signature ...)", "extra", False, rawappend=True)]),
  T("Send-as info",
    "Shows the settings of one send-as identity (name, signature, verified).",
    "user {email} info sendas {sendas}",
    [F("Mailbox", "email"), F("Send-as address", "sendas"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set vacation responder",
    "Turns on an automatic reply. Dates are YYYY-MM-DD (Google's format).",
    "user {email} vacation on subject {subject} message {message} [startdate {start}] [enddate {end}]",
    [F("Mailbox", "email"), F("Subject", "subject"), F("Message", "message"),
     F("Start date YYYY-MM-DD (optional)", "start", False),
     F("End date YYYY-MM-DD (optional)", "end", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Vacation responder off", "Turns the automatic reply off.",
    "user {email} vacation off",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set signature", "Replaces the mailbox signature (plain text or HTML).",
    "user {email} signature {signature}",
    [F("Mailbox", "email"), F("Signature text", "signature"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create filter",
    "Creates a Gmail filter. Fill any of the criteria (from / subject / "
    "words), and it applies the chosen label. For other actions (archive, "
    "markread, star, trash, forward) use the advanced box.",
    "user {email} create filter [from {from}] [subject {subject}] [haswords {haswords}] label {label}",
    [F("Mailbox", "email"), F("From (optional)", "from", False),
     F("Subject contains (optional)", "subject", False),
     F("Has the words (optional)", "haswords", False),
     F("Apply label", "label"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show filters",
    "Lists a mailbox's Gmail filters and their IDs.",
    "user {email} show filters",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete filter",
    "Deletes a filter by its ID (get the ID from Show filters).",
    "user {email} delete filters {filterid}",
    [F("Mailbox", "email"), F("Filter ID", "filterid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create label",
    "Creates a Gmail label in the mailbox.",
    "user {email} create label {label}",
    [F("Mailbox", "email"), F("Label name", "label"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete label",
    "Deletes a Gmail label from the mailbox.",
    "user {email} delete label {label}",
    [F("Mailbox", "email"), F("Label name", "label"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show labels",
    "Lists the mailbox's Gmail labels.",
    "user {email} show labels",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Turn IMAP on/off",
    "Enables or disables IMAP access for the mailbox.",
    "user {email} imap {state}",
    [F("Mailbox", "email"), F("IMAP", "state", choices=["on", "off"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Turn POP on/off",
    "Enables or disables POP access for the mailbox.",
    "user {email} pop {state}",
    [F("Mailbox", "email"), F("POP", "state", choices=["on", "off"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export IMAP access status (whole domain) - CSV/Sheet",
    "Prints whether IMAP is enabled for every mailbox in the domain - a "
    "security-posture check, since IMAP is a common way older/less-secure mail "
    "clients (and some attackers) keep connecting to a mailbox.",
    "all users print imap {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export POP access status (whole domain) - CSV/Sheet",
    "Prints whether POP is enabled for every mailbox in the domain - the POP "
    "companion to the IMAP report above, for the same security review.",
    "all users print pop {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set mailbox language",
    "Sets the Gmail display language, e.g. en, es, fr.",
    "user {email} language {lang}",
    [F("Mailbox", "email"), F("Language code e.g. en, es", "lang"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a user's language setting - CSV/Sheet",
    "Shows the account's language setting - handy when a user reports their "
    "account is showing the wrong language and you want to confirm what it is "
    "set to before changing it.",
    "user {email} print language {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a user's Gmail profile (message/thread counts) - CSV/Sheet",
    "Shows account-level Gmail info for a mailbox - total message and thread "
    "counts and the email address - a quick way to gauge how full a mailbox is "
    "or confirm the account is active.",
    "user {email} print gmailprofile {todrive}",
    [F("Mailbox", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Search messages (preview)",
    "Shows matching messages WITHOUT touching them. Always run this "
    "before any delete. Query syntax = Gmail search box.",
    "user {email} show messages query {query}",
    [F("Mailbox", "email"), F("Gmail query e.g. from:x subject:y", "query"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Trash messages (DESTRUCTIVE)",
    "Moves matching messages to Trash (recoverable ~30 days). The max "
    "limit is a seatbelt against a bad query.",
    "user {email} trash messages query {query} max_to_trash {max} doit",
    [F("Mailbox", "email"), F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"),
     F("Max messages to trash", "max", default="25"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # ---------------------------------------------------------------------------
  # BULK Gmail actions - apply the SAME setting to MANY mailboxes at once,
  # chosen with the user-scope picker (an OU / OU+children / a group / a query /
  # a CSV column / ALL). Great for district-wide signatures, summer auto-replies,
  # and security cleanup.
  # ---------------------------------------------------------------------------
  T("BULK: set email signature for many users",
    "Sets the SAME email signature on every mailbox in the chosen scope - e.g. "
    "roll out a district-standard footer to all staff. You can use HTML. To "
    "personalize per user, add replace tags in the advanced box, e.g.  replace "
    "NAME '&{name}'  (see the GAM signature wiki), or point at a file with  "
    "file C:\\sig.html  instead of typing text.",
    "{userscope:usertype:userval} signature {sig}",
    [*_user_scope(),
     F("Signature text (HTML allowed)", "sig"),
     F("Extra arguments (advanced, e.g. replace TAG value)", "extra", False,
       rawappend=True)]),
  T("BULK: set vacation / auto-reply for many users",
    "Turns ON an out-of-office auto-reply with the same subject and message for "
    "every mailbox in the chosen scope - e.g. a summer-break reply for all "
    "staff. Add  startdate <date> enddate <date>  in the advanced box to limit "
    "when it runs.",
    "{userscope:usertype:userval} vacation on subject {subject} message {message}",
    [*_user_scope(),
     F("Subject", "subject"),
     F("Message (HTML allowed)", "message"),
     F("Extra arguments (advanced, e.g. startdate 2027-06-01)", "extra", False,
       rawappend=True)]),
  T("BULK: turn OFF vacation / auto-reply for many users",
    "Turns the auto-reply OFF for every mailbox in the chosen scope - e.g. clear "
    "the summer reply for all staff when school resumes.",
    "{userscope:usertype:userval} vacation off",
    [*_user_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: turn OFF auto-forwarding for many users (security)",
    "Turns automatic forwarding OFF for every mailbox in the chosen scope - the "
    "remediation step after a phishing incident, to stop any accounts quietly "
    "forwarding mail out. Pair it with 'Check auto-forwarding for EVERYONE' to "
    "find them first.",
    "{userscope:usertype:userval} forward off",
    [*_user_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: add a delegate to many mailboxes",
    "Gives one person delegate access (they can read/send as the mailbox) to "
    "every mailbox in the chosen scope - e.g. give a front-office assistant "
    "access to a set of shared mailboxes.",
    "{userscope:usertype:userval} delegate to {delegate}",
    [*_user_scope(),
     F("Delegate email (who gets access)", "delegate"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: remove a delegate from many mailboxes (DESTRUCTIVE)",
    "Removes one person's delegate access from every mailbox in the chosen "
    "scope - e.g. revoking a departing assistant's access everywhere at once.",
    "{userscope:usertype:userval} delete delegate {delegate}",
    [*_user_scope(),
     F("Delegate email (whose access to remove)", "delegate"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # ---------------------------------------------------------------------------
  # More message actions (restore, spam, labels, forward, export, import),
  # label management, and sending mail. Test a query with 'Search messages
  # (preview)' first. The max boxes are seatbelts against a bad query.
  # ---------------------------------------------------------------------------
  T("Restore (untrash) messages",
    "Moves messages that match a Gmail query OUT of the Trash and back into "
    "the mailbox - e.g. undo an accidental cleanup. Example query: in:trash "
    "from:boss@example.com",
    "user {email} untrash messages query {query} max_to_untrash {max} doit",
    [F("Mailbox", "email"),
     F("Gmail query e.g. in:trash from:boss@example.com", "query"),
     F("Max messages to restore", "max", default="100"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Mark messages as spam (DESTRUCTIVE)",
    "Moves every message that matches a Gmail query into Spam.",
    "user {email} spam messages query {query} max_to_spam {max} doit",
    [F("Mailbox", "email"),
     F("Gmail query e.g. from:bad@evil.com", "query"),
     F("Max messages to mark", "max", default="25"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Add or remove a label on matching messages",
    "Adds a label to, or removes one from, every message that matches a Gmail "
    "query. Tips: to mark messages READ, remove the label UNREAD; to archive "
    "them, remove the label INBOX.",
    "user {email} modify messages query {query} max_to_modify {max} doit {labelaction} {label}",
    [F("Mailbox", "email"),
     F("Gmail query e.g. from:news@example.com", "query"),
     F("Action", "labelaction", valuemap={"Add this label": "addlabel",
       "Remove this label": "removelabel"}),
     F("Label name e.g. Newsletters, UNREAD, INBOX", "label"),
     F("Max messages to change", "max", default="100"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Forward matching messages to someone",
    "Forwards every message that matches a Gmail query to another address - "
    "e.g. send a departed user's invoices to the business office.",
    "user {email} forward messages to {recipient} query {query} max_to_forward {max} doit",
    [F("Mailbox (forward FROM)", "email"),
     F("Forward TO (email)", "recipient"),
     F("Gmail query e.g. subject:invoice", "query"),
     F("Max messages to forward", "max", default="25"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export matching messages to .eml files",
    "Saves every message that matches a Gmail query as a .eml file in a folder "
    "on this PC - handy for an investigation or a records request.",
    "user {email} export messages query {query} max_to_export {max} doit targetfolder {folder}",
    [F("Mailbox", "email"),
     F("Gmail query e.g. from:attacker@evil.com", "query"),
     F("Folder on this PC to save into", "folder", default="C:\\GAMExports"),
     F("Max messages to export", "max", default="100"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Import a message from a file into a mailbox",
    "Imports a message saved as an .eml file (e.g. from 'Export matching "
    "messages') into a mailbox - useful for restoring a message. Optionally put it under a "
    "label.",
    "user {email} import message emlfile {file} [addlabel {label}]",
    [F("Mailbox to import into", "email"),
     F("Message file (.eml)", "file", filepicker=True),
     F("Label to add (optional)", "label", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rename a Gmail label",
    "Renames one label in a mailbox; messages keep the label under its new "
    "name.",
    "user {email} update labelsettings {label} name {newname}",
    [F("Mailbox", "email"), F("Current label name", "label"),
     F("New label name", "newname"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rename or merge labels by pattern (advanced)",
    "Renames every label whose name matches a pattern (a regular expression); "
    "%s in the replacement is the matched part. Add  merge  in the advanced "
    "box to merge into labels that already exist. Example: pattern ^Old/(.*)$ "
    " replacement New/%s",
    "user {email} update labels search {search} replace {replace}",
    [F("Mailbox", "email"),
     F("Match pattern (regex) e.g. ^Old/(.*)$", "search"),
     F("Replacement e.g. New/%s", "replace"),
     F("Extra arguments (advanced, e.g. merge)", "extra", False,
       rawappend=True)]),
  T("Send an email as a user",
    "Sends an email FROM a user's mailbox to one or more recipients (comma "
    "separated). Add  html  in the advanced box for an HTML body, or  cc  / "
    "bcc  addresses.",
    "user {sender} sendemail to {recipient} subject {subject} message {message}",
    [F("Send FROM (mailbox)", "sender"),
     F("Send TO (email, or several comma separated)", "recipient"),
     F("Subject", "subject"), F("Message", "message"),
     F("Extra arguments (advanced, e.g. cc x@example.com html)", "extra",
       False, rawappend=True)]),
  T("BULK: email many users (one message each)",
    "Sends the same message TO every user in the chosen scope, FROM an address "
    "you pick - e.g. an announcement to all staff. Add  html  in the advanced "
    "box for an HTML body.",
    "{userscope:usertype:userval} sendemail from {sender} subject {subject} message {message}",
    [*_user_scope(),
     F("Send FROM (address)", "sender"),
     F("Subject", "subject"), F("Message", "message"),
     F("Extra arguments (advanced, e.g. html)", "extra", False,
       rawappend=True)]),
  T("Show a user's signature",
    "Shows a user's current Gmail signature.",
    "user {email} show signature",
    [F("User email", "email"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Gmail filter details",
    "Shows one Gmail filter in full - its criteria and actions. Get the ID "
    "from 'Show filters'.",
    "user {email} info filters {filterid}",
    [F("User email", "email"), F("Filter ID", "filterid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a draft in a user's mailbox",
    "Puts a ready-to-send draft in a user's Drafts folder (they review and "
    "send it themselves).",
    "user {email} draft message to {to} subject {subject} message {message}",
    [F("Mailbox", "email"), F("To (email)", "to"), F("Subject", "subject"),
     F("Message", "message"),
     F("Extra arguments (advanced, e.g. cc x@example.com)", "extra", False,
       rawappend=True)]),
  T("Archive messages into a Google Group",
    "Copies messages that match a Gmail query from a mailbox into a Google "
    "Group's archive - e.g. move an old shared mailbox's history into a "
    "collaborative-inbox group.",
    "user {email} archive messages {group} query {query} max_to_archive {max} doit",
    [F("Mailbox", "email"), F("Group email", "group"),
     F("Gmail query e.g. before:2026/01/01", "query"),
     F("Max messages", "max", default="1000"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Calendars": [
  # --- Calendar sharing (ACLs) - admin form, works on any calendar ---
  T("Who can access a calendar? (sharing)",
    "Lists the sharing (ACL) entries. Calendar ID is usually an email.",
    "calendars {cal} show acls",
    [F("Calendar ID (usually an email address)", "cal"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Grant calendar access",
    "Shares a calendar with a person, group, or the whole domain at the "
    "chosen level.",
    "calendars {cal} add acls {role} {scope} sendnotifications false",
    [F("Calendar ID (usually an email address)", "cal"),
     F("Access level", "role", valuemap={"See only free/busy (hide details)": "freebusy",
       "See all event details": "reader", "Make changes to events": "writer",
       "Make changes and manage sharing": "owner"}),
     F("Share with (email, or group:addr / domain:dom / domain / default)", "scope"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change calendar access level",
    "Changes an existing sharing entry to a different access level.",
    "calendars {cal} update acls {role} {scope}",
    [F("Calendar ID", "cal"),
     F("New access level", "role", valuemap={"See only free/busy (hide details)": "freebusy",
       "See all event details": "reader", "Make changes to events": "writer",
       "Make changes and manage sharing": "owner"}),
     F("Who (email / group:addr / domain:dom)", "scope"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove calendar access (DESTRUCTIVE)",
    "Revokes a person's, group's, or domain's access to the calendar.",
    "calendars {cal} delete acls {scope}",
    [F("Calendar ID", "cal"), F("Who to remove (email / group:addr / domain:dom)", "scope"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Export calendar sharing (CSV/Sheet)",
    "Prints all sharing (ACL) entries for a calendar.",
    "calendars {cal} print acls {todrive}",
    [F("Calendar ID", "cal"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Who can access a user's calendar? (ACLs) - CSV/Sheet",
    "Starts from the PERSON: lists who has been granted access to a user's "
    "calendar and at what level - useful for checking who can see, for example, "
    "an administrator's or principal's calendar. Leave the calendar as 'primary' "
    "for their main calendar, or enter another calendar ID they own.",
    "user {email} print calendaracls {cal} {todrive}",
    [F("User email", "email"),
     F("Calendar (usually 'primary')", "cal", default="primary"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a user's calendar settings (timezone etc) - CSV/Sheet",
    "Prints a user's calendar settings - time zone, date/time format, week "
    "start day, working hours, and more. Handy when someone reports their "
    "calendar is in the wrong time zone.",
    "user {email} print calsettings {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a user's out-of-office / working location / focus time",
    "Shows a user's Calendar status entries. Pick which kind: out-of-office "
    "(when they are away), working location (home/office/where they are working "
    "from), or focus time (blocks marked heads-down).",
    "user {email} print {kind}",
    [F("User email", "email"),
     F("Which", "kind", choices=["outofoffice", "workinglocation", "focustime"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- Bulk sharing changes across MANY calendars from a CSV ---
  # These read a whole column of calendar IDs from a CSV in ONE gam run (fast),
  # instead of one gam per row. IMPORTANT: pick a Domain (config section) at the
  # top that is an OWNER of these calendars - usually your OWN account's
  # section, NOT the default GAM account, which is typically not an owner and
  # will get "not found / forbidden" on every row.
  T("Bulk REMOVE calendar access from a CSV (DESTRUCTIVE)",
    "Removes ONE person's, group's, or domain's access from EVERY calendar "
    "listed in a CSV. The CSV needs a column of calendar IDs; the 'id' column "
    "produced by 'List a user's calendars' works as-is. FIRST pick the Domain "
    "at the top that owns these calendars. TEST on a one-row CSV before running "
    "the whole list - removing access cannot be undone except by re-granting "
    "it. NOTE: Google will NOT let you remove your OWN access ('Cannot change "
    "your own access level') - only another owner can remove you. To just get "
    "calendars out of your own list, use 'Bulk show/hide calendars' below "
    "instead.",
    "calendars csvfile {file}:{idcol} delete acls {scope}",
    [F("CSV file of calendar IDs", "file", filepicker=True),
     F("Column name holding the calendar ID", "idcol", default="id"),
     F("Who to remove (your email / group:addr / domain:dom)", "scope"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Bulk GRANT calendar access from a CSV",
    "Shares EVERY calendar listed in a CSV with one person, group, or domain "
    "at the chosen level, in one run. The CSV needs a column of calendar IDs. "
    "FIRST pick the Domain at the top that owns these calendars. Test on a "
    "one-row CSV first.",
    "calendars csvfile {file}:{idcol} add acls {role} {scope} sendnotifications false",
    [F("CSV file of calendar IDs", "file", filepicker=True),
     F("Column name holding the calendar ID", "idcol", default="id"),
     F("Access level", "role", valuemap={"See only free/busy (hide details)": "freebusy",
       "See all event details": "reader", "Make changes to events": "writer",
       "Make changes and manage sharing": "owner"}),
     F("Share with (email / group:addr / domain:dom / domain / default)", "scope"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Bulk show/hide calendars in a user's list from a CSV",
    "Shows or hides MANY calendars in one user's list at once by looping over a "
    "CSV of calendar IDs - the reliable way to declutter. Example: you were "
    "added as owner to hundreds of Classroom calendars and Google won't let you "
    "drop your own ownership; set Hide = Yes and Show = No to get them all out "
    "of your list (reversible any time). This changes ONLY how the calendars "
    "look in THAT user's list - it does not touch ownership or anyone else. "
    "Runs fine under the default account (it acts as the user you name). The CSV "
    "needs a column of calendar IDs; set the column name below to match your "
    "file (e.g. 'id' from 'List a user's calendars', or 'calendarId'). MAKE "
    "SURE the CSV does not include the user's OWN primary calendar, or it will "
    "be hidden too.",
    "csv {file} gam user {email} update calendars ~{idcol} [selected {selected}] [hidden {hidden}] [color {color}]",
    [F("User email (whose list)", "email"),
     F("CSV file of calendar IDs", "file", filepicker=True),
     F("Column name holding the calendar ID", "idcol", default="id"),
     F("Show in their list?", "selected", False,
       valuemap={"": "", "Yes - show it": "true", "No - leave unshown": "false"}),
     F("Hide from their list?", "hidden", False,
       valuemap={"": "", "Yes - hide it": "true", "No - keep visible": "false"}),
     F("Color (optional)", "color", False, valuemap={
       "": "", "Tomato": "tomato", "Flamingo": "flamingo", "Tangerine": "tangerine",
       "Pumpkin": "pumpkin", "Mango": "mango", "Banana": "banana", "Citron": "citron",
       "Avocado": "avocado", "Pistachio": "pistachio", "Basil": "basil",
       "Eucalyptus": "eucalyptus", "Sage": "sage", "Peacock": "peacock",
       "Cobalt": "cobalt", "Blueberry": "blueberry", "Lavender": "lavender",
       "Wisteria": "wisteria", "Amethyst": "amethyst", "Grape": "grape",
       "Radicchio": "radicchio", "Cherry Blossom": "cherryblossom", "Cocoa": "cocoa",
       "Graphite": "graphite", "Birch": "birch"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Transfer a calendar to another user",
    "Transfers ownership of a user's SECONDARY calendar to another user "
    "(the new owner gets full control). Primary calendars cannot be "
    "transferred.",
    "calendars {cal} transfer {target}",
    [F("Calendar ID to transfer", "cal"), F("New owner email", "target"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- Events on a calendar ---
  T("Add event",
    "Adds an event to a calendar. Put the time and attendees in the advanced "
    "box, e.g.  start 2027-06-01T09:00:00-05:00 end 2027-06-01T10:00:00-05:00 "
    "attendee jsmith@ex.com  (times need a time zone: Z for UTC or an offset "
    "like -05:00). For an all-day event: start allday 2027-06-01 end allday "
    "2027-06-02.",
    "calendars {cal} add event summary {summary}",
    [F("Calendar ID", "cal"), F("Event title (summary)", "summary"),
     F("Time / attendees (advanced)", "extra", False, rawappend=True)]),
  T("List events",
    "Prints events; use dates to narrow the window (YYYY-MM-DD).",
    "calendars {cal} print events [after {after}] [before {before}] fields summary,start,end",
    [F("Calendar ID", "cal"), F("After date (optional)", "after", False),
     F("Before date (optional)", "before", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update event(s) (advanced)",
    "Changes events. In the advanced box, name the event(s) then the changes, "
    "e.g.  events id:<eventId> summary \"New title\"  or  events query "
    "\"old title\" location \"Room 5\".",
    "calendars {cal} update events",
    [F("Calendar ID", "cal"),
     F("Event selector + changes (see example)", "extra", False, rawappend=True)]),
  T("Delete event(s) (DESTRUCTIVE)",
    "Deletes events. In the advanced box, name the event(s), e.g.  events "
    "id:<eventId>  or  events query \"Fire Drill\".",
    "calendars {cal} delete events",
    [F("Calendar ID", "cal"),
     F("Event selector (see example)", "extra", False, rawappend=True)],
    destructive=True),
  T("Remove an event from EVERYONE's calendar (phishing invite) (DESTRUCTIVE)",
    "Deletes a calendar event from the PRIMARY calendar of every user (or a "
    "narrower scope) - built for a phishing or spam calendar invite. It matches "
    "by the ORGANIZER'S email (the address that sent the invite), so it clears "
    "every copy of that invite at once. This cannot be undone. Default scope is "
    "ALL users; narrow it to run faster.",
    "{mailscope:scopetype:scopeval} delete events primary matchfield organizeremail {organizer} doit",
    [F("Organizer/sender email of the invite", "organizer"),
     F("Scope", "scopetype", valuemap={"All users": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Move event(s) to another calendar (advanced)",
    "Moves events to a different calendar. In the advanced box: name the "
    "event(s) then the destination, e.g.  events id:<eventId> to "
    "othercal@ex.com.",
    "calendars {cal} move events",
    [F("Source calendar ID", "cal"),
     F("Event selector + 'to <calendar>' (see example)", "extra", False, rawappend=True)]),
  T("Wipe ALL events from a calendar (DESTRUCTIVE)",
    "Deletes EVERY event on the calendar. The calendar itself remains.",
    "calendars {cal} wipe events",
    [F("Calendar ID", "cal"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Empty a calendar's trash (DESTRUCTIVE)",
    "Permanently removes events already in the calendar's trash.",
    "calendars {cal} empty calendartrash",
    [F("Calendar ID", "cal"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # --- A user's calendar LIST (subscribe, show/hide, color) ---
  T("Add a calendar to a user's list",
    "Subscribes a user to another calendar (adds it to their list). Optionally "
    "set it shown/hidden right away.",
    "user {email} add calendars {cal} [selected {selected}] [hidden {hidden}]",
    [F("User email", "email"), F("Calendar ID to add", "cal"),
     F("Show in their calendar list?", "selected", False,
       valuemap={"": "", "Yes - show it": "true", "No - leave unshown": "false"}),
     F("Hide from their list?", "hidden", False,
       valuemap={"": "", "Yes - hide it": "true", "No - keep visible": "false"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show / hide or recolor a calendar in a user's list",
    "Changes how a calendar appears in a user's list: show it or not, hide it "
    "or not, and its color (the 24 named colors Google Calendar offers).",
    "user {email} update calendars {cal} [selected {selected}] [hidden {hidden}] [color {color}]",
    [F("User email", "email"), F("Calendar ID", "cal"),
     F("Show in their calendar list?", "selected", False,
       valuemap={"": "", "Yes - show it": "true", "No - leave unshown": "false"}),
     F("Hide from their list?", "hidden", False,
       valuemap={"": "", "Yes - hide it": "true", "No - keep visible": "false"}),
     F("Color (optional)", "color", False, valuemap={
       "": "", "Tomato": "tomato", "Flamingo": "flamingo", "Tangerine": "tangerine",
       "Pumpkin": "pumpkin", "Mango": "mango", "Banana": "banana", "Citron": "citron",
       "Avocado": "avocado", "Pistachio": "pistachio", "Basil": "basil",
       "Eucalyptus": "eucalyptus", "Sage": "sage", "Peacock": "peacock",
       "Cobalt": "cobalt", "Blueberry": "blueberry", "Lavender": "lavender",
       "Wisteria": "wisteria", "Amethyst": "amethyst", "Grape": "grape",
       "Radicchio": "radicchio", "Cherry Blossom": "cherryblossom", "Cocoa": "cocoa",
       "Graphite": "graphite", "Birch": "birch"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove a calendar from a user's list",
    "Unsubscribes the user from a calendar (removes it from their list). Does "
    "NOT delete the calendar.",
    "user {email} delete calendars {cal}",
    [F("User email", "email"), F("Calendar ID", "cal"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # ---------------------------------------------------------------------------
  # BULK calendar-list actions - subscribe / unsubscribe / show-hide a calendar
  # for MANY users at once, chosen with the user-scope picker (OU / group /
  # query / CSV / ALL). Great for pushing a shared calendar (e.g. district
  # events) onto every staff member's list.
  # ---------------------------------------------------------------------------
  T("BULK: subscribe many users to a calendar",
    "Adds a shared calendar to the calendar list of every user in the chosen "
    "scope - e.g. subscribe all staff to the district events calendar. Enter "
    "the calendar's ID (usually its email address).",
    "{userscope:usertype:userval} add calendars {cal} [selected {selected}] [hidden {hidden}]",
    [*_user_scope(),
     F("Calendar ID to add (usually an email)", "cal"),
     F("Show in their calendar list?", "selected", False,
       valuemap={"": "", "Yes - show it": "true", "No - leave unshown": "false"}),
     F("Hide from their list?", "hidden", False,
       valuemap={"": "", "Yes - hide it": "true", "No - keep visible": "false"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: unsubscribe many users from a calendar (DESTRUCTIVE)",
    "Removes a calendar from the calendar list of every user in the chosen "
    "scope. Does NOT delete the calendar itself - it just unsubscribes them.",
    "{userscope:usertype:userval} delete calendars {cal}",
    [*_user_scope(),
     F("Calendar ID to remove (usually an email)", "cal"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: show / hide / recolor a calendar for many users",
    "Changes how a calendar appears in the lists of every user in the chosen "
    "scope - show it, hide it, or set its color. Handy after subscribing a group "
    "to a calendar, to make sure it is visible for everyone.",
    "{userscope:usertype:userval} update calendars {cal} [selected {selected}] [hidden {hidden}] [color {color}]",
    [*_user_scope(),
     F("Calendar ID", "cal"),
     F("Show in their calendar list?", "selected", False,
       valuemap={"": "", "Yes - show it": "true", "No - leave unshown": "false"}),
     F("Hide from their list?", "hidden", False,
       valuemap={"": "", "Yes - hide it": "true", "No - keep visible": "false"}),
     F("Color (optional)", "color", False, valuemap={
       "": "", "Tomato": "tomato", "Flamingo": "flamingo", "Tangerine": "tangerine",
       "Pumpkin": "pumpkin", "Mango": "mango", "Banana": "banana", "Citron": "citron",
       "Basil": "basil", "Sage": "sage", "Peacock": "peacock", "Cobalt": "cobalt",
       "Blueberry": "blueberry", "Lavender": "lavender", "Grape": "grape",
       "Graphite": "graphite", "Birch": "birch"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Calendar info (in a user's list)",
    "Shows the settings of one calendar as it appears in a user's list.",
    "user {email} info calendars {cal}",
    [F("User email", "email"), F("Calendar ID", "cal"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's calendars (CSV/Sheet)",
    "Prints the calendars in a user's calendar list.",
    "user {email} print calendars {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- A user's own (secondary) calendars ---
  T("Create a secondary calendar (for a user)",
    "Creates a new calendar the user owns. Add description/location/timezone "
    "in the advanced box, e.g.  description \"Team\" timezone America/Chicago.",
    "user {email} create calendar summary {summary}",
    [F("User email (owner)", "email"), F("Calendar name (summary)", "summary"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Modify a calendar's settings (advanced)",
    "Changes a calendar the user owns: summary/description/location/timezone. "
    "Put the changes in the advanced box, e.g.  summary \"New name\" timezone "
    "America/Chicago.",
    "user {email} modify calendars {cal}",
    [F("User email (owner)", "email"), F("Calendar ID", "cal"),
     F("Settings to change (see example)", "extra", False, rawappend=True)]),
  T("Delete a secondary calendar (DESTRUCTIVE)",
    "Permanently DELETES a calendar the user owns (not just unsubscribes). "
    "Primary calendars cannot be deleted.",
    "user {email} remove calendars {cal}",
    [F("User email (owner)", "email"), F("Calendar ID to delete", "cal"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Show a user's calendar settings",
    "Shows the user's Calendar app settings (time zone, working hours, etc.).",
    "user {email} show calsettings",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # Attendee swaps, purging, and out-of-office / working location / focus time.
  # ---------------------------------------------------------------------------
  T("Swap an attendee on events (replace one person with another) (DESTRUCTIVE)",
    "Finds the events on a user's calendar that include one attendee and "
    "replaces that attendee with another - e.g. a new hire takes over a "
    "departing employee's recurring meetings. Test on one calendar first.",
    "user {email} update calattendees {cal} matchfield attendees {old} replace {old} {new} doit",
    [F("Calendar owner", "email"),
     F("Calendar (usually 'primary')", "cal", default="primary"),
     F("Attendee to replace (old)", "old"), F("New attendee", "new"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Purge specific events permanently (DESTRUCTIVE)",
    "Permanently deletes the events you select, skipping the calendar's trash "
    "so they cannot be restored. You MUST say which events, e.g.  query "
    "\"Old Meeting\"  or  eventid <id>  - this task refuses to run without a "
    "selection, because GAM would otherwise purge EVERY event on the calendar.",
    "user {email} purge events {cal}",
    [F("Calendar owner", "email"),
     F("Calendar (usually 'primary')", "cal", default="primary"),
     F("Which events (required) e.g. query \"Old Meeting\"", "which",
       rawappend=True)],
    destructive=True),
  T("Import an event by iCalUID (advanced)",
    "Imports an event into a calendar, keyed by its iCalUID (used when "
    "migrating events). Put the event details in the Event details box, e.g.  "
    "summary \"Board Meeting\" start 2027-01-05T09:00:00-06:00 end "
    "2027-01-05T10:00:00-06:00  (times need a time zone: Z for UTC or an "
    "offset like -06:00)",
    "user {email} import event {cal} icaluid {icaluid}",
    [F("Calendar owner", "email"),
     F("Calendar (usually 'primary')", "cal", default="primary"),
     F("iCalUID", "icaluid"),
     F("Event details (required, see example)", "details", rawappend=True)]),
  T("Create an out-of-office block",
    "Adds an Out of office entry to a user's calendar for a date range and, "
    "optionally, auto-declines invitations during it.",
    "user {email} create outofoffice range {start} {end} declinemode {decline} [declinemessage {msg}] noreminders",
    [F("User email", "email"),
     F("Start date (YYYY-MM-DD)", "start"), F("End date (YYYY-MM-DD)", "end"),
     F("Decline invitations during it?", "decline", valuemap={"No": "none",
       "Decline new invitations": "new",
       "Decline all (new and existing)": "all"}),
     F("Decline message (optional)", "msg", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set a user's working location",
    "Sets where a user is working - home, an office, or a custom place - for a "
    "date range. Coworkers see it in Calendar.",
    "user {email} create workinglocation {loctype} [{locname}] range {start} {end} noreminders",
    [F("User email", "email"),
     F("Location type", "loctype", valuemap={"Home": "home",
       "Office": "office", "Custom place": "custom"}),
     F("Office or place name (not needed for Home)", "locname", False),
     F("Start date (YYYY-MM-DD)", "start"), F("End date (YYYY-MM-DD)", "end"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create focus time",
    "Blocks focus time on a user's calendar between two times and optionally "
    "declines meetings during it. Times need a time zone, e.g. "
    "2027-01-05T09:00:00-06:00 (or end with Z for UTC).",
    "user {email} create focustime timerange {start} {end} declinemode {decline} noreminders",
    [F("User email", "email"),
     F("Start time e.g. 2027-01-05T09:00:00-06:00", "start"),
     F("End time e.g. 2027-01-05T11:00:00-06:00", "end"),
     F("Decline meetings during it?", "decline", valuemap={"No": "none",
       "Decline new invitations": "new",
       "Decline all (new and existing)": "all"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove out-of-office / working location / focus time (DESTRUCTIVE)",
    "Removes a user's out-of-office, working-location, or focus-time entries "
    "within a date range.",
    "user {email} delete {kind} range {start} {end}",
    [F("User email", "email"),
     F("Which", "kind", valuemap={"Out of office": "outofoffice",
       "Working location": "workinglocation", "Focus time": "focustime"}),
     F("Start date (YYYY-MM-DD)", "start"), F("End date (YYYY-MM-DD)", "end"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Show out-of-office / working location / focus time",
    "Lists a user's out-of-office, working-location, or focus-time entries "
    "between two dates.",
    "user {email} show {kind} range {start} {end}",
    [F("User email", "email"),
     F("Which", "kind", valuemap={"Out of office": "outofoffice",
       "Working location": "workinglocation", "Focus time": "focustime"}),
     F("Start date (YYYY-MM-DD)", "start"), F("End date (YYYY-MM-DD)", "end"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Event details",
    "Shows everything about one event - attendees and their responses, "
    "times, Meet link, and so on. Get the event ID from 'List events'.",
    "user {email} info events {cal} eventid {eventid}",
    [F("Calendar owner", "email"),
     F("Calendar (usually 'primary')", "cal", default="primary"),
     F("Event ID", "eventid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Drive": [
  T("List a user's files",
    "Prints the files a user owns. Warning: can be large; a query like "
    "mimeType contains 'video/' narrows it.",
    "user {email} print filelist fields id,name,mimetype [query {query}]",
    [F("User email", "email"), F("Drive query (optional) e.g. mimeType contains 'video/'", "query", False)]),
  T("PERMANENTLY delete a file from EVERYONE's Drive (by name or ID)",
    "Two-phase: searches Drives across the domain for a file - ANY type (Google "
    "Docs/Sheets, Office files, PDFs, mp3s, anything) - by its NAME or by its "
    "file ID, shows how many OWNED copies were found, then - after you type "
    "DELETE to confirm - PERMANENTLY DELETES each owned copy (NOT recoverable, "
    "it does not go to Trash). Only the Drives that actually have the file are "
    "touched. Built to pull a malicious file out of the whole domain. By NAME "
    "finds every separate copy (each user's own file); by ID targets one "
    "specific file. Evidence is saved to a timestamped folder under Logs.",
    "",
    [F("Find by", "findby", valuemap={"File name": "name", "File ID": "id"}),
     F("File name, or file ID", "fileref"),
     F("Search scope", "scopetype", valuemap={"All users": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Speed: parallel threads (blank = config default)", "threads", False)],
    destructive=True, workflow="drivewipe"),
  T("Remove access to an OUTSIDE file (not owned by us) - by name or ID",
    "For a file OWNED BY AN EXTERNAL user that was shared with your people (a "
    "malicious file with no email to clean up). Two-phase: finds EVERY internal "
    "user in the chosen scope who has the file (by NAME or file ID), lists "
    "them, then - after you type DELETE - removes each user's access. "
    "IMPORTANT: Google only lets a user drop their OWN access when they were "
    "given EDIT rights; VIEW-ONLY external shares CANNOT be removed this way (a "
    "Google platform limit, not GAM) - for those, use the Admin console "
    "Security Investigation Tool ('Remove access'). Either way you get a CSV of "
    "exactly who has the file, which is what you need for the investigation "
    "tool. Evidence saved under Logs.",
    "",
    [F("Find by", "findby", valuemap={"File name": "name", "File ID": "id"}),
     F("File name, or file ID", "fileref"),
     F("Whose access to remove", "scopetype", valuemap={
       "One or more users (comma separated)": "user",
       "A whole domain": "domains",
       "An OU and its sub-OUs": "ou_and_children",
       "A group": "group",
       "Everyone (all users)": "all"}),
     F("User(s) / domain / OU path / group (blank only for Everyone)",
       "scopeval", False),
     F("Speed: parallel threads (blank = config default)", "threads", False)],
    destructive=True, workflow="removeextaccess"),
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
     F("Role", "role", valuemap={"Viewer": "reader", "Commenter": "commenter",
       "Editor": "writer"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Unshare a file/folder (DESTRUCTIVE)",
    "Removes one person's permission on a file or folder.",
    "user {owner} delete drivefileacl {fileid} {who}",
    [F("File owner", "owner"), F("File/folder ID", "fileid"),
     F("Person to remove (email)", "who"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("File info",
    "Shows details for one Drive file or folder by ID.",
    "user {owner} info drivefile {fileid}",
    [F("File owner", "owner"), F("File/folder ID", "fileid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a file's sharing (ACLs)",
    "Shows everyone who has access to one file or folder.",
    "user {owner} show drivefileacls {fileid}",
    [F("File owner", "owner"), F("File/folder ID", "fileid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Count a user's files",
    "Reports how many files a user owns, grouped by type.",
    "user {email} print filecounts {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Empty a user's Drive trash (DESTRUCTIVE)",
    "Permanently removes everything in a user's Drive trash.",
    "user {email} empty drivetrash",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Copy a file/folder",
    "Copies a Drive file or folder. Add  newfilename \"Name\"  or  parentid "
    "<folderId>  in the advanced box to rename or place the copy.",
    "user {email} copy drivefile {fileid}",
    [F("File owner", "email"), F("File/folder ID", "fileid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move a file/folder",
    "Moves a file/folder to a new parent folder. Put  parentid <folderId>  in "
    "the advanced box (and optionally  newfilename \"Name\").",
    "user {email} move drivefile {fileid}",
    [F("File owner", "email"), F("File/folder ID", "fileid"),
     F("Extra arguments (advanced, e.g. parentid <id>)", "extra", False, rawappend=True)]),
  T("Download a file",
    "Downloads a Drive file to disk. By default it lands in the current "
    "folder; add  targetfolder C:\\path  in the advanced box to choose where.",
    "user {email} get drivefile {fileid}",
    [F("File owner", "email"), F("File ID", "fileid"),
     F("Extra arguments (advanced, e.g. targetfolder C:\\path)", "extra", False, rawappend=True)]),
  T("Delete a file/folder (DESTRUCTIVE)",
    "Sends a file/folder to the owner's Drive trash (recoverable). Add  purge  "
    "in the advanced box to delete it permanently instead.",
    "user {email} delete drivefile {fileid}",
    [F("File owner", "email"), F("File/folder ID", "fileid"),
     F("Extra arguments (advanced, e.g. purge)", "extra", False, rawappend=True)],
    destructive=True),
  T("Transfer ownership of a file/folder",
    "Makes another user the owner of a specific file or folder (and its "
    "contents).",
    "user {email} transfer ownership {fileid} {newowner}",
    [F("Current owner", "email"), F("File/folder ID", "fileid"),
     F("New owner email", "newowner"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Claim ownership of a file/folder",
    "Makes the given user the owner of a file they can access (the reverse of "
    "transfer - useful for reclaiming a departed user's shared files).",
    "user {email} claim ownership {fileid}",
    [F("User who will own it", "email"), F("File/folder ID", "fileid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Collect orphaned files",
    "Gathers a user's orphaned files (files with no parent folder) so they are "
    "reachable again. Add  targetuserfoldername \"Name\"  in the advanced box "
    "to name the collection folder.",
    "user {email} collect orphans",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Is this a shortcut? (check)",
    "Reports whether a Drive item is a shortcut and, if so, what it points to.",
    "user {email} check drivefileshortcut {fileid}",
    [F("File owner", "email"), F("File ID", "fileid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a file's revisions (CSV/Sheet)",
    "Prints the version history of one file.",
    "user {email} print filerevisions {fileid} {todrive}",
    [F("File owner", "email"), F("File ID", "fileid"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete old file revisions (DESTRUCTIVE)",
    "Permanently removes old versions (revisions) of a file to reclaim space - "
    "the current version is never removed. Pick which revisions to delete, e.g. "
    "'All except the newest N' with 5 keeps only the 5 newest. Run 'List a "
    "file's revisions' first to see what is there. (Before v2.40 this task "
    "only previewed and never deleted - it was missing GAM's 'doit'.)",
    "user {email} delete filerevisions {fileid} select {seltype} {selval} doit",
    [F("File owner", "email"), F("File ID", "fileid"),
     F("Delete which revisions", "seltype", valuemap={
       "All except the newest N (keep N newest)": "allexceptlast",
       "The oldest N": "first",
       "The newest N": "last",
       "All except the oldest N": "allexceptfirst",
       "Everything before a date/time": "before",
       "Everything after a date/time": "after",
       "One revision by its ID": "id"}),
     F("N, date/time (e.g. 2026-01-01), or revision ID", "selval"),
     F("Extra arguments (advanced, e.g. max_to_delete 20)", "extra", False,
       rawappend=True)],
    destructive=True),
  T("Show a user's folder tree (CSV/Sheet)",
    "Prints a user's Drive folder hierarchy.",
    "user {email} print filetree {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Who owns this file? (by ID) - CSV/Sheet",
    "Looks up who owns a file when you have its ID (from the URL). Works "
    "district-wide without knowing whose Drive it is in - handy for the "
    "malicious-file and lost-file investigations. To search by NAME instead, "
    "use the next task.",
    "print ownership {fileid} {todrive}",
    [F("File ID (from the file's URL)", "fileid"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Who owns this file? (by name) - CSV/Sheet",
    "Looks up who owns a file (or files) matching a name, district-wide. Every "
    "file with that exact name is listed with its owner and ID - so you can "
    "then act on the right one by ID.",
    "print ownership drivefilename {filename} {todrive}",
    [F("Exact file name", "filename"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Where does a file live? (its folder path) - CSV/Sheet",
    "Shows the full folder path to a file inside a user's Drive - useful when a "
    "user says 'I can't find my file' or you need to know where a shared file "
    "actually sits.",
    "user {email} print filepath {fileid} {todrive}",
    [F("File owner (whose Drive to look in)", "email"),
     F("File ID (from the file's URL)", "fileid"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("What has a user been doing in Drive? (activity log) - CSV/Sheet",
    "Prints a user's recent Drive activity - files created, edited, shared, "
    "moved, renamed, trashed, and by whom. Useful for investigations or for "
    "reconstructing what happened to a file. Narrow it in the advanced box, "
    "e.g.  start 2026-09-01  |  drivefilename Report.docx.",
    "user {email} print driveactivity {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, e.g. start <date>)", "extra", False,
       rawappend=True)]),
  T("Find empty folders in a user's Drive - CSV/Sheet",
    "Lists folders in a user's Drive that contain no files - handy for tidying "
    "up or reclaiming a messy Drive before an account is archived.",
    "user {email} print emptydrivefolders {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List comments on a file - CSV/Sheet",
    "Prints the comments left on one file (who said what and when) - useful for "
    "investigations or for reviewing feedback on a shared document.",
    "user {email} print filecomments {fileid} {todrive}",
    [F("File owner (whose Drive to look in)", "email"),
     F("File ID (from the file's URL)", "fileid"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Sharing counts per user (sharing / DLP audit) - CSV/Sheet",
    "Prints how many files each user has shared and in what ways (internal, "
    "external / anyone-with-link, etc.) - a quick data-loss / oversharing "
    "review across the domain. Runs across all users, so it can take a while.",
    "all users print filesharecounts {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Find dormant Drives (last-modified per user) - CSV/Sheet",
    "Prints the date each user's Drive was last modified - useful for finding "
    "abandoned or dormant Drives before archiving or reclaiming licenses. Runs "
    "across all users, so it can take a while.",
    "all users print drivelastmodification {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("How big is a folder? (disk usage) - CSV/Sheet",
    "Reports the total size of a folder and everything inside it, in a user's "
    "Drive - useful for finding what is eating a user's storage. Enter the "
    "folder's ID (from its URL).",
    "user {email} print diskusage {fileid} {todrive}",
    [F("Folder owner (whose Drive to look in)", "email"),
     F("Folder ID (from the folder's URL)", "fileid"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a user's Drive settings - CSV/Sheet",
    "Prints a user's Drive settings (storage quota and usage, upload limits, "
    "folder-color defaults, and more) - useful when troubleshooting sync or "
    "storage complaints.",
    "user {email} print drivesettings {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # BULK / whole-Drive actions (offboarding, cleanup, reclaiming storage).
  # ---------------------------------------------------------------------------
  T("Empty a user's Drive trash",
    "Permanently empties one user's Drive trash, reclaiming that storage. Files "
    "already in the trash are gone for good; files not in the trash are not "
    "touched.",
    "user {email} empty drivetrash",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Empty EVERYONE's Drive trash (reclaim storage) (DESTRUCTIVE)",
    "Permanently empties the Drive trash of EVERY user in the domain - a "
    "domain-wide storage reclaim. Anything sitting in any user's trash is gone "
    "for good. This runs across all users and can take a while.",
    "all users empty drivetrash",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Transfer a user's ENTIRE Drive to another user (offboarding)",
    "Gives ownership of ALL of a leaving user's My Drive files to another user "
    "(they land in a folder in the new owner's Drive). The classic offboarding "
    "step so a departing person's work is not lost. Does not touch Shared Drive "
    "files (those are owned by the Shared Drive).",
    "user {email} transfer drive {newowner}",
    [F("Leaving user (current owner)", "email"),
     F("New owner (receives the files)", "newowner"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Transfer ownership of files matching a query (to another user)",
    "Transfers ownership of only the files that match a Drive query from one "
    "user to another - e.g. move just the files in a shared project. Query "
    "syntax is the Drive search language, e.g.  name contains 'Budget'  |  "
    "'folderID' in parents.",
    "user {email} transfer ownership query {query} {newowner}",
    [F("Current owner", "email"),
     F("Drive query e.g. name contains 'Budget'", "query"),
     F("New owner", "newowner"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Trash files matching a query (from a user's Drive) (DESTRUCTIVE)",
    "Moves every file matching a Drive query into the user's trash (recoverable "
    "until the trash is emptied). Use it to clean up in bulk - e.g. old exports. "
    "ALWAYS test the query with 'Find files (query)' first. To delete "
    "PERMANENTLY instead, put  purge  in place of the default in the advanced "
    "box (replace 'trash').",
    "user {email} delete drivefile query {query} trash",
    [F("File owner", "email"),
     F("Drive query e.g. name contains 'Old Export'", "query"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Bulk SHARE files matching a query (add a person)",
    "Grants one person access to EVERY file in a user's Drive that matches a "
    "query - e.g. give a co-teacher reader access to all files in a project "
    "folder. Test the query with 'Find files (query)' first.",
    "user {owner} add drivefileacl query {query} user {who} role {role}",
    [F("File owner (whose Drive)", "owner"),
     F("Drive query e.g. 'FOLDER_ID' in parents", "query"),
     F("Person to give access", "who"),
     F("Access level", "role", valuemap={"Viewer (read)": "reader",
       "Commenter": "commenter", "Editor (write)": "writer"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Bulk UNSHARE files matching a query (remove a person) (DESTRUCTIVE)",
    "Removes one person's access from EVERY file in a user's Drive that matches "
    "a query - e.g. pull a departing collaborator off all of a project's files.",
    "user {owner} delete drivefileacl query {query} {who}",
    [F("File owner (whose Drive)", "owner"),
     F("Drive query e.g. 'FOLDER_ID' in parents", "query"),
     F("Person whose access to remove", "who"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Delete empty folders in a user's Drive (cleanup) (DESTRUCTIVE)",
    "Removes folders that contain no files from a user's Drive - tidies up "
    "after files are moved out. Use 'Find empty folders' first to preview.",
    "user {email} delete emptydrivefolders",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Collect orphaned files into a folder",
    "Finds a user's orphaned files (files whose parent folder was deleted, so "
    "they are hard to find) and gathers them into a single folder in their "
    "Drive so nothing is lost.",
    "user {email} collect orphans",
    [F("User email", "email"),
     F("Extra arguments (advanced, e.g. targetuserfoldername 'Recovered')",
       "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # Restore, purge, create, rename, and replace files.
  # ---------------------------------------------------------------------------
  T("Restore (untrash) a file",
    "Moves a file out of the owner's Drive trash and back where it was.",
    "user {email} untrash drivefile {fileid}",
    [F("File owner", "email"), F("File ID (from its URL)", "fileid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Restore (untrash) files matching a query",
    "Restores every trashed file in a user's Drive that matches a query - e.g. "
    "undo a bulk cleanup. Example query:  trashed = true and name contains "
    "'Budget'",
    "user {email} untrash drivefile query {query}",
    [F("File owner", "email"),
     F("Drive query e.g. trashed = true and name contains 'Budget'", "query"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Permanently purge a trashed file (DESTRUCTIVE)",
    "Permanently deletes a file that is already in the owner's trash. It "
    "cannot be recovered afterward.",
    "user {email} purge drivefile {fileid}",
    [F("File owner", "email"), F("File ID (from its URL)", "fileid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create a folder path (nested folders)",
    "Creates a path of nested folders in a user's My Drive in one step; any "
    "folder that does not exist yet is created. Example: Projects/2027/Budget",
    "user {email} create drivefolderpath fullpath {path}",
    [F("User email", "email"),
     F("Folder path e.g. Projects/2027/Budget", "path"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a shortcut to a file or folder",
    "Adds a Drive shortcut that points to a file or folder. To place it in a "
    "particular folder, add  parentid <folderID>  in the advanced box.",
    "user {email} create drivefileshortcut {fileid} [shortcutname {name}]",
    [F("User email", "email"), F("File/folder ID to link to", "fileid"),
     F("Shortcut name (optional)", "name", False),
     F("Extra arguments (advanced, e.g. parentid <folderID>)", "extra",
       False, rawappend=True)]),
  T("Rename a file or folder",
    "Renames a file or folder in a user's Drive.",
    "user {email} update drivefile {fileid} newfilename {newname}",
    [F("File owner", "email"), F("File/folder ID", "fileid"),
     F("New name", "newname"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Replace a file's contents from a file on this PC",
    "Uploads a local file as the NEW contents of an existing Drive file, "
    "keeping its ID, sharing, and link - e.g. publish an updated handbook "
    "without breaking anyone's links.",
    "user {email} update drivefile {fileid} localfile {file}",
    [F("File owner", "email"), F("File ID", "fileid"),
     F("Local file to upload", "file", filepicker=True),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # Drive labels (classification labels) - run as an admin with adminaccess.
  # ---------------------------------------------------------------------------
  T("List Drive labels (classification labels) - CSV/Sheet",
    "Prints your organization's Drive labels (e.g. Confidential / Internal) "
    "and their fields.",
    "print classificationlabels adminaccess {todrive}",
    [*_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Drive label info",
    "Shows one Drive label in full. Use its name from 'List Drive labels' "
    "(labels/...).",
    "info classificationlabels {label} adminaccess",
    [F("Label name e.g. labels/abc123", "label"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List who can use a Drive label - CSV/Sheet",
    "Prints the permissions on a Drive label (who can apply, edit, or manage "
    "it).",
    "print classificationlabelpermissions {label} adminaccess {todrive}",
    [F("Label name e.g. labels/abc123", "label"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Let a user or group use a Drive label",
    "Grants a user or group a role on a Drive label.",
    "create classificationlabelpermission {label} {whotype} {who} role {role} adminaccess",
    [F("Label name e.g. labels/abc123", "label"),
     F("Grant to", "whotype", valuemap={"A user": "user", "A group": "group"}),
     F("Their email", "who"),
     F("Role", "role", valuemap={"Can apply the label": "applier",
       "Can read it": "reader", "Can edit it": "editor",
       "Can manage it": "organizer"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove a user or group from a Drive label (DESTRUCTIVE)",
    "Removes a user's or group's role on a Drive label.",
    "delete classificationlabelpermission {label} {whotype} {who} adminaccess",
    [F("Label name e.g. labels/abc123", "label"),
     F("Remove", "whotype", valuemap={"A user": "user", "A group": "group"}),
     F("Their email", "who"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Upload a file from this PC",
    "Uploads a file into a user's Drive, optionally into a folder and "
    "optionally converted to a Google Doc / Sheet / Slides (e.g. .docx -> "
    "Doc, .xlsx or .csv -> Sheet, .pptx -> Slides).",
    "user {email} create drivefile localfile {file} [parentid {folder}] [mimetype {mime}]",
    [F("User email", "email"), F("File on this PC", "file", filepicker=True),
     F("Folder ID (optional, blank = My Drive)", "folder", False),
     F("Convert to (optional)", "mime", False, valuemap={"": "",
       "Google Doc": "gdoc", "Google Sheet": "gsheet",
       "Google Slides": "gpresentation"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("File details (full, with its folder path)",
    "Shows everything about one file - owner, size, dates, sharing, labels - "
    "plus the folder path it lives in.",
    "user {email} show fileinfo {fileid} filepath",
    [F("User with access", "email"), F("File ID", "fileid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a file's folder tree - CSV/Sheet",
    "Prints every folder above a file, up to My Drive or the Shared Drive - "
    "handy for 'where is this file?'.",
    "user {email} print fileparenttree {fileid} {todrive}",
    [F("User with access", "email"), F("File ID", "fileid"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Apply or remove a Drive label on a file",
    "Adds a Drive label (e.g. Confidential) to a file, or removes it. Use the "
    "label ID from 'List Drive labels'.",
    "user {email} process filedrivelabels {fileid} {action} {labelid}",
    [F("User with edit access", "email"), F("File ID", "fileid"),
     F("Action", "action", valuemap={"Apply the label": "addlabel",
       "Remove the label": "deletelabel"}),
     F("Label ID", "labelid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Shared Drives": [
  T("List Shared Drives",
    "Prints all Shared Drives visible to the admin.",
    "print shareddrives fields id,name {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List Shared Drive memberships (ACLs)",
    "Prints who has access to which Shared Drives.",
    "print shareddriveacls {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List Shared Drive organizers/managers (CSV/Sheet)",
    "Prints the Manager (organizer) of every Shared Drive - useful for auditing "
    "who controls each one. Add 'includefileorganizers' in the advanced box to "
    "also include people granted file-organizer rights.",
    "print shareddriveorganizers {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List Shared Drives grouped by OU (CSV/Sheet)",
    "Prints every Shared Drive together with the organizational unit it is "
    "assigned to - useful for checking which campus/department OU each Shared "
    "Drive belongs to.",
    "print oushareddrives {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create Shared Drive",
    "Creates a new Shared Drive. Optionally place it in an OU or set a theme "
    "via the advanced box, e.g.  ou /Staff  |  theme 'Bird'.",
    "create shareddrive {name}",
    [F("Shared Drive name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rename Shared Drive",
    "Changes a Shared Drive's name. Enter its NAME or ID (auto-detected).",
    "update shareddrive {shareddrive:driveid} name {name}",
    [F("Shared Drive name OR ID", "driveid"), F("New name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Shared Drive info",
    "Shows a Shared Drive's settings and restrictions.",
    "info shareddrive {shareddrive:driveid}",
    [F("Shared Drive name OR ID", "driveid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Hide Shared Drive",
    "Hides a Shared Drive from the default view (does not delete it).",
    "hide shareddrive {shareddrive:driveid}",
    [F("Shared Drive name OR ID", "driveid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Unhide Shared Drive",
    "Restores a hidden Shared Drive to the default view.",
    "unhide shareddrive {shareddrive:driveid}",
    [F("Shared Drive name OR ID", "driveid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add member to Shared Drive",
    "Grants a role on a Shared Drive. Enter the Shared Drive's NAME or its ID "
    "(either works - it is auto-detected). Roles use Google's names: Manager "
    "= full control; Content Manager = add/edit/move/delete files; Contributor "
    "= add and edit files; Commenter = comment only; Viewer = read only.",
    "add drivefileacl {shareddrive:driveid} user {who} role {role}",
    [F("Shared Drive name OR ID (either works)", "driveid"),
     F("User email", "who"),
     F("Role", "role", valuemap={"Viewer": "reader", "Commenter": "commenter",
       "Contributor": "writer", "Content Manager": "contentmanager",
       "Manager": "organizer"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change member role on Shared Drive",
    "Changes an existing member's role on a Shared Drive.",
    "update drivefileacl {shareddrive:driveid} {who} role {role}",
    [F("Shared Drive name OR ID", "driveid"), F("Member email", "who"),
     F("New role", "role", valuemap={"Viewer": "reader", "Commenter": "commenter",
       "Contributor": "writer", "Content Manager": "contentmanager",
       "Manager": "organizer"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove member from Shared Drive (DESTRUCTIVE)",
    "Removes a member's access to a Shared Drive.",
    "delete drivefileacl {shareddrive:driveid} {who}",
    [F("Shared Drive name OR ID", "driveid"), F("Member email", "who"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List members of a Shared Drive",
    "Prints the members and roles of one Shared Drive.",
    "print drivefileacls {shareddrive:driveid} {todrive}",
    [F("Shared Drive name OR ID", "driveid"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete Shared Drive (DESTRUCTIVE)",
    "Deletes a Shared Drive. It must be EMPTY unless you add "
    "'allowitemdeletion' in the advanced box (which deletes its files too).",
    "delete shareddrive {shareddrive:driveid}",
    [F("Shared Drive name OR ID", "driveid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
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
  # ---------------------------------------------------------------------------
  # BULK Shared Drive actions from a CSV. Use 'List Shared Drives' or 'List
  # Shared Drive memberships' (with the CSV output option) to produce a list of
  # Shared Drive IDs to feed these. Column names are case-sensitive.
  # ---------------------------------------------------------------------------
  T("BULK: create Shared Drives from a CSV",
    "Creates many Shared Drives in ONE pass from a CSV - e.g. one per department "
    "or team at the start of the year. The CSV needs a name column.",
    "csv {file} gam create shareddrive ~{namecol}",
    [F("CSV file", "file", filepicker=True),
     F("Name column header", "namecol", default="Name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: delete Shared Drives from a CSV (DESTRUCTIVE)",
    "Deletes every Shared Drive whose ID is listed in a CSV column. Each drive "
    "must be EMPTY unless you add 'allowitemdeletion' in the advanced box "
    "(which deletes its files too). This cannot be undone - TEST your CSV first.",
    "csv {file} gam delete shareddrive ~{idcol}",
    [F("CSV file", "file", filepicker=True),
     F("Shared Drive ID column header", "idcol", default="id"),
     F("Extra arguments (advanced, e.g. allowitemdeletion)", "extra", False,
       rawappend=True)],
    destructive=True),
  T("BULK: add a member to Shared Drives from a CSV",
    "Grants one person a role on every Shared Drive whose ID is listed in a CSV "
    "column - e.g. give a new team lead access to all of a department's Shared "
    "Drives at once.",
    "csv {file} gam add drivefileacl ~{idcol} user {who} role {role}",
    [F("CSV file of Shared Drive IDs", "file", filepicker=True),
     F("Shared Drive ID column header", "idcol", default="id"),
     F("Person to give access", "who"),
     F("Role", "role", valuemap={"Viewer": "reader", "Commenter": "commenter",
       "Contributor": "writer", "Content Manager": "contentmanager",
       "Manager": "organizer"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: remove a member from Shared Drives from a CSV (DESTRUCTIVE)",
    "Removes one person's access from every Shared Drive whose ID is listed in "
    "a CSV column - e.g. pull a departing staff member off a set of Shared "
    "Drives at once.",
    "csv {file} gam delete drivefileacl ~{idcol} {who}",
    [F("CSV file of Shared Drive IDs", "file", filepicker=True),
     F("Shared Drive ID column header", "idcol", default="id"),
     F("Person whose access to remove", "who"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: move Shared Drives to an OU from a CSV",
    "Assigns every Shared Drive whose ID is listed in a CSV column to an "
    "organizational unit - useful for organizing Shared Drives by campus or "
    "department (see 'List Shared Drives grouped by OU').",
    "csv {file} gam update shareddrive ~{idcol} ou {ou}",
    [F("CSV file of Shared Drive IDs", "file", filepicker=True),
     F("Shared Drive ID column header", "idcol", default="id"),
     F("Destination OU path e.g. /Shared Drives/FSHS", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Copy one Shared Drive's members to another",
    "Adds every member (and role) of one Shared Drive to another. Existing "
    "members of the target stay. Name or ID for each.",
    "copy shareddriveacls {shareddrive:source} to {shareddrive:target}",
    [F("Copy FROM Shared Drive (name or ID)", "source"),
     F("Copy TO Shared Drive (name or ID)", "target"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Sync Shared Drive members - exact match (DESTRUCTIVE)",
    "Makes a Shared Drive's members EXACTLY match another's: missing members "
    "are added and extra members are REMOVED.",
    "sync shareddriveacls {shareddrive:source} with {shareddrive:target}",
    [F("Shared Drive to CHANGE (name or ID)", "source"),
     F("Match the members of (name or ID)", "target"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Shared Drive details (admin)",
    "Shows a Shared Drive's settings and restrictions (name or ID).",
    "show shareddriveinfo {shareddrive:driveid}",
    [F("Shared Drive (name or ID)", "driveid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Classroom": [
  T("List courses (by teacher)",
    "Prints courses; give a teacher email to see just theirs.",
    "print courses [teacher {teacher}] {todrive}",
    [F("Teacher email (optional)", "teacher", False),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List course participants",
    "Prints students and teachers across courses.",
    "print course-participants {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add teacher to course", "Adds a co-teacher to a course by course ID.",
    "course {courseid} add teachers {teacher}",
    [F("Course ID (find it with List courses)", "courseid"), F("Teacher email", "teacher"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove teacher from course",
    "Removes a co-teacher from a course.",
    "course {courseid} remove teachers {teacher}",
    [F("Course ID", "courseid"), F("Teacher email", "teacher"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add student to course", "Adds a student to a course by course ID.",
    "course {courseid} add students {student}",
    [F("Course ID (find it with List courses)", "courseid"), F("Student email", "student"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove student from course", "Removes a student from a course.",
    "course {courseid} remove students {student}",
    [F("Course ID", "courseid"), F("Student email", "student"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Invite a user to a course (invitation)",
    "Sends a Classroom INVITATION the user must accept, instead of adding them "
    "directly - use this when a direct add is not allowed (for example inviting "
    "someone as a co-teacher who must confirm). Pick the role.",
    "user {email} create classroominvitation courses {courseid} role {role}",
    [F("User email to invite", "email"), F("Course ID", "courseid"),
     F("Role", "role", choices=["student", "teacher", "owner"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Accept a course invitation for a user",
    "Accepts a pending Classroom invitation on a user's behalf - handy when a "
    "user cannot or will not click the emailed invite themselves.",
    "user {email} accept classroominvitation courses {courseid}",
    [F("User email", "email"), F("Course ID", "courseid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Cancel a user's course invitation",
    "Withdraws a pending Classroom invitation for a user (before they accept "
    "it) - for example if you invited the wrong person or to the wrong role.",
    "user {email} delete classroominvitation courses {courseid}",
    [F("User email", "email"), F("Course ID", "courseid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Sync students from a group (DESTRUCTIVE)",
    "Makes the course's students EXACTLY match a Google Group's members: "
    "missing students are added and anyone else is REMOVED.",
    "course {courseid} sync students group {group}",
    [F("Course ID", "courseid"), F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Sync students from an OU (DESTRUCTIVE)",
    "Makes the course's students EXACTLY match the users in an OU: missing "
    "students are added and anyone else is REMOVED.",
    "course {courseid} sync students ou {ou}",
    [F("Course ID", "courseid"), F("OU path e.g. /Students/Grade9", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Add students from a group (adds only - no removals)",
    "Adds every member of a Google Group to the course as students. Unlike "
    "'Sync students from a group', this only ADDS - it never removes anyone "
    "already in the course. Good for topping up a roster.",
    "courses {courseid} add students group {group}",
    [F("Course ID", "courseid"), F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add teachers from a group (adds only - no removals)",
    "Adds every member of a Google Group to the course as co-teachers. Only "
    "ADDS - never removes existing teachers.",
    "courses {courseid} add teachers group {group}",
    [F("Course ID", "courseid"), F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Bulk add students from a CSV (adds only)",
    "Adds students to the course from a CSV column of email addresses in ONE "
    "pass - only ADDS, never removes. Enter the CSV and the column header that "
    "holds the student emails.",
    "courses {courseid} add students csvfile {file}:{emailcol}",
    [F("Course ID", "courseid"),
     F("CSV file", "file", filepicker=True),
     F("Email column header", "emailcol", default="email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add students from an OU (adds only - no removals)",
    "Adds every user in an OU to the course as students. Only ADDS - never "
    "removes anyone already enrolled. (For an exact match that also removes, "
    "use 'Sync students from an OU'.)",
    "courses {courseid} add students ou {ou}",
    [F("Course ID", "courseid"), F("OU path e.g. /Students/Grade9", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add teachers from an OU (adds only - no removals)",
    "Adds every user in an OU to the course as co-teachers. Only ADDS - never "
    "removes existing teachers.",
    "courses {courseid} add teachers ou {ou}",
    [F("Course ID", "courseid"), F("OU path e.g. /Staff/FSHS", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Bulk add teachers from a CSV (adds only)",
    "Adds co-teachers to the course from a CSV column of email addresses in ONE "
    "pass - only ADDS, never removes.",
    "courses {courseid} add teachers csvfile {file}:{emailcol}",
    [F("Course ID", "courseid"),
     F("CSV file", "file", filepicker=True),
     F("Email column header", "emailcol", default="email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add course alias",
    "Adds an alias (friendly ID) to a course, e.g. d:MATH101.",
    "courses {courseid} add alias {alias}",
    [F("Course ID", "courseid"), F("Alias e.g. d:MATH101", "alias"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove course alias",
    "Removes an alias (friendly ID) from a course - the counterpart to 'Add "
    "course alias'. Enter the same alias form, e.g. d:MATH101.",
    "course {courseid} delete alias {alias}",
    [F("Course ID", "courseid"), F("Alias e.g. d:MATH101", "alias"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Invite guardian",
    "Invites a parent/guardian email to follow a student's Classroom "
    "summaries. The guardian must accept the emailed invitation.",
    "create guardian {guardian} {student}",
    [F("Guardian email", "guardian"), F("Student email", "student"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List guardians",
    "Prints guardian links and pending invitations.",
    "print guardians {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change course owner",
    "New owner must already be a teacher in the course (use Add teacher "
    "first). Old owner remains a teacher.",
    "update course {courseid} owner {newowner}",
    [F("Course ID (find it with List courses)", "courseid"), F("New owner email", "newowner"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Archive course", "Archives a course (required before deleting).",
    "update course {courseid} status archived",
    [F("Course ID (find it with List courses)", "courseid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Archive ALL active Classrooms (end of year) (DESTRUCTIVE)",
    "End-of-year cleanup: finds EVERY active Google Classroom, shows you the "
    "count and a sample, asks you to type ARCHIVE, then archives them all. "
    "Archived classes are hidden but NOT deleted (teachers and students can "
    "still open them). Run AFTER the school year ends and BEFORE new classes "
    "are created, so you do not archive next year's courses. The full list "
    "is saved to the Logs folder as a record.",
    "", [], destructive=True, workflow="archivecourses"),
  T("Reactivate (restore) an archived course",
    "Sets an archived course back to ACTIVE so teachers and students can use it "
    "again - the counterpart to 'Archive course'. Useful if a course was "
    "archived by mistake.",
    "update course {courseid} status active",
    [F("Course ID (find it with List courses)", "courseid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete course (DESTRUCTIVE)", "Deletes an archived course.",
    "delete course {courseid}",
    [F("Course ID (find it with List courses)", "courseid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # --- Create / edit / inspect a course ---
  T("Create a course",
    "Creates a new Google Classroom. The owner (primary teacher) defaults to "
    "the account GAM runs as unless you set one.",
    "create course name {name} [section {section}] [room {room}] [owner {owner}]",
    [F("Course name", "name"), F("Section (optional)", "section", False),
     F("Room (optional)", "room", False),
     F("Owner/teacher email (optional)", "owner", False),
     F("Extra arguments (advanced, e.g. description ...)", "extra", False, rawappend=True)]),
  T("Bulk create courses from a CSV",
    "Creates many Google Classrooms in ONE pass from a CSV - the start-of-year "
    "way to stand up a whole campus of courses. The CSV needs a course-name "
    "column and a teacher/owner-email column; column names are case-sensitive.",
    "csv {file} gam create course name ~{namecol} owner ~{ownercol}",
    [F("CSV file", "file", filepicker=True),
     F("Course-name column header", "namecol", default="Name"),
     F("Owner-email column header", "ownercol", default="Owner"),
     F("Extra arguments (advanced, e.g. section ~Section)", "extra", False,
       rawappend=True)]),
  T("Update course details (advanced)",
    "Changes a course's name/section/room/description/subject. Put the changes "
    "in the advanced box, e.g.  name \"Algebra I\" section \"1st Period\" room "
    "\"B12\".",
    "update course {courseid}",
    [F("Course ID (find it with List courses)", "courseid"),
     F("Changes (see example)", "extra", False, rawappend=True)]),
  T("Course info",
    "Shows one course's details (owner, state, section, enrollment codes).",
    "info course {courseid}",
    [F("Course ID (find it with List courses)", "courseid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Sync teachers from a group (DESTRUCTIVE)",
    "Makes the course's teachers EXACTLY match a Google Group's members: "
    "missing teachers are added and anyone else is REMOVED.",
    "course {courseid} sync teachers group {group}",
    [F("Course ID", "courseid"), F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Sync teachers from an OU (DESTRUCTIVE)",
    "Makes the course's teachers EXACTLY match the users in an OU: missing "
    "teachers are added and anyone else is REMOVED.",
    "course {courseid} sync teachers ou {ou}",
    [F("Course ID", "courseid"), F("OU path e.g. /Staff/FSHS", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create a course topic",
    "Adds a topic (a unit/section heading that assignments can be filed under) "
    "to a course.",
    "course {courseid} create topic {topic}",
    [F("Course ID", "courseid"), F("Topic name e.g. Unit 1", "topic"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a course topic (DESTRUCTIVE)",
    "Removes a topic from a course by its topic ID (find it with 'List topics'). "
    "Assignments filed under it are not deleted, just un-filed.",
    "course {courseid} delete topic {topicid}",
    [F("Course ID", "courseid"), F("Topic ID (from List topics)", "topicid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Post an announcement to a class",
    "Posts an announcement to a course's stream. Enter the message text. Add "
    "'state draft' in the advanced box to save it as a draft instead of posting "
    "immediately, or 'scheduledtime <time>' to schedule it.",
    "course {courseid} create announcement text {text}",
    [F("Course ID", "courseid"), F("Announcement text", "text"),
     F("Extra arguments (advanced, e.g. state draft)", "extra", False,
       rawappend=True)]),
  T("Edit or publish an announcement",
    "Changes an existing announcement by its ID (find it with 'List "
    "announcements'). Enter new text to edit it, and/or add 'state published' "
    "in the advanced box to publish a draft.",
    "course {courseid} update announcement {annid} [text {text}]",
    [F("Course ID", "courseid"),
     F("Announcement ID (from List announcements)", "annid"),
     F("New text (optional)", "text", False),
     F("Extra arguments (advanced, e.g. state published)", "extra", False,
       rawappend=True)]),
  T("Delete an announcement (DESTRUCTIVE)",
    "Removes an announcement from a course's stream by its ID (find it with "
    "'List announcements') - use this to pull down a post made in error.",
    "course {courseid} remove announcement {annid}",
    [F("Course ID", "courseid"),
     F("Announcement ID (from List announcements)", "annid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create a student group",
    "Creates a named student group inside a course (for organizing group work). "
    "Add members afterward with 'Add members to a student group'.",
    "create course-studentgroups course {courseid} title {title}",
    [F("Course ID", "courseid"), F("Group title e.g. Group A", "title"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add members to a student group",
    "Adds a student (or a whole Google Group's members) to a course student "
    "group. Get the student-group ID from 'List student groups'. For one "
    "student enter their email; for a whole group enter  group <email>  and for "
    "an OU enter  ou <path>.",
    "create course-studentgroup-members {courseid} {groupid}",
    [F("Course ID", "courseid"),
     F("Student-group ID (from List student groups)", "groupid"),
     F("Member - a student email, or  group <email>  or  ou <path>", "member",
       rawappend=True)]),
  T("Rename a student group",
    "Changes the title of a course student group. Get the student-group ID "
    "from 'List student groups'.",
    "update course-studentgroups {courseid} {groupid} title {title}",
    [F("Course ID", "courseid"),
     F("Student-group ID (from List student groups)", "groupid"),
     F("New title", "title"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove a member from a student group",
    "Removes a student (or a whole Google Group's members) from a course "
    "student group. The student stays in the course; only their spot in the "
    "group is removed. For one student enter their email; for a whole group "
    "enter  group <email>  and for an OU enter  ou <path>.",
    "delete course-studentgroup-members {courseid} {groupid}",
    [F("Course ID", "courseid"),
     F("Student-group ID (from List student groups)", "groupid"),
     F("Member - a student email, or  group <email>  or  ou <path>", "member",
       rawappend=True)]),
  T("Sync a student group's members (exact match) (DESTRUCTIVE)",
    "Makes a student group's members EXACTLY match a source: missing members "
    "are added and anyone else is REMOVED. Enter the source as  group <email>  "
    "or  ou <path>  (or a single email).",
    "sync course-studentgroup-members {courseid} {groupid}",
    [F("Course ID", "courseid"),
     F("Student-group ID (from List student groups)", "groupid"),
     F("Source -  group <email>  or  ou <path>", "member", rawappend=True)],
    destructive=True),
  T("Delete a student group (DESTRUCTIVE)",
    "Deletes a course student group by its ID (find it with 'List student "
    "groups'). The students themselves stay in the course; only the grouping "
    "is removed.",
    "delete course-studentgroups {courseid} {groupid}",
    [F("Course ID", "courseid"),
     F("Student-group ID (from List student groups)", "groupid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Bulk invite guardians from a CSV",
    "Invites many parent/guardian links in ONE pass from a CSV - the fast way "
    "to onboard guardians at the start of the year. The CSV needs a "
    "guardian-email column and a student-email column; each guardian must still "
    "accept the emailed invitation. Column names are case-sensitive.",
    "csv {file} gam create guardian ~{guardiancol} ~{studentcol}",
    [F("CSV file", "file", filepicker=True),
     F("Guardian-email column header", "guardiancol", default="Guardian"),
     F("Student-email column header", "studentcol", default="Student"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- Read-only exports of course content ---
  T("List coursework/assignments (CSV/Sheet)",
    "Prints the coursework (assignments/questions) across courses.",
    "print course-works {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False, rawappend=True)]),
  T("Count courses per student or teacher (CSV/Sheet)",
    "Prints how many courses each student (or each teacher) is enrolled in - "
    "useful for spotting students in no classes, teachers with an unusual load, "
    "or checking enrollment during rollover.",
    "print course-counts {who} {todrive}",
    [F("Count by", "who", choices=["students", "teachers"]),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List student work submissions (CSV/Sheet)",
    "Prints student coursework submissions across courses (who turned in what, "
    "state, and grade). Narrow it in the advanced box, e.g.  course <id>  to a "
    "single class, since a whole-domain pull can be large.",
    "print course-submissions {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False,
       rawappend=True)]),
  T("List course materials (CSV/Sheet)",
    "Prints the materials (attachments, links, files) posted to courses. "
    "Narrow it in the advanced box, e.g.  course <id>.",
    "print course-materials {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False,
       rawappend=True)]),
  T("List pending Classroom invitations (CSV/Sheet)",
    "Prints outstanding Classroom invitations that have not been accepted yet - "
    "students or teachers who were invited to a class but have not joined. "
    "Narrow in the advanced box, e.g.  course <id>  or  teacher <email>  or  "
    "student <email>.",
    "print classroominvitations {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a user's Classroom profile (CSV/Sheet)",
    "Prints a user's Google Classroom profile - their Classroom user ID, name, "
    "and whether they can be a teacher or student - useful when Classroom will "
    "not let you add someone to a course and you need to check their profile.",
    "user {email} print classroomprofile {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List announcements (CSV/Sheet)",
    "Prints the stream announcements across courses.",
    "print course-announcements {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False, rawappend=True)]),
  T("List topics (CSV/Sheet)",
    "Prints the topics (unit headings) across courses.",
    "print course-topics {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False, rawappend=True)]),
  T("List student groups (CSV/Sheet)",
    "Prints Classroom student groups across courses.",
    "print course-studentgroups {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False, rawappend=True)]),
  # --- Guardian removal ---
  T("Remove a guardian link (DESTRUCTIVE)",
    "Removes an ACCEPTED guardian from a student (stops the summaries). Use "
    "Cancel guardian invitation instead for a still-pending invite.",
    "user {student} delete guardians {guardian}",
    [F("Student email", "student"), F("Guardian email", "guardian"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Cancel a pending guardian invitation",
    "Cancels a guardian invitation that has not been accepted yet. Get the "
    "invitation ID from List guardians.",
    "user {student} cancel guardianinvitations {invitationid}",
    [F("Student email", "student"), F("Guardian invitation ID", "invitationid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Sync a student's guardians - exact match (DESTRUCTIVE)",
    "Makes a student's guardians EXACTLY match the list you give (comma "
    "separated): missing guardians are invited and anyone else is removed.",
    "user {student} sync guardians {guardians}",
    [F("Student email", "student"),
     F("Guardian email(s), comma separated", "guardians"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Remove a student's guardians (DESTRUCTIVE)",
    "Removes a student's guardians and/or pending guardian invitations.",
    "user {student} clear guardians {which}",
    [F("Student email", "student"),
     F("Remove", "which", valuemap={"Accepted guardians": "accepted",
       "Pending invitations": "invitations", "Both": "all"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List student-group members in a course - CSV/Sheet",
    "Prints the members of every student group in a course.",
    "print course-studentgroup-members course {courseid} {todrive}",
    [F("Course ID or alias", "courseid"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete all student groups in a course (DESTRUCTIVE)",
    "Removes every student group from a course (students stay enrolled).",
    "clear course-studentgroups course {courseid}",
    [F("Course ID or alias", "courseid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Google Meet": [
  # Meet data is read PER USER (the meeting organizer/host). A conference is
  # identified by its MeetConferenceName; get it from 'List a user's Meet
  # conferences' first, then use it for participants/recordings/transcripts.
  T("List a user's Meet conferences - CSV/Sheet",
    "Prints the Meet conferences (meetings) a user hosted or joined, with their "
    "conference names/IDs and times. Start here, then feed a conference into the "
    "tasks below.",
    "user {email} print meetconferences {todrive}",
    [F("User email (the meeting host)", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List participants of a meeting (attendance) - CSV/Sheet",
    "Prints who attended a specific Meet conference and when they joined/left - "
    "useful for class or meeting attendance. Get the conference name from 'List "
    "a user's Meet conferences'.",
    "user {email} print meetparticipants {conference} {todrive}",
    [F("User email (the meeting host)", "email"),
     F("Meet conference name/ID", "conference"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List recordings of a meeting - CSV/Sheet",
    "Prints the recordings made in a specific Meet conference (with Drive links) "
    "- handy for finding a class recording. Get the conference name from 'List a "
    "user's Meet conferences'.",
    "user {email} print meetrecordings {conference} {todrive}",
    [F("User email (the meeting host)", "email"),
     F("Meet conference name/ID", "conference"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List transcripts of a meeting - CSV/Sheet",
    "Prints the transcripts captured in a specific Meet conference. Get the "
    "conference name from 'List a user's Meet conferences'.",
    "user {email} print meettranscripts {conference} {todrive}",
    [F("User email (the meeting host)", "email"),
     F("Meet conference name/ID", "conference"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a Meet meeting space",
    "Creates a reusable Meet meeting space for a user and prints its link and "
    "meeting code. Access type decides who can join without knocking. Add "
    "more settings in the advanced box, e.g.  autorecording true  moderation "
    "true",
    "user {email} create meetspace accesstype {access}",
    [F("Owner email", "email"),
     F("Who can join without asking", "access", valuemap={
       "Anyone with the link": "open",
       "People in your organization": "trusted",
       "Only invited people": "restricted"}),
     F("Extra arguments (advanced, e.g. autorecording true)", "extra", False,
       rawappend=True)]),
  T("Change a Meet space's settings",
    "Changes a meeting space's settings. Put them in the box, e.g.  "
    "accesstype restricted  autorecording true  autotranscription true  "
    "chatrestriction hostsonly",
    "user {email} update meetspace {space}",
    [F("Owner email", "email"),
     F("Space e.g. spaces/abc or a meeting code", "space"),
     F("Settings (required, see example)", "settings", rawappend=True)]),
  T("Meet space info",
    "Shows a meeting space's link, code, settings, and any active meeting.",
    "user {email} info meetspace {space}",
    [F("Owner email", "email"),
     F("Space e.g. spaces/abc or a meeting code", "space"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("End the meeting running in a space (DESTRUCTIVE)",
    "Ends the active meeting in a meeting space - everyone is removed.",
    "user {email} end meetconference {space}",
    [F("Owner email", "email"),
     F("Space e.g. spaces/abc or a meeting code", "space"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Google Forms": [
  # Forms are Drive files; enter the form's file ID (the long part of its URL).
  # These read the form and its responses as the OWNING user.
  T("Show a form's questions / structure - CSV/Sheet",
    "Prints the questions and settings of a Google Form. Enter the form owner "
    "and the form's file ID (from its edit URL).",
    "user {email} print forms {fileid} {todrive}",
    [F("Form owner email", "email"),
     F("Form file ID (from the form's URL)", "fileid"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export a form's responses - CSV/Sheet",
    "Prints the responses submitted to a Google Form - a teacher's quiz results "
    "or a district survey, exported to a Sheet or CSV. Enter the form owner and "
    "the form's file ID (from its edit URL).",
    "user {email} print formresponses {fileid} {todrive}",
    [F("Form owner email", "email"),
     F("Form file ID (from the form's URL)", "fileid"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a form",
    "Creates a new Google Form in a user's Drive with a title and optional "
    "description; optionally make it a quiz. Add questions in Forms, or load "
    "them from JSON with  json file <file>  in the advanced box.",
    "user {email} create form title {title} [description {desc}] [isquiz {quiz}]",
    [F("Owner email", "email"), F("Form title", "title"),
     F("Description (optional)", "desc", False),
     F("Quiz? (optional)", "quiz", False, valuemap={"": "",
       "Yes - make it a quiz": "true"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change a form's title or description",
    "Updates a form's title and/or description.",
    "user {email} update form {fileid} [title {title}] [description {desc}]",
    [F("Owner email", "email"), F("Form file ID (from its URL)", "fileid"),
     F("New title (optional)", "title", False),
     F("New description (optional)", "desc", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Open or close a form for responses",
    "Starts or stops accepting responses on a form (e.g. close a sign-up at "
    "the deadline).",
    "user {email} update form {fileid} ispublished true isacceptingresponses {accept}",
    [F("Owner email", "email"), F("Form file ID (from its URL)", "fileid"),
     F("Responses", "accept", valuemap={"Stop accepting responses": "false",
       "Accept responses": "true"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Google Chat": [
  # ---------------------------------------------------------------------------
  # IMPORTANT: Google requires a Chat bot for ANY Chat API use. Set it up once
  # by running  gam setup chat  in a console (GAM wiki: Users - Chat). Tasks
  # marked (admin) run as an admin with 'asadmin' and see every space of type
  # SPACE in the organization; the others act as the user you enter.
  # ---------------------------------------------------------------------------
  T("List all Chat spaces (admin) - CSV/Sheet",
    "Prints every Chat space (type SPACE) in the organization, using an "
    "admin's Chat admin access. Requires GAM's Chat bot (gam setup chat). "
    "Optional query narrows it - see Google's spaces.search reference.",
    "user {admin} print chatspaces asadmin [query {query}] {todrive}",
    [F("Admin email", "admin"), F("Query (optional)", "query", False),
     *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List members of a Chat space (admin) - CSV/Sheet",
    "Prints the members of any Chat space, using an admin's Chat admin "
    "access. Space looks like spaces/AAAAxxxx (from 'List all Chat spaces').",
    "user {admin} print chatmembers asadmin {space} {todrive}",
    [F("Admin email", "admin"), F("Space e.g. spaces/AAAAxxxx", "space"),
     *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Chat space info (admin)",
    "Shows one Chat space's details and settings, using admin access.",
    "user {admin} info chatspace asadmin {space}",
    [F("Admin email", "admin"), F("Space e.g. spaces/AAAAxxxx", "space"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List the Chat spaces a user is in - CSV/Sheet",
    "Prints the spaces, group chats, and direct messages a user belongs to.",
    "user {email} print chatspaces {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List messages in a Chat space - CSV/Sheet",
    "Prints the messages in a space, read as a user who is a MEMBER of it "
    "(discovery / records requests). Optional date range e.g. start "
    "2027-01-01 end 2027-01-31 in the advanced box.",
    "user {email} print chatmessages {space} {todrive}",
    [F("User email (a member of the space)", "email"),
     F("Space e.g. spaces/AAAAxxxx", "space"), *_out(),
     F("Extra arguments (advanced, e.g. start 2027-01-01)", "extra", False,
       rawappend=True)]),
  T("Search a user's Chat messages - CSV/Sheet",
    "Searches the Chat messages a user can see for keywords (comma "
    "separated).",
    "user {email} print chatsearchmessages keywords {keywords} {todrive}",
    [F("User email", "email"), F("Keywords (comma separated)", "keywords"),
     *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a Chat space",
    "Creates a named Chat space owned by a user, optionally adding members "
    "right away.",
    "user {email} create chatspace type space displayname {name} [description {desc}] [members {mtype} {mval}]",
    [F("Owner email", "email"), F("Space name", "name"),
     F("Description (optional)", "desc", False),
     F("Add members (optional)", "mtype", False, valuemap={"": "",
       "These users (comma separated)": "users",
       "A group's members": "group", "An OU's users": "ou"}),
     F("Users / group email / OU path (optional)", "mval", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rename or describe a Chat space",
    "Changes a space's name and/or description (as a space manager).",
    "user {email} update chatspace {space} [displayname {name}] [description {desc}]",
    [F("User email (a manager of the space)", "email"),
     F("Space e.g. spaces/AAAAxxxx", "space"),
     F("New name (optional)", "name", False),
     F("New description (optional)", "desc", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a Chat space (admin) (DESTRUCTIVE)",
    "Deletes a Chat space and all of its messages, using admin access.",
    "user {admin} delete chatspace asadmin {space}",
    [F("Admin email", "admin"), F("Space e.g. spaces/AAAAxxxx", "space"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Add a member to a Chat space (admin)",
    "Adds a user or a group to a Chat space with the role you pick, using "
    "admin access (members must be in your organization).",
    "user {admin} create chatmember asadmin {space} role {role} {mtype} {member}",
    [F("Admin email", "admin"), F("Space e.g. spaces/AAAAxxxx", "space"),
     F("Role", "role", valuemap={"Member": "member", "Manager": "manager"}),
     F("Add", "mtype", valuemap={"A user": "user", "A group": "group"}),
     F("User or group email", "member"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove a member from a Chat space (admin) (DESTRUCTIVE)",
    "Removes a user or a group from a Chat space, using admin access.",
    "user {admin} delete chatmember asadmin {space} {mtype} {member}",
    [F("Admin email", "admin"), F("Space e.g. spaces/AAAAxxxx", "space"),
     F("Remove", "mtype", valuemap={"A user": "user", "A group": "group"}),
     F("User or group email", "member"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Change a member's role in a Chat space (admin)",
    "Makes a space member a manager, owner, or plain member, using admin "
    "access.",
    "user {admin} update chatmember asadmin {space} role {role} user {member}",
    [F("Admin email", "admin"), F("Space e.g. spaces/AAAAxxxx", "space"),
     F("New role", "role", valuemap={"Manager": "manager", "Owner": "owner",
       "Member": "member"}),
     F("Member email", "member"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Post a message in a Chat space (as a user)",
    "Posts a text message in a space as the user you enter (they must be a "
    "member).",
    "user {email} create chatmessage {space} text {text}",
    [F("Post as (user email)", "email"),
     F("Space e.g. spaces/AAAAxxxx", "space"), F("Message", "text"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Post a message as the GAM Chat bot",
    "Posts a text message in a space as GAM's Chat bot - handy for automated "
    "announcements. The bot must have been added to the space.",
    "create chatmessage {space} text {text}",
    [F("Space e.g. spaces/AAAAxxxx", "space"), F("Message", "text"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Edit a Chat message",
    "Replaces the text of a message the user posted. Message looks like "
    "spaces/AAAAxxxx/messages/yyyy.",
    "user {email} update chatmessage name {message} text {text}",
    [F("User email (who posted it)", "email"),
     F("Message name", "message"), F("New text", "text"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a Chat message (DESTRUCTIVE)",
    "Deletes one Chat message the user posted.",
    "user {email} delete chatmessage name {message}",
    [F("User email (who posted it)", "email"), F("Message name", "message"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Show a user's Chat status - CSV/Sheet",
    "Prints a user's Chat availability (active, away, do not disturb) and "
    "custom status.",
    "user {email} print chatavailability {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Set a user's Chat status",
    "Sets a user to Away, or to Do not disturb / Active for a number of "
    "SECONDS (e.g. 3600 = one hour).",
    "user {email} update chatavailability {status} [ttl {ttl}]",
    [F("User email", "email"),
     F("Status", "status", valuemap={"Away": "away",
       "Do not disturb (needs seconds)": "dnd",
       "Active (needs seconds)": "active"}),
     F("For how many seconds (Do not disturb / Active)", "ttl", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List custom Chat emoji - CSV/Sheet",
    "Prints the organization's custom Chat emoji.",
    "user {email} print chatemojis {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add a custom Chat emoji",
    "Uploads an image as a custom emoji. The name must start and end with "
    "colons, lowercase, e.g. :team-spirit:",
    "user {email} create chatemoji {name} sourcefolder {folder} filename {file}",
    [F("User email (the emoji's creator)", "email"),
     F("Emoji name e.g. :team-spirit:", "name"),
     F("Folder with the image", "folder"),
     F("Image file name e.g. team.png", "file"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a custom Chat emoji (DESTRUCTIVE)",
    "Deletes a custom emoji. Use its name from 'List custom Chat emoji' "
    "(customEmojis/...).",
    "user {email} delete chatemoji {emoji}",
    [F("User email", "email"), F("Emoji e.g. customEmojis/abc", "emoji"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Chat message details",
    "Shows one Chat message in full (sender, text, attachments, thread). "
    "Message looks like spaces/AAAAxxxx/messages/yyyy.",
    "user {email} info chatmessage name {message}",
    [F("User email (a member of the space)", "email"),
     F("Message name", "message"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Google Tasks & Keep": [
  T("List a user's Google Tasks - CSV/Sheet",
    "Prints the to-do items in a user's Google Tasks. Occasionally useful when "
    "recovering or reviewing what a departing user had tracked.",
    "user {email} print tasks {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, e.g. tasklists <id>)", "extra", False,
       rawappend=True)]),
  T("List a user's Google Tasks lists - CSV/Sheet",
    "Prints the names of the task lists a user has in Google Tasks (the "
    "containers their to-do items live in).",
    "user {email} print tasklists {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's Google Keep notes - CSV/Sheet",
    "Prints the notes in a user's Google Keep. Occasionally useful when "
    "reviewing or preserving what a departing user kept in Keep.",
    "user {email} print notes {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),

  # A task list is named by its title (Google's default list is 'My Tasks').
  # A single task is identified as  tasklistID/taskID  - copy both from 'List a
  # user's Google Tasks'. A Keep note is named like  notes/abc123.
  T("Create a task",
    "Adds a to-do item to one of a user's task lists. Google Tasks only "
    "stores the DATE of a due date, but GAM needs it written as a full time: "
    "2027-01-15T00:00:00Z",
    "user {email} create task tltitle:{tasklist} title {title} [notes {notes}] [due {due}]",
    [F("User email", "email"),
     F("Task list title", "tasklist", default="My Tasks"),
     F("Task title", "title"), F("Notes (optional)", "notes", False),
     F("Due date (optional) e.g. 2027-01-15T00:00:00Z", "due", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Complete, rename, or edit a task",
    "Changes a task: mark it complete, give it a new title, or both.",
    "user {email} update task {taskid} [title {title}] [status {status}]",
    [F("User email", "email"), F("Task (tasklistID/taskID)", "taskid"),
     F("New title (optional)", "title", False),
     F("Status (optional)", "status", False, valuemap={"": "",
       "Completed": "completed", "Not done": "needsaction"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a task (DESTRUCTIVE)",
    "Deletes one task.",
    "user {email} delete task {taskid}",
    [F("User email", "email"), F("Task (tasklistID/taskID)", "taskid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create a task list",
    "Creates a new task list for a user.",
    "user {email} create tasklist title {title}",
    [F("User email", "email"), F("List title", "title"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rename a task list",
    "Renames one of a user's task lists.",
    "user {email} update tasklist tltitle:{tasklist} title {newtitle}",
    [F("User email", "email"), F("Current list title", "tasklist"),
     F("New list title", "newtitle"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a task list (DESTRUCTIVE)",
    "Deletes a task list and every task in it.",
    "user {email} delete tasklist tltitle:{tasklist}",
    [F("User email", "email"), F("List title", "tasklist"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Clear completed tasks from a list (DESTRUCTIVE)",
    "Removes all COMPLETED tasks from a task list; open tasks stay.",
    "user {email} clear tasklist tltitle:{tasklist}",
    [F("User email", "email"),
     F("List title", "tasklist", default="My Tasks"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create a Keep note",
    "Creates a Google Keep note in a user's account.",
    "user {email} create note title {title} message {text}",
    [F("User email", "email"), F("Title", "title"), F("Note text", "text"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a Keep note (DESTRUCTIVE)",
    "Deletes a Keep note. Get its name (notes/...) from 'List a user's Google "
    "Keep notes'.",
    "user {email} delete note {note}",
    [F("User email (note owner)", "email"),
     F("Note name e.g. notes/abc123", "note"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Share a Keep note",
    "Gives another user or a group access to a Keep note.",
    "user {email} create noteacl {note} {whotype} {who}",
    [F("User email (note owner)", "email"),
     F("Note name e.g. notes/abc123", "note"),
     F("Share with", "whotype", valuemap={"A user": "user", "A group": "group"}),
     F("Their email", "who"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Stop sharing a Keep note (DESTRUCTIVE)",
    "Removes a user's or group's access to a Keep note.",
    "user {email} delete noteacl {note} {whotype} {who}",
    [F("User email (note owner)", "email"),
     F("Note name e.g. notes/abc123", "note"),
     F("Remove", "whotype", valuemap={"A user": "user", "A group": "group"}),
     F("Their email", "who"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Download a Keep note's attachments",
    "Saves a note's attachments (images, recordings) into a folder on this PC.",
    "user {email} get noteattachments {note} targetfolder {folder}",
    [F("User email (note owner)", "email"),
     F("Note name e.g. notes/abc123", "note"),
     F("Folder on this PC", "folder", default="C:\\GAMExports"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Task details",
    "Shows one task in full (notes, due date, status, links).",
    "user {email} info task {taskid}",
    [F("User email", "email"), F("Task (tasklistID/taskID)", "taskid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move a task (reorder or make it a subtask)",
    "Moves a task within its list: under a parent task (a subtask) and/or "
    "after another task. Leave both blank to move it to the top.",
    "user {email} move task {taskid} [parent {parent}] [previous {previous}]",
    [F("User email", "email"), F("Task (tasklistID/taskID)", "taskid"),
     F("Parent task ID (optional)", "parent", False),
     F("Put it after this task ID (optional)", "previous", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Keep note details",
    "Shows one Keep note in full, including who it is shared with.",
    "user {email} info note {note}",
    [F("User email (note owner)", "email"),
     F("Note name e.g. notes/abc123", "note"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Google Sheets & Docs": [
  # A spreadsheet is identified by its file ID (the long part of its URL).
  # Ranges use Sheets notation, e.g.  Sheet1!A1:D50.
  T("Read a range from a Sheet - CSV/Sheet",
    "Prints the cells in a range of a Google Sheet - to the screen, another "
    "Sheet, or a CSV file.",
    "user {email} print sheetrange {fileid} range {range} {todrive}",
    [F("User with access to the Sheet", "email"),
     F("Spreadsheet file ID (from its URL)", "fileid"),
     F("Range e.g. Sheet1!A1:D50", "range"), *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a spreadsheet's tabs and properties - CSV/Sheet",
    "Prints a spreadsheet's tabs (sheets) and settings.",
    "user {email} print sheet {fileid} {todrive}",
    [F("User with access to the Sheet", "email"),
     F("Spreadsheet file ID (from its URL)", "fileid"), *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Append rows to a Sheet from a JSON file",
    "Adds rows after the existing data in a Sheet, read from a JSON file "
    "shaped like  {\"range\": \"Sheet1!A1\", \"values\": "
    "[[\"a\",\"b\"],[\"c\",\"d\"]]}",
    "user {email} append sheetrange {fileid} json file {file}",
    [F("User with access to the Sheet", "email"),
     F("Spreadsheet file ID (from its URL)", "fileid"),
     F("JSON file", "file", filepicker=True),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Write values into a Sheet range from a JSON file (DESTRUCTIVE)",
    "Overwrites a range of a Sheet with values from a JSON file shaped like  "
    "{\"range\": \"Sheet1!A1:B2\", \"values\": "
    "[[\"a\",\"b\"],[\"c\",\"d\"]]}",
    "user {email} update sheetrange {fileid} json file {file}",
    [F("User with access to the Sheet", "email"),
     F("Spreadsheet file ID (from its URL)", "fileid"),
     F("JSON file", "file", filepicker=True),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Clear a range in a Sheet (DESTRUCTIVE)",
    "Erases the values in a range of a Google Sheet (formatting stays).",
    "user {email} clear sheetrange {fileid} range {range}",
    [F("User with access to the Sheet", "email"),
     F("Spreadsheet file ID (from its URL)", "fileid"),
     F("Range e.g. Sheet1!A1:D50", "range"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Download a Google Doc as JSON (Docs API)",
    "Saves a Google Doc's full structure (text, styles, suggestions) as a "
    "JSON file on this PC - for scripting or records. Use Drive's download "
    "tasks for PDF / Word copies.",
    "user {email} get document {fileid} targetfolder {folder}",
    [F("User with access to the Doc", "email"),
     F("Doc file ID (from its URL)", "fileid"),
     F("Folder on this PC", "folder", default="C:\\GAMExports"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a spreadsheet from JSON (advanced)",
    "Creates a new Google Sheet from a Sheets API create request in a JSON "
    "file (title, tabs, starting data).",
    "user {email} create sheet json file {file}",
    [F("Owner email", "email"), F("JSON file", "file", filepicker=True),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Licenses": [
  T("Show license counts", "Domain totals by SKU.", "show licenses",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List available license SKUs (names GAM accepts)",
    "Lists the license product/SKU names GAM recognizes for your account - the "
    "exact names and SKU ids you can type into the other license tasks. Handy "
    "when you are not sure what to call a license.",
    "show configlicenseskus",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List users with a specific license",
    "Lists every user who has the given license, so you can see who is using "
    "it. Enter a license NAME (e.g. 'Education Plus') or a SKU id. Use the "
    "dropdown to send the result to a Google Sheet instead of the screen.",
    "print licenses skus {license:sku} {todrive}",
    [F("License name or SKU", "sku"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add license to user", "Assigns a license to a user. Enter a license "
    "NAME (e.g. 'Education Plus') or a SKU id.",
    "user {email} add license {license:sku}",
    [F("User email", "email"), F("License name or SKU", "sku"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove license from user", "Removes a license from a user. Enter a "
    "license NAME or a SKU id.",
    "user {email} delete license {license:sku}",
    [F("User email", "email"), F("License name or SKU", "sku"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Bulk add/remove licenses (from CSV file)",
    "Reads a CSV that has 'Email' and 'License' columns and adds or removes "
    "that license for each user. The License cell can be a friendly NAME "
    "(e.g. 'Google Workspace for Education Standard', or just 'Education "
    "Plus') OR a SKU id (e.g. 1010310005). It lists the changes and asks you "
    "to confirm before doing anything.",
    "", [F("CSV file", "file", filepicker=True),
         F("Action", "action", valuemap={"Add": "add", "Remove": "delete"})],
    destructive=True, workflow="bulklicense_csv"),
  T("Bulk add/remove licenses (from Google Sheet)",
    "Same as the CSV version but reads a Google Sheet (columns 'Email' and "
    "'License'). Give an admin who can open the sheet, the sheet's file ID "
    "(the long part of its URL), and the tab name.",
    "", [F("Admin who can open the sheet", "user"),
         F("Sheet file ID (from the URL)", "fileid"),
         F("Tab name e.g. Sheet1", "sheet"),
         F("Action", "action", valuemap={"Add": "add", "Remove": "delete"})],
    destructive=True, workflow="bulklicense_sheet"),
  # ---------------------------------------------------------------------------
  # BULK license actions by SCOPE - assign / remove / swap a license across an
  # OU, group, query, CSV, or everyone. Enter a license NAME (e.g. 'Education
  # Plus') or a SKU id; the name is translated for you.
  # ---------------------------------------------------------------------------
  T("BULK: assign a license to many users (by OU / group / query / CSV)",
    "Assigns the same license to every user in the chosen scope - e.g. give "
    "Education Plus to all students in an OU. Enter a license NAME or SKU.",
    "{userscope:usertype:userval} add license {license:sku}",
    [*_user_scope(),
     F("License name or SKU", "sku"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: remove a license from many users (DESTRUCTIVE)",
    "Removes the same license from every user in the chosen scope. Enter a "
    "license NAME or SKU.",
    "{userscope:usertype:userval} delete license {license:sku}",
    [*_user_scope(),
     F("License name or SKU", "sku"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: swap a license for many users (move A -> B)",
    "Moves every user in the chosen scope from one license to another - e.g. "
    "upgrade a grade from Education Fundamentals to Education Plus. Enter both "
    "as a license NAME or SKU.",
    "{userscope:usertype:userval} update license {license:newsku} from {license:oldsku}",
    [*_user_scope(),
     F("NEW license name or SKU", "newsku"),
     F("OLD license name or SKU (being replaced)", "oldsku"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: sync a license - exact match (DESTRUCTIVE)",
    "Makes EXACTLY the users in the chosen scope hold a license: users in the "
    "scope without it get it, and users OUTSIDE the scope who have it lose it. "
    "Add  preview  in the advanced box to see the changes first, or  addonly "
    " /  removeonly  to do only half. Enter a license NAME or SKU.",
    "{userscope:usertype:userval} sync license {license:sku}",
    [*_user_scope(), F("License name or SKU", "sku"),
     F("Extra arguments (advanced, e.g. preview)", "extra", False,
       rawappend=True)],
    destructive=True),
 ],
 "Vault": [
  # Google Vault: legal holds, matters, and exports for eDiscovery and
  # retention. Complex options (queries, date ranges, export format/region,
  # encryption) go in each task's advanced box - see the GAM wiki 'Vault'
  # page. Matter and Hold/Export items may be given by NAME or by ID.
  T("Create matter",
    "Creates a Vault matter (the container that holds legal holds and "
    "exports). Collaborators are people allowed to work in the matter.",
    "create matter name {name} [description {desc}] [collaborators {collaborators}]",
    [F("Matter name", "name"), F("Description (optional)", "desc", False),
     F("Collaborator email(s), comma separated (optional)", "collaborators", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update matter (name / description / collaborators)",
    "Renames a matter, changes its description, or adds/removes "
    "collaborators. Leave a field blank to leave it unchanged.",
    "update matter {matter} [name {name}] [description {desc}] [addcollaborators {addcollab}] [removecollaborators {removecollab}]",
    [F("Matter (name or ID)", "matter"), F("New name (optional)", "name", False),
     F("New description (optional)", "desc", False),
     F("Add collaborator(s), comma separated (optional)", "addcollab", False),
     F("Remove collaborator(s), comma separated (optional)", "removecollab", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Close matter",
    "Closes a matter. Its holds are released. It can be reopened later.",
    "close matter {matter}",
    [F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Reopen matter",
    "Reopens a previously closed matter.",
    "reopen matter {matter}",
    [F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete matter (DESTRUCTIVE)",
    "Deletes a matter. The matter must be closed first. Recoverable with "
    "Undelete for a limited time.",
    "delete matter {matter}",
    [F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Undelete matter",
    "Restores a recently deleted matter.",
    "undelete matter {matter}",
    [F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Matter info",
    "Shows a matter's details. 'full' also lists its holds and permissions.",
    "info matter {matter} {detail}",
    [F("Matter (name or ID)", "matter"),
     F("Detail", "detail", choices=["basic", "full"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List matters",
    "Prints Vault matters. Optionally filter by state.",
    "print matters [matterstate {state}] {todrive}",
    [F("State (optional)", "state", False,
       valuemap={"": "", "Open": "OPEN", "Closed": "CLOSED", "Deleted": "DELETED"}),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create hold",
    "Places a legal hold. Corpus is the data type. Scope it to specific "
    "accounts (comma separated) OR an OU. Query/terms/date-range options go "
    "in the advanced box, e.g.  terms project falcon  |  "
    "starttime 2025-01-01 endtime 2025-12-31.",
    "create hold matter {matter} name {name} corpus {corpus} [accounts {accounts}] [orgunit {ou}]",
    [F("Matter (name or ID)", "matter"), F("Hold name", "name"),
     F("Data type", "corpus", valuemap={"Gmail": "mail", "Drive": "drive",
       "Groups": "groups", "Calendar": "calendar", "Chat": "hangouts_chat",
       "Voice": "voice"}),
     F("Account email(s), comma separated (optional)", "accounts", False),
     F("OU path instead of accounts (optional)", "ou", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update hold (add/remove accounts)",
    "Adds or removes held accounts on an existing hold. Comma separate "
    "multiple addresses.",
    "update hold {hold} matter {matter} [addaccounts {addaccounts}] [removeaccounts {removeaccounts}]",
    [F("Hold (name or ID)", "hold"), F("Matter (name or ID)", "matter"),
     F("Add account(s) (optional)", "addaccounts", False),
     F("Remove account(s) (optional)", "removeaccounts", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete hold (DESTRUCTIVE)",
    "Removes a legal hold. Held data is no longer preserved by this hold.",
    "delete hold {hold} matter {matter}",
    [F("Hold (name or ID)", "hold"), F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Hold info",
    "Shows a hold's scope, corpus, and query.",
    "info hold {hold} matter {matter}",
    [F("Hold (name or ID)", "hold"), F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List holds",
    "Prints the holds in one or more matters (comma separate matter IDs).",
    "print holds [matters {matters}] {todrive}",
    [F("Matter(s) (name/ID, comma separated, optional)", "matters", False),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- Saved search queries (reusable searches inside a matter) ---
  T("Create a saved search query",
    "Saves a reusable search inside a matter (the same thing as a saved query "
    "in the Vault web UI). Scope it to accounts (comma separated) OR an OU. "
    "Search terms and date range go in the advanced box, e.g.  terms project "
    "falcon  |  starttime 2025-01-01 endtime 2025-12-31.",
    "create vaultquery {matter} name {name} corpus {corpus} [accounts {accounts}] [orgunit {ou}]",
    [F("Matter (name or ID)", "matter"), F("Saved query name", "name"),
     F("Data type", "corpus", valuemap={"Gmail": "mail", "Drive": "drive",
       "Groups": "groups", "Calendar": "calendar", "Chat": "hangouts_chat",
       "Voice": "voice", "Gemini": "gemini"}),
     F("Account email(s), comma separated (optional)", "accounts", False),
     F("OU path instead of accounts (optional)", "ou", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List saved queries (CSV/Sheet)",
    "Prints the saved search queries in one or more matters.",
    "print vaultqueries [matters {matters}] {todrive}",
    [F("Matter(s) (name/ID, comma separated, optional)", "matters", False),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Saved query info",
    "Shows one saved query's scope and search terms.",
    "info vaultquery {query} matter {matter}",
    [F("Saved query (name or ID)", "query"), F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a saved query (DESTRUCTIVE)",
    "Deletes a saved search query from a matter. Exports already made from it "
    "are not affected.",
    "delete vaultquery {query} matter {matter}",
    [F("Saved query (name or ID)", "query"), F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Count matching items (before exporting)",
    "Reports how many messages match a search, so you can size an export "
    "before you run it. Scope to accounts (comma separated) OR an OU. Add "
    "date range in the advanced box, e.g.  starttime 2025-01-01 endtime "
    "2025-12-31.",
    "print vaultcounts matter {matter} corpus {corpus} [accounts {accounts}] [orgunit {ou}] {todrive}",
    [F("Matter (name or ID)", "matter"),
     F("Data type", "corpus", valuemap={"Gmail": "mail", "Groups": "groups"}),
     F("Account email(s), comma separated (optional)", "accounts", False),
     F("OU path instead of accounts (optional)", "ou", False),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create export",
    "Starts a Vault export. Scope to accounts (comma separated) OR an OU. "
    "Format and region options are in the advanced box, e.g.  format mbox  |  "
    "region us  |  starttime 2025-01-01 endtime 2025-12-31.",
    "create export matter {matter} name {name} corpus {corpus} [accounts {accounts}] [orgunit {ou}]",
    [F("Matter (name or ID)", "matter"), F("Export name", "name"),
     F("Data type", "corpus", valuemap={"Gmail": "mail", "Drive": "drive",
       "Groups": "groups", "Calendar": "calendar", "Chat": "hangouts_chat",
       "Voice": "voice"}),
     F("Account email(s), comma separated (optional)", "accounts", False),
     F("OU path instead of accounts (optional)", "ou", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Download export",
    "Downloads a finished export's files. By default they land in the "
    "current folder; add  targetfolder C:\\path  in the advanced box to "
    "choose where.",
    "download export {export} matter {matter}",
    [F("Export (name or ID)", "export"), F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export info",
    "Shows an export's status (check here before downloading) and details.",
    "info export {export} matter {matter}",
    [F("Export (name or ID)", "export"), F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete export (DESTRUCTIVE)",
    "Deletes an export and its generated files from Vault.",
    "delete export {export} matter {matter}",
    [F("Export (name or ID)", "export"), F("Matter (name or ID)", "matter"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List exports",
    "Prints all Vault exports.",
    "print exports {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # Google Takeout / Cloud Storage buckets (e.g. an organization-wide data
  # export). Bucket names look like takeout-export-xxxxxxxx-....
  # ---------------------------------------------------------------------------
  T("Download a Takeout export bucket",
    "Downloads every file in a Google Takeout (data export) storage bucket "
    "into a folder on this PC. These exports can be very large.",
    "download storagebucket {bucket} targetfolder {folder}",
    [F("Bucket e.g. takeout-export-6454fb47-...", "bucket"),
     F("Folder on this PC", "folder", default="C:\\GAMExports"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Copy a Takeout bucket to your own bucket",
    "Copies a Takeout export bucket into another Cloud Storage bucket you own "
    "(optionally under a folder prefix), before the export expires.",
    "copy storagebucket sourcebucket {source} targetbucket {target} [targetprefix {prefix}]",
    [F("Source bucket (takeout-export-...)", "source"),
     F("Target bucket", "target"),
     F("Target folder prefix (optional) e.g. export_2027/", "prefix", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Download one Cloud Storage file",
    "Downloads a single object from Cloud Storage. Name looks like "
    "gs://bucket/path/file or bucket/path/file.",
    "download storagefile {object} targetfolder {folder}",
    [F("Object e.g. gs://bucket/path/file.zip", "object"),
     F("Folder on this PC", "folder", default="C:\\GAMExports"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Copy a saved search to another matter",
    "Copies a saved Vault search (query) into another matter - reuse a "
    "search across investigations.",
    "copy vaultquery {matter} {query} targetmatter {target}",
    [F("Source matter (name or ID)", "matter"),
     F("Saved search (name or ID)", "query"),
     F("Target matter (name or ID)", "target"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Mobile Devices": [
  T("List mobile devices",
    "Prints managed mobile devices (phones/tablets).",
    "print mobile {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Mobile device info",
    "Shows details for one device by its resource ID (from List mobile).",
    "info mobile {resourceid}",
    [F("Device resource ID", "resourceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Approve mobile device",
    "Approves a pending device for access.",
    "update mobile {resourceid} action approve",
    [F("Device resource ID", "resourceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Block mobile device",
    "Blocks a device from accessing account data.",
    "update mobile {resourceid} action block",
    [F("Device resource ID", "resourceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Account-wipe mobile device (DESTRUCTIVE)",
    "Removes the account and its data from the device (not a full factory "
    "wipe). Use for a lost or reassigned device.",
    "update mobile {resourceid} action accountwipe",
    [F("Device resource ID", "resourceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Delete mobile device (DESTRUCTIVE)",
    "Removes the device record from management.",
    "delete mobile {resourceid}",
    [F("Device resource ID", "resourceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Cloud Identity Devices": [
  # The newer Cloud Identity device API (Endpoint Verification, company-owned
  # inventory, per-user device access). This is SEPARATE from the older
  # "Mobile Devices" section above: a "device" is the hardware; a "device user"
  # is one account's presence on that device. IDs come from the List tasks.
  T("List devices (CSV/Sheet)",
    "Prints devices known to Cloud Identity (Endpoint Verification and "
    "company-owned inventory).",
    "print devices {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Device info",
    "Shows one device by its ID (from List devices).",
    "info device {deviceid}",
    [F("Device ID", "deviceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List device users (CSV/Sheet)",
    "Prints the per-account device presences (which accounts are signed in on "
    "which devices).",
    "print deviceusers {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Device user info",
    "Shows one device user by its ID (from List device users).",
    "info deviceuser {deviceuserid}",
    [F("Device user ID", "deviceuserid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Approve a device user",
    "Approves a pending account presence on a device so it can access data.",
    "approve deviceuser {deviceuserid} doit",
    [F("Device user ID", "deviceuserid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Block a device user",
    "Blocks an account's presence on a device from accessing data.",
    "block deviceuser {deviceuserid} doit",
    [F("Device user ID", "deviceuserid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Wipe a device user (DESTRUCTIVE)",
    "Wipes ONLY this account's data from the device (a selective wipe). Use "
    "for a lost or reassigned device where you keep the hardware record.",
    "wipe deviceuser {deviceuserid} doit",
    [F("Device user ID", "deviceuserid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Cancel a pending device-user wipe",
    "Cancels a wipe that was requested but has not completed yet.",
    "cancelwipe deviceuser {deviceuserid} doit",
    [F("Device user ID", "deviceuserid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Wipe a device (DESTRUCTIVE)",
    "Factory-wipes the WHOLE device (all data, all accounts). Use for a lost "
    "company-owned device.",
    "wipe device {deviceid} doit",
    [F("Device ID", "deviceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Cancel a pending device wipe",
    "Cancels a full-device wipe that was requested but has not completed yet.",
    "cancelwipe device {deviceid} doit",
    [F("Device ID", "deviceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a device (DESTRUCTIVE)",
    "Removes the device record from Cloud Identity. Does not wipe the device.",
    "delete device {deviceid} doit",
    [F("Device ID", "deviceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Register a company-owned device (advanced)",
    "Adds a company-owned device to inventory by serial number so it can be "
    "managed and later claimed by a user.",
    "create device serialnumber {sn} devicetype {devicetype} [assettag {assettag}]",
    [F("Serial number", "sn"),
     F("Device type", "devicetype", valuemap={"Android": "android",
       "ChromeOS": "chrome_os", "Google Sync": "google_sync", "iOS": "ios",
       "Linux": "linux", "macOS": "mac_os", "Windows": "windows"}),
     F("Asset tag (optional)", "assettag", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a device user (DESTRUCTIVE)",
    "Removes a user's account from a managed device record. Get the device "
    "user ID from 'List device users'.",
    "delete deviceuser {deviceuserid} doit",
    [F("Device user ID", "deviceuserid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Custom Schemas": [
  T("List schemas",
    "Prints the custom user schemas defined for the domain.",
    "print schemas {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Schema info",
    "Shows one schema's fields.",
    "info schema {name}",
    [F("Schema name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create schema (advanced)",
    "Creates a custom user schema. Define at least one field in the advanced "
    "box, e.g.  field StudentID type string endfield  field GradYear type "
    "int64 endfield.",
    "create schema {name}",
    [F("Schema name", "name"),
     F("Field definitions (see example)", "extra", False, rawappend=True)]),
  T("Delete schema (DESTRUCTIVE)",
    "Deletes a custom user schema and all values stored in it.",
    "delete schema {name}",
    [F("Schema name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Set a user's schema value",
    "Sets one custom-schema field on a user. Field is Schema.Field, e.g. "
    "SIS.StudentID.",
    "update user {email} {schemafield} {value}",
    [F("User email", "email"), F("Schema.Field e.g. SIS.StudentID", "schemafield"),
     F("Value", "value"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: set a schema field for many users from a CSV",
    "Sets a custom-schema field (like SIS.StudentID or SIS.GradYear) on many "
    "users in ONE pass, using a DIFFERENT value per row from a CSV. The CSV "
    "needs an email column and a value column; column names are case-sensitive. "
    "The schema and field must already exist (see 'Create schema').",
    "csv {file} gam update user ~{emailcol} {schemafield} ~{valuecol}",
    [F("CSV file", "file", filepicker=True),
     F("Email column header", "emailcol", default="Email"),
     F("Schema.Field e.g. SIS.StudentID", "schemafield"),
     F("Value column header", "valuecol", default="Value"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add a field to a schema",
    "Adds one field to an existing custom schema (existing fields stay).",
    "update schema {name} field {field} type {ftype} endfield",
    [F("Schema name", "name"), F("New field name", "field"),
     F("Field type", "ftype", valuemap={"Text": "string",
       "Whole number": "int64", "Decimal number": "double",
       "True / false": "bool", "Date": "date", "Email": "email",
       "Phone": "phone"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove a field from a schema (DESTRUCTIVE)",
    "Deletes one field from a custom schema - every user's value for it is "
    "lost.",
    "update schema {name} deletefield {field}",
    [F("Schema name", "name"), F("Field name", "field"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Contacts": [
  T("List domain shared contacts",
    "Prints the domain's shared (external) contacts.",
    "print contacts {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Contact info",
    "Shows one shared contact by its ID.",
    "info contacts {contactid}",
    [F("Contact ID", "contactid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create shared contact (advanced)",
    "Creates a domain shared contact. Put the details in the advanced box, "
    "e.g.  name 'Jane Vendor' email work jane@vendor.com organization "
    "'Vendor Inc'.",
    "create contact",
    [F("Contact details (see example)", "extra", False, rawappend=True)]),
  T("BULK: import shared contacts from a CSV",
    "Creates many domain shared contacts in ONE pass from a CSV - e.g. import a "
    "board, vendor, or partner directory so it shows up in everyone's "
    "auto-complete. The CSV needs first-name, last-name, and email columns; "
    "column names are case-sensitive. Add more fields (organization, phone) in "
    "the advanced box with tilde columns, e.g.  organization ~Company.",
    "csv {file} gam create contact givenname ~{firstcol} familyname ~{lastcol} email work ~{emailcol} primary",
    [F("CSV file", "file", filepicker=True),
     F("First-name column header", "firstcol", default="First"),
     F("Last-name column header", "lastcol", default="Last"),
     F("Email column header", "emailcol", default="Email"),
     F("Extra arguments (advanced, e.g. organization ~Company)", "extra", False,
       rawappend=True)]),
  T("Update shared contact (advanced)",
    "Changes a domain shared contact by ID. Put the changes in the advanced "
    "box, e.g.  name 'Jane Vendor' email work jane@vendor.com organization "
    "'Vendor Inc'.",
    "update contacts {contactid}",
    [F("Contact ID", "contactid"),
     F("Changes (see example)", "extra", False, rawappend=True)]),
  T("Delete shared contact (DESTRUCTIVE)",
    "Deletes a domain shared contact by ID.",
    "delete contacts {contactid}",
    [F("Contact ID", "contactid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # --- Domain contacts (People API) ---
  T("List domain contacts - People API (CSV/Sheet)",
    "Prints the domain's directory contacts using the newer People API. Use "
    "this if 'List domain shared contacts' is missing newer entries.",
    "print domaincontacts {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- A single user's personal contacts ---
  T("List a user's personal contacts (CSV/Sheet)",
    "Prints the contacts saved in one user's own Google Contacts.",
    "user {email} print contacts {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's 'Other contacts' (CSV/Sheet)",
    "Prints the auto-collected 'Other contacts' (people a user has emailed but "
    "never saved) for one user.",
    "user {email} print othercontacts {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove a bad address from EVERYONE's 'Other contacts' (DESTRUCTIVE)",
    "Removes an auto-collected 'Other contact' matching an email from EVERY "
    "user (or a narrower scope) - for example, scrub a fraudulent or spoofed "
    "address so it stops auto-completing in everyone's Compose box after a "
    "phishing incident. Matches by an email pattern. Default scope is ALL "
    "users.",
    "{mailscope:scopetype:scopeval} delete othercontacts emailmatchpattern {pattern}",
    [F("Email to remove e.g. fakeuser@baddomain.com", "pattern"),
     F("Scope", "scopetype", valuemap={"All users": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # --- A user's contact groups (labels in Contacts) ---
  T("List a user's contact groups (CSV/Sheet)",
    "Prints the contact groups (labels) in one user's Google Contacts.",
    "user {email} print contactgroups {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a contact group (for a user)",
    "Creates a new contact group (label) in a user's Google Contacts.",
    "user {email} create contactgroup name {name}",
    [F("User email", "email"), F("Group name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a contact group (DESTRUCTIVE)",
    "Deletes a contact group (label) from a user's Google Contacts. The "
    "contacts themselves are not deleted.",
    "user {email} delete contactgroups {group}",
    [F("User email", "email"), F("Contact group name or ID", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Remove duplicate personal contacts (DESTRUCTIVE)",
    "Removes duplicate email addresses from a user's personal contacts. Add "
    " matchtype  in the advanced box to count only same-type (work/home) "
    "addresses as duplicates.",
    "user {email} dedup contacts",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List a user's contact delegates - CSV/Sheet",
    "Prints who can manage a user's Contacts on their behalf.",
    "user {email} print contactdelegates {todrive}",
    [F("User email", "email"), *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add a contact delegate",
    "Lets another user manage this user's Contacts (e.g. an assistant).",
    "user {email} create contactdelegate {delegate}",
    [F("User email", "email"), F("Delegate email", "delegate"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove a contact delegate (DESTRUCTIVE)",
    "Stops another user from managing this user's Contacts.",
    "user {email} delete contactdelegate {delegate}",
    [F("User email", "email"), F("Delegate email", "delegate"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Replace a domain in a user's contacts",
    "Changes an old email domain to a new one in every one of a user's "
    "personal contacts - e.g. after an organization renames its domain.",
    "user {email} replacedomain contacts domain {old} {new}",
    [F("User email", "email"), F("Old domain e.g. oldname.org", "old"),
     F("New domain e.g. newname.org", "new"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Copy or move 'Other contacts' into My Contacts",
    "Takes the auto-saved 'Other contacts' (people the user emailed) and "
    "copies them into My Contacts, or moves them (removing them from Other "
    "contacts). Optional query narrows which ones.",
    "user {email} {action} othercontacts [query {query}]",
    [F("User email", "email"),
     F("Action", "action", valuemap={"Copy": "copy", "Move": "move"}),
     F("Query (optional) e.g. a name or domain", "query", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Admin Roles & Privileges": [
  T("List admin role assignments",
    "Prints who is assigned which admin role and at what scope.",
    "print admins {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List admin roles",
    "Prints all built-in and custom admin roles.",
    "print adminroles {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List privileges",
    "Prints all admin privileges that roles can grant.",
    "print privileges {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Assign admin role (whole domain)",
    "Grants a user an admin role across the whole domain. Role is a role "
    "name or ID (see List admin roles).",
    "create admin {who} {role} customer",
    [F("User email", "who"), F("Role name or ID", "role"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Assign admin role (scoped to an OU)",
    "Grants a user an admin role limited to one OU.",
    "create admin {who} {role} org_unit {ou}",
    [F("User email", "who"), F("Role name or ID", "role"),
     F("OU path", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove admin assignment (DESTRUCTIVE)",
    "Revokes an admin role assignment by its assignment ID (from List admin "
    "role assignments).",
    "delete admin {assignmentid}",
    [F("Role assignment ID", "assignmentid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create custom admin role",
    "Creates a new custom admin role. Add privileges afterward.",
    "create adminrole {name} [description {desc}]",
    [F("Role name", "name"), F("Description (optional)", "desc", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Admin role details (privileges)",
    "Shows an admin role and every privilege it grants.",
    "info adminrole {role} privileges",
    [F("Role name or ID", "role"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rename or edit a custom admin role",
    "Changes a custom admin role's name and/or description. To change its "
    "privileges, add  privileges <list>  in the advanced box.",
    "update adminrole {role} [name {newname}] [description {desc}]",
    [F("Role name or ID", "role"), F("New name (optional)", "newname", False),
     F("New description (optional)", "desc", False),
     F("Extra arguments (advanced, e.g. privileges ...)", "extra", False,
       rawappend=True)]),
  T("Delete a custom admin role (DESTRUCTIVE)",
    "Deletes a custom admin role. Remove it from any admins first.",
    "delete adminrole {role}",
    [F("Role name or ID", "role"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Data Transfers": [
  T("Transfer data to another user",
    "Transfers a leaving user's app data (e.g. 'Drive and Docs', 'Calendar') "
    "to another user. Service list is comma separated, no spaces.",
    "create datatransfer {olduser} {services} {newuser}",
    [F("Old (leaving) user", "olduser"),
     F("Service(s) e.g. Drive and Docs", "services", default="Drive and Docs"),
     F("New (receiving) user", "newuser"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List data transfers",
    "Prints past and in-progress data transfers.",
    "print transfers {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Data transfer info",
    "Shows the status of one transfer by its ID.",
    "info transfer {transferid}",
    [F("Transfer ID", "transferid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List transferable apps",
    "Lists the applications whose data can be transferred between users (e.g. "
    "'Drive and Docs', 'Calendar'), with their app IDs - handy for confirming "
    "the exact service names to use in a transfer.",
    "print transferapps",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Chrome Printers": [
  T("List printers",
    "Prints the Chrome printers registered in the domain.",
    "print printers {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Printer info",
    "Shows details for one Chrome printer by ID.",
    "info printer {printerid}",
    [F("Printer ID", "printerid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create printer (advanced)",
    "Registers a Chrome printer. Provide attributes in the advanced box, "
    "e.g.  displayname 'Library HP' orgunitid /Staff makeandmodel 'HP "
    "LaserJet' uri ipp://... ",
    "create printer",
    [F("Printer attributes (see example)", "extra", False, rawappend=True)]),
  T("Delete printer (DESTRUCTIVE)",
    "Removes a Chrome printer by ID.",
    "delete printer {printerid}",
    [F("Printer ID", "printerid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List printer models",
    "Prints the printer models Chrome supports (for makeandmodel values).",
    "print printermodels {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update a printer",
    "Changes a Chrome printer. Put the changes in the box, e.g.  displayname "
    "\"Library Printer\"  description \"Room 12\"  ou /Library",
    "update printer {printerid}",
    [F("Printer ID", "printerid"),
     F("Changes (required, see example)", "changes", rawappend=True)]),
 ],
 "Buildings, Features & Rooms": [
  T("List buildings",
    "Prints the buildings defined for resource booking.",
    "print buildings {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create building",
    "Creates a building. Add floors/address in the advanced box, e.g. "
    "floors '1,2,3'.",
    "create building {name}",
    [F("Building name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete building (DESTRUCTIVE)",
    "Deletes a building by its ID.",
    "delete building {buildingid}",
    [F("Building ID", "buildingid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List features",
    "Prints room features (e.g. Projector, Whiteboard).",
    "print features {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create feature",
    "Creates a room feature that resources can advertise.",
    "create feature name {name}",
    [F("Feature name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List calendar resources (rooms)",
    "Prints bookable resources such as rooms and equipment.",
    "print resources {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create calendar resource (room)",
    "Creates a bookable resource. Add type/capacity/building in the advanced "
    "box, e.g.  capacity 30 buildingid Main type Room.",
    "create resource {resourceid} {name}",
    [F("Resource ID (short unique code)", "resourceid"),
     F("Display name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete calendar resource (DESTRUCTIVE)",
    "Deletes a bookable resource by ID.",
    "delete resource {resourceid}",
    [F("Resource ID", "resourceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Building info",
    "Shows a building's details (address, floors, and so on).",
    "info building {buildingid}",
    [F("Building ID", "buildingid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update a building",
    "Changes a building's details. Put the changes in the box, e.g.  name "
    "\"Main Office\"  floors 1,2,3  address \"123 Main St\"  city Austin",
    "update building {buildingid}",
    [F("Building ID", "buildingid"),
     F("Changes (required, see example)", "changes", rawappend=True)]),
  T("Rename a feature",
    "Renames a room feature (e.g. 'Projector' to 'Projector - HDMI').",
    "update feature {name} name {newname}",
    [F("Current feature name", "name"), F("New name", "newname"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Room / resource info",
    "Shows a bookable room or resource. Add  acls  in the advanced box to see "
    "who can book it.",
    "info resource {resourceid}",
    [F("Resource ID", "resourceid"),
     F("Extra arguments (advanced, e.g. acls)", "extra", False,
       rawappend=True)]),
  T("Update a room / resource",
    "Changes a bookable room or resource. Put the changes in the box, e.g.  "
    "name \"Room 101\"  capacity 30  buildingid <ID>  floor 1  addfeatures "
    "Projector",
    "update resource {resourceid}",
    [F("Resource ID", "resourceid"),
     F("Changes (required, see example)", "changes", rawappend=True)]),
  T("Delete a feature (DESTRUCTIVE)",
    "Deletes a room feature. Remove it from rooms first.",
    "delete feature {name}",
    [F("Feature name", "name"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Reseller / Channel": [
  # For resellers and MSPs managing customers through the Google Channel /
  # Reseller APIs. These are read-only listings; the actual provisioning
  # (create/transfer/cancel subscriptions) is high-stakes - use GAM directly or
  # the advanced box for those.
  T("List reseller subscriptions - CSV/Sheet",
    "Prints the subscriptions you manage as a reseller, across your customers.",
    "print resoldsubscriptions {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List channel customers - CSV/Sheet",
    "Prints the customers in your Channel Services (reseller) account.",
    "print channelcustomers {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List channel customer entitlements - CSV/Sheet",
    "Prints the entitlements (what each customer is licensed for) in your "
    "Channel Services account.",
    "print channelcustomercentitlements {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List channel offers - CSV/Sheet",
    "Prints the offers available in your Channel Services account.",
    "print channeloffers {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List channel products - CSV/Sheet",
    "Prints the products available in your Channel Services account.",
    "print channelproducts {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List channel SKUs - CSV/Sheet",
    "Prints the SKUs available in your Channel Services account.",
    "print channelskus {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # Reseller actions (Google Workspace reseller / partner accounts only).
  # Customer ID = the customer's domain or ID. SKU = a license name or SKU ID.
  # ---------------------------------------------------------------------------
  T("Reseller customer info",
    "Shows a customer's details on your reseller account.",
    "info resoldcustomer {customerid}",
    [F("Customer domain or ID", "customerid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a reseller customer",
    "Creates (or transfers in, with the customer's transfer token) a customer "
    "on your reseller account.",
    "create resoldcustomer {domain} customer_auth_token {token} email {altemail} name {orgname} contact {contact} phone {phone} address1 {address} city {city} state {state} zipcode {zip} country {country}",
    [F("Customer domain", "domain"),
     F("Customer auth (transfer) token", "token"),
     F("Alternate (non-domain) email", "altemail"),
     F("Organization name", "orgname"), F("Contact name", "contact"),
     F("Phone", "phone"), F("Street address", "address"), F("City", "city"),
     F("State / region", "state"), F("ZIP / postal code", "zip"),
     F("Country code e.g. US", "country"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update a reseller customer",
    "Changes a customer's details. Put the changes in the box, e.g.  contact "
    "\"Jane Doe\"  phone 555-0100  email admin@example.org",
    "update resoldcustomer {customerid}",
    [F("Customer domain or ID", "customerid"),
     F("Changes (required, see example)", "changes", rawappend=True)]),
  T("Reseller subscription info",
    "Shows one subscription (plan, seats, renewal, status).",
    "info resoldsubscription {customerid} {license:sku}",
    [F("Customer domain or ID", "customerid"),
     F("License name or SKU", "sku"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a reseller subscription",
    "Adds a subscription for a customer with a plan and seat count.",
    "create resoldsubscription {customerid} sku {license:sku} plan {plan} seats {seats}",
    [F("Customer domain or ID", "customerid"),
     F("License name or SKU", "sku"),
     F("Plan", "plan", valuemap={
       "Annual, paid monthly": "annual_monthly_pay",
       "Annual, paid yearly": "annual_yearly_pay",
       "Flexible": "flexible", "Trial": "trial", "Free": "free"}),
     F("Seats", "seats"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change a subscription's seats",
    "Changes the number of seats on a customer's subscription.",
    "update resoldsubscription {customerid} {license:sku} seats {seats}",
    [F("Customer domain or ID", "customerid"),
     F("License name or SKU", "sku"), F("New seat count", "seats"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change a subscription's renewal setting",
    "Sets what happens at the end of an annual commitment.",
    "update resoldsubscription {customerid} {license:sku} renewal {renewal}",
    [F("Customer domain or ID", "customerid"),
     F("License name or SKU", "sku"),
     F("Renewal", "renewal", valuemap={
       "Auto-renew, paid monthly": "auto_renew_monthly_pay",
       "Auto-renew, paid yearly": "auto_renew_yearly_pay",
       "Renew current users, paid monthly": "renew_current_users_monthly_pay",
       "Renew current users, paid yearly": "renew_current_users_yearly_pay",
       "Switch to pay as you go": "switch_to_pay_as_you_go",
       "Cancel at end of term": "cancel"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change a subscription's plan",
    "Moves a customer's subscription to a different plan.",
    "update resoldsubscription {customerid} {license:sku} plan {plan}",
    [F("Customer domain or ID", "customerid"),
     F("License name or SKU", "sku"),
     F("New plan", "plan", valuemap={
       "Annual, paid monthly": "annual_monthly_pay",
       "Annual, paid yearly": "annual_yearly_pay",
       "Flexible": "flexible", "Trial": "trial"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Suspend, activate, or start paid service (DESTRUCTIVE)",
    "Suspends or re-activates a subscription, or converts a trial to paid "
    "service.",
    "update resoldsubscription {customerid} {license:sku} {action}",
    [F("Customer domain or ID", "customerid"),
     F("License name or SKU", "sku"),
     F("Action", "action", valuemap={"Suspend": "suspend",
       "Activate": "activate",
       "Start paid service (end the trial)": "startpaidservice"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Cancel, downgrade, or transfer a subscription (DESTRUCTIVE)",
    "Ends a subscription on your reseller account: cancel it, downgrade it, "
    "or transfer the customer to buying directly from Google.",
    "delete resoldsubscription {customerid} {license:sku} {how}",
    [F("Customer domain or ID", "customerid"),
     F("License name or SKU", "sku"),
     F("How", "how", valuemap={"Cancel": "cancel", "Downgrade": "downgrade",
       "Transfer to direct billing": "transfer_to_direct"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Marketing & Analytics": [
  # User-linked Google Marketing Platform products (Analytics, Tag Manager,
  # Looker Studio) plus YouTube. Read the accounts/assets a given user can see.
  T("List a user's Google Analytics accounts - CSV/Sheet",
    "Prints the Google Analytics accounts a user has access to.",
    "user {email} print analyticaccounts {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's Analytics account summaries - CSV/Sheet",
    "Prints a summarized view of a user's Analytics accounts and their "
    "properties.",
    "user {email} print analyticaccountsummaries {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's Analytics properties - CSV/Sheet",
    "Prints the Google Analytics properties a user can access.",
    "user {email} print analyticproperties {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's Analytics data streams - CSV/Sheet",
    "Prints the data streams under a user's Analytics properties.",
    "user {email} print analyticdatastreams {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's Tag Manager accounts - CSV/Sheet",
    "Prints the Google Tag Manager accounts a user has access to (use the "
    "advanced box / GAM directly to drill into containers and workspaces).",
    "user {email} print tagmanagerccounts {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's Looker Studio (Data Studio) permissions - CSV/Sheet",
    "Prints who has access to a user's Looker Studio (formerly Data Studio) "
    "assets - a sharing audit for reports and data sources.",
    "user {email} print datastudiopermissions {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a user's Looker Studio (Data Studio) assets",
    "Lists a user's Looker Studio reports and data sources.",
    "user {email} show datastudioassets",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's YouTube channels - CSV/Sheet",
    "Prints the YouTube channels associated with a user's account.",
    "user {email} print youtubechannels {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List Tag Manager containers - CSV/Sheet",
    "Prints the containers in a Tag Manager account. Account looks like "
    "accounts/123456 (from 'List a user's Tag Manager accounts').",
    "user {email} print tagmanagercontainers {account} {todrive}",
    [F("User email", "email"), F("Account e.g. accounts/123456", "account"),
     *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List Tag Manager workspaces - CSV/Sheet",
    "Prints the workspaces in a container. Container looks like "
    "accounts/123456/containers/7890.",
    "user {email} print tagmanagerworkspaces {container} {todrive}",
    [F("User email", "email"),
     F("Container e.g. accounts/123456/containers/7890", "container"),
     *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List Tag Manager tags - CSV/Sheet",
    "Prints the tags in a workspace. Workspace looks like "
    "accounts/123456/containers/7890/workspaces/1.",
    "user {email} print tagmanagertags {workspace} {todrive}",
    [F("User email", "email"),
     F("Workspace e.g. accounts/123456/containers/7890/workspaces/1",
       "workspace"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List Tag Manager user permissions - CSV/Sheet",
    "Prints who has access to a Tag Manager account and at what level.",
    "user {email} print tagmanagerpermissions {account} {todrive}",
    [F("User email", "email"), F("Account e.g. accounts/123456", "account"),
     *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Share Looker Studio assets with someone",
    "Grants viewer or editor access to a user's Looker Studio (Data Studio) "
    "reports / data sources whose title matches. Who looks like "
    "user:a@example.com, group:team@example.com, or domain:example.com "
    "(comma separated).",
    "user {email} add datastudiopermissions assettype {atype} title {title} role {role} {who}",
    [F("Asset owner email", "email"),
     F("Asset type", "atype", valuemap={"Reports": "report",
       "Data sources": "datasource", "Both": "all"}),
     F("Asset title (which assets)", "title"),
     F("Role", "role", valuemap={"Viewer": "viewer", "Editor": "editor"}),
     F("Who e.g. user:a@example.com", "who"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove Looker Studio sharing (DESTRUCTIVE)",
    "Removes someone's access to a user's Looker Studio reports / data "
    "sources whose title matches.",
    "user {email} delete datastudiopermissions assettype {atype} title {title} role any {who}",
    [F("Asset owner email", "email"),
     F("Asset type", "atype", valuemap={"Reports": "report",
       "Data sources": "datasource", "Both": "all"}),
     F("Asset title (which assets)", "title"),
     F("Who e.g. user:a@example.com", "who"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List a user's Search Console sites - CSV/Sheet",
    "Prints the sites a user has in Google Search Console (Webmaster Tools) "
    "and their permission level.",
    "user {email} print webmastersites {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's verified web resources - CSV/Sheet",
    "Prints the sites and domains a user has verified with Google Site "
    "Verification.",
    "user {email} print webresources {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's Business Profile accounts - CSV/Sheet",
    "Prints the Google Business Profile (Maps / Search listing) accounts a "
    "user can manage.",
    "user {email} print businessprofileaccounts {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Customer / Settings": [
  T("Customer info",
    "Shows the account's customer settings (language, phone, address, "
    "alternate email).",
    "info customer",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Instance info",
    "Shows service/domain instance information.",
    "info instance",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update customer settings (advanced)",
    "Changes account-wide customer settings. Put changes in the advanced box, "
    "e.g.  language en  |  phone 432-555-0100  |  alternateemail "
    "admin@backupdomain.com.",
    "update customer",
    [F("Settings to change", "extra", False, rawappend=True)]),
 ],
 "Reports": [
  T("Admin activity (7 days)",
    "Who changed what in the Admin console over the last week.",
    "report admin start -7d",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Login activity (3 days)", "Recent login events across the domain.",
    "report login start -3d",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Failed sign-in attempts (7 days)",
    "Lists FAILED login attempts across the domain over the last week - a quick "
    "way to spot brute-force attempts or a user locked out. Change the window "
    "in the advanced box, e.g.  start -30d.",
    "report login start -7d event login_failure",
    [F("Extra arguments (advanced, e.g. start -30d)", "extra", False,
       rawappend=True)]),
  T("Drive activity (7 days)",
    "File create/edit/share/download events across the domain.",
    "report drive start -7d",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Token (OAuth) activity (7 days)",
    "Third-party app authorization events across the domain.",
    "report token start -7d",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("User usage snapshot", "Storage and Gmail statistics for one user.",
    "report user user {email}",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("ALL users - usage & activity report (CSV/Sheet)",
    "Usage and activity statistics for EVERY user (storage, Gmail/Drive counts, "
    "last-activity times, and more) - the all-users version of the snapshot "
    "above. Can be LARGE and slow on a big domain, and the data lags a couple "
    "of days. Narrow or focus it in the advanced box, e.g.  date 2026-09-20  |  "
    "parameters accounts:last_login_time,gmail:last_interaction_time  (see the "
    "GAM Reports wiki for parameter names).",
    "report users {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. date ... / parameters ...)", "extra",
       False, rawappend=True)]),
  T("Customer usage snapshot",
    "Account-wide usage totals (accounts, storage, app usage).",
    "report customer",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Activity report (advanced)",
    "Any activity report. Pick the app and add a date range in the advanced "
    "box, e.g.  start -30d  |  user jsmith@ex.com  |  event login_failure.",
    "report {app}",
    [F("Application", "app", choices=["admin", "login", "drive", "token",
       "calendar", "groups", "mobile", "rules", "saml", "chat", "meet",
       "user", "customer"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Usage report - users over a date range - CSV/Sheet",
    "Prints per-user usage (storage, Gmail and Drive activity, last login, and "
    "more) between two dates. Narrow it in the advanced box, e.g.  ou /Sales "
    " or  parameters accounts:last_login_time",
    "report usage user start {start} end {end} {todrive}",
    [F("Start date (YYYY-MM-DD)", "start"), F("End date (YYYY-MM-DD)", "end"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Usage report - whole organization over a date range - CSV/Sheet",
    "Prints organization-wide usage totals between two dates.",
    "report usage customer start {start} end {end} {todrive}",
    [F("Start date (YYYY-MM-DD)", "start"), F("End date (YYYY-MM-DD)", "end"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List usage report parameters - CSV/Sheet",
    "Lists the parameter names you can use to narrow the usage reports.",
    "report usageparameters {which} {todrive}",
    [F("For", "which", choices=["user", "customer"]), *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Security": [
  T("Sign user out everywhere",
    "Kills all web and device sessions. First move for a compromised "
    "account.",
    "user {email} signout",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Deprovision (offboarding)",
    "Deletes app passwords, backup codes, and OAuth tokens; optionally "
    "also signs out and disables 2SV.",
    "user {email} deprovision popimap signout turnoff2sv",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Turn 2-Step Verification OFF (DESTRUCTIVE)",
    "Disables the user's 2SV enrollment (e.g. when they lost their device "
    "and need to re-enroll). Reduces account security until re-enrolled.",
    "user {email} turnoff2sv",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Show app passwords (ASPs)",
    "Lists the user's application-specific passwords. Attackers sometimes "
    "create one to keep mailbox access after a password reset.",
    "user {email} show asps",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete all app passwords (DESTRUCTIVE)",
    "Revokes every application-specific password for the user.",
    "user {email} delete asps all",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Generate backup codes",
    "Creates a fresh set of 2SV backup codes for the user.",
    "user {email} update backupcodes",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show backup codes",
    "Shows the user's current 2SV backup codes.",
    "user {email} show backupcodes",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show mailbox rules (Gmail filters)",
    "Lists every Gmail filter (rule) on a mailbox with its conditions and "
    "actions. Attackers who phish an account often add a rule that auto-"
    "deletes or forwards incoming mail to hide their tracks. Watch for "
    "actions like trash/delete, forward to an OUTSIDE address, or "
    "skip-inbox combined with mark-as-read.",
    "user {email} show filters",
    [F("Mailbox e.g. user@example.com", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
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
    "user {email} print tokens",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Revoke one app's access",
    "Deletes the OAuth grant for a specific client ID (from Show tokens).",
    "user {email} delete tokens clientid {clientid}",
    [F("User email", "email"), F("Client ID (copy from Show OAuth tokens)", "clientid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Show security & admin alerts - CSV/Sheet",
    "Prints the alerts Google raised for the domain (suspicious logins, leaked "
    "passwords, malware/phishing, device compromise, and more) - the same "
    "alerts shown in the Admin console Alert Center. Narrow them in the advanced "
    "box, e.g.  filter \"createTime >= 2026-09-01T00:00:00Z\"  (see the GAM "
    "wiki for filter fields).",
    "print alerts {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("2-Step Verification (2SV) enrollment report - CSV/Sheet",
    "Lists every user with whether 2-Step Verification is ENROLLED and whether "
    "it is ENFORCED for them - the report to run for a security review or to "
    "find accounts that still need 2FA turned on.",
    "print users fields primaryemail,name,orgunitpath,suspended,isenrolledin2sv,isenforcedin2sv {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. query isEnrolledIn2Sv=False)", "extra",
       False, rawappend=True)]),
  T("Alert details",
    "Shows the full details of one Alert Center alert. Get the alert ID from "
    "'Show security & admin alerts'.",
    "info alert {alertid}",
    [F("Alert ID", "alertid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete an alert",
    "Deletes (dismisses) an Alert Center alert. It can be brought back with "
    "'Restore a deleted alert'.",
    "delete alert {alertid}",
    [F("Alert ID", "alertid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Restore a deleted alert",
    "Brings back an Alert Center alert that was deleted.",
    "undelete alert {alertid}",
    [F("Alert ID", "alertid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # S/MIME certificates, Gmail client-side encryption (CSE), Alert Center
  # settings and feedback, email monitors, and backup codes.
  # ---------------------------------------------------------------------------
  T("List a user's S/MIME certificates - CSV/Sheet",
    "Prints the S/MIME certificates on a user's mailbox (for signed and "
    "encrypted email).",
    "user {email} print smimes {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Upload an S/MIME certificate",
    "Uploads a user's S/MIME certificate (a .p12 / .pfx file) and makes it "
    "their default. The certificate password is masked in GAMGUI's log file.",
    "user {email} add smime file {file} [password {password}] default",
    [F("User email", "email"),
     F("Certificate file (.p12 / .pfx)", "file", filepicker=True),
     F("Certificate password (if it has one)", "password", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Make an S/MIME certificate the default",
    "Picks which of a user's S/MIME certificates Gmail uses. Get the ID from "
    "'List a user's S/MIME certificates'.",
    "user {email} update smime default id {id}",
    [F("User email", "email"), F("Certificate ID", "id"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete an S/MIME certificate (DESTRUCTIVE)",
    "Removes one S/MIME certificate from a user's mailbox.",
    "user {email} delete smime id {id}",
    [F("User email", "email"), F("Certificate ID", "id"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List a user's CSE identities - CSV/Sheet",
    "Prints a user's Gmail client-side encryption (CSE) identities.",
    "user {email} print cseidentities {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's CSE key pairs - CSV/Sheet",
    "Prints a user's Gmail client-side encryption key pairs and their state.",
    "user {email} print csekeypairs {todrive}",
    [F("User email", "email"), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a CSE key pair (advanced)",
    "Creates a Gmail CSE key pair for a user from their certificate folder "
    "and wrapped-private-key folder, and adds a CSE identity for it. See the "
    "GAM wiki 'Users - Gmail - Client Side Encryption' for the file layout.",
    "user {email} create csekeypair incertdir {certdir} inkeydir {keydir} addidentity",
    [F("User email", "email"),
     F("Certificate folder on this PC", "certdir"),
     F("Wrapped private key folder on this PC", "keydir"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Enable or disable a CSE key pair",
    "Turns a user's CSE key pair on or off.",
    "user {email} {action} csekeypair {keypairid}",
    [F("User email", "email"),
     F("Action", "action", valuemap={"Disable": "disable",
       "Enable": "enable"}),
     F("Key pair ID", "keypairid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Permanently destroy a CSE key pair (DESTRUCTIVE)",
    "OBLITERATES a CSE key pair. Mail encrypted only with it can never be "
    "decrypted again. Disable it first and make sure it is no longer needed.",
    "user {email} obliterate csekeypair {keypairid}",
    [F("User email", "email"), F("Key pair ID", "keypairid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create a CSE identity from a key pair",
    "Creates a Gmail CSE identity that uses an existing key pair.",
    "user {email} create cseidentity primarykeypairid {keypairid}",
    [F("User email", "email"), F("Key pair ID", "keypairid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a CSE identity (DESTRUCTIVE)",
    "Deletes a user's Gmail CSE identity.",
    "user {email} delete cseidentity",
    [F("User email", "email"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Show Alert Center settings",
    "Shows where Alert Center sends alert notifications (a Cloud Pub/Sub "
    "topic), if anywhere.",
    "show alertsettings",
    [     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Send alerts to a Pub/Sub topic",
    "Sends Alert Center notifications to a Google Cloud Pub/Sub topic (for a "
    "SIEM or ticketing integration). Format: projects/<project>/topics/<topic>",
    "update alertsettings {topic}",
    [F("Pub/Sub topic", "topic"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Stop sending alerts to Pub/Sub",
    "Clears the Alert Center Pub/Sub notification setting.",
    "clear alertsettings",
    [     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rate an alert (feedback)",
    "Tells Google how useful an alert was.",
    "create alertfeedback {alertid} {rating}",
    [F("Alert ID", "alertid"),
     F("Rating", "rating", valuemap={"Very useful": "very_useful",
       "Somewhat useful": "somewhat_useful", "Not useful": "not_useful"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List alert feedback - CSV/Sheet",
    "Prints the feedback given on alerts, optionally for one alert.",
    "print alertfeedback [alert {alertid}] {todrive}",
    [F("Alert ID (optional)", "alertid", False), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List email monitors on a mailbox",
    "Shows email monitors (the Email Audit API): mailboxes whose mail is "
    "being copied to another address.",
    "audit monitor list {email}",
    [F("Monitored mailbox", "email"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create an email monitor (copy a mailbox's mail) (DESTRUCTIVE)",
    "Copies a user's incoming and outgoing mail to another address until the "
    "end time (Email Audit API) - for a legal or HR investigation. Use only "
    "with proper authorization.",
    "audit monitor create {email} {dest} [end {end}]",
    [F("Mailbox to monitor", "email"), F("Send copies to", "dest"),
     F("End (optional) e.g. 2027-01-31T23:59", "end", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Delete an email monitor (DESTRUCTIVE)",
    "Stops copying a mailbox's mail to the destination address.",
    "audit monitor delete {email} {dest}",
    [F("Monitored mailbox", "email"), F("Destination address", "dest"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Delete a user's backup codes (DESTRUCTIVE)",
    "Invalidates all of a user's 2-Step Verification backup codes (e.g. after "
    "they were exposed).",
    "user {email} delete backupcodes",
    [F("User email", "email"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Access & Identity (SSO, CAA, Policies)": [
  # ---------------------------------------------------------------------------
  # Context-Aware Access levels, third-party SSO (SAML / OIDC), Cloud Identity
  # policies, and allowlisted domains.
  # ---------------------------------------------------------------------------
  T("List Context-Aware Access levels - CSV/Sheet",
    "Prints your Context-Aware Access (CAA) access levels - the rules (IP "
    "ranges, countries, device state) that apps can require.",
    "print caalevels {todrive}",
    [*_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a CAA level - allowed IP ranges",
    "Creates an access level that matches users coming from the IP ranges you "
    "list (comma separated, e.g. 203.0.113.0/24,198.51.100.0/24). Assign it "
    "to apps in the Admin console.",
    "create caalevel {name} [description {desc}] basic condition ipsubnetworks {subnets} endcondition",
    [F("Level name e.g. CORP_IPS", "name"),
     F("IP ranges (CIDR, comma separated)", "subnets"),
     F("Description (optional)", "desc", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a CAA level - allowed countries",
    "Creates an access level that matches users in the countries you list "
    "(two-letter codes, comma separated, e.g. US,CA).",
    "create caalevel {name} [description {desc}] basic condition regions {regions} endcondition",
    [F("Level name e.g. CORP_COUNTRIES", "name"),
     F("Country codes e.g. US,CA", "regions"),
     F("Description (optional)", "desc", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a CAA level - custom rule (advanced)",
    "Creates an access level from a custom CEL expression, e.g. requiring a "
    "managed browser. See Google's custom access level reference.",
    "create caalevel {name} [description {desc}] custom {cel}",
    [F("Level name", "name"), F("CEL expression", "cel"),
     F("Description (optional)", "desc", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change a CAA level's rule",
    "Replaces an access level's rule. Put the new rule in the box, e.g.  basic "
    "condition regions US,CA,MX endcondition  or  custom \"<CEL expression>\"",
    "update caalevel {name}",
    [F("Level name", "name"),
     F("New rule (required, see example)", "rule", rawappend=True)]),
  T("Delete a CAA level (DESTRUCTIVE)",
    "Deletes an access level. Apps that required it stop checking it.",
    "delete caalevel {name}",
    [F("Level name", "name"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List inbound SSO profiles - CSV/Sheet",
    "Prints your third-party identity-provider (SAML / OIDC) SSO profiles - "
    "e.g. Okta, Entra ID (Azure AD), ClassLink.",
    "print inboundssoprofiles {todrive}",
    [*_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("SSO profile info",
    "Shows one SSO profile's settings (entity ID, sign-in / sign-out URLs).",
    "info inboundssoprofile {profile}",
    [F("Profile display name or ID", "profile"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a SAML SSO profile",
    "Creates a SAML SSO profile for a third-party identity provider. Get the "
    "entity ID and URLs from your IdP. Then add its certificate ('Add an SSO "
    "signing certificate') and assign it ('Turn on SSO for an OU / group').",
    "create inboundssoprofile saml name {name} entityid {entityid} loginurl {loginurl} [logouturl {logouturl}] [changepasswordurl {cpurl}]",
    [F("Profile name e.g. Okta", "name"), F("IdP entity ID", "entityid"),
     F("Sign-in page URL", "loginurl"),
     F("Sign-out page URL (optional)", "logouturl", False),
     F("Change-password URL (optional)", "cpurl", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update an SSO profile",
    "Changes an SSO profile. Put the changes in the box, e.g.  loginurl "
    "https://idp.example.com/sso  entityid https://idp.example.com",
    "update inboundssoprofile {profile}",
    [F("Profile display name or ID", "profile"),
     F("Changes (required, see example)", "changes", rawappend=True)]),
  T("Delete an SSO profile (DESTRUCTIVE)",
    "Deletes an SSO profile. Make sure no OU or group still uses it, or those "
    "users could lose their way to sign in.",
    "delete inboundssoprofile {profile}",
    [F("Profile display name or ID", "profile"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List SSO signing certificates",
    "Shows the identity-provider signing certificates on your SSO profiles "
    "(check expiration dates before they break sign-in).",
    "show inboundssocredentials [profile {profile}]",
    [F("Profile (optional, blank = all)", "profile", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add an SSO signing certificate",
    "Uploads your identity provider's signing certificate (a PEM file) to an "
    "SSO profile - e.g. when the IdP rotates its certificate.",
    "create inboundssocredential profile {profile} pemfile {file}",
    [F("Profile display name or ID", "profile"),
     F("Certificate file (.pem)", "file", filepicker=True),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete an SSO signing certificate (DESTRUCTIVE)",
    "Removes a signing certificate from an SSO profile. Use the full name "
    "from 'List SSO signing certificates' (inboundSamlSsoProfiles/.../"
    "idpCredentials/...).",
    "delete inboundssocredential {credential}",
    [F("Certificate name", "credential"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List SSO assignments - CSV/Sheet",
    "Prints which OUs and groups use which SSO profile (or have SSO off).",
    "print inboundssoassignments {todrive}",
    [*_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Turn on SSO (or off) for an OU",
    "Sets how users in an OU sign in: through a SAML SSO profile, or with "
    "Google (SSO off). Test with a small OU first.",
    "create inboundssoassignment ou {ou} mode {mode} [profile {profile}]",
    [F("OU path", "ou"),
     F("Sign-in mode", "mode", valuemap={
       "SAML SSO with a profile": "saml_sso",
       "SSO off (Google sign-in)": "sso_off",
       "Use the domain-wide SAML setting": "domain_wide_saml_if_enabled"}),
     F("SSO profile (only for 'SAML SSO with a profile')", "profile", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Turn on SSO (or off) for a group",
    "Sets how members of a group sign in. The rank decides which group wins "
    "when a user is in more than one (1 = highest).",
    "create inboundssoassignment group {group} rank {rank} mode {mode} [profile {profile}]",
    [F("Group email", "group"), F("Rank (1 = highest priority)", "rank",
       default="1"),
     F("Sign-in mode", "mode", valuemap={
       "SAML SSO with a profile": "saml_sso",
       "SSO off (Google sign-in)": "sso_off",
       "Use the domain-wide SAML setting": "domain_wide_saml_if_enabled"}),
     F("SSO profile (only for 'SAML SSO with a profile')", "profile", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove an SSO assignment (DESTRUCTIVE)",
    "Removes an OU's or group's SSO assignment so it inherits again. Examples: "
    " orgunit:/Students  or  group:staff@example.com",
    "delete inboundssoassignment {selector}",
    [F("Assignment e.g. orgunit:/Students", "selector"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List Cloud Identity policies - CSV/Sheet",
    "Prints the security and data-protection policies Google exposes through "
    "the Cloud Identity Policy API (DLP rules and many Admin console "
    "settings), with the OU or group each applies to. Optional filter.",
    "print policies [filter {filter}] {todrive}",
    [F("Filter (optional)", "filter", False), *_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Cloud Identity policy info",
    "Shows one policy in full. Use its name from 'List Cloud Identity "
    "policies' (policies/...). Tip: add  formatjson  in the advanced box and "
    "save the output as a template for 'Create or update a policy from JSON'.",
    "info policies {name}",
    [F("Policy name e.g. policies/abc123", "name"),
     F("Extra arguments (advanced, e.g. formatjson)", "extra", False,
       rawappend=True)]),
  T("Create or update a Cloud Identity policy from JSON",
    "Creates a new policy, or updates an existing one, from a JSON file "
    "(easiest: export an existing policy with 'Cloud Identity policy info' + "
    "formatjson, edit it, then load it here). Optionally aim it at an OU or a "
    "group.",
    "{action} policy json file {file} [{targettype} {target}]",
    [F("Action", "action", valuemap={"Update an existing policy": "update",
       "Create a new policy": "create"}),
     F("JSON file", "file", filepicker=True),
     F("Apply to (optional)", "targettype", False, valuemap={"": "",
       "An OU": "ou", "A group": "group"}),
     F("OU path or group email (optional)", "target", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a Cloud Identity policy (DESTRUCTIVE)",
    "Deletes a policy so the OU or group inherits again.",
    "delete policies {name}",
    [F("Policy name e.g. policies/abc123", "name"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List allowlisted domains - CSV/Sheet",
    "Prints the domains on your Cloud Identity allowlist.",
    "print allowlisteddomains {todrive}",
    [*_out(),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add allowlisted domains",
    "Adds one or more domains (comma separated) to the allowlist.",
    "create allowlisteddomains {domains}",
    [F("Domain(s), comma separated", "domains"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove an allowlisted domain (DESTRUCTIVE)",
    "Removes a domain from the allowlist. Use its ID from 'List allowlisted "
    "domains'.",
    "delete allowlisteddomains {domainid}",
    [F("Allowlisted domain ID", "domainid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
 ],
 "Email Cleanup": [
  # Every task here can be SCOPED (all mailboxes / specific domain(s) / an OU
  # and its sub-OUs / a group) via the Search-scope selector, and sped up with
  # the parallel-threads box. Scoping to fewer mailboxes is the biggest
  # speedup; more threads runs the remaining mailboxes more concurrently
  # (higher = faster but watch for API rate limits; blank uses gam.cfg's
  # value). The {mailscope:...} token builds the correct GAM user selector.
  T("Search mailboxes (preview)",
    "Searches mailboxes for matching messages and lists "
    "from/to/subject/message-id/date. Read-only. Default scope is ALL "
    "mailboxes; narrow it with the Search scope box (a domain, an OU + its "
    "sub-OUs, or a group) to run faster. Query uses Gmail search syntax, "
    "e.g.: from:bad@evil.com subject:\"Gift Card\".",
    "[config num_threads {threads}] {mailscope:scopetype:scopeval} print messages query {query} headers from,to,subject,message-id,date",
    [F("Gmail query e.g. from:x subject:\"y\"", "query"),
     F("Search scope", "scopetype", valuemap={"All mailboxes": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Speed: parallel threads (blank = config default)", "threads", False)]),
  T("Trash from mailboxes (DESTRUCTIVE)",
    "Moves matching messages to Trash (recoverable for ~30 days). Run the "
    "search preview first and check the hit count. Default scope is ALL "
    "mailboxes - narrow it to run faster. The max limit stops a bad query "
    "from running away.",
    "[config num_threads {threads}] {mailscope:scopetype:scopeval} trash messages query {query} max_to_trash {max} doit",
    [F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"),
     F("Max per mailbox", "max", default="5000"),
     F("Search scope", "scopetype", valuemap={"All mailboxes": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Speed: parallel threads (blank = config default)", "threads", False)],
    destructive=True),
  T("Delete from mailboxes (DESTRUCTIVE)",
    "Permanently deletes matching messages - no trash, no recovery. For "
    "phishing incident response. ALWAYS run the search preview first. Default "
    "scope is ALL mailboxes - narrow it to run faster. Prefer an exact "
    "Message-ID query when you have one: rfc822msgid:<the-message-id> - far "
    "more precise than from+subject matching.",
    "[config num_threads {threads}] {mailscope:scopetype:scopeval} delete messages query {query} max_to_delete {max} doit",
    [F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"),
     F("Max per mailbox", "max", default="5000"),
     F("Search scope", "scopetype", valuemap={"All mailboxes": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Speed: parallel threads (blank = config default)", "threads", False)],
    destructive=True),
  T("Delete from ONE mailbox (DESTRUCTIVE)",
    "Permanently deletes matching messages from a single mailbox.",
    "user {email} delete messages query {query} max_to_delete {max} doit",
    [F("Mailbox", "email"), F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"),
     F("Max to delete", "max", default="100")], destructive=True),
  T("Find & PERMANENTLY delete a message from ONLY the mailboxes that have it",
    "Two-phase and fast: searches mailboxes for a message, shows how many "
    "matched, then - after you type DELETE to confirm - PERMANENTLY DELETES it "
    "(NOT recoverable, it does not go to Trash) from ONLY the mailboxes that "
    "actually had it (every other mailbox is skipped, so it is far quicker than "
    "scanning the whole domain again). Built for malicious/phishing mail. This "
    "is the lightweight targeted version of the full incident workflow: no Drive "
    "sweep, no audit reports. Tip: an exact rfc822msgid:<the-message-id> query "
    "is the most precise. Evidence is saved to a timestamped folder under Logs.",
    "",
    [F('Gmail query e.g. from:bad@evil.com subject:"Gift Card"', "query"),
     F("Search scope", "scopetype", valuemap={"All mailboxes": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Speed: parallel threads (blank = config default)", "threads", False),
     F("Max per mailbox (seatbelt)", "max", default="5000")],
    destructive=True, workflow="targetedcleanup"),
  T("Full incident-response workflow",
    "Runs the complete phishing cleanup in four phases: 1) searches mailboxes "
    "for messages matching From + Subject and saves the evidence CSV, 2) shows "
    "you the hit count and requires typing DELETE to continue, 3) deletes "
    "matches - by exact Message-ID when available (precise), otherwise by the "
    "From+Subject query, 4) pulls Gmail and Drive audit reports for the "
    "lookback window. Default scope is ALL mailboxes; narrow it (a domain, an "
    "OU + sub-OUs, or a group) to run faster. All evidence lands in a "
    "timestamped Incident folder under Logs. Canceling at the DELETE prompt "
    "keeps the evidence and deletes nothing.",
    "",
    [F("From address e.g. attacker@evil.com", "from"),
     F("Subject text e.g. Compensation Review & Bonus (no quotes needed)",
       "subject"),
     F("Also sweep Drive for the attachment", "drivesweep",
       valuemap={"No - skip Drive (default)": "off",
                 "Yes - auto-detect the attachment name from the emails": "auto",
                 "Yes - use the filename I enter below": "manual"}),
     F("Attachment filename(s) to remove from Drive (comma separated; for the "
       "'use the filename' option)", "attachname", False),
     F("Search scope", "scopetype", valuemap={"All mailboxes": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Speed: parallel threads (blank = config default)", "threads", False),
     F("Audit lookback days", "days", default="30"),
     F("Max delete per mailbox (seatbelt)", "max", default="5000")],
    destructive=True, workflow=True),
 ],
 "Bulk / Batch": [
  # Run ANY gam command once per row of a CSV or a Google Sheet. Put a cell
  # value into the command with ~ColumnName (a whole argument) or ~~ColumnName~~
  # (inside a word). GAM runs the rows in parallel. This gives bulk to every
  # command in the tool, not just the ones with a built-in bulk helper.
  T("Bulk: run a command for each CSV row",
    "Pick a CSV file, then type the gam command to run for each row, using "
    "~ColumnName where a cell value goes. Example (CSV has columns email,cal): "
    "  user ~email add calendars ~cal selected true  - runs once per row. "
    "ALWAYS test on a small CSV first.",
    "csv {file} gam",
    [F("CSV file", "file", filepicker=True),
     F("Command per row - required, use ~Column for cells", "extra", False, rawappend=True)]),
  T("Bulk: run a command for each Google Sheet row",
    "Same as the CSV version but reads a Google Sheet. Give an admin who can "
    "open the sheet, the sheet's file ID (the long part of its URL), and the "
    "tab name, then the command using ~ColumnName.",
    "csv gsheet {owner} id:{fileid} {tab} gam",
    [F("Admin who can open the sheet", "owner"),
     F("Sheet file ID (from the URL)", "fileid"),
     F("Tab name e.g. Sheet1", "tab"),
     F("Command per row - required, use ~Column for cells", "extra", False, rawappend=True)]),
 ],
 "Diagnostics": [
  T("GAM version", "Version, config file, and customer info.", "version",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("GAM version (extended)",
    "Version plus the active config file, section (domain), and paths - "
    "handy for confirming which tenant you are pointed at.",
    "version extended",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Domain info", "Read-only summary of the Workspace domain.", "info domain",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("OAuth info", "Which admin GAM runs as and the granted scopes.", "oauth info",
    [F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Check service account",
    "Verifies the service account can access the scopes needed to act as "
    "users (domain-wide delegation health check).",
    "user {email} check serviceaccount",
    [F("Any user email to test as", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
}

# =============================================================================
# SECTION: GAM documentation links (the "GAM docs" button)
# =============================================================================
# Every link points at a page of the GAM7 wiki. The page names below were
# checked against a clone of the wiki (tests/check_doc_links.py re-checks them)
# so the button never opens a missing page.
WIKI_BASE = "https://github.com/GAM-team/GAM/wiki/"

# The page for each category - used when no more specific hint matches.
CATEGORY_DOCS = {
    "OAuth Setup": "Authorization",
    "Common Tasks": "Users",
    "Users": "Users",
    "Groups": "Groups",
    "Aliases": "Aliases",
    "Org Units": "Organizational-Units",
    "Domains & Domain Aliases": "Domains",
    "Chromebooks": "ChromeOS-Devices",
    "Chrome Browsers & Policies": "Chrome-Policies",
    "Gmail": "Users-Gmail-Settings",
    "Calendars": "Users-Calendars",
    "Drive": "Users-Drive-Files-Manage",
    "Shared Drives": "Shared-Drives",
    "Classroom": "Classroom-Courses",
    "Google Meet": "Users-Meet",
    "Google Forms": "Users-Forms",
    "Google Chat": "Users-Chat",
    "Google Tasks & Keep": "Users-Tasks",
    "Google Sheets & Docs": "Users-Spreadsheets",
    "Licenses": "Licenses",
    "Vault": "Vault-Takeout",
    "Mobile Devices": "Mobile-Devices",
    "Cloud Identity Devices": "Cloud-Identity-Devices",
    "Custom Schemas": "Schemas",
    "Contacts": "Users-People-Contacts-Profiles",
    "Admin Roles & Privileges": "Administrators",
    "Data Transfers": "Google-Data-Transfers",
    "Chrome Printers": "Chrome-Printers",
    "Buildings, Features & Rooms": "Resources",
    "Reseller / Channel": "Reseller",
    "Marketing & Analytics": "Users-Analytics-Admin",
    "Customer / Settings": "Customer",
    "Reports": "Reports",
    "Security": "Users-Deprovision",
    "Access & Identity (SSO, CAA, Policies)": "Inbound-SSO",
    "Email Cleanup": "Users-Gmail-Messages-Threads",
    "Bulk / Batch": "Bulk-Processing",
    "Diagnostics": "Version-and-Help",
}

# More specific pages, chosen from the GAM object named in a task's command
# template. Checked IN ORDER; the first regular expression that matches the
# template wins. Word boundaries (\b) keep e.g. 'contactdelegate' from
# matching the Gmail 'delegate' rule.
DOC_HINTS = [
    (r"\btasks?\b|\btasklists?\b", "Users-Tasks"),
    (r"\b(create|delete|info|print|show) notes?\b|noteacl|noteattachments",
     "Users-Keep-Notes"),
    (r"contactdelegates?", "Users-Contacts-Delegates"),
    (r"\b(create|delete|info|print|show) filters?\b", "Users-Gmail-Filters"),
    (r"\bdelegates?\b", "Users-Gmail-Delegates"),
    (r"\bsendas\b|\bsignature\b|\bvacation\b",
     "Users-Gmail-Send-As-Signature-Vacation"),
    (r"\bsmimes?\b", "Users-Gmail-S-MIME"),
    (r"csekeypairs?|cseidentit", "Users-Gmail-CSE"),
    (r"\bsendemail\b", "Send-Email"),
    (r"\b(messages?|threads?)\b", "Users-Gmail-Messages-Threads"),
    (r"\blabels?\b|\blabelsettings\b", "Users-Gmail-Labels"),
    (r"\bforward(ingaddress(es)?)?\b", "Users-Gmail-Forwarding"),
    (r"classificationlabel|filedrivelabels", "Users-Classification-Labels"),
    (r"filerevisions", "Users-Drive-Revisions"),
    (r"drivefileshortcut", "Users-Drive-Shortcuts"),
    (r"\bfilelist\b|\bfileinfo\b|fileparenttree", "Users-Drive-Files-Display"),
    (r"\borphans\b", "Users-Drive-Orphans"),
    # Only the per-user form; the admin forms belong to Shared Drives.
    (r"^user .*\bdrivefileacls?\b", "Users-Drive-Permissions"),
    (r"course-studentgroup", "Classroom-StudentGroups"),
    (r"\bguardians?\b", "Classroom-Guardians"),
    (r"\bphoto\b", "Users-Profile-Photo"),
    (r"userinvitation|isinvitable", "Unmanaged-Accounts"),
    (r"\bprofile (share|unshare)\b|\bshow profile\b", "Users-Profile-Sharing"),
    (r"\bdeprovision\b", "Users-Deprovision"),
    (r"\bbackupcodes\b", "Users-Backup-Verification-Codes"),
    (r"\basps\b", "Users-Application-Specific-Passwords"),
    (r"\bsignout\b|\bturnoff2sv\b", "Users-Signout-Turnoff2SV"),
    (r"^report\b", "Reports"),
    (r"\bevents?\b|\boutofoffice\b|\bworkinglocation\b|\bfocustime\b",
     "Users-Calendars-Events"),
    (r"\bacls\b|\bcalendaracls\b", "Calendars-Access"),
    (r"\balerts?\b|\balertsettings\b|\balertfeedback\b", "Alert-Center"),
    (r"\bcaalevels?\b", "Context-Aware-Access-Levels"),
    (r"\bcigroups?\b|cigroup-members", "Cloud-Identity-Groups"),
    (r"\bpolicies\b|\bpolicy\b", "Cloud-Identity-Policies"),
    (r"\ballowlisteddomains?\b", "Cloud-Identity-Allowlisted-Domains"),
    (r"\bverify\b", "Domains-Verification"),
    (r"\bbrowsers?\b|\bbrowsertokens?\b", "Chrome-Browser-Cloud-Management"),
    (r"chromeprofile", "Chrome-Profile-Management"),
    (r"chromeapp", "Chrome-Installed-Apps"),
    (r"chromehistory", "Chrome-Version-History"),
    (r"\bsheet(range)?s?\b", "Users-Spreadsheets"),
    (r"\baudit monitor\b", "Email-Audit-Monitor"),
    (r"datastudio", "Users-Data-Studio"),
    (r"tagmanager", "Users-Tag-Manager"),
    (r"youtube", "Users-YouTube"),
    (r"webmastersites|webresources", "Users-Web-Resources-and-Sites"),
    (r"businessprofile", "Users-Business-Account-Management"),
    (r"channel(customer|offer|product|sku)", "Cloud-Channel"),
    (r"storagebucket|storagefile", "Cloud-Storage"),
    (r"\bsakeys?\b", "Authorization"),
]


def task_doc_url(category, task):
    # Returns the GAM wiki URL for a task: the task's own "doc" key if it has
    # one, else the first DOC_HINTS match on its command template, else its
    # category's page, else the wiki home page.
    if task and task.get("doc"):
        return WIKI_BASE + task["doc"]
    template = (task or {}).get("template", "") or ""
    # Blank out {placeholders} and [optional segments] first, so a field
    # named {label} or an optional '[filter {filter}]' cannot be mistaken for
    # the GAM object the task actually works on.
    template = re.sub(r"\{[^}]*\}", " ", template)
    template = re.sub(r"\[[^\]]*\]", " ", template)
    for pattern, page in DOC_HINTS:
        if re.search(pattern, template):
            return WIKI_BASE + page
    page = CATEGORY_DOCS.get(category)
    return WIKI_BASE + page if page else WIKI_BASE + "Home"

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
    redirect_prefix = []                          # 'redirect csv <path>' if CSV
    redirect_display = []                          # same, quoted, for the preview

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
        # Special token {todrive}: the output destination. The "todrive" field
        # value is "" (Screen), "todrive" (Google Sheet) or "csv" (local file).
        # Google Sheet appends the 'todrive' keyword here; CSV instead turns the
        # "csvout" path into a LEADING 'redirect csv <path>' (a gam directive
        # that must come before the command), collected now and prepended below.
        if token == "{todrive}":
            dest = values.get("todrive", "").strip()
            if dest == "todrive":
                argv.append("todrive")
                display_parts.append("todrive")
            elif dest == "csv":
                path = values.get("csvout", "").strip()
                if not path:
                    return "", [], ("Choose a CSV file to write, or set 'Save "
                                    "results to' back to Screen or Google Sheet.")
                redirect_prefix[:] = ["redirect", "csv", path]
                redirect_display[:] = ["redirect", "csv", quote_if_needed(path)]
            # dest "" (Screen): nothing to add
            continue
        # Special token {shareddrive:KEY}: expand into the correct Shared Drive
        # selector so ONE field can accept either a name or an ID. Shared Drive
        # IDs start with "0A" and contain no spaces, so the value is treated as
        # an ID (keyword "shareddriveid") when it matches that shape, otherwise
        # as a name (keyword "shareddrive"). This produces TWO arguments
        # (keyword + value), which a single {placeholder} could not.
        selector = re.fullmatch(r"\{shareddrive:(\w+)\}", token)
        if selector:
            value = values.get(selector.group(1), "").strip()
            if not value:
                return "", [], "Missing required value: " + selector.group(1)
            keyword = ("shareddriveid"
                       if re.fullmatch(r"0A[A-Za-z0-9_\-]{6,}", value)
                       else "shareddrive")
            argv.append(keyword)
            argv.append(value)
            display_parts.append(keyword)
            display_parts.append(quote_if_needed(value))
            continue
        # Special token {license:KEY}: translate the field value (a friendly
        # license name, a SKU id, or a GAM alias) into the SKU id gam expects.
        lic = re.fullmatch(r"\{license:(\w+)\}", token)
        if lic:
            raw = values.get(lic.group(1), "").strip()
            if not raw:
                return "", [], "Missing required value: " + lic.group(1)
            sku = translate_license(raw)
            if not sku:
                return "", [], ("Unknown license '" + raw
                                + "' - use a license name or a SKU id")
            argv.append(sku)
            display_parts.append(quote_if_needed(sku))
            continue
        # Special token {mailscope:TYPEKEY:VALKEY}: expands into the GAM user
        # selector that scopes a mailbox operation. TYPEKEY holds the gam
        # keyword ("all", "domains", "ou_and_children", or "group") and VALKEY
        # holds the domain(s)/OU/group. "all" becomes the two tokens
        # "all users"; the others become "<keyword> <value>" (two tokens).
        # This exists because a single {placeholder} cannot emit two argv
        # elements, and a scope value with spaces must stay one element.
        scope = re.fullmatch(r"\{mailscope:(\w+):(\w+)\}", token)
        if scope:
            stype = values.get(scope.group(1), "").strip() or "all"
            sval = values.get(scope.group(2), "").strip()
            if stype == "all":
                argv.extend(["all", "users"])
                display_parts.extend(["all", "users"])
            else:
                if not sval:
                    return "", [], ("This scope needs a value (domain, OU, "
                                    "or group) in the scope-value box")
                argv.append(stype)
                argv.append(sval)
                display_parts.append(stype)
                display_parts.append(quote_if_needed(sval))
            continue
        # Special token {crosscope:TYPEKEY:VALKEY}: expands into the GAM
        # <CrOSTypeEntity> selector that picks WHICH Chromebooks a bulk action
        # targets. TYPEKEY holds a short scope key and VALKEY holds the value
        # (serial list / OU path / query). The keys map to gam keywords:
        #   all         -> "all cros"                    (every managed device)
        #   sn          -> "cros_sn <serials>"           (comma list of serials)
        #   ou          -> "cros_ou <ou>"                (devices directly in OU)
        #   ou_children -> "cros_ou_and_children <ou>"   (OU and all sub-OUs)
        #   query       -> "crosquery <query>"           (a CrOS search query)
        # Like {mailscope}, this exists because one {placeholder} cannot emit
        # the two argv elements (keyword + value) a selector needs.
        cscope = re.fullmatch(r"\{crosscope:(\w+):(\w+)\}", token)
        if cscope:
            ctype = values.get(cscope.group(1), "").strip() or "all"
            cval = values.get(cscope.group(2), "").strip()
            cros_keyword = {"all": "all", "sn": "cros_sn", "ou": "cros_ou",
                            "ou_children": "cros_ou_and_children",
                            "query": "crosquery"}.get(ctype)
            if cros_keyword is None:
                return "", [], ("Unknown device scope '" + ctype + "'")
            if ctype == "all":
                argv.extend(["all", "cros"])
                display_parts.extend(["all", "cros"])
            else:
                if not cval:
                    return "", [], ("This device scope needs a value "
                                    "(serial numbers, an OU path, or a query) "
                                    "in the scope-value box")
                argv.append(cros_keyword)
                argv.append(cval)
                display_parts.append(cros_keyword)
                display_parts.append(quote_if_needed(cval))
            continue
        # Special token {userscope:TYPEKEY:VALKEY}: expands into the GAM
        # <UserTypeEntity> that picks WHICH users a bulk action targets. Mirrors
        # {crosscope} but for people. Keys map to gam selectors:
        #   all         -> "all users"                  (every account)
        #   ou          -> "ou <ou>"                    (users directly in OU)
        #   ou_children -> "ou_and_children <ou>"       (OU and all sub-OUs)
        #   group       -> "group <email>"              (a group's members)
        #   query       -> "query <query>"              (a user search query)
        #   csv         -> "csvfile <file>:<column>"    (a CSV column of emails)
        #   user        -> "user <email>"               (one person)
        uscope = re.fullmatch(r"\{userscope:(\w+):(\w+)\}", token)
        if uscope:
            utype = values.get(uscope.group(1), "").strip() or "all"
            uval = values.get(uscope.group(2), "").strip()
            user_keyword = {"all": "all", "ou": "ou",
                            "ou_children": "ou_and_children", "group": "group",
                            "query": "query", "csv": "csvfile",
                            "user": "user"}.get(utype)
            if user_keyword is None:
                return "", [], ("Unknown user scope '" + utype + "'")
            if utype == "all":
                argv.extend(["all", "users"])
                display_parts.extend(["all", "users"])
            else:
                if not uval:
                    return "", [], ("This user scope needs a value (an OU path, "
                                    "a group, a query, or a CSV file:column) in "
                                    "the scope-value box")
                argv.append(user_keyword)
                argv.append(uval)
                display_parts.append(user_keyword)
                display_parts.append(quote_if_needed(uval))
            continue
        filled = re.sub(r"{(\w+)(?:\|([^}]*))?}", fill, token)
        if problem[0]:
            return "", [], problem[0]
        argv.append(filled)                       # raw - no escaping needed
        display_parts.append(quote_if_needed(filled))

    # Raw-append fields (advanced box): split the user's free text with the
    # same quote-aware splitter used for edited previews and append each token
    # verbatim. Lets any uncommon gam flag through without a dedicated widget.
    for field in task["fields"]:
        if field.get("rawappend"):
            extra = values.get(field["key"], "").strip()
            # A REQUIRED free-text field must not be silently dropped: some
            # commands change meaning when their selector is missing (e.g.
            # 'purge events <cal>' with no event selector purges EVERY event,
            # and a sync with no source would empty the target). Refuse to
            # build the command instead.
            if field.get("required") and not extra:
                return "", [], "Missing required value: " + field["key"]
            if extra:
                for tok in win_split(extra):
                    argv.append(tok)
                    display_parts.append(quote_if_needed(tok))

    # A CSV redirect is a leading gam directive, so it goes at the very front
    # of the command (before select/the verb), which is where gam expects it.
    argv = redirect_prefix + argv
    display_parts = redirect_display + display_parts
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
# SECTION: License SKU reference (for the bulk-license tools)
#   Maps Google's friendly license names to their skuId, so a CSV/Sheet
#   "License" column can hold a NAME, a numeric SKU id, or a GAM alias.
#   Source: Google's licensing "Products & SKUs" documentation.
# =============================================================================

_LICENSE_SKUS = {
    "Google Workspace Business Starter": "1010020027",
    "Google Workspace Business Standard": "1010020028",
    "Google Workspace Business Plus": "1010020025",
    "Google Workspace Enterprise Essentials": "1010060003",
    "Google Workspace Enterprise Starter": "1010020029",
    "Google Workspace Enterprise Standard": "1010020026",
    "Google Workspace Enterprise Plus": "1010020020",
    "Google Workspace Essentials": "1010060001",
    "Google Workspace Enterprise Essentials Plus": "1010060005",
    "Google Workspace Frontline Starter": "1010020030",
    "Google Workspace Frontline Standard": "1010020031",
    "Google Workspace Frontline Plus": "1010020034",
    "Google Workspace for Education Fundamentals": "1010070001",
    "Google Workspace for Education Gmail Only": "1010070004",
    "Google Workspace for Education Standard": "1010310005",
    "Google Workspace for Education Standard (Staff)": "1010310006",
    "Google Workspace for Education Standard (Extra Student)": "1010310007",
    "Google Workspace for Education Plus": "1010310008",
    "Google Workspace for Education Plus (Staff)": "1010310009",
    "Google Workspace for Education Plus (Extra Student)": "1010310010",
    "Google Workspace for Education: Teaching and Learning Upgrade": "1010370001",
    "Cloud Identity": "1010010001",
    "Cloud Identity Premium": "1010050001",
    "Google Voice Starter": "1010330003",
    "Google Voice Standard": "1010330004",
    "Google Voice Premier": "1010330002",
    "Google Meet Global Dialing": "1010360001",
    "Google Workspace Additional Storage 100 GB": "1010430002",
    "Google Workspace Additional Storage 1TB": "1010430003",
    "Google Workspace Additional Storage 10TB": "1010430001",
    "Chrome Enterprise Premium": "1010400001",
    "Cloud Search Platform": "1010350001",
    "Google Vault": "Google-Vault",
    "Google Vault Former Employee": "Google-Vault-Former-Employee",
}

# Normalized lookup: lowercase names, plus prefix-stripped forms so that a
# short "Education Standard" also matches "Google Workspace for Education
# Standard".
_LICENSE_LOOKUP = {}
for _lname, _lsku in _LICENSE_SKUS.items():
    _LICENSE_LOOKUP[_lname.lower()] = _lsku
    for _lpref in ("google workspace for ", "google workspace "):
        if _lname.lower().startswith(_lpref):
            _LICENSE_LOOKUP[_lname.lower()[len(_lpref):]] = _lsku


def translate_license(value):
    # Returns a SKU id for a friendly NAME, passes through a numeric SKU id or
    # a GAM alias (e.g. Google-Apps-Unlimited), or None if unrecognized. GAM
    # does the final validation when the command runs.
    v = (value or "").strip()
    if not v:
        return None
    sku = _LICENSE_LOOKUP.get(v.lower())
    if sku:
        return sku
    if re.fullmatch(r"\d{6,}", v):                       # numeric SKU id
        return v
    if "-" in v and re.fullmatch(r"[A-Za-z0-9-]+", v):   # GAM alias
        return v
    return None
