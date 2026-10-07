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
import os
import re
import time

from gam_catalog import (
    unshare_plan, reshare_commands, UNDO_COLUMNS, RESHARE_NAMES, UNSHARE_MODES,
    sd_scan_steps, sd_build_report, SD_REPORT_COLUMNS, handoff_plan, HANDOFF_AFTER,
    gam_setup_steps, retire_plan, translate_license, grade_name, quote_if_needed,
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


# --- The table both front ends use ------------------------------------------------
# workflow name -> (prepare, run, what the prepare function needs besides the
# form's values: "log_dir", "records_dir" or nothing).
WORKFLOWS = {
    "transferdrive": (prepare_transfer_drive, run_transfer_drive, None),
    "shareddrive": (prepare_move_to_shareddrive, run_move_to_shareddrive, "records_dir"),
    "sdscan": (prepare_sd_scan, run_sd_scan, None),
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
