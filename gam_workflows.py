# =============================================================================
# gam_workflows.py - multi-step workflows shared by GAMGUI.py (the
# desktop app) and gam_web.py (the browser version) so both run the SAME
# gam commands in the SAME order (2.84; moved out of GamGui).
#
# Each workflow is two functions:
#   prepare_<name>(values, ...) -> plan
#       Checks the form's values and works out everything to do. Pure:
#       nothing is run. Raises ValueError with a plain-English message the
#       front end shows as an error.
#   run_<name>(io, plan)
#       Runs the plan through an "io" object (see WorkflowIO below). Called
#       from a background thread. An unexpected exception is left to the
#       caller, which shows it as WORKFLOW ERROR.
#
# A plan may carry "ask" (and "ask_title"): a yes / no question the front
# end asks BEFORE starting (the desktop shows a Yes / No box, the browser
# shows the same text with Yes / No buttons). Typed confirmations (DELETE,
# REMOVE, RESTORE) happen inside run_<name> through io.confirm.
#
# Workflows here (catalog workflow name -> functions):
#   transferdrive    Transfer My Drive to another user
#   shareddrive      Move a user's Drive INTO a NEW Shared Drive
#   sdscan           Find outside sharing on Shared Drives - CSV report
#   findsharing      Find sharing (Shared Drives or users' My Drive) - 2.87
#   sdeach           Shared Drive reports (counts, last change, files) - 2.87
#   sdwriters        Upgrade Shared Drive Contributors to Content managers
#                    (and put them back from its record file) - 2.87
#   sdroles          Shared Drive members by role, one row per drive - 2.87
#   sdexpand         Shared Drive members with groups expanded - 2.87
#   fileroles        Who has access to each file, by type and role - 2.88
#   groupcompare     Compare users (OU, query...) with a group's members - 2.88
#   oucounts         Users and Chromebooks per OU - 2.88
#   filterforwards   Gmail filters forwarding outside (find / delete) - 2.88
#   mailfroms        Messages per sender - 2.88
#   dupfiles         Duplicate files in My Drive (find / trash / untrash) - 2.88
#   drivedaily       Files created per day, by type - 2.88
#   driveaccess      Who appears on the most files - 2.88
#   browserexts      Chrome extensions on managed browsers - 2.89
#   lastgroupmail    Last message sent to each group - 2.89
#   eventattendees   Calendar events, one attendee per row - 2.89
#   oldcontacts      Old addresses in users' contacts (find / delete) - 2.89
#   vacationhtml     Plain-text vacation replies to HTML (find / convert /
#                    put back) - 2.89
#   sheetprotect     Protected ranges in Sheets (find / remove / put back /
#                    copy editors to a copy) - 2.89
#   csvtools         CSV tools: join, add OU / Chromebook ID, combine, count,
#                    dedupe, common values, JSON, one row per item - 2.89
#   sdempty          Empty a Shared Drive into its trash / put back - 2.89
#   iptrace          Trace an IP address through every log - 2.89
#   linkclicks       Who clicked a phishing link (Gmail log) - 2.89
#   lockmany         Lock out several compromised accounts - 2.89
#   foreignsignins   Sign-ins from outside your countries - 2.90
#   pirstart         Public Information Request: matter, searches, exports - 2.90
#   pircheck         Public Information Request: status + download - 2.90
#   pirclose         Public Information Request: remove holds, close - 2.90
#   pirlist          Public Information Request matters (CSV) - 2.90
#   unshare          Remove outside sharing listed in a report
#   reshare          Put back sharing from an undo file
#   drivewipe        PERMANENTLY delete a file from EVERYONE's Drive
#   removeextaccess  Remove access to an OUTSIDE file (not owned by us)
#   handoff          Staff departure hand-off (plan: gam_catalog.handoff_plan)
# Plus the run of "Set up an administrator" (new_admin_confirm /
# run_new_admin) - each front end has its own form for that one.
# =============================================================================

import collections
import csv
import datetime
import io as io_module          # "io" is the workflows' front-end object
import json                     # 2.89: csvtools' JSON output
import os
import re
import time

from gam_catalog import (
    unshare_plan, reshare_commands, UNDO_COLUMNS, RESHARE_NAMES, UNSHARE_MODES,
    sd_scan_steps, sd_build_report, SD_REPORT_COLUMNS, handoff_plan, HANDOFF_AFTER,
    gam_setup_steps, retire_plan, translate_license, grade_name, quote_if_needed,
    find_sharing_steps, FIND_WHAT, find_guests, find_disabled, find_only_disabled,
    sd_each_steps, SD_EACH,
    sd_writers_read_step, sd_writers_command, sd_writers_record,
    sd_writers_check_record, SD_WRITERS_COLUMNS, sd_roles_steps, sd_roles_report,
    sd_expand_steps, sd_expand_groups, sd_expand_report, SD_EXPAND_COLUMNS,
    file_roles_steps, file_roles_report, group_compare_steps, group_compare_report,
    GROUP_COMPARE_COLUMNS, ou_counts_steps, ou_counts_report, filter_forward_steps,
    filter_forward_rows, filter_forward_check_report, parse_domain_list,
    mail_froms_steps, mail_froms_report, dup_files_steps, dup_files_rows,
    dup_files_check_report, DUP_FILES_COLUMNS, drive_daily_steps, drive_daily_report,
    drive_access_steps, drive_access_report,
    browser_exts_steps, browser_exts_report, last_group_mail_steps,
    last_group_mail_report, LAST_GROUP_MAIL_COLUMNS, event_attendees_steps,
    event_attendees_report, old_contacts_steps, old_contacts_report,
    old_contacts_check_report, OLD_CONTACTS_COLUMNS, vacation_html_steps,
    vacation_html_report, vacation_html_check_report, VACATION_HTML_COLUMNS,
    sheet_protect_steps, sheet_protect_ranges, sheet_protect_check_report,
    sheet_protect_requests, sheet_copy_editor_requests, SHEET_PROTECT_COLUMNS,
    CSV_TOOLS, csv_join, csv_combine, csv_count, csv_dedupe, csv_common, csv_json_list,
    csv_explode, _redirect, CSV_LOOP_PLAIN, sd_empty_steps, sd_empty_record,
    sd_empty_check_record, SD_EMPTY_COLUMNS, ip_trace_steps, ip_trace_report,
    IP_TRACE_COLUMNS, IP_ACCOUNT_COLUMNS, link_clicks_steps, link_clicks_report,
    LINK_CLICK_COLUMNS, lock_many_steps, LOCK_MANY_NAME, foreign_signins_steps,
    foreign_signins_report, FOREIGN_SIGNIN_COLUMNS, FOREIGN_ACCOUNT_COLUMNS, IP_TRACE_NAME,
    pir_criteria, pir_label, pir_matter_name, pir_matter_argv, pir_query_argv,
    pir_hold_argv, pir_count_argv, pir_export_argv, pir_exports_argv, pir_download_argv,
    pir_matters_argv, pir_holds_argv, pir_delete_hold_argv, pir_close_argv,
    pir_group_members_argv, pir_id_from, pir_admin_from, pir_matter_ref, pir_record_new,
    pir_record_save, pir_record_load, pir_summary_text, PIR_MARKER, PIR_SERVICES,
    pir_accounts_too_long, _pir_emails,
    _csv_file_column,
)


# --- The io object ------------------------------------------------------------
class WorkflowIO(object):
    # What a workflow needs from its front end. Subclasses provide:
    #   out(text)                       show text (live progress)
    #   stream(argv, label, collect=None) -> exit code, or -1 when stopped;
    #                                   shows the output as it comes; collect
    #                                   (a list) also receives every line
    #   capture(argv) -> (exit code, full output)   output is shown too
    #   confirm(summary, word) -> True only when the person typed <word>
    #   cancelled() -> True when the person pressed Stop
    #   clear_cancel()                  forget a Stop (used before putting an
    #                                   account back the way it was)
    #   log(text)                       the front end's log file (optional)
    def log(self, text):
        pass

    def wait(self, seconds):
        # Waits in half-second steps so Stop still works; False if stopped.
        end = time.time() + seconds
        while time.time() < end:
            if self.cancelled():
                return False
            time.sleep(0.5)
        return not self.cancelled()

    def user_state(self, user):
        return user_state(self, user)

    def restore_state(self, user, changed_suspend, changed_archive):
        return restore_state(self, user, changed_suspend, changed_archive)


def user_state(io, user):
    # A user's (suspended, archived) state as booleans, or None when it
    # could not be read. GAM cannot move Drive files out of a suspended or
    # archived account, so those are switched on for the run.
    rc, out = io.capture(["info", "user", user, "quick"])
    if rc != 0:
        return None
    suspended = bool(re.search(r"Account Suspended:\s*True", out))
    archived = bool(re.search(r"Is Archived:\s*True", out))
    return (suspended, archived)


def restore_state(io, user, changed_suspend, changed_archive):
    # Puts the account back exactly as it was. Runs even after Stop, so an
    # account that started disabled is never left enabled.
    io.clear_cancel()
    if changed_suspend:
        io.out("\n----- restoring suspended state -----\n")
        io.stream(["update", "user", user, "suspended", "on"], "re-suspend")
    if changed_archive:
        io.out("\n----- restoring archived state -----\n")
        io.stream(["update", "user", user, "archived", "on"], "re-archive")


def _enable_for_run(io, user, was_suspended, was_archived, why=""):
    # Switches a suspended / archived account on for the run. Returns
    # (ok, changed_suspend, changed_archive); ok is False when it could not.
    changed_suspend = changed_archive = False
    if was_archived:
        io.out("\n----- unarchiving%s -----\n" % why)
        if io.stream(["update", "user", user, "archived", "off"], "unarchive") != 0:
            io.out("Could not unarchive. Stopping.\n")
            return False, changed_suspend, changed_archive
        changed_archive = True
    if was_suspended:
        io.out("\n----- unsuspending%s -----\n" % why)
        if io.stream(["update", "user", user, "suspended", "off"], "unsuspend") != 0:
            io.out("Could not unsuspend. Stopping.\n")
            return False, changed_suspend, changed_archive
        changed_suspend = True
    return True, changed_suspend, changed_archive


def _stamp():
    return datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")


def new_folder(base_dir, prefix, stamp=None):
    # A NEW folder <base_dir>\<prefix><stamp> for a run's evidence; a second
    # run in the same second gets _2, _3... so nothing is ever overwritten.
    base = os.path.join(base_dir, prefix + (stamp or _stamp()))
    folder, number = base, 2
    while os.path.exists(folder):
        folder = base + "_" + str(number)
        number += 1
    os.makedirs(folder)
    return folder


def read_csv_rows(path):
    # A CSV GAM wrote, as a list of dicts; a missing file (GAM found nothing
    # to write) is an empty list.
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError:
        return []


def _scope(values, default):
    # The search scope boxes -> (scope words, thread prefix, label).
    scopetype = (values.get("scopetype", default) or "").strip() or default
    scopeval = (values.get("scopeval", "") or "").strip()
    threads = (values.get("threads", "") or "").strip()
    if threads and not threads.isdigit():
        raise ValueError("Threads must be a whole number, or blank.")
    scope_entity = ["all", "users"] if scopetype == "all" else [scopetype, scopeval]
    thread_prefix = ["config", "num_threads", threads] if threads else []
    label = "all users" if scopetype == "all" else scopetype + " " + scopeval
    return scopetype, scopeval, scope_entity, thread_prefix, label


# --- Transfer My Drive (transferdrive) --------------------------------------
def prepare_transfer_drive(values):
    old = (values.get("old", "") or "").strip()
    new = (values.get("new", "") or "").strip()
    if not (old and new):
        raise ValueError("Old user and new user are required.")
    return {"old": old, "new": new, "folder": (values.get("folder", "") or "").strip(),
            "ask_title": "CONFIRM",
            "ask": ("Transfer ALL of " + old + "'s Drive files to " + new + "?\n\n"
                    "If " + old + " is suspended or archived it will be temporarily "
                    "enabled for the transfer, then set back to how it was.")}


def run_transfer_drive(io, plan):
    # State-aware Drive transfer: GAM cannot pull files from a suspended or
    # archived account, so enable it, transfer, then restore the exact
    # original state (active stays active).
    old, new = plan["old"], plan["new"]
    changed_suspend = changed_archive = False
    try:
        io.out("\n===== TRANSFER DRIVE: " + old + " -> " + new + " =====\n")
        state = io.user_state(old)
        if state is None:
            io.out("Could not read " + old + "'s account state (does it exist?). "
                   "Stopping.\n")
            return
        was_suspended, was_archived = state
        io.out("Original state: suspended=%s archived=%s\n" % (was_suspended, was_archived))
        ok, changed_suspend, changed_archive = _enable_for_run(
            io, old, was_suspended, was_archived, " (required to transfer)")
        if not ok:
            io.out("Cannot transfer.\n")
            return
        io.out("\n----- transferring drive -----\n")
        argv = ["user", old, "transfer", "drive", new]
        if plan["folder"]:
            argv += ["targetuserfoldername", plan["folder"]]
        rc = io.stream(argv, "transfer")
        if rc == -1:
            # Stop was pressed: say so plainly (not the "normal warning" note).
            io.out("\n[stopped - the transfer did not finish; files already "
                   "moved stay with " + new + "]\n")
        elif rc != 0:
            io.out("\n[note] transfer finished with a nonzero code (rc=%s). A "
                   "'Permission ... Does not exist' warning is normal and does not "
                   "mean files were missed - check the new user's '%s old files' "
                   "folder to confirm.\n" % (rc, old))
    finally:
        # Always put the account back the way we found it.
        io.restore_state(old, changed_suspend, changed_archive)
        io.out("\n===== TRANSFER COMPLETE (account restored to original state) =====\n")


# --- Move a user's Drive into a NEW Shared Drive (shareddrive) ---------------
def prepare_move_to_shareddrive(values, records_dir):
    old = (values.get("old", "") or "").strip()
    new = (values.get("new", "") or "").strip()
    name = (values.get("drivename", "") or "").strip()
    admin = (values.get("admin", "") or "").strip()
    if not (old and new and name and admin):
        raise ValueError("Old user, new user, Shared Drive name, and admin are "
                         "all required.")
    # 2.70: optionally drop the files' own sharing on the way in (GAM's
    # movefilepermissions false), so only the Shared Drive's members have
    # access - but FIRST save a record of who every file was shared with.
    dropshare = (values.get("dropshare", "No") or "No") == "Yes"
    stamp = datetime.datetime.now().strftime("%m-%d-%Y-%H%M%S")
    record_path = os.path.join(records_dir, "SharedDriveMove-"
                               + re.sub(r"[^A-Za-z0-9@._-]", "_", old)
                               + "-" + stamp + ".csv")
    if dropshare:
        steps = ("  3. Save a record of who every file is shared with:\n"
                 "       " + record_path + "\n"
                 "  4. Move " + old + "'s My Drive contents into it and\n"
                 "     REMOVE the files' old sharing (only the Shared\n"
                 "     Drive's members keep access)\n")
    else:
        steps = ("  3. Move " + old + "'s My Drive contents into it (the\n"
                 "     files keep their sharing)\n"
                 "  4. (no sharing record needed)\n")
    return {"old": old, "new": new, "name": name, "admin": admin,
            "dropshare": dropshare, "records_dir": records_dir,
            "record_path": record_path, "ask_title": "CONFIRM WORKFLOW",
            "ask": ("This offboarding workflow will:\n\n"
                    "  1. Enable " + old + " if it is suspended/archived\n"
                    "  2. Create a NEW Shared Drive named '" + name + "'\n"
                    + steps +
                    "  5. Make " + new + " a manager of it\n"
                    "  6. Remove the temporary admin/old-user access\n"
                    "  7. Restore " + old + " to its original state\n\nProceed?")}


