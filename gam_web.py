#!/usr/bin/env python3
# =============================================================================
# gam_web.py - a BROWSER version of GAMGUI for headless environments like
# Google Cloud Shell (which has no graphical display for a desktop window).
#
# It reuses GAMGUI's task catalog and command builder, serves a small web UI,
# and runs gam commands on the server. View it through Cloud Shell's
# "Web Preview" button (port 8080 by default). Standard library only.
#
# Usage:
#   python3 gam_web.py            # then click Web Preview -> port 8080
#   PORT=8081 python3 gam_web.py  # use a different Cloud Shell preview port
#
# Notes:
#   - Binds to 127.0.0.1 only (Cloud Shell's Web Preview proxies to localhost),
#     so it is not exposed on the network. It runs YOUR gam with YOUR existing
#     authorization; it stores no credentials.
#   - Multi-step "workflow" tasks: since 2.85 every one works here too -
#     Incident response (Email Cleanup); since 2.84 the Compromised account
#     response and its checklist, Find & delete from ONLY the mailboxes
#     that have it, the Mailbox takeover audit, the seven Drive sharing
#     workflows and the staff hand-off (gam_workflows.py - shared with the
#     desktop app), Set up an administrator and Edit a DLP detector; since
#     2.85 archive all Classrooms, retire Chromebooks, bulk licenses and
#     both Chromebook OU rollovers.
# =============================================================================

import os
import sys
import json
import html
import types
import csv
import collections        # 2.85: Chromebook counts per OU (rollovers)
import io as io_module    # 2.85: parse a captured CSV (rollovers)
import uuid
import datetime
import threading
import subprocess
import http.server

# --- Import GAMGUI for its DATA and LOGIC only (never opens a window) --------
# GAMGUI is a tkinter app; on a headless server tkinter may not be installed.
# Stub it so the import succeeds - we only use the task catalog and the
# command builder, and we never create a Tk window.
try:
    import tkinter  # noqa: F401
except Exception:
    class _Stub:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, _n):
            return _Stub

        def __call__(self, *a, **k):
            return _Stub()

    _tk = types.ModuleType("tkinter")
    _tk.Tk = _Stub
    _tk.StringVar = _Stub
    _tk.Text = _Stub
    _tk.Frame = _Stub
    sys.modules["tkinter"] = _tk
    for _sub in ("ttk", "messagebox", "filedialog", "scrolledtext",
                 "simpledialog"):
        _m = types.ModuleType("tkinter." + _sub)
        _m.__getattr__ = lambda _name: _Stub
        sys.modules["tkinter." + _sub] = _m
        setattr(_tk, _sub, _m)

import GAMGUI as gg   # noqa: E402  (import after the tkinter stub above)
import gam_catalog as gc  # noqa: E402  (docs links, time-zone helpers)
import gam_workflows     # noqa: E402  (2.84: Drive sharing workflows, shared)
import re             # noqa: E402
import hmac           # noqa: E402  (constant-time token comparison)
import secrets        # noqa: E402  (cryptographically strong session token)

PORT = int(os.environ.get("PORT", "8080"))

# --- Request security ---------------------------------------------------------
# /api/run executes gam commands, so ONLY this app's own page may call the API.
# Binding to 127.0.0.1 is not enough on its own: any web page open in the same
# browser could otherwise send a "simple" cross-site POST to
# http://127.0.0.1:PORT/api/run (browsers allow that without asking), and a
# DNS-rebinding page could even read our responses. Three defenses:
#   1. SESSION_TOKEN - a random secret created at startup and embedded in the
#      page this server serves. Every /api/ call must send it in the
#      X-GAMWeb-Token header. Other sites cannot read our page to learn it,
#      and a custom header forces the browser's CORS preflight, which this
#      server never approves.
#   2. POST bodies must be Content-Type: application/json (no simple requests).
#   3. The Host header must be localhost / 127.0.0.1, a Google Cloud Shell
#      Web Preview host, or a host listed in GAMWEB_ALLOWED_HOSTS (comma
#      separated) - this defeats DNS rebinding.
SESSION_TOKEN = secrets.token_urlsafe(32)
MAX_BODY = 1024 * 1024                      # 1 MB is far more than any request
_EXTRA_HOSTS = {h.strip().lower() for h in
                os.environ.get("GAMWEB_ALLOWED_HOSTS", "").split(",") if h.strip()}


def host_allowed(host_header):
    # True when the request's Host header (minus any :port) is one we serve.
    host = (host_header or "").strip().lower()
    if host.startswith("["):                 # IPv6 literal like [::1]:8080
        host = host.split("]")[0] + "]"
    else:
        host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    if host in ("127.0.0.1", "localhost", "[::1]") or host in _EXTRA_HOSTS:
        return True
    # Google Cloud Shell Web Preview hostnames.
    return host.endswith(".cloudshell.dev") or host.endswith("-dot-devshell.appspot.com")


def _resolve_gam():
    # gam_web needs the gam EXECUTABLE, not a shell alias. find_gam checks the
    # PATH and next to the app; but on Linux/Cloud Shell GAM is commonly
    # installed to ~/bin/gam7/gam and exposed only as a shell alias (which is
    # NOT on the PATH). So also accept an explicit path and check common
    # install locations.
    #   Override with:  python3 gam_web.py /path/to/gam
    #              or:  GAM_PATH=/path/to/gam python3 gam_web.py
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        return sys.argv[1]
    env = os.environ.get("GAM_PATH", "")
    if env and os.path.isfile(env):
        return env
    found = gg.find_gam("")
    if found:
        return found
    home = os.path.expanduser("~")
    for cand in (os.path.join(home, "bin", "gam7", "gam"),
                 os.path.join(home, "bin", "gam", "gam"),
                 os.path.join(home, "gam7", "gam"),
                 os.path.join(home, "gam", "gam"),
                 "/usr/local/bin/gam", "/usr/bin/gam"):
        if os.path.isfile(cand):
            return cand
    return ""


GAM = _resolve_gam()


# --- Task helpers ------------------------------------------------------------

# 2.84: desktop workflows that open their own window there and their own
# screen here (showAdmin / showDlp in the page) instead of a form.
WEB_SCREENS = ("newadmin", "dlpedit", "classof", "gradeou")   # rollovers: 2.85


def usable_tasks():
    # Every plain (non-workflow) task, as (category, index, task), in the
    # same grouped order as the desktop tree (gam_catalog.task_groups, 2.80).
    # 2.84: plus the shared Drive sharing workflows (gam_workflows).
    for cat in gg.TASKS:
        for _heading, items in gc.task_groups(cat):
            for idx, task in items:
                if task.get("workflow") in gam_workflows.WORKFLOWS \
                        or task.get("workflow") in WEB_SCREENS:
                    yield cat, idx, task
                    continue
                if task.get("workflow") or task.get("audit") or task.get("external") \
                        or task.get("interactive"):
                    continue
                yield cat, idx, task


def _group_of(cat, idx):
    # The heading a task is shown under ("" = none) - see TASK_GROUPS.
    for heading, items in gc.task_groups(cat):
        if any(i == idx for i, _t in items):
            return heading
    return ""


def tasks_json():
    # Catalog for the browser: categories -> tasks -> fields.
    cats = {}
    for cat, idx, task in usable_tasks():
        field_list = []
        for f in task["fields"]:
            vmap = f.get("valuemap")
            # Pre-fill the form's default (e.g. "My Tasks", "primary"), but not
            # a Windows path like C:\GAMExports on a Linux server (Cloud Shell).
            default = f.get("default", "") or ""
            if os.name != "nt" and re.match(r"^[A-Za-z]:\\", default):
                default = ""
            field_list.append({
                "label": f["label"],
                "key": f["key"],
                "required": f["required"],
                "default": default,
                "options": (list(vmap.keys()) if vmap
                            else (f["choices"] if f["choices"] is not None
                                  else None)),
                # 2.83: the Pick... list for this box, or None (gc.web_picker).
                "picker": gc.web_picker(task, f),
            })
        cats.setdefault(cat, []).append({
            "cat": cat, "idx": idx, "name": task["name"],
            "group": _group_of(cat, idx),
            "desc": task["desc"], "destructive": task["destructive"],
            "fields": field_list,
            # The GAM wiki page for this task (same as the desktop button).
            "doc": gc.task_doc_url(cat, task),
            # True when the task takes a local date/time that becomes UTC.
            "localtime": gc.uses_local_time(task),
            # True when "Preview (dry run)" is offered (see supports_dry_run).
            "dryrun": gc.supports_dry_run(task),
            # 2.84: a shared multi-step workflow (run as a job, see
            # workflow_start) - "" for a plain one-command task.
            "workflow": task.get("workflow") or "",
        })
    return cats


def collect(task, values):
    # Translate any friendly dropdown value back to the gam value (valuemap).
    out = {}
    for f in task["fields"]:
        v = (values.get(f["key"], "") or "")
        vmap = f.get("valuemap")
        if vmap and v in vmap:
            v = vmap[v]
        out[f["key"]] = v
    return out


_GAM_VERSION = []


def gam_version():
    # The installed GAM's version line ("GAM 7.48.21 - ..."), asked once
    # ('gam version' only reads local files) and kept; "" if unknown.
    if not _GAM_VERSION:
        text = ""
        if GAM:
            try:
                done = subprocess.run([GAM, "version"], capture_output=True,
                                      text=True, encoding="utf-8",
                                      errors="replace", timeout=60)
                text = (done.stdout or "").strip().splitlines()[0] if done.stdout else ""
            except Exception:
                text = ""
        _GAM_VERSION.append(text)
    return _GAM_VERSION[0]


# --- Pick... lists (2.83) -------------------------------------------------------
# The same lists as the desktop pickers (gam_catalog.PICK_LISTS /
# PICK_TABLES): only those list names are accepted, each runs its own
# READ-ONLY 'gam print' command, and a searched list (mobile devices) only
# takes text that mobile_search_query accepts. Lists are kept in memory
# until the page asks for a refresh.
LIST_CACHE = {}
LIST_LOCK = threading.Lock()


def picker_tables():
    # What the page needs to draw each Pick... window (no window sizes).
    out = {}
    for kind, spec in gc.PICK_TABLES.items():
        out[kind] = {k: v for k, v in spec.items() if k != "size"}
        out[kind]["columns"] = [[col[0], col[1]] for col in spec["columns"]
                                if col[2]]          # width 0 = not shown
        if kind in gc.SEARCHED_LISTS:
            out[kind]["search_allowed"] = gc.SEARCHED_LISTS[kind]["allowed"]
            out[kind]["search_bad"] = gc.SEARCHED_LISTS[kind]["bad"]
    return out


def list_rows(data):
    # POST /api/list {kind, all, text, refresh} -> {"rows": [...]} or
    # {"error": "..."}.
    kind = str(data.get("kind") or "")
    spec = gc.PICK_TABLES.get(kind)
    if not spec:
        return {"error": "Unknown list."}
    if not GAM:
        return {"error": "gam was not found on this machine."}
    if spec.get("combine"):
        # "members": the users and groups lists (each kept on its own),
        # merged into one table with a Type column.
        parts = [list_rows({"kind": part, "refresh": data.get("refresh")})
                 for part in spec["combine"]]
        for part in parts:
            if part.get("error"):
                return part
        lists = []
        for name, part in zip(spec["combine"], parts):
            if name in ("users", "groups"):     # rows -> (email, name) pairs
                lists.append([(r["email"], r["name"]) for r in part["rows"]])
            else:
                lists.append(part["rows"])
        return {"rows": gc.combine_rows(kind, lists)}
    list_kind = kind
    if data.get("all") and spec.get("all_kind"):
        list_kind = spec["all_kind"]
    argv, parser, ok_codes, timeout = gc.PICK_LISTS[list_kind]
    if spec.get("search"):
        # One read-only search per query (gc.SEARCHED_LISTS), merged.
        queries = gc.search_queries(kind, str(data.get("text") or "")[:200])
        if not queries:
            return {"error": gc.SEARCHED_LISTS[kind]["bad"]}
        found = []
        for query in queries:
            answer = _list_once(kind, argv + ["query", query], parser, ok_codes,
                                timeout, (kind, query), data.get("refresh"))
            if answer.get("error"):
                return answer
            found.append(answer["rows"])
        return {"rows": gc.merge_search_rows(kind, found)}
    return _list_once(kind, argv, parser, ok_codes, timeout, (list_kind, ""),
                      data.get("refresh"))


