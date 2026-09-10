# NOTES.md - GAMGUI

## WHAT HAS BEEN DONE
- 09-10-2026: AUTO-UPDATER updategamgui.ps1 (modeled on the community GAM
  updater NoSubstitute/gamupdate, but adapted). Keys off the GitHub latest-
  release TAG vs a marker file (gamgui-version.txt in the install folder) since
  GAMGUI has no self-version-check command. Adds SHA-256 verification (parsed
  from the release body, which publishes the zip hash) - an improvement over the
  reference which does no checksum. Installs via robocopy /MIR /XF gamgui.ini
  gamgui-version.txt /XD Logs (preserves settings + logs + marker). Refuses to
  overwrite a RUNNING instance, but only when the running exe's path is under
  the target InstallRoot (precise, not global). Doubles as a fresh installer.
  PS 5.1 + 7 compatible, TLS 1.2 forced, ASCII-only, full header + comments.
  Switches: -InstallRoot, -Repo, -Force, -Quiet (scheduled), -Launch. Logs to
  <install>\Logs\GAMGUI-Update.log (MM-DD-YYYY HH:MM:SS). TESTED end-to-end into
  a throwaway folder: fresh install (none->2.7, SHA OK), already-current, and
  -Force reinstall all pass. Wrote a "2.7" marker into the real C:\GAM7\GAMGUI
  so Gabe's first run won't needlessly reinstall. Build-EXE.bat now copies the
  script into dist\GAMGUI (future zips bundle it). GitHub API used:
  https://api.github.com/repos/<owner>/<repo>/releases/latest with a User-Agent
  header (required or 403). WHY PowerShell not Batch: REST/JSON/zip/SHA/mirror.
- 09-10-2026: v2.7 BULK SHOW/HIDE CALENDARS (the real fix for Gabe's Classroom
  calendars). Gabe's bulk delete-acl FAILED with "Cannot change your own access
  level" - a hard Google Calendar API restriction (cannotChangeOwnAcl): you
  cannot delete/modify your OWN ACL rule, even as owner. Read the ACLs of one
  of his calendars: owners = the calendar's own system address + a PER-COURSE
  teachers group (..._teachers_...@fsisd.net) + Gabe. No single common human
  owner to impersonate, so truly removing him would mean impersonating a teacher
  per course (invasive/fragile). SOLUTION = bulk HIDE from his list (his own
  calendarList, never restricted, reversible). Verified on one calendar:
  `gam user gabriel.clifton@ update calendars <cal> selected false hidden true`
  -> Updated. Added GUI task "Bulk show/hide calendars in a user's list from a
  CSV" (user {email} update calendars csvfile {file}:{idcol} [selected][hidden]
  [color]) - UserCalendarEntity accepts CSVFileSelector so one run does the
  whole column; runs under DEFAULT account (impersonates the named user via
  DWD, no gclifton needed). Updated "Bulk REMOVE calendar access" desc to note
  the self-removal restriction. GAM fact learned: gam <user> delete calendaracls
  <cal> <scope> (line 6327) is the user-scoped ACL delete - ANOTHER owner could
  remove Gabe, but not Gabe himself. 307 tasks.
- 09-10-2026: v2.6 BULK CALENDAR SHARING FROM CSV. Gabe owns 500+ Google
  Classroom calendars (added by a program; each has other owners too) and wants
  to drop himself as owner in bulk. Added two Calendars tasks that use GAM's
  native CalendarEntity csvfile selector so ONE gam run handles the whole
  column (fast, parallelized) instead of one gam per row:
  "Bulk REMOVE calendar access from a CSV" (calendars csvfile <file>:<idcol>
  delete acls <scope>, destructive) and "Bulk GRANT ..." (add acls <role>
  <scope> sendnotifications false). Verified the csvfile:field selector parses
  a Windows drive-colon path (both / and \\ forms) via a read-only show-acls
  test with a throwaway CSV. CRITICAL run note baked into the task descriptions:
  pick the Domain/config section that OWNS the calendars (Gabe's own gclifton
  section authed as gabriel.clifton@), NOT the default fsisd.gam account which
  is not an owner. Discovery command for the ID list: gam user
  gabriel.clifton@fsisd.net print calendars ownedsecondary todrive (ownedsecondary
  = exactly the secondary calendars he owns; id column = "id"). 306 tasks / 29
  categories.
