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
#   - Multi-step "workflow" tasks (incident response, bulk license, archive
#     courses, drive transfer) are desktop-only for now and are hidden here;
#     use the desktop GAMGUI or the gam CLI for those.
# =============================================================================

import os
import sys
import json
import html
import types
import csv
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

def usable_tasks():
    # Every plain (non-workflow) task, as (category, index, task).
    for cat, tasks in gg.TASKS.items():
        for idx, task in enumerate(tasks):
            if task.get("workflow") or task.get("audit") or task.get("external") \
                    or task.get("interactive"):
                continue
            yield cat, idx, task


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
            })
        cats.setdefault(cat, []).append({
            "cat": cat, "idx": idx, "name": task["name"],
            "desc": task["desc"], "destructive": task["destructive"],
            "fields": field_list,
            # The GAM wiki page for this task (same as the desktop button).
            "doc": gc.task_doc_url(cat, task),
            # True when the task takes a local date/time that becomes UTC.
            "localtime": "{zulu:" in (task.get("template") or ""),
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

    try:
        stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        incdir = os.path.join(gg.LOG_DIR, "Incident_" + stamp)
        os.makedirs(incdir, exist_ok=True)
        match_csv = os.path.join(incdir, "MatchedMessages.csv")
        query = gg.incident_query(job["from"], job["subject"])

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
    if not sender or not subject:
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
           "drivesweep": drivesweep, "attachname": attachname, "drivematches": 0}
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
            "output": "".join(job["log"])}


def incident_confirm(data):
    job = INCIDENT_JOBS.get(data.get("job"))
    if not job:
        return {"error": "unknown job"}
    job["proceed"] = (data.get("word") == "DELETE")
    job["confirm_event"].set()
    return {"ok": True, "proceed": job["proceed"]}


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
</style></head><body>
<header>GAM Web <small>a browser front-end for GAM (Cloud Shell friendly)</small></header>
<div id="gam" class="gam"></div>
<div class="wrap">
  <div class="left"><div class="search"><input id="q" placeholder="Search tasks..."></div><div id="tree"></div></div>
  <div class="right">
    <div id="pane"><p class="desc">Pick a task on the left, or use Custom command.</p></div>
  </div>
