================================================================================
  GAMGUI 2.59 - A GRAPHICAL FRONT-END FOR GAM7
  Author: Gabriel Clifton
================================================================================

  This is the full reference manual. New, non-technical users should start
  with HOW-TO-GUIDE.txt (a plain-English walkthrough) and README.md (the
  illustrated overview with screenshots).

1. WHAT THIS PROGRAM DOES
   GAMGUI is a point-and-click front end for GAM7, the command line tool for
   Google Workspace administration (https://github.com/GAM-team/GAM).
   It presents over 710 admin tasks as fill-in-the-blank forms across 38
   categories, plus a "Run ANY GAM command (advanced)" console that accepts
   any GAM command not built into a form. You get GAM's power without
   memorizing commands. It is built for anyone who uses GAM - schools,
   businesses, nonprofits, and resellers/MSPs alike.

   The categories are: OAuth Setup, Common Tasks, Users, Groups, Aliases,
   Org Units, Domains & Domain Aliases, Chromebooks, Chrome Browsers &
   Policies, Gmail, Calendars, Drive,
   Shared Drives, Classroom, Google Meet, Google Forms, Google Chat, Google
   Tasks & Keep, Google Sheets & Docs, Licenses, Vault, Mobile Devices, Cloud Identity Devices, Custom Schemas, Contacts,
   Admin Roles & Privileges, Data Transfers, Reseller / Channel, Marketing &
   Analytics, Chrome Printers, Buildings/Features/Rooms, Customer/Settings,
   Reports, Security, Access & Identity (SSO, CAA, Policies), Email Cleanup, Bulk/Batch, and Diagnostics.

   Not covered, because GAM itself does not manage them: Google Voice (only
   its license SKUs, which ARE covered under Licenses), Google Sites, and
   Cloud Storage buckets.

   BULK ACTIONS: many categories include BULK tasks that act on many objects
   at once. They share a target picker - point an action at an OU, an OU and
   its sub-OUs, a group, a search query, a CSV column, or everyone. Examples:
     - Users:       bulk create from a CSV; bulk suspend / unsuspend / move to
                    an OU / change any attribute across a scope.
     - Gmail:       set a signature, set/clear an auto-reply, turn OFF
                    auto-forwarding, add/remove a delegate across a scope.
     - Chromebooks: bulk move / disable / deprovision / reboot / powerwash /
                    wipe by OU, query, or CSV; import asset tags from a CSV.
     - Drive:       bulk transfer / share / unshare files matching a query;
                    empty trash; collect orphaned files; transfer a whole Drive.
     - Groups:      bulk add / remove members; add/remove one user across many
                    groups; create / delete groups from a CSV.
     - Classroom:   add students/teachers from a group, OU, or CSV; bulk create
                    courses; bulk invite guardians.
     - Licenses:    exact-match sync of a license to a scope (adds it to users
                    in the scope, removes it from everyone else).
     - Photos:      set profile photos for a whole scope from a folder of
                    images named after each user.
     - Email:       send the same message to every user in a scope.

   EVERYDAY TASKS ADDED IN 2.40 (by category):
     - Gmail:       restore messages from Trash; mark as spam; add/remove a
                    label on matching messages (remove UNREAD = mark read,
                    remove INBOX = archive); forward matching messages; export
                    them to .eml files; import an .eml; rename a label;
                    rename/merge labels by pattern; send email as a user.
     - Drive:       restore a trashed file or every trashed file matching a
                    query; permanently purge a trashed file; create a nested
                    folder path; create a shortcut; rename; replace a file's
                    contents from this PC (keeps its ID, link, and sharing).
     - Users:       download / set / delete a profile photo; check whether an
                    address is an unmanaged (personal) account on your domain;
                    invite it to join; check or cancel the invitation.
     - Calendars:   swap one attendee for another on every matching event;
                    purge selected events (a selector is REQUIRED - see the
                    safety note below); import an event by iCalUID; create
                    out-of-office, working location, and focus time entries,
                    and remove them.
     - Groups:      check whether a user is in one or more groups (optionally
                    through nested groups); a user's role in a group.
     - Org Units:   OU info (details and users, optionally sub-OUs).
     - Classroom:   sync a student's guardians to an exact list; clear a
                    student's guardians or pending invitations.
     - Contacts:    remove duplicate addresses; list / add / remove contact
                    delegates.
     - Admin Roles: a role's privileges; rename/edit or delete a custom role.
     - Buildings, Features & Rooms: building info and update; rename a
                    feature; room/resource info and update.
     - Chrome Printers: update a printer.
     - Reports:     usage reports (per user or whole organization) for a date
                    range; list the usage-report parameter names.
     - Security:    Alert Center alert details; delete or restore an alert.
     - Google Tasks & Keep (NEW category): list, create, complete, rename, and
                    delete tasks and task lists; clear completed tasks; list,
                    create, delete, and share Keep notes; download a note's
                    attachments.
     - Google Sheets & Docs (NEW category): read a range or a spreadsheet's
                    tabs (to screen, Sheet, or CSV); append rows or write
                    values from a JSON file; clear a range.

   SECURITY AND IDENTITY TASKS ADDED IN 2.41 (by category):
     - Chrome Browsers & Policies (NEW category): show / set / remove Chrome
                    policies for an OU; look up policy schemas; managed
                    Chrome browsers (info, move, annotate, delete); browser
                    enrollment tokens (create, list, revoke); managed Chrome
                    profiles (list, info, delete, clear cache / cookies);
                    installed apps and extensions and which devices have one;
                    wallpaper / avatar images; managed networks from JSON.
     - Access & Identity (SSO, CAA, Policies) (NEW category): SAML SSO
                    profiles (create, update, delete), IdP signing
                    certificates, SSO on/off for an OU or group; Context-
                    Aware Access levels (IP ranges, countries, custom rule);
                    Cloud Identity policies (list, info, create/update from
                    JSON, delete); allowlisted domains.
     - Groups:      Cloud Identity view - security groups, dynamic groups
                    (members by query), lock / unlock, members that EXPIRE on
                    a date, member lists with expirations.
     - Security:    S/MIME certificates (list, upload, default, delete);
                    Gmail client-side encryption key pairs and identities;
                    Alert Center Pub/Sub settings and feedback; email
                    monitors (Email Audit API); delete backup codes.
     - Drive:       Drive labels (classification labels) and who can use them.
     - Shared Drives: copy one drive's members to another, or sync them to
                    an exact match.
     - Chromebooks: download device files (logs, screenshots).
     - Domains:     get a verification token; verify a domain.
     - OAuth Setup: show GAM's service-account keys; rotate the key (you
                    choose whether old keys are kept, replaced, or deleted).

   COLLABORATION AND RESELLER TASKS ADDED IN 2.42 (by category):
     - Google Chat: list every space in the organization (admin, 'asadmin'),
                    a space's members, its messages, and search messages;
                    create / rename / delete spaces; add / remove members and
                    change roles; post / edit / delete messages as a user or
                    as GAM's Chat bot; show / set Chat status; custom emoji.
                    NOTE: Google requires GAM's Chat bot for ANY Chat task -
                    run  gam setup chat  once (GAM wiki: Users - Chat).
                    FIXED: the v2.38 'admin' space/member lists used the bot
                    form (only spaces the bot is in) and 'List a user's Chat
                    messages' left out the required space.
     - Google Meet: create a meeting space with join rules; change its
                    settings; space info; end a running meeting.
     - Google Forms: create a form (optionally a quiz); rename; open or close
                    it for responses.
     - Google Sheets & Docs: download a Google Doc as JSON (Docs API).
     - Reseller / Channel: customer info / create / update; subscription
                    info / create; change seats, plan, or renewal; suspend,
                    activate, start paid service; cancel, downgrade, or
                    transfer to direct.
     - Marketing & Analytics: Tag Manager containers, workspaces, tags, and
                    permissions; share / unshare Looker Studio assets;
                    Search Console sites; verified web resources; Business
                    Profile accounts.
     - Vault:       download or copy a Google Takeout export bucket; download
                    one Cloud Storage file.
     - Chrome Browsers & Policies: Chrome version history.
     - Gmail:       show a user's signature; Gmail filter details.

   COMPLETENESS SWEEP IN 2.43 (by category):
     - Users:       hide / show a user in the shared directory; is a user
                    shown; list directory profiles; is a user suspended.
     - Aliases:     move an alias to another user or group.
     - Groups:      sync a user's groups to an exact list (removes them from
                    every other group - optionally limited to one domain).
     - Gmail:       create a draft in a user's mailbox; archive matching
                    messages into a Google Group.
     - Calendars:   show out-of-office / working location / focus time;
                    event details.
     - Drive:       upload a file from this PC (optionally converting to a
                    Google Doc / Sheet / Slides); full file details with
                    folder path; a file's folder tree; apply or remove a
                    Drive label on a file.
     - Shared Drives: Shared Drive details (admin).
     - Chromebooks: device telemetry (battery, storage, CPU, memory); the
                    result of a remote command; count devices in a scope.
     - Cloud Identity Devices: delete a device user.
     - Org Units:   is this OU empty? (check before deleting).
     - Custom Schemas: add or remove a field on an existing schema.
     - Buildings, Features & Rooms: delete a feature.
     - Contacts:    replace an old domain in a user's contacts; copy or move
                    Other contacts into My Contacts.
     - Classroom:   list student-group members; delete all student groups.
     - Vault:       copy a saved search to another matter.
     - Google Tasks & Keep: task details; move a task; Keep note details.
     - Google Sheets & Docs: create a spreadsheet from JSON.
     - Domains:     domain alias info; make a domain the primary domain.
     - Google Chat: message details.

   WHAT IS STILL CONSOLE-ONLY (use "Run ANY GAM command"): GAM's own setup
   and plumbing - creating GCP projects and service accounts, OAuth
   create / refresh / export, enabling APIs, YubiKey keys, and 'gam setup
   chat'. Plus a few rarely used variants (Chat sidebar sections, Gmail label
   operations by internal label ID, domain shared-contact photos).

   TEMPORARY ADMIN ROLES (2.45): Admin Roles & Privileges > "Assign a
   TEMPORARY admin role" (whole domain or one OU) grants a role that Google
   removes automatically at the expiration.
     - Type the expiration DATE as YYYY-MM-DD, MM-DD-YYYY, or M/D/YYYY.
     - Type the TIME as 24-hour (17:30) or 12-hour (5:30 PM), or leave it
       blank for midnight at the START of that date.
     - Both are in THIS computer's time zone. GAMGUI converts them to UTC
       ("Zulu", e.g. 2026-10-31T22:00:00Z) - the format Google's API needs -
       using the daylight-saving offset in effect on the date you enter. The
       converted time is what you see in the command preview.
     - The expiration must be in the future and within one year; GAMGUI
       refuses to build the command otherwise.
     - Requires GAM 7.48.06 or newer ('gam create admin ... expires').
     - 2.46: the same local date/time entry is now used by Groups > Add a
       member who expires on a date, Chrome Browsers & Policies > Create a
       browser enrollment token (optional expiration), Calendars > Create
       focus time (a date plus local start and end times), and Google Tasks
       & Keep > Create a task (the due date is date-only and is written as
       midnight UTC with NO time-zone shift, so it never moves a day).
     - "List admin role assignments" shows the end time in the
       expirationDetails.expireTime column (in gam.cfg's time zone - UTC
       unless you changed it).

   PASSWORDS ARE MASKED IN THE LOG: the value after any "password" keyword
   (new-user and reset passwords, S/MIME certificate passwords) is written to
   the session log as ******** . The command that runs is not changed.

   REQUIRED FREE-TEXT BOXES: a few tasks have a required free-text box (for
   example "Which events" on Purge specific events, or "Changes" on Update a
   building). Time values follow GAM's formats: a full time needs a time
   zone, e.g. 2027-01-05T09:00:00-06:00 (or Z for UTC); a Google Tasks due
   date is written 2027-01-15T00:00:00Z; many time fields also accept a
   relative value such as +90d. GAMGUI refuses to build the command if that box is empty,
   because leaving it off could change what GAM does (purge events with no
   selector purges EVERY event on the calendar). When a value in one of these
   boxes contains spaces, wrap it in DOUBLE quotes, e.g. query "Old Meeting".

   INCIDENT RESPONSE (Email Cleanup category): search every mailbox (or a
   domain / OU / group) for a malicious message (read-only preview), then
   trash or permanently delete matches with a per-mailbox limit as a seatbelt.
   The "Full incident-response workflow" runs the complete cleanup: 1) a scoped
   search saved to an evidence CSV, 2) a confirmation showing the hit count and
   requiring you to type DELETE, 3) deletion by exact Message-ID when available
   (falling back to the From+Subject query), 4) optional Drive sweep of the
   attachment, and 5) Gmail/Drive audit report pulls for the lookback window.
   All evidence is saved to a timestamped Incident folder under Logs, and
   canceling at the confirmation keeps the evidence while deleting nothing.

   For every task GAMGUI:
     - Builds the exact gam command from your form entries
     - Shows it in an editable preview BEFORE anything runs (so you learn the
       command, and can tweak it)
     - Runs it through YOUR gam executable and streams the output live
     - Requires an extra typed/dialog confirmation for destructive actions
     - Logs everything to a session log file

   GAMGUI never talks to Google itself and holds no credentials. All authority
   comes from your existing GAM authorization. If GAM is not set up, GAMGUI
   cannot do anything.

