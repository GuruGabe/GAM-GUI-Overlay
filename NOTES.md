# NOTES.md - GAMGUI

## WHAT HAS BEEN DONE
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