</div>
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
  const cats=await getj('/api/tasks');
  const tree=document.getElementById('tree');
  for(const cat in cats){
    const c=document.createElement('div');c.className='cat';c.textContent=cat;c.dataset.cat=cat;tree.appendChild(c);
    for(const t of cats[cat]){
      const d=document.createElement('div');d.className='task'+(t.destructive?' d':'');d.textContent=t.name;d.dataset.cat=cat;d.dataset.search=(cat+' '+t.name).toLowerCase();
      d.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));d.classList.add('sel');showTask(t);};
      tree.appendChild(d);
    }
  }
  const inc=document.createElement('div');inc.className='task d';inc.textContent='Incident response (Email Cleanup)';
  inc.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));inc.classList.add('sel');showIncident();};
  tree.appendChild(inc);
  const cc=document.createElement('div');cc.className='task';cc.textContent='Custom command';
  cc.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));cc.classList.add('sel');showCustom();};
  tree.appendChild(cc);
  document.getElementById('q').oninput=filterTree;
}
// Live search: show tasks whose category or name contains the text; hide
// categories with no match. Clearing the box shows everything again.
function filterTree(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  const shown={};
  document.querySelectorAll('#tree .task').forEach(d=>{
    const ok=!q||!d.dataset.search||d.dataset.search.includes(q);
    d.style.display=ok?'':'none'; if(ok&&d.dataset.cat)shown[d.dataset.cat]=1;});
  document.querySelectorAll('#tree .cat').forEach(c=>{c.style.display=(!q||shown[c.dataset.cat])?'':'none';});
}
function showTask(t){
  CUR=t;let h='<h2>'+esc(t.name)+' <a class="doc" target="_blank" rel="noopener noreferrer" href="'+esc(t.doc)+'">GAM docs</a></h2><div class="desc">'+esc(t.desc)+'</div>';
  if(t.localtime){h+='<div class="tz">Times are in your time zone ('+esc(Intl.DateTimeFormat().resolvedOptions().timeZone||'local')+') and are converted to UTC for Google.</div>';}
  for(const f of t.fields){
    h+='<div class="row"><label class="'+(f.required?'req':'')+'">'+esc(f.label)+'</label>';
    if(f.options){h+='<select data-k="'+esc(f.key)+'">'+f.options.map(o=>'<option'+(o===f.default?' selected':'')+'>'+esc(o)+'</option>').join('')+'</select>';}
    else{h+='<input data-k="'+esc(f.key)+'" value="'+esc(f.default)+'">';}
    h+='</div>';
  }
  h+='<div class="prev" id="prev"></div>';
  h+='<button id="run">Run</button> <button class="sec" onclick="copyCmd()">Copy</button>';
  h+='<div class="out" id="out"></div>';
  document.getElementById('pane').innerHTML=h;
  document.querySelectorAll('[data-k]').forEach(i=>i.oninput=build);
  document.getElementById('run').onclick=run;
  build();
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
  document.getElementById('prev').textContent=r.error?('('+r.error+')'):('gam '+r.display);
  window._argv=r.argv;window._err=r.error;
}
function copyCmd(){navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('prev').textContent);}
async function run(){
  if(window._err==='building'){await build();}
  if(window._err){alert('Fill in the required fields first.');return;}
  if(CUR.destructive && !confirm('This is a DESTRUCTIVE action:\\n\\ngam '+document.getElementById('prev').textContent.replace(/^gam /,'')+'\\n\\nAre you sure?'))return;
  const out=document.getElementById('out');out.textContent='Running...\\n';
  const btn=document.getElementById('run');btn.disabled=true;
  const r=await api('/api/run',{argv:window._argv});
  out.textContent=r.output+'\\n[exit code '+r.code+']';btn.disabled=false;
}
function showCustom(){
  CUR=null;
  document.getElementById('pane').innerHTML='<h2>Custom command</h2><div class="desc">Type any gam command (without the leading "gam").</div>'+
   '<div class="row"><textarea id="cc" rows="3" placeholder="print users fields primaryemail"></textarea></div>'+
   '<button id="run">Run</button><div class="out" id="out"></div>';
  document.getElementById('run').onclick=async()=>{
    const cmd=document.getElementById('cc').value.trim();if(!cmd)return;
    const out=document.getElementById('out');out.textContent='Running...\\n';
    const r=await api('/api/run',{command:cmd});
    out.textContent=r.output+'\\n[exit code '+r.code+']';
  };
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
        elif path == "/api/incident/status":
            job_id = self.path.split("job=")[-1] if "job=" in self.path else ""
            self._send(200, json.dumps(incident_status(job_id)))
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
        if self.path == "/api/build":
            try:
                task = gg.TASKS[data["cat"]][int(data["idx"])]
                if (task.get("workflow") or task.get("audit")
                        or task.get("external") or task.get("interactive")):
                    self._send(200, json.dumps(
                        {"error": "This task is desktop-only for now; use the "
                                  "desktop GAMGUI or the gam CLI."}))
                    return
                # Date/time tasks: convert in the VIEWER's time zone (sent by
                # the browser), not this server's - Cloud Shell runs in UTC.
                tz = str(data.get("tz") or "")[:64]
                if "{zulu:" in (task.get("template") or "")                         and gc._zone_or_none(tz) is None:
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
                display, argv, err = gg.build_command(
                    task, collect(task, data.get("values", {})), tz=tz or None)
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
                self._send(200, json.dumps(
                    {"output": (proc.stdout or "") + (proc.stderr or ""),
                     "code": proc.returncode}))
            except Exception as exc:
                self._send(200, json.dumps({"output": str(exc), "code": 1}))
        elif self.path == "/api/incident/start":
            self._send(200, json.dumps(incident_start(data)))
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
