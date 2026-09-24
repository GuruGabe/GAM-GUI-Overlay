# NOTES.md - GAMGUI

## WHAT HAS BEEN DONE
- 09-22-2026: v2.18 GAM group page-2 attempt. IMPORTANT TOOLING LIMIT: the
  google-apps-manager group's SPA only exposes ~30 recently-active threads to an
  UNAUTHENTICATED crawler (WebFetch and the in-app browser); infinite-scroll
  will NOT load older/archive threads without a signed-in session (tried JS
  scrollTop on containers AND real mouse-wheel scroll via computer tool - 0 new
  beyond the ~30). Only 1 genuinely new how-to thread appeared vs v2.17's page:
  "Request for Google Workspace Application Usage & Last Activity" (Ross pointed
  to the Reports wiki, no verbatim cmd). Added Reports task "ALL users - usage &
  activity report (CSV/Sheet)" = `report users {todrive}` (we only had per-user
  `report user user {email}`). 318 tasks. TO GO DEEPER into older threads Gabe
  must feed links from his signed-in view, OR use claude-in-chrome w/ his
  session, OR better: re-run tests/coverage_audit.py against GamCommands.txt (the
  COMPLETE capability list) to find gaps systematically - proposed to Gabe.
- 09-22-2026: v2.17 GAM GROUP COVERAGE PASS (Gabe: read the google-apps-manager
  Google Group, ensure GAMGUI can do whatever people ask about). Group is PUBLIC
  (WebFetch reads it, no creds). Read page 1 (28 threads) + fetched the 5 key
  "how do I X" threads for exact commands. Added 5 guided tasks for real gaps:
  (1) Users "Bulk delete users from a CSV" (csv {file} gam delete user
  ~{emailcol}). (2) Calendars "Remove an event from EVERYONE's calendar
  (phishing invite)" ({mailscope} delete events primary matchfield organizeremail
  {organizer} doit). (3) Contacts "Remove a bad address from EVERYONE's Other
  contacts" ({mailscope} delete othercontacts emailmatchpattern {pattern}) -
  from the Brian Lee phishing-contact thread. (4) Groups "Sync group members
  from a CSV" (update group {group} sync member csvfile {file}:{emailcol}).
  (5) Shared Drives "List Shared Drive organizers/managers" (print
  shareddriveorganizers). Rest of page 1 already covered or niche (dynamic
  groups, shared-drive file-level access = console). ONGOING: only page 1 done -
  the group has many pages of history; continue in future rounds. All reachable
  via console meanwhile. 317 tasks.
- 09-22-2026: v2.16 NEW Groups task "List members by ROLE (one or more groups) -
  CSV/Sheet" (`print group-members select {groups} roles {role} {todrive}`).
  Gabe couldn't find a role-filtered member export. select accepts one or a
  comma-list of groups; roles = member|manager|owner (GroupRoleList, comma
  combos via valuemap); *_out() for Screen/Sheet/CSV. Output cols
  group,type,role,id,status,email. Also added *_out() to the existing "List
  members" (was single group, no export). Verified select+roles parses and
  builds (incl. redirect-csv prefix). 312 tasks.
- 09-22-2026: v2.15 two fixes from Gabe's testing.
  (1) WORKFLOW PREVIEWS showed prose ("Workflow: ... Click Run") instead of gam
  commands - GAMGUI is meant to TEACH the commands. Rewrote the preview branches
  for targetedcleanup, drivewipe, removeextaccess, AND the full incident
  workflow to show the REAL two gam commands (FIND + action) with live values
  substituted (scope, threads, query, ~user/~~msgid~~/~~fileid~~). Bumped
  preview_box height 3->6. NOTE for future: workflows can SHOW commands but not
  be edited (they run their own orchestration); the ~305 regular tasks remain
  the exact editable command. Older workflows (transferdrive/shareddrive/
  archivecourses/bulklicense) still show prose - offered to convert if Gabe
  wants (they have branching logic). (2) BUG in incident Drive sweep: it
  searched scope_entity (e.g. ALL users) for the attachment FILENAME ->
  false-positive trashes of unrelated same-named files owned by people who never
  got the email, incl. an account disabled >1yr. FIX: write AffectedUsers.csv
  from the `users` set (mailboxes that matched the email) and scope the Drive
  filelist to `csvfile AffectedUsers.csv:user` instead of scope_entity (verified
  `gam csvfile <f>:user print filelist` works as a UserTypeEntity). Also Phase 4
  now prints each file NAME + owner before trashing (was ID only). Owner parse
  gained "Owner" col (csvfile runs label the impersonated user as "Owner").
  311 tasks.
- 09-22-2026: v2.14 NEW Drive workflow "Remove access to an OUTSIDE file (not
  owned by us) - by name or ID" (workflow="removeextaccess", _run_remove_ext_
  access). External user shared a malicious file with the district, no email to
  clean up. RESEARCHED the platform limits (created a test doc, shared to
  fsisd.gam, tested as reader vs writer): a user can `delete drivefileacl <fid>
  <self>` to drop their OWN access ONLY if given EDIT rights; a VIEW-ONLY
  recipient gets exit 56 "Does not exist" (Google platform limit - the external
  owner controls viewer ACLs; not fixable in GAM). So the workflow: Phase1
  `<scope> print filelist {query "name='<esc>'" | select id:<ref>} showownedby
  others fields id,name,owners` -> parse (impersonated user col = "Owner"|"User")
  + id + external owner (owners.0.emailAddress) -> WhoHasTheFile.csv; confirm;
  Phase2 `<threads> csv RemoveTargets.csv gam user ~user delete drivefileacl
  id:~~fileid~~ ~user` (both ~user whole-arg = acting user AND ACL scope; id
  embedded ~~fileid~~). VERIFIED Phase2 end-to-end with an edit-shared file ->
  "Deleted", recipient no longer sees it. Scope options incl. "One or more users
  (comma list)" -> user type. For view-only shares that error, the who-has-it CSV
  feeds the Admin console Security Investigation Tool ("Remove access"). Cleaned
  up all test files (purged). 311 tasks.
