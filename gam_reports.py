# =============================================================================
# Script:   gam_reports.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  09-24-2026
# Modified: 09-25-2026
# Version:  1.4 (GAMGUI 2.59 - 17 reports: files shared outside)
#
# Purpose:
#   The REPORT BUILDER catalog and script generator. An admin ticks the
#   reports they want (admin activity per admin, sign-ins from other
#   countries, leaked-password lockouts, stale accounts, old Chromebooks...),
#   and this module writes ONE Windows batch file that runs them all, each
#   into its own dated folder, with a log - ready for Task Scheduler.
#
# Notes:
#   - Every GAM command here was checked against a real GAM7 (read-only) and
#     GAM's source/wiki. Facts that shaped the design:
#       * 'gam report ... yesterday' uses gam.cfg's timezone (UTC by default),
#         so each command starts with 'config timezone local' to get the
#         local calendar day and local times in the output.
#       * That setting does NOT reach 'gam csv' child processes, so "one file
#         per admin" is ONE GAM call followed by a PowerShell split - the
#         per-admin files always add up to the whole day.
#       * About a third of admin events have no admin email (SYSTEM, Security
#         Center, Device, auto-provisioning); they get 'automatic-...' files.
#       * Login events carry networkInfo.regionCode (country) - no third-party
#         IP lookup service is needed for the out-of-country report.
#   - Paths are handed to PowerShell through environment variables, never
#     pasted into its code, so no folder name can break or inject into it.
#   - This module never runs anything; GAMGUI only saves the text it returns.
# =============================================================================

import base64
import json
import re

from gam_catalog import cmd_line_for_bat, _safe_text, _check_script_path

# ---- time periods for activity (audit log) reports --------------------------
# (label, gam arguments, which date names the output folder). Google keeps
# most audit data for about six months, hence the 180-day ceiling.
PERIODS = [
    ("Yesterday (the full day)", ["yesterday"], "YDAY"),
    ("Today so far", ["today"], "RUNDAY"),
    ("Last 7 days", ["start", "-7d"], "RUNDAY"),
    ("Last 30 days", ["start", "-30d"], "RUNDAY"),
    ("Last 90 days", ["start", "-90d"], "RUNDAY"),
    ("Last 180 days", ["start", "-180d"], "RUNDAY"),
    ("This month so far", ["thismonth"], "RUNDAY"),
]
PERIOD_LABELS = [p[0] for p in PERIODS]
DEFAULT_PERIOD = PERIOD_LABELS[0]


class BatPath(str):
    # Marks an argument that is a path built from batch variables, such as
    # %OUT%\report.csv. It is written inside plain double quotes WITHOUT
    # doubling the %, so cmd.exe fills in the folder when the script runs.
    pass


def _out(filename):
    # A file inside the report's dated output folder (%OUT%).
    return BatPath("%OUT%\\" + filename)


def _opt(key, label, kind, default, lo=None, hi=None):
    # One option of a report. kind: "bool", "int" (lo..hi), "period",
    # or "countries" (2-letter country codes).
    return {"key": key, "label": label, "kind": kind, "default": default,
            "lo": lo, "hi": hi}


_PERIOD_OPT = _opt("period", "Time period", "period", DEFAULT_PERIOD)

# ---- the report catalog -------------------------------------------------------
# 'folder' is the report's folder under the output root; each run writes into
# <root>\<folder>\<MM-DD-YYYY>. 'build(values)' returns (steps, date_var);
# a step is ("gam", argv) or ("split", in_file, include_automatic).
REPORTS = []


def _report(key, section, name, desc, folder, options, build, alert=False):
    # alert=True marks reports where ANY row deserves attention (a leaked
    # password, a sign-in from abroad...). "Email only when an alert report
    # finds something" counts only these.
    REPORTS.append({"key": key, "section": section, "name": name,
                    "desc": desc, "folder": folder, "options": options,
                    "build": build, "alert": alert})


def _period(values):
    for label, args, datevar in PERIODS:
        if label == values.get("period"):
            return list(args), datevar
    raise ValueError("Unknown time period: " + str(values.get("period")))


def _activity(values, filename, middle, filters=()):
    # A standard audit-log report: local time zone, optional row filters,
    # output to one CSV, the chosen period.
    args, datevar = _period(values)
    argv = ["config", "timezone", "local"] + list(filters) + [
        "redirect", "csv", _out(filename)] + middle + args
    return [("gam", argv)], datevar


def _build_admin(values):
    args, datevar = _period(values)
    if values.get("split", True):
        argv = ["config", "timezone", "local", "redirect", "csv",
                _out("_all-admin-activity.csv"), "report", "admin"] + args
        return [("gam", argv),
                ("split", "_all-admin-activity.csv",
                 bool(values.get("automatic", True)))], datevar
    argv = ["config", "timezone", "local", "redirect", "csv",
            _out("admin-activity.csv"), "report", "admin"] + args
    return [("gam", argv)], datevar


_report("admin_activity", "Admin audit",
        "Admin activity - one file per admin",
        "Everything every admin did in the Admin console or through GAM/API, "
        "saved as one file per admin (named by email) plus "
        "_all-admin-activity.csv with everything.",
        "Admin activity",
        [_PERIOD_OPT,
         _opt("split", "One file per admin", "bool", True),
         _opt("automatic", "Include automatic actions (SYSTEM, Security "
              "Center, devices) as automatic-... files", "bool", True)],
        _build_admin)

_report("group_changes", "Admin audit", "Group membership changes",
        "Every member added to or removed from a group, and by whom.",
        "Group membership changes", [_PERIOD_OPT],
        lambda v: _activity(v, "group-membership-changes.csv",
                            ["report", "admin", "event",
                             "ADD_GROUP_MEMBER,REMOVE_GROUP_MEMBER"]))

# Event names below were each checked against the live Reports API (v2.56):
# an unknown name makes the WHOLE report fail ("not found in manifest").
_ROLE_EVENTS = ("ASSIGN_ROLE,UNASSIGN_ROLE,GRANT_ADMIN_PRIVILEGE,"
                "REVOKE_ADMIN_PRIVILEGE,CREATE_ROLE,DELETE_ROLE,ADD_PRIVILEGE,"
                "REMOVE_PRIVILEGE,RENAME_ROLE,UPDATE_ROLE")
_ACCESS_EVENTS = ("AUTHORIZE_API_CLIENT_ACCESS,REMOVE_API_CLIENT_ACCESS,"
                  "CHANGE_APP_ACCESS,ADD_TO_TRUSTED_BY_OAUTH_SCOPE_OAUTH2_APPS,"
                  "ADD_TO_TRUSTED_OAUTH2_APPS,ADD_TO_LIMITED_OAUTH2_APPS,"
                  "ADD_TO_BLOCKED_OAUTH2_APPS,REMOVE_FROM_TRUSTED_OAUTH2_APPS,"
                  "REMOVE_FROM_LIMITED_OAUTH2_APPS,REMOVE_FROM_BLOCKED_OAUTH2_APPS,"
                  "CHANGE_SAML2_SERVICE_PROVIDER_CONFIG_ACS_ENDPOINT,"
                  "CHANGE_SAML2_SERVICE_PROVIDER_CONFIG_ENTITY_ID,"
                  "INBOUND_SSO_PROFILE_CREATED,INBOUND_SSO_PROFILE_UPDATED,"
                  "INBOUND_SSO_PROFILE_DELETED,CHANGE_SSO_SETTINGS")
_ACCOUNT_EVENTS = ("CREATE_USER,DELETE_USER,UNDELETE_USER,SUSPEND_USER,"
                   "UNSUSPEND_USER,RENAME_USER,ARCHIVE_USER,UNARCHIVE_USER,"
                   "CHANGE_PASSWORD,MOVE_USER_TO_ORG_UNIT")