2. REQUIREMENTS
   - Windows 10/11 (prebuilt app). From source: any OS with Python 3.10+ and
     tkinter (macOS/Linux work too; see item 3).
   - GAM7 installed and authorized for your domain.
   - Admin rights: only whatever your gam commands themselves need. (Updating
     the Setup.exe install also needs Windows administrator rights - see item 9.)
   - Network access: what gam itself uses, plus api.github.com / github.com for
     the optional update check.

   FOR NON-TECHNICAL USERS: see HOW-TO-GUIDE.txt in this folder - a full
   plain-English walkthrough written for coworkers who have never used GAM or a
   command line. Hand that file to new users before their first use.

3. HOW TO GET AND RUN IT
   From the Releases page (https://github.com/GuruGabe/GAM-GUI-Overlay/releases)
   choose ONE Windows option:

   PORTABLE (recommended for a folder or network share):
     a. Download GAMGUI-<version>-Windows.zip and unzip it.
     b. Keep the whole GAMGUI\ folder together (GAMGUI.exe needs the _internal\
        folder next to it). A good home is C:\GAM7\GAMGUI\.
     c. Launch GAMGUI.exe. gam.exe is found automatically when GAM is installed
        normally (C:\GAM7). If not, click "Locate gam.exe..." (top right); the
        choice is saved in gamgui.ini.

   INSTALLER:
     a. Download GAMGUI-<version>-Setup.exe and run it (needs admin rights).
     b. It installs to Program Files, creates Start-Menu and desktop shortcuts,
        and registers in Add/Remove Programs. Launch it from the shortcut.

   Windows may warn about an unrecognized app because it is not code-signed;
   choose "More info -> Run anyway".

   macOS (.dmg) and Linux (.deb / .rpm / .tar.gz) builds are attached to each
   release as well.

   MACOS FIRST LAUNCH: GAMGUI is not signed with a paid Apple Developer ID or
   notarized, so macOS warns once ("cannot be verified"):
     - macOS 15 Sequoia and later: open it, click Done, then System Settings
       -> Privacy & Security -> "GAMGUI was blocked..." -> Open Anyway, and
       enter your password.
     - macOS 14 and earlier: right-click (Control-click) GAMGUI -> Open ->
       Open.
     - Or in Terminal: xattr -dr com.apple.quarantine /Applications/GAMGUI.app
   Releases 2.49 and earlier had a packaging bug that made macOS say the app
   is "DAMAGED" - fixed in 2.50; download 2.50 or later.

   MACOS: POINTING GAMGUI AT GAM AND gam.cfg (2.52): an app opened from
   Finder or the Dock does not get the Terminal's PATH or a GAMCFGDIR set in
   ~/.zshrc. GAMGUI now also looks for gam in GAM7's default ~/bin/gam7/gam.
   If your gam.cfg is not in ~/.gam, click Locate gam.cfg... (top right,
   2.54) and pick it (Cmd+Shift+. shows hidden folders; Cmd+Shift+G types a
   path). Check any download
   against the SHA-256 in its release notes (shasum -a 256 <file>).

   FROM SOURCE (Windows/macOS/Linux):
     a. Install Python 3.10+ (python.org; on Linux also install python3-tk).
     b. python GAMGUI.py

   BUILDING THE APP YOURSELF (Windows):
     a. py -m pip install pyinstaller
     b. Run Build-EXE.bat. It first runs extract_tcl.py (which pulls the
        Tcl/Tk 9 libraries out of the DLL's zip filesystem - required on
        Python 3.14, or the build crashes with "_tcl_data not found"), then
        builds the one-folder app with those libraries bundled.
     c. The result is dist\GAMGUI\ - copy the whole folder to its home.
     The one-folder (not single-file) layout is intentional: the single-file
     build crashed intermittently on Python 3.14 (Tcl/Tk 9).

4. OPTIONS AND SETTINGS
   GAMGUI takes no command line parameters. Settings live in gamgui.ini (next
   to the program for a portable copy, or in %LOCALAPPDATA%\GAMGUI for an
   installed copy that cannot write to Program Files):
     - gam_path       : the gam executable to use (set via Locate gam.exe...).
                        If blank or missing, GAMGUI looks next to itself, on
                        the PATH, then in GAM7's default install folder
                        (C:\GAM7 on Windows; ~/bin/gam7 on macOS/Linux).
     - gam_cfg_dir    : Locate gam.cfg... (top right, or the Settings menu)
                        - the folder holding the gam.cfg you picked (GAM only
                        reads a file named exactly gam.cfg). When set, GAMGUI sets the
                        GAMCFGDIR environment variable for every gam it starts
                        and writes it into saved scripts (which stop with exit
                        code 3 if gam.cfg is missing there). Blank = GAM's own
                        default: GAMCFGDIR if set, else ~/.gam (checked in
                        GAM's source). The top bar shows the folder in use and
                        why; Settings -> Where is my gam.cfg? explains it.
     - dark_mode      : View -> Dark mode (a soft low-contrast dark theme).
     - check_updates  : Help -> Check for updates at startup (on by default).
     - text_size      : View -> Larger text / Smaller text / Normal text size
                        (Ctrl +, Ctrl -, Ctrl 0). A step number from 0 to 6;
                        1 is normal size.
   Favorites and the Recent list are kept in gamgui_tasklists.json in the same
   folder as gamgui.ini. Deleting that file simply empties both lists.

   BROWSER VERSION (gam_web.py) - 2.48 CHANGES:
     - SECURITY: only GAM Web's own page can use it. A random session token
       is created at each start and written into the page; every API request
       must send it (X-GAMWeb-Token header), must be JSON, and must arrive
       with an expected Host (localhost, 127.0.0.1, a Google Cloud Shell
       preview host, or one listed in the GAMWEB_ALLOWED_HOSTS environment
       variable). Before this, another web page open in the same browser
       could have sent commands to http://127.0.0.1:<port>/api/run.
     - FIX: typing quickly could leave an OLDER build of the command in the
       preview - and Run would use it. Each build is now numbered and only
       the newest one counts.
     - Date/time tasks convert in the VIEWER's time zone (sent by the
       browser), not the server's. If the server cannot resolve that zone and
       its own offset differs, it refuses with a clear message instead of
       producing a wrong time (install Python's 'tzdata' package to fix).
     - Added a task search box, a GAM docs link per task, and pre-filled
       defaults (Windows-only default paths are left blank on Linux).

   RUN ANY TASK FOR EVERY ROW OF A CSV (2.47): open a task, click "Run for
   each CSV row...", and pick a CSV whose first row holds column names. For
   each box choose the CSV column that holds its value, or keep the form
   value (same for every row). GAMGUI builds ONE command -
     gam csv <file> [maxrows N] gam <the task, with ~Column for mapped boxes>
   - shows it in the preview, and you click Run (destructive tasks still
   confirm). Details:
     - A mapped box becomes ~Column, or ~~Column~~ when the value sits inside
       a larger argument (GAM's documented CSV substitution).
     - "Test run: only the first N rows" adds maxrows N - try a few rows first.
     - Output: Screen, or ONE CSV file / ONE Google Sheet for all rows (GAMGUI
       uses GAM's 'redirect csv ... multiprocess' outside the loop).
     - The Section dropdown is applied INSIDE the loop ('gam select <section>'
       on each row), because GAM does not carry an outer select into it.
     - Dropdowns, the advanced box, and boxes GAMGUI translates (license
       names, dates/times, scope pickers) cannot vary per row.
     - Changing a box in the form afterwards rebuilds the single-run command;
       click "Run for each CSV row..." again to rebuild the bulk one.

   STAFF DEPARTURE HAND-OFF (2.57): Users -> Staff departure hand-off. One
   run hands a departing staff member's account to the person taking over.
   Each step is a Yes/No choice:
     - mailbox delegation      gam user <old> delegate to <new>
     - calendar editor         gam calendar <old> add editor <new>
     - forwarding (keep copy)  gam user <old> add forwardingaddress <new>
                               gam user <old> forward on keep <new>
     - auto-reply              gam user <old> vacation on subject ... message
                               ... (#old# / #new# filled in; \n = new line)
     - Drive transfer          gam create datatransfer <old> drive <new> all
                               (Google Data Transfer: private + shared files,
                               runs in the background at Google)
     - remove from ALL groups  gam user <old> delete groups   (default No)
   Afterwards the old account is one of:
     - Kept ACTIVE but locked: gam update user <old> password random, then
       gam user <old> deprovision popimap signout (no turnoff2sv: it fails
       where 2SV is enforced, and the password already locks the account -
       found in the live test). Forwarding and
       the auto-reply keep working; it still uses a license. The random
       password is not shown or logged (GAM only writes it out with
       'logpassword').
     - SUSPENDED: gam update user <old> suspended on. Google's help page
       "Suspend a user temporarily" says new email to a suspended user is
       blocked, so forwarding and the auto-reply stop - the confirmation
       says so when forwarding / auto-reply are on.
     - Put back the way it was.
   Delegation, calendar sharing, forwarding and the auto-reply act AS the old
   user, so a suspended / archived old account is enabled first (only when
   one of those steps is on). If the run stops early (Stop, an error), the
   account is put back to its original state. The preview lists every gam
   command; you type HANDOFF to run it; a summary shows OK / FAILED per step.
   Both accounts are looked up before anything changes.
   LIVE-TESTED (2.58) on two throwaway accounts in a test OU (created and
   deleted for the test): delegation "accepted", calendar ACL "writer" (GAM's
   name for editor), forwarding + auto-reply (blank line from \n kept), the
   Drive file changed owner (transfer "completed"), and a real test message
   reached the new account both forwarded and with the auto-reply. Found and
   fixed by that test:
     - 'turnoff2sv' FAILS where 2-Step Verification is ENFORCED by policy, so
       the lock step no longer uses it (the random password locks the
       account; app passwords, backup codes, tokens and POP/IMAP are still
       removed and the user is signed out).
     - Right after an account is switched back on, Gmail can answer
       "Delegator user is disabled" for a moment: the step is retried every
       15 seconds, up to 4 times.
     - Running a hand-off again: "already exists" (delegate / forwarding
       address already there) is shown as "OK (was already set)".

   REPORT BUILDER (2.53): Reports -> Report builder... writes ONE script
   that runs any mix of ready-made reports: a Windows batch file for Task
   Scheduler, or (2.55) a macOS / Linux bash script for cron.
   Each report is saved as CSV files in
       <output folder>\<report name>\<MM-DD-YYYY>\
   Reports: Admin activity (one file per admin, plus automatic-... files for
   SYSTEM / Security Center / device actions, plus _all-admin-activity.csv),
   Group membership changes, Password changes, Sign-ins from outside your
   countries, Accounts disabled for a leaked password, Suspicious sign-ins,
   Users with many failed sign-ins, Storage used per user, Active accounts
   not signed in lately, Accounts without 2-Step Verification, Suspended
   accounts, Chromebooks not used lately.
   Added in 2.59: Files shared outside your domains (Drive audit log,
   change_document_visibility + change_user_access). You list your own
   domains (sub-domains are included, so example.org also covers
   students.example.org) and, optionally, partner domains to ignore. A row
   is kept when a PERSON outside those domains got access, or (optional)
   when a file was opened to anyone with the link / the web. GAMGUI does not
   rely on Google's 'visibility_change = external' flag: in a live test it
   also marked many shares to people inside the domain. It uses the plain
   list form of GAM's row filters - the JSON form of
   csv_output_row_drop_filter was silently ignored in the same test.
   Added in 2.56: Admin role changes, App access and SSO changes (both
   alert reports), Account changes, and Accounts using the default profile
   picture (one OU and its sub-OUs, or all active accounts - uses the _ns
   selectors so suspended accounts are skipped). Every event name in these
   reports was checked one by one against the live Reports API: an unknown
   name makes the whole report fail ("Event ... not found in manifest").
     - Every command starts with "config timezone local", so "Yesterday" is
       the local calendar day (GAM's default is the UTC day) and times in
       the CSVs are local.
     - "One file per admin" = one GAM call for the whole day, then PowerShell
       splits it by the admin's email (actor.email), so the per-admin files
       always add up to the day. (A per-admin GAM loop was tested and
       rejected: GAM's csv loop does not pass the local time zone to its
       child processes, so those files covered the UTC day instead.)
     - The out-of-country report uses networkInfo.regionCode, the country
       Google records for each sign-in. No IP addresses go to any third
       party.
     - Folder dates come from PowerShell, so they do not depend on the PC's
       regional date format.
     - Output folder: blank = a Reports folder next to the script. Clean-up
       (optional): dated folders older than N days are deleted - only
       folders named MM-DD-YYYY inside this script's own report folders.
     - Log: Logs\<script name>.log next to the script. A failed report is
       logged and the rest still run. Exit codes: 0 all worked, 1 a report
       failed, 2 gam.exe missing, 3 gam.cfg missing (when a GAM config folder
       is set), 4 could not read the date.
     - The script's first comment block holds its settings (one base64
       line); "Open a saved report script..." reads it back for editing.
     - The window remembers your last choices (gamgui.ini report_builder).
     - Scheduling: Task Scheduler > Create Task; "Run whether user is logged
       on or not" as an account that can read the GAM config folder; Daily
       trigger after midnight; Action = Start a program > the .bat.
     - Keep the .bat in a folder whose path has no & ( ) % ^ ! - cmd.exe,
       which Task Scheduler uses to start it, drops the quotes around such a
       path. GAMGUI warns before saving there (Save as script too).
     - SECURITY: the reports hold names, emails, sign-in IPs and locations.
       Keep the output folder readable only by IT.
     - GOOGLE SHEETS (2.54): each report can also replace one tab of an
       existing Google Sheet (paste the sheet's link or file ID; tab blank =
       the report's name). GAM arguments: todrive tdfileid <id> tdretaintitle
       true tdsheet <tab> tdupdatesheet true tdnobrowser true tdnoemail true
       tdlocalcopy true [tduser <Sheets account>]. tdlocalcopy matters: with
       todrive, GAM writes no local CSV without it (checked in GAM's source).
       A wrong file ID fails that report before any data is read ("Drive
       File ID: ..., Not Found", exit 2) - check the log after the first run.
       Tested live: the tab read back from Google matched the local CSV.
     - EMAIL SUMMARY (2.54): Never / Every run / Only when an alert report
       finds something (alert reports: sign-ins outside your countries,
       leaked-password lockouts, suspicious sign-ins, many failed sign-ins;
       a failed report also triggers it). Body = Logs\<name>-summary.txt (row
       count per report). Optional attachments: each report's main CSV when
       it has rows and is 5 MB or less. Sent with 'gam sendemail <to>
       [from <addr>] subject ... file <summary> attach ...' as GAM's admin
       account (or From), so no SMTP password is stored. Tested live.
     - Every run writes Logs\<name>-summary.txt, emailing or not.
     - MACOS / LINUX (2.55): Script type = "macOS / Linux shell script (.sh)"
       writes a bash script that does the same things. It uses only what a
       stock Mac has: bash 3.2, the system awk, and date (it tries GNU
       'date -d' first, then BSD 'date -v'). "One file per admin" is split
       by a small awk CSV reader (quoted commas, doubled quotes and line
       breaks inside values are handled; records are copied unchanged).
       Schedule it with cron, e.g. crontab -e, then add this line:
           0 1 * * * '/full/path/GAM-Daily-Reports.sh'
       The .sh can be made on any system (e.g. on Windows for a Linux
       server). Tested with real bash, awk in strict POSIX mode, and a
       stand-in for BSD date; a live run on a real tenant split 67,048 admin
       events into 13 files with every event in the right file.

   SAVE AS SCRIPT (2.51): the "Save as script..." button (next to Copy)
   saves the command in the preview as a script that runs it exactly:
     - Windows: a .bat with a standard header block, @ECHO OFF / SETLOCAL, a
       GAM path line you can edit, and a log at Logs\<script name>.log next
       to the script (MM-DD-YYYY HH:MM:SS start/end lines, GAM's output, and
       the exit code). The script exits with GAM's exit code, so Task
       Scheduler can report failures. CRLF line endings.
     - macOS / Linux: a .sh (bash) with the same logging; schedule with cron.
     - Special characters (& | < > ^ % quotes) are escaped so cmd.exe passes
       every argument to GAM unchanged - proven by running generated scripts
       through the real cmd.exe (tests/test_script_export.py).
     - WARNINGS before saving: a command containing a password (it would be
       stored in plain text in the script), and destructive tasks (a script
       runs without the confirmation GAMGUI normally shows).
     - The Section dropdown's choice is included in the script.
     - Multi-step workflows (incident response, bulk license, etc.) cannot be
       saved as one script.

   SEARCH, SHORTCUTS, AND SAVING OUTPUT (2.49):
     - Search matches every word you type against the task's name, category,
       description, AND its GAM command - e.g. "cigroup" or "vacation".
     - Ctrl+F = search box; Enter (in the search box) = open the first match;
       Esc = clear the search; Ctrl+Enter = Run (same confirmations as the
       button); F1 = GAM docs for the open task.
     - "Save output..." writes the output pane to a .txt file exactly as
       shown - it may contain names, addresses, or a password GAM printed, so
       store it with care.

   DATES IN 2.49: Security > "Create an email monitor" now takes a local end
   date/time (converted to UTC 'YYYY-MM-DD HH:MM', the form GAM passes to the
   Email Audit API, which documents UTC dates). The dormant-users report date
   accepts MM-DD-YYYY as well as YYYY-MM-DD. Every date/time box in GAMGUI now
   takes normal local entries.

   WORKING FASTER (2.44):
     - FAVORITES: click "+ Favorite" (or right-click a task) to pin it at the
       top of the task list; "- Favorite" or right-click removes it.
     - RECENT: the last 10 tasks you ran appear under "Recent". Right-click
       the Recent heading to clear the list.
     - LIVE PREVIEW: the command preview rebuilds a moment after you type in
       any box. (If you hand-edit the preview and then change a box, the
       preview is rebuilt from the boxes.)
     - GAM DOCS: opens the GAM wiki page that documents the task you are on.
     - BROWSE...: file pickers for non-CSV files (.eml, .pem, .p12, images,
       JSON) now list All files instead of only CSV files.
   In a form, fields marked * are required; others are optional and are simply
   omitted from the command when left blank.

   OUTPUT DESTINATION: any task that lists or exports results has a "Save
   results to" dropdown - the screen, a Google Sheet, or a CSV file on your PC.

   MULTIPLE DOMAINS: the Section dropdown at the top (named "Domain" before
   2.54; renamed on the suggestion of GAM developer Ross Scroggs, since it
   picks a gam.cfg section) runs a command against a
   chosen gam.cfg section (tenant) without changing your saved default - handy
   for MSPs. Single-domain setups just see "(default)".

5. WHAT IT CHANGES / SIDE EFFECTS
   GAMGUI itself changes nothing except writing gamgui.ini,
   gamgui_tasklists.json (Favorites / Recent), and log files. The
   gam commands you run change whatever they say they change - the preview box
   always shows the exact command first. Destructive tasks (delete/suspend/
   deprovision a user; delete a group/OU/course; powerwash/wipe/deprovision a
   device; sync membership; trash/delete messages; transfer a Drive; remove
   access/licenses; and the bulk equivalents) pop a confirmation showing the
   full command before running.

6. LOG FILES
   Logs\GAMGUI_MM-DD-YYYY_HH-MM-SS.log - one per session. Contains timestamps,
   every command run, all output, and exit codes. Note that a password you type
   into a "create user ... password X" form WILL appear in the log and on
   screen - prefer the random-password option (GAM generates it server-side),
   and treat any CSV that contains plaintext passwords as sensitive: store it
   safely and delete it after provisioning. Keep or purge logs per your
   organization's retention practice.

7. TROUBLESHOOTING
   "gam.exe not found"      - Click Locate gam.exe and browse to it.
   gam works in Terminal but not in GAMGUI (macOS), or the wrong tenant is
   used                     - Locate gam.cfg... (top right) and pick your
                              gam.cfg. Confirm with
                              Diagnostics > GAM version (Config File: line).
   Output shows auth errors - Run a Diagnostics task (e.g. Authorization check);
                              re-authorize GAM if scopes are missing.
   Window frozen            - It should never freeze (commands run on a
                              background thread); long commands just take long.
                              Use Stop to kill a runaway command.
   "(Missing required value)" in the preview - fill in the starred fields.
   Bulk task did nothing    - Check the scope picker: it needs a value (an OU
                              path, a group, a query, or a file:column) unless
                              you chose "ALL".
   Update did not run       - See item 9. An installed copy needs an admin (UAC)
                              prompt; a portable copy must be closed first.

8. KNOWN LIMITATIONS
   - The guided forms cover the common options; the "Extra arguments (advanced)"
     box on each task and the "Run ANY GAM command (advanced)" console cover the
     long tail of GAM's thousands of command permutations.
   - Commands run WITHOUT a shell: arguments go straight to gam, so characters
     like & | > < and quotes inside subjects and queries are always safe. The
     trade-off: shell pipes (|) and > redirection do not work in the console -
     use GAM's own "redirect csv ./file.csv" or "todrive" instead.
   - GAM cannot create or grade Classroom assignments (a Classroom API limit),
     so those are not offered.
   - The preview is editable by design; treat it like a terminal and do not
     paste commands you do not understand.
   - English only.

9. KEEPING GAMGUI UP TO DATE
   IN-APP (easiest): GAMGUI checks for a newer release at startup (if online)
   and asks whether to update. Click Yes and it closes, updates itself, and
   reopens - it never updates without your OK. A portable copy updates in
   place (keeping gamgui.ini, gamgui_tasklists.json, and Logs); an installed
   copy re-runs the installer
   with a Windows administrator (UAC) prompt. You can also use Help -> Check
   for updates now..., and toggle the startup check under Help.

   MANUAL (bundled script): updategamgui.ps1 in the app folder is what the
   in-app updater runs. Run it yourself, e.g. a weekly scheduled task:
       powershell -ExecutionPolicy Bypass -File "C:\GAM7\GAMGUI\updategamgui.ps1" -Quiet
   It auto-detects a portable copy, a Setup.exe install, or both, and updates
   each one that is behind. Switches: -InstallType auto|zip|exe|both,
   -InstallRoot "<path>", -Force, -Launch, -Quiet. Every download is verified
   against a SHA-256 published in the release notes. Update activity is logged
   to <install>\Logs\GAMGUI-Update.log.
================================================================================