- 09-10-2026: v2.5 COVERAGE FILL + HUMAN-READABLE DROPDOWNS. Ran the coverage
  audit (tests/coverage_audit.py), closed the high-value gaps as guided tasks,
  and left niche commands to the console per Gabe's chosen scope. 265 -> 304
  tasks, 28 -> 29 categories; audit "rough guided coverage" 23% -> 27% (the
  audit is a heuristic; the real jump is that the useful daily commands are now
  guided). All new templates spot-checked with build_command; multi-word values
  stay single argv tokens (template is split BEFORE placeholder fill).
  - Dropdown wording now matches the Google product, not the raw API value:
    Calendar sharing = Google's exact labels ("See only free/busy (hide
    details)" ...); calendar show/hide = Yes/No (was true/false); calendar
    Color = dropdown of Google's 24 named colors. Vault Data type =
    Gmail/Drive/Groups/Calendar/Chat/Voice (was mail/hangouts_chat); matter
    State = Open/Closed/Deleted. valuemap is applied by BOTH front-ends
    (GAMGUI _collect_values and gam_web), so friendly label -> gam value works
    in the browser twin too. Pattern for an OPTIONAL humanized dropdown: put a
    "": "" blank key first so "leave unset" stays selectable.
  - New guided tasks: Contacts (update shared contact; user personal/other
    contacts + contact groups; domaincontacts), a NEW "Cloud Identity Devices"
    category (print/info devices+deviceusers, approve/block/wipe/cancelwipe,
    delete device, register company-owned device), Classroom (create/update/
    info course, sync teachers, list coursework/announcements/topics/student-
    groups, remove guardian, cancel guardian invite), Gmail (update/info
    sendas, forwardingaddress info/delete/domain export), Vault (saved queries
    create/list/info/delete, print vaultcounts).