_report("admin_roles", "Admin audit", "Admin role changes",
        "Admin roles assigned or removed, super admin granted or revoked, "
        "and roles created or edited - who did it and to whom.",
        "Admin role changes", [_PERIOD_OPT],
        lambda v: _activity(v, "admin-role-changes.csv",
                            ["report", "admin", "event", _ROLE_EVENTS]),
        alert=True)

_report("access_changes", "Admin audit", "App access and SSO changes",
        "Domain-wide delegation granted or removed (API client access), "
        "third-party apps trusted, limited or blocked, and SAML / SSO "
        "profile changes.",
        "App access and SSO changes", [_PERIOD_OPT],
        lambda v: _activity(v, "app-access-and-sso-changes.csv",
                            ["report", "admin", "event", _ACCESS_EVENTS]),
        alert=True)

_report("account_changes", "Admin audit", "Account changes",
        "Accounts created, deleted, restored, suspended, unsuspended, "
        "renamed, archived, moved to another OU, or given a new password by "
        "an admin.",
        "Account changes", [_PERIOD_OPT],
        lambda v: _activity(v, "account-changes.csv",
                            ["report", "admin", "event", _ACCOUNT_EVENTS]))

_report("password_changes", "Admin audit", "Password changes",
        "Users who changed their own password (Accounts audit log).",
        "Password changes", [_PERIOD_OPT],
        lambda v: _activity(v, "password-changes.csv",
                            ["report", "user_accounts", "event",
                             "password_edit"]))


def _build_abroad(values):
    codes = values["countries"]
    events = "login_success,login_failure" if values.get("failures") \
        else "login_success"
    # Drop rows whose country IS allowed; rows with no country are kept
    # (unknown location is worth a look).
    drop = "networkInfo.regionCode:regex:^(" + "|".join(codes) + ")$"
    return _activity(values, "sign-ins-outside-" + "-".join(codes) + ".csv",
                     ["report", "login", "event", events],
                     ["csv_output_row_drop_filter", drop])


_report("signins_abroad", "Sign-in security",
        "Sign-ins from outside your countries",
        "Sign-ins from any country not in your list, using the country "
        "Google records for each sign-in (no outside IP-lookup service).",
        "Sign-ins outside allowed countries",
        [_PERIOD_OPT,
         _opt("countries", "Allowed countries (2-letter codes, e.g. US MX)",
              "countries", "US"),
         _opt("failures", "Include FAILED sign-in attempts too", "bool", False)],
        _build_abroad, alert=True)

_report("leaked_passwords", "Sign-in security",
        "Accounts disabled for a leaked password",
        "Google disabled these accounts because their password was found "
        "in a data leak. They need a password reset.",
        "Leaked password lockouts", [_PERIOD_OPT],
        lambda v: _activity(v, "leaked-password-lockouts.csv",
                            ["report", "login", "event",
                             "account_disabled_password_leak"]), alert=True)

_report("suspicious_logins", "Sign-in security", "Suspicious sign-ins",
        "Sign-ins Google flagged as suspicious (including less-secure-app "
        "and programmatic ones).",
        "Suspicious sign-ins", [_PERIOD_OPT],
        lambda v: _activity(v, "suspicious-sign-ins.csv",
                            ["report", "login", "event",
                             "suspicious_login,suspicious_login_less_secure_app,"
                             "suspicious_programmatic_login"]), alert=True)


def _build_failed(values):
    n = values["threshold"]
    return _activity(values, "failed-sign-ins-" + str(n) + "-or-more.csv",
                     ["report", "login", "event", "login_failure",
                      "countsonly"],
                     ["csv_output_row_filter",
                      "login_failure:count>=" + str(n)])


_report("failed_logins", "Sign-in security",
        "Users with many failed sign-ins",
        "One row per user with their number of failed sign-ins - a sign of "
        "password guessing.",
        "Failed sign-ins",
        [_PERIOD_OPT,
         _opt("threshold", "Only users with at least this many failures",
              "int", 5, 1, 100000)],
        _build_failed, alert=True)


def _build_storage(values):
    argv = ["config", "timezone", "local", "redirect", "csv",
            _out("storage-per-user.csv"), "report", "users", "parameters",
            "accounts:drive_used_quota_in_mb,accounts:gmail_used_quota_in_mb,"
            "accounts:gplus_photos_used_quota_in_mb,accounts:total_quota_in_mb,"
            "accounts:used_quota_in_mb,accounts:used_quota_in_percentage"]
    if values.get("gb"):
        argv.append("convertmbtogb")
    return [("gam", argv)], "RUNDAY"


_report("storage", "Accounts", "Storage used per user",
        "Drive, Gmail and Photos storage for every account Google reports "
        "on - all domains in your Workspace account, including recently "
        "deleted accounts. Google's usage data is usually 2-3 days behind; "
        "GAM picks the newest day available.",
        "Storage per user",
        [_opt("gb", "Show sizes in GB instead of MB", "bool", False)],
        _build_storage)


def _build_stale(values):
    n = values["days"]
    argv = ["config", "timezone", "local", "csv_output_row_filter",
            "lastLoginTime:date<-" + str(n) + "d", "redirect", "csv",
            _out("not-signed-in-" + str(n) + "-days.csv"), "print", "users",
            "query", "isSuspended=False", "fields",
            "primaryemail,name,ou,lastlogintime,creationtime"]
    return [("gam", argv)], "RUNDAY"


_report("stale_users", "Accounts", "Active accounts not signed in lately",
        "Active (not suspended) accounts with no sign-in for N days, "
        "including accounts that have NEVER signed in.",
        "Stale accounts",
        [_opt("days", "No sign-in for at least this many days", "int", 90,
              1, 3650)],
        _build_stale)

_report("no_2sv", "Accounts", "Accounts without 2-Step Verification",
        "Active accounts that have not turned on 2-Step Verification.",
        "No 2-Step Verification", [],
        lambda v: ([("gam", ["config", "timezone", "local", "redirect", "csv",
                             _out("no-2sv.csv"), "print", "users", "query",
                             "isSuspended=False isEnrolledIn2Sv=False",
                             "fields",
                             "primaryemail,name,ou,isenrolledin2sv,"
                             "isenforcedin2sv,lastlogintime"])], "RUNDAY"))

_report("suspended_users", "Accounts", "Suspended accounts",
        "Every suspended account with the reason and when it was suspended.",
        "Suspended accounts", [],
        lambda v: ([("gam", ["config", "timezone", "local", "redirect", "csv",
                             _out("suspended.csv"), "print", "users", "query",
                             "isSuspended=True", "fields",
                             "primaryemail,name,ou,suspended,lastlogintime"])],
                   "RUNDAY"))


def _build_photo(values):
    # Active accounts whose profile picture is still Google's default
    # (verified live: the People API marks it photos.0.default = true). The
    # _ns selectors skip suspended accounts. One People API call per user,
    # run in parallel (multiprocess), like the FSISD script this replaces.
    ou = values.get("ou")
    who = ["ou_and_children_ns", ou] if ou else ["all", "users_ns"]
    argv = ["config", "timezone", "local", "csv_output_row_filter",
            "photos.0.default:boolean:true", "auto_batch_min", "1",
            "redirect", "csv", _out("default-profile-picture.csv"),
            "multiprocess"] + who + ["print", "peopleprofile", "fields",
                                     "photos"]
    return [("gam", argv)], "RUNDAY"


