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
import datetime as _dt         # Local date/time -> UTC for admin role expirations

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

def dropdown_start(field, current):
    # 2.91: the value a dropdown starts on in the desktop form. 'current' is
    # what the box would start with (the remembered value or the default).
    # Kept when it is one of the choices; else a REQUIRED box starts on its
    # first choice and an optional one stays blank. (Before 2.91 a required
    # box always started on its first choice, ignoring its default - 38
    # fields opened on the wrong choice; the browser was always right.)
    vmap = field.get("valuemap")
    choices = list(vmap.keys()) if vmap else (field.get("choices") or [])
    if current in choices:
        return current
    if field.get("required") and choices:
        return choices[0]
    return current if not choices else ""


def dropdown_choices(field):
    # 2.92: the list a dropdown offers, the SAME in the desktop app and the
    # browser. An OPTIONAL dropdown whose default is not one of its choices
    # gets a blank first entry: blank = 'leave it as it is'. Without it the
    # browser started on the first real choice ('Change a group's settings'
    # sent all 7 settings) and the desktop could not go back to blank.
    vmap = field.get("valuemap")
    choices = list(vmap.keys()) if vmap else (list(field.get("choices") or []))
    if choices and not field.get("required") and (field.get("default") or "") not in choices:
        return [""] + choices
    return choices


def F(label, key, required=True, choices=None, default="", valuemap=None,
      filepicker=False, rawappend=False, picker=None, remember=""):
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
    # picker="user" / "group" (2.83): this box gets the Pick... list even
    # though no command template says what it holds (workflow boxes).
    field = {"label": label, "key": key, "required": required,
             "choices": choices, "default": default, "valuemap": valuemap,
             "filepicker": filepicker, "rawappend": rawappend}
    if picker:
        field["picker"] = picker
    # remember="name" (2.90, Gabe): the box starts with what was typed in it
    # the last time the task ran (desktop: gamgui.ini 'remember_<name>';
    # browser: localStorage) instead of the default.
    if remember:
        field["remember"] = remember
    return field


# 2.83: what to do about a compromised account that GAM cannot do. Shown at
# the end of the guided workflow, saved as NEXT-STEPS.txt in its evidence
# folder, and shown by the checklist task. ASCII only.
# 2.89: grouped, and extended from MOREnet's "Detailed Tips for Investigating
# a Google Account Compromise" (08-26-2026, sent by Gabe 10-15-2026) - its
# Admin-console-only steps are here; its GAM-able steps are GAMGUI tasks
# (evidence in the guided response, Trace an IP address, Who clicked a
# phishing link, Suspicious sign-ins, Lock out several accounts).
COMPROMISED_CHECKLIST = """STEPS GAM CANNOT DO - DO THESE NEXT

A. THE USER AND THEIR DEVICES
 1. Talk to the user in person or by phone - not by email (the attacker may
    still be reading it).
 2. Saved passwords: assume the attacker has every password saved in the
    user's browser. Have the user change the password of EVERY site saved
    there (Chrome: Settings > Passwords, or passwords.google.com) and every
    other account that used the same or a similar password - bank, personal
    email, social media, other school systems.
 3. Chrome sync: if sync was on, the attacker's own browser may have synced
    those passwords and bookmarks. With the user, open myaccount.google.com
    > Security > Your devices and sign out every device they do not know.
 4. Malware: scan or reimage the user's computer(s) and phone - every device
    where they opened the attachment or clicked the link. A keylogger would
    capture the NEW password too. Keep the user's browser history from the
    time of the compromise for the investigation.
 5. Before giving the account back: set a new temporary password
    (Users > Reset password) and require a change at the next sign-in. If
    2-Step Verification was turned off, have the user re-enroll it on a
    phone or security key THEY hold. Check the recovery email and phone in
    UserInfo.txt and AccountChanges.csv - the attacker may have changed them.
 6. "Sign in with Google": with the user, review myaccount.google.com >
    Security > Your connections to third-party apps & services.

B. INVESTIGATE (the evidence folder, then the Admin console)
 7. Write down: how it started, WHEN (the first odd sign-in - the compromise
    can be days or weeks before the phishing went out), which accounts, what
    data was opened, and which other systems were reached.
 8. Sign-ins: SignInIPs.csv lists every IP address with its country and
    whether Google flagged it suspicious (Logins.csv has each sign-in).
    Rule out the school's and the user's home addresses. For each odd one,
    run Compromised Account > Trace an IP address - it shows every account
    that address touched, and whether it used Takeout (mass export), signed
    in to other systems (SSO), or opened Drive files and mail.
 9. Footholds: in the evidence folder, look for any Gmail filter,
    forwarding address, delegate or send-as identity the user did not set
    up, and remove it (Gmail tasks). An auto-forward to an outside address
    or a filter that deletes or archives mail is the classic sign. Also
    Drafts.csv (attackers park text in drafts), TrashedMail.csv (mail they
    deleted to hide replies), Sites.csv (sites made during the compromise),
    ContactsLog.csv (were contacts exported?) and Takeout.csv.
10. Investigation tool (Security > Investigation tool): Gmail log events
    for exactly what mail was read, forwarded or deleted; Device log events
    for unusual devices (virtual machines) - Devices > Mobile & endpoints >
    the device > View audit info shows what was downloaded. Document it
    before you wipe or delete a device.
11. Vault: mail and files the attacker permanently deleted (if retention is
    on), and the user's drafts and history beyond what GAMGUI saved.
12. Other systems: SSO.csv lists the systems signed into with Google.
    Check those systems' own logs, and every system whose password was
    saved in Google Password Manager.
13. Security > Alert center: related alerts (suspicious sign-in, leaked
    password, phishing) for this and other users.

C. STOP THE SPREAD (Admin console)
14. Who got the phishing email / who clicked: Email Cleanup finds and
    removes it from every mailbox (this works on every edition - the
    Investigation tool's delete needs Plus); Compromised Account > Who
    clicked a phishing link lists everyone who clicked it. Lock those
    accounts too (Lock out several accounts) and change their passwords.
15. Phishing link: Apps > Google Workspace > Gmail > Compliance > Content
    compliance: a rule for Inbound (and Internal - receiving) mail that
    matches the bad domain (Simple content match), action Quarantine (or
    Reject). It blocks every future message with a link to that domain.
16. A file shared from outside as the phishing: make a 'blocklist' group
    that allows outside members (GAMGUI: Groups > Create group, Let a group
    have outside members, Add member), then Security > Access and data
    control > Trust rules: Drive > Receiving files, from that group, Block.
    Test it with a personal Gmail account first.
17. Offline access: consider turning off offline access for Gmail, Docs and
    Calendar (Admin console - search 'offline').

D. NOTIFY
18. Mail the attacker sent: SentMail.csv lists recent sent mail. If the
    account sent phishing, warn the people it went to and remove it with
    Email Cleanup (Full incident-response workflow).
19. Outside people and the organization the phishing came from: call or
    email their IT, from an account that was NOT compromised. Give the
    sender, the subject and what the link or attachment does; write links
    so they cannot be clicked (hxxps://bad[.]example[.]com). Ask anyone who
    clicked to tell their IT, sign out of every session and THEN change
    the password. Do not tell them whether to delete the message, and say
    nothing about data being or not being exposed unless legal counsel
    says to.
20. If student or staff data may have been exposed, follow your
    organization's incident-reporting policy (law enforcement where it
    applies - in the US, the FBI's ic3.gov for money losses or crypto
    wallet addresses in the phishing - and your state's information-sharing
    group).

E. AFTERWARDS - HARDEN (Admin console)
21. Gmail > Safety: turn on the spoofing and authentication protections
    with the action Quarantine, and 'Apply future recommended settings
    automatically'. Enhanced pre-delivery scanning and malware protections
    on; ransomware detection on (Education Plus).
22. SPF, DKIM and DMARC for every domain you send mail from (DNS, plus
    Apps > Gmail > Authenticate email for DKIM).
23. Security > Google session control: 12 hours or less. It applies at the
    next sign-in, so sign everyone out once (Compromised Account > Sign out
    many users).
24. Limit how many recipients a message can have (by OU); Vault retention
    on; data region set if you need one.
25. Security > Rules: an alert (or suspend) rule for suspicious sign-ins and
    'Sensitive action' re-authentication events.
26. Passkeys or security keys - at least for every admin; fewer super
    admins (custom admin roles); DLP rules for ID and banking numbers;
    Context-Aware Access.
27. When it is safe: Users > Suspend / unsuspend user to reactivate, and
    Users > Reset password to give the user their new password.
"""


def compromised_plan(values):
    # 2.84 (moved from GamGui._compromised_plan so the desktop app and the
    # browser version run the SAME steps): the guided compromised-account
    # workflow, from the form, as (phase, label, argv, file name or "") in
    # run order. Pure - nothing is run.
    #   1 CONTAIN  - lock (unusable password) + sign out everywhere
    #   2 EVIDENCE - read-only, saved before anything is removed
    #   3 REMOVE   - app passwords / backup codes / tokens, IMAP / POP, 2SV
    #   4 SUSPEND  - last: GAM cannot remove backup codes from a
    #                suspended user (GAM wiki, Users - Deprovision)
    email = values.get("email", "").strip()
    contain = values.get("contain", "lock") or "lock"
    days = (values.get("days", "30") or "30").strip()
    since = "-" + days + "d"
    plan = []
    if contain != "none":
        plan.append(("CONTAIN", "Block sign-in (a password nobody can type)",
                     ["update", "user", email, "password", "blocklogin"], ""))
        plan.append(("CONTAIN", "Sign out everywhere (revoke every session cookie)",
                     ["user", email, "signout"], ""))
    evidence = [
        ("Account details (recovery email / phone, 2SV, last sign-in)",
         ["info", "user", email], "UserInfo.txt"),
        ("Gmail filters", ["user", email, "show", "filters"], "Filters.txt"),
        ("Forwarding", ["user", email, "show", "forward"], "Forwarding.txt"),
        ("Forwarding addresses", ["user", email, "show", "forwardingaddresses"],
         "ForwardingAddresses.txt"),
        ("Delegates", ["user", email, "show", "delegates"], "Delegates.txt"),
        ("Send-as identities", ["user", email, "show", "sendas"], "SendAs.txt"),
        ("Vacation / auto-reply", ["user", email, "show", "vacation"], "Vacation.txt"),
        ("IMAP setting", ["user", email, "show", "imap"], "Imap.txt"),
        ("POP setting", ["user", email, "show", "pop"], "Pop.txt"),
        ("App passwords", ["user", email, "show", "asps"], "AppPasswords.txt"),
        ("Apps with access (OAuth tokens)", ["user", email, "print", "tokens"],
         "OAuthTokens.csv"),
        ("Mobile devices", ["print", "mobile", "query", "email:" + email],
         "MobileDevices.csv"),
        ("Mail sent in the last %s days" % days,
         ["user", email, "print", "messages", "query", "in:sent newer_than:%sd" % days,
          "headers", "from,to,subject,date", "max_to_print", "500"], "SentMail.csv"),
        ("Sign-in log (IP addresses)", ["report", "login", "user", email, "start", since],
         "Logins.csv"),
        # (No app-authorization log: a busy account can have 50,000+
        # events a week - "Apps with access" above is what matters.)
        ("Drive activity log", ["report", "drive", "user", email, "start", since],
         "DriveActivity.csv"),
        ("Gmail log (not in every Workspace edition)",
         ["report", "gmail", "user", email, "start", since], "GmailLog.csv"),
        # 2.89 (MOREnet's investigation tips): what else the attacker did.
        ("Account changes log (password, recovery, 2-Step Verification)",
         ["report", "useraccounts", "user", email, "start", since], "AccountChanges.csv"),
        ("Takeout log (mass data export)",
         ["report", "takeout", "user", email, "start", since], "Takeout.csv"),
        ("SSO log (other systems signed into with Google)",
         ["report", "saml", "user", email, "start", since], "SSO.csv"),
        ("Contacts log (were contacts exported?)",
         ["report", "contacts", "user", email, "start", since], "ContactsLog.csv"),
        ("Device log", ["report", "mobile", "user", email, "start", since], "DeviceLog.csv"),
        # Gmail log type 15 = 'Link in message body was clicked' (Reports API
        # appendix); GAM's Gmail report covers at most 30 days.
        ("Links clicked in mail (Gmail log)",
         ["report", "gmail", "user", email, "filter", "event_info.mail_event_type==15",
          "range", "-%sd" % min(int(days) if days.isdigit() else 30, 30), "today"],
         "LinkClicks.csv"),
        ("Drafts (attackers park text in drafts)",
         ["user", email, "print", "messages", "query", "in:drafts",
          "headers", "from,to,subject,date", "max_to_print", "200"], "Drafts.csv"),
        ("Mail moved to the Trash in the last %s days" % days,
         ["user", email, "print", "messages", "query", "in:trash newer_than:%sd" % days,
          "includespamtrash", "headers", "from,to,subject,date", "max_to_print", "500"],
         "TrashedMail.csv"),
        ("Google Sites the user owns",
         ["user", email, "print", "filelist", "query",
          "mimeType = 'application/vnd.google-apps.site'",
          "fields", "id,name,createdtime,modifiedtime"], "Sites.csv"),
    ]
    for label, argv, name in evidence:
        plan.append(("EVIDENCE", label, argv, name))
    if contain != "none":
        if values.get("deprov", "yes") == "yes":
            plan.append(("REMOVE", "Remove app passwords, backup codes and every "
                         "app's access", ["user", email, "deprovision"], ""))
        if values.get("popimap", "yes") == "yes":
            plan.append(("REMOVE", "Turn off IMAP", ["user", email, "imap", "off"], ""))
            plan.append(("REMOVE", "Turn off POP", ["user", email, "pop", "off"], ""))
        if values.get("turnoff2sv", "no") == "yes":
            plan.append(("REMOVE", "Turn off 2-Step Verification (the user re-enrolls)",
                         ["user", email, "turnoff2sv"], ""))
        if contain == "suspend":
            plan.append(("SUSPEND", "Suspend the account",
                         ["update", "user", email, "suspended", "on"], ""))
    return plan


def compromised_step_state(rc, out):
    # One step's result in plain words for the screen and Summary.txt.
    #   0 ok; 60 = GAM found none (e.g. no app passwords); -2 = the
    #   report's time limit stopped it. Seen in the live test (10-06-2026):
    #   an OU that ENFORCES 2-Step Verification refuses turnoff2sv.
    if "required by admin policy" in (out or ""):
        return "not possible - 2-Step Verification is enforced by policy for this user"
    return {0: "ok", 60: "none found",
            -2: "stopped after 10 minutes (too much data)"}.get(rc, "exit code %d" % rc)


SIGNIN_IP_COLUMNS = ["ipAddress", "country", "signIns", "suspicious", "failed", "first",
                     "last", "types"]


def signin_ip_rows(rows):
    # A 'report login' CSV -> one row per IP address: country, how many
    # sign-in events, how many Google flagged suspicious, failures, first /
    # last time, login types. Most suspicious first, then busiest.
    ips = {}
    for row in rows:
        ip = (row.get("ipAddress") or "").strip()
        if not ip:
            continue
        e = ips.setdefault(ip, {"ipAddress": ip, "country": set(), "signIns": 0,
                                "suspicious": 0, "failed": 0, "first": "", "last": "",
                                "types": set()})
        e["signIns"] += 1
        if (row.get("is_suspicious") or "").strip().lower() == "true":
            e["suspicious"] += 1
        if (row.get("name") or "") == "login_failure":
            e["failed"] += 1
        region = (row.get("networkInfo.regionCode") or "").strip()
        if region:
            e["country"].add(region)
        if (row.get("login_type") or "").strip():
            e["types"].add(row["login_type"].strip())
        when = (row.get("id.time") or "").strip()
        if when and (not e["first"] or when < e["first"]):
            e["first"] = when
        if when and when > e["last"]:
            e["last"] = when
    out = []
    for e in ips.values():
        out.append(dict(e, country=", ".join(sorted(e["country"])),
                        types=", ".join(sorted(e["types"]))))
    out.sort(key=lambda r: (-r["suspicious"], -r["signIns"], r["ipAddress"]))
    return out


def _read_csv_file(path):
    import csv, os
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def compromised_findings(folder):
    # 2.89: after the evidence is saved - the sign-in IP addresses as
    # SignInIPs.csv, and a few plain-English lines for the screen and
    # Summary.txt (what to look at first). Read-only on the folder's files.
    import csv, os
    lines = ["FINDINGS (from the evidence above)"]
    logins = _read_csv_file(os.path.join(folder, "Logins.csv"))
    if logins:
        ips = signin_ip_rows(logins)
        with open(os.path.join(folder, "SignInIPs.csv"), "w", encoding="utf-8",
                  newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SIGNIN_IP_COLUMNS)
            writer.writeheader()
            writer.writerows(ips)
        countries = sorted({c for r in ips for c in r["country"].split(", ") if c})
        flagged = [r for r in ips if r["suspicious"]]
        lines.append("  Sign-ins: %d events from %d IP addresses (countries: %s) - "
                     "SignInIPs.csv" % (len(logins), len(ips), ", ".join(countries) or "?"))
        if flagged:
            lines.append("  Google flagged %d IP address(es) as SUSPICIOUS: %s"
                         % (len(flagged), ", ".join(r["ipAddress"] for r in flagged[:5])))
            lines.append("    -> Compromised Account > Trace an IP address, for each one.")
    elif logins is None:
        lines.append("  Sign-ins: no sign-in log was saved.")
    else:
        lines.append("  Sign-ins: none in the log for that time.")
    for name, what in (("Takeout.csv", "Takeout (data export) events - check them first"),
                       ("AccountChanges.csv", "account changes (password, recovery, 2SV)"),
                       ("SSO.csv", "sign-ins to other systems through Google (SSO)"),
                       ("ContactsLog.csv", "contacts events"),
                       ("LinkClicks.csv", "links clicked in mail"),
                       ("Drafts.csv", "drafts"),
                       ("TrashedMail.csv", "messages moved to the Trash"),
                       ("Sites.csv", "Google Sites the user owns")):
        rows = _read_csv_file(os.path.join(folder, name))
        if rows:
            lines.append("  %d %s - %s" % (len(rows), what, name))
    return lines


def flagged_signin_ips(folder, most=5):
    # 2.90: the IP addresses Google flagged suspicious in a guided run's
    # SignInIPs.csv (most-flagged first, at most 'most' - Trace an IP address
    # takes up to 5) - what the desktop app offers to trace.
    import os
    rows = _read_csv_file(os.path.join(folder, "SignInIPs.csv")) or []
    return [r["ipAddress"] for r in rows
            if (r.get("suspicious") or "0").isdigit() and int(r["suspicious"]) > 0][:most]


def mailbox_audit_checks(email):
    # The Mailbox takeover audit's read-only checks, as (label, argv) in run
    # order - the four common email-attacker footholds on one mailbox.
    # Shared by the desktop app and the browser version (2.84) so both run
    # the SAME commands. Pure - nothing is run.
    return [
        ("Gmail filters / rules", ["user", email, "show", "filters"]),
        ("Forwarding addresses", ["user", email, "show", "forwardingaddresses"]),
        ("Send-as identities", ["user", email, "show", "sendas"]),
        ("Mailbox delegates", ["user", email, "show", "delegates"]),
    ]


def _mail_fields(more_example="after:2026/10/01 has:attachment"):
    # 2.83: the search boxes every Email Cleanup task shares - the same
    # plain From / Subject boxes as the Full incident workflow, plus the
    # exact Message-ID and (advanced) any other Gmail search words, so
    # nobody has to remember  from:x subject:(y) rfc822msgid:z.
    # 2.84: the Gmail category's message tasks use them too; more_example
    # is the More box's example for the task (e.g. before:2026/01/01).
    return [F("From address e.g. attacker@evil.com", "from", False),
            F("Subject words e.g. Compensation Review & Bonus (no quotes "
              "needed)", "subject", False),
            F("Message-ID (optional - the most precise) e.g. "
              "CAB1x2y3@mail.example.com", "msgid", False),
            F("More Gmail search words (optional, advanced) e.g. "
              + more_example, "more", False)]


# Staff departure hand-off (workflow="handoff") - the three "afterwards"
# choices and the default auto-reply. Google documents that a SUSPENDED
# user's new email is blocked, which is why "keep active but locked" exists.
HANDOFF_AFTER = [
    "Kept ACTIVE but locked (mail keeps flowing; uses a license)",
    "SUSPENDED (Google blocks new mail to the old address)",
    "Put back the way it was",
]
# Remove outside sharing from a report (workflow="unshare") - what to remove.
UNSHARE_MODES = [
    "Everything listed (outside people AND public links)",
    "Only outside people",
    "Only 'anyone with the link' / public links",
]
HANDOFF_MESSAGE = ("Thank you for your email. #old# is no longer with our "
                   "organization. Please send future messages to #new#."
                   "\\n\\nThis is an automated reply.")


# 2.84: who can post (send email) to a group - friendly words -> GAM's
# whocanpostmessage values (GamCommands.txt, GAM 7.48.22). The GAM word is
# in brackets so the choice matches GAM's documentation.
WHO_CAN_POST = {
    "Group members (all_members_can_post)": "all_members_can_post",
    "Anyone in the organization (all_in_domain_can_post)": "all_in_domain_can_post",
    "Group managers and owners (all_managers_can_post)": "all_managers_can_post",
    "Group owners only (all_owners_can_post)": "all_owners_can_post",
    "Nobody (none_can_post)": "none_can_post",
    "Anyone, even people OUTSIDE the organization (anyone_can_post)": "anyone_can_post",
}
# The bulk tasks' extra choice: each row's own value, from the column the
# 'Who can post - every group' report writes (GAM's ~Column substitution).
BULK_WHO_CAN_POST = {
    "Each row's own setting (whoCanPostMessage column)": "~whoCanPostMessage",
}

# 2.84: the everyday group settings, for "Group settings" in Groups. Each
# is (GAM option, report column, friendly words -> GAM value). Options and
# values from GamCommands.txt (GAM 7.48.22); the report columns are what
# 'print groups ... settings fields ...' writes (checked against gam.exe
# 10-07-2026), and GAM accepts the report's UPPER-CASE values back.
GROUP_SETTINGS = [
    ("whocanjoin", "whoCanJoin", "Who can join", {
        "Only people who are invited (invited_can_join)": "invited_can_join",
        "People can ask to join (can_request_to_join)": "can_request_to_join",
        "Anyone in the organization can join (all_in_domain_can_join)":
            "all_in_domain_can_join",
        "Anyone, even people OUTSIDE the organization (anyone_can_join)":
            "anyone_can_join"}),
    ("whocanviewmembership", "whoCanViewMembership", "Who can see the members", {
        "Group members (all_members_can_view)": "all_members_can_view",
        "Anyone in the organization (all_in_domain_can_view)": "all_in_domain_can_view",
        "Group managers and owners (all_managers_can_view)": "all_managers_can_view",
        "Group owners only (all_owners_can_view)": "all_owners_can_view"}),
    ("whocanviewgroup", "whoCanViewGroup", "Who can read the conversations", {
        "Group members (all_members_can_view)": "all_members_can_view",
        "Anyone in the organization (all_in_domain_can_view)": "all_in_domain_can_view",
        "Group managers and owners (all_managers_can_view)": "all_managers_can_view",
        "Group owners only (all_owners_can_view)": "all_owners_can_view",
        "Anyone, even people OUTSIDE the organization (anyone_can_view)":
            "anyone_can_view"}),
    ("whocancontactowner", "whoCanContactOwner", "Who can contact the group's owners", {
        "Anyone in the organization (all_in_domain_can_contact)":
            "all_in_domain_can_contact",
        "Group members (all_members_can_contact)": "all_members_can_contact",
        "Group managers and owners (all_managers_can_contact)":
            "all_managers_can_contact",
        "Group owners only (all_owners_can_contact)": "all_owners_can_contact",
        "Anyone, even people OUTSIDE the organization (anyone_can_contact)":
            "anyone_can_contact"}),
    ("whocandiscovergroup", "whoCanDiscoverGroup", "Who can find the group", {
        "Anyone in the organization (all_in_domain_can_discover)":
            "all_in_domain_can_discover",
        "Group members only (all_members_can_discover)": "all_members_can_discover",
        "Anyone, even people OUTSIDE the organization (anyone_can_discover)":
            "anyone_can_discover"}),
    ("messagemoderationlevel", "messageModerationLevel", "Messages held for approval", {
        "None - nothing is held (moderate_none)": "moderate_none",
        "From new members (moderate_new_members)": "moderate_new_members",
        "From people who are not members (moderate_non_members)":
            "moderate_non_members",
        "Every message (moderate_all_messages)": "moderate_all_messages"}),
    ("whocanpostmessage", "whoCanPostMessage", "Who can post", WHO_CAN_POST),
]
# All seven settings' GAM option names, comma separated (for 'fields').
GROUP_SETTING_FIELDS = ",".join(opt for opt, _col, _l, _m in GROUP_SETTINGS)


def _group_setting_fields(bulk=False):
    # One OPTIONAL dropdown per setting (blank = leave it as it is). The
    # bulk tasks add "Each row's own setting (<column> column)" - GAM's
    # ~Column, the column the settings report writes.
    out = []
    for opt, col, label, choices in GROUP_SETTINGS:
        if bulk:
            choices = dict(choices, **{"Each row's own setting (%s column)" % col:
                                       "~" + col})
        out.append(F(label + " (blank = leave it as it is)", opt, False,
                     valuemap=choices))
    return out


def _group_setting_template():
    # " [whocanjoin {whocanjoin}] [whocanviewmembership {...}] ..."
    return "".join(" [%s {%s}]" % (opt, opt) for opt, _c, _l, _m in GROUP_SETTINGS)


def _need_one(task, keys, message):
    # Marks a task so build_command refuses it unless at least ONE of these
    # boxes is filled (e.g. "change settings" with every setting blank).
    task["needone"] = (list(keys), message)
    return task


FIND_WHERE = {
    "Shared Drives (each drive's files, read as one of its organizers)": "shared",
    "Users' My Drive (the files each user owns)": "mydrive",
}
# key -> (label, what the list box needs: None | "domains" | "addresses",
#         also checks a Shared Drive's own members)
FIND_WHAT = [
    ("outside", "Shared OUTSIDE your domains (people, groups, domains)", None, True),
    ("anyone", "Shared with ANYONE (public on the web, or anyone with the link)", None, False),
    ("public", "Public on the web - anyone can FIND it", None, False),
    ("anyonelink", "Anyone WITH THE LINK (not findable)", None, False),
    ("link", "Shared by LINK - anyone or a whole domain, with the link", None, False),
    ("findable", "FINDABLE - anyone or a whole domain can search for it", None, False),
    ("domains", "Shared with THESE DOMAINS (the domain, or anyone in it)", "domains", True),
    ("groups", "Shared with THESE GROUPS", "addresses", True),
    ("users", "Shared with THESE USERS", "addresses", True),
    ("deleted", "Shared with DELETED users or groups", None, True),
    ("everything", "ALL sharing (every permission except the owner)", None, True),
    ("guests", "GUESTS - access to Shared Drive files WITHOUT being a member of the "
               "drive (Shared Drives only)", None, False),
    # 2.88: Ross's GetSuspendedUserSharedDriveACLs / GetTeamDriveSuspendedUsersACLs.
    ("suspended", "Shared with SUSPENDED or ARCHIVED users (they cannot open it any "
                  "more)", None, True),
    # 2.88: Ross's GetSharedWithListOfDisabledUsersDriveACLs / ...SharedDriveACLs.
    ("onlysuspended", "Shared ONLY with suspended or archived users (nobody active "
                      "can open it but the owner)", None, False),
    # 2.88: Ross's GetSharedWithNonAccountUsersDriveACLs.
    ("nonaccount", "Shared with people who have NO account here (outside people, "
                   "deleted users)", None, True),
]
FIND_WHAT_LABELS = {label: key for key, label, _n, _m in FIND_WHAT}
FIND_WHO = {
    "One user (or several, comma separated)": "user",
    "An OU and its sub-OUs": "ou_and_children",
    "A group's members": "group",
    "Everyone (all users)": "all",
}


def _find_fields(where=None, what=None, who=None):
    # The Find sharing form (2.87). The GAM Scripts entries pass a preset
    # (the labels of FIND_WHERE / FIND_WHAT / FIND_WHO) as the defaults.
    first = lambda d: list(d)[0]
    what_label = [w[1] for w in FIND_WHAT if w[0] == (what or "outside")][0]
    where_label = [k for k, v in FIND_WHERE.items() if v == (where or "shared")][0]
    who_label = [k for k, v in FIND_WHO.items() if v == who][0] if who else ""
    return [
        F("Where to look", "where", default=where_label, valuemap=FIND_WHERE),
        F("What to look for", "what", default=what_label,
          valuemap={w[1]: w[0] for w in FIND_WHAT}),
        F("Your own domains, comma separated (needed for Shared Drives and OUTSIDE)",
          "own", False),
        F("With OUTSIDE: also find 'anyone with the link' / public files", "anyone",
          False, default="Yes", valuemap={"Yes": "yes", "No": "no"}),
        F("For THESE domains / groups / users: comma separated", "list", False),
        F("... or a CSV file with them", "listcsv", False, filepicker=True),
        F("Column in that CSV (blank = the first column)", "listcol", False),
        F("Shared Drives: only drives whose name contains (optional)", "match", False),
        F("Shared Drives: include sharing the files inherit from the drive / folder",
          "inherited", False, default="No - only sharing set on the file itself",
          valuemap={"No - only sharing set on the file itself": "no",
                    "Yes - include inherited sharing": "yes"}),
        F("My Drive: whose files", "who", False, default=who_label, valuemap=FIND_WHO),
        F("My Drive: the user(s) / OU / group", "whoval", False),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
        F("Speed: parallel threads (blank = config default)", "threads", False),
    ]


# 2.87: the "GAM Scripts (Ross Scroggs)" section - one entry per script of
# GAM-team/GAM-Scripts whose job GAM now does itself (Ross, via Gabe,
# 10-08-2026: "some of them have been superceded by commands"). Each opens
# Find sharing set up for it: (new name, where, what, who, Ross's scripts).
GAM_SCRIPT_FINDS = [
    ("Shared Drive files shared outside your domains", "shared", "outside", None,
     "GetSharedExternallyTeamDriveACLs.py, GetNonDomainTeamDriveACLs.py"),
    ("Shared Drive files shared with anyone", "shared", "anyone", None,
     "GetSharedWithAnyoneTeamDriveACLs.py"),
    ("Shared Drive files shared by link", "shared", "link", None,
     "GetLinkSharedTeamDriveACLs.py"),
    ("Shared Drive files shared with chosen domains", "shared", "domains", None,
     "GetSharedWithDomainTeamDriveACLs.py"),
    ("Shared Drive files shared with chosen groups", "shared", "groups", None,
     "GetSharedWithGroupTeamDriveACLs.py"),
    ("Shared Drive files shared with chosen users (or a CSV list)", "shared", "users", None,
     "GetSharedWithUserTeamDriveACLs.py, GetSharedWithListOfUsersTeamDriveACLs.py"),
    ("Shared Drive sharing with deleted users or groups", "shared", "deleted", None,
     "GetTeamDriveDeletedPermissions.py, GetTeamDriveDeletedUsersACLs.py"),
    ("All Shared Drive file sharing", "shared", "everything", None,
     "GetTeamDriveFileACLs.py"),
    ("Shared Drive guests - file access without drive membership", "shared", "guests",
     None, "GetTeamDriveGuestMembers.py"),
    ("Shared Drive sharing with suspended or archived users", "shared", "suspended", None,
     "GetSuspendedUserSharedDriveACLs.py, GetTeamDriveSuspendedUsersACLs.py"),
    ("Shared Drive files shared only with suspended or archived users", "shared",
     "onlysuspended", None, "GetSharedWithListOfDisabledUsersSharedDriveACLs.py"),
    ("My Drive files shared only with suspended or archived users", "mydrive",
     "onlysuspended", "all", "GetSharedWithListOfDisabledUsersDriveACLs.py"),
    ("My Drive files shared with people who have no account here", "mydrive",
     "nonaccount", "all", "GetSharedWithNonAccountUsersDriveACLs.py"),
    ("My Drive files shared outside your domains", "mydrive", "outside", "all",
     "GetSharedExternallyDriveACLs.py, GetNonDomainDriveACLs.py, "
     "GetSharedOnlyExternallyDriveACLs.py"),
    ("My Drive files shared with anyone", "mydrive", "anyone", "all",
     "GetSharedWithAnyoneDriveACLs.py"),
    ("My Drive files shared by link", "mydrive", "link", "all",
     "GetLinkSharedDriveACLs.py, GetTypeWithLinkDriveACLs.py"),
    ("My Drive files anyone or a domain can find", "mydrive", "findable", "all",
     "GetAllowFileDiscoveryDriveACLs.py"),
    ("My Drive files shared with chosen domains", "mydrive", "domains", "user",
     "GetSharedWithDomainDriveACLs.py, GetUserNonOwnerDomainDriveACLs.py"),
    ("My Drive files shared with chosen groups", "mydrive", "groups", "all",
     "GetSharedWithGroupDriveACLs.py"),
    ("My Drive files shared with chosen users (or a CSV list)", "mydrive", "users", "all",
     "GetSharedWithUserDriveACLs.py, GetSharedWithListOfUsersDriveACLs.py"),
    ("My Drive sharing with deleted users or groups", "mydrive", "deleted", "all",
     "GetSharedFileDeletedPermissions.py"),
    ("All My Drive file sharing (except the owner)", "mydrive", "everything", "user",
     "GetSharedFilePermissions.py, GetUserNonOwnerDriveACLs.py, "
     "ShowUserNonOwnerDriveACLs.py, MakeOneItemPerRowACLs.py"),
]


def _sd_script_tasks():
    # 2.87: Ross's Shared Drive scripts that ONE GAM command now replaces
    # (GAM wiki, Shared Drives: Display members / external members of all
    # Shared Drives, Shared Drives with no members / organizers). Listed in
    # Shared Drives AND in GAM Scripts (by the script's new name). Each
    # command was read by gam.exe 7.48.23 (nonsense last word).
    return [
        T("Members of every Shared Drive - one per row (CSV/Sheet)",
          "Every member of every Shared Drive, one per row, with the drive's name "
          "and created time. Was Ross Scroggs' GetTeamDriveMembers.py and "
          "GetTeamDriveNameACLs.py (GAM-Scripts) - GAM does it now.",
          "print shareddriveacls oneitemperrow {todrive}", [*_out()]),
        T("Shared Drive members outside your domains (CSV/Sheet)",
          "Members of any Shared Drive whose address is NOT in your domains, one per "
          "row. Was Ross Scroggs' GetNonDomainTeamDriveACLs.py (GAM-Scripts) - GAM "
          "does it now. For the FILES inside the drives use Find sharing.",
          "print shareddriveacls pm notdomainlist {own} em oneitemperrow {todrive}",
          [F("Your own domains, comma separated (include sub-domains)", "own"),
           *_out()]),
        T("Shared Drive memberships of deleted users or groups (CSV/Sheet)",
          "Shared Drive members that are users or groups that no longer exist. Was "
          "Ross Scroggs' GetTeamDriveDeletedPermissions.py / "
          "GetTeamDriveDeletedUsersACLs.py (GAM-Scripts) - GAM does it now.",
          "print shareddriveacls pm deleted true em oneitemperrow {todrive}", [*_out()]),
        T("Shared Drives with no members or no organizers (CSV/Sheet)",
          "Lists the Shared Drives that have no members at all, or no organizer "
          "(manager) - nobody can manage those. GAM wiki, Shared Drives.",
          "print shareddrives query {which} {todrive}",
          [F("Which Shared Drives", "which", default="With no organizers (managers)",
             valuemap={"With no organizers (managers)": "organizerCount = 0",
                       "With no members at all": "memberCount = 0"}),
           *_out()]),
    ]


def _drive_script_tasks():
    # 2.87: two more of Ross's My Drive scripts that ONE GAM command does now.
    # Without pmfilter a file matches when ANY of its permissions matches;
    # 'pma skip' turns that around (GAM source: PermissionMatch.
    # CheckPermissionMatches). Read by gam.exe 7.48.23.
    return [
        T("Files that are shared - one row per file (CSV/Sheet)",
          "Every file the user(s) own that anyone else can see (any sharing at "
          "all), one row per file. Was Ross Scroggs' GetSharedFiles.py (GAM-"
          "Scripts) - GAM does it now. For WHO it is shared with, use Find sharing.",
          "{userscope:usertype:userval} print filelist showownedby me fields "
          "id,name,mimetype,webviewlink pm notrole owner em {todrive}",
          [*_user_scope(), *_out()]),
        T("Files that are NOT shared with anyone (CSV/Sheet)",
          "Every file the user(s) own that nobody else can see. Was Ross Scroggs' "
          "GetNonSharedFiles.py (GAM-Scripts) - GAM does it now.",
          "{userscope:usertype:userval} print filelist showownedby me fields "
          "id,name,mimetype,webviewlink pm notrole owner em pma skip {todrive}",
          [*_user_scope(), *_out()]),
        # GAM source (printFileList): with filepath + oneitemperrow, the
        # path columns are added to the row BEFORE it is split per
        # permission, so every permission row carries the file's path.
        T("Sharing with folder paths - one row per permission (CSV/Sheet)",
          "Every permission on the user(s)' files, one per row, with the file's "
          "folder path and the owner's address in their own columns. Was Ross "
          "Scroggs' GetPermissionsByPath.py, GetFilePermissionsWithPaths.py and "
          "UpdateOwnerFromPermissions.py (GAM-Scripts) - GAM does it now. To "
          "remove sharing afterwards use Find sharing (its report feeds 'Remove "
          "outside sharing listed in a report').",
          "{userscope:usertype:userval} print filelist showownedby {whose} fields "
          "id,name,mimetype,permissions,owners.emailaddress filepath oneitemperrow "
          "[pm {ownerrow} owner em pmfilter] {todrive}",
          [*_user_scope(),
           F("Which files", "whose", default="Files they own",
             valuemap={"Files they own": "me",
                       "Every file they can see (owned by anyone)": "any"}),
           F("The owner's own entry", "ownerrow",
             default="Leave it out (only the sharing)",
             valuemap={"Leave it out (only the sharing)": "notrole",
                       "Include it": ""}),
           *_out()]),
    ]


# "Upgrade Shared Drive Contributors to Content managers" (sdwriters, 2.87) -
# the steps are sd_writers_read_step / sd_writers_command further down.
SD_WRITERS_MODES = {
    "Make every Contributor a Content manager": "upgrade",
    "Put them back as Contributors (from a record file)": "undo",
}
SD_WRITERS_COLUMNS = ["drive_id", "drive_name", "type", "member", "perm", "old_role"]
SD_WRITERS_ROLE = {"upgrade": "contentmanager", "undo": "writer"}


def _sd_writers_fields():
    return [
        F("What to do", "mode", default="Make every Contributor a Content manager",
          valuemap=SD_WRITERS_MODES),
        F("Only Shared Drives whose name contains (optional)", "match", False),
        F("Folder for the record file", "folder", default="C:\\GAMExports"),
        F("Put back: the record file (SharedDrives-Contributors-...csv)", "csvfile",
          False, filepicker=True),
    ]


# "Shared Drive members by role" (sdroles, 2.87) - Ross's
# GetTeamDriveMembersByRole.py: one row per drive, a column per role. The
# steps are sd_roles_steps / sd_roles_report further down.
SD_ROLES = [("organizer", "Manager"), ("fileOrganizer", "Content manager"),
            ("writer", "Contributor"), ("commenter", "Commenter"), ("reader", "Viewer")]
SD_ROLES_TYPES = {
    "Everyone (users, groups and domains)": "all",
    "Users only": "user",
    "Groups only": "group",
}
SD_ROLES_SEP = {"A space": "space", "A comma": "comma", "A new line in the cell": "newline"}
SD_ROLES_NAMES = {
    "Google's names (Manager, Content manager, Contributor...)": "gui",
    "GAM / API names (organizer, fileOrganizer, writer...)": "api",
}
SD_ROLES_NAME = "Shared Drive members by role - one row per drive (CSV)"


def _sd_roles_fields():
    return [
        F("Only Shared Drives whose name contains (optional)", "match", False),
        F("Members to list", "types", default="Everyone (users, groups and domains)",
          valuemap=SD_ROLES_TYPES),
        F("Only members in these domains, comma separated (optional)", "domains", False),
        F("Role names in the column headings", "names",
          default="Google's names (Manager, Content manager, Contributor...)",
          valuemap=SD_ROLES_NAMES),
        F("Between the members in a cell", "sep", default="A space", valuemap=SD_ROLES_SEP),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _sd_roles_tasks():
    # [the Shared Drives task, the GAM Scripts entry] - the same workflow.
    return [
        T(SD_ROLES_NAME,
          "One row per Shared Drive with its Managers, Content managers, "
          "Contributors, Commenters and Viewers each in their own column. GAM lists "
          "every drive's members; GAMGUI puts them side by side. Drives with no "
          "members are listed too. Read-only.",
          "", _sd_roles_fields(), workflow="sdroles"),
        T("Shared Drive members by role",
          "Ross Scroggs' GetTeamDriveMembersByRole.py (GAM-Scripts): GAM lists the "
          "members, GAMGUI puts each role in its own column (this also fixes two "
          "bugs that stopped the script: it looked drives up by the wrong name, "
          "and a domain member made it fail). This is '%s'. Read-only." % SD_ROLES_NAME,
          "", _sd_roles_fields(), workflow="sdroles"),
    ]


# "Shared Drive members with groups expanded" (sdexpand, 2.87) - Ross's
# ExpandSharedDriveGroupMembers.py / GetTeamDriveACLsExpandGroups.py. GAM has
# no expansion of its own; the steps are sd_expand_steps / sd_expand_report
# further down.
SD_EXPAND_NAME = "Shared Drive members with groups expanded - CSV"
SD_EXPAND_COLUMNS = ["drive_id", "drive_name", "role", "member", "member_type",
                     "via_group", "level", "subgroup"]


def _sd_expand_fields():
    return [
        F("Only Shared Drives whose name contains (optional)", "match", False),
        F("Also keep the group's own row", "keepgroup", default="No - only the people",
          valuemap={"No - only the people": "no", "Yes - the group row too": "yes"}),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _sd_expand_tasks():
    return [
        T(SD_EXPAND_NAME,
          "Every member of every Shared Drive, with each GROUP member replaced by the "
          "people in it (groups inside groups too - 'level' and 'subgroup' show how "
          "they got there). Answers 'who can REALLY open this drive?'. Read-only.",
          "", _sd_expand_fields(), workflow="sdexpand"),
        T("Shared Drive members with groups expanded",
          "Ross Scroggs' ExpandSharedDriveGroupMembers.py and "
          "GetTeamDriveACLsExpandGroups.py (GAM-Scripts): GAM lists the drive members "
          "and the groups' members; GAMGUI puts each group's people in its place. "
          "This is '%s'. Read-only." % SD_EXPAND_NAME,
          "", _sd_expand_fields(), workflow="sdexpand"),
    ]


# "Who has access to each file - one row per file" (fileroles, 2.88) - Ross's
# GetSharedFilePermissionsTypeRoleLists.py. Steps: file_roles_steps /
# file_roles_report further down. Users and groups can have any role; a
# domain or 'anyone' only Commenter / Viewer / Editor (Ross's lists).
FILE_ROLE_NAMES = [("reader", "Viewer"), ("commenter", "Commenter"), ("writer", "Editor"),
                   ("fileOrganizer", "Content manager"), ("organizer", "Manager")]
FILE_ROLE_TYPES = [("user", "Users", None), ("group", "Groups", None),
                   ("domain", "Domains", ("reader", "commenter", "writer")),
                   ("anyone", "Anyone", ("reader", "commenter", "writer"))]
FILE_ROLES_NAME = "Who has access to each file - one row per file (CSV)"


def _file_roles_fields():
    first = lambda d: list(d)[0]
    return [
        F("Whose files", "who", default=first(FIND_WHO), valuemap=FIND_WHO),
        F("The user(s) / OU / group", "whoval", False),
        F("Also count them", "counts", default="No",
          valuemap={"No": "no", "Yes - a count column for each list": "yes"}),
        F("Between the names in a cell", "sep", default="A space", valuemap=SD_ROLES_SEP),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
        F("Speed: parallel threads (blank = config default)", "threads", False),
    ]


def _file_roles_tasks():
    return [
        T(FILE_ROLES_NAME,
          "For every file the user(s) own that is shared: the people, groups, domains "
          "and 'anyone' links that can open it, grouped by what they can do (Viewer, "
          "Commenter, Editor...) - one row per file. Read-only.",
          "", _file_roles_fields(), workflow="fileroles"),
        T("Who has access to each file (by type and role)",
          "Ross Scroggs' GetSharedFilePermissionsTypeRoleLists.py (GAM-Scripts): GAM "
          "lists each file's sharing, GAMGUI groups it by type and role. This is "
          "'%s'. Read-only." % FILE_ROLES_NAME,
          "", _file_roles_fields(), workflow="fileroles"),
    ]


# "Compare a set of users with a group" (groupcompare, 2.88) - Ross's
# CheckMembership.py, GetUsersNotInGroup.py and CheckOUGroupMembership.py.
# Steps: group_compare_steps / group_compare_report further down.
GROUP_COMPARE_NAME = "Compare users (an OU, a query...) with a group's members (CSV)"
GROUP_COMPARE_COLUMNS = ["email", "status"]


def _group_compare_fields():
    return [
        *_user_scope(),
        F("Group(s) - one email, or several comma separated", "groups"),
        F("People in groups inside the group", "nested",
          default="Count them as members (recommended)",
          valuemap={"Count them as members (recommended)": "yes",
                    "Only direct members": "no"}),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _group_compare_tasks():
    return [
        T(GROUP_COMPARE_NAME,
          "Who is in the users you pick (an OU, a query, a CSV...) but NOT in the "
          "group, and who is in the group but NOT in those users - e.g. staff missing "
          "from the staff list, or people still on it who left the OU. Read-only.",
          "", _group_compare_fields(), workflow="groupcompare"),
        T("Users not in a group / OU vs group membership",
          "Ross Scroggs' CheckMembership.py, GetUsersNotInGroup.py and "
          "CheckOUGroupMembership.py (GAM-Scripts): GAM lists both, GAMGUI compares. "
          "This is '%s'. Read-only." % GROUP_COMPARE_NAME,
          "", _group_compare_fields(), workflow="groupcompare"),
    ]


# "Users and Chromebooks per OU" (oucounts, 2.88) - Ross's GetOrgUnitUserCounts,
# GetOrgUnitCrOSCounts and GetOrgUnitUserCrOSCounts. Steps: ou_counts_steps /
# ou_counts_report further down.
OU_COUNTS_NAME = "Users and Chromebooks per OU - counts (CSV)"
OU_COUNTS_WHAT = {"Users and Chromebooks": "both", "Users only": "users",
                  "Chromebooks only": "cros"}


def _ou_counts_fields():
    return [
        F("Count", "what", default="Users and Chromebooks", valuemap=OU_COUNTS_WHAT),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _ou_counts_tasks():
    return [
        T(OU_COUNTS_NAME,
          "One row per OU (empty ones too): how many users are in it directly (and how "
          "many of them are suspended), and how many Chromebooks, split by status "
          "(ACTIVE, DISABLED, DEPROVISIONED...). Read-only.",
          "", _ou_counts_fields(), workflow="oucounts"),
        T("Users and Chromebooks per OU",
          "Ross Scroggs' GetOrgUnitUserCounts.py, GetOrgUnitCrOSCounts.py and "
          "GetOrgUnitUserCrOSCounts.py (GAM-Scripts): GAM lists the OUs, users and "
          "Chromebooks, GAMGUI counts them. This is '%s'. Read-only." % OU_COUNTS_NAME,
          "", _ou_counts_fields(), workflow="oucounts"),
    ]


# "Gmail filters that forward outside your domains" (filterforwards, 2.88) -
# Ross's GetNonDomainFilterForwards.py. A forwarding filter to an outside
# address is a classic sign of a taken-over account. Steps:
# filter_forward_steps / filter_forward_rows further down.
FILTER_FWD_NAME = "Gmail filters that forward mail outside your domains (workflow)"
FILTER_FWD_MODES = {
    "Find them (read-only report)": "find",
    "Delete the filters listed in a report (DESTRUCTIVE)": "delete",
}


def _filter_fwd_fields():
    return [
        F("What to do", "mode", default="Find them (read-only report)",
          valuemap=FILTER_FWD_MODES),
        *_user_scope(),
        F("Your own domains, comma separated (forwards to these are fine)", "own", False),
        F("Folder for the report", "folder", default="C:\\GAMExports"),
        F("Delete: the report file (Gmail-OutsideForwardFilters-...csv)", "csvfile", False,
          filepicker=True),
    ]


def _filter_fwd_tasks():
    return [
        T(FILTER_FWD_NAME,
          "Finds every Gmail filter that FORWARDS mail to an address outside your "
          "domains - a common sign of a taken-over account, or of mail leaving the "
          "district. The report lists each filter (who, what it matches, where it "
          "forwards). To remove them: delete the rows to KEEP from the report, then "
          "run this again with 'Delete the filters listed in a report' (you type "
          "DELETE first; the report stays as the record).",
          "", _filter_fwd_fields(), workflow="filterforwards", destructive=True),
        T("Gmail filters forwarding outside your domains",
          "Ross Scroggs' GetNonDomainFilterForwards.py (GAM-Scripts): GAM lists the "
          "filters, GAMGUI keeps the ones forwarding outside. This is '%s'."
          % FILTER_FWD_NAME,
          "", _filter_fwd_fields(), workflow="filterforwards", destructive=True),
    ]


# "Who sends the most mail" (mailfroms, 2.88) - Ross's CountFroms.py. GAM
# lists each matching message's From header (column 'From' - GAM source
# SMTP_HEADERS_MAP); GAMGUI counts per address. Steps: mail_froms_steps /
# mail_froms_report further down.
MAIL_FROMS_NAME = "Who sends the most mail - messages per sender (CSV)"


def _mail_froms_fields():
    return [
        *_user_scope(),
        F("Which messages (Gmail search)", "query", default="in:inbox"),
        F("Most messages to read per mailbox (blank = all that match)", "max", False,
          default="5000"),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _mail_froms_tasks():
    return [
        T(MAIL_FROMS_NAME,
          "For the mailbox(es) you pick: every sender address with how many of the "
          "matching messages came from it, most first - e.g. what is filling an "
          "inbox, or which outside sender mails the district most. Read-only.",
          "", _mail_froms_fields(), workflow="mailfroms"),
        T("Messages per sender",
          "Ross Scroggs' CountFroms.py (GAM-Scripts): GAM lists the senders, GAMGUI "
          "counts them. This is '%s'. Read-only." % MAIL_FROMS_NAME,
          "", _mail_froms_fields(), workflow="mailfroms"),
    ]


# "Duplicate files in My Drive" (dupfiles, 2.88) - Ross's DeleteDuplicateFiles.py,
# but the copies go to the TRASH (Drive keeps them 30 days; 'Put them back'
# untrashes them from the report) instead of being deleted. Steps:
# dup_files_steps / dup_files_rows further down.
DUP_FILES_NAME = "Duplicate files in My Drive - find, trash, put back (workflow)"
DUP_FILES_MODES = {
    "Find them (read-only report)": "find",
    "Move the copies listed in a report to the TRASH": "trash",
    "Put them back (untrash the files in a report)": "untrash",
}


def _dup_files_fields():
    return [
        F("What to do", "mode", default="Find them (read-only report)",
          valuemap=DUP_FILES_MODES),
        *_user_scope(),
        F("Folders too", "folders", default="No - files only",
          valuemap={"No - files only": "no", "Yes - folders as well": "yes"}),
        F("Folder for the report", "folder", default="C:\\GAMExports"),
        F("Trash / put back: the report file (MyDrive-DuplicateFiles-...csv)", "csvfile",
          False, filepicker=True),
    ]


def _dup_files_tasks():
    return [
        T(DUP_FILES_NAME,
          "Finds files that are exact copies by name, type and folder in the same "
          "person's My Drive - the newest one is kept, every older copy is listed. "
          "Then, if you want: delete the rows to KEEP from the report and move the rest "
          "to the TRASH (you type TRASH first; Drive keeps trashed files 30 days, and "
          "'Put them back' untrashes them from the same report).",
          "", _dup_files_fields(), workflow="dupfiles", destructive=True),
        T("Duplicate files (find, trash, put back)",
          "Ross Scroggs' DeleteDuplicateFiles.py (GAM-Scripts), made safer: copies go "
          "to the trash (not deleted) and can be put back. This is '%s'."
          % DUP_FILES_NAME,
          "", _dup_files_fields(), workflow="dupfiles", destructive=True),
    ]


# Two read-only Drive reports (2.88): files created per day by type (Ross's
# GetDailyMimeTypeCreations.py) and who appears on the most files (Ross's
# GetUserGroupAccessCounts.py). Steps / reports further down.
DRIVE_DAILY_NAME = "Files created per day, by type (CSV)"
DRIVE_ACCESS_NAME = "Who appears on the most files - users and groups (CSV)"


def _drive_count_fields():
    return [*_user_scope(), F("Folder for the results", "folder", default="C:\\GAMExports")]


def _drive_count_tasks():
    return [
        T(DRIVE_DAILY_NAME,
          "For the users you pick: how many files they created each day, by type (Docs, "
          "Sheets, PDFs...), newest day first. Read-only.",
          "", _drive_count_fields(), workflow="drivedaily"),
        T(DRIVE_ACCESS_NAME,
          "Across the files the users you pick own: every user and group that has "
          "access, with how many files as Owner / Editor / Commenter / Viewer - who "
          "can see the most. Read-only.",
          "", _drive_count_fields(), workflow="driveaccess"),
        T("Files created per day by type",
          "Ross Scroggs' GetDailyMimeTypeCreations.py (GAM-Scripts): GAM lists, "
          "GAMGUI counts. This is '%s'. Read-only." % DRIVE_DAILY_NAME,
          "", _drive_count_fields(), workflow="drivedaily"),
        T("User and group file access counts",
          "Ross Scroggs' GetUserGroupAccessCounts.py (GAM-Scripts): GAM lists, GAMGUI "
          "counts. This is '%s'. Read-only." % DRIVE_ACCESS_NAME,
          "", _drive_count_fields(), workflow="driveaccess"),
    ]


SD_WRITERS_NAME = "Upgrade Shared Drive Contributors to Content managers (workflow)"
SD_WRITERS_SCRIPT_NAME = "Upgrade Shared Drive writers to content managers"


def _sd_writers_task(name, desc):
    return T(name, desc, "", _sd_writers_fields(), workflow="sdwriters")


def _sd_writers_tasks():
    # [the Shared Drives task, the GAM Scripts entry] - the same workflow.
    return [
        _sd_writers_task(
            SD_WRITERS_NAME,
            "Every Contributor (can add and edit files) of every Shared Drive - or of "
            "the drives whose name contains your text - becomes a Content manager "
            "(can also move and delete files). First the Contributors are listed and "
            "saved to a record file; nothing changes until you type UPGRADE. The "
            "record file puts them back as Contributors (choose 'Put them back')."),
        _sd_writers_task(
            SD_WRITERS_SCRIPT_NAME,
            "Ross Scroggs' UpgradeWritersToContentManagers.py (GAM-Scripts) - GAM now "
            "does this itself: list the Contributors ('writers') of every Shared "
            "Drive, then change each to Content manager. This is 'Upgrade Shared "
            "Drive Contributors to Content managers'; nothing changes until you type "
            "UPGRADE, and the record file it saves puts them back."),
    ]


def _group_script_tasks():
    # 2.88: Ross's Groups scripts that GAM now does itself. Column names
    # checked with gam.exe 7.48.26 (headers only): print users groups ->
    # GroupsCount,Groups; print groups ... totalcount [internal external] ->
    # TotalCount, TotalInternalCount, TotalExternalCount. GAM's
    # csv_output_row_filter (<field>:count=N / count>N ...) keeps only the
    # rows wanted, so no Python step is needed.
    script = lambda names: " Was Ross Scroggs' %s (GAM-Scripts) - GAM does it now." % names
    return [
        T("Empty groups - no members, managers or owners (CSV/Sheet)",
          "Every group with nobody in it - candidates for clean-up." +
          script("GetEmptyGroups.py"),
          "config csv_output_row_filter TotalCount:count=0 print groups memberscount "
          "managerscount ownerscount totalcount {todrive}", [*_out()]),
        T("Groups a user owns (CSV/Sheet)",
          "Every group the person is an OWNER of - e.g. before they leave." +
          script("GetGroupsOwnedByUser.py"),
          "print groups showownedby {email} {todrive}",
          [F("User email", "email"), *_out()]),
        T("Every user with their groups - one row per user (CSV/Sheet)",
          "Each user and the groups they belong to (with a count). Optionally only the "
          "users a search finds, e.g. orgUnitPath='/Staff'." +
          script("ConvertGroupUsersToUserGroups.py"),
          "print users [query {query}] groups {todrive}",
          [F("Only users matching (optional) e.g. orgUnitPath='/Staff'", "query", False),
           *_out()]),
        T("Users who are in no group at all (CSV/Sheet)",
          "Users who belong to no group - often missed when groups give access to "
          "Drive, sites or mail lists." + script("GetUsersNoGroups.py"),
          "config csv_output_row_filter GroupsCount:count=0 print users [query {query}] "
          "groups {todrive}",
          [F("Only users matching (optional) e.g. orgUnitPath='/Staff'", "query", False),
           *_out()]),
        T("Users who are in many groups (CSV/Sheet)",
          "Users who belong to at least the number of groups you pick." +
          script("GetUsersGroupCounts.py"),
          "config csv_output_row_filter {many} print users [query {query}] groups {todrive}",
          [F("At least", "many", default="10 groups or more",
             valuemap={"5 groups or more": "GroupsCount:count>=5",
                       "10 groups or more": "GroupsCount:count>=10",
                       "20 groups or more": "GroupsCount:count>=20",
                       "50 groups or more": "GroupsCount:count>=50"}),
           F("Only users matching (optional) e.g. orgUnitPath='/Staff'", "query", False),
           *_out()]),
        T("Users' groups and the groups above them (CSV/Sheet)",
          "For each user: every group they are in AND the groups those groups are "
          "in (the whole chain up)." + script("ConvertGroupUsersToUserGroupParents.py"),
          "{userscope:usertype:userval} print grouptree {todrive}",
          [*_user_scope(), *_out()]),
        T("Group members outside your domains - one per row (CSV/Sheet)",
          "Every member, manager and owner of any group whose address is NOT in your "
          "domains." + script("GetGroupsWithExternalMembers.py"),
          "print group-members external internaldomains {own} fields email,type,role "
          "{todrive}",
          [F("Your own domains, comma separated", "own"), *_out()]),
        T("Groups with ONLY outside members (CSV/Sheet)",
          "Groups where every member, manager and owner is outside your domains - "
          "nobody of yours is in them." + script("GetGroupsWithOnlyExternalMembers.py"),
          "config csv_output_row_filter "
          "'TotalInternalCount:count=0','TotalExternalCount:count>0' print groups "
          "internal external internaldomains {own} memberscount managerscount "
          "ownerscount totalcount {todrive}",
          [F("Your own domains, comma separated", "own"), *_out()]),
        T("How many users and groups are in each group (CSV/Sheet)",
          "For every group: how many of its members are users, groups, or 'everyone "
          "in the organization'." + script("GetGroupTypeCounts.py"),
          "print groups memberscount showmembertypes {todrive}", [*_out()]),
        T("How many groups a domain has",
          "Counts the groups in one of your domains." + script("CountGroupsByDomain.py"),
          "print groups domain {domain} showitemcountonly",
          [F("Domain", "domain")]),
    ]


def _calendar_script_tasks():
    # 2.88: Ross's DeleteFutureEvents / DeleteCalendarAttendees - GAM's own
    # event selection (after <Time>, matchfield organizeremail / attendees)
    # and removeattendee do what the scripts did with CSV filtering.
    return [
        T("Delete a user's own future events (DESTRUCTIVE)",
          "Deletes the meetings a person ORGANIZED on their primary calendar from a "
          "date on (default: now) - e.g. for staff who have left, so their meetings "
          "stop appearing for everyone. Use Preview (dry run) first. Was Ross "
          "Scroggs' DeleteFutureEvents.py (GAM-Scripts) - GAM does it now.",
          "user {email} delete events primary after {start} matchfield organizeremail "
          "{email} {doit}",
          [F("User email (the organizer)", "email"),
           F("From (now, or a date like 2026-12-01)", "start", default="now")],
          destructive=True),
        T("Remove a person from future events (DESTRUCTIVE)",
          "Takes one attendee off every future event on the primary calendars in the "
          "scope (from a date on, default now) - e.g. a former employee still invited "
          "to recurring meetings. Was Ross Scroggs' DeleteCalendarAttendees.py "
          "(GAM-Scripts) - GAM does it now.",
          "{mailscope:scopetype:scopeval} update events primary after {start} "
          "matchfield attendees {attendee} removeattendee {attendee}",
          [F("Attendee to remove (email)", "attendee"),
           F("From (now, or a date like 2026-12-01)", "start", default="now"),
           F("Calendars of", "scopetype", valuemap={"All users": "all",
             "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
             "A group": "group"}),
           F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False)],
          destructive=True),
    ]


# 2.89: the school-useful scripts Gabe picked 10-14-2026 (SCRIPTS-PLAN.md).
# Steps / reports: browser_exts_*, last_group_mail_*, event_attendees_* further
# down. Each task has a main home (Chrome Browsers & Policies, Groups,
# Calendars, Classroom) and a same-job entry under Ross's script name in GAM
# Scripts (Ross Scroggs).
BROWSER_EXTS_NAME = "Chrome extensions on managed browsers - which machines have each (CSV)"
LAST_GROUP_MAIL_NAME = "Last message sent to each group - find unused groups (CSV)"
EVENT_ATTENDEES_NAME = "Calendar events - one attendee per row (CSV)"
GUARDIAN_EMAILS_NAME = "Guardians with student emails (CSV/Sheet)"
LAST_GROUP_MAIL_SOURCES = {
    "These groups (comma separated)": "list",
    "A CSV column of group emails (file:column)": "csv",
    "Every group (slow - every member of every group is checked)": "all"}


def _browser_exts_fields():
    return [
        F("Browsers in OU (blank = every managed browser)", "ou", False),
        F("Which extensions", "which", valuemap={
            "Every extension": "all",
            "Not installed by policy (users added them, or sideloaded)": "notforced",
            "Sideloaded / developer installs only": "sideload"}),
        F("Rows", "per", valuemap={"One row per extension": "extension",
                                   "One row per extension version": "version"}),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _last_group_mail_fields():
    return [
        F("Which groups", "source", valuemap=LAST_GROUP_MAIL_SOURCES),
        F("Group email(s), comma separated - or the CSV file:column", "groups", False,
          picker="group"),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _event_attendees_fields():
    return [
        *_user_scope(),
        F("Calendar (primary, or a calendar ID)", "calendar", default="primary"),
        F("From (now, or a date like 2026-09-01)", "after", default="now"),
        F("Until (blank = no end, or a date like 2027-06-01)", "before", False),
        F("Only attendees in these domains (blank = every attendee)", "domains", False),
        F("Only these attendees, comma separated (blank = every attendee)", "emails", False),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _school_script_tasks():
    # [0] Chrome extensions, [1] last group message, [2] attendees per row -
    # the main entries; [3:] the GAM Scripts entries under Ross's names.
    return [
        T(BROWSER_EXTS_NAME,
          "For Chrome browsers managed with Chrome Browser Cloud Management "
          "(Windows / Mac, not Chromebooks): every extension, how many machines "
          "have it, how it got there (forced by policy, added by the user, "
          "sideloaded), its permissions and the machine names. Pick 'Sideloaded' "
          "to find extensions installed outside the Web Store. Read-only.",
          "", _browser_exts_fields(), workflow="browserexts"),
        T(LAST_GROUP_MAIL_NAME,
          "For each group: the newest message that came through it, who sent it "
          "and how many days ago - groups nobody uses come first. Google keeps no "
          "'last post' date, so GAM looks in the members' mailboxes (newest "
          "message only): slow for big groups. Messages sent Bcc to a group are "
          "not seen. Read-only.",
          "", _last_group_mail_fields(), workflow="lastgroupmail"),
        T(EVENT_ATTENDEES_NAME,
          "Lists events on the calendars you pick with ONE ROW PER ATTENDEE "
          "(event, start, organizer, then the attendee's email, name and answer) "
          "- easy to filter in Excel. Optionally only attendees in some domains "
          "(e.g. outside guests) or some addresses. Read-only.",
          "", _event_attendees_fields(), workflow="eventattendees"),
        T("Chrome browser extension report",
          "Ross Scroggs' BrowserExtensions.py (GAM-Scripts): GAM lists the browsers, "
          "GAMGUI makes one row per extension. This is '%s'. Read-only."
          % BROWSER_EXTS_NAME, "", _browser_exts_fields(), workflow="browserexts"),
        T("Last message sent to each group",
          "Ross Scroggs' GetLastGroupEmail.py (GAM-Scripts). This is '%s'. Read-only."
          % LAST_GROUP_MAIL_NAME, "", _last_group_mail_fields(), workflow="lastgroupmail"),
        T("Events with one attendee per row",
          "Ross Scroggs' MakeOneAttendeePerRowEvents.py (GAM-Scripts). This is '%s'. "
          "Read-only." % EVENT_ATTENDEES_NAME,
          "", _event_attendees_fields(), workflow="eventattendees"),
        T(GUARDIAN_EMAILS_NAME,
          "Classroom guardians with each student's email address next to the "
          "student ID. Was Ross Scroggs' GetGuardianStudentEmails.py (GAM-Scripts) "
          "- GAM does it now (showstudentemails). Same as Classroom > List "
          "guardians.",
          "print guardians {which} showstudentemails {todrive}",
          [F("Show", "which", valuemap={
              "Accepted guardians and pending invitations": "all",
              "Accepted guardians only": "accepted",
              "Pending invitations only": "invitations"}),
           *_out()]),
    ]


# 2.89: the clean-up scripts (Gabe 10-14-2026, group 2). Steps / reports:
# old_contacts_*, vacation_html_*, sheet_protect_* further down. Each finds
# first (read-only report); changes come from that report after a typed word.
OLD_CONTACTS_NAME = "Remove old addresses from users' contacts - find, delete (workflow)"
VACATION_HTML_NAME = "Plain-text vacation replies to HTML - find, convert, put back (workflow)"
SHEET_PROTECT_NAME = "Protected ranges in Google Sheets - find, remove, put back, copy editors (workflow)"


def _old_contacts_fields():
    return [
        F("What to do", "mode", valuemap={
            "Find them (read-only report)": "find",
            "Delete the contacts listed in a report (DESTRUCTIVE)": "delete"}),
        *_user_scope(),
        F("Old addresses come from", "oldsource", valuemap={
            "Users in an OU (e.g. staff who left)": "ou",
            "A CSV column of addresses (file:column)": "csv",
            "These addresses (comma separated)": "list"}),
        F("OU path / file:column / addresses (for Find)", "oldval", False),
        F("Report file (for Delete - the Old-Contacts-...csv)", "csvfile", False,
          filepicker=True),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _vacation_html_fields():
    return [
        F("What to do", "mode", valuemap={
            "Find plain-text replies (read-only report)": "find",
            "Convert the replies listed in a report to HTML": "convert",
            "Put the original plain text back (same report)": "putback"}),
        *_user_scope(),
        F("Which replies (for Find)", "onlyon", valuemap={
            "Only replies that are switched on": "on",
            "Every saved reply, on or off": "all"}),
        F("Report file (for Convert / Put back - the Vacation-PlainText-...csv)",
          "csvfile", False, filepicker=True),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _sheet_protect_fields():
    return [
        F("What to do", "mode", valuemap={
            "Find protected ranges (read-only report)": "find",
            "Remove the ranges listed in a report (DESTRUCTIVE)": "remove",
            "Put the removed ranges back (same report)": "putback",
            "Copy protected-range editors from a Sheet to its copy": "copyeditors"}),
        F("Sheets' owner (email)", "owner", False, picker="user"),
        F("Sheet ID or link (Find: blank = every Sheet they own; Copy: the original)",
          "sheet", False),
        F("The copy's ID or link (Copy editors only)", "copy", False),
        F("Report file (for Remove / Put back - the Sheet-ProtectedRanges-...csv)",
          "csvfile", False, filepicker=True),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
    ]


def _cleanup_script_tasks():
    # [0] contacts, [1] vacation, [2] Sheets - the main entries; [3:] the GAM
    # Scripts entries under Ross's script names.
    return [
        T(OLD_CONTACTS_NAME,
          "Finds the contacts in users' own Contacts that hold an old address - "
          "e.g. staff who left, listed from their OU - as a report you check; "
          "then deletes the contacts in that report after you type DELETE. Google "
          "Contacts' 'Undo changes' can bring them back for 30 days.",
          "", _old_contacts_fields(), destructive=True, workflow="oldcontacts"),
        T(VACATION_HTML_NAME,
          "Finds vacation / auto-replies saved as plain text and turns them into "
          "HTML (line breaks kept) - subject, dates and on/off stay as they are. "
          "The report keeps each original, so 'Put back' undoes it.",
          "", _vacation_html_fields(), destructive=True, workflow="vacationhtml"),
        T(SHEET_PROTECT_NAME,
          "Lists the protected ranges (locked cells / tabs) in the Sheets a user "
          "owns, with who may edit them; removes the ones in that report after you "
          "type REMOVE (the report can put them back). Or copies who may edit "
          "each protected range from a Sheet to its copy - a copied Sheet keeps "
          "the ranges but only its owner can edit them.",
          "", _sheet_protect_fields(), destructive=True, workflow="sheetprotect"),
        T("Delete old contacts",
          "Ross Scroggs' DeleteOldContacts.py (GAM-Scripts). This is '%s'."
          % OLD_CONTACTS_NAME, "", _old_contacts_fields(), destructive=True,
          workflow="oldcontacts"),
        T("Convert vacation messages to HTML",
          "Ross Scroggs' UpdateVacationToHTML.py (GAM-Scripts). This is '%s'."
          % VACATION_HTML_NAME, "", _vacation_html_fields(), destructive=True,
          workflow="vacationhtml"),
        T("Delete / copy protected ranges in Sheets",
          "Ross Scroggs' DeleteProtectedRanges.py and ExtractProtectedRanges.py "
          "(GAM-Scripts). This is '%s'." % SHEET_PROTECT_NAME, "",
          _sheet_protect_fields(), destructive=True, workflow="sheetprotect"),
    ]


# 2.89: CSV tools (Ross's CSV helper scripts, Gabe 10-14-2026 group 3). One
# workflow, csvtools; each task carries its operation in task["csvop"]
# (gam_workflows.prepare passes the task). (op, name, Ross's script(s), what
# it does, field keys). Steps: csv_join / csv_combine ... further down.
def _csv_in(label="CSV file"):
    return F(label, "file1", filepicker=True)


_CSV_FIELDS = {
    "file1": _csv_in(),
    "col1": F("Column (as in its header row)", "col1"),
    "emailcol": F("Column holding the user email addresses", "col1", default="email"),
    "serialcol": F("Column holding the serial numbers", "col1", default="serialNumber"),
    "keycol": F("Key column - one row per value of it", "col1"),
    "valuecol": F("Values column - its values are joined", "col2"),
    "keep": F("Other columns to keep from each key's first row (comma separated)",
              "cols", False),
    "sep": F("Join the values with", "sep", valuemap={
        "Spaces (what GAM's csvkmd / ~~ lists expect)": " ", "Commas": ",",
        "Semicolons": ";"}),
    "file2": F("Second CSV file", "file2", filepicker=True),
    "col2join": F("Matching column in the second file (blank = same name)", "col2", False),
    "addcols": F("Columns to add from the second file (comma separated, blank = all)",
                 "cols", False),
    "unmatched": F("Rows of the first file with no match", "unmatched", valuemap={
        "Keep them (added columns blank)": "keep", "Leave them out": "drop"}),
    "min": F("Show values found at least this many times", "min", default="1"),
    "files": F("CSV files, separated by ; (2 or more)", "files"),
    "commoncol": F("Column to compare (the same name in every file)", "col1", default="email"),
    "jsoncol": F("JSON column", "col1", default="JSON"),
    "prefix": F("Numbered columns' name, e.g. parents for parents.0.id, parents.1.id",
                "col1"),
    "folder": F("Folder for the results", "folder", default="C:\\GAMExports"),
}
CSV_TOOLS = [
    ("join", "CSV: join two files on a column",
     "MergeUserData / AppendUserData / MergeGroupInfoMembers",
     "Adds the columns of a second CSV file to each row of the first, matching "
     "a column (e.g. email) - like VLOOKUP. A name the first file already has "
     "gets '.file2'.",
     ["file1", "col1", "file2", "col2join", "addcols", "unmatched", "folder"]),
    ("addou", "CSV: add each user's OU (by an email column)", "AddOrgUnit",
     "Adds orgUnitPath to every row of a CSV, looked up from its email column "
     "(GAM lists every user's OU first - read-only).",
     ["file1", "emailcol", "folder"]),
    ("addcrosid", "CSV: add Chromebook device IDs (by a serial number column)",
     "AddCrosIDfromSN",
     "Adds deviceId to every row of a CSV of Chromebook serial numbers (GAM "
     "lists every Chromebook's serial first - read-only), so later commands "
     "can use the ID directly - much quicker on many devices.",
     ["file1", "serialcol", "folder"]),
    ("combine", "CSV: combine rows - one row per key, values joined",
     "CSVKMD / CombineKeyValues / CombineCourseParticipants",
     "One row per value of a key column with all its values from another column "
     "joined - e.g. one row per course with all its students, ready for a "
     "bulk command.",
     ["file1", "keycol", "valuecol", "keep", "sep", "folder"]),
    ("count", "CSV: count rows per value", "CountKeyValues",
     "How many rows hold each value of a column, most first.",
     ["file1", "col1", "min", "folder"]),
    ("rows", "CSV: count rows", "CountCSVRows",
     "How many data rows a CSV file has (the header row not counted).", ["file1"]),
    ("dedupe", "CSV: remove duplicate rows (by a column)", "DeleteDuplicateRows",
     "Keeps the first row for each value of a column and leaves out the rest.",
     ["file1", "col1", "folder"]),
    ("common", "CSV: values found in every file (e.g. emails)", "FindCommonEmails",
     "The values of a column that appear in ALL the files - e.g. users found "
     "in several report CSVs.",
     ["files", "commoncol", "folder"]),
    ("json", "CSV: JSON column to a .json file", "ConvertCSVtoJSON",
     "Writes the JSON column of a CSV made with formatjson as one .json file "
     "(a list of the objects).",
     ["file1", "jsoncol", "folder"]),
    ("explode", "CSV: one row per numbered item (e.g. parents.0, parents.1)",
     "MakeOneParentPerRow",
     "Turns numbered columns (parents.0.id, parents.1.id...) into one row per "
     "item with a single parents.id column.",
     ["file1", "prefix", "folder"]),
]


def _csv_tool_tasks(ross=False):
    tasks = []
    for op, name, scripts, desc, keys in CSV_TOOLS:
        if ross:
            name = "%s (%s)" % (name.replace("CSV: ", "CSV - "), scripts)
            # Every GAM Scripts entry names Ross's original .py (test_v287).
            files = " / ".join(s.strip() + ".py" for s in scripts.split("/"))
            desc = ("Ross Scroggs' %s (GAM-Scripts), done by GAMGUI. %s" % (files, desc))
        if op != "rows":
            desc += " Writes a new file; the input files are not changed."
        t = T(name, desc, "", [dict(_CSV_FIELDS[k]) for k in keys], workflow="csvtools")
        t["csvop"] = op
        tasks.append(t)
    return tasks


# 2.89: three asks from the GAM group (10-2026), all GAM's own commands.
#   Delete many Gmail labels - 'delete labels regex:<pattern>|--ALL_LABELS--'
#     (wiki Users-Gmail-Labels); the messages stay, only the labels go.
#   Files 'Shared with me' - Ross, thread tunnoU637s4: print filelist choose
#     sharedwithme fields id,name,mimetype,owners.emailaddress filepath.
#   Empty a Shared Drive - wiki Users-Drive-Cleanup "Delete contents of a
#     Shared Drive", but the top-level items go to the Shared Drive's TRASH
#     (30 days, put back from the record) instead of purge. Steps:
#     sd_empty_steps further down; workflow sdempty.
SD_EMPTY_NAME = "Empty a Shared Drive - move everything to its trash, put back (workflow)"
SHARED_WITH_ME_NAME = "Files in a user's 'Shared with me' - owner and path (CSV/Sheet)"


def _label_cleanup_tasks():
    return [
        T("Delete labels whose name matches a pattern (DESTRUCTIVE)",
          "Deletes every label of the mailbox whose name matches a regular "
          "expression - e.g. ^Old/ for 'Old' and everything under it. The "
          "messages are NOT deleted; they just lose that label. Use Show labels "
          "first to see what matches.",
          "user {email} delete labels regex:{pattern}",
          [F("Mailbox", "email"),
           F("Label names matching (regular expression, e.g. ^Old/)", "pattern")],
          destructive=True),
        T("Delete ALL of a user's labels (DESTRUCTIVE)",
          "Deletes every label the user made (Inbox, Sent and the other system "
          "labels stay). The messages are NOT deleted; they just lose their "
          "labels.",
          "user {email} delete labels --ALL_LABELS--",
          [F("Mailbox", "email")], destructive=True),
    ]


def _shared_with_me_task():
    return T(SHARED_WITH_ME_NAME,
             "For the users you pick: every file and folder in their 'Shared with "
             "me' - name, type, the owner (owners.0.emailAddress - the Owner "
             "column is just the user listed) and the folder path. Read-only.",
             "{userscope:usertype:userval} print filelist choose sharedwithme fields "
             "id,name,mimetype,owners.emailaddress filepath {todrive}",
             [*_user_scope(), *_out()])


def _sd_empty_fields():
    return [
        F("What to do", "mode", valuemap={
            "Move everything to the Shared Drive's trash (you type EMPTY first)": "empty",
            "Put back what was moved (from the record file)": "putback"}),
        F("A manager of the Shared Drive (email)", "manager", False, picker="user"),
        F("Shared Drive ID (Pick... fills it in)", "driveid", False, picker="shareddrive"),
        F("Folder for the record files", "folder", default="C:\\GAMExports"),
        F("Put back: the record file (SharedDrive-Emptied-...csv)", "csvfile", False,
          filepicker=True),
    ]


def _sd_empty_tasks():
    return [
        T(SD_EMPTY_NAME,
          "Empties a Shared Drive without deleting it: first saves a list of "
          "EVERYTHING in it (a record), then - after you type EMPTY - moves its "
          "top-level files and folders to the Shared Drive's trash, where they "
          "stay 30 days. 'Put back' with the record brings them back. Run it as "
          "one of the drive's managers.",
          "", _sd_empty_fields(), destructive=True, workflow="sdempty"),
    ]


# 2.89: Compromised Account - the GAM-able steps of MOREnet's "Detailed Tips
# for Investigating a Google Account Compromise" (Gabe 10-15-2026). Steps /
# reports: ip_trace_*, link_clicks_*, lock_many_* further down.
IP_TRACE_NAME = "Trace an IP address - every account it touched, in every log (CSV)"
LINK_CLICKS_NAME = "Who clicked a phishing link (Gmail log) - CSV"
LOCK_MANY_NAME = "Lock out several compromised accounts at once (DESTRUCTIVE)"
SUSPICIOUS_SIGNINS_NAME = "Suspicious sign-ins - whole domain (CSV/Sheet)"
TAKEOUT_ALL_NAME = "Google Takeout exports - whole domain (CSV/Sheet)"
FOREIGN_SIGNINS_NAME = "Sign-ins from outside your countries - whole domain (CSV)"
# 2.98: workflow adminreview (steps / report: admin_review_* further down).
ADMIN_REVIEW_NAME = ("Admin role review - every role, 2-Step Verification, suspended, "
                     "last sign-in (CSV)")
ACCOUNT_CHANGES_ALL_NAME = "Password, recovery and 2SV changes - whole domain (CSV/Sheet)"
# Not DESTRUCTIVE - like 'Sign out user': nothing is lost, people sign in
# again (test_completion270: a typed 'signout' is not classed destructive).
SIGNOUT_MANY_NAME = "Sign out many users at once (revoke sessions)"


# 2.90 (Gabe 10-15-2026): Public Information Requests - spec
# docs/2026-10-15-public-information-requests-design.md. One Vault matter per
# request; a saved search (+ optional hold) and an export per chosen service.
# The description marker is how 'List requests' tells these matters apart
# from other legal matters.
PIR_CATEGORY = "Public Information Requests"
PIR_MARKER = "Public Information Request (GAMGUI)"
# (Vault corpus, the name people know). Voice is left out on purpose (spec 10).
PIR_SERVICES = [("mail", "Gmail"), ("drive", "Drive"), ("hangouts_chat", "Chat"),
                ("calendar", "Calendar"), ("groups", "Groups"), ("gemini", "Gemini")]
PIR_DEFAULT_ON = {"mail", "drive", "hangouts_chat"}
PIR_START_NAME = "Start a request - search and export (workflow)"
PIR_CHECK_NAME = "Check a request and download its exports (workflow)"
PIR_CLOSE_NAME = "Close a request - remove its holds, close the matter (DESTRUCTIVE)"
PIR_LIST_NAME = "List requests (CSV)"
PIR_AFTER_WAIT = "Wait here and download them (checks every minute)"
PIR_AFTER_LATER = "Stop - I will download them later with 'Check a request'"


def _pir_service_field(code, label):
    # One Include / Leave out dropdown per service (no bare on/off choices).
    on, off = "Include - search " + label, "Leave out"
    return F(label, "svc_" + code, default=on if code in PIR_DEFAULT_ON else off,
             valuemap={on: "yes", off: "no"})


def _pir_record_field():
    # Check / Close find the request by its record file, or by the matter.
    return F("The request's record (request.json) - or leave blank and give the matter",
             "record", False, filepicker=True)


def _pir_tasks():
    folder = F("Folder for requests (each request gets its own folder)", "folder",
               default="C:\\GAMExports\\Public Information Requests")
    return [
        T(PIR_START_NAME,
          "For a Public Information Request: creates ONE Vault matter, a saved search "
          "for each service you include (same people, words and dates), an optional "
          "hold, counts for Gmail and Groups, and an export per service - then saves a "
          "record of it all (request.json and Request summary.txt) in the request's "
          "folder. Google builds exports in minutes to hours: by default GAMGUI waits "
          "and downloads them into the request's folder (Stop is safe - 'Check a "
          "request' finishes later). Exports hold other people's mail and files - keep "
          "the folder somewhere only the right people can open.",
          "", [F("Request number or name (e.g. PIR 2026-0147)", "request"),
               F("Requestor (optional - added to the matter's name, which Vault users see)",
                 "requestor", False),
               *[_pir_service_field(code, label) for code, label in PIR_SERVICES],
               F("Whose data", "scopetype", valuemap={
                   "These people (emails, comma separated)": "people",
                   "People in a CSV column (file:column)": "csv",
                   "A group's members": "group",
                   "An OU (and its sub-OUs)": "ou",
                   "Everyone in the domain (very large)": "everyone"}),
               F("Emails / file:column / group / OU path (blank only for Everyone)",
                 "scopeval", False),
               F("Groups to search (group addresses - Groups only)", "groups", False),
               F("Search words (blank = everything in the dates)", "terms", False),
               F("From date (YYYY-MM-DD, optional)", "start", False),
               F("To date (YYYY-MM-DD, optional, included)", "end", False),
               F("Gmail only: From (optional)", "gfrom", False),
               F("Gmail only: To (optional)", "gto", False),
               F("Gmail only: Subject words (optional)", "gsubject", False),
               F("Also place a hold (preserve the data while the request is open)",
                 "hold", default="No", valuemap={"No": "no",
                                                 "Yes - add a hold per service": "yes"}),
               F("Gmail export format", "format", default="MBOX",
                 valuemap={"MBOX": "mbox", "PST (Outlook)": "pst"}),
               F("Collaborators - share the matter with (emails, optional)",
                 "collaborators", False),
               # 2.91 (Gabe's first real request): Start used to stop after
               # making the exports; downloading them was a separate task.
               F("When the exports are made", "after", default=PIR_AFTER_WAIT,
                 valuemap={PIR_AFTER_WAIT: "wait", PIR_AFTER_LATER: "later"}),
               folder],
          workflow="pirstart"),
        T(PIR_CHECK_NAME,
          "Shows each export's status (done / still building / failed, and the days "
          "left before Vault deletes it - 15 days after it was made) and downloads every "
          "finished export not downloaded yet into the request's folder, one folder per "
          "service. Run it again later for the rest. 'Finish the request' makes "
          "whatever a stopped Start did not (saved searches, holds, exports), redoes "
          "failed exports, then waits and downloads them like Start does. 'Package "
          "the request' makes ONE .zip to hand over - every downloaded file, Request "
          "summary.txt and Files.csv (not request.json) - with its SHA-256 beside it.",
          "", [_pir_record_field(),
               F("Or the matter's name or ID (when there is no record)", "matter", False),
               F("What to do", "mode", default="Check and download",
                 valuemap={"Check and download": "check",
                           "Finish the request - make what is missing, redo failed exports":
                               "retry",
                           "Package the request for hand-over (one .zip with its checksum)":
                               "package"}),
               folder],
          workflow="pircheck"),
        T(PIR_CLOSE_NAME,
          "After you type CLOSE: removes the request's holds and closes its Vault "
          "matter. Downloaded files, the record and the matter stay (a closed matter "
          "can be reopened in Vault).",
          "", [_pir_record_field(),
               F("Or the matter's name or ID (when there is no record)", "matter", False),
               folder],
          destructive=True, workflow="pirclose"),
        T(PIR_LIST_NAME,
          "Every Public Information Request matter GAMGUI started (found by its "
          "description), open or closed, with its matter ID and collaborators. "
          "Read-only.",
          "", [F("Folder for the results", "folder", default="C:\\GAMExports")],
          workflow="pirlist"),
    ]


# Characters Windows does not allow in a folder name (the request name
# becomes the request's folder).
_PIR_FOLDER_BAD = re.compile(r'[<>:"/\\|?*]')
# Names Windows keeps for devices; a folder cannot be called that.
_PIR_RESERVED = re.compile(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])")


def _pir_emails(text, what):
    # "a@x.org, B@x.org" -> ["a@x.org", "b@x.org"]; anything that is not an
    # email address is refused by name so the admin can fix that one entry.
    items = [a.strip().lower() for a in re.split(r"[,;\s]+", text or "") if a.strip()]
    bad = [a for a in items if not _PLAIN_EMAIL.fullmatch(a)]
    if bad:
        raise ValueError("Not an email address (%s): %s" % (what, ", ".join(bad)))
    return items


def _pir_day(text, what, tz, next_day=False):
    # A LOCAL date -> Vault's UTC timestamp ("" when blank = no limit).
    # next_day=True moves to the next day's 00:00 so the To date is
    # included whole. rule "any": a request looks at past dates.
    text = (text or "").strip()
    if not text:
        return ""
    day = _parse_local_date(text)
    if day is None:
        raise ValueError("%s not recognized - use YYYY-MM-DD (e.g. 2026-09-01)." % what)
    if next_day:
        day = day + _dt.timedelta(days=1)
    stamp, err = local_to_zulu(day.strftime("%Y-%m-%d"), "", rule="any", tz=tz)
    if err:
        raise ValueError("%s: %s" % (what, err))
    return stamp


# Review I8: every address goes into ONE GAM argument (search and hold), and a
# Windows command line holds 32,767 characters in all. Well under that.
PIR_MAX_ACCOUNT_CHARS = 20000


def pir_accounts_too_long(emails):
    # "" when the list fits in one search; else what to do instead.
    size = len(",".join(emails))
    if size <= PIR_MAX_ACCOUNT_CHARS:
        return ""
    return ("%d people is too many for one search (%d characters; the most is %d). "
            "Search their OU instead (Whose data: An OU), or split the request."
            % (len(emails), size, PIR_MAX_ACCOUNT_CHARS))


def _pir_gmail_people(text, op):
    # A Gmail From / To box -> one search term (review I7). Comma-separated
    # entries become (a OR b); an entry with a space (a person's name) is
    # put in double quotes, so 'John Smith' does not become 'from:John'
    # plus a loose word. Quotes the admin typed are dropped first.
    items = [" ".join(i.replace('"', " ").split()) for i in (text or "").split(",")]
    items = ['"%s"' % i if " " in i else i for i in items if i]
    if not items:
        return ""
    return op + (items[0] if len(items) == 1 else "(%s)" % " OR ".join(items))


def pir_criteria(values, tz=None):
    # The Start form -> one checked set of criteria shared by every service
    # (spec section 4). Raises ValueError in plain words. tz: the browser's
    # IANA zone (None = this computer's zone).
    import os
    request = (values.get("request") or "").strip()
    if not request:
        raise ValueError("Enter the request number or name (e.g. PIR 2026-0147).")
    # M4 (10-16-2026): also no control characters (a pasted tab) and no
    # name Windows reserves for devices (CON, NUL, COM1... - with or
    # without an extension).
    if (_PIR_FOLDER_BAD.search(request) or request.endswith(".") or len(request) > 80
            or any(ord(ch) < 32 for ch in request)
            or _PIR_RESERVED.fullmatch(request.split(".")[0].strip())):
        raise ValueError("The request name becomes a folder name - leave out < > : \" / "
                         "\\ | ? * and tabs, do not use a Windows device name (CON, NUL, "
                         "COM1...), and keep it under 80 characters.")
    services = [code for code, _l in PIR_SERVICES if (values.get("svc_" + code) or "") == "yes"]
    if not services:
        raise ValueError("Include at least one service (Gmail, Drive, Chat...).")
    # Whose data: the value box means something different for each type.
    stype = (values.get("scopetype") or "people").strip()
    sval = (values.get("scopeval") or "").strip()
    scope = {"type": stype, "value": sval, "emails": []}
    if stype == "people":
        scope["emails"] = _pir_emails(sval, "whose data")
        if not scope["emails"]:
            raise ValueError("Enter the people's email addresses, comma separated.")
    elif stype == "csv":
        _csv_file_column(sval)                     # checked again (and read) in prepare
    elif stype == "group":
        if not _PLAIN_EMAIL.fullmatch(sval.lower()):
            raise ValueError("Enter the group's email address.")
        scope["value"] = sval.lower()
    elif stype == "ou":
        if not sval.startswith("/"):
            raise ValueError("Enter the OU path, e.g. /Staff.")
    elif stype != "everyone":
        raise ValueError("Choose whose data to search.")
    # Groups searches group archives, so it needs group addresses.
    groups = _pir_emails(values.get("groups"), "groups to search")
    if "groups" in services and not groups:
        raise ValueError("Groups is included - enter the group addresses to search.")
    # One set of words for every service; Gmail also gets From / To / Subject.
    terms = " ".join((values.get("terms") or "").split())
    extras = []
    for key, op in (("gfrom", "from:"), ("gto", "to:")):
        part = _pir_gmail_people(values.get(key), op)
        if part:
            extras.append(part)
    if (values.get("gsubject") or "").strip():
        extras.append("subject:(%s)" % " ".join(values["gsubject"].split()))
    start = _pir_day(values.get("start"), "From date", tz)
    end = _pir_day(values.get("end"), "To date", tz, next_day=True)
    if start and end and start >= end:
        raise ValueError("The From date is after the To date.")
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose the folder for requests.")
    # M3: absolute, because GAM resolves a relative path against its own
    # folder (drive_dir) while GAMGUI would read it from its own.
    folder = os.path.abspath(folder)
    return {"request": request,
            "requestor": " ".join((values.get("requestor") or "").split())[:100],
            "services": services, "scope": scope, "groups": groups, "terms": terms,
            "mail_terms": " ".join([terms] + extras).strip(), "start": start, "end": end,
            "hold": (values.get("hold") or "no") == "yes",
            "format": (values.get("format") or "mbox"),
            "collaborators": _pir_emails(values.get("collaborators"), "collaborators"),
            "folder": folder, "request_folder": os.path.join(folder, request),
            # M7: the dates as the admin typed them and the zone they mean,
            # for the record (start / end above are Vault's UTC times).
            "start_typed": (values.get("start") or "").strip(),
            "end_typed": (values.get("end") or "").strip(), "tz": tz or ""}


# --- PIR: the GAM commands (GAM 7.48.26 forms; spec section 2) --------------
# GAM reads a bare matter / saved search / hold / export ID as a NAME and
# looks the name up (UID_PATTERN 'u?id: ?(.+)' in GAM's source); only
# 'id:<ID>' is taken as an ID (the same rule as the 2.83 "name or ID"
# boxes - see ID_FORMS). Confirmed again by the 10-15-2026 parse check.


def _pir_id(value):
    # An ID GAMGUI stored -> 'id:<ID>' (left alone if it already has one).
    value = (value or "").strip()
    return value if re.match(r"(?i)u?id:", value) else "id:" + value


def pir_matter_ref(text):
    # A matter the admin TYPED: a Vault matter ID (a UUID) gets 'id:'; any
    # other text is a matter name, which GAM looks up itself.
    text = (text or "").strip()
    return _pir_id(text) if ID_FORMS["uuid"].fullmatch(text) else text


def pir_label(code):
    # Vault corpus -> the name people know ("mail" -> "Gmail").
    return dict(PIR_SERVICES).get(code, code)


def pir_matter_name(cr):
    # "<request> - <requestor>", or just the request when no requestor.
    return cr["request"] + (" - " + cr["requestor"] if cr["requestor"] else "")


def pir_matter_argv(cr, today):
    # The matter; the description carries the marker 'List requests' finds.
    # sendemails false: collaborators are added without a Google email.
    argv = ["create", "vaultmatter", "name", pir_matter_name(cr), "description",
            "%s. Started %s." % (PIR_MARKER, today)]
    if cr["collaborators"]:
        argv += ["collaborators", ",".join(cr["collaborators"]), "sendemails", "false"]
    return argv + ["returnidonly"]


def pir_scope_argv(cr, code, emails):
    # Whose data, in Vault's words. Groups always searches the group
    # addresses; everyone else follows the form's 'Whose data'.
    if code == "groups":
        return ["accounts", ",".join(cr["groups"])]
    if cr["scope"]["type"] == "ou":
        return ["orgunit", cr["scope"]["value"]]
    if cr["scope"]["type"] == "everyone":
        return ["everyone"]
    return ["accounts", ",".join(emails)]


def _pir_when(cr):
    # The date range (either end may be open).
    return (["start", cr["start"]] if cr["start"] else []) + (["end", cr["end"]] if cr["end"] else [])


def pir_query_argv(cr, code, matter_id, emails):
    # One saved search per service. Gmail's words include From/To/Subject;
    # Drive also searches Shared Drives; Chat also searches spaces (rooms).
    words = cr["mail_terms"] if code == "mail" else cr["terms"]
    argv = (["create", "vaultquery", _pir_id(matter_id), "name",
             "%s - %s" % (cr["request"], pir_label(code)), "corpus", code]
            + pir_scope_argv(cr, code, emails) + (["terms", words] if words else [])
            + _pir_when(cr))
    if code == "drive":
        argv += ["includeshareddrives", "true"]
    if code == "hangouts_chat":
        argv += ["includerooms", "true"]
    return argv + ["returnidonly"]


def pir_hold_argv(cr, code, matter_id, emails):
    # One hold per service. Vault holds have no 'everyone' (orgunit / is the
    # whole domain) and only Gmail / Groups holds take words and dates.
    scope = pir_scope_argv(cr, code, emails)
    if scope == ["everyone"]:
        scope = ["orgunit", "/"]
    argv = (["create", "vaulthold", "matter", _pir_id(matter_id), "name",
             "%s - %s hold" % (cr["request"], pir_label(code)), "corpus", code] + scope)
    if code in ("mail", "groups"):
        words = cr["mail_terms"] if code == "mail" else cr["terms"]
        argv += (["terms", words] if words else []) + _pir_when(cr)
    if code == "drive":
        argv += ["includeshareddrives", "true"]
    if code == "hangouts_chat":
        argv += ["includerooms", "true"]
    return argv + ["returnidonly"]


def pir_count_argv(path, matter_id, query_id):
    # How many messages a Gmail / Groups saved search finds (CSV: account,count).
    # GAM's form is 'matter <M> vaultquery <Q>' (the keyword is required).
    return _redirect(path) + ["print", "vaultcounts", "matter", _pir_id(matter_id),
                              "vaultquery", _pir_id(query_id)]


def pir_export_argv(cr, code, matter_id, query_id, attempt=1):
    # An export from a saved search; only Gmail takes the MBOX / PST choice.
    # A redo gets its own name ('... (retry 2)'): Vault export names are
    # unique in a matter (GAM lists ALREADY_EXISTS for exports.create).
    name = "%s - %s" % (cr["request"], pir_label(code))
    if attempt > 1:
        name += " (retry %d)" % attempt
    return (["create", "vaultexport", "matter", _pir_id(matter_id), "name",
             name, "vaultquery", _pir_id(query_id)]
            + (["format", cr["format"]] if code == "mail" else []) + ["returnidonly"])


def pir_exports_argv(path, matter_id):
    # Every export in the matter with its status and size (read-only).
    return _redirect(path) + ["print", "vaultexports", "matters", _pir_id(matter_id), "fields",
                              "id,name,status,createtime,stats"]


def pir_download_argv(export_id, matter_id, folder):
    # GAM downloads the export's files and checks their checksums.
    return ["download", "vaultexport", _pir_id(export_id), "matter", _pir_id(matter_id),
            "targetfolder", folder]


def pir_matters_argv(path, people=False):
    # Every Vault matter (read-only) - for the duplicate check, the lookup
    # by name and the list. people=True (List only) adds each matter's
    # people, which costs GAM one lookup per person per matter.
    return _redirect(path) + ["print", "vaultmatters", "fields",
                              "matterid,name,description,state"
                              + (",matterpermissions" if people else "")]


def pir_holds_argv(path, matter_id):
    # The matter's holds (Close without a record).
    return _redirect(path) + ["print", "vaultholds", "matters", _pir_id(matter_id)]


def pir_delete_hold_argv(hold_id, matter_id):
    return ["delete", "vaulthold", _pir_id(hold_id), "matter", _pir_id(matter_id)]


def pir_close_argv(matter_id):
    return ["close", "vaultmatter", _pir_id(matter_id)]


def pir_group_members_argv(path, group):
    # The group's USER members, nested groups included.
    return _redirect(path) + ["print", "group-members", "group", group, "recursive",
                              "types", "user", "fields", "email"]


def pir_id_from(output):
    # 'returnidonly' prints just the new ID on its own line; anything else
    # (an ERROR line) gives "". The FIRST such line counts: 'create
    # vaultmatter' prints the ID and THEN may warn about a collaborator it
    # could not add (exit 50) - the matter exists all the same.
    for line in (output or "").splitlines():
        if re.fullmatch(r"[A-Za-z0-9_\-]{6,}", line.strip()):
            return line.strip()
    return ""


def pir_admin_from(output):
    # GAM 'oauth info' names the admin it signs in as on this line (checked
    # against gam.exe 7.48.26, 10-15-2026). For the request record only.
    match = re.search(r"^Google Workspace Admin:\s*(\S+@\S+)\s*$", output or "", re.M)
    return match.group(1).lower() if match else ""


# --- PIR: the request record (request.json + Request summary.txt) -----------
def pir_record_new(cr, now_text, admin):
    # Everything Check / Close need, filled in step by step by Start.
    return {"marker": PIR_MARKER, "request": cr["request"], "requestor": cr["requestor"],
            "created": now_text, "admin": admin, "criteria": cr, "matter": {"id": "", "name": ""},
            "services": {code: {"label": pir_label(code), "query": "", "hold": "", "export": "",
                                "count": "", "status": "", "downloaded": [], "error": ""}
                         for code in cr["services"]},
            "steps": [], "closed": ""}


def pir_record_save(path, rec):
    # Written to a .tmp file first, then swapped in, so a crash mid-write
    # never leaves a half-written record.
    import json, os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(rec, handle, indent=2, ensure_ascii=True)
    os.replace(tmp, path)


def pir_record_load(path):
    # Refuses any JSON that is not a GAMGUI request record.
    import json
    try:
        with open(path, encoding="utf-8") as handle:
            rec = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot read the request record %s: %s" % (path, exc))
    if not isinstance(rec, dict) or rec.get("marker") != PIR_MARKER or not rec.get("matter"):
        raise ValueError("%s is not a GAMGUI request record (request.json)." % path)
    return rec


def pir_summary_text(rec):
    # The record in plain English, ASCII only (Request summary.txt).
    cr = rec.get("criteria") or {}
    scope = cr.get("scope") or {}
    who = {"people": ", ".join(scope.get("emails") or []),
           "csv": "a CSV column: %s (%d people)" % (scope.get("value", ""),
                                                    len(scope.get("emails") or [])),
           "group": "members of " + scope.get("value", ""), "ou": "OU " + scope.get("value", ""),
           "everyone": "everyone in the domain"}.get(scope.get("type"), "(not recorded)")
    lines = ["PUBLIC INFORMATION REQUEST - " + rec["request"],
             "=" * 60,
             "Requestor:    " + (rec.get("requestor") or "(not given)"),
             "Started:      %s by %s" % (rec.get("created", ""), rec.get("admin") or "?"),
             "Vault matter: %s (%s)" % (rec["matter"].get("name", ""),
                                        rec["matter"].get("id") or "not created"),
             "Whose data:   " + who,
             "Search words: " + (cr.get("terms") or "(none - everything)"),
             "Gmail search: " + (cr.get("mail_terms") or "(none - everything)"),
             "Dates:        %s to %s (%s; the To date included)" % (
                 cr.get("start_typed") or "(no start)", cr.get("end_typed") or "(no end)",
                 cr.get("tz") or "this computer's time zone"),
             "Dates (UTC):  %s to %s (what Vault was given)" % (
                 cr.get("start") or "(no start)", cr.get("end") or "(no end)"),
             "Hold:         " + ("yes" if cr.get("hold") else "no"), "", "SERVICES"]
    for _code, s in rec["services"].items():
        lines.append("  %-9s search %s  hold %s  export %s  count %s  status %s%s" % (
            s["label"], s["query"] or "-", s["hold"] or "-", s["export"] or "-",
            s["count"] if s["count"] != "" else "-", s["status"] or "-",
            ("  ERROR: " + s["error"]) if s["error"] else ""))
        for f in s["downloaded"]:
            lines.append("            downloaded %s (%s bytes) %s" % (f["file"], f["bytes"], f["when"]))
    if any(s["downloaded"] for s in rec["services"].values()):
        lines += ["", "Files.csv (in this folder) lists every downloaded file with its size and",
                  "the SHA-256 checksum taken when it was downloaded."]
    lines += ["", "STEPS"] + ["  " + s for s in rec["steps"]]
    if rec.get("closed"):
        lines.append("CLOSED: " + rec["closed"])
    return "\n".join(lines).encode("ascii", "replace").decode("ascii") + "\n"


def _compromise_more_tasks():
    days = F("Days to look back (1-180; the Gmail log keeps 30)", "days", default="30")
    return [
        T(IP_TRACE_NAME,
          "For one or more IP addresses (e.g. the odd ones in a compromised "
          "account's SignInIPs.csv): every account that address signed in to, "
          "and what it did - sign-ins, SSO sign-ins to other systems, Takeout "
          "exports, Drive and Gmail activity, app authorizations, account "
          "changes and Admin console actions. One CSV per log plus a list of "
          "the accounts it touched. Read-only.",
          "", [F("IP address(es), comma separated (up to 5)", "ips"), days,
               F("Folder for the results", "folder", default="C:\\GAMExports")],
          workflow="iptrace"),
        T(LINK_CLICKS_NAME,
          "Everyone who clicked a link in a phishing email (Gmail log: 'link in "
          "message body clicked' and 'link in an attachment preview clicked'), "
          "found by the email's subject words or its Message-ID. For each click: "
          "who, when, from which IP address. Anyone listed should be locked out "
          "and change their password. Read-only.",
          "", [F("Subject words (any part of the subject)", "subject", False),
               F("Message-ID (exact - better than the subject)", "msgid", False),
               F("Days to look back (1-30)", "days", default="7"),
               F("Folder for the results", "folder", default="C:\\GAMExports")],
          workflow="linkclicks"),
        T(SUSPICIOUS_SIGNINS_NAME,
          "Every sign-in Google flagged as suspicious, for the whole domain, with "
          "the account, time, IP address and country. Read-only.",
          "report login user all filter is_suspicious==true start -{days}d {todrive}",
          [F("Days to look back", "days", default="7"), *_out()]),
        T(FOREIGN_SIGNINS_NAME,
          "Every successful sign-in from a country other than yours (e.g. US) "
          "in the last few days, for every account - with the IP address, "
          "country and whether Google flagged it - plus one row per account. "
          "A classic sign of a taken-over account. Read-only (on a big domain "
          "the sign-in log is large; keep the days small).",
          "", [F("Your countries - two-letter codes, comma separated", "countries",
                 default="US", remember="signin_countries"),
               F("Days to look back (1-30)", "days", default="3"),
               F("Folder for the results", "folder", default="C:\\GAMExports")],
          workflow="foreignsignins"),
        # 2.90: the article's 'Did they use Takeout?' and account-change
        # checks, for everyone at once.
        T(TAKEOUT_ALL_NAME,
          "Every Google Takeout (download all my data) event in the domain - a "
          "compromised account mass-exporting mail and files shows up here. "
          "Read-only.",
          "report takeout user all start -{days}d {todrive}",
          [F("Days to look back", "days", default="30"), *_out()]),
        T(ACCOUNT_CHANGES_ALL_NAME,
          "Every password, recovery email / phone and 2-Step Verification change "
          "in the domain (the user accounts log) - attackers change these to keep "
          "the account. Read-only.",
          "report useraccounts user all start -{days}d {todrive}",
          [F("Days to look back", "days", default="7"), *_out()]),
        T(LOCK_MANY_NAME,
          "For several accounts at once (a CSV of the people who clicked, a group, "
          "an OU...): saves a record of them, then - after you type LOCK - blocks "
          "sign-in with a password nobody can type and signs them out everywhere; "
          "optionally suspends them too. Give each a new password later (Users > "
          "Reset password).",
          "", [*_user_scope(),
               F("Also suspend them", "suspend", valuemap={
                   "No - lock them out, mail still arrives": "no",
                   "Yes - also suspend (stops new mail too)": "yes"}),
               F("Folder for the record", "folder", default="C:\\GAMExports")],
          destructive=True, workflow="lockmany"),
        T(SIGNOUT_MANY_NAME,
          "Signs the chosen users out of every web and device session (resets "
          "their sign-in cookies) - e.g. after shortening the session length, or "
          "for everyone who clicked a phishing link. They sign in again with "
          "their password.",
          "{userscope:usertype:userval} signout",
          [*_user_scope()]),
    ]


def _share_count_task():
    # 2.88: Ross's GetUserShareCounts / GetExternalShareCounts - GAM's print
    # filesharecounts with internaldomains splits inside / outside itself.
    return T("Sharing counts per user - inside vs outside your domains (CSV/Sheet)",
             "For the users you pick: how many of their files are shared, and how - "
             "with people and groups inside your domains, outside them, a whole "
             "domain, or anyone with the link. Optionally a total row. Was Ross "
             "Scroggs' GetUserShareCounts.py and GetExternalShareCounts.py "
             "(GAM-Scripts) - GAM does it now.",
             "{userscope:usertype:userval} print filesharecounts internaldomains {own} "
             "[summary {summary}] {todrive}",
             [*_user_scope(),
              F("Your own domains, comma separated", "own"),
              F("Totals", "summary", False, default="One row per user",
                valuemap={"One row per user": "", "Per user, plus a total row": "plus",
                          "Only the total row": "only"}),
              *_out()])


def _license_holder_task():
    # 2.88: Ross's GetLicenseHolders - GAM's <users> print users licenses.
    return T("Licenses held by a set of users (CSV/Sheet)",
             "For the users you pick (an OU, a group, a query...): which Google "
             "licenses each one holds - one license per row, so a CSV of it can feed a "
             "bulk license change. Was Ross Scroggs' GetLicenseHolders.py (GAM-Scripts) "
             "- GAM does it now.",
             "{userscope:usertype:userval} print users licenses onelicenseperrow {todrive}",
             [*_user_scope(), *_out()])


def _gam_script_finds():
    return [T(name,
              "Ross Scroggs' %s (GAM-Scripts) - GAM now does this itself with "
              "permission matching, so no Python is needed. This is Find sharing, "
              "already set up for it (change any box). Read-only; the report feeds "
              "'Remove outside sharing listed in a report'." % scripts,
              "", _find_fields(where, what, who), workflow="findsharing")
            for name, where, what, who, scripts in GAM_SCRIPT_FINDS]


SD_EACH = {
    "counts": ("File counts and storage used (size, as in the Admin console)",
               ["print", "filecounts", "select", "shareddriveid", "~id", "showsize",
                "showsizeunits"]),
    "lastmod": ("The most recently changed file",
                ["print", "drivelastmodification", "select", "shareddriveid", "~id"]),
    "files": ("Every file, with its folder path",
              ["print", "filelist", "select", "shareddriveid", "~id", "fields",
               "id,name,mimetype,size,modifiedtime", "filepath"]),
}
SD_EACH_LABELS = {label: key for key, (label, _w) in SD_EACH.items()}


def _sd_each_fields(what="counts"):
    # The "Shared Drive reports" form (2.87); GAM Scripts entries preset it.
    return [
        F("Which report", "what", default=SD_EACH[what][0], valuemap=SD_EACH_LABELS),
        F("Your own domains, comma separated (each drive is read as one of its "
          "organizers in them)", "own"),
        F("Only Shared Drives whose name contains (optional)", "match", False),
        F("Folder for the results", "folder", default="C:\\GAMExports"),
        F("Speed: parallel threads (blank = config default)", "threads", False),
    ]


# (new name, report, Ross's scripts) - GAM Scripts entries that open it.
GAM_SCRIPT_SD_EACH = [
    ("Shared Drive file counts and storage", "counts",
     "GetTeamDriveFileCounts.py, GetTeamDriveCountsSize.py, GetTeamDriveStorageInfo.py"),
    ("Shared Drive last changed file", "lastmod", "GetTeamDriveLastModified.py"),
    ("Shared Drive file lists", "files", "GetTeamDriveFileLists.py"),
]


def _sd_each_tasks():
    return [T(name, "Ross Scroggs' %s (GAM-Scripts) - GAM now does this itself: one "
              "command per Shared Drive, run as one of its organizers. This is "
              "'Shared Drive reports', already set up for it. Read-only." % scripts,
              "", _sd_each_fields(what), workflow="sdeach")
            for name, what, scripts in GAM_SCRIPT_SD_EACH]


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
    # 2.82 FIX: was '[showdetails]' - an optional part with no {field} in it
    # is always dropped, so 'show details' never reached GAM.
    "oauth info [{showdetails}]",
    [F("Show the details of every permission (scope)?", "showdetails", False,
       default="No", valuemap={"No": "", "Yes - list every scope": "showdetails"})]),
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
    "Unsuspending restores access. (2.81: the choices say what they do - "
    "GAM's own words are 'suspended on' = suspend, 'suspended off' = "
    "unsuspend.)",
    "update user {email} suspended {state}",
    [F("User email", "email"),
     F("What to do", "state", default="Suspend (block sign-in; data and license kept)",
       valuemap={"Suspend (block sign-in; data and license kept)": "on",
                 "Unsuspend (let them sign in again)": "off"}),
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
    "update group {group} add {role} {dryrun} {member}",
    [F("Group email", "group"),
     F("Role", "role", default="Member", valuemap={"Member": "member",
                 "Manager (can manage the members)": "manager",
                 "Owner (full control of the group)": "owner"}),
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
  T("Set up an administrator (account, roles, OUs)",
    "Creates an admin account (or uses an existing one) and gives it admin "
    "roles for the whole organization or only chosen OUs, in one window. "
    "Same as Admin Roles & Privileges > Set up an administrator. Click Run "
    "to open the window.",
    "", [], workflow="newadmin"),
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
    "Unsuspending restores access. (2.81: the choices say what they do - "
    "GAM's own words are 'suspended on' = suspend, 'suspended off' = "
    "unsuspend.)",
    "update user {email} suspended {state}",
    [F("User email", "email"),
     F("What to do", "state", default="Suspend (block sign-in; data and license kept)",
       valuemap={"Suspend (block sign-in; data and license kept)": "on",
                 "Unsuspend (let them sign in again)": "off"}),
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
    [F("User email", "email"),
     F("In the Global Address List", "state", default="Hide this user",
       valuemap={"Hide this user": "off", "Show this user": "on"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Staff departure hand-off (mailbox, calendar, Drive) (DESTRUCTIVE)",
    "Hands a departing staff member's account to the person taking over, in "
    "one run - each step can be turned off: give them access to the old "
    "mailbox (delegate) and calendar (editor), forward new mail to them "
    "(keeping a copy), set an auto-reply, transfer all Drive files "
    "(Google Data Transfer), and optionally remove the old account from all "
    "groups. A suspended or archived old account is enabled for the steps "
    "that need it. AFTERWARDS choose: keep it ACTIVE but locked (new random "
    "password, signed out, app passwords / backup codes / POP-IMAP removed) so "
    "forwarding and the auto-reply keep working - it still uses a license; "
    "or SUSPEND it - Google then BLOCKS new mail to the old address, so "
    "forwarding and the auto-reply stop working; or put it back the way it "
    "was. You type HANDOFF to confirm.",
    "",
    [F("Departing staff member (old account)", "old"),
     F("Person taking over (new account)", "new"),
     F("Give them access to the old mailbox (delegate)", "delegate", True,
       ["Yes", "No"], "Yes"),
     F("Give them editor access to the old calendar", "calendar", True,
       ["Yes", "No"], "Yes"),
     F("Forward new mail to them (keep a copy)", "forward", True,
       ["Yes", "No"], "Yes"),
     F("Turn on an auto-reply", "vacation", True, ["Yes", "No"], "Yes"),
     F("Auto-reply subject", "subject", False, default="Automated reply"),
     F("Auto-reply message (#old# and #new# are filled in; \\n = new line)",
       "message", False, default=HANDOFF_MESSAGE),
     F("Transfer all their Drive files to them", "drive", True,
       ["Yes", "No"], "Yes"),
     F("Remove the old account from ALL groups", "groups", True,
       ["No", "Yes"], "No"),
     F("Afterwards, the old account should be", "after", True,
       HANDOFF_AFTER, HANDOFF_AFTER[0])],
    destructive=True, workflow="handoff"),
  T("Deprovision user (offboarding) (DESTRUCTIVE)",
    "Offboarding cleanup for a leaving user: removes POP/IMAP access, signs "
    "the user out of all sessions, revokes application-specific passwords, "
    "OAuth tokens and backup codes, and turns off 2-Step Verification. Does "
    "NOT delete the account or its data. If your domain ENFORCES 2-Step "
    "Verification, the 2SV part fails (exit 50) - everything else is still "
    "done.",
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
  # 2.70: GAM 7.45.00 added isdisabled / disabledbefore / disabledafter.
  # "Disabled" = suspended OR archived; GAM adds suspensionTime,
  # archivalTime and disabledTime (the earlier of the two) columns itself
  # (checked live 09-28-2026). A relative time such as -90d is GAM's own
  # <DateTime> form, so no date conversion is needed.
  T("Deprovision candidates: accounts suspended or archived for a while - CSV/Sheet",
    "Lists accounts that are suspended OR archived, with the date they were "
    "turned off (disabledTime) - the usual list for deciding which accounts "
    "to delete or free licenses from. Pick how long they must have been off. "
    "Needs GAM 7.45 or newer.",
    "print users isdisabled true [disabledbefore {before}] fields "
    "primaryemail,name,orgunitpath,suspended,archived,lastlogintime {todrive}",
    [F("Turned off for more than", "before", False,
       default="(any length of time)",
       valuemap={"(any length of time)": "", "30 days": "-30d",
                 "90 days": "-90d", "180 days": "-180d", "1 year": "-1y",
                 "2 years": "-2y"}),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Dormant / never-signed-in users report - CSV/Sheet",
    "Lists accounts that have NOT signed in since a date you choose (never-used "
    "accounts show a very old last-login) - useful for reclaiming licenses and "
    "security cleanup. Enter the cutoff date (YYYY-MM-DD or MM-DD-YYYY); "
    "accounts last active before it are listed.",
    "print users query lastLoginTime<{date!isodate}T00:00:00Z fields primaryemail,orgunitpath,lastlogintime,suspended {todrive}",
    [F("Not signed in since (YYYY-MM-DD or MM-DD-YYYY)", "date", default="2025-01-01"),
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
  T("BULK: archive users (by OU / group / query / CSV) (DESTRUCTIVE)",
    "Archives MANY accounts at once (e.g. last year's departed staff): "
    "sign-in blocked, data kept, each moved to an Archived User license. "
    "Your organization needs enough Archived User licenses for that "
    "edition, or Google refuses the ones it cannot cover.",
    "update users {userscope:usertype:userval} archived on",
    [*_user_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: unarchive users (by OU / group / query / CSV)",
    "Makes MANY archived accounts normal accounts again - each needs a free "
    "regular Workspace license.",
    "update users {userscope:usertype:userval} archived off",
    [*_user_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
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
  # 2.81 (Gabe): Google's 'archive a user' was missing. GAM: 'update user
  # <email> archived on|off' (<UserBasicAttribute> archive|archived
  # <Boolean>); 'print users isarchived' lists them (GAM wiki Users).
  T("Archive / unarchive user",
    "Archiving is for people who leave but whose data you keep (e.g. "
    "former staff): like suspending it blocks sign-in and keeps all their "
    "data, but the account moves from a regular Workspace license to an "
    "Archived User license. Your organization needs Archived User licenses "
    "for that edition, or Google refuses. Unarchiving makes it a normal "
    "account again and needs a free regular license.",
    "update user {email} archived {state}",
    [F("User email", "email"),
     F("What to do", "state",
       default="Archive (block sign-in; keep data; Archived User license)",
       valuemap={"Archive (block sign-in; keep data; Archived User license)": "on",
                 "Unarchive (normal account again; needs a free license)": "off"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Archived users report - CSV/Sheet",
    "Lists every archived account with its OU and last sign-in. Add "
    "'disabledbefore -90d' in the advanced box for accounts archived more "
    "than 90 days ago (GAM 7.45+).",
    "print users isarchived fields primaryemail,name,orgunitpath,archived,"
    "lastlogintime {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Is a user suspended?",
    "Quick check of whether one account is suspended.",
    "check suspended {email}",
    [F("User email", "email"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Groups": [
  *_group_script_tasks(),          # 2.88: Ross Scroggs' Groups scripts, done by GAM
  _group_compare_tasks()[0],
  _school_script_tasks()[1],       # 2.89: last message to each group
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
    "See the GAM wiki 'Group Settings' page for all settings. For the "
    "everyday ones (who can join, see, contact, find, post) use 'Change a "
    "group's settings' - it has plain-word choices.",
    "update group {group}",
    [F("Group email", "group"),
     F("Settings to change", "extra", False, rawappend=True)]),
  # 2.70: from the GAM list (09-21-2026, Ross Scroggs): whocanaddexternal
  # members only takes effect with allowexternalmembers true IN THE SAME
  # command, and its values are only_admins_can_add_external_members |
  # end_users_can_add_external_members (the wiki said only_owners_... -
  # wrong, since corrected). To let the group's OWNERS add outsiders, Ross
  # also sets whocanmoderatemembers owners_only.
  T("Let a group have outside (external) members",
    "Allows people outside your organization in a group, and says who may "
    "add them: the group's own owners/managers, or only Workspace admins. "
    "'Who can add or remove members' sets which of the group's people can "
    "manage membership (Owners only = what Ross Scroggs suggests for letting "
    "group owners add outsiders).",
    "update group {group} allowexternalmembers true whocanaddexternalmembers "
    "{who} [whocanmoderatemembers {moderate}]",
    [F("Group email", "group"),
     F("Who may add outside members", "who", True,
       valuemap={"The group's owners/managers": "end_users_can_add_external_members",
                 "Only Workspace admins": "only_admins_can_add_external_members"}),
     F("Who can add or remove members (optional)", "moderate", False,
       default="(leave as it is)",
       valuemap={"(leave as it is)": "", "Owners only": "owners_only",
                 "Owners and managers": "owners_and_managers",
                 "All members": "all_members", "Nobody": "none"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Block outside (external) members in a group",
    "Stops people outside your organization from being added to a group. "
    "Outsiders who are already members are NOT removed - use the group's "
    "member list for that.",
    "update group {group} allowexternalmembers false",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Add member",
    "Adds one address to a group with the chosen role.",
    "update group {group} add {role} {dryrun} {member}",
    [F("Group email", "group"),
     F("Role", "role", default="Member", valuemap={"Member": "member",
                 "Manager (can manage the members)": "manager",
                 "Owner (full control of the group)": "owner"}),
     F("Member email", "member"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Change member role",
    "Changes an existing member's role (member / manager / owner).",
    "update group {group} update {role} {dryrun} {member}",
    [F("Group email", "group"),
     F("New role", "role", default="Member", valuemap={"Member": "member",
                 "Manager (can manage the members)": "manager",
                 "Owner (full control of the group)": "owner"}),
     F("Member email", "member"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove member",
    "Removes one address from a group.",
    "update group {group} delete member {dryrun} {member}",
    [F("Group email", "group"), F("Member email", "member"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Sync group from OU (DESTRUCTIVE)",
    "Makes group membership EXACTLY match the users in an OU tree: missing "
    "users are added and anyone else is REMOVED from the group.",
    "update group {group} sync member notsuspended {dryrun} ous_and_children {ou}",
    [F("Group email", "group"), F("OU path e.g. /Staff/Building1", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Sync group members from a CSV (DESTRUCTIVE)",
    "Makes a group's membership EXACTLY match a CSV list of email addresses: "
    "anyone in the CSV who is missing is ADDED, and anyone in the group who is "
    "NOT in the CSV is REMOVED. The CSV needs an email column. TEST first - it "
    "removes members who are not in your list.",
    "update group {group} sync member {dryrun} csvfile {file}:{emailcol}",
    [F("Group email", "group"),
     F("CSV file of member emails", "file", filepicker=True),
     F("Column name holding the email", "emailcol", default="email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Remove ALL members (DESTRUCTIVE)",
    "Empties the group: removes every member, manager, and owner. The group "
    "itself remains.",
    "update group {group} clear member manager owner {dryrun}",
    [F("Group email", "group"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # ---------------------------------------------------------------------------
  # BULK group actions - add/remove many members at once, act on many groups
  # from a CSV, and create/delete groups in bulk. GAM's <UserTypeEntity> lets
  # the member source be a single email, a whole group, an OU, or a CSV column,
  # so those source fields are free-text (tokenized) - type, for example:
  #   jsmith@example.org      (one person)
  #   group staff@example.org (everyone in a group)
  #   ou /Students/Grade9     (everyone in an OU)
  #   csvfile C:\list.csv:email   (a CSV column)
  # ---------------------------------------------------------------------------
  T("BULK: add members to a group (from a group / OU / CSV) - adds only",
    "Adds many members to ONE group in a single pass, WITHOUT removing anyone "
    "already in it (unlike Sync). Pick the role, then enter the source of "
    "members. Good for topping up a distribution list from a class OU or group.",
    "update group {group} add {role} {dryrun}",
    [F("Group email", "group"),
     F("Add them as", "role", valuemap={"Members": "member",
       "Managers": "manager", "Owners": "owner"}),
     F("Source - email / group <email> / ou <path> / csvfile <file>:<col>",
       "source", rawappend=True)]),
  T("BULK: remove members from a group (from a group / OU / CSV) (DESTRUCTIVE)",
    "Removes many members from ONE group in a single pass. Enter the source of "
    "members to remove (an email, a group, an OU, or a CSV column). Leave the "
    "role as 'Any role' to remove them no matter what role they hold.",
    "update group {group} remove [{role}] {dryrun}",
    [F("Group email", "group"),
     F("Remove from role", "role", required=False, valuemap={"Any role": "",
       "Members": "member", "Managers": "manager", "Owners": "owner"}),
     F("Source - email / group <email> / ou <path> / csvfile <file>:<col>",
       "source", rawappend=True)],
    destructive=True),
  T("BULK: add ONE user to MANY groups (from a CSV of groups)",
    "Adds a single person to every group listed in a CSV column - e.g. dropping "
    "a new staff member into all their distribution lists at once.",
    "update groups csvfile {file}:{groupcol} add {role} {dryrun} {user}",
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
    "update groups csvfile {file}:{groupcol} remove [{role}] {dryrun} {user}",
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
  # 2.75: from the GAM Public Chat - 'recursive' alone lists only the PEOPLE
  # at the bottom of the nesting, so an empty sub-group never shows up;
  # 'types group' lists the nested groups themselves (verified with gam.exe).
  T("List EVERYONE in a group, including nested groups - CSV/Sheet",
    "Opens up every group inside the group (and groups inside those) and "
    "lists the result. Choose People to see every person who gets the "
    "group's email or access, or Nested groups to see every group inside "
    "it - including EMPTY groups, which the people list cannot show.",
    "print group-members group {group} recursive [{nodup}] [types {types}] {todrive}",
    [F("Group email", "group"),
     F("Show", "types", True, default="People (everyone, through all nested groups)",
       valuemap={"People (everyone, through all nested groups)": "user",
                 "Nested groups only (even empty ones)": "group",
                 "People and nested groups": "user,group"}),
     F("A person in two sub-groups", "nodup", False, default="List them once",
       valuemap={"List them once": "noduplicates",
                 "List them once per sub-group": ""}),
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
    "print groups roles members,managers,owners [{memtypes}] {todrive}",
    [F("Split members into users / groups (optional, GAM 7.46.09+)", "memtypes",
       False, default="No",
       valuemap={"No": "", "Yes - separate user and group members": "showmembertypes"}),
     *_out(),
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
     F("Extra arguments (advanced, e.g. emailmatchpattern ^staff)", "extra", False,
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
    "automatically at that time (e.g. a contractor or a substitute). Enter "
    "the date and time in your local time; GAMGUI converts it to UTC for "
    "Google. Leave the time blank for midnight at the start of that date.",
    "update cigroups {group} add member expire {zulu:expdate:exptime:future} {dryrun} user {email}",
    [F("Group email", "group"), F("User email", "email"),
     F("Remove them on - date (YYYY-MM-DD or MM-DD-YYYY)", "expdate"),
     F("Remove them at - time, your local time (optional, e.g. 17:30 or "
       "5:30 PM; blank = midnight)", "exptime", False),
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
  # 2.84 (Gabe): who can post (send email) to a group - see it for one
  # group or every group, and change it. Values from GamCommands.txt
  # (GAM 7.48.22, <GroupAttribute> whocanpostmessage); 'matchsetting'
  # limits 'print groups' to the groups with that setting.
  T("Who can post to a group? (one group)",
    "Shows who is allowed to post (send email) to one group: everyone, only "
    "people in the organization, members, managers, owners, or nobody.",
    "info group {group} fields whocanpostmessage",
    [F("Group email", "group")]),
  T("Who can post - every group - CSV/Sheet",
    "Lists who is allowed to post (send email) to EVERY group. Pick a setting "
    "in the optional box to list only those groups - for example the groups "
    "that anyone outside the organization can email.",
    "print groups [matchsetting whocanpostmessage {only}] settings fields "
    "whocanpostmessage {todrive}",
    [F("Only the groups where this can post (optional)", "only", False,
       valuemap=WHO_CAN_POST),
     *_out()]),
  T("Change who can post to a group",
    "Sets who is allowed to post (send email) to a group. 'Anyone, even "
    "people OUTSIDE the organization' lets the whole internet email the "
    "group - spam and phishing included.",
    "update group {group} whocanpostmessage {who}",
    [F("Group email", "group"),
     F("Who can post", "who", valuemap=WHO_CAN_POST)]),
  # Bulk (Gabe): the same setting for every group in a CSV or Sheet, OR each
  # row's own setting from the whoCanPostMessage column - the column 'Who
  # can post - every group' writes, so its report can be edited and fed
  # straight back. Column names are case-sensitive (GAM's ~Column).
  T("BULK: change who can post - from a CSV",
    "Changes who can post (send email) to every group listed in a CSV, in ONE "
    "pass. Give every group the same setting, or use each row's own "
    "whoCanPostMessage column: export 'Who can post - every group' to a CSV, "
    "change that column (values like all_members_can_post) and use the file "
    "here. Column names are case-sensitive.",
    "csv {file} gam update group ~{groupcol} whocanpostmessage {who}",
    [F("CSV file", "file", filepicker=True),
     F("Group-email column header", "groupcol", default="email"),
     F("Who can post", "who", valuemap=dict(WHO_CAN_POST, **BULK_WHO_CAN_POST))]),
  T("BULK: change who can post - from a Google Sheet",
    "Same as the CSV version but reads a Google Sheet: give an admin who can "
    "open the sheet, its file ID (the long part of its URL) and the tab name. "
    "Tip: 'Who can post - every group' can send its report straight to a "
    "Sheet - change the whoCanPostMessage column there, then use it here.",
    "csv gsheet {owner} id:{fileid} {tab} gam update group ~{groupcol} "
    "whocanpostmessage {who}",
    [F("Admin who can open the sheet", "owner"),
     F("Sheet file ID (from the URL)", "fileid"),
     F("Tab name e.g. Sheet1", "tab"),
     F("Group-email column header", "groupcol", default="email"),
     F("Who can post", "who", valuemap=dict(WHO_CAN_POST, **BULK_WHO_CAN_POST))]),
  # 2.84 (Gabe): the everyday group settings the same way - see them for one
  # group or every group, change any of them, and bulk from a CSV / Sheet
  # (the settings report can be edited and fed straight back).
  T("Group settings - one group (join, see, contact, find, post)",
    "Shows a group's everyday settings: who can join, see the members, read "
    "the conversations, contact the owners, find the group and post, and "
    "which messages are held for approval.",
    "info group {group} fields " + GROUP_SETTING_FIELDS,
    [F("Group email", "group")]),
  T("Group settings - every group - CSV/Sheet",
    "Lists the everyday settings of EVERY group (who can join, see the "
    "members, read the conversations, contact the owners, find the group and "
    "post, and moderation). Send it to a Sheet or CSV, change the cells, and "
    "use it with 'BULK: change group settings' to apply the changes.",
    "print groups settings fields " + GROUP_SETTING_FIELDS + " {todrive}",
    [*_out()]),
  _need_one(T("Change a group's settings",
    "Changes any of a group's everyday settings at once. Leave a box blank to "
    "keep that setting as it is. A choice ending in 'OUTSIDE the "
    "organization' opens that part of the group to the whole internet.",
    "update group {group}" + _group_setting_template(),
    [F("Group email", "group"), *_group_setting_fields()]),
    [opt for opt, _c, _l, _m in GROUP_SETTINGS],
    "Choose at least one setting to change."),
  _need_one(T("BULK: change group settings - from a CSV",
    "Changes the settings of every group listed in a CSV, in ONE pass. For "
    "each setting choose one value for all groups, 'Each row's own setting' "
    "(a column of the 'Group settings - every group' report - edit it and "
    "use it here), or leave it blank to keep it. Column names are "
    "case-sensitive.",
    "csv {file} gam update group ~{groupcol}" + _group_setting_template(),
    [F("CSV file", "file", filepicker=True),
     F("Group-email column header", "groupcol", default="email"),
     *_group_setting_fields(bulk=True)]),
    [opt for opt, _c, _l, _m in GROUP_SETTINGS],
    "Choose at least one setting to change."),
  _need_one(T("BULK: change group settings - from a Google Sheet",
    "Same as the CSV version but reads a Google Sheet: give an admin who can "
    "open the sheet, its file ID (the long part of its URL) and the tab name. "
    "Tip: send 'Group settings - every group' to a Sheet, change the cells, "
    "then use 'Each row's own setting' here.",
    "csv gsheet {owner} id:{fileid} {tab} gam update group ~{groupcol}"
    + _group_setting_template(),
    [F("Admin who can open the sheet", "owner"),
     F("Sheet file ID (from the URL)", "fileid"),
     F("Tab name e.g. Sheet1", "tab"),
     F("Group-email column header", "groupcol", default="email"),
     *_group_setting_fields(bulk=True)]),
    [opt for opt, _c, _l, _m in GROUP_SETTINGS],
    "Choose at least one setting to change."),
 ],
 "Aliases": [
  T("Create alias",
    "Adds an extra receive-address to a user or group.",
    "create alias {alias} {kind} {target}",
    [F("Alias address", "alias"),
     F("The alias is for", "kind", default="A user",
       valuemap={"A user": "user", "A group": "group",
                 "Let GAM work out which": "target"}),
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
    "Prints every user and group alias in the domain. To list only the "
    "aliases in ONE domain (e.g. an old secondary domain), type it in the "
    "box. To then delete them: save as a CSV file, check the list, and use "
    "'Bulk delete aliases from a CSV' (its column is 'Alias').",
    "print aliases [aliasmatchpattern .*@{aliasdomain}] {todrive}",
    [F("Only aliases in this domain (optional, e.g. old.example.com)",
       "aliasdomain", False),
     *_out(),
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
  _ou_counts_tasks()[0],                     # 2.88 (Ross's GetOrgUnit*Counts)
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
     F("What to do", "action", default="Disable (lock the device)",
       valuemap={"Disable (lock the device)": "disable",
                 "Re-enable (unlock it)": "reenable"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Deprovision device (retire) (DESTRUCTIVE)",
    "Removes the Chromebook from management (retiring it / disposal). This "
    "frees the license. It cannot be undone without re-enrolling. To ALSO "
    "wipe it, run 'Powerwash device' FIRST - once it is deprovisioned it no "
    "longer takes commands. A device that is off powerwashes when it next "
    "comes online.",
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
    "cros_sn {serial} issuecommand command remote_powerwash times_to_check_status 10 {doit}",
    [F("Serial number", "serial"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Wipe users from device (DESTRUCTIVE)",
    "Removes all user profiles from the device but keeps enrollment.",
    "cros_sn {serial} issuecommand command wipe_users {doit}",
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
     F("What to do", "action", default="Disable (lock the device)",
       valuemap={"Disable (lock the device)": "disable",
                 "Re-enable (unlock it)": "reenable"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: deprovision devices (retire) (DESTRUCTIVE)",
    "Removes MANY Chromebooks from management at once (retiring / disposal), "
    "freeing their licenses - e.g. deprovisioning an end-of-life model. This "
    "CANNOT be undone without re-enrolling each device. Add 'maxtodeprov "
    "<number>' in the advanced box to cap how many it will touch as a safety "
    "limit. To ALSO wipe them, run 'BULK: powerwash devices' on the same "
    "devices FIRST - deprovisioned devices no longer take commands; devices "
    "that are off powerwash when they next come online.",
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
    "{crosscope:crostype:crosval} issuecommand command remote_powerwash times_to_check_status 10 {doit}",
    [*_cros_scope(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Retire Chromebooks: wipe, then deprovision (DESTRUCTIVE)",
    "One step for devices leaving the district: sends a remote POWERWASH "
    "(factory reset) to each device, then DEPROVISIONS it (removes it from "
    "management and frees its license) - in that order, because a "
    "deprovisioned device no longer takes commands. Devices that are off "
    "powerwash when they next come online. If any powerwash fails, it "
    "STOPS before deprovisioning so you can check. Cannot be undone without "
    "re-enrolling. Not offered for ALL devices.",
    "",
    [F("Target devices by", "crostype",
       valuemap={"Serial numbers (comma separated)": "sn",
                 "An OU (devices directly in it)": "ou",
                 "An OU and all its sub-OUs": "ou_children",
                 "A device query (e.g. location:Cart5)": "query"}),
     F("Serials / OU path / query", "crosval")],
    destructive=True, workflow="retire"),
  T("Move 'Class of' Chromebook OUs up a grade (yearly rollover)",
    "For districts that keep a Chromebook OU per graduating class (e.g. "
    "'Class of 27', 'Class of 2027', with extras like 'Class of 27 "
    "Bluetooth'). Opens a window that FINDS those OUs and how they are "
    "arranged (which campus or grade OU holds which grade), then shows "
    "exactly what will happen for the school year you pick: each class moves "
    "to the OU for its new grade, the new incoming class is created (with "
    "the same extras), and graduated classes are left alone or moved where "
    "you say. Nothing changes until you click Run there and type ROLLOVER. "
    "Safe to run again - it only does what is still left.",
    "",
    [], workflow="classof"),
  T("Move Chromebooks up a grade in grade-named OUs (yearly rollover)",
    "For districts whose Chromebook OUs are named for a GRADE ('Grade 5', "
    "'5th Grade', 'Kindergarten') instead of a class year. Opens a window "
    "that finds those OUs and counts the Chromebooks in each, then moves "
    "the Chromebooks up one grade - highest grade first, graduated seniors' "
    "Chromebooks to an OU you pick. It never moves two grades at once, never "
    "mixes two grades in one OU, and remembers which steps finished so a "
    "step is never run twice. Nothing changes until you click Run there and "
    "type ROLLOVER.",
    "",
    [], workflow="gradeou"),
  T("BULK: wipe users from devices (DESTRUCTIVE)",
    "Removes all user profiles from MANY devices at once but keeps them "
    "enrolled - e.g. clearing a cart between users. Local user data on each "
    "device is lost.",
    "{crosscope:crostype:crosval} issuecommand command wipe_users {doit}",
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
    "user, policies). Get its ID from 'List enrolled Chrome BROWSERS (not "
    "Chromebooks)' under Chromebooks.",
    "info browser {deviceid} {detail}",
    [F("Browser ID (browserPermanentId column; deviceId before GAM 7.49)", "deviceid"),
     F("Detail", "detail", valuemap={"Basic": "basic", "Full": "full",
       "Annotated fields only (asset ID, location, notes, user)": "annotated"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Move Chrome browsers to an OU",
    "Moves managed Chrome browsers to another OU so different policies apply. "
    "Pick them by browser IDs (comma separated), a browser query, or the OU "
    "they are in now.",
    "move browsers ou {ou} {seltype} {selval}",
    [F("Move TO this OU", "ou"),
     F("Pick browsers by", "seltype", valuemap={
       "Browser IDs (comma separated)": "ids",
       "A browser query (e.g. machine_name:LAB-*)": "queries",
       "The OU they are in now": "browserou"}),
     F("Browser IDs / query / current OU", "selval"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update a Chrome browser's asset ID / location / notes / user",
    "Sets the annotated fields on a managed Chrome browser (the same fields as "
    "a Chromebook's asset tag and location). Fill in only what you want to "
    "change.",
    "update browser {deviceid} [assetid {assetid}] [location {location}] [notes {notes}] [user {user}]",
    [F("Browser ID (browserPermanentId column; deviceId before GAM 7.49)", "deviceid"),
     F("Asset ID (optional)", "assetid", False),
     F("Location (optional)", "location", False),
     F("Notes (optional)", "notes", False),
     F("User (optional)", "user", False),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Delete a Chrome browser (DESTRUCTIVE)",
    "Removes a browser from Chrome Browser Cloud Management. It stops "
    "receiving your policies until it is enrolled again.",
    "delete browser {deviceid}",
    [F("Browser ID (browserPermanentId column; deviceId before GAM 7.49)", "deviceid"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Create a browser enrollment token",
    "Creates a token used to enroll Chrome browsers into management (deployed "
    "to machines by GPO/registry or MDM). Browsers enrolled with it land in "
    "the OU you choose. Treat the token like a password. The token does not "
    "expire - revoke it when it is no longer needed (GAM 7.49.01 removed the "
    "'expire' option).",
    # 2.97: GAM 7.49.01 dropped expire|expires from create browsertoken
    # (doCreateChromeBrowserToken; GamCommands.txt) - sending it is now an
    # "Invalid argument", so the two expiry boxes are gone.
    "create browsertoken [ou {ou}]",
    [F("OU for enrolled browsers (optional, blank = top level)", "ou", False),
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
  _school_script_tasks()[0],         # 2.89: Ross's BrowserExtensions
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
  _filter_fwd_tasks()[0],                  # 2.88 (Ross's GetNonDomainFilterForwards)
  _mail_froms_tasks()[0],                  # 2.88 (Ross's CountFroms)
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
    "all users print forwardingaddresses [{enabled}] {todrive}",
    [F("Show whether each address is turned on (optional, GAM 7.46.08+)",
       "enabled", False, default="No",
       valuemap={"No": "", "Yes": "showenabled"}),
     *_out(),
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
  _cleanup_script_tasks()[1],      # 2.89: Ross's UpdateVacationToHTML
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
  *_label_cleanup_tasks(),         # 2.89: many labels at once (GAM group ask)
  T("Show labels",
    "Lists the mailbox's Gmail labels.",
    "user {email} show labels",
    [F("Mailbox", "email"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # 2.88: label counts. 'print labels showcounts' = Gmail's own totals per
  # label (fast). 'print messages ... showlabels countsonly oneitemperrow
  # [showlabelids]' (GAM 7.48.25 / 7.48.26) = for the messages a search
  # finds, how many are in each label - one label per row.
  T("Labels with message counts - CSV/Sheet",
    "Every Gmail label in the mailbox with its ID and how many messages (and "
    "unread messages) it holds - Gmail's own counts, so it is quick even for a "
    "big mailbox.",
    "user {email} print labels [onlyuser {onlyuser}] showcounts {todrive}",
    [F("Mailbox", "email"),
     F("Which labels", "onlyuser", False, default="All labels (INBOX, SPAM... too)",
       valuemap={"All labels (INBOX, SPAM... too)": "",
                 "Only the labels the user made": "true"}),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Count matching messages per label - CSV/Sheet",
    "For the messages a search finds (e.g. everything from one sender), how "
    "many are in each label - one label per row. Reads each matching message, "
    "so narrow the search for a big mailbox. Needs GAM 7.48.25 or newer "
    "(label IDs: 7.48.26).",
    "user {email} print messages query {mailquery:from:subject:msgid:more} "
    "[max_to_print {max}] showlabels countsonly oneitemperrow [{labelids}] {todrive}",
    [F("Mailbox", "email"),
     *_mail_fields(),
     F("Max messages to read (blank = all that match)", "max", False),
     F("Show label IDs too", "labelids", False, default="No - names only",
       valuemap={"No - names only": "",
                 "Yes - names and IDs (GAM 7.48.26+)": "showlabelids"}),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Turn IMAP on/off",
    "Enables or disables IMAP access for the mailbox.",
    "user {email} imap {state}",
    [F("Mailbox", "email"),
     F("IMAP (mail apps such as Outlook or Apple Mail)", "state",
       default="Turn IMAP on (allow mail apps)",
       valuemap={"Turn IMAP on (allow mail apps)": "on",
                 "Turn IMAP off (block mail apps)": "off"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Turn POP on/off",
    "Enables or disables POP access for the mailbox.",
    "user {email} pop {state}",
    [F("Mailbox", "email"),
     F("POP (older mail apps that download mail)", "state",
       default="Turn POP on (allow)",
       valuemap={"Turn POP on (allow)": "on", "Turn POP off (block)": "off"}),
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
    "before any delete. Fill in the sender, subject words or Message-ID "
    "(More search words take any Gmail search).",
    "user {email} show messages query {mailquery:from:subject:msgid:more}",
    [F("Mailbox", "email"), *_mail_fields(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Trash messages (DESTRUCTIVE)",
    "Moves matching messages to Trash (recoverable ~30 days). The max "
    "limit is a seatbelt against a bad query.",
    "user {email} trash messages query {mailquery:from:subject:msgid:more} max_to_trash {max} {doit}",
    [F("Mailbox", "email"), *_mail_fields(),
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
    "personalize per user, write {NAME} in the signature and put  replace "
    "NAME field:name.fullname  in the advanced box (GAM's Tag Replace wiki "
    "lists the fields), or point at a file with  file C:\\sig.html  instead "
    "of typing text.",
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
    "Moves matching messages OUT of the Trash and back into the mailbox - "
    "e.g. undo an accidental cleanup. Fill in the sender, subject words or "
    "Message-ID; GAMGUI searches only the Trash (in:trash is added).",
    "user {email} untrash messages query {mailquery:from:subject:msgid:more:intrash} max_to_untrash {max} {doit}",
    [F("Mailbox", "email"),
     *_mail_fields(),
     F("Max messages to restore", "max", default="100"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Mark messages as spam (DESTRUCTIVE)",
    "Moves every message that matches a Gmail query into Spam.",
    "user {email} spam messages query {mailquery:from:subject:msgid:more} max_to_spam {max} {doit}",
    [F("Mailbox", "email"),
     *_mail_fields(),
     F("Max messages to mark", "max", default="25"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Add or remove a label on matching messages",
    "Adds a label to, or removes one from, every message that matches a Gmail "
    "query. Tips: to mark messages READ, remove the label UNREAD; to archive "
    "them, remove the label INBOX.",
    "user {email} modify messages query {mailquery:from:subject:msgid:more} max_to_modify {max} {doit} {labelaction} {label}",
    [F("Mailbox", "email"),
     *_mail_fields(),
     # 2.88: GAM 7.48.25 added addlabelid / removelabelid - no extra
     # lookups of the label's name (GAM_VERSION_NEEDS warns on older GAM).
     F("Action", "labelaction", valuemap={"Add this label": "addlabel",
       "Remove this label": "removelabel",
       "Add this label - by its label ID (quicker; GAM 7.48.25+)": "addlabelid",
       "Remove this label - by its label ID (quicker; GAM 7.48.25+)": "removelabelid"}),
     F("Label name e.g. Newsletters, UNREAD, INBOX (or its ID for the 'by its "
       "label ID' choices - 'Labels with message counts' shows the IDs)", "label"),
     F("Max messages to change", "max", default="100"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Forward matching messages to someone",
    "Forwards every message that matches a Gmail query to another address - "
    "e.g. send a departed user's invoices to the business office.",
    "user {email} forward messages to {recipient} query {mailquery:from:subject:msgid:more} max_to_forward {max} {doit}",
    [F("Mailbox (forward FROM)", "email"),
     F("Forward TO (email)", "recipient"),
     *_mail_fields(),
     F("Max messages to forward", "max", default="25"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Export matching messages to .eml files",
    "Saves every message that matches a Gmail query as a .eml file in a folder "
    "on this PC - handy for an investigation or a records request.",
    "user {email} export messages query {mailquery:from:subject:msgid:more} max_to_export {max} {doit} targetfolder {folder}",
    [F("Mailbox", "email"),
     *_mail_fields(),
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
    "user {email} archive messages {group} query {mailquery:from:subject:msgid:more} max_to_archive {max} {doit}",
    [F("Mailbox", "email"), F("Group email", "group"),
     *_mail_fields("before:2026/01/01"),
     F("Max messages", "max", default="1000"),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Calendars": [
  *_calendar_script_tasks(),          # 2.88 (Ross's DeleteFutureEvents / ...Attendees)
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
     F("Which", "kind", default="Out of office",
       valuemap={"Out of office": "outofoffice",
                 "Working location": "workinglocation", "Focus time": "focustime"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # --- Bulk sharing changes across MANY calendars from a CSV ---
  # These read a whole column of calendar IDs from a CSV in ONE gam run (fast),
  # instead of one gam per row. IMPORTANT: pick a Domain (config section) at the
  # top that is an OWNER of these calendars - usually your OWN account's
  # section, NOT the default GAM account, which is typically not an owner and
  # will get "not found / forbidden" on every row.
  T("Bulk REMOVE calendar access from a CSV (DESTRUCTIVE)",
    "Removes ONE person's, group's, or domain's access from EVERY calendar "
    "listed in a CSV. The CSV needs a column of calendar IDs; the 'calendarId' "
    "column produced by 'List a user's calendars' works as-is. FIRST pick the Domain "
    "at the top that owns these calendars. TEST on a one-row CSV before running "
    "the whole list - removing access cannot be undone except by re-granting "
    "it. NOTE: Google will NOT let you remove your OWN access ('Cannot change "
    "your own access level') - only another owner can remove you. To just get "
    "calendars out of your own list, use 'Bulk show/hide calendars' below "
    "instead.",
    "calendars csvfile {file}:{idcol} delete acls {scope}",
    [F("CSV file of calendar IDs", "file", filepicker=True),
     F("Column name holding the calendar ID", "idcol", default="calendarId"),
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
     F("Column name holding the calendar ID", "idcol", default="calendarId"),
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
    "file ('calendarId' in 'List a user's calendars'). MAKE "
    "SURE the CSV does not include the user's OWN primary calendar, or it will "
    "be hidden too.",
    "csv {file} gam user {email} update calendars ~{idcol} [selected {selected}] [hidden {hidden}] [color {color}]",
    [F("User email (whose list)", "email"),
     F("CSV file of calendar IDs", "file", filepicker=True),
     F("Column name holding the calendar ID", "idcol", default="calendarId"),
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
    # FIX 2.72: GAM's parser needs the word 'ownership' (doCalendarsTransfer
    # Ownership) - GamCommands.txt leaves it out, and GAM 7.48.14 rejected
    # the old command with "Expected <ownership>".
    "calendars {cal} transfer ownership {target}",
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
  _school_script_tasks()[2],          # 2.89: Ross's MakeOneAttendeePerRowEvents
  T("List events",
    "Prints events; use dates to narrow the window (YYYY-MM-DD).",
    "calendars {cal} print events [after {after}] [before {before}] fields summary,start,end",
    [F("Calendar ID", "cal"), F("After date (optional)", "after", False),
     F("Before date (optional)", "before", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Update event(s) (advanced)",
    "Changes events. In the advanced box, name the event(s) then the changes, "
    "e.g.  eventid <id> summary \"New title\"  or  query \"old title\" "
    "location \"Room 5\".",
    "calendars {cal} update events",
    [F("Calendar ID", "cal"),
     F("Event selector + changes (see example)", "extra", False, rawappend=True)]),
  dict(T("Delete event(s) (DESTRUCTIVE)",
    "Deletes the events you select (they go to the calendar's trash). Say "
    "which events, e.g.  query \"Fire Drill\"  or  eventid <id>  - this task "
    "refuses to run without a selection, because GAM would otherwise delete "
    "EVERY event on the calendar.",
    "calendars {cal} delete events",
    [F("Calendar ID", "cal"),
     F("Which events (required) e.g. query \"Fire Drill\"", "extra", True,
       rawappend=True)],
    destructive=True),
    # 2.83: without doit GAM deletes NOTHING ("No events are deleted unless
    # you specify the doit option") - so this task never deleted anything.
    tail=("doit",)),
  T("Remove an event from EVERYONE's calendar (phishing invite) (DESTRUCTIVE)",
    "Deletes a calendar event from the PRIMARY calendar of every user (or a "
    "narrower scope) - built for a phishing or spam calendar invite. It matches "
    "by the ORGANIZER'S email (the address that sent the invite), so it clears "
    "every copy of that invite at once. This cannot be undone. Default scope is "
    "ALL users; narrow it to run faster.",
    "{mailscope:scopetype:scopeval} delete events primary matchfield organizeremail {organizer} {doit}",
    [F("Organizer/sender email of the invite", "organizer"),
     F("Scope", "scopetype", valuemap={"All users": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Move event(s) to another calendar (advanced)",
    "Moves events to a different calendar. In the advanced box: name the "
    "event(s) then the destination, e.g.  eventid <id> to othercal@example.com"
    "  or  query \"Fire Drill\" to othercal@example.com.",
    "calendars {cal} move events",
    [F("Source calendar ID", "cal"),
     F("Event selector + 'to <calendar>' (see example)", "extra", False, rawappend=True)]),
  # 2.75: from the GAM Public Chat (calendar ownership transfers). GAM acts
  # as the user (moveCalendarEvents); Google only lets the ORGANIZER move an
  # event, and only 'default' events (not out-of-office / focus time /
  # working location) can move - hence the two filters.
  T("Move a user's events to another calendar (e.g. a leaving staff member)",
    "Moves the events a user ORGANIZED from their main calendar to another "
    "calendar - e.g. a new calendar their manager or replacement owns, "
    "before the account is removed. FIRST give this user 'Make changes to "
    "events' access to the destination calendar (Grant calendar access) - "
    "Google requires it. Only regular events move (not out-of-office, focus "
    "time or working location). Attendees keep the event; it now lives on "
    "the new calendar.",
    "user {email} move events primary [after {after}] eventtypes default "
    "[matchfield organizerself {orgself}] destination {dest} [{notify}]",
    [F("User whose events move", "email"),
     F("Destination calendar ID", "dest"),
     F("Which events", "after", False, default="Upcoming only (from today)",
       valuemap={"Upcoming only (from today)": "today",
                 "All, past and upcoming": ""}),
     F("Only events they organized", "orgself", False,
       default="Yes (others would fail)",
       valuemap={"Yes (others would fail)": "true",
                 "No - try every event": ""}),
     F("Email the attendees about it?", "notify", False, default="No",
       valuemap={"No": "", "Yes": "notifyattendees"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
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
    "set it shown/hidden right away, and give it a friendlier name in their "
    "list (handy for imported calendars with long names; only the owner can "
    "rename the calendar itself).",
    "user {email} add calendars {cal} [selected {selected}] [hidden {hidden}] [summary {listname}]",
    [F("User email", "email"), F("Calendar ID to add", "cal"),
     F("Name shown in their list (optional - e.g. Bell Schedule)", "listname", False),
     F("Show in their calendar list?", "selected", False,
       valuemap={"": "", "Yes - show it": "true", "No - leave unshown": "false"}),
     F("Hide from their list?", "hidden", False,
       valuemap={"": "", "Yes - hide it": "true", "No - keep visible": "false"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show / hide or recolor a calendar in a user's list",
    "Changes how a calendar appears in a user's list: show it or not, hide it "
    "or not, its color (the 24 named colors Google Calendar offers) and the "
    "name it shows under (only in THEIR list).",
    "user {email} update calendars {cal} [selected {selected}] [hidden {hidden}] [color {color}] [summary {listname}]",
    [F("User email", "email"), F("Calendar ID", "cal"),
     F("Name shown in their list (optional - e.g. Bell Schedule)", "listname", False),
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
    "the calendar's ID (usually its email address). Optionally give it a "
    "friendlier name in their lists.",
    "{userscope:usertype:userval} add calendars {cal} [selected {selected}] [hidden {hidden}] [summary {listname}]",
    [*_user_scope(),
     F("Calendar ID to add (usually an email)", "cal"),
     F("Name shown in their list (optional - e.g. Bell Schedule)", "listname", False),
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
    "to a calendar, to make sure it is visible for everyone. Can also rename "
    "it in their lists.",
    "{userscope:usertype:userval} update calendars {cal} [selected {selected}] [hidden {hidden}] [color {color}] [summary {listname}]",
    [*_user_scope(),
     F("Calendar ID", "cal"),
     F("Name shown in their list (optional - e.g. Bell Schedule)", "listname", False),
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
    "user {email} print calendars [{owned}] {todrive}",
    [F("User email", "email"),
     F("Which calendars (optional)", "owned", False, default="All they can see",
       valuemap={"All they can see": "",
                 "Only secondary calendars they own (GAM 7.46.08+)": "ownedsecondary",
                 "Only calendars from our organization (GAM 7.48.15+)":
                     "showownorganizationonly"}),
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
    "user {email} update calattendees {cal} matchfield attendees {old} replace {old} {new} {doit}",
    [F("Calendar owner", "email"),
     F("Calendar (usually 'primary')", "cal", default="primary"),
     F("Attendee to replace (old)", "old"), F("New attendee", "new"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  dict(T("Purge specific events permanently (DESTRUCTIVE)",
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
    # 2.83: doit AFTER the selection. Without it GAM is documented to purge
    # nothing (GAM 7.48.20 still destroys the events - GAM issue #1997 - but
    # a fix there would leave this task doing nothing).
    tail=("doit",)),
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
    "Blocks focus time on a user's calendar between two times on one day and "
    "optionally declines meetings during it. Enter the times in your local "
    "time; GAMGUI converts them to UTC for Google.",
    "user {email} create focustime timerange {zulu:fdate:start} {zulu:fdate:end} declinemode {decline} noreminders",
    [F("User email", "email"),
     F("Date (YYYY-MM-DD or MM-DD-YYYY)", "fdate"),
     F("Start time, your local time (e.g. 9:00 AM or 09:00)", "start"),
     F("End time, your local time (e.g. 11:00 AM or 11:00)", "end"),
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
  _shared_with_me_task(),          # 2.89 (GAM group ask, Ross's command)
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
  T("Find outside sharing on Shared Drives - CSV report",
    "Scans every Shared Drive (or the ones whose name contains your text) "
    "for sharing that reaches OUTSIDE your domains: outside members of the "
    "drive, and files or folders inside it shared with outside people, "
    "groups or domains, or opened to 'anyone with the link' / the web. "
    "Read-only - nothing is changed. It reads each drive's files as one of "
    "its organizers; a drive with no organizer in your domains cannot be "
    "read, so it is listed in a separate 'NotScanned' file instead of "
    "looking clean. To remove what it finds: open the OutsideSharing CSV, "
    "DELETE the rows you want to keep, save, and use 'Remove outside "
    "sharing listed in a report'. Big districts: this can take a while.",
    "",
    [F("Your own domains, comma separated (include sub-domains)", "own"),
     F("Also find 'anyone with the link' / public files", "links", True,
       default="Yes", valuemap={"Yes": "yes", "No": "no"}),
     F("Only Shared Drives whose name contains (optional)", "match", False),
     F("Folder for the results", "folder", default="C:\\GAMExports"),
     F("Speed: parallel threads (blank = config default)", "threads", False)],
    workflow="sdscan"),
  # 2.87: Ross Scroggs' Drive / Shared Drive sharing scripts, done by GAM's
  # own permission matching (find_sharing_steps). The "GAM Scripts" section
  # has one entry per script that opens this already set up.
  T("Find sharing (Shared Drives or users' My Drive) - CSV report",
    "Finds sharing on Shared Drives or in users' My Drive: outside your "
    "domains, with anyone, by link, findable, with chosen domains / groups / "
    "users, with deleted users or groups, or everything. GAM does the "
    "filtering itself (permission matching), one permission per row. "
    "Read-only - nothing is changed. To remove what it finds: open the "
    "report, DELETE the rows you want to keep, save, and use 'Remove outside "
    "sharing listed in a report' (it saves an undo file first).",
    "", _find_fields(), workflow="findsharing"),
  *_drive_script_tasks(),
  _file_roles_tasks()[0],
  _share_count_task(),
  _dup_files_tasks()[0],                     # 2.88 (Ross's DeleteDuplicateFiles, safer)
  *_drive_count_tasks()[:2],                 # 2.88 (Ross's GetDailyMimeTypeCreations etc.)
  T("Remove outside sharing listed in a report (DESTRUCTIVE)",
    "Countermeasure for two reports: the Report builder's 'Files shared "
    "outside your domains' (My Drive files) and 'Find outside sharing on "
    "Shared Drives'. Open the CSV in Excel or Sheets, DELETE the rows you "
    "want to keep, save it, then pick it here. GAMGUI removes the outside "
    "access and/or the 'anyone with the link' / public link on each listed "
    "file - as the file's owner, or for Shared Drives as the drive's "
    "organizer (a drive's own outside members are removed with admin "
    "rights). Access that was already removed is skipped. Before anything "
    "changes, an UNDO file is saved next to the report (use 'Put back "
    "sharing from an undo file'). You type REMOVE to confirm.",
    "",
    [F("Report CSV (rows you want to keep already deleted)", "csvfile",
       filepicker=True),
     F("What to remove", "mode", True, UNSHARE_MODES, UNSHARE_MODES[0])],
    destructive=True, workflow="unshare"),
  T("Put back sharing from an undo file",
    "Re-adds the sharing that 'Remove outside sharing listed in a report' "
    "took away, using the undo file it saved (same people, same roles; "
    "links come back as view-only). No notification emails are sent. You "
    "type RESTORE to confirm.",
    "",
    [F("Undo file (...-undo-....csv)", "csvfile", filepicker=True)],
    workflow="reshare"),
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
  # 2.99: GAM's copysheetprotectedranges (GAM 6.08) - Drive's own copy of a
  # Google Sheet does not bring over who may edit its protected ranges. Before
  # GAM 7.49.05 it failed on any Sheet WITHOUT protected ranges ("Must
  # specify at least one request"), so a folder copy only works from 7.49.05.
  T("Copy a file/folder",
    "Copies a Drive file or folder. Add  newfilename \"Name\"  or  parentid "
    "<folderId>  in the advanced box to rename or place the copy. Google "
    "Sheets: choose whether their protected ranges (and who may edit them) "
    "come along (GAM 7.49.05 or later for folders).",
    "user {email} copy drivefile {fileid} [{protect}]",
    [F("File owner", "email"), F("File/folder ID", "fileid"),
     F("Protected ranges in Google Sheets", "protect", default="As Drive copies them",
       valuemap={"As Drive copies them": "",
                 "Copy them and who may edit them": "copysheetprotectedranges"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # 2.70: destination folder box, and GAM 7.45's movefilepermissions - when
  # moving into a Shared Drive, "No" removes the file's own sharing first so
  # only the Shared Drive's members have access.
  T("Move a file/folder",
    "Moves a file/folder into another folder (a folder in a Shared Drive "
    "works too). Keep its sharing, or remove it first so only the "
    "destination's sharing applies - handy when moving into a Shared Drive. "
    "To move to the TOP of a Shared Drive put  teamdriveparentid <driveId>  "
    "in the advanced box instead of a folder ID. (Removing sharing needs GAM "
    "7.45 or newer.)",
    "user {email} move drivefile {fileid} [parentid {parent}] "
    "[movefilepermissions {keepshare}]",
    [F("File owner", "email"), F("File/folder ID", "fileid"),
     F("Move into folder ID (optional)", "parent", False),
     F("Keep who it is shared with", "keepshare", False,
       default="Yes - keep its sharing",
       valuemap={"Yes - keep its sharing": "",
                 "No - remove its sharing first": "false"}),
     F("Extra arguments (advanced, e.g. newfilename \"Name\")", "extra", False,
       rawappend=True)]),
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
    "user {email} transfer ownership {fileid} {newowner} {dryrun}",
    [F("Current owner", "email"), F("File/folder ID", "fileid"),
     F("New owner email", "newowner"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # 2.74: options for the "take over a shared folder" job (a GAM-list
  # question: a curriculum folder that many teachers add to all year, handed
  # to a role account such as curriculum@ at the end of the year). Checked
  # in GAM's source (claimOwnership): a FOLDER is claimed with everything in
  # it, every sub-folder down; old owners keep EDIT access by default
  # (retainrole writer); only owners in the claiming user's own domain are
  # included unless 'subdomains' names others (e.g. a student domain).
  T("Claim ownership of a file/folder",
    "Makes the given user the owner of a file, or of a FOLDER and everything "
    "inside it (every sub-folder down), no matter how many different people "
    "own the items - e.g. hand a shared curriculum folder to a role account "
    "such as curriculum@ at the end of the school year, so the work survives "
    "staff turnover. The previous owners keep edit access unless you choose "
    "otherwise. Items owned by accounts in ANOTHER domain (e.g. a student "
    "domain) are skipped unless you list that domain. Click Preview (dry run) "
    "first: it lists every item that would change hands. Do it before "
    "departing staff accounts are deleted - deleting an account deletes the "
    "files it still owns.",
    "user {email} claim ownership {fileid} [retainrole {retain}] "
    "[subdomains {subdomains}] [{trashed}] [{paths}] {dryrun}",
    [F("User who will own it (e.g. a role account)", "email"),
     F("File or FOLDER ID (a folder includes everything inside it)", "fileid"),
     F("What the previous owners keep", "retain", False,
       default="Edit access (GAM's default)",
       valuemap={"Edit access (GAM's default)": "", "Comment only": "commenter",
                 "View only": "reader", "No access": "none"}),
     F("Also items owned by these other domains (optional, comma separated, "
       "e.g. student.example.org)", "subdomains", False),
     F("Include items in the trash", "trashed", False, default="No",
       valuemap={"No": "", "Yes": "includetrashed"}),
     F("Show each item's folder path (handy with Preview)", "paths", False,
       default="No", valuemap={"No": "", "Yes": "filepath"}),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Collect orphaned files",
    "Gathers a user's orphaned files (files with no parent folder) so they are "
    "reachable again. Add  targetuserfoldername \"Name\"  in the advanced box "
    "to name the collection folder.",
    "user {email} collect orphans {dryrun}",
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
    "user {email} delete filerevisions {fileid} select {seltype} {selval} {doit}",
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
    "user {email} print filecomments {fileid} [{deleted}] {todrive}",
    [F("File owner (whose Drive to look in)", "email"),
     F("File ID (from the file's URL)", "fileid"),
     F("Include deleted comments (optional)", "deleted", False, default="No",
       valuemap={"No": "", "Yes": "showdeleted"}),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # 2.73: GAM 7.01.02+ - my_commentable_items = the Docs, Sheets and Slides
  # the user owns; positivecountsonly = only files that have comments, with
  # the number of comments and replies (checked in GAM's source,
  # printShowFileComments). Google added comment and suggestion WRITING to
  # the Docs/Sheets/Slides APIs on 09-30-2026 - GAM 7.48.14 can only read
  # them; see NOTES.md "READY FOR GAM: comments and suggestions".
  T("Which of a user's Docs, Sheets and Slides have comments? (counts) - CSV/Sheet",
    "Lists only the Google Docs, Sheets and Slides a user owns that have "
    "comments, with how many comments and replies each has - a quick way to "
    "find where discussions are happening before opening each file.",
    "user {email} print filecomments my_commentable_items positivecountsonly {todrive}",
    [F("User email", "email"),
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
    "user {email} transfer drive {newowner} {dryrun}",
    [F("Leaving user (current owner)", "email"),
     F("New owner (receives the files)", "newowner"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("Transfer ownership of files matching a query (to another user)",
    "Transfers ownership of only the files that match a Drive query from one "
    "user to another - e.g. move just the files in a shared project. Query "
    "syntax is the Drive search language, e.g.  name contains 'Budget'  |  "
    "'folderID' in parents.",
    "user {email} transfer ownership query {query} {newowner} {dryrun}",
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
    "user {email} collect orphans {dryrun}",
    [F("User email", "email"),
     F("Extra arguments (advanced, e.g. targetuserfoldername Recovered)",
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
    "plus the folder path it lives in and, for a Shared Drive file, the "
    "Shared Drive's name. The user must be able to see the file (for a "
    "Shared Drive file: a member of that drive).",
    "user {email} show fileinfo {fileid} filepath showdrivename",
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
  *_sd_script_tasks(),
  T("Shared Drive reports: file counts, storage, last change, file lists (CSV)",
    "One report over every Shared Drive (or the ones whose name contains your "
    "text): file counts and storage used, the most recently changed file, or "
    "every file with its folder path. Each drive is read as one of its "
    "organizers in your domains; drives with none are listed in a separate "
    "NotScanned file. Read-only.",
    "", _sd_each_fields(), workflow="sdeach"),
  _sd_writers_tasks()[0],
  _sd_roles_tasks()[0],
  _sd_expand_tasks()[0],
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
  *_sd_empty_tasks(),              # 2.89: empty it first (wiki Users-Drive-Cleanup)
  T("Move a user's Drive INTO a NEW Shared Drive (workflow)",
    "Offboarding helper: creates a NEW Shared Drive, moves the old user's "
    "My Drive contents into it, hands management to the new user, then "
    "removes the temporary access. Designed for a SUSPENDED user - it "
    "unsuspends them for the move and re-suspends them at the end. Needs an "
    "admin account. (Ported from the Move-UserDrive-to-SharedDrive batch.) "
    "Optionally REMOVE the files' old sharing, so only the Shared Drive's "
    "members have access - a record of who each file was shared with is "
    "saved first (Records folder), in case anyone asks later.",
    "", [F("Old user (unsuspended for the move, then re-suspended)", "old"),
         F("New user (becomes the Shared Drive manager)", "new"),
         F("Name for the new Shared Drive", "drivename"),
         F("Admin account (runs the ACL changes)", "admin"),
         F("Remove the files' old sharing (a record is saved first)",
           "dropshare", True, ["No", "Yes"], "No")],
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
    "are added and extra members are REMOVED. Runs as the admin you name "
    "(with admin access), the same as GAM's own form of this command.",
    # FIX 2.72: in GAM 7.48.14 the top-level 'gam sync shareddriveacls'
    # crashes (TypeError: copySyncSharedDriveACLs() missing 'users' - the
    # 'sync' table calls it without the admin that 'copy' passes). The user
    # form with asadmin is what the top-level one means, and it works.
    "user {admin} sync shareddriveacls {shareddrive:source} with "
    "{shareddrive:target} asadmin",
    [F("Admin email (GAM runs this as that admin)", "admin"),
     F("Shared Drive to CHANGE (name or ID)", "source"),
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
     F("Role", "role", default="Student",
       valuemap={"Student": "student", "Teacher": "teacher",
                 "Owner (becomes the class owner)": "owner"}),
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
  # 2.89: 'which' and 'showstudentemails' - GAM's showstudentemails replaces
  # Ross Scroggs' GetGuardianStudentEmails.py (a Students.csv + a Python join).
  T("List guardians",
    "Prints guardian links and/or pending invitations. 'Show student "
    "emails' adds each student's email address next to the student ID - "
    "the list to send to a campus or import elsewhere.",
    "print guardians {which} [{studentemails}] {todrive}",
    [F("Show", "which", valuemap={
        "Accepted guardians and pending invitations": "all",
        "Accepted guardians only": "accepted",
        "Pending invitations only": "invitations"}),
     F("Student email addresses", "studentemails", valuemap={
        "Show student emails (slower - looks each student up)": "showstudentemails",
        "Student IDs only": ""}),
     *_out(),
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
    "create course name {name} [section {section}] [room {room}] "
    "[subject {subject}] [levels {levels}] [owner {owner}]",
    [F("Course name", "name"), F("Section (optional)", "section", False),
     F("Room (optional)", "room", False),
     F("Subject (optional)", "subject", False),
     # 2.83: Classroom's grade-level box - free text, as teachers type it
     # (e.g. '9th Grade', '9-12'); GAM 7.47.07+.
     F("Grade level(s) (optional) e.g. 9th Grade or 9-12", "levels", False),
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
     F("Extra arguments (advanced, e.g. section ~Section levels ~Grade)", "extra",
       False, rawappend=True)]),
  T("Update course details (advanced)",
    "Changes a course's name/section/room/description/subject/grade levels. "
    "Put the changes in the advanced box, e.g.  name \"Algebra I\" section "
    "\"1st Period\" room \"B12\" levels \"9th Grade\".",
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
    # FIX 2.72: GAM reads this word as "courseworks" (it drops '-' and case)
    # and has no such command; the real one is coursework.
    "print course-work {todrive}",
    [*_out(),
     F("Extra arguments (advanced, e.g. course <id>)", "extra", False, rawappend=True)]),
  T("Count courses per student or teacher (CSV/Sheet)",
    "Prints how many courses each student (or each teacher) is enrolled in - "
    "useful for spotting students in no classes, teachers with an unusual load, "
    "or checking enrollment during rollover.",
    "print course-counts {who} {todrive}",
    [F("Count for", "who", default="Each student",
       valuemap={"Each student": "students", "Each teacher": "teachers"}),
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
    # 2.78: GAM 7.48.17 took this out of Developer Preview (GamUpdate.txt;
    # the DEVELOPER_PREVIEW_REQUIRED check was removed from the source).
    "Searches the Chat messages a user can see for keywords (comma "
    "separated). Needs GAM 7.48.17 or newer - older GAM only runs it with "
    "Developer Preview settings in gam.cfg (developer_preview_apis = chat "
    "and a developer_preview_api_key) and otherwise stops with 'Developer "
    "Preview is required for this command'.",
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
    "Adds a to-do item to one of a user's task lists. Google Tasks stores "
    "only the DATE of a due date; GAMGUI writes it in the form Google needs "
    "(midnight UTC of that date, with no time-zone shift).",
    "user {email} create task tltitle:{tasklist} title {title} [notes {notes}] [due {utcdate:due}]",
    [F("User email", "email"),
     F("Task list title", "tasklist", default="My Tasks"),
     F("Task title", "title"), F("Notes (optional)", "notes", False),
     F("Due date (optional, YYYY-MM-DD or MM-DD-YYYY)", "due", False),
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
  _cleanup_script_tasks()[2],      # 2.89: Ross's Delete/ExtractProtectedRanges
  T("Download a Google Doc as JSON (Docs API)",
    "Saves a Google Doc's full structure (text, styles, suggestions) as a "
    "JSON file on this PC - for scripting or records. Use Drive's download "
    "tasks for PDF / Word copies.",
    # 2.76: GAM 7.48.16 added 'comments' and renamed 'viewmode' to
    # 'suggestions' (getGoogleDocument still accepts both names).
    "user {email} get document {fileid} [suggestions {sugg}] [comments {comments}] targetfolder {folder}",
    [F("User with access to the Doc", "email"),
     F("Doc file ID (from its URL)", "fileid"),
     F("Folder on this PC", "folder", default="C:\\GAMExports"),
     F("Suggested edits (optional)", "sugg", False, default="Google's default",
       valuemap={"Google's default": "", "Shown in the text": "inline",
                 "As if accepted": "accepted", "Left out": "without"}),
     F("Comments (optional, GAM 7.48.16+)", "comments", False,
       default="Google's default",
       valuemap={"Google's default": "", "Included": "included",
                 "Left out": "omitted"}),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Create a spreadsheet from JSON (advanced)",
    "Creates a new Google Sheet from a Sheets API create request in a JSON "
    "file (title, tabs, starting data).",
    "user {email} create sheet json file {file}",
    [F("Owner email", "email"), F("JSON file", "file", filepicker=True),
          F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
 ],
 "Licenses": [
  _license_holder_task(),                         # 2.88 (Ross's GetLicenseHolders)
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
    "user {email} add license {license:sku} {dryrun}",
    [F("User email", "email"), F("License name or SKU", "sku"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove license from user", "Removes a license from a user. Enter a "
    "license NAME or a SKU id.",
    "user {email} delete license {license:sku} {dryrun}",
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
    "{userscope:usertype:userval} add license {license:sku} {dryrun}",
    [*_user_scope(),
     F("License name or SKU", "sku"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("BULK: remove a license from many users (DESTRUCTIVE)",
    "Removes the same license from every user in the chosen scope. Enter a "
    "license NAME or SKU.",
    "{userscope:usertype:userval} delete license {license:sku} {dryrun}",
    [*_user_scope(),
     F("License name or SKU", "sku"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  T("BULK: swap a license for many users (move A -> B)",
    "Moves every user in the chosen scope from one license to another - e.g. "
    "upgrade a grade from Education Fundamentals to Education Plus. Enter both "
    "as a license NAME or SKU.",
    "{userscope:usertype:userval} update license {license:newsku} from {license:oldsku} {dryrun}",
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
    "{userscope:usertype:userval} sync license {license:sku} {dryrun}",
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
     F("Detail", "detail", default="Basic",
       valuemap={"Basic": "basic",
                 "Full (also who can see the matter)": "full"}),
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
 PIR_CATEGORY: _pir_tasks(),
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
  # 2.94: which devices / device type / users choices. The TYPE is kept by
  # GAM's csv_output_row_filter on the output rows, NOT by GAM's
  # 'query type:...': on 10-21-2026 'query type:CHROMEOS' paged forever
  # (467,700 "devices" in 2 hours for 644 real ChromeOS - GAM issue #2015),
  # type:chromeos found 0 and type:CHROME_OS was refused by Google. The row
  # filter gave exactly the 644. No ^/$ anchors: cmd.exe eats '^' in a saved
  # .bat, and no deviceType value contains another one.
  T("List devices (CSV/Sheet)",
    "Prints devices known to Cloud Identity (Endpoint Verification and "
    "company-owned inventory). Pick company-owned or personal devices, one "
    "device type, and whether to look up who uses each device (slower on "
    "big domains). The type is kept by filtering GAM's results - Google's own "
    "'type:' search does not work for ChromeOS (GAM issue #2015). Choose "
    "'Leave out repeats' if Google sends the same device more than once "
    "(GAM 7.49.04 or later).",
    "[config csv_output_row_filter {devtype}] print devices [{owner}] [{users}] [{dupes}] {todrive}",
    [F("Which devices", "owner", default="All devices",
       valuemap={"All devices": "", "Company-owned only": "company",
                 "Personal (BYOD) only": "personal"}),
     F("Device type", "devtype", default="Every type",
       valuemap={"Every type": "", "ChromeOS": "deviceType:regex:CHROME_OS",
                 "Windows": "deviceType:regex:WINDOWS", "Mac": "deviceType:regex:MAC_OS",
                 "iOS": "deviceType:regex:IOS", "Android": "deviceType:regex:ANDROID",
                 "Linux": "deviceType:regex:LINUX"}),
     F("Show each device's users", "users", default="Devices and their users",
       valuemap={"Devices and their users": "", "Devices only (faster)": "nodeviceusers"}),
     # GAM 7.49.04 'deleteduplicates' (#2015): leaves repeated records out
     # of GAM's output only - nothing is deleted in Google - and stops if
     # Google repeats a page token or sends a page of nothing but repeats.
     # Older GAM refuses the word, so the default changes nothing.
     F("Repeated records", "dupes", default="Keep what Google sends",
       valuemap={"Keep what Google sends": "",
                 "Leave out repeats (GAM 7.49.04 or later)": "deleteduplicates"}),
     *_out(),
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
    "e.g.  name \"Jane Vendor\" email work jane@vendor.com primary "
    "organization work \"Vendor Inc\" primary  (double quotes around text "
    "with spaces).",
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
    "box, e.g.  name \"Jane Vendor\" email work jane@vendor.com primary "
    "organization work \"Vendor Inc\" primary  (double quotes around text "
    "with spaces).",
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
  _cleanup_script_tasks()[0],      # 2.89: Ross's DeleteOldContacts
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
  T("Set up an administrator (account, roles, OUs)",
    "Everything for a new admin in ONE window: create the account (or use "
    "an existing one), tick admin roles from your domain's list (or create "
    "a new custom role), and choose where they apply - the whole "
    "organization or only the OUs you pick from your OU tree - with an "
    "optional end date. Click Run to open the window. It shows every GAM "
    "command before anything happens, and can show the steps for letting "
    "that admin run GAM with only these rights.",
    "", [], workflow="newadmin"),
  T("List admin role assignments",
    "Prints who is assigned which admin role and at what scope. Temporary "
    "roles show their end time in the expirationDetails.expireTime column "
    "(GAM shows it in gam.cfg's time zone - UTC unless you changed it).",
    "print admins {todrive}",
    [*_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # 2.98 (10-28-2026): built from what GAM 7.49.02 printed live (read-only).
  T(ADMIN_REVIEW_NAME,
    "Every admin role assignment - Super Admin first - with, for each person, "
    "whether they are suspended, enrolled in and made to use 2-Step "
    "Verification, and their last sign-in. Points out what is worth a second "
    "look: admins without 2-Step Verification (super admins first), suspended "
    "accounts that still hold a role, a role held by an account that no "
    "longer exists, admins who have not signed in for a while, one person "
    "with many roles, fewer than two super admins (Google recommends a "
    "backup), and temporary roles with their end date. Three read-only GAM "
    "commands, one CSV.",
    "", [F("Point out admins who have not signed in for this many days", "days",
           default="90"),
         F("Folder for the results", "folder", default="C:\\GAMExports")],
    workflow="adminreview"),
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
    "Grants a user, group, or service account an admin role across the whole "
    "domain, with no end date. Role is a role name or ID (see List admin "
    "roles). For access that should end on its own, use 'Assign a TEMPORARY "
    "admin role'.",
    "create admin {who} {role} customer",
    [F("User, group, or service account email", "who"),
     F("Role name or ID", "role"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Assign admin role (scoped to an OU)",
    "Grants a user, group, or service account an admin role limited to one "
    "OU, with no end date.",
    "create admin {who} {role} org_unit {ou}",
    [F("User, group, or service account email", "who"),
     F("Role name or ID", "role"),
     F("OU path", "ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  # ---------------------------------------------------------------------------
  # TEMPORARY admin roles (Google, September 2026): the role assignment ends
  # automatically at the expiration and Google revokes the access. Enter the
  # date and time in THIS computer's time zone; GAMGUI converts it to UTC
  # ("Zulu", e.g. 2027-01-05T15:00:00Z) for GAM and Google - the {zulu:...}
  # token in build_command. Blank time = midnight at the start of that date.
  # Must be in the future and within one year. Needs GAM 7.48.06 or newer
  # (the 'expires' option of 'gam create admin').
  # ---------------------------------------------------------------------------
  T("Assign a TEMPORARY admin role (whole domain)",
    "Grants an admin role across the whole domain that EXPIRES on its own - "
    "e.g. covering for someone on leave, a project, or an audit. Enter the "
    "expiration in your local time; GAMGUI converts it to UTC (Zulu) for "
    "Google, and the preview shows the converted time. Leave the time blank "
    "for midnight at the start of that date. Must be within one year. The "
    "primary super admin cannot be given a temporary role.",
    "create admin {who} {role} customer expires {zulu:expdate:exptime:year}",
    [F("User, group, or service account email", "who"),
     F("Role name or ID", "role"),
     F("Expires on - date (YYYY-MM-DD or MM-DD-YYYY)", "expdate"),
     F("Expires at - time, your local time (optional, e.g. 17:30 or "
       "5:30 PM; blank = midnight)", "exptime", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Assign a TEMPORARY admin role (scoped to an OU)",
    "Grants an admin role limited to one OU that EXPIRES on its own. Enter "
    "the expiration in your local time; GAMGUI converts it to UTC (Zulu) for "
    "Google. Leave the time blank for midnight at the start of that date. "
    "Must be within one year.",
    "create admin {who} {role} org_unit {ou} expires {zulu:expdate:exptime:year}",
    [F("User, group, or service account email", "who"),
     F("Role name or ID", "role"),
     F("OU path", "ou"),
     F("Expires on - date (YYYY-MM-DD or MM-DD-YYYY)", "expdate"),
     F("Expires at - time, your local time (optional, e.g. 17:30 or "
       "5:30 PM; blank = midnight)", "exptime", False),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Remove admin assignment (DESTRUCTIVE)",
    "Revokes an admin role assignment by its assignment ID (from List admin "
    "role assignments).",
    "delete admin {assignmentid}",
    [F("Role assignment ID", "assignmentid"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)],
    destructive=True),
  # FIX 2.68: GAM REQUIRES 'privileges' when creating a role ("Missing
  # argument: privileges" without it - checked in GAM 7.48.14's source), so
  # the old form without a privileges box could never work.
  T("Create custom admin role",
    "Creates a new custom admin role. Privileges: all_ou gives everything "
    "that can be limited to an OU - use it for an admin who manages only "
    "some OUs (then assign it with 'Assign admin role (scoped to an OU)'). "
    "all gives every privilege, but such a role can only be given for the "
    "whole organization. Or click Pick... to choose single privileges. "
    "(Set up an administrator does all of this in one window.)",
    "create adminrole {name} [description {desc}] privileges {privs}",
    [F("Role name", "name"), F("Description (optional)", "desc", False),
     F("Privileges - all_ou, all, or names separated by commas", "privs",
       default="all_ou"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Admin role details (privileges)",
    "Shows an admin role and every privilege it grants.",
    "info adminrole {role} privileges",
    [F("Role name or ID", "role"),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Rename or edit a custom admin role",
    "Changes a custom admin role's name, description, and/or privileges. "
    "New privileges REPLACE the role's current ones (Pick... lists them; "
    "all_ou = everything that can be limited to OUs). Leave a box blank to "
    "keep what it has now.",
    "update adminrole {role} [name {newname}] [description {desc}] "
    "[privileges {privs}]",
    [F("Role name or ID", "role"), F("New name (optional)", "newname", False),
     F("New description (optional)", "desc", False),
     F("New privileges (optional) - all_ou, all, or names separated by "
       "commas", "privs", False),
     F("Extra arguments (advanced, optional)", "extra", False,
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
    "Transfers a leaving user's app data (e.g. 'Drive and Docs', 'Calendar', "
    "'Data Studio' - GAM 7.48.01+ for Data Studio) to another user. Service "
    "list is comma separated, no spaces after the commas.",
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
    "e.g.  displayname \"Library HP\" ou /Staff makeandmodel \"HP "
    "LaserJet\" uri ipp://...  (double quotes around text with spaces).",
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
    # FIX 2.72: the misspelling (extra 'c') exists only in GAM's syntax file
    # and a source comment - the parser wants channelcustomerentitlements.
    "print channelcustomerentitlements {todrive}",
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
  # Data Studio) plus YouTube. Read the accounts/assets a given user can see.
  # 2.79: Google renamed Looker Studio back to Data Studio (GAM 7.48.10;
  # 'lookerstudio...' stay as synonyms). Old task names: TASK_RENAMES.
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
    # FIX 2.72: 'tagmanagerccounts' (missing 'a') is only in GAM's syntax
    # file and a source comment - NOT "a real GAM quirk" as 2.39 thought;
    # the parser wants tagmanageraccounts.
    "user {email} print tagmanageraccounts {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("List a user's Data Studio (Looker Studio) permissions - CSV/Sheet",
    "Prints who has access to a user's Data Studio assets (called Looker "
    "Studio until 2026) - a sharing audit for reports and data sources.",
    "user {email} print datastudiopermissions {todrive}",
    [F("User email", "email"),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Show a user's Data Studio (Looker Studio) assets",
    "Lists a user's Data Studio reports and data sources.",
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
  T("Share Data Studio (Looker Studio) assets with someone",
    "Grants viewer or editor access to a user's Data Studio "
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
  T("Remove Data Studio (Looker Studio) sharing (DESTRUCTIVE)",
    "Removes someone's access to a user's Data Studio reports / data "
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
    [F("Report", "app", default="Admin console changes (admin)",
       valuemap={"Admin console changes (admin)": "admin",
                 "Sign-ins (login)": "login", "Drive (drive)": "drive",
                 "Apps given access - OAuth (token)": "token",
                 "Calendar (calendar)": "calendar", "Groups (groups)": "groups",
                 "Mobile devices (mobile)": "mobile",
                 "Data protection rules (rules)": "rules",
                 "Sign-ins to SAML apps (saml)": "saml", "Chat (chat)": "chat",
                 "Meet (meet)": "meet", "Each user's usage (user)": "user",
                 "Whole organization's usage (customer)": "customer",
                 # 2.92: every other activity log GAM 7.48.30 reads
                 # (REPORT_CHOICE_MAP); retired gplus / jamboard left out.
                 "Classroom (classroom)": "classroom",
                 "Classroom assignments (assignments)": "assignments",
                 "Gmail (gmail)": "gmail",
                 "Chrome (chrome)": "chrome",
                 "Vault (vault)": "vault",
                 "Google Takeout (takeout)": "takeout",
                 "Context-Aware Access (contextawareaccess)": "contextawareaccess",
                 "Gemini in Workspace apps (geminiinworkspaceapps)": "geminiinworkspaceapps",
                 "User account changes (useraccounts)": "useraccounts",
                 "Keep (keep)": "keep", "Tasks (tasks)": "tasks",
                 "Contacts (contacts)": "contacts", "Profile (profile)": "profile",
                 "Graduation (graduation)": "graduation",
                 "Groups Enterprise (groupsenterprise)": "groupsenterprise",
                 "Meet hardware (meethardware)": "meethardware",
                 "Access Evaluation (accessevaluation)": "accessevaluation",
                 "Access Transparency (accesstransparency)": "accesstransparency",
                 "Admin data actions (admindataaction)": "admindataaction",
                 "Data migration (datamigration)": "datamigration",
                 "Directory Sync (directorysync)": "directorysync",
                 "Secure LDAP (ldap)": "ldap",
                 "Google Cloud (gcp)": "gcp",
                 "Cloud Search (cloudsearch)": "cloudsearch",
                 "Looker Studio (datastudio)": "datastudio"}),
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
    [F("For", "which", default="Users",
       valuemap={"Users": "user", "The whole organization": "customer"}), *_out(),
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
    "also signs out and disables 2SV. If your domain ENFORCES 2-Step "
    "Verification, the 2SV part fails (exit 50) - everything else is still "
    "done.",
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
    # FIX 2.72: GamCommands.txt says 'alert <AlertID>' but GAM's parser
    # (doPrintShowAlertFeedback) only accepts 'alertid' - checked against
    # gam.exe 7.48.14.
    "print alertfeedback [alertid {alertid}] {todrive}",
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
    "with proper authorization. Enter the end in your local time; GAMGUI "
    "converts it to UTC for Google. With no end date GAM's default applies "
    "(30 days from now).",
    "audit monitor create {email} {dest} [end {utcminute:enddate:endtime:future}]",
    [F("Mailbox to monitor", "email"), F("Send copies to", "dest"),
     F("End date (optional, YYYY-MM-DD or MM-DD-YYYY)", "enddate", False),
     F("End time, your local time (optional; blank = midnight)", "endtime",
       False),
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
  # 2.99 (10-29-2026): a 'Which settings' list and an OU match. Each filter
  # was run live (read-only) and matched the same rows as the full listing;
  # GAM keeps the LAST 'filter', so a custom filter replaces the choice, and
  # 'ou' is a case-insensitive regular expression of the WHOLE OU path.
  T("List Cloud Identity policies - CSV/Sheet",
    "Prints the Admin console settings Google exposes through the Cloud "
    "Identity Policy API (security, Gmail, Drive, DLP rules...): one row for "
    "each OU or group that sets its own value - OUs that are not listed "
    "inherit from their parent. 'Security' covers 2-Step Verification, "
    "passwords, session length and account recovery. A custom filter typed "
    "below replaces the choice. Only these OUs is a pattern for the whole OU "
    "path, e.g. .*Student.* or /High School.* . Needs the Cloud Identity "
    "Policy permission (see the GAM wiki page Cloud-Identity-Policies).",
    "print policies [filter {settings}] [filter {filter}] [ou {oumatch}] {todrive}",
    [F("Which settings", "settings",
       default="Security (2-Step Verification, passwords, sessions, recovery)",
       valuemap={
           "Security (2-Step Verification, passwords, sessions, recovery)":
               "setting.type.matches('settings/security.*')",
           "2-Step Verification only":
               "setting.type.matches('settings/security.two_step_verification.*')",
           "Gmail": "setting.type.matches('settings/gmail.*')",
           "Drive and Docs": "setting.type.matches('settings/drive_and_docs.*')",
           "Data protection (DLP) rules": "setting.type.matches('settings/rule.*')",
           "Google Chat": "setting.type.matches('settings/chat.*')",
           "Google Meet": "setting.type.matches('settings/meet.*')",
           "Classroom": "setting.type.matches('settings/classroom.*')",
           "Gemini and AI apps": "setting.type.matches("
               "'settings/(gemini_app|gemini_for_workspace|ai_studio|notebooklm).*')",
           "Takeout (people downloading their data)":
               "setting.type.matches('settings/.*takeout.*')",
           "Third-party app access": "setting.type.matches("
               "'settings/(api_controls|workspace_marketplace).*')",
           "Every setting (slowest)": ""}),
     F("Custom filter (optional - replaces the choice above)", "filter", False),
     F("Only these OUs (optional) e.g. .*Student.*", "oumatch", False),
     *_out(),
     F("Extra arguments (advanced, optional)", "extra", False, rawappend=True)]),
  T("Cloud Identity policy info",
    "Shows one policy in full. Use its name from 'List Cloud Identity "
    "policies' (policies/...). Tip: add  formatjson  in the advanced box and "
    "save the output as a template for 'Create or update a policy from JSON'.",
    "info policies {name}",
    [F("Policy name e.g. policies/abc123", "name"),
     F("Extra arguments (advanced, e.g. formatjson)", "extra", False,
       rawappend=True)]),
  T("Edit a DLP detector's URL or word list",
    "Opens a window listing your data-protection detectors (Security > "
    "Access and data control > Data protection > Manage detectors). Pick a "
    "URL list or word list, edit it one entry per line, and save - you see "
    "what is added and removed before anything changes, and the old version "
    "is saved to the Records folder (put it back with 'Create or update a "
    "Cloud Identity policy from JSON'). Needs GAM 7.46+ and the Cloud "
    "Identity Policy permission (see the GAM wiki page "
    "Cloud-Identity-Policies).",
    "",
    [], workflow="dlpedit"),
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
 "Compromised Account": [
  # 2.83 (Gabe's idea): one place for an account someone else got into -
  # lock it, keep the evidence, remove the attacker's footholds, and a
  # checklist of what GAM cannot do. Ties into Email Cleanup when a
  # phishing email started it. The workflow code is
  # GamGui._run_compromised; the checklist text is COMPROMISED_CHECKLIST.
  T("Respond to a compromised account (guided)",
    "One run for an account someone else got into. 1) CONTAIN: blocks "
    "sign-in with a password nobody can type and signs the account out "
    "everywhere (revokes every session cookie). 2) EVIDENCE (read-only, saved "
    "to a timestamped folder under Logs): account details incl. recovery "
    "email/phone, Gmail filters, forwarding, delegates, send-as, vacation "
    "reply, app passwords, OAuth app access, mobile devices, mail sent "
    "recently, drafts, mail moved to the Trash, Google Sites, links clicked, "
    "and the sign-in (IP address), account-change, Takeout, SSO, contacts, "
    "device, Drive and Gmail logs - then FINDINGS: every sign-in IP address "
    "with its country and whether Google flagged it suspicious. 3) REMOVE "
    "FOOTHOLDS: app passwords, backup codes and every "
    "app's access; optionally IMAP/POP and 2-Step Verification. 4) "
    "Optionally SUSPEND (last - GAM cannot remove backup codes from a "
    "suspended user). 5) Shows the checklist of steps GAM cannot do (saved "
    "passwords in the browser, malware scan, re-enrolling 2SV...). If a "
    "phishing email started it, fill in its From / Subject and GAMGUI offers "
    "to open the Full incident-response workflow to remove it from every "
    "mailbox. Choose 'Only collect the evidence' to change nothing.",
    "",
    [F("Compromised account", "email", picker="user"),
     F("What to do with the account", "contain",
       valuemap={"Lock it out but keep it active (sign-in blocked, mail still "
                 "arrives) - recommended": "lock",
                 "Lock it out AND suspend it (also stops new mail)": "suspend",
                 "Only collect the evidence - change nothing (read-only)": "none"}),
     F("Remove app passwords, backup codes and every app's access", "deprov",
       valuemap={"Yes - remove them (recommended)": "yes",
                 "No - leave them": "no"}),
     F("Turn off IMAP and POP (attackers use them to download mail)", "popimap",
       valuemap={"Yes - turn them off (recommended)": "yes",
                 "No - leave them as they are": "no"}),
     F("Turn off 2-Step Verification so the user re-enrolls (not possible "
       "where 2-Step Verification is enforced)", "turnoff2sv",
       valuemap={"No - leave 2-Step Verification as it is": "no",
                 "Yes - the attacker may have added their own phone or key": "yes"}),
     F("Days of sign-in and activity logs to collect", "days", default="30"),
     F("Phishing email that started it - From address (optional)", "from", False),
     F("Phishing email - Subject words (optional)", "subject", False)],
    destructive=True, workflow="compromised"),
  T("Compromised account checklist (steps GAM cannot do)",
    "Shows the checklist only - nothing runs. The user and their devices "
    "(saved passwords, Chrome sync, malware, 2-Step Verification), what to "
    "investigate in the Admin console, stopping the spread (link-blocking "
    "rule, Drive trust rule), notifying people, and settings to harden "
    "afterwards.",
    "", [], workflow="compromisedchecklist"),
  *_compromise_more_tasks(),       # 2.89 (MOREnet's investigation tips)
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
    "sub-OUs, or a group) to run faster. Fill in the sender, the subject "
    "words and/or the Message-ID - GAMGUI writes the Gmail search for you.",
    "[config num_threads {threads}] {mailscope:scopetype:scopeval} print messages query {mailquery:from:subject:msgid:more} headers from,to,subject,message-id,date",
    [*_mail_fields(),
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
    "[config num_threads {threads}] {mailscope:scopetype:scopeval} trash messages query {mailquery:from:subject:msgid:more} max_to_trash {max} {doit}",
    [*_mail_fields(),
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
    "scope is ALL mailboxes - narrow it to run faster. Prefer the exact "
    "Message-ID when you have one (paste it in its box) - far more precise "
    "than from+subject matching.",
    "[config num_threads {threads}] {mailscope:scopetype:scopeval} delete messages query {mailquery:from:subject:msgid:more} max_to_delete {max} {doit}",
    [*_mail_fields(),
     F("Max per mailbox", "max", default="5000"),
     F("Search scope", "scopetype", valuemap={"All mailboxes": "all",
       "Specific domain(s)": "domains", "An OU and its sub-OUs": "ou_and_children",
       "A group": "group"}),
     F("Scope value (domain(s)/OU/group; blank for All)", "scopeval", False),
     F("Speed: parallel threads (blank = config default)", "threads", False)],
    destructive=True),
  T("Delete from ONE mailbox (DESTRUCTIVE)",
    "Permanently deletes matching messages from a single mailbox.",
    "user {email} delete messages query {mailquery:from:subject:msgid:more} max_to_delete {max} {doit}",
    [F("Mailbox", "email"), *_mail_fields(),
     F("Max to delete", "max", default="100")], destructive=True),
  T("Find & PERMANENTLY delete a message from ONLY the mailboxes that have it",
    "Two-phase and fast: searches mailboxes for a message, shows how many "
    "matched, then - after you type DELETE to confirm - PERMANENTLY DELETES it "
    "(NOT recoverable, it does not go to Trash) from ONLY the mailboxes that "
    "actually had it (every other mailbox is skipped, so it is far quicker than "
    "scanning the whole domain again). Built for malicious/phishing mail. This "
    "is the lightweight targeted version of the full incident workflow: no Drive "
    "sweep, no audit reports. Tip: the exact Message-ID (its own box) is the "
    "most precise. Evidence is saved to a timestamped folder under Logs.",
    "",
    [*_mail_fields(),
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
 "GAM Scripts (Ross Scroggs)": _gam_script_finds() + _sd_script_tasks()[:3] + _sd_each_tasks()
                               + _sd_writers_tasks()[1:] + _sd_roles_tasks()[1:]
                               + _sd_expand_tasks()[1:] + _file_roles_tasks()[1:]
                               + _drive_script_tasks() + _group_script_tasks()
                               + _group_compare_tasks()[1:]
                               + [_share_count_task(), _license_holder_task()]
                               + _ou_counts_tasks()[1:] + _filter_fwd_tasks()[1:]
                               + _calendar_script_tasks() + _mail_froms_tasks()[1:]
                               + _dup_files_tasks()[1:] + _drive_count_tasks()[2:]
                               + _school_script_tasks()[3:]        # 2.89
                               + _cleanup_script_tasks()[3:]       # 2.89
                               + _csv_tool_tasks(ross=True),       # 2.89
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
  *_csv_tool_tasks(),               # 2.89: Ross's CSV helper scripts
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
    PIR_CATEGORY: "Vault-Takeout",
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
    # 2.88: the two newer categories had no page and fell back to the wiki
    # home page. Ross's scripts are listed on the wiki's Scripts page; the
    # compromised-account steps start with signing the user out.
    "GAM Scripts (Ross Scroggs)": "Scripts",
    "Compromised Account": "Users-Signout-Turnoff2SV",
}

# More specific pages, chosen from the GAM object named in a task's command
# template. Checked IN ORDER; the first regular expression that matches the
# template wins. Word boundaries (\b) keep e.g. 'contactdelegate' from
# matching the Gmail 'delegate' rule.
DOC_HINTS = [
    # 2.73: comments have their own wiki page (was sent to Drive Files Manage)
    (r"\bfilecomments\b", "Users-Drive-Comments"),
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


# 2.90: a workflow task has no command template for DOC_HINTS to read, so it
# fell back to its category's page (Trace an IP address -> the Signout page).
# The wiki page for what each workflow does (checked by check_doc_links.py).
WORKFLOW_DOCS = {
    "findsharing": "Users-Drive-Permissions", "fileroles": "Users-Drive-Permissions",
    "sdscan": "Shared-Drives", "sdeach": "Shared-Drives", "sdwriters": "Shared-Drives",
    "sdroles": "Shared-Drives", "sdexpand": "Shared-Drives",
    "groupcompare": "Groups-Membership", "oucounts": "Organizational-Units",
    "filterforwards": "Users-Gmail-Filters",
    "mailfroms": "Users-Gmail-Messages-Threads", "lastgroupmail": "Users-Gmail-Messages-Threads",
    "dupfiles": "Users-Drive-Cleanup", "sdempty": "Users-Drive-Cleanup",
    "drivedaily": "Users-Drive-Files-Display", "driveaccess": "Users-Drive-Files-Display",
    "browserexts": "Chrome-Browser-Cloud-Management",
    "eventattendees": "Users-Calendars-Events",
    "oldcontacts": "Users-People-Contacts-Profiles",
    "vacationhtml": "Users-Gmail-Send-As-Signature-Vacation",
    "sheetprotect": "Users-Spreadsheets", "csvtools": "Bulk-Processing",
    "iptrace": "Reports", "linkclicks": "Reports", "foreignsignins": "Reports",
    "transferdrive": "Users-Drive-Transfer",
    "adminreview": "Administrators",                                      # 2.98
}


def task_doc_url(category, task):
    # Returns the GAM wiki URL for a task: the task's own "doc" key if it has
    # one, else the first DOC_HINTS match on its command template, else (a
    # workflow, 2.90) WORKFLOW_DOCS, else its category's page, else the wiki
    # home page.
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
    if (task or {}).get("workflow") in WORKFLOW_DOCS:
        return WIKI_BASE + WORKFLOW_DOCS[task["workflow"]]
    page = CATEGORY_DOCS.get(category)
    return WIKI_BASE + page if page else WIKI_BASE + "Home"

# =============================================================================
# SECTION: CSV bulk runs ("Run for each row of a CSV")
# =============================================================================
# Any ordinary task can be run once per row of a CSV file with GAM's own
# loop:   gam csv <file> [maxrows N] gam <the task's command>
# where a field mapped to a CSV column becomes ~Column (the whole argument)
# or ~~Column~~ (when the value sits inside a larger argument such as
# tltitle:~~List~~). GAM substitutes each row's value. See the GAM wiki page
# Bulk-Processing.

def bulk_unavailable(task):
    # 2.92: why a task cannot run once per CSV row ("Run for each CSV row"),
    # or "" when it can. Shared by the desktop and the browser.
    if task is None or task.get("workflow") or task.get("audit") \
            or task.get("external") or task.get("interactive"):
        return ("Select an ordinary task first. Guided workflows, the mailbox audit, "
                "and the Run ANY GAM command console cannot be run per CSV row.")
    if task["template"].lstrip().startswith("csv "):
        return "This task already reads a CSV file itself - just fill in its form."
    if not any(bulk_field_modes(task).values()):
        return ("None of this task's boxes can change from row to row (its values are "
                "dropdowns or are translated by GAMGUI), so it cannot run per CSV row.")
    return ""


def bulk_guess_column(field, columns):
    # 2.92 (moved from the desktop): the CSV column a box most likely comes
    # from - one named like the box or its label (e.g. 'Email' for an email
    # box), or one that contains a key of 4+ letters. "" = use the form value.
    def norm(text):
        return re.sub(r"[^a-z0-9]", "", (text or "").lower())
    key, label = field.get("key", ""), field.get("label", "")
    for col in columns:
        if norm(col) in (norm(key), norm(label)) or (len(key) >= 4 and norm(key) in norm(col)):
            return col
    return ""


def bulk_field_modes(task):
    # For each field of a task, how it can be fed from a CSV column:
    #   "whole"    - its {key} is a whole argument -> ~Column
    #   "embedded" - its {key} sits inside a larger argument -> ~~Column~~
    #   None       - it cannot vary per row (dropdowns, output choice,
    #                free-text 'advanced' boxes, and fields that feed a
    #                special token such as {license:}, {zulu:}, or a scope
    #                picker - those are translated by GAMGUI ONCE, not per row)
    template = task.get("template", "") or ""
    tokens = re.sub(r"[\[\]]", " ", template).split()
    modes = {}
    for field in task.get("fields", []):
        key = field["key"]
        if (field.get("valuemap") or field.get("choices") is not None
                or field.get("rawappend") or key in ("todrive", "csvout")):
            modes[key] = None
            continue
        mode = None
        for tok in tokens:
            if tok in ("{" + key + "}",) or tok.startswith("{" + key + "|"):
                mode = "whole"
                break
            if re.search(r"\{" + re.escape(key) + r"(\|[^}]*)?\}", tok):
                mode = "embedded"           # e.g. tltitle:{tasklist}
        # A key that only appears inside a special token is not mappable.
        if re.search(r"\{\w+:[^}]*\b" + re.escape(key) + r"\b[^}]*\}", template) \
                and mode != "whole":
            mode = None
        modes[key] = mode
    return modes


def build_bulk_command(task, values, csv_path, mapping, maxrows="",
                       domain_prefix=None, tz=None, dry_run=False):
    # Builds the argv for running 'task' once per CSV row.
    #   values        - the form values (dropdowns already translated)
    #   csv_path      - the CSV file to read
    #   mapping       - {field key: CSV column name} for per-row fields
    #   maxrows       - optional "N" to process only the first N rows (a
    #                   test run); blank = every row
    #   domain_prefix - e.g. ['select', 'tenant2'] - placed INSIDE the loop,
    #                   because GAM does not carry an outer 'select' (without
    #                   'save') into the per-row commands.
    #   dry_run       - (2.66) the "Preview (dry run)" form: each row's
    #                   command is built with build_command(dry_run=True)
    #                   ('preview' added / 'doit' left out), and the output
    #                   always goes to the SCREEN - a preview's "would do"
    #                   lines are messages, not results, so a CSV/Sheet
    #                   choice would only create an empty file.
    # Returns (display, argv, error). Results a task would print go to the
    # screen, or - using GAM's documented multiprocess redirect - to ONE
    # CSV file or ONE Google Sheet for all rows (not one per row).
    if not csv_path or not csv_path.strip():
        return "", [], "Choose the CSV file to read."
    if not mapping:
        return "", [], "Map at least one field to a CSV column."
    modes = bulk_field_modes(task)
    per_row = dict(values)
    for key, column in mapping.items():
        mode = modes.get(key)
        if mode is None:
            return "", [], "The field '" + key + "' cannot come from the CSV."
        if not column or not column.strip():
            return "", [], "Pick a CSV column for '" + key + "'."
        per_row[key] = ("~" + column) if mode == "whole" else ("~~" + column + "~~")
    # The output choice is applied OUTSIDE the loop, so build the per-row
    # command as if it printed to the screen.
    dest = "" if dry_run else values.get("todrive", "").strip()
    out_path = values.get("csvout", "").strip()
    per_row["todrive"] = ""
    per_row["csvout"] = ""
    display, argv, err = build_command(task, per_row, tz=tz, dry_run=dry_run)
    if err:
        return "", [], err
    outer, outer_disp = [], []
    if dest == "csv":
        if not out_path:
            return "", [], ("Choose a CSV file to write, or set 'Save "
                            "results to' back to Screen or Google Sheet.")
        outer = ["redirect", "csv", out_path, "multiprocess"]
        outer_disp = ["redirect", "csv", quote_if_needed(out_path), "multiprocess"]
    elif dest == "todrive":
        outer = ["redirect", "csv", "-", "multiprocess", "todrive"]
        outer_disp = list(outer)
    loop = ["csv", csv_path]
    loop_disp = ["csv", quote_if_needed(csv_path)]
    rows = (maxrows or "").strip()
    if rows:
        if not rows.isdigit() or int(rows) < 1:
            return "", [], "Test rows must be a whole number of 1 or more."
        loop += ["maxrows", rows]
        loop_disp += ["maxrows", rows]
    inner_prefix = list(domain_prefix or [])
    full = outer + loop + ["gam"] + inner_prefix + argv
    shown = " ".join(outer_disp + loop_disp + ["gam"] + inner_prefix) + " " + display
    return shown, full, ""


# =============================================================================
# SECTION: "Save as script..." - turn a built command into a .bat / .sh file
# =============================================================================
# The script runs the EXACT argument list GAMGUI would run, so the escaping
# below must survive two parsers on Windows:
#   1. cmd.exe reading the .bat line - it treats & | < > ^ ( ) as operators
#      when they are OUTSIDE double quotes, and expands %...% everywhere;
#   2. gam.exe's C runtime splitting its command line into arguments
#      (quotes group words; backslashes before a quote are special).
# tests/test_script_export.py proves it by running generated .bat files
# through the real cmd.exe and comparing the arguments that arrive.

_CMD_SPECIALS = set('&|<>^()')


def _crt_quote(arg):
    # Quotes ONE argument for the Windows C runtime (the rules Python's own
    # command-line parser follows). Arguments containing spaces, quotes, or
    # anything cmd.exe treats specially are always quoted.
    if arg and not re.search(r'[\s"&|<>^()%!,;=]', arg):
        return arg
    out, slashes = '"', 0
    for ch in arg:
        if ch == "\\":
            slashes += 1
            continue
        if ch == '"':
            out += "\\" * (2 * slashes + 1) + '"'   # escape the quote itself
        else:
            out += "\\" * slashes + ch
        slashes = 0
    return out + "\\" * (2 * slashes) + '"'          # protect a trailing \


def cmd_line_for_bat(argv):
    # Builds the argument text for a .bat line. First CRT-quote each
    # argument, then make the result safe for cmd.exe: cmd flips its "inside
    # quotes" state on EVERY double quote, and outside that state the
    # operators & | < > ^ ( ) need a ^ in front. % is doubled everywhere
    # because a batch file expands %...% even inside quotes.
    if any(("\n" in a or "\r" in a) for a in argv):
        raise ValueError("an argument contains a line break")
    line = " ".join(_crt_quote(a) for a in argv)
    out, inside = [], False
    for ch in line:
        if ch == '"':
            inside = not inside
            out.append(ch)
        elif ch == "%":
            out.append("%%")
        elif not inside and ch in _CMD_SPECIALS:
            out.append("^" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _safe_text(text):
    # Plain, harmless text for batch comments and ECHO lines: keeps letters,
    # digits and simple punctuation, turns everything else into a space.
    return re.sub(r"[^A-Za-z0-9 .,:/_\-]", " ", text or "").strip()


_PLAIN_EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")


# =============================================================================
# SECTION: Pickers (OU tree, admin roles, privileges) - 2.68
# =============================================================================
# Form boxes that take an OU path get a "Browse OUs..." button, admin-role
# boxes a "Pick..." button, and a privileges box a "Pick..." button. The
# lists come from this domain (read-only GAM 'print' commands run by the
# desktop app); the helpers below decide WHICH boxes get a button and turn
# GAM's CSV output into plain lists. No GUI code here, so tests can call
# them directly.

# Scope dropdown values that mean "an OU" - a scope value box only offers
# Browse OUs... while its scope dropdown is on one of these.
OU_SCOPE_TYPES = {"ou", "ou_children", "ou_and_children", "browserou"}

# Scope value box -> the dropdown that says what kind of value it holds.
_SCOPE_PARTNERS = {"userval": "usertype", "crosval": "crostype",
                   "scopeval": "scopetype", "mval": "mtype",
                   "selval": "seltype"}


def ou_picker_mode(task, field):
    # Which OU button a form box gets:
    #   None               - none (not an OU box, or a dropdown / file box)
    #   "ou"               - always (a box that only takes an OU path)
    #   ("scope", TYPEKEY) - only while the TYPEKEY dropdown is an OU type
    #                        (a box that takes an email OR an OU OR ...)
    if not task or not field or field.get("rawappend") or field.get("choices") \
            or field.get("valuemap") or field.get("filepicker"):
        return None
    label = field.get("label", "")
    keys = {f["key"] for f in task.get("fields", [])}
    partner = _SCOPE_PARTNERS.get(field["key"])
    if partner and partner in keys:
        return ("scope", partner)            # checked first: its label can say "file:column"
    if re.search(r"column", label, re.I):
        return None                          # a CSV column NAME, not a path
    if re.search(r"\bOU\b", label):
        return "ou"
    return None


def role_picker(task, field):
    # True for a box that takes an EXISTING admin role (name or ID): the
    # role in 'create admin <who> <role> ...' or 'adminrole <role>' (info,
    # update, delete). Not the NAME box of 'create adminrole' - that role
    # does not exist yet.
    if not task or not field or field.get("rawappend"):
        return False
    template = task.get("template", "") or ""
    key = re.escape(field["key"])
    if re.search(r"\bcreate adminrole \{" + key + r"\}", template):
        return False
    return bool(re.search(r"\badmin \{\w+\} \{" + key + r"\}", template)
                or re.search(r"\badminrole \{" + key + r"\}", template))


def privilege_picker(task, field):
    # True for a box that takes admin role privileges ('privileges {key}').
    if not task or not field or field.get("rawappend"):
        return False
    return bool(re.search(r"\bprivileges \{" + re.escape(field["key"]) + r"\}",
                          task.get("template", "") or ""))


def _csv_rows(text):
    # GAM's 'print' output (CSV on stdout) -> list of dicts.
    import csv as _csv
    import io as _io
    return list(_csv.DictReader(_io.StringIO(text or "")))


def _natural_key(text):
    # Sort key that ignores case and compares numbers as numbers, so
    # "Grade 9" comes before "Grade 10" (a plain sort puts 10 first).
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.lower())
            for part in re.split(r"(\d+)", text) if part != ""]


def parse_ou_paths(text):
    # 'gam print orgs fields orgunitpath' -> sorted list of OU paths.
    # Sorted without regard to case and with numbers in number order.
    paths = set()
    for row in _csv_rows(text):
        path = (row.get("orgUnitPath") or "").strip()
        if path.startswith("/") and path != "/":
            paths.add(path)
    return sorted(paths, key=_natural_key)


def ou_children(paths):
    # {parent path: [child paths]} for the OU tree. The top level's parent
    # is "/". A parent missing from the list (it should not happen) is
    # added so no OU is ever unreachable in the tree.
    kids = {"/": []}
    for path in paths:
        node = path
        while node != "/":
            parent = node.rsplit("/", 1)[0] or "/"
            bucket = kids.setdefault(parent, [])
            if node not in bucket:
                bucket.append(node)
            node = parent
    for parent in kids:
        kids[parent].sort(key=_natural_key)
    return kids


def parse_admin_roles(text):
    # 'gam print adminroles' -> list of {id, name, desc, system, super},
    # Super Admin first, then the others by their friendly label.
    roles = []
    for row in _csv_rows(text):
        name = (row.get("roleName") or "").strip()
        if not name:
            continue
        roles.append({"id": (row.get("roleId") or "").strip(), "name": name,
                      "desc": (row.get("roleDescription") or "").strip(),
                      "system": row.get("isSystemRole") == "True",
                      "super": row.get("isSuperAdminRole") == "True"})
    roles.sort(key=lambda r: (not r["super"], role_label(r).lower()))
    return roles


def role_label(role):
    # A friendly name for a role. Google's built-in roles have code names
    # such as _GROUPS_ADMIN_ROLE with a readable description ("Groups
    # Administrator"), so the description is shown for those.
    if role.get("super"):
        return "Super Admin"
    if role.get("system") and role.get("desc"):
        return role["desc"]
    name = role.get("name", "")
    if role.get("system") and name.startswith("_"):
        # No description: _MIGRATION_DRIVE_ADMIN_ROLE -> Migration Drive Admin Role
        return " ".join(w.capitalize() for w in name.strip("_").split("_"))
    return name


def parse_privileges(text):
    # 'gam print privileges' -> list of {name, service, service_id, ou,
    # depth}. GAM flattens the privilege tree into columns such as
    # childPrivileges.0.childPrivileges.1.privilegeName, so every column
    # ending in 'privilegeName' is one privilege and the text before it is
    # its prefix (the number of 'childPrivileges' in it is how deep it is).
    found, seen = [], set()
    for row in _csv_rows(text):
        for col, value in row.items():
            if not col or not col.endswith("privilegeName") or not value:
                continue
            prefix = col[:-len("privilegeName")]
            sid = (row.get(prefix + "serviceId") or "").strip()
            key = (value.strip(), sid)
            if key in seen:
                continue
            seen.add(key)
            found.append({"name": value.strip(),
                          "service": (row.get(prefix + "serviceName") or "").strip(),
                          "service_id": sid,
                          "ou": row.get(prefix + "isOuScopable") == "True",
                          "depth": prefix.count("childPrivileges")})
    return found


def privilege_tokens(selected, all_privileges):
    # The value for 'privileges': names separated by commas. A name that
    # exists in more than one service (APP_ADMIN does) is written as
    # NAME:serviceId, the form GAM accepts for exactly that case - a plain
    # name would be matched to whichever service GAM saw last.
    counts = {}
    for priv in all_privileges:
        counts[priv["name"]] = counts.get(priv["name"], 0) + 1
    out = []
    for priv in selected:
        token = priv["name"]
        if counts.get(priv["name"], 0) > 1 and priv.get("service_id"):
            token += ":" + priv["service_id"]
        if token not in out:
            out.append(token)
    return ",".join(out)


# =============================================================================
# SECTION: "Set up an administrator" (workflow="newadmin") - 2.68
# =============================================================================
# One window: the account (create it, or use an existing one), the admin
# roles (existing ones, and/or a new custom role), and WHERE they apply (the
# whole organization, or only chosen OUs), with an optional end date. This
# builds the ordered GAM commands; the desktop app shows them, asks for
# confirmation, and runs them. Based on the steps Ross Scroggs (GAM) gave
# for an OU-limited GAM admin:
#   gam create adminrole "<name>" privileges all_ou
#   gam create admin <user> "<name>" org_unit /Test
NEWADMIN_PRIVS = {
    "All OU-level privileges (can be limited to OUs)": "all_ou",
    "All privileges (whole organization only)": "all",
    "Only the privileges I pick": "list",
}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def new_admin_plan(v, super_roles=("_SEED_ADMIN_ROLE",), tz=None,
                   role_labels=None):
    # v (all strings unless noted):
    #   email, create ("yes" to create the account), first, last, password,
    #   account_ou, must_change (bool), notify,
    #   roles (list of existing role NAMES),
    #   new_role_name, new_role_desc, new_role_privs ("all_ou"/"all"/"list"),
    #   new_role_list (comma-separated privileges when "list"),
    #   scope ("customer" or "ous"), ous (list of OU paths),
    #   expdate, exptime (optional end of the access, local time).
    # super_roles: role names that are Super Admin (from the live list).
    # role_labels: optional {role name: friendly label} used ONLY in the step
    #   labels (the commands always use the name GAM expects).
    # Returns {"email", "steps": [(label, argv, kind)], "super", "roles",
    # "where", "expires"}; raises ValueError with a plain message.
    email = (v.get("email") or "").strip()
    if not _EMAIL_RE.match(email):
        raise ValueError("Enter the administrator's full email address.")
    steps = []
    create = (v.get("create") or "") == "yes"
    if create:
        first = (v.get("first") or "").strip()
        last = (v.get("last") or "").strip()
        pw = v.get("password") or ""
        if not first or not last:
            raise ValueError("Enter a first and last name for the new account.")
        if len(pw) < 8:
            raise ValueError("The password must be at least 8 characters "
                             "(Google's minimum) - or click Generate.")
        argv = ["create", "user", email, "firstname", first, "lastname", last,
                "password", pw, "changepassword",
                "on" if v.get("must_change", True) else "off"]
        account_ou = (v.get("account_ou") or "").strip()
        if account_ou:
            if not account_ou.startswith("/"):
                raise ValueError("The account's OU must start with / "
                                 "(e.g. /Staff/IT).")
            argv += ["ou", account_ou]
        notify = (v.get("notify") or "").strip()
        if notify:
            if not _EMAIL_RE.match(notify):
                raise ValueError("'Email the sign-in details to' must be an "
                                 "email address.")
            argv += ["notify", notify]
        steps.append(("Create the account " + email, argv, "user"))

    roles = [r.strip() for r in (v.get("roles") or []) if r and r.strip()]
    new_name = (v.get("new_role_name") or "").strip()
    new_privs = (v.get("new_role_privs") or "").strip()
    if new_name:
        if new_name.lower() in [r.lower() for r in roles]:
            raise ValueError("The new role '" + new_name + "' is also ticked "
                             "in the existing roles - untick it there.")
        if new_privs == "list":
            privs = (v.get("new_role_list") or "").strip().strip(",")
            if not privs:
                raise ValueError("Pick the privileges for the new role.")
        elif new_privs in ("all_ou", "all"):
            privs = new_privs
        else:
            raise ValueError("Choose the new role's privileges.")
        argv = ["create", "adminrole", new_name]
        desc = (v.get("new_role_desc") or "").strip()
        if desc:
            argv += ["description", desc]
        argv += ["privileges", privs]
        steps.append(("Create the admin role '" + new_name + "'", argv, "role"))
        roles.append(new_name)
    if not roles:
        raise ValueError("Tick at least one admin role, or create a new one.")

    supers = {s.lower() for s in super_roles}
    is_super = any(r.lower() in supers for r in roles)
    if (v.get("scope") or "customer") == "ous":
        ous = []
        for ou in v.get("ous") or []:
            ou = ou.strip()
            if ou and ou not in ous:
                ous.append(ou)
        if not ous:
            raise ValueError("Add at least one OU, or choose 'The whole "
                             "organization'.")
        if any(not ou.startswith("/") for ou in ous):
            raise ValueError("Every OU must start with / (e.g. /Staff).")
        # Google only lets a role be limited to an OU when EVERY privilege in
        # it can be - Super Admin and 'all privileges' never can.
        if is_super:
            raise ValueError("Super Admin cannot be limited to OUs - choose "
                             "'The whole organization', or a different role.")
        if new_name and new_privs == "all":
            raise ValueError("A role with ALL privileges cannot be limited to "
                             "OUs. Choose 'All OU-level privileges' for the "
                             "new role, or 'The whole organization'.")
        scopes = [["org_unit", ou] for ou in ous]
        where = ous
    else:
        scopes = [["customer"]]
        where = ["the whole organization"]

    stamp = ""
    if (v.get("expdate") or "").strip():
        stamp, err = local_to_zulu(v.get("expdate"), v.get("exptime") or "",
                                   rule="year", tz=tz)
        if err:
            raise ValueError("Access ends: " + err)

    for role in roles:
        for scope in scopes:
            argv = ["create", "admin", email, role] + scope
            if stamp:
                argv += ["expires", stamp]
            shown = (role_labels or {}).get(role, role)
            label = ("Give '" + shown + "' for "
                     + (scope[1] if scope[0] == "org_unit"
                        else "the whole organization"))
            steps.append((label, argv, "assign"))
    return {"email": email, "steps": steps, "super": is_super,
            "roles": roles,
            "role_labels": [(role_labels or {}).get(r, r) for r in roles],
            "where": where, "expires": stamp, "created": create}


def gam_setup_steps(email):
    # The follow-up Ross gave for letting the new admin run GAM with ONLY
    # these rights. Shown as text - GAMGUI does not run it, because
    # 'oauth create' replaces the GAM sign-in of whatever config it runs in.
    return (
        "To let " + email + " run GAM with only these rights (from Ross "
        "Scroggs, GAM):\n"
        "  Do this on THEIR computer, or in a separate GAM config folder -\n"
        "  never in your own, or it replaces YOUR GAM sign-in.\n"
        "  1. gam oauth create\n"
        "       (sign in as " + email + " when the browser opens)\n"
        "  2. gam user " + email + " update serviceaccount\n"
        "       (checks the service account's access; if something is\n"
        "       missing it prints an Admin console link for a super admin\n"
        "       to approve)\n"
        "  3. Test the commands they need.\n"
        "  GAMGUI: Settings > Locate gam.cfg... points GAMGUI at that folder.\n"
        "  Wiki: " + WIKI_BASE + "Administrators\n")


def handoff_plan(values):
    # Builds the Staff departure hand-off (workflow="handoff") from the form
    # values. Pure function - nothing runs here - so it is fully testable.
    # Returns a dict:
    #   old, new       - the two addresses (lower-case)
    #   steps          - [(label, argv), ...] in order
    #   needs_active   - True when a step only works on an ACTIVE account
    #                    (Gmail delegation, forwarding and auto-reply, and
    #                    calendar sharing all act AS the old user)
    #   after          - one of HANDOFF_AFTER
    #   after_steps    - [(label, argv)] for the chosen "afterwards"
    # Raises ValueError with a plain message for bad input. Every command
    # was checked against GAM's own grammar (GamCommands.txt).
    old = (values.get("old") or "").strip().lower()
    new = (values.get("new") or "").strip().lower()
    for label, addr in (("Departing staff member", old),
                        ("Person taking over", new)):
        if not _PLAIN_EMAIL.fullmatch(addr):
            raise ValueError(label + ": enter a full email address.")
    if old == new:
        raise ValueError("The departing account and the person taking over "
                         "must be different.")
    yes = lambda key, default="Yes": (values.get(key) or default) == "Yes"
    steps = []
    active = False
    if yes("delegate"):
        steps.append(("Mailbox delegation",
                      ["user", old, "delegate", "to", new]))
        active = True
    if yes("calendar"):
        steps.append(("Calendar editor access",
                      ["calendar", old, "add", "editor", new]))
        active = True
    if yes("forward"):
        steps.append(("Add the forwarding address",
                      ["user", old, "add", "forwardingaddress", new]))
        steps.append(("Forward new mail (keep a copy)",
                      ["user", old, "forward", "on", "keep", new]))
        active = True
    if yes("vacation"):
        subject = (values.get("subject") or "").strip() or "Automated reply"
        message = (values.get("message") or "").strip() or HANDOFF_MESSAGE
        message = message.replace("#old#", old).replace("#new#", new)
        steps.append(("Auto-reply",
                      ["user", old, "vacation", "on", "subject", subject,
                       "message", message]))
        active = True
    if yes("drive"):
        # Google Data Transfer: runs in the background at Google, works
        # for a suspended owner too; 'all' = private AND shared files.
        steps.append(("Drive transfer (Google Data Transfer)",
                      ["create", "datatransfer", old, "drive", new, "all"]))
    if yes("groups", "No"):
        steps.append(("Remove from all groups",
                      ["user", old, "delete", "groups"]))
    if not steps:
        raise ValueError("Every step is turned off - nothing to do.")
    after = values.get("after") or HANDOFF_AFTER[0]
    if after not in HANDOFF_AFTER:
        raise ValueError("Choose what happens to the old account afterwards.")
    if after == HANDOFF_AFTER[0]:
        after_steps = [
            ("New random password (not shown or logged)",
             ["update", "user", old, "password", "random"]),
            # No 'turnoff2sv': it FAILS where 2SV is enforced by policy
            # (found in the live test), and the random password already
            # locks the account.
            ("Sign out, remove app passwords / backup codes / POP-IMAP",
             ["user", old, "deprovision", "popimap", "signout"]),
        ]
    elif after == HANDOFF_AFTER[1]:
        after_steps = [("Suspend", ["update", "user", old, "suspended", "on"])]
    else:
        after_steps = []                  # restored by the caller
    return {"old": old, "new": new, "steps": steps, "needs_active": active,
            "after": after, "after_steps": after_steps}


# ---- Remove / put back outside sharing (workflows "unshare" / "reshare") ----
# Input is the Report builder's "Files shared outside your domains" CSV (the
# admin deletes the rows to KEEP first). Checked against a real Drive audit
# log: new_value holds the role granted (can_edit / can_comment / can_view)
# or, for link events, the new visibility; 'none' means access was removed.
_ROLE_FROM_AUDIT = {"can_edit": "writer", "can_comment": "commenter",
                    "can_view": "reader"}
_LINK_PERMS = {"people_with_link": "anyonewithlink",
               "public_on_the_web": "anyone"}
# 2.76: 'scope' says how the sharing is put back - "file" (as the file's
# owner, or a Shared Drive organizer) or "drive" (a member of a Shared Drive
# itself, changed with admin rights). Undo files from before 2.76 have no
# scope column; they are all "file".
UNDO_COLUMNS = ["owner", "doc_id", "kind", "target", "role", "doc_title", "scope"]


def unshare_plan(rows, mode):
    # rows: dicts from the report CSV. Returns (actions, skipped):
    #   actions - one dict per permission to remove (duplicates merged):
    #             owner, doc_id, perm (email | anyonewithlink | anyone),
    #             kind (user | anyonewithlink | anyone), target, role,
    #             doc_title. 'role' is what to re-add on undo; for a link it
    #             is unknown in the audit log, so viewer (reader) is used.
    #   skipped - (file title or ID, reason) for rows that cannot be done.
    # Raises ValueError when the file is not that report or nothing applies.
    if mode not in UNSHARE_MODES:
        raise ValueError("Choose what to remove.")
    rows = list(rows)
    # 2.76: the Shared Drive scan's report has its own columns.
    if rows and set(SD_REPORT_COLUMNS).issubset(rows[0].keys()):
        return _sd_unshare_plan(rows, mode)
    need = {"doc_id", "owner", "target_user", "visibility"}
    if not rows or not need.issubset(rows[0].keys()):
        raise ValueError("This CSV is not a GAMGUI 'Files shared outside your "
                         "domains' report (it needs the columns doc_id, "
                         "owner, target_user and visibility).")
    actions, skipped = {}, []
    for row in rows:
        doc = (row.get("doc_id") or "").strip()
        owner = (row.get("owner") or "").strip().lower()
        target = (row.get("target_user") or "").strip().lower()
        vis = (row.get("visibility") or "").strip().lower()
        newv = (row.get("new_value") or "").strip().lower()
        title = (row.get("doc_title") or "").strip() or doc
        if str(row.get("owner_is_shared_drive", "")).strip().lower() == "true":
            skipped.append((title, "file is in a shared drive - change its "
                            "sharing in Drive or the Admin console"))
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", doc) or \
                not _PLAIN_EMAIL.fullmatch(owner):
            skipped.append((title, "no file ID or owner address in this row"))
            continue
        if newv == "none":
            skipped.append((title, "that access was already removed"))
            continue
        # Creating a file logs the OWNER being given access to it
        # (new_value 'owner' - seen in the live test). Never remove that.
        if newv == "owner" or (target and target == owner):
            skipped.append((title, "that is the file owner's own access"))
            continue
        if target and mode != UNSHARE_MODES[2]:
            if _PLAIN_EMAIL.fullmatch(target):
                actions[(owner, doc, target)] = {
                    "owner": owner, "doc_id": doc, "perm": target,
                    "kind": "user", "target": target, "doc_title": title,
                    "role": _ROLE_FROM_AUDIT.get(newv, "reader")}
            else:
                skipped.append((title, "recipient is not a valid address"))
        if vis in _LINK_PERMS and mode != UNSHARE_MODES[1]:
            perm = _LINK_PERMS[vis]
            actions[(owner, doc, perm)] = {
                "owner": owner, "doc_id": doc, "perm": perm, "kind": perm,
                "target": "", "doc_title": title, "role": "reader"}
    if not actions:
        raise ValueError("Nothing to remove for this choice."
                         + (" (%d rows skipped - see the reasons in the output.)"
                            % len(skipped) if skipped else ""))
    return list(actions.values()), skipped


def reshare_commands(undo_rows):
    # From an undo file written by the "unshare" workflow: returns
    # [(kind, rows, gam argv for 'gam csv <file> gam ...')] - one GAM csv
    # loop per kind of sharing. Raises ValueError for a file that is not an
    # undo file. Roles are checked so nothing unexpected is granted.
    rows = list(undo_rows)
    if not rows or not set(UNDO_COLUMNS[:5]).issubset(rows[0].keys()):
        raise ValueError("This CSV is not a GAMGUI undo file (it needs the "
                         "columns " + ", ".join(UNDO_COLUMNS[:5]) + ").")
    # 2.76: Shared Drive rows add groups, domains and the drive's own
    # members (scope "drive", put back with admin rights: 'gam add
    # drivefileacl <drive id> ...' - GamCommands.txt, SharedDriveEntityAdmin).
    groups = {}
    for row in rows:
        kind = (row.get("kind") or "").strip()
        role = (row.get("role") or "").strip().lower()
        scope = (row.get("scope") or "file").strip().lower()
        if kind not in _RESHARE_TAILS or role not in _RESHARE_ROLES \
                or scope not in ("file", "drive"):
            raise ValueError("Unexpected kind/role/scope in the undo file: "
                             "%r / %r / %r" % (kind, role, scope))
        if scope == "drive" and kind not in ("user", "group", "domain",
                                             "domainwithlink"):
            raise ValueError("A Shared Drive member cannot be a link: %r" % kind)
        # The person, group or domain that gets access back must look right
        # (a blank or odd value would make GAM grant something unexpected).
        target = (row.get("target") or "").strip()
        if kind in ("user", "group") and not _PLAIN_EMAIL.fullmatch(target):
            raise ValueError("Not an email address in the undo file: %r" % target)
        if kind.startswith("domain") and not _DOMAIN_NAME.fullmatch(target):
            raise ValueError("Not a domain name in the undo file: %r" % target)
        groups.setdefault((scope, kind), []).append(row)
    bases = {"file": ["gam", "user", "~owner", "add", "drivefileacl", "~doc_id"],
             "drive": ["gam", "add", "drivefileacl", "~doc_id"]}
    out = []
    for scope in ("file", "drive"):
        for kind in _RESHARE_TAILS:
            if (scope, kind) in groups:
                label = kind if scope == "file" else "drive-" + kind
                out.append((label, groups[(scope, kind)],
                            bases[scope] + _RESHARE_TAILS[kind]))
    return out


# How each kind of sharing is added back (see reshare_commands), in order.
_RESHARE_TAILS = {
    "user": ["user", "~target", "role", "~role"],
    "group": ["group", "~target", "role", "~role"],
    "domain": ["domain", "~target", "role", "~role", "allowfilediscovery", "true"],
    "domainwithlink": ["domain", "~target", "role", "~role", "withlink"],
    "anyonewithlink": ["anyone", "role", "~role", "withlink"],
    "anyone": ["anyone", "role", "~role", "allowfilediscovery", "true"],
}
# Roles an undo file may grant back (Drive API names, lower case). A Shared
# Drive's own members can also be content managers or managers.
_RESHARE_ROLES = {"reader", "commenter", "writer", "fileorganizer", "organizer"}
# Plain words for each label reshare_commands returns (for the summary).
RESHARE_NAMES = {
    "user": "people's access", "group": "groups' access",
    "domain": "whole-domain shares", "domainwithlink": "domain link shares",
    "anyonewithlink": "'anyone with the link' links", "anyone": "public links",
    "drive-user": "Shared Drive members (people)",
    "drive-group": "Shared Drive members (groups)",
    "drive-domain": "Shared Drive members (domains)",
    "drive-domainwithlink": "Shared Drive members (domains)",
}


# =============================================================================
# SECTION: Outside sharing on SHARED DRIVES (2.76)
# =============================================================================
# From the GAM Public Chat (Ross Scroggs, 08-05-2026). The Report builder's
# outside-sharing report reads the Drive AUDIT LOG and the removal acts as
# each file's OWNER - neither works for Shared Drive files (the drive owns
# them). This scans what is shared RIGHT NOW instead:
#   1. print shareddriveorganizers  - one organizer in your domains per drive
#      (filelist has no admin mode: a scan as a non-member silently returns
#      nothing, so drives with NO such organizer are listed as NOT SCANNED)
#   2. print shareddriveacls        - outside MEMBERS of each drive (admin)
#   3. gam csv <organizers> gam user ~organizers print filelist select
#      teamdriveid ~id ... pm ... inherited false em pmfilter oneitemperrow
#      - outside sharing set on the files themselves. 'inherited false' =
#      only sharing set directly on an item, the only kind that can be
#      removed there (Ross); drive members show up in step 2 instead.
# Column names checked in GAM 7.48.16's source: printShowSharedDriveACLs
# (User,id,name,createdTime,permission.*), printFileList (Owner,id,name,
# mimeType,webViewLink,driveId,driveName,permission.*).
SD_REPORT_COLUMNS = ["where", "drive_name", "drive_id", "doc_title", "doc_id",
                     "mime_type", "link", "act_as", "perm_id", "kind",
                     "target", "role", "discoverable"]
_DOMAIN_NAME = re.compile(r"(?i)[a-z0-9-]+(\.[a-z0-9-]+)+")


# =============================================================================
# SECTION: Groups inside each category (2.80)
# =============================================================================
# Gabe: "better organize each section - group companion/similar commands
# together, make it easier to find what you need." The task tree shows each
# category's tasks under these headings, in this order. A heading of "" means
# no heading (small categories: just a better order). Task NAMES and
# categories are unchanged, so Favorites, Recent, saved scripts and the
# browser version keep working. tests/test_v280_groups.py checks that every
# task is in exactly one group. A task missing here (added later) is shown
# under "More" at the end of its category instead of disappearing.
TASK_GROUPS = {
 "OAuth Setup": [
  ("", ["Create / authorize a GAM admin account",
        "Update / add scopes to a GAM account",
        "Who is GAM authorized as? (oauth info)",
        "Check service account (domain-wide delegation)",
        "Show GAM's service-account keys",
        "Rotate GAM's service-account key (DESTRUCTIVE)"]),
 ],
 "Common Tasks": [
  ("", ["Create user", "Reset password", "Suspend / unsuspend user",
        "Move user to OU", "User info", "Add group member",
        "List group members", "Export users to CSV/Sheet"]),
 ],
 "Users": [
  ("Create & change accounts", [
    "Create user", "Set up an administrator (account, roles, OUs)",
    "Update user - any attribute (advanced)", "Rename user (display name)",
    "Change primary email", "Update job info (title + department)",
    "Set recovery email", "Set recovery phone", "Move user to OU"]),
  ("Passwords, suspend, archive & sign-out", [
    "Reset password", "Suspend / unsuspend user", "Is a user suspended?",
    "Archive / unarchive user", "Sign out user (revoke sessions)"]),
  ("Look up & reports", [
    "User info", "Export users to CSV/Sheet",
    "Export users - advanced (query / fields / OU)", "Count users by OU",
    "Suspended users report - CSV/Sheet", "Archived users report - CSV/Sheet",
    "Dormant / never-signed-in users report - CSV/Sheet",
    "Deprovision candidates: accounts suspended or archived for a while - CSV/Sheet",
    "Export EVERY address in the domain (users+groups+aliases) - CSV/Sheet"]),
  ("Leaving staff & deleting accounts", [
    "Staff departure hand-off (mailbox, calendar, Drive) (DESTRUCTIVE)",
    "Deprovision user (offboarding) (DESTRUCTIVE)", "Delete user (DESTRUCTIVE)",
    "Bulk delete users from a CSV (DESTRUCTIVE)", "Undelete user"]),
  ("Bulk changes (many users)", [
    "BULK: create users from a CSV",
    "BULK: update users from a CSV (per-row values)",
    "BULK: change users (any attribute) (by OU / group / query / CSV)",
    "BULK: move users to an OU (by OU / group / query / CSV)",
    "BULK: suspend users (by OU / group / query / CSV) (DESTRUCTIVE)",
    "BULK: unsuspend users (by OU / group / query / CSV)",
    "BULK: archive users (by OU / group / query / CSV) (DESTRUCTIVE)",
    "BULK: unarchive users (by OU / group / query / CSV)"]),
  ("Profile photos", [
    "Download a user's profile photo", "Set a user's profile photo from a file",
    "BULK: set profile photos from a folder",
    "Delete a user's profile photo (DESTRUCTIVE)"]),
  ("Directory & address list", [
    "Hide/show in Global Address List", "Show or hide a user in the directory",
    "Is a user shown in the directory?",
    "List directory profiles (People API) - CSV/Sheet"]),
  ("Inviting unmanaged accounts", [
    "Can this address be invited? (unmanaged account check)",
    "Invite an unmanaged account to join the organization",
    "Invitation status for an address", "List pending user invitations - CSV/Sheet",
    "Cancel an invitation"]),
 ],
 "Groups": [
  ("Group reports & clean-up (from Ross Scroggs' scripts)",
   [t["name"] for t in _group_script_tasks()] + [GROUP_COMPARE_NAME, LAST_GROUP_MAIL_NAME]),
  ("Create & change groups", [
    "Create group", "Update group name / description / email",
    "Update group settings (advanced)", "Group info", "Delete group (DESTRUCTIVE)"]),
  ("Members", [
    "Add member", "Change member role", "Remove member",
    "Add a member who expires on a date", "Remove ALL members (DESTRUCTIVE)"]),
  ("Who is in a group? (look up & export)", [
    "List members", "List EVERYONE in a group, including nested groups - CSV/Sheet",
    "List members by ROLE (one or more groups) - CSV/Sheet",
    "List group members with expirations - CSV/Sheet",
    "Show a group's nested tree (sub-groups) - CSV/Sheet",
    "Is a user in a group? (check membership)",
    "A user's membership details in a group",
    "What groups is a user in? (their memberships) - CSV/Sheet",
    "Export all groups", "Export all groups + members"]),
  ("Sync members (exact match)", [
    "Sync group from OU (DESTRUCTIVE)",
    "Sync group members from a CSV (DESTRUCTIVE)",
    "Sync a user's groups - exact list (DESTRUCTIVE)"]),
  ("Bulk changes", [
    "BULK: add members to a group (from a group / OU / CSV) - adds only",
    "BULK: remove members from a group (from a group / OU / CSV) (DESTRUCTIVE)",
    "BULK: add ONE user to MANY groups (from a CSV of groups)",
    "BULK: remove ONE user from MANY groups (from a CSV of groups) (DESTRUCTIVE)",
    "BULK: create groups from a CSV", "BULK: delete groups from a CSV (DESTRUCTIVE)"]),
  ("Outside (external) members", [
    "Let a group have outside (external) members",
    "Block outside (external) members in a group"]),
  ("Who can post to a group", [
    "Who can post to a group? (one group)",
    "Who can post - every group - CSV/Sheet",
    "Change who can post to a group",
    "BULK: change who can post - from a CSV",
    "BULK: change who can post - from a Google Sheet"]),
  ("Group settings (join, see, contact, find, post)", [
    "Group settings - one group (join, see, contact, find, post)",
    "Group settings - every group - CSV/Sheet",
    "Change a group's settings",
    "BULK: change group settings - from a CSV",
    "BULK: change group settings - from a Google Sheet"]),
  ("Security, dynamic & locked groups", [
    "Create a security group", "Make an existing group a security group (DESTRUCTIVE)",
    "Create a dynamic group (members by query)", "Lock or unlock a group",
    "Group info (Cloud Identity view)",
    "List groups with Cloud Identity details - CSV/Sheet"]),
 ],
 "Aliases": [
  ("", ["Create alias", "Move an alias to another user or group", "Delete alias",
        "Alias info", "What is this address?", "Export all aliases",
        "BULK: create aliases from a CSV",
        "Bulk delete aliases from a CSV (DESTRUCTIVE)"]),
 ],
 "Org Units": [
  ("", ["Show OU tree", "List OUs (CSV/Sheet)", OU_COUNTS_NAME, "OU info (details and users)",
        "Create OU", "Update / rename OU", "Move users into OU",
        "Is this OU empty? (check before deleting)", "Delete OU (DESTRUCTIVE)",
        "BULK: create OUs from a CSV", "BULK: delete OUs from a CSV (DESTRUCTIVE)"]),
 ],
 "Domains & Domain Aliases": [
  ("", ["List domains", "Domain info", "Add secondary domain",
        "Get a domain verification token", "Verify a domain",
        "List verified sites and domains",
        "Make a domain the primary domain (DESTRUCTIVE)", "Delete domain (DESTRUCTIVE)",
        "List domain aliases", "Domain alias info", "Add domain alias",
        "Delete domain alias (DESTRUCTIVE)"]),
 ],
 "Chromebooks": [
  ("Look up a device", [
    "Device info by serial", "Who used this Chromebook last?", "Find devices (query)",
    "Count devices in a scope", "Device telemetry (battery, storage, CPU, memory)",
    "Get the result of a device command", "Download device files (logs / screenshots)"]),
  ("Change one device", [
    "Move device to OU", "Update device (asset tag / user / location / notes)",
    "Disable / re-enable device"]),
  ("Remote commands (one device)", [
    "Reboot device", "Take a screenshot", "Set device volume",
    "Wipe users from device (DESTRUCTIVE)", "Powerwash device (DESTRUCTIVE)"]),
  ("Bulk changes (many devices)", [
    "BULK: move devices to an OU",
    "BULK: set device fields (asset tag / user / location / notes)",
    "BULK: update asset tags from a CSV", "BULK: disable / re-enable devices",
    "BULK: reboot devices", "BULK: wipe users from devices (DESTRUCTIVE)",
    "BULK: powerwash devices (DESTRUCTIVE)"]),
  ("Retire devices", [
    "Retire Chromebooks: wipe, then deprovision (DESTRUCTIVE)",
    "Deprovision device (retire) (DESTRUCTIVE)",
    "BULK: deprovision devices (retire) (DESTRUCTIVE)"]),
  ("Yearly OU rollover (end of school year)", [
    "Move 'Class of' Chromebook OUs up a grade (yearly rollover)",
    "Move Chromebooks up a grade in grade-named OUs (yearly rollover)"]),
  ("Reports", [
    "Export devices to CSV/Sheet", "Device activity report",
    "Telemetry report (battery/CPU/network/storage) - CSV/Sheet",
    "Devices needing attention - CSV/Sheet",
    "ChromeOS version report (patch compliance) - CSV/Sheet",
    "Device counts (by OU / model / version) - CSV/Sheet",
    "Auto-Update Expiration (AUE) dates - CSV/Sheet",
    "Check serial number validity (enrollable?) - CSV/Sheet",
    "List enrolled Chrome BROWSERS (not Chromebooks) - CSV/Sheet"]),
 ],
 "Chrome Browsers & Policies": [
  ("Chrome browsers", [
    "Chrome browser info", "Move Chrome browsers to an OU",
    "Update a Chrome browser's asset ID / location / notes / user",
    "Delete a Chrome browser (DESTRUCTIVE)"]),
  ("Browser enrollment tokens", [
    "Create a browser enrollment token", "List browser enrollment tokens - CSV/Sheet",
    "Revoke a browser enrollment token (DESTRUCTIVE)"]),
  ("Managed Chrome profiles", [
    "List managed Chrome profiles - CSV/Sheet", "Chrome profile info",
    "Send a command to a Chrome profile (clear cache / cookies)",
    "Show a Chrome profile's command results",
    "Delete a managed Chrome profile (DESTRUCTIVE)"]),
  ("Apps & extensions", [
    "List installed Chrome apps & extensions - CSV/Sheet", BROWSER_EXTS_NAME,
    "Which devices have an app / extension installed - CSV/Sheet",
    "Chrome app / extension info"]),
  ("Chrome policies", [
    "Show Chrome policies for an OU - CSV/Sheet", "Set a Chrome policy for an OU",
    "Remove a Chrome policy from an OU (inherit again) (DESTRUCTIVE)",
    "Look up Chrome policy schemas", "Chrome policy schema details",
    "Upload a wallpaper / avatar image for Chrome policy"]),
  ("Networks & versions", [
    "Create a Chrome network (Wi-Fi / Ethernet / VPN) from JSON",
    "Delete a Chrome network (DESTRUCTIVE)", "Chrome version history - CSV/Sheet"]),
 ],
 "Gmail": [
  ("Delegates (mailbox access)", [
    "Show delegates", "Add delegate", "Remove delegate",
    "Export delegates (whole domain)", "BULK: add a delegate to many mailboxes",
    "BULK: remove a delegate from many mailboxes (DESTRUCTIVE)"]),
  ("Forwarding", [
    "Enable forwarding", "Turn forwarding on (after registering)",
    "Turn forwarding off", "Show forwarding addresses", "Forwarding address info",
    "Delete a forwarding address (DESTRUCTIVE)",
    "Export forwarding addresses (whole domain)",
    "Is mail being auto-forwarded out? (security check)",
    "Check auto-forwarding for EVERYONE (security sweep) - CSV/Sheet",
    "BULK: turn OFF auto-forwarding for many users (security)"]),
  ("Vacation / auto-reply", [
    "Show a mailbox's vacation / auto-reply", "Set vacation responder",
    "Vacation responder off", "Who has auto-reply ON? (whole domain) - CSV/Sheet",
    "BULK: set vacation / auto-reply for many users",
    "BULK: turn OFF vacation / auto-reply for many users", VACATION_HTML_NAME]),
  ("Signatures & send-as addresses", [
    "Show a user's signature", "Set signature",
    "BULK: set email signature for many users", "Show send-as addresses",
    "Send-as info", "Add send-as address",
    "Update send-as (name / signature) (advanced)", "Delete send-as address"]),
  # 2.89: split - a heading holds at most 12 tasks.
  ("Filters", [
    "Show filters", "Gmail filter details", "Create filter", "Delete filter",
    FILTER_FWD_NAME]),
  ("Labels", [
    "Show labels", "Labels with message counts - CSV/Sheet",
    "Count matching messages per label - CSV/Sheet", "Create label", "Rename a Gmail label",
    "Rename or merge labels by pattern (advanced)", "Delete label"]
   + [t["name"] for t in _label_cleanup_tasks()]),
  ("Messages in a mailbox", [
    "Search messages (preview)", MAIL_FROMS_NAME, "Trash messages (DESTRUCTIVE)",
    "Restore (untrash) messages", "Mark messages as spam (DESTRUCTIVE)",
    "Add or remove a label on matching messages",
    "Forward matching messages to someone",
    "Export matching messages to .eml files",
    "Import a message from a file into a mailbox",
    "Archive messages into a Google Group"]),
  ("Send mail & drafts", [
    "Send an email as a user", "BULK: email many users (one message each)",
    "Create a draft in a user's mailbox"]),
  ("Mailbox settings (IMAP, POP, language)", [
    "Turn IMAP on/off", "Turn POP on/off",
    "Export IMAP access status (whole domain) - CSV/Sheet",
    "Export POP access status (whole domain) - CSV/Sheet",
    "Set mailbox language", "Show a user's language setting - CSV/Sheet",
    "Show a user's Gmail profile (message/thread counts) - CSV/Sheet"]),
 ],
 "Calendars": [
  ("Calendar sharing", [
    "Who can access a calendar? (sharing)", "Grant calendar access",
    "Change calendar access level", "Remove calendar access (DESTRUCTIVE)",
    "Who can access a user's calendar? (ACLs) - CSV/Sheet",
    "Export calendar sharing (CSV/Sheet)", "Bulk GRANT calendar access from a CSV",
    "Bulk REMOVE calendar access from a CSV (DESTRUCTIVE)"]),
  ("Events", [
    "List events", EVENT_ATTENDEES_NAME, "Event details", "Add event",
    "Update event(s) (advanced)",
    "Delete event(s) (DESTRUCTIVE)", "Move event(s) to another calendar (advanced)",
    "Import an event by iCalUID (advanced)",
    "Purge specific events permanently (DESTRUCTIVE)"]),
  ("Leaving staff & cleanup", [
    "Delete a user's own future events (DESTRUCTIVE)",
    "Remove a person from future events (DESTRUCTIVE)",
    "Move a user's events to another calendar (e.g. a leaving staff member)",
    "Transfer a calendar to another user",
    "Swap an attendee on events (replace one person with another) (DESTRUCTIVE)",
    "Remove an event from EVERYONE's calendar (phishing invite) (DESTRUCTIVE)",
    "Wipe ALL events from a calendar (DESTRUCTIVE)",
    "Empty a calendar's trash (DESTRUCTIVE)"]),
  ("A user's calendar list (subscribe, show / hide)", [
    "List a user's calendars (CSV/Sheet)", "Calendar info (in a user's list)",
    "Add a calendar to a user's list",
    "Show / hide or recolor a calendar in a user's list",
    "Remove a calendar from a user's list",
    "Bulk show/hide calendars in a user's list from a CSV",
    "BULK: subscribe many users to a calendar",
    "BULK: unsubscribe many users from a calendar (DESTRUCTIVE)",
    "BULK: show / hide / recolor a calendar for many users"]),
  ("Secondary calendars & settings", [
    "Create a secondary calendar (for a user)",
    "Modify a calendar's settings (advanced)",
    "Delete a secondary calendar (DESTRUCTIVE)", "Show a user's calendar settings",
    "Show a user's calendar settings (timezone etc) - CSV/Sheet"]),
  ("Out of office, working location & focus time", [
    "Show a user's out-of-office / working location / focus time",
    "Show out-of-office / working location / focus time",
    "Create an out-of-office block", "Set a user's working location",
    "Create focus time",
    "Remove out-of-office / working location / focus time (DESTRUCTIVE)"]),
 ],
 "Drive": [
  ("Look up a file", [
    "File info", "File details (full, with its folder path)",
    "Where does a file live? (its folder path) - CSV/Sheet",
    "Show a file's folder tree - CSV/Sheet", "Who owns this file? (by ID) - CSV/Sheet",
    "Who owns this file? (by name) - CSV/Sheet", "Is this a shortcut? (check)",
    "List a file's revisions (CSV/Sheet)", "List comments on a file - CSV/Sheet"]),
  ("Look at a user's Drive", [
    "List a user's files", "Count a user's files", DRIVE_DAILY_NAME, DRIVE_ACCESS_NAME,
    "Show a user's folder tree (CSV/Sheet)",
    "How big is a folder? (disk usage) - CSV/Sheet",
    "Show a user's Drive settings - CSV/Sheet",
    "Which of a user's Docs, Sheets and Slides have comments? (counts) - CSV/Sheet",
    "What has a user been doing in Drive? (activity log) - CSV/Sheet",
    "Find empty folders in a user's Drive - CSV/Sheet",
    "Find dormant Drives (last-modified per user) - CSV/Sheet", SHARED_WITH_ME_NAME]),
  ("Sharing", [
    "List a file's sharing (ACLs)", "Share a file/folder",
    "Unshare a file/folder (DESTRUCTIVE)",
    "Bulk SHARE files matching a query (add a person)",
    "Bulk UNSHARE files matching a query (remove a person) (DESTRUCTIVE)",
    "Sharing counts per user (sharing / DLP audit) - CSV/Sheet"]),
  ("Outside sharing & bad files", [
    "Find outside sharing on Shared Drives - CSV report",
    "Find sharing (Shared Drives or users' My Drive) - CSV report",
    "Files that are shared - one row per file (CSV/Sheet)",
    "Files that are NOT shared with anyone (CSV/Sheet)",
    "Sharing with folder paths - one row per permission (CSV/Sheet)",
    "Who has access to each file - one row per file (CSV)",
    "Sharing counts per user - inside vs outside your domains (CSV/Sheet)",
    "Remove outside sharing listed in a report (DESTRUCTIVE)",
    "Put back sharing from an undo file",
    "Remove access to an OUTSIDE file (not owned by us) - by name or ID",
    "PERMANENTLY delete a file from EVERYONE's Drive (by name or ID)"]),
  ("Ownership & transfers", [
    "Transfer ownership of a file/folder", "Claim ownership of a file/folder",
    "Transfer ownership of files matching a query (to another user)",
    "Transfer My Drive to another user",
    "Transfer a user's ENTIRE Drive to another user (offboarding)",
    "Collect orphaned files", "Collect orphaned files into a folder"]),
  ("Upload, create, copy & move", [
    "Upload a file from this PC", "Download a file",
    "Create a folder path (nested folders)",
    "Create a shortcut to a file or folder", "Copy a file/folder",
    "Move a file/folder", "Rename a file or folder",
    "Replace a file's contents from a file on this PC"]),
  ("Trash, restore & delete", [
    DUP_FILES_NAME,
    "Delete a file/folder (DESTRUCTIVE)",
    "Trash files matching a query (from a user's Drive) (DESTRUCTIVE)",
    "Restore (untrash) a file", "Restore (untrash) files matching a query",
    "Permanently purge a trashed file (DESTRUCTIVE)",
    "Empty a user's Drive trash (DESTRUCTIVE)", "Empty a user's Drive trash",
    "Empty EVERYONE's Drive trash (reclaim storage) (DESTRUCTIVE)",
    "Delete old file revisions (DESTRUCTIVE)",
    "Delete empty folders in a user's Drive (cleanup) (DESTRUCTIVE)"]),
  ("Drive labels", [
    "List Drive labels (classification labels) - CSV/Sheet", "Drive label info",
    "Apply or remove a Drive label on a file",
    "List who can use a Drive label - CSV/Sheet",
    "Let a user or group use a Drive label",
    "Remove a user or group from a Drive label (DESTRUCTIVE)"]),
 ],
 "Shared Drives": [
  ("Find & look up", [
    "List Shared Drives", "Shared Drive info", "Shared Drive details (admin)",
    "List Shared Drives grouped by OU (CSV/Sheet)",
    "List Shared Drive memberships (ACLs)",
    "List Shared Drive organizers/managers (CSV/Sheet)",
    "List members of a Shared Drive"]),
  ("Every Shared Drive at once (from Ross Scroggs' scripts)",
   [t["name"] for t in _sd_script_tasks()]
   + ["Shared Drive reports: file counts, storage, last change, file lists (CSV)",
      SD_WRITERS_NAME, SD_ROLES_NAME, SD_EXPAND_NAME]),
  ("Create & change", [
    "Create Shared Drive", "Rename Shared Drive", "Hide Shared Drive",
    "Unhide Shared Drive", "Delete Shared Drive (DESTRUCTIVE)", SD_EMPTY_NAME,
    "Move a user's Drive INTO a NEW Shared Drive (workflow)"]),
  ("Members", [
    "Add member to Shared Drive", "Change member role on Shared Drive",
    "Remove member from Shared Drive (DESTRUCTIVE)",
    "Copy one Shared Drive's members to another",
    "Sync Shared Drive members - exact match (DESTRUCTIVE)"]),
  ("Bulk changes (from a CSV)", [
    "BULK: create Shared Drives from a CSV",
    "BULK: delete Shared Drives from a CSV (DESTRUCTIVE)",
    "BULK: add a member to Shared Drives from a CSV",
    "BULK: remove a member from Shared Drives from a CSV (DESTRUCTIVE)",
    "BULK: move Shared Drives to an OU from a CSV"]),
 ],
 "Classroom": [
  ("Courses", [
    "List courses (by teacher)", "Course info", "Create a course",
    "Bulk create courses from a CSV", "Update course details (advanced)",
    "Change course owner", "Add course alias", "Remove course alias",
    "Delete course (DESTRUCTIVE)"]),
  ("End of year", [
    "Archive course", "Archive ALL active Classrooms (end of year) (DESTRUCTIVE)",
    "Reactivate (restore) an archived course"]),
  ("Teachers & students", [
    "List course participants", "Add teacher to course",
    "Remove teacher from course", "Add student to course",
    "Remove student from course", "Count courses per student or teacher (CSV/Sheet)",
    "Show a user's Classroom profile (CSV/Sheet)"]),
  ("Add or sync from a group / OU / CSV", [
    "Add students from a group (adds only - no removals)",
    "Add students from an OU (adds only - no removals)",
    "Bulk add students from a CSV (adds only)",
    "Sync students from a group (DESTRUCTIVE)", "Sync students from an OU (DESTRUCTIVE)",
    "Add teachers from a group (adds only - no removals)",
    "Add teachers from an OU (adds only - no removals)",
    "Bulk add teachers from a CSV (adds only)",
    "Sync teachers from a group (DESTRUCTIVE)", "Sync teachers from an OU (DESTRUCTIVE)"]),
  ("Course invitations", [
    "Invite a user to a course (invitation)", "Accept a course invitation for a user",
    "Cancel a user's course invitation",
    "List pending Classroom invitations (CSV/Sheet)"]),
  ("Guardians", [
    "List guardians", "Invite guardian", "Bulk invite guardians from a CSV",
    "Cancel a pending guardian invitation", "Remove a guardian link (DESTRUCTIVE)",
    "Sync a student's guardians - exact match (DESTRUCTIVE)",
    "Remove a student's guardians (DESTRUCTIVE)"]),
  ("Class content (work, topics, announcements)", [
    "List coursework/assignments (CSV/Sheet)",
    "List student work submissions (CSV/Sheet)", "List course materials (CSV/Sheet)",
    "List topics (CSV/Sheet)", "Create a course topic",
    "Delete a course topic (DESTRUCTIVE)", "List announcements (CSV/Sheet)",
    "Post an announcement to a class", "Edit or publish an announcement",
    "Delete an announcement (DESTRUCTIVE)"]),
  ("Student groups", [
    "List student groups (CSV/Sheet)",
    "List student-group members in a course - CSV/Sheet",
    "Create a student group", "Rename a student group",
    "Add members to a student group", "Remove a member from a student group",
    "Sync a student group's members (exact match) (DESTRUCTIVE)",
    "Delete a student group (DESTRUCTIVE)",
    "Delete all student groups in a course (DESTRUCTIVE)"]),
 ],
 "Google Meet": [
  ("", ["List a user's Meet conferences - CSV/Sheet",
        "List participants of a meeting (attendance) - CSV/Sheet",
        "List recordings of a meeting - CSV/Sheet",
        "List transcripts of a meeting - CSV/Sheet", "Meet space info",
        "Create a Meet meeting space", "Change a Meet space's settings",
        "End the meeting running in a space (DESTRUCTIVE)"]),
 ],
 "Google Forms": [
  ("", ["Show a form's questions / structure - CSV/Sheet",
        "Export a form's responses - CSV/Sheet", "Create a form",
        "Change a form's title or description", "Open or close a form for responses"]),
 ],
 "Google Chat": [
  ("Spaces", [
    "List all Chat spaces (admin) - CSV/Sheet",
    "List the Chat spaces a user is in - CSV/Sheet", "Chat space info (admin)",
    "Create a Chat space", "Rename or describe a Chat space",
    "Delete a Chat space (admin) (DESTRUCTIVE)"]),
  ("Space members", [
    "List members of a Chat space (admin) - CSV/Sheet",
    "Add a member to a Chat space (admin)",
    "Change a member's role in a Chat space (admin)",
    "Remove a member from a Chat space (admin) (DESTRUCTIVE)"]),
  ("Messages", [
    "List messages in a Chat space - CSV/Sheet",
    "Search a user's Chat messages - CSV/Sheet", "Chat message details",
    "Post a message in a Chat space (as a user)",
    "Post a message as the GAM Chat bot", "Edit a Chat message",
    "Delete a Chat message (DESTRUCTIVE)"]),
  ("Status & custom emoji", [
    "Show a user's Chat status - CSV/Sheet", "Set a user's Chat status",
    "List custom Chat emoji - CSV/Sheet", "Add a custom Chat emoji",
    "Delete a custom Chat emoji (DESTRUCTIVE)"]),
 ],
 "Google Tasks & Keep": [
  ("Google Tasks", [
    "List a user's Google Tasks lists - CSV/Sheet",
    "List a user's Google Tasks - CSV/Sheet", "Task details", "Create a task list",
    "Rename a task list", "Delete a task list (DESTRUCTIVE)", "Create a task",
    "Complete, rename, or edit a task", "Move a task (reorder or make it a subtask)",
    "Delete a task (DESTRUCTIVE)", "Clear completed tasks from a list (DESTRUCTIVE)"]),
  ("Google Keep", [
    "List a user's Google Keep notes - CSV/Sheet", "Keep note details",
    "Create a Keep note", "Share a Keep note", "Stop sharing a Keep note (DESTRUCTIVE)",
    "Download a Keep note's attachments", "Delete a Keep note (DESTRUCTIVE)"]),
 ],
 "Google Sheets & Docs": [
  ("", ["Read a range from a Sheet - CSV/Sheet",
        "Show a spreadsheet's tabs and properties - CSV/Sheet",
        "Append rows to a Sheet from a JSON file",
        "Write values into a Sheet range from a JSON file (DESTRUCTIVE)",
        "Clear a range in a Sheet (DESTRUCTIVE)",
        "Create a spreadsheet from JSON (advanced)", SHEET_PROTECT_NAME,
        "Download a Google Doc as JSON (Docs API)"]),
 ],
 "Licenses": [
  ("", ["Show license counts", "List available license SKUs (names GAM accepts)",
        "List users with a specific license", "Licenses held by a set of users (CSV/Sheet)",
        "Add license to user",
        "Remove license from user",
        "BULK: assign a license to many users (by OU / group / query / CSV)",
        "BULK: remove a license from many users (DESTRUCTIVE)",
        "BULK: swap a license for many users (move A -> B)",
        "BULK: sync a license - exact match (DESTRUCTIVE)",
        "Bulk add/remove licenses (from CSV file)",
        "Bulk add/remove licenses (from Google Sheet)"]),
 ],
 "Vault": [
  ("Matters", [
    "List matters", "Matter info", "Create matter",
    "Update matter (name / description / collaborators)", "Close matter",
    "Reopen matter", "Delete matter (DESTRUCTIVE)", "Undelete matter"]),
  ("Holds", [
    "List holds", "Hold info", "Create hold", "Update hold (add/remove accounts)",
    "Delete hold (DESTRUCTIVE)"]),
  ("Saved searches", [
    "List saved queries (CSV/Sheet)", "Saved query info",
    "Create a saved search query", "Copy a saved search to another matter",
    "Count matching items (before exporting)",
    "Delete a saved query (DESTRUCTIVE)"]),
  ("Exports & downloads", [
    "List exports", "Export info", "Create export", "Download export",
    "Delete export (DESTRUCTIVE)", "Download a Takeout export bucket",
    "Copy a Takeout bucket to your own bucket", "Download one Cloud Storage file"]),
 ],
 PIR_CATEGORY: [("", [PIR_START_NAME, PIR_CHECK_NAME, PIR_CLOSE_NAME, PIR_LIST_NAME])],
 "Mobile Devices": [
  ("", ["List mobile devices", "Mobile device info", "Approve mobile device",
        "Block mobile device", "Account-wipe mobile device (DESTRUCTIVE)",
        "Delete mobile device (DESTRUCTIVE)"]),
 ],
 "Cloud Identity Devices": [
  ("Devices", [
    "List devices (CSV/Sheet)", "Device info",
    "Register a company-owned device (advanced)", "Wipe a device (DESTRUCTIVE)",
    "Cancel a pending device wipe", "Delete a device (DESTRUCTIVE)"]),
  ("Device users", [
    "List device users (CSV/Sheet)", "Device user info", "Approve a device user",
    "Block a device user", "Wipe a device user (DESTRUCTIVE)",
    "Cancel a pending device-user wipe", "Delete a device user (DESTRUCTIVE)"]),
 ],
 "Custom Schemas": [
  ("", ["List schemas", "Schema info", "Create schema (advanced)",
        "Add a field to a schema", "Remove a field from a schema (DESTRUCTIVE)",
        "Delete schema (DESTRUCTIVE)", "Set a user's schema value",
        "BULK: set a schema field for many users from a CSV"]),
 ],
 "Contacts": [
  ("Domain shared contacts", [
    "List domain shared contacts", "List domain contacts - People API (CSV/Sheet)",
    "Contact info", "Create shared contact (advanced)",
    "Update shared contact (advanced)", "BULK: import shared contacts from a CSV",
    "Delete shared contact (DESTRUCTIVE)"]),
  ("A user's contacts", [
    "List a user's personal contacts (CSV/Sheet)",
    "List a user's contact groups (CSV/Sheet)", "Create a contact group (for a user)",
    "Delete a contact group (DESTRUCTIVE)",
    "Remove duplicate personal contacts (DESTRUCTIVE)",
    "Replace a domain in a user's contacts", OLD_CONTACTS_NAME]),
  ("'Other contacts' (auto-saved addresses)", [
    "List a user's 'Other contacts' (CSV/Sheet)",
    "Copy or move 'Other contacts' into My Contacts",
    "Remove a bad address from EVERYONE's 'Other contacts' (DESTRUCTIVE)"]),
  ("Contact delegates", [
    "List a user's contact delegates - CSV/Sheet", "Add a contact delegate",
    "Remove a contact delegate (DESTRUCTIVE)"]),
 ],
 "Admin Roles & Privileges": [
  ("Set up & assign admins", [
    "Set up an administrator (account, roles, OUs)", "List admin role assignments",
    ADMIN_REVIEW_NAME,                                                    # 2.98
    "Assign admin role (whole domain)", "Assign admin role (scoped to an OU)",
    "Assign a TEMPORARY admin role (whole domain)",
    "Assign a TEMPORARY admin role (scoped to an OU)",
    "Remove admin assignment (DESTRUCTIVE)"]),
  ("Roles & privileges", [
    "List admin roles", "Admin role details (privileges)", "List privileges",
    "Create custom admin role", "Rename or edit a custom admin role",
    "Delete a custom admin role (DESTRUCTIVE)"]),
 ],
 "Data Transfers": [
  ("", ["List transferable apps", "Transfer data to another user",
        "List data transfers", "Data transfer info"]),
 ],
 "Chrome Printers": [
  ("", ["List printers", "Printer info", "List printer models",
        "Create printer (advanced)", "Update a printer", "Delete printer (DESTRUCTIVE)"]),
 ],
 "Buildings, Features & Rooms": [
  ("Buildings", [
    "List buildings", "Building info", "Create building", "Update a building",
    "Delete building (DESTRUCTIVE)"]),
  ("Rooms & resources", [
    "List calendar resources (rooms)", "Room / resource info",
    "Create calendar resource (room)", "Update a room / resource",
    "Delete calendar resource (DESTRUCTIVE)"]),
  ("Room features", [
    "List features", "Create feature", "Rename a feature",
    "Delete a feature (DESTRUCTIVE)"]),
 ],
 "Reseller / Channel": [
  ("Customers", [
    "List channel customers - CSV/Sheet", "Reseller customer info",
    "Create a reseller customer", "Update a reseller customer",
    "List channel customer entitlements - CSV/Sheet"]),
  ("Subscriptions", [
    "List reseller subscriptions - CSV/Sheet", "Reseller subscription info",
    "Create a reseller subscription", "Change a subscription's seats",
    "Change a subscription's renewal setting", "Change a subscription's plan",
    "Suspend, activate, or start paid service (DESTRUCTIVE)",
    "Cancel, downgrade, or transfer a subscription (DESTRUCTIVE)"]),
  ("Channel catalog", [
    "List channel offers - CSV/Sheet", "List channel products - CSV/Sheet",
    "List channel SKUs - CSV/Sheet"]),
 ],
 "Marketing & Analytics": [
  ("Google Analytics", [
    "List a user's Google Analytics accounts - CSV/Sheet",
    "List a user's Analytics account summaries - CSV/Sheet",
    "List a user's Analytics properties - CSV/Sheet",
    "List a user's Analytics data streams - CSV/Sheet"]),
  ("Tag Manager", [
    "List a user's Tag Manager accounts - CSV/Sheet",
    "List Tag Manager containers - CSV/Sheet",
    "List Tag Manager workspaces - CSV/Sheet", "List Tag Manager tags - CSV/Sheet",
    "List Tag Manager user permissions - CSV/Sheet"]),
  ("Data Studio (Looker Studio)", [
    "List a user's Data Studio (Looker Studio) permissions - CSV/Sheet",
    "Show a user's Data Studio (Looker Studio) assets",
    "Share Data Studio (Looker Studio) assets with someone",
    "Remove Data Studio (Looker Studio) sharing (DESTRUCTIVE)"]),
  ("Search Console, Business Profile & YouTube", [
    "List a user's Search Console sites - CSV/Sheet",
    "List a user's verified web resources - CSV/Sheet",
    "List a user's Business Profile accounts - CSV/Sheet",
    "List a user's YouTube channels - CSV/Sheet"]),
 ],
 "Customer / Settings": [
  ("", ["Customer info", "Instance info", "Update customer settings (advanced)"]),
 ],
 "Reports": [
  ("", ["Admin activity (7 days)", "Login activity (3 days)",
        "Failed sign-in attempts (7 days)", "Drive activity (7 days)",
        "Token (OAuth) activity (7 days)", "Activity report (advanced)",
        "User usage snapshot", "Customer usage snapshot",
        "ALL users - usage & activity report (CSV/Sheet)",
        "Usage report - users over a date range - CSV/Sheet",
        "Usage report - whole organization over a date range - CSV/Sheet",
        "List usage report parameters - CSV/Sheet"]),
 ],
 "Security": [
  ("Sign-in, 2-Step Verification & app access", [
    "Sign user out everywhere", "Turn 2-Step Verification OFF (DESTRUCTIVE)",
    "2-Step Verification (2SV) enrollment report - CSV/Sheet",
    "Generate backup codes", "Show backup codes",
    "Delete a user's backup codes (DESTRUCTIVE)", "Show app passwords (ASPs)",
    "Delete all app passwords (DESTRUCTIVE)", "Show OAuth tokens",
    "Revoke one app's access", "Deprovision (offboarding)"]),
  ("Mailbox checks", [
    "Mailbox takeover audit (one user)", "Show mailbox rules (Gmail filters)",
    "List email monitors on a mailbox",
    "Create an email monitor (copy a mailbox's mail) (DESTRUCTIVE)",
    "Delete an email monitor (DESTRUCTIVE)"]),
  ("Alert Center", [
    "Show security & admin alerts - CSV/Sheet", "Alert details",
    "Rate an alert (feedback)", "List alert feedback - CSV/Sheet",
    "Delete an alert", "Restore a deleted alert", "Show Alert Center settings",
    "Send alerts to a Pub/Sub topic", "Stop sending alerts to Pub/Sub"]),
  ("S/MIME certificates", [
    "List a user's S/MIME certificates - CSV/Sheet", "Upload an S/MIME certificate",
    "Make an S/MIME certificate the default",
    "Delete an S/MIME certificate (DESTRUCTIVE)"]),
  ("Client-side encryption (CSE)", [
    "List a user's CSE identities - CSV/Sheet", "List a user's CSE key pairs - CSV/Sheet",
    "Create a CSE key pair (advanced)", "Enable or disable a CSE key pair",
    "Permanently destroy a CSE key pair (DESTRUCTIVE)",
    "Create a CSE identity from a key pair", "Delete a CSE identity (DESTRUCTIVE)"]),
 ],
 "Access & Identity (SSO, CAA, Policies)": [
  ("Context-Aware Access levels", [
    "List Context-Aware Access levels - CSV/Sheet",
    "Create a CAA level - allowed IP ranges", "Create a CAA level - allowed countries",
    "Create a CAA level - custom rule (advanced)", "Change a CAA level's rule",
    "Delete a CAA level (DESTRUCTIVE)"]),
  ("Single sign-on (SAML SSO)", [
    "List inbound SSO profiles - CSV/Sheet", "SSO profile info",
    "Create a SAML SSO profile", "Update an SSO profile",
    "Delete an SSO profile (DESTRUCTIVE)", "List SSO signing certificates",
    "Add an SSO signing certificate", "Delete an SSO signing certificate (DESTRUCTIVE)",
    "List SSO assignments - CSV/Sheet", "Turn on SSO (or off) for an OU",
    "Turn on SSO (or off) for a group", "Remove an SSO assignment (DESTRUCTIVE)"]),
  ("Policies & data protection (DLP)", [
    "List Cloud Identity policies - CSV/Sheet", "Cloud Identity policy info",
    "Edit a DLP detector's URL or word list",
    "Create or update a Cloud Identity policy from JSON",
    "Delete a Cloud Identity policy (DESTRUCTIVE)"]),
  ("Allowlisted domains", [
    "List allowlisted domains - CSV/Sheet", "Add allowlisted domains",
    "Remove an allowlisted domain (DESTRUCTIVE)"]),
 ],
 # 2.89 added 5 (MOREnet's investigation tips) - still 12 or fewer, so one
 # list without headings (test_v280_groups).
 "Compromised Account": [
  ("", ["Respond to a compromised account (guided)",
        "Compromised account checklist (steps GAM cannot do)",
        IP_TRACE_NAME, LINK_CLICKS_NAME, SUSPICIOUS_SIGNINS_NAME,
        FOREIGN_SIGNINS_NAME, TAKEOUT_ALL_NAME, ACCOUNT_CHANGES_ALL_NAME,   # 2.90
        LOCK_MANY_NAME, SIGNOUT_MANY_NAME]),
 ],
 "Email Cleanup": [
  ("", ["Search mailboxes (preview)",
        "Find & PERMANENTLY delete a message from ONLY the mailboxes that have it",
        "Full incident-response workflow", "Trash from mailboxes (DESTRUCTIVE)",
        "Delete from mailboxes (DESTRUCTIVE)", "Delete from ONE mailbox (DESTRUCTIVE)"]),
 ],
 # 2.87: Ross Scroggs' scripts (GAM_SCRIPT_FINDS), by where they look.
 "GAM Scripts (Ross Scroggs)": [
  ("Shared Drive sharing", [n for n, w, _x, _y, _z in GAM_SCRIPT_FINDS if w == "shared"]),
  ("Shared Drive members", [t["name"] for t in _sd_script_tasks()[:3]]
                           + [SD_WRITERS_SCRIPT_NAME, "Shared Drive members by role",
                              "Shared Drive members with groups expanded"]),
  ("Shared Drive reports", [n for n, _w, _s in GAM_SCRIPT_SD_EACH]),
  ("My Drive sharing", [n for n, w, _x, _y, _z in GAM_SCRIPT_FINDS if w == "mydrive"]),
  # 2.88: split off (a heading holds at most 12 tasks).
  ("My Drive file reports", [t["name"] for t in _drive_script_tasks()]
                            + ["Who has access to each file (by type and role)",
                               "Duplicate files (find, trash, put back)",
                               "Files created per day by type",
                               "User and group file access counts"]),
  ("Groups", [t["name"] for t in _group_script_tasks()]
             + ["Users not in a group / OU vs group membership",
                "Last message sent to each group"]),
  ("Users, licenses & counts", [_share_count_task()["name"],
                                _license_holder_task()["name"],
                                "Users and Chromebooks per OU"]),
  ("Gmail", ["Gmail filters forwarding outside your domains", "Messages per sender"]),
  ("Calendar", [t["name"] for t in _calendar_script_tasks()]
               + ["Events with one attendee per row"]),
  # 2.89
  ("Chrome & Classroom", ["Chrome browser extension report", GUARDIAN_EMAILS_NAME]),
  ("Clean-up (contacts, vacation, Sheets)", [t["name"] for t in _cleanup_script_tasks()[3:]]),
  ("CSV tools", [t["name"] for t in _csv_tool_tasks(ross=True)]),
 ],
 "Bulk / Batch": [
  # 2.89: + the 10 CSV tools - 12 tasks, so still one list (test_v280_groups).
  ("", ["Bulk: run a command for each CSV row",
        "Bulk: run a command for each Google Sheet row"]
   + [t["name"] for t in _csv_tool_tasks()]),
 ],
 "Diagnostics": [
  ("", ["GAM version", "GAM version (extended)", "Domain info", "OAuth info",
        "Check service account"]),
 ],
}


def task_groups(category):
    # [(heading, [(index, task), ...]), ...] for a category, in display
    # order (TASK_GROUPS). index = the task's position in TASKS[category],
    # which is what the tree and Favorites keep. A task not listed in
    # TASK_GROUPS (added later) appears under "More" at the end.
    tasks = TASKS.get(category, [])
    where = {t["name"]: i for i, t in enumerate(tasks)}
    out, used = [], set()
    for heading, names in TASK_GROUPS.get(category, []):
        items = [(where[n], tasks[where[n]]) for n in names
                 if n in where and where[n] not in used]
        used.update(i for i, _t in items)
        if items:
            out.append((heading, items))
    rest = [(i, t) for i, t in enumerate(tasks) if i not in used]
    if rest:
        out.append(("More" if out else "", rest))
    return out


# Tasks GAMGUI renamed: old name -> new name. Favorites and Recent are saved
# by name, so they are translated when loaded (nothing is lost on update).
TASK_RENAMES = {
    "List a user's Looker Studio (Data Studio) permissions - CSV/Sheet":
        "List a user's Data Studio (Looker Studio) permissions - CSV/Sheet",
    "Show a user's Looker Studio (Data Studio) assets":
        "Show a user's Data Studio (Looker Studio) assets",
    'Share Looker Studio assets with someone':
        'Share Data Studio (Looker Studio) assets with someone',
    'Remove Looker Studio sharing (DESTRUCTIVE)':
        'Remove Data Studio (Looker Studio) sharing (DESTRUCTIVE)',
}


def parse_domain_list(text):
    # "example.org, students.example.org" -> ["example.org", ...]. Raises
    # ValueError for an empty list or anything that is not a domain name.
    items = [d.strip().lower().lstrip("@")
             for d in re.split(r"[,;\s]+", text or "") if d.strip()]
    bad = [d for d in items if not _DOMAIN_NAME.fullmatch(d)]
    if bad:
        raise ValueError("Not a domain name: " + ", ".join(bad))
    if not items:
        raise ValueError("Type your own domain(s), e.g. example.org - list "
                         "every domain you own, sub-domains too.")
    return items


def sd_scan_steps(values, folder, stamp):
    # The three GAM commands of the scan, as [(label, argv)], and the file
    # names used: {"organizers", "members", "files", "report", "notscanned"}.
    # values: own (domains), links ("yes"/"no"), match (drive name text),
    # threads. Raises ValueError for bad input.
    import os
    own = ",".join(parse_domain_list(values.get("own", "")))
    threads = (values.get("threads") or "").strip()
    if threads and not threads.isdigit():
        raise ValueError("Threads must be a whole number (or blank).")
    links = (values.get("links") or "yes").strip().lower() != "no"
    name = (values.get("match") or "").strip()
    # matchname is a regular expression GAM matches from the START of the
    # name (re.match), so ".*" + the escaped text means "name contains".
    match = ["matchname", ".*" + re.escape(name)] if name else []
    files = {key: os.path.join(folder, "SharedDrives-%s-%s.csv" % (part, stamp))
             for key, part in (("organizers", "Organizers"),
                               ("members", "OutsideMembers-raw"),
                               ("files", "OutsideFiles-raw"),
                               ("report", "OutsideSharing"),
                               ("notscanned", "NotScanned"))}
    people = ["pm", "typelist", "domain,group,user", "notdomainlist", own]
    steps = [
        ("Find an organizer in your domains for each Shared Drive",
         ["redirect", "csv", files["organizers"], "print",
          "shareddriveorganizers", "domainlist", own] + match),
        ("Find outside MEMBERS of each Shared Drive",
         ["redirect", "csv", files["members"], "print", "shareddriveacls"]
         + match + people + ["em", "oneitemperrow", "basicpermissions"]),
        ("Find outside sharing on the FILES in each Shared Drive (as its "
         "organizer)",
         ["config", "csv_input_row_filter", "organizers:regex:^.+$"]
         + (["num_threads", threads] if threads else [])
         + ["redirect", "csv", files["files"], "multiprocess",
            "redirect", "stderr", "-", "multiprocess",
            "csv", files["organizers"], "gam", "user", "~organizers",
            "print", "filelist", "select", "teamdriveid", "~id",
            "fields", "teamdriveid,id,name,mimetype,webviewlink,basicpermissions",
            "showdrivename"]
         + people + ["inherited", "false", "em"]
         + (["pm", "type", "anyone", "inherited", "false", "em"] if links else [])
         + ["pmfilter", "oneitemperrow"]),
    ]
    return steps, files


def _true(value):
    return str(value or "").strip().lower() == "true"


def sd_build_report(member_rows, file_rows, organizer_rows, keep_deleted=False):
    # Turns GAM's raw CSVs into GAMGUI's report rows (SD_REPORT_COLUMNS) and
    # the list of drives that could not be scanned. Returns (rows, notscanned).
    # keep_deleted (2.87, Find sharing's "deleted users or groups"): keep the
    # permissions of deleted users / groups (their target shows "(deleted)").
    def one(where, drive_name, drive_id, title, doc_id, mime, link, act_as, r):
        kind = (r.get("permission.type") or "").strip().lower()
        target = (r.get("permission.emailAddress") or "").strip().lower()
        if kind == "domain":
            target = (r.get("permission.domain") or "").strip().lower()
        if _true(r.get("permission.deleted")):
            target = target or "(deleted)"
        return {"where": where, "drive_name": drive_name, "drive_id": drive_id,
                "doc_title": title, "doc_id": doc_id, "mime_type": mime,
                "link": link, "act_as": (act_as or "").strip().lower(),
                "perm_id": (r.get("permission.id") or "").strip(),
                "kind": kind, "target": target,
                "role": (r.get("permission.role") or "").strip(),
                "discoverable": "true" if _true(r.get("permission.allowFileDiscovery"))
                                else "false"}
    rows = []
    for r in member_rows:
        if (_true(r.get("permission.deleted")) and not keep_deleted) \
                or not r.get("permission.id"):
            continue
        rows.append(one("drive", r.get("name", ""), r.get("id", ""),
                        "(the Shared Drive itself - a member)", r.get("id", ""),
                        "shared drive", "", "", r))
    for r in file_rows:
        if (_true(r.get("permission.deleted")) and not keep_deleted) \
                or not r.get("permission.id"):
            continue
        rows.append(one("file", r.get("driveName", ""), r.get("driveId", ""),
                        r.get("name", ""), r.get("id", ""), r.get("mimeType", ""),
                        r.get("webViewLink", ""), r.get("Owner", ""), r))
    notscanned = [{"drive_id": r.get("id", ""), "drive_name": r.get("name", ""),
                   "why": "no organizer in your domains - add one, then scan again"}
                  for r in organizer_rows if not (r.get("organizers") or "").strip()]
    return rows, notscanned


# =============================================================================
# SECTION: Find sharing - Shared Drives or users' My Drive (2.87)
# =============================================================================
# Ross Scroggs' GAM-Scripts for Drive / Shared Drive sharing (Get...DriveACLs,
# Get...TeamDriveACLs) list GAM's files and then filter the permissions in
# Python. GAM now does that filtering itself with permission matching
# (<PermissionMatch> ... em, pmfilter, oneitemperrow - GamCommands.txt 7.48.23;
# Ross: "some of them have been superceded by commands"). This builds those
# GAM commands; the report has the Shared Drive scan's columns
# (SD_REPORT_COLUMNS), so 'Remove outside sharing listed in a report' and
# 'Put back sharing from an undo file' work on it unchanged.
# Checked in GAM's source (gam/__init__.py, PermissionMatch): 'withlink true'
# means allowFileDiscovery FALSE (link only); allowfilediscovery / withlink
# need type anyone or domain in the same match; several pm clauses are ORed
# (pmm or is the default).
_FIND_LIST_MAX = 500          # Windows command lines are limited to ~32,000 characters


def find_list(values):
    # The domains / addresses for the "these ..." choices: the box (comma
    # separated) plus, when given, a CSV file's column. Lower case, no
    # repeats. ValueError for a problem.
    import csv as _csv
    out = []
    for item in re.split(r"[,\s]+", (values.get("list") or "").strip()):
        if item and item.lower() not in out:
            out.append(item.lower())
    path = (values.get("listcsv") or "").strip()
    if path:
        column = (values.get("listcol") or "").strip()
        try:
            with open(path, encoding="utf-8-sig", newline="") as handle:
                reader = _csv.DictReader(handle)
                if not column:
                    column = (reader.fieldnames or [""])[0]
                if column not in (reader.fieldnames or []):
                    raise ValueError("The CSV has no column '%s' (it has: %s)."
                                     % (column, ", ".join(reader.fieldnames or [])))
                for row in reader:
                    item = (row.get(column) or "").strip().lower()
                    if item and item not in out:
                        out.append(item)
        except OSError as exc:
            raise ValueError("Cannot read the CSV file: %s" % exc)
    if len(out) > _FIND_LIST_MAX:
        raise ValueError("That is %d entries - at most %d at a time (split the "
                         "list)." % (len(out), _FIND_LIST_MAX))
    return out


def find_pm(what, values, own, inherited_too=True):
    # GAM's <PermissionMatch> clauses for one "what" choice. inherited_too
    # False adds 'inherited false' (only sharing set on the file itself -
    # Shared Drive files inherit the drive's members).
    inh = [] if inherited_too else ["inherited", "false"]

    def clause(*words):
        return ["pm"] + list(words) + inh + ["em"]
    if what == "outside":
        if not own:
            raise ValueError("Enter your own domains (comma separated).")
        out = clause("typelist", "domain,group,user", "notdomainlist", ",".join(own))
        if (values.get("anyone") or "yes") == "yes":
            out += clause("type", "anyone")
        return out
    if what == "anyone":
        return clause("type", "anyone")
    if what == "public":
        return clause("type", "anyone", "allowfilediscovery", "true")
    if what == "anyonelink":
        return clause("type", "anyone", "withlink", "true")
    if what == "link":
        return clause("type", "anyone", "withlink", "true") + \
            clause("type", "domain", "withlink", "true")
    if what == "findable":
        return clause("type", "anyone", "allowfilediscovery", "true") + \
            clause("type", "domain", "allowfilediscovery", "true")
    if what in ("domains", "groups", "users"):
        items = find_list(values)
        if not items:
            raise ValueError("Enter the %s (comma separated), or a CSV file with "
                             "them." % {"domains": "domains", "groups": "group "
                                        "addresses", "users": "user addresses"}[what])
        if what == "domains":
            bad = [d for d in items if not _DOMAIN_NAME.fullmatch(d)]
            if bad:
                raise ValueError("Not a domain name: " + ", ".join(bad[:5]))
            return clause("domainlist", ",".join(items))
        bad = [a for a in items if not _PLAIN_EMAIL.fullmatch(a)]
        if bad:
            raise ValueError("Not an email address: " + ", ".join(bad[:5]))
        return clause("type", what[:-1], "emailaddresslist", ",".join(items))
    if what == "deleted":
        return clause("deleted", "true")
    if what == "everything":
        return clause("notrole", "owner")
    if what == "guests":
        # GAM keeps permissions set on the FILE (permissionDetails.0.
        # permissionType = file - Ross's own pre-filter); a drive member with
        # extra access on one file also matches, so run_find_sharing then
        # drops the drive's own members (find_guests). No 'inherited' here:
        # GAM checks the two permissionDetails tests one after the other on a
        # trimmed list (PermissionMatch.CheckPermissionMatch), so they are
        # not combined.
        return ["pm", "typelist", "domain,group,user", "permtype", "file", "em"]
    if what == "nonaccount":
        # Every USER permission; run_find_sharing drops the ones whose
        # address (or alias) is an account here (find_disabled reads both
        # lists).
        return clause("type", "user")
    if what == "suspended":
        # Every USER permission; run_find_sharing keeps the ones whose
        # address (or alias) belongs to a suspended / archived account
        # (find_disabled) - GAM cannot match "suspended" itself (Ross's
        # scripts filter the same way).
        return clause("type", "user")
    if what == "onlysuspended":
        # All of each file's sharing except the owner; run_find_sharing keeps
        # a file only when EVERY entry is a disabled account (find_only_disabled).
        return clause("notrole", "owner")
    raise ValueError("Choose what to look for.")


def find_only_disabled(report_rows, disabled):
    # The rows of files whose every sharing entry is a user in 'disabled'.
    by_doc = {}
    for row in report_rows:
        by_doc.setdefault(row["doc_id"], []).append(row)
    return [row for row in report_rows
            if all(r["kind"] == "user" and r["target"] in disabled
                   for r in by_doc[row["doc_id"]])]


def find_disabled(user_rows):
    # GAM's 'print users isdisabled true fields primaryemail,aliases' rows ->
    # every address of those accounts (primary + aliases.N), lower case.
    out = set()
    for row in user_rows:
        for key, value in row.items():
            if (key == "primaryEmail" or key.startswith("aliases.")
                    or key.startswith("nonEditableAliases.")) and "@" in (value or ""):
                out.add(value.strip().lower())
    return out


def find_guests(member_rows, report_rows):
    # Ross's GetTeamDriveGuestMembers.py: keep only the report rows whose
    # user / group / domain is NOT a member of that file's Shared Drive.
    # member_rows = GAM's print shareddriveacls oneitemperrow rows.
    members = {}
    for r in member_rows:
        kind = (r.get("permission.type") or "").strip().lower()
        who = (r.get("permission.domain") if kind == "domain"
               else r.get("permission.emailAddress")) or ""
        if kind in ("user", "group", "domain") and who.strip():
            members.setdefault((r.get("id") or "").strip(), set()).add(
                (kind, who.strip().lower()))
    return [row for row in report_rows
            if (row["kind"], row["target"]) not in members.get(row["drive_id"], set())]


def find_sharing_steps(values, folder, stamp):
    # The read-only GAM commands of "Find sharing", as [(label, argv)], and
    # the file names: {"organizers", "members", "files", "report",
    # "notscanned"} (organizers / members only for Shared Drives).
    import os
    where = values.get("where") or "shared"
    what = values.get("what") or ""
    meta = [w for w in FIND_WHAT if w[0] == what]
    if where not in ("shared", "mydrive") or not meta:
        raise ValueError("Choose where to look and what to look for.")
    _key, _label, _needs, members_too = meta[0]
    if what == "guests" and where != "shared":
        raise ValueError("Guests are people with access to a Shared Drive's files "
                         "who are not members of the drive - choose Shared Drives.")
    # Your own domains: needed for Shared Drives (an organizer in them reads
    # each drive) and for "outside"; blank is fine otherwise.
    own = parse_domain_list(values.get("own", "")) if (values.get("own") or "").strip() \
        else []
    threads = (values.get("threads") or "").strip()
    if threads and not threads.isdigit():
        raise ValueError("Threads must be a whole number (or blank).")
    tprefix = ["num_threads", threads] if threads else []
    inherited_too = (values.get("inherited") or "yes") == "yes"
    pm = find_pm(what, values, own, inherited_too)
    base = "SharedDrives" if where == "shared" else "MyDrive"
    files = {key: os.path.join(folder, "%s-%s-%s.csv" % (base, part, stamp))
             for key, part in (("organizers", "Organizers"), ("members", "Members-raw"),
                               ("files", "Files-raw"), ("report", "Sharing-" + what),
                               ("notscanned", "NotScanned"), ("disabled", "Disabled-raw"))}
    fields = ["fields", "id,name,mimetype,webviewlink,basicpermissions"]
    # 2.88: 'suspended' first lists the suspended / archived accounts
    # (isdisabled: GAM 7.45+), with their aliases.
    first = [("List SUSPENDED and ARCHIVED users (with their aliases)",
              ["redirect", "csv", files["disabled"], "print", "users", "isdisabled",
               "true", "fields", "primaryemail,aliases"])] \
        if what in ("suspended", "onlysuspended") else []
    if what == "nonaccount":
        # Every account here (active or not) - anyone else has no account.
        first = [("List EVERY user account here (with their aliases)",
                  ["redirect", "csv", files["disabled"], "print", "users", "fields",
                   "primaryemail,aliases"])]
    if where == "shared":
        if not own:
            raise ValueError("Enter your own domains - each Shared Drive is read "
                             "as one of its organizers in them.")
        name = (values.get("match") or "").strip()
        match = ["matchname", ".*" + re.escape(name)] if name else []
        steps = first + [("Find an organizer in your domains for each Shared Drive",
                          ["redirect", "csv", files["organizers"], "print",
                           "shareddriveorganizers", "domainlist", ",".join(own)] + match)]
        if members_too:
            steps.append(("Check each Shared Drive's own MEMBERS",
                          ["redirect", "csv", files["members"], "print", "shareddriveacls"]
                          # A drive's members are never "anyone" - no link clause.
                          + match + find_pm(what, dict(values, anyone="no"), own)
                          + ["oneitemperrow", "basicpermissions"]))
        if what == "guests":
            # Every member of every drive - to leave them out (find_guests).
            steps.append(("List each Shared Drive's MEMBERS (they are not guests)",
                          ["redirect", "csv", files["members"], "print", "shareddriveacls"]
                          + match + ["oneitemperrow", "basicpermissions"]))
        steps.append(("Check the FILES in each Shared Drive (as its organizer)",
                      ["config", "csv_input_row_filter", "organizers:regex:^.+$"] + tprefix
                      + ["redirect", "csv", files["files"], "multiprocess", "redirect",
                         "stderr", "-", "multiprocess", "csv", files["organizers"], "gam",
                         "user", "~organizers", "print", "filelist", "select",
                         "teamdriveid", "~id"] + fields[:1]
                      + ["teamdriveid," + fields[1], "showdrivename"]
                      + pm + ["pmfilter", "oneitemperrow"]))
        return steps, files
    who = values.get("who") or ""
    whoval = (values.get("whoval") or "").strip()
    if who not in FIND_WHO.values():
        raise ValueError("Choose whose My Drive to check.")
    if who != "all" and not whoval:
        raise ValueError("Enter the user(s), OU or group.")
    entity = ["all", "users"] if who == "all" else [who, whoval]
    # auto_batch_min 1: GAM checks the users in parallel (Ross's own steps).
    return first + [("Check the files each user OWNS",
             ["config", "auto_batch_min", "1"] + tprefix
             + ["redirect", "csv", files["files"], "multiprocess", "redirect", "stderr",
                "-", "multiprocess"] + entity
             + ["print", "filelist", "showownedby", "me"] + fields + pm
             + ["pmfilter", "oneitemperrow"])], files


# "Shared Drive reports" (2.87): one GAM command per Shared Drive, run as
# one of its organizers - Ross's GetTeamDriveFileCounts / CountsSize /
# StorageInfo / LastModified / FileLists, done by GAM now (wiki: Shared
# Drives - Display Shared Drive Storage Info; Users Drive Files Display -
# Display information about last modified file on a drive). Every command
# was read by gam.exe 7.48.23. key -> (label, the per-drive GAM words)


def sd_each_steps(values, folder, stamp):
    # [(label, argv)] and {"organizers", "report", "notscanned"} for a
    # Shared Drive report. Read-only.
    import os
    what = values.get("what") or ""
    if what not in SD_EACH:
        raise ValueError("Choose which report.")
    if not (values.get("own") or "").strip():
        raise ValueError("Enter your own domains - each Shared Drive is read as one "
                         "of its organizers in them.")
    own = parse_domain_list(values.get("own", ""))
    threads = (values.get("threads") or "").strip()
    if threads and not threads.isdigit():
        raise ValueError("Threads must be a whole number (or blank).")
    name = (values.get("match") or "").strip()
    match = ["matchname", ".*" + re.escape(name)] if name else []
    files = {key: os.path.join(folder, "SharedDrives-%s-%s.csv" % (part, stamp))
             for key, part in (("organizers", "Organizers"),
                               ("report", {"counts": "FileCountsStorage",
                                           "lastmod": "LastModified",
                                           "files": "FileLists"}[what]),
                               ("notscanned", "NotScanned"))}
    return [("Find an organizer in your domains for each Shared Drive",
             ["redirect", "csv", files["organizers"], "print", "shareddriveorganizers",
              "domainlist", ",".join(own)] + match),
            ("Run the report on each Shared Drive (as its organizer)",
             ["config", "csv_input_row_filter", "organizers:regex:^.+$"]
             + (["num_threads", threads] if threads else [])
             + ["redirect", "csv", files["report"], "multiprocess", "redirect", "stderr",
                "-", "multiprocess", "csv", files["organizers"], "gam", "user",
                "~organizers"] + SD_EACH[what][1]
             + ["addcsvdata", "driveName", "~name"])], files


# "Upgrade Shared Drive Contributors to Content managers" (sdwriters, 2.87):
# Ross's UpgradeWritersToContentManagers.py, done by GAM now. Read every
# Shared Drive's Contributors (API role 'writer') with admin rights, save
# them as a record, then 'update drivefileacl shareddriveid <drive> id:<perm>
# role contentmanager' for each (GAM source: doUpdateDriveFileACLs uses
# admin access; 'contentmanager' -> fileOrganizer). The record puts them
# back (role writer). Every command was read by gam.exe 7.48.23. The
# form and the tasks are near _sd_writers_tasks (they are needed when the
# task list is built).
def sd_writers_read_step(values, folder, stamp):
    # (label, argv) and the record / GAM-file paths for the read step.
    import os
    name = (values.get("match") or "").strip()
    # matchname is a regular expression GAM checks from the START of the
    # name, so ".*" + the escaped text = "contains".
    match = ["matchname", ".*" + re.escape(name)] if name else []
    files = {"gam": os.path.join(folder, "SharedDrives-Writers-GAM-%s.csv" % stamp),
             "record": os.path.join(folder, "SharedDrives-Contributors-%s.csv" % stamp)}
    return ("List every Contributor of every Shared Drive (admin)",
            ["redirect", "csv", files["gam"], "print", "shareddriveacls", "role",
             "writer", "oneitemperrow"] + match), files


def sd_roles_steps(values, folder, stamp):
    # "Shared Drive members by role": ONE read-only GAM command, then
    # sd_roles_report pivots it. shownopermissionsdrives true keeps drives
    # with no members (GAM source: printShowSharedDriveACLs writes the
    # drive's id / name / createdTime row with no permission columns).
    import os
    if (values.get("types") or "all") not in SD_ROLES_TYPES.values():
        raise ValueError("Choose which members to list.")
    if (values.get("domains") or "").strip():
        parse_domain_list(values["domains"])          # ValueError for a bad one
    name = (values.get("match") or "").strip()
    match = ["matchname", ".*" + re.escape(name)] if name else []
    files = {"raw": os.path.join(folder, "SharedDrives-Members-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "SharedDrives-MembersByRole-%s.csv" % stamp)}
    return [("List every member of every Shared Drive (admin)",
             ["redirect", "csv", files["raw"], "print", "shareddriveacls"] + match
             + ["oneitemperrow", "shownopermissionsdrives", "true"])], files


def sd_roles_report(gam_rows, values):
    # GAM's rows -> (headings, one row per drive). Ross's version looked the
    # drive up by Python's built-in 'id' and failed on domain members; this
    # one keys on the drive ID and lists a domain member by its domain.
    types = values.get("types") or "all"
    domains = parse_domain_list(values["domains"]) if (values.get("domains") or "").strip() \
        else []
    sep = {"space": " ", "comma": ", ", "newline": "\n"}[values.get("sep") or "space"]
    gui = (values.get("names") or "gui") == "gui"
    heads = [g if gui else a for a, g in SD_ROLES]
    drives = {}
    for r in gam_rows:
        drive = (r.get("id") or "").strip()
        if not drive:
            continue
        entry = drives.setdefault(drive, {"id": drive, "name": r.get("name", ""),
                                          "createdTime": r.get("createdTime", ""),
                                          "roles": {a: [] for a, _g in SD_ROLES}})
        kind = (r.get("permission.type") or "").strip().lower()
        role = (r.get("permission.role") or "").strip()
        if not kind or role not in entry["roles"] or _true(r.get("permission.deleted")):
            continue
        if types != "all" and kind != types:
            continue
        who = (r.get("permission.domain") if kind == "domain"
               else r.get("permission.emailAddress")) or ""
        who = who.strip().lower()
        if not who:
            continue
        member_domain = who if kind == "domain" else who.split("@")[-1]
        if domains and member_domain not in domains:
            continue
        if who not in entry["roles"][role]:
            entry["roles"][role].append(who)
    rows = []
    for entry in sorted(drives.values(), key=lambda e: e["name"].lower()):
        row = {"id": entry["id"], "name": entry["name"], "createdTime": entry["createdTime"]}
        for (api, _g), head in zip(SD_ROLES, heads):
            row[head] = sep.join(sorted(entry["roles"][api]))
        rows.append(row)
    return ["id", "name", "createdTime"] + heads, rows


def sd_expand_steps(values, folder, stamp):
    # (step 1, step 2) and the file paths. Step 2 reads only the groups that
    # step 1 found (gam_workflows writes them to files["groups"] first);
    # csvfile <path>:group - GAM splits off a Windows drive letter
    # (os.path.splitdrive) before looking for the ':column'.
    import os
    name = (values.get("match") or "").strip()
    match = ["matchname", ".*" + re.escape(name)] if name else []
    files = {key: os.path.join(folder, "SharedDrives-%s-%s.csv" % (part, stamp))
             for key, part in (("members", "Members-raw"), ("groups", "Groups-raw"),
                               ("groupmembers", "GroupMembers-raw"),
                               ("report", "MembersExpanded"))}
    return ([("List every member of every Shared Drive (admin)",
              ["redirect", "csv", files["members"], "print", "shareddriveacls"] + match
              + ["oneitemperrow"]),
             ("List the people in those groups (groups inside groups too)",
              # 'select csvfile' goes LAST: a csvfile selector takes its own
              # 'fields <headers>' option, so a 'fields' after it is eaten
              # (found with gam.exe 7.48.24).
              ["redirect", "csv", files["groupmembers"], "print", "group-members",
               "fields", "email,type", "recursive", "select", "csvfile",
               files["groups"] + ":group"])], files)


def sd_expand_groups(member_rows):
    # The group addresses that are Shared Drive members (lower case, sorted).
    return sorted({(r.get("permission.emailAddress") or "").strip().lower()
                   for r in member_rows
                   if (r.get("permission.type") or "").strip().lower() == "group"
                   and not _true(r.get("permission.deleted"))
                   and (r.get("permission.emailAddress") or "").strip()})


def sd_expand_report(member_rows, group_rows, keep_group=False):
    # Drive members + group members -> SD_EXPAND_COLUMNS rows. A group row
    # becomes one row per USER in it (GAM's 'recursive' gives level and
    # subgroup); a group with no people left (empty, or GAM could not read
    # it) keeps its own row so it is never silently dropped.
    roles = dict(SD_ROLES)
    people = {}
    for g in group_rows:
        if (g.get("type") or "").strip().upper() != "USER":
            continue
        people.setdefault((g.get("group") or "").strip().lower(), []).append(g)
    rows = []
    for r in member_rows:
        kind = (r.get("permission.type") or "").strip().lower()
        if not kind or _true(r.get("permission.deleted")):
            continue
        who = ((r.get("permission.domain") if kind == "domain"
                else r.get("permission.emailAddress")) or "").strip().lower()
        base = {"drive_id": r.get("id", ""), "drive_name": r.get("name", ""),
                "role": roles.get((r.get("permission.role") or "").strip(),
                                  r.get("permission.role", "")),
                "member": who, "member_type": kind, "via_group": "", "level": "",
                "subgroup": ""}
        inside = people.get(who, []) if kind == "group" else []
        if kind != "group" or keep_group or not inside:
            rows.append(base)
        for g in inside:
            rows.append(dict(base, member=(g.get("email") or "").strip().lower(),
                             member_type="user", via_group=who,
                             level=g.get("level", ""),
                             subgroup=(g.get("subgroup") or "").strip().lower()))
    return rows


def file_roles_steps(values, folder, stamp):
    # One read-only GAM command (Ross's own: every non-owner permission of
    # each file the user(s) own, one per row), then file_roles_report.
    import os
    who = values.get("who") or ""
    whoval = (values.get("whoval") or "").strip()
    if who not in FIND_WHO.values():
        raise ValueError("Choose whose files to check.")
    if who != "all" and not whoval:
        raise ValueError("Enter the user(s), OU or group.")
    threads = (values.get("threads") or "").strip()
    if threads and not threads.isdigit():
        raise ValueError("Threads must be a whole number (or blank).")
    entity = ["all", "users"] if who == "all" else [who, whoval]
    files = {"raw": os.path.join(folder, "MyDrive-Permissions-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "MyDrive-AccessByRole-%s.csv" % stamp)}
    return [("List the sharing of every file the user(s) own",
             ["config", "auto_batch_min", "1"] + (["num_threads", threads] if threads else [])
             + ["redirect", "csv", files["raw"], "multiprocess", "redirect", "stderr", "-",
                "multiprocess"] + entity
             + ["print", "filelist", "showownedby", "me", "fields",
                "id,name,mimetype,webviewlink,basicpermissions", "pm", "notrole", "owner",
                "em", "pmfilter", "oneitemperrow"])], files


def file_roles_report(gam_rows, values):
    # GAM's rows (one permission each) -> (headings, one row per file).
    sep = {"space": " ", "comma": ", ", "newline": "\n"}[values.get("sep") or "space"]
    counts = (values.get("counts") or "no") == "yes"
    roles = dict(FILE_ROLE_NAMES)
    columns = []
    for kind, label, only in FILE_ROLE_TYPES:
        for role, name in FILE_ROLE_NAMES:
            if only is None or role in only:
                columns.append((kind, role, "%s - %s" % (label, name)))
    found = {}
    for r in gam_rows:
        doc = (r.get("id") or "").strip()
        if not doc or _true(r.get("permission.deleted")):
            continue
        entry = found.setdefault(doc, {"Owner": r.get("Owner", ""), "id": doc,
                                       "name": r.get("name", ""),
                                       "mimeType": r.get("mimeType", ""),
                                       "webViewLink": r.get("webViewLink", ""), "lists": {}})
        kind = (r.get("permission.type") or "").strip().lower()
        role = (r.get("permission.role") or "").strip()
        if role not in roles:
            continue
        if kind == "anyone":
            who = "anyone" if _true(r.get("permission.allowFileDiscovery")) else "anyone with the link"
        elif kind == "domain":
            who = (r.get("permission.domain") or "").strip().lower()
        else:
            who = (r.get("permission.emailAddress") or "").strip().lower()
        if who and who not in entry["lists"].setdefault((kind, role), []):
            entry["lists"][(kind, role)].append(who)
    heads = ["Owner", "id", "name", "mimeType", "webViewLink"]
    for _k, _r, head in columns:
        heads.append(head)
        if counts:
            heads.append(head + " (count)")
    rows = []
    for entry in sorted(found.values(), key=lambda e: (e["Owner"].lower(), e["name"].lower())):
        row = {h: entry[h] for h in heads[:5]}
        for kind, role, head in columns:
            names = sorted(entry["lists"].get((kind, role), []))
            row[head] = sep.join(names)
            if counts:
                row[head + " (count)"] = len(names)
        rows.append(row)
    return heads, rows


def _filelist_step(values, raw, fields, extra=()):
    # '<users> print filelist showownedby me fields ...' into raw (parallel).
    who = user_scope_argv(values)
    return (["config", "auto_batch_min", "1", "redirect", "csv", raw, "multiprocess",
             "redirect", "stderr", "-", "multiprocess"] + who
            + ["print", "filelist", "showownedby", "me", "fields", fields] + list(extra))


def dup_files_steps(values, folder, stamp):
    import os
    files = {"raw": os.path.join(folder, "MyDrive-Files-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "MyDrive-DuplicateFiles-%s.csv" % stamp)}
    extra = ["filepath"] + ([] if (values.get("folders") or "no") == "yes"
                            else ["showmimetype", "not", "gfolder"])
    return [("List the files each user owns (name, type, created, folder path)",
             _filelist_step(values, files["raw"], "id,name,mimetype,createdtime,webviewlink",
                            extra))], files


def dup_files_rows(file_rows):
    # Ross's rule: same owner, name, type and folder path(s) -> the NEWEST is
    # kept, every older copy is returned. Each file once (GAM can repeat a
    # file per path - all its paths count together).
    files = {}
    for r in file_rows:
        fid = (r.get("id") or "").strip()
        if not fid:
            continue
        entry = files.setdefault(fid, {"row": r, "paths": set()})
        for key, value in r.items():
            if re.fullmatch(r"path\.\d+", key or "") and value:
                entry["paths"].add(value)
    groups = {}
    for fid, entry in files.items():
        r = entry["row"]
        key = ((r.get("Owner") or "").lower(), r.get("name") or "", r.get("mimeType") or "",
               frozenset(entry["paths"]))
        groups.setdefault(key, []).append(r)
    out = []
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        rows = sorted(rows, key=lambda x: x.get("createdTime") or "", reverse=True)
        for r in rows[1:]:
            out.append({"Owner": r.get("Owner", ""), "id": r.get("id", ""),
                        "name": r.get("name", ""), "mimeType": r.get("mimeType", ""),
                        "createdTime": r.get("createdTime", ""),
                        "path": sorted(key[3])[0] if key[3] else "",
                        "kept_id": rows[0].get("id", ""),
                        "webViewLink": r.get("webViewLink", "")})
    return sorted(out, key=lambda r: (r["Owner"].lower(), r["path"].lower(), r["name"].lower()))


DUP_FILES_COLUMNS = ["Owner", "id", "name", "mimeType", "createdTime", "path", "kept_id",
                     "webViewLink"]


def dup_files_check_report(rows):
    if not rows:
        raise ValueError("The file has no rows.")
    for number, row in enumerate(rows, 2):
        if not _PLAIN_EMAIL.fullmatch((row.get("Owner") or "").strip().lower()) or \
                not re.fullmatch(r"[A-Za-z0-9_-]{10,}", (row.get("id") or "").strip()):
            raise ValueError("Row %d has no Owner / file id - use the MyDrive-"
                             "DuplicateFiles-...csv this task made." % number)
    return rows


def drive_daily_steps(values, folder, stamp):
    import os
    files = {"raw": os.path.join(folder, "MyDrive-Created-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "MyDrive-CreatedPerDay-%s.csv" % stamp)}
    return [("List each file's created time and type",
             _filelist_step(values, files["raw"], "id,createdtime,mimetype"))], files


# Friendly names for the commonest types (others keep Google's own name).
MIME_NAMES = {
    "application/vnd.google-apps.document": "Google Docs",
    "application/vnd.google-apps.spreadsheet": "Google Sheets",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.form": "Google Forms",
    "application/vnd.google-apps.drawing": "Google Drawings",
    "application/vnd.google-apps.folder": "Folders",
    "application/vnd.google-apps.shortcut": "Shortcuts",
    "application/pdf": "PDF",
    "image/jpeg": "JPEG images", "image/png": "PNG images",
    "video/mp4": "MP4 videos",
}


def drive_daily_report(rows):
    counts, types = {}, set()
    for r in rows:
        created = (r.get("createdTime") or "")[:10]
        if not created:
            continue
        kind = MIME_NAMES.get(r.get("mimeType") or "", r.get("mimeType") or "other")
        types.add(kind)
        day = counts.setdefault(((r.get("Owner") or "").lower(), created), {})
        day[kind] = day.get(kind, 0) + 1
    heads = ["Owner", "day", "total"] + sorted(types)
    out = []
    for (owner, day), kinds in counts.items():
        row = {"Owner": owner, "day": day, "total": sum(kinds.values())}
        row.update({k: kinds.get(k, 0) for k in types})
        out.append(row)
    out.sort(key=lambda r: r["day"], reverse=True)      # newest day first...
    out.sort(key=lambda r: r["Owner"])                  # ...within each owner (stable)
    return heads, out


def drive_access_steps(values, folder, stamp):
    import os
    files = {"raw": os.path.join(folder, "MyDrive-Permissions-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "MyDrive-AccessCounts-%s.csv" % stamp)}
    return [("List every permission of the files the users own",
             _filelist_step(values, files["raw"], "id,name,basicpermissions",
                            ["oneitemperrow"]))], files


def drive_access_report(rows):
    # -> rows: type, address, Owner, Editor, Commenter, Viewer, total files.
    names = {"owner": "Owner", "writer": "Editor", "commenter": "Commenter",
             "reader": "Viewer", "fileOrganizer": "Content manager", "organizer": "Manager"}
    counts = {}
    for r in rows:
        kind = (r.get("permission.type") or "").strip().lower()
        if kind not in ("user", "group") or _true(r.get("permission.deleted")):
            continue
        who = (r.get("permission.emailAddress") or "").strip().lower()
        role = names.get((r.get("permission.role") or "").strip())
        if not who or not role:
            continue
        entry = counts.setdefault((kind, who), {})
        entry[role] = entry.get(role, 0) + 1
    heads = ["type", "address", "Owner", "Editor", "Commenter", "Viewer", "Content manager",
             "Manager", "total"]
    out = [dict({"type": k, "address": w, "total": sum(e.values())},
                **{h: e.get(h, 0) for h in heads[2:8]})
           for (k, w), e in counts.items()]
    out.sort(key=lambda r: (-r["total"], r["address"]))
    return heads, out


def mail_froms_steps(values, folder, stamp):
    import os
    query = (values.get("query") or "").strip()
    if not query:
        raise ValueError("Enter which messages, e.g. in:inbox (a blank search reads "
                         "every message).")
    most = (values.get("max") or "").strip()
    if most and not most.isdigit():
        raise ValueError("The most messages to read must be a whole number, or blank.")
    who = user_scope_argv(values)
    files = {"raw": os.path.join(folder, "Mail-Froms-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Mail-MessagesPerSender-%s.csv" % stamp)}
    return [("List the sender of each matching message",
             ["config", "auto_batch_min", "1", "redirect", "csv", files["raw"],
              "multiprocess", "redirect", "stderr", "-", "multiprocess"] + who
             + ["print", "messages", "query", query]
             + (["max_to_print", most] if most else []) + ["headers", "from"])], files


def mail_froms_report(rows):
    # 'Name <a@b>' / 'a@b' -> one row per address: address, name, count.
    counts, names = {}, {}
    for row in rows:
        raw = (row.get("From") or "").strip()
        if not raw:
            continue
        found = re.search(r"<([^<>@\s]+@[^<>\s]+)>", raw) or \
            re.search(r"([^\s<>\"']+@[^\s<>\"']+)", raw)
        address = (found.group(1) if found else raw).strip().lower()
        counts[address] = counts.get(address, 0) + 1
        if address not in names:
            name = raw.split("<", 1)[0].strip().strip('"').strip() if "<" in raw else ""
            names[address] = name
    return [{"sender": a, "name": names[a], "messages": n}
            for a, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


# --- 2.89: Chrome extensions on managed browsers (browserexts) ---------------
# Ross Scroggs' BrowserExtensions.py. GAM prints every managed browser with
# its profiles and their extensions as one JSON cell per machine; GAMGUI
# turns that around into one row per extension with the machines that have
# it. Excel cannot hold more than 32,767 characters in a cell, so a long
# machine list continues in machineNames_2, machineNames_3...
EXCEL_CELL_LIMIT = 32000


def _redirect(path, multi=False):
    # 'redirect csv <path> [multiprocess] noescapechar true' (2.89). GAM's
    # default CSV OUTPUT escapes a backslash as two (csv_output_no_escape_char
    # False) while its CSV INPUT does not (csv_input_no_escape_char True) -
    # found live 10-14-2026 when a vacation reply's \n came back as \\n.
    # noescapechar true makes GAM write plain CSV whatever gam.cfg says, so
    # GAMGUI reads exactly what Google returned. 'gam csv <file>' loops get
    # 'noescapechar true' too (CSV_LOOP_PLAIN).
    return ["redirect", "csv", path] + (["multiprocess"] if multi else []) \
        + ["noescapechar", "true"]


CSV_LOOP_PLAIN = ["noescapechar", "true"]


def split_cell(items, separator=", ", limit=EXCEL_CELL_LIMIT):
    # ["a", "b", ...] -> ["a, b, ...", ...]: the joined text cut at item
    # boundaries so no piece is longer than limit. Always at least one piece.
    pieces, current = [], ""
    for item in items:
        item = str(item)
        joined = item if not current else current + separator + item
        if current and len(joined) > limit:
            pieces.append(current)
            current = item
        else:
            current = joined
    pieces.append(current)
    return pieces


def browser_json(text):
    # One browser's JSON cell -> dict, or None when it cannot be read. With
    # GAM's default escaped CSV output a JSON \" arrives as \\" (Ross's
    # FIX_DOUBLE_SLASH_QUOTE; seen live 10-14-2026). GAMGUI now asks for
    # plain CSV (noescapechar true - see _redirect), so this fix is only a
    # fallback, tried when the plain text fails, because a real path ending
    # in a backslash ("C:\\Temp\\") looks the same.
    import json
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return json.loads(text.replace('\\\\"', '\\"'))
    except ValueError:
        return None


# installType -> the report's count column.
BROWSER_EXT_KINDS = {"ADMIN": "forcedByPolicy", "NORMAL": "userInstalled",
                     "SIDELOAD": "sideloaded", "DEVELOPMENT": "sideloaded"}


def browser_exts_steps(values, folder, stamp):
    # One read-only GAM command: every managed browser (or one OU's) with
    # its extensions, as JSON.
    import os
    which = (values.get("which") or "all").strip()
    if which not in ("all", "notforced", "sideload"):
        raise ValueError("Choose which extensions to list.")
    per = (values.get("per") or "extension").strip()
    if per not in ("extension", "version"):
        raise ValueError("Choose one row per extension or per version.")
    ou = (values.get("ou") or "").strip()
    files = {"raw": os.path.join(folder, "Chrome-Browsers-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Chrome-Extensions-%s.csv" % stamp)}
    return [("List the managed Chrome browsers and their extensions",
             _redirect(files["raw"]) + ["print", "browsers"]
             + (["ou", ou] if ou else [])
             + ["fields", "browsers,machinename", "formatjson"])], files


def browser_exts_report(rows, which="all", per="extension"):
    # GAM's rows (deviceId, JSON) -> (columns, report rows, machines that
    # could not be read). One report row per extension (or extension +
    # version): how many machines have it, how it got there, and which.
    found, unreadable = {}, []
    for row in rows:
        data = browser_json(row.get("JSON") or "")
        if data is None:
            unreadable.append(row.get("deviceId") or "?")
            continue
        machine = data.get("machineName") or data.get("deviceId") or row.get("deviceId") or "?"
        for browser in data.get("browsers") or []:
            for profile in browser.get("profiles") or []:
                for ext in profile.get("extensions") or []:
                    ext_id = ext.get("extensionId") or ""
                    if not ext_id:
                        continue
                    kind = BROWSER_EXT_KINDS.get((ext.get("installType") or "").upper(),
                                                 "otherInstall")
                    if which == "notforced" and kind == "forcedByPolicy":
                        continue
                    if which == "sideload" and kind != "sideloaded":
                        continue
                    version = ext.get("version") or ""
                    key = (ext_id, version if per == "version" else "")
                    entry = found.setdefault(key, {
                        "name": "", "versions": set(), "permissions": set(),
                        "machines": set(), "disabled": set(),
                        "forcedByPolicy": set(), "userInstalled": set(),
                        "sideloaded": set(), "otherInstall": set()})
                    entry["name"] = entry["name"] or ext.get("name") or ""
                    if version:
                        entry["versions"].add(version)
                    perms = ext.get("permissions") or []
                    if isinstance(perms, str):
                        perms = [perms]
                    entry["permissions"].update(str(p) for p in perms)
                    entry["machines"].add(machine)
                    entry[kind].add(machine)
                    if ext.get("disabled"):
                        entry["disabled"].add(machine)
    out, most_pieces = [], 1
    for (ext_id, version), e in found.items():
        pieces = split_cell(sorted(e["machines"], key=str.lower))
        most_pieces = max(most_pieces, len(pieces))
        row = {"extensionId": ext_id,
               "version": version if per == "version" else ", ".join(sorted(e["versions"])),
               "name": e["name"], "machines": len(e["machines"]),
               "forcedByPolicy": len(e["forcedByPolicy"]),
               "userInstalled": len(e["userInstalled"]),
               "sideloaded": len(e["sideloaded"]), "otherInstall": len(e["otherInstall"]),
               "disabled": len(e["disabled"]),
               "permissions": ", ".join(sorted(e["permissions"])),
               "storeLink": "https://chromewebstore.google.com/detail/" + ext_id,
               "machineNames": pieces[0]}
        for number, piece in enumerate(pieces[1:], start=2):
            row["machineNames_%d" % number] = piece
        out.append(row)
    out.sort(key=lambda r: (-r["machines"], r["name"].lower(), r["extensionId"], r["version"]))
    columns = ["extensionId", "version" if per == "version" else "versions", "name",
               "machines", "forcedByPolicy", "userInstalled", "sideloaded", "otherInstall",
               "disabled", "permissions", "storeLink", "machineNames"] \
        + ["machineNames_%d" % n for n in range(2, most_pieces + 1)]
    if per != "version":
        for row in out:
            row["versions"] = row.pop("version")
    return columns, out, unreadable


# --- 2.89: Last message sent to each group (lastgroupmail) -------------------
# Ross Scroggs' GetLastGroupEmail.py. Google keeps no "last post" date for a
# group, so GAM looks in each member's mailbox for the newest message that
# came through the group (Gmail search list:<group>, newest only) and GAMGUI
# keeps the newest per group. 'showdate' gives a sortable local time in the
# Date column (GAM source: row['Date'] = formatLocalTimestamp(internalDate)).
def _csv_file_column(text):
    # "C:\\x\\groups.csv:email" -> ("C:\\x\\groups.csv", "email"). The LAST
    # colon splits them, so a drive letter (C:) stays part of the file.
    text = (text or "").strip()
    if ":" not in text:
        raise ValueError("Enter the CSV file and its column as file:column, "
                         "e.g. C:\\GAMExports\\groups.csv:email")
    path, column = text.rsplit(":", 1)
    path, column = path.strip().strip('"'), column.strip()
    if not path or not column or len(path) < 2 or path.endswith((":", "\\", "/")):
        raise ValueError("Enter the CSV file and its column as file:column, "
                         "e.g. C:\\GAMExports\\groups.csv:email")
    return path, column


def last_group_mail_steps(values, folder, stamp):
    # The read-only GAM command(s), the files, and (list mode) the group
    # list the run writes to files["groups"] first.
    import os
    source = (values.get("source") or "list").strip()
    files = {"groups": os.path.join(folder, "Last-Group-Mail-groups-%s.csv" % stamp),
             "raw": os.path.join(folder, "Last-Group-Mail-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Last-Group-Mail-%s.csv" % stamp)}
    steps, groups = [], []
    if source == "list":
        groups = [g.strip().lower() for g in re.split(r"[,;\s]+", values.get("groups") or "")
                  if g.strip()]
        bad = [g for g in groups if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", g)]
        if bad:
            raise ValueError("Not a group email address: " + ", ".join(bad))
        if not groups:
            raise ValueError("Enter the group email(s), comma separated.")
        listfile, column = files["groups"], "email"
    elif source == "csv":
        listfile, column = _csv_file_column(values.get("groups"))
        files["groups"] = ""
    elif source == "all":
        listfile, column = files["groups"], "email"
        steps.append(("List every group", _redirect(listfile) + ["print", "groups"]))
    else:
        raise ValueError("Choose which groups.")
    steps.append(("Find the newest message from each group in its members' mailboxes",
                  _redirect(files["raw"], True)
                  + ["redirect", "stderr", "-", "multiprocess",
                   "csv", listfile] + CSV_LOOP_PLAIN + ["gam", "group_ns", "~" + column,
                   "print", "messages", "query", "list:~~%s~~" % column,
                   "max_to_print", "1", "showdate", "headers", "from,to,cc,subject",
                   "addcsvdata", "Group", "~" + column]))
    return steps, files, groups, (listfile, column)


def _parse_message_time(text):
    import datetime
    try:
        return datetime.datetime.fromisoformat((text or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def last_group_mail_report(groups, rows, now=None):
    # groups: every group asked about (lower case). rows: GAM's messages
    # (User, Group, Date, From, To, Cc, Subject). -> one row per group with
    # its newest message; groups with none first, then the quietest.
    import datetime
    now = now or datetime.datetime.now(datetime.timezone.utc)
    best = {}
    for row in rows:
        group = (row.get("Group") or "").strip().lower()
        if not group:
            continue
        # Only messages addressed to the group (To or Cc) - the same check
        # as Ross's script, so a message that only mentions the list is not
        # counted. A message sent Bcc to the group is not seen.
        addressed = " ".join(str(row.get(k) or "") for k in row
                             if (k or "").lower() in ("to", "cc")).lower()
        if group not in addressed:
            continue
        when = _parse_message_time(row.get("Date"))
        held = best.get(group)
        if held is None or (when and (held[0] is None or when > held[0])):
            best[group] = (when, row)
    seen, out = set(), []
    for group in list(groups) + sorted(best):
        if group in seen:
            continue
        seen.add(group)
        when, row = best.get(group, (None, None))
        if row is None:
            out.append({"group": group, "lastMessage": "", "daysAgo": "", "from": "",
                        "subject": "", "foundInMailbox": "",
                        "note": "no message found in the members' mailboxes"})
            continue
        days = ""
        if when is not None:
            moment = when if when.tzinfo else when.replace(tzinfo=datetime.timezone.utc)
            days = max(0, (now - moment).days)
        out.append({"group": group, "lastMessage": row.get("Date") or "", "daysAgo": days,
                    "from": row.get("From") or "", "subject": row.get("Subject") or "",
                    "foundInMailbox": row.get("User") or "", "note": ""})
    out.sort(key=lambda r: (r["lastMessage"] != "",
                            -(r["daysAgo"] if r["daysAgo"] != "" else 0), r["group"]))
    return out


LAST_GROUP_MAIL_COLUMNS = ["group", "lastMessage", "daysAgo", "from", "subject",
                           "foundInMailbox", "note"]


# --- 2.89: Calendar events, one attendee per row (eventattendees) ------------
# Ross Scroggs' MakeOneAttendeePerRowEvents.py. GAM prints attendees as
# attendees.0.email, attendees.1.email... columns; GAMGUI writes one row per
# attendee, optionally only attendees in some domains / some addresses.
_ATTENDEE_COLUMN = re.compile(r"attendees\.(\d+)\.(.+)$")
ATTENDEE_FIRST = ["email", "displayName", "responseStatus", "optional", "organizer",
                  "resource", "self"]


def _address_list(text):
    return [a.strip().lower() for a in re.split(r"[,;\s]+", text or "") if a.strip()]


def event_attendees_steps(values, folder, stamp):
    import os
    who = user_scope_argv(values)
    calendar = (values.get("calendar") or "primary").strip()
    if not calendar or re.search(r"\s", calendar):
        raise ValueError("Enter one calendar: primary, or a calendar ID (no spaces).")
    after = (values.get("after") or "").strip()
    before = (values.get("before") or "").strip()
    if not after:
        raise ValueError("Enter where to start: now, or a date like 2026-09-01.")
    domains = parse_domain_list(values["domains"]) if (values.get("domains") or "").strip() \
        else []
    emails = _address_list(values.get("emails"))
    bad = [e for e in emails if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e)]
    if bad:
        raise ValueError("Not an email address: " + ", ".join(bad))
    files = {"raw": os.path.join(folder, "Event-Attendees-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Event-Attendees-%s.csv" % stamp)}
    argv = (["config", "auto_batch_min", "1"] + _redirect(files["raw"], True)
            + ["redirect", "stderr", "-", "multiprocess"] + who
            + ["print", "events", calendar, "after", after]
            + (["before", before] if before else []))
    # GAM leaves out events with nobody wanted, so far fewer rows come back.
    if domains:
        argv += ["matchfield", "attendeesdomainlist", ",".join(domains)]
    if emails:
        argv += ["matchfield", "attendees", ",".join(emails)]
    argv += ["fields", "id,summary,start,end,status,organizer,attendees"]
    return [("List the events and their attendees", argv)], files, domains, emails


def event_attendees_report(rows, domains=(), emails=()):
    # -> (columns, one row per attendee). Event columns keep GAM's order;
    # attendee details follow as attendee.<field>.
    domains = [d.lower() for d in domains]
    emails = [e.lower() for e in emails]
    base_cols, att_fields = [], []
    for row in rows:
        for key in row:
            match = _ATTENDEE_COLUMN.match(key or "")
            if match:
                if match.group(2) not in att_fields:
                    att_fields.append(match.group(2))
            elif key and key != "attendees" and key not in base_cols:
                base_cols.append(key)
    att_fields.sort(key=lambda f: (ATTENDEE_FIRST.index(f) if f in ATTENDEE_FIRST
                                   else len(ATTENDEE_FIRST), f))
    out = []
    for row in rows:
        people = {}
        for key, value in row.items():
            match = _ATTENDEE_COLUMN.match(key or "")
            if match:
                people.setdefault(int(match.group(1)), {})[match.group(2)] = value
        base = {k: row.get(k, "") for k in base_cols}
        for number in sorted(people):
            person = people[number]
            address = (person.get("email") or "").strip().lower()
            if not address:
                continue
            # Exact domains, the same rule as GAM's attendeesdomainlist (so a
            # sub-domain must be listed too).
            if domains and address.rsplit("@", 1)[-1] not in domains:
                continue
            if emails and address not in emails:
                continue
            new = dict(base)
            for field in att_fields:
                new["attendee." + field] = person.get(field, "")
            out.append(new)
    return base_cols + ["attendee." + f for f in att_fields], out


def _email_list_or_csv(source, text, what):
    # A typed list ("list") or a CSV file:column ("csv") -> ("list", [addresses])
    # or ("csv", (path, column)). Raises ValueError.
    if source == "csv":
        return "csv", _csv_file_column(text)
    items = _address_list(text)
    bad = [a for a in items if not _PLAIN_EMAIL.fullmatch(a)]
    if bad:
        raise ValueError("Not an email address: " + ", ".join(bad))
    if not items:
        raise ValueError("Enter the %s, comma separated." % what)
    return "list", items


# --- 2.89: Old addresses in users' contacts (oldcontacts) ---------------------
# Ross Scroggs' DeleteOldContacts.py. find: GAM lists every contact of the
# chosen users (People API: columns User, resourceName, emailAddresses.N.value,
# names.N.displayName - GAM source _printPerson / flattenJSON); GAMGUI keeps the
# contacts holding an old address. delete: the report's contacts, after a
# typed DELETE (the report stays as the record - Google Contacts' own 'Undo
# changes' can bring them back for 30 days).
OLD_CONTACTS_COLUMNS = ["User", "resourceName", "name", "oldAddress", "allAddresses"]


def old_contacts_steps(values, folder, stamp):
    import os
    who = user_scope_argv(values)
    source = (values.get("oldsource") or "ou").strip()
    files = {"old": os.path.join(folder, "Old-Contacts-addresses-%s.csv" % stamp),
             "raw": os.path.join(folder, "Old-Contacts-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Old-Contacts-%s.csv" % stamp)}
    steps, old = [], None
    if source == "ou":
        ou = (values.get("oldval") or "").strip()
        if not ou.startswith("/"):
            raise ValueError("Enter the OU path of the old users, e.g. /Staff/Left.")
        steps.append(("List the old users' addresses",
                      _redirect(files["old"]) + ["ou", ou, "print", "users"]))
        old = ("csv", (files["old"], "primaryEmail"))
    elif source in ("csv", "list"):
        old = _email_list_or_csv(source, values.get("oldval"), "old addresses")
        files["old"] = ""
    else:
        raise ValueError("Choose where the old addresses come from.")
    steps.append(("List the contacts of the chosen users",
                  ["config", "auto_batch_min", "1"] + _redirect(files["raw"], True)
                  + ["redirect", "stderr", "-", "multiprocess"] + who
                  + ["print", "contacts", "fields", "emailaddresses,names"]))
    return steps, files, old


def old_contacts_report(old_addresses, rows):
    # Contacts with at least one old address -> report rows, by user.
    old = {a.strip().lower() for a in old_addresses if a and a.strip()}
    out = []
    for row in rows:
        addresses = [(v or "").strip() for k, v in row.items()
                     if re.fullmatch(r"emailAddresses\.\d+\.value", k or "") and (v or "").strip()]
        hits = [a for a in addresses if a.lower() in old]
        if not hits or not (row.get("resourceName") or "").startswith("people/"):
            continue
        name = row.get("names.0.displayName") or row.get("names.0.unstructuredName") or ""
        out.append({"User": row.get("User", ""), "resourceName": row["resourceName"],
                    "name": name, "oldAddress": ", ".join(hits),
                    "allAddresses": ", ".join(addresses)})
    out.sort(key=lambda r: (r["User"].lower(), r["name"].lower(), r["resourceName"]))
    return out


def old_contacts_check_report(rows):
    if not rows:
        raise ValueError("The file has no rows.")
    for number, row in enumerate(rows, 2):
        if not _PLAIN_EMAIL.fullmatch((row.get("User") or "").strip().lower()) or \
                not re.fullmatch(r"people/c?\d+", (row.get("resourceName") or "").strip()):
            raise ValueError("Row %d has no User / resourceName - use the Old-Contacts-"
                             "...csv this task made." % number)
    return rows


# --- 2.89: Plain-text vacation replies to HTML (vacationhtml) ---------------
# Ross Scroggs' UpdateVacationToHTML.py. GAM's 'print vacation compact' writes
# the reply with line breaks as the two characters \n (and \r); GAM's
# 'vacation htmlmessage' turns \n back into <br/> and keeps the subject, dates
# and on/off as they are (GAM source setVacation: getVacation, then update).
# The text is HTML-escaped first, so a '<' or '&' in the reply stays visible.
VACATION_HTML_COLUMNS = ["User", "enabled", "subject", "message", "htmlmessage"]


def vacation_html_steps(values, folder, stamp):
    import os
    who = user_scope_argv(values)
    files = {"raw": os.path.join(folder, "Vacation-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Vacation-PlainText-%s.csv" % stamp)}
    only_on = (values.get("onlyon") or "on").strip() == "on"
    return [("Read the vacation replies",
             ["config", "auto_batch_min", "1"] + _redirect(files["raw"], True)
             + ["redirect", "stderr", "-", "multiprocess"] + who
             + ["print", "vacation", "compact"] + (["enabledonly"] if only_on else []))], files


def vacation_to_html(message):
    # GAM's compact text -> the htmlmessage to send (\n stays for GAM to turn
    # into <br/>; \r goes).
    import html
    text = (message or "").replace("\\r", "")
    return "<div>" + html.escape(text, quote=False) + "</div>"


def vacation_html_report(rows):
    out = []
    for row in rows:
        message = row.get("message") or ""
        if (row.get("html") or "").strip().lower() == "true" or not message.strip() \
                or message == "None":
            continue
        out.append({"User": row.get("User", ""), "enabled": row.get("enabled", ""),
                    "subject": row.get("subject", ""),
                    "message": message.replace("\\r", ""),
                    "htmlmessage": vacation_to_html(message)})
    out.sort(key=lambda r: r["User"].lower())
    return out


def vacation_html_check_report(rows):
    if not rows:
        raise ValueError("The file has no rows.")
    for number, row in enumerate(rows, 2):
        if not _PLAIN_EMAIL.fullmatch((row.get("User") or "").strip().lower()) or \
                "message" not in row or not (row.get("htmlmessage") or "").startswith("<div>"):
            raise ValueError("Row %d has no User / message / htmlmessage - use the "
                             "Vacation-PlainText-...csv this task made." % number)
    return rows


# --- 2.89: Protected ranges in Google Sheets (sheetprotect) -------------------
# Ross Scroggs' DeleteProtectedRanges.py and ExtractProtectedRanges.py.
#   find    - every protected range in the Sheets a user owns (read-only)
#   remove  - the report's ranges, after a typed REMOVE (deleteProtectedRange)
#   putback - the same report adds them again (addProtectedRange, same ID)
#   copyeditors - a Sheet's protected-range editors onto its copy
#             (updateProtectedRange fields editors - Drive's copy keeps the
#             ranges and their IDs but not who may edit them)
# GAM: 'print sheet <files> sheetsfields protectedranges formatjson' writes
# User, spreadsheetId, JSON; 'update sheet <id> json <requests>' sends them.
SHEET_PROTECT_COLUMNS = ["User", "spreadsheetId", "sheet", "protectedRangeId",
                         "description", "warningOnly", "editors", "range", "JSON"]
_SHEET_QUERY = "'me' in owners and mimeType = 'application/vnd.google-apps.spreadsheet'"


def _sheet_id(text, what):
    text = (text or "").strip()
    found = re.search(r"/d/([A-Za-z0-9_-]{20,})", text)
    if found:
        text = found.group(1)
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", text):
        raise ValueError("Enter the %s's file ID (or paste its link)." % what)
    return text


def sheet_protect_steps(values, folder, stamp):
    import os
    mode = (values.get("mode") or "find").strip()
    owner = (values.get("owner") or "").strip().lower()
    if not _PLAIN_EMAIL.fullmatch(owner):
        raise ValueError("Enter the Sheets' owner (an email address).")
    files = {"raw": os.path.join(folder, "Sheet-Protected-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Sheet-ProtectedRanges-%s.csv" % stamp)}
    if mode == "find":
        sheet = (values.get("sheet") or "").strip()
        # A plain file ID - 'print sheet drivefile <id>' is refused by GAM
        # 7.48.26 (Invalid argument, live 10-14-2026).
        target = ([_sheet_id(sheet, "Sheet")] if sheet else ["query", _SHEET_QUERY])
        return [("Read the protected ranges",
                 _redirect(files["raw"]) + ["user", owner, "print", "sheet"] + target
                 + ["sheetsfields", "properties,protectedranges", "formatjson"])], files
    if mode == "copyeditors":
        source = _sheet_id(values.get("sheet"), "original Sheet")
        copy = _sheet_id(values.get("copy"), "copy")
        if source == copy:
            raise ValueError("The copy must be a different file from the original.")
        files["source"], files["copy"] = source, copy
        return [("Read the original's protected ranges",
                 _redirect(files["raw"]) + ["user", owner, "print", "sheet", source,
                  "sheetsfields", "properties,protectedranges", "formatjson"]),
                ("Read the copy's protected ranges",
                 _redirect(files["raw"] + ".copy.csv") + ["user", owner, "print",
                  "sheet", copy, "sheetsfields", "properties,protectedranges",
                  "formatjson"])], files
    raise ValueError("Choose what to do.")


def sheet_protect_ranges(rows):
    # GAM's rows -> one dict per protected range (with the range's own JSON).
    import json
    out = []
    for row in rows:
        try:
            data = json.loads(row.get("JSON") or "{}")
        except ValueError:
            continue
        for sheet in data.get("sheets") or []:
            title = (sheet.get("properties") or {}).get("title", "")
            for prange in sheet.get("protectedRanges") or []:
                editors = prange.get("editors") or {}
                who = (editors.get("users") or []) + ["group:" + g for g in
                                                      editors.get("groups") or []]
                if editors.get("domainUsersCanEdit"):
                    who.append("domain")
                cells = prange.get("range") or {}
                where = "whole sheet" if set(cells) <= {"sheetId"} else ", ".join(
                    "%s=%s" % (k, cells[k]) for k in sorted(cells) if k != "sheetId")
                if prange.get("namedRangeId"):
                    where = "named range " + prange["namedRangeId"]
                out.append({"User": row.get("User", ""),
                            "spreadsheetId": row.get("spreadsheetId", ""),
                            "sheet": title,
                            "protectedRangeId": str(prange.get("protectedRangeId", "")),
                            "description": prange.get("description", ""),
                            "warningOnly": str(bool(prange.get("warningOnly"))),
                            "editors": ", ".join(who), "range": where,
                            "JSON": json.dumps(prange, sort_keys=True)})
    return out


def sheet_protect_check_report(rows):
    import json
    if not rows:
        raise ValueError("The file has no rows.")
    for number, row in enumerate(rows, 2):
        try:
            prange = json.loads(row.get("JSON") or "")
        except ValueError:
            prange = None
        if not _PLAIN_EMAIL.fullmatch((row.get("User") or "").strip().lower()) or \
                not re.fullmatch(r"[A-Za-z0-9_-]{20,}", (row.get("spreadsheetId") or "").strip()) \
                or not isinstance(prange, dict) or "protectedRangeId" not in prange:
            raise ValueError("Row %d has no User / spreadsheetId / JSON - use the Sheet-"
                             "ProtectedRanges-...csv this task made." % number)
    return rows


# Read-only (output) fields Google rejects or ignores when a range is added.
_PROTECT_OUTPUT_ONLY = ("requestingUserCanEdit",)


def sheet_protect_requests(rows, action):
    # Report rows -> [(User, spreadsheetId, JSON request body)], one per Sheet.
    #   remove  -> deleteProtectedRange per range
    #   putback -> addProtectedRange with the range as it was (same ID)
    import json
    sheets = {}
    for row in rows:
        prange = json.loads(row["JSON"])
        key = (row["User"].strip(), row["spreadsheetId"].strip())
        if action == "remove":
            request = {"deleteProtectedRange": {"protectedRangeId": prange["protectedRangeId"]}}
        else:
            prange = {k: v for k, v in prange.items() if k not in _PROTECT_OUTPUT_ONLY}
            request = {"addProtectedRange": {"protectedRange": prange}}
        sheets.setdefault(key, []).append(request)
    return [(user, sid, json.dumps({"requests": reqs}))
            for (user, sid), reqs in sorted(sheets.items())]


def sheet_copy_editor_requests(original, copy):
    # The original's ranges -> updateProtectedRange (editors only) for the
    # ranges the copy has under the same ID. -> (body or None, matched,
    # missing IDs).
    import json
    have = {r["protectedRangeId"] for r in copy}
    requests, missing = [], []
    for r in original:
        if r["protectedRangeId"] not in have:
            missing.append(r["protectedRangeId"])
            continue
        prange = json.loads(r["JSON"])
        requests.append({"updateProtectedRange": {
            "protectedRange": {"protectedRangeId": prange["protectedRangeId"],
                               "editors": prange.get("editors") or {}},
            "fields": "editors"}})
    body = json.dumps({"requests": requests}) if requests else None
    return body, len(requests), missing


# --- 2.89: Trace an IP address (iptrace) --------------------------------------
# 'report <log> user all ip <IP>' - the Reports API filters by the actor's
# IP address on the server. The Gmail log keeps (and GAM reads) 30 days.
IP_TRACE_LOGS = [("login", "Sign-ins"), ("saml", "SSO sign-ins to other systems"),
                 ("takeout", "Takeout exports"), ("drive", "Drive activity"),
                 ("gmail", "Gmail activity"), ("token", "App authorizations (OAuth)"),
                 ("useraccounts", "Account changes"), ("admin", "Admin console actions")]
IP_TRACE_COLUMNS = ["ipAddress", "log", "events", "accounts", "first", "last", "file"]
IP_ACCOUNT_COLUMNS = ["account", "ipAddress", "logs", "events", "first", "last"]


def _days(values, top=180, default="30"):
    days = (values.get("days") or default).strip()
    if not days.isdigit() or not 1 <= int(days) <= top:
        raise ValueError("Days must be a whole number from 1 to %d." % top)
    return int(days)


def ip_trace_steps(values, folder, stamp):
    import ipaddress, os
    ips = [p.strip() for p in re.split(r"[,;\s]+", values.get("ips") or "") if p.strip()]
    if not ips:
        raise ValueError("Enter the IP address(es) to trace.")
    if len(ips) > 5:
        raise ValueError("Trace up to 5 IP addresses at a time.")
    for ip in ips:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise ValueError("Not an IP address: " + ip)
    days = _days(values)
    steps, files = [], {"summary": os.path.join(folder, "IPTrace-%s.csv" % stamp),
                        "accounts": os.path.join(folder, "IPTrace-Accounts-%s.csv" % stamp),
                        "logs": []}
    for ip in ips:
        safe = re.sub(r"[^0-9A-Za-z]", "-", ip)
        for app, label in IP_TRACE_LOGS:
            path = os.path.join(folder, "IPTrace-%s-%s-%s.csv" % (safe, app, stamp))
            when = (["range", "-%dd" % min(days, 30), "today"] if app == "gmail"
                    else ["start", "-%dd" % days])
            steps.append(("%s - %s" % (label, ip),
                          _redirect(path) + ["report", app, "user", "all", "ip", ip] + when))
            files["logs"].append((ip, app, label, path))
    return steps, files


def ip_trace_report(results):
    # results: [(ip, label, path, rows)] -> (summary rows, account rows).
    summary, accounts = [], {}
    for ip, label, path, rows in results:
        who, times = set(), []
        for row in rows:
            account = (row.get("actor.email") or "").strip().lower()
            when = (row.get("id.time") or "").strip()
            if when:
                times.append(when)
            if not account:
                continue
            who.add(account)
            a = accounts.setdefault((account, ip), {"account": account, "ipAddress": ip,
                                                    "logs": set(), "events": 0,
                                                    "first": "", "last": ""})
            a["logs"].add(label)
            a["events"] += 1
            if when and (not a["first"] or when < a["first"]):
                a["first"] = when
            if when and when > a["last"]:
                a["last"] = when
        summary.append({"ipAddress": ip, "log": label, "events": len(rows),
                        "accounts": ", ".join(sorted(who)),
                        "first": min(times) if times else "",
                        "last": max(times) if times else "",
                        "file": path if rows else ""})
    out = [dict(a, logs=", ".join(sorted(a["logs"]))) for a in accounts.values()]
    out.sort(key=lambda r: (-r["events"], r["account"]))
    return summary, out


# --- 2.90: Sign-ins from outside your countries (foreignsignins) --------------
# 'report login user all event login_success' then GAMGUI keeps the rows whose
# networkInfo.regionCode (two-letter country, seen live 10-15-2026) is not one
# of yours. The Reports API cannot filter on 'not this country' itself.
FOREIGN_SIGNIN_COLUMNS = ["account", "time", "ipAddress", "country", "suspicious", "loginType"]
FOREIGN_ACCOUNT_COLUMNS = ["account", "signIns", "countries", "ipAddresses", "suspicious",
                           "first", "last"]


def foreign_signins_steps(values, folder, stamp):
    import os
    countries = [c.strip().upper() for c in re.split(r"[,;\s]+", values.get("countries") or "")
                 if c.strip()]
    if not countries:
        raise ValueError("Enter the countries your people sign in from (two-letter codes, "
                         "e.g. US).")
    bad = [c for c in countries if not re.fullmatch(r"[A-Z]{2}", c)]
    if bad:
        raise ValueError("Use two-letter country codes (e.g. US, MX): " + ", ".join(bad))
    days = _days(values, top=30, default="3")
    files = {"raw": os.path.join(folder, "SignIns-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "SignIns-OutsideCountries-%s.csv" % stamp),
             "accounts": os.path.join(folder, "SignIns-OutsideCountries-Accounts-%s.csv" % stamp)}
    return [("Successful sign-ins in the last %d days (every account)" % days,
             _redirect(files["raw"]) + ["report", "login", "user", "all",
                                        "event", "login_success", "start", "-%dd" % days])
            ], files, countries


def foreign_signins_report(rows, countries):
    # -> (sign-in rows from other countries, per-account rows). A sign-in
    # with no country is left out (Google gives none for some sign-ins).
    home = {c.upper() for c in countries}
    out, accounts = [], {}
    for row in rows:
        country = (row.get("networkInfo.regionCode") or "").strip().upper()
        if not country or country in home:
            continue
        account = (row.get("actor.email") or "").strip().lower()
        when = (row.get("id.time") or "").strip()
        flagged = (row.get("is_suspicious") or "").strip().lower() == "true"
        out.append({"account": account, "time": when, "ipAddress": row.get("ipAddress", ""),
                    "country": country, "suspicious": "yes" if flagged else "",
                    "loginType": row.get("login_type", "")})
        a = accounts.setdefault(account, {"account": account, "signIns": 0, "countries": set(),
                                          "ipAddresses": set(), "suspicious": 0,
                                          "first": "", "last": ""})
        a["signIns"] += 1
        a["countries"].add(country)
        if row.get("ipAddress"):
            a["ipAddresses"].add(row["ipAddress"])
        a["suspicious"] += 1 if flagged else 0
        if when and (not a["first"] or when < a["first"]):
            a["first"] = when
        if when and when > a["last"]:
            a["last"] = when
    out.sort(key=lambda r: (r["account"], r["time"]))
    acc = [dict(a, countries=", ".join(sorted(a["countries"])),
                ipAddresses=", ".join(sorted(a["ipAddresses"]))) for a in accounts.values()]
    acc.sort(key=lambda r: (-r["suspicious"], -r["signIns"], r["account"]))
    return out, acc


# --- 2.98: Admin role review (adminreview) ------------------------------------
# 'print admins' names who holds each role (assignedToUser / assignedToGroup /
# assignedToServiceAccount; assignedToUnknown is True when the account no
# longer exists) and where (scopeType CUSTOMER or ORG_UNIT + orgUnit); a
# temporary role has expirationDetails.expireTime. Two 'print users' (super
# admins = isAdmin, delegated = isDelegatedAdmin) add suspended, 2-Step
# Verification and the last sign-in. All seen live with GAM 7.49.02 on
# 10-28-2026. Built-in roles print as _SEED_ADMIN_ROLE (Super Admin),
# _GROUPS_ADMIN_ROLE...; only Super Admin's name is known for sure, the rest
# are made readable from the code.
ADMIN_REVIEW_COLUMNS = ["role", "assignedTo", "type", "scope", "expires", "suspended",
                        "twoStepEnrolled", "twoStepEnforced", "lastSignIn", "notes"]
ADMIN_REVIEW_USER_FIELDS = ("primaryemail,suspended,isenrolledin2sv,isenforcedin2sv,"
                            "lastlogintime,isadmin,isdelegatedadmin")
SUPER_ADMIN_ROLE = "_SEED_ADMIN_ROLE"
ADMIN_REVIEW_MANY = 10      # one holder with this many roles or more is pointed out


def admin_role_label(role):
    # '_SEED_ADMIN_ROLE' -> 'Super Admin'; '_GROUPS_ADMIN_ROLE' -> 'Groups Admin';
    # a custom role keeps its own name.
    role = (role or "").strip()
    if role == SUPER_ADMIN_ROLE:
        return "Super Admin"
    if role.startswith("_") and role.endswith("_ROLE"):
        return " ".join(w.capitalize() for w in role[1:-5].split("_") if w)
    return role


def admin_review_steps(values, folder, stamp):
    # Three read-only GAM commands.
    import os
    days = _days(values, top=3650, default="90")
    files = {"admins": os.path.join(folder, "AdminReview-assignments-raw-%s.csv" % stamp),
             "super": os.path.join(folder, "AdminReview-superadmins-raw-%s.csv" % stamp),
             "delegated": os.path.join(folder, "AdminReview-delegated-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "AdminRoleReview-%s.csv" % stamp)}
    return [("Every admin role assignment",
             _redirect(files["admins"]) + ["print", "admins"]),
            ("Super admins - suspended, 2-Step Verification, last sign-in",
             _redirect(files["super"]) + ["print", "users", "query", "isAdmin=true",
                                          "fields", ADMIN_REVIEW_USER_FIELDS]),
            ("Delegated admins - suspended, 2-Step Verification, last sign-in",
             _redirect(files["delegated"]) + ["print", "users", "query", "isDelegatedAdmin=true",
                                              "fields", ADMIN_REVIEW_USER_FIELDS])], files, days


def _signin_date(text):
    # GAM's lastLoginTime ('2026-08-07T14:10:59Z', 'Never', or 1970 for never)
    # -> (date or None, text for the report).
    import datetime
    text = (text or "").strip()
    if not text or text.lower() == "never" or text.startswith("1970"):
        return None, "never"
    try:
        return datetime.date.fromisoformat(text[:10]), text[:10]
    except ValueError:
        return None, text


def admin_review_report(assignments, users, days, today=None):
    # -> (report rows, summary lines). users = the rows of both 'print users'.
    import datetime
    today = today or datetime.date.today()
    people = {}
    for u in users:
        email = (u.get("primaryEmail") or "").strip().lower()
        if email:
            people[email] = u
    yes = lambda v: (v or "").strip().lower() == "true"
    rows, held = [], {}
    for a in assignments:
        if yes(a.get("assignedToUnknown")):
            kind, who = "unknown", (a.get("assignedTo") or "").strip()
        elif a.get("assignedToUser"):
            kind, who = "user", a["assignedToUser"].strip()
        elif a.get("assignedToGroup"):
            kind, who = "group", a["assignedToGroup"].strip()
        elif a.get("assignedToServiceAccount"):
            kind, who = "service account", a["assignedToServiceAccount"].strip()
        else:
            kind, who = "unknown", (a.get("assignedTo") or "").strip()
        role = admin_role_label(a.get("role") or a.get("roleId"))
        scope = "whole organization" if (a.get("scopeType") or "").upper() != "ORG_UNIT" \
            else "OU " + (a.get("orgUnit") or a.get("orgUnitId") or "?")
        expires = (a.get("expirationDetails.expireTime") or "").strip()
        row = {"role": role, "assignedTo": who, "type": kind, "scope": scope,
               "expires": expires, "suspended": "", "twoStepEnrolled": "",
               "twoStepEnforced": "", "lastSignIn": "", "notes": ""}
        notes = []
        if kind == "unknown":
            notes.append("the account no longer exists - remove this assignment")
        u = people.get(who.lower()) if kind == "user" else None
        if u is not None:
            row["suspended"] = "yes" if yes(u.get("suspended")) else "no"
            row["twoStepEnrolled"] = "yes" if yes(u.get("isEnrolledIn2Sv")) else "NO"
            row["twoStepEnforced"] = "yes" if yes(u.get("isEnforcedIn2Sv")) else "no"
            when, row["lastSignIn"] = _signin_date(u.get("lastLoginTime"))
            if row["suspended"] == "yes":
                notes.append("suspended but still holds this role")
            if row["twoStepEnrolled"] == "NO":
                notes.append("no 2-Step Verification")
            if when is None and row["lastSignIn"] == "never":
                notes.append("never signed in")
            elif when is not None and (today - when).days >= days:
                notes.append("no sign-in for %d days" % (today - when).days)
        if expires:
            notes.append("temporary - ends " + expires[:10])
        row["notes"] = "; ".join(notes)
        rows.append(row)
        if kind != "unknown":
            held.setdefault((kind, who.lower()), []).append(row)
    rows.sort(key=lambda r: (r["role"] != "Super Admin", r["role"].lower(),
                             r["assignedTo"].lower()))

    # ---- summary --------------------------------------------------------------
    supers = sorted({r["assignedTo"].lower() for r in rows
                     if r["role"] == "Super Admin" and r["type"] == "user"
                     and r["suspended"] != "yes"})
    lines = ["%d role assignments, %d holders (people, groups, service accounts)."
             % (len(rows), len(held)),
             "Super admins (people, not suspended): %d" % len(supers)
             + ("  - Google recommends at least two, so one is left if the other is "
                "locked out." if len(supers) < 2 else "")]
    bad2sv = sorted({r["assignedTo"] for r in rows if r["twoStepEnrolled"] == "NO"
                     and r["suspended"] != "yes"},
                    key=lambda e: (e.lower() not in supers, e.lower()))
    for email in bad2sv:
        lines.append("NOTE: %s%s has no 2-Step Verification." % (
            email, " (SUPER ADMIN)" if email.lower() in supers else ""))
    for email in sorted({r["assignedTo"] for r in rows if r["suspended"] == "yes"}):
        lines.append("NOTE: %s is suspended but still holds a role." % email)
    gone = sum(1 for r in rows if r["type"] == "unknown")
    if gone:
        lines.append("NOTE: %d assignment(s) belong to an account that no longer exists."
                     % gone)
    for (kind, who), rs in sorted(held.items(), key=lambda kv: -len(kv[1])):
        if len(rs) >= ADMIN_REVIEW_MANY:
            lines.append("NOTE: %s holds %d roles - fewer, broader roles are easier to "
                         "review." % (rs[0]["assignedTo"], len(rs)))
    idle = sorted({r["assignedTo"] for r in rows if r["notes"].find("no sign-in for") >= 0
                   or "never signed in" in r["notes"]})
    if idle:
        lines.append("NOTE: %d admin(s) have not signed in for %d days or more (see the "
                     "notes column)." % (len(idle), days))
    temp = sum(1 for r in rows if r["expires"])
    if temp:
        lines.append("%d temporary role(s) - see the expires column." % temp)
    return rows, lines


# --- 2.89: Who clicked a phishing link (linkclicks) ---------------------------
# Gmail log event types 15 'link in message body was clicked' and 16 'link in
# an attachment clicked during preview' (Reports API appendix). GAM flattens
# message_info as parameters.N.messageValue.parameter.M.name / .value pairs
# (seen live 10-15-2026: subject, rfc2822_message_id, source...).
LINK_CLICK_COLUMNS = ["user", "time", "ipAddress", "country", "click", "subject",
                      "messageId"]


def link_clicks_steps(values, folder, stamp):
    import os
    subject = (values.get("subject") or "").strip()
    msgid = (values.get("msgid") or "").strip().strip("<>").strip()
    if not subject and not msgid:
        raise ValueError("Enter the phishing email's subject words or its Message-ID.")
    days = _days(values, top=30, default="7")
    steps, files = [], {"report": os.path.join(folder, "LinkClicks-%s.csv" % stamp),
                        "raw": []}
    for kind in (15, 16):
        path = os.path.join(folder, "LinkClicks-raw-%d-%s.csv" % (kind, stamp))
        steps.append(("Link clicks (Gmail log type %d) in the last %d days" % (kind, days),
                      _redirect(path) + ["report", "gmail", "user", "all", "filter",
                                         "event_info.mail_event_type==%d" % kind,
                                         "range", "-%dd" % days, "today"]))
        files["raw"].append((kind, path))
    return steps, files, subject, msgid


def gmail_log_value(row, group, name):
    # The value of message_info / event_info parameter <name> in one flattened
    # 'report gmail' row ('' when absent).
    groups = {}
    for key, value in row.items():
        m = re.fullmatch(r"parameters\.(\d+)\.name", key or "")
        if m and value == group:
            groups[m.group(1)] = True
    for n in groups:
        prefix = "parameters.%s.messageValue.parameter." % n
        for key, value in row.items():
            m = re.fullmatch(re.escape(prefix) + r"(\d+)\.name", key or "")
            if m and value == name:
                base = prefix + m.group(1) + "."
                for kind in ("value", "intValue", "boolValue"):
                    if row.get(base + kind):
                        return row[base + kind]
    return ""


def link_clicks_report(raw, subject="", msgid=""):
    # raw: [(type, rows)] -> the clicks on the phishing email.
    want_words = [w.lower() for w in subject.split() if w]
    want_id = msgid.strip().strip("<>").strip().lower()
    out = []
    for kind, rows in raw:
        for row in rows:
            subj = gmail_log_value(row, "message_info", "subject")
            mid = gmail_log_value(row, "message_info", "rfc2822_message_id").strip("<>").lower()
            if want_id and mid != want_id:
                continue
            if want_words and not all(w in subj.lower() for w in want_words):
                continue
            out.append({"user": row.get("actor.email", ""), "time": row.get("id.time", ""),
                        "ipAddress": row.get("ipAddress", ""),
                        "country": row.get("networkInfo.regionCode", ""),
                        "click": "link in the message" if kind == 15
                        else "link in an attachment",
                        "subject": subj, "messageId": mid})
    out.sort(key=lambda r: (r["time"], r["user"]))
    return out


# --- 2.89: Lock out several compromised accounts (lockmany) -------------------
def lock_many_steps(values, folder, stamp):
    import os
    if (values.get("usertype") or "").strip() in ("", "all"):
        raise ValueError("Choose the accounts to lock (a CSV, group, OU, query or user) "
                         "- not ALL users.")
    who = user_scope_argv(values)
    files = {"record": os.path.join(folder, "Locked-Accounts-%s.csv" % stamp)}
    record = ("Save a record of the accounts (before anything changes)",
              _redirect(files["record"]) + who + ["print", "users", "fields",
                                                   "primaryemail,suspended,orgunitpath,"
                                                   "lastlogintime,isenrolledin2sv"])
    changes = [("Block sign-in (a password nobody can type)",
                ["update", "users"] + who + ["password", "blocklogin"]),
               ("Sign out everywhere (revoke every session cookie)", who + ["signout"])]
    if (values.get("suspend") or "no") == "yes":
        changes.append(("Suspend them", ["update", "users"] + who + ["suspended", "on"]))
    return [record] + changes, files


# --- 2.89: Empty a Shared Drive (sdempty) ------------------------------------
SD_EMPTY_COLUMNS = ["User", "id", "name", "mimeType"]


def _drive_id(text):
    text = (text or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", text):
        raise ValueError("Enter the Shared Drive's ID (Pick... fills it in) - not its name.")
    return text


def sd_empty_steps(values, folder, stamp):
    # Two read-only lists: everything in the drive (the record) and its
    # top-level items (the ones moved to the trash - their contents go with
    # them).
    import os
    manager = (values.get("manager") or "").strip().lower()
    if not _PLAIN_EMAIL.fullmatch(manager):
        raise ValueError("Enter a manager of the Shared Drive (an email address).")
    sid = _drive_id(values.get("driveid"))
    files = {"all": os.path.join(folder, "SharedDrive-Contents-%s.csv" % stamp),
             "top": os.path.join(folder, "SharedDrive-TopLevel-raw-%s.csv" % stamp),
             "record": os.path.join(folder, "SharedDrive-Emptied-%s.csv" % stamp)}
    select = ["user", manager, "print", "filelist", "select", "shareddriveid", sid]
    return [("List everything in the Shared Drive (the record)",
             _redirect(files["all"]) + select
             + ["fields", "id,name,mimetype", "fullpath"]),
            ("List its top-level files and folders",
             _redirect(files["top"]) + select
             + ["fields", "id,name,mimetype", "query", "'%s' in parents" % sid])], files


def sd_empty_record(rows, manager):
    # GAM's top-level rows -> the record / work rows (User = the manager).
    return [{"User": manager, "id": (r.get("id") or "").strip(), "name": r.get("name", ""),
             "mimeType": r.get("mimeType", "")} for r in rows if (r.get("id") or "").strip()]


def sd_empty_check_record(rows):
    if not rows:
        raise ValueError("The file has no rows.")
    for number, row in enumerate(rows, 2):
        if not _PLAIN_EMAIL.fullmatch((row.get("User") or "").strip().lower()) or \
                not re.fullmatch(r"[A-Za-z0-9_-]{10,}", (row.get("id") or "").strip()):
            raise ValueError("Row %d has no User / id - use the SharedDrive-Emptied-...csv "
                             "this task made." % number)
    return rows


# --- 2.89: CSV tools (csvtools) -------------------------------------------------
# Ross Scroggs' CSV helper scripts (Gabe 10-14-2026, group 3): AddOrgUnit,
# AddCrosIDfromSN, MergeUserData / AppendUserData / MergeGroupInfoMembers,
# CSVKMD / CombineKeyValues / CombineCourseParticipants, CountKeyValues,
# CountCSVRows, DeleteDuplicateRows, FindCommonEmails, ConvertCSVtoJSON,
# MakeOneParentPerRow. All local: they read CSV files and write a NEW file
# (never the input); 'addou' / 'addcrosid' first run one read-only GAM list.
# Each function: (columns, rows, ...) in -> (columns, rows, notes) out.
# Values are matched without regard to case or spaces around them.
def _key(value):
    return (value or "").strip().lower()


def csv_join(cols1, rows1, key1, cols2, rows2, key2, add=None, keep_unmatched=True,
             suffix=".file2"):
    # Each row of file 1 + the columns of the file-2 row with the same key.
    # add: the file-2 columns to bring over (None = all but its key). A name
    # file 1 already has gets suffix. -> (columns, rows, notes)
    for col, cols, which in ((key1, cols1, "first"), (key2, cols2, "second")):
        if col not in cols:
            raise ValueError("The %s file has no column '%s' (it has: %s)."
                             % (which, col, ", ".join(cols)))
    add = [c for c in (add or [c for c in cols2 if c != key2])]
    missing = [c for c in add if c not in cols2]
    if missing:
        raise ValueError("The second file has no column(s): " + ", ".join(missing))
    lookup, dups = {}, 0
    for row in rows2:
        k = _key(row.get(key2))
        if not k:
            continue
        if k in lookup:
            dups += 1
            continue
        lookup[k] = row
    names = {c: (c + suffix if c in cols1 else c) for c in add}
    out, unmatched = [], 0
    for row in rows1:
        other = lookup.get(_key(row.get(key1)))
        if other is None:
            unmatched += 1
            if not keep_unmatched:
                continue
        new = dict(row)
        for c in add:
            new[names[c]] = other.get(c, "") if other else ""
        out.append(new)
    notes = ["%d rows matched, %d had no match%s" % (
        len(rows1) - unmatched, unmatched,
        " (left out)" if unmatched and not keep_unmatched else "")]
    if dups:
        notes.append("%d rows of the second file repeat a key - the first one was used" % dups)
    return list(cols1) + [names[c] for c in add], out, notes


def csv_combine(cols, rows, key, value, keep=(), separator=" "):
    # One row per key: its values (each once, in order) joined by separator,
    # plus the 'keep' columns from the key's first row (Ross's CSVKMD).
    for c in [key, value] + list(keep):
        if c not in cols:
            raise ValueError("The file has no column '%s' (it has: %s)." % (c, ", ".join(cols)))
    groups, order = {}, []
    for row in rows:
        k = (row.get(key) or "").strip()
        if not k:
            continue
        if k not in groups:
            groups[k] = {"first": row, "values": []}
            order.append(k)
        v = (row.get(value) or "").strip()
        if v and v not in groups[k]["values"]:
            groups[k]["values"].append(v)
    out = []
    for k in order:
        g = groups[k]
        new = {key: k, value: separator.join(g["values"])}
        for c in keep:
            new[c] = g["first"].get(c, "")
        new["count"] = len(g["values"])
        out.append(new)
    return [key] + list(keep) + [value, "count"], out, [
        "%d rows -> %d keys" % (len(rows), len(out))]


def csv_count(cols, rows, key, minimum=1):
    # How many rows hold each value of a column, most first (CountKeyValues).
    if key not in cols:
        raise ValueError("The file has no column '%s' (it has: %s)." % (key, ", ".join(cols)))
    counts, shown = {}, {}
    for row in rows:
        v = (row.get(key) or "").strip()
        counts[v.lower()] = counts.get(v.lower(), 0) + 1
        shown.setdefault(v.lower(), v)
    out = [{key: shown[k], "count": n} for k, n in counts.items() if n >= minimum]
    out.sort(key=lambda r: (-r["count"], r[key].lower()))
    return [key, "count"], out, ["%d rows, %d different values%s" % (
        len(rows), len(counts), ", %d shown (count %d or more)" % (len(out), minimum)
        if minimum > 1 else "")]


def csv_dedupe(cols, rows, key):
    # The first row for each value of a column (DeleteDuplicateRows).
    if key not in cols:
        raise ValueError("The file has no column '%s' (it has: %s)." % (key, ", ".join(cols)))
    seen, out = set(), []
    for row in rows:
        k = _key(row.get(key))
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
    return list(cols), out, ["%d rows -> %d (%d duplicates removed)"
                             % (len(rows), len(out), len(rows) - len(out))]


def csv_common(files, column):
    # Values found in EVERY file's column (FindCommonEmails). files:
    # [(name, columns, rows)].
    common, shown = None, {}
    for name, cols, rows in files:
        if column not in cols:
            raise ValueError("%s has no column '%s' (it has: %s)." % (name, column, ", ".join(cols)))
        values = set()
        for row in rows:
            v = (row.get(column) or "").strip()
            if v:
                values.add(v.lower())
                shown.setdefault(v.lower(), v)
        common = values if common is None else common & values
    out = [{column: shown[v]} for v in sorted(common or [])]
    return [column], out, ["%d files, %d values in all of them" % (len(files), len(out))]


def csv_json_list(cols, rows, column):
    # A JSON column -> a list of the objects (ConvertCSVtoJSON) and how many
    # rows could not be read.
    import json
    if column not in cols:
        raise ValueError("The file has no column '%s' (it has: %s)." % (column, ", ".join(cols)))
    out, bad = [], 0
    for row in rows:
        text = (row.get(column) or "").strip()
        if not text:
            continue
        try:
            out.append(json.loads(text))
        except ValueError:
            bad += 1
    return out, bad


def csv_explode(cols, rows, prefix):
    # prefix.0.x, prefix.1.x ... columns -> one row per number, as prefix.x
    # (MakeOneParentPerRow and friends). A row with none keeps one row.
    pat = re.compile(r"%s\.(\d+)(?:\.(.+))?$" % re.escape(prefix))
    fields, base = [], []
    for c in cols:
        m = pat.match(c)
        if m:
            name = prefix + ("." + m.group(2) if m.group(2) else "")
            if name not in fields:
                fields.append(name)
        elif c != prefix and not re.fullmatch(re.escape(prefix) + r"(\.count|Count)?", c):
            base.append(c)
    if not fields:
        raise ValueError("No columns named %s.0..., %s.1... in the file." % (prefix, prefix))
    out = []
    for row in rows:
        items = {}
        for c, v in row.items():
            m = pat.match(c or "")
            if m and (v or "") != "":
                items.setdefault(int(m.group(1)), {})[
                    prefix + ("." + m.group(2) if m.group(2) else "")] = v
        keep = {c: row.get(c, "") for c in base}
        if not items:
            out.append(dict(keep))
        for n in sorted(items):
            new = dict(keep)
            new.update(items[n])
            out.append(new)
    return base + fields, out, ["%d rows -> %d" % (len(rows), len(out))]


def filter_forward_steps(values, folder, stamp):
    # The read-only step of 'find' (every filter of the chosen users).
    import os
    if not (values.get("own") or "").strip():
        raise ValueError("Enter your own domains - forwards to them are left out.")
    parse_domain_list(values["own"])
    who = user_scope_argv(values)
    files = {"raw": os.path.join(folder, "Gmail-Filters-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Gmail-OutsideForwardFilters-%s.csv" % stamp)}
    return [("List the Gmail filters of the users",
             ["config", "auto_batch_min", "1", "redirect", "csv", files["raw"],
              "multiprocess", "redirect", "stderr", "-", "multiprocess"] + who
             + ["print", "filters"])], files


def filter_forward_rows(filter_rows, own):
    # GAM's print filters rows whose 'forward' action ('forward x@domain' -
    # GAM source _printFilter) goes to a domain NOT in own (sub-domains of
    # your domains count as yours).
    own = [d.lower() for d in own]
    out = []
    for row in filter_rows:
        found = re.match(r"^forward\s+\S*@(\S+)$", (row.get("forward") or "").strip(), re.I)
        if not found:
            continue
        domain = found.group(1).lower()
        if not any(domain == d or domain.endswith("." + d) for d in own):
            out.append(row)
    return out


def filter_forward_check_report(rows):
    # The report for 'delete': every row needs the user and the filter id.
    if not rows:
        raise ValueError("The file has no rows.")
    for number, row in enumerate(rows, 2):
        if not _PLAIN_EMAIL.fullmatch((row.get("User") or "").strip().lower()) or \
                not re.fullmatch(r"[A-Za-z0-9_-]+", (row.get("id") or "").strip()):
            raise ValueError("Row %d has no User / filter id - use the Gmail-"
                             "OutsideForwardFilters-...csv this task made." % number)
    return rows


def ou_counts_steps(values, folder, stamp):
    import os
    what = values.get("what") or "both"
    if what not in OU_COUNTS_WHAT.values():
        raise ValueError("Choose what to count.")
    files = {key: os.path.join(folder, "OUCounts-%s-%s.csv" % (part, stamp))
             for key, part in (("ous", "OUs-raw"), ("users", "Users-raw"),
                               ("cros", "Chromebooks-raw"), ("report", "PerOU"))}
    steps = [("List every OU", ["redirect", "csv", files["ous"], "print", "ous", "fields",
                                "orgunitpath"])]
    if what in ("both", "users"):
        steps.append(("List every user's OU", ["redirect", "csv", files["users"], "print",
                                               "users", "fields", "orgunitpath,suspended"]))
    if what in ("both", "cros"):
        steps.append(("List every Chromebook's OU and status",
                      ["redirect", "csv", files["cros"], "print", "cros", "fields",
                       "orgunitpath,status"]))
    return steps, files


def ou_counts_report(ou_rows, user_rows, cros_rows, what="both"):
    # -> (headings, one row per OU) - direct counts (users / devices IN that OU).
    counts = {}
    ous = ["/"] + sorted({(r.get("orgUnitPath") or "").strip() for r in ou_rows} - {"", "/"},
                         key=str.lower)
    for ou in ous:
        counts[ou] = {"users": 0, "suspended": 0, "cros": 0, "status": {}}
    statuses = []
    for r in user_rows:
        entry = counts.setdefault((r.get("orgUnitPath") or "/").strip() or "/",
                                  {"users": 0, "suspended": 0, "cros": 0, "status": {}})
        entry["users"] += 1
        if _true(r.get("suspended")):
            entry["suspended"] += 1
    for r in cros_rows:
        entry = counts.setdefault((r.get("orgUnitPath") or "/").strip() or "/",
                                  {"users": 0, "suspended": 0, "cros": 0, "status": {}})
        status = (r.get("status") or "UNKNOWN").strip().upper() or "UNKNOWN"
        entry["cros"] += 1
        entry["status"][status] = entry["status"].get(status, 0) + 1
        if status not in statuses:
            statuses.append(status)
    statuses.sort(key=lambda s: (s != "ACTIVE", s))
    heads = ["orgUnitPath"]
    if what in ("both", "users"):
        heads += ["Users", "Users suspended"]
    if what in ("both", "cros"):
        heads += ["Chromebooks"] + ["Chromebooks %s" % s for s in statuses]
    rows = []
    for ou in sorted(counts, key=lambda o: (o != "/", o.lower())):
        e = counts[ou]
        row = {"orgUnitPath": ou}
        if what in ("both", "users"):
            row.update({"Users": e["users"], "Users suspended": e["suspended"]})
        if what in ("both", "cros"):
            row["Chromebooks"] = e["cros"]
            for s in statuses:
                row["Chromebooks %s" % s] = e["status"].get(s, 0)
        rows.append(row)
    return heads, rows


def user_scope_argv(values, typekey="usertype", valkey="userval"):
    # The {userscope:...} token as argv (the same words build_command makes).
    utype = (values.get(typekey) or "").strip() or "all"
    uval = (values.get(valkey) or "").strip()
    word = {"all": "all", "ou": "ou", "ou_children": "ou_and_children", "group": "group",
            "query": "query", "csv": "csvfile", "user": "user"}.get(utype)
    if word is None:
        raise ValueError("Choose which users.")
    if utype == "all":
        return ["all", "users"]
    if not uval:
        raise ValueError("Enter the OU path, group, query, CSV file:column or user.")
    return [word, uval]


def group_compare_steps(values, folder, stamp):
    # Two read-only GAM commands; group_compare_report compares them.
    import os
    groups = (values.get("groups") or "").strip()
    if not groups:
        raise ValueError("Enter the group (or several, comma separated).")
    who = user_scope_argv(values)
    files = {"users": os.path.join(folder, "Compare-Users-raw-%s.csv" % stamp),
             "members": os.path.join(folder, "Compare-GroupMembers-raw-%s.csv" % stamp),
             "report": os.path.join(folder, "Compare-UsersVsGroup-%s.csv" % stamp)}
    nested = ["recursive", "noduplicates"] if (values.get("nested") or "yes") == "yes" else []
    return [("List the users", ["redirect", "csv", files["users"]] + who
             + ["print", "users", "fields", "primaryemail"]),
            ("List the group's members", ["redirect", "csv", files["members"], "print",
                                          "group-members", "fields", "email,type"] + nested
             + ["select", groups])], files


def group_compare_report(user_rows, member_rows):
    # -> rows {email, status}: in the users but not the group, then in the
    # group but not the users (only USER members - groups inside are
    # expanded by GAM when 'recursive' is on).
    users = {(r.get("primaryEmail") or "").strip().lower() for r in user_rows}
    users.discard("")
    members = {(r.get("email") or "").strip().lower() for r in member_rows
               if (r.get("type") or "").strip().upper() == "USER"}
    members.discard("")
    return ([{"email": e, "status": "in the users, NOT in the group"}
             for e in sorted(users - members)]
            + [{"email": e, "status": "in the group, NOT in the users"}
               for e in sorted(members - users)])


def sd_writers_command(record, mode):
    # The change, one row of the record file at a time.
    return ["csv", record, "gam", "update", "drivefileacl", "shareddriveid",
            "~drive_id", "~perm", "role", SD_WRITERS_ROLE[mode], "nodetails"]


_SD_ID = re.compile(r"[A-Za-z0-9_-]{10,}")
_SD_PERM = re.compile(r"id:[A-Za-z0-9_-]+")


def sd_writers_record(gam_rows):
    # GAM's print shareddriveacls rows -> the record rows (one per member;
    # GAM can repeat a member once per permissionDetails entry).
    out, seen = [], set()
    for row in gam_rows:
        drive = (row.get("id") or "").strip()
        pid = (row.get("permission.id") or "").strip()
        if (row.get("permission.role") or "").strip() != "writer":
            continue
        if not _SD_ID.fullmatch(drive) or not re.fullmatch(r"[A-Za-z0-9_-]+", pid):
            continue
        if (drive, pid) in seen:
            continue
        seen.add((drive, pid))
        out.append({"drive_id": drive, "drive_name": (row.get("name") or "").strip(),
                    "type": (row.get("permission.type") or "").strip(),
                    "member": (row.get("permission.emailAddress") or
                               row.get("permission.domain") or "").strip(),
                    "perm": "id:" + pid, "old_role": "writer"})
    return out


def sd_writers_check_record(rows):
    # The record file for "put back": every row needs a drive ID and a
    # permission ID ('id:...'). Raises ValueError naming the first bad row.
    if not rows:
        raise ValueError("The file has no rows.")
    for number, row in enumerate(rows, 2):
        if not _SD_ID.fullmatch((row.get("drive_id") or "").strip()) or \
                not _SD_PERM.fullmatch((row.get("perm") or "").strip()):
            raise ValueError("Row %d has no drive_id / perm (id:...) - use the "
                             "SharedDrives-Contributors-...csv this task saved."
                             % number)
    return rows


def _sd_unshare_plan(rows, mode):
    # unshare_plan for the Shared Drive report (SD_REPORT_COLUMNS). Files are
    # changed as the organizer named in act_as; a drive's own members with
    # admin rights. Each permission is removed by its ID ('id:<permission
    # id>' - <DriveFilePermissionID> in GamCommands.txt).
    actions, skipped = {}, []
    for row in rows:
        where = (row.get("where") or "").strip().lower()
        doc = (row.get("doc_id") or "").strip()
        pid = (row.get("perm_id") or "").strip()
        kind = (row.get("kind") or "").strip().lower()
        target = (row.get("target") or "").strip().lower()
        role = (row.get("role") or "").strip().lower()
        act_as = (row.get("act_as") or "").strip().lower()
        title = (row.get("doc_title") or "").strip() or doc
        found = _true(row.get("discoverable"))
        if where not in ("file", "drive"):
            skipped.append((title, "the 'where' column must be file or drive"))
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", doc) or \
                not re.fullmatch(r"[A-Za-z0-9_-]+", pid):
            skipped.append((title, "no file ID or permission ID in this row"))
            continue
        if where == "file" and not _PLAIN_EMAIL.fullmatch(act_as):
            skipped.append((title, "no organizer to act as (act_as)"))
            continue
        if kind in ("user", "group"):
            if mode == UNSHARE_MODES[2]:
                continue
            if not _PLAIN_EMAIL.fullmatch(target):
                skipped.append((title, "recipient is not a valid address"))
                continue
            how = kind
        elif kind == "domain":
            if mode == UNSHARE_MODES[2]:
                continue
            if not _DOMAIN_NAME.fullmatch(target):
                skipped.append((title, "not a valid domain name"))
                continue
            how = "domain" if found else "domainwithlink"
        elif kind == "anyone" and where == "file":
            if mode == UNSHARE_MODES[1]:
                continue
            how = "anyone" if found else "anyonewithlink"
        else:
            skipped.append((title, "unexpected kind of sharing: %r" % kind))
            continue
        if role not in _RESHARE_ROLES:
            skipped.append((title, "unexpected role: %r" % role))
            continue
        actions[(where, doc, pid)] = {
            "owner": act_as, "doc_id": doc, "perm": "id:" + pid, "kind": how,
            "target": target, "role": role, "doc_title": title, "scope": where}
    if not actions:
        raise ValueError("Nothing to remove for this choice."
                         + (" (%d rows skipped - see the reasons in the output.)"
                            % len(skipped) if skipped else ""))
    return list(actions.values()), skipped


# =============================================================================
# SECTION: Retire Chromebooks - powerwash, then deprovision (2.76)
# =============================================================================
# From the GAM Public Chat (08-12-2026): admins who retire hundreds of
# Chromebooks a summer send remote_powerwash and THEN deprovision; devices
# that are off powerwash when they next come online. A deprovisioned device
# no longer takes commands, so the order matters.
RETIRE_STEPS = [
    ("Powerwash (wipe) the devices",
     "{crosscope:crostype:crosval} issuecommand command remote_powerwash "
     "times_to_check_status 1 doit"),
    ("Deprovision (retire) the devices",
     "{crosscope:crostype:crosval} update action deprovision_retiring_device "
     "acknowledge_device_touch_requirement"),
]


def retire_plan(task, values):
    # [(label, argv)] for the Retire workflow, built with the task's own
    # fields. ALL devices is refused (the field has no such choice, and this
    # double-checks a hand-edited value).
    if (values.get("crostype") or "").strip() in ("", "all"):
        raise ValueError("Choose which devices (serials, an OU, or a query) - "
                         "retiring ALL devices is not offered.")
    if not (values.get("crosval") or "").strip():
        raise ValueError("Type the serial numbers, OU path or query.")
    steps = []
    for label, template in RETIRE_STEPS:
        _display, argv, error = build_command(
            {"template": template, "fields": task["fields"]}, values)
        if error:
            raise ValueError(error)
        steps.append((label, argv))
    return steps


# =============================================================================
# SECTION: DLP detector lists (2.76)
# =============================================================================
# A detector's URL or word list, edited in a window (GAM Public Chat
# 07-29-2026, Ross: info policies <name> formatjson -> edit -> update policy
# json file). Field names: urlList.urls (Ross's example) and wordList.words
# (GAM 7.48.16 doCreateUpdateCIPolicy). GAM itself drops the read-only times
# and the OU path/group email before sending the update.
_DETECTOR_LISTS = {"settings/detector.url_list": ("urlList", "urls", "URL"),
                   "settings/detector.word_list": ("wordList", "words", "word")}


DETECTOR_TYPES = list(_DETECTOR_LISTS)


def detector_items(policy):
    # (kind word, [items]) for a URL- or word-list detector; ValueError for
    # any other policy (regular expressions etc. are edited in the console).
    stype = (policy.get("setting") or {}).get("type", "")
    if stype not in _DETECTOR_LISTS:
        raise ValueError("This is not a URL list or word list detector (%s) - "
                         "change it in the Admin console." % (stype or "unknown"))
    outer, inner, word = _DETECTOR_LISTS[stype]
    value = policy["setting"].get("value") or {}
    items = (value.get(outer) or {}).get(inner) or []
    return word, [str(i) for i in items]


def detector_lines(text, word):
    # Text box -> clean list: one per line, blanks and duplicates dropped
    # (case-insensitive, first spelling kept). URLs may not contain spaces.
    out, seen = [], set()
    for line in (text or "").splitlines():
        item = line.strip()
        if not item or item.lower() in seen:
            continue
        if word == "URL" and re.search(r"\s", item):
            raise ValueError("A URL cannot contain spaces: " + item)
        seen.add(item.lower())
        out.append(item)
    if not out:
        raise ValueError("The list cannot be empty - Google requires at least "
                         "one entry.")
    return out


def detector_with_items(policy, items):
    # A copy of the policy JSON with the new list, ready for 'gam update
    # policy json file <file>'. 'warnings' (added by GAM's display) is dropped.
    import copy
    new = copy.deepcopy(policy)
    new.pop("warnings", None)
    outer, inner, _word = _DETECTOR_LISTS[new["setting"]["type"]]
    new["setting"].setdefault("value", {}).setdefault(outer, {})[inner] = list(items)
    return new


def detector_diff(old, new):
    # (added, removed) between two lists, case-insensitive.
    o = {i.lower() for i in old}
    n = {i.lower() for i in new}
    return ([i for i in new if i.lower() not in o],
            [i for i in old if i.lower() not in n])


# =============================================================================
# SECTION: Chromebook "Class of" OU rollover (2.76)
# =============================================================================
# Many districts keep a Chromebook OU per graduating class ("Class of 27",
# "Class of 2027", "Grad 2027") under each campus, and move it to the next
# campus as the students move up. This finds those OUs by their naming
# pattern, works out which container holds which grade, and plans the moves
# and the new incoming class for a school year. Nothing is assumed about
# names or nesting - everything comes from the OU tree:
#   grade = school year (the fall year) + 13 - class year
#   e.g. 2026-2027: Class of 2027 = grade 12, Class of 2040 = PK (-1).
# Containers: the parent OU of each class OU. Whole containers are taken
# most Chromebooks first (see classof_grade_map); one whose grades overlap a
# container already taken "keeps its own classes" (nothing moves in or out;
# it just gets its new lowest grade) - e.g. an alternative campus. The admin
# can switch any container in the window.
# Lessons from the 06-24-2026 live run of the PowerShell version:
#   - 'gam create org <leaf> parent <parent>' - never the full path there.
#   - a child OU moves WITH its parent; never move it separately.
GRADE_NAMES = {-2: "EE", -1: "PK", 0: "K"}
_YEAR_TOKEN = re.compile(r"(?<!\d)(\d{4}|\d{2})(?!\d)")
_CLASS_WORDS = re.compile(r"(?i)class|grad|cohort|year|\byr\b")


def grade_name(grade):
    return GRADE_NAMES.get(grade, str(grade))


def school_year_now(today=None):
    # The fall year of the school year the OU tree is set up for, judged by
    # the date: from September 1 on it is this year, before that last year
    # (so a rollover done in June, July or August prepares the coming year).
    today = today or _dt.date.today()
    return today.year if today.month >= 9 else today.year - 1


def classof_default_years(saved, today=None):
    # (set up now, prepare for) for the rollover window. 'saved' = the
    # school year GAMGUI last finished a rollover for (gamgui.ini), or None.
    # Live test 10-02-2026: re-opening the window right after a rollover
    # still said "set up now for <last year>", so Find planned a SECOND
    # rollover. Now: set up = the saved year when there is one; prepare =
    # next year in the rollover season (March-August), else this year - and
    # never earlier than 'set up', so right after a rollover nothing is left.
    today = today or _dt.date.today()
    now = school_year_now(today)
    current = saved or now
    target = now + 1 if 3 <= today.month <= 8 else now
    return current, max(current, target)


def school_year_label(fall_year):
    return "%d-%d" % (fall_year, fall_year + 1)


def _leaf(path):
    return path.rstrip("/").rsplit("/", 1)[-1]


def _parent(path):
    parent = path.rstrip("/").rsplit("/", 1)[0]
    return parent or "/"


def _under(path, root):
    root = "/" + root.strip("/")
    return root == "/" or path == root or path.startswith(root + "/")


def classof_templates(ou_paths, fall_year, root="/"):
    # Naming patterns that look like class years, best first:
    # [{"template": "Class of {YY}", "years": n, "ous": n, "example": leaf}].
    # A pattern needs 3+ different years; words like 'class' or 'grad' and
    # more OUs rank higher. Years outside fall_year-15 .. +20 are ignored
    # (so 'Grade 09' is not read as 2009).
    found = {}
    for path in ou_paths:
        if not _under(path, root) or path == "/":
            continue
        leaf = _leaf(path)
        for m in _YEAR_TOKEN.finditer(leaf):
            text = m.group(1)
            year = int(text) if len(text) == 4 else 2000 + int(text)
            if not fall_year - 15 <= year <= fall_year + 20:
                continue
            template = (leaf[:m.start()] + ("{YYYY}" if len(text) == 4 else "{YY}")
                        + leaf[m.end():])
            entry = found.setdefault(template, {"years": set(), "ous": 0,
                                                "example": leaf})
            entry["years"].add(year)
            entry["ous"] += 1
    out = [{"template": t, "years": len(e["years"]), "ous": e["ous"],
            "example": e["example"]}
           for t, e in found.items() if len(e["years"]) >= 3]
    out.sort(key=lambda e: (not _CLASS_WORDS.search(e["template"]),
                            -e["ous"], e["template"]))
    return out


def classof_main_and_variants(templates):
    # The class OU pattern and its variants ("Class of {YY} Bluetooth" is a
    # variant of "Class of {YY}"): main = the best-ranked pattern that is not
    # a longer form of another one.
    names = [t["template"] for t in templates]
    mains = [n for n in names
             if not any(o != n and o in n for o in names)]
    if not mains:
        return "", []
    main = mains[0]
    return main, [n for n in names if n != main and main in n]


def _template_regex(template):
    part = re.escape(template)
    part = part.replace(re.escape("{YYYY}"), r"(?P<y>\d{4})")
    part = part.replace(re.escape("{YY}"), r"(?P<y>\d{2})")
    return re.compile(r"(?i)^" + part + r"$")


def _template_year(template, leaf):
    m = _template_regex(template).match(leaf)
    if not m:
        return None
    text = m.group("y")
    return int(text) if len(text) == 4 else 2000 + int(text)


def classof_leaf(template, year):
    # The OU name for a class year: 'Class of {YY}' + 2041 -> 'Class of 41'.
    return (template.replace("{YYYY}", "%04d" % year)
            .replace("{YY}", "%02d" % (year % 100)))


def classof_discover(ou_paths, template, variants, fall_year, root="/",
                     device_counts=None):
    # Finds every class OU (its name matches the template) under root.
    # Returns {"cohorts": [...], "containers": {parent: [cohort, ...]},
    #          "paths": set of all OU paths}. Each cohort: path, parent,
    # leaf, year, grade (for fall_year), children (variant OUs inside it),
    # siblings (variant OUs next to it, same year), devices (in the class OU
    # and everything under it, plus its sibling variants).
    paths = set(p.rstrip("/") or "/" for p in ou_paths)
    counts = device_counts or {}
    children = {}
    for p in paths:
        if p != "/":
            children.setdefault(_parent(p), []).append(p)

    def subtree_devices(path):
        return sum(n for ou, n in counts.items()
                   if ou == path or ou.startswith(path + "/"))

    cohorts = []
    for p in sorted(paths):
        if p == "/" or not _under(p, root):
            continue
        year = _template_year(template, _leaf(p))
        if year is None:
            continue
        # A class OU inside another class OU is not a class of its own.
        if _template_year(template, _leaf(_parent(p))) is not None:
            continue
        parent = _parent(p)
        kids = [c for c in children.get(p, [])
                if any(_template_year(v, _leaf(c)) == year for v in variants)]
        sibs = [s for s in children.get(parent, [])
                if s != p and any(_template_year(v, _leaf(s)) == year
                                  for v in variants)]
        cohorts.append({"path": p, "parent": parent, "leaf": _leaf(p),
                        "year": year, "grade": fall_year + 13 - year,
                        "children": sorted(kids), "siblings": sorted(sibs),
                        "devices": subtree_devices(p)
                        + sum(subtree_devices(s) for s in sibs)})
    containers = {}
    for c in cohorts:
        containers.setdefault(c["parent"], []).append(c)
    return {"cohorts": cohorts, "containers": containers, "paths": paths,
            "template": template, "variants": list(variants),
            "fall_year": fall_year, "root": root}


def classof_grade_map(disc, separate=(), force=()):
    # {grade: container} and the sorted list of containers that keep their
    # own classes. Whole OUs are taken in order - the ones the admin forced
    # into the ladder first, then the most Chromebooks, then the fewest
    # grades - and an OU whose grades overlap one already taken keeps its
    # own classes (an alternative campus, a program spanning many grades, a
    # second feeder campus). 2.76 live-test review: deciding grade by grade
    # let a small alternative high school (grades 10-12) take those grades
    # from the real high school (9-12); the device count prevents that.
    # 'separate' = OUs the admin marked "keeps its own classes";
    # 'force' = OUs the admin put in the ladder.
    grades = {}
    devices = {}
    for parent, cs in disc["containers"].items():
        gs = {c["grade"] for c in cs if -2 <= c["grade"] <= 12}
        if gs:
            grades[parent] = gs
            devices[parent] = sum(c["devices"] for c in cs)
    order = sorted(grades, key=lambda p: (p not in force, -devices[p],
                                          len(grades[p]), p))
    gmap, keep_own = {}, []
    for parent in order:
        if parent in separate and parent not in force:
            keep_own.append(parent)
        elif grades[parent] & set(gmap):
            keep_own.append(parent)
        else:
            for g in grades[parent]:
                gmap[g] = parent
    return gmap, sorted(keep_own)


def classof_plan(disc, gmap, keep_own, target_year, graduated_ou=""):
    # The ordered actions that set the OUs up for target_year (fall year):
    # [{"kind": "move"|"create"|"note"|"warn", "text": ..., "argv": [...]}].
    # It compares where things ARE with where they SHOULD BE, so running it
    # again after a partial run only does what is left.
    template = disc["template"]
    paths = set(disc["paths"])
    ladder = set(gmap.values())
    keep_own = set(keep_own)
    graduated_ou = ("/" + graduated_ou.strip("/")) if graduated_ou.strip() else ""
    moves, creates, notes = [], [], []
    planned = set()

    def move(path, dest, why):
        target = dest.rstrip("/") + "/" + _leaf(path)
        # Also catches two classes with the same name headed for the same
        # OU (e.g. 'Class of 27' from two campuses into one Graduated OU).
        if target in paths or target in planned:
            notes.append({"kind": "warn", "text": "Cannot move %s into %s - an "
                          "OU named '%s' is already there. Merge them by hand."
                          % (path, dest, _leaf(path)), "argv": []})
            return
        planned.add(target)
        moves.append({"kind": "move", "text": "Move %s  ->  into %s  (%s)"
                      % (path, dest, why), "path": path, "dest": dest,
                      "argv": ["update", "org", path, "parent", dest]})

    # Oldest class first; for the same year the campus OUs come before the
    # ones that keep their own classes (they win a name clash in a
    # Graduated OU).
    for c in sorted(disc["cohorts"], key=lambda c: (c["year"],
                                                    c["parent"] in keep_own,
                                                    c["path"])):
        if c["parent"] not in ladder and c["parent"] not in keep_own:
            continue                      # e.g. an archive of old classes
        g = target_year + 13 - c["year"]
        if g > 12:
            if graduated_ou and c["parent"] != graduated_ou:
                for p in [c["path"]] + c["siblings"]:
                    move(p, graduated_ou, "graduated")
            elif not graduated_ou:
                notes.append({"kind": "note", "text": "%s graduated (%d "
                              "Chromebooks) - left where it is."
                              % (c["path"], c["devices"]), "argv": []})
            continue
        if c["parent"] in keep_own:
            # E.g. two elementary campuses feeding one middle school: only
            # one OU per class can move up, so the other campus's class
            # would sit there. Say so instead of doing something surprising.
            # Grades the OU holds NOW (discovery year); a class going past
            # the top one (but not graduating) is the case above.
            top = max([x["grade"] for x in disc["containers"][c["parent"]]
                       if -2 <= x["grade"] <= 12] or [12])
            if top < g <= 12:
                notes.append({"kind": "warn", "text": "%s will be grade %s - "
                              "above the grades this OU holds, so it stays "
                              "where it is. Move its Chromebooks by hand if "
                              "the students change campus." % (
                                  c["path"], grade_name(g)), "argv": []})
            continue
        if g < -2:
            continue
        dest = gmap.get(g)
        if not dest:
            notes.append({"kind": "warn", "text": "%s will be grade %s - no OU "
                          "is set for that grade, so it stays where it is."
                          % (c["path"], grade_name(g)), "argv": []})
            continue
        if dest != c["parent"]:
            for p in [c["path"]] + c["siblings"]:
                move(p, dest, "grade " + grade_name(g))

    def variants_for(container):
        # Variant names seen beside/inside class OUs - this container's
        # first, else anywhere - as (template, inside?) pairs.
        pool = disc["containers"].get(container) or disc["cohorts"]
        found = []
        for c in pool:
            for kid in c["children"]:
                found += [(v, True) for v in disc["variants"]
                          if _template_year(v, _leaf(kid)) == c["year"]]
            for sib in c["siblings"]:
                found += [(v, False) for v in disc["variants"]
                          if _template_year(v, _leaf(sib)) == c["year"]]
        return sorted(set(found))

    def create(parent, year, grade):
        leaf = classof_leaf(template, year)
        path = parent.rstrip("/") + "/" + leaf
        if path in paths:
            return
        creates.append({"kind": "create", "text": "Create %s  (grade %s)"
                        % (path, grade_name(grade)), "path": path,
                        "argv": ["create", "org", leaf, "parent", parent]})
        for vt, inside in variants_for(parent):
            vleaf = classof_leaf(vt, year)
            vparent = path if inside else parent
            creates.append({"kind": "create", "text": "Create %s/%s"
                            % (vparent.rstrip("/"), vleaf),
                            "path": vparent.rstrip("/") + "/" + vleaf,
                            "argv": ["create", "org", vleaf, "parent", vparent]})

    ladder_years = {c["year"] for c in disc["cohorts"] if c["parent"] in ladder}
    for g in sorted(gmap):
        year = target_year + 13 - g
        if year not in ladder_years:
            create(gmap[g], year, g)
    for container in sorted(keep_own):
        have = {c["year"] for c in disc["containers"].get(container, [])}
        now = [c["grade"] for c in disc["containers"].get(container, [])
               if -2 <= c["grade"] <= 12]
        if not now:
            continue
        for g in range(min(now), max(now) + 1):
            year = target_year + 13 - g
            if year not in have:
                create(container, year, g)
    return moves + creates + notes


# =============================================================================
# SECTION: Chromebooks in GRADE-named OUs - yearly rollover (2.80)
# =============================================================================
# For districts whose Chromebook OUs are named for a GRADE ("Grade 5",
# "5th Grade", "Grade 05", "Kindergarten", "PK") instead of a class year.
# The OUs stay; the DEVICES move up one grade: everything directly in the
# 'Grade 11' OU goes to 'Grade 12', and so on. Two rules make that safe:
#   - Highest grade first (12 -> graduated, then 11 -> 12 ... ), so a grade
#     is empty before the grade below moves in.
#   - NOT repeatable: moving devices twice would push them up two grades,
#     so the window remembers which steps finished for which school year
#     and never runs a finished step again (unlike the 'Class of' rollover,
#     which compares where OUs ARE with where they SHOULD be).
# GAM: 'gam update org <new OU> move cros_ou <old OU>' - cros_ou = devices
# DIRECTLY in that OU (not its sub-OUs), moved in batches
# (_batchMoveCrOSesToOrgUnit, GAM 7.48.17 source).
_GRADE_PATTERNS = [
    # (regex, how to read the grade) - the first that matches wins.
    (re.compile(r"(?i)\b(?:grade|gr\.?)\s*0*(\d{1,2})\b"), "number"),
    (re.compile(r"(?i)\b0*(\d{1,2})(?:st|nd|rd|th)\s*grade\b"), "number"),
    (re.compile(r"(?i)\b(?:grade|gr\.?)\s*(kg|k|pk|ee)\b"), "letters"),
    (re.compile(r"(?i)\b(pre-?k|pre-?kindergarten|prekindergarten)\b"), "pk"),
    (re.compile(r"(?i)\b(kindergarten|kinder)\b"), "k"),
]
_GRADE_LETTERS = {"kg": 0, "k": 0, "pk": -1, "ee": -2}
_DEVICE_WORDS = re.compile(r"(?i)chromebook|device|laptop|cros|\bcb\b|1:1|1to1|one.?to.?one")


def grade_of_ou(leaf):
    # (grade, pattern) for an OU name that names a grade, else None.
    # 'pattern' is the name with the grade part replaced by '#', so OUs of
    # one ladder ('Grade 3', 'Grade 4') share it.
    for regex, how in _GRADE_PATTERNS:
        m = regex.search(leaf)
        if not m:
            continue
        text = m.group(1).lower()
        if how == "number":
            grade = int(text)
        elif how == "letters":
            grade = _GRADE_LETTERS[text]
        else:
            grade = -1 if how == "pk" else 0
        if not -2 <= grade <= 12:
            return None
        return grade, leaf[:m.start(1)] + "#" + leaf[m.end(1):]
    return None


def gradeou_discover(ou_paths, device_counts, root="/"):
    # Every OU under root whose name names a grade:
    # [{"path", "parent", "grade", "pattern", "devices", "suggested", "why"}]
    # 'suggested' = included by default: the path looks like a device OU
    # (Chromebook, device, laptop...). Student ACCOUNT OUs are often named
    # for grades too; those are listed but left out unless the admin adds
    # them (a few misfiled Chromebooks in a user OU are not a device ladder).
    counts = device_counts or {}
    paths = sorted(set(p.rstrip("/") for p in ou_paths if p.rstrip("/")))
    kids = {}
    for p in paths:
        kids.setdefault(_parent(p), []).append(_leaf(p))
    found = []
    for path in paths:
        if path == "/" or not _under(path, root):
            continue
        got = grade_of_ou(_leaf(path))
        if not got:
            continue
        grade, pattern = got
        devices = counts.get(path, 0)
        # 2.80 (FSISD's tree): a grade OU that holds 'Class of 27'-style OUs
        # belongs to the Class-of rollover - moving devices here too would
        # fight it.
        classof = [k for k in kids.get(path, [])
                   if _CLASS_WORDS.search(k) and _YEAR_TOKEN.search(k)]
        suggested = bool(_DEVICE_WORDS.search(path)) and not classof
        why = ("holds 'Class of' OUs (e.g. %s) - use the 'Class of' rollover"
               % classof[0] if classof else
               "" if suggested else
               "name does not say Chromebook/device - add it if it is a "
               "device OU")
        found.append({"path": path, "parent": _parent(path), "grade": grade,
                      "pattern": pattern, "devices": devices,
                      "suggested": suggested, "why": why})
    # Each campus's OUs together, in grade order (K, 1, 2 ... 9, 10 - not
    # 'Grade 10' before 'Grade 9').
    found.sort(key=lambda f: (f["parent"].lower(), f["grade"], f["path"]))
    return found


def gradeou_plan(ous, graduated_ou="", leave_graduated=False, done=()):
    # The moves for one rollover, highest grade first:
    # [{"kind": "move"|"note"|"warn"|"done", "text", "src", "dest",
    #   "grade", "devices", "argv"}]. 'ous' = the INCLUDED OUs from
    # gradeou_discover. 'done' = source OUs already moved this school year
    # (shown as done, never run again).
    # Where grade g goes: the OU for grade g+1 in the SAME ladder (same
    # parent and name pattern) if there is one; otherwise the only OU for
    # grade g+1 among all included ones (e.g. 5th grade at an elementary
    # campus -> 6th grade at the middle school). Two or more = ambiguous ->
    # a warning, not a guess. Grade 12 -> the graduated OU.
    graduated_ou = ("/" + graduated_ou.strip("/")) if graduated_ou.strip() else ""
    done = set(done)
    by_grade = {}
    for o in ous:
        by_grade.setdefault(o["grade"], []).append(o)
    out = []
    # OUs whose Chromebooks are NOT moving out although they should (no OU
    # for the next grade, ambiguous, graduated with nowhere to go). Moving
    # the grade below INTO one of them would mix two grades, so that move
    # waits too - and so on down. (Found on FSISD's tree: 8th grade had no
    # 9th-grade OU, yet 7th grade would have moved in.) An explicit 'leave
    # the graduates' is the admin's choice and does not block.
    stuck = set()

    def hold(o, text):
        out.append({"kind": "warn", "text": text, "argv": [], "src": o["path"]})
        if o["devices"]:
            stuck.add(o["path"])

    for o in sorted(ous, key=lambda o: (-o["grade"], o["path"])):
        g = o["grade"]
        if g >= 12:
            if leave_graduated:
                out.append({"kind": "note", "text": "%s: %d Chromebooks stay "
                            "(graduated) - next year's seniors join them."
                            % (o["path"], o["devices"]), "argv": []})
                continue
            if not graduated_ou:
                hold(o, "%s: say where graduated seniors' Chromebooks go (or "
                     "choose to leave them)." % o["path"])
                continue
            dest = graduated_ou
        else:
            same = [x for x in by_grade.get(g + 1, [])
                    if x["parent"] == o["parent"] and x["pattern"] == o["pattern"]]
            cands = same or by_grade.get(g + 1, [])
            if not cands:
                hold(o, "%s (grade %s): no included OU for grade %s - its "
                     "Chromebooks stay." % (o["path"], grade_name(g),
                                            grade_name(g + 1)))
                continue
            if len(cands) > 1:
                hold(o, "%s (grade %s): more than one OU for grade %s (%s) - "
                     "its Chromebooks stay; move them by hand." % (
                         o["path"], grade_name(g), grade_name(g + 1),
                         ", ".join(c["path"] for c in cands)))
                continue
            dest = cands[0]["path"]
        if dest in stuck and o["path"] not in done:
            hold(o, "Waiting: %s  ->  %s would mix two grades (Chromebooks "
                 "still in %s are not moving out)." % (o["path"], dest, dest))
            continue
        step = {"src": o["path"], "dest": dest, "grade": g,
                "devices": o["devices"],
                "argv": ["update", "org", dest, "move", "cros_ou", o["path"]]}
        if o["path"] in done:
            step.update(kind="done", text="Already done: %s  ->  %s"
                        % (o["path"], dest))
        else:
            step.update(kind="move", text="Move %d Chromebooks: %s  ->  %s"
                        % (o["devices"], o["path"], dest))
        out.append(step)
    return out


def contains_password(argv):
    # True when the command carries a password value ('password <value>'),
    # which a saved script would store in plain text.
    low = [a.lower() for a in argv]
    return any(a == "password" and i + 1 < len(argv) for i, a in enumerate(low))


def _check_script_path(label, path):
    # Scripts are saved as plain ASCII (cmd.exe reads .bat files in the OEM
    # code page, so accented letters would be mangled). A path we cannot write
    # faithfully is refused with a clear message instead of being silently
    # turned into '?' characters. A line break could inject a second command.
    if any(ord(ch) > 126 or ord(ch) < 32 for ch in path):
        raise ValueError(label + " contains a non-ASCII character or a line "
                         "break, so it cannot be written into a script safely:\n"
                         + path + "\nSave the script, then type the path in by "
                         "hand, or move that folder to a plain-ASCII path.")


def _sh_dq(text):
    # Escapes text for use INSIDE a bash double-quoted string: backslash,
    # double quote, dollar sign, and backtick are the only special characters
    # there (a backtick would otherwise run a command).
    for ch in ("\\", '"', "$", "`"):
        text = text.replace(ch, "\\" + ch)
    return text


def make_bat_script(argv, gam_path, script_name, title, version, today,
                    cfg_dir=""):
    # Returns the text of a Windows batch file (CRLF line endings) that runs
    # gam with 'argv', appends everything to Logs\<script_name>.log next to
    # the script, and exits with gam's own exit code - ready to double-click
    # or to schedule in Task Scheduler. 'today' is MM-DD-YYYY. 'cfg_dir' is
    # GAMGUI's "GAM config folder" setting (blank = GAM's own default); when
    # set, the script sets GAMCFGDIR so a scheduled run uses the same gam.cfg.
    _check_script_path("The gam path", gam_path)
    _check_script_path("The GAM config folder", cfg_dir)
    name = _safe_text(script_name) or "gam-task"
    what = _safe_text(title) or "GAM command"
    shown = _safe_text(" ".join(argv))[:150]
    lines = [
        "@ECHO OFF",
        "SETLOCAL ENABLEEXTENSIONS",
        ":: " + "=" * 77,
        ":: Script:   " + name + ".bat",
        ":: Author:   Generated by GAMGUI " + version + " (Save as script)",
        ":: Created:  " + today,
        ":: Modified: " + today,
        ":: Version:  1.0",
        "::",
        ":: Purpose:",
        "::   " + what,
        "::   Runs: gam " + shown,
        "::",
        ":: Usage:",
        "::   " + name + ".bat   (double-click, or schedule it in Task Scheduler)",
        "::",
        ":: Requirements:",
        "::   GAM7 installed and authorized. Set GAM below if it is not at the",
        "::   path shown. No admin rights needed unless GAM itself needs them.",
        "::",
        ":: Notes:",
        "::   Output and a start/end line with the exit code are appended to",
        "::   Logs\\" + name + ".log next to this script. Exit code = GAM's.",
        ":: " + "=" * 77,
        "",
        ":INIT",
        ":: Where gam.exe lives - change this if GAM is installed elsewhere.",
        'SET "GAM=' + gam_path.replace("%", "%%") + '"',
    ]
    if cfg_dir:
        lines += [
            ":: GAM's config folder (the folder holding gam.cfg), as set in",
            ":: GAMGUI. Delete this line to use GAM's own default instead.",
            'SET "GAMCFGDIR=' + cfg_dir.replace("%", "%%") + '"',
        ]
    lines += [
        ":: Log folder and file, kept next to this script.",
        'SET "LOGDIR=%~dp0Logs"',
        'SET "LOG=%LOGDIR%\\' + name + '.log"',
        'IF NOT EXIST "%LOGDIR%" MKDIR "%LOGDIR%"',
        ":: Stop with a clear message if gam.exe is missing. (A GOTO, not an",
        ":: IF ( ... ) block: a ) inside a path such as 'Program Files (x86)'",
        ":: would end the block early.)",
        'IF NOT EXIST "%GAM%" GOTO :NOGAM',
    ]
    if cfg_dir:
        lines += [
            ":: Without gam.cfg in that folder GAM would quietly start a new,",
            ":: unauthorized configuration there - stop with a message instead.",
            'IF NOT EXIST "%GAMCFGDIR%\\gam.cfg" GOTO :NOCFG',
        ]
    lines += [
        "",
        ":MAIN",
        "CALL :STAMP",
        '>>"%LOG%" ECHO [%STAMP%] START ' + what,
        ":: The GAM command, exactly as built in GAMGUI. The log redirection",
        ":: comes FIRST on purpose: an argument with an odd number of quotes",
        ":: would otherwise make cmd.exe read a redirection at the END of the",
        ":: line as part of the quoted text.",
        '>>"%LOG%" 2>&1 "%GAM%" ' + cmd_line_for_bat(argv),
        'SET "RC=%ERRORLEVEL%"',
        "CALL :STAMP",
        '>>"%LOG%" ECHO [%STAMP%] END exit code %RC%',
        'IF NOT "%RC%"=="0" ECHO GAM finished with exit code %RC% - see "%LOG%"',
        'IF "%RC%"=="0" ECHO Done - output is in "%LOG%"',
        "ENDLOCAL & EXIT /B %RC%",
        "",
        ":NOGAM",
        'ECHO ERROR: gam.exe not found at "%GAM%" - edit the GAM line in this script.',
        "CALL :STAMP",
        '>>"%LOG%" ECHO [%STAMP%] ERROR gam.exe not found at "%GAM%"',
        "ENDLOCAL & EXIT /B 2",
        "",
    ]
    if cfg_dir:
        lines += [
            ":NOCFG",
            'ECHO ERROR: gam.cfg not found in "%GAMCFGDIR%" - edit the GAMCFGDIR line in this script.',
            "CALL :STAMP",
            '>>"%LOG%" ECHO [%STAMP%] ERROR gam.cfg not found in "%GAMCFGDIR%"',
            "ENDLOCAL & EXIT /B 3",
            "",
        ]
    lines += [
        ":STAMP",
        ":: Sets STAMP to the current date/time as MM-DD-YYYY HH:MM:SS (the",
        ":: format does not depend on the PC's regional settings).",
        "FOR /F \"usebackq delims=\" %%T IN (`powershell -NoProfile -Command \"Get-Date -Format 'MM-dd-yyyy HH:mm:ss'\"`) DO SET \"STAMP=%%T\"",
        "GOTO :EOF",
        "",
    ]
    return "\r\n".join(lines)


def make_sh_script(argv, gam_path, script_name, title, version, today,
                   cfg_dir=""):
    # The macOS / Linux counterpart: a bash script that runs the same argv
    # (each argument single-quoted, so the shell changes nothing) and logs to
    # Logs/<script_name>.log next to the script. 'cfg_dir' works as in
    # make_bat_script (exported as GAMCFGDIR when set).
    import shlex
    _check_script_path("The gam path", gam_path)
    _check_script_path("The GAM config folder", cfg_dir)
    name = _safe_text(script_name) or "gam-task"
    what = _safe_text(title) or "GAM command"
    lines = [
        "#!/usr/bin/env bash",
        "# " + "=" * 77,
        "# Script:   " + name + ".sh",
        "# Author:   Generated by GAMGUI " + version + " (Save as script)",
        "# Created:  " + today,
        "# Purpose:  " + what,
        "# Usage:    ./" + name + ".sh   (or schedule it with cron)",
        "# Notes:    Output + start/end lines go to Logs/" + name + ".log next",
        "#           to this script. Exit code = GAM's.",
        "# " + "=" * 77,
        "set -u",
        "# Where gam lives - change this if GAM is installed elsewhere.",
        'GAM="${GAM:-' + _sh_dq(gam_path) + '}"',
    ]
    if cfg_dir:
        lines += [
            "# GAM's config folder (the folder holding gam.cfg), as set in GAMGUI.",
            "# Delete this line to use GAM's own default instead.",
            'export GAMCFGDIR="' + _sh_dq(cfg_dir) + '"',
        ]
    lines += [
        'LOGDIR="$(cd "$(dirname "$0")" && pwd)/Logs"',
        'mkdir -p "$LOGDIR"',
        'LOG="$LOGDIR/' + name + '.log"',
        'if [ ! -x "$GAM" ]; then',
        '    echo "ERROR: gam not found at $GAM - edit the GAM line in this script."',
        '    echo "[$(date \'+%m-%d-%Y %H:%M:%S\')] ERROR gam not found at $GAM" >> "$LOG"',
        "    exit 2",
        "fi",
    ]
    if cfg_dir:
        lines += [
            "# Without gam.cfg there GAM would quietly start a new, unauthorized",
            "# configuration - stop with a message instead.",
            'if [ ! -f "$GAMCFGDIR/gam.cfg" ]; then',
            '    echo "ERROR: gam.cfg not found in $GAMCFGDIR - edit the GAMCFGDIR line in this script."',
            '    echo "[$(date \'+%m-%d-%Y %H:%M:%S\')] ERROR gam.cfg not found in $GAMCFGDIR" >> "$LOG"',
            "    exit 3",
            "fi",
        ]
    lines += [
        'echo "[$(date \'+%m-%d-%Y %H:%M:%S\')] START ' + what + '" >> "$LOG"',
        '"$GAM" ' + " ".join(shlex.quote(a) for a in argv) + ' >> "$LOG" 2>&1',
        "RC=$?",
        'echo "[$(date \'+%m-%d-%Y %H:%M:%S\')] END exit code $RC" >> "$LOG"',
        'exit "$RC"',
        "",
    ]
    return "\n".join(lines)


# =============================================================================
# SECTION: Local date/time -> UTC ("Zulu") conversion
# =============================================================================
# Google's Directory API stores a temporary admin role's expiration as an
# RFC 3339 UTC timestamp (roleAssignments expirationDetails.expireTime), and
# GAM's 'create admin ... expires <time>' passes a full timestamp straight
# through to the API (verified in GAM's source, getTimeOrDeltaFromNow). So
# GAMGUI converts the date/time the admin types - in THIS computer's time zone
# - into UTC itself and hands GAM an exact '...Z' timestamp. That way the
# result never depends on gam.cfg's timezone setting.

# How far ahead an expiration may be. GAM's wiki: "it must be within one
# year". 365 days is used so a value right at the edge is never rejected by
# Google after GAMGUI said it was fine.
MAX_EXPIRATION_DAYS = 365

_DATE_FORMATS = ("%Y-%m-%d",       # 2027-01-05  (ISO)
                 "%m-%d-%Y",       # 01-05-2027  (FSISD MM-DD-YYYY standard)
                 "%m/%d/%Y")       # 1/5/2027 or 01/05/2027 (US style)


def _parse_local_date(text):
    # Returns a datetime.date, or None if the text is not a recognized date.
    text = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return _dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_local_time(text):
    # Returns (hour, minute) in 24-hour form, or None if unrecognized.
    # Blank means midnight (00:00). Accepts 24-hour '14:30' or '14:30:00' and
    # 12-hour '2:30 PM', '2:30pm', '2 PM', '12 AM' (midnight), '12 PM' (noon).
    text = text.strip().upper().replace(".", "")
    if not text:
        return (0, 0)
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(AM|PM)?", text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(4)
    if m.group(2) is None and ampm is None:
        return None                    # a bare number like '9' is ambiguous
    if minute > 59 or (m.group(3) and int(m.group(3)) > 59):
        return None
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ampm == "PM" else 0)
    elif hour > 23:
        return None
    return (hour, minute)


# Rules a {zulu:DATEKEY:TIMEKEY:RULE} token can apply to the converted time:
#   any    - no limit (e.g. focus time, which may be in the past)
#   future - must be after now (e.g. a group membership that expires)
#   year   - after now AND within MAX_EXPIRATION_DAYS (temporary admin roles)
ZULU_RULES = ("any", "future", "year")


def _zone_or_none(tz_name):
    # Returns a tzinfo for an IANA time zone name such as "America/Chicago",
    # or None when no name is given or it is not a valid/known zone (the
    # caller then falls back to this computer's local zone). Used by the
    # browser version, whose SERVER may be in UTC (Google Cloud Shell) while
    # the person typing is not - the browser sends its own zone name.
    if not tz_name or not re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+\-]+)*", tz_name):
        return None
    try:
        from zoneinfo import ZoneInfo        # Python 3.9+; needs tz data
        return ZoneInfo(tz_name)
    except Exception:
        return None


def local_to_zulu(date_text, time_text="", now=None, rule="year", tz=None):
    # Converts a LOCAL date (+ optional LOCAL time) into a UTC timestamp
    # string 'YYYY-MM-DDTHH:MM:SSZ' for GAM. Returns (timestamp, "") on
    # success or ("", error_message) on bad input. 'rule' is one of
    # ZULU_RULES (default "year", the temporary-admin-role limit). 'now' can
    # be passed in (an aware UTC datetime) so tests are repeatable. 'tz' is
    # an optional IANA zone name (from the browser version); when missing or
    # unknown, this computer's own time zone is used.
    if not (date_text or "").strip():
        return "", "Missing required value: date"
    day = _parse_local_date(date_text)
    if day is None:
        return "", ("Date not recognized - use YYYY-MM-DD or MM-DD-YYYY "
                    "(e.g. 2027-01-05 or 01-05-2027)")
    hm = _parse_local_time(time_text or "")
    if hm is None:
        return "", ("Time not recognized - use 24-hour HH:MM (e.g. 17:30) "
                    "or 12-hour with AM/PM (e.g. 5:30 PM), or leave it blank "
                    "for midnight")
    # A naive datetime is LOCAL time; astimezone() attaches this computer's
    # time zone (including daylight saving time for that date), then the
    # value is converted to UTC.
    local = _dt.datetime(day.year, day.month, day.day, hm[0], hm[1])
    zone = _zone_or_none(tz)
    if zone is not None:
        # The named zone applies its own daylight-saving rules for that date.
        utc = local.replace(tzinfo=zone).astimezone(_dt.timezone.utc)
    else:
        utc = local.astimezone().astimezone(_dt.timezone.utc)
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if rule in ("future", "year") and utc <= now:
        return "", "The date/time must be in the future"
    if rule == "year" and utc > now + _dt.timedelta(days=MAX_EXPIRATION_DAYS):
        return "", ("The expiration must be within one year (Google's "
                    "limit for temporary admin roles)")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ"), ""


def supports_dry_run(task):
    # True when the "Preview (dry run)" button can run this task so that GAM
    # shows what WOULD change without changing anything. Two template tokens
    # mark it:
    #   {dryrun} - the command has GAM's own 'preview' option; the token marks
    #       WHERE it goes (group membership commands only accept it right
    #       before the member list). A normal build leaves it out; a dry-run
    #       build puts 'preview' there.
    #   {doit}   - GAM only acts when 'doit' is given. A normal build writes
    #       'doit'; a dry-run build leaves it out, so GAM just reports what it
    #       would do.
    # Only use {doit} where GAM's source shows the command does NOTHING
    # without doit. A plain 'doit' stays plain where that is not true -
    # Chromebook reboot / take_a_screenshot / set_volume run even WITHOUT
    # doit (GAM only requires it for remote_powerwash and wipe_users).
    # Every marked task was checked against GAM's source (7.48.14).
    if not task or task.get("workflow") or task.get("audit") \
            or task.get("external") or task.get("interactive"):
        return False
    tokens = (task.get("template", "") or "").split()
    return "{dryrun}" in tokens or "{doit}" in tokens


# =============================================================================
# SECTION: GAM's own syntax for a task (2.70)
# =============================================================================
# The "Syntax" button shows the part of GamCommands.txt - the syntax file
# that ships with GAM, so it always matches the INSTALLED version and works
# offline - that describes the open task's command (an idea from the GAM
# list, 09-13-2026: grep GamCommands.txt instead of guessing).
def parse_gam_commands(text):
    # GamCommands.txt -> list of (keywords, block). A block is one line that
    # starts with "gam " plus the indented lines that continue it. keywords
    # holds a SET of spellings per keyword ("update group|groups" -> {update},
    # {group, groups}); <...> and [...] parts are skipped.
    blocks, current = [], None
    for line in (text or "").splitlines():
        if line.startswith("gam "):
            if current:
                blocks.append(current)
            words = []
            for token in line.split()[1:]:
                if token[:1] in "<[(":
                    continue
                spellings = {w.lower() for w in token.split("|") if w and w[:1] not in "<[("}
                if spellings:
                    words.append(spellings)
            current = [words, [line]]
        elif current and line[:1] in (" ", "\t") and line.strip():
            current[1].append(line)
        elif current:
            blocks.append(current)
            current = None
    if current:
        blocks.append(current)
    return [(words, "\n".join(lines)) for words, lines in blocks]


def _task_keywords(task):
    # The fixed GAM words of a task's command, e.g. "user {email} move
    # drivefile {fileid}" -> ["user", "move", "drivefile"]. A 'gam csv
    # <file> gam <command>' template is judged by its inner command.
    template = (task or {}).get("template", "") or ""
    if " gam " in template:
        template = template.split(" gam ", 1)[1]
    template = re.sub(r"\[[^\]]*\]", " ", template)
    return [w.lower() for w in template.split()
            if not w.startswith("{") and not w.startswith("~")
            and re.fullmatch(r"[A-Za-z_][A-Za-z_\-]*", w)]


# Words too common to identify a command on their own.
_GENERIC_VERBS = {"print", "show", "info", "create", "add", "update", "delete",
                  "remove", "get", "set", "list", "user", "users", "all"}


def syntax_blocks(task, parsed, limit=6):
    # The GamCommands.txt blocks that best match a task's command. Leading
    # selector words in the template ("user", "all users", "ou") appear in
    # GamCommands.txt as <UserTypeEntity>, so matching may start 0-2 words
    # into the template. A block must match at least two words in order.
    keys = _task_keywords(task)
    if not keys or not parsed:
        return []
    scored = []
    for words, block in parsed:
        best = 0
        for skip in (0, 1, 2):
            want = keys[skip:skip + 4]
            got, pos = 0, 0
            for word in want:
                while pos < len(words) and word not in words[pos]:
                    pos += 1
                if pos >= len(words):
                    break
                got += 1
                pos += 1
            # The first wanted word must be one of the block's first two
            # keywords, so "print users" does not match "... print users"
            # buried deep inside an unrelated command.
            if got and not any(want[0] in w for w in words[:2]):
                got = 0
            # One matching word is enough only for a distinctive command
            # word (signout, vacation, whatis) - never for print/create/...
            if got == 1 and (want[0] in _GENERIC_VERBS
                             or not any(want[0] in w for w in words[:1])):
                got = 0
            best = max(best, got)
        if best >= 1:
            scored.append((best, block))
    if not scored:
        return []
    top = max(score for score, _b in scored)
    out = []
    for score, block in scored:
        if score == top and block not in out:     # the file repeats some
            out.append(block)
    return out[:limit]


# =============================================================================
# SECTION: What a typed command does (2.70)
# =============================================================================
# For "Run ANY GAM command" and for a task command someone edited by hand:
# GAMGUI cannot know those in advance, so it reads the words and sorts the
# command into one of four kinds (the idea behind Paul Ogier's GAM Script
# Checker, GAM list 09-14-2026). Gabe's rule: ALWAYS ask "Are you sure"
# before anything destructive. Whole words only ("in:trash" or a query
# 'trashed=true' is not the word "trash"); GAM ignores case and "_" in its
# keywords, so the words are compared that way. When unsure it errs toward
# asking - an extra click is cheaper than a deleted account.
DESTRUCTIVE_WORDS = {
    "delete", "del", "purge", "wipe", "clear", "empty", "erase", "trash",
    "deprovision", "remove", "revoke", "sync", "powerwash", "remotepowerwash",
    "wipeusers", "deletefield", "cancel",
    # 2.71: found by checking every task GAMGUI itself marks DESTRUCTIVE -
    # typed by hand, these did not ask before:
    "spam", "turnoff2sv", "obliterate", "dedup", "suspend", "disable",
    "accountwipe",
}
# Words that START a destructive value, e.g. Chromebook actions
# deprovision_retiring_device / deprovision_same_model_replace.
DESTRUCTIVE_PREFIXES = ("deprovision", "wipe")
# Combinations that are destructive only together (each word alone is
# ordinary): suspending accounts, ending a live meeting, a new primary
# domain, overwriting a Sheet range, swapping licenses, copying a mailbox
# (email monitor), replacing the service account key.
DESTRUCTIVE_COMBOS = [
    ("suspended", "on"), ("suspended", "true"),
    ("archived", "on"), ("archived", "true"), ("archive", "on"), ("archive", "true"),
    ("end", "meetconference"),
    ("update", "domain", "primary"),
    ("update", "sheetrange"),
    ("update", "license"),
    ("audit", "monitor", "create"),
    ("rotate", "sakey"),
    # Turning an EXISTING group into a security group cannot be undone
    # (creating a new one with it is fine).
    ("update", "makesecuritygroup"),
    # Ownership moves - hard to undo. 'info transfer' (a data transfer's
    # status) only reads, so the word alone is not enough.
    ("transfer", "drive"), ("transfer", "ownership"), ("calendars", "transfer"),
    # 2.74: claiming a FOLDER moves ownership of everything in it.
    ("claim", "ownership"),
    ("update", "calattendees"),
    # 2.75: moving a user's events takes them off their calendar for good.
    ("move", "events"),
    # 2.88: taking attendees off events (GAM sends no undo).
    ("update", "events", "removeattendee"),
    ("update", "events", "selectremoveattendees"),
]
READ_ONLY_WORDS = {
    "print", "show", "info", "report", "check", "version", "whatis", "help",
    "get", "list", "count", "verify",
}
# These run OTHER commands listed in a file, which GAMGUI cannot see. (A
# 'gam csv <file> gam <command>' or 'loop' shows its command, so it is
# judged by that command.)
FILE_RUNNER_WORDS = {"batch", "tbatch"}


def classify_command(argv):
    # Returns (kind, words): kind is "destructive", "unknown", "changes" or
    # "read-only"; words are the words that decided it.
    raw = [str(a).lower() for a in argv]
    words = [w.replace("_", "") for w in raw]
    found = [w for w in words if w in DESTRUCTIVE_WORDS]
    found += [w for w in raw if w.startswith(DESTRUCTIVE_PREFIXES)
              and w.replace("_", "") not in DESTRUCTIVE_WORDS]
    wordset = set(words)
    for combo in DESTRUCTIVE_COMBOS:
        if all(w in wordset for w in combo):
            found.append(" ".join(combo))
    if found:
        return "destructive", sorted(set(found))
    runners = [w for w in words if w in FILE_RUNNER_WORDS]
    if runners:
        return "unknown", sorted(set(runners))
    if any(w in READ_ONLY_WORDS for w in words):
        return "read-only", sorted(set(w for w in words if w in READ_ONLY_WORDS))
    return "changes", []


def _template_words(template):
    # The fixed words of a task's command (placeholders and optional
    # segments dropped) - what the task ALWAYS sends to GAM.
    template = re.sub(r"\[[^\]]*\]", " ", template or "")
    return [w for w in template.split() if not w.startswith("{")]


def _mark_destructive_by_words():
    # 2.71 - Gabe's rule is ALWAYS an "Are you sure" before anything
    # destructive. A task whose own command words are destructive (it
    # deletes, removes, cancels, clears...) gets destructive=True, so it
    # confirms when run from its form exactly as it would when typed into
    # Run ANY GAM command. Only ever ADDS the flag; names are unchanged, so
    # Favorites / Recent keep working.
    marked = []
    for tasks in TASKS.values():
        for task in tasks:
            if task.get("destructive") or task.get("workflow") \
                    or task.get("audit") or task.get("external"):
                continue
            if classify_command(_template_words(task.get("template")))[0] == "destructive":
                task["destructive"] = True
                marked.append(task["name"])
    return marked


# Runs once when the catalog loads.
AUTO_MARKED_DESTRUCTIVE = _mark_destructive_by_words()


def known_gam_bug(argv, gam_version=""):
    # A warning for a typed command that hits a KNOWN GAM bug in the GAM
    # that will run it, or "". gam_version: the installed GAM's version
    # text ("GAM 7.48.20 ..." / "7.48.21"); unknown = warn, to be safe.
    # GAM issue #1997 (opened 10-06-2026, FIXED in GAM 7.48.21): before
    # 7.48.21, 'purge events' WITHOUT doit still destroyed the matched
    # events (moved to a temporary calendar that was then deleted) while
    # GAM printed "Not Deleted: Use the doit argument".
    have = version_tuple(gam_version)
    if have and have >= (7, 48, 21):
        return ""
    words = [str(a).lower().replace("_", "") for a in argv]
    for i in range(len(words) - 1):
        if words[i] == "purge" and words[i + 1] in ("events", "event") \
                and "doit" not in words:
            return ("WARNING - known bug in GAM before 7.48.21 (#1997): "
                    "'purge events' without doit STILL permanently deletes "
                    "the matched events, even though GAM says 'Not Deleted'. "
                    "It is not a preview. Update GAM to 7.48.21 or newer.")
    return ""


def command_kind_text(kind, words):
    # One plain-English line for the output pane.
    return {
        "destructive": "DESTRUCTIVE - deletes, removes or wipes something "
                       "(" + ", ".join(words) + ")",
        "unknown": "runs commands from a file (" + ", ".join(words) + ") - "
                   "GAMGUI cannot see what they do",
        "changes": "changes something in Google Workspace",
        "read-only": "only reads (nothing is changed)",
    }[kind]


# =============================================================================
# SECTION: Plain-English help for common GAM errors (2.70)
# =============================================================================
# After a command FAILS, GAMGUI adds one short line saying what the error
# usually means and what to do (GAM GitHub issues #1790 / #1795 ask GAM for
# clearer permission errors). The patterns are GAM's own message texts
# (gamlib/glmsgs.py) and Google's error reasons. First match wins; the
# more specific patterns come first.
GAM_ERROR_HELP = [
    # 2.71: GAM prints BOTH of these when Google refuses a service (seen in
    # GAM issue #1991 for 'print cigroups' - the admin had run oauth create
    # several times without it helping), so the plain "sign in again" hint
    # below would send them in circles.
    (r"Not Authorized to access this resource[\s\S]*Reauthentication is needed|"
     r"Reauthentication is needed[\s\S]*Not Authorized to access this resource",
     "Google refused this service for GAM's sign-in. The usual causes: the "
     "sign-in does not include this service (run 'gam oauth update' and "
     "make sure it is ticked), or the account GAM signs in as lacks the "
     "admin role for it. Signing in again without changing either will not "
     "help."),
    # 2.72: GAM's service account reports a user that does not exist this
    # way (seen in the parse check) - it is NOT an expired sign-in.
    (r"invalid_grant: Invalid email or User ID",
     "That user does not exist (or is not in this domain) - check the "
     "spelling of the email address."),
    # 2.75: messages people posted in the GAM Public Chat. Each one would
    # otherwise get a generic (or wrong) hint below - "Does not exist" for
    # the damaged key file, "Not Authorized" for the calendar ones.
    (r"Service Account OAuth2 File:[\s\S]*(Does not exist|invalid format)",
     "GAM's service account key file (oauth2service.json in the GAM "
     "settings folder) is missing or damaged. GAM's fix is 'gam upload "
     "sakey'; if that is refused, see the GAM wiki page Authorization, "
     "'Authorize service account key uploads'."),
    (r"Writer access required to both calendars",
     "The user GAM acts as must be able to make changes on BOTH calendars. "
     "Share the destination calendar with that user (Grant calendar access, "
     "'Make changes to events') and run it again. Only events that user "
     "organized can be moved."),
    (r"owner access to this calendar",
     "Only the calendar's OWNER can change the calendar itself (its name, "
     "description, time zone). To change how it looks for a user, use 'Show "
     "/ hide or recolor a calendar in a user's list' - it can also rename it "
     "in their list."),
    (r"InactiveCourseOwner|course owner's account is not active",
     "The class owner's account is suspended or deleted. Restore the owner "
     "(unsuspend, in an OU where Classroom is on), wait a few minutes, then "
     "change the class owner."),
    (r"at least 2 unique memberships",
     "A group chat needs at least two OTHER people - do not list the user "
     "who is creating it."),
    (r"Service/App not enabled",
     "That address does not have this service - it may be a GROUP or an "
     "alias rather than a user (check it with 'What is this address?'), or "
     "the service is off or not licensed for that user's OU."),
    (r"The service is currently unavailable|backendError",
     "Google's servers turned this down for now - a short outage, or a "
     "limit on how many changes one account can make quickly (e.g. hundreds "
     "of calendar events in a row). Wait a while and run it again; spread "
     "big jobs out over time."),
    (r"Developer Preview is required",
     "This uses a Google API that this GAM treats as a Developer Preview. "
     "Update GAM first - newer GAM may not need it (Chat message search "
     "does not from GAM 7.48.17; see the GAM wiki page How-to-Update-GAM7). "
     "Otherwise set developer_preview_apis (e.g. chat) and "
     "developer_preview_api_key in gam.cfg - see the GAM wiki page gam.cfg."),
    (r"Reauthentication is needed|invalid_grant",
     "GAM's sign-in has expired or was revoked. Run OAuth Setup > Create / "
     "authorize a GAM admin account (gam oauth create) again."),
    (r"No Client Access allowed",
     "Client access is not set up for GAM's Google Cloud project. See the GAM "
     "wiki page How-to-Install-GAM7, 'Enable GAM7 client access'."),
    (r"There are no scopes authorized for the API",
     "GAM's sign-in does not include this Google service yet. Run 'gam oauth "
     "update' (OAuth Setup category), tick the service, and try again."),
    (r"Service Account Client ID|No Service Account Access allowed",
     "GAM's service account is not approved for this service. Run 'gam user "
     "<your admin email> update serviceaccount'; if it prints an Admin "
     "console link, a super admin must approve it there."),
    (r"API access Denied|accessNotConfigured|has not been used in project",
     "The Google API for this is not turned on in GAM's Cloud project. Run "
     "'gam update project' (or 'gam enable apis') and try again."),
    (r"Not Authorized to access this resource|Insufficient permissions|"
     r"403: forbidden|permissionDenied",
     "The account GAM signs in as (shown on the status line) does not have "
     "the admin rights for this. Give it the needed admin role, or pick a "
     "Section that signs in as an admin who has them."),
    (r"Service not applicable",
     "That user does not have this Google service - for example no license "
     "for it, or the service is turned off for their OU."),
    (r"Condition not met",
     "Google refused this change because of a setting on the item - for a "
     "group, for example, outside members are not allowed, or its members "
     "are set by a rule (a dynamic group)."),
    (r"quotaExceeded|rateLimitExceeded|userRateLimitExceeded",
     "Google is limiting how fast GAM can go. Wait a few minutes and run it "
     "again."),
    (r"Invalid argument|Invalid choice|Unknown argument|Missing argument",
     "GAM did not understand part of the command - a typo, a missing value, "
     "or an option this GAM version does not have. The Syntax button shows "
     "exactly what your GAM accepts."),
    (r"Does not exist",
     "Google could not find the user, group, file or other item named - "
     "check the spelling, and that it is in this domain (or Section)."),
    (r"\bDuplicate\b|already exists",
     "It already exists, so nothing new was made."),
]


def explain_gam_error(output):
    # One plain-English hint for a failed command's output, or "".
    for pattern, text in GAM_ERROR_HELP:
        if re.search(pattern, output or "", re.I):
            return text
    return ""


# =============================================================================
# SECTION: GAM version needs (2.70)
# =============================================================================
# Options GAMGUI can send that only exist in newer GAM releases (from GAM's
# GamUpdate.txt). An older GAM stops with "Invalid argument", so the desktop
# app compares the BUILT command with the installed GAM version and asks
# before running. Each rule: (word in the command, other words that must
# also be there, first GAM version that has it).
GAM_VERSION_NEEDS = [
    ("expires", ("create", "admin"), "7.48.06"),       # temporary admin roles
    ("extensionupdatecheck", (), "7.48.11"),
    ("allowlisteddomains", (), "7.48.00"),
    ("allowlisteddomain", (), "7.48.00"),
    ("chatavailability", (), "7.47.00"),
    ("showmembertypes", (), "7.46.09"),
    ("ownedsecondary", (), "7.46.08"),
    ("showownorganizationonly", (), "7.48.15"),
    # 'create|update policy ... ou|group' always failed before 7.48.02
    # (GAM issue #1974, Error 7016).
    ("policy", ("ou",), "7.48.02"),
    ("policy", ("group",), "7.48.02"),
    ("comments", ("get", "document"), "7.48.16"),
    ("suggestions", ("get", "document"), "7.48.16"),
    ("showenabled", (), "7.46.08"),
    ("configlicenseskus", (), "7.46.07"),
    ("isdisabled", (), "7.45.00"),
    ("disabledbefore", (), "7.45.00"),
    ("disabledafter", (), "7.45.00"),
    ("movefilepermissions", (), "7.45.00"),
    ("whocanaddexternalmembers", (), "7.40.03"),
    # 2.83: a course's subject and grade levels (GAM 7.47.07).
    ("subject", ("course",), "7.47.07"),
    ("levels", ("course",), "7.47.07"),
    # 2.88: Gmail label options (GamUpdate.txt 7.48.25 / 7.48.26).
    ("addlabelid", (), "7.48.25"),
    ("removelabelid", (), "7.48.25"),
    ("oneitemperrow", ("countsonly",), "7.48.25"),
    ("showlabelids", (), "7.48.26"),
]


def version_tuple(text):
    # "7.48.06" / "GAM 7.48.06" -> (7, 48, 6); anything unreadable -> ().
    found = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not found:
        return ()
    return tuple(int(part or 0) for part in found.groups())


def gam_version_needed(argv):
    # The newest GAM version a built command needs, and the word that needs
    # it: ("7.48.06", "expires") - or ("", "") when any GAM 7 will do.
    words = {str(a).lower() for a in argv}
    best, word = "", ""
    for keyword, also, version in GAM_VERSION_NEEDS:
        if keyword in words and all(w in words for w in also):
            if version_tuple(version) > version_tuple(best):
                best, word = version, keyword
    return best, word


def dry_run_note(exit_code):
    # One plain-English line shown after a dry run. GAM ends many dry runs
    # with a NON-zero exit code that is not an error here, and an admin
    # should not read "[exit code 60]" as a failure (codes from GAM 7.48's
    # source: 30 orphans found, 51 action not performed, 60 nothing matched).
    notes = {
        # GAM's preview lists the PLANNED changes; it does not ask Google
        # whether each one would be accepted (Ross Scroggs, GAM list,
        # 09-01-2026) - a "Condition not met" only shows on the real run.
        0: "Dry run finished - GAM listed the changes a real run would try "
           "(marked Preview). Nothing was changed. Google can still refuse "
           "a change on the real run (e.g. 'Condition not met').",
        30: "Dry run finished - the orphaned files above would be collected. "
            "Nothing was moved.",
        51: "Dry run finished - GAM counted what a real run would act on and "
            "stopped there, as it does without 'doit'. Nothing was changed.",
        60: "Dry run finished - nothing matched, so a real run would change "
            "nothing either.",
    }
    return "[" + notes.get(exit_code, (
        "Dry run stopped with exit code " + str(exit_code) + " - read GAM's "
        "message above (often a typo in a name or address). Nothing was "
        "changed.")) + "]"


def uses_local_time(task):
    # True when a task takes a LOCAL date/time that GAMGUI converts to UTC
    # ({zulu:} or {utcminute:}). The desktop app shows this computer's time
    # zone on such forms; the browser version sends the viewer's zone.
    template = (task or {}).get("template", "") or ""
    return "{zulu:" in template or "{utcminute:" in template


def date_to_utc_midnight(date_text):
    # For DATE-ONLY Google fields (a Google Tasks due date): Google stores
    # just the date and wants it written as midnight UTC, e.g.
    # 2027-01-15T00:00:00Z. There is deliberately NO time-zone shift here -
    # shifting would move the due date to the previous day for anyone west
    # of UTC. Returns (timestamp, "") or ("", error).
    day = _parse_local_date(date_text or "")
    if day is None:
        return "", ("Date not recognized - use YYYY-MM-DD or MM-DD-YYYY "
                    "(e.g. 2027-01-15 or 01-15-2027)")
    return day.strftime("%Y-%m-%dT00:00:00Z"), ""

# =============================================================================
# SECTION: Command building
# =============================================================================

# 2.90 (Gabe): characters a cmd.exe prompt treats specially. A preview / Copy
# value holding one is wrapped in double quotes so a password like
# P@ss&word! survives being pasted into cmd. (Run never needed it: GAMGUI
# hands GAM an argument list, no shell.) Commas, ; and = are left out - they
# only split arguments inside batch files, and every field list
# (id,name,mimetype) would otherwise show in quotes. "Save as script" has its
# own stricter quoting (_crt_quote / cmd_line_for_bat).
_DISPLAY_QUOTE = re.compile(r'[\s"&|<>^()%!]')


def quote_if_needed(value):
    # Wrap a value in double quotes when it contains spaces - or, since 2.90,
    # a character cmd.exe treats specially - so the command line stays
    # intact. Values already fully quoted are left alone.
    # Embedded quotes are escaped as \" (NOT stripped) so Gmail queries like
    #   from:bad@evil.com subject:"Gift Card"
    # keep their inner quotes when the whole query gets wrapped - the same
    # form GAM expects on the command line.
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        return value
    if _DISPLAY_QUOTE.search(value):
        return '"' + value.replace('"', '\\"') + '"'
    return value

# =============================================================================
# SECTION: pasted look-alike characters in address / ID boxes (2.93)
# =============================================================================
# GAM issue #1623: smart quotes pasted from Word / Outlook broke a GAM command.
# GAMGUI sent '\u201cjsmith@x\u201d' or 'j\u200bsmith@x' (an invisible
# zero-width space) to GAM as they were, and GAM answered "does not exist".
# Only IDENTIFIER boxes are cleaned (addresses, groups, OUs, IDs, scopes);
# subjects, messages, names and passwords keep every character - curly quotes
# are real content there. The preview shows the cleaned command.
IDENTIFIER_KEYS = {
    "email", "user", "users", "group", "groups", "member", "owner", "admin", "target",
    "student", "delegate", "alias", "old", "new", "ou", "path", "userval", "scopeval",
    "crosval", "whoval", "who", "list", "own", "domain", "domains", "courseid", "groupid",
    "cal", "matter", "driveid", "fileid", "serial", "resourceid", "deviceid",
    "deviceuserid", "customerid", "role", "profile", "alertid", "notify", "dest",
    "space", "note"}
NEVER_CLEAN_KEYS = {"password", "subject", "message", "text", "desc", "name", "title",
                    "query", "more", "from", "msgid", "label", "extra"}
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WRAP_QUOTES = "\"'\u201c\u201d\u201e\u2018\u2019\u201a\u00ab\u00bb"


def is_identifier_field(task, field):
    # True for a box that holds an address / ID (cleaned before building).
    key = field.get("key", "")
    if key in NEVER_CLEAN_KEYS or field.get("valuemap") or field.get("choices") \
            or field.get("filepicker") or field.get("rawappend"):
        return False
    return key in IDENTIFIER_KEYS or bool(task is not None and web_picker(task, field))


def _clean_item(item):
    lead = item[:len(item) - len(item.lstrip())]
    core = item.strip().replace("\u00a0", " ").strip()
    while len(core) >= 2 and core[0] in _WRAP_QUOTES and core[-1] in _WRAP_QUOTES:
        core = core[1:-1].strip()
    return lead + core


def clean_identifier(value):
    # Drops invisible zero-width characters anywhere; then, for each comma-
    # separated item, non-breaking spaces at its ends and quotes (straight or
    # curly) wrapped around the whole item. Separators and inner text stay.
    text = _ZERO_WIDTH.sub("", str(value or ""))
    return re.sub(r"[^,]+", lambda m: _clean_item(m.group(0)), text)


def clean_identifier_values(task, values):
    # The form's values with every identifier box cleaned (see above).
    out = dict(values)
    for field in (task or {}).get("fields", []):
        key = field["key"]
        if key in out and isinstance(out[key], str) and is_identifier_field(task, field):
            out[key] = clean_identifier(out[key])
    return out


def build_command(task, values, tz=None, dry_run=False):
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
    # tz: optional IANA time zone name for {zulu:} date/time fields (the
    # browser version passes the viewer's zone); None = this computer's zone.
    # dry_run: build the "Preview (dry run)" form of the command (see
    # supports_dry_run) - {dryrun} becomes 'preview' and {doit} is left out.
    # A task without either token returns an error instead, so a caller can
    # never get a "preview" that would really make changes.
    if dry_run and not supports_dry_run(task):
        return "", [], "This task has no dry run."
    # 2.84: "at least one of these boxes" (see _need_one) - e.g. changing
    # group settings with every setting left blank would change nothing.
    # 2.93: pasted curly quotes / invisible characters in address and ID
    # boxes are removed first (clean_identifier_values).
    values = clean_identifier_values(task, values)
    if task.get("needone"):
        keys, message = task["needone"]
        if not any(str(values.get(k) or "").strip() for k in keys):
            return "", [], message
    template = task["template"]
    # 2.83: a "name or ID" box whose GAM item is <Name>|id:<ID> (marked
    # "idform", see _mark_unique_id_boxes) sends an ID as 'id:<ID>'. GAM
    # reads a BARE ID as a NAME and answers "Does not exist" (checked on
    # 7.48.20 for Vault matters, saved queries and admin roles).
    if any(f.get("idform") or f.get("addprefix") for f in task.get("fields", [])):
        values = dict(values)
        for f in task["fields"]:
            if f.get("idform") and values.get(f["key"]):
                values[f["key"]] = unique_ids(values[f["key"]], f["idform"])
            # A bare ID where GAM needs the full resource name (e.g. a Meet
            # conference: conferenceRecords/<ID>) gets that prefix.
            value = (values.get(f["key"]) or "").strip()
            if f.get("addprefix") and re.fullmatch(r"[A-Za-z0-9_-]+", value):
                values[f["key"]] = f["addprefix"] + value

    def seg_sub(match):
        segment = match.group(0)[1:-1]           # strip the [ ]
        # Collect the FIELD keys inside the segment. A plain {key} or
        # {key|fallback} names one field; a special token such as
        # {zulu:DATE:TIME:rule} or {utcdate:KEY} names its fields AFTER the
        # prefix (a rule word like 'future' is not a field and is simply
        # always blank, which does not affect the any-filled test).
        keys = []
        for inner in re.findall(r"{([^}]*)}", segment):
            if ":" in inner:
                keys.extend(inner.split(":")[1:])
            else:
                keys.append(re.match(r"\w*", inner).group(0))
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
        # {key!isodate} normalizes a date typed as MM-DD-YYYY, M/D/YYYY, or
        # YYYY-MM-DD to YYYY-MM-DD - for dates that sit INSIDE a larger GAM
        # argument (e.g. a query like lastLoginTime<{date!isodate}T00:00:00Z).
        key, conv, fallback = match.group(1), match.group(2), match.group(3) or ""
        value = values.get(key, "").strip()
        if not value:
            if fallback:
                value = fallback
            else:
                problem[0] = "Missing required value: " + key
        elif conv == "isodate":
            day = _parse_local_date(value)
            if day is None:
                problem[0] = ("Date not recognized - use YYYY-MM-DD or "
                              "MM-DD-YYYY (e.g. 2025-01-01 or 01-01-2025)")
            else:
                value = day.isoformat()
        return value

    for token in rendered.split():
        # Special token {dryrun}: where GAM's 'preview' option goes. A normal
        # build leaves it out; a dry-run build puts 'preview' here.
        if token == "{dryrun}":
            if dry_run:
                argv.append("preview")
                display_parts.append("preview")
            continue
        # Special token {doit}: GAM's 'doit' (act for real). A normal build
        # writes 'doit'; a dry-run build leaves it out.
        if token == "{doit}":
            if not dry_run:
                argv.append("doit")
                display_parts.append("doit")
            continue
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
        # 2.83: special token {mailquery:FROM:SUBJECT:MSGID:MORE} - ONE
        # argument: the Gmail search built from the plain boxes (mail_query).
        # Refused when every box is blank: an empty search would match EVERY
        # message in every mailbox.
        # 2.84: a 5th part 'intrash' adds in:trash (Restore from Trash).
        mailq = re.fullmatch(r"\{mailquery:(\w+):(\w+):(\w+):(\w+)(?::(intrash))?\}",
                             token)
        if mailq:
            query = mail_query(*[values.get(k, "") for k in mailq.groups()[:4]])
            if not query:
                return "", [], ("Fill in the From address, Subject words, "
                                "Message-ID or More search words - a blank "
                                "search would match EVERY message.")
            if mailq.group(5) and "in:trash" not in query.lower():
                query = "in:trash " + query
            argv.append(query)
            display_parts.append(quote_if_needed(query))
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
        # Special token {zulu:DATEKEY:TIMEKEY}: turns a LOCAL date and an
        # optional LOCAL time from two form fields into one UTC ("Zulu")
        # timestamp such as 2027-01-05T15:00:00Z (see local_to_zulu). Used by
        # the temporary admin role tasks: Google's API wants the expiration
        # in UTC, but people think in their own time zone. A blank time means
        # midnight at the START of that date, local time.
        # An optional 4th part names the rule (see ZULU_RULES): any / future
        # / year. Without it the rule is "any". If the TIME field is marked
        # required in the task, a blank time is an error (focus time needs
        # real start and end times) instead of silently meaning midnight.
        zulu = re.fullmatch(r"\{zulu:(\w+):(\w+)(?::(\w+))?\}", token)
        if zulu:
            date_key, time_key = zulu.group(1), zulu.group(2)
            rule = zulu.group(3) or "any"
            time_field = next((f for f in task["fields"]
                               if f["key"] == time_key), None)
            if (time_field is not None and time_field.get("required")
                    and not values.get(time_key, "").strip()):
                return "", [], "Missing required value: " + time_key
            stamp, err = local_to_zulu(values.get(date_key, ""),
                                       values.get(time_key, ""), rule=rule,
                                       tz=tz)
            if err:
                return "", [], err
            argv.append(stamp)
            display_parts.append(stamp)
            continue
        # Special token {utcdate:KEY}: a DATE-ONLY value written as midnight
        # UTC with no time-zone shift (Google Tasks due dates) - see
        # date_to_utc_midnight. Accepts the same date formats as {zulu:}.
        udate = re.fullmatch(r"\{utcdate:(\w+)\}", token)
        if udate:
            stamp, err = date_to_utc_midnight(values.get(udate.group(1), ""))
            if err:
                return "", [], err
            argv.append(stamp)
            display_parts.append(stamp)
            continue
        # Special token {utcminute:DATEKEY:TIMEKEY:RULE}: like {zulu:} but in
        # the 'YYYY-MM-DD HH:MM' (UTC) shape that GAM's email audit monitor
        # expects - GAM passes that text straight to Google's Email Audit API,
        # whose documentation uses UTC for these dates. ONE argument even
        # though it contains a space (argv is passed without a shell).
        uminute = re.fullmatch(r"\{utcminute:(\w+):(\w+)(?::(\w+))?\}", token)
        if uminute:
            stamp, err = local_to_zulu(values.get(uminute.group(1), ""),
                                       values.get(uminute.group(2), ""),
                                       rule=uminute.group(3) or "any", tz=tz)
            if err:
                return "", [], err
            stamp = stamp[:10] + " " + stamp[11:16]      # 2027-01-31 23:59
            argv.append(stamp)
            display_parts.append(quote_if_needed(stamp))
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
        filled = re.sub(r"{(\w+)(?:!(\w+))?(?:\|([^}]*))?}", fill, token)
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

    # 2.83: fixed words that must come AFTER the typed part (task "tail").
    # GAM reads 'delete|purge events' as: calendar, the event selection,
    # THEN options such as doit - a selector after doit is an unknown
    # argument. A task with a tail never offers a dry run (see
    # supports_dry_run: no {dryrun} / {doit} token).
    for tok in task.get("tail", ()):
        argv.append(tok)
        display_parts.append(quote_if_needed(tok))

    # A dry run must never contain 'doit' - it would make GAM really do it.
    # The template's {doit} was left out above, so one here came from a
    # form field, most likely an Extra-arguments box. GAM ignores case and
    # underscores in its keywords ('DoIt', 'do_it'), so compare that way.
    if dry_run and any(a.lower().replace("_", "") == "doit" for a in argv):
        return "", [], ("A dry run cannot include 'doit' - remove it from "
                        "the Extra arguments box.")

    # A CSV redirect is a leading gam directive. GAM reads those in a FIXED
    # order - select, config, redirect - so it goes at the front, but AFTER
    # a template's 'config ...' block (2.94: before, 'redirect csv x.csv
    # config csv_output_row_filter ...' was refused - 'Invalid choice
    # (config)' - for every row-filter task saving to a CSV file).
    at = redirect_position(argv)
    argv = argv[:at] + redirect_prefix + argv[at:]
    display_parts = display_parts[:at] + redirect_display + display_parts[at:]
    return " ".join(display_parts), argv, ""


def redirect_position(argv):
    # Where a leading 'redirect' belongs in argv: 0, or right after a leading
    # 'config <variable> <value> ... [save] [verify]' block, read the way GAM
    # reads it (7.48.31 SetGlobalVariables: the block ends at the first word
    # that is not a gam.cfg variable, 'save' or 'verify').
    if not argv or argv[0].lower() != "config":
        return 0
    import gam_config                    # lazy: only needed for config blocks
    names = {v["name"] for v in gam_config.CFG_VARS}
    i = 1
    while i < len(argv):
        word = argv[i].lower()
        if word in ("save", "verify"):
            i += 1
        elif word in names:
            i += 2                       # the variable and its one value
            if i - 1 < len(argv) and argv[i - 1] == "=":
                i += 1                   # 'config name = value' form
        else:
            break
    return min(i, len(argv))


def mail_query(sender="", subject="", msgid="", more=""):
    # The Gmail search for the Email Cleanup boxes: from:<sender>
    # subject:(<words>) (see incident_query) rfc822msgid:<id> <more>. A
    # Message-ID may be pasted with its < > - they are removed. "" when
    # every box is blank (callers must then refuse to run: an empty search
    # matches EVERY message).
    parts = [incident_query(sender or "", subject or "")]
    msgid = (msgid or "").strip().strip("<>").strip()
    if msgid:
        parts.append("rfc822msgid:" + msgid)
    parts.append((more or "").strip())
    return " ".join(p for p in parts if p)


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

# 2.92: GAM's own license table (gamlib/glskus.py _SKUS; refreshed to GAM
# 7.48.31 in 2.93):
# SKU id -> (product id, display name, aliases). GAM accepts a license as its
# SKU id, an alias or its display name (GAM's getProductAndSKU), so GAMGUI
# does too - before 2.92 it refused 43 products it did not list itself
# (e.g. Google AI Pro for Education, 'geminiedu'). GAM-Change-Watch reports
# when GAM's table changes; refresh this copy then.
GAM_SKUS = {
    '1010010001': ('101001', 'Cloud Identity Free', ('identity', 'cloudidentity', 'cloudidentityfree')),
    '1010050001': ('101005', 'Cloud Identity Premium', ('identitypremium', 'cloudidentitypremium')),
    '1010070001': ('Google-Apps', 'Google Workspace for Education Fundamentals', ('gwef', 'workspaceeducationfundamentals')),
    '1010070004': ('Google-Apps', 'Google Workspace for Education Gmail Only', ('gwegmo', 'workspaceeducationgmailonly')),
    '1010310002': ('101031', 'Google Workspace for Education Plus - Legacy', ('gsefe', 'e4e', 'gsuiteenterpriseeducation')),
    '1010310003': ('101031', 'Google Workspace for Education Plus - Legacy (Student)', ('gsefes', 'e4es', 'gsuiteenterpriseeducationstudent')),
    '1010310005': ('101031', 'Google Workspace for Education Standard', ('gwes', 'workspaceeducationstandard')),
    '1010310006': ('101031', 'Google Workspace for Education Standard (Staff)', ('gwesstaff', 'workspaceeducationstandardstaff')),
    '1010310007': ('101031', 'Google Workspace for Education Standard (Extra Student)', ('gwesstudent', 'workspaceeducationstandardstudent')),
    '1010310008': ('101031', 'Google Workspace for Education Plus', ('gwep', 'workspaceeducationplus')),
    '1010310009': ('101031', 'Google Workspace for Education Plus (Staff)', ('gwepstaff', 'workspaceeducationplusstaff')),
    '1010310010': ('101031', 'Google Workspace for Education Plus (Extra Student)', ('gwepstudent', 'workspaceeducationplusstudent')),
    '1010330002': ('101033', 'Google Voice Premier', ('gvpremier', 'voicepremier', 'googlevoicepremier')),
    '1010330003': ('101033', 'Google Voice Starter', ('gvstarter', 'voicestarter', 'googlevoicestarter')),
    '1010330004': ('101033', 'Google Voice Standard', ('gvstandard', 'voicestandard', 'googlevoicestandard')),
    '1010350001': ('101035', 'Cloud Search', ('cloudsearch',)),
    '1010360001': ('101036', 'Google Meet Global Dialing', ('meetdialing', 'googlemeetglobaldialing')),
    '1010370001': ('101037', 'Google Workspace for Education: Teaching and Learning Upgrade', ('gwetlu', 'workspaceeducationupgrade')),
    '1010380001': ('101038', 'AppSheet Core', ('appsheetcore',)),
    '1010380002': ('101038', 'AppSheet Enterprise Standard', ('appsheetstandard', 'appsheetenterprisestandard')),
    '1010380003': ('101038', 'AppSheet Enterprise Plus', ('appsheetplus', 'appsheetenterpriseplus')),
    '1010390001': ('101039', 'Assured Controls', ('assuredcontrols',)),
    '1010390002': ('101039', 'Assured Controls Plus', ('assuredcontrolsplus',)),
    '1010400001': ('101040', 'Chrome Enterprise Premium', ('beyondcorp', 'beyondcorpenterprise', 'bce', 'cep', 'chromeenterprisepremium')),
    '1010430001': ('101043', 'Google Workspace Additional Storage 10TB', ('gwas10tb', 'plusstorage10tb', 'gwas', 'plusstorage')),
    '1010430002': ('101043', 'Google Workspace Additional Storage 100GB', ('gwas100gb', 'plusstorage100gb')),
    '1010430003': ('101043', 'Google Workspace Additional Storage 1TB', ('gwas1tb', 'plusstorage1tb')),
    '1010470001': ('101047', 'Gemini Enterprise - Legacy', ('geminient', 'duetai')),
    '1010470002': ('101047', 'Google Workspace Labs', ('gwlabs', 'workspacelabs')),
    '1010470003': ('101047', 'Gemini Business', ('geminibiz',)),
    '1010470004': ('101047', 'Google AI Pro for Education', ('gaiproedu', 'geminiedu')),
    '1010470005': ('101047', 'Gemini Education Premium', ('geminiedupremium',)),
    '1010470006': ('101047', 'AI Security', ('aisecurity',)),
    '1010470007': ('101047', 'AI Meetings and Messaging', ('aimeetingsandmessaging',)),
    '1010470008': ('101047', 'Google AI Ultra for Business', ('geminiultra',)),
    '1010470009': ('101047', 'AI Expanded Access', ('aiexpandedaccess',)),
    '1010490001': ('101049', 'Endpoint Education Upgrade', ('eeu',)),
    '1010500001': ('101050', 'Colab Pro', ('colabpro',)),
    '1010500002': ('101050', 'Colab Pro+', ('colabpro+', 'colabproplus')),
    'Google-Apps': ('Google-Apps', 'G Suite Legacy', ('standard', 'free')),
    'Google-Apps-For-Business': ('Google-Apps', 'G Suite Basic', ('gafb', 'gafw', 'basic', 'gsuitebasic')),
    'Google-Apps-For-Education': ('Google-Apps', 'Google Workspace for Education - Fundamentals', ('gafe', 'gsuiteeducation', 'gsuiteedu')),
    'Google-Apps-For-Government': ('Google-Apps', 'Google Workspace Government', ('gafg', 'gsuitegovernment', 'gsuitegov')),
    'Google-Apps-For-Postini': ('Google-Apps', 'Google Apps Message Security', ('gams', 'postini', 'gsuitegams', 'gsuitepostini', 'gsuitemessagesecurity')),
    'Google-Apps-Lite': ('Google-Apps', 'G Suite Lite', ('gal', 'gsl', 'lite', 'gsuitelite')),
    'Google-Apps-Unlimited': ('Google-Apps', 'G Suite Business', ('gau', 'gsb', 'unlimited', 'gsuitebusiness')),
    '1010020020': ('Google-Apps', 'Google Workspace Enterprise Plus (formerly G Suite Enterprise)', ('gae', 'gse', 'enterprise', 'gsuiteenterprise', 'wsentplus', 'workspaceenterpriseplus')),
    '1010020025': ('Google-Apps', 'Google Workspace Business Plus', ('wsbizplus', 'workspacebusinessplus')),
    '1010020026': ('Google-Apps', 'Google Workspace Enterprise Standard', ('wsentstan', 'workspaceenterprisestandard')),
    '1010020027': ('Google-Apps', 'Google Workspace Business Starter', ('wsbizstart', 'wsbizstarter', 'workspacebusinessstarter')),
    '1010020028': ('Google-Apps', 'Google Workspace Business Standard', ('wsbizstan', 'workspacebusinessstandard')),
    '1010020029': ('Google-Apps', 'Workspace Enterprise Starter', ('wes', 'wsentstarter', 'workspaceenterprisestarter')),
    '1010020030': ('Google-Apps', 'Google Workspace Frontline Starter', ('wsflw', 'workspacefrontline', 'workspacefrontlineworker')),
    '1010020031': ('Google-Apps', 'Google Workspace Frontline Standard', ('wsflwstan', 'workspacefrontlinestan', 'workspacefrontlineworkerstan')),
    '1010020034': ('Google-Apps', 'Google Workspace Frontline Plus', ('wsflwplus', 'workspacefrontlineplus', 'workspacefrontlineworkerplus')),
    '1010340001': ('101034', 'Google Workspace Enterprise Plus - Archived User', ('gseau', 'enterprisearchived', 'gsuiteenterprisearchived')),
    '1010340002': ('101034', 'Google Workspace Business - Archived User', ('gsbau', 'businessarchived', 'gsuitebusinessarchived')),
    '1010340003': ('101034', 'Google Workspace Business Plus - Archived User', ('wsbizplusarchived', 'workspacebusinessplusarchived')),
    '1010340004': ('101034', 'Google Workspace Enterprise Standard - Archived User', ('wsentstanarchived', 'workspaceenterprisestandardarchived')),
    '1010340005': ('101034', 'Google Workspace Business Starter - Archived User', ('wsbizstarterarchived', 'workspacebusinessstarterarchived')),
    '1010340006': ('101034', 'Google Workspace Business Standard - Archived User', ('wsbizstanarchived', 'workspacebusinessstanarchived')),
    '1010340007': ('101034', 'Google Workspace for Education Fundamentals - Archived User', ('gwefau', 'gwefarchived', 'workspaceeducationfundamentalsarchived')),
    '1010060001': ('101006', 'Google Workspace Essentials (formerly G Suite Essentials)', ('gsuiteessentials', 'essentials', 'd4e', 'driveenterprise', 'drive4enterprise', 'wsess', 'workspaceesentials')),
    '1010060003': ('Google-Apps', 'Google Workspace Enterprise Essentials', ('wsentess', 'workspaceenterpriseessentials')),
    '1010060005': ('Google-Apps', 'Google Workspace Enterprise Essentials Plus', ('wsessplus', 'workspaceessentialsplus')),
    'Google-Drive-storage-20GB': ('Google-Drive-storage', 'Google Drive Storage 20GB', ('drive20gb', '20gb', 'googledrivestorage20gb')),
    'Google-Drive-storage-50GB': ('Google-Drive-storage', 'Google Drive Storage 50GB', ('drive50gb', '50gb', 'googledrivestorage50gb')),
    'Google-Drive-storage-200GB': ('Google-Drive-storage', 'Google Drive Storage 200GB', ('drive200gb', '200gb', 'googledrivestorage200gb')),
    'Google-Drive-storage-400GB': ('Google-Drive-storage', 'Google Drive Storage 400GB', ('drive400gb', '400gb', 'googledrivestorage400gb')),
    'Google-Drive-storage-1TB': ('Google-Drive-storage', 'Google Drive Storage 1TB', ('drive1tb', '1tb', 'googledrivestorage1tb')),
    'Google-Drive-storage-2TB': ('Google-Drive-storage', 'Google Drive Storage 2TB', ('drive2tb', '2tb', 'googledrivestorage2tb')),
    'Google-Drive-storage-4TB': ('Google-Drive-storage', 'Google Drive Storage 4TB', ('drive4tb', '4tb', 'googledrivestorage4tb')),
    'Google-Drive-storage-8TB': ('Google-Drive-storage', 'Google Drive Storage 8TB', ('drive8tb', '8tb', 'googledrivestorage8tb')),
    'Google-Drive-storage-16TB': ('Google-Drive-storage', 'Google Drive Storage 16TB', ('drive16tb', '16tb', 'googledrivestorage16tb')),
    'Google-Vault': ('Google-Vault', 'Google Vault', ('vault', 'googlevault')),
    'Google-Vault-Former-Employee': ('Google-Vault', 'Google Vault - Former Employee', ('vfe', 'googlevaultformeremployee')),
    'Google-Chrome-Device-Management': ('Google-Chrome-Device-Management', 'Google Chrome Device Management', ('chrome', 'cdm', 'googlechromedevicemanagement')),
}


# On Google's official product list (developers.google.com/workspace/admin/
# licensing/v1/how-tos/products, checked 10-19-2026) but missing from GAM's
# table until GAM 7.48.31 (GAM issue #2011, reported from GAMGUI): sent as
# GAM's no-validate form 'nv:<product>:<sku>', which every GAM version
# accepts - a plain id is 'Invalid choice' on GAM older than 7.48.31.
GOOGLE_ONLY_SKUS = {"1010430002": "101043",     # Additional Storage 100 GB
                    "1010430003": "101043"}     # Additional Storage 1TB


def _sku_norm(text):
    # GAM's comparison: lower case, no '-', spaces or quotes.
    return re.sub(r"[-\s\"']", "", (text or "").lower())


_GAM_SKU_LOOKUP = {}
for _gsku, (_gprod, _gname, _galiases) in GAM_SKUS.items():
    _GAM_SKU_LOOKUP[_sku_norm(_gsku)] = _gsku
    _GAM_SKU_LOOKUP[_sku_norm(_gname)] = _gsku
    for _galias in _galiases:
        _GAM_SKU_LOOKUP.setdefault(_sku_norm(_galias), _gsku)

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
    # 2.92: GAMGUI's friendly names first, then GAM's own table (SKU id,
    # display name or alias - matched the way GAM matches them); a Google
    # product GAM's table lacks goes as 'nv:<product>:<sku>'.
    v = (value or "").strip()
    if not v:
        return None
    sku = _LICENSE_LOOKUP.get(v.lower()) or _GAM_SKU_LOOKUP.get(_sku_norm(v))
    if not sku and re.fullmatch(r"\d{6,}", v):            # numeric SKU id
        sku = v
    if not sku and "-" in v and re.fullmatch(r"[A-Za-z0-9-]+", v):   # GAM alias
        return v
    if sku in GOOGLE_ONLY_SKUS:
        return "nv:%s:%s" % (GOOGLE_ONLY_SKUS[sku], sku)
    return sku


# =============================================================================
# SECTION: "Undo:" notes for destructive tasks (2.82)
# =============================================================================
# Admins of every skill level should see BEFORE they run a destructive task
# whether it can be put back, and how. Each note is factual: it names the
# GAMGUI task that reverses it, or says GAM has no undo (GAM's only undo
# commands are undelete user / vault matter / alert, untrash Drive files and
# untrash Gmail messages - GamCommands.txt). Tasks where Google's own
# behaviour is not certain are left without a note rather than guessed.
# Applied to the task descriptions when the catalog loads.
_NO_UNDO = "Undo: none in GAM"
UNDO_NOTES = {
    # --- Users / Security ---
    "Deprovision user (offboarding) (DESTRUCTIVE)":
        "Undo: none for the removed app passwords, backup codes and app "
        "access - the user sets them up again.",
    "Deprovision (offboarding)":
        "Undo: none for the removed app passwords, backup codes and app "
        "access - the user sets them up again.",
    "Delete a user's profile photo (DESTRUCTIVE)":
        "Undo: upload it again (Set a user's profile photo from a file) - "
        "download it first if you may need it.",
    "Cancel an invitation": "Undo: invite the address again.",
    "Delete all app passwords (DESTRUCTIVE)":
        _NO_UNDO + " - the user creates new app passwords.",
    "Revoke one app's access":
        "Undo: the user signs in to the app again and gives it access.",
    "Delete an S/MIME certificate (DESTRUCTIVE)":
        "Undo: upload it again (Upload an S/MIME certificate) - keep the file.",
    "Delete a CSE identity (DESTRUCTIVE)":
        "Undo: create it again (Create a CSE identity from a key pair).",
    "Stop sending alerts to Pub/Sub": "Undo: Send alerts to a Pub/Sub topic.",
    "Delete an email monitor (DESTRUCTIVE)":
        "Undo: create it again (Create an email monitor).",
    "Delete a user's backup codes (DESTRUCTIVE)":
        "Undo: generate new ones (Generate backup codes) - the old codes "
        "never work again.",
    # --- Groups ---
    "Remove member": "Undo: add them back (Add member).",
    "Delete group (DESTRUCTIVE)":
        _NO_UNDO + " - export its members first (List members) if you may "
        "need to recreate it.",
    "Remove ALL members (DESTRUCTIVE)":
        _NO_UNDO + " - export the members first (List members) if you may "
        "need to put them back.",
    "Sync group from OU (DESTRUCTIVE)":
        _NO_UNDO + " - export the members first (List members) if you may "
        "need to put them back.",
    "Sync group members from a CSV (DESTRUCTIVE)":
        _NO_UNDO + " - export the members first (List members) if you may "
        "need to put them back.",
    "BULK: remove members from a group (from a group / OU / CSV) (DESTRUCTIVE)":
        "Undo: add them back (BULK: add members to a group) with the same "
        "source.",
    "BULK: remove ONE user from MANY groups (from a CSV of groups) (DESTRUCTIVE)":
        "Undo: BULK: add ONE user to MANY groups with the same CSV.",
    "Sync a user's groups - exact list (DESTRUCTIVE)":
        _NO_UNDO + " - list their groups first (What groups is a user in?) "
        "if you may need to put them back.",
    # --- Aliases, OUs, domains ---
    "Bulk delete aliases from a CSV (DESTRUCTIVE)":
        "Undo: create them again (BULK: create aliases from a CSV) - keep "
        "the CSV.",
    "Delete OU (DESTRUCTIVE)":
        "Undo: create it again (Create OU) - settings and policies that were "
        "set on it are not restored.",
    "Delete domain (DESTRUCTIVE)": "Undo: add and verify it again.",
    "Delete domain alias (DESTRUCTIVE)": "Undo: add it again (Add domain alias).",
    # --- Chromebooks, Chrome, mobile ---
    "Powerwash device (DESTRUCTIVE)": "Undo: none - the local data is gone.",
    "BULK: powerwash devices (DESTRUCTIVE)": "Undo: none - the local data is gone.",
    "Delete a Chrome network (DESTRUCTIVE)": "Undo: create it again from its JSON.",
    "Account-wipe mobile device (DESTRUCTIVE)": "Undo: none - the data is gone from the device.",
    "Wipe a device user (DESTRUCTIVE)": "Undo: none - the data is gone from the device.",
    "Wipe a device (DESTRUCTIVE)": "Undo: none - the data is gone from the device.",
    # --- Gmail ---
    "Remove delegate": "Undo: add them back (Add delegate).",
    "BULK: remove a delegate from many mailboxes (DESTRUCTIVE)":
        "Undo: BULK: add a delegate to many mailboxes (same scope).",
    "Delete a forwarding address (DESTRUCTIVE)":
        "Undo: add it again (Enable forwarding) - an outside address may "
        "have to confirm again.",
    "Delete send-as address": "Undo: add it again (Add send-as address).",
    "Delete filter":
        "Undo: create it again (Create filter) - note its settings first "
        "(Gmail filter details).",
    "Delete label":
        "Messages that had the label are NOT deleted; they only lose the "
        "label. Undo: create the label again and add it back to the messages.",
    # --- Calendars ---
    "Remove calendar access (DESTRUCTIVE)": "Undo: grant it again (Grant calendar access).",
    "Delete event(s) (DESTRUCTIVE)": _NO_UNDO + ".",
    "Move event(s) to another calendar (advanced)": "Undo: move them back the same way.",
    "Move a user's events to another calendar (e.g. a leaving staff member)":
        "Undo: move them back the same way (as the destination calendar's owner).",
    "Wipe ALL events from a calendar (DESTRUCTIVE)": _NO_UNDO + ".",
    "Remove a calendar from a user's list":
        "Undo: add it back (Add a calendar to a user's list).",
    "BULK: unsubscribe many users from a calendar (DESTRUCTIVE)":
        "Undo: BULK: subscribe many users to a calendar (same scope).",
    "Swap an attendee on events (replace one person with another) (DESTRUCTIVE)":
        "Undo: swap them back the same way.",
    "Remove out-of-office / working location / focus time (DESTRUCTIVE)":
        "Undo: create them again.",
    # --- Drive / Shared Drives ---
    "Unshare a file/folder (DESTRUCTIVE)": "Undo: share it again (Share a file/folder).",
    "Transfer ownership of a file/folder": "Undo: transfer ownership back the same way.",
    "Claim ownership of a file/folder":
        "Undo: transfer ownership back (Transfer ownership of a file/folder).",
    "Transfer a user's ENTIRE Drive to another user (offboarding)":
        "Undo: transfer the files back (Transfer ownership of a file/folder).",
    "Transfer ownership of files matching a query (to another user)":
        "Undo: transfer them back the same way.",
    "Bulk UNSHARE files matching a query (remove a person) (DESTRUCTIVE)":
        "Undo: Bulk SHARE files matching a query, with the same query.",
    "Remove a user or group from a Drive label (DESTRUCTIVE)":
        "Undo: Let a user or group use a Drive label.",
    "Remove member from Shared Drive (DESTRUCTIVE)":
        "Undo: add them back (Add member to Shared Drive).",
    "Delete Shared Drive (DESTRUCTIVE)": _NO_UNDO + ".",
    "BULK: remove a member from Shared Drives from a CSV (DESTRUCTIVE)":
        "Undo: BULK: add a member to Shared Drives from a CSV (same CSV).",
    "Sync Shared Drive members - exact match (DESTRUCTIVE)":
        _NO_UNDO + " - list the members first (List members of a Shared "
        "Drive) if you may need to put them back.",
    # --- Classroom ---
    "Remove teacher from course": "Undo: add them back (Add teacher to course).",
    "Remove student from course": "Undo: add them back (Add student to course).",
    "Cancel a user's course invitation": "Undo: invite them again.",
    "Sync students from a group (DESTRUCTIVE)":
        _NO_UNDO + " - list the students first (List course participants).",
    "Sync students from an OU (DESTRUCTIVE)":
        _NO_UNDO + " - list the students first (List course participants).",
    "Sync teachers from a group (DESTRUCTIVE)":
        _NO_UNDO + " - list the teachers first (List course participants).",
    "Sync teachers from an OU (DESTRUCTIVE)":
        _NO_UNDO + " - list the teachers first (List course participants).",
    "Remove course alias": "Undo: add it again (Add course alias).",
    "Delete course (DESTRUCTIVE)":
        _NO_UNDO + " - archive it instead if it only needs to be hidden.",
    "Delete an announcement (DESTRUCTIVE)": _NO_UNDO + ".",
    "Remove a member from a student group":
        "Undo: add them back (Add members to a student group).",
    "Sync a student group's members (exact match) (DESTRUCTIVE)":
        _NO_UNDO + " - list the members first (List student-group members "
        "in a course).",
    "Delete a student group (DESTRUCTIVE)": _NO_UNDO + ".",
    "Delete all student groups in a course (DESTRUCTIVE)": _NO_UNDO + ".",
    "Remove a guardian link (DESTRUCTIVE)":
        "Undo: invite the guardian again (they must accept again).",
    "Cancel a pending guardian invitation": "Undo: invite them again.",
    "Sync a student's guardians - exact match (DESTRUCTIVE)":
        "Undo: invite the removed guardians again (they must accept again).",
    "Remove a student's guardians (DESTRUCTIVE)":
        "Undo: invite the guardians again (they must accept again).",
    # --- Chat, Tasks, Keep, Sheets ---
    "Delete a Chat space (admin) (DESTRUCTIVE)": _NO_UNDO + ".",
    "Remove a member from a Chat space (admin) (DESTRUCTIVE)":
        "Undo: add them back (Add a member to a Chat space).",
    "Delete a Chat message (DESTRUCTIVE)": _NO_UNDO + ".",
    "Delete a custom Chat emoji (DESTRUCTIVE)": _NO_UNDO + ".",
    "Delete a task (DESTRUCTIVE)": _NO_UNDO + ".",
    "Delete a task list (DESTRUCTIVE)": _NO_UNDO + ".",
    "Clear completed tasks from a list (DESTRUCTIVE)": _NO_UNDO + ".",
    "Delete a Keep note (DESTRUCTIVE)": _NO_UNDO + ".",
    "Stop sharing a Keep note (DESTRUCTIVE)": "Undo: share it again (Share a Keep note).",
    "Write values into a Sheet range from a JSON file (DESTRUCTIVE)":
        "Undo: open the Sheet's version history (File > Version history).",
    "Clear a range in a Sheet (DESTRUCTIVE)":
        "Undo: open the Sheet's version history (File > Version history).",
    # --- Licenses, Vault, schemas, contacts, admin roles ---
    "Remove license from user": "Undo: add it back (Add license to user).",
    "BULK: remove a license from many users (DESTRUCTIVE)":
        "Undo: BULK: assign a license to many users (same scope).",
    "BULK: sync a license - exact match (DESTRUCTIVE)":
        "Undo: add the license back to anyone it was removed from (Add "
        "license to user).",
    "BULK: swap a license for many users (move A -> B)":
        "Undo: swap them back the same way (B -> A).",
    "Delete hold (DESTRUCTIVE)":
        "Undo: create the hold again - anything deleted while no hold "
        "applied may be gone for good.",
    "Delete a saved query (DESTRUCTIVE)": "Undo: create it again (Create a saved search query).",
    "Delete export (DESTRUCTIVE)": _NO_UNDO + " - create a new export if needed.",
    "Delete schema (DESTRUCTIVE)": _NO_UNDO + ".",
    "Remove a field from a schema (DESTRUCTIVE)": _NO_UNDO + ".",
    "Delete shared contact (DESTRUCTIVE)": _NO_UNDO + ".",
    "Remove a bad address from EVERYONE's 'Other contacts' (DESTRUCTIVE)": _NO_UNDO + ".",
    "Remove duplicate personal contacts (DESTRUCTIVE)":
        _NO_UNDO + " - export the contacts first (List a user's personal "
        "contacts).",
    "Remove a contact delegate (DESTRUCTIVE)": "Undo: Add a contact delegate.",
    "Remove admin assignment (DESTRUCTIVE)": "Undo: assign the role again.",
    "Delete a custom admin role (DESTRUCTIVE)":
        _NO_UNDO + " - note its privileges first (Admin role details).",
    # --- Printers, buildings, rooms, features ---
    "Delete printer (DESTRUCTIVE)": _NO_UNDO + " - create it again if needed.",
    "Delete building (DESTRUCTIVE)": _NO_UNDO + " - create it again if needed.",
    "Delete calendar resource (DESTRUCTIVE)": _NO_UNDO + " - create it again if needed.",
    "Delete a feature (DESTRUCTIVE)": _NO_UNDO + " - create it again if needed.",
    # --- Marketing, access & identity ---
    "Remove Data Studio (Looker Studio) sharing (DESTRUCTIVE)":
        "Undo: Share Data Studio (Looker Studio) assets with someone.",
    "Delete a CAA level (DESTRUCTIVE)":
        _NO_UNDO + " - note its rule first (List Context-Aware Access levels).",
    "Delete an SSO profile (DESTRUCTIVE)": _NO_UNDO + ".",
    "Delete an SSO signing certificate (DESTRUCTIVE)":
        "Undo: add it again (Add an SSO signing certificate) - keep the file.",
    "Remove an allowlisted domain (DESTRUCTIVE)": "Undo: Add allowlisted domains.",
}


def _apply_undo_notes():
    # Adds each note to its task's description (once), when the catalog
    # loads. A name that is not a task is a bug - tests/test_v282.py checks.
    for tasks in TASKS.values():
        for task in tasks:
            note = UNDO_NOTES.get(task["name"])
            if note and note not in task["desc"]:
                task["desc"] = task["desc"].rstrip() + " " + note


_apply_undo_notes()


# =============================================================================
# SECTION: "name or ID" boxes - IDs sent as id:<ID> (2.83)
# =============================================================================
# Several GAM items are a NAME or 'id:<ID>' (GAM wiki: <MatterItem>,
# <QueryItem>, <HoldItem>, <ExportItem> ::= <UniqueID>|<String>; <RoleItem>
# ::= id:<RoleID>|<RoleName>; <UniqueID> ::= id:<String>). Typed bare, an ID
# is looked up as a NAME and GAM answers "Does not exist". For the items
# whose ID shape is known, GAMGUI adds the id: itself:
#   uuid   - Vault matter and saved query IDs (0f97bd80-c3e2-40ec-b249-...)
#   roleid - admin role IDs (all digits; 15 in every real one seen, and no
#            role NAME was all digits)
#   ssoid  - inbound SSO profile IDs. GAM 7.48.20 wants id:<ID> and adds
#            'inboundSamlSsoProfiles/' itself - the wiki's documented
#            id:inboundSamlSsoProfiles/<ID> FAILED before 7.48.22 ("does
#            not match the pattern"; fixed in 7.48.22 after GAMGUI's
#            report), and a bare ID or the full name GAM prints is looked
#            up as a display name. So the printed name becomes id:<ID>, and
#            a bare value shaped like the real IDs (15 lower-case letters /
#            digits starting with 2 digits) gets id:.
# Holds and exports have no real example to check the shape against, so
# their boxes say to type id:<ID> instead (no guessing).
ID_FORMS = {
    "uuid": re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                       r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"),
    "roleid": re.compile(r"\d{10,}"),
    "ssoid": re.compile(r"(?:id:)?(?:inboundSamlSsoProfiles/)?(?P<id>\d{2}[a-z0-9]{13})"),
}


def unique_ids(text, form):
    # Each comma-separated item shaped like an ID of this form -> id:<ID>.
    # Names, and IDs that already say id: / uid:, are left as they are; text
    # with nothing to change comes back exactly as typed.
    # A form with an (?P<id>...) group sends only that part (e.g. the ID
    # out of a full 'inboundSamlSsoProfiles/<ID>' name).
    items = [item.strip() for item in str(text).split(",")]
    fixed = []
    for item in items:
        match = ID_FORMS[form].fullmatch(item)
        if not match:
            fixed.append(item)
        elif "id" in ID_FORMS[form].groupindex:
            fixed.append("id:" + match.group("id"))
        else:
            fixed.append("id:" + item)
    return ",".join(fixed) if fixed != items else text


def vault_matter_ids(text):
    # Vault matter IDs (see unique_ids).
    return unique_ids(text, "uuid")


def _mark_unique_id_boxes():
    # Marks the boxes above (not the NAME box when creating one):
    #   "vaultid"  - takes an existing Vault matter (also gets the picker)
    #   "idform"   - the ID shape to turn into id:<ID>
    for tasks in TASKS.values():
        for task in tasks:
            for field in task["fields"]:
                label = field.get("label", "")
                if field.get("rawappend") or not re.search(
                        r"name or ID|name/ID", label, re.I):
                    continue
                if re.search(r"matter", label, re.I):
                    field["vaultid"] = True
                    field["idform"] = "uuid"
                elif re.search(r"saved (query|search)", label, re.I):
                    field["idform"] = "uuid"
                elif re.match(r"Role name or ID", label):
                    field["idform"] = "roleid"
                elif re.match(r"Profile display name or ID", label):
                    field["idform"] = "ssoid"
                elif re.match(r"Meet conference name/ID", label):
                    # GAM hands this straight to Google as the parent,
                    # which must be conferenceRecords/<ID> (GAM 7.48.20
                    # _printShowMeetItems) - a bare ID cannot work.
                    field["addprefix"] = "conferenceRecords/"
                elif re.match(r"(Hold|Export) \(name or ID\)", label):
                    field["label"] = label.replace("(name or ID)",
                                                   "(name, or id:<ID>)")


_mark_unique_id_boxes()


def _note_chrome_browser_scopes():
    # 2.96: GAM 7.49.00 manages Chrome browsers and their enrollment tokens
    # with Google's Chrome Management API. Its wiki page (Chrome-Browsers-
    # and-Enrollment-Tokens): run 'gam oauth update' once and tick the two
    # new scopes - until then these tasks fail with a permission error. The
    # old command words (browser, browsertoken) still work in 7.49.00.
    browser = {"browser", "browsers", "chromebrowser", "chromebrowsers"}
    token = {"browsertoken", "browsertokens", "chromebrowsertoken", "chromebrowsertokens"}
    for tasks in TASKS.values():
        for task in tasks:
            words = set(task.get("template", "").lower().split())
            if not words & (browser | token) or "gam oauth update" in task["desc"]:
                continue
            scope = ("Chrome Management API - Enrollment Tokens" if words & token
                     else "Chrome Management API - Browsers")
            task["desc"] += (" If this fails with a permission error after updating to GAM "
                             "7.49.00: run 'gam oauth update' once and tick '" + scope + "'.")


_note_chrome_browser_scopes()


# =============================================================================
# SECTION: Search synonyms (2.82)
# =============================================================================
# The task search needs every typed word to appear in a task's name,
# category, description or GAM command. Admins type everyday words that GAM
# and Google do not use: "disable user" (Google: suspend), "mfa" / "2fa"
# (2-Step Verification), "ooo" (vacation / out of office), "erase
# chromebook" (powerwash), "address book" (Global Address List). Each typed
# word may now also match its synonyms. Phrases are joined into one word
# first ("out of office" -> "ooo").
SEARCH_PHRASES = {
    "out of office": "ooo", "out-of-office": "ooo", "address book": "addressbook",
    "new hire": "newhire", "new staff": "newhire", "new user": "newhire",
    "two factor": "2fa", "two-factor": "2fa", "2 factor": "2fa",
    "multi factor": "mfa", "multi-factor": "mfa", "third party": "thirdparty",
    "third-party": "thirdparty", "factory reset": "factoryreset",
    "log out": "signout", "sign out": "signout", "log off": "signout",
}
_SAME_AS = [
    # Each group: words that should find each other.
    ["suspend", "disable", "lock", "block"],
    # 2.83: the Compromised Account section
    ["compromised", "hacked", "breach", "breached", "takeover", "phished"],
    ["offboard", "offboarding", "deprovision", "departure", "leaving",
     "departing", "hand-off"],
    ["2fa", "mfa", "2sv", "2-step", "two-step"],
    ["ooo", "out-of-office", "vacation", "auto-reply", "autoreply"],
    ["erase", "wipe", "powerwash", "factoryreset", "factory-reset"],
    ["seat", "seats", "license"],
    ["recover", "restore", "undelete", "untrash", "reactivate", "put back"],
    ["remove", "delete", "revoke", "unshare"],
    ["list", "show", "print", "export", "report"],
    ["thirdparty", "oauth", "app access", "token"],
    ["addressbook", "global address list", "directory"],
    ["newhire", "onboard", "onboarding", "create user"],
    ["signout", "sign out", "revoke sessions"],
    ["reassign", "transfer", "change course owner"],
    ["email", "gmail", "mailbox", "mail"],
]
SEARCH_SYNONYMS = {}
for _group in _SAME_AS:
    for _word in _group:
        SEARCH_SYNONYMS.setdefault(_word, set()).update(_group)


def search_terms(needle):
    # The typed text -> one set of acceptable spellings per word.
    text = " " + (needle or "").lower().strip() + " "
    for phrase, joined in SEARCH_PHRASES.items():
        text = text.replace(" " + phrase + " ", " " + joined + " ")
    return [SEARCH_SYNONYMS.get(word, set()) | {word} for word in text.split()]


def task_matches(needle, category, task):
    # True when EVERY typed word (or one of its synonyms) appears in the
    # task's name, category, description or GAM command.
    haystack = " ".join((task["name"], category, task.get("desc", ""),
                         task.get("template", "") or "")).lower()
    return all(any(alt in haystack for alt in alts)
               for alts in search_terms(needle))


# =============================================================================
# SECTION: User / group picker (2.82)
# =============================================================================
# A "Pick..." button for boxes that take an EXISTING user or group, so an
# admin does not have to know the exact address. Decided from where the box
# sits in the GAM command (like role_picker): 'user {key}' -> users,
# 'group {key}' -> groups. Boxes that NAME a new account or group ('create
# user {key}', 'create group {key}') get no picker. 2.83 adds the other GAM
# words that always take a user in your domain (Classroom teachers /
# students, mail and contact delegates) and the Cloud Identity spelling of a
# group (cigroup). Words that may also mean a group or an outside address
# (member, admin, owner) stay typed.
def address_picker(task, field):
    # "user", "group" or None for one form box.
    if not task or not field or field.get("rawappend") or field.get("choices") \
            or field.get("valuemap") or field.get("filepicker"):
        return None
    if field.get("picker") in ("user", "group"):
        return field["picker"]
    template = task.get("template", "") or ""
    key = re.escape(field["key"])
    if re.search(r"\bcreate (?:user|group|cigroup) \{" + key + r"\}", template):
        return None
    if re.search(r"(?:^|\s)(?:users?|teachers?|students?|delegate|contactdelegate)"
                 r" \{" + key + r"\}", template):
        return "user"
    if re.search(r"(?:^|\s)(?:groups?|cigroups?) \{" + key + r"\}", template):
        return "group"
    return None


def parse_user_list(text):
    # 'gam print users fields primaryemail,name' -> [(email, full name)],
    # sorted by email.
    out = []
    for row in _csv_rows(text):
        email = (row.get("primaryEmail") or "").strip()
        if email:
            out.append((email, (row.get("name.fullName") or "").strip()))
    return sorted(out, key=lambda r: r[0].lower())


def parse_group_list(text):
    # 'gam print groups fields email,name' -> [(email, name)], sorted.
    out = []
    for row in _csv_rows(text):
        email = (row.get("email") or "").strip()
        if email:
            out.append((email, (row.get("name") or "").strip()))
    return sorted(out, key=lambda r: r[0].lower())


# =============================================================================
# SECTION: Course picker (2.83)
# =============================================================================
# A "Pick..." button for boxes that take a Google Classroom course ID, so an
# admin can find the course by its name, section or teacher instead of
# running List courses first. Decided from where the box sits in the GAM
# command: 'course {key}', 'courses {key}' and the student-group commands
# 'course-studentgroups {key}' / 'course-studentgroup-members {key}'.
#   "active" - list active + provisioned courses first (quick)
#   "all"    - start with every course, archived ones included (the task
#              works on archived courses: delete, reactivate)
COURSE_STATE_NAMES = {
    "ACTIVE": "Active",
    "ARCHIVED": "Archived",
    "PROVISIONED": "Provisioned (not accepted)",
    "DECLINED": "Declined",
    "SUSPENDED": "Suspended",
}


def course_picker(task, field):
    # "active", "all" or None for one form box.
    if not task or not field or field.get("rawappend") or field.get("choices") \
            or field.get("valuemap") or field.get("filepicker"):
        return None
    template = task.get("template", "") or ""
    key = re.escape(field["key"])
    if not re.search(r"(?:^|\s)(?:courses?|course-studentgroups|"
                     r"course-studentgroup-members) \{" + key + r"\}", template):
        return None
    if re.match(r"\s*delete course \{", template) or \
            re.search(r"\bstatus active\b", template):
        return "all"
    return "active"


def parse_course_list(text):
    # 'gam print courses ... fields id,name,section,coursestate owneremail'
    # -> [{"id", "name", "section", "state", "owner"}], sorted by name, then
    # section. state is plain English (COURSE_STATE_NAMES).
    out = []
    for row in _csv_rows(text):
        course_id = (row.get("id") or "").strip()
        if not course_id:
            continue
        state = (row.get("courseState") or "").strip()
        out.append({
            "id": course_id,
            "name": (row.get("name") or "").strip(),
            "section": (row.get("section") or "").strip(),
            "state": COURSE_STATE_NAMES.get(state, state.title()),
            "owner": (row.get("ownerEmail") or "").strip(),
        })
    return sorted(out, key=lambda r: (r["name"].lower(), r["section"].lower(), r["id"]))


# =============================================================================
# SECTION: Picker lists for other IDs (2.83)
# =============================================================================
# 'Pick...' for boxes that take the ID of an existing Chrome browser, Chrome
# printer, building, calendar resource (room) or alias - IDs nobody knows by
# heart. Only the info / delete / update commands get one ('<verb> <word>
# {key}' at the start of the command); create commands name something new,
# and the course-alias tasks take a COURSE alias, not a user/group alias.
# Mobile devices are SEARCHED instead of listed: a district's whole 'print
# mobile' can take many minutes (43,000+ rows in one test), but 'query
# email:<start>*' answers in seconds (see mobile_search_query).
ID_PICKER_WORDS = {
    "mobile": "mobile",
    "browser": "browsers",
    "printer": "printers",
    "building": "buildings",
    "resource": "resources",
    "alias": "aliases",
}

# Columns each list keeps, in GAM's CSV header spelling; the first is what
# the list is sorted by, ID_PICK_KEYS names the one that goes in the box.
ID_PICK_COLUMNS = {
    "browsers": ("machineName", "orgUnitPath", "lastActivityTime", "deviceId"),
    "printers": ("displayName", "makeAndModel", "orgUnitPath", "id"),
    "buildings": ("buildingName", "description", "buildingId"),
    "resources": ("resourceName", "resourceType", "resourceEmail", "resourceId"),
    "aliases": ("Alias", "Target", "TargetType"),
    "mobile": ("email", "model", "os", "status", "lastSync", "resourceId"),
    "shareddrives": ("name", "orgUnit", "createdTime", "id"),
    "chromebooks": ("serialNumber", "annotatedAssetId", "annotatedUser",
                    "orgUnitPath", "status", "lastSync", "deviceId"),
    "matters": ("name", "state", "description", "matterId"),
}
ID_PICK_KEYS = {
    "mobile": "resourceId",
    "shareddrives": "id",
    "matters": "matterId",
    "chromebooks": "serialNumber",
    "browsers": "deviceId",
    "printers": "id",
    "buildings": "buildingId",
    "resources": "resourceId",
    "aliases": "Alias",
}


def id_picker(task, field):
    # "browsers" / "printers" / "buildings" / "resources" / "aliases" or None.
    if not task or not field or field.get("rawappend") or field.get("choices") \
            or field.get("valuemap") or field.get("filepicker"):
        return None
    template = task.get("template", "") or ""
    found = re.match(r"\s*(?:info|delete|update) (\w+) \{" + re.escape(field["key"])
                     + r"\}", template)
    if not found:
        return None
    return ID_PICKER_WORDS.get(found.group(1))


def shareddrive_picker(task, field):
    # "shareddrives" for a box behind a {shareddrive:KEY} token (it takes a
    # Shared Drive name or ID), else None. The picker fills in the ID:
    # names can repeat (5 pairs in one real district), IDs cannot, and the
    # token sends an ID as 'shareddriveid'.
    if not task or not field or field.get("rawappend") or field.get("choices") \
            or field.get("valuemap") or field.get("filepicker"):
        return None
    # 2.89: a workflow box (no command template) asks for it with
    # F(..., picker="shareddrive").
    if field.get("picker") == "shareddrive":
        return "shareddrives"
    token = "{shareddrive:" + field["key"] + "}"
    return "shareddrives" if token in (task.get("template", "") or "") else None


def matter_picker(task, field):
    # "matters" for a box that takes an existing Vault matter (marked
    # "vaultid" by _mark_vault_matter_boxes), else None. The picker puts the
    # matter ID in the box; build_command sends it as id:<ID>.
    if not task or not field or not field.get("vaultid"):
        return None
    if field.get("rawappend") or field.get("choices") or field.get("valuemap"):
        return None
    return "matters"


def chromebook_picker(task, field):
    # "chromebooks" for a box that takes a Chromebook's serial number
    # ('cros_sn {key}'), else None. The list is SEARCHED (see
    # SEARCHED_LISTS) - a district can have tens of thousands.
    if not task or not field or field.get("rawappend") or field.get("choices") \
            or field.get("valuemap") or field.get("filepicker"):
        return None
    if re.search(r"\bcros_sn \{" + re.escape(field["key"]) + r"\}",
                 task.get("template", "") or ""):
        return "chromebooks"
    return None


# Lists that are SEARCHED instead of loaded whole (2.83): a whole 'print
# mobile' / 'print cros' can take many minutes. The Find text must match
# "allowed" (after trimming and lower-casing) - letters, digits and a few
# address characters, at least 3 - so it can only ever fill in the value of
# these fixed queries, never change what kind of query it is. Each query
# answers in seconds; the results are merged (see merge_search_rows).
#   mobile      - devices of every address that STARTS with the text
#   chromebooks - serial numbers, asset tags (each word) and users starting
#                 with the text (GAM 7.48.20, checked on real devices:
#                 'id:' = serial, 'asset_id:', 'user:'; case does not matter)
SEARCHED_LISTS = {
    "mobile": {"allowed": r"[a-z0-9._@+-]{3,}", "queries": ("email:{}*",),
               "bad": "Type at least 3 characters of the email address "
                      "(letters, numbers, . _ @ + - only)."},
    "chromebooks": {"allowed": r"[a-z0-9._@-]{3,}",
                    "queries": ("id:{}", "asset_id:{}", "user:{}"),
                    "bad": "Type at least 3 characters of a serial number, "
                           "asset tag or user (letters, numbers, . _ @ - "
                           "only, no spaces)."},
}


def search_queries(kind, text):
    # The Find box text -> the queries GAM sends for a searched list, or
    # None when the text is not allowed (see SEARCHED_LISTS).
    rule = SEARCHED_LISTS.get(kind)
    text = (text or "").strip().lower()
    if not rule or not re.fullmatch(rule["allowed"], text):
        return None
    return [query.format(text) for query in rule["queries"]]


def merge_search_rows(kind, lists):
    # The rows of several searches -> one list, each device once (by its
    # ID column), sorted by the first column.
    key = ID_PICK_KEYS[kind]
    first = ID_PICK_COLUMNS[kind][0]
    seen, out = set(), []
    for rows in lists:
        for row in rows:
            if row.get(key) not in seen:
                seen.add(row.get(key))
                out.append(row)
    return sorted(out, key=lambda r: (str(r.get(first, "")).lower(), str(r.get(key))))


def mobile_search_query(text):
    # The mobile-device query for the Find text ('email:<text>*'), or None
    # (kept for older callers - see search_queries).
    queries = search_queries("mobile", text)
    return queries[0] if queries else None


def parse_id_list(kind, text):
    # A 'gam print ...' CSV -> [dict of ID_PICK_COLUMNS[kind]], rows without
    # the ID skipped, sorted by the first column (then the ID). GAM's
    # timestamps (2026-10-06T12:53:46Z) are shortened to '2026-10-06 12:53'.
    columns = ID_PICK_COLUMNS[kind]
    id_key = ID_PICK_KEYS[kind]
    out = []
    for row in _csv_rows(text):
        item = {col: (row.get(col) or "").strip() for col in columns}
        if not item[id_key]:
            continue
        for col in columns:
            if re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d", item[col]):
                item[col] = item[col][:16].replace("T", " ")
        if kind == "matters":
            item["state"] = item["state"].title()   # OPEN -> Open
        out.append(item)
    return sorted(out, key=lambda r: (r[columns[0]].lower(), r[id_key]))


# =============================================================================
# SECTION: Picker lists shared by the desktop and browser versions (2.83)
# =============================================================================
# The READ-ONLY gam print command behind each list, the function that reads
# its CSV, the exit codes that still mean "the list is complete", and a
# timeout in seconds: kind -> (argv, parser, ok_codes, timeout).
PICK_LISTS = {
    "ous": (["print", "orgs", "fields", "orgunitpath"], parse_ou_paths,
            (0,), 300),
    "roles": (["print", "adminroles"], parse_admin_roles, (0,), 300),
    "privileges": (["print", "privileges"], parse_privileges, (0,), 300),
    "users": (["print", "users", "fields", "primaryemail,name"],
              parse_user_list, (0,), 300),
    "groups": (["print", "groups", "fields", "email,name"],
               parse_group_list, (0,), 300),
    # Exit code 56 ("does not exist") only means some course's owner
    # account was deleted - its row says 'Unknown user' and the list is
    # complete. Every archived course can take minutes: longer timeouts.
    "courses": (["print", "courses", "states", "active,provisioned",
                 "fields", "id,name,section,coursestate", "owneremail"],
                parse_course_list, (0, 56), 600),
    "courses_all": (["print", "courses", "fields",
                     "id,name,section,coursestate", "owneremail"],
                    parse_course_list, (0, 56), 1800),
    "browsers": (["print", "browsers", "fields",
                  "deviceid,machinename,orgunitpath,lastactivitytime"],
                 lambda text: parse_id_list("browsers", text), (0,), 300),
    "printers": (["print", "printers"],
                 lambda text: parse_id_list("printers", text), (0,), 300),
    "buildings": (["print", "buildings"],
                  lambda text: parse_id_list("buildings", text), (0,), 300),
    "resources": (["print", "resources"],
                  lambda text: parse_id_list("resources", text), (0,), 300),
    "aliases": (["print", "aliases"],
                lambda text: parse_id_list("aliases", text), (0,), 300),
    # Searched with 'query email:<start>*' (mobile_search_query).
    "mobile": (["print", "mobile", "fields",
                "resourceid,email,model,os,status,lastsync"],
               lambda text: parse_id_list("mobile", text), (0,), 300),
    # Searched (SEARCHED_LISTS): run once per query with 'query <q>'.
    "chromebooks": (["print", "cros", "fields",
                     "deviceid,serialnumber,annotatedassetid,annotateduser,"
                     "orgunitpath,status,lastsync"],
                    lambda text: parse_id_list("chromebooks", text), (0,), 300),
    "matters": (["print", "vaultmatters", "fields",
                 "matterid,name,state,description"],
                lambda text: parse_id_list("matters", text), (0,), 300),
    "shareddrives": (["print", "shareddrives", "fields",
                      "id,name,createdtime,orgunit"],
                     lambda text: parse_id_list("shareddrives", text), (0,), 300),
}


# What each table picker shows (desktop GamGui._pick_table and the
# browser version's Pick... window). columns: (key in
# the list's rows, heading, width). id: the key whose value goes in the box.
# all_kind: a second, bigger list behind an "Include ..." checkbox.
PICK_TABLES = {
    "ous": {
        "noun": "OU", "article": "an", "plural": "OUs", "size": "680x560",
        "id": "path", "find": "the OU path",
        "columns": (("path", "OU path", 600),),
        "loading": "Loading the OUs from Google..."},
    "roles": {
        "noun": "admin role", "article": "an", "plural": "admin roles",
        "size": "760x520", "id": "name", "find": "the role's name",
        "columns": (("label", "Role", 320), ("name", "Name GAM uses", 320)),
        "loading": "Loading the admin roles from Google..."},
    "users": {
        "noun": "user", "plural": "users", "size": "680x560", "id": "email",
        "find": "a name or address",
        "columns": (("email", "Email address", 330), ("name", "Name", 280)),
        "loading": "Loading the users from Google (a large domain can take "
                   "a minute)..."},
    "chromebooks": {
        "noun": "Chromebook", "plural": "Chromebooks", "size": "1060x560",
        "id": "serialNumber", "search": True,
        "find": "the serial number, asset tag or user",
        "columns": (("serialNumber", "Serial number", 150),
                    ("annotatedAssetId", "Asset tag", 150),
                    ("annotatedUser", "Assigned user", 200),
                    ("orgUnitPath", "OU", 220), ("status", "Status", 100),
                    ("lastSync", "Last sync (UTC)", 130),
                    ("deviceId", "Device ID", 0)),
        "search_help": "Type the start of a serial number, an asset tag "
                       "word, or a user (at least 3 characters), then press "
                       "Enter or click Search.",
        "loading": "Searching Google for the Chromebooks..."},
    "matters": {
        "noun": "Vault matter", "plural": "Vault matters", "size": "860x500",
        "id": "matterId", "find": "the matter's name, state or description",
        "columns": (("name", "Matter", 260), ("state", "State", 80),
                    ("description", "Description", 260),
                    ("matterId", "Matter ID", 250)),
        "loading": "Loading the Vault matters from Google..."},
    "shareddrives": {
        "noun": "Shared Drive", "plural": "Shared Drives", "size": "900x560",
        "id": "id", "find": "the Shared Drive's name, OU or ID",
        "columns": (("name", "Shared Drive", 280), ("orgUnit", "OU", 220),
                    ("createdTime", "Created (UTC)", 130),
                    ("id", "Shared Drive ID", 200)),
        "loading": "Loading the Shared Drives from Google..."},
    # People and rooms together (calendar_picker); loaded from both lists.
    "calendars": {
        "noun": "calendar", "plural": "calendars", "size": "800x560",
        "id": "email", "combine": ("users", "resources"),
        "find": "a person's or room's name or address",
        "columns": (("email", "Calendar address", 360), ("name", "Name", 240),
                    ("type", "Type", 120)),
        "loading": "Loading the people and rooms from Google (a large "
                   "domain can take a minute)..."},
    # Users and groups together (member_picker); loaded from both lists.
    "members": {
        "noun": "user or group", "plural": "users and groups",
        "size": "760x560", "id": "email", "combine": ("users", "groups"),
        "find": "a name or address",
        "columns": (("email", "Email address", 330), ("name", "Name", 260),
                    ("type", "Type", 80)),
        "loading": "Loading the users and groups from Google (a large "
                   "domain can take a minute)..."},
    "groups": {
        "noun": "group", "plural": "groups", "size": "680x560", "id": "email",
        "find": "a name or address",
        "columns": (("email", "Email address", 330), ("name", "Name", 280)),
        "loading": "Loading the groups from Google (a large domain can take "
                   "a minute)..."},
    "courses": {
        "noun": "course", "plural": "courses", "size": "900x580", "id": "id",
        "find": "the course name, section, teacher's address or ID",
        "columns": (("name", "Course name", 220), ("section", "Section", 130),
                    ("owner", "Teacher (owner)", 220), ("state", "State", 170),
                    ("id", "Course ID", 110)),
        "loading": "Loading active courses from Google (a large district can "
                   "take a minute)...",
        "all_kind": "courses_all",
        "all_label": "Include archived courses (slower)",
        "all_loading": "Loading EVERY course from Google, archived ones "
                       "included (this can take a few minutes)..."},
    "browsers": {
        "noun": "browser", "plural": "browsers", "size": "900x560",
        "id": "deviceId", "find": "the computer name, OU or device ID",
        "columns": (("machineName", "Computer name", 220),
                    ("orgUnitPath", "OU", 240),
                    ("lastActivityTime", "Last active (UTC)", 140),
                    ("deviceId", "Device ID", 260)),
        "loading": "Loading the enrolled Chrome browsers from Google..."},
    "printers": {
        "noun": "printer", "plural": "printers", "size": "860x500", "id": "id",
        "find": "the printer name, model or OU",
        "columns": (("displayName", "Printer", 220),
                    ("makeAndModel", "Make and model", 220),
                    ("orgUnitPath", "OU", 220), ("id", "Printer ID", 140)),
        "loading": "Loading the Chrome printers from Google..."},
    "buildings": {
        "noun": "building", "plural": "buildings", "size": "760x500",
        "id": "buildingId", "find": "the building name or ID",
        "columns": (("buildingName", "Building", 240),
                    ("description", "Description", 260),
                    ("buildingId", "Building ID", 200)),
        "loading": "Loading the buildings from Google..."},
    "resources": {
        "noun": "room / resource", "plural": "rooms / resources",
        "size": "900x560", "id": "resourceId",
        "find": "the room's name, type, calendar address or ID",
        "columns": (("resourceName", "Name", 240),
                    ("resourceType", "Type", 140),
                    ("resourceEmail", "Calendar address", 300),
                    ("resourceId", "Resource ID", 160)),
        "loading": "Loading the rooms and resources from Google..."},
    "aliases": {
        "noun": "alias", "article": "an", "plural": "aliases", "size": "760x500",
        "id": "Alias",
        "find": "the alias or the address it belongs to",
        "columns": (("Alias", "Alias", 280), ("Target", "Belongs to", 280),
                    ("TargetType", "Type", 120)),
        "loading": "Loading the aliases from Google (GAM checks every user "
                   "and group - this can take a minute)..."},
    # Searched, not listed: see gam_catalog.mobile_search_query.
    "mobile": {
        "noun": "mobile device", "plural": "mobile devices",
        "size": "1000x560", "id": "resourceId", "search": True,
        "find": "the start of the person's email address",
        "columns": (("email", "User", 240), ("model", "Model", 150),
                    ("os", "OS", 120), ("status", "Status", 100),
                    ("lastSync", "Last sync (UTC)", 130),
                    ("resourceId", "Resource ID", 200)),
        "search_help": "Type the start of the person's email address (at "
                       "least 3 characters), then press Enter or click "
                       "Search. Google lists the devices of every address "
                       "that starts that way.",
        "loading": "Searching Google for the devices..."},
}


# Boxes whose GAM word is not 'user' / 'group' but that still take an
# existing user, group, or either ("members": users and groups in one list).
# Each rule is the exact shape of the command around the box ({K} = the
# box); the first rule that matches wins. Typed values always still work -
# a member may also be an outside address.
MEMBER_PICKER_RULES = (
    (r"^oauth (?:create|update) \[admin \{K\}\]", "users"),
    (r"\btransfer ownership \{K\}(?!\s*\{)", "users"),           # calendar
    (r"\btransfer ownership (?:query )?\{\w+\} \{K\}", "users"),  # Drive files
    (r"\btransfer drive \{K\}", "users"),
    (r"\bowner \{K\}", "users"),                                 # Classroom
    (r"\bdelegate to \{K\}", "users"),
    (r"\binfo member \{K\}", "groups"),
    (r"\barchive messages \{K\}", "groups"),
    (r"^update group \{\w+\} (?:add|update|delete) .*\{K\}\s*$", "members"),
    (r"^update groups csvfile \S+ (?:add|remove) .*\{K\}\s*$", "members"),
    (r"\bcreate admin \{K\}", "members"),
    (r"\bdrivefileacl (?:query \{\w+\}|~?\{[\w:]+\}) \{K\}", "members"),
    (r"\bchatmember asadmin .*\{mtype\} \{K\}", "members"),
    (r"\{whotype\} \{K\}", "members"),
    (r"^update alias \{\w+\} \{ttype\} \{K\}", "members"),
)


def member_picker(task, field):
    # "users", "groups", "members" or None (see MEMBER_PICKER_RULES).
    if not task or not field or field.get("rawappend") or field.get("choices") \
            or field.get("valuemap") or field.get("filepicker"):
        return None
    template = task.get("template", "") or ""
    box = r"\{" + re.escape(field["key"]) + r"\}"
    for pattern, kind in MEMBER_PICKER_RULES:
        if re.search(pattern.replace(r"\{K\}", box), template):
            return kind
    return None


def member_rows(users, groups):
    # The users list ((email, name) pairs) and groups list -> one table,
    # sorted by address, with a Type column.
    rows = [{"email": e, "name": n, "type": "User"} for e, n in users]
    rows += [{"email": e, "name": n, "type": "Group"} for e, n in groups]
    return sorted(rows, key=lambda r: r["email"].lower())


def calendar_picker(task, field):
    # "calendars" for a box that takes a calendar ID ('calendars {key}'):
    # a person's calendar is their address, a room's is its calendar
    # address, so one list of both fits. Not for deleting a SECONDARY
    # calendar or transferring one - those are usually a person's own
    # extra calendars, which neither list has.
    if not task or not field or field.get("rawappend") or field.get("choices") \
            or field.get("valuemap") or field.get("filepicker"):
        return None
    template = task.get("template", "") or ""
    if re.search(r"\bremove calendars \{|\btransfer ownership\b", template):
        return None
    if re.search(r"(?:^|\s)calendars \{" + re.escape(field["key"]) + r"\}", template):
        return "calendars"
    return None


def calendar_rows(users, resources):
    # The users list ((email, name) pairs) and the rooms / resources list
    # (parse_id_list dicts) -> one table of calendar addresses with a Type.
    rows = [{"email": e, "name": n, "type": "Person"} for e, n in users]
    rows += [{"email": r.get("resourceEmail", ""), "name": r.get("resourceName", ""),
              "type": "Room / resource"} for r in resources if r.get("resourceEmail")]
    return sorted(rows, key=lambda r: r["email"].lower())


def combine_rows(kind, parts):
    # A combined picker table from its lists, in PICK_TABLES[kind]
    # ["combine"] order.
    if kind == "calendars":
        return calendar_rows(*parts)
    return member_rows(*parts)


def pick_rows(kind, items):
    # A parsed list -> table rows (dicts keyed like PICK_TABLES[kind]
    # columns): OU paths, admin roles and (email, name) pairs are turned
    # into dicts; lists that are dicts already pass through.
    rows = []
    for item in items:
        if kind == "ous":
            rows.append({"path": item})
        elif kind == "roles":
            rows.append({"label": role_label(item), "name": item.get("name", "")})
        elif isinstance(item, (tuple, list)):
            rows.append({"email": item[0], "name": item[1] if len(item) > 1 else ""})
        else:
            rows.append(item)
    return rows


def web_picker(task, field):
    # The Pick... list a form box gets in the browser version, or None:
    # {"kind": <PICK_TABLES key>, "all": <start with the bigger list>}. The
    # same rules as the desktop buttons; an OU box only when it ALWAYS takes
    # an OU (boxes that take "an email OR an OU" stay typed there).
    if ou_picker_mode(task, field) == "ou":
        return {"kind": "ous", "all": False}
    if role_picker(task, field) and not field.get("choices") \
            and not field.get("valuemap"):
        return {"kind": "roles", "all": False}
    kind = address_picker(task, field)
    if kind:
        return {"kind": kind + "s", "all": False}
    course_mode = course_picker(task, field)
    if course_mode:
        return {"kind": "courses", "all": course_mode == "all"}
    kind = id_picker(task, field)
    if kind:
        return {"kind": kind, "all": False}
    kind = (member_picker(task, field) or shareddrive_picker(task, field)
            or matter_picker(task, field) or chromebook_picker(task, field)
            or calendar_picker(task, field))
    if kind:
        return {"kind": kind, "all": False}
    return None