def run_move_to_shareddrive(io, plan):
    # Create a Shared Drive, move the old user's My Drive into it, hand it to
    # the new user, remove temporary access, put the old user back.
    old, new, name, admin = plan["old"], plan["new"], plan["name"], plan["admin"]
    dropshare, record_path = plan["dropshare"], plan["record_path"]
    changed_suspend = changed_archive = False
    try:
        io.out("\n===== MOVE DRIVE -> NEW SHARED DRIVE =====\n")
        state = io.user_state(old)
        if state is None:
            io.out("Could not read " + old + "'s account state (does it exist?). "
                   "Stopping.\n")
            return
        was_suspended, was_archived = state
        io.out("Original state: suspended=%s archived=%s\n" % (was_suspended, was_archived))
        ok, changed_suspend, changed_archive = _enable_for_run(
            io, old, was_suspended, was_archived)
        if not ok or io.cancelled():
            return
        if dropshare:
            # The record comes BEFORE anything is created or moved; no
            # record = no move, so sharing is never lost unrecorded.
            io.out("\n----- save a record of the files' sharing -----\n")
            os.makedirs(plan["records_dir"], exist_ok=True)
            rc = io.stream(["redirect", "csv", record_path, "user", old, "print",
                            "filelist", "select", "root", "fields",
                            "id,name,mimetype,webviewlink,permissions",
                            "oneitemperrow", "filepath"], "sharing record")
            if rc != 0 or not os.path.isfile(record_path) \
                    or os.path.getsize(record_path) == 0:
                io.out("\n[stopped: the sharing record could not be saved, so "
                       "NOTHING was moved and no sharing was removed.]\n")
                return
            io.out("Sharing record saved: " + record_path + "\n(one row per file "
                   "per person or link it was shared with)\n")
            io.log("SHARING RECORD: " + record_path)
        if io.cancelled():
            return
        rc, out = io.capture(["user", old, "create", "teamdrive", name])
        if io.cancelled():
            return
        match = re.search(r"id:\s*([A-Za-z0-9_\-]{10,})", out)
        if rc != 0 or not match:
            io.out("\n[stopped: could not create the Shared Drive or read its id, "
                   "so NOTHING was moved.]\n")
            return
        drive_id = match.group(1)
        io.out("\nNew Shared Drive id: " + drive_id + "\n")
        steps = [
            ("grant old user temporary manager access",
             ["user", admin, "add", "drivefileacl", drive_id, "user", old,
              "role", "manager", "asadmin"]),
            ("move the old user's My Drive into the Shared Drive"
             + (" (removing the files' old sharing)" if dropshare else ""),
             ["user", old, "move", "drivefile", "root", "teamdriveparentid",
              drive_id, "mergewithparent"]
             + (["movefilepermissions", "false"] if dropshare else [])),
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
            if io.cancelled():
                io.out("[stopped by user - remaining steps skipped]\n")
                break
            io.out("\n----- " + label + " -----\n")
            io.stream(argv, label)
        io.out("\n===== DONE: Shared Drive '" + name + "' is now managed by "
               + new + " =====\n")
        if dropshare:
            io.out("Who the files were shared with before the move: "
                   + record_path + "\n")
    finally:
        io.restore_state(old, changed_suspend, changed_archive)


# --- Find outside sharing on Shared Drives (sdscan, read-only) ---------------
def prepare_sd_scan(values):
    folder = (values.get("folder", "") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = sd_scan_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files}


def run_sd_scan(io, plan):
    # organizers -> outside drive members -> outside sharing on files (as
    # each drive's organizer), then ONE plain report CSV the admin can trim
    # and hand to "Remove outside sharing listed in a report". Read-only.
    steps, files = plan["steps"], plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== FIND OUTSIDE SHARING ON SHARED DRIVES (read-only) =====\n")
    for number, (label, argv) in enumerate(steps, 1):
        io.out("\n----- Step %d of %d: %s -----\n" % (number, len(steps), label))
        if number == 3 and not any((r.get("organizers") or "").strip()
                                   for r in read_csv_rows(files["organizers"])):
            io.out("No Shared Drive has an organizer in your domains - no files "
                   "to read.\n")
            break
        rc = io.stream(argv, "sdscan")
        if rc == -1:
            io.out("\nStopped - no report was made.\n")
            return
        if number == 1 and rc != 0:
            io.out("\nStopping: the Shared Drives could not be listed (exit %s).\n" % rc)
            return
    rows, notscanned = sd_build_report(read_csv_rows(files["members"]),
                                       read_csv_rows(files["files"]),
                                       read_csv_rows(files["organizers"]))
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SD_REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    if notscanned:
        with open(files["notscanned"], "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["drive_id", "drive_name", "why"])
            writer.writeheader()
            writer.writerows(notscanned)
    # GAM's raw files were only needed to build the report.
    for key in ("members", "files", "organizers"):
        try:
            os.remove(files[key])
        except OSError:
            pass
    kinds = collections.Counter(
        ("drive member" if r["where"] == "drive" else
         "link" if r["kind"] == "anyone" else "person/group/domain") for r in rows)
    io.out("\n===== SUMMARY =====\n"
           "  %d outside members of Shared Drives\n"
           "  %d files shared with outside people, groups or domains\n"
           "  %d files open to 'anyone with the link' / the web\n"
           "  Report: %s\n"
           % (kinds["drive member"], kinds["person/group/domain"], kinds["link"],
              files["report"]))
    if notscanned:
        io.out("  %d Shared Drives could NOT be read (no organizer in your "
               "domains) - listed in:\n  %s\n" % (len(notscanned), files["notscanned"]))
    io.out("  To remove sharing: open the report, DELETE the rows you want to "
           "keep, save, then Drive > Remove outside sharing listed in a report.\n")


# --- Find sharing - Shared Drives or users' My Drive (findsharing, 2.87) -------
# Ross Scroggs' Drive / Shared Drive sharing scripts, done by GAM's own
# permission matching (gam_catalog.find_sharing_steps). Read-only; the
# report feeds "Remove outside sharing listed in a report" and its undo.
def prepare_find_sharing(values):
    folder = (values.get("folder", "") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = find_sharing_steps(values, folder, _stamp())
    what = values.get("what") or ""
    label = [w[1] for w in FIND_WHAT if w[0] == what][0]
    return {"folder": folder, "steps": steps, "files": files, "what": what,
            "label": label, "where": values.get("where")}


def run_find_sharing(io, plan):
    steps, files = plan["steps"], plan["files"]
    shared = plan["where"] == "shared"
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== FIND SHARING (read-only): %s - %s =====\n"
           % ("Shared Drives" if shared else "users' My Drive", plan["label"]))
    for number, (label, argv) in enumerate(steps, 1):
        io.out("\n----- Step %d of %d: %s -----\n" % (number, len(steps), label))
        if shared and "FILES" in label and not any(
                (r.get("organizers") or "").strip()
                for r in read_csv_rows(files["organizers"])):
            io.out("No Shared Drive has an organizer in your domains - no files to "
                   "read.\n")
            break
        rc = io.stream(argv, "findsharing")
        if rc == -1:
            io.out("\nStopped - no report was made.\n")
            return
        if number == 1 and rc != 0:
            io.out("\nStopping: the first step did not work (exit %s) - see the "
                   "lines above.\n" % rc)
            return
    guests = plan["what"] == "guests"
    members = read_csv_rows(files["members"]) if shared else []
    rows, notscanned = sd_build_report(
        [] if guests else members,
        read_csv_rows(files["files"]),
        read_csv_rows(files["organizers"]) if shared else [],
        keep_deleted=plan["what"] == "deleted")
    if guests:
        # The members only say who is NOT a guest (Ross's
        # GetTeamDriveGuestMembers.py) - they are not report rows.
        rows = find_guests(members, rows)
    if plan["what"] == "nonaccount":
        # 2.88: sharing with addresses that are NOT an account here (Ross's
        # GetSharedWithNonAccountUsersDriveACLs.py).
        accounts = find_disabled(read_csv_rows(files["disabled"]))
        if not accounts:
            # An empty list (GAM failed) would list EVERYONE - report nothing.
            io.out("\nThe list of accounts came back empty - the report is left "
                   "empty (it would otherwise list everyone).\n")
        rows = [r for r in rows if accounts and r["kind"] == "user" and r["target"]
                and r["target"] not in accounts]
        io.out("\n%d accounts here were checked.\n" % len(accounts))
    if plan["what"] in ("suspended", "onlysuspended"):
        # 2.88: only the sharing with suspended / archived accounts (any of
        # their addresses) - Ross's GetSuspendedUserSharedDriveACLs.py; or
        # (onlysuspended) only files shared with NOBODY else - Ross's
        # GetSharedWithListOfDisabledUsers*ACLs.py.
        disabled = find_disabled(read_csv_rows(files["disabled"]))
        if plan["what"] == "suspended":
            rows = [r for r in rows if r["kind"] == "user" and r["target"] in disabled]
        else:
            rows = find_only_disabled(rows, disabled)
        io.out("\n%d suspended / archived accounts were checked.\n" % len(disabled))
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SD_REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    if notscanned:
        with open(files["notscanned"], "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["drive_id", "drive_name", "why"])
            writer.writeheader()
            writer.writerows(notscanned)
    for key in ("members", "files", "organizers", "disabled"):
        try:
            os.remove(files[key])            # GAM's raw files built the report
        except OSError:
            pass
    kinds = collections.Counter(r["kind"] or "?" for r in rows)
    io.out("\n===== SUMMARY =====\n  %d permissions found (%s)\n  on %d files%s\n"
           "  Report: %s\n"
           % (len(rows), ", ".join("%d %s" % (n, k) for k, n in sorted(kinds.items()))
              or "none", len({r["doc_id"] for r in rows if r["where"] == "file"}),
              (" and %d Shared Drive memberships" % sum(1 for r in rows
                                                       if r["where"] == "drive"))
              if shared else "", files["report"]))
    if notscanned:
        io.out("  %d Shared Drives could NOT be read (no organizer in your domains) - "
               "listed in:\n  %s\n" % (len(notscanned), files["notscanned"]))
    if plan["what"] == "deleted":
        io.out("  Sharing with DELETED users or groups is listed for your records; "
               "'Remove outside sharing listed in a report' skips those rows (they "
               "cannot be put back).\n")
    else:
        io.out("  To remove sharing: open the report, DELETE the rows you want to "
               "keep, save, then Drive > Remove outside sharing listed in a report "
               "(it saves an undo file first).\n")


# --- Shared Drive reports (sdeach, 2.87) ---------------------------------------
# One read-only GAM command per Shared Drive, as one of its organizers
# (gam_catalog.sd_each_steps) - Ross's GetTeamDrive* count / storage / last
# modified / file list scripts, done by GAM now. GAM writes the report.
def prepare_sd_each(values):
    folder = (values.get("folder", "") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = sd_each_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files,
            "label": SD_EACH[values["what"]][0]}


def run_sd_each(io, plan):
    steps, files = plan["steps"], plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== SHARED DRIVE REPORT (read-only): %s =====\n" % plan["label"])
    for number, (label, argv) in enumerate(steps, 1):
        io.out("\n----- Step %d of %d: %s -----\n" % (number, len(steps), label))
        organizers = read_csv_rows(files["organizers"]) if number == 2 else []
        if number == 2 and not any((r.get("organizers") or "").strip() for r in organizers):
            io.out("No Shared Drive has an organizer in your domains - nothing to "
                   "report.\n")
            return
        rc = io.stream(argv, "sdeach")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        if number == 1 and rc != 0:
            io.out("\nStopping: the Shared Drives could not be listed (exit %s).\n" % rc)
            return
    notscanned = [{"drive_id": r.get("id", ""), "drive_name": r.get("name", ""),
                   "why": "no organizer in your domains - add one, then run again"}
                  for r in organizers if not (r.get("organizers") or "").strip()]
    if notscanned:
        with open(files["notscanned"], "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["drive_id", "drive_name", "why"])
            writer.writeheader()
            writer.writerows(notscanned)
    try:
        os.remove(files["organizers"])
    except OSError:
        pass
    rows = read_csv_rows(files["report"])
    io.out("\n===== DONE =====\n  %d rows - report: %s\n" % (len(rows), files["report"]))
    if notscanned:
        io.out("  %d Shared Drives could NOT be read (no organizer in your domains) - "
               "listed in:\n  %s\n" % (len(notscanned), files["notscanned"]))


# --- Shared Drive members by role (sdroles, 2.87) ------------------------------
# Ross Scroggs' GetTeamDriveMembersByRole.py: one GAM command (every member of
# every drive), then one row per drive with a column per role. Read-only.
def prepare_sd_roles(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = sd_roles_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files, "values": dict(values)}


def run_sd_roles(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== SHARED DRIVE MEMBERS BY ROLE (read-only) =====\n")
    label, argv = plan["steps"][0]
    io.out("\n----- %s -----\n" % label)
    rc = io.stream(argv, "sdroles")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    gam_rows = read_csv_rows(files["raw"])
    if rc != 0 and not gam_rows:
        io.out("\nStopping: the Shared Drives could not be read (exit %s).\n" % rc)
        return
    heads, rows = sd_roles_report(gam_rows, plan["values"])
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=heads)
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.remove(files["raw"])          # the report replaces GAM's file
    except OSError:
        pass
    io.out("\n===== DONE =====\n  %d Shared Drives - report: %s\n" % (len(rows), files["report"]))


# --- Duplicate files in My Drive (dupfiles, 2.88) ------------------------------
# Ross Scroggs' DeleteDuplicateFiles.py, made safer: find = read-only report;
# trash = the report's copies go to the TRASH after a typed TRASH; untrash =
# the same report puts them back (typed RESTORE).
def prepare_dup_files(values, log_dir):
    mode = values.get("mode") or "find"
    if mode in ("trash", "untrash"):
        path = (values.get("csvfile") or "").strip()
        if not path or not os.path.isfile(path):
            raise ValueError("Choose the report file (MyDrive-DuplicateFiles-...csv).")
        try:
            rows = dup_files_check_report(read_csv_rows(path))
        except (OSError, ValueError, csv.Error) as exc:
            raise ValueError("Cannot use that file:\n" + str(exc))
        return {"mode": mode, "report": path, "rows": rows,
                "work": os.path.join(log_dir, "dupfiles-%s-%s.csv" % (mode, _stamp()))}
    if mode != "find":
        raise ValueError("Choose what to do.")
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the report.")
    steps, files = dup_files_steps(values, folder, _stamp())
    return {"mode": mode, "folder": folder, "steps": steps, "files": files}


def run_dup_files(io, plan):
    if plan["mode"] == "find":
        files = plan["files"]
        os.makedirs(plan["folder"], exist_ok=True)
        io.out("\n===== DUPLICATE FILES IN MY DRIVE (read-only) =====\n")
        label, argv = plan["steps"][0]
        io.out("\n----- %s -----\n" % label)
        rc = io.stream(argv, "dupfiles")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        rows = read_csv_rows(files["raw"])
        dups = dup_files_rows(rows)
        with open(files["report"], "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=DUP_FILES_COLUMNS)
            writer.writeheader()
            writer.writerows(dups)
        try:
            os.remove(files["raw"])
        except OSError:
            pass
        io.out("\n===== DONE =====\n  %d files read, %d older copies found (%d owners)\n"
               "  Report: %s\n" % (len(rows), len(dups), len({d["Owner"] for d in dups}),
                                   files["report"]))
        if dups:
            io.out("  To trash them: delete the rows to KEEP from the report, save, then run "
                   "this task with 'Move the copies listed in a report to the TRASH'.\n")
        return
    rows, trash = plan["rows"], plan["mode"] == "trash"
    word = "TRASH" if trash else "RESTORE"
    summary = ("%s\n\nFrom: %s\n\n  %d files of %d owners will be %s.\n\n%s" % (
        "MOVE DUPLICATE FILES TO THE TRASH" if trash else "PUT BACK FILES FROM THE TRASH",
        plan["report"], len(rows), len({r["Owner"] for r in rows}),
        "moved to their owner's TRASH" if trash else "taken back out of the trash",
        "Drive keeps trashed files for 30 days - 'Put them back' with this same report "
        "undoes it." if trash else "Files already emptied from the trash cannot come back."))
    if not io.confirm(summary, word):
        io.out("\nCanceled - nothing was changed.\n")
        return
    io.out("\n===== %s =====\n" % ("TRASH DUPLICATE FILES" if trash else "PUT BACK FILES"))
    try:
        os.makedirs(os.path.dirname(plan["work"]), exist_ok=True)
        with open(plan["work"], "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Owner", "id"])
            writer.writerows([r["Owner"].strip(), r["id"].strip()] for r in rows)
        lines = []
        rc = io.stream(["csv", plan["work"], "gam", "user", "~Owner",
                        "trash" if trash else "untrash", "drivefile", "~id"],
                       "dupfiles", collect=lines)
        if rc == -1:
            io.out("\nStopped.\n")
            return
        done = len(re.findall(r"\bTrashed\b" if trash else r"\bUntrashed\b", "".join(lines)))
        io.out("\n===== SUMMARY =====\n  %d of %d %s - see the lines above for the rest "
               "(exit %s).\n" % (done, len(rows), "trashed" if trash else "put back", rc))
        if trash:
            io.out("  To put them back: this task, 'Put them back', with the report:\n  %s\n"
                   % plan["report"])
    finally:
        try:
            os.remove(plan["work"])
        except OSError:
            pass


# --- Files created per day / who appears on the most files (2.88) ---------------
def _prepare_drive_count(values, builder):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = builder(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files}


def prepare_drive_daily(values):
    return _prepare_drive_count(values, drive_daily_steps)


def prepare_drive_access(values):
    return _prepare_drive_count(values, drive_access_steps)


def _run_drive_count(io, plan, title, reporter):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== %s (read-only) =====\n" % title)
    label, argv = plan["steps"][0]
    io.out("\n----- %s -----\n" % label)
    rc = io.stream(argv, "drivecount")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    heads, rows = reporter(read_csv_rows(files["raw"]))
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=heads)
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.remove(files["raw"])
    except OSError:
        pass
    io.out("\n===== DONE =====\n  %d rows - report: %s\n" % (len(rows), files["report"]))


def run_drive_daily(io, plan):
    _run_drive_count(io, plan, "FILES CREATED PER DAY, BY TYPE", drive_daily_report)


def run_drive_access(io, plan):
    _run_drive_count(io, plan, "WHO APPEARS ON THE MOST FILES", drive_access_report)


# --- Who sends the most mail (mailfroms, 2.88) ---------------------------------
# Ross Scroggs' CountFroms.py: GAM lists the From of each message, GAMGUI
# counts per address. Read-only.
def prepare_mail_froms(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = mail_froms_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files}


def run_mail_froms(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== MESSAGES PER SENDER (read-only) =====\n")
    label, argv = plan["steps"][0]
    io.out("\n----- %s -----\n" % label)
    rc = io.stream(argv, "mailfroms")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    rows = read_csv_rows(files["raw"])
    report = mail_froms_report(rows)
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sender", "name", "messages"])
        writer.writeheader()
        writer.writerows(report)
    try:
        os.remove(files["raw"])
    except OSError:
        pass
    io.out("\n===== DONE =====\n  %d messages from %d senders\n  Report: %s\n"
           % (len(rows), len(report), files["report"]))
    for row in report[:5]:
        io.out("    %6d  %s\n" % (row["messages"], row["sender"]))


def _remove_quietly(path):
    # Deletes a working file GAM wrote; one that is missing or still open
    # (e.g. in Excel) is left alone.
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _write_report(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# --- Chrome extensions on managed browsers (browserexts, 2.89) --------------
# Ross Scroggs' BrowserExtensions.py: GAM prints every managed browser as
# JSON; browser_exts_report makes one row per extension. Read-only.
def prepare_browser_exts(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = browser_exts_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files,
            "which": (values.get("which") or "all").strip(),
            "per": (values.get("per") or "extension").strip()}


def run_browser_exts(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== CHROME EXTENSIONS ON MANAGED BROWSERS (read-only) =====\n")
    label, argv = plan["steps"][0]
    io.out("\n----- %s -----\n" % label)
    rc = io.stream(argv, "browserexts")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    rows = read_csv_rows(files["raw"])
    if not rows:
        io.out("\nGAM listed no managed Chrome browsers (exit code %s) - nothing to "
               "report. Browsers appear here only when they are enrolled in Chrome "
               "Browser Cloud Management.\n" % rc)
        _remove_quietly(files["raw"])
        return
    columns, report, unreadable = browser_exts_report(rows, plan["which"], plan["per"])
    _write_report(files["report"], columns, report)
    _remove_quietly(files["raw"])
    io.out("\n===== DONE =====\n  %d browsers, %d extensions\n  Report: %s\n"
           % (len(rows), len(report), files["report"]))
    if unreadable:
        io.out("  %d browser(s) could not be read (their data was not valid JSON): %s\n"
               % (len(unreadable), ", ".join(unreadable[:10])
                  + (" ..." if len(unreadable) > 10 else "")))
    for row in report[:5]:
        io.out("    %5d machines  %s\n" % (row["machines"], row["name"] or row["extensionId"]))


# --- Last message sent to each group (lastgroupmail, 2.89) -------------------
# Ross Scroggs' GetLastGroupEmail.py. Read-only. In list mode the groups are
# written to a small CSV first so GAM can loop over them (gam csv ...).
def prepare_last_group_mail(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files, groups, source = last_group_mail_steps(values, folder, _stamp())
    plan = {"folder": folder, "steps": steps, "files": files, "groups": groups,
            "source": source}
    if (values.get("source") or "").strip() == "all":
        plan["ask_title"] = "EVERY GROUP"
        plan["ask"] = ("This checks the mailbox of every member of every group for "
                       "its newest message - on a big domain it can take hours.\n\n"
                       "Run it now?")
    return plan


def _group_list_from_csv(path, column):
    # The group addresses in one column of a CSV (lower case, no blanks);
    # raises ValueError when the file or the column is missing.
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if column not in (reader.fieldnames or []):
                raise ValueError("The CSV file has no column '%s' (it has: %s)."
                                 % (column, ", ".join(reader.fieldnames or [])))
            return [(row.get(column) or "").strip().lower() for row in reader
                    if (row.get(column) or "").strip()]
    except OSError as exc:
        raise ValueError("Cannot read the CSV file %s: %s" % (path, exc))


def run_last_group_mail(io, plan):
    files = plan["files"]
    listfile, column = plan["source"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== LAST MESSAGE SENT TO EACH GROUP (read-only) =====\n")
    if plan["groups"]:
        # List mode: the groups typed in the form -> a one-column CSV for GAM.
        _write_report(listfile, ["email"], [{"email": g} for g in plan["groups"]])
    elif not files.get("groups"):
        # CSV mode: the person's own file - check it and its column first.
        try:
            if not _group_list_from_csv(listfile, column):
                io.out("\nThe column '%s' of %s is empty - nothing to check.\n"
                       % (column, listfile))
                return
        except ValueError as exc:
            io.out("\n%s\n" % exc)
            return
    steps = plan["steps"]
    for number, (label, argv) in enumerate(steps):
        io.out("\n----- %s -----\n" % label)
        rc = io.stream(argv, "lastgroupmail")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        if number == 0 and len(steps) > 1 and not read_csv_rows(listfile):
            io.out("\nGAM listed no groups (exit code %s) - stopping.\n" % rc)
            return
    groups = plan["groups"]
    if not groups:
        try:
            groups = _group_list_from_csv(listfile, column)
        except ValueError as exc:
            io.out("\n%s\n" % exc)
            groups = []
    report = last_group_mail_report(groups, read_csv_rows(files["raw"]))
    _write_report(files["report"], LAST_GROUP_MAIL_COLUMNS, report)
    _remove_quietly(files["raw"])
    if files.get("groups"):
        _remove_quietly(files["groups"])
    quiet = [r for r in report if r["lastMessage"] == ""]
    io.out("\n===== DONE =====\n  %d groups, %d with no message found\n  Report: %s\n"
           % (len(report), len(quiet), files["report"]))
    for row in report[:5]:
        io.out("    %-40s %s\n" % (row["group"], row["lastMessage"] or "(none found)"))


# --- Calendar events, one attendee per row (eventattendees, 2.89) -----------
# Ross Scroggs' MakeOneAttendeePerRowEvents.py. Read-only.
def prepare_event_attendees(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files, domains, emails = event_attendees_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files, "domains": domains,
            "emails": emails}


def run_event_attendees(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== CALENDAR EVENTS - ONE ATTENDEE PER ROW (read-only) =====\n")
    label, argv = plan["steps"][0]
    io.out("\n----- %s -----\n" % label)
    rc = io.stream(argv, "eventattendees")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    rows = read_csv_rows(files["raw"])
    columns, report = event_attendees_report(rows, plan["domains"], plan["emails"])
    _write_report(files["report"], columns or ["attendee.email"], report)
    _remove_quietly(files["raw"])
    io.out("\n===== DONE =====\n  %d events, %d attendee rows\n  Report: %s\n"
           % (len(rows), len(report), files["report"]))


def _report_plan(values, log_dir, name, check, label):
    # The plan of a 'change things from a report' mode: the report checked
    # with check(rows) (ValueError -> shown as the error), plus a work file
    # in the log folder for GAM's csv loop.
    path = (values.get("csvfile") or "").strip()
    if not path or not os.path.isfile(path):
        raise ValueError("Choose the report file (%s)." % label)
    try:
        rows = check(read_csv_rows(path))
    except (OSError, ValueError, csv.Error, KeyError) as exc:
        raise ValueError("Cannot use that file:\n" + str(exc))
    return {"report": path, "rows": rows,
            "work": os.path.join(log_dir, "%s-%s.csv" % (name, _stamp()))}


def _run_csv_loop(io, plan, columns, rows, argv, label, done_word):
    # Writes rows (dicts) to the plan's work file and runs 'gam csv <file>
    # gam <argv>' once; -> (lines GAM printed, how many done_word lines,
    # exit code). The work file is removed afterwards.
    os.makedirs(os.path.dirname(plan["work"]), exist_ok=True)
    _write_report(plan["work"], columns, rows)
    try:
        lines = []
        rc = io.stream(["csv", plan["work"]] + CSV_LOOP_PLAIN + ["gam"] + argv, label,
                       collect=lines)
        done = len(re.findall(done_word, "".join(lines))) if rc != -1 else 0
        return lines, done, rc
    finally:
        _remove_quietly(plan["work"])


# --- CSV tools (csvtools, 2.89) -----------------------------------------------
# Ross Scroggs' CSV helper scripts, done locally. The task says which tool
# (task["csvop"]); the input files are only read, the result is a NEW file.
def read_csv_table(path, what="the CSV file"):
    # -> (columns, rows); ValueError when it cannot be read.
    path = (path or "").strip().strip('"')
    if not path or not os.path.isfile(path):
        raise ValueError("Choose %s (not found: %s)." % (what, path or "nothing chosen"))
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            return list(reader.fieldnames or []), rows
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Cannot read %s: %s" % (path, exc))


def _csv_list(text):
    return [c.strip() for c in (text or "").split(",") if c.strip()]


def prepare_csv_tools(values, task):
    op = (task or {}).get("csvop")
    if op not in {t[0] for t in CSV_TOOLS}:
        raise ValueError("Unknown CSV tool.")
    plan = {"op": op, "values": dict(values), "steps": []}
    files = ([f.strip().strip('"') for f in (values.get("files") or "").split(";") if f.strip()]
             if op == "common" else [values.get("file1")])
    if op == "common" and len(files) < 2:
        raise ValueError("Enter two or more CSV files, separated by ;")
    for path in files + ([values.get("file2")] if op == "join" else []):
        if not (path or "").strip() or not os.path.isfile(path.strip().strip('"')):
            raise ValueError("Choose the CSV file(s) - not found: %s" % ((path or "").strip()
                                                                       or "nothing chosen"))
    plan["files"] = [f.strip().strip('"') for f in files]
    if op != "rows":
        folder = (values.get("folder") or "").strip()
        if not folder:
            raise ValueError("Choose a folder for the result.")
        stamp = _stamp()
        plan["folder"] = folder
        plan["out"] = os.path.join(folder, "CSV-%s-%s.%s" % (op, stamp,
                                                             "json" if op == "json" else "csv"))
        if op == "addou":
            plan["lookup"] = os.path.join(folder, "CSV-users-ou-raw-%s.csv" % stamp)
            plan["steps"] = [("List every user's OU", _redirect(plan["lookup"]) + [
                                                       "print", "users", "fields",
                                                       "primaryemail,ou"])]
        elif op == "addcrosid":
            plan["lookup"] = os.path.join(folder, "CSV-cros-serials-raw-%s.csv" % stamp)
            plan["steps"] = [("List every Chromebook's serial number",
                              _redirect(plan["lookup"]) + ["print", "cros", "fields",
                               "serialnumber"])]
    if op == "count":
        if not (values.get("min") or "1").strip().isdigit():
            raise ValueError("The 'at least' count must be a whole number.")
    if op in ("join", "addou", "addcrosid", "count", "dedupe", "common", "json", "explode",
              "combine") and not (values.get("col1") or "").strip():
        raise ValueError("Enter the column name.")
    if op == "combine" and not (values.get("col2") or "").strip():
        raise ValueError("Enter the values column.")
    return plan


def run_csv_tools(io, plan):
    op, v = plan["op"], plan["values"]
    col1 = (v.get("col1") or "").strip()
    io.out("\n===== %s =====\n" % [t[1] for t in CSV_TOOLS if t[0] == op][0].upper())
    try:
        for label, argv in plan["steps"]:
            os.makedirs(plan["folder"], exist_ok=True)
            io.out("\n----- %s (read-only) -----\n" % label)
            rc = io.stream(argv, "csvtools")
            if rc == -1:
                io.out("\nStopped.\n")
                return
        if op == "common":
            tables = [(os.path.basename(p),) + read_csv_table(p) for p in plan["files"]]
            cols, rows, notes = csv_common(tables, col1)
        else:
            cols1, rows1 = read_csv_table(plan["files"][0])
            if op == "rows":
                io.out("\n%s\n  %d data rows (plus the header row), %d columns.\n"
                       % (plan["files"][0], len(rows1), len(cols1)))
                return
            if op == "join":
                cols2, rows2 = read_csv_table(v.get("file2"), "the second CSV file")
                cols, rows, notes = csv_join(
                    cols1, rows1, col1, cols2, rows2, (v.get("col2") or "").strip() or col1,
                    _csv_list(v.get("cols")) or None, (v.get("unmatched") or "keep") == "keep")
            elif op in ("addou", "addcrosid"):
                cols2, rows2 = read_csv_table(plan["lookup"], "GAM's list")
                if not rows2:
                    io.out("\nGAM listed nothing to look up - stopping.\n")
                    return
                key2, add = (("primaryEmail", ["orgUnitPath"]) if op == "addou"
                             else ("serialNumber", ["deviceId"]))
                cols, rows, notes = csv_join(cols1, rows1, col1, cols2, rows2, key2, add, True)
            elif op == "combine":
                cols, rows, notes = csv_combine(cols1, rows1, col1, (v.get("col2") or "").strip(),
                                                _csv_list(v.get("cols")), v.get("sep") or " ")
            elif op == "count":
                cols, rows, notes = csv_count(cols1, rows1, col1, int(v.get("min") or 1))
            elif op == "dedupe":
                cols, rows, notes = csv_dedupe(cols1, rows1, col1)
            elif op == "explode":
                cols, rows, notes = csv_explode(cols1, rows1, col1)
            else:   # json
                items, bad = csv_json_list(cols1, rows1, col1)
                os.makedirs(plan["folder"], exist_ok=True)
                with open(plan["out"], "w", encoding="utf-8") as handle:
                    json.dump(items, handle, indent=2, ensure_ascii=False)
                io.out("\n===== DONE =====\n  %d JSON objects%s\n  File: %s\n" % (
                    len(items), " (%d rows could not be read)" % bad if bad else "",
                    plan["out"]))
                return
        os.makedirs(plan["folder"], exist_ok=True)
        _write_report(plan["out"], cols, rows)
        io.out("\n===== DONE =====\n  %s\n  File: %s\n" % ("\n  ".join(notes), plan["out"]))
    except ValueError as exc:
        io.out("\n%s\n" % exc)
    finally:
        _remove_quietly(plan.get("lookup"))


# --- Compromised Account investigation (2.89, MOREnet's tips) -----------------
def prepare_ip_trace(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = ip_trace_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files}


def run_ip_trace(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== TRACE AN IP ADDRESS (read-only) =====\n")
    results = []
    for (label, argv), (ip, _app, log_label, path) in zip(plan["steps"], files["logs"]):
        io.out("\n----- %s -----\n" % label)
        rc = io.stream(argv, "iptrace")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        rows = read_csv_rows(path)
        if not rows:
            _remove_quietly(path)          # keep only the logs with something in them
        results.append((ip, log_label, path, rows))
    summary, accounts = ip_trace_report(results)
    _write_report(files["summary"], IP_TRACE_COLUMNS, summary)
    _write_report(files["accounts"], IP_ACCOUNT_COLUMNS, accounts)
    io.out("\n===== DONE =====\n")
    for row in summary:
        if row["events"]:
            io.out("  %-15s %-32s %5d events  accounts: %s\n" % (
                row["ipAddress"], row["log"], row["events"], row["accounts"][:120]))
    if not any(r["events"] for r in summary):
        io.out("  Nothing from these addresses in the logs for that time.\n")
    io.out("  Summary: %s\n  Accounts: %s (%d)\n" % (files["summary"], files["accounts"],
                                                    len(accounts)))


def prepare_foreign_signins(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files, countries = foreign_signins_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files, "countries": countries}


def run_foreign_signins(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== SIGN-INS FROM OUTSIDE YOUR COUNTRIES (read-only) =====\n")
    label, argv = plan["steps"][0]
    io.out("\n----- %s -----\n" % label)
    rc = io.stream(argv, "foreignsignins")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    rows = read_csv_rows(files["raw"])
    signins, accounts = foreign_signins_report(rows, plan["countries"])
    _write_report(files["report"], FOREIGN_SIGNIN_COLUMNS, signins)
    _write_report(files["accounts"], FOREIGN_ACCOUNT_COLUMNS, accounts)
    _remove_quietly(files["raw"])
    io.out("\n===== DONE =====\n  %d sign-ins read, %d from outside %s, by %d accounts\n"
           "  Sign-ins: %s\n  Accounts: %s\n" % (
               len(rows), len(signins), ", ".join(plan["countries"]), len(accounts),
               files["report"], files["accounts"]))
    for a in accounts[:10]:
        io.out("    %-40s %3d sign-ins  %s%s\n" % (a["account"], a["signIns"], a["countries"],
                                                   "  (flagged)" if a["suspicious"] else ""))
    if accounts:
        io.out("  Check each with the person; trace odd addresses with Compromised Account > "
               "%s.\n" % IP_TRACE_NAME)


def prepare_link_clicks(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files, subject, msgid = link_clicks_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files, "subject": subject,
            "msgid": msgid}


def run_link_clicks(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== WHO CLICKED A PHISHING LINK (read-only) =====\n")
    for label, argv in plan["steps"]:
        io.out("\n----- %s -----\n" % label)
        rc = io.stream(argv, "linkclicks")
        if rc == -1:
            io.out("\nStopped.\n")
            return
    raw = [(kind, read_csv_rows(path)) for kind, path in files["raw"]]
    clicks = link_clicks_report(raw, plan["subject"], plan["msgid"])
    _write_report(files["report"], LINK_CLICK_COLUMNS, clicks)
    for _kind, path in files["raw"]:
        _remove_quietly(path)
    users = sorted({c["user"] for c in clicks if c["user"]})
    io.out("\n===== DONE =====\n  %d link clicks read, %d on this email, by %d people\n"
           "  Report: %s\n" % (sum(len(r) for _k, r in raw), len(clicks), len(users),
                               files["report"]))
    for user in users[:20]:
        io.out("    %s\n" % user)
    if users:
        io.out("  Lock them out and have them change their password: Compromised Account > "
               "%s (the report's 'user' column works as a CSV of accounts).\n" % LOCK_MANY_NAME)


def prepare_lock_many(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the record.")
    steps, files = lock_many_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files}


def run_lock_many(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== LOCK OUT SEVERAL ACCOUNTS =====\n")
    label, argv = plan["steps"][0]
    io.out("\n----- %s (read-only) -----\n" % label)
    rc = io.stream(argv, "lockmany")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    accounts = [r.get("primaryEmail", "") for r in read_csv_rows(files["record"])
                if r.get("primaryEmail")]
    if not accounts:
        io.out("\nNo accounts found (exit code %s) - nothing to lock.\n" % rc)
        return
    changes = plan["steps"][1:]
    summary = ("LOCK OUT %d ACCOUNTS\n\n%s%s\n\nThis will:\n%s\n\nRecord: %s\nAfterwards give "
               "each a new password (Users > Reset password)." % (
                   len(accounts), "\n".join("  " + a for a in accounts[:15]),
                   "\n  ... and %d more" % (len(accounts) - 15) if len(accounts) > 15 else "",
                   "\n".join("  - " + lab for lab, _a in changes), files["record"]))
    if not io.confirm(summary, "LOCK"):
        io.out("\nCanceled - nothing was changed (the record stays).\n")
        return
    io.log("LOCKMANY start: %d accounts; record %s" % (len(accounts), files["record"]))
    for label, argv in changes:
        io.out("\n----- %s -----\n" % label)
        rc = io.stream(argv, "lockmany")
        if rc == -1:
            io.out("\nStopped.\n")
            io.log("LOCKMANY stopped at: " + label)
            return
        io.log("LOCKMANY %s: exit %s" % (label, rc))
    io.out("\n===== DONE =====\n  %d accounts - see the lines above for each one.\n"
           "  Google can take a minute or two to show them as suspended (seen live).\n"
           "  Record: %s\n" % (len(accounts), files["record"]))


# --- Empty a Shared Drive (sdempty, 2.89) --------------------------------------
# Wiki Users-Drive-Cleanup "Delete contents of a Shared Drive", made safer:
# the top-level items go to the Shared Drive's TRASH (30 days) instead of
# purge, after a record of everything and a typed EMPTY; 'putback' untrashes
# the record's items (typed RESTORE).
def prepare_sd_empty(values, log_dir):
    mode = (values.get("mode") or "empty").strip()
    if mode == "putback":
        plan = _report_plan(values, log_dir, "sdempty-putback", sd_empty_check_record,
                            "SharedDrive-Emptied-...csv")
        plan["mode"] = mode
        return plan
    if mode != "empty":
        raise ValueError("Choose what to do.")
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the record files.")
    steps, files = sd_empty_steps(values, folder, _stamp())
    return {"mode": mode, "folder": folder, "steps": steps, "files": files,
            "manager": (values.get("manager") or "").strip().lower(),
            "driveid": (values.get("driveid") or "").strip(),
            "work": os.path.join(log_dir, "sdempty-trash-%s.csv" % _stamp())}


def run_sd_empty(io, plan):
    if plan["mode"] == "putback":
        rows = plan["rows"]
        summary = ("PUT BACK A SHARED DRIVE'S ITEMS\n\nFrom: %s\n\n  %d top-level files and "
                   "folders (and what is inside them) will be taken back out of the "
                   "Shared Drive's trash.\n\nItems already emptied from the trash cannot "
                   "come back." % (plan["report"], len(rows)))
        if not io.confirm(summary, "RESTORE"):
            io.out("\nCanceled - nothing was changed.\n")
            return
        io.out("\n===== PUT BACK =====\n")
        io.log("SDEMPTY PUTBACK start: %d items from %s" % (len(rows), plan["report"]))
        _lines, done, rc = _run_csv_loop(
            io, plan, ["User", "id"],
            [{"User": r["User"].strip(), "id": r["id"].strip()} for r in rows],
            ["user", "~User", "untrash", "drivefile", "~id"], "sdempty", r"\bUntrashed\b")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        io.out("\n===== SUMMARY =====\n  %d of %d items put back - see the lines above for "
               "the rest (exit %s).\n" % (done, len(rows), rc))
        io.log("SDEMPTY PUTBACK done: %d of %d (exit %s)" % (done, len(rows), rc))
        return
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== EMPTY A SHARED DRIVE =====\n")
    for label, argv in plan["steps"]:
        io.out("\n----- %s (read-only) -----\n" % label)
        rc = io.stream(argv, "sdempty")
        if rc == -1:
            io.out("\nStopped.\n")
            return
    everything = read_csv_rows(files["all"])
    top = sd_empty_record(read_csv_rows(files["top"]), plan["manager"])
    _remove_quietly(files["top"])
    if not top:
        io.out("\nNothing to move: GAM listed no top-level items (exit code %s). Is the "
               "drive already empty, and is %s one of its managers?\n"
               % (rc, plan["manager"]))
        return
    _write_report(files["record"], SD_EMPTY_COLUMNS, top)
    io.out("\n  Record of everything in the drive: %s\n  Record of what is moved (for "
           "Put back): %s\n" % (files["all"], files["record"]))
    summary = ("EMPTY A SHARED DRIVE\n\nShared Drive: %s\nAs manager: %s\n\n  %d top-level "
               "files and folders (%d items in all) will be moved to the Shared Drive's "
               "TRASH.\n\nThey stay there 30 days; 'Put back' with\n%s\nundoes it. The "
               "Shared Drive itself is not deleted." % (
                   plan["driveid"], plan["manager"], len(top), len(everything),
                   files["record"]))
    if not io.confirm(summary, "EMPTY"):
        io.out("\nCanceled - nothing was changed (the record files stay).\n")
        return
    io.log("SDEMPTY start: %d top-level items of %s as %s; record %s"
           % (len(top), plan["driveid"], plan["manager"], files["record"]))
    _lines, done, rc = _run_csv_loop(
        io, plan, ["User", "id"], top,
        ["user", "~User", "trash", "drivefile", "~id"], "sdempty", r"\bTrashed\b")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    io.out("\n===== SUMMARY =====\n  %d of %d top-level items moved to the trash - see the "
           "lines above for the rest (exit %s).\n  To put them back: this task, 'Put back', "
           "with\n  %s\n" % (done, len(top), rc, files["record"]))
    io.log("SDEMPTY done: %d of %d (exit %s)" % (done, len(top), rc))


# --- Old addresses in users' contacts (oldcontacts, 2.89) --------------------
# Ross Scroggs' DeleteOldContacts.py. find = read-only report; delete = the
# report's contacts after a typed DELETE.
def prepare_old_contacts(values, log_dir):
    mode = (values.get("mode") or "find").strip()
    if mode == "delete":
        plan = _report_plan(values, log_dir, "oldcontacts-delete", old_contacts_check_report,
                            "Old-Contacts-...csv")
        plan["mode"] = mode
        return plan
    if mode != "find":
        raise ValueError("Choose what to do.")
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the report.")
    steps, files, old = old_contacts_steps(values, folder, _stamp())
    return {"mode": mode, "folder": folder, "steps": steps, "files": files, "old": old}


def run_old_contacts(io, plan):
    if plan["mode"] == "delete":
        rows = plan["rows"]
        summary = ("DELETE CONTACTS\n\nFrom: %s\n\n  %d contacts of %d users will be "
                   "DELETED from their Google Contacts.\n\nGoogle Contacts' 'Undo changes' "
                   "(contacts.google.com, as each user) can bring them back for 30 days; "
                   "the report keeps their names and addresses." % (
                       plan["report"], len(rows), len({r["User"].lower() for r in rows})))
        if not io.confirm(summary, "DELETE"):
            io.out("\nCanceled - nothing was changed.\n")
            return
        io.out("\n===== DELETE OLD CONTACTS =====\n")
        io.log("OLDCONTACTS DELETE start: %d contacts from %s" % (len(rows), plan["report"]))
        _lines, done, rc = _run_csv_loop(
            io, plan, ["User", "resourceName"],
            [{"User": r["User"].strip(), "resourceName": r["resourceName"].strip()}
             for r in rows],
            ["user", "~User", "delete", "contacts", "~resourceName"], "oldcontacts",
            r"\bDeleted\b")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        io.out("\n===== SUMMARY =====\n  %d of %d contacts deleted - see the lines above "
               "for the rest (exit %s).\n" % (done, len(rows), rc))
        io.log("OLDCONTACTS DELETE done: %d of %d (exit %s)" % (done, len(rows), rc))
        return
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== OLD ADDRESSES IN USERS' CONTACTS (read-only) =====\n")
    kind, old = plan["old"]
    if kind == "csv" and not files.get("old"):
        # The person's own CSV: check the file and its column before GAM runs.
        try:
            if not _group_list_from_csv(*old):
                io.out("\nThe column '%s' of %s is empty - nothing to look for.\n"
                       % (old[1], old[0]))
                return
        except ValueError as exc:
            io.out("\n%s\n" % str(exc).replace("group", "address"))
            return
    for label, argv in plan["steps"]:
        io.out("\n----- %s -----\n" % label)
        rc = io.stream(argv, "oldcontacts")
        if rc == -1:
            io.out("\nStopped.\n")
            return
    if kind == "csv":
        try:
            old = _group_list_from_csv(*old)
        except ValueError as exc:
            io.out("\n%s\n" % exc)
            return
    if not old:
        io.out("\nNo old addresses to look for (exit code %s) - stopping.\n" % rc)
        return
    rows = read_csv_rows(files["raw"])
    report = old_contacts_report(old, rows)
    _write_report(files["report"], OLD_CONTACTS_COLUMNS, report)
    _remove_quietly(files["raw"])
    _remove_quietly(files.get("old"))
    io.out("\n===== DONE =====\n  %d old addresses, %d contacts read, %d contacts hold an "
           "old address (%d users)\n  Report: %s\n" % (
               len(old), len(rows), len(report), len({r["User"] for r in report}),
               files["report"]))
    if report:
        io.out("  To delete them: remove the rows to KEEP from the report, save, then run "
               "this task with 'Delete the contacts listed in a report'.\n")


# --- Plain-text vacation replies to HTML (vacationhtml, 2.89) -----------------
# Ross Scroggs' UpdateVacationToHTML.py. find = read-only report; convert /
# putback = the report, after a typed CONVERT / RESTORE.
def prepare_vacation_html(values, log_dir):
    mode = (values.get("mode") or "find").strip()
    if mode in ("convert", "putback"):
        plan = _report_plan(values, log_dir, "vacationhtml-" + mode,
                            vacation_html_check_report, "Vacation-PlainText-...csv")
        plan["mode"] = mode
        return plan
    if mode != "find":
        raise ValueError("Choose what to do.")
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the report.")
    steps, files = vacation_html_steps(values, folder, _stamp())
    return {"mode": mode, "folder": folder, "steps": steps, "files": files}


def run_vacation_html(io, plan):
    if plan["mode"] in ("convert", "putback"):
        rows, convert = plan["rows"], plan["mode"] == "convert"
        word = "CONVERT" if convert else "RESTORE"
        summary = ("%s\n\nFrom: %s\n\n  %d users' vacation replies will be %s.\n\n"
                   "Subject, dates and on/off are not changed. %s" % (
                       "VACATION REPLIES TO HTML" if convert else "PUT BACK PLAIN-TEXT REPLIES",
                       plan["report"], len(rows),
                       "rewritten as HTML" if convert else "set back to the original text",
                       "'Put back' with this same report undoes it." if convert else ""))
        if not io.confirm(summary, word):
            io.out("\nCanceled - nothing was changed.\n")
            return
        io.out("\n===== %s =====\n" % ("CONVERT TO HTML" if convert else "PUT BACK"))
        io.log("VACATIONHTML %s start: %d users from %s" % (word, len(rows), plan["report"]))
        column = "htmlmessage" if convert else "message"
        _lines, done, rc = _run_csv_loop(
            io, plan, ["User", "text"],
            [{"User": r["User"].strip(), "text": r[column]} for r in rows],
            ["user", "~User", "vacation", column, "~text"], "vacationhtml",
            r"Vacation Enabled")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        io.out("\n===== SUMMARY =====\n  %d of %d replies updated - see the lines above "
               "for the rest (exit %s).\n" % (done, len(rows), rc))
        io.log("VACATIONHTML %s done: %d of %d (exit %s)" % (word, done, len(rows), rc))
        return
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== PLAIN-TEXT VACATION REPLIES (read-only) =====\n")
    label, argv = plan["steps"][0]
    io.out("\n----- %s -----\n" % label)
    rc = io.stream(argv, "vacationhtml")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    rows = read_csv_rows(files["raw"])
    report = vacation_html_report(rows)
    _write_report(files["report"], VACATION_HTML_COLUMNS, report)
    _remove_quietly(files["raw"])
    io.out("\n===== DONE =====\n  %d replies read, %d are plain text\n  Report: %s\n"
           % (len(rows), len(report), files["report"]))
    if report:
        io.out("  To convert them: check the htmlmessage column, remove rows to leave "
               "alone, save, then run this task with 'Convert the replies listed in a "
               "report to HTML'.\n")


# --- Protected ranges in Google Sheets (sheetprotect, 2.89) ------------------
# Ross Scroggs' DeleteProtectedRanges.py / ExtractProtectedRanges.py.
def prepare_sheet_protect(values, log_dir):
    mode = (values.get("mode") or "find").strip()
    if mode in ("remove", "putback"):
        plan = _report_plan(values, log_dir, "sheetprotect-" + mode,
                            sheet_protect_check_report, "Sheet-ProtectedRanges-...csv")
        plan["mode"] = mode
        return plan
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = sheet_protect_steps(values, folder, _stamp())
    plan = {"mode": mode, "folder": folder, "steps": steps, "files": files,
            "owner": (values.get("owner") or "").strip().lower()}
    if mode == "copyeditors":
        plan["work"] = os.path.join(log_dir, "sheetprotect-copy-%s.json" % _stamp())
    return plan


def _sheet_ranges(path):
    ranges = sheet_protect_ranges(read_csv_rows(path))
    _remove_quietly(path)
    return ranges


def run_sheet_protect(io, plan):
    mode = plan["mode"]
    if mode in ("remove", "putback"):
        rows, remove = plan["rows"], mode == "remove"
        requests = sheet_protect_requests(rows, mode)
        word = "REMOVE" if remove else "RESTORE"
        summary = ("%s\n\nFrom: %s\n\n  %d protected ranges in %d Sheets will be %s.\n\n%s" % (
            "REMOVE PROTECTED RANGES" if remove else "PUT BACK PROTECTED RANGES",
            plan["report"], len(rows), len(requests),
            "REMOVED - anyone who can edit the Sheet can then edit those cells"
            if remove else "added again, with the same editors",
            "'Put back' with this same report undoes it." if remove else
            "A range that is already there again makes that Sheet's request fail."))
        if not io.confirm(summary, word):
            io.out("\nCanceled - nothing was changed.\n")
            return
        io.out("\n===== %s =====\n" % ("REMOVE PROTECTED RANGES" if remove else "PUT BACK"))
        io.log("SHEETPROTECT %s start: %d ranges, %d Sheets from %s"
               % (word, len(rows), len(requests), plan["report"]))
        _lines, done, rc = _run_csv_loop(
            io, plan, ["User", "spreadsheetId", "JSON"],
            [{"User": u, "spreadsheetId": s, "JSON": j} for u, s, j in requests],
            ["user", "~User", "update", "sheet", "~spreadsheetId", "json", "~JSON"],
            "sheetprotect", r"\bUpdated\b")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        io.out("\n===== SUMMARY =====\n  %d of %d Sheets updated - see the lines above "
               "for the rest (exit %s).\n" % (done, len(requests), rc))
        io.log("SHEETPROTECT %s done: %d of %d Sheets (exit %s)"
               % (word, done, len(requests), rc))
        return
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== PROTECTED RANGES IN GOOGLE SHEETS =====\n")
    raws = [argv[argv.index("redirect") + 2] for _label, argv in plan["steps"]]
    for label, argv in plan["steps"]:
        io.out("\n----- %s -----\n" % label)
        rc = io.stream(argv, "sheetprotect")
        if rc == -1:
            io.out("\nStopped.\n")
            return
    if mode == "find":
        ranges = _sheet_ranges(raws[0])
        _write_report(files["report"], SHEET_PROTECT_COLUMNS, ranges)
        io.out("\n===== DONE =====\n  %d protected ranges in %d Sheets\n  Report: %s\n"
               % (len(ranges), len({r["spreadsheetId"] for r in ranges}), files["report"]))
        if ranges:
            io.out("  To remove them: delete the rows to KEEP from the report, save, then "
                   "run this task with 'Remove the ranges listed in a report'.\n")
        return
    # copyeditors: the original's editors onto the copy's ranges (same IDs).
    original, copy = _sheet_ranges(raws[0]), _sheet_ranges(raws[1])
    body, matched, missing = sheet_copy_editor_requests(original, copy)
    if not original:
        io.out("\nThe original Sheet has no protected ranges (or could not be read) - "
               "nothing to copy.\n")
        return
    if body is None:
        io.out("\nThe copy has none of the original's protected ranges (IDs %s) - "
               "nothing to copy. Was it made with Make a copy / Drive copy?\n"
               % ", ".join(missing[:10]))
        return
    summary = ("COPY PROTECTED-RANGE EDITORS\n\nFrom Sheet: %s\nTo its copy: %s\n\n"
               "  %d protected ranges get the original's editors.%s" % (
                   files["source"], files["copy"], matched,
                   "\n  %d of the original's ranges are not in the copy and are left out."
                   % len(missing) if missing else ""))
    if not io.confirm(summary, "COPY"):
        io.out("\nCanceled - nothing was changed.\n")
        return
    os.makedirs(os.path.dirname(plan["work"]), exist_ok=True)
    with open(plan["work"], "w", encoding="utf-8") as handle:
        handle.write(body)
    try:
        io.log("SHEETPROTECT COPY start: %d ranges to %s" % (matched, files["copy"]))
        lines = []
        rc = io.stream(["user", plan["owner"], "update", "sheet", files["copy"], "json",
                        "file", plan["work"]], "sheetprotect", collect=lines)
        ok = rc == 0 and re.search(r"\bUpdated\b", "".join(lines))
        io.out("\n===== %s =====\n  %d protected ranges in the copy now have the original's "
               "editors.\n" % ("DONE" if ok else "SEE THE LINES ABOVE", matched if ok else 0))
        io.log("SHEETPROTECT COPY done: exit %s" % rc)
    finally:
        _remove_quietly(plan["work"])


# --- Gmail filters that forward outside your domains (filterforwards, 2.88) ---
# Ross Scroggs' GetNonDomainFilterForwards.py. find = read-only report;
# delete = the report's filters, after a typed DELETE (the report stays as
# the record of what was removed).
def prepare_filter_forwards(values, log_dir):
    mode = values.get("mode") or "find"
    if mode == "delete":
        path = (values.get("csvfile") or "").strip()
        if not path or not os.path.isfile(path):
            raise ValueError("Choose the report file (Gmail-OutsideForwardFilters-...csv).")
        try:
            rows = filter_forward_check_report(read_csv_rows(path))
        except (OSError, ValueError, csv.Error) as exc:
            raise ValueError("Cannot use that file:\n" + str(exc))
        work = os.path.join(log_dir, "filter-delete-%s.csv" % _stamp())
        return {"mode": mode, "report": path, "rows": rows, "work": work}
    if mode != "find":
        raise ValueError("Choose what to do.")
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the report.")
    steps, files = filter_forward_steps(values, folder, _stamp())
    return {"mode": mode, "folder": folder, "steps": steps, "files": files,
            "own": parse_domain_list(values.get("own", ""))}


def run_filter_forwards(io, plan):
    if plan["mode"] == "find":
        files = plan["files"]
        os.makedirs(plan["folder"], exist_ok=True)
        io.out("\n===== GMAIL FILTERS FORWARDING OUTSIDE (read-only) =====\n")
        label, argv = plan["steps"][0]
        io.out("\n----- %s -----\n" % label)
        rc = io.stream(argv, "filterforwards")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        rows = read_csv_rows(files["raw"])
        found = filter_forward_rows(rows, plan["own"])
        heads = []
        for row in found:
            heads += [k for k in row if k not in heads]
        with open(files["report"], "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=heads or ["User", "id", "forward"])
            writer.writeheader()
            writer.writerows(found)
        try:
            os.remove(files["raw"])
        except OSError:
            pass
        io.out("\n===== DONE =====\n  %d filters read, %d forward outside your domains "
               "(%d users)\n  Report: %s\n" % (
                   len(rows), len(found), len({r.get("User") for r in found}),
                   files["report"]))
        if found:
            io.out("  To remove them: delete the rows to KEEP from the report, save, then "
                   "run this task with 'Delete the filters listed in a report'.\n")
        return
    rows = plan["rows"]
    summary = ("DELETE GMAIL FILTERS\n\nFrom: %s\n\n  %d filters of %d users will be "
               "DELETED.\n\nGAM cannot put a deleted filter back - the report file keeps "
               "what each one did." % (plan["report"], len(rows),
                                       len({r.get("User") for r in rows})))
    if not io.confirm(summary, "DELETE"):
        io.out("\nCanceled - nothing was changed.\n")
        return
    io.out("\n===== DELETE GMAIL FILTERS =====\n")
    try:
        os.makedirs(os.path.dirname(plan["work"]), exist_ok=True)
        with open(plan["work"], "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["User", "id"])
            writer.writerows([r["User"].strip(), r["id"].strip()] for r in rows)
        lines = []
        rc = io.stream(["csv", plan["work"], "gam", "user", "~User", "delete", "filter", "~id"],
                       "filterforwards", collect=lines)
        if rc == -1:
            io.out("\nStopped.\n")
            return
        done = len(re.findall(r"\bDeleted\b", "".join(lines)))
        io.out("\n===== SUMMARY =====\n  %d of %d deleted ('Deleted') - see the lines above "
               "for the rest (exit %s).\n" % (done, len(rows), rc))
    finally:
        try:
            os.remove(plan["work"])
        except OSError:
            pass


# --- Users and Chromebooks per OU (oucounts, 2.88) ------------------------------
# Ross Scroggs' GetOrgUnitUserCounts / GetOrgUnitCrOSCounts /
# GetOrgUnitUserCrOSCounts: GAM lists, GAMGUI counts per OU. Read-only.
def prepare_ou_counts(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = ou_counts_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files,
            "what": values.get("what") or "both"}


def run_ou_counts(io, plan):
    files, steps = plan["files"], plan["steps"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== USERS AND CHROMEBOOKS PER OU (read-only) =====\n")
    for number, (label, argv) in enumerate(steps, 1):
        io.out("\n----- Step %d of %d: %s -----\n" % (number, len(steps), label))
        rc = io.stream(argv, "oucounts")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        if number == 1 and rc != 0:
            io.out("\nStopping: the OUs could not be listed (exit %s).\n" % rc)
            return
    heads, rows = ou_counts_report(read_csv_rows(files["ous"]), read_csv_rows(files["users"]),
                                   read_csv_rows(files["cros"]), plan["what"])
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=heads)
        writer.writeheader()
        writer.writerows(rows)
    for key in ("ous", "users", "cros"):
        try:
            os.remove(files[key])
        except OSError:
            pass
    io.out("\n===== DONE =====\n  %d OUs - report: %s\n" % (len(rows), files["report"]))


# --- Compare users with a group (groupcompare, 2.88) ----------------------------
# Ross Scroggs' CheckMembership.py / GetUsersNotInGroup.py / CheckOUGroup-
# Membership.py: two read-only GAM lists, compared here. Read-only.
def prepare_group_compare(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = group_compare_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files}


def run_group_compare(io, plan):
    files, steps = plan["files"], plan["steps"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== COMPARE USERS WITH A GROUP (read-only) =====\n")
    for number, (label, argv) in enumerate(steps, 1):
        io.out("\n----- Step %d of %d: %s -----\n" % (number, len(steps), label))
        rc = io.stream(argv, "groupcompare")
        if rc == -1:
            io.out("\nStopped.\n")
            return
    users = read_csv_rows(files["users"])
    members = read_csv_rows(files["members"])
    if not users or not members:
        # An empty side would list EVERYONE on the other side as missing.
        io.out("\nStopping: %s came back empty - nothing to compare (see the lines "
               "above).\n" % ("the user list" if not users else "the group's member list"))
        return
    rows = group_compare_report(users, members)
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GROUP_COMPARE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    for key in ("users", "members"):
        try:
            os.remove(files[key])
        except OSError:
            pass
    missing = sum(1 for r in rows if r["status"].startswith("in the users"))
    io.out("\n===== DONE =====\n  %d users checked, %d group members\n"
           "  %d in the users but NOT in the group\n  %d in the group but NOT in the users\n"
           "  Report: %s\n" % (len(users), len(members), missing, len(rows) - missing,
                               files["report"]))


# --- Who has access to each file (fileroles, 2.88) ------------------------------
# Ross Scroggs' GetSharedFilePermissionsTypeRoleLists.py: one GAM command,
# then one row per file with the sharing grouped by type and role. Read-only.
def prepare_file_roles(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = file_roles_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files, "values": dict(values)}


def run_file_roles(io, plan):
    files = plan["files"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== WHO HAS ACCESS TO EACH FILE (read-only) =====\n")
    label, argv = plan["steps"][0]
    io.out("\n----- %s -----\n" % label)
    rc = io.stream(argv, "fileroles")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    gam_rows = read_csv_rows(files["raw"])
    if rc != 0 and not gam_rows:
        io.out("\nStopping: the files could not be read (exit %s).\n" % rc)
        return
    heads, rows = file_roles_report(gam_rows, plan["values"])
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=heads)
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.remove(files["raw"])          # the report replaces GAM's file
    except OSError:
        pass
    io.out("\n===== DONE =====\n  %d shared files - report: %s\n" % (len(rows), files["report"]))


# --- Shared Drive members with groups expanded (sdexpand, 2.87) ---------------
# Ross Scroggs' ExpandSharedDriveGroupMembers.py / GetTeamDriveACLsExpandGroups.py:
# drive members -> the groups among them -> their people (recursive) -> one
# report with each group replaced by its people. Read-only.
def prepare_sd_expand(values):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    steps, files = sd_expand_steps(values, folder, _stamp())
    return {"folder": folder, "steps": steps, "files": files,
            "keep_group": (values.get("keepgroup") or "no") == "yes"}


def run_sd_expand(io, plan):
    files, steps = plan["files"], plan["steps"]
    os.makedirs(plan["folder"], exist_ok=True)
    io.out("\n===== SHARED DRIVE MEMBERS WITH GROUPS EXPANDED (read-only) =====\n")
    io.out("\n----- Step 1 of 2: %s -----\n" % steps[0][0])
    rc = io.stream(steps[0][1], "sdexpand")
    if rc == -1:
        io.out("\nStopped.\n")
        return
    members = read_csv_rows(files["members"])
    if rc != 0 and not members:
        io.out("\nStopping: the Shared Drives could not be read (exit %s).\n" % rc)
        return
    groups = sd_expand_groups(members)
    group_rows = []
    if groups:
        with open(files["groups"], "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["group"])
            writer.writerows([g] for g in groups)
        io.out("\n----- Step 2 of 2: %s (%d groups) -----\n" % (steps[1][0], len(groups)))
        rc = io.stream(steps[1][1], "sdexpand")
        if rc == -1:
            io.out("\nStopped.\n")
            return
        group_rows = read_csv_rows(files["groupmembers"])
    else:
        io.out("\nNo Shared Drive has a group as a member - nothing to expand.\n")
    rows = sd_expand_report(members, group_rows, plan["keep_group"])
    with open(files["report"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SD_EXPAND_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    for key in ("members", "groups", "groupmembers"):
        try:
            os.remove(files[key])            # GAM's raw files built the report
        except OSError:
            pass
    io.out("\n===== DONE =====\n  %d rows (%d of them people found through %d groups)\n"
           "  Report: %s\n" % (len(rows), sum(1 for r in rows if r["via_group"]),
                               len(groups), files["report"]))


# --- Upgrade Shared Drive Contributors to Content managers (sdwriters, 2.87) ---
# Ross Scroggs' UpgradeWritersToContentManagers.py, done by GAM now. Upgrade:
# list the Contributors (read-only), save them as a record, ask for UPGRADE,
# then change each one. Put back: the record file -> Contributor again.
def prepare_sd_writers(values):
    mode = values.get("mode") or "upgrade"
    if mode == "undo":
        path = (values.get("csvfile") or "").strip()
        if not path:
            raise ValueError("Choose the record file (SharedDrives-Contributors-"
                             "...csv) to put back.")
        if not os.path.isfile(path):
            raise ValueError("That record file does not exist:\n" + path)
        try:
            rows = sd_writers_check_record(read_csv_rows(path))
        except (OSError, ValueError, csv.Error) as exc:
            raise ValueError("Cannot use that file:\n" + str(exc))
        return {"mode": mode, "record": path, "rows": rows,
                "command": sd_writers_command(path, mode)}
    if mode != "upgrade":
        raise ValueError("Choose what to do.")
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the record file.")
    step, files = sd_writers_read_step(values, folder, _stamp())
    return {"mode": mode, "folder": folder, "step": step, "files": files,
            "record": files["record"], "command": sd_writers_command(files["record"], mode)}


def run_sd_writers(io, plan):
    mode, record = plan["mode"], plan["record"]
    if mode == "upgrade":
        os.makedirs(plan["folder"], exist_ok=True)
        io.out("\n===== UPGRADE SHARED DRIVE CONTRIBUTORS TO CONTENT MANAGERS =====\n")
        label, argv = plan["step"]
        io.out("\n----- Step 1 of 2: %s (read-only) -----\n" % label)
        rc = io.stream(argv, "sdwriters")
        if rc == -1:
            io.out("\nStopped - nothing was changed.\n")
            return
        gam_rows = read_csv_rows(plan["files"]["gam"])
        if rc != 0 and not gam_rows:
            io.out("\nStopping: the Shared Drives could not be read (exit %s) - "
                   "nothing was changed.\n" % rc)
            return
        rows = sd_writers_record(gam_rows)
        try:
            os.remove(plan["files"]["gam"])     # the record replaces GAM's file
        except OSError:
            pass
        if not rows:
            io.out("\nNo Shared Drive has a Contributor - nothing to change.\n")
            return
        # The record is written BEFORE anything changes: it is the undo.
        with open(record, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SD_WRITERS_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        io.out("Record saved: " + record + "\n")
        summary = ("MAKE CONTRIBUTORS CONTENT MANAGERS\n\n"
                   "  %d Contributors on %d Shared Drives become Content managers\n"
                   "  (they can then also move and delete files).\n\n"
                   "The list is in the record file - it puts them back:\n  %s"
                   % (len(rows), len({r["drive_id"] for r in rows}), record))
        word, step2 = "UPGRADE", "Step 2 of 2: change each one to Content manager"
    else:
        rows = plan["rows"]
        summary = ("PUT BACK CONTRIBUTORS\n\nFrom: %s\n\n"
                   "  %d members on %d Shared Drives become Contributors again."
                   % (record, len(rows), len({r["drive_id"] for r in rows})))
        word, step2 = "RESTORE", "Change each one back to Contributor"
        io.out("\n===== PUT BACK SHARED DRIVE CONTRIBUTORS =====\n")
    if not io.confirm(summary, word):
        io.out("\nCanceled - nothing was changed.%s\n"
               % (" The list is in " + record if mode == "upgrade" else ""))
        return
    io.out("\n----- %s -----\n" % step2)
    lines = []
    rc = io.stream(plan["command"], "sdwriters", collect=lines)
    if rc == -1:
        io.out("\nStopped. Whatever was changed is in the record file:\n  %s\n" % record)
        return
    done = len(re.findall(r"\bUpdated\b", "".join(lines)))
    io.out("\n===== SUMMARY =====\n  %d of %d changed ('Updated').\n"
           "  %d other results - see the lines above (exit code %s).\n"
           % (done, len(rows), max(0, len(rows) - done), rc))
    if mode == "upgrade":
        io.out("  To put them back: this task, 'Put them back as Contributors', with "
               "the record file:\n  %s\n" % record)


# --- Remove outside sharing listed in a report (unshare) ---------------------
def prepare_unshare(values, log_dir):
    # The admin trims the report CSV to the rows to act on; this removes that
    # sharing as each file's OWNER, after saving an undo file. What exactly
    # to remove is gam_catalog.unshare_plan.
    path = (values.get("csvfile") or "").strip()
    mode = values.get("mode") or UNSHARE_MODES[0]
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        actions, skipped = unshare_plan(rows, mode)
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot use that file:\n" + str(exc))
    # 2.76: a Shared Drive's own members ("drive" scope) are removed with
    # admin rights; everything else as the file's owner / organizer.
    on_files = [a for a in actions if a.get("scope") != "drive"]
    members = [a for a in actions if a.get("scope") == "drive"]
    links = sum(1 for a in on_files if a["kind"].startswith("anyone"))
    stamp = _stamp()
    undo_path = os.path.splitext(path)[0] + "-undo-" + stamp + ".csv"
    summary = ("REMOVE OUTSIDE SHARING\n\nFrom: " + path + "\n\n"
               "  %d outside people's / groups' / domains' access\n"
               "  %d 'anyone with the link' / public links\n"
               "  on %d files (removed as each file's owner or Shared Drive "
               "organizer)\n"
               "  %d outside members of Shared Drives (admin)\n"
               "  %d rows skipped (reasons are listed in the output)\n\n"
               "An undo file is saved first:\n  %s"
               % (len(on_files) - links, links,
                  len(set(a["doc_id"] for a in on_files)), len(members),
                  len(skipped), undo_path))
    return {"path": path, "actions": actions, "skipped": skipped,
            "on_files": on_files, "members": members, "undo_path": undo_path,
            "summary": summary,
            "work": os.path.join(log_dir, "unshare-work-" + stamp + ".csv"),
            "work2": os.path.join(log_dir, "unshare-members-" + stamp + ".csv")}


def run_unshare(io, plan):
    actions, undo_path = plan["actions"], plan["undo_path"]
    work, work2 = plan["work"], plan["work2"]
    try:
        if not io.confirm(plan["summary"], "REMOVE"):
            io.out("\nCanceled - nothing was changed.\n")
            return
        io.out("\n===== REMOVE OUTSIDE SHARING =====\n")
        for title, why in plan["skipped"]:
            io.out("  skipped: " + title + " - " + why + "\n")
        # The undo file is written BEFORE anything is removed.
        with open(undo_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=UNDO_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(actions)
        io.out("Undo file saved: " + undo_path + "\n")
        lines = []
        rc = 0
        for rows_now, work_now, argv in (
                (plan["on_files"], work, ["gam", "user", "~owner", "delete",
                                          "drivefileacl", "~doc_id", "~perm"]),
                (plan["members"], work2, ["gam", "delete", "drivefileacl",
                                          "~doc_id", "~perm"])):
            if not rows_now:
                continue
            os.makedirs(os.path.dirname(work_now), exist_ok=True)
            with open(work_now, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["owner", "doc_id", "perm"])
                for a in rows_now:
                    writer.writerow([a["owner"], a["doc_id"], a["perm"]])
            rc_now = io.stream(["csv", work_now] + argv, "unshare", collect=lines)
            if rc_now == -1:
                io.out("\nStopped. Whatever was removed is in the undo file.\n")
                return
            rc = rc or rc_now
        text = "".join(lines)
        done = len(re.findall(r"\bDeleted\b", text))
        # "Delete Failed: Does not exist" (checked with real GAM) = the file
        # or that access is already gone - nothing to do.
        gone = len(re.findall(r"Does not exist", text))
        io.out("\n===== SUMMARY =====\n  %d of %d removed ('Deleted').\n"
               "  %d already gone ('Does not exist').\n"
               "  %d other results - see the lines above (exit code %s).\n  "
               "To put it all back: Drive > Put back sharing from an undo file > "
               "%s\n" % (done, len(actions), gone,
                         max(0, len(actions) - done - gone), rc, undo_path))
    finally:
        for temp in (work, work2):
            try:
                os.remove(temp)
            except OSError:
                pass


# --- Put back sharing from an undo file (reshare) ---------------------------
def prepare_reshare(values, log_dir):
    path = (values.get("csvfile") or "").strip()
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        commands = reshare_commands(rows)
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot use that file:\n" + str(exc))
    summary = ("PUT BACK SHARING\n\nFrom: " + path + "\n\n"
               + "".join("  %d %s\n" % (len(r), RESHARE_NAMES.get(kind, kind))
                         for kind, r, _argv in commands)
               + "\nNo notification emails are sent.")
    return {"path": path, "commands": commands, "summary": summary,
            "log_dir": log_dir, "stamp": _stamp()}


def run_reshare(io, plan):
    temps = []
    results = []
    try:
        if not io.confirm(plan["summary"], "RESTORE"):
            io.out("\nCanceled - nothing was changed.\n")
            return
        io.out("\n===== PUT BACK SHARING =====\n")
        os.makedirs(plan["log_dir"], exist_ok=True)
        for kind, kind_rows, argv in plan["commands"]:
            work = os.path.join(plan["log_dir"], "reshare-" + kind + "-"
                                + plan["stamp"] + ".csv")
            temps.append(work)
            with open(work, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=UNDO_COLUMNS[:5],
                                        extrasaction="ignore")
                writer.writeheader()
                writer.writerows(kind_rows)
            lines = []
            rc = io.stream(["csv", work] + argv, "reshare " + kind, collect=lines)
            if rc == -1:
                return
            added = len(re.findall(r"\bAdded\b", "".join(lines)))
            results.append((kind, added, len(kind_rows), rc))
        io.out("\n===== SUMMARY =====\n" + "".join(
            "  %d of %d %s put back ('Added')%s\n" % (
                added, total, RESHARE_NAMES.get(kind, kind),
                "" if added == total else " - see the lines above (exit %s)" % rc)
            for kind, added, total, rc in results))
    finally:
        for work in temps:
            try:
                os.remove(work)
            except OSError:
                pass


# --- PERMANENTLY delete a file from EVERYONE's Drive (drivewipe) ---------------
def prepare_drive_wipe(values, log_dir):
    # Search Drives for a file by NAME or ID, then permanently delete every
    # OWNED copy that matched (one parallel pass over just those owners).
    findby = (values.get("findby", "name") or "").strip() or "name"
    fileref = (values.get("fileref", "") or "").strip()
    if not fileref:
        raise ValueError("Enter a file name or file ID.")
    scopetype, scopeval, scope_entity, thread_prefix, label = _scope(values, "all")
    if scopetype != "all" and not scopeval:
        raise ValueError("The chosen search scope needs a value (domain, OU "
                         "path, or group email).")
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
    return {"log_dir": log_dir, "scope_entity": scope_entity,
            "thread_prefix": thread_prefix, "scope_label": label,
            "search": search, "what": what}


def run_drive_wipe(io, plan):
    thread_prefix, what = plan["thread_prefix"], plan["what"]
    work_dir = new_folder(plan["log_dir"], "DriveWipe_")
    match_csv = os.path.join(work_dir, "MatchedFiles.csv")
    targets_csv = os.path.join(work_dir, "DeleteTargets.csv")
    io.out("\n===== PHASE 1: SEARCH DRIVES (" + plan["scope_label"] + ") =====\n"
           "Looking for " + what + "\n")
    rc = io.stream(thread_prefix + ["redirect", "csv", match_csv]
                   + plan["scope_entity"] + plan["search"], "drive search")
    if rc == -1:
        io.out("\n[canceled - nothing changed]\n")
        return
    if not os.path.isfile(match_csv):
        io.out("\n[stopped: search produced no results file - check "
               "authorization and the value]\n")
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
    io.out("\nFound " + str(len(targets)) + " owned copy/copies. Evidence: "
           + match_csv + "\n")
    if not targets:
        io.out("\nNo owned copies matched - nothing to remove. Done.\n")
        return
    if not io.confirm(str(len(targets)) + " owned Drive file(s) matched " + what
                      + ".\n\nExamples:\n  " + "\n  ".join(sample)
                      + ("\n  ..." if len(targets) > len(sample) else "")
                      + "\n\nThey will be PERMANENTLY DELETED (NOT recoverable - "
                      "they do NOT go to Trash).", "DELETE"):
        io.out("\n[canceled at confirmation - nothing changed]\n")
        return
    with open(targets_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["owner", "fileid"])
        for owner, fid in targets:
            writer.writerow([owner, fid])
    io.out("\n===== PHASE 2: PERMANENTLY DELETE matched copies =====\n")
    # owner is a whole arg (~owner); the id is embedded, so ~~fileid~~.
    # 'purge' permanently deletes (verified: it does not go to Trash).
    rc = io.stream(thread_prefix + ["csv", targets_csv, "gam", "user", "~owner",
                                    "delete", "drivefile", "id:~~fileid~~", "purge"],
                   "permanently delete matched files")
    if rc == -1:
        return
    io.out("\n===== DONE ===== Permanently deleted " + str(len(targets))
           + " file(s). Evidence: " + work_dir + "\n")


# --- Remove access to an OUTSIDE file (removeextaccess) ----------------------
def prepare_remove_ext_access(values, log_dir):
    # Find every internal user (in scope) who can see an EXTERNALLY owned
    # file (by name or id), then remove each user's OWN access. Google only
    # lets a user drop their own access when they had EDIT rights, so
    # view-only external shares report an error (use the Admin console
    # Security Investigation Tool for those).
    findby = (values.get("findby", "name") or "").strip() or "name"
    fileref = (values.get("fileref", "") or "").strip()
    if not fileref:
        raise ValueError("Enter a file name or file ID.")
    scopetype, scopeval, scope_entity, thread_prefix, label = _scope(values, "user")
    if scopetype != "all" and not scopeval:
        raise ValueError("Enter the user(s), domain, OU, or group (only "
                         "'Everyone' may be left blank).")
    if findby == "id":
        search = ["print", "filelist", "select", "id:" + fileref,
                  "showownedby", "others", "fields", "id,name,owners"]
        what = "file ID " + fileref
    else:
        escaped = fileref.replace("\\", "\\\\").replace("'", "\\'")
        search = ["print", "filelist", "query", "name = '" + escaped + "'",
                  "showownedby", "others", "fields", "id,name,owners"]
        what = "files named '" + fileref + "'"
    return {"log_dir": log_dir, "scope_entity": scope_entity,
            "thread_prefix": thread_prefix, "scope_label": label,
            "search": search, "what": what}


def run_remove_ext_access(io, plan):
    thread_prefix, what = plan["thread_prefix"], plan["what"]
    work_dir = new_folder(plan["log_dir"], "RemoveAccess_")
    match_csv = os.path.join(work_dir, "WhoHasTheFile.csv")
    targets_csv = os.path.join(work_dir, "RemoveTargets.csv")
    io.out("\n===== PHASE 1: FIND WHO HAS IT (" + plan["scope_label"] + ") =====\n"
           "Looking for " + what + " that your users can see but do NOT own\n")
    rc = io.stream(thread_prefix + ["redirect", "csv", match_csv]
                   + plan["scope_entity"] + plan["search"], "find access")
    if rc == -1:
        io.out("\n[canceled - nothing changed]\n")
        return
    if not os.path.isfile(match_csv):
        io.out("\n[stopped: search produced no results file - check "
               "authorization and the value]\n")
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
    io.out("\nFound " + str(len(pairs)) + " internal user(s) with the file"
           + ((" - external owner: " + extowner) if extowner else "")
           + ".\nEvidence (who has it): " + match_csv + "\n")
    if not pairs:
        io.out("\nNo internal users in that scope have this file. Nothing to "
               "remove. Done.\n")
        return
    if not io.confirm(str(len(pairs)) + " internal user(s) can see " + what
                      + ".\n\nExamples:\n  " + "\n  ".join(sample)
                      + ("\n  ..." if len(pairs) > len(sample) else "")
                      + "\n\nThis will remove each user's access. NOTE: only "
                      "EDIT-shared copies can be removed this way; VIEW-ONLY "
                      "external shares will report an error - use the Admin "
                      "console Security Investigation Tool for those.", "DELETE"):
        io.out("\n[canceled at confirmation - nothing changed]\n")
        return
    with open(targets_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["user", "fileid"])
        for user, fid in pairs:
            writer.writerow([user, fid])
    io.out("\n===== PHASE 2: REMOVE ACCESS =====\n(a 'Does not exist' error for a "
           "user just means it was a view-only external share GAM cannot remove "
           "- handle those in the Admin investigation tool.)\n")
    # ~user is a whole argument (both the acting user AND the ACL scope, i.e.
    # the user removes their own permission); the file id is embedded in
    # id:... so it uses DOUBLE tildes.
    rc = io.stream(thread_prefix + ["csv", targets_csv, "gam", "user", "~user",
                                    "delete", "drivefileacl", "id:~~fileid~~", "~user"],
                   "remove access")
    if rc == -1:
        return
    io.out("\n===== DONE ===== Attempted access removal for " + str(len(pairs))
           + " user(s). Any that errored were view-only external shares (use the "
           "investigation tool). Evidence: " + work_dir + "\n")


# --- Staff departure hand-off (handoff) ------------------------------------------
def prepare_handoff(values):
    # The plan (which gam commands, in which order) comes from
    # gam_catalog.handoff_plan; this adds the confirmation text.
    plan = dict(handoff_plan(values))
    old, new = plan["old"], plan["new"]
    summary = ("STAFF DEPARTURE HAND-OFF\n\n" + old + "  ->  " + new
               + "\n\nSteps:\n" + "\n".join("  - " + label for label, _a in plan["steps"])
               + "\n\nAfterwards the old account will be:\n  " + plan["after"])
    if plan["after"] == HANDOFF_AFTER[1] and any(
            label.startswith(("Forward", "Auto-reply")) for label, _a in plan["steps"]):
        summary += ("\n\nNOTE: Google blocks new mail to a SUSPENDED account, so "
                    "forwarding and the auto-reply will NOT work after this. Choose "
                    "'Kept ACTIVE but locked' if mail should keep flowing.")
    plan["summary"] = summary
    return plan


def run_handoff(io, plan):
    # Steps that act AS the old user (mailbox delegation, calendar sharing,
    # forwarding, auto-reply) need an active account, so a suspended or
    # archived one is enabled first. Afterwards the account is locked,
    # suspended, or put back exactly as it was - and if the run stops early
    # for ANY reason, it is put back as it was (never left enabled when it
    # started disabled).
    old, new = plan["old"], plan["new"]
    changed_suspend = changed_archive = False
    finished = False
    results = []
    try:
        if not io.confirm(plan["summary"], "HANDOFF"):
            io.out("\nHand-off canceled - nothing was changed.\n")
            return
        io.out("\n===== STAFF DEPARTURE HAND-OFF: " + old + " -> " + new + " =====\n")
        state = io.user_state(old)
        if state is None:
            io.out("Could not read " + old + "'s account (does it exist?). Nothing "
                   "was changed.\n")
            return
        if io.user_state(new) is None:
            io.out("Could not read " + new + "'s account (does it exist?). Nothing "
                   "was changed.\n")
            return
        was_suspended, was_archived = state
        io.out("Original state of %s: suspended=%s archived=%s\n"
               % (old, was_suspended, was_archived))
        # Enable the account when a step (or 'kept active') needs it.
        if plan["needs_active"] or plan["after"] == HANDOFF_AFTER[0]:
            if was_archived:
                io.out("\n----- unarchiving -----\n")
                if io.stream(["update", "user", old, "archived", "off"], "unarchive") != 0:
                    io.out("Could not unarchive. Stopping.\n")
                    return
                changed_archive = True
            if was_suspended:
                io.out("\n----- unsuspending -----\n")
                if io.stream(["update", "user", old, "suspended", "off"], "unsuspend") != 0:
                    io.out("Could not unsuspend. Stopping.\n")
                    return
                changed_suspend = True
        for label, argv in plan["steps"] + plan["after_steps"]:
            io.out("\n----- " + label + " -----\n")
            # Captured (not streamed) so the text can be checked: re-running
            # a hand-off makes GAM exit 50 with "already exists" for a
            # delegate / forwarding address that is already there - the
            # result is right, so report it as "already set" instead of
            # FAILED (seen in the live test).
            rc, out = io.capture(argv)
            # Right after an account is switched back on, Gmail can still
            # call it disabled for a short while ("Delegator user is
            # disabled" - seen in the live test). Retry every 15 seconds, up
            # to 4 times, when WE just enabled it.
            tries = 0
            while (rc not in (0, -1) and (changed_suspend or changed_archive)
                   and tries < 4 and not io.cancelled()
                   and re.search(r"user is (disabled|suspended)", out, re.I)):
                tries += 1
                io.out("\nGoogle is still switching " + old + " back on - trying "
                       "again in 15 seconds (%d of 4)...\n" % tries)
                if not io.wait(15):
                    return                    # Stop pressed while waiting
                rc, out = io.capture(argv)
            if rc == -1 or io.cancelled():
                return                        # Stop pressed
            if rc != 0 and re.search(r"already exists", out, re.I):
                rc = "already"
            results.append((label, rc))
        if plan["after"] == HANDOFF_AFTER[2]:
            io.restore_state(old, changed_suspend, changed_archive)
        finished = True
    finally:
        if not finished and (changed_suspend or changed_archive):
            io.out("\nThe hand-off did not finish - putting " + old + " back the "
                   "way it was.\n")
            io.restore_state(old, changed_suspend, changed_archive)
        if results:
            io.out("\n===== HAND-OFF SUMMARY =====\n" + "".join(
                "  %-52s %s\n" % (label, "OK" if rc == 0 else
                                  "OK (was already set)" if rc == "already"
                                  else "FAILED (exit %s)" % rc)
                for label, rc in results))
            if any(label.startswith("Drive transfer") and rc == 0
                   for label, rc in results):
                io.out("  The Drive transfer continues in the background at Google; "
                       + new + " gets an email when it is done. Check it any time "
                       "with Data Transfers > show transfers.\n")


# --- Archive ALL active Classrooms (archivecourses) ----------------------------
def prepare_archive_courses(values, log_dir):
    # End of year: archive every ACTIVE Google Classroom. The list is found
    # first (read-only), ARCHIVE is typed, then 'gam csv' archives them in
    # parallel. Nothing to check in the form (it has no boxes).
    return {"log_dir": log_dir}


def run_archive_courses(io, plan):
    os.makedirs(plan["log_dir"], exist_ok=True)
    csv_path = os.path.join(plan["log_dir"], "ActiveCourses_" + _stamp() + ".csv")
    io.out("\n===== ARCHIVE ALL ACTIVE CLASSROOMS =====\nStep 1: finding active "
           "courses...\n")
    rc = io.stream(["redirect", "csv", csv_path, "print", "courses", "states", "active",
                    "fields", "id,name,ownerEmail"], "list active courses")
    if rc == -1:
        return
    if not os.path.isfile(csv_path):
        io.out("\n[stopped: could not produce the course list. Nothing was "
               "archived.]\n")
        return
    rows = [row for row in read_csv_rows(csv_path) if row.get("id")]
    if not rows:
        io.out("\nNo active courses found. Nothing to archive.\n")
        return
    io.out("\nFound " + str(len(rows)) + " active course(s). Sample:\n")
    for row in rows[:10]:
        io.out("  - " + row.get("name", "?") + "  (" + row.get("ownerEmail", "?") + ")\n")
    if len(rows) > 10:
        io.out("  ...and " + str(len(rows) - 10) + " more\n")
    if not io.confirm(str(len(rows)) + " active Classroom(s) will be ARCHIVED (hidden, "
                      "not deleted).", "ARCHIVE"):
        io.out("\n[canceled - nothing archived. The list is saved at " + csv_path + "]\n")
        return
    io.out("\nStep 2: archiving " + str(len(rows)) + " course(s) (this can take a "
           "while)...\n")
    io.stream(["csv", csv_path, "gam", "update", "course", "~id", "status", "archived"],
              "archive courses")
    io.out("\n===== DONE. The archived-course list is saved at " + csv_path + " =====\n")


# --- Retire Chromebooks: wipe, then deprovision (retire) ------------------------
_RETIRE_NAMES = {"sn": "Serial numbers", "ou": "Devices directly in OU",
                 "ou_children": "Devices in OU and its sub-OUs",
                 "query": "Devices matching"}


def prepare_retire(values, task):
    # The two commands come from gam_catalog.retire_plan (it raises
    # ValueError for a problem). check_argv: the commands whose GAM version
    # the front end checks first (the desktop asks; the browser warns).
    steps = retire_plan(task, values)
    summary = ("RETIRE CHROMEBOOKS\n\n%s: %s\n\n"
               "1. POWERWASH - each device is factory reset; all local data is "
               "wiped (devices that are off do it when they next come online).\n"
               "2. DEPROVISION - removed from management, license freed.\n\n"
               "This cannot be undone without re-enrolling each device."
               % (_RETIRE_NAMES.get(values.get("crostype"), "Devices"),
                  (values.get("crosval") or "").strip()))
    return {"steps": steps, "summary": summary,
            "check_argv": [argv for _label, argv in steps]}


def run_retire(io, plan):
    steps = plan["steps"]
    if not io.confirm(plan["summary"], "RETIRE"):
        io.out("\nCanceled - nothing was changed.\n")
        return
    io.out("\n===== RETIRE CHROMEBOOKS =====\n")
    label, argv = steps[0]
    io.out("\n----- 1 of 2: " + label + " -----\n")
    rc = io.stream(argv, "retire powerwash")
    if rc == -1:
        io.out("\nStopped - deprovisioning was NOT run.\n")
        return
    if rc != 0:
        io.out("\nThe powerwash step reported a problem (exit %s), so deprovisioning "
               "was NOT run - a deprovisioned device could no longer be wiped. Check "
               "the lines above, then run this again (devices already powerwashed "
               "simply get another powerwash request).\n" % rc)
        return
    label, argv = steps[1]
    io.out("\n----- 2 of 2: " + label + " -----\n")
    rc = io.stream(argv, "retire deprovision")
    if rc == -1:
        return
    io.out("\n===== DONE =====\n  Powerwash sent; deprovision %s.\n"
           % ("finished" if rc == 0 else
              "reported a problem (exit %s) - see the lines above" % rc))


# --- Bulk add/remove licenses (bulklicense_csv / bulklicense_sheet) -------------
def prepare_bulk_license_csv(values, log_dir):
    path = (values.get("file", "") or "").strip()
    if not path or not os.path.isfile(path):
        raise ValueError("Pick a CSV file that exists.")
    return {"path": path, "action": (values.get("action", "") or "").strip(),
            "log_dir": log_dir}


def run_bulk_license_csv(io, plan):
    with open(plan["path"], newline="", encoding="utf-8-sig") as fh:
        text = fh.read()
    _bulk_license_core(io, text, plan["action"],
                       "CSV file " + os.path.basename(plan["path"]), plan["log_dir"])


def prepare_bulk_license_sheet(values, log_dir):
    user = (values.get("user", "") or "").strip()
    fileid = (values.get("fileid", "") or "").strip()
    sheet = (values.get("sheet", "") or "").strip()
    if not (user and fileid and sheet):
        raise ValueError("Admin, sheet file ID, and tab name are all required.")
    return {"user": user, "fileid": fileid, "sheet": sheet,
            "action": (values.get("action", "") or "").strip(), "log_dir": log_dir}


def run_bulk_license_sheet(io, plan):
    # Exports the tab to a CSV with gam, then the same core as the CSV one.
    os.makedirs(plan["log_dir"], exist_ok=True)
    out_name = "BulkLicSheet_" + _stamp() + ".csv"
    out_path = os.path.join(plan["log_dir"], out_name)
    io.out("\n===== BULK LICENSES FROM GOOGLE SHEET =====\nExporting the sheet tab "
           "to CSV...\n")
    rc, _out = io.capture(["user", plan["user"], "get", "drivefile", "id:" + plan["fileid"],
                           "csvsheet", plan["sheet"], "targetfolder", plan["log_dir"],
                           "targetname", out_name, "overwrite", "true"])
    if rc != 0 or not os.path.isfile(out_path):
        io.out("\n[stopped: could not export the sheet. Check the admin, file ID, and "
               "tab name.]\n")
        return
    with open(out_path, newline="", encoding="utf-8-sig") as fh:
        text = fh.read()
    _bulk_license_core(io, text, plan["action"], "Google Sheet", plan["log_dir"])


def _bulk_license_core(io, csv_text, action, source, log_dir):
    # Parse Email / License, turn license names into SKUs, show a sample,
    # ask for the typed word (ADD / REMOVE), then 'gam csv' (in parallel).
    io.out("\nReading rows from " + source + "...\n")
    reader = csv.DictReader(io_module.StringIO(csv_text))
    headers = reader.fieldnames or []
    email_col = next((h for h in headers if h.strip().lower() == "email"), None)
    lic_col = next((h for h in headers if h.strip().lower() == "license"), None)
    if not email_col or not lic_col:
        io.out("\n[stopped: the data needs 'Email' and 'License' column headers. "
               "Found: " + (", ".join(headers) or "none") + "]\n")
        return
    pairs, unknown = [], []
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
        io.out("\nThese rows could not be understood:\n")
        for email, lic in unknown[:20]:
            io.out("  - " + email + " : license '" + lic + "'\n")
        if len(unknown) > 20:
            io.out("  ...and " + str(len(unknown) - 20) + " more\n")
        io.out("\n[stopped: " + str(len(unknown)) + " unrecognized row(s). Nothing was "
               "changed. Use a friendly license name or a SKU id in the License "
               "column.]\n")
        return
    if not pairs:
        io.out("\nNo usable rows found. Nothing to do.\n")
        return
    verb = "ADD" if action == "add" else "REMOVE"
    io.out("\n" + str(len(pairs)) + " change(s) to " + verb + ". Sample:\n")
    for email, sku in pairs[:10]:
        io.out("  - " + email + "  " + ("gets" if action == "add" else "loses")
               + " SKU " + sku + "\n")
    if len(pairs) > 10:
        io.out("  ...and " + str(len(pairs) - 10) + " more\n")
    if not io.confirm(str(len(pairs)) + " user(s) will " + verb.lower()
                      + " the listed license.", verb):
        io.out("\n[canceled - nothing changed]\n")
        return
    os.makedirs(log_dir, exist_ok=True)
    run_csv = os.path.join(log_dir, "BulkLicRun_" + _stamp() + ".csv")
    with open(run_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Email", "SKU"])
        for email, sku in pairs:
            writer.writerow([email, sku])
    io.out("\nApplying " + str(len(pairs)) + " change(s)...\n")
    io.stream(["csv", run_csv, "gam", "user", "~Email", action, "license", "~SKU"],
              "bulk license " + action)
    io.out("\n===== DONE (list saved at " + run_csv + ") =====\n")


# --- Chromebook OU rollovers (classof / gradeou) - 2.85 -------------------------
# Each front end has its own screen for finding the OUs and choosing (the
# plans come from gam_catalog.classof_plan / gradeou_plan); these are the
# shared runs. Both save a record CSV of every step and its result.
def unique_path(path):
    # 'name.csv' if free, else 'name-2.csv', 'name-3.csv'... - a record is
    # never overwritten (two runs in the same second share a time stamp).
    base, ext = os.path.splitext(path)
    number = 2
    while os.path.exists(path):
        path = "%s-%d%s" % (base, number, ext)
        number += 1
    return path


def _save_record(io, record_path, header, rows):
    try:
        os.makedirs(os.path.dirname(record_path), exist_ok=True)
        saved_to = unique_path(record_path)
        with open(saved_to, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        io.out("  Record: " + saved_to + "\n")
    except OSError as exc:
        io.out("  Could not save the record: " + str(exc) + "\n")


def _gam_text(argv):
    return "gam " + " ".join(quote_if_needed(a) for a in argv)


def run_classof(io, actions, summary, target_label, record_path, on_all_done=None):
    # The "Class of" OU rollover: actions = the plan's moves + creates.
    # Safe to run again (the plan only holds what is left; "Duplicate" from
    # create org = it is already there). on_all_done() when every step
    # finished (the front end then remembers the school year).
    results = []
    try:
        if not io.confirm(summary, "ROLLOVER"):
            io.out("\nRollover canceled - nothing was changed.\n")
            return
        io.out("\n===== CHROMEBOOK OU ROLLOVER: %s =====\n" % target_label)
        for action in actions:
            io.out("\n- " + action["text"] + "\n")
            rc, out = io.capture(action["argv"])
            if rc == -1 or io.cancelled():
                results.append((action, "stopped"))
                break
            # create org: "Duplicate" = it is already there (GAM 7.48.16
            # doCreateOrg); counts as done.
            if rc == 0:
                result = "done"
            elif re.search(r"duplicate", out, re.I):
                result = "already there"
            else:
                result = "FAILED (exit %s)" % rc
            results.append((action, result))
        done = sum(1 for _a, r in results if r in ("done", "already there"))
        failed = [a for a, r in results if r.startswith("FAILED")]
        io.out("\n===== SUMMARY =====\n  %d of %d done.\n" % (done, len(actions)))
        for action in failed:
            io.out("  FAILED: " + action["text"] + "\n")
        if len(results) < len(actions) or failed:
            io.out("  Open the rollover again and run it - only what is left is "
                   "done.\n")
        elif on_all_done is not None:
            on_all_done()
    finally:
        if results:
            _save_record(io, record_path,
                         ["action", "ou", "to_or_parent", "result", "gam_command"],
                         [[a["kind"], a.get("path", ""), a["argv"][-1], r,
                           _gam_text(a["argv"])] for a, r in results])


def run_gradeou(io, steps, summary, target_label, record_path, mark_done):
    # The grade-named OU rollover: steps = the plan's moves, highest grade
    # first. NOT repeatable (moving twice = two grades up), so mark_done(src)
    # is called right after EACH finished step - the front end saves it at
    # once - and a failed step stops the ones below it (they would mix two
    # grades).
    results = []
    try:
        if not io.confirm(summary, "ROLLOVER"):
            io.out("\nRollover canceled - nothing was changed.\n")
            return
        io.out("\n===== CHROMEBOOK GRADE ROLLOVER: %s =====\n" % target_label)
        for step in steps:
            io.out("\n- " + step["text"] + "\n")
            rc, out = io.capture(step["argv"])
            if rc == -1 or io.cancelled():
                results.append((step, "stopped"))
                break
            if rc != 0:
                results.append((step, "FAILED (exit %s)" % rc))
                io.out("\nStopping: this step failed, so the grades below it were "
                       "NOT moved (they would mix with the Chromebooks still here). "
                       "Fix the problem and run again - finished steps are "
                       "skipped.\n")
                break
            results.append((step, "done"))
            mark_done(step["src"])
        done = sum(1 for _s, r in results if r == "done")
        io.out("\n===== SUMMARY =====\n  %d of %d steps done.\n" % (done, len(steps)))
    finally:
        if results:
            _save_record(io, record_path,
                         ["from_ou", "to_ou", "grade", "chromebooks_counted", "result",
                          "gam_command"],
                         [[s["src"], s["dest"], grade_name(s["grade"]), s["devices"], r,
                           _gam_text(s["argv"])] for s, r in results])


# --- Set up an administrator (newadmin) ----------------------------------------
# The plan (the ordered GAM commands) is gam_catalog.new_admin_plan; each
# front end has its own form for it (the desktop's window, the browser's
# page). These two functions are the shared confirmation and run.
def new_admin_confirm(plan):
    # (summary, word): word "ADMIN" when it gives FULL control (Super Admin
    # or 'privileges all', which is as powerful) - else None = Yes / No.
    roles = ", ".join(plan["role_labels"])
    where = "\n".join("    " + w for w in plan["where"])
    summary = ("SET UP AN ADMINISTRATOR\n\n" + plan["email"]
               + ("  (NEW account)" if plan["created"] else "")
               + "\n\nRoles: " + roles + "\nWhere:\n" + where
               + ("\nAccess ends: " + plan["expires"] + " (UTC)" if plan["expires"] else "")
               + "\n\n%d steps. " % len(plan["steps"]))
    if plan["super"] or any(k == "role" and a[-1] == "all" for _l, a, k in plan["steps"]):
        summary += ("\n\nThis gives FULL control of the whole organization (Super "
                    "Admin or every privilege). Type ADMIN to confirm.")
        return summary, "ADMIN"
    return summary + "Run them now?", None


def run_new_admin(io, plan, word, summary, gamhelp, on_created=None):
    # Runs the plan in order. The account and a new role must exist before
    # roles can be given, so a failure there stops the run. Re-running is
    # safe: "already exists" counts as done. A role given right after the
    # account was created can fail for a short while (Google has not
    # finished creating it), so that is retried every 15 seconds, up to 4
    # times. on_created() is called at the end when a NEW account was made
    # (the front end then shows its sign-in details once).
    email = plan["email"]
    results = []
    try:
        if word and not io.confirm(summary, word):
            io.out("\nSet up an administrator canceled - nothing was changed.\n")
            return
        io.out("\n===== SET UP AN ADMINISTRATOR: " + email + " =====\n")
        for label, argv, kind in plan["steps"]:
            io.out("\n----- " + label + " -----\n")
            rc, out = io.capture(argv)
            tries = 0
            # GAM looks the account up first and prints "Does not exist"
            # while Google is still creating it (GAM 7.48.14 source:
            # convertEmailAddressToUID). Nothing else is retried - a bad OU
            # or role fails straight away.
            while (kind == "assign" and plan["created"] and rc not in (0, -1)
                   and tries < 4 and not io.cancelled()
                   and re.search(r"does not exist", out, re.I)):
                tries += 1
                io.out("\nGoogle is still setting up the new account - trying "
                       "again in 15 seconds (%d of 4)...\n" % tries)
                if not io.wait(15):
                    return
                rc, out = io.capture(argv)
            if rc == -1 or io.cancelled():
                return
            # What each step says when it was already done (seen in the live
            # test 09-28-2026): the account -> "Duplicate" / "already
            # exists"; the role assignment -> "Duplicate"; a custom role ->
            # "Another role exists with the same role name" (exit 50).
            if rc != 0 and re.search(r"already exists|duplicate|another role exists "
                                     r"with the same", out, re.I):
                rc = "already"
            results.append((label, rc))
            if kind in ("user", "role") and rc not in (0, "already"):
                io.out("\nStopping: the next steps need this one to work. Nothing "
                       "after it was run.\n")
                break
    finally:
        if results:
            io.out("\n===== SET UP AN ADMINISTRATOR - SUMMARY =====\n"
                   + "".join("  %-60s %s\n" % (label[:60], "OK" if rc == 0 else
                             "OK (was already set)" if rc == "already"
                             else "FAILED (exit %s)" % rc)
                             for label, rc in results))
            if any(rc not in (0, "already") for _l, rc in results):
                io.out("  Read GAM's message above the summary. Fix it in the form "
                       "(Run again is safe - finished steps show 'already set') "
                       "and run it again.\n")
            created_ok = any(k == "user" for _l, _a, k in plan["steps"]) and \
                results[0][1] == 0
            if gamhelp:
                io.out("\n" + gam_setup_steps(email))
            if created_ok and on_created is not None:
                on_created()


# --- Public Information Requests (2.90) ----------------------------------------
# Spec docs/2026-10-15-public-information-requests-design.md. One Vault matter
# per request; request.json in the request's folder carries every Vault ID
# between Start, Check and Close. GAMGUI's log gets the request, the step
# names and Vault IDs only - never the requestor, search words or people.
# Workflows whose GAM commands carry private details (the requestor in the
# matter name, the search words, the people searched). While one runs, the
# desktop app logs only WHICH command ran, not its arguments or output.
PRIVATE_WORKFLOWS = {"pirstart", "pircheck", "pirclose", "pirlist"}


def private_argv_label(argv):
    # 'redirect csv <file> noescapechar true create vaultquery ...' ->
    # 'create vaultquery': the command's two words, nothing private.
    words = list(argv)
    if words[:1] == ["redirect"]:
        words = words[3:]
        if words[:1] == ["multiprocess"]:
            words = words[1:]
        if words[:2] == ["noescapechar", "true"]:
            words = words[2:]
    return " ".join(words[:2])


def _pir_tag(rec):
    # How the GAMGUI log names a request: its number for a record Start made;
    # the matter ID otherwise (a matter NAME can hold the requestor).
    if rec.get("criteria"):
        return rec["request"]
    return "matter " + (rec.get("matter") or {}).get("id", "?")


def _pir_now():
    # MM-DD-YYYY HH:MM:SS (Gabe's date / time format) for the record.
    return datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")


def prepare_pir_start(values, log_dir):
    # Checks the form (pir_criteria) and builds the Yes / No question shown
    # before anything is created. values["tz"]: the browser's time zone.
    cr = pir_criteria(values, tz=(values.get("tz") or None))
    record = os.path.join(cr["request_folder"], "request.json")
    if os.path.exists(record):
        raise ValueError("%s already has a request record - use 'Check a request', or "
                         "give this request another name." % cr["request_folder"])
    emails = list(cr["scope"]["emails"])
    if cr["scope"]["type"] == "csv":
        # The CSV is read now so a wrong file / column is refused before Run.
        path, column = _csv_file_column(cr["scope"]["value"])
        # M15: checked like typed addresses, lower case, each once.
        emails = list(dict.fromkeys(
            _pir_emails(",".join(_group_list_from_csv(path, column)), "CSV column")))
        if not emails:
            raise ValueError("The CSV column '%s' is empty." % column)
    too_long = pir_accounts_too_long(emails)
    if too_long:
        raise ValueError(too_long)
    svc = ", ".join(pir_label(s) for s in cr["services"])
    who = {"people": "%d people" % len(emails), "csv": "%d people (CSV)" % len(emails),
           "group": "members of " + cr["scope"]["value"], "ou": "OU " + cr["scope"]["value"],
           "everyone": "EVERYONE in the domain - this can be very large"}[cr["scope"]["type"]]
    ask = ("Start Public Information Request %s?\n\nVault matter: %s\nServices: %s\n"
           "Whose data: %s\nDates: %s to %s\nHold: %s\n\nThis creates the matter, a saved "
           "search%s and an export for each service. Nothing is deleted." % (
               cr["request"], pir_matter_name(cr), svc, who,
               values.get("start") or "no start", values.get("end") or "no end",
               "yes" if cr["hold"] else "no", ", a hold" if cr["hold"] else ""))
    return {"criteria": cr, "record": record, "emails": emails, "ask": ask,
            "ask_title": "PUBLIC INFORMATION REQUEST"}


def _pir_save(rec, plan):
    # The record and its plain-English summary, saved after EVERY step so a
    # failure or a closed window never loses what was already created.
    pir_record_save(plan["record"], rec)
    with open(os.path.join(os.path.dirname(plan["record"]), "Request summary.txt"), "w",
              encoding="ascii", errors="replace", newline="\r\n") as handle:
        handle.write(pir_summary_text(rec))


def _pir_step(io, rec, plan, label, argv, code=None, key=None):
    # Runs one 'create ... returnidonly' step and returns the new ID, or ""
    # (Stop pressed, or GAM failed - the reason is recorded and shown; the
    # caller then stops so nothing more is created).
    if io.cancelled():
        rec["steps"].append("%s %s: STOPPED" % (_pir_now(), label))
        _pir_save(rec, plan)
        io.out("\nStopped before: %s\n" % label)
        return ""
    try:
        rc, out = io.capture(argv)
    except (OSError, ValueError) as exc:
        # The command could not even start (e.g. WinError 206, a command
        # line too long) - a recorded failure of THIS step, not a crash.
        rc, out = -9, "ERROR: GAM could not be started: %s" % exc
    # An ID means Google created it, whatever the exit code (a matter whose
    # collaborator could not be added still exists - review I1).
    new_id = pir_id_from(out)
    note = ""
    if new_id and rc != 0:
        warn = [l.strip() for l in (out or "").splitlines() if l.strip() and l.strip() != new_id]
        note = " (exit %s: %s)" % (rc, warn[-1] if warn else "see above")
        io.out("\n%s was created, but GAM also said: %s\n" % (label, warn[-1] if warn else rc))
    rec["steps"].append("%s %s: %s%s" % (_pir_now(), label, new_id or "FAILED", note))
    if new_id and code and key:
        rec["services"][code][key] = new_id
    if not new_id:
        reason = (out or "").strip().splitlines()[-1:] or ["no ID returned"]
        if code:
            rec["services"][code]["error"] = "%s: %s" % (label, reason[0])
        io.out("\n%s FAILED: %s\n" % (label, reason[0]))
    _pir_save(rec, plan)
    io.log("PIR %s %s: %s" % (_pir_tag(rec), label, new_id or "FAILED"))
    return new_id


def run_pir_start(io, plan):
    cr = plan["criteria"]
    folder = cr["request_folder"]
    # M11: the request's own folder is made only when the matter is (the
    # record save makes it); the read-only checks work in the parent.
    work = cr["folder"]
    os.makedirs(work, exist_ok=True)
    io.out("\n===== PUBLIC INFORMATION REQUEST %s =====\n" % cr["request"])
    # 1. Read-only: Vault answers, and no matter has this name yet.
    check_file = os.path.join(work, "_pirstart_matters.csv")
    rc = io.stream(pir_matters_argv(check_file), "pirstart")
    if rc == -1:
        _remove_quietly(check_file)
        io.out("\nStopped - nothing was created.\n")
        return
    rows = read_csv_rows(check_file)
    _remove_quietly(check_file)
    # A DELETED matter (Vault keeps it 30 days) is gone for this purpose.
    matters = [m for m in rows if (m.get("state") or "").upper() != "DELETED"]
    if rc != 0 and not rows:
        io.out("\nGAM could not list Vault matters (exit %s). The GAM admin needs Vault "
               "rights (Admin console > Account > Admin roles > Google Vault), and GAM "
               "needs the Vault API scope.\n" % rc)
        return
    name = pir_matter_name(cr)
    # M2: the same name, or a GAMGUI request matter for the same request
    # NUMBER with another (or no) requestor, is a duplicate.
    number = cr["request"].lower()
    same = [m for m in matters if (m.get("name") or "").strip().lower() == name.lower()
            or (PIR_MARKER in (m.get("description") or "")
                and ((m.get("name") or "").strip().lower() == number
                     or (m.get("name") or "").strip().lower().startswith(number + " - ")))]
    if same:
        io.out("\nA Vault matter for this request already exists ('%s') - nothing was "
               "created. Use 'Check a request', or another request name.\n"
               % (same[0].get("name") or "").strip())
        return
    emails = list(plan["emails"])
    if cr["scope"]["type"] == "group":
        # A group's USER members (nested groups too), read now.
        mfile = os.path.join(work, "_pirstart_members.csv")
        mrc = io.stream(pir_group_members_argv(mfile, cr["scope"]["value"]), "pirstart")
        if mrc == -1:                                  # M10: Stop, not 'no members'
            _remove_quietly(mfile)
            io.out("\nStopped - nothing was created.\n")
            return
        emails = sorted({(r.get("email") or "").strip().lower() for r in read_csv_rows(mfile)
                         if (r.get("email") or "").strip()})
        _remove_quietly(mfile)
        if not emails:
            io.out("\nThe group %s has no members who are users (or GAM could not read "
                   "it - see above) - nothing was created.\n" % cr["scope"]["value"])
            return
        too_long = pir_accounts_too_long(emails)
        if too_long:
            io.out("\n" + too_long + " Nothing was created.\n")
            return
    # The admin GAM signs in as - recorded, never logged.
    _rc, who = io.capture(["oauth", "info"])
    rec = pir_record_new(cr, _pir_now(), pir_admin_from(who))
    rec["criteria"]["scope"]["emails"] = emails
    # 2. The matter.
    matter = _pir_step(io, rec, plan, "Create the Vault matter",
                       pir_matter_argv(cr, _pir_now()[:10]))
    if not matter:
        return
    rec["matter"] = {"id": matter, "name": name}
    _pir_save(rec, plan)
    # 3. Saved searches, 4. holds, 5. counts, 6. exports - stop at the first failure.
    for code in cr["services"]:
        if not _pir_step(io, rec, plan, "%s saved search" % pir_label(code),
                         pir_query_argv(cr, code, matter, emails), code, "query"):
            return
    if cr["hold"]:
        for code in cr["services"]:
            if not _pir_step(io, rec, plan, "%s hold" % pir_label(code),
                             pir_hold_argv(cr, code, matter, emails), code, "hold"):
                return
    for code in [s for s in cr["services"] if s in ("mail", "groups")]:
        # Vault counts Gmail and Groups only; a failed count is not fatal.
        cfile = os.path.join(folder, "_counts.csv")
        crc = io.stream(pir_count_argv(cfile, matter, rec["services"][code]["query"]), "pirstart")
        rows = read_csv_rows(cfile)
        _remove_quietly(cfile)
        if crc != 0 or not rows:
            # Review I6: never record a count GAM did not make as 0 - in a
            # records request 0 reads as "nothing responsive".
            rec["services"][code]["count"] = "not counted (exit %s)" % crc
            io.out("  %s: not counted (exit %s) - the export still runs\n" % (pir_label(code), crc))
        else:
            total = sum(int(r.get("count")) for r in rows if str(r.get("count") or "").isdigit())
            errors = [r for r in rows if (r.get("error") or "").strip()]
            rec["services"][code]["count"] = total
            io.out("  %s: %d messages%s\n" % (pir_label(code), total,
                   " (%d accounts could not be counted)" % len(errors) if errors else ""))
        _pir_save(rec, plan)
    for code in cr["services"]:
        if not _pir_step(io, rec, plan, "%s export" % pir_label(code),
                         pir_export_argv(cr, code, matter, rec["services"][code]["query"]),
                         code, "export"):
            return
        rec["services"][code]["status"] = "IN_PROGRESS"
    _pir_save(rec, plan)
    io.out("\n===== STARTED =====\n  Matter: %s (%s)\n  Exports: %d - Google builds them in "
           "minutes to hours.\n  Next: 'Check a request and download its exports' with\n"
           "  %s\n" % (name, matter, len(cr["services"]), plan["record"]))


def prepare_pir_check(values, log_dir):
    # Check / Close work from the request's record (request.json), or - when
    # there is none - from a matter name or ID the admin types.
    record = (values.get("record") or "").strip().strip('"')
    matter = (values.get("matter") or "").strip()
    if record:
        rec = pir_record_load(record)                 # refuses a wrong file now
        if not (rec.get("matter") or {}).get("id"):
            raise ValueError("The Vault matter for this request was never created (see "
                             "the record's steps). Delete the request's folder and start "
                             "the request again.")
    elif not matter:
        raise ValueError("Choose the request's record (request.json), or give the "
                         "matter's name or ID.")
    return {"record": record, "matter": matter, "mode": (values.get("mode") or "check"),
            "folder": (values.get("folder") or "").strip()}


def _pir_days_left(created):
    # Vault deletes an export 15 days after it was created.
    try:
        made = datetime.datetime.strptime(created[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=datetime.timezone.utc)
    except ValueError:
        return "?"
    left = 15 - (datetime.datetime.now(datetime.timezone.utc) - made).days
    return max(0, left)


def _pir_find_matter(io, folder, text):
    # A typed matter name or ID -> (matterId, name), read-only. GAM would take
    # a bare ID as a NAME, so the ID is looked up here and passed as id:<ID>.
    lfile = os.path.join(folder, "_matters.csv")
    io.stream(pir_matters_argv(lfile), "pircheck")
    rows = [r for r in read_csv_rows(lfile) if (r.get("state") or "").upper() != "DELETED"]
    _remove_quietly(lfile)
    want = pir_matter_ref(text)
    want = want[3:] if want.lower().startswith("id:") else want
    hits = [r for r in rows if (r.get("matterId") or "") == want
            or (r.get("name") or "").strip().lower() == want.lower()]
    if not hits:
        # M8: the request NUMBER alone finds GAMGUI's request matter
        # '<number> - <requestor>' (only matters with the PIR marker).
        hits = [r for r in rows if PIR_MARKER in (r.get("description") or "")
                and (r.get("name") or "").strip().lower().startswith(want.lower() + " - ")]
    if len(hits) != 1:
        io.out("\n%s - nothing was changed.\n" % (
            "No Vault matter has that name or ID" if not hits else
            "%d Vault matters have that name - give the matter ID instead" % len(hits)))
        return None
    return hits[0].get("matterId", ""), hits[0].get("name", "")


def _pir_open(io, plan):
    # -> (record, record path, folder), or None. Without a record: a bare
    # record for the matter, kept in <folder>\<matter name>\request.json.
    if plan["record"]:
        rec = pir_record_load(plan["record"])
        return rec, plan["record"], os.path.dirname(plan["record"])
    base = plan["folder"] or "."
    os.makedirs(base, exist_ok=True)
    found = _pir_find_matter(io, base, plan["matter"])
    if not found:
        return None
    matter_id, name = found
    folder = os.path.join(base, re.sub(r'[<>:"/\\|?*]', "_", name).strip(" .")[:80] or matter_id)
    path = os.path.join(folder, "request.json")
    if os.path.exists(path):
        return pir_record_load(path), path, folder
    rec = {"marker": PIR_MARKER, "request": name, "requestor": "", "created": _pir_now(),
           "admin": "", "criteria": None, "matter": {"id": matter_id, "name": name},
           "services": {}, "steps": [], "closed": ""}
    return rec, path, folder


def _pir_label_of(name):
    # Export name '<request> - Gmail (retry 2)' -> 'Gmail'.
    label = name.rsplit(" - ", 1)[-1] if " - " in name else name
    return re.sub(r" \(retry \d+\)$", "", label)


def _pir_finish(io, rec, save_plan):
    # 'Finish the request' (review I2/I3): for a record Start made, makes
    # whatever is missing - saved searches, holds (when chosen), exports -
    # and redoes FAILED exports under a new name. Same order as Start; stops
    # at the first failure. Returns how many things it made.
    cr = rec["criteria"]
    matter = rec["matter"]["id"]
    emails = cr["scope"]["emails"]
    made = 0
    for code in cr["services"]:
        s = rec["services"][code]
        if not s["query"]:
            if not _pir_step(io, rec, save_plan, "%s saved search" % pir_label(code),
                             pir_query_argv(cr, code, matter, emails), code, "query"):
                return made
            made += 1
    if cr["hold"]:
        for code in cr["services"]:
            if not rec["services"][code]["hold"]:
                if not _pir_step(io, rec, save_plan, "%s hold" % pir_label(code),
                                 pir_hold_argv(cr, code, matter, emails), code, "hold"):
                    return made
                made += 1
    for code in cr["services"]:
        s = rec["services"][code]
        if s["export"] and s["status"] != "FAILED":
            continue
        attempt = s.get("attempt", 1) + (1 if s["export"] else 0)
        label = "%s export%s" % (pir_label(code), " (retry %d)" % attempt if attempt > 1 else "")
        if not _pir_step(io, rec, save_plan, label,
                         pir_export_argv(cr, code, matter, s["query"], attempt), code, "export"):
            return made
        s["attempt"], s["status"], s["error"] = attempt, "IN_PROGRESS", ""
        s["downloaded"] = [d for d in s["downloaded"] if d.get("export") == s["export"]]
        made += 1
    _pir_save(rec, save_plan)
    return made


def _pir_download(io, rec, save_plan, folder, code, s, eid, matter):
    # Downloads one finished export into <request folder>\<Service>. Files
    # written by this run (new, or overwritten over a partial copy - review
    # I4) are recorded with their sizes; a failed run records nothing.
    # Returns False when Stop was pressed.
    label = s["label"]
    target = os.path.join(folder, label)
    os.makedirs(target, exist_ok=True)
    began = time.time() - 2
    rc = io.stream(pir_download_argv(eid, matter, target), "pircheck")
    if rc == -1:
        io.out("\nStopped.\n")
        return False
    known = {d["file"] for d in s["downloaded"]}
    written = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        if os.path.isfile(full) and os.path.getmtime(full) >= began:
            written.append(name)
    if rc == 0 and written:
        for name in written:
            rel = os.path.join(label, name)
            if rel not in known:
                s["downloaded"].append({"export": eid, "file": rel,
                                        "bytes": os.path.getsize(os.path.join(target, name)),
                                        "when": _pir_now()})
    else:
        io.out("  %s download FAILED (exit %s) - run Check again.\n" % (label, rc))
    rec["steps"].append("%s downloaded %s export (exit %s)" % (_pir_now(), label, rc))
    io.log("PIR %s downloaded %s export %s (exit %s)" % (_pir_tag(rec), label, eid, rc))
    return True


def run_pir_check(io, plan):
    opened = _pir_open(io, plan)
    if not opened:
        return
    rec, path, folder = opened
    os.makedirs(folder, exist_ok=True)
    matter = rec["matter"]["id"]
    save_plan = {"record": path}
    io.out("\n===== %s REQUEST %s =====\n" % (
        "FINISH" if plan["mode"] == "retry" else "CHECK", rec["request"]))
    if not matter:
        io.out("\nThe Vault matter was never created (see the record's steps). Delete the "
               "folder %s and start the request again.\n" % folder)
        return
    efile = os.path.join(folder, "_exports.csv")
    if io.stream(pir_exports_argv(efile, matter), "pircheck") == -1:
        _remove_quietly(efile)
        io.out("\nStopped.\n")
        return
    rows = read_csv_rows(efile)
    _remove_quietly(efile)
    # Pair each export Vault lists with its service. A record Start made
    # knows each service's CURRENT export ID (older ones, replaced by a
    # redo, are ignored); without one, the export's name gives the service.
    pairs = []
    if rec.get("criteria"):
        by_id = {row.get("id", ""): row for row in rows}
        for code, s in rec["services"].items():
            row = by_id.get(s["export"]) if s["export"] else None
            if row is not None:
                s["status"] = (row.get("status") or "").upper()
                pairs.append((code, s, row))
    else:
        for row in rows:
            label = _pir_label_of(row.get("name", ""))
            s = rec["services"].setdefault(label, {
                "label": label, "query": "", "hold": "", "export": row.get("id", ""),
                "count": "", "status": "", "downloaded": [], "error": ""})
            s["status"] = (row.get("status") or "").upper()
            pairs.append((label, s, row))
    if plan["mode"] == "retry":
        if not rec.get("criteria"):
            io.out("\n'Finish the request' needs the request's record (request.json) - "
                   "nothing was changed.\n")
            return
        made = _pir_finish(io, rec, save_plan)
        _pir_save(rec, save_plan)
        io.out("\n===== %d made =====\n  Next: 'Check a request' to download the exports.\n"
               "  Record: %s\n" % (made, path))
        return
    if not rows:
        io.out("\nThe matter has no exports (or GAM could not list them - see above).\n")
    for code, s, row in pairs:
        status, eid = s["status"], row.get("id", "")
        words = {"COMPLETED": "done", "IN_PROGRESS": "still building",
                 "FAILED": "failed - use 'Finish the request'"}.get(status, status)
        left = _pir_days_left(row.get("createTime") or "")
        # M6: Vault deletes an export 15 days after it was made - flag the
        # last 3 days (whole days; the time zone can shift it by one).
        soon = (" - DOWNLOAD SOON" if isinstance(left, int) and left <= 3
                and not s["downloaded"] else "")
        io.out("  %-9s %s  (%s items, about %s days left%s)\n" % (
            s["label"], words, row.get("stats.exportedArtifactCount") or "?", left, soon))
        if status == "COMPLETED" and eid not in {d["export"] for d in s["downloaded"]}:
            if not _pir_download(io, rec, save_plan, folder, code, s, eid, matter):
                _pir_save(rec, save_plan)
                return
    for code, s in rec["services"].items():
        if not s["export"] and rec.get("criteria"):
            io.out("  %-9s no export yet - use 'Finish the request'\n" % s["label"])
    _pir_save(rec, save_plan)
    left = [s["label"] for s in rec["services"].values()
            if s["status"] != "COMPLETED" or not s["downloaded"]]
    io.out("\n===== %s =====\n  Record: %s\n" % (
        "COMPLETE - every export is downloaded" if not left else "Not finished: " + ", ".join(left),
        path))


def prepare_pir_close(values, log_dir):
    # Same input as Check: the record, or a matter name / ID.
    return prepare_pir_check(dict(values, mode="close"), log_dir)


def run_pir_close(io, plan):
    # After the typed word CLOSE: removes the request's holds, then closes
    # the matter. Nothing else is deleted; a closed matter can be reopened.
    opened = _pir_open(io, plan)
    if not opened:
        return
    rec, path, folder = opened
    matter = rec["matter"]["id"]
    # (service code or "", hold ID): from the record, else from Vault.
    holds = [(code, s["hold"]) for code, s in rec["services"].items() if s.get("hold")]
    if not plan["record"]:
        hfile = os.path.join(folder, "_holds.csv")
        os.makedirs(folder, exist_ok=True)
        io.stream(pir_holds_argv(hfile, matter), "pirclose")
        holds = [("", r.get("holdId")) for r in read_csv_rows(hfile) if r.get("holdId")]
        _remove_quietly(hfile)
    # Review I9: a closed matter's exports cannot be downloaded until it is
    # reopened, and Vault still deletes them 15 days after they were made.
    pending = [s["label"] for s in rec["services"].values() if not s["downloaded"]]
    warn = ("\n\nNOT DOWNLOADED YET: %s. After closing, Check cannot download them "
            "until the matter is reopened in Vault - run Check first." % ", ".join(pending)
            if pending and rec.get("criteria") else "")
    if not io.confirm("CLOSE PUBLIC INFORMATION REQUEST %s\n\nMatter: %s\n\nRemoves %d hold(s) "
                      "and closes the matter. Downloaded files and the record stay; the matter "
                      "can be reopened in Vault.%s" % (rec["request"], rec["matter"]["name"],
                                                         len(holds), warn), "CLOSE"):
        io.out("\nCanceled - nothing was changed.\n")
        return
    removed = 0
    for code, hold in holds:
        rc, _out = io.capture(pir_delete_hold_argv(hold, matter))
        if rc == 0:
            removed += 1
            if code:
                rec["services"][code]["hold"] = ""     # a second Close skips it
        rec["steps"].append("%s removed hold %s (exit %s)" % (_pir_now(), hold, rc))
        io.log("PIR %s removed hold %s (exit %s)" % (_pir_tag(rec), hold, rc))
    rc, _out = io.capture(pir_close_argv(matter))
    if rc == 0:
        rec["closed"] = _pir_now()
        rec["steps"].append("%s closed the matter" % _pir_now())
    else:                                           # M5: never 'CLOSED' when it was not
        rec["steps"].append("%s close FAILED (exit %s)" % (_pir_now(), rc))
    io.log("PIR %s closed matter %s (exit %s)" % (_pir_tag(rec), matter, rc))
    _pir_save(rec, {"record": path})
    io.out("\n===== %s =====\n  %d of %d hold(s) removed; matter %s.\n  Record: %s\n" % (
        "CLOSED" if rc == 0 and removed == len(holds) else "SEE THE LINES ABOVE",
        removed, len(holds), "closed" if rc == 0 else "NOT closed (exit %s)" % rc, path))


PIR_LIST_COLUMNS = ["request", "state", "matterId", "collaborators"]


def prepare_pir_list(values, log_dir):
    folder = (values.get("folder") or "").strip()
    if not folder:
        raise ValueError("Choose a folder for the results.")
    return {"folder": folder, "file": os.path.join(folder, "Public-Information-Requests-%s.csv"
                                                   % _stamp())}


def run_pir_list(io, plan):
    # Read-only: every matter whose description has GAMGUI's marker.
    os.makedirs(plan["folder"], exist_ok=True)
    raw = plan["file"] + ".raw"
    rc = io.stream(pir_matters_argv(raw, people=True), "pirlist")
    out = []
    for row in read_csv_rows(raw):
        if PIR_MARKER not in (row.get("description") or ""):
            continue
        who = [v for k, v in row.items()
               if re.fullmatch(r"matterPermissions\.\d+\.email", k or "") and v]
        out.append({"request": row.get("name", ""), "state": row.get("state", ""),
                    "matterId": row.get("matterId", ""), "collaborators": ", ".join(who)})
    _remove_quietly(raw)
    if rc != 0 and not out:
        io.out("\nGAM could not list Vault matters (exit %s) - see above.\n" % rc)
        return
    _write_report(plan["file"], PIR_LIST_COLUMNS, out)
    io.out("\n===== %d requests =====\n  %s\n" % (len(out), plan["file"]))


# --- The table both front ends use ------------------------------------------------
# workflow name -> (prepare, run, what the prepare function needs besides the
# form's values: "log_dir", "records_dir" or nothing).
WORKFLOWS = {
    "transferdrive": (prepare_transfer_drive, run_transfer_drive, None),
    "shareddrive": (prepare_move_to_shareddrive, run_move_to_shareddrive, "records_dir"),
    "sdscan": (prepare_sd_scan, run_sd_scan, None),
    "findsharing": (prepare_find_sharing, run_find_sharing, None),       # 2.87
    "sdeach": (prepare_sd_each, run_sd_each, None),                       # 2.87
    "sdwriters": (prepare_sd_writers, run_sd_writers, None),              # 2.87
    "sdroles": (prepare_sd_roles, run_sd_roles, None),                    # 2.87
    "sdexpand": (prepare_sd_expand, run_sd_expand, None),                 # 2.87
    "fileroles": (prepare_file_roles, run_file_roles, None),              # 2.88
    "groupcompare": (prepare_group_compare, run_group_compare, None),     # 2.88
    "oucounts": (prepare_ou_counts, run_ou_counts, None),                 # 2.88
    "filterforwards": (prepare_filter_forwards, run_filter_forwards, "log_dir"),  # 2.88
    "mailfroms": (prepare_mail_froms, run_mail_froms, None),              # 2.88
    "dupfiles": (prepare_dup_files, run_dup_files, "log_dir"),            # 2.88
    "drivedaily": (prepare_drive_daily, run_drive_daily, None),           # 2.88
    "driveaccess": (prepare_drive_access, run_drive_access, None),        # 2.88
    "browserexts": (prepare_browser_exts, run_browser_exts, None),        # 2.89
    "lastgroupmail": (prepare_last_group_mail, run_last_group_mail, None),  # 2.89
    "eventattendees": (prepare_event_attendees, run_event_attendees, None),  # 2.89
    "oldcontacts": (prepare_old_contacts, run_old_contacts, "log_dir"),     # 2.89
    "vacationhtml": (prepare_vacation_html, run_vacation_html, "log_dir"),  # 2.89
    "sheetprotect": (prepare_sheet_protect, run_sheet_protect, "log_dir"),  # 2.89
    "csvtools": (prepare_csv_tools, run_csv_tools, "task"),                 # 2.89
    "sdempty": (prepare_sd_empty, run_sd_empty, "log_dir"),                 # 2.89
    "iptrace": (prepare_ip_trace, run_ip_trace, None),                      # 2.89
    "linkclicks": (prepare_link_clicks, run_link_clicks, None),             # 2.89
    "lockmany": (prepare_lock_many, run_lock_many, None),                   # 2.89
    "foreignsignins": (prepare_foreign_signins, run_foreign_signins, None),  # 2.90
    "pirstart": (prepare_pir_start, run_pir_start, "log_dir"),            # 2.90
    "pircheck": (prepare_pir_check, run_pir_check, "log_dir"),            # 2.90
    "pirclose": (prepare_pir_close, run_pir_close, "log_dir"),            # 2.90
    "pirlist": (prepare_pir_list, run_pir_list, "log_dir"),               # 2.90
    "unshare": (prepare_unshare, run_unshare, "log_dir"),
    "reshare": (prepare_reshare, run_reshare, "log_dir"),
    "drivewipe": (prepare_drive_wipe, run_drive_wipe, "log_dir"),
    "removeextaccess": (prepare_remove_ext_access, run_remove_ext_access, "log_dir"),
    "handoff": (prepare_handoff, run_handoff, None),
    # 2.85: Year-end and bulk.
    "archivecourses": (prepare_archive_courses, run_archive_courses, "log_dir"),
    "retire": (prepare_retire, run_retire, "task"),
    "bulklicense_csv": (prepare_bulk_license_csv, run_bulk_license_csv, "log_dir"),
    "bulklicense_sheet": (prepare_bulk_license_sheet, run_bulk_license_sheet, "log_dir"),
}


def prepare(name, values, log_dir, records_dir, task=None):
    # The plan for one workflow (see WORKFLOWS); raises ValueError. task:
    # the catalog task (retire_plan needs it to tell its boxes apart).
    prep, _run, extra = WORKFLOWS[name]
    if extra == "log_dir":
        return prep(values, log_dir)
    if extra == "records_dir":
        return prep(values, records_dir)
    if extra == "task":
        return prep(values, task)
    return prep(values)