def _build_shared_outside(values):
    # Drive audit: sharing changes that reach OUTSIDE your domains. Checked
    # live (v2.59): Google's own 'visibility_change = external' flag also
    # marks many shares to people IN the domain, so GAMGUI decides itself:
    #   keep (anymatch): a person share (target_user has an @) OR a file
    #                    opened to anyone with the link / public on the web
    #   drop:            recipients in your domains or ignored partner
    #                    domains, sub-domains included, any letter case
    # The list form of the filters is used on purpose: in the live test the
    # JSON form of csv_output_row_drop_filter was silently ignored.
    domains = values["own"] + values.get("ignore", [])
    keep = "target_user:regex:@"
    if values.get("links", True):
        keep += " visibility:regex:^(people_with_link|public_on_the_web)$"
    drop = ("target_user:regex:(?i)@([a-z0-9-]+\\.)*("
            + "|".join(re.escape(d) for d in domains) + ")$")
    return _activity(values, "shared-outside.csv",
                     ["report", "drive", "event",
                      "change_document_visibility,change_user_access"],
                     ["csv_output_row_filter_mode", "anymatch",
                      "csv_output_row_filter", keep,
                      "csv_output_row_drop_filter", drop,
                      "csv_output_header_filter",
                      "id.time,actor.email,name,doc_title,doc_type,owner,"
                      "target_user,visibility,old_visibility,doc_id"])


_report("shared_outside", "Drive sharing", "Files shared outside your domains",
        "Files shared with people outside your own domains, and files "
        "opened to 'anyone with the link' or the whole web - who shared "
        "what, with whom. Catches typos in recipients' addresses too.",
        "Files shared outside",
        [_PERIOD_OPT,
         _opt("own", "Your own domains (sub-domains included), e.g. "
              "example.org", "domains", ""),
         _opt("ignore", "Partner domains to ignore (optional)",
              "domains_opt", ""),
         _opt("links", "Include files opened to 'anyone with the link'",
              "bool", True)],
        _build_shared_outside)

_report("default_photo", "Accounts", "Accounts using the default profile picture",
        "Active accounts that still show Google's default picture (the "
        "letter). One lookup per account, so a whole domain takes a while - "
        "limit it to an OU (sub-OUs included) if you like.",
        "Default profile picture",
        [_opt("ou", "Only this OU and its sub-OUs, e.g. /Staff (blank = all "
              "active accounts)", "ou", "")],
        _build_photo)


def _build_cros(values):
    n = values["days"]
    argv = ["config", "timezone", "local", "redirect", "csv",
            _out("chromebooks-not-synced-" + str(n) + "-days.csv"),
            "print", "cros", "query", "status:provisioned sync:..#querytime1#",
            "querytime1", "-" + str(n) + "d", "fields",
            "deviceid,serialnumber,orgunitpath,lastsync,model,annotateduser,"
            "annotatedassetid,annotatedlocation"]
    return [("gam", argv)], "RUNDAY"


_report("old_chromebooks", "Devices", "Chromebooks not used lately",
        "Provisioned Chromebooks that have not synced with Google for N "
        "days - lost, broken, or sitting in a closet.",
        "Chromebooks not synced",
        [_opt("days", "Not synced for at least this many days", "int", 180,
              1, 3650)],
        _build_cros)

# Every report can ALSO update one tab of an existing Google Sheet (verified
# live: 'redirect csv <file> todrive tdfileid <id> tdretaintitle true tdsheet
# <tab> tdupdatesheet true ... tdlocalcopy true' writes the local CSV first,
# then replaces that tab; without tdlocalcopy GAM skips the local file).
SHEET_OPTS = [
    _opt("sheet_id", "Also update a Google Sheet - link or file ID (optional)",
         "sheet", ""),
    _opt("sheet_tab", "Tab name (blank = the report's name)", "tab", ""),
]
for _r in REPORTS:
    _r["options"] = list(_r["options"]) + SHEET_OPTS

REPORT_BY_KEY = {r["key"]: r for r in REPORTS}
ALERT_KEYS = [r["key"] for r in REPORTS if r["alert"]]

EMAIL_WHEN = ["Never", "Every run", "Only when an alert report finds something"]
_EMAIL_RE = re.compile(r"[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")
ATTACH_LIMIT = 5000000          # bytes; bigger CSVs are not attached


def sheet_id_from(text):
    # Accepts a Google Sheets link (https://docs.google.com/spreadsheets/d/
    # <ID>/edit...) or a bare file ID; returns the ID, "" for blank, or
    # raises ValueError. IDs are letters, digits, - and _ only.
    text = (text or "").strip()
    if not text:
        return ""
    found = re.search(r"/d/([A-Za-z0-9_-]{20,})", text)
    if found:
        return found.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", text):
        return text
    raise ValueError("paste the sheet's link or its file ID (the long part "
                     "of the link between /d/ and /edit).")


def clean_emails(text, what, allow_blank=True):
    # A comma/space separated list of plain email addresses -> "a@x,b@y".
    items = [e for e in re.split(r"[\s,;]+", (text or "").strip()) if e]
    if not items and allow_blank:
        return ""
    if not items or not all(_EMAIL_RE.fullmatch(e) for e in items):
        raise ValueError(what + ": enter email addresses separated by commas "
                         "(plain addresses only, e.g. it@example.com).")
    return ",".join(items)


# ---- validation -----------------------------------------------------------------
def clean_values(report, raw):
    # Turns what the user typed/ticked into checked values; raises ValueError
    # with a plain message naming the report and option on anything invalid.
    # Every value that reaches a command is validated here, so nothing typed
    # can smuggle extra arguments or quotes into the script.
    out = {}
    for opt in report["options"]:
        value = raw.get(opt["key"], opt["default"])
        where = report["name"] + " - " + opt["label"] + ": "
        if opt["kind"] == "bool":
            out[opt["key"]] = bool(value)
        elif opt["kind"] == "int":
            text = str(value).strip()
            if not re.fullmatch(r"\d{1,6}", text) or not (
                    opt["lo"] <= int(text) <= opt["hi"]):
                raise ValueError(where + "enter a whole number from "
                                 + str(opt["lo"]) + " to " + str(opt["hi"]) + ".")
            out[opt["key"]] = int(text)
        elif opt["kind"] == "period":
            if value not in PERIOD_LABELS:
                raise ValueError(where + "choose a period from the list.")
            out[opt["key"]] = value
        elif opt["kind"] == "countries":
            codes = [c.upper() for c in re.split(r"[\s,;]+", str(value)) if c]
            if not codes or not all(re.fullmatch(r"[A-Z]{2}", c) for c in codes):
                raise ValueError(where + "use 2-letter country codes separated "
                                 "by spaces or commas, e.g. US MX CA.")
            out[opt["key"]] = sorted(set(codes))
        elif opt["kind"] == "sheet":
            try:
                out[opt["key"]] = sheet_id_from(value)
            except ValueError as exc:
                raise ValueError(where + str(exc))
        elif opt["kind"] in ("domains", "domains_opt"):
            names = [d.lower() for d in re.split(r"[\s,;]+", str(value or "")) if d]
            if opt["kind"] == "domains" and not names:
                raise ValueError(where + "enter at least one domain, e.g. "
                                 "example.org")
            if not all(re.fullmatch(r"([a-z0-9-]+\.)+[a-z]{2,63}", d)
                       and len(d) <= 253 for d in names):
                raise ValueError(where + "enter domain names only (e.g. "
                                 "example.org), separated by spaces or commas.")
            out[opt["key"]] = sorted(set(names))
        elif opt["kind"] == "ou":
            ou = str(value or "").strip()
            if ou and (not ou.startswith("/") or len(ou) > 500 or '"' in ou
                       or any(ord(ch) < 32 or ord(ch) > 126 for ch in ou)):
                raise ValueError(where + "enter an OU path that starts with "
                                 "/ (e.g. /Staff), or leave it blank.")
            out[opt["key"]] = ou
        elif opt["kind"] == "tab":
            tab = str(value or "").strip()
            if len(tab) > 100 or '"' in tab or any(
                    ord(ch) < 32 or ord(ch) > 126 for ch in tab):
                raise ValueError(where + "use up to 100 plain characters, no "
                                 "double quotes.")
            out[opt["key"]] = tab
    return out