- 09-03-2026: v2.0 FULL-COVERAGE EXPANSION (for a conference where Gabe teaches
  GAM and presents GAMGUI). Catalog grew to 233 guided tasks across 26
  categories, targeting every GAM7 command. Approach A (hybrid): guided forms
  for the common commands + a per-task "Extra arguments (advanced)" rawappend
  box + a raw "Run ANY GAM command" console = three completeness layers, so
  nothing is unreachable without drowning beginners.
  - Moved the catalog + builder into gam_catalog.py (re-exported from
    GAMGUI.py) so desktop and gam_web.py share one source. Web inherits 226
    guided tasks automatically.
  - Added a headless validator (tests/validate_catalog.py) that builds every
    task and gates each batch; added unit tests for rawappend and the domain
    selector.
  - Added the multi-domain dropdown (reads gam.cfg sections via GAMCFGDIR +
    manual add). Verified empirically that "gam select <section> <cmd>" is a
    one-shot that does NOT persist the saved default. Injected into all three
    gam Popen sites.
  - Added a search box (filters the 233-task tree live) and a pinned "Common
    Tasks" category.
  - New categories: Domains, Shared Drives (dedicated), Vault (dedicated),
    Mobile Devices, Custom Schemas, Contacts, Admin Roles & Privileges, Data
    Transfers, Chrome Printers, Buildings/Features/Rooms, Customer/Settings.
  - All syntax verified against C:\GAM7\GamCommands.txt (GAM's own grammar).
    Fixed latent bugs: multi-user OU move, Chromebook powerwash targeting.
- (Earlier versions below.)

## WHAT WAS DONE (earlier)
- 07-23-2026: v1.0 built. Single-file tkinter app (stdlib only), 71 tasks
  in 13 categories + Custom command mode. Data-driven task catalog
  (TASKS dict) with template renderer supporting optional [segments] and
  {key|fallback} tokens. Threaded execution with live output, session
  logging, destructive-action confirmations, gam auto-detection with
  gamgui.ini persistence.
- 07-23-2026: Unit-tested build_command(): required/optional/fallback/
  quoting cases plus a sweep proving all 71 task templates render.
- 07-23-2026: README.txt, Build-EXE.bat (CRLF-verified) written.

## WHAT STILL NEEDS TO BE DONE
- Live GUI click-through test by Gabe (automated tests covered the
  command builder, not the widgets).
- Windows EXE build via PyInstaller (in progress this session).
- macOS/Linux build + test (source runs cross-platform; needs a tester).
- Screenshots for the GAM team submission.

## IDEAS FOR IMPROVEMENT
- CSV bulk-run builder: pick a CSV, map columns to a task's fields,
  generate a "gam csv" command.
- Favorites/recent commands list.
- Per-task "open wiki page" help button (slugs are known).
- Dark mode; larger font option for projector demos.
- Dry-run mode that appends "preview" where GAM supports it.

## KNOWN ISSUES / BUGS
- Combobox for optional dropdown fields defaults to first choice when
  required, blank when optional - verify UX feels right in live use.
- Commands run via shell=True; the editable preview is intentionally a
  power-user feature but means GAMGUI trusts its operator like a
  terminal does. Documented in README section 8.

## SESSION LOG
- 09-09-2026: v2.3 - Added an "OAuth Setup" category at the top (authorize /
  refresh the GAM account from the GUI). New interactive=True task type
  launches gam oauth create/update in its own console (browser sign-in + scope
  menu), honoring the Domain dropdown; excluded from the web version. Also
  helped resolve a Vault export DOWNLOAD failure: Google Vault grants Cloud
  Storage access only to the export's CREATOR, so downloading exports made by
  gabriel.clifton@ while GAM auths as fsisd.gam@ returns 403. Set up a locked
  [gclifton] gam.cfg config section (own config_dir, ACL restricted to Gabe)
  so GAM can authenticate as the creator; it appears in the Domain dropdown.
  Wrote a GAM feature proposal (docs/GAM-role-aware-oauth-proposal.md) for the
  GAM maintainers on role-aware oauth scope selection. Released 2.3.
- 09-04-2026: v2.2 - Incident workflow now optionally hunts the phishing
  ATTACHMENT in Drive and removes it (desktop + web). Opt-in "Also sweep Drive
  for the attachment": auto-detect the filename from the caught emails (adds
  attachmentnamepattern .* showattachments to discovery, parses any CSV column
  with "attachment" in its header) or type it. Searches the same scope for
  OWNED copies (print filelist query "name = '<n>'" showownedby me
  excludetrashed), shows the match count at the single DELETE confirmation,
  then TRASHES matches (user <owner> trash drivefile id:<id>) - recoverable,
  not purge, because filename matching can false-positive. New evidence CSV
  DriveAttachmentMatches.csv. Verified all gam syntax; tested the full web
  flow with a mocked gam (auto-detect -> search -> trash). Rebuilt EXE (title
  GAMGUI 2.2; note: first launch was slow, CrowdStrike scanning the fresh
  exe - opens in ~2s after), made GAMGUI-v2.2-Windows.zip. Pushed both repos.
  DEPLOY PENDING: Gabe's instance was running, so C:\GAM7 not refreshed yet.
- 09-04-2026: v2.1 - Email Cleanup scope + speed, and Domain-dropdown fix.
  (1) The Domain dropdown was listing gam.cfg sections co/coac/coactec/cotec,
  which are NOT other domains - they are cros-reporting presets that inherit
  config_dir from [DEFAULT]. Fixed _domain_choices to show only sections with
  their OWN config_dir (real separate tenants); those 4 now correctly hide.
  (2) Added a Search-scope selector (All mailboxes / domain(s) / OU+children /
  group) and a parallel-threads box to every Email Cleanup task AND the
  incident workflow, on desktop and the web version. New {mailscope:type:val}
  template token. Verified against real gam that "config num_threads" must come
  BEFORE "redirect". Rebuilt EXE (title confirms GAMGUI 2.1), redeployed to the
  C:\GAM7 folder via robocopy, made GAMGUI-v2.1-Windows.zip. Pushed to GitHub.