- 09-21-2026: v2.13 the two 2.12 targeted workflows now PERMANENTLY delete (no
  Trash option) - Gabe: they're for malicious content, no recovery wanted.
  Removed the Action (trash/delete) field from both catalog tasks; renamed to
  "Find & PERMANENTLY delete a message..." and "PERMANENTLY delete a file from
  EVERYONE's Drive...". _run_targeted_cleanup: always verb=delete/max_to_delete
  (gam delete messages is permanent, bypasses Trash). _run_drive_wipe: always
  `delete drivefile id:~~fileid~~ purge`. VERIFIED purge is truly permanent:
  created a throwaway Doc in gabriel.clifton@ Drive, ran delete drivefile
  id:<id> purge -> "Purged", info drivefile -> "Does not exist", filelist query
  -> 0 (not in Trash). Preview + confirm text now say "PERMANENTLY DELETED (not
  recoverable)". Regular Trash-from-mailboxes + per-file Drive tasks still offer
  recoverable trash. 310 tasks.
- 09-21-2026: v2.12 TWO new two-phase workflows (Gabe asked for both).
  (A) Email Cleanup "Find & remove a message from ONLY the mailboxes that have
  it (fast)" - workflow="targetedcleanup", _run_targeted_cleanup: Phase1 search
  (redirect csv MatchedMessages.csv <scope> print messages query <q> headers
  ...), parse user+Message-ID -> pairs, typed-DELETE confirm, Phase2 write
  DeleteTargets.csv (user,msgid) + ONE pass `<threads> csv DeleteTargets.csv gam
  user ~user {trash|delete} messages query rfc822msgid:~~msgid~~
  {max_to_trash|max_to_delete} <max> doit`. Trash vs Delete toggle. Lightweight
  (no Drive/audit). (B) Drive "Delete a file from EVERYONE's Drive (by name or
  ID)" - workflow="drivewipe", _run_drive_wipe: Phase1 `<scope> print filelist`
  either `query "name='<esc>'" showownedby me excludetrashed` (by name) or
  `select id:<ref> showownedby me` (by id) fields id,name,mimetype,owners; parse
  owner (Owner|User|owners.0.emailAddress) + id -> targets; typed-DELETE confirm
  (shows up to 8 samples); Phase2 write DeleteTargets.csv (owner,fileid) + ONE
  pass `<threads> csv ... gam user ~owner {trash drivefile id:~~fileid~~ | delete
  drivefile id:~~fileid~~ purge}`. Trash(recoverable) vs Delete-permanently
  (purge). Wired: dispatch (elif wf==...), preview branches BEFORE the generic
  incident preview, methods after _ask_delete_confirm. Verified: forms render,
  previews show right verbs, methods wired, catalog 310 tasks, GAMGUI parses.
  Command pieces individually verified earlier (filelist select id: parses;
  trash/delete drivefile at GamCommands 7199-7201; ~~embedded~~ substitution).
  NOT executed end-to-end (needs live domain) - safety: typed DELETE, only
  matched targets, empty-owner rows skipped. Desktop-only (usable_tasks hides
  workflow tasks in web). Owner column: all-users runs -> "User", single-user ->
  "Owner" (parse handles both).
- 09-21-2026: v2.11 three-part request from Gabe.
  (1) NEW "Bulk delete aliases from a CSV" (Aliases): loop form
  `csv {file} gam delete alias ~{aliascol}` (default column "Alias", editable),
  destructive. GAM auto-detects user vs group alias. 308 tasks.
  (2) FIX incident audit report: gmaileventtypes used 7,15-19,28,31,32 but GAM's
  <NumberRange> ::= <Number>|(<Number>/<Number>) uses a SLASH not a hyphen
  ("Invalid argument: Expected NumberRangeList"). Corrected to 7,15/19,28,31,32
  in GAMGUI.py AND gam_web.py. (The no-eventtypes fallback had masked it.)
  (3) SPEED: incident Phase 3 (delete) was `for mid in msgids: gam <all users>
  delete messages query rfc822msgid:mid doit` = M scans of ALL N mailboxes.
  Rewrote to write DeleteTargets.csv (user,msgid from discovery hits) + run ONE
  parallelized pass: `<thread_prefix> csv DeleteTargets.csv gam user ~user
  delete messages query rfc822msgid:~msgid max_to_delete <max> doit` - touches
  ONLY matched mailboxes. Verified `config num_threads N csv <file> gam ...`
  ordering works + parallelizes ("Using 2 processes"). Clean headers user/msgid
  avoid the hyphen-in-~Message-ID substitution issue. Desktop AND web. NOTE:
  standalone "Trash/Delete from mailboxes" tasks are still single all-mailbox
  passes (parallelizable via threads box + scope); could add a dedicated
  lightweight two-phase trash/delete workflow if Gabe wants it outside the full
  incident tool.
- 09-16-2026: v2.10 FIX - installed-copy crash. Gabe installed via the Setup.exe
  to Program Files and got "Failed to execute script GAMGUI ... [WinError 5]
  Access is denied: C:\Program Files\GAMGUI\Logs" at __init__ makedirs(LOG_DIR).
  Root cause: app wrote Logs + gamgui.ini next to the exe (app_dir()), fine for
  a portable copy but not in read-only Program Files. FIX: new data_dir() -
  returns app_dir() if a real write-probe (_is_writable, since os.access W_OK
  lies on Windows) succeeds, else %LOCALAPPDATA%\GAMGUI. DATA_DIR computed once
  at import; INI_PATH/LOG_DIR now under DATA_DIR. Portable C:\GAM7\GAMGUI is
  writable so unchanged. Verified: source dir -> app dir; simulated Program
  Files -> LocalAppData fallback, writable. Bumped 2.10, rebuilt, re-released,
  re-ran installer CI.