def _list_once(kind, argv, parser, ok_codes, timeout, key, refresh):
    # Runs ONE read-only list command (or returns the copy kept from last
    # time) -> {"rows": [...]} or {"error": "..."}.
    if not refresh:
        with LIST_LOCK:
            cached = LIST_CACHE.get(key)
        if cached is not None:
            return {"rows": cached}
    try:
        proc = subprocess.run([GAM] + argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except Exception as exc:
        return {"error": str(exc)}
    if proc.returncode not in ok_codes:
        tail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        return {"error": tail[-400:] if tail else
                "GAM stopped with exit code %d" % proc.returncode}
    rows = gc.pick_rows(kind, parser(proc.stdout))
    with LIST_LOCK:
        LIST_CACHE[key] = rows
    return {"rows": rows}


# --- Compromised account (2.84) ------------------------------------------------
# The desktop app's guided workflow (gam_catalog.compromised_plan - the SAME
# steps) as a background job the page polls, like the incident workflow.
# Changing anything needs the typed word CONTAIN (checked here, not only in
# the page); "only collect the evidence" changes nothing. Evidence goes to
# a timestamped folder under GAMWEB_EVIDENCE_DIR (default: GAMGUI's Logs).
COMPROMISED_JOBS = {}
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def compromised_start(data):
    # POST /api/compromised/start -> {"job": id} or {"error": "..."}.
    if not GAM:
        return {"error": "gam was not found on this machine."}
    values = {k: str(data.get(k, "") or "").strip() for k in
              ("email", "contain", "deprov", "popimap", "turnoff2sv", "days",
               "from", "subject")}
    if not _EMAIL.fullmatch(values["email"]):
        return {"error": "Enter the compromised account's email address."}
    if values["contain"] not in ("lock", "suspend", "none"):
        return {"error": "Choose what to do with the account."}
    for key, default in (("deprov", "yes"), ("popimap", "yes"), ("turnoff2sv", "no")):
        if values[key] not in ("yes", "no"):
            values[key] = default
    if not values["days"].isdigit() or not 1 <= int(values["days"]) <= 180:
        return {"error": "Days of logs must be a whole number from 1 to 180."}
    if values["contain"] != "none" and str(data.get("word", "")) != "CONTAIN":
        return {"error": "Type CONTAIN to confirm - the account will be locked "
                         "and signed out."}
    job_id = uuid.uuid4().hex
    job = {"status": "running", "log": [], "values": values, "folder": ""}
    COMPROMISED_JOBS[job_id] = job
    threading.Thread(target=_compromised_worker, args=(job,), daemon=True).start()
    return {"job": job_id}


def _compromised_worker(job):
    log = job["log"]
    values = job["values"]
    email = values["email"]
    try:
        base_dir = os.environ.get("GAMWEB_EVIDENCE_DIR") or gg.LOG_DIR
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", email.split("@")[0])
        folder = base = os.path.join(base_dir, "Compromised_" + safe + "_" + stamp)
        number = 2
        while os.path.exists(folder):           # never reuse a folder
            folder = base + "_" + str(number)
            number += 1
        os.makedirs(folder)
        job["folder"] = folder
        log.append("===== COMPROMISED ACCOUNT: %s =====\nEvidence folder (on the "
                   "server): %s\n" % (email, folder))
        summary = ["Compromised account response - " + email,
                   "Started " + datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S"),
                   "Mode: " + values["contain"], ""]
        titles = {"CONTAIN": "1) CONTAIN - lock and sign out",
                  "EVIDENCE": "2) EVIDENCE (read-only) - saved to the folder",
                  "REMOVE": "3) REMOVE the attacker's footholds",
                  "SUSPEND": "4) SUSPEND"}
        phase = ""
        for step_phase, label, argv, name in gc.compromised_plan(values):
            if step_phase != phase:
                phase = step_phase
                log.append("\n===== " + titles[phase] + " =====\n")
            full = (["redirect", "csv", os.path.join(folder, name)] + argv
                    if name.endswith(".csv") else argv)
            # Log reports get a 10-minute limit (a busy account's can run
            # for a very long time), like the desktop app.
            limit = 600 if argv[0] == "report" else None
            try:
                proc = subprocess.run([GAM] + full, capture_output=True, text=True,
                                      encoding="utf-8", errors="replace", timeout=limit)
                rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
            except subprocess.TimeoutExpired:
                rc, out = -2, ""
            if name and not name.endswith(".csv"):
                with open(os.path.join(folder, name), "w", encoding="utf-8",
                          newline="\r\n") as fh:
                    fh.write(out)
            state = gc.compromised_step_state(rc, out)
            log.append("  %s: %s%s\n" % (label, state, (" -> " + name) if name else ""))
            summary.append("%-8s %-60s %s%s" % (step_phase, label, state,
                                                 ("  " + name) if name else ""))
        summary += ["", gc.COMPROMISED_CHECKLIST]
        with open(os.path.join(folder, "Summary.txt"), "w", encoding="utf-8",
                  newline="\r\n") as fh:
            fh.write("\n".join(summary) + "\n")
        with open(os.path.join(folder, "NEXT-STEPS.txt"), "w", encoding="utf-8",
                  newline="\r\n") as fh:
            fh.write(gc.COMPROMISED_CHECKLIST)
        log.append("\n===== DONE - evidence and Summary.txt in " + folder
                   + " =====\n\n" + gc.COMPROMISED_CHECKLIST)
    except Exception as exc:
        log.append("\nERROR: " + str(exc) + "\n")
    finally:
        job["status"] = "done"


def compromised_status(job_id):
    job = COMPROMISED_JOBS.get(job_id)
    if not job:
        return {"error": "unknown job"}
    return {"status": job["status"], "output": "".join(job["log"]),
            "folder": job["folder"],
            "from": job["values"]["from"], "subject": job["values"]["subject"]}


# --- Incident-response workflow (Email Cleanup) ------------------------------
# The multi-phase workflow runs in a BACKGROUND thread because domain-wide
# discovery is slow; the browser polls /api/incident/status for progress and
# posts /api/incident/confirm to approve the deletion. State lives in
# INCIDENT_JOBS keyed by a job id (single-user localhost tool).

INCIDENT_JOBS = {}


def _gam_stream(argv, out):
    # Run one gam command, appending its output lines to the job log; return rc.
    out("\n> gam " + " ".join(argv) + "\n")
    proc = subprocess.Popen([GAM] + argv, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    for line in proc.stdout:
        out(line)
    proc.wait()
    return proc.returncode


def _incident_worker(job):
    log = job["log"]

    def out(s):
        log.append(s)

    # 2.84: job["targeted"] = the desktop's "Find & PERMANENTLY delete a
    # message from ONLY the mailboxes that have it": the same search and
    # DELETE pause, no Drive sweep, no audit reports, and it never falls
    # back to a scope-wide delete.
    targeted = job.get("targeted", False)
    try:
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        base_dir = os.environ.get("GAMWEB_EVIDENCE_DIR") or gg.LOG_DIR
        incdir = base = os.path.join(base_dir, ("Cleanup_" if targeted
                                                else "Incident_") + stamp)
        number = 2
        while os.path.exists(incdir):           # never reuse a folder
            incdir = base + "_" + str(number)
            number += 1
        os.makedirs(incdir)
        job["folder"] = incdir
        match_csv = os.path.join(incdir, "MatchedMessages.csv")
        # Targeted: the plain From / Subject / Message-ID / More boxes
        # (gam_catalog.mail_query); the incident: From + Subject.
        query = job.get("query") or gg.incident_query(job["from"], job["subject"])

        # Build the scoped user selector and optional thread override. Scoping
        # to fewer mailboxes is the main speedup; config MUST precede redirect
        # (verified against gam), so thread_prefix goes first.
        stype = job.get("scopetype", "all")
        sval = job.get("scopeval", "")
        threads = job.get("threads", "")
        drivesweep = job.get("drivesweep", "off")
        attachname = job.get("attachname", "")
        scope_entity = ["all", "users"] if stype == "all" else [stype, sval]
        thread_prefix = ["config", "num_threads", threads] if threads else []
        scope_label = "all mailboxes" if stype == "all" else (stype + " " + sval)

        out("\n===== PHASE 1: SEARCH MAILBOXES (%s) =====\n"
            "This can take a while on a large scope...\n" % scope_label)
        discovery_argv = (thread_prefix + ["redirect", "csv", match_csv]
                          + scope_entity
                          + ["print", "messages", "query", query,
                             "headers", "from,to,subject,message-id,date"])
        # When a Drive sweep is requested, also capture attachment names.
        if drivesweep != "off":
            discovery_argv += ["attachmentnamepattern", ".*", "showattachments"]
        rc = _gam_stream(discovery_argv, out)
        if not os.path.isfile(match_csv):
            out("\n[stopped: discovery produced no results file - check "
                "authorization and the query]\n")
            job["status"] = "done"
            return
        if rc != 0:
            out("\n[note] discovery finished with some per-mailbox errors "
                "(rc=%d). Normal on a large domain - suspended/unlicensed "
                "mailboxes are skipped. Continuing.\n" % rc)

        hits, users, msgids = [], set(), set()
        with open(match_csv, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                hits.append(row)
                if row.get("User"):
                    users.add(row["User"])
                if row.get("Message-ID"):
                    msgids.add(row["Message-ID"])
        job["count"] = len(hits)
        job["mailboxes"] = len(users)
        job["msgids"] = sorted(msgids)
        out("\nFound %d message(s) in %d mailbox(es); %d unique Message-ID(s).\n"
            "Evidence saved to: %s\n" % (len(hits), len(users), len(msgids),
                                         match_csv))
        if not hits:
            out("\nNothing matched - no deletion needed. Workflow complete.\n")
            job["status"] = "done"
            return

        # ---- Drive attachment search (read-only, before confirmation) ----
        drive_matches = []          # list of (owner_email, fileid, name)
        attach_names = []
        drive_match_csv = os.path.join(incdir, "DriveAttachmentMatches.csv")
        if drivesweep == "manual" and attachname:
            attach_names = [a.strip() for a in attachname.split(",") if a.strip()]
        elif drivesweep == "auto":
            seen = set()
            for row in hits:
                for col, val in row.items():
                    if col and "attachment" in col.lower() and val and val.strip():
                        for nm in val.replace("\n", ",").split(","):
                            nm = nm.strip()
                            if nm and nm.lower() not in seen:
                                seen.add(nm.lower())
                                attach_names.append(nm)
        if drivesweep != "off":
            if not attach_names:
                out("\n[Drive sweep] No attachment filename to search for "
                    "(none entered, none auto-detected). Skipping Drive.\n")
            else:
                out("\n===== DRIVE SWEEP: SEARCH (read-only) =====\n"
                    "Looking for owned Drive copies of: %s\n"
                    % ", ".join(attach_names))
                clauses = ["name = '" + n.replace("'", "\\'") + "'"
                           for n in attach_names]
                dquery = " or ".join(clauses)
                _gam_stream(thread_prefix + ["redirect", "csv", drive_match_csv]
                            + scope_entity
                            + ["print", "filelist", "query", dquery,
                               "showownedby", "me", "excludetrashed",
                               "fields", "id,name,owners,size"], out)
                if os.path.isfile(drive_match_csv):
                    with open(drive_match_csv, newline="",
                              encoding="utf-8") as fh:
                        for row in csv.DictReader(fh):
                            owner = (row.get("User")
                                     or row.get("owners.0.emailAddress")
                                     or "").strip()
                            fid = (row.get("id") or "").strip()
                            fname = (row.get("name") or "").strip()
                            if owner and fid:
                                drive_matches.append((owner, fid, fname))
                out("\nDrive matches: %d owned file(s). Evidence: %s\n"
                    % (len(drive_matches), drive_match_csv))
        job["drivematches"] = len(drive_matches)

        job["status"] = "awaiting_confirm"
        job["confirm_event"].wait()
        if not job.get("proceed"):
            out("\n[canceled at confirmation - evidence kept, nothing deleted]\n")
            job["status"] = "done"
            return

        out("\n===== PHASE 3: DELETE =====\n")
        # THE SPEEDUP: delete straight from the mailboxes discovery matched
        # (a tiny targets CSV of user+message-id), in ONE parallelized pass,
        # instead of re-scanning EVERY mailbox with "all users" for each id.
        pairs, seen_pairs = [], set()
        for row in hits:
            u = (row.get("User") or "").strip()
            mid = (row.get("Message-ID") or "").strip()
            if u and mid and (u, mid) not in seen_pairs:
                seen_pairs.add((u, mid))
                pairs.append((u, mid))
        if pairs:
            targets_csv = os.path.join(incdir, "DeleteTargets.csv")
            with open(targets_csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["user", "msgid"])
                for u, mid in pairs:
                    w.writerow([u, mid])
            matched_boxes = len(set(u for u, _ in pairs))
            out("Deleting %d message(s) from the %d matched mailbox(es) ONLY - "
                "every mailbox that did not contain the message is skipped.\n"
                % (len(pairs), matched_boxes))
            # gam: single ~field is a whole-arg replace (~user); DOUBLE ~~field~~
            # substitutes inside a larger string, so use rfc822msgid:~~msgid~~
            # (single-tilde would stay literal here and delete nothing).
            _gam_stream(thread_prefix + ["csv", targets_csv, "gam", "user",
                        "~user", "delete", "messages", "query",
                        "rfc822msgid:~~msgid~~", "max_to_delete", job["max"],
                        "doit"], out)
        elif targeted:
            # Only-the-matched-mailboxes is the promise: no user + Message-ID
            # pairs means nothing to target, so nothing is deleted.
            out("The search results had no mailbox + Message-ID pairs - "
                "nothing deleted. Evidence: %s\n" % match_csv)
        elif job["msgids"]:
            q = " OR ".join("rfc822msgid:" + m for m in job["msgids"])
            _gam_stream(thread_prefix + scope_entity
                        + ["delete", "messages", "query", q,
                           "max_to_delete", job["max"], "doit"], out)
        else:
            _gam_stream(thread_prefix + scope_entity
                        + ["delete", "messages", "query", query,
                           "max_to_delete", job["max"], "doit"], out)

        if drive_matches:
            out("\n===== PHASE 4: TRASH DRIVE ATTACHMENT COPIES =====\n")
            trashed = 0
            for owner, fid, fname in drive_matches:
                rct = _gam_stream(["user", owner, "trash", "drivefile",
                                   "id:" + fid], out)
                if rct == 0:
                    trashed += 1
            out("\nTrashed %d of %d Drive file(s) (owner's Drive Trash, "
                "recoverable ~30 days).\n" % (trashed, len(drive_matches)))

        if targeted:
            out("\n===== DONE ===== Matched mailboxes only; every other "
                "mailbox was skipped.\nEvidence: %s\n" % incdir)
            job["status"] = "done"
            return

        out("\n===== PHASE 5: AUDIT REPORTS =====\n")
        gmail_csv = os.path.join(incdir, "GmailAuditRaw.csv")
        drive_csv = os.path.join(incdir, "DriveDownloadRaw.csv")
        rc = _gam_stream(["redirect", "csv", gmail_csv, "report", "gmail",
                          "user", "all", "start", "-" + job["days"] + "d",
                          "event", "delivery",
                          "gmaileventtypes", "7,15/19,28,31,32"], out)
        if rc != 0:
            _gam_stream(["redirect", "csv", gmail_csv, "report", "gmail",
                         "user", "all", "start", "-" + job["days"] + "d",
                         "event", "delivery"], out)
        _gam_stream(["redirect", "csv", drive_csv, "report", "drive", "user",
                     "all", "start", "-" + job["days"] + "d",
                     "event", "download"], out)
        out("\n===== WORKFLOW COMPLETE =====\nAll evidence in: %s\n" % incdir)
        job["status"] = "done"
    except Exception as exc:
        out("\nWORKFLOW ERROR: " + str(exc) + "\n")
        job["status"] = "done"


def incident_start(data):
    sender = (data.get("from") or "").strip()
    subject = (data.get("subject") or "").strip()
    # 2.84: mode "targeted" = Find & delete from ONLY the mailboxes that have
    # it (see _incident_worker). Any of its four boxes is enough, but a
    # blank search is refused - it would match EVERY message.
    targeted = (data.get("mode") or "") == "targeted"
    query = ""
    if targeted:
        query = gc.mail_query(sender, subject, str(data.get("msgid") or ""),
                              str(data.get("more") or ""))
        if not query:
            return {"error": "Fill in the From address, Subject words, "
                             "Message-ID or More search words - a blank "
                             "search would match EVERY message."}
    elif not sender or not subject:
        return {"error": "From address and Subject are required."}
    days = (data.get("days") or "30").strip() or "30"
    maxd = (data.get("max") or "5000").strip() or "5000"
    if not days.isdigit() or not maxd.isdigit():
        return {"error": "Lookback days and max delete must be whole numbers."}
    # Search scope + speed. scopetype is the gam keyword sent by the page.
    scopetype = (data.get("scopetype") or "all").strip() or "all"
    scopeval = (data.get("scopeval") or "").strip()
    threads = (data.get("threads") or "").strip()
    if scopetype not in ("all", "domains", "ou_and_children", "group"):
        return {"error": "Invalid search scope."}
    if scopetype != "all" and not scopeval:
        return {"error": "The chosen search scope needs a value "
                         "(domain, OU path, or group email)."}
    if threads and not threads.isdigit():
        return {"error": "Speed (threads) must be a whole number, or blank."}
    # Optional Drive attachment sweep.
    drivesweep = (data.get("drivesweep") or "off").strip() or "off"
    attachname = (data.get("attachname") or "").strip()
    if targeted:
        drivesweep, attachname = "off", ""     # the lightweight version
    if drivesweep not in ("off", "auto", "manual"):
        return {"error": "Invalid Drive sweep option."}
    if drivesweep == "manual" and not attachname:
        return {"error": "Enter the attachment filename for the Drive sweep, "
                         "or choose auto-detect / skip."}
    job_id = uuid.uuid4().hex
    job = {"status": "running", "log": [], "from": sender, "subject": subject,
           "days": days, "max": maxd, "count": 0, "mailboxes": 0,
           "msgids": [], "confirm_event": threading.Event(),
           "scopetype": scopetype, "scopeval": scopeval, "threads": threads,
           "drivesweep": drivesweep, "attachname": attachname, "drivematches": 0,
           "targeted": targeted, "query": query, "folder": ""}
    INCIDENT_JOBS[job_id] = job
    threading.Thread(target=_incident_worker, args=(job,), daemon=True).start()
    return {"job": job_id}


def incident_status(job_id):
    job = INCIDENT_JOBS.get(job_id)
    if not job:
        return {"error": "unknown job"}
    return {"status": job["status"], "count": job["count"],
            "mailboxes": job["mailboxes"], "msgids": len(job["msgids"]),
            "drivematches": job.get("drivematches", 0),
            "folder": job.get("folder", ""),
            "output": "".join(job["log"])}


# --- Mailbox takeover audit (2.84) ---------------------------------------------
# The desktop's read-only audit of one mailbox (gam_catalog.mailbox_audit_
# checks - the SAME four show commands). Nothing changes, so it runs while
# the request waits; each command gets a 5-minute limit.
def mailbox_audit(data):
    if not GAM:
        return {"error": "gam was not found on this machine."}
    email = str(data.get("email", "") or "").strip()
    if not _EMAIL.fullmatch(email):
        return {"error": "Enter the mailbox's email address."}
    parts = ["===== MAILBOX TAKEOVER AUDIT: %s =====\nReview each section for "
             "anything the user did not set up themselves - especially "
             "forwarding to an outside address or a filter that deletes "
             "incoming mail.\n" % email]
    for label, argv in gc.mailbox_audit_checks(email):
        parts.append("\n----- %s -----\n> gam %s\n" % (label, " ".join(argv)))
        try:
            proc = subprocess.run([GAM] + argv, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=300)
            parts.append((proc.stdout or "") + (proc.stderr or ""))
        except subprocess.TimeoutExpired:
            parts.append("[stopped after 5 minutes]\n")
    parts.append("\n===== AUDIT COMPLETE =====\n")
    return {"output": "".join(parts)}


def incident_confirm(data):
    job = INCIDENT_JOBS.get(data.get("job"))
    if not job:
        return {"error": "unknown job"}
    job["proceed"] = (data.get("word") == "DELETE")
    job["confirm_event"].set()
    return {"ok": True, "proceed": job["proceed"]}


# --- Drive sharing workflows (2.84) ---------------------------------------------
# The desktop app's Drive sharing workflows (gam_workflows - the SAME steps)
# as background jobs: the page sends the task's form, the server checks it
# and plans it (gam_workflows.prepare), then runs it on a thread. When the
# workflow needs an answer (a Yes / No question, or a typed word such as
# DELETE) the job waits; the page shows the question and posts the answer.
# The server compares the typed word itself. Stop kills the running gam.
WORKFLOW_JOBS = {}


def _start_gam(argv):
    # A gam run whose WHOLE process tree Stop can end: GAM is a packaged
    # program that starts a second process, and killing only the first one
    # leaves the second running (and holding the output open). On Linux /
    # macOS it gets its own process group; on Windows taskkill /T is used.
    return subprocess.Popen([GAM] + argv, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", start_new_session=(os.name != "nt"))


def _kill_tree(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class _WebIO(gam_workflows.WorkflowIO):
    # gam_workflows' io for a browser job (see gam_workflows.WorkflowIO).
    def __init__(self, job):
        self.job = job

    def out(self, text):
        self.job["log"].append(text)

    def stream(self, argv, label, collect=None):
        if self.job["cancel"]:
            return -1
        # The echo masks any password (e.g. a new admin account's) - see
        # GAMGUI.redact_secrets; the command itself is unchanged.
        self.out("\n> gam " + gg.redact_secrets(" ".join(argv)) + "\n")
        proc = _start_gam(argv)
        self.job["proc"] = proc
        for line in proc.stdout:
            self.out(line)
            if collect is not None:
                collect.append(line)
        proc.wait()
        self.job["proc"] = None
        return -1 if self.job["cancel"] else proc.returncode

    def capture(self, argv):
        if self.job["cancel"]:
            return -1, ""
        # The echo masks any password (e.g. a new admin account's) - see
        # GAMGUI.redact_secrets; the command itself is unchanged.
        self.out("\n> gam " + gg.redact_secrets(" ".join(argv)) + "\n")
        lines = []
        rc = self.stream_quiet(argv, lines)
        out = "".join(lines)
        self.out(out)
        return rc, out

    def stream_quiet(self, argv, lines):
        # Like stream, but the output is only collected (capture shows it
        # all at once, like the desktop app).
        proc = _start_gam(argv)
        self.job["proc"] = proc
        for line in proc.stdout:
            lines.append(line)
        proc.wait()
        self.job["proc"] = None
        return -1 if self.job["cancel"] else proc.returncode

    def confirm(self, summary, word):
        # Waits for the page's answer. word None = a Yes / No question.
        job = self.job
        # Clear first, THEN check Stop: a Stop after this check sets the
        # event again, so the wait below can never hang.
        job["event"].clear()
        if job["cancel"]:
            return False
        job["answer"] = None
        # n numbers the questions so the page shows each one exactly once.
        job["asked"] = job.get("asked", 0) + 1
        job["confirm"] = {"summary": summary, "word": word or "", "n": job["asked"]}
        job["status"] = "awaiting_confirm"
        job["event"].wait()
        job["event"].clear()
        job["confirm"] = None
        job["status"] = "running"
        answer = job["answer"]
        return answer == (word or "yes") and not job["cancel"]

    def cancelled(self):
        return self.job["cancel"]

    def clear_cancel(self):
        self.job["cancel"] = False


def _web_workflow_dirs():
    # Where a browser run's evidence, undo files and records go: the
    # GAMWEB_EVIDENCE_DIR folder when set, else GAMGUI's Logs / Records.
    base = os.environ.get("GAMWEB_EVIDENCE_DIR")
    return (base or gg.LOG_DIR), (base or gg.RECORDS_DIR)


def _workflow_task(data):
    # The catalog task a request names, when it is one of the shared
    # workflows (else None).
    try:
        task = gg.TASKS[data["cat"]][int(data["idx"])]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return task if task.get("workflow") in gam_workflows.WORKFLOWS else None


def _workflow_values(task, data):
    # The form's values with dropdown words turned into gam words. The
    # Shared Drive scan's folder defaults to the evidence folder here (a
    # Windows path like C:\\GAMExports means nothing on a Linux server).
    values = collect(task, data.get("values") or {})
    if task["workflow"] == "sdscan" and not (values.get("folder") or "").strip():
        values["folder"] = _web_workflow_dirs()[0]
    return values


def workflow_check(task, data):
    # For the live preview: "" when the form is ready, else what is missing.
    log_dir, records_dir = _web_workflow_dirs()
    try:
        gam_workflows.prepare(task["workflow"], _workflow_values(task, data),
                              log_dir, records_dir, task=task)
    except ValueError as exc:
        return str(exc)
    return ""


def workflow_start(data):
    # POST /api/workflow/start -> {"job": id} or {"error": "..."}.
    if not GAM:
        return {"error": "gam was not found on this machine."}
    task = _workflow_task(data)
    if task is None:
        return {"error": "This workflow is desktop-only for now."}
    log_dir, records_dir = _web_workflow_dirs()
    try:
        os.makedirs(log_dir, exist_ok=True)
        plan = gam_workflows.prepare(task["workflow"], _workflow_values(task, data),
                                     log_dir, records_dir, task=task)
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}
    # 2.85: commands that need a newer GAM (retire) - the desktop asks
    # first; here the warning goes at the top of the confirmation.
    if plan.get("check_argv") and plan.get("summary"):
        plan["summary"] = _gam_too_old(plan["check_argv"]) + plan["summary"]
    run = gam_workflows.WORKFLOWS[task["workflow"]][1]

    def body(io):
        if plan.get("ask") and not io.confirm(plan["ask"], None):
            io.out("\nCanceled - nothing was changed.\n")
            return
        run(io, plan)
    return {"job": _start_job(body)}


def _start_job(body):
    # A new background job: body(io) runs on its own thread with a _WebIO;
    # the page polls /api/workflow/status. Returns the job id.
    job_id = uuid.uuid4().hex
    job = {"status": "running", "log": [], "cancel": False, "proc": None,
           "event": threading.Event(), "confirm": None, "answer": None}
    WORKFLOW_JOBS[job_id] = job

    def worker():
        io = _WebIO(job)
        try:
            body(io)
        except Exception as exc:
            io.out("\nWORKFLOW ERROR: " + str(exc) + "\n")
        finally:
            # "stopped", not "cancel": putting an account back clears cancel.
            if job.get("stopped"):
                io.out("\n[stopped]\n")
            job["status"] = "done"
    threading.Thread(target=worker, daemon=True).start()
    return job_id


def workflow_status(job_id):
    job = WORKFLOW_JOBS.get(job_id)
    if not job:
        return {"error": "unknown job"}
    answer = {"status": job["status"], "output": "".join(job["log"]),
              "confirm": job["confirm"], "result": job.get("result")}
    # A new admin account's sign-in details are handed over ONCE, then
    # forgotten (never in the output, the log or a later status).
    signin = job.pop("signin", None)
    if signin:
        answer["signin"] = signin
    return answer


def workflow_confirm(data):
    # The page's answer: the typed word, "yes", or "" (Cancel / No).
    job = WORKFLOW_JOBS.get(data.get("job"))
    if not job:
        return {"error": "unknown job"}
    job["answer"] = str(data.get("answer") or "")
    job["event"].set()
    return {"ok": True}


def workflow_stop(data):
    # Stop: no further steps; the running gam is ended; a waiting question
    # is answered "no". Accounts are still put back as they were.
    job = WORKFLOW_JOBS.get(data.get("job"))
    if not job:
        return {"error": "unknown job"}
    job["cancel"] = True
    job["stopped"] = True
    proc = job.get("proc")
    if proc is not None:
        _kill_tree(proc)
    job["event"].set()
    return {"ok": True}


def _read_gam(argv, timeout):
    # A read-only gam run -> (exit code, stdout, stderr); (-1, "", why) when
    # it could not run or took too long.
    try:
        proc = subprocess.run([GAM] + argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except Exception as exc:
        return -1, "", str(exc)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


# --- Edit a DLP detector's URL or word list (2.84) -------------------------------
# The desktop's DLP editor as three requests: list the detectors (read-only),
# preview a change (what is added / removed), save it (the old and new JSON
# go to the records folder FIRST, then 'gam update policy json file').
DLP_POLICIES = []


def dlp_list(data):
    if not GAM:
        return {"error": "gam was not found on this machine."}
    # 'show policies' prints one JSON line per policy with formatjson (GAM
    # 7.48.16 _showPolicy); nowarnings keeps GAM's own 'warnings' out of
    # the JSON that is sent back on Save.
    rc, out, err = _read_gam(["show", "policies", "filter",
                              "setting.type.matches('settings/detector.*')",
                              "nowarnings", "formatjson"], 600)
    if rc != 0:
        hint = gc.explain_gam_error(out + err)
        return {"error": ((err or out).strip()[-600:] or "GAM could not read the "
                          "detectors.") + ("\n\n" + hint if hint else "")}
    found = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            policy = json.loads(line)
            gc.detector_items(policy)
        except (ValueError, KeyError, TypeError):
            continue                          # not a URL / word list
        found.append(policy)
    DLP_POLICIES[:] = found
    return {"detectors": [{"id": i, "name": _dlp_name(p),
                           "word": gc.detector_items(p)[0],
                           "items": gc.detector_items(p)[1]}
                          for i, p in enumerate(found)]}


def _dlp_name(policy):
    return ((policy.get("setting") or {}).get("value", {}).get("displayName")
            or policy.get("name", ""))


def _dlp_change(data):
    # (policy, name, word, new list, added, removed); ValueError for a
    # problem the page shows.
    try:
        policy = DLP_POLICIES[int(data.get("id"))]
    except (TypeError, ValueError, IndexError):
        raise ValueError("Reload the detectors and try again.")
    name = _dlp_name(policy)
    if str(data.get("name") or "") != name:
        raise ValueError("The detector list changed - reload and try again.")
    word, old = gc.detector_items(policy)
    new = gc.detector_lines(str(data.get("text") or ""), word)
    added, removed = gc.detector_diff(old, new)
    return policy, name, word, new, added, removed


def dlp_preview(data):
    try:
        _p, name, _w, _new, added, removed = _dlp_change(data)
    except ValueError as exc:
        return {"error": str(exc)}
    if not added and not removed:
        return {"nothing": True}

    def some(items):
        text = "\n".join("    " + i for i in items[:25])
        return text + ("\n    ... and %d more" % (len(items) - 25)
                       if len(items) > 25 else "")
    return {"question": ("Change the detector '%s'?\n\nAdd %d:\n%s\n\nRemove %d:\n%s"
                         "\n\nThe old version is saved to the records folder first."
                         % (name, len(added), some(added), len(removed), some(removed)))}


def dlp_save(data):
    if not GAM:
        return {"error": "gam was not found on this machine."}
    try:
        policy, name, _w, new, added, removed = _dlp_change(data)
    except ValueError as exc:
        return {"error": str(exc)}
    if not added and not removed:
        return {"error": "Nothing changed."}
    records = _web_workflow_dirs()[1]
    stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name)[:40] or "detector"
    try:
        os.makedirs(records, exist_ok=True)
        base = os.path.join(records, "DLP-%s-%%s-%s" % (safe, stamp))
        number = 1
        while os.path.exists(base % "before" + ("_%d" % number if number > 1 else "") + ".json"):
            number += 1                   # two saves in one second: never overwrite
        suffix = ("_%d" % number if number > 1 else "") + ".json"
        before = base % "before" + suffix
        after = base % "new" + suffix
        with open(before, "w", encoding="utf-8") as handle:
            json.dump(policy, handle, indent=2)
        with open(after, "w", encoding="utf-8") as handle:
            json.dump(gc.detector_with_items(policy, new), handle, indent=2)
    except OSError as exc:
        return {"error": "Could not save the files in the records folder:\n" + str(exc)}
    argv = ["update", "policy", "json", "file", after]
    rc, out, err = _read_gam(argv, 600)
    text = ("===== EDIT DLP DETECTOR: " + name + " =====\nOld version: " + before
            + "\n\n> gam " + " ".join(argv) + "\n" + out + err)
    if rc == 0:
        text += ("\nSaved (%d added, %d removed). To undo: Access & Identity > Create "
                 "or update a Cloud Identity policy from JSON > Update, with the old "
                 "version file above.\n" % (len(added), len(removed)))
        DLP_POLICIES[int(data.get("id"))] = gc.detector_with_items(policy, new)
    else:
        text += "\nThe detector was NOT changed (exit %s) - see above.\n" % rc
    return {"output": text, "code": rc}


# --- Chromebook OU rollovers (2.85) ----------------------------------------------
# The desktop's two rollover windows as pages: "Class of" OUs (classof) and
# grade-named OUs (gradeou). Find runs as a job (reading the OU tree and
# counting the Chromebooks in each OU can take minutes); the plan is worked
# out on the SERVER from that scan and the page's choices, and Run works it
# out again (the page never sends commands). What the desktop keeps in
# gamgui.ini - the school year the OUs are set up for, and which grade-OU
# steps already ran (moving twice = two grades up) - is kept in
# gamweb-rollover.json in the records folder.
ROLLOVER_SCAN = {}
ROLLOVER_LOCK = threading.Lock()


def _rollover_state_path():
    return os.path.join(_web_workflow_dirs()[1], "gamweb-rollover.json")


def _rollover_state():
    try:
        with open(_rollover_state_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _rollover_save(key, value):
    with ROLLOVER_LOCK:
        data = _rollover_state()
        data[key] = value
        os.makedirs(os.path.dirname(_rollover_state_path()), exist_ok=True)
        with open(_rollover_state_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)


def _gradeou_done(year):
    state = _rollover_state().get("gradeou_done") or {}
    try:
        return set(state.get("done", [])) if int(state.get("year", 0)) == year else set()
    except (TypeError, ValueError):
        return set()


def rollover_years(data):
    # POST /api/rollover/years {kind} -> the year choices and defaults.
    kind = str(data.get("kind") or "")
    now = gc.school_year_now()
    if kind == "classof":
        try:
            saved = int(_rollover_state().get("classof_year") or 0) or None
        except (TypeError, ValueError):
            saved = None
        cur, tgt = gc.classof_default_years(saved)
        years = sorted(set([now + d for d in range(-3, 3)] + [cur, tgt]))
    elif kind == "gradeou":
        state = _rollover_state().get("gradeou_done") or {}
        try:
            done_year = int(state.get("year", 0)) or None
        except (TypeError, ValueError):
            done_year = None
        cur, tgt = gc.classof_default_years(done_year)
        years = sorted(set([now + d for d in range(-1, 3)] + [tgt]))
    else:
        return {"error": "Unknown rollover."}
    return {"years": [{"year": y, "label": gc.school_year_label(y)} for y in years],
            "current": cur, "target": tgt}


def rollover_scan(data):
    # POST /api/rollover/scan {kind, root, count} -> {"job": id}. Read-only:
    # the OU tree, and (gradeou always, classof when asked) the Chromebooks
    # per OU. The result is kept for the plan and shown when the job ends.
    if not GAM:
        return {"error": "gam was not found on this machine."}
    kind = str(data.get("kind") or "")
    if kind not in ("classof", "gradeou"):
        return {"error": "Unknown rollover."}
    root = str(data.get("root") or "").strip() or "/"
    count = kind == "gradeou" or bool(data.get("count"))

    def body(io):
        ROLLOVER_SCAN.pop(kind, None)
        io.out("Reading the OU tree...\n")
        argv, parser, ok_codes, timeout = gc.PICK_LISTS["ous"]
        lines = []
        rc = io.stream_quiet(argv, lines)
        if rc == -1:
            return
        if rc not in ok_codes:
            io.out("Could not read the OUs:\n" + "".join(lines)[-600:] + "\n")
            return
        paths = list(parser("".join(lines)))
        counts = {}
        if count:
            io.out("Counting the Chromebooks in each OU (this can take a minute or "
                   "two)...\n")
            lines = []
            rc = io.stream_quiet(["print", "cros", "fields", "orgunitpath"], lines)
            if rc == -1:
                return
            if rc != 0:
                if kind == "gradeou":
                    io.out("Could not count the Chromebooks:\n"
                           + "".join(lines)[-600:] + "\n")
                    return
                io.out("Could not count the Chromebooks - continuing without "
                       "counts.\n")
            else:
                counts = collections.Counter(
                    (r.get("orgUnitPath") or "").rstrip("/") or "/"
                    for r in csv.DictReader(io_module.StringIO("".join(lines))))
        scan = {"root": root, "paths": paths, "counts": counts}
        if kind == "gradeou":
            scan["found"] = gc.gradeou_discover(paths, counts, root)
            io.out("Found %d OUs named for a grade under %s.\n" % (len(scan["found"]), root))
        else:
            io.out("Read %d OUs.\n" % len(paths))
        ROLLOVER_SCAN[kind] = scan
        io.job["result"] = {"ok": True}
    return {"job": _start_job(body)}


def _year(data, key):
    try:
        return int(data.get(key))
    except (TypeError, ValueError):
        raise ValueError("Choose the school year.")


def _classof_work(data):
    # The scan + the page's choices -> everything the plan needs.
    scan = ROLLOVER_SCAN.get("classof")
    if not scan:
        raise ValueError("Click 'Find class OUs' first.")
    cur, target = _year(data, "cur_year"), _year(data, "tgt_year")
    root = scan["root"]
    templates = gc.classof_templates(scan["paths"], cur, root)
    if not templates:
        return {"templates": [], "message": "No OUs named after class years were "
                "found under " + root + "."}
    names = [t["template"] for t in templates]
    main, _v = gc.classof_main_and_variants(templates)
    chosen = str(data.get("template") or "")
    chosen = chosen if chosen in names else main
    variants = [n for n in names if n != chosen and chosen in n]
    disc = gc.classof_discover(scan["paths"], chosen, variants, cur, root=root,
                               device_counts=scan["counts"])
    known = set(disc["containers"])
    separate = {str(p) for p in (data.get("separate") or []) if str(p) in known}
    force = {str(p) for p in (data.get("force") or []) if str(p) in known}
    gmap, keep = gc.classof_grade_map(disc, separate, force)
    grad_ou = str(data.get("grad_ou") or "").strip() if data.get("grad_mode") == "move" else ""
    plan = gc.classof_plan(disc, gmap, keep, target, grad_ou)
    return {"templates": templates, "chosen": chosen, "variants": variants,
            "disc": disc, "gmap": gmap, "keep": keep, "plan": plan,
            "cur": cur, "target": target, "root": root}


def classof_plan_view(data):
    # POST /api/rollover/plan {kind: classof, ...} -> what the page shows.
    try:
        w = _classof_work(data)
    except ValueError as exc:
        return {"error": str(exc)}
    if not w["templates"]:
        return {"templates": [], "message": w["message"]}
    disc, plan, gmap = w["disc"], w["plan"], w["gmap"]
    rows = []
    for parent in sorted(disc["containers"]):
        cs = disc["containers"][parent]
        gs = sorted({c["grade"] for c in cs if -2 <= c["grade"] <= 12})
        rows.append({"path": parent,
                     "grades": (gc.grade_name(gs[0]) + "-" + gc.grade_name(gs[-1])
                                if len(gs) > 1 else gc.grade_name(gs[0]) if gs
                                else "graduated only"),
                     "classes": len(cs),
                     "devices": sum(c["devices"] for c in cs)
                     if ROLLOVER_SCAN["classof"]["counts"] else "-",
                     "keep": parent in w["keep"]})
    moves = [a for a in plan if a["kind"] == "move"]
    creates = [a for a in plan if a["kind"] == "create"]
    other = [a for a in plan if a["kind"] in ("note", "warn")]
    lines = ["For school year %s (OUs found as set up for %s): %d moves, %d new OUs"
             % (gc.school_year_label(w["target"]), gc.school_year_label(disc["fall_year"]),
                len(moves), len(creates))]
    lines += ["  " + a["text"] for a in moves + creates] or ["  (nothing to do)"]
    if other:
        lines.append("\nNotes:")
        lines += [("  WARNING: " if a["kind"] == "warn" else "  ") + a["text"] for a in other]
    lines.append("\nWhich OU holds each grade (from the OUs found):")
    lines += ["  %-3s -> %s" % (gc.grade_name(g), gmap[g]) for g in sorted(gmap)]
    return {"templates": [{"template": t["template"], "label": "%s   (e.g. '%s', %d OUs)"
                           % (t["template"], t["example"], t["ous"])} for t in w["templates"]],
            "chosen": w["chosen"],
            "extras": ("Extras: " + ", ".join(w["variants"])) if w["variants"]
            else "No extras found",
            "found": len(disc["cohorts"]), "root": w["root"], "rows": rows,
            "text": "\n".join(lines), "can_run": bool(moves or creates)}


def _gradeou_work(data):
    scan = ROLLOVER_SCAN.get("gradeou")
    if not scan:
        raise ValueError("Click 'Find grade OUs' first.")
    year = _year(data, "year")
    found = scan["found"]
    if data.get("use") is None:
        use = {f["path"] for f in found if f["suggested"]}
    else:
        use = {str(p) for p in data.get("use") or []}
    included = [f for f in found if f["path"] in use]
    mode = "leave" if data.get("grad_mode") == "leave" else "move"
    plan = gc.gradeou_plan(included, str(data.get("grad_ou") or "").strip()
                           if mode == "move" else "",
                           leave_graduated=mode == "leave", done=_gradeou_done(year))
    return {"year": year, "found": found, "use": use, "plan": plan}


def gradeou_plan_view(data):
    try:
        w = _gradeou_work(data)
    except ValueError as exc:
        return {"error": str(exc)}
    plan = w["plan"]
    moves = [s for s in plan if s["kind"] == "move"]
    lines = ["For school year %s: %d moves, highest grade first (%d Chromebooks "
             "counted)" % (gc.school_year_label(w["year"]), len(moves),
                           sum(s["devices"] for s in moves))]
    lines += ["  " + s["text"] for s in plan if s["kind"] in ("move", "done")] \
        or ["  (nothing to do - include the device OUs above)"]
    other = [s for s in plan if s["kind"] in ("warn", "note")]
    if other:
        lines.append("\nNotes:")
        lines += [("  WARNING: " if s["kind"] == "warn" else "  ") + s["text"] for s in other]
    return {"rows": [{"path": f["path"], "grade": gc.grade_name(f["grade"]),
                      "devices": f["devices"], "use": f["path"] in w["use"],
                      "why": f["why"]} for f in w["found"]],
            "text": "\n".join(lines) + "\n", "can_run": bool(moves)}


def rollover_plan(data):
    kind = str(data.get("kind") or "")
    if kind == "classof":
        return classof_plan_view(data)
    if kind == "gradeou":
        return gradeou_plan_view(data)
    return {"error": "Unknown rollover."}


def rollover_start(data):
    # POST /api/rollover/start {kind, ...the same choices as the plan}. The
    # plan is worked out AGAIN here from the scan, then run as a job that
    # asks for ROLLOVER (gam_workflows.run_classof / run_gradeou).
    if not GAM:
        return {"error": "gam was not found on this machine."}
    kind = str(data.get("kind") or "")
    records = _web_workflow_dirs()[1]
    stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
    try:
        if kind == "classof":
            w = _classof_work(data)
            if not w["templates"]:
                return {"error": w["message"]}
            moves = [a for a in w["plan"] if a["kind"] == "move"]
            creates = [a for a in w["plan"] if a["kind"] == "create"]
            if not (moves or creates):
                return {"error": "Nothing to do."}
            target = w["target"]
            summary = ("CHROMEBOOK OU ROLLOVER\n\nThe OUs are set up now for %s.\nThey "
                       "will be set up for %s.\n(If the first year is wrong, cancel and "
                       "fix it - classes would move the wrong number of grades.)\n\n%d "
                       "OUs moved to the OU for their new grade (Chromebooks inside move "
                       "with them)\n%d new OUs created\n\nThe plan and each result are "
                       "saved to the records folder."
                       % (gc.school_year_label(w["disc"]["fall_year"]),
                          gc.school_year_label(target), len(moves), len(creates)))
            summary = _gam_too_old([a["argv"] for a in moves + creates]) + summary
            record = os.path.join(records, "ChromebookOU-Rollover-%s-%s.csv"
                                  % (gc.school_year_label(target), stamp))

            def body(io):
                gam_workflows.run_classof(
                    io, moves + creates, summary, gc.school_year_label(target), record,
                    on_all_done=lambda: _rollover_save("classof_year", target))
            return {"job": _start_job(body)}
        if kind == "gradeou":
            w = _gradeou_work(data)
            steps = [s for s in w["plan"] if s["kind"] == "move"]
            if not steps:
                return {"error": "Nothing to do."}
            target = w["year"]
            summary = ("CHROMEBOOK GRADE ROLLOVER for %s\n\n%d steps, highest grade "
                       "first - about %d Chromebooks move up one grade.\nSteps already "
                       "done for this school year are skipped.\nIf a step fails, the "
                       "steps below it do NOT run (they would mix two grades).\n\nThe "
                       "plan and each result are saved to the records folder."
                       % (gc.school_year_label(target), len(steps),
                          sum(s["devices"] for s in steps)))
            summary = _gam_too_old([s["argv"] for s in steps]) + summary
            record = os.path.join(records, "ChromebookGrade-Rollover-%s-%s.csv"
                                  % (gc.school_year_label(target), stamp))

            def mark_done(src):
                # Saved right after EACH step, so a stop or a crash can never
                # make a finished step run again.
                with ROLLOVER_LOCK:
                    state = _rollover_state().get("gradeou_done") or {}
                done = list(state.get("done", [])) if state.get("year") == target else []
                if src not in done:
                    done.append(src)
                _rollover_save("gradeou_done", {"year": target, "done": done})

            def body(io):
                gam_workflows.run_gradeou(io, steps, summary,
                                          gc.school_year_label(target), record, mark_done)
            return {"job": _start_job(body)}
    except ValueError as exc:
        return {"error": str(exc)}
    return {"error": "Unknown rollover."}


# --- Set up an administrator (2.84) ----------------------------------------------
# The desktop's "Set up an administrator" window as a page. The plan is
# gam_catalog.new_admin_plan and the run is gam_workflows.run_new_admin -
# the SAME commands. The roles (and which are Super Admin) are read by the
# SERVER, never taken from the page. A new account's password is masked in
# every echo and handed to the page once at the end (workflow_status).
ADMIN_LISTS = {}


def _admin_list(kind, refresh=False):
    # "roles" or "privileges", parsed (with their flags) -> (items, error).
    if not refresh and kind in ADMIN_LISTS:
        return ADMIN_LISTS[kind], ""
    argv, parser, ok_codes, timeout = gc.PICK_LISTS[kind]
    rc, out, err = _read_gam(argv, timeout)
    if rc not in ok_codes:
        tail = (err + out).strip()
        return None, (tail[-400:] if tail else "GAM stopped with exit code %d" % rc)
    ADMIN_LISTS[kind] = parser(out)
    return ADMIN_LISTS[kind], ""


def admin_lists(data):
    # POST /api/admin/lists {kind: "roles"|"privileges", refresh}.
    kind = str(data.get("kind") or "")
    if kind not in ("roles", "privileges"):
        return {"error": "Unknown list."}
    if not GAM:
        return {"error": "gam was not found on this machine."}
    items, err = _admin_list(kind, bool(data.get("refresh")))
    if err:
        return {"error": err}
    if kind == "roles":
        return {"items": [{"name": r["name"], "label": gc.role_label(r),
                           "system": r["system"], "super": r["super"]} for r in items],
                # The new role's privilege choices (the desktop's dropdown).
                "privmodes": list(gc.NEWADMIN_PRIVS)}
    return {"items": [{"key": p["name"] + "|" + p["service_id"], "name": p["name"],
                       "service": p["service"], "ou": p["ou"], "depth": p["depth"]}
                      for p in items]}


def _admin_plan(data):
    # The page's form -> (plan, values); ValueError for a problem.
    v = data.get("values") or {}
    text = lambda k: str(v.get(k) or "")
    roles, err = _admin_list("roles")
    if err:
        raise ValueError("Could not read the admin roles: " + err)
    labels = {r["name"]: gc.role_label(r) for r in roles}
    picked = [str(r) for r in (v.get("roles") or [])]
    for name in picked:
        if name not in labels:
            raise ValueError("Unknown admin role '" + name + "' - click Refresh roles.")
    privs_mode = gc.NEWADMIN_PRIVS.get(text("new_role_privs"), text("new_role_privs"))
    values = {"email": text("email"), "create": "yes" if text("create") == "yes" else "exists",
              "first": text("first"), "last": text("last"), "password": text("password"),
              "must_change": bool(v.get("must_change", True)),
              "account_ou": text("account_ou"), "notify": text("notify"),
              "roles": picked,
              "new_role_name": text("new_role_name") if v.get("new_role") else "",
              "new_role_desc": text("new_role_desc"), "new_role_privs": privs_mode,
              "new_role_list": "",
              "scope": "ous" if text("scope") == "ous" else "customer",
              "ous": [o.strip() for o in text("ous").splitlines() if o.strip()],
              "expdate": text("expdate"), "exptime": text("exptime"),
              "gamhelp": bool(v.get("gamhelp"))}
    if values["new_role_name"] and privs_mode == "list":
        privs, err = _admin_list("privileges")
        if err:
            raise ValueError("Could not read the privileges: " + err)
        keys = set(str(k) for k in (v.get("new_role_picks") or []))
        chosen = [p for p in privs if p["name"] + "|" + p["service_id"] in keys]
        values["new_role_list"] = gc.privilege_tokens(chosen, privs)
    # The access end date is in the VIEWER's time zone (as /api/build).
    tz = str(data.get("tz") or "")[:64]
    if values["expdate"].strip() and gc._zone_or_none(tz) is None:
        try:
            browser_off = int(data.get("tzoffset"))
        except (TypeError, ValueError):
            browser_off = None
        server_off = -int(datetime.datetime.now().astimezone().utcoffset()
                          .total_seconds() // 60)
        if browser_off != server_off:
            raise ValueError("Cannot convert your local time on this server (its "
                             "time zone differs from yours and zone data is "
                             "missing). Install the Python 'tzdata' package on "
                             "the server, or use the desktop GAMGUI.")
        tz = ""
    supers = [r["name"] for r in roles if r["super"]] or ["_SEED_ADMIN_ROLE"]
    plan = gc.new_admin_plan(values, super_roles=supers, tz=tz or None, role_labels=labels)
    return plan, values


def admin_preview(data):
    # The commands, numbered, with any password masked.
    try:
        plan, _values = _admin_plan(data)
    except ValueError as exc:
        return {"error": str(exc)}
    return {"lines": ["%d. %s\n   gam %s" % (n, label, gg.redact_secrets(
        " ".join(gc.quote_if_needed(a) for a in argv)))
        for n, (label, argv, _kind) in enumerate(plan["steps"], 1)]}


def _gam_too_old(argv_list):
    # The desktop's version check (GamGui._gam_new_enough) as a sentence for
    # the confirmation, or "" (unknown version: never block).
    found = re.search(r"\d+\.\d+\.\d+", gam_version() or "")
    if not found:
        return ""
    have = gc.version_tuple(found.group(0))
    need, word = "", ""
    for argv in argv_list:
        n, w = gc.gam_version_needed(argv)
        if gc.version_tuple(n) > gc.version_tuple(need):
            need, word = n, w
    if not need or have >= gc.version_tuple(need):
        return ""
    return ("NOTE: this uses '" + word + "', which needs GAM " + need + " or newer. "
            "This server has GAM " + found.group(0) + ", so GAM will probably stop "
            "with 'Invalid argument'. Update GAM first.\n\n")


def admin_start(data):
    if not GAM:
        return {"error": "gam was not found on this machine."}
    try:
        plan, values = _admin_plan(data)
    except ValueError as exc:
        return {"error": str(exc)}
    summary, word = gam_workflows.new_admin_confirm(plan)
    summary = _gam_too_old([a for _l, a, _k in plan["steps"]]) + summary
    password = values["password"] if plan["created"] else ""

    def body(io):
        def created():
            io.job["signin"] = {"email": plan["email"], "password": password}
        if word is None and not io.confirm(summary, None):
            io.out("\nSet up an administrator canceled - nothing was changed.\n")
            return
        gam_workflows.run_new_admin(io, plan, word, summary, values["gamhelp"],
                                    on_created=created if password else None)
    return {"job": _start_job(body)}


# --- The single-page web UI --------------------------------------------------

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>GAM Web</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 :root{--bg:#f6f7f9;--panel:#fff;--line:#d9dee3;--accent:#1a73e8;--warn:#c5221f}
 *{box-sizing:border-box}
 body{margin:0;font:14px/1.45 system-ui,Segoe UI,Roboto,Arial;background:var(--bg);color:#202124}
 header{background:#202124;color:#fff;padding:8px 14px;font-weight:600}
 header small{font-weight:400;color:#9aa0a6;margin-left:8px}
 .wrap{display:flex;height:calc(100vh - 39px)}
 .left{width:290px;overflow:auto;border-right:1px solid var(--line);background:var(--panel)}
 .right{flex:1;overflow:auto;padding:14px}
 .cat{padding:7px 12px;font-weight:600;background:#eef1f4;border-top:1px solid var(--line);cursor:pointer}
 .task{padding:6px 12px 6px 22px;cursor:pointer;border-top:1px solid #eef1f4}
 .grp{padding:5px 12px 3px 16px;font-style:italic;color:#555;border-top:1px solid #eef1f4}
 .task:hover{background:#eaf1fd}
 .task.sel{background:#d2e3fc}
 .task.d{color:var(--warn)}
 h2{margin:2px 0 4px;font-size:16px}
 .desc{color:#5f6368;margin-bottom:10px}
 label{display:block;margin:8px 0 2px;font-weight:600}
 input,select,textarea{width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:4px;font:inherit}
 .row{margin-bottom:6px}
 .req:after{content:" *";color:var(--warn)}
 .prev{font-family:ui-monospace,Consolas,monospace;background:#f1f3f4;border:1px solid var(--line);border-radius:4px;padding:8px;margin:10px 0;white-space:pre-wrap;min-height:20px}
 button{font:inherit;padding:7px 14px;border:0;border-radius:4px;background:var(--accent);color:#fff;cursor:pointer}
 button.sec{background:#e8eaed;color:#202124}
 button:disabled{opacity:.5;cursor:default}
 .out{font-family:ui-monospace,Consolas,monospace;background:#202124;color:#e8eaed;padding:10px;border-radius:4px;white-space:pre-wrap;margin-top:12px;min-height:120px;max-height:55vh;overflow:auto}
 .gam{padding:4px 14px;background:#fef7e0;border-bottom:1px solid var(--line);font-size:12px}
 .gam.bad{background:#fce8e6;color:var(--warn)}
 .search{padding:8px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--panel)}
 .doc{font-size:13px;margin-left:8px}
 .tz{color:#5f6368;font-size:12px;margin:4px 0 8px}
 .pk{display:flex;gap:6px}
 .pk input{flex:1}
 .modal{position:fixed;inset:0;background:rgba(0,0,0,.35);display:none;align-items:center;justify-content:center;z-index:10}
 .modal .box{background:var(--panel);width:min(1000px,95vw);max-height:92vh;display:flex;flex-direction:column;padding:14px;border-radius:6px}
 .pkbar{display:flex;gap:8px;align-items:center;margin:6px 0}
 .pkbar #pkq{flex:1}
 .pkall{display:flex;align-items:center;gap:4px;font-weight:400;margin:0;white-space:nowrap}
 .pkall input{width:auto}
 .pktab{flex:1;overflow:auto;border:1px solid var(--line);min-height:200px;max-height:55vh}
 .pktab table{border-collapse:collapse;width:100%}
 .pktab th,.pktab td{text-align:left;padding:4px 8px;border-bottom:1px solid #eef1f4;white-space:nowrap}
 .pktab th{position:sticky;top:0;background:#eef1f4}
 .pktab tbody tr{cursor:pointer}
 .pktab tr.sel td{background:#d2e3fc}
 .pkfoot{display:flex;gap:6px;margin-top:8px}
 .pkfoot .gap{flex:1}
</style></head><body>
<header>GAM Web <small>a browser front-end for GAM (Cloud Shell friendly)</small></header>
<div id="gam" class="gam"></div>
<div class="wrap">
  <div class="left"><div class="search"><input id="q" placeholder="Search tasks..."></div><div id="tree"></div></div>
  <div class="right">
    <div id="pane"><p class="desc">Pick a task on the left, or use Custom command.</p></div>
  </div>
</div>
<div id="pk" class="modal"><div class="box">
  <h2 id="pkt"></h2><div class="desc" id="pkh"></div>
  <div class="pkbar"><input id="pkq" placeholder="Find..."><label id="pkal" class="pkall"><input type="checkbox" id="pka"><span id="pkat"></span></label><button class="sec" id="pks">Search</button></div>
  <div class="pktab"><table><thead id="pkhd"></thead><tbody id="pkb"></tbody></table></div>
  <div class="desc" id="pkst"></div>
  <div class="pkfoot"><button class="sec" id="pkr">Refresh list</button><span class="gap"></span><button id="pku">Use</button><button class="sec" id="pkc">Cancel</button></div>
</div></div>
<script>
let CUR=null;
// Escapes text for HTML - including quotes, because values are also placed
// inside attributes (value="...", href="...").
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
const TOKEN='__GAMWEB_TOKEN__';
function hdrs(){return {'X-GAMWeb-Token':TOKEN};}
async function getj(path){const r=await fetch(path,{headers:hdrs()});return r.json();}
async function api(path,body){const h=hdrs();h['Content-Type']='application/json';const r=await fetch(path,{method:'POST',headers:h,body:JSON.stringify(body)});return r.json();}
async function boot(){
  const g=await getj('/api/gam');
  const el=document.getElementById('gam');
  if(g.gam){el.textContent='gam: '+g.gam;} else {el.className='gam bad';el.textContent='gam not found on this machine - install/authorize GAM first.';}
  PT=await getj('/api/picktables');
  pkInit();
  const cats=await getj('/api/tasks');
  const tree=document.getElementById('tree');
  for(const cat in cats){
    const c=document.createElement('div');c.className='cat';c.textContent=cat;c.dataset.cat=cat;tree.appendChild(c);
    let lastGroup='';
    for(const t of cats[cat]){
      if(t.group&&t.group!==lastGroup){const gh=document.createElement('div');gh.className='grp';gh.textContent=t.group;gh.dataset.cat=cat;tree.appendChild(gh);}
      lastGroup=t.group||'';
      const d=document.createElement('div');d.className='task'+(t.destructive?' d':'');d.textContent=t.name;d.dataset.cat=cat;d.dataset.key=cat+'|'+t.idx;
      d.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));d.classList.add('sel');showTask(t);};
      tree.appendChild(d);
    }
  }
  const inc=document.createElement('div');inc.className='task d';inc.textContent='Incident response (Email Cleanup)';
  inc.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));inc.classList.add('sel');showIncident();};
  tree.appendChild(inc);
  const cmp=document.createElement('div');cmp.className='task d';cmp.textContent='Compromised account response';
  cmp.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));cmp.classList.add('sel');showCompromised();};
  tree.appendChild(cmp);
  const ck=document.createElement('div');ck.className='task';ck.textContent='Compromised account checklist (steps GAM cannot do)';
  ck.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));ck.classList.add('sel');showChecklist();};
  tree.appendChild(ck);
  const tg=document.createElement('div');tg.className='task d';tg.textContent='Find & PERMANENTLY delete a message from ONLY the mailboxes that have it';
  tg.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));tg.classList.add('sel');showTargeted();};
  tree.appendChild(tg);
  const au=document.createElement('div');au.className='task';au.textContent='Mailbox takeover audit (one user)';
  au.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));au.classList.add('sel');showAudit();};
  tree.appendChild(au);
  const cc=document.createElement('div');cc.className='task';cc.textContent='Custom command';
  cc.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));cc.classList.add('sel');showCustom();};
  tree.appendChild(cc);
  document.getElementById('q').oninput=filterTree;
}
// Live search: show tasks whose category or name contains the text; hide
// categories with no match. Clearing the box shows everything again.
// 2.82: the server does the matching (same rules and synonyms as the
// desktop app); only the newest answer is used while typing.
let SEARCH_SEQ=0;
async function filterTree(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  const seq=++SEARCH_SEQ;
  let keys=null;
  if(q){const r=await api('/api/search',{q:q}); if(seq!==SEARCH_SEQ)return; keys=new Set(r.keys||[]);}
  const shown={};
  document.querySelectorAll('#tree .task').forEach(d=>{
    const ok=!q||!d.dataset.key||keys.has(d.dataset.key);
    d.style.display=ok?'':'none'; if(ok&&d.dataset.cat)shown[d.dataset.cat]=1;});
  document.querySelectorAll('#tree .cat').forEach(c=>{c.style.display=(!q||shown[c.dataset.cat])?'':'none';});
  document.querySelectorAll('#tree .grp').forEach(g=>{g.style.display=q?'none':'';});
}
function showTask(t){
  if(t.workflow==='newadmin'){return showAdmin(t);}   // 2.84: own screens
  if(t.workflow==='dlpedit'){return showDlp(t);}
  if(t.workflow==='classof'||t.workflow==='gradeou'){return showRollover(t,t.workflow);}
  CUR=t;let h='<h2>'+esc(t.name)+' <a class="doc" target="_blank" rel="noopener noreferrer" href="'+esc(t.doc)+'">GAM docs</a></h2><div class="desc">'+esc(t.desc)+'</div>';
  if(t.localtime){h+='<div class="tz">Times are in your time zone ('+esc(Intl.DateTimeFormat().resolvedOptions().timeZone||'local')+') and are converted to UTC for Google.</div>';}
  for(const f of t.fields){
    h+='<div class="row"><label class="'+(f.required?'req':'')+'">'+esc(f.label)+'</label>';
    if(f.options){h+='<select data-k="'+esc(f.key)+'">'+f.options.map(o=>'<option'+(o===f.default?' selected':'')+'>'+esc(o)+'</option>').join('')+'</select>';}
    else if(f.picker&&PT[f.picker.kind]){h+='<div class="pk"><input data-k="'+esc(f.key)+'" value="'+esc(f.default)+'"><button class="sec" data-pick="'+esc(f.key)+'">Pick...</button></div>';}
    else{h+='<input data-k="'+esc(f.key)+'" value="'+esc(f.default)+'">';}
    h+='</div>';
  }
  h+='<div class="prev" id="prev"></div>';
  h+='<button id="run">Run</button> ';
  if(t.dryrun){h+='<button class="sec" id="dry" title="Shows what this would change, without changing anything">Preview (dry run)</button> ';}
  // 2.84: a multi-step workflow has a Stop button and a question box
  // instead of Copy (there is no single command to copy).
  if(t.workflow){h+='<button class="sec" id="wfstop" style="display:none">Stop</button>';
    h+='<div id="wfask" style="display:none;margin-top:10px;padding:8px;background:#fce8e6;border-radius:4px"></div>';}
  else{h+='<button class="sec" onclick="copyCmd()">Copy</button>';}
  h+='<div class="out" id="out"></div>';
  document.getElementById('pane').innerHTML=h;
  document.querySelectorAll('[data-k]').forEach(i=>i.oninput=build);
  document.querySelectorAll('[data-pick]').forEach(b=>{const f=t.fields.find(x=>x.key===b.getAttribute('data-pick'));b.onclick=()=>openPicker(f);});
  document.getElementById('run').onclick=run;
  if(t.dryrun){document.getElementById('dry').onclick=dryRun;}
  build();
}
// 2.83: Pick... - a searchable list of users, groups, courses, OUs, admin
// roles, Chrome browsers, printers, buildings, rooms, aliases or mobile
// devices. The server runs a READ-ONLY 'gam print' for the list (POST
// /api/list); Find filters it here; the chosen row's ID goes in the box.
// Mobile devices are SEARCHED by the start of the user's address.
let PT={}, PK=null;
const PKMAX=500;
function $(id){return document.getElementById(id);}
function pkInit(){
  $('pkq').oninput=()=>{if(PK)pkFill();};
  $('pkq').onkeydown=e=>{
    if(e.key==='Escape'){pkClose();return;}
    if(e.key!=='Enter'||!PK)return;
    const text=$('pkq').value.trim().toLowerCase();
    if(PK.spec.search&&text!==PK.searched){pkSearch();return;}
    const rows=$('pkb').querySelectorAll('tr');
    if(rows.length===1){PK.sel=+rows[0].dataset.i;pkUse();}
  };
  $('pka').onchange=()=>{if(PK)pkLoad(false);};
  $('pks').onclick=()=>{if(PK)pkSearch();};
  $('pkr').onclick=()=>{if(!PK)return;if(PK.spec.search&&PK.searched===null)return;pkLoad(true);};
  $('pku').onclick=()=>pkUse();
  $('pkc').onclick=()=>pkClose();
  $('pkb').onclick=e=>{const tr=e.target.closest('tr');if(!tr||!PK)return;PK.sel=+tr.dataset.i;$('pkb').querySelectorAll('tr.sel').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');};
  $('pkb').ondblclick=e=>{const tr=e.target.closest('tr');if(!tr||!PK)return;PK.sel=+tr.dataset.i;pkUse();};
}
function openPicker(f){
  const spec=PT[f.picker.kind];if(!spec)return;
  PK={f:f,kind:f.picker.kind,spec:spec,rows:[],sel:null,seq:0,searched:null};
  const art=spec.article||'a';
  $('pkt').textContent='Choose '+art+' '+spec.noun;
  $('pkh').textContent='Type part of '+spec.find+', then double-click the '+spec.noun+' (or click it and Use).';
  $('pkq').value='';
  $('pkal').style.display=spec.all_kind?'':'none';
  $('pka').checked=!!f.picker.all;
  $('pkat').textContent=spec.all_label||'';
  $('pks').style.display=spec.search?'':'none';
  $('pku').textContent='Use this '+spec.noun;
  $('pkhd').innerHTML='<tr>'+spec.columns.map(c=>'<th>'+esc(c[1])+'</th>').join('')+'</tr>';
  $('pkb').innerHTML='';
  $('pk').style.display='flex';$('pkq').focus();
  if(spec.search){$('pkst').textContent=spec.search_help;}else{pkLoad(false);}
}
function pkClose(){$('pk').style.display='none';PK=null;}
function pkSearch(){
  // Same rule as the server (gam_catalog.SEARCHED_LISTS) - checked here
  // first so a typo gets a plain hint instead of a failed load.
  const text=$('pkq').value.trim().toLowerCase();
  if(!new RegExp('^(?:'+PK.spec.search_allowed+')$').test(text)){$('pkst').textContent=PK.spec.search_bad;return;}
  PK.searched=text;pkLoad(false);
}
async function pkLoad(refresh){
  const mine=PK, seq=++PK.seq;
  const all=!!(PK.spec.all_kind&&$('pka').checked);
  $('pkst').textContent=all?PK.spec.all_loading:PK.spec.loading;
  const body={kind:PK.kind,all:all,refresh:!!refresh};
  if(PK.spec.search){body.text=PK.searched;}
  const r=await api('/api/list',body);
  if(PK!==mine||seq!==PK.seq)return;           // closed, or a newer load started
  if(r.error){$('pkst').textContent='Could not load the list: '+r.error;return;}
  PK.rows=r.rows||[];PK.sel=null;pkFill();
}
function pkFill(){
  const q=$('pkq').value.trim().toLowerCase(), keys=PK.spec.columns.map(c=>c[0]);
  const parts=[];let total=0;
  for(let i=0;i<PK.rows.length;i++){
    const vals=keys.map(k=>String(PK.rows[i][k]==null?'':PK.rows[i][k]));
    if(q&&vals.join(' ').toLowerCase().indexOf(q)<0)continue;
    total++;
    if(parts.length<PKMAX){parts.push('<tr data-i="'+i+'">'+vals.map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>');}
  }
  $('pkb').innerHTML=parts.join('');PK.sel=null;
  if(PK.spec.search&&PK.searched===null){$('pkst').textContent=PK.spec.search_help;return;}
  $('pkst').textContent=total+' '+(total===1?PK.spec.noun:PK.spec.plural)+(total>PKMAX?' - showing the first '+PKMAX+'; type to narrow':'')+'.';
}
function pkUse(){
  if(!PK)return;
  if(PK.sel===null||!PK.rows[PK.sel]){alert('Click '+(PK.spec.article||'a')+' '+PK.spec.noun+' first.');return;}
  const value=String(PK.rows[PK.sel][PK.spec.id]||'');
  const f=PK.f;
  // 2.84: onpick = add the choice to a list instead of filling one box.
  if(f.onpick){pkClose();f.onpick(value);return;}
  const box=[...document.querySelectorAll('[data-k]')].find(i=>i.getAttribute('data-k')===f.key);
  pkClose();
  if(box){box.value=value;if(CUR)build();}
}
function values(){const v={};document.querySelectorAll('[data-k]').forEach(i=>v[i.getAttribute('data-k')]=i.value);return v;}
// Every keystroke requests a fresh build. Responses can arrive OUT OF ORDER,
// so each request gets a number and only the NEWEST one may update the
// preview and the argv that Run uses - an older, stale command must never win.
let BUILDSEQ=0;
async function build(){
  const mine=++BUILDSEQ;
  window._err='building';                       // Run waits for the newest build
  const r=await api('/api/build',{cat:CUR.cat,idx:CUR.idx,values:values(),
    tz:(Intl.DateTimeFormat().resolvedOptions().timeZone||''),tzoffset:new Date().getTimezoneOffset()});
  if(mine!==BUILDSEQ)return;                    // a newer build superseded this one
  document.getElementById('prev').textContent=r.error?('('+r.error+')'):((r.workflow?'':'gam ')+r.display);
  window._argv=r.argv;window._err=r.error;
}
function copyCmd(){navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('prev').textContent);}
async function run(){
  if(window._err==='building'){await build();}
  if(CUR.workflow){if(window._err){alert(window._err);return;}return startWorkflow();}
  if(window._err){alert('Fill in the required fields first.');return;}
  if(CUR.destructive && !confirm('This is a DESTRUCTIVE action:\\n\\ngam '+document.getElementById('prev').textContent.replace(/^gam /,'')+'\\n\\nAre you sure?'))return;
  const out=document.getElementById('out');out.textContent='Running...\\n';
  const btn=document.getElementById('run');btn.disabled=true;
  const r=await api('/api/run',{argv:window._argv});
  out.textContent=r.output+'\\n[exit code '+r.code+']';btn.disabled=false;
}
// 2.84: the Drive sharing workflows run as a server job (the same steps as
// the desktop app). Questions come back in the status: a Yes / No one, or
// a word to type (the server checks the word).
let WFJOB=null, WFTIMER=null;
async function startWorkflow(){
  const r=await api('/api/workflow/start',{cat:CUR.cat,idx:CUR.idx,values:values()});
  if(r.error){alert(r.error);return;}
  WFJOB=r.job;$('run').disabled=true;$('out').textContent='Starting...';
  const box=$('wfask');if(box){box.dataset.n='';box.style.display='none';}   // a new job numbers from 1 again
  const st=$('wfstop');if(st){st.style.display='';st.onclick=()=>api('/api/workflow/stop',{job:WFJOB});}
  if(WFTIMER)clearInterval(WFTIMER);
  WFTIMER=setInterval(pollWorkflow,1500);
}
async function pollWorkflow(){
  if(!WFJOB)return;
  const mine=WFJOB;
  const s=await getj('/api/workflow/status?job='+encodeURIComponent(mine));
  if(mine!==WFJOB)return;
  const out=$('out');if(out){out.textContent=s.output||'';out.scrollTop=out.scrollHeight;}
  // A new admin account's sign-in details: sent ONCE by the server.
  if(s.signin){
    const w=$('wfsign');
    const html='<div style="margin-top:10px;padding:8px;background:#e6f4ea;border-radius:4px"><b>The account was created.</b> Give these sign-in details to the new admin now - GAMGUI does not keep the password anywhere, and this page shows it only once.'+
      '<div class="row"><label>Email</label><input readonly value="'+esc(s.signin.email)+'"></div><div class="row"><label>Password</label><input readonly value="'+esc(s.signin.password)+'"></div></div>';
    if(w){w.innerHTML=html;}else{alert('The account was created. Email: '+s.signin.email+'  Password: '+s.signin.password);}
  }
  const box=$('wfask');
  if(s.status==='awaiting_confirm'&&s.confirm){
    if(box&&box.dataset.n!==String(s.confirm.n)){
      box.dataset.n=String(s.confirm.n);box.style.display='block';
      let h='<pre style="white-space:pre-wrap;margin:0 0 8px">'+esc(s.confirm.summary)+'</pre>';
      if(s.confirm.word){h+='<b>Type '+esc(s.confirm.word)+' to continue.</b><div class="row"><input id="wfword" placeholder="'+esc(s.confirm.word)+'"></div><button id="wfyes">Continue</button> <button class="sec" id="wfno">Cancel</button>';}
      else{h+='<button id="wfyes">Yes</button> <button class="sec" id="wfno">No</button>';}
      box.innerHTML=h;
      $('wfyes').onclick=()=>answerWorkflow(s.confirm.word?$('wfword').value:'yes');
      $('wfno').onclick=()=>answerWorkflow('');
    }
  } else if(box){box.style.display='none';}
  if(s.status==='done'){
    clearInterval(WFTIMER);WFTIMER=null;
    const b=$('run');if(b)b.disabled=false;
    const st=$('wfstop');if(st)st.style.display='none';
    if(typeof WFDONE==='function'){const f=WFDONE;WFDONE=null;f();}   // 2.85: e.g. refresh a rollover plan
  }
}
// 2.84: Set up an administrator - the desktop window as a page. The server
// reads the roles and builds the commands (POST /api/admin/preview); Run
// starts a job (POST /api/admin/start) that pollWorkflow follows. A new
// account's sign-in details arrive once at the end (s.signin).
let ADM={roles:[],privs:[],modes:[]};
function showAdmin(t){
  CUR=null;
  const inp=(id,ph,type)=>'<input id="'+id+'"'+(type?' type="'+type+'"':'')+' placeholder="'+(ph||'')+'">';
  const row=(lab,html)=>'<div class="row"><label>'+lab+'</label>'+html+'</div>';
  $('pane').innerHTML='<h2>'+esc(t.name)+' <a class="doc" target="_blank" rel="noopener noreferrer" href="'+esc(t.doc)+'">GAM docs</a></h2>'+
   '<div class="desc">Set up an administrator in one place: the account, the admin roles, and where they apply. Nothing changes until you click Run and confirm - Show the commands lists exactly what will run first.</div>'+
   '<h3>1. The account</h3>'+
   row('Email address *','<div class="pk">'+inp('aem','admin@example.com')+'<button class="sec" id="aempk">Pick...</button></div>')+
   row('The account','<select id="acr"><option value="exists">The account already exists</option><option value="yes">Create the account now</option></select>')+
   '<div id="anew" style="display:none">'+row('First name *',inp('afirst'))+row('Last name *',inp('alast'))+
   row('Password * (at least 8 characters)','<div class="pk">'+inp('apw','','password')+'<button class="sec" id="apwgen">Generate</button><button class="sec" id="apwshow">Show / hide</button></div>')+
   '<div class="row"><label><input type="checkbox" id="amust" checked style="width:auto"> Must choose a new password at first sign-in</label></div>'+
   row('Put the account in OU (optional)','<div class="pk">'+inp('aou','/Staff/IT')+'<button class="sec" id="aoupk">Pick...</button></div>')+
   row('Email the sign-in details to (optional)',inp('anotify'))+'</div>'+
   '<h3>2. Admin roles</h3><div class="desc">Tick one or more. The list is your domain&#39;s roles, built-in and custom.</div>'+
   '<div id="aroles" style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:4px;padding:6px"></div>'+
   '<div class="desc" id="arstat">Loading admin roles from Google...</div><button class="sec" id="arref">Refresh roles</button>'+
   '<div class="row"><label><input type="checkbox" id="anr" style="width:auto"> Also create a NEW custom role and give it</label></div>'+
   '<div id="anrbox" style="display:none">'+row('Role name',inp('anrname'))+row('Description (optional)',inp('anrdesc'))+
   row('Privileges','<select id="anrprivs"></select>')+
   '<div id="aprivbox" style="display:none">'+inp('apfind','Find a privilege...')+'<div id="aprivs" style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:4px;padding:6px"></div><div class="desc" id="apstat"></div></div></div>'+
   '<h3>3. Where the roles apply</h3>'+
   row('Scope','<select id="ascope"><option value="customer">The whole organization</option><option value="ous">Only these OUs (and the OUs inside them)</option></select>')+
   row('OUs (one per line)','<textarea id="aous" rows="3" placeholder="/Staff"></textarea><button class="sec" id="aouadd">Add an OU...</button>')+
   '<h3>4. Optional</h3>'+
   row('Access ends on (MM-DD-YYYY) - blank for access that does not end, at most one year ahead',inp('aexpd'))+
   row('at (time, blank = midnight) - your time zone',inp('aexpt'))+
   '<div class="row"><label><input type="checkbox" id="agam" style="width:auto"> They will run GAM themselves - show the steps for that afterwards</label></div>'+
   '<div class="prev" id="aprev"></div>'+
   '<button class="sec" id="ashow">Show the commands</button> <button id="run">Run</button> <button class="sec" id="wfstop" style="display:none">Stop</button>'+
   '<div id="wfask" style="display:none;margin-top:10px;padding:8px;background:#fce8e6;border-radius:4px"></div>'+
   '<div id="wfsign"></div><div class="out" id="out"></div>';
  $('acr').onchange=()=>{$('anew').style.display=$('acr').value==='yes'?'':'none';};
  $('anr').onchange=()=>{$('anrbox').style.display=$('anr').checked?'':'none';admPrivs();};
  $('anrprivs').onchange=admPrivs;
  $('ascope').onchange=admPrivs;
  $('apfind').oninput=admPrivFill;
  $('aempk').onclick=()=>openPicker({key:'aem',picker:{kind:'users',all:false},onpick:v=>{$('aem').value=v;}});
  $('aoupk').onclick=()=>openPicker({key:'aou',picker:{kind:'ous',all:false},onpick:v=>{$('aou').value=v;}});
  $('aouadd').onclick=()=>openPicker({key:'aous',picker:{kind:'ous',all:false},onpick:v=>{
    const have=$('aous').value.split(/\\r?\\n/).map(x=>x.trim()).filter(x=>x);
    if(have.indexOf(v)<0)have.push(v);$('aous').value=have.join('\\n');$('ascope').value='ous';admPrivs();}});
  $('apwgen').onclick=()=>{$('apw').value=admPassword();$('apw').type='text';};
  $('apwshow').onclick=()=>{$('apw').type=$('apw').type==='password'?'text':'password';};
  $('arref').onclick=()=>admRoles(true);
  $('ashow').onclick=admShow;
  $('run').onclick=admRun;
  admRoles(false);
}
function admPassword(){
  // 16 characters that are easy to read out and type (no quotes or spaces),
  // with at least one upper, lower, digit and symbol - as the desktop app.
  const A='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%*-_+=';
  for(;;){
    const r=new Uint32Array(16);crypto.getRandomValues(r);
    const p=Array.from(r,x=>A[x%A.length]).join('');
    if(/[A-Z]/.test(p)&&/[a-z]/.test(p)&&/[0-9]/.test(p)&&/[^A-Za-z0-9]/.test(p))return p;
  }
}
async function admRoles(refresh){
  $('arstat').textContent='Loading admin roles from Google...';
  const r=await api('/api/admin/lists',{kind:'roles',refresh:refresh});
  if(!$('aroles'))return;
  if(r.error){$('arstat').textContent='Could not load the roles: '+r.error;return;}
  const ticked=new Set([...document.querySelectorAll('#aroles input:checked')].map(i=>i.value));
  ADM.roles=r.items;ADM.modes=r.privmodes||[];
  $('aroles').innerHTML=r.items.map(x=>'<label style="font-weight:400;margin:2px 0"><input type="checkbox" style="width:auto" value="'+esc(x.name)+'"'+(ticked.has(x.name)?' checked':'')+'> '+esc(x.label)+(x.system?' [built-in]':' [custom]')+'</label>').join('');
  if(!$('anrprivs').options.length){$('anrprivs').innerHTML=ADM.modes.map(m=>'<option>'+esc(m)+'</option>').join('');}
  $('arstat').textContent=r.items.length+' roles. Super Admin can only be given for the whole organization.';
}
async function admPrivs(){
  // The privilege list shows only for "Only the privileges I pick".
  const on=$('anr').checked&&/privileges I pick/.test($('anrprivs').value);
  $('aprivbox').style.display=on?'':'none';
  if(!on)return;
  if(!ADM.privs.length){
    $('apstat').textContent='Loading the privileges from Google...';
    const r=await api('/api/admin/lists',{kind:'privileges'});
    if(r.error){$('apstat').textContent='Could not load the privileges: '+r.error;return;}
    ADM.privs=r.items;
  }
  admPrivFill();
}
function admPrivFill(){
  const q=$('apfind').value.trim().toLowerCase(), ouOnly=$('ascope').value==='ous';
  const ticked=new Set([...document.querySelectorAll('#aprivs input:checked')].map(i=>i.value));
  const show=ADM.privs.filter(p=>(!ouOnly||p.ou)&&(!q||(p.name+' '+p.service).toLowerCase().indexOf(q)>=0));
  $('aprivs').innerHTML=show.map(p=>'<label style="font-weight:400;margin:2px 0;padding-left:'+(p.depth*14)+'px"><input type="checkbox" style="width:auto" value="'+esc(p.key)+'"'+(ticked.has(p.key)?' checked':'')+'> '+esc(p.name)+' <span class="desc">('+esc(p.service)+')</span></label>').join('');
  $('apstat').textContent=show.length+' privileges'+(ouOnly?' that can be limited to OUs':'')+'.';
}
function admValues(){
  return {email:$('aem').value.trim(),create:$('acr').value,first:$('afirst').value,last:$('alast').value,
    password:$('apw').value,must_change:$('amust').checked,account_ou:$('aou').value,notify:$('anotify').value,
    roles:[...document.querySelectorAll('#aroles input:checked')].map(i=>i.value),
    new_role:$('anr').checked,new_role_name:$('anrname').value,new_role_desc:$('anrdesc').value,
    new_role_privs:$('anrprivs').value,new_role_picks:[...document.querySelectorAll('#aprivs input:checked')].map(i=>i.value),
    scope:$('ascope').value,ous:$('aous').value,expdate:$('aexpd').value,exptime:$('aexpt').value,gamhelp:$('agam').checked};
}
function admBody(){return {values:admValues(),tz:(Intl.DateTimeFormat().resolvedOptions().timeZone||''),tzoffset:new Date().getTimezoneOffset()};}
async function admShow(){
  const r=await api('/api/admin/preview',admBody());
  $('aprev').textContent=r.error?('('+r.error+')'):r.lines.join('\\n');
  return !r.error;
}
async function admRun(){
  if(!(await admShow())){alert($('aprev').textContent.replace(/^\\(|\\)$/g,''));return;}
  const r=await api('/api/admin/start',admBody());
  if(r.error){alert(r.error);return;}
  $('apw').value='';                                // the page does not keep it
  WFJOB=r.job;$('run').disabled=true;$('out').textContent='Starting...';$('wfsign').innerHTML='';
  const box=$('wfask');if(box){box.dataset.n='';box.style.display='none';}
  const st=$('wfstop');st.style.display='';st.onclick=()=>api('/api/workflow/stop',{job:WFJOB});
  if(WFTIMER)clearInterval(WFTIMER);
  WFTIMER=setInterval(pollWorkflow,1500);
}
// 2.85: Chromebook OU rollovers - "Class of" OUs (classof) and grade-named
// OUs (gradeou). Find = a read-only scan job on the server; the plan is
// worked out on the server from the scan and these choices; Run works it
// out again there and asks for ROLLOVER.
let RO={}, WFDONE=null;
async function showRollover(t,kind){
  CUR=null;RO={kind:kind,sep:[],force:[],keep:[],use:null,scanned:false};
  const co=kind==='classof';
  const y=await api('/api/rollover/years',{kind:kind});
  if(y.error){alert(y.error);return;}
  const opts=sel=>y.years.map(o=>'<option value="'+o.year+'"'+(o.year===sel?' selected':'')+'>'+esc(o.label)+'</option>').join('');
  const row=(lab,html)=>'<div class="row"><label>'+lab+'</label>'+html+'</div>';
  let h='<h2>'+esc(t.name)+' <a class="doc" target="_blank" rel="noopener noreferrer" href="'+esc(t.doc)+'">GAM docs</a></h2>';
  h+='<div class="desc">'+(co?
    'Finds the Chromebook OUs named after a graduating class (e.g. Class of 27 or Class of 2027), works out which OU holds which grade, and plans the yearly move: each class goes to the OU for its new grade, the new incoming class is created (with the same extras, e.g. Bluetooth), and graduated classes are left alone or moved where you say. Nothing changes until you click Run and type ROLLOVER. Safe to run again - it only does what is left.':
    'For Chromebook OUs named for a GRADE (Grade 5, 5th Grade, Kindergarten). The OUs stay; the Chromebooks move up one grade, highest grade first. Only the Chromebooks DIRECTLY in each OU move (not its sub-OUs). This is not repeatable - moving twice would move them two grades - so the server remembers which steps finished for which school year and never runs a finished step again. Nothing changes until you click Run and type ROLLOVER.')+'</div>';
  h+=row('Look under OU','<div class="pk"><input id="rroot" value="/"><button class="sec" id="rrootpk">Pick...</button></div>');
  if(co){
    h+=row('The OUs are set up now for','<select id="rcur">'+opts(y.current)+'</select>');
    h+=row('Prepare them for','<select id="rtgt">'+opts(y.target)+'</select>');
    h+='<div class="row"><label><input type="checkbox" id="rcount" checked style="width:auto"> Count the Chromebooks in each OU (slower)</label></div>';
  } else {
    h+=row('School year this is for','<select id="ryear">'+opts(y.target)+'</select>');
  }
  h+='<button id="rfind">Find '+(co?'class':'grade')+' OUs</button> <span class="desc" id="rstat">'+(co?'Click Find class OUs to start.':'Click Find grade OUs to start (it counts the Chromebooks in each OU - a minute or two).')+'</span>';
  if(co){h+=row('Naming pattern','<select id="rpat"></select><div class="desc" id="rextras"></div>');}
  h+='<div class="desc" style="margin-top:8px">'+(co?'OUs that hold class OUs. The one with the most Chromebooks wins a grade; click an OU to switch Keeps its own classes (e.g. an alternative campus):':'OUs named for a grade (click one to include or leave it out):')+'</div>';
  h+='<table id="rtab" style="border-collapse:collapse;width:100%"></table>';
  h+=row(co?'Graduated classes':'Graduated seniors Chromebooks','<select id="rgmode">'+(co?
    '<option value="leave">Leave them where they are</option><option value="move">Move them into the OU below</option>':
    '<option value="move">Move them into the OU below</option><option value="leave">Leave them (next year&#39;s seniors join them)</option>')+'</select>');
  h+=row('OU for graduated '+(co?'classes':'Chromebooks'),'<div class="pk"><input id="rgou"><button class="sec" id="rgoupk">Pick...</button></div>');
  h+='<label>What will happen:</label><div class="prev" id="rplan"></div>';
  h+='<button class="sec" id="rupd">Update the plan</button> <button id="run" disabled>Run...</button> <button class="sec" id="wfstop" style="display:none">Stop</button>';
  h+='<div id="wfask" style="display:none;margin-top:10px;padding:8px;background:#fce8e6;border-radius:4px"></div><div class="out" id="out"></div>';
  $('pane').innerHTML=h;
  $('rrootpk').onclick=()=>openPicker({key:'rroot',picker:{kind:'ous',all:false},onpick:v=>{$('rroot').value=v;}});
  $('rgoupk').onclick=()=>openPicker({key:'rgou',picker:{kind:'ous',all:false},onpick:v=>{$('rgou').value=v;rPlan();}});
  $('rfind').onclick=rFind;$('rupd').onclick=rPlan;$('run').onclick=rRun;
  $('rgmode').onchange=rPlan;$('rgou').onchange=rPlan;
  if(co){
    $('rcur').onchange=()=>{RO.sep=[];RO.force=[];rPlan(true);};
    $('rtgt').onchange=()=>rPlan();
    $('rpat').onchange=()=>{RO.sep=[];RO.force=[];rPlan();};
  } else {$('ryear').onchange=()=>rPlan();}
}
function rBody(){
  const b={kind:RO.kind,grad_mode:$('rgmode').value,grad_ou:$('rgou').value.trim()};
  if(RO.kind==='classof'){b.cur_year=+$('rcur').value;b.tgt_year=+$('rtgt').value;b.template=$('rpat').value||'';b.separate=RO.sep;b.force=RO.force;}
  else{b.year=+$('ryear').value;b.use=RO.use;}
  return b;
}
async function rFind(){
  const co=RO.kind==='classof';
  $('rfind').disabled=true;$('run').disabled=true;$('rstat').textContent='Reading the OU tree...';
  const r=await api('/api/rollover/scan',{kind:RO.kind,root:$('rroot').value.trim()||'/',count:co?$('rcount').checked:true});
  if(r.error){$('rfind').disabled=false;alert(r.error);return;}
  const job=r.job;
  for(;;){
    await new Promise(res=>setTimeout(res,1500));
    const s=await getj('/api/workflow/status?job='+encodeURIComponent(job));
    if(!$('rstat'))return;
    const lines=(s.output||'').trim().split('\\n');$('rstat').textContent=lines[lines.length-1]||'';
    if(s.status==='done'){
      $('rfind').disabled=false;
      if(!(s.result&&s.result.ok)){$('out').textContent=s.output||'';return;}
      RO.sep=[];RO.force=[];RO.use=null;RO.scanned=true;
      if(co){$('rpat').innerHTML='';}
      return rPlan();
    }
  }
}
async function rPlan(resetPattern){
  if(!RO.scanned)return;
  if(resetPattern&&$('rpat')){$('rpat').innerHTML='';}
  const r=await api('/api/rollover/plan',rBody());
  if(!$('rplan'))return;
  $('run').disabled=true;
  if(r.error){$('rplan').textContent='('+r.error+')';return;}
  const tab=$('rtab');
  if(RO.kind==='classof'){
    if(!r.templates.length){$('rplan').textContent=r.message||'';tab.innerHTML='';$('rpat').innerHTML='';return;}
    $('rpat').innerHTML=r.templates.map(x=>'<option value="'+esc(x.template)+'"'+(x.template===r.chosen?' selected':'')+'>'+esc(x.label)+'</option>').join('');
    $('rextras').textContent=r.extras;
    $('rstat').textContent='Found '+r.found+' class OUs under '+r.root+'.';
    RO.keep=r.rows.filter(x=>x.keep).map(x=>x.path);
    tab.innerHTML='<tr><th style="text-align:left">OU</th><th>Grades now</th><th>Class OUs</th><th>Chromebooks</th><th>Keeps its own classes</th></tr>'+
      r.rows.map(x=>'<tr data-p="'+esc(x.path)+'" style="cursor:pointer;border-top:1px solid var(--line)"><td>'+esc(x.path)+'</td><td style="text-align:center">'+esc(x.grades)+'</td><td style="text-align:center">'+x.classes+'</td><td style="text-align:center">'+x.devices+'</td><td style="text-align:center">'+(x.keep?'YES':'')+'</td></tr>').join('');
  } else {
    if(RO.use===null){RO.use=r.rows.filter(x=>x.use).map(x=>x.path);}
    tab.innerHTML='<tr><th style="text-align:left">OU</th><th>Grade</th><th>Chromebooks</th><th>Included</th><th style="text-align:left">Note</th></tr>'+
      r.rows.map(x=>'<tr data-p="'+esc(x.path)+'" style="cursor:pointer;border-top:1px solid var(--line)"><td>'+esc(x.path)+'</td><td style="text-align:center">'+esc(x.grade)+'</td><td style="text-align:center">'+x.devices+'</td><td style="text-align:center">'+(x.use?'YES':'')+'</td><td>'+esc(x.why)+'</td></tr>').join('');
  }
  tab.querySelectorAll('tr[data-p]').forEach(tr=>tr.onclick=()=>rToggle(tr.getAttribute('data-p')));
  $('rplan').textContent=r.text;
  $('run').disabled=!r.can_run;
}
async function rToggle(p){
  const drop=(a,v)=>a.filter(x=>x!==v);
  if(RO.kind==='classof'){
    // As the desktop: an OU that keeps its own classes joins the grade
    // ladder; an OU in the ladder is set to keep its own classes.
    if(RO.keep.indexOf(p)>=0){RO.force=drop(RO.force,p).concat([p]);RO.sep=drop(RO.sep,p);}
    else{RO.sep=drop(RO.sep,p).concat([p]);RO.force=drop(RO.force,p);}
    await rPlan();
    if(RO.force.indexOf(p)>=0&&RO.keep.indexOf(p)>=0){alert('Another OU you put in the ladder already holds some of these grades, so this one still keeps its own classes. Click that other OU first.');}
  } else {
    RO.use=RO.use.indexOf(p)>=0?drop(RO.use,p):RO.use.concat([p]);
    rPlan();
  }
}
async function rRun(){
  const r=await api('/api/rollover/start',rBody());
  if(r.error){alert(r.error);return;}
  WFJOB=r.job;$('run').disabled=true;$('out').textContent='Starting...';
  const box=$('wfask');if(box){box.dataset.n='';box.style.display='none';}
  const st=$('wfstop');st.style.display='';st.onclick=()=>api('/api/workflow/stop',{job:WFJOB});
  // Afterwards: grade OUs - show the finished steps; Class of - the year
  // may now be saved, so read the years again and find the OUs again.
  WFDONE=async()=>{
    if(!$('rplan'))return;
    if(RO.kind==='gradeou'){rPlan();return;}
    const y=await api('/api/rollover/years',{kind:'classof'});
    if(!y.error&&$('rcur')){$('rcur').value=String(y.current);$('rtgt').value=String(y.target);}
    rFind();
  };
  if(WFTIMER)clearInterval(WFTIMER);
  WFTIMER=setInterval(pollWorkflow,1500);
}
// 2.84: Edit a DLP detector's URL or word list (the desktop's DLP editor).
let DLP=[];
function showDlp(t){
  CUR=null;
  $('pane').innerHTML='<h2>'+esc(t.name)+' <a class="doc" target="_blank" rel="noopener noreferrer" href="'+esc(t.doc)+'">GAM docs</a></h2>'+
   '<div class="desc">Pick a detector, change its list (one entry per line), then click Save. You see what is added and removed first, and the old version is saved to the records folder on the server.</div>'+
   '<div class="row"><label>Detector</label><div class="pk"><select id="dsel"></select><button class="sec" id="dreload">Reload</button></div></div>'+
   '<div class="desc" id="dstat">Loading the detectors...</div>'+
   '<textarea id="dtext" rows="18"></textarea><br><button id="dsave">Save...</button>'+
   '<div class="out" id="dout"></div>';
  $('dsel').onchange=dlpShow;$('dreload').onclick=()=>dlpLoad();$('dsave').onclick=dlpSave;
  dlpLoad();
}
async function dlpLoad(keep){
  $('dreload').disabled=true;$('dstat').textContent='Loading the detectors...';
  const r=await api('/api/dlp/list',{});
  if(!$('dsel'))return;
  $('dreload').disabled=false;
  if(r.error){$('dstat').textContent='Could not read the detectors.';alert(r.error);return;}
  DLP=r.detectors;
  $('dsel').innerHTML=DLP.map(d=>'<option value="'+d.id+'">'+esc(d.name)+'  ('+esc(d.word)+' list)</option>').join('');
  if(!DLP.length){$('dtext').value='';$('dstat').textContent='No URL list or word list detectors were found. Create one in the Admin console first.';return;}
  if(keep!=null&&DLP[keep]){$('dsel').value=String(keep);}
  dlpShow();
}
function dlpShow(){
  const d=DLP[+$('dsel').value];if(!d)return;
  $('dtext').value=d.items.join('\\n');
  $('dstat').textContent=d.items.length+' '+d.word+'s. One per line; blank lines and repeats are ignored.';
}
async function dlpSave(){
  const d=DLP[+$('dsel').value];if(!d)return;
  const body={id:d.id,name:d.name,text:$('dtext').value};
  const p=await api('/api/dlp/preview',body);
  if(p.error){alert(p.error);return;}
  if(p.nothing){alert('Nothing changed.');return;}
  if(!confirm(p.question))return;
  $('dsave').disabled=true;$('dout').textContent='Saving...';
  const r=await api('/api/dlp/save',body);
  $('dsave').disabled=false;
  $('dout').textContent=r.error||r.output||'';
  if(r.code===0){dlpLoad(d.id);}
}
async function answerWorkflow(a){
  const box=$('wfask');if(box){box.style.display='none';}
  await api('/api/workflow/confirm',{job:WFJOB,answer:a});
}
// Preview (dry run): builds the preview form of the command on the server
// (GAM's 'preview' option, or without 'doit') and runs it. Nothing changes,
// so there is no destructive confirmation.
async function dryRun(){
  const r=await api('/api/build',{cat:CUR.cat,idx:CUR.idx,values:values(),dry_run:true,
    tz:(Intl.DateTimeFormat().resolvedOptions().timeZone||''),tzoffset:new Date().getTimezoneOffset()});
  if(r.error){alert(r.error);return;}
  const out=document.getElementById('out');
  out.textContent='[DRY RUN - changes nothing] gam '+r.display+'\\nRunning...\\n';
  const run=document.getElementById('run'),dry=document.getElementById('dry');
  run.disabled=true;dry.disabled=true;
  const x=await api('/api/run',{argv:r.argv,dry_run:true});
  out.textContent='[DRY RUN - changes nothing] gam '+r.display+'\\n\\n'+x.output+'\\n[exit code '+x.code+']'+(x.note?'\\n'+x.note:'');
  run.disabled=false;dry.disabled=false;
}
function showCustom(){
  CUR=null;
  document.getElementById('pane').innerHTML='<h2>Custom command</h2><div class="desc">Type any gam command (without the leading "gam").</div>'+
   '<div class="row"><textarea id="cc" rows="3" placeholder="print users fields primaryemail"></textarea></div>'+
   '<button id="run">Run</button><div class="out" id="out"></div>';
  document.getElementById('run').onclick=async()=>{
    const cmd=document.getElementById('cc').value.trim();if(!cmd)return;
    // 2.70: read the command first; anything destructive (or a batch file
    // GAMGUI cannot see into) needs "Are you sure" - same as the desktop.
    const k=await api('/api/classify',{command:cmd});
    if((k.kind==='destructive'||k.kind==='unknown')&&!confirm('This command '+k.text+':\\n\\ngam '+cmd+(k.warning?'\\n\\n'+k.warning:'')+'\\n\\nAre you sure you want to run it?'))return;
    const out=document.getElementById('out');out.textContent='[What this command does: '+k.text+']\\nRunning...\\n';
    const r=await api('/api/run',{command:cmd});
    out.textContent='[What this command does: '+k.text+']\\n'+r.output+'\\n[exit code '+r.code+']';
  };
}
// 2.84: Compromised account response - the desktop's guided workflow
// (same steps, run by the server; POST /api/compromised/start, then poll).
let CMPJOB=null, CMPTIMER=null;
function showCompromised(){
  CUR=null;
  const yesno=(id,a,b)=>'<select id="'+id+'"><option value="'+a[0]+'">'+a[1]+'</option><option value="'+b[0]+'">'+b[1]+'</option></select>';
  document.getElementById('pane').innerHTML=
   '<h2>Compromised account response</h2>'+
   '<div class="desc">Locks the account (a password nobody can type) and signs it out everywhere, saves the evidence on the server (filters, forwarding, delegates, app access, mobile devices, mail it sent, sign-in IP addresses, Drive and Gmail logs), removes app passwords and app access, turns off IMAP / POP, and can suspend it. Ends with a checklist of what GAM cannot do. Choose "Only collect the evidence" to change nothing.</div>'+
   '<div class="row"><label class="req">Compromised account</label><div class="pk"><input id="cemail" data-k="cemail" placeholder="user@example.com"><button class="sec" id="cpick">Pick...</button></div></div>'+
   '<div class="row"><label>What to do with the account</label><select id="ccontain"><option value="lock">Lock it out but keep it active (sign-in blocked, mail still arrives) - recommended</option><option value="suspend">Lock it out AND suspend it (also stops new mail)</option><option value="none">Only collect the evidence - change nothing (read-only)</option></select></div>'+
   '<div class="row"><label>Remove app passwords, backup codes and every app\\'s access</label>'+yesno('cdeprov',['yes','Yes - remove them (recommended)'],['no','No - leave them'])+'</div>'+
   '<div class="row"><label>Turn off IMAP and POP</label>'+yesno('cpopimap',['yes','Yes - turn them off (recommended)'],['no','No - leave them as they are'])+'</div>'+
   '<div class="row"><label>Turn off 2-Step Verification so the user re-enrolls (not possible where it is enforced)</label>'+yesno('c2sv',['no','No - leave it as it is'],['yes','Yes - the attacker may have added their own phone or key'])+'</div>'+
   '<div class="row"><label>Days of sign-in and activity logs</label><input id="cdays" value="30"></div>'+
   '<div class="row"><label>Phishing email that started it - From address (optional)</label><input id="cfrom"></div>'+
   '<div class="row"><label>Phishing email - Subject words (optional)</label><input id="csubject"></div>'+
   '<div class="row"><label>Type CONTAIN to confirm (not needed for evidence only)</label><input id="cword" placeholder="CONTAIN"></div>'+
   '<button id="cstart">Run</button> <span id="cnext"></span>'+
   '<div class="out" id="cout"></div>';
  document.getElementById('cpick').onclick=()=>openPicker({key:'cemail',picker:{kind:'users',all:false}});
  document.getElementById('cstart').onclick=startCompromised;
}
async function startCompromised(){
  const v=id=>document.getElementById(id).value.trim();
  const body={email:v('cemail'),contain:v('ccontain'),deprov:v('cdeprov'),popimap:v('cpopimap'),turnoff2sv:v('c2sv'),days:v('cdays'),from:v('cfrom'),subject:v('csubject'),word:v('cword')};
  if(body.contain!=='none'&&body.word!=='CONTAIN'){alert('Type CONTAIN to confirm - the account will be locked and signed out.');return;}
  const r=await api('/api/compromised/start',body);
  if(r.error){alert(r.error);return;}
  CMPJOB=r.job;document.getElementById('cstart').disabled=true;
  document.getElementById('cout').textContent='Starting...';
  if(CMPTIMER)clearInterval(CMPTIMER);
  CMPTIMER=setInterval(pollCompromised,1500);
}
// 2.84: the checklist on its own (read-only text from the server).
async function showChecklist(){
  CUR=null;
  document.getElementById('pane').innerHTML='<h2>Compromised account checklist</h2>'+
   '<div class="desc">What to do that GAM cannot do for you. Nothing is run.</div><div class="out" id="ckout">Loading...</div>';
  const r=await getj('/api/compromised/checklist');
  const o=document.getElementById('ckout');if(o)o.textContent=r.text||r.error||'';
}
async function pollCompromised(){
  if(!CMPJOB)return;
  const s=await getj('/api/compromised/status?job='+encodeURIComponent(CMPJOB));
  const out=document.getElementById('cout');if(out){out.textContent=s.output||'';out.scrollTop=out.scrollHeight;}
  if(s.status==='done'){
    clearInterval(CMPTIMER);CMPTIMER=null;
    const b=document.getElementById('cstart');if(b)b.disabled=false;
    const nx=document.getElementById('cnext');
    if(nx&&(s.from||s.subject)){
      nx.innerHTML='<button class="sec" id="cinc">Remove the phishing email from every mailbox (Incident response)</button>';
      document.getElementById('cinc').onclick=()=>{showIncident();document.getElementById('if').value=s.from||'';document.getElementById('is').value=s.subject||'';};
    }
  }
}
let INCJOB=null, INCTIMER=null;
function showIncident(){
  CUR=null;
  document.getElementById('pane').innerHTML=
   '<h2>Incident response - remove a phishing email from mailboxes</h2>'+
   '<div class="desc">Searches mailboxes for a matching message, shows the count, then (after you type DELETE to confirm) removes it by exact Message-ID and pulls Gmail/Drive audit reports. Evidence is saved on the server. Default scope is ALL mailboxes; narrow the scope (a domain, an OU and its sub-OUs, or a group) to run faster.</div>'+
   '<div class="row"><label class="req">From address</label><input id="if" placeholder="attacker@example.com"></div>'+
   '<div class="row"><label class="req">Subject text</label><input id="is" placeholder="Compensation Review &amp; Bonus (no quotes needed)"></div>'+
   '<div class="row"><label>Also sweep Drive for the attachment</label><select id="ids"><option value="off">No - skip Drive (default)</option><option value="auto">Yes - auto-detect the name from the emails</option><option value="manual">Yes - use the filename I enter</option></select></div>'+
   '<div class="row"><label>Attachment filename(s)</label><input id="ian" placeholder="comma separated - only for the filename option; matched files go to Trash"></div>'+
   '<div class="row"><label>Search scope</label><select id="isc"><option value="all">All mailboxes</option><option value="domains">Specific domain(s)</option><option value="ou_and_children">An OU and its sub-OUs</option><option value="group">A group</option></select></div>'+
   '<div class="row"><label>Scope value</label><input id="isv" placeholder="domain(s) / OU path / group email - blank for All"></div>'+
   '<div class="row"><label>Speed: parallel threads</label><input id="ith" placeholder="blank = config default (e.g. 20 for faster)"></div>'+
   '<div class="row"><label>Audit lookback days</label><input id="id" value="30"></div>'+
   '<div class="row"><label>Max delete per mailbox</label><input id="im" value="5000"></div>'+
   '<button id="istart">Search mailboxes</button>'+
   '<div id="iconfirm" style="display:none;margin-top:10px;padding:8px;background:#fce8e6;border-radius:4px"></div>'+
   '<div class="out" id="iout"></div>';
  document.getElementById('istart').onclick=startIncident;
}
async function startIncident(){
  const body={from:document.getElementById('if').value.trim(),subject:document.getElementById('is').value.trim(),days:document.getElementById('id').value.trim(),max:document.getElementById('im').value.trim(),scopetype:document.getElementById('isc').value,scopeval:document.getElementById('isv').value.trim(),threads:document.getElementById('ith').value.trim(),drivesweep:document.getElementById('ids').value,attachname:document.getElementById('ian').value.trim()};
  if(!body.from||!body.subject){alert('From address and Subject are required.');return;}
  if(body.scopetype!=='all'&&!body.scopeval){alert('The chosen search scope needs a value (domain, OU path, or group email).');return;}
  if(body.drivesweep==='manual'&&!body.attachname){alert('Enter the attachment filename for the Drive sweep, or choose auto-detect / skip.');return;}
  const r=await api('/api/incident/start',body);
  if(r.error){alert(r.error);return;}
  INCJOB=r.job;document.getElementById('istart').disabled=true;
  document.getElementById('iout').textContent='Starting discovery...';
  if(INCTIMER)clearInterval(INCTIMER);
  INCTIMER=setInterval(pollIncident,1500);
}
async function pollIncident(){
  if(!INCJOB)return;
  const s=await getj('/api/incident/status?job='+encodeURIComponent(INCJOB));
  const out=document.getElementById('iout');if(out){out.textContent=s.output||'';out.scrollTop=out.scrollHeight;}
  const cf=document.getElementById('iconfirm');
  if(s.status==='awaiting_confirm'){
    if(cf && cf.style.display==='none'){
      cf.style.display='block';
      cf.innerHTML='<b>'+s.count+' message(s) in '+s.mailboxes+' mailbox(es) matched.</b>'+(s.drivematches>0?(' <b>Plus '+s.drivematches+' matching Drive file(s)</b> will be moved to their owner\\'s Trash.'):'')+' Type DELETE to proceed, then click Delete.'+
        '<div class="row"><input id="iword" placeholder="type DELETE"></div>'+
        '<button id="idel">Delete</button> <button class="sec" id="icancel">Cancel</button>';
      document.getElementById('idel').onclick=()=>confirmIncident(document.getElementById('iword').value);
      document.getElementById('icancel').onclick=()=>confirmIncident('');
    }
  } else if(cf){ cf.style.display='none'; }
  if(s.status==='done'){clearInterval(INCTIMER);INCTIMER=null;const b=document.getElementById('istart');if(b)b.disabled=false;}
}
// 2.84: Find & delete from ONLY the mailboxes that have it - the incident
// job in "targeted" mode. It reuses the incident ids (istart / iconfirm /
// iout) so pollIncident and confirmIncident work unchanged.
function showTargeted(){
  CUR=null;
  const row=(id,lab,ph)=>'<div class="row"><label>'+lab+'</label><input id="'+id+'" placeholder="'+ph+'"></div>';
  document.getElementById('pane').innerHTML=
   '<h2>Find &amp; PERMANENTLY delete a message from ONLY the mailboxes that have it</h2>'+
   '<div class="desc">Two steps and fast: searches mailboxes for a message and shows how many matched, then - after you type DELETE - PERMANENTLY DELETES it (NOT recoverable, it does not go to Trash) from ONLY the mailboxes that had it. Every other mailbox is skipped. The lightweight version of Incident response: no Drive sweep, no audit reports. Fill in at least one search box; the exact Message-ID is the most precise. Evidence is saved on the server.</div>'+
   row('tf','From address','attacker@example.com')+
   row('ts','Subject words','no quotes needed')+
   row('tm','Message-ID (most precise)','e.g. CAB123@mail.example.com - the &lt; &gt; are optional')+
   row('tmore','More search words (optional)','e.g. after:2026/10/01 has:attachment')+
   '<div class="row"><label>Search scope</label><select id="tsc"><option value="all">All mailboxes</option><option value="domains">Specific domain(s)</option><option value="ou_and_children">An OU and its sub-OUs</option><option value="group">A group</option></select></div>'+
   row('tsv','Scope value','domain(s) / OU path / group email - blank for All')+
   row('tth','Speed: parallel threads','blank = config default (e.g. 20 for faster)')+
   '<div class="row"><label>Max per mailbox (seatbelt)</label><input id="tmx" value="5000"></div>'+
   '<button id="istart">Search mailboxes</button>'+
   '<div id="iconfirm" style="display:none;margin-top:10px;padding:8px;background:#fce8e6;border-radius:4px"></div>'+
   '<div class="out" id="iout"></div>';
  document.getElementById('istart').onclick=startTargeted;
}
async function startTargeted(){
  const v=id=>document.getElementById(id).value.trim();
  const body={mode:'targeted',from:v('tf'),subject:v('ts'),msgid:v('tm'),more:v('tmore'),scopetype:v('tsc'),scopeval:v('tsv'),threads:v('tth'),max:v('tmx')};
  if(!body.from&&!body.subject&&!body.msgid&&!body.more){alert('Fill in the From address, Subject words, Message-ID or More search words - a blank search would match EVERY message.');return;}
  if(body.scopetype!=='all'&&!body.scopeval){alert('The chosen search scope needs a value (domain, OU path, or group email).');return;}
  const r=await api('/api/incident/start',body);
  if(r.error){alert(r.error);return;}
  INCJOB=r.job;document.getElementById('istart').disabled=true;
  document.getElementById('iout').textContent='Searching...';
  if(INCTIMER)clearInterval(INCTIMER);
  INCTIMER=setInterval(pollIncident,1500);
}
// 2.84: Mailbox takeover audit - read-only, so no confirmation.
function showAudit(){
  CUR=null;
  document.getElementById('pane').innerHTML=
   '<h2>Mailbox takeover audit (one user)</h2>'+
   '<div class="desc">READ-ONLY. Shows the four things an attacker who got into a mailbox usually sets up: Gmail filters, forwarding addresses, send-as identities and delegates. Nothing is changed.</div>'+
   '<div class="row"><label class="req">Mailbox</label><div class="pk"><input id="aemail" data-k="aemail" placeholder="user@example.com"><button class="sec" id="apick">Pick...</button></div></div>'+
   '<button id="astart">Run audit</button>'+
   '<div class="out" id="aout"></div>';
  document.getElementById('apick').onclick=()=>openPicker({key:'aemail',picker:{kind:'users',all:false}});
  document.getElementById('astart').onclick=async()=>{
    const b=document.getElementById('astart');b.disabled=true;
    document.getElementById('aout').textContent='Running the four read-only checks...';
    const r=await api('/api/audit',{email:document.getElementById('aemail').value.trim()});
    b.disabled=false;
    if(r.error){document.getElementById('aout').textContent='';alert(r.error);return;}
    document.getElementById('aout').textContent=r.output||'';
  };
}
async function confirmIncident(word){
  const cf=document.getElementById('iconfirm');if(cf)cf.style.display='none';
  await api('/api/incident/confirm',{job:INCJOB,word:word});
}
boot();
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass   # quiet

    def _allowed(self, api):
        # Applies the request-security rules (see SESSION_TOKEN above). The
        # page itself only needs an allowed Host; every /api/ call also needs
        # the session token. Sends a 403 and returns False when refused.
        if not host_allowed(self.headers.get("Host", "")):
            self._send(403, json.dumps({"error": (
                "Refused: unexpected Host header. If you reach GAM Web through "
                "another hostname, add it to GAMWEB_ALLOWED_HOSTS.")}))
            return False
        if api and not hmac.compare_digest(
                self.headers.get("X-GAMWeb-Token", ""), SESSION_TOKEN):
            self._send(403, json.dumps({"error": "Refused: missing or wrong "
                                        "session token. Reload the page."}))
            return False
        return True

    def do_GET(self):
        # Route on the PATH only, ignoring any ?query string. Cloud Shell's Web
        # Preview requests the root as "/?authuser=0", so an exact self.path ==
        # "/" check would miss it and fall through to the 404 below (which
        # returns "{}") - that was the blank "{}" page in Cloud Shell.
        path = self.path.split("?", 1)[0]
        if not self._allowed(api=path.startswith("/api/")):
            return
        if path == "/" or path.startswith("/index"):
            # The session token is written into the page the browser loads;
            # only a page served from here can therefore call the API.
            self._send(200, PAGE.replace("__GAMWEB_TOKEN__", SESSION_TOKEN),
                       "text/html; charset=utf-8")
        elif path == "/api/tasks":
            self._send(200, json.dumps(tasks_json()))
        elif path == "/api/gam":
            self._send(200, json.dumps({"gam": GAM}))
        elif path == "/api/picktables":
            self._send(200, json.dumps(picker_tables()))
        elif path == "/api/incident/status":
            job_id = self.path.split("job=")[-1] if "job=" in self.path else ""
            self._send(200, json.dumps(incident_status(job_id)))
        elif path == "/api/compromised/status":
            job_id = self.path.split("job=")[-1] if "job=" in self.path else ""
            self._send(200, json.dumps(compromised_status(job_id)))
        elif path == "/api/workflow/status":
            job_id = self.path.split("job=")[-1] if "job=" in self.path else ""
            self._send(200, json.dumps(workflow_status(job_id)))
        elif path == "/api/compromised/checklist":
            # 2.84: the steps GAM cannot do (the desktop's checklist task).
            self._send(200, json.dumps({"text": gc.COMPROMISED_CHECKLIST}))
        else:
            self._send(404, "{}")

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length) or "{}")

    def do_POST(self):
        if not self._allowed(api=True):
            return
        # Only real JSON requests from our own page: a cross-site "simple"
        # request cannot carry this content type without a CORS preflight.
        if not self.headers.get("Content-Type", "").lower().startswith(
                "application/json"):
            self._send(415, json.dumps({"error": "JSON requests only"}))
            return
        try:
            data = self._body()
        except Exception:
            self._send(400, json.dumps({"error": "bad request"}))
            return
        if self.path == "/api/list":
            # 2.83: a Pick... list (read-only; see list_rows).
            self._send(200, json.dumps(list_rows(data)))
            return
        if self.path == "/api/search":
            # 2.82: the same search as the desktop app (every word, or one of
            # its synonyms, in the name / category / description / command).
            query = str(data.get("q", ""))[:200]
            keys = [cat + "|" + str(idx) for cat, idx, task in usable_tasks()
                    if gc.task_matches(query, cat, task)]
            self._send(200, json.dumps({"keys": keys}))
            return
        if self.path == "/api/build":
            try:
                task = gg.TASKS[data["cat"]][int(data["idx"])]
                if task.get("workflow") in gam_workflows.WORKFLOWS:
                    # 2.84: a workflow has no single command - the preview
                    # says whether the form is ready (or what is missing).
                    problem = workflow_check(task, data)
                    self._send(200, json.dumps(
                        {"workflow": True, "argv": [], "error": problem,
                         "display": "Runs several gam commands in order. Nothing "
                                    "changes until you answer its questions "
                                    "(Yes / No, or a word you type)."}))
                    return
                if (task.get("workflow") or task.get("audit")
                        or task.get("external") or task.get("interactive")):
                    self._send(200, json.dumps(
                        {"error": "This task is desktop-only for now; use the "
                                  "desktop GAMGUI or the gam CLI."}))
                    return
                # Date/time tasks: convert in the VIEWER's time zone (sent by
                # the browser), not this server's - Cloud Shell runs in UTC.
                tz = str(data.get("tz") or "")[:64]
                if gc.uses_local_time(task) and gc._zone_or_none(tz) is None:
                    # The zone name cannot be resolved here (e.g. Windows
                    # without tz data). Falling back to the server's zone is
                    # only safe when it matches the browser's current offset.
                    try:
                        browser_off = int(data.get("tzoffset"))
                    except (TypeError, ValueError):
                        browser_off = None
                    server_off = -int(datetime.datetime.now().astimezone()
                                      .utcoffset().total_seconds() // 60)
                    if browser_off != server_off:
                        self._send(200, json.dumps({"error": (
                            "Cannot convert your local time on this server "
                            "(its time zone differs from yours and zone data "
                            "is missing). Install the Python 'tzdata' package "
                            "on the server, or use the desktop GAMGUI.")}))
                        return
                    tz = ""
                # dry_run=true builds the "Preview (dry run)" form ('preview'
                # added / 'doit' left out); build_command refuses it for a
                # task that has no dry run.
                display, argv, err = gg.build_command(
                    task, collect(task, data.get("values", {})), tz=tz or None,
                    dry_run=bool(data.get("dry_run")))
                self._send(200, json.dumps(
                    {"display": display, "argv": argv, "error": err}))
            except Exception as exc:
                self._send(200, json.dumps({"error": str(exc)}))
        elif self.path == "/api/run":
            if not GAM:
                self._send(200, json.dumps(
                    {"output": "gam was not found on this machine.", "code": 1}))
                return
            if "command" in data:                      # custom command
                argv = _split(data["command"])
            else:
                argv = list(data.get("argv") or [])
            try:
                proc = subprocess.run([GAM] + argv, capture_output=True,
                                      text=True, encoding="utf-8",
                                      errors="replace", timeout=1800)
                result = {"output": (proc.stdout or "") + (proc.stderr or ""),
                          "code": proc.returncode}
                # A dry run's non-zero exit is often not an error (60 =
                # nothing matched); the page shows this plain-English line.
                if data.get("dry_run"):
                    result["note"] = gc.dry_run_note(proc.returncode)
                self._send(200, json.dumps(result))
            except Exception as exc:
                self._send(200, json.dumps({"output": str(exc), "code": 1}))
        elif self.path == "/api/classify":
            # 2.70: what a typed command does (read-only / changes /
            # destructive / unknown) - see gam_catalog.classify_command.
            kind, words = gc.classify_command(_split(str(data.get("command", ""))))
            self._send(200, json.dumps({
                "kind": kind, "text": gc.command_kind_text(kind, words),
                # 2.83: a known GAM bug this command would hit (e.g. #1997).
                "warning": gc.known_gam_bug(_split(str(data.get("command", ""))),
                                            gam_version())}))
        elif self.path == "/api/incident/start":
            self._send(200, json.dumps(incident_start(data)))
        elif self.path == "/api/workflow/start":
            # 2.84: the Drive sharing workflows (see workflow_start).
            self._send(200, json.dumps(workflow_start(data)))
        elif self.path == "/api/rollover/years":
            # 2.85: the Chromebook OU rollovers (rollover_*).
            self._send(200, json.dumps(rollover_years(data)))
        elif self.path == "/api/rollover/scan":
            self._send(200, json.dumps(rollover_scan(data)))
        elif self.path == "/api/rollover/plan":
            self._send(200, json.dumps(rollover_plan(data)))
        elif self.path == "/api/rollover/start":
            self._send(200, json.dumps(rollover_start(data)))
        elif self.path == "/api/dlp/list":
            # 2.84: Edit a DLP detector (dlp_list / dlp_preview / dlp_save).
            self._send(200, json.dumps(dlp_list(data)))
        elif self.path == "/api/dlp/preview":
            self._send(200, json.dumps(dlp_preview(data)))
        elif self.path == "/api/dlp/save":
            self._send(200, json.dumps(dlp_save(data)))
        elif self.path == "/api/admin/lists":
            # 2.84: Set up an administrator (admin_lists / preview / start).
            self._send(200, json.dumps(admin_lists(data)))
        elif self.path == "/api/admin/preview":
            self._send(200, json.dumps(admin_preview(data)))
        elif self.path == "/api/admin/start":
            self._send(200, json.dumps(admin_start(data)))
        elif self.path == "/api/workflow/confirm":
            self._send(200, json.dumps(workflow_confirm(data)))
        elif self.path == "/api/workflow/stop":
            self._send(200, json.dumps(workflow_stop(data)))
        elif self.path == "/api/audit":
            # 2.84: the read-only Mailbox takeover audit (see mailbox_audit).
            self._send(200, json.dumps(mailbox_audit(data)))
        elif self.path == "/api/compromised/start":
            # 2.84: see compromised_start.
            self._send(200, json.dumps(compromised_start(data)))
        elif self.path == "/api/incident/confirm":
            self._send(200, json.dumps(incident_confirm(data)))
        else:
            self._send(404, "{}")


def _split(command):
    # Split a hand-typed command line like the desktop app does (no shell).
    s = command.strip()
    if s.lower().startswith("gam "):
        s = s[4:]
    return gg.win_split(s)


def main():
    print("GAM Web starting on http://127.0.0.1:%d/" % PORT)
    if GAM:
        print("gam: %s" % GAM)
    else:
        print("gam: NOT FOUND. Install/authorize GAM, then either add it to the")
        print("     PATH or start with:  python3 gam_web.py /path/to/gam")
    print("In Google Cloud Shell, click 'Web Preview' -> 'Preview on port %d'."
          % PORT)
    print("Press Ctrl+C to stop.")
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