def _clean_folder(path):
    # Output folder: blank = a Reports folder next to the script. Otherwise
    # plain ASCII, no quotes, no line breaks, no trailing slash.
    path = (path or "").strip()
    if not path:
        return ""
    _check_script_path("The output folder", path)
    if '"' in path:
        raise ValueError("The output folder cannot contain a double quote.")
    return path.rstrip("\\/") or path


# ---- script generation ----------------------------------------------------------
# PowerShell used by the script. It reads every path from environment
# variables (GG_IN, GG_OUT, GG_ROOT...) that the batch file sets, so no folder
# name is ever pasted into PowerShell code. It contains no double quote and
# no percent sign, so it sits safely inside one quoted cmd.exe argument.
_PS_SPLIT = (
    "$ErrorActionPreference='Stop';"
    "$rows=@(Import-Csv -LiteralPath $env:GG_IN);"
    "if($env:GG_AUTO -ne '1'){$rows=@($rows|Where-Object{$_.'actor.email'})};"
    "$groups=@($rows|Group-Object -Property {if($_.'actor.email'){$_.'actor.email'}"
    "else{'automatic-'+$_.'actor.key'}});"
    "foreach($grp in $groups){"
    "$n=$grp.Name -replace '[^A-Za-z0-9@._-]','_';"
    "if($n.Length -gt 100){$n=$n.Substring(0,100)};"
    "$grp.Group|Export-Csv -LiteralPath (Join-Path -Path $env:GG_OUT -ChildPath ($n+'.csv'))"
    " -NoTypeInformation -Encoding UTF8};"
    "Write-Output ('Split '+$rows.Count+' events into '+$groups.Count+' per-admin files')"
)

_PS_CLEANUP = (
    "$ErrorActionPreference='Stop';"
    "$cut=(Get-Date).Date.AddDays(-[int]$env:GG_KEEP);"
    "if(Test-Path -LiteralPath $env:GG_ROOT){"
    "Get-ChildItem -LiteralPath $env:GG_ROOT -Directory|"
    "Where-Object{$_.Name -match '^[0-9]{2}-[0-9]{2}-[0-9]{4}$'}|ForEach-Object{"
    "$d=$null;try{$d=[datetime]::ParseExact($_.Name,'MM-dd-yyyy',$null)}catch{};"
    "if($d -ne $null -and $d -lt $cut){"
    "Remove-Item -LiteralPath $_.FullName -Recurse -Force;"
    "Write-Output ('Removed old report folder '+$_.FullName)}}}"
)

# Stores in N the number of data rows in the CSV named by GG_IN (0 if the
# file is missing or unreadable).
_PS_COUNT = ("FOR /F \"usebackq delims=\" %%C IN (`powershell -NoProfile -Command "
             "\"try{if(Test-Path -LiteralPath $env:GG_IN){@(Import-Csv -LiteralPath "
             "$env:GG_IN).Count}else{0}}catch{0}\"`) DO SET \"N=%%C\"")

_PS_DATES = ("FOR /F \"usebackq delims=\" %%D IN (`powershell -NoProfile -Command "
             "\"(Get-Date).AddDays({0}).ToString('MM-dd-yyyy')\"`) DO SET \"{1}=%%D\"")

SETTINGS_TAG = ":: GAMGUI-REPORT-SETTINGS: "
SH_SETTINGS_TAG = "# GAMGUI-REPORT-SETTINGS: "


def _bat_args(argv):
    # The argument text for one gam line. Ordinary arguments go through the
    # same proven escaping as Save as script; they are checked to hold no
    # double quote, so cmd.exe's quote state is closed between arguments.
    # BatPath arguments are written as "...%VAR%..." so the folder is filled
    # in at run time (inside quotes, so & ( ) etc. in it are harmless).
    parts = []
    for arg in argv:
        if isinstance(arg, BatPath):
            if not re.fullmatch(r"(%[A-Z]+%|[A-Za-z0-9 ._\-\\])+", arg) \
                    or arg.endswith("\\"):
                raise ValueError("internal: unsafe path argument " + arg)
            parts.append('"' + arg + '"')
        else:
            if '"' in arg:
                raise ValueError("internal: a report argument contains a quote")
            parts.append(cmd_line_for_bat([arg]))
    return " ".join(parts)


def settings_blob(selection, out_root, keep_days, extra=None):
    # The builder's choices, stored in the script as one base64 line so
    # "Open a saved report script..." can load them back for editing.
    # 'extra' holds the email / Google Sheet account settings.
    data = {"v": 1, "reports": selection, "out_root": out_root,
            "keep_days": keep_days}
    data.update(extra or {})
    raw = json.dumps(data, sort_keys=True).encode("ascii")
    return base64.b64encode(raw).decode("ascii")


def read_settings(script_text):
    # The reverse of settings_blob; returns the dict or raises ValueError.
    for line in script_text.splitlines():
        tag = next((t for t in (SETTINGS_TAG, SH_SETTINGS_TAG)
                    if line.startswith(t)), None)
        if tag:
            try:
                data = json.loads(base64.b64decode(line[len(tag):].strip()))
            except (ValueError, TypeError) as exc:
                raise ValueError("The saved settings line is damaged: " + str(exc))
            if not isinstance(data, dict) or data.get("v") != 1:
                raise ValueError("Unrecognized report settings version.")
            return data
    raise ValueError("This file was not made by the GAMGUI Report builder.")


# Word options of 'redirect csv <file> ...' that may sit between the file
# name and 'todrive' (see the wiki's Meta-Commands-and-File-Redirection).
_REDIRECT_OPTS = ("multiprocess", "append", "noheader")


def _todrive_args(sheet_id, tab, sheet_user):
    # GAM arguments that send a report to one tab of an existing Google
    # Sheet AND keep the local CSV (tdlocalcopy - verified in GAM's source:
    # with todrive and no tdlocalcopy, no local file is written). No browser
    # window and no "file uploaded" email, since this runs unattended.
    args = ["todrive", "tdfileid", sheet_id, "tdretaintitle", "true",
            "tdsheet", tab, "tdupdatesheet", "true", "tdnobrowser", "true",
            "tdnoemail", "true", "tdlocalcopy", "true"]
    if sheet_user:
        args += ["tduser", sheet_user]
    return args