- 09-16-2026: REAL INSTALLERS for every OS (Gabe: "build installers, exe, DMG,
  etc... set everything so the OS knows it is installed and the version, like
  the Windows Uninstall registry key"). Added installer/gamgui.iss (Inno Setup:
  Program Files install, Start Menu + optional desktop shortcut, uninstaller,
  AUTOMATIC Add/Remove Programs entry under HKLM\...\Uninstall\{AppId}_is1 plus
  an explicit HKLM\SOFTWARE\GAMGUI\Version key; stable AppId GUID
  9F2C7A14-3B8E-4D6A-B1C5-8E0F2A9D4C77; SourceDir=.. so it packages the
  repo-root dist\GAMGUI). installer/build-macos-dmg.sh (sets CFBundleShort
  VersionString/CFBundleVersion/CFBundleIdentifier via PlistBuddy, then hdiutil
  UDZO DMG with an /Applications symlink). installer/build-linux-packages.sh
  (fpm -> .deb + .rpm; app to /opt/GAMGUI, launcher /usr/bin/gamgui, .desktop;
  registers with dpkg/rpm). Expanded .github/workflows/build-installers.yml to
  build BOTH the installer and the portable archive per OS (Windows job choco-
  installs Inno Setup and runs ISCC.exe; Linux job apt-installs ruby/rpm and
  gem-installs fpm). Could NOT install Inno Setup locally to test (choco needs
  admin, session not elevated) - validating via the CI run instead. Kept the
  portable zips/tar (auto-updater still downloads the Windows zip).
