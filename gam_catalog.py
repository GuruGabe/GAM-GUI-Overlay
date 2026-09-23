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
    # all / ou / ou_children / group / query / csv. The second field holds the
    # OU path, group email, query, or a CSV file:column (blank only for ALL).
    return [
        F("Target users by", "usertype",
          valuemap={"An OU (users directly in it)": "ou",
                    "An OU and all its sub-OUs": "ou_children",
                    "A group's members": "group",
                    "A user query (e.g. orgUnitPath=/Students)": "query",
                    "A CSV column of emails (file:column)": "csv",
                    "ALL users in the domain": "all"}),
        F("Scope value - OU path / group / query / file:column "
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
    "box, e.g.  start 2025-06-01T09:00:00 end 2025-06-01T10:00:00 attendee "
    "jsmith@ex.com  (or for an all-day event: start 2025-06-01 end 2025-06-02).",
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
    "Removes selected old versions of a file. In the advanced box, name the "
    "revisions, e.g.  select id:<revisionId>  or  select allexceptnewest.",
    "user {email} delete filerevisions {fileid}",
    [F("File owner", "email"), F("File ID", "fileid"),
     F("Revision selector (see example)", "extra", False, rawappend=True)],
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
        uscope = re.fullmatch(r"\{userscope:(\w+):(\w+)\}", token)
        if uscope:
            utype = values.get(uscope.group(1), "").strip() or "all"
            uval = values.get(uscope.group(2), "").strip()
            user_keyword = {"all": "all", "ou": "ou",
                            "ou_children": "ou_and_children", "group": "group",
                            "query": "query", "csv": "csvfile"}.get(utype)
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