def _prepare(selection, gam_path, script_name, out_root, keep_days, cfg_dir,
             sheet_user, email_to, email_when, email_attach, email_from):
    # Validation and report building shared by the .bat and .sh generators.
    # Returns a dict of checked values; raises ValueError with a plain
    # message on any invalid choice.
    if not selection:
        raise ValueError("Tick at least one report.")
    _check_script_path("The gam path", gam_path)
    _check_script_path("The GAM config folder", cfg_dir)
    out_root = _clean_folder(out_root)
    keep = str(keep_days).strip() or "0"
    if not re.fullmatch(r"\d{1,4}", keep):
        raise ValueError("Keep report folders: enter a number of days "
                         "(0 = keep everything).")
    keep = int(keep)
    sheet_user = clean_emails(sheet_user, "Google account for Sheets")
    email_from = clean_emails(email_from, "Send email from")
    if "," in sheet_user or "," in email_from:
        raise ValueError("Google account for Sheets / Send email from: enter "
                         "ONE address.")
    if email_when not in EMAIL_WHEN:
        raise ValueError("Choose when to send the email.")
    emailing = email_when != EMAIL_WHEN[0]
    email_to = clean_emails(email_to, "Email the summary to",
                            allow_blank=not emailing)
    name = _safe_text(script_name) or "gam-reports"
    chosen = []
    for key, raw in selection:
        report = REPORT_BY_KEY.get(key)
        if report is None:
            raise ValueError("Unknown report: " + str(key))
        values = clean_values(report, raw or {})
        steps, datevar = report["build"](values)
        # The report's main CSV = the first %OUT% file its first GAM step
        # writes. It is the one counted, uploaded, and attached.
        first = steps[0][1]
        at = [i for i, a in enumerate(first) if isinstance(a, BatPath)][0]
        main = first[at][len("%OUT%\\"):]
        if values.get("sheet_id"):
            tab = values.get("sheet_tab") or report["folder"]
            # GAM: in 'redirect csv <file> [multiprocess] [append] ...
            # [todrive ...]' the todrive part must come LAST, so skip past
            # any redirect options that follow the file name.
            end = at + 1
            while end < len(first) and first[end] in _REDIRECT_OPTS:
                end += 1
            first = first[:end] + _todrive_args(
                values["sheet_id"], tab, sheet_user) + first[end:]
            steps = [("gam", first)] + list(steps[1:])
        chosen.append((report, values, steps, datevar, main))
    stored = [[k, clean_values(REPORT_BY_KEY[k], r or {})] for k, r in selection]
    names = [c[0]["name"] for c in chosen]
    extra = {"sheet_user": sheet_user, "email_to": email_to,
             "email_when": email_when, "email_attach": bool(email_attach),
             "email_from": email_from}
    return {"chosen": chosen, "stored": stored, "names": names,
            "extra": extra, "name": name, "keep": keep, "out_root": out_root,
            "emailing": emailing, "email_to": email_to,
            "email_from": email_from, "email_when": email_when,
            "email_attach": bool(email_attach)}