- 09-16-2026: v2.9 CSV-DOWNLOAD FOR EVERY todrive TASK + multi-OS CI.
  Someone asked that everything with a todrive (Google Sheet) option also be
  downloadable as a local CSV. All 54 todrive fields were perfectly uniform
  (`F("Send to Google Sheet?", "todrive", False, choices=["", "todrive"])` +
  template `[{todrive}]`), so it was a central change: new `_out()` helper
  returns TWO fields - a "Save results to" dropdown (Screen "" / Google Sheet
  "todrive" / CSV file "csv") and a "csvout" Save-As file picker - splatted via
  *_out() into every task (one replace_all); templates `[{todrive}]` ->
  `{todrive}` (one replace_all). build_command now treats `{todrive}` as a
  SPECIAL token: "todrive" appends the suffix; "csv" turns the csvout path into
  a LEADING `redirect csv <path>` (verified gam accepts it as a prefix, and
  `select <section> redirect csv <file> <cmd>` order works too). New filepicker
  mode "save" -> asksaveasfilename (_browse_file gained a mode arg). Web
  inherits it (destination dropdown + a text field for the path). Verified:
  screen/sheet/csv all build right; space-in-path stays ONE argv token, display
  quotes it; blank csv path errors clearly; GUI form renders. 307 tasks.
  MULTI-OS CI: added .github/workflows/build-installers.yml (matrix
  windows/macos/ubuntu, Python 3.14, PyInstaller, xvfb on Linux because
  extract_tcl.py calls tkinter.Tk() which needs a display) + docs/RELEASING.md.
  NOTE: the CI has NOT been run yet (can't trigger GitHub Actions from here) -
  it is manual-dispatch and based on the working Build-EXE.bat/build-app.sh, so
  mac/linux may need a first-run tweak.
- 09-10-2026: v2.8 DARK MODE + calendar bulk-hide FIX.
  DARK MODE: View menu > "Dark mode" checkbutton. Soft dark-gray palette
  (bg #2b2b2b, entry/output #3c3f41, text #e0e0e0, muted-blue selection
  #4a6785) - JetBrains-Darcula-ish, NOT pure black (Gabe: "darken a bit, not
  blinding"). Applied via ttk "clam" theme (the only ttk theme that honors
  custom colors on Windows; native "vista" ignores them) + direct coloring of
  the two classic tk.Text widgets (preview + output). Light mode restores the
  saved native theme exactly. Persisted in gamgui.ini [gamgui] dark_mode.
  New: DARK_PALETTE/LIGHT_PALETTE dicts, self.style/_default_theme in __init__,
  menubar, _apply_theme()/_toggle_dark(). Verified via style.lookup that every
  widget class resolves light-on-dark (no dark-on-dark) in dark and reverts to
  SystemWindowText/SystemButtonFace in light. NOTE: could not screenshot the
  live window here (ImageGrab returned all-black - this non-interactive desktop
  does not paint to the screen buffer); relied on programmatic color checks.
  CALENDAR FIX: "Bulk show/hide calendars from a CSV" was shipped in 2.7 using
  `user {email} update calendars csvfile {file}:{idcol} ...` - but the real gam
  7.48 binary REJECTS csvfile in the USER-scoped UserCalendarEntity ("Invalid
  argument"), even though GamCommands.txt line 6218 lists CSVFileSelector as
  valid (doc vs binary mismatch - the verify-external-CLI-behavior lesson
  again). csvfile DOES work in the ADMIN `gam calendars csvfile ...` form (so
  Bulk REMOVE/GRANT are fine). Fixed show/hide to the generic loop:
  `csv {file} gam user {email} update calendars ~{idcol} [selected][hidden]
  [color]` - verified working against a real calendar. Gabe's working one-liner:
  gam csv "F:/.../cals.csv" gam user gabriel.clifton@fsisd.net update calendars
  ~calendarId selected false hidden true (warn: exclude his OWN primary cal).
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
- Dry-run mode that appends "preview" where GAM supports it.

## KNOWN ISSUES / BUGS
- Combobox for optional dropdown fields defaults to first choice when
  required, blank when optional - verify UX feels right in live use.
- Commands run WITHOUT a shell (argv list straight to gam) - the old
  shell=True design was removed (see SESSION LOG). The editable preview is
  still intentionally a power-user feature: GAMGUI trusts its operator
  like a terminal does. (Stale shell=True wording here and in the Stop
  comment in GAMGUI.py corrected 09-24-2026.)

## SESSION LOG
- 09-24-2026: v2.47 - CSV bulk-run builder (was the top NOTES idea).
  gam_catalog.bulk_field_modes (whole / embedded / None) and
  build_bulk_command (pure, tested in tests/test_bulk.py, 18 checks);
  GAMGUI 'Run for each CSV row...' dialog (tests/test_bulk_gui.py drives it:
  BOM + spaced column/path, auto-match, maxrows, exact argv). GAM wiki
  Bulk-Processing: outer 'select' needs 'save' to reach the loop -> GAMGUI
  puts select INSIDE; redirect csv/todrive need 'multiprocess'. Real GAM
  check: 'gam csv "<path with space>" maxrows 2 gam version' ran exactly 2
  rows. Screenshot docs/img/bulk.png (dialog captured via PrintWindow).
  NOTE: gam version now reports Config File \\FSISDDC01\GAMCONFIG\gam.cfg.
- 09-24-2026: v2.46 - local date/time everywhere. local_to_zulu gained
  rule= any|future|year (token 4th part; admin tasks now say :year
  explicitly, default is 'any'); date_to_utc_midnight + {utcdate:KEY} for
  Google Tasks (date-only - NO tz shift). seg_sub now reads field keys inside
  special tokens (only the 2 intended tasks have special tokens in [..]).
  Required time field blank -> error. Validator: all {zulu:} tokens (focus
  time has two), rule part is not a field, {utcdate:} synth. Tests:
  tests/test_zulu.py (+6 rule checks). Remaining raw-time boxes left on
  purpose: audit monitor 'end' (GAM <DateTime>, semantics unverified), event
  details in the advanced box, and the dormant-users report date.
- 09-24-2026: v2.45 - TEMPORARY ADMIN ROLES (Gabe's request, Google blog
  09-2026). GAM 7.48.06 added 'create admin ... expires <DateTime>'. GAM
  SOURCE CHECK (clone at GAM-Projects/gamsrc, sparse src/gam): 'expires' uses
  getTimeOrDeltaFromNow, which passes a full RFC 3339 string through
  unchanged (a bare date is read in gam.cfg's timezone; a zone-less
  date+time may be rejected by the API) - so GAMGUI builds the exact UTC
  '...Z' itself. New gam_catalog.local_to_zulu() + {zulu:DATEKEY:TIMEKEY}
  token (dates YYYY-MM-DD / MM-DD-YYYY / M/D/YYYY; times 24h or AM/PM;
  blank = local midnight; future and <= 365 days). NOTE: {zulu:} must NOT be
  used inside an optional [..] segment (seg_sub reads the key as 'zulu').
  Tests: tests/test_zulu.py (US Central on this PC: 17:30 Jan 5 -> 23:30Z;
  5 PM Nov 20 -> 23:00Z after DST). Validator taught {zulu:}. Share
  updater replaced with v2.1 (v2.0 kept as updategamgui.ps1.v2.0.bak).
- 09-24-2026: v2.44 - UX release. Live preview (StringVar trace ->
  200 ms after() debounce, cancelled in _clear_form); Favorites / Recent
  (gamgui_tasklists.json, keyed by [category, name] so reorders are safe;
  special tree nodes tagged 'special' and refreshed in place so the open form
  is never wiped); text size (scales Tk NAMED fonts from remembered base
  sizes, Treeview rowheight re-applied after theme_use; Ctrl-Key-0 NOT
  Ctrl-0 - a bare digit in a Tk event pattern is a mouse button); GAM docs
  button (gam_catalog.CATEGORY_DOCS + ordered DOC_HINTS regexes on the
  template with {placeholders} and [optional] parts blanked first - they
  caused false matches like {label} -> Gmail labels). tkinter.font imported
  lazily because gam_web stubs tkinter. Tests: tests/test_v244_features.py
  (19 checks, temp data dir), tests/check_doc_links.py (every docs page +
  README wiki link exists in the local clone). README had 8 dead wiki links -
  fixed. Screenshot docs/img/favorites.png via tests/shot_tool.py.
  CAUGHT BEFORE RELEASE: updategamgui.ps1 portable path uses robocopy /MIR
  with only gamgui.ini / gamgui-version.txt / Logs excluded - it would have
  DELETED gamgui_tasklists.json on every update. Added to /XF (v2.1) and
  proved on a scratch folder (rc 3: tasklists kept, stale file removed).
  RULE: any new user-data file in the app folder MUST be added to that /XF.
  The \\fileserver\software\GAM\updategamgui.ps1 copy is NOT updated
  (Gabe's share - ask first).
- 09-24-2026: v2.43 - COMPLETENESS SWEEP (35 tasks, 714/38). Fixed
  tests/gap_audit.py false positives: KNOWN_VERBS lacked the verbs added in
  2.40-2.42 (revoke/end/append/download/obliterate/dedup/rotate/sendemail/
  audit/...) and dropdown-supplied verbs/objects ({action} csekeypair,
  delete {kind}) were not expanded - now each valuemap value is harvested.
  171 -> 112 uncovered; the rest are Tier 4 GAM plumbing, parser artifacts
  ([<UserTypeEntity>] classificationlabels, GAM doc typo 'chromschemas',
  GAM print-form quirks channelcustomercentitlements/tagmanagerccounts),
  alternate syntaxes already covered another way (suspend user vs update
  user suspended, calendaracls vs calendar acls, [create] filter/label), and
  low-value variants (chat sections, labelid ops, contact photos). New local
  helpers (tests/ is not in the repo): syn.py (grammar lookup -> syn_out.txt),
  wiki.py (wiki lookup -> wiki_out.txt), build_new.py (build-test tasks new
  vs an old catalog copy), tier5_sweep.py. GAM wiki clone moved to
  GAM-Projects\gamwiki because the session scratchpad gets wiped.
- 09-23-2026: v2.42 - GAP-CLOSING TIER 3 (54 new/rebuilt, 679/38 cats). Google
  Chat category REBUILT: v2.38 used the bot form (print chatspaces /
  chatmembers <space>) mislabeled '(admin)' and 'user X print chatmessages'
  with no <ChatSpace>+ (always errors). Admin forms are 'user <admin> ...
  asadmin'. Every Chat API call needs 'gam setup chat' (wiki Users-Chat).
  Skipped 'sync chatmembers' (in GamCommands.txt but undocumented in the wiki
  - semantics of 'users <UserTypeEntity>' unverified). Reseller subscription
  tasks reuse the {license:sku} token. Looker Studio share/unshare REQUIRE a
  title so they can't blanket every asset. This completes Tiers 1-3 of the
  gap audit; Tier 4 (GAM setup plumbing) intentionally stays in the console.
- 09-23-2026: v2.41 - GAP-CLOSING TIER 2 (89 tasks, 628/38 cats). New cats
  'Chrome Browsers & Policies' (after Chromebooks) and 'Access & Identity (SSO,
  CAA, Policies)' (after Security). SECURITY FIX found while adding S/MIME:
  _log() and _append_output() wrote the full command (incl. 'password X') to
  the session log in plain text - added redact_secrets() (regex on the
  'password' keyword, handles plain / quoted / argv-repr / 'Password:' echo;
  leaves changepasswordurl alone) applied ONLY to the log writes. Old logs may
  hold passwords - told Gabe. Time-format audit: GAM <Time> needs a zone
  (Z or +/-hh:mm) or a relative +Nd; <DateTime> = yyyy-mm-ddThh:mm; <Date> =
  yyyy-mm-dd. Fixed v2.40 examples (task due, focustime, import event) and the
  old 'Add event' all-day example (needs 'allday'). Rotate sakey defaults to
  retain_existing (Gabe's oauth2service.json is on a shared DC folder).
  Scratchpad note: an earlier typo'd scratchpad path (daaf034 vs daaf304) got
  wiped by a cleanup; working scripts live in the real session scratchpad now.
- 09-23-2026: v2.40 - GAP-CLOSING TIER 1 (74 tasks, 539/36 cats). Source:
  tests/gap_audit.py strict matcher (~300 real uncovered command variants after
  false positives), grouped by Gabe-approved tiers: 1 everyday, 2 security /
  identity (v2.41), 3 collaboration / reseller management (v2.42), 4 GAM setup
  plumbing stays in the console. New cats Google Tasks & Keep (3 list tasks
  moved from Users) and Google Sheets & Docs, after Google Chat. Syntax gotchas
  verified against GamCommands.txt + a shallow clone of GAM.wiki (scratchpad
  gamwiki/): 'check groups' options go BEFORE the group list (so a dropdown, not
  rawappend); Keep note body is 'message <text>' (NOT 'text'); noteacl JSONData
  is an ALTERNATIVE to user/group (wiki text says so); import an exported mail
  with 'emlfile' (plain 'file' is a text body); dedup contacts removes duplicate
  ADDRESSES; clear tasklist clears COMPLETED tasks only. win_split does NOT
  honor single quotes - all rawappend examples must use DOUBLE quotes (fixed 5
  descriptions). FIX: delete filerevisions lacked doit (no-op) + invalid example
  selector. SAFETY: build_command now refuses an empty REQUIRED rawappend field.
  Screenshot docs/img/productivity.png (Tasks & Keep) via PrintWindow; README
  new section 'Google Tasks, Keep, and Sheets' + table/bullets; README.txt new
  '2.40 by category' list + required-box note; HOW-TO new recipes + safety #4.
- 09-23-2026: v2.39 - NEW categories Reseller/Channel + Marketing & Analytics
  (14 tasks, 465/34 cats). Gabe's key reframe: GAMGUI is for the WHOLE GAM
  community (public, shared with GAM community who are largely NOT K-12), so my
  'niche for K-12' filtering was wrong - added the services the broader audience
  uses. Reseller/Channel (MSPs): print resoldsubscriptions/channelcustomers/
  channelcustomercentitlements/channeloffers/channelproducts/channelskus.
  Marketing & Analytics: user print analyticaccounts/accountsummaries/properties/
  datastreams; tagmanagerccounts (NOTE: GAM print form is 'tagmanagerccounts' -
  missing an 'a'; the SHOW form is 'tagmanageraccounts' - a real GAM quirk);
  datastudiopermissions + show datastudioassets; youtubechannels. GAM has NO
  Voice mgmt (Voice = license SKUs only). No GAM support for Sites/Cloud Storage
  buckets either. Validator green 465/34. README table +2 rows, count updated.
- 09-23-2026: v2.38 - NEW categories Google Meet/Forms/Chat (9 tasks, 451/32
  cats). Gabe noticed Meet+Forms missing - they were filtered as 'niche' during
  the coverage-audit sweeps (my grep excluded meet/forms/chat/voice/tagmanager/
  analytics/etc.); too aggressive for K-12. Meet: user print meetconferences /
  meetparticipants <conf> / meetrecordings <conf> / meettranscripts <conf>.
  Forms: user print forms <fileid> / formresponses <fileid>. Chat: print
  chatspaces / chatmembers <space> / user print chatmessages. All read-only.
  ANSWER re 'anything else missing': genuinely-niche and still intentionally out
  = Google Voice, new Sites, Tag Manager, Looker Studio/DataStudio, Analytics,
  YouTube, Cloud Storage, reseller/channel (no K-12 admin use). Validator green
  451/32. README table +3 rows.
- 09-23-2026: v2.37 - 2 tasks (442): Contacts bulk import shared contacts from
  CSV (csv {f} gam create contact givenname ~First familyname ~Last email work
  ~Email primary); Reports failed sign-in attempts (report login start -7d event
  login_failure). DEMO-READINESS QA PASS: ran a full build_command over all 428
  non-workflow tasks (translating valuemaps as the GUI does) -> 0 real problems;
  fixed tests/validate_catalog.py to know {crosscope:}/{userscope:} tokens +
  synth MAPPED valuemap values -> 'Catalog OK: 442 tasks / 29 cats'; gam_web
  imports. IMPORTANT: my ad-hoc validation FALSE-flagged 30 scope tasks until I
  applied valuemap translation (friendly label 'An OU...' -> 'ou') like
  _collect_values; always translate valuemaps before build_command in tests.
  tests/ is NOT tracked in the repo (dev-only), so validator fix stays local.
- 09-23-2026: v2.36 - 3 security-posture reports (440 tasks), dedicated/
  discoverable vs hand-crafted queries (better for the demo). 2SV enrollment
  (print users fields ...,isenrolledin2sv,isenforcedin2sv, Security cat),
  Suspended users (print users query isSuspended=True ...), Dormant/never-
  signed-in (print users query lastLoginTime<{date}T00:00:00Z ..., date field
  default 2025-01-01). GAM fields: isenrolledin2sv/isenforcedin2sv; query
  isSuspended=True; lastLoginTime<date (never-logged-in = epoch last login).
  All build-tested. README reports section + table rows to refresh.
- 09-23-2026: v2.35 - 4 BULK License/Schema (437 tasks). Licenses scope-based
  via {userscope}: assign ({scope} add license {license:sku}), remove ({scope}
  delete license, destructive), swap ({scope} update license {license:newsku}
  from {license:oldsku}, destructive) - {license:KEY} token translates NAME->SKU
  per arbitrary field key so newsku/oldsku both work. Custom Schemas: bulk set
  schema field from CSV (csv {f} gam update user ~Email SIS.StudentID ~Value).
  GAM: <UserTypeEntity> create|add|delete|update license <SKUIDList>. All
  build-tested, 0 raise. Docs: README Licenses + Custom Schemas rows refreshed.
  Gabe presenting to a large IT-admin audience soon - keep quality demo-ready.
- 09-23-2026: v2.34 - 6 BULK Calendar/OU/Alias actions (433 tasks). Calendars
  (scope-based via {userscope}): subscribe ({scope} add calendars {cal}
  [selected][hidden]), unsubscribe ({scope} delete calendars {cal}, destructive),
  show/hide/recolor ({scope} update calendars {cal} ...). OUs: bulk create/delete
  from CSV (csv {f} gam create|delete org ~OrgUnit; verb is 'org' not 'ou',
  buildpath auto-creates parents). Aliases: bulk create from CSV (csv {f} gam
  create alias ~Alias user ~Email). NOTE: 'Move users into OU' already bulk via
  the v2.30 Users {userscope} 'BULK: move users to an OU'. All build-tested;
  valuemap fields (selected/hidden) resolve in the GUI _collect_values, blank
  drops the [selected {x}] segment. README table rows (Calendars? no row; OUs,
  Aliases) + Calendars section refreshed.
- 09-23-2026: v2.33 - 5 BULK Shared Drive actions from a CSV (427 tasks): create
  (csv {f} gam create shareddrive ~Name), delete (~id, destructive), add/remove
  a member (csv {f} gam add|delete drivefileacl ~id user {who} role {r} /
  ~id {who}), move to OU (csv {f} gam update shareddrive ~id ou {ou}). GAM:
  SharedDriveIDEntity accepts a bare id; update shareddrive supports ou|org;
  add|delete drivefileacl take a shared-drive id (=its root). Fed by the CSV
  output of List Shared Drives / memberships. Docs (README Drive section +
  Shared Drives table row) refreshed; no new screenshot (covered by drive.png).
- 09-23-2026: v2.32 - 6 BULK Gmail + 4 Drive actions (422 tasks). Gmail bulk all
  ride the {userscope} token (gam <UserTypeEntity> ...): set signature ({scope}
  signature {sig}), set/clear vacation ({scope} vacation on subject {s} message
  {m} / vacation off), turn off auto-forwarding ({scope} forward off - security
  remediation), add/remove delegate ({scope} delegate to {d} / delete delegate
  {d}, remove is destructive). Drive: bulk share/unshare files matching a query
  (user {o} add|delete drivefileacl query {q} ...), delete empty folders
  (destructive), collect orphans (recover parentless files). All build-tested,
  0 raise. GAM: <UserTypeEntity> signature|vacation|forward|delegate|delete
  delegate all take the user selector; add/delete drivefileacl <DriveFileEntity>
  accepts query; collect orphans / delete emptydrivefolders / empty drivetrash.
  DOC OVERHAUL this session per Gabe (keep README.md/README.txt/HOW-TO-GUIDE.txt
  current + screenshots per section) - see below / separate commit.
- 09-23-2026: v2.31 - FIX in-app self-update (Gabe: running update from the exe
  install updated the ZIP not the EXE) + 5 BULK Drive actions (412 tasks).
  ROOT CAUSE of the updater bug: _do_self_update used installed = not
  _is_writable(appdir), but an ADMIN can write to Program Files, so the exe
  install was misdetected as portable -> ran -InstallType zip into Program Files
  (or the wrong root) and never re-ran the installer / updated the registry.
  FIX: new module-level registry_exe_install() (winreg, lazy import, win32-only
  so gam_web on Linux is unaffected) reads HKLM\SOFTWARE\GAMGUI Version +
  InstallLocation; _same_path() (normcase/normpath, strip trailing slash);
  installed = same_path(appdir, reg location). Exe path now elevates via
  ctypes.windll.shell32.ShellExecuteW(None,'runas','powershell.exe', '-File
  "<updater>" -InstallType exe -Launch') (rc<=32 => UAC declined, warn + don't
  close); portable path unchanged (detached CREATE_NEW_CONSOLE, sleep 3, zip).
  Replaced the fragile nested 'Start-Process -Verb RunAs inside a detached PS'.
  Verified detection: appdir=C:\Program Files\GAMGUI -> installed=True (elevated
  exe); C:\GAM7\GAMGUI -> False (portable). App builds, web imports. DRIVE bulk:
  empty a user's drivetrash + empty ALL users' drivetrash (destructive), transfer
  a user's ENTIRE Drive (user {e} transfer drive {new}, offboarding), transfer
  ownership of files matching a query (transfer ownership query {q} {new}), trash
  files matching a query (delete drivefile query {q} trash, advanced can swap to
  purge). All destructive-flagged; query-with-spaces quotes to one arg correctly.
  NOTE: registry showed Gabe's Program Files install is now 2.28 (was 2.22).
- 09-23-2026: v2.30 - 6 BULK Users actions (407 tasks). NEW {userscope:usertype:
  userval} token (parallel to {crosscope}/{mailscope}) + _user_scope() helper:
  expands to gam <UserTypeEntity> all users|ou <o>|ou_and_children <o>|group
  <g>|query <q>|csvfile <f:c>; empty-value guard. Scope-based tasks: suspend
  (destructive)/unsuspend (update users {scope} suspended on|off), move to OU
  (org {neworg}), change any attribute (rawappend, destructive). CSV-row tasks:
  create users from CSV (csv {file} gam create user ~Email firstname ~First
  lastname ~Last password ~Password + advanced ~OrgUnit/changepasswordatnextlogin)
  - FLAGGED plaintext-password CSV security in the description; update users from
  CSV per-row (csv {file} gam update user ~Email + advanced ~Column subs).
  Verified all scope types expand, guard fires, 0 raise on empty build. Web twin
  gets {userscope} free. GAM: update users <UserTypeEntity> <UserAttribute>*;
  csvfile <file>:<field> is the CSV UserTypeEntity form; suspended <Boolean> +
  org <ou> are UserAttributes.
- 09-23-2026: v2.29 - 6 BULK Groups actions (401 tasks). add/remove members to
  ONE group from a group/OU/CSV (update group {g} add|remove [role] <source>);
  add/remove ONE user across MANY groups from a CSV (update groups csvfile
  {file}:{col} add|remove [role] {user}); bulk create groups from CSV (csv
  {file} gam create group ~Email name ~Name); bulk delete groups from CSV
  (delete groups csvfile {file}:{col}). GAM facts: <GroupEntity> accepts
  csvfile/file selectors so 'update groups csvfile f.csv:group ...' acts on many
  groups; the member arg is <UserItem>|<UserTypeEntity> so source can be email /
  group <email> / ou <path> / csvfile <file>:<col> -> made source fields
  rawappend (tokenized). ROLE-BLANK FIX: 'Any role' maps to '' which failed the
  required-field check and produced EMPTY output; fixed by making the role field
  required=False AND bracketing the template token '[{role}]' so an empty role
  DROPS the segment (seg_sub) -> 'remove <source>' with no role = remove
  regardless of role. LESSON: a valuemap option that maps to '' must pair with
  required=False + a [bracketed] template token, or the empty value both fails
  validation and (unbracketed) emits an empty argv element. Verified all source
  forms + blank/role; 0 raise on empty build.
- 09-23-2026: v2.28 - 7 more Classroom actions (395 tasks): edit/publish an
  announcement (course {id} update announcement {annid} [text {t}]), delete an
  announcement (remove announcement, destructive), rename student group (update
  course-studentgroups {id} {gid} title {t}), remove member from / sync (exact,
  destructive) student group members (delete|sync course-studentgroup-members
  {id} {gid} <member>), accept/cancel a course invitation for a user (user
  {email} accept|delete classroominvitation courses {id}). BUG FIX: the v2.27
  "Add members to a student group" (and the new remove/sync) took the member as
  a plain {field}, so a multi-token value like 'group staff@fsisd.net' or 'ou
  /path' got quote_if_needed-wrapped into ONE argv element (broken). Changed the
  member/source field to rawappend=True (tokenized via win_split) and dropped
  {member} from the template - now a bare email = 1 token, 'group <email>'/'ou
  <path>' = 2 tokens. LESSON: any field whose value may legitimately contain a
  space-separated KEYWORD + value must be rawappend, not a plain {placeholder}.
  Verified all three across email/group/ou inputs. GAM has NO create coursework
  (Classroom API restricts assignment creation) so that stays uncovered.
- 09-23-2026: v2.27 - BUILT-IN auto-update in the app + 6 more Classroom
  actions (388 tasks). IN-APP UPDATER (GAMGUI.py): on startup (if
  check_updates ini setting true, default true) a daemon thread hits the
  GitHub latest-release API (urllib, 12s timeout), compares tag to APP_VERSION
  via _version_tuple (numeric), and if newer calls _prompt_update -> askyesno.
  On yes, _do_self_update launches the BUNDLED updategamgui.ps1 in a detached
  CREATE_NEW_CONSOLE powershell that sleeps 3s (lets app exit) then updates +
  -Launch, and the app self.destroy()s so files unlock. Portable (app_dir
  writable) -> zip update no elevation; installed (Program Files, not writable)
  -> Start-Process -Verb RunAs -InstallType exe (UAC). Non-Windows or no bundled
  updater -> opens Releases page. New Help menu: Check for updates now / Check at
  startup toggle (persists) / About. All network failures swallowed (offline ok).
  gam_web unaffected (never builds the window). Smoke-tested: GamGui() builds
  with new menu, check_updates=True, destroys clean; live API returns 2.26;
  version compare unit-tested (2.9<2.26 correct). Classroom: invite a user to a
  course (user {email} create classroominvitation courses {id} role {r}), post
  announcement (course {id} create announcement text {t}), delete topic, create/
  add-members/delete student group (course-studentgroups + -members).
  ALSO FIXED: the \\fileserver\software\GAM\updategamgui.ps1 copy was a 513KB
  saved GitHub BLOB WEBPAGE (HTML), not the script - PowerShell choked on its
  CSS/JS. Root cause: downloaded from the github.com/blob URL not Raw. Replaced
  it with the correct 25KB script (parses clean). Class name is GamGui (not App).
- 09-23-2026: v2.26 - More Classroom actions (6) + AUTO-UPDATER rewrite.
  Classroom: add students/teachers from an OU (adds-only), bulk add teachers
  from CSV, sync teachers from an OU (destructive), create a course topic
  (course {id} create topic {name}), bulk invite guardians from a CSV (csv
  {file} gam create guardian ~Guardian ~Student - start-of-year parent
  onboarding). 382 tasks. UPDATER updategamgui.ps1 -> v2.0: now detects install
  TYPE (portable zip / Setup.exe / both) and updates each. Portable = zip+
  robocopy (unchanged). Exe = re-run new Setup.exe silently (/VERYSILENT
  /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /NORESTARTAPPLICATIONS), needs
  admin (skips with message if not elevated / -Quiet). Detects exe install via
  HKLM\SOFTWARE\GAMGUI (Version + InstallLocation), checks WOW6432Node too.
  New -InstallType auto|zip|exe|both. Per-asset SHA parse: Get-PublishedHash
  matches 'SHA-256 (<assetname>):' label then next 64-hex, with single-hash
  fallback for old zip-only releases. IMPORTANT DISCOVERY: this machine HAS a
  stale Setup.exe install at C:\Program Files\GAMGUI (registry v2.22) that my
  portable C:\GAM7 deploys never touched - exactly the bug this fixes. RELEASE
  PROCESS CHANGE: now publish BOTH the Windows-zip AND Setup.exe SHA-256 in the
  release body (updater verifies each). Unit-tested Get-PublishedHash (new+old
  formats) and Get-ExeInstall against the real registry - both pass; script
  parses clean, ASCII-only. Released + deployed portable to C:\GAM7.
- 09-23-2026: v2.25 - SWITCHED from read-gap sweeping to ACTIONS (Gabe's
  direction). 14 new tasks, 376 total. Added a new {crosscope:crostype:crosval}
  template token (parallel to {mailscope}) in build_command that expands into
  the right gam <CrOSTypeEntity>: sn->cros_sn, ou->cros_ou, ou_children->
  cros_ou_and_children, query->crosquery, all->"all cros". New _cros_scope()
  helper returns the two scope fields (like _out()). 8 BULK Chromebook actions
  (move OU, set fields, asset-tags-from-CSV, disable/reenable, deprovision,
  reboot, powerwash, wipe users) - disable/deprovision/powerwash/wipe flagged
  destructive. 6 Classroom actions (add students/teachers from a group adds-only
  via plural 'courses ... add <role> <UserTypeEntity>'; bulk add students from
  CSV via csvfile {file}:{col}; remove course alias = course {id} delete alias;
  reactivate archived course = update course {id} status active; bulk create
  courses from CSV via csv loop). Web twin gets {crosscope} free (shares
  gg.build_command + applies valuemaps). Verified: crosscope expands for all 5
  scope types, empty-value guard fires, 0 tasks raise on empty build, destructive
  flags correct. Released + deployed to C:\GAM7.
- 09-23-2026: v2.24 - Sixth gap-closing batch (3 new tasks, 362 total).
  Calendars print outofoffice|workinglocation|focustime (dropdown, no todrive);
  Users print notes (Keep); Data Transfers print transferapps. NOTE: audit
  flagged print othercontacts + guardians + Chrome printers as gaps but ALL were
  already covered (audit signature-matching false-positives) - caught the
  othercontacts one via a grep -c dupe check AFTER adding and removed my
  duplicate before release. Lesson: grep the exact template string in the
  catalog before adding, since the audit over-reports. Released + deployed to
  C:\GAM7.
- 09-23-2026: v2.23 - Fifth gap-closing batch (9 new tasks, 359 total), the
  smaller "helpful to all, not some" read tasks per Gabe. Gmail print
  gmailprofile; Drive print diskusage (folder size, needs folder id) + print
  drivesettings; Calendars print calsettings (timezone etc); Users print tasks +
  print tasklists (Google Tasks); Chromebooks print browsers (CBCM-enrolled
  Chrome browsers, distinct from Chromebook devices); Classroom print
  classroomprofile; Licenses show configlicenseskus (console, no todrive).
  Skipped already-covered: print buildings/features/calendars. All verified vs
  GamCommands.txt, build-tested Screen/Sheet/CSV. Released + deployed to C:\GAM7.
- 09-22-2026: v2.22 - Fourth gap-closing batch (7 new tasks, 350 total),
  remaining useful read/export tasks. Gmail: all-users print vacation
  enabledonly (who has auto-reply ON), all-users print imap + print pop
  (security posture), user print language (help-desk). Drive: all-users print
  filesharecounts (DLP/oversharing audit), all-users print drivelastmodification
  (dormant Drives). Users: print userinvitations (pending org invites). Skipped
  as already-covered false-positives in the audit: print admins, print
  adminroles. Skipped as console-dupes of print tasks already added: all the
  "show <x>" read-variants (Screen output of the print task covers them). All
  verified vs GamCommands.txt, build-tested Screen/Sheet/CSV. Released +
  deployed to C:\GAM7.
- 09-22-2026: v2.21 - Third gap-closing batch (6 new tasks, 343 total),
  focused on Chromebooks + Classroom. Chromebooks: chromeaues (AUE / device
  end-of-life dates - big for retirement/budget planning), chromesnvalidity
  (serial validity; takes cros_sn <serials>, comma-separated field). Classroom:
  course-submissions, course-materials, classroominvitations (admin form, no
  user entity). Calendars: user-scoped print calendaracls (who can see a
  person's calendar; calendar field defaults to 'primary' via F default=).
  All verified against GamCommands.txt and build-tested in all three output
  modes. Released + deployed to C:\GAM7 the usual way.
- 09-22-2026: v2.20 - Second gap-closing batch (6 new tasks, 337 total).
  Drive: driveactivity (activity log for investigations), emptydrivefolders
  (cleanup before archiving), filecomments (comments on a file). Shared Drives:
  oushareddrives (drives grouped by OU). Chromebooks: chromedevicecounts (fleet
  counts by OU/model/version). Classroom: course-counts students|teachers
  (enrollment/load check at rollover; students|teachers is a required dropdown).
  All verified against GamCommands.txt and build-tested in all three output
  modes (Screen/Sheet/CSV). v2.19 was deployed to C:\GAM7\GAMGUI first (built
  exe, robocopy /MIR from the release Windows zip preserving Logs, version
  marker bumped to 2.19, launch smoke-tested clean); then 2.20 built/released/
  deployed the same way.
- 09-22-2026: v2.19 - Ran coverage_audit.py against the full GAM command list
  (GamCommands.txt) and closed the highest-value gaps: 13 new tasks, 331 total.
  Groups (user's own memberships; nested group tree), Drive (find a file's
  owner by ID or name, and its folder path - ties into the malicious-file
  investigations), Gmail security (is a mailbox auto-forwarding out? one user
  and whole-domain sweep; show vacation/auto-reply), Chromebooks (telemetry,
  needs-attention, ChromeOS version compliance), Security (Alert Center alerts),
  Users (export every address in the domain). All verified against
  GamCommands.txt and build-tested (Screen/Sheet/CSV routing confirmed). Both
  the desktop GUI and gam_web share the one gam_catalog TASKS list, so the web
  twin picks these up automatically. Coverage audit note: raw "families" number
  (855) counts every legacy alias and niche service (DataStudio, Vault subcmds,
  Chat, Tag Manager, channel/resold, analytics) as separate signatures, so the
  27% figure understates real usefulness - remaining gaps are being filtered for
  genuine K-12 help-desk value, not chased for the percentage.
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