- 09-04-2026: v2.0 - Built the one-folder EXE from the full-coverage source
  (233 tasks). Fixed Build-EXE.bat (added --noconfirm so it is re-runnable;
  it was aborting COLLECT when dist\GAMGUI already existed). Verified the
  package: 0 .enc files, Tcl/Tk data bundled, packaged app launches with the
  "GAMGUI 2.0" window (confirms gam_catalog.py is bundled). Deployed to the
  C:\GAM7 GAMGUI folder via robocopy /MIR (excluded gamgui.ini and Logs) only
  after Gabe closed his running instance. Produced GAMGUI-v2.0-Windows.zip
  (14.1 MB) for a GitHub Release upload.
- 09-03-2026: v2.0 - Full-coverage catalog expansion (see WHAT HAS BEEN DONE).
- 08-06-2026: v1.9 - Fixed the real startup crash ("Tcl data directory
  _tcl_data not found") Gabe hit repeatedly. NOT the temp/_MEI theory (that
  was a partial red herring) - actual root cause: Python 3.14 uses Tcl/Tk 9
  which embeds its script library in the DLL via zipfs (//zipfs:/...), and
  PyInstaller 6.21 does not bundle it -> _tcl_data missing -> tkinter can't
  init -> crash EVERY launch. The "intermittent success" was the windowed
  crash DIALOG keeping the process alive and fooling my HasExited check;
  reliable detection = look for a traceback in captured stderr. Fix: switch
  to ONE-FOLDER packaging + extract_tcl.py (Tcl [file copy] from zipfs to
  disk) + --add-data _tcl_data/_tk_data. 7/7 clean launches. Now installed
  at C:\GAM7\GAMGUI\ (folder), with "Launch GAMGUI" shortcut in C:\GAM7; old
  one-file C:\GAM7\GAMGUI.exe removed. Build-EXE.bat -> v2.0 (extract step).
  NOTE: app_dir moved to C:\GAM7\GAMGUI so logs/gamgui.ini now live there;
  gam auto-detected via PATH (C:\GAM7\gam.exe). DEPLOY RULE: never
  Stop-Process -Force Gabe's open instance; build to dist, copy when idle.
  8 orphaned _MEI folders remain in C:\Temp (sandbox blocked cleanup;
  harmless, one-folder makes no new ones - Gabe can clear C:\Temp\_MEI* any
  time).
- 08-06-2026: v1.8 - Gabe reported a Python error on screen. Investigated:
  scanned all 08-06 GAMGUI logs, NO tracebacks; his runs aborted at
  discovery (rc60/50, pre-v1.7 bug). Most likely cause of the on-screen
  error was my Stop-Process -Force killing his open instance during rebuilds
  -> STOP force-killing his instance; check-not-running / ask-to-close
  instead. Found + fixed a REAL latent bug while auditing the now-reachable
  (post-v1.7) confirm/delete/audit phases: _poll_output could deadlock the
  worker (confirm dialog exception left event unset) and kill the poll loop
  (exception skipped the after() reschedule) -> hardened with finally on
  both event.set and reschedule + catch-all. NOTE for future deploys: build
  to dist, copy only when no GAMGUI running; never force-kill his instance.
- 07-23-2026: v1.7 - Fixed incident workflow aborting mid-discovery.
  Root cause: "all users print messages" over ~27k users returns nonzero
  (rc50) because some mailboxes always fail (suspended/unlicensed/no
  mailbox), and Phase 1 treated any nonzero as fatal. Reproduced with a
  2-user set (1 nonexistent) -> rc50 but CSV still written. Fix: abort only
  on cancel (rc -1) or missing CSV; nonzero-with-CSV -> informational note +
  continue. Standalone Delete/Trash/Search-ALL tasks show the nonzero exit
  code but still work (they don't gate a multi-phase flow); could add a
  similar note later.
- 07-23-2026: v1.6 - Diagnosed Gabe's "&" 0-match: read-only gam echo probe
  proved gam receives the full query+& intact, so it is GMAIL quoted-phrase
  strictness, NOT a GAMGUI bug. Fix: incident_query() now builds
  subject:(...) grouped words instead of an exact quoted phrase (punctuation
  tolerant, more reliable); verified gam accepts/echoes it. Added Security >
  "Mailbox takeover audit (one user)" (read-only sweep: show filters/
  forwardingaddresses/sendas/delegates - all 4 verified rc=0 on real gam)
  and "Show mailbox rules (Gmail filters)". Honest limitation surfaced to
  Gabe: Gmail API exposes no filter creation timestamp, so "freshly created"
  rules can't be isolated - audit lists all current rules instead. Wrote
  HOW-TO-GUIDE.txt (11 parts) for non-technical coworkers - this is the doc
  to ship with the GUI to end users.
- 07-23-2026: v1.5 - Built the incident-response workflow INTO the app
  (replaces the launcher for Gabe's machine-local batch script, making it
  portable for GAM-team distribution). Four phases mirroring the batch
  original: discovery -> typed-DELETE confirm (marshalled from worker
  thread to UI via queue+Event) -> delete by Message-ID with query
  fallback -> Gmail/Drive audit pulls with gmaileventtypes fallback.
  Evidence in Logs\Incident_<stamp>\. Verified gam's actual CSV headers
  (User,threadId,id,From,To,Subject,Message-ID,Date) with a read-only
  probe before writing the parser. NOT ported: attachment hash/Drive
  presence correlation from Analyze-GAMEmailCleanupData.ps1 - documented
  as a known limitation and a future enhancement.
- 07-23-2026: v1.4 - Gabe found "&" in a subject cut the delete command in
  half (query truncated AND doit/max never reached gam). Root cause:
  shell=True + cmd.exe not understanding \" escapes, so & acted as a
  command separator. Rewrote execution to shell-less argv: build_command
  now returns (display, argv, error); unedited form runs use the exact
  argv, edited/custom commands go through win_split (Windows-rule
  splitter that preserves backslash paths). Proven end-to-end with an
  argv-echo child using Gabe's exact failing subject. Trade-off: no shell
  pipes/> in Custom mode (documented; GAM redirect/todrive covers it).
  Also added inline examples to all query/ID/OU prompts per Gabe's
  feedback for non-GAM-savvy operators.
- 07-23-2026: v1.3 - Gabe's live test caught doit ordering: GAM wants
  "max_to_delete N doit" (doit LAST), I had "doit max_to_delete N" and GAM
  errored asking for doit. Fixed in all 4 message trash/delete templates;
  grep confirms no template has arguments after doit anywhere. Lesson
  matches the standing "verify external CLI behavior" memory - the
  EmailCleanup batch script had the correct order all along. Also: Gabe
  reported no domain-level search-and-destroy - he was likely running a
  stale v1.1 window; the Email Cleanup category shipped in v1.2 and the
  title bar now shows the version for disambiguation.
- 07-23-2026: v1.2 - Added Email Cleanup category per Gabe: domain-wide
  search/trash/delete (max-per-mailbox seatbelt, defaults mirroring his
  EmailCleanup batch workflow) + external-task launcher that opens
  GAM7-Workspace-Email-Cleanup.bat in its own console (it is interactive,
  cannot run in the output pane). Fixed quote_if_needed stripping embedded
  quotes - Gmail queries with subject:"phrase" now escape as \". Tests:
  quote escaping, 75-task sweep, external path check. Installed to C:\GAM7.
- 07-23-2026: Initial build session (cheat sheet + test plan + GAMGUI).
- 07-23-2026: v1.1 - Gabe reported Stop button did not stop gam. Root
  cause: shell=True wraps gam in cmd.exe; proc.kill() killed only the
  wrapper. Fixed with taskkill /T /F (Windows) / process-group SIGKILL
  (POSIX); verified with synthetic child-process repro test. Ctrl+C-style
  graceful interrupt ruled out: windowed apps have no console to deliver
  console control events. Rebuild initially failed with a file lock -
  lingering GAMGUI.exe instances held dist\GAMGUI.exe; killed and rebuilt.
  v1.1 installed to C:\GAM7\GAMGUI.exe (hash-verified).