def make_report_script(selection, gam_path, script_name, version, today,
                       out_root="", keep_days=0, cfg_dir="", sheet_user="",
                       email_to="", email_when="Never", email_attach=False,
                       email_from=""):
    # selection: list of (report key, raw option values) in the order to run.
    # Returns the text of a Windows batch file (CRLF). Raises ValueError with
    # a plain message on any invalid choice.
    #   sheet_user  : account that can edit the Sheets (blank = GAM's admin)
    #   email_to    : summary recipients; email_when one of EMAIL_WHEN
    #   email_attach: attach each report's CSV when it is 5 MB or less
    #   email_from  : optional sender (blank = GAM's admin account)
    p = _prepare(selection, gam_path, script_name, out_root, keep_days,
                 cfg_dir, sheet_user, email_to, email_when, email_attach,
                 email_from)
    chosen, stored, names, extra = p["chosen"], p["stored"], p["names"], p["extra"]
    name, keep, out_root, emailing = p["name"], p["keep"], p["out_root"], p["emailing"]
    email_to, email_from = p["email_to"], p["email_from"]

    L = [
        "@ECHO OFF",
        "SETLOCAL ENABLEEXTENSIONS",
        ":: " + "=" * 77,
        ":: Script:   " + name + ".bat",
        ":: Author:   Generated by the GAMGUI " + version + " Report builder",
        ":: Created:  " + today,
        ":: Modified: " + today,
        ":: Version:  1.0",
        "::",
        ":: Purpose:",
        "::   Runs these Google Workspace reports with GAM and saves each one as",
        "::   CSV files in its own dated folder:",
    ]
    L += ["::     - " + _safe_text(n) for n in names]
    L += [
        "::",
        ":: Usage:",
        "::   " + name + ".bat   (double-click, or schedule it daily in Task Scheduler)",
        "::",
        ":: Requirements:",
        "::   GAM7 installed and authorized for the account that runs this script",
        "::   (for a scheduled task: the task's 'Run as' user must be able to read",
        "::   the GAM config folder). Windows PowerShell (built into Windows).",
        "::",
        ":: Notes:",
        "::   - Output: OUTROOT\\report name\\MM-DD-YYYY\\*.csv. 'Yesterday'",
        "::     reports are filed under yesterday's date; others under today's.",
        "::   - The reports contain staff/student email addresses and sign-in",
        "::     details: keep OUTROOT in a folder only IT can read.",
        "::   - Log: Logs\\" + name + ".log next to this script (start/end, GAM output).",
        "::   - Exit code 0 = every report worked; 1 = at least one failed (see log).",
        "::   - A summary with each report's row count is written to",
        "::     Logs\\" + name + "-summary.txt (and emailed, if chosen in the builder).",
        "::   - Open this file in GAMGUI (Reports > Report builder > Open a saved",
        "::     report script...) to change it; the line below holds its settings.",
        ":: " + "=" * 77,
        SETTINGS_TAG + settings_blob(stored, out_root, keep, extra),
        "",
        ":INIT",
        ":: Where gam.exe lives - change this if GAM is installed elsewhere.",
        'SET "GAM=' + gam_path.replace("%", "%%") + '"',
    ]
    if cfg_dir:
        L += [
            ":: GAM's config folder (the folder holding gam.cfg), as set in",
            ":: GAMGUI. Delete this line to use GAM's own default instead.",
            'SET "GAMCFGDIR=' + cfg_dir.replace("%", "%%") + '"',
        ]
    L += [
        ":: Where the reports go. Blank in the builder = a Reports folder next",
        ":: to this script.",
        ('SET "OUTROOT=' + out_root.replace("%", "%%") + '"') if out_root
        else 'SET "OUTROOT=%~dp0Reports"',
        ":: Dated report folders older than this many days are deleted at the",
        ":: end of each run (only folders named MM-DD-YYYY inside this script's",
        ":: own report folders). 0 = keep everything.",
        'SET "KEEPDAYS=' + str(keep) + '"',
        ":: Log folder and file, kept next to this script.",
        'SET "LOGDIR=%~dp0Logs"',
        'SET "LOG=%LOGDIR%\\' + name + '.log"',
        'IF NOT EXIST "%LOGDIR%" MKDIR "%LOGDIR%"',
        ":: Stop with a clear message if gam.exe is missing (GOTO, not an IF",
        ":: ( ... ) block, so a ) in a path cannot end the block early).",
        'IF NOT EXIST "%GAM%" GOTO :NOGAM',
    ]
    if cfg_dir:
        L += ['IF NOT EXIST "%GAMCFGDIR%\\gam.cfg" GOTO :NOCFG']
    L += [
        ":: Today's and yesterday's dates as MM-DD-YYYY for the folder names,",
        ":: from PowerShell so they do not depend on the PC's regional settings.",
        _PS_DATES.format("0", "RUNDAY"),
        _PS_DATES.format("-1", "YDAY"),
        'IF "%YDAY%"=="" GOTO :NODATE',
        ":: Counts reports that fail; the script's exit code is 1 if any did.",
        'SET "FAILS=0"',
        ":: Rows found by the alert reports (leaked passwords, sign-ins from",
        ":: abroad, ...) and the list of CSVs to attach to the email.",
        'SET "ALERTS=0"',
        'SET "ATTACH="',
        ":: This run's summary: one line per report with its row count.",
        'SET "SUMMARY=%LOGDIR%\\' + name + '-summary.txt"',
        '>"%SUMMARY%" ECHO GAMGUI report run on %RUNDAY% - ' + name + '.bat',
        '>>"%SUMMARY%" ECHO Reports folder: "%OUTROOT%"',
        '>>"%SUMMARY%" ECHO.',
        "",
        ":MAIN",
        "CALL :STAMP",
        '>>"%LOG%" ECHO [%STAMP%] ===== START: ' + str(len(chosen)) + " report(s)",
    ]
    for index, (report, values, steps, datevar, main) in enumerate(chosen, 1):
        title = _safe_text(report["name"])
        L += [
            "",
            ":: " + "-" * 77,
            ":: Report " + str(index) + ": " + title,
            ":: " + "-" * 77,
            'SET "OUT=%OUTROOT%\\' + report["folder"] + "\\%" + datevar + '%"',
            'IF NOT EXIST "%OUT%" MKDIR "%OUT%"',
            "CALL :STAMP",
            '>>"%LOG%" ECHO [%STAMP%] ' + title + ' -^> "%OUT%"',
        ]
        for step in steps:
            if step[0] == "gam":
                L += [
                    ":: The log redirection comes first on the line on purpose.",
                    '>>"%LOG%" 2>&1 "%GAM%" ' + _bat_args(step[1]),
                    'SET "RC=%ERRORLEVEL%"',
                    'IF NOT "%RC%"=="0" CALL :FAILED "' + title + '"',
                ]
            else:
                _kind, infile, automatic = step
                L += [
                    ":: Split the day's file into one CSV per admin (PowerShell",
                    ":: reads the paths from these variables).",
                    'SET "GG_IN=%OUT%\\' + infile + '"',
                    'SET "GG_OUT=%OUT%"',
                    'SET "GG_AUTO=' + ("1" if automatic else "0") + '"',
                    ":: Only when GAM succeeded (RC=0) and wrote the file.",
                    'IF "%RC%"=="0" IF EXIST "%GG_IN%" >>"%LOG%" 2>&1 powershell '
                    '-NoProfile -ExecutionPolicy Bypass -Command "' + _PS_SPLIT + '"',
                    'IF "%RC%"=="0" IF ERRORLEVEL 1 CALL :FAILED "' + title + ' (split)"',
                ]
        L += [
            ":: Count the report's rows (Import-Csv, so a value with a line",
            ":: break still counts once) for the log, summary and email.",
            'SET "N=0"',
            'SET "GG_IN=%OUT%\\' + main + '"',
            'IF "%RC%"=="0" ' + _PS_COUNT,
            'IF "%RC%"=="0" >>"%LOG%" ECHO     %N% rows in ' + main,
            'IF "%RC%"=="0" >>"%SUMMARY%" ECHO ' + title + ': %N% rows - "%OUT%"',
            'IF NOT "%RC%"=="0" >>"%SUMMARY%" ECHO ' + title + ': FAILED - see the log',
        ]
        if report["alert"]:
            L += ['IF "%RC%"=="0" SET /A ALERTS+=N']
        if emailing and email_attach:
            L += [
                ":: Attach the CSV to the email if it has rows and is 5 MB or less.",
                'IF "%RC%"=="0" IF NOT "%N%"=="0" IF EXIST "%GG_IN%" FOR %%F IN ("%GG_IN%") DO '
                'IF %%~zF GTR 0 IF %%~zF LEQ ' + str(ATTACH_LIMIT)
                + ' SET ATTACH=%ATTACH% attach "%%~fF"',
                'IF "%RC%"=="0" IF EXIST "%GG_IN%" FOR %%F IN ("%GG_IN%") DO '
                'IF %%~zF GTR ' + str(ATTACH_LIMIT)
                + ' >>"%SUMMARY%" ECHO     (not attached: larger than 5 MB)',
            ]
    L += [
        "",
        ":: " + "-" * 77,
        ":: Clean-up: delete dated folders older than KEEPDAYS (if not 0).",
        ":: " + "-" * 77,
        'IF "%KEEPDAYS%"=="0" GOTO :EMAIL',
        'SET "GG_KEEP=%KEEPDAYS%"',
    ]
    for folder in sorted(set(c[0]["folder"] for c in chosen)):
        L += [
            'SET "GG_ROOT=%OUTROOT%\\' + folder + '"',
            '>>"%LOG%" 2>&1 powershell -NoProfile -ExecutionPolicy Bypass '
            '-Command "' + _PS_CLEANUP + '"',
            'IF ERRORLEVEL 1 CALL :FAILED "clean-up of ' + folder + '"',
        ]
    L += ["", ":EMAIL"]
    if emailing:
        send = cmd_line_for_bat(["sendemail", email_to]
                                + (["from", email_from] if email_from else []))
        L += [
            ":: " + "-" * 77,
            ":: Email the summary (" + email_when + ").",
            ":: " + "-" * 77,
            '>>"%SUMMARY%" ECHO.',
            '>>"%SUMMARY%" ECHO Failed steps: %FAILS%. Log: "%LOG%"',
        ]
        if email_when == EMAIL_WHEN[2]:
            L += [
                ":: No alert rows and nothing failed: nothing to report.",
                'IF "%ALERTS%"=="0" IF "%FAILS%"=="0" >>"%LOG%" ECHO No alert rows and no failures - no email sent.',
                'IF "%ALERTS%"=="0" IF "%FAILS%"=="0" GOTO :DONE',
            ]
        L += [
            "CALL :STAMP",
            '>>"%LOG%" ECHO [%STAMP%] Emailing the summary to ' + email_to,
            ":: 'file' = the message body; ATTACH holds attach \"...csv\" pairs.",
            '>>"%LOG%" 2>&1 "%GAM%" ' + send + ' subject "GAMGUI reports %RUNDAY%: '
            '%ALERTS% alert rows, %FAILS% failed steps" file "%SUMMARY%" %ATTACH%',
            'IF ERRORLEVEL 1 CALL :FAILED "email"',
        ]
    L += [
        "",
        ":DONE",
        "CALL :STAMP",
        '>>"%LOG%" ECHO [%STAMP%] ===== END: %FAILS% report step(s) failed',
        'IF NOT "%FAILS%"=="0" ECHO %FAILS% report step(s) FAILED - see "%LOG%"',
        'IF NOT "%FAILS%"=="0" ENDLOCAL & EXIT /B 1',
        'ECHO Done - reports are in "%OUTROOT%"',
        "ENDLOCAL & EXIT /B 0",
        "",
        ":FAILED",
        ":: Records a failed step and keeps going with the other reports.",
        'SET /A FAILS+=1',
        "CALL :STAMP",
        '>>"%LOG%" ECHO [%STAMP%] FAILED: %~1',
        "GOTO :EOF",
        "",
        ":NOGAM",
        'ECHO ERROR: gam.exe not found at "%GAM%" - edit the GAM line in this script.',
        "CALL :STAMP",
        '>>"%LOG%" ECHO [%STAMP%] ERROR gam.exe not found at "%GAM%"',
        "ENDLOCAL & EXIT /B 2",
        "",
    ]
    if cfg_dir:
        L += [
            ":NOCFG",
            'ECHO ERROR: gam.cfg not found in "%GAMCFGDIR%" - edit the GAMCFGDIR line in this script.',
            "CALL :STAMP",
            '>>"%LOG%" ECHO [%STAMP%] ERROR gam.cfg not found in "%GAMCFGDIR%"',
            "ENDLOCAL & EXIT /B 3",
            "",
        ]
    L += [
        ":NODATE",
        "ECHO ERROR: could not read today's date from PowerShell.",
        "CALL :STAMP",
        '>>"%LOG%" ECHO [%STAMP%] ERROR could not read the date from PowerShell',
        "ENDLOCAL & EXIT /B 4",
        "",
        ":STAMP",
        ":: Sets STAMP to the current date/time as MM-DD-YYYY HH:MM:SS.",
        "FOR /F \"usebackq delims=\" %%T IN (`powershell -NoProfile -Command \"Get-Date -Format 'MM-dd-yyyy HH:mm:ss'\"`) DO SET \"STAMP=%%T\"",
        "GOTO :EOF",
        "",
    ]
    for line in L:
        if any(ord(ch) > 126 for ch in line):
            raise ValueError("internal: non-ASCII text in the script")
    return "\r\n".join(L)


