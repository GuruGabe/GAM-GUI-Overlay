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
    "print users fields primaryemail,firstname,lastname,orgunitpath,lastlogintime,suspended [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print users fields primaryemail,firstname,lastname,orgunitpath,lastlogintime,suspended [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export users - advanced (query / fields / OU)",
    "Prints users you choose. Query examples: orgUnitPath=/Students  |  "
    "isSuspended=True  |  email:jsmith*. Fields is a comma list, e.g. "
    "primaryemail,name,orgunitpath,lastlogintime. Leave fields blank for "
    "the defaults.",
    "print users [query {query}] [fields {fields}] [{todrive}]",
    [F("Query (optional)", "query", False),
     F("Fields, comma separated (optional)", "fields", False),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Count users by OU",
    "Reports how many users are in each organizational unit.",
    "print usercountsbyorgunit [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete user (DESTRUCTIVE)",
    "Deletes the account. Recoverable with Undelete for about 20 days, "
    "after that everything is gone. Transfer Drive/Calendar data first!",
    "delete user {email}",
    [F("User email", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Undelete user",
    "Restores a user deleted within the last ~20 days.",
    "undelete user {email} [ou {ou}]",
    [F("User email", "email"), F("Restore to OU (optional)", "ou", False),
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
  T("Remove ALL members (DESTRUCTIVE)",
    "Empties the group: removes every member, manager, and owner. The group "
    "itself remains.",
    "update group {group} clear member manager owner",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("List members",
    "Shows the full roster of a group.",
    "print group-members group {group}",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Group info",
    "Shows a group's settings, aliases, and member counts.",
    "info group {group}",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export all groups",
    "Prints every group in the domain.",
    "print groups [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export all groups + members",
    "Prints every group WITH its members, managers, and owners.",
    "print groups roles members,managers,owners [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
  T("Alias info",
    "Shows what an alias points to.",
    "info alias {alias}",
    [F("Alias address", "alias"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export all aliases",
    "Prints every user and group alias in the domain.",
    "print aliases [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print ous [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
 ],
 "Domains & Domain Aliases": [
  T("Domain info",
    "Shows details for a domain. Leave blank to show the primary domain.",
    "info domain [{domain}]",
    [F("Domain name (optional)", "domain", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List domains",
    "Prints all domains in the account.",
    "print domains [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print domainaliases [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print cros fields serialnumber,ou,status,lastsync,annotateduser,annotatedassetid [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Find devices (query)",
    "Prints devices matching a query, e.g.  sync:..  |  status:provisioned  "
    "|  asset_id:12345  |  user:jsmith. See the CrOS query help.",
    "print cros query {query} [{todrive}]",
    [F("Query e.g. status:deprovisioned", "query"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Device activity report",
    "Prints recent-user and network activity for the fleet.",
    "print crosactivity [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Who used this Chromebook last?",
    "Shows recent users and networks for a device.",
    "cros_sn {serial} info recentusers lastknownnetwork",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Gmail": [
  T("Show delegates", "Lists who can open this mailbox as a delegate.",
    "user {email} show delegates",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export delegates (whole domain)",
    "Prints every mailbox's delegates across the domain to CSV/Sheet.",
    "all users print delegates [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "all users print forwardingaddresses [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
  T("Set mailbox language",
    "Sets the Gmail display language, e.g. en, es, fr.",
    "user {email} language {lang}",
    [F("Mailbox", "email"), F("Language code e.g. en, es", "lang"),
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
    "calendars {cal} print acls [{todrive}]",
    [F("Calendar ID", "cal"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "Shows or hides MANY calendars in one user's list at once, from a CSV of "
    "calendar IDs - the reliable way to declutter. Example: you were added as "
    "owner to hundreds of Classroom calendars and Google won't let you drop "
    "your own ownership; set Hide = Yes and Show = No to get them all out of "
    "your list (reversible any time). This changes ONLY how the calendars look "
    "in THAT user's list - it does not touch ownership or anyone else. Runs "
    "fine under the default account (it acts as the user you name). The CSV "
    "needs a column of calendar IDs (the 'id' column from 'List a user's "
    "calendars').",
    "user {email} update calendars csvfile {file}:{idcol} [selected {selected}] [hidden {hidden}] [color {color}]",
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
  T("Calendar info (in a user's list)",
    "Shows the settings of one calendar as it appears in a user's list.",
    "user {email} info calendars {cal}",
    [F("User email", "email"), F("Calendar ID", "cal"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's calendars (CSV/Sheet)",
    "Prints the calendars in a user's calendar list.",
    "user {email} print calendars [{todrive}]",
    [F("User email", "email"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "user {email} print filecounts [{todrive}]",
    [F("User email", "email"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "user {email} print filerevisions {fileid} [{todrive}]",
    [F("File owner", "email"), F("File ID", "fileid"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "user {email} print filetree [{todrive}]",
    [F("User email", "email"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Shared Drives": [
  T("List Shared Drives",
    "Prints all Shared Drives visible to the admin.",
    "print shareddrives fields id,name [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List Shared Drive memberships (ACLs)",
    "Prints who has access to which Shared Drives.",
    "print shareddriveacls [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print drivefileacls {shareddrive:driveid} [{todrive}]",
    [F("Shared Drive name OR ID", "driveid"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
 ],
 "Classroom": [
  T("List courses (by teacher)",
    "Prints courses; give a teacher email to see just theirs.",
    "print courses [teacher {teacher}] [{todrive}]",
    [F("Teacher email (optional)", "teacher", False),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List course participants",
    "Prints students and teachers across courses.",
    "print course-participants [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
  T("Add course alias",
    "Adds an alias (friendly ID) to a course, e.g. d:MATH101.",
    "courses {courseid} add alias {alias}",
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
    "print guardians [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
  # --- Read-only exports of course content ---
  T("List coursework/assignments (CSV/Sheet)",
    "Prints the coursework (assignments/questions) across courses.",
    "print course-works [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False, rawappend=True)]),
  T("List announcements (CSV/Sheet)",
    "Prints the stream announcements across courses.",
    "print course-announcements [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False, rawappend=True)]),
  T("List topics (CSV/Sheet)",
    "Prints the topics (unit headings) across courses.",
    "print course-topics [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False, rawappend=True)]),
  T("List student groups (CSV/Sheet)",
    "Prints Classroom student groups across courses.",
    "print course-studentgroups [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
  T("List users with a specific license",
    "Lists every user who has the given license, so you can see who is using "
    "it. Enter a license NAME (e.g. 'Education Plus') or a SKU id. Use the "
    "dropdown to send the result to a Google Sheet instead of the screen.",
    "print licenses skus {license:sku} [{todrive}]",
    [F("License name or SKU", "sku"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print matters [matterstate {state}] [{todrive}]",
    [F("State (optional)", "state", False,
       valuemap={"": "", "Open": "OPEN", "Closed": "CLOSED", "Deleted": "DELETED"}),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print holds [matters {matters}] [{todrive}]",
    [F("Matter(s) (name/ID, comma separated, optional)", "matters", False),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print vaultqueries [matters {matters}] [{todrive}]",
    [F("Matter(s) (name/ID, comma separated, optional)", "matters", False),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print vaultcounts matter {matter} corpus {corpus} [accounts {accounts}] [orgunit {ou}] [{todrive}]",
    [F("Matter (name or ID)", "matter"),
     F("Data type", "corpus", valuemap={"Gmail": "mail", "Groups": "groups"}),
     F("Account email(s), comma separated (optional)", "accounts", False),
     F("OU path instead of accounts (optional)", "ou", False),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print exports [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Mobile Devices": [
  T("List mobile devices",
    "Prints managed mobile devices (phones/tablets).",
    "print mobile [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print devices [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Device info",
    "Shows one device by its ID (from List devices).",
    "info device {deviceid}",
    [F("Device ID", "deviceid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List device users (CSV/Sheet)",
    "Prints the per-account device presences (which accounts are signed in on "
    "which devices).",
    "print deviceusers [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print schemas [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
 ],
 "Contacts": [
  T("List domain shared contacts",
    "Prints the domain's shared (external) contacts.",
    "print contacts [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print domaincontacts [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- A single user's personal contacts ---
  T("List a user's personal contacts (CSV/Sheet)",
    "Prints the contacts saved in one user's own Google Contacts.",
    "user {email} print contacts [{todrive}]",
    [F("User email", "email"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's 'Other contacts' (CSV/Sheet)",
    "Prints the auto-collected 'Other contacts' (people a user has emailed but "
    "never saved) for one user.",
    "user {email} print othercontacts [{todrive}]",
    [F("User email", "email"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- A user's contact groups (labels in Contacts) ---
  T("List a user's contact groups (CSV/Sheet)",
    "Prints the contact groups (labels) in one user's Google Contacts.",
    "user {email} print contactgroups [{todrive}]",
    [F("User email", "email"),
     F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print admins [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List admin roles",
    "Prints all built-in and custom admin roles.",
    "print adminroles [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List privileges",
    "Prints all admin privileges that roles can grant.",
    "print privileges [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print transfers [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Data transfer info",
    "Shows the status of one transfer by its ID.",
    "info transfer {transferid}",
    [F("Transfer ID", "transferid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Chrome Printers": [
  T("List printers",
    "Prints the Chrome printers registered in the domain.",
    "print printers [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print printermodels [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Buildings, Features & Rooms": [
  T("List buildings",
    "Prints the buildings defined for resource booking.",
    "print buildings [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
    "print features [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create feature",
    "Creates a room feature that resources can advertise.",
    "create feature name {name}",
    [F("Feature name", "name"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List calendar resources (rooms)",
    "Prints bookable resources such as rooms and equipment.",
    "print resources [{todrive}]",
    [F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"]),
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