# =============================================================================
# macOS / Linux: the same reports as a bash script (v2.55)
# =============================================================================
# Written for what a stock Mac has: bash 3.2 (no associative arrays, no
# mapfile, no 'set -u' - bash 3.2 treats an empty array as unbound), POSIX awk
# (macOS ships the one-true-awk, not gawk), and both BSD date (macOS: -v) and
# GNU date (Linux: -d). No PowerShell, Python, or other extras.

# awk: data rows in a CSV (a quoted field may hold a line break, so a record
# ends only where the running count of double quotes is even).
_AWK_COUNT = ('{ q += gsub(/"/, "\\""); if (q % 2 == 0) { r++; q = 0 } } '
              'END { if (r > 0) r--; print r + 0 }')

# awk: split the admin log into one CSV per admin. Parses quoted CSV fields
# by hand (POSIX awk has no CSV mode), finds actor.email / actor.key in the
# header, and copies each record UNCHANGED into <email>.csv - or into
# automatic-<key>.csv when there is no admin email (skipped if auto != 1).
# Names get the same cleanup as the Windows version. Files are closed after
# every write so any number of admins works within awk's open-file limit.
_AWK_SPLIT = (
    'function parse(s,   i, c, f, inq, n) { split("", F); n = 0; f = ""; inq = 0; '
    'for (i = 1; i <= length(s); i++) { c = substr(s, i, 1); '
    'if (inq) { if (c == "\\"") { if (substr(s, i + 1, 1) == "\\"") '
    '{ f = f "\\""; i++ } else inq = 0 } else f = f c } '
    'else if (c == "\\"") inq = 1; else if (c == ",") { F[++n] = f; f = "" } '
    'else f = f c } F[++n] = f; return n } '
    '{ line = $0; q += gsub(/"/, "\\"", line); '
    'rec = pend ? rec "\\n" $0 : $0; pend = 1; if (q % 2) next; q = 0; pend = 0; '
    'if (!seenhdr) { seenhdr = 1; header = rec; n = parse(rec); '
    'for (i = 1; i <= n; i++) { if (F[i] == "actor.email") ce = i; '
    'if (F[i] == "actor.key") ck = i } next } '
    'n = parse(rec); key = (ce && F[ce] != "") ? F[ce] : ""; '
    'if (key == "") { if (auto != "1") next; '
    'key = "automatic-" ((ck && F[ck] != "") ? F[ck] : "unknown") } '
    'gsub(/[^A-Za-z0-9@._-]/, "_", key); key = substr(key, 1, 100); '
    'file = outdir "/" key ".csv"; '
    'if (!(file in made)) { made[file] = 1; files++; print header > file; close(file) } '
    'print rec >> file; close(file); total++ } '
    'END { printf "Split %d events into %d per-admin files\\n", total, files }'
)


def _sh_arg(arg):
    # One argument for a bash command line. A BatPath (%OUT%\file.csv)
    # becomes "${OUT}/file.csv" - double quotes so the folder is filled in
    # at run time and its spaces are safe. Everything else is single-quoted
    # by shlex, so the shell changes nothing.
    import shlex
    if isinstance(arg, BatPath):
        text = re.sub(r"%([A-Z]+)%", r"${\1}", arg).replace("\\", "/")
        if not re.fullmatch(r"(\$\{[A-Z]+\}|[A-Za-z0-9 ._\-/])+", text):
            raise ValueError("internal: unsafe path argument " + arg)
        return '"' + text + '"'
    return shlex.quote(arg)


def _sh_dq_text(text):
    # Escapes text for a bash double-quoted string (\ " $ ` are special).
    for ch in ("\\", '"', "$", "`"):
        text = text.replace(ch, "\\" + ch)
    return text


def make_report_sh(selection, gam_path, script_name, version, today,
                   out_root="", keep_days=0, cfg_dir="", sheet_user="",
                   email_to="", email_when="Never", email_attach=False,
                   email_from=""):
    # The macOS / Linux twin of make_report_script: same reports, folders,
    # Sheets upload, summary, email and clean-up, as a bash script (LF line
    # endings) for cron. Same arguments; raises ValueError the same way.
    p = _prepare(selection, gam_path, script_name, out_root, keep_days,
                 cfg_dir, sheet_user, email_to, email_when, email_attach,
                 email_from)
    chosen, stored, names, extra = p["chosen"], p["stored"], p["names"], p["extra"]
    name, keep, out_root, emailing = p["name"], p["keep"], p["out_root"], p["emailing"]
    email_to, email_from = p["email_to"], p["email_from"]
    out_root = out_root.replace("\\", "/") if out_root else ""
    q = _sh_dq_text
    L = [
        "#!/usr/bin/env bash",
        "# " + "=" * 77,
        "# Script:   " + name + ".sh",
        "# Author:   Generated by the GAMGUI " + version + " Report builder",
        "# Created:  " + today,
        "# Version:  1.0",
        "#",
        "# Purpose:",
        "#   Runs these Google Workspace reports with GAM and saves each one as",
        "#   CSV files in its own dated folder:",
    ]
    L += ["#     - " + _safe_text(n) for n in names]
    L += [
        "#",
        "# Usage:",
        "#   ./" + name + ".sh   (or schedule it daily with cron, e.g. crontab -e:",
        "#   0 1 * * * '/full/path/" + name + ".sh')",
        "#",
        "# Requirements:",
        "#   GAM7 installed and authorized for the account that runs this script.",
        "#   bash, awk and date - all built into macOS and Linux.",
        "#",
        "# Notes:",
        "#   - Output: OUTROOT/report name/MM-DD-YYYY/*.csv. 'Yesterday' reports",
        "#     are filed under yesterday's date; others under today's.",
        "#   - The reports contain staff/student email addresses and sign-in",
        "#     details: keep OUTROOT in a folder only IT can read.",
        "#   - Log: Logs/" + name + ".log next to this script; summary with each",
        "#     report's row count: Logs/" + name + "-summary.txt (and emailed, if",
        "#     chosen in the builder).",
        "#   - Exit code 0 = every report worked; 1 = at least one failed (see log);",
        "#     2 = gam missing; 3 = gam.cfg missing; 4 = could not read the date.",
        "#   - Open this file in GAMGUI (Reports > Report builder > Open a saved",
        "#     report script...) to change it; the line below holds its settings.",
        "# " + "=" * 77,
        SH_SETTINGS_TAG + settings_blob(stored, out_root, keep, extra),
        "",
        "# Where gam lives - change this if GAM is installed elsewhere.",
        'GAM="' + q(gam_path) + '"',
    ]
    if cfg_dir:
        L += [
            "# GAM's config folder (the folder holding gam.cfg), as set in GAMGUI.",
            "# Delete this line to use GAM's own default instead.",
            'export GAMCFGDIR="' + q(cfg_dir) + '"',
        ]
    L += [
        'SCRIPTDIR="$(cd "$(dirname "$0")" && pwd)"',
        "# Where the reports go (blank in the builder = Reports next to this script).",
        ('OUTROOT="' + q(out_root) + '"') if out_root
        else 'OUTROOT="$SCRIPTDIR/Reports"',
        "# Dated report folders older than this many days are deleted at the end",
        "# of each run (only MM-DD-YYYY folders inside this script's own report",
        "# folders). 0 = keep everything.",
        "KEEPDAYS=" + str(keep),
        'LOGDIR="$SCRIPTDIR/Logs"',
        'mkdir -p "$LOGDIR"',
        'LOG="$LOGDIR/' + name + '.log"',
        'SUMMARY="$LOGDIR/' + name + '-summary.txt"',
        "",
        "stamp() { date '+%m-%d-%Y %H:%M:%S'; }",
        'log() { echo "[$(stamp)] $*" >> "$LOG"; }',
        "# A failed step is logged and counted; the other reports still run.",
        'failed() { FAILS=$((FAILS + 1)); log "FAILED: $1"; }',
        "# A date N days from today in a given format: GNU date (Linux) first,",
        "# then BSD date (macOS). N must carry its sign: +0, -1, -30.",
        'day_offset() { date -d "$1 days" "+$2" 2>/dev/null || date -v"$1"d "+$2"; }',
        "# Data rows in a CSV (0 if it is missing).",
        "csv_rows() { [ -f \"$1\" ] || { echo 0; return; }; awk '" + _AWK_COUNT
        + "' \"$1\"; }",
        "# One CSV per admin: split_admins <all.csv> <folder> <include automatic 1/0>",
        "split_admins() { awk -v outdir=\"$2\" -v auto=\"$3\" '" + _AWK_SPLIT
        + "' \"$1\"; }",
        "# Deletes MM-DD-YYYY folders older than KEEPDAYS in one report folder.",
        "# Folder names that are not real dates (e.g. 99-99-2020) are left alone.",
        "cleanup() {",
        '    [ -d "$1" ] || return 0',
        '    local cut d n m dd ymd',
        '    cut=$(day_offset "-$KEEPDAYS" %Y%m%d) || return 1',
        '    for d in "$1"/[0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]; do',
        '        [ -d "$d" ] || continue',
        '        n=$(basename "$d"); m=${n:0:2}; dd=${n:3:2}',
        '        [ "$m" -ge 1 ] && [ "$m" -le 12 ] && [ "$dd" -ge 1 ] && [ "$dd" -le 31 ] || continue',
        '        ymd="${n:6:4}${n:0:2}${n:3:2}"',
        '        if [ "$ymd" -lt "$cut" ]; then',
        '            rm -rf "$d" && echo "Removed old report folder $d"',
        "        fi",
        "    done",
        "}",
        "",
        'if [ ! -x "$GAM" ]; then',
        '    echo "ERROR: gam not found at $GAM - edit the GAM line in this script."',
        '    log "ERROR gam not found at $GAM"',
        "    exit 2",
        "fi",
    ]
    if cfg_dir:
        L += [
            'if [ ! -f "$GAMCFGDIR/gam.cfg" ]; then',
            '    echo "ERROR: gam.cfg not found in $GAMCFGDIR - edit the GAMCFGDIR line in this script."',
            '    log "ERROR gam.cfg not found in $GAMCFGDIR"',
            "    exit 3",
            "fi",
        ]
    L += [
        'RUNDAY=$(day_offset +0 %m-%d-%Y)',
        'YDAY=$(day_offset -1 %m-%d-%Y)',
        'if [ -z "$YDAY" ] || [ -z "$RUNDAY" ]; then',
        '    echo "ERROR: could not work out the date."; log "ERROR could not work out the date"; exit 4',
        "fi",
        "FAILS=0",
        "ALERTS=0",
        "ATTACH=()",
        'echo "GAMGUI report run on $RUNDAY - ' + name + '.sh" > "$SUMMARY"',
        'echo "Reports folder: \\"$OUTROOT\\"" >> "$SUMMARY"',
        'echo >> "$SUMMARY"',
        'log "===== START: ' + str(len(chosen)) + ' report(s)"',
    ]
    for index, (report, values, steps, datevar, main) in enumerate(chosen, 1):
        title = _safe_text(report["name"])
        L += [
            "",
            "# " + "-" * 77,
            "# Report " + str(index) + ": " + title,
            "# " + "-" * 77,
            'OUT="$OUTROOT/' + report["folder"] + '/$' + datevar + '"',
            'mkdir -p "$OUT"',
            'log "' + title + ' -> \\"$OUT\\""',
        ]
        for step in steps:
            if step[0] == "gam":
                L += [
                    '"$GAM" ' + " ".join(_sh_arg(a) for a in step[1])
                    + ' >> "$LOG" 2>&1',
                    "RC=$?",
                    '[ "$RC" -eq 0 ] || failed "' + title + '"',
                ]
            else:
                _kind, infile, automatic = step
                L += [
                    "# One CSV per admin (only when GAM succeeded and wrote the file).",
                    'if [ "$RC" -eq 0 ] && [ -f "$OUT/' + infile + '" ]; then',
                    '    split_admins "$OUT/' + infile + '" "$OUT" '
                    + ("1" if automatic else "0") + ' >> "$LOG" 2>&1 || failed "'
                    + title + ' (split)"',
                    "fi",
                ]
        L += [
            "N=0",
            'if [ "$RC" -eq 0 ]; then',
            '    N=$(csv_rows "$OUT/' + main + '")',
            '    echo "    $N rows in ' + main + '" >> "$LOG"',
            '    echo "' + title + ': $N rows - \\"$OUT\\"" >> "$SUMMARY"',
            "else",
            '    echo "' + title + ': FAILED - see the log" >> "$SUMMARY"',
            "fi",
        ]
        if report["alert"]:
            L += ['[ "$RC" -eq 0 ] && ALERTS=$((ALERTS + N))']
        if emailing and email_attach:
            L += [
                "# Attach the CSV to the email if it has rows and is 5 MB or less.",
                'if [ "$RC" -eq 0 ] && [ "$N" -gt 0 ]; then',
                '    SIZE=$(wc -c < "$OUT/' + main + '" | tr -d " ")',
                '    if [ "$SIZE" -le ' + str(ATTACH_LIMIT) + ' ]; then',
                '        ATTACH+=(attach "$OUT/' + main + '")',
                "    else",
                '        echo "    (not attached: larger than 5 MB)" >> "$SUMMARY"',
                "    fi",
                "fi",
            ]
    L += [
        "",
        "# Clean-up of dated folders older than KEEPDAYS (if not 0).",
        'if [ "$KEEPDAYS" -gt 0 ]; then',
    ]
    for folder in sorted(set(c[0]["folder"] for c in chosen)):
        L += ['    cleanup "$OUTROOT/' + folder + '" >> "$LOG" 2>&1 || failed "clean-up of '
              + folder + '"']
    L += ["fi"]
    if emailing:
        send = " ".join(_sh_arg(a) for a in ["sendemail", email_to]
                        + (["from", email_from] if email_from else []))
        mail = [
            '    log "Emailing the summary to ' + email_to + '"',
            '    "$GAM" ' + send + ' subject "GAMGUI reports $RUNDAY: $ALERTS alert rows, '
            '$FAILS failed steps" file "$SUMMARY" "${ATTACH[@]}" >> "$LOG" 2>&1 || failed "email"',
        ]
        L += [
            "",
            "# Email the summary (" + p["email_when"] + ").",
            'echo >> "$SUMMARY"',
            'echo "Failed steps: $FAILS. Log: \\"$LOG\\"" >> "$SUMMARY"',
        ]
        if p["email_when"] == EMAIL_WHEN[2]:
            L += ['if [ "$ALERTS" -eq 0 ] && [ "$FAILS" -eq 0 ]; then',
                  '    echo "No alert rows and no failures - no email sent." >> "$LOG"',
                  "else"] + mail + ["fi"]
        else:
            L += ["if true; then"] + mail + ["fi"]
    L += [
        "",
        'log "===== END: $FAILS report step(s) failed"',
        'if [ "$FAILS" -gt 0 ]; then',
        '    echo "$FAILS report step(s) FAILED - see \\"$LOG\\""',
        "    exit 1",
        "fi",
        'echo "Done - reports are in \\"$OUTROOT\\""',
        "exit 0",
        "",
    ]
    for line in L:
        if any(ord(ch) > 126 for ch in line):
            raise ValueError("internal: non-ASCII text in the script")
    return "\n".join(L)
